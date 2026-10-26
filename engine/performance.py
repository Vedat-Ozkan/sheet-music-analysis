from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from bisect import bisect_right
from dataclasses import dataclass

from engine.render import load_toolkit
from engine.score import MEI, XML_ID, ScoreIndex

LEVELS = {"ppp": 30, "pp": 42, "p": 55, "mp": 66, "mf": 78, "f": 92, "ff": 105, "fff": 118}
ACCENTS = {"sf": 20, "sfz": 20, "sffz": 24, "fz": 18, "rf": 14, "rfz": 16, "z": 16}
DEFAULT_LEVEL = 66
SWELL = 15
ORNAMENT_NOTE_MS = 70
NATURAL = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
LETTERS = "cdefgab"
ALTER = {"s": 1, "f": -1, "n": 0, "x": 2, "ss": 2, "ff": -2}
SHARP_ORDER, FLAT_ORDER = "fcgdaeb", "beadgcf"
UPPER_NOTE_TRILLS = {"bach", "handel", "händel", "vivaldi", "scarlatti", "telemann", "couperin", "rameau", "purcell", "corelli", "haydn", "mozart", "clementi"}


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    velocity: int = DEFAULT_LEVEL


def performance_midi(score: bytes, measures: tuple[int, int] | None = None) -> bytes:
    toolkit = load_toolkit(score, keep_pedals=True)
    mei = toolkit.getMEI()
    root = ET.fromstring(mei)
    index = ScoreIndex(mei)
    timemap = toolkit.renderToTimemap({"includeMeasures": True})
    clock = _Clock(timemap)

    bars = list(root.iter(f"{MEI}measure"))
    bar_ids = [bar.get(XML_ID) for bar in bars]
    meters = {segment.id: measure.meter for measure in index.measures for segment in measure.segments}
    starts = {entry["measureOn"]: entry["qstamp"] for entry in timemap if "measureOn" in entry}

    def at(bar_id: str, tstamp: str) -> float:
        unit = int((meters.get(bar_id) or "4/4").split("/")[1])
        return starts.get(bar_id, 0.0) + (float(tstamp) - 1) * 4 / unit

    def later(bar_id: str, tstamp2: str) -> float:
        ahead, beat = re.fullmatch(r"(\d+)m\+([\d.]+)", tstamp2).groups()
        position = min(bar_ids.index(bar_id) + int(ahead), len(bar_ids) - 1)
        return at(bar_ids[position], beat)

    notes = _notes(toolkit, timemap, root, clock)
    marks, pedals, ornaments = [], [], {}
    for bar in bars:
        bar_id = bar.get(XML_ID)
        for element in bar:
            tag = element.tag.replace(MEI, "")
            if tag == "dynam" and element.get("tstamp"):
                text = re.sub(r"[\s.]", "", "".join(element.itertext())).lower()
                marks.append((at(bar_id, element.get("tstamp")), text, None))
            elif tag == "hairpin" and element.get("tstamp") and element.get("tstamp2"):
                marks.append((at(bar_id, element.get("tstamp")), element.get("form"), later(bar_id, element.get("tstamp2"))))
            elif tag == "pedal" and element.get("tstamp"):
                pedals.append((at(bar_id, element.get("tstamp")), element.get("dir")))
            elif tag in ("trill", "mordent", "turn") and element.get("startid"):
                ornaments[element.get("startid").lstrip("#")] = element

    loudness = _Loudness(sorted(marks, key=lambda mark: mark[0]), clock)
    for note in notes.values():
        note.velocity = loudness.at(note.start)
    key = _key_alterations(index.key_signature)
    spelling = _spelling(bars)
    upper_start = _starts_trills_above(root)
    performed = []
    for note_id, note in notes.items():
        ornament = ornaments.get(note_id)
        if ornament is None:
            performed.append(note)
            continue
        upper = _neighbour(note_id, 1, ornament.get("accidupper"), spelling, notes, key)
        lower = _neighbour(note_id, -1, ornament.get("accidlower"), spelling, notes, key)
        kind = ornament.tag.replace(MEI, "")
        performed.extend(_ornamented(note, kind, ornament.get("form", "upper"), upper, lower, upper_start))

    window = (0.0, max(note.end for note in performed))
    if measures:
        first, last = (int(part) for part in index.measure_range(*measures).split("-"))
        chosen = {note.get(XML_ID) for bar in bars[first - 1 : last] for note in bar.iter(f"{MEI}note")}
        kept = [note for note_id, note in notes.items() if note_id in chosen]
        if kept:
            window = (min(note.start for note in kept), max(note.end for note in kept))
        performed = [note for note in performed if window[0] - 1 <= note.start <= window[1]]
    pedal_events, down = [], False
    for q, direction in sorted(pedals):
        time, value = clock.ms(q), 127 if direction == "down" else 0
        if time < window[0]:
            down = bool(value)
        elif time <= window[1]:
            pedal_events.append((time, value))
    if down:
        pedal_events.insert(0, (window[0], 127))
    return _write(performed, pedal_events, window[0])


