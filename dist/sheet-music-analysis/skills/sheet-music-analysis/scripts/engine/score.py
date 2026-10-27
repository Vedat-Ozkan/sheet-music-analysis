from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
ACCIDENTALS = {"f": "b", "s": "#", "ff": "bb", "ss": "##", "x": "##", "n": ""}
CONTAINERS = {"beam", "tuplet", "bTrem", "fTrem", "graceGrp"}
LETTERS = "CDEFGAB"
SEMITONES = (0, 2, 4, 5, 7, 9, 11)
TOLERANCE = Fraction(1, 96)


class PositionError(ValueError):
    pass


@dataclass
class Event:

    id: str
    measure: int
    staff: int
    onset: Fraction
    duration: Fraction
    pitch: str | None = None
    grace: bool = False
    layer: int = 1
    tied: bool = False
    segment: str = ""
    attack: str = ""
    slashed: bool = False

@dataclass
class Mark:

    kind: str
    offset: Fraction
    value: str
    length: Fraction = Fraction(0)
    pitch: str = ""
    upper: str = ""
    lower: str = ""

@dataclass
class Segment:

    id: str
    index: int
    start: Fraction

@dataclass
class Measure:
    id: str
    number: int
    index: int
    beat_length: Fraction
    meter: str = ""
    declared_length: Fraction | None = None
    events: list[Event] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.segments:
            self.segments = [Segment(self.id, self.index, Fraction(0))]

    @property
    def last_index(self) -> int:
        return self.segments[-1].index

    @property
    def content_length(self) -> Fraction:
        return max((event.onset + event.duration for event in self.events), default=Fraction(0))

    @property
    def length(self) -> Fraction:
        return self.declared_length if self.declared_length is not None else self.content_length

    def segment_at(self, offset: Fraction) -> Segment:
        return next(segment for segment in reversed(self.segments) if segment.start <= offset or segment is self.segments[0])

    def offset_of(self, beat: float) -> Fraction:
        offset = (Fraction(beat).limit_denominator(96) - 1) * self.beat_length
        if offset < 0 or (self.length and offset >= self.length):
            beats = float(self.length / self.beat_length)
            raise PositionError(f"Measure {self.number} has no beat {beat}; its beats run from 1 up to {1 + beats:g}")
        return offset

    def beat_of(self, offset: Fraction) -> float:
        return float(offset / self.beat_length + 1)


def normalise_pitch(pitch: str) -> str:
    return pitch[0].upper() + pitch[1:].replace("-", "b")


def beat_length(count: int, unit: int) -> Fraction:
    if unit == 8 and count > 3 and count % 3 == 0:
        return Fraction(3, 2)
    return Fraction(4, unit)


def transpose(pitch: str, diatonic: int, semitones: int) -> str:
    accidental = pitch[1:].rstrip("0123456789")
    octave = int(pitch[1 + len(accidental) :])
    step = LETTERS.index(pitch[0])
    sounding = SEMITONES[step] + accidental.count("#") - accidental.count("b") + 12 * octave + semitones
    new_octave, new_step = divmod(step + 7 * octave + diatonic, 7)
    alter = sounding - (SEMITONES[new_step] + 12 * new_octave)
    return f"{LETTERS[new_step]}{'#' * alter if alter > 0 else 'b' * -alter}{new_octave}"


def _pitch(note: ET.Element) -> str:
    accidental = note.get("accid") or note.get("accid.ges")
    if accidental is None:
        child = note.find(f"{MEI}accid")
        if child is not None:
            accidental = child.get("accid") or child.get("accid.ges")
    octave = note.get("oct.ges") or note.get("oct")
    return f"{note.get('pname').upper()}{ACCIDENTALS.get(accidental or '', '')}{octave}"


def _duration(element: ET.Element, ppq: int) -> Fraction:
    if element.get("dur.ppq") is not None:
        return Fraction(int(element.get("dur.ppq")), ppq)
    if element.get("dur") is None or not element.get("dur").isdigit():
        return Fraction(0)
    duration = Fraction(4, int(element.get("dur")))
    dots = int(element.get("dots", "0"))
    return duration * (2 - Fraction(1, 2**dots))


