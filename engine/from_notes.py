from __future__ import annotations

import math
import re
from dataclasses import replace
import xml.etree.ElementTree as ET
from fractions import Fraction

from engine import notes
from engine.correct import replace_bars
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
    return replace_bars(_empty_score(measures, staves), _with_every_staff(text, staves))


def _rest_bar_before(first: Measure) -> Measure:
    return replace(first, number=first.number - 1, name=str(first.number - 1), declared_length=_full_length(first), events=[])


def join_pages(pages: list[str]) -> str:
    read = []
    for number, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        head = HEADER.fullmatch(lines[0]) if lines else None
        if not head:
            raise notes.NotesError(f'Page {number}: the note list must start with a "{notes.VERSION} div=… ts=… ks=…" line')
        read.append((number, int(head["div"]), head["meter"], head["key"], lines[1:]))
    div = math.lcm(*(page[1] for page in read))
    meter, key = read[0][2], read[0][3]
    joined = [f"{notes.VERSION} div={div} ts={meter} ks={key}"]
    bar, last_length, bar_at, voices_at, completing = None, None, 0, {}, None

    def pad_voices_left_out() -> None:
        for label, at in voices_at.items():
            if label not in completing["voices"] and not notes.WORDS_LABEL.fullmatch(label):
                joined[at] += f" {completing['length']} r"

    for number, own, page_meter, page_key, lines in read:
        scale = div // own
        opening = {"ts": page_meter or meter, "ks": page_key}
        page_opens = True
        for line in lines:
            label, _, body = line.partition(":")
            if line.startswith("m"):
                found = BAR_LINE.fullmatch(line)
                if not found:
                    raise notes.NotesError(f"Page {number}: a bar line looks like 'm3 len=96', not {line!r}")
                if completing:
                    pad_voices_left_out()
                    completing = None
                changes = opening | dict(part.split("=", 1) for part in found["changes"].split())
                opening = {}
                length = int(found["length"]) * scale
                full = _units_in_bar(meter, div) if changes.get("ts", meter) == meter and changes.get("ks", key) == key else None
                if page_opens and None not in (last_length, full) and last_length < full and last_length + length == full:
                    completing = {"first_half": last_length, "length": length, "voices": set()}
                    joined[bar_at] = joined[bar_at].replace(f" len={last_length}", f" len={full}", 1)
                    page_opens, last_length = False, full
                    continue
                bar = int(line.split()[0][1:]) if bar is None else bar + 1
                page_opens, last_length, bar_at, voices_at = False, length, len(joined), {}
                line = f"m{bar} len={length}"
                if changes.get("ts", meter) != meter:
                    meter = changes["ts"]
                    line += f" ts={meter}"
                if changes.get("ks", key) != key:
                    key = changes["ks"]
                    line += f" ks={key}"
            elif label != "x" and not notes.WORDS_LABEL.fullmatch(label):
                body = " ".join(str(int(entry) * scale) if entry.isdigit() else entry for entry in body.split())
                line = f"{label}: {body}"
                if completing:
                    completing["voices"].add(label)
                    if label in voices_at:
                        joined[voices_at[label]] += f" {body}"
                        continue
                    line = f"{label}: {completing['first_half']} r {body}"
            elif completing and label in voices_at:
                completing["voices"].add(label)
                joined[voices_at[label]] += f" {body.strip()}"
                continue
            if label != "x" and not line.startswith("m"):
                voices_at[label] = len(joined)
            joined.append(line)
    if completing:
        pad_voices_left_out()
    return "\n".join(joined)


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
