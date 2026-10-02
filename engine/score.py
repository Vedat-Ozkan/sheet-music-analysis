"""Index of a score's measures and notes, built from Verovio's MEI.

Annotations address the music by position (measure number, beat, staff, pitch).
This index turns those positions into the element IDs that Verovio draws.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
ACCIDENTALS = {"f": "b", "s": "#", "ff": "bb", "ss": "##", "x": "##", "n": ""}
CONTAINERS = {"beam", "tuplet", "bTrem", "fTrem", "graceGrp"}
TOLERANCE = Fraction(1, 96)


class PositionError(ValueError):
    """An annotation points at a place that is not in the score."""


@dataclass
class Event:
    """A note or rest. Chord notes are separate events sharing an onset."""

    id: str
    measure: int
    staff: int
    onset: Fraction  # quarter notes from the start of the measure
    duration: Fraction
    pitch: str | None = None  # "Eb4"; None for rests
    grace: bool = False
    layer: int = 1  # the voice within the staff
    tied: bool = False  # tied to the next note of the same pitch


@dataclass
class Measure:
    id: str
    number: int  # the printed number; a pickup is 0
    index: int  # 1-based position in the score, which is what Verovio's measureRange counts
    beat_length: Fraction  # quarter notes per beat (a dotted quarter in 12/8)
    meter: str = ""  # "12/8"
    declared_length: Fraction | None = None  # a full bar's length; None for a pickup or other incomplete measure
    events: list[Event] = field(default_factory=list)

    @property
    def length(self) -> Fraction:
        """Quarter notes in the measure: a full bar of its meter, or what it holds if it is incomplete."""
        if self.declared_length is not None:
            return self.declared_length
        return max((event.onset + event.duration for event in self.events), default=Fraction(0))

    def offset_of(self, beat: float) -> Fraction:
        """Quarter-note offset of a beat; raises if the beat lies outside the measure."""
        offset = (Fraction(beat).limit_denominator(96) - 1) * self.beat_length
        if offset < 0 or (self.length and offset >= self.length):
            beats = float(self.length / self.beat_length)
            raise PositionError(f"Measure {self.number} has no beat {beat}; its beats run from 1 up to {1 + beats:g}")
        return offset

    def beat_of(self, offset: Fraction) -> float:
        return float(offset / self.beat_length + 1)


def normalise_pitch(pitch: str) -> str:
    """Accept music21 spelling ("E-4") as well as "Eb4"."""
    return pitch[0].upper() + pitch[1:].replace("-", "b")


def beat_length(count: int, unit: int) -> Fraction:
    if unit == 8 and count > 3 and count % 3 == 0:
        return Fraction(3, 2)
    return Fraction(4, unit)


def _pitch(note: ET.Element) -> str:
    accidental = note.get("accid") or note.get("accid.ges")
    if accidental is None:
        child = note.find(f"{MEI}accid")
        if child is not None:
            accidental = child.get("accid") or child.get("accid.ges")
    octave = note.get("oct.ges") or note.get("oct")  # sounding octave, e.g. under an 8va line
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
    def __init__(self, mei: str):
        root = ET.fromstring(mei)
        self.measures: list[Measure] = []
        self.meter = ""  # "12/8", from the first score definition
        self.key_signature = ""  # MEI form: "3f" is three flats, "2s" two sharps, "0" none
        self._ppq = 1
        self._beat_length = Fraction(1)
        self._meter = ""
        self._tie_starts: set[str] = set()
        for score_def in root.iter(f"{MEI}scoreDef"):
            self._read_definitions(score_def)
            break
        for section in root.iter(f"{MEI}score"):
            self._walk(section)
        for measure in self.measures:
            for event in measure.events:
                event.tied = event.tied or event.id in self._tie_starts
        self._finish()

    @classmethod
    def from_measures(cls, measures: list[Measure], meter: str, key_signature: str, ppq: int) -> ScoreIndex:
        """An index built from already-read measures, for scores that arrive as a note list."""
        index = cls.__new__(cls)
        index.measures, index.meter, index.key_signature, index._ppq = measures, meter, key_signature, ppq
        index._finish()
        return index

    def _finish(self) -> None:
        self._by_number = {measure.number: measure for measure in self.measures}
        self._by_id = {measure.id: measure for measure in self.measures}

    @property
    def ppq(self) -> int:
        """Divisions per quarter note in which every duration is a whole number."""
        return self._ppq

    def measure_by_id(self, id: str) -> Measure:
        return self._by_id[id]

    def _read_definitions(self, element: ET.Element) -> None:
        for staff_def in element.iter(f"{MEI}staffDef"):
            if staff_def.get("ppq"):
                self._ppq = int(staff_def.get("ppq"))
        count, unit = element.get("meter.count"), element.get("meter.unit")
        meter = element.find(f".//{MEI}meterSig")
        if meter is not None:
            count, unit = meter.get("count", count), meter.get("unit", unit)
        if count and unit and count.isdigit():
            self._beat_length = beat_length(int(count), int(unit))
            self._meter = f"{count}/{unit}"
            self.meter = self.meter or self._meter
        key = element.find(f".//{MEI}keySig")
        signature = key.get("sig") if key is not None else element.get("keysig") or element.get("key.sig")
        if signature and not self.key_signature:
            self.key_signature = signature

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
        number = element.get("n", "")
        measure = Measure(
            id=element.get(XML_ID),
            number=int(number) if number.lstrip("-").isdigit() else len(self.measures) + 1,
            index=len(self.measures) + 1,
            beat_length=self._beat_length,
            meter=self._meter,
        )
        if element.get("metcon") != "false" and self._meter:
            count, unit = self._meter.split("/")
            measure.declared_length = Fraction(int(count) * 4, int(unit))
        for staff in element.findall(f"{MEI}staff"):
            for position, layer in enumerate(staff.findall(f"{MEI}layer"), start=1):
                self._layer = position
                self._read_layer(layer, measure, int(staff.get("n", "1")), Fraction(0))
        for tie in element.findall(f"{MEI}tie"):
            self._tie_starts.add((tie.get("startid") or "").lstrip("#"))
        measure.events.sort(key=lambda event: (event.onset, event.staff))
        self.measures.append(measure)

    def _read_layer(self, element: ET.Element, measure: Measure, staff: int, cursor: Fraction) -> Fraction:
        for child in element:
            tag = child.tag.replace(MEI, "")
            if tag in CONTAINERS:
                cursor = self._read_layer(child, measure, staff, cursor)
                continue
            if tag not in ("note", "chord", "rest", "space"):
                continue
            grace = child.get("grace") is not None
            duration = Fraction(0) if grace else _duration(child, self._ppq)
            notes = child.findall(f"{MEI}note") if tag == "chord" else [child] if tag == "note" else []
            for note in notes:
                event = Event(note.get(XML_ID), measure.number, staff, cursor, duration, _pitch(note), grace, self._layer)
                event.tied = note.get("tie") in ("i", "m")
                measure.events.append(event)
            if tag == "rest":
                measure.events.append(Event(child.get(XML_ID), measure.number, staff, cursor, duration, layer=self._layer))
            cursor += duration
        return cursor

    def measure(self, number: int) -> Measure:
        if number not in self._by_number:
            first, last = self.measures[0].number, self.measures[-1].number
            raise PositionError(f"Measure {number} does not exist; the score has measures {first} to {last}")
        return self._by_number[number]

    def measure_range(self, first: int, last: int) -> str:
        """Verovio measureRange covering printed measures first..last, with the pickup when starting at 1."""
        start = self.measure(first).index
        if first == 1 and start > 1 and self.measures[start - 2].number == 0:
            start -= 1
        return f"{start}-{self.measure(last).index}"

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