class ScoreIndex:
    ornaments_from_above = False

    def __init__(self, mei: str):
        root = ET.fromstring(mei)
        self.measures: list[Measure] = []
        self.meter = ""
        self.key_signature = ""
        self.renumbered = False
        self._ppq: dict[int, int] = {}
        self._transposition: dict[int, tuple[int, int]] = {}
        self._beat_length = Fraction(1)
        self._meter = ""
        self._position = 0
        self._tie_starts: set[str] = set()
        for score_def in root.iter(f"{MEI}scoreDef"):
            self._read_definitions(score_def)
            break
        for section in root.iter(f"{MEI}score"):
            self._walk(section)
        for measure in self.measures:
            measure.events.sort(key=lambda event: (event.onset, event.staff))
            for event in measure.events:
                event.tied = event.tied or event.id in self._tie_starts
        self._renumber_if_needed()
        self._finish()

    @classmethod
    def from_measures(cls, measures: list[Measure], meter: str, key_signature: str) -> ScoreIndex:
        index = cls.__new__(cls)
        index.measures, index.meter, index.key_signature, index.renumbered = measures, meter, key_signature, False
        index._finish()
        return index

    def _finish(self) -> None:
        self._by_number = {measure.number: measure for measure in self.measures}
        self._by_segment = {segment.id: (measure, segment) for measure in self.measures for segment in measure.segments}

    @property
    def ppq(self) -> int:
        divisions = 1
        for measure in self.measures:
            for value in [measure.length] + [part for event in measure.events for part in (event.onset, event.duration)]:
                divisions = math.lcm(divisions, value.denominator)
        return divisions

    def locate_segment(self, id: str) -> tuple[Measure, Segment]:
        return self._by_segment[id]

    def _read_definitions(self, element: ET.Element) -> None:
        for staff_def in element.iter(f"{MEI}staffDef"):
            staff = int(staff_def.get("n", "1"))
            if staff_def.get("ppq"):
                self._ppq[staff] = int(staff_def.get("ppq"))
            if staff_def.get("trans.semi") is not None:
                self._transposition[staff] = (int(staff_def.get("trans.diat", "0")), int(staff_def.get("trans.semi")))
        count, unit = element.get("meter.count"), element.get("meter.unit")
        self._read_meter(element.find(f".//{MEI}meterSig"), count, unit)
        key = element.find(f".//{MEI}keySig")
        signature = key.get("sig") if key is not None else element.get("keysig") or element.get("key.sig")
        if signature and not self.key_signature:
            self.key_signature = signature

    def _read_meter(self, meter: ET.Element | None, count: str | None = None, unit: str | None = None) -> None:
        if meter is not None:
            count, unit = meter.get("count", count), meter.get("unit", unit)
        if count and unit and count.isdigit() and unit.isdigit():
            self._beat_length = beat_length(int(count), int(unit))
            self._meter = f"{count}/{unit}"
            self.meter = self.meter or self._meter

    def _walk(self, element: ET.Element) -> None:
        for child in element:
            tag = child.tag.replace(MEI, "")
            if tag == "measure":
                self._read_measure(child)
            elif tag == "scoreDef":
                self._read_definitions(child)
            elif tag in ("section", "ending", "mdiv", "score"):
                self._walk(child)

    def _read_measure(self, element: ET.Element) -> None:
        self._position += 1
        self._read_meter(element.find(f".//{MEI}meterSig"))
        label = element.get("n", "")
        numbered = label.lstrip("-").isdigit()
        incomplete = element.get("metcon") == "false"
        previous = self.measures[-1] if self.measures else None
        measure = Measure(
            id=element.get(XML_ID),
            number=int(label) if numbered else previous.number + 1 if previous else 1,
            index=self._position,
            beat_length=self._beat_length,
            meter=self._meter,
        )
        full = None
        if self._meter:
            count, unit = self._meter.split("/")
            full = Fraction(int(count) * 4, int(unit))
        if not incomplete:
            measure.declared_length = full
        for staff in element.findall(f"{MEI}staff"):
            for position, layer in enumerate(staff.findall(f"{MEI}layer"), start=1):
                self._layer = position
                self._read_layer(layer, measure, int(staff.get("n", "1")), Fraction(0))
        if not measure.events and full is not None:
            measure.declared_length = full
        for tie in element.findall(f"{MEI}tie"):
            self._tie_starts.add((tie.get("startid") or "").lstrip("#"))

        continues = (
            previous is not None
            and incomplete
            and previous.declared_length is None
            and (not numbered or measure.number == previous.number)
            and full is not None
            and previous.content_length + measure.content_length <= full + TOLERANCE
            and previous.number != 0
        )
        if continues:
            shift = previous.content_length
            previous.segments.append(Segment(measure.id, measure.index, shift))
            for event in measure.events:
                event.onset += shift
                event.measure = previous.number
            previous.events.extend(measure.events)
            return
        self.measures.append(measure)

    def _read_layer(self, element: ET.Element, measure: Measure, staff: int, cursor: Fraction) -> Fraction:
        ppq = self._ppq.get(staff) or next(iter(self._ppq.values()), 1)
        shift = self._transposition.get(staff)
        for child in element:
            tag = child.tag.replace(MEI, "")
            if tag in CONTAINERS:
                cursor = self._read_layer(child, measure, staff, cursor)
                continue
            if tag not in ("note", "chord", "rest", "space"):
                continue
            grace = child.get("grace") is not None
            duration = Fraction(0) if grace else _duration(child, ppq)
            notes = child.findall(f"{MEI}note") if tag == "chord" else [child] if tag == "note" else []
            notes = [note for note in notes if note.get("pname")]
            for note in notes:
                pitch = transpose(_pitch(note), *shift) if shift else _pitch(note)
                event = Event(note.get(XML_ID), measure.number, staff, cursor, duration, pitch, grace, self._layer)
                event.tied = note.get("tie") in ("i", "m")
                event.segment = measure.id
                event.attack = child.get(XML_ID, "")
                event.slashed = child.get("grace") == "unacc"
                measure.events.append(event)
            if tag == "rest":
                rest = Event(child.get(XML_ID), measure.number, staff, cursor, duration, layer=self._layer, segment=measure.id)
                measure.events.append(rest)
            cursor += duration
        return cursor

    def _renumber_if_needed(self) -> None:
        numbers = [measure.number for measure in self.measures]
        if all(a < b for a, b in zip(numbers, numbers[1:])):
            return
        self.renumbered = True
        first = self.measures[0]
        number = 0 if first.declared_length is None and len(self.measures) > 1 else 1
        for measure in self.measures:
            measure.number = number
            for event in measure.events:
                event.measure = number
            number += 1

    def measure(self, number: int) -> Measure:
        if number not in self._by_number:
            first, last = self.measures[0].number, self.measures[-1].number
            raise PositionError(f"Measure {number} does not exist; the score has measures {first} to {last}")
        return self._by_number[number]

    def measure_range(self, first: int, last: int, *, include_pickup: bool = True) -> str:
        start = self.measure(first)
        position = self.measures.index(start)
        if include_pickup and first == 1 and position > 0 and self.measures[position - 1].number == 0:
            start = self.measures[position - 1]
        return f"{start.index}-{self.measure(last).last_index}"

    def find_note(self, measure: int, beat: float, staff: int | None = None, pitch: str | None = None) -> Event:
        bar = self.measure(measure)
        offset = bar.offset_of(beat)
        notes = [event for event in bar.events if event.pitch and not event.grace]
        here = [event for event in notes if abs(event.onset - offset) <= TOLERANCE]
        matches = [
            event
            for event in here
            if (staff is None or event.staff == staff) and (pitch is None or event.pitch == normalise_pitch(pitch))
        ]
        if matches:
            return matches[0]
        if here:
            found = ", ".join(f"{event.pitch} (staff {event.staff})" for event in here)
            raise PositionError(f"No note matches staff={staff} pitch={pitch} at measure {measure} beat {beat}; notes there: {found}")
        beats = sorted({round(bar.beat_of(event.onset), 3) for event in notes})
        raise PositionError(f"No note starts at measure {measure} beat {beat}; notes start at beats {beats}")
