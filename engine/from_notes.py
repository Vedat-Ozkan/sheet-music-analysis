from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
import xml.etree.ElementTree as ET
from fractions import Fraction

from engine import correct, notes
from engine.errors import UserError
from engine.score import Measure

REST_TYPES = ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th")
DIVISIONS = 32
MAX_STAVES = 32
MAX_VOICES = 8
MAX_BARS = 1000
MAX_BAR_LENGTH = 64
HEADER = re.compile(notes.VERSION + r" div=(?P<div>[1-9]\d*) ts=(?P<meter>\S*) ks=(?P<key>\S+)")
BAR_LINE = re.compile(r"m\d+ len=(?P<length>\d+)(?P<changes>(?: (?:ts|ks)=\S+)*)")


def score_from_pages(pages: list[str]) -> bytes:
    if not pages:
        raise notes.NotesError("No pages were handed in")
    for number, page in enumerate(pages, 1):
        try:
            score_from_notes(page, after_a_rest_bar=number > 1)
        except UserError as error:
            raise notes.NotesError(f"Page {number}: {error}") from error
    return score_from_notes(join_pages(pages))


def score_from_notes(text: str, *, after_a_rest_bar: bool = False) -> bytes:
    index = notes.decode(text)
    events = [event for measure in index.measures for event in measure.events]
    staves = max((event.staff for event in events), default=1)
    if staves > MAX_STAVES or max((event.layer for event in events), default=1) > MAX_VOICES:
        raise notes.NotesError(f"Staves are numbered 1 to {MAX_STAVES} from the top and voices 1 to {MAX_VOICES}")
    if len(index.measures) > MAX_BARS:
        raise notes.NotesError(f"The note list has {len(index.measures)} bars; at most {MAX_BARS} can be built")
    for measure in index.measures:
        if measure.length > MAX_BAR_LENGTH:
            raise notes.NotesError(f"Bar {measure.number}: len= makes this bar longer than {MAX_BAR_LENGTH} quarter notes")
    first = index.measures[0] if index.measures else None
    if first and not after_a_rest_bar and first.number != 0 and first.length < _full_length(first):
        raise notes.NotesError(f"Bar {first.name}: len= makes the first bar shorter than its time signature; only a "
                               "pickup is shorter, and a pickup is written m0")
    measures = [_rest_bar_before(first), *index.measures] if first and after_a_rest_bar else index.measures
    return correct.replace_bars(_empty_score(measures, staves), _with_every_staff(text, staves))


def _rest_bar_before(first: Measure) -> Measure:
    return replace(first, number=first.number - 1, name=str(first.number - 1), declared_length=_full_length(first), events=[])


@dataclass
class _Bar:
    written_number: int
    length: int
    changes: dict[str, str]
    voices: dict[str, str] = field(default_factory=dict)
    words: dict[str, str] = field(default_factory=dict)
    other: list[str] = field(default_factory=list)


