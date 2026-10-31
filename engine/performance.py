from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction

from engine.render import load_toolkit
from engine.score import LETTERS, MEI, SEMITONES, XML_ID, Event, Mark, Measure, ScoreIndex

LEVELS = {"ppp": 30, "pp": 42, "p": 55, "mp": 66, "mf": 78, "f": 92, "ff": 105, "fff": 118}
ACCENTS = {"sf": 20, "sfz": 20, "sffz": 24, "fz": 18, "rf": 14, "rfz": 16, "z": 16}
SWELLS = ("cresc", "crescendo", "dim", "dimin", "diminuendo", "decresc")
DYNAMICS = {*LEVELS, *ACCENTS, "fp", *SWELLS}
DEFAULT_LEVEL = 66
DEFAULT_TEMPO = 120.0
TEMPO_WORDS = {"grave": 40, "largo": 50, "larghetto": 60, "lento": 60, "adagio": 66, "adagietto": 76, "andante": 80,
               "andantino": 90, "moderato": 100, "allegretto": 112, "allegro": 132, "vivace": 150, "presto": 170,
               "prestissimo": 190}
SWELL = 15
ORNAMENT_NOTE_MS = 70
SLASHED_GRACE_MS = 30
ALTER = {"s": 1, "f": -1, "n": 0, "x": 2, "ss": 2, "ff": -2}
SHARP_ORDER, FLAT_ORDER = "FCGDAEB", "BEADGCF"
TEXT_VERSION, TEXT_UNIT_MS = "P1", 10
UPPER_NOTE_COMPOSERS = {"bach", "handel", "händel", "vivaldi", "scarlatti", "telemann", "couperin", "rameau", "purcell", "corelli", "haydn", "mozart", "clementi"}
ORNAMENT_CODES = {("trill", "upper"): "tr", ("trill", "lower"): "tr", ("mordent", "upper"): "mu", ("mordent", "lower"): "ml",
                  ("turn", "upper"): "tu", ("turn", "lower"): "tl"}


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    velocity: int = DEFAULT_LEVEL


def performance_midi(score: bytes, measures: tuple[int, int] | None = None) -> bytes:
    return _write(*perform(marked_index(score), measures))


def performance_text(index: ScoreIndex, measures: tuple[int, int] | None = None, tempo: float | None = None) -> str:
    notes, pedals, offset = perform(index, measures, tempo)
    tokens, previous, velocity = [TEXT_VERSION], 0, None
    for note in sorted(notes, key=lambda note: (note.start, note.pitch)):
        start = max(round((note.start - offset) / TEXT_UNIT_MS), previous)
        end = round((_held(note.end, pedals) - offset) / TEXT_UNIT_MS)
        if note.velocity != velocity:
            tokens.append(f"v{note.velocity}")
            velocity = note.velocity
        tokens.append(f"{start - previous}.{max(end - start, 1)}.{note.pitch}")
        previous = start
    return " ".join(tokens)


