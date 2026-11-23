from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction

from engine.errors import UserError

MEI = "{http://www.music-encoding.org/ns/mei}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
ACCIDENTALS = {"f": "b", "s": "#", "ff": "bb", "ss": "##", "x": "##", "n": ""}
CONTAINERS = {"beam", "tuplet", "bTrem", "fTrem", "graceGrp"}
LETTERS = "CDEFGAB"
SEMITONES = (0, 2, 4, 5, 7, 9, 11)
STEPS = dict(zip(LETTERS, SEMITONES))
SIGN_ALTERATION = {"#": 1, "♯": 1, "b": -1, "♭": -1, "-": -1}
TOLERANCE = Fraction(1, 96)
CHORD_SYMBOL = re.compile(r"[A-G]|N\.?C\.?$")
BEAT_DENOMINATOR = 96
POSITION_DENOMINATOR = 960


class PositionError(UserError):
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
    key_signature: str = ""
    declared_length: Fraction | None = None
    label: str = ""
    name: str = ""
    full_length: Fraction | None = None
    events: list[Event] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    chord_symbols: list[tuple[Fraction, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.segments:
            self.segments = [Segment(self.id, self.index, Fraction(0))]

    @property
    def printed(self) -> int | str:
        return int(self.name) if _whole(self.name) else self.name

    @property
    def last_index(self) -> int:
        return self.segments[-1].index

    @property
    def content_length(self) -> Fraction:
        return max((event.onset + event.duration for event in self.events), default=Fraction(0))

    @property
    def length(self) -> Fraction:
        return self.declared_length if self.declared_length is not None else self.content_length

    @property
    def is_short(self) -> bool:
        return self.full_length is not None and 0 < self.content_length < self.full_length - TOLERANCE

    @property
    def is_pickup(self) -> bool:
        return self.index == 1 and self.number == 0

    @property
    def pickup_padding(self) -> Fraction:
        return self.full_length - self.length if self.is_pickup and self.full_length is not None else Fraction(0)

    def segment_at(self, offset: Fraction) -> Segment:
        return next(segment for segment in reversed(self.segments) if segment.start <= offset or segment is self.segments[0])

    def offset_of(self, beat: float) -> Fraction:
        offset = (Fraction(beat).limit_denominator(BEAT_DENOMINATOR) - 1) * self.beat_length
        if round(beat, 2) == beat:
            nearest = min((event.onset for event in self.events), key=lambda onset: abs(onset - offset), default=offset)
            if abs(nearest - offset) <= self.beat_length / 200:
                offset = nearest
        if offset < 0 or (self.length and offset >= self.length):
            beats = float(self.length / self.beat_length)
            raise PositionError(f"Measure {self.name} has no beat {beat}; its beats run from 1 up to {1 + beats:g}")
        return offset

    def beat_of(self, offset: Fraction) -> float:
        return float(offset / self.beat_length + 1)

    @property
    def beat_unit(self) -> int:
        return parse_meter(self.meter)[1] if self.meter else 4

    def tstamp_of(self, segment: Segment, offset: Fraction) -> float:
        return float(1 + (offset - segment.start) * self.beat_unit / 4)

    def offset_at_tstamp(self, segment: Segment, tstamp: str) -> Fraction:
        return segment.start + max(Fraction(tstamp).limit_denominator(POSITION_DENOMINATOR) - 1, Fraction(0)) * 4 / self.beat_unit

    @property
    def beat_count(self) -> int:
        return int(self.length / self.beat_length + 1 - TOLERANCE) if self.length else 0


def alteration(signs: str) -> int:
    return sum(SIGN_ALTERATION.get(sign, 0) for sign in signs)


def pitch_class(name: str) -> int:
    return (STEPS[name[0].upper()] + alteration(name[1:])) % 12


def normalise_pitch(pitch: str) -> str:
    return pitch[0].upper() + pitch[1:].replace("-", "b")


NOTE_TYPE_LENGTH = {"whole": 4, "half": 2, "quarter": 1, "eighth": Fraction(1, 2),
                    "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}


def beat_length(count: int, unit: int) -> Fraction:
    if unit == 8 and count > 3 and count % 3 == 0:
        return Fraction(3, 2)
    return Fraction(4, unit)


def bar_length(count: int, unit: int) -> Fraction:
    return Fraction(count * 4, unit)


def read_meter(signatures: Iterable[tuple[str | None, str | None]]) -> tuple[int, int] | None:
    read = []
    for count, unit in signatures:
        terms = [term.strip() for term in (count or "").split("+")]
        unit = (unit or "").strip()
        if not all(term.isdigit() for term in terms) or not unit.isdigit() or int(unit) == 0:
            return None
        read.append((sum(map(int, terms)), int(unit)))
    if not read:
        return None
    shared_unit = math.lcm(*(unit for _, unit in read))
    return sum(count * shared_unit // unit for count, unit in read), shared_unit


def parse_meter(text: str) -> tuple[int, int]:
    count, unit = text.split("/")
    return int(count), int(unit)


def musicxml_meter(time: ET.Element | None) -> tuple[int, int] | None:
    if time is None:
        return None
    return read_meter(zip((beats.text for beats in time.findall("beats")), (unit.text for unit in time.findall("beat-type"))))


def _whole(label: str) -> bool:
    return label.lstrip("-").isdigit()


def _printed_number(name: str) -> int | None:
    digits = re.match(r"\d+", name)
    return int(digits.group(0)) if digits else None


def _letters(count: int) -> str:
    letters = ""
    while count:
        count, rest = divmod(count - 1, 26)
        letters = chr(ord("a") + rest) + letters
    return letters


def _fifths_of(semitones: int, steps: str | None) -> int:
    return 7 * semitones - 12 * int(steps) if steps is not None else (7 * semitones + 6) % 12 - 6


def fifths_of_signature(signature: str) -> int:
    if signature in ("", "0"):
        return 0
    return int(signature[:-1]) * (1 if signature[-1] == "s" else -1)


def signature_of_fifths(fifths: int) -> str:
    return "0" if fifths == 0 else f"{abs(fifths)}{'s' if fifths > 0 else 'f'}"


def _shifted(signature: str | None, fifths: int) -> str | None:
    if not signature or not fifths:
        return signature
    return signature_of_fifths(fifths_of_signature(signature) + fifths)


def transpose(pitch: str, semitones: int) -> str:
    diatonic = round(semitones * 7 / 12)
    accidental = pitch[1:].rstrip("0123456789")
    octave = int(pitch[1 + len(accidental) :])
    step = LETTERS.index(pitch[0])
    sounding = SEMITONES[step] + alteration(accidental) + 12 * octave + semitones
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
    played: list[Measure] | None = None

    def __init__(self, mei: str):
        root = ET.fromstring(mei)
        self.measures: list[Measure] = []
        self.meter = ""
        self.key_signature = ""
        self.renumbered = False
        self.named_by_count = False
        self._ppq: dict[int, int] = {}
        self._transposition: dict[int, int] = {}
        self._written_fifths: dict[int, int] = {}
        self._beat_length = Fraction(1)
        self._bar_length: Fraction | None = None
        self._meter_is_a_sum = False
        self._meter = ""
        self._key_signature = ""
        self._position = 0
        self._drawn_bars = 0
        self._drawn_position: dict[int, int] = {}
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
        self._name_bars()
        self._finish()

    @classmethod
    def from_measures(cls, measures: list[Measure], meter: str, key_signature: str) -> ScoreIndex:
        index = cls.__new__(cls)
        index.measures, index.meter, index.key_signature, index.renumbered = measures, meter, key_signature, False
        index.named_by_count = False
        for measure in measures:
            measure.name = measure.name or str(measure.number)
        index._finish()
        return index

    def _finish(self) -> None:
        self._by_number = {measure.number: measure for measure in self.measures}
        self._by_name = {measure.name: measure for measure in self.measures}
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
                self._transposition[staff] = int(staff_def.get("trans.semi"))
                self._written_fifths[staff] = _fifths_of(int(staff_def.get("trans.semi")), staff_def.get("trans.diat"))
        self._read_meter(element)
        concert = [staff_def.find(f"{MEI}keySig") for staff_def in element.iter(f"{MEI}staffDef")
                   if int(staff_def.get("n", "1")) not in self._transposition]
        key = next((found for found in concert if found is not None), None)
        signature = key.get("sig") if key is not None else None
        if signature is None and (shared := element.find(f"{MEI}keySig")) is not None:
            signature = _shifted(shared.get("sig"), self._written_fifths.get(1, 0))
        if signature is None:
            written = next(((int(staff_def.get("n", "1")), found) for staff_def in element.iter(f"{MEI}staffDef")
                            if (found := staff_def.find(f"{MEI}keySig")) is not None), None)
            signature = (_shifted(written[1].get("sig"), self._written_fifths.get(written[0], 0)) if written
                         else element.get("keysig") or element.get("key.sig"))
        if signature:
            self._key_signature = signature
            self.key_signature = self.key_signature or signature

    def _read_meter(self, element: ET.Element) -> None:
        group = element.find(f".//{MEI}meterSigGrp")
        if group is not None and group.get("func") == "mixed":
            signatures = group.findall(f"{MEI}meterSig")
        else:
            signatures = [found for found in [element.find(f".//{MEI}meterSig")] if found is not None] or [element]
        count, unit = element.get("meter.count"), element.get("meter.unit")
        written = [(signature.get("count", count), signature.get("unit", unit)) for signature in signatures]
        meter = read_meter(written)
        if meter:
            self._meter_is_a_sum = len(written) > 1 or "+" in written[0][0]
            self._beat_length = beat_length(*meter)
            self._bar_length = bar_length(*meter)
            self._meter = "{}/{}".format(*meter)
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
        self._drawn_bars += 1
        self._drawn_position[self._position] = self._drawn_bars
        self._read_meter(element)
        label = element.get("label", element.get("n", ""))
        if label != element.get("n", ""):
            self.renumbered = True
        numbered = label.lstrip("-").isdigit()
        incomplete = element.get("metcon") == "false"
        previous = self.measures[-1] if self.measures else None
        measure = Measure(
            id=element.get(XML_ID),
            number=int(label) if numbered else previous.number + 1 if previous else 1,
            index=self._position,
            beat_length=self._beat_length,
            meter=self._meter,
            key_signature=self._key_signature,
            label=label,
            name=element.get("n", "") if element.get("label") is not None else "",
            full_length=self._bar_length,
        )
        full = self._bar_length
        if not incomplete:
            measure.declared_length = full
        for staff in element.findall(f"{MEI}staff"):
            number = int(staff.get("n", "1"))
            for position, layer in enumerate(staff.findall(f"{MEI}layer"), start=1):
                self._layer = int(layer.get("n")) if layer.get("n", "").isdigit() else position
                self._read_layer(layer, measure, number, Fraction(0))
        if self._meter_is_a_sum and full is not None and abs(measure.content_length - full) <= TOLERANCE:
            incomplete = False
            measure.declared_length = full
        if not measure.events and full is not None:
            measure.declared_length = full
        for tie in element.findall(f"{MEI}tie"):
            self._tie_starts.add((tie.get("startid") or "").lstrip("#"))
        for harm in element.findall(f"{MEI}harm"):
            symbol = "".join(harm.itertext()).strip().replace("♭", "b").replace("♯", "#")
            at = measure.offset_at_tstamp(measure.segments[0], harm.get("tstamp", "1"))
            if CHORD_SYMBOL.match(symbol) and (at, symbol) not in measure.chord_symbols:
                measure.chord_symbols.append((at, symbol))

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
            previous.chord_symbols.extend((at + shift, symbol) for at, symbol in measure.chord_symbols)
            return
        self.measures.append(measure)
        rest = element.find(f".//{MEI}multiRest")
        for following in range(1, int(rest.get("num", "1")) if rest is not None else 1):
            self._position += 1
            self._drawn_position[self._position] = self._drawn_bars
            self.measures.append(Measure(f"{measure.id}-{following}", measure.number + following, self._position, self._beat_length,
                                         self._meter, self._key_signature, full,
                                         label=str(measure.number + following) if numbered else "", full_length=full))

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
                pitch = transpose(_pitch(note), shift) if shift else _pitch(note)
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
        number = 0 if first.declared_length is None and first.is_short else 1
        for measure in self.measures:
            measure.number = number
            for event in measure.events:
                event.measure = number
            number += 1

    def _name_bars(self) -> None:
        numbers = [int(measure.label) for measure in self.measures if _whole(measure.label)]
        names = self._printed_names() if all(earlier <= later for earlier, later in zip(numbers, numbers[1:])) else []
        if len(set(names)) < len(self.measures):
            self.named_by_count = True
            names = [str(measure.number) for measure in self.measures]
        for measure, name in zip(self.measures, names):
            measure.name = measure.name or name

    def _printed_names(self) -> list[str]:
        names, base, extra = [], None, 0
        for measure, following in zip(self.measures, self.measures[1:] + [None]):
            if measure.is_pickup and following is not None and measure.label == following.label:
                names.append("0")
            elif _whole(measure.label) and (base is None or int(measure.label) > base):
                base, extra = int(measure.label), 0
                names.append(str(base))
            elif base is None:
                names.append(str(measure.number))
            else:
                extra += 1
                names.append(f"{base}{_letters(extra)}")
        return names

    @property
    def name_span(self) -> str:
        return f"{self.measures[0].name} to {self.measures[-1].name}"

    def bar(self, name: str | int) -> Measure:
        wanted = str(name).strip().lower()
        if wanted not in self._by_name:
            raise PositionError(f"Measure {wanted} does not exist; the score has measures {self.name_span}")
        return self._by_name[wanted]

    def numbers(self, names: tuple[str, str] | None) -> tuple[int, int] | None:
        if names is None:
            return None
        asked = [str(name).strip().lower() for name in names]
        first, last = self._range_end(asked[0], first=True), self._range_end(asked[1], first=False)
        if first.number > last.number and first.name != asked[0] and last.name != asked[1]:
            self.bar(asked[0])
        if first.number > last.number:
            raise PositionError(f"Measures {asked[0]}-{asked[1]} run backwards; give the first bar first, e.g. {asked[1]}-{asked[0]}")
        return first.number, last.number

    def _range_end(self, name: str, *, first: bool) -> Measure:
        wanted = str(name).strip().lower()
        if wanted in self._by_name or not wanted.isdigit():
            return self.bar(wanted)
        printed = [measure for measure in self.measures if _printed_number(measure.name) is not None]
        inside = [measure for measure in printed if (_printed_number(measure.name) >= int(wanted)) == first]
        if not inside:
            return self.bar(wanted)
        return inside[0] if first else inside[-1]

    def name_of(self, number: int) -> str:
        return self.measure(number).name

    def measure(self, number: int) -> Measure:
        if number not in self._by_number:
            raise PositionError(f"Measure {number} does not exist; the score has measures {self.name_span}")
        return self._by_number[number]

    def select(self, first: int | None = None, last: int | None = None, *, include_pickup: bool = True) -> list[Measure]:
        start = self.measures.index(self.measure(first)) if first is not None else 0
        end = self.measures.index(self.measure(last)) if last is not None else len(self.measures) - 1
        if include_pickup and first == 1 and start == 1 and self.measures[0].is_pickup:
            start = 0
        return self.measures[start : end + 1]

    def measure_range(self, first: int, last: int, *, include_pickup: bool = True) -> str:
        chosen = self.select(first, last, include_pickup=include_pickup)
        return f"{self._drawn_position[chosen[0].index]}-{self._drawn_position[chosen[-1].last_index]}"

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
            raise PositionError(f"No note matches staff={staff} pitch={pitch} at measure {bar.name} beat {beat}; notes there: {found}")
        beats = sorted({round(bar.beat_of(event.onset), 3) for event in notes})
        raise PositionError(f"No note starts at measure {bar.name} beat {beat}; notes start at beats {beats}")