class _Clock:
    def __init__(self, timemap: list[dict]):
        self.points = sorted({(entry["qstamp"], entry["tstamp"]) for entry in timemap})
        self.quarters = [q for q, _ in self.points]

    def ms(self, q: float) -> float:
        position = max(bisect_right(self.quarters, q) - 1, 0)
        q0, t0 = self.points[position]
        if position + 1 < len(self.points):
            q1, t1 = self.points[position + 1]
            return t0 + (q - q0) * (t1 - t0) / (q1 - q0)
        if position > 0:
            qp, tp = self.points[position - 1]
            return t0 + (q - q0) * (t0 - tp) / (q0 - qp)
        return t0 + (q - q0) * 1000


def _notes(toolkit, timemap: list[dict], root: ET.Element, clock: _Clock) -> dict[str, Note]:
    tied = {tie.get("endid", "").lstrip("#"): tie.get("startid", "").lstrip("#") for tie in root.iter(f"{MEI}tie")}
    for note in root.iter(f"{MEI}note"):
        if note.get("tie") in ("m", "t") and note.get(XML_ID) not in tied:
            tied[note.get(XML_ID)] = None
    on, off = {}, {}
    for entry in timemap:
        for note_id in entry.get("on", []):
            on[note_id] = entry["tstamp"]
        for note_id in entry.get("off", []):
            off[note_id] = entry["tstamp"]
    notes = {}
    for note_id, start in on.items():
        head = note_id
        while head in tied and tied[head]:
            head = tied[head]
        end = off.get(note_id, start + 100)
        if head != note_id and head in notes:
            notes[head].end = max(notes[head].end, end)
            continue
        notes[note_id] = Note(start, end, toolkit.getMIDIValuesForElement(note_id)["pitch"])
    return notes


class _Loudness:
    def __init__(self, marks: list[tuple[float, str, float | None]], clock: _Clock):
        self.levels, self.accents, self.swells = [], [], []
        for q, text, end in marks:
            moment = clock.ms(q)
            if end is not None or text in ("cresc", "crescendo", "dim", "dimin", "diminuendo", "decresc"):
                rising = text.startswith("cres")
                self.swells.append((moment, clock.ms(end) if end is not None else None, rising))
            elif text == "fp":
                self.accents.append((moment, LEVELS["f"] - LEVELS["p"]))
                self.levels.append((moment, LEVELS["p"]))
            elif text in LEVELS:
                self.levels.append((moment, LEVELS[text]))
            elif text in ACCENTS:
                self.accents.append((moment, ACCENTS[text]))
        self.levels.sort()
        self.times = [time for time, _ in self.levels]

    def level(self, ms: float) -> int:
        position = bisect_right(self.times, ms) - 1
        return self.levels[position][1] if position >= 0 else DEFAULT_LEVEL

    def at(self, ms: float) -> int:
        value = float(self.level(ms))
        for begin, end, rising in self.swells:
            following = next((time for time in self.times if time > begin), None)
            finish = end if end is not None else following if following is not None else begin + 4000
            if not begin <= ms < finish:
                continue
            target = self.level(following) if following is not None and following <= finish + 1000 else self.level(begin) + (SWELL if rising else -SWELL)
            value += (target - self.level(begin)) * (ms - begin) / max(finish - begin, 1)
        for moment, boost in self.accents:
            if abs(ms - moment) < 40:
                value += boost
        return max(1, min(127, round(value)))