def marked_index(score: bytes) -> ScoreIndex:
    mei = load_toolkit(score, keep_pedals=True).getMEI()
    root = ET.fromstring(mei)
    index = ScoreIndex(mei)
    starts = _bar_starts(index)
    bars = list(root.iter(f"{MEI}measure"))
    bar_ids = [bar.get(XML_ID) for bar in bars]
    events = {event.id: measure for measure in index.measures for event in measure.events}

    def place(bar_id: str, tstamp: str) -> tuple[Measure, Fraction]:
        measure, segment = index.locate_segment(bar_id)
        unit = int((measure.meter or index.meter or "4/4").split("/")[1])
        return measure, segment.start + max(Fraction(tstamp).limit_denominator(960) - 1, Fraction(0)) * 4 / unit

    for score_def in root.iter(f"{MEI}scoreDef"):
        if score_def.get("midi.bpm") and index.measures:
            index.measures[0].marks.append(Mark("tempo", Fraction(0), score_def.get("midi.bpm")))
        break
    worded = []
    for bar in bars:
        bar_id = bar.get(XML_ID)
        for element in bar:
            tag = element.tag.replace(MEI, "")
            tstamp = element.get("tstamp")
            if tag in ("dir", "tempo") and tstamp and not element.get("midi.bpm"):
                word = next((word for word in re.findall(r"[a-z]+", "".join(element.itertext()).lower()) if word in TEMPO_WORDS), None)
                if word:
                    measure, offset = place(bar_id, tstamp)
                    worded.append((measure, Mark("tempo", offset, word if measure.beat_length == 2 else f"{TEMPO_WORDS[word] * float(measure.beat_length):g}")))
            if tag == "dynam" and tstamp:
                measure, offset = place(bar_id, tstamp)
                text = next((word for word in re.findall(r"[a-z]+", "".join(element.itertext()).lower()) if word in DYNAMICS), None)
                if text:
                    measure.marks.append(Mark("dynamic", offset, text))
            elif tag == "hairpin" and tstamp and element.get("tstamp2") and element.get("form") in ("cres", "dim"):
                measure, offset = place(bar_id, tstamp)
                ahead, beat = re.fullmatch(r"(\d+)m\+([\d.]+)", element.get("tstamp2")).groups()
                target, target_offset = place(bar_ids[min(bar_ids.index(bar_id) + int(ahead), len(bar_ids) - 1)], beat)
                length = max(starts[id(target)] + target_offset - starts[id(measure)] - offset, Fraction(0))
                measure.marks.append(Mark("hairpin", offset, "<" if element.get("form") == "cres" else ">", length))
            elif tag == "pedal" and tstamp and element.get("dir") in ("down", "up"):
                measure, offset = place(bar_id, tstamp)
                measure.marks.append(Mark("pedal", offset, element.get("dir")))
            elif tag == "tempo" and tstamp and element.get("midi.bpm"):
                measure, offset = place(bar_id, tstamp)
                measure.marks.append(Mark("tempo", offset, element.get("midi.bpm")))
            elif tag in ("trill", "mordent", "turn") and element.get("startid", "").lstrip("#") in events:
                note_id = element.get("startid").lstrip("#")
                measure = events[note_id]
                event = next(event for event in measure.events if event.id == note_id)
                code = ORNAMENT_CODES[(tag, element.get("form", "upper"))]
                measure.marks.append(Mark("ornament", event.onset, code, pitch=event.pitch,
                                          upper=element.get("accidupper", ""), lower=element.get("accidlower", "")))
    if not any(mark.kind == "tempo" for measure in index.measures for mark in measure.marks):
        for measure, mark in worded:
            measure.marks.append(mark)
    for measure in index.measures:
        measure.marks.sort(key=lambda mark: mark.offset)
    index.ornaments_from_above = _starts_ornaments_above(root)
    return index


def unclear_tempos(index: ScoreIndex) -> list[tuple[int, str]]:
    return [(measure.number, mark.value) for measure in index.measures for mark in measure.marks
            if mark.kind == "tempo" and mark.value in TEMPO_WORDS]