def join_pages(pages: list[str]) -> str:
    read = [_page_heading(number, text) for number, text in enumerate(pages, 1)]
    div = math.lcm(*(own for own, _, _, _ in read))
    meter, key = read[0][1], read[0][2]
    bars = _joined([_page_bars(number, lines, div // own, page_meter, page_key)
                    for number, (own, page_meter, page_key, lines) in enumerate(read, 1)], div, meter, key)
    return _bars_as_text(bars, div, meter, key)


def _page_heading(number: int, text: str) -> tuple[int, str, str, list[str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = HEADER.fullmatch(lines[0]) if lines else None
    if not head:
        raise notes.NotesError(f'Page {number}: the note list must start with a "{notes.VERSION} div=… ts=… ks=…" line')
    return int(head["div"]), head["meter"], head["key"], lines[1:]


def _page_bars(number: int, lines: list[str], scale: int, meter: str, key: str) -> list[_Bar]:
    bars = []
    for line in lines:
        label, _, body = line.partition(":")
        if line.startswith("m"):
            found = BAR_LINE.fullmatch(line)
            if not found:
                raise notes.NotesError(f"Page {number}: a bar line looks like 'm3 len=96', not {line!r}")
            opening = {"ts": meter, "ks": key} if not bars else {}
            changes = {name: value for name, value in opening.items() if value} | dict(
                part.split("=", 1) for part in found["changes"].split())
            bars.append(_Bar(int(line.split()[0][1:]), int(found["length"]) * scale, changes))
        elif not bars:
            raise notes.NotesError(f"Page {number}: a voice line needs a bar line like 'm3 len=96' before it")
        elif label == "x":
            bars[-1].other.append(line)
        elif notes.WORDS_LABEL.fullmatch(label):
            bars[-1].words[label[:-1]] = body.strip()
        else:
            bars[-1].voices[label] = " ".join(str(int(entry) * scale) if entry.isdigit() else entry for entry in body.split())
    return bars


def _joined(pages: list[list[_Bar]], div: int, meter: str, key: str) -> list[_Bar]:
    bars = []
    for page in pages:
        for position, bar in enumerate(page):
            if position == 0 and bars and _completes(bars[-1], bar, div, meter, key):
                bars[-1] = _one_bar(bars[-2] if len(bars) > 1 else None, bars[-1], bar, div)
                continue
            if position == 0 and bars:
                bar = replace(bar, words={label: _words_after_the_turn(bars[-1].voices.get(label), bar.voices.get(label), words, div)
                                          for label, words in bar.words.items()})
            meter, key = bar.changes.get("ts", meter), bar.changes.get("ks", key)
            bars.append(bar)
    return bars


def _completes(before: _Bar, after: _Bar, div: int, meter: str, key: str) -> bool:
    full = _units_in_bar(meter, div)
    unchanged = after.changes.get("ts", meter) == meter and after.changes.get("ks", key) == key
    return unchanged and full is not None and before.length < full and before.length + after.length == full


def _one_bar(previous: _Bar | None, before: _Bar, after: _Bar, div: int) -> _Bar:
    labels = [*before.voices, *(label for label in after.voices if label not in before.voices)]
    voices = {label: f"{before.voices.get(label, f'{before.length} r')} {after.voices.get(label, f'{after.length} r')}"
              for label in labels}
    words = {}
    for label in [*before.words, *(label for label in after.words if label not in before.words)]:
        tied_in = bool(previous and label in previous.voices and correct.ends_tied(previous.voices[label], div, False))
        tied_across = label in before.voices and correct.ends_tied(before.voices[label], div, tied_in)
        first = before.words.get(label) or _unsung(before.voices.get(label), div, tied_in)
        second = (_words_after_the_turn(before.voices.get(label), after.voices.get(label), after.words[label], div)
                  if label in after.words else _unsung(after.voices.get(label), div, tied_across))
        words[label] = " ".join(filter(None, (first, second)))
    return _Bar(before.written_number, before.length + after.length, before.changes, voices, words, before.other + after.other)


def _words_after_the_turn(before: str | None, after: str | None, words: str, div: int) -> str:
    tied_in = bool(before and correct.ends_tied(before, div, False))
    if not after or not tied_in or correct.sung_notes(after, div, True) == correct.sung_notes(after, div, False):
        return words
    return " ".join(words.split()[1:])


def _unsung(body: str | None, div: int, tied_into: bool) -> str:
    return " ".join("_" * (correct.sung_notes(body, div, tied_into) if body else 0))


def _bars_as_text(bars: list[_Bar], div: int, meter: str, key: str) -> str:
    lines = [f"{notes.VERSION} div={div} ts={meter} ks={key}"]
    for number, bar in enumerate(bars, bars[0].written_number if bars else 0):
        line = f"m{number} len={bar.length}"
        if bar.changes.get("ts", meter) != meter:
            meter = bar.changes["ts"]
            line += f" ts={meter}"
        if bar.changes.get("ks", key) != key:
            key = bar.changes["ks"]
            line += f" ks={key}"
        lines.append(line)
        for label, body in bar.voices.items():
            lines.append(f"{label}: {body}")
            if label in bar.words:
                lines.append(f"{label}w: {bar.words[label]}")
        lines.extend(f"{label}w: {body}" for label, body in bar.words.items() if label not in bar.voices)
        lines.extend(bar.other)
    return "\n".join(lines)


def _empty_score(measures: list[Measure], staves: int) -> bytes:
    root = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(ET.SubElement(root, "part-list"), "score-part", id="P1"), "part-name")
    part = ET.SubElement(root, "part", id="P1")
    meter = key = None
    for measure in measures:
        full = _full_length(measure)
        bar = ET.SubElement(part, "measure", number=measure.name)
        if measure.length != full:
            bar.set("implicit", "yes")
        if part[0] is bar or measure.meter != meter or measure.key_signature != key:
            attributes = ET.SubElement(bar, "attributes")
            if part[0] is bar:
                ET.SubElement(attributes, "divisions").text = str(DIVISIONS)
            if measure.key_signature != key:
                key = measure.key_signature
                ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(_fifths(key))
            if measure.meter != meter and measure.meter:
                meter = measure.meter
                time = ET.SubElement(attributes, "time")
                ET.SubElement(time, "beats").text, ET.SubElement(time, "beat-type").text = meter.split("/")
            if part[0] is bar:
                ET.SubElement(attributes, "staves").text = str(staves)
                for staff in range(1, staves + 1):
                    sign, line, _ = notes.CLEFS["F" if staff == staves > 1 else "G"]
                    clef = ET.SubElement(attributes, "clef", number=str(staff))
                    ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = sign, str(line)
        for staff in range(1, staves + 1):
            if staff > 1:
                ET.SubElement(ET.SubElement(bar, "backup"), "duration").text = str(int(measure.length * DIVISIONS))
            for kind, length in [(None, measure.length)] if measure.length == full else _rests(measure):
                note = ET.SubElement(bar, "note")
                ET.SubElement(note, "rest", {} if kind else {"measure": "yes"})
                ET.SubElement(note, "duration").text = str(int(length * DIVISIONS))
                ET.SubElement(note, "voice").text = str(staff)
                if kind:
                    ET.SubElement(note, "type").text = kind
                ET.SubElement(note, "staff").text = str(staff)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _units_in_bar(meter: str, div: int) -> int | None:
    if not meter:
        return None
    beats, unit = meter.split("/")
    return 4 * int(beats) * div // int(unit)


def _full_length(measure: Measure) -> Fraction:
    if not measure.meter:
        return measure.length
    beats, unit = measure.meter.split("/")
    return Fraction(4 * int(beats), int(unit))


def _fifths(key: str) -> int:
    return 0 if key in ("0", "") else int(key[:-1]) * (1 if key.endswith("s") else -1)


def _rests(measure: Measure) -> list[tuple[str, Fraction]]:
    rests, left = [], measure.length
    for power, kind in enumerate(REST_TYPES):
        length = Fraction(4, 2**power)
        while left >= length:
            rests.append((kind, length))
            left -= length
    if left or not rests:
        raise notes.NotesError(f"Bar {measure.number}: len= gives a length no bar can have")
    return rests


def _with_every_staff(text: str, staves: int) -> str:
    lines, written, length = [], set(range(1, staves + 1)), ""

    def fill():
        lines.extend(f"{staff}.1: {length} r" for staff in range(1, staves + 1) if staff not in written)

    for line in filter(None, map(str.strip, text.splitlines())):
        if line.startswith("m") and lines:
            fill()
            written, length = set(), line.split("len=", 1)[1].split()[0]
        elif line[0].isdigit() and not notes.WORDS_LABEL.fullmatch(line.partition(":")[0]):
            written.add(int(line.split(".", 1)[0]))
        lines.append(line)
    fill()
    return "\n".join(lines)