def _key_alterations(signature: str) -> dict[str, int]:
    alterations = dict.fromkeys(LETTERS, 0)
    match = re.fullmatch(r"(\d+)([sf])", signature or "")
    if match:
        count, kind = int(match.group(1)), match.group(2)
        for letter in (SHARP_ORDER if kind == "s" else FLAT_ORDER)[:count]:
            alterations[letter] = 1 if kind == "s" else -1
    return alterations


def _spelling(bars: list[ET.Element]) -> dict[str, tuple[str, str, str, int, str | None]]:
    spelling = {}
    for bar in bars:
        for staff in bar.iter(f"{MEI}staff"):
            for note in staff.iter(f"{MEI}note"):
                accid = note.get("accid") or next((child.get("accid") for child in note.iter(f"{MEI}accid")), None)
                spelling[note.get(XML_ID)] = (bar.get(XML_ID), staff.get("n"), note.get("pname"), int(note.get("oct")), accid)
    return spelling


def _starts_trills_above(root: ET.Element) -> bool:
    composers = " ".join("".join(name.itertext()) for name in root.iter(f"{MEI}persName") if name.get("role") == "composer")
    return any(word in UPPER_NOTE_TRILLS for word in re.findall(r"\w+", composers.lower()))


def _neighbour(note_id: str, direction: int, printed: str | None, spelling: dict, notes: dict[str, Note], key: dict[str, int]) -> int:
    bar, staff, letter, octave, _ = spelling[note_id]
    position = LETTERS.index(letter) + direction
    letter, octave = LETTERS[position % 7], octave + position // 7
    if printed in ALTER:
        alteration = ALTER[printed]
    else:
        earlier = [
            (notes[other].start, ALTER[accid])
            for other, (other_bar, other_staff, other_letter, other_octave, accid) in spelling.items()
            if (other_bar, other_staff, other_letter, other_octave) == (bar, staff, letter, octave)
            and accid in ALTER and other in notes and notes[other].start < notes[note_id].start
        ]
        alteration = max(earlier)[1] if earlier else key[letter]
    return 12 * (octave + 1) + NATURAL[letter] + alteration


def _ornamented(note: Note, kind: str, form: str, upper: int, lower: int, upper_start: bool) -> list[Note]:
    length = note.end - note.start
    step = min(ORNAMENT_NOTE_MS, length / 4)
    if kind == "trill":
        pairs = max(int(length // step - 1) // 2, 1)
        pitches = [upper, note.pitch] * pairs if upper_start else [note.pitch, upper] * pairs + [note.pitch]
    elif kind == "mordent":
        pitches = [note.pitch, upper if form == "upper" else lower, note.pitch]
    else:
        pitches = [upper, note.pitch, lower, note.pitch] if form == "upper" else [lower, note.pitch, upper, note.pitch]
    played = []
    for position, pitch in enumerate(pitches):
        start = note.start + position * step
        end = note.end if position == len(pitches) - 1 else start + step
        played.append(Note(start, end, pitch, note.velocity))
    return played


def _write(notes: list[Note], pedals: list[tuple[float, int]], offset: float) -> bytes:
    events = []
    for note in notes:
        events.append((note.start, 1, bytes((0x90, note.pitch, note.velocity))))
        events.append((max(note.end, note.start + 20), 0, bytes((0x80, note.pitch, 0))))
    for time, value in pedals:
        events.append((time, 2 if value else 0, bytes((0xB0, 64, value))))
    track = bytearray(b"\x00\xff\x51\x03" + (1_000_000).to_bytes(3, "big"))
    now = 0
    for time, _, data in sorted(events, key=lambda event: (event[0], event[1])):
        tick = max(round(time - offset), 0)
        track += _length(tick - now) + data
        now = tick
    track += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 1000) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def _length(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))