def perform(index: ScoreIndex, measures: tuple[int, int] | None = None, tempo: float | None = None) -> tuple[list[Note], list[tuple[float, int]], float]:
    starts = _bar_starts(index)

    def bpm(measure: Measure, value: str) -> float:
        if value not in TEMPO_WORDS:
            try:
                return float(value)
            except ValueError:
                raise ValueError(f"Bar {measure.number} is marked {value!r}; give the tempo in quarter notes per minute "
                                 f"or as one of {', '.join(TEMPO_WORDS)}") from None
        return tempo or TEMPO_WORDS[value] * float(measure.beat_length)

    clock = _Clock([(starts[id(measure)] + mark.offset, bpm(measure, mark.value)) for measure in index.measures
                    for mark in measure.marks if mark.kind == "tempo"])
    at = {id(measure): (lambda offset, measure=measure: float(starts[id(measure)] + offset)) for measure in index.measures}
    notes, heads = _notes(index, starts, clock)

    dynamics, pedals = [], []
    for measure in index.measures:
        for mark in measure.marks:
            q = at[id(measure)](mark.offset)
            if mark.kind == "dynamic":
                dynamics.append((q, mark.value, None))
            elif mark.kind == "hairpin":
                dynamics.append((q, "cres" if mark.value == "<" else "dim", q + float(mark.length)))
            elif mark.kind == "pedal":
                pedals.append((clock.ms(q), 127 if mark.value == "down" else 0))
    loudness = _Loudness(sorted(dynamics, key=lambda mark: mark[0]), clock)
    for note, _ in notes:
        note.velocity = loudness.at(note.start)

    ornaments = {}
    for measure in index.measures:
        for mark in measure.marks:
            if mark.kind == "ornament":
                event = next((event for event in measure.events if not event.grace and event.onset == mark.offset
                              and event.pitch == mark.pitch and event.id in heads), None)
                if event:
                    ornaments[id(heads[event.id])] = (mark, measure, event)
    performed = []
    for note, _ in notes:
        if id(note) not in ornaments:
            performed.append(note)
            continue
        mark, measure, event = ornaments[id(note)]
        key = _key_alterations(measure.key_signature)
        upper = _neighbour(event, measure, 1, mark.upper, key)
        lower = note.pitch - 1 if mark.value in ("tu", "tl") and not mark.lower else _neighbour(event, measure, -1, mark.lower, key)
        performed.extend(_ornamented(note, mark.value, upper, lower, index.ornaments_from_above))

    window = (0.0, max((note.end for note in performed), default=0.0))
    if measures:
        chosen = _chosen(index, measures)
        ids = {id(measure) for measure in chosen}
        kept = [note.start for note, measure in notes if id(measure) in ids]
        window = (min(kept, default=clock.ms(float(starts[id(chosen[0])]))), clock.ms(float(starts[id(chosen[-1])] + chosen[-1].length)))
        performed = [note for note in performed if window[0] - 1 <= note.start < window[1]]
    pedal_events, down = [], False
    for time, value in sorted(pedals):
        if time < window[0]:
            down = bool(value)
        elif time <= window[1]:
            pedal_events.append((time, value))
    if down:
        pedal_events.insert(0, (window[0], 127))
    return performed, pedal_events, window[0]


def _held(end: float, pedals: list[tuple[float, int]]) -> float:
    before = [value for time, value in pedals if time <= end]
    if not before or not before[-1]:
        return end
    return next((time for time, value in pedals if time > end and not value), end)


def _bar_starts(index: ScoreIndex) -> dict[int, Fraction]:
    starts, position = {}, Fraction(0)
    for measure in index.measures:
        starts[id(measure)] = position
        position += measure.length
    return starts


def _chosen(index: ScoreIndex, measures: tuple[int, int]) -> list[Measure]:
    first, last = index.measure(measures[0]), index.measure(measures[1])
    start, end = index.measures.index(first), index.measures.index(last)
    if measures[0] == 1 and start > 0 and index.measures[start - 1].number == 0:
        start -= 1
    return index.measures[start : end + 1]


class _Clock:
    def __init__(self, tempos: list[tuple[Fraction, float]]):
        self.points = [(0.0, 0.0, DEFAULT_TEMPO)]
        for q, bpm in sorted(tempos):
            q0, t0, previous = self.points[-1]
            time = t0 + (float(q) - q0) * 60_000 / previous
            if float(q) == q0:
                self.points[-1] = (q0, t0, bpm)
            else:
                self.points.append((float(q), time, bpm))
        self.quarters = [q for q, _, _ in self.points]

    def ms(self, q: float) -> float:
        q0, t0, bpm = self.points[max(bisect_right(self.quarters, q) - 1, 0)]
        return t0 + (q - q0) * 60_000 / bpm


def _midi(pitch: str) -> int:
    accidental = pitch[1:].rstrip("0123456789")
    octave = int(pitch[1 + len(accidental) :])
    return 12 * (octave + 1) + SEMITONES[LETTERS.index(pitch[0])] + accidental.count("#") - accidental.count("b")


