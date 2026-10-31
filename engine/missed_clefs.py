import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction

_STEPS = "CDEFGAB"
_SEMITONES = (0, 2, 4, 5, 7, 9, 11)
_CLEF_POSITION = {("G", "2"): 0, ("F", "4"): -12}
_ACCIDENTALS = {"sharp": 1, "flat": -1, "natural": 0, "double-sharp": 2, "flat-flat": -2}
MIN_CROSSINGS_REMOVED = 3
MOST_OF_THE_GAIN = Fraction(3, 4)


@dataclass
class _Note:
    element: ET.Element
    measure: int
    staff: str
    start: Fraction
    end: Fraction
    step: int
    octave: int
    alter: int

    @property
    def midi(self) -> int:
        return _midi(self.step, self.octave, self.alter)


def _midi(step: int, octave: int, alter: int) -> int:
    return (octave + 1) * 12 + _SEMITONES[step] + alter


def _key_alter(fifths: int, step: int) -> int:
    if fifths > 0 and "FCGDAEB".index(_STEPS[step]) < fifths:
        return 1
    if fifths < 0 and "BEADGCF".index(_STEPS[step]) < -fifths:
        return -1
    return 0


def _read(part: ET.Element):
    notes, clefs, keys, line_starts, starts = [], [], [], [], []
    divisions, start = 1, Fraction(0)
    for index, measure in enumerate(part.iter("measure")):
        printed = measure.find("print")
        if index == 0 or (printed is not None and "yes" in (printed.get("new-system"), printed.get("new-page"))):
            line_starts.append(index)
        starts.append(start)
        cursor = longest = Fraction(0)
        for element in measure:
            if element.tag == "attributes":
                if element.findtext("divisions"):
                    divisions = int(element.findtext("divisions"))
                for clef in element.findall("clef"):
                    clefs.append((index, start + cursor, clef.get("number", "1"), (clef.findtext("sign"), clef.findtext("line")), element, clef))
                for key in element.findall("key"):
                    if key.findtext("fifths"):
                        keys.append((start + cursor, int(key.findtext("fifths"))))
            elif element.tag == "backup":
                cursor -= Fraction(element.findtext("duration", "0")) / divisions
            elif element.tag == "forward":
                cursor += Fraction(element.findtext("duration", "0")) / divisions
            elif element.tag == "note":
                length = Fraction(element.findtext("duration", "0")) / divisions
                if element.find("chord") is not None:
                    cursor -= length
                pitch = element.find("pitch")
                if pitch is not None:
                    notes.append(_Note(element, index, element.findtext("staff", "1"), start + cursor, start + cursor + length,
                                       _STEPS.index(pitch.findtext("step")), int(pitch.findtext("octave")), int(float(pitch.findtext("alter", "0")))))
                cursor += length
            longest = max(longest, cursor)
        start += longest
    return notes, clefs, keys, line_starts, starts


def _crossings(note: _Note, midi: int, others: list[_Note]) -> int:
    for other in others:
        if other.start < note.end and note.start < other.end and other.staff != note.staff:
            if (note.staff > other.staff and midi > other.midi) or (note.staff < other.staff and midi < other.midi):
                return 1
    return 0


def _flipped(note: _Note, shift: int, fifths: int) -> tuple[int, int, int]:
    position = note.octave * 7 + note.step + shift
    step, octave = position % 7, position // 7
    accidental = _ACCIDENTALS.get(note.element.findtext("accidental"))
    if accidental is not None:
        return step, octave, accidental
    if note.alter != _key_alter(fifths, note.step):
        return step, octave, note.alter
    return step, octave, _key_alter(fifths, step)


def _set_pitch(note: _Note, step: int, octave: int, alter: int) -> None:
    pitch = note.element.find("pitch")
    pitch.find("step").text = _STEPS[step]
    pitch.find("octave").text = str(octave)
    old = pitch.find("alter")
    if old is not None:
        pitch.remove(old)
    if alter:
        element = ET.Element("alter")
        element.text = str(alter)
        pitch.insert(1, element)


def _repair(part: ET.Element) -> bool:
    notes, clefs, keys, line_starts, starts = _read(part)
    measures = list(part.iter("measure"))
    repaired = False
    for k, at, staff, clef, attributes, element in clefs:
        if k == 0 or k not in line_starts or at != starts[k]:
            continue
        before = [c for c in clefs if c[2] == staff and c[1] < at]
        if not before or before[-1][3] == clef or not {before[-1][3], clef} <= _CLEF_POSITION.keys():
            continue
        line = max(start for start in line_starts if start < k)
        region = [n for n in notes if n.staff == staff and line <= n.measure < k and n.start >= before[-1][1]]
        if not region:
            continue
        shift = _CLEF_POSITION[clef] - _CLEF_POSITION[before[-1][3]]
        nearby = [n for n in notes if n.staff != staff and line <= n.measure < k]
        changes = []
        for note in region:
            fifths = next((f for t, f in reversed(keys) if t <= note.start), 0)
            new = _flipped(note, shift, fifths)
            if not 21 <= _midi(*new) <= 108:
                break
            changes.append((note, new, _crossings(note, _midi(*new), nearby) - _crossings(note, note.midi, nearby)))
        else:
            points = sorted({note.start for note in region})
            gains = {point: sum(delta for note, _, delta in changes if note.start >= point) for point in points}
            best = min(gains.values())
            if best > -MIN_CROSSINGS_REMOVED:
                continue
            point = max(point for point, gain in gains.items() if gain <= best * MOST_OF_THE_GAIN)
            moved = [(note, new) for note, new, _ in changes if note.start >= point]
            for note, new in moved:
                _set_pitch(note, *new)
            first = min((note for note, _ in moved), key=lambda note: (note.start, list(measures[note.measure]).index(note.element)))
            restated = ET.Element("attributes")
            restated.append(element)
            attributes.remove(element)
            if len(attributes) == 0:
                measures[k].remove(attributes)
            target = measures[first.measure]
            target.insert(list(target).index(first.element), restated)
            repaired = True
    return repaired


def restore_missed_clefs(score: bytes) -> bytes:
    root = ET.fromstring(score)
    repaired = [_repair(part) for part in root.iter("part") if part.find("measure/attributes/staves") is not None]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) if any(repaired) else score