def _notes(index: ScoreIndex, starts: dict[int, Fraction], clock: _Clock) -> tuple[list[tuple[Note, Measure]], dict[str, Note]]:
    notes, heads, open_ties, graces, mains = [], {}, {}, {}, {}
    for measure in index.measures:
        for event in measure.events:
            if not event.pitch:
                continue
            if event.grace:
                graces.setdefault((id(measure), event.staff, event.onset, event.slashed), []).append(event)
                continue
            begin, finish = starts[id(measure)] + event.onset, starts[id(measure)] + event.onset + event.duration
            pitch, tie = _midi(event.pitch), (event.staff, _midi(event.pitch))
            held = open_ties.pop(tie, None)
            if held and held[1] == begin:
                note = held[0]
                note.end = clock.ms(float(finish))
            else:
                note = Note(clock.ms(float(begin)), clock.ms(float(finish)), pitch)
                notes.append((note, measure))
                mains.setdefault((id(measure), event.staff, event.onset), []).append(note)
            heads[event.id] = note
            if event.tied:
                open_ties[tie] = (note, finish)
    for (measure_id, staff, onset, slashed), group in graces.items():
        measure = next(measure for measure in index.measures if id(measure) == measure_id)
        arrival = clock.ms(float(starts[measure_id] + onset))
        if slashed:
            for position, event in enumerate(group):
                start = arrival - (len(group) - position) * SLASHED_GRACE_MS
                notes.append((Note(start, start + SLASHED_GRACE_MS, _midi(event.pitch)), measure))
            continue
        main = mains.get((measure_id, staff, onset), [])
        span = (main[0].end - main[0].start) / 2 if main else SLASHED_GRACE_MS * len(group)
        for position, event in enumerate(group):
            start = arrival + position * span / len(group)
            notes.append((Note(start, start + span / len(group), _midi(event.pitch)), measure))
        for note in main:
            note.start += span
    notes.sort(key=lambda item: item[0].start)
    return notes, heads


class _Loudness:
    def __init__(self, marks: list[tuple[float, str, float | None]], clock: _Clock):
        self.levels, self.accents, self.swells = [], [], []
        for q, text, end in marks:
            moment = clock.ms(q)
            if end is not None or text in SWELLS:
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


def _starts_ornaments_above(root: ET.Element) -> bool:
    composers = " ".join("".join(name.itertext()) for name in root.iter(f"{MEI}persName") if name.get("role") == "composer")
    return any(word in UPPER_NOTE_COMPOSERS for word in re.findall(r"\w+", composers.lower()))


def _spelled(pitch: str) -> tuple[str, int, int]:
    accidental = pitch[1:].rstrip("0123456789")
    return pitch[0], int(pitch[1 + len(accidental) :]), accidental.count("#") - accidental.count("b")


def _neighbour(event: Event, measure: Measure, direction: int, printed: str, key: dict[str, int]) -> int:
    letter, octave, _ = _spelled(event.pitch)
    position = LETTERS.index(letter) + direction
    letter, octave = LETTERS[position % 7], octave + position // 7
    if printed in ALTER:
        alteration = ALTER[printed]
    else:
        earlier = [(other.onset, _spelled(other.pitch)[2]) for other in measure.events
                   if other.pitch and other.staff == event.staff and other.onset < event.onset
                   and _spelled(other.pitch)[:2] == (letter, octave)]
        alteration = max(earlier)[1] if earlier else key[letter]
    return 12 * (octave + 1) + SEMITONES[LETTERS.index(letter)] + alteration


def _ornamented(note: Note, code: str, upper: int, lower: int, upper_start: bool) -> list[Note]:
    length = note.end - note.start
    step = min(ORNAMENT_NOTE_MS, length / 4)
    if code == "tr":
        pairs = max(int(length // step - 1) // 2, 1)
        pitches = [upper, note.pitch] * pairs if upper_start else [note.pitch, upper] * pairs + [note.pitch]
    elif code in ("mu", "ml"):
        pitches = [note.pitch, upper if code == "mu" else lower, note.pitch]
    else:
        first, second = (upper, lower) if code == "tu" else (lower, upper)
        pitches = [first, note.pitch, second, note.pitch] if upper_start else [note.pitch, first, note.pitch, second, note.pitch]
        step = length / len(pitches)
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
