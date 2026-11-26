from __future__ import annotations

import copy
import io
import math
import re
import statistics
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar, LTCurve, LTLine, LTRect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import PDFException
from pdfminer.psexceptions import PSException

from engine import correct

STANDARD_TUNINGS = {4: ["G2", "D2", "A1", "E1"], 6: ["E4", "B3", "G3", "D3", "A2", "E2"],
                    7: ["E4", "B3", "G3", "D3", "A2", "E2", "B1"]}
STAFF_LINES = {4, 5, 6, 7}
SMUFL_TIME_DIGITS = {chr(0xE080 + digit): str(digit) for digit in range(10)}
SMUFL_TIME_WHOLE = {"": (4, 4), "": (2, 2)}
SMUFL_RESTS = {"": Fraction(4), "": Fraction(2), "": Fraction(1), "": Fraction(1, 2),
               "": Fraction(1, 4), "": Fraction(1, 8), "": Fraction(1, 16)}
SMUFL_FLAGS = {chr(0xE240 + index): index // 2 + 1 for index in range(8)}
SMUFL_DOT = ""
SMUFL_TUPLET_DIGITS = {chr(0xE880 + digit): str(digit) for digit in range(10)}
SMUFL_REPEAT_DOTS = {"", ""}
TUPLETS = {3: 2, 5: 4, 6: 4, 7: 4}
NOTE_TYPES = {Fraction(4): "whole", Fraction(2): "half", Fraction(1): "quarter", Fraction(1, 2): "eighth",
              Fraction(1, 4): "16th", Fraction(1, 8): "32nd", Fraction(1, 16): "64th"}
NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
TUNING_TEXT = re.compile(r"tuning\s*:?\s*((?:[A-G][#b♯♭]?\s*){4,7})", re.IGNORECASE)
DROP_TEXT = re.compile(r"\bdrop\s*([A-G][#b♯♭]?)\b", re.IGNORECASE)
CAPO_TEXT = re.compile(r"\bcapo\s*(?:fret\s*)?(\d{1,2}|[IVX]{1,5})\b", re.IGNORECASE)
ROMAN = {"I": 1, "V": 5, "X": 10}
TABLATURE_UNDER_STAFF = False


@dataclass
class TabReading:
    musicxml: bytes
    pages: int
    tuning: list[str]
    tuning_printed: bool
    capo: int
    meter_printed: bool
    doubtful: list[int]
    notes: int
    beside_staff: bool

    def facts(self) -> dict:
        return {"tuning": self.tuning, "tuning_printed": self.tuning_printed, "capo": self.capo, "doubtful": self.doubtful,
                "notes": self.notes}


@dataclass
class Glyph:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    size: float
    font: str
    origin_x: float
    origin_y: float

    @property
    def x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Shape:
    x0: float
    x1: float
    y0: float
    y1: float
    thickness: float
    curved: bool = False

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Staff:
    page: int
    lines: list[float]
    x0: float
    x1: float

    @property
    def gap(self) -> float:
        return (self.lines[0] - self.lines[-1]) / (len(self.lines) - 1)

    @property
    def top(self) -> float:
        return self.lines[0]

    @property
    def bottom(self) -> float:
        return self.lines[-1]


@dataclass
class Fret:
    string: int
    fret: int
    x: float
    bracketed: bool
    tie_stop: bool = False
    tie_start: bool = False


@dataclass
class Stem:
    x: float
    up: bool
    outer: float
    reach: float
    inner: float
    beams: int = 0
    flags: int = 0
    dots: int = 0
    tuplet: Fraction = Fraction(1)
    group: int | None = None


@dataclass
class Item:
    x: float
    frets: list[Fret]
    length: Fraction | None
    voice: int = 1
    rest: bool = False
    tuplet: Fraction = Fraction(1)
    gap: float = 0
    stem: Stem | None = None


@dataclass
class Page:
    glyphs: list[Glyph]
    shapes: list[Shape]
    width: float
    height: float


def read_tab(data: bytes) -> TabReading | None:
    try:
        pages = _pages(data)
    except (PDFException, PSException):
        return None
    every_staff = [staff for number, page in enumerate(pages) for staff in _staves(page, number)]
    tops = {number: [staff.top for staff in every_staff if staff.page == number] for number in range(len(pages))}
    staves = [staff for staff in every_staff if len(staff.lines) in STANDARD_TUNINGS]
    fret_font = _fret_font(pages, staves)
    if fret_font is None:
        return None
    frets_of = {id(staff): _frets(pages[staff.page], staff, fret_font) for staff in staves}
    strings = Counter(len(staff.lines) for staff in staves if frets_of[id(staff)]).most_common(1)
    if not strings:
        return None
    staves = [staff for staff in staves if len(staff.lines) == strings[0][0]]
    text = _page_texts(pages)
    tuning, printed = _tuning(text, pages, staves, fret_font)
    capo = _capo(text)
    zones = {id(staff): _zone(pages[staff.page], staff, every_staff) for staff in staves}
    full_stems = _full_reach(zones, staves, tops)
    bars, meters, repeats = [], {}, {}
    for staff in staves:
        _read_staff(zones[id(staff)], staff, frets_of[id(staff)], fret_font, full_stems, tops[staff.page], bars, meters, repeats)
    if not any(item.frets for bar in bars for item in bar):
        return None
    meter, meter_printed = _meter(meters, bars)
    doubtful_positions = [position for position, bar in enumerate(bars) if _settle(bar, _meter_at(meters, position, meter))]
    open_strings = [_midi(name) + capo for name in tuning]
    first_full = sum((item.length for item in _voice(bars[0], 1)), Fraction(0))
    pickup = bool(bars[0]) and first_full < _bar_length(_meter_at(meters, 0, meter))
    numbers = [position if pickup else position + 1 for position in range(len(bars))]
    musicxml = _musicxml(bars, meters, meter, numbers, pickup, repeats, open_strings, len(tuning))
    return TabReading(laid_out(musicxml, tuning), len(pages), tuning, printed, capo, meter_printed,
                      [numbers[position] for position in doubtful_positions],
                      sum(len(item.frets) for bar in bars for item in bar),
                      any(len(staff.lines) == 5 for staff in every_staff))


def laid_out(score: bytes, tuning: list[str]) -> bytes:
    return with_tablature_staff(score, tuning) if TABLATURE_UNDER_STAFF else score


def with_tablature_staff(score: bytes, tuning: list[str]) -> bytes:
    root = ET.fromstring(score)
    for measure in root.iter("measure"):
        attributes = measure.find("attributes")
        if attributes is not None and attributes.find("divisions") is not None:
            attributes.find("clef").set("number", "1")
            attributes.insert(list(attributes).index(attributes.find("clef")), ET.Element("staves"))
            attributes.find("staves").text = "2"
            clef = ET.SubElement(attributes, "clef", number="2")
            ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = "TAB", "5"
            details = ET.SubElement(attributes, "staff-details", number="2")
            ET.SubElement(details, "staff-lines").text = str(len(tuning))
            for line, name in enumerate(reversed(tuning), 1):
                string = ET.SubElement(details, "staff-tuning", line=str(line))
                ET.SubElement(string, "tuning-step").text = name[0]
                if name[1:-1]:
                    ET.SubElement(string, "tuning-alter").text = "1" if name[1] == "#" else "-1"
                ET.SubElement(string, "tuning-octave").text = name[-1]
        timed = [element for element in measure if element.tag in ("note", "backup", "forward")]
        cursor = 0
        for element in timed:
            if element.tag == "note":
                ET.SubElement(element, "staff").text = "1"
            if element.tag == "backup":
                cursor -= int(element.findtext("duration"))
            elif element.find("chord") is None:
                cursor += int(element.findtext("duration"))
        ET.SubElement(ET.SubElement(measure, "backup"), "duration").text = str(cursor)
        for element in timed:
            copied = copy.deepcopy(element)
            if copied.find("voice") is not None:
                copied.find("voice").text = str(int(copied.findtext("voice")) + 4)
            if copied.tag == "note":
                copied.find("staff").text = "2"
                for sign in copied.findall("accidental"):
                    copied.remove(sign)
            measure.append(copied)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def notice(facts: dict) -> str:
    names = " ".join(name[:-1] for name in reversed(facts["tuning"]))
    text = (f"The notes were read from the fret numbers of the tablature, with the tuning printed on it ({names})."
            if facts["tuning_printed"] else
            f"The notes were read from the fret numbers of the tablature, in standard "
            f"{'bass' if len(facts['tuning']) == 4 else 'guitar'} tuning ({names}) because no tuning is printed on it.")
    return text + (f" The capo on fret {facts['capo']} is counted in." if facts["capo"] else "")


def _pages(data: bytes) -> list[Page]:
    resources = PDFResourceManager()
    device = PDFPageAggregator(resources, laparams=None)
    interpreter = PDFPageInterpreter(resources, device)
    pages = []
    for page in PDFPage.get_pages(io.BytesIO(data)):
        interpreter.process_page(page)
        pages.append(_page(device.get_result()))
    return pages


def _page(layout) -> Page:
    glyphs, shapes = [], []

    def walk(node):
        for item in node:
            if isinstance(item, LTChar):
                glyphs.append(Glyph(item.get_text(), item.x0, item.x1, item.y0, item.y1, item.size, item.fontname,
                                    item.matrix[4], item.matrix[5]))
            elif isinstance(item, LTCurve):
                if not _white(item):
                    shapes.append(_shape(item))
            elif hasattr(item, "__iter__"):
                walk(item)

    walk(layout)
    return Page(glyphs, shapes, layout.width, layout.height)


def _white(item: LTCurve) -> bool:
    colour = item.non_stroking_color if item.fill else item.stroking_color
    values = colour if isinstance(colour, (list, tuple)) else [colour]
    return len(values) in (1, 3) and all(isinstance(value, (int, float)) and value >= 0.95 for value in values)


def _shape(item: LTCurve) -> Shape:
    width = item.linewidth if item.stroke else 0
    if isinstance(item, LTLine):
        return Shape(item.x0, item.x1, item.y0, item.y1, width)
    curved = any(segment[0] in "cvy" for segment in item.original_path or [])
    if isinstance(item, LTRect) or (len(item.pts) == 4 and not curved):
        left = sorted(item.pts, key=lambda point: point[0])[:2]
        thickness = abs(left[0][1] - left[1][1]) if item.width >= item.height else item.width
        return Shape(item.x0, item.x1, item.y0, item.y1, thickness + width)
    return Shape(item.x0, item.x1, item.y0, item.y1, min(item.width, item.height) + width, curved)


def _staves(page: Page, number: int) -> list[Staff]:
    flat = [shape for shape in page.shapes if not shape.curved and shape.width > 0
            and shape.height <= max(shape.width / 8, shape.thickness * 1.5)]
    if not flat:
        return []
    weights = Counter()
    for shape in flat:
        weights[round(shape.thickness, 2)] += shape.width
    line = max(weights.most_common(1)[0][0], page.height / 5000)
    rows = []
    for shape in sorted((shape for shape in flat if shape.thickness <= 2.5 * line), key=lambda shape: (shape.y0 + shape.y1) / 2):
        middle = (shape.y0 + shape.y1) / 2
        if rows and middle - rows[-1][0] <= max(line, page.height / 2000):
            rows[-1][1].append((shape.x0, shape.x1))
        else:
            rows.append((middle, [(shape.x0, shape.x1)]))
    long_rows = []
    for middle, spans in rows:
        covered, start, end = _union(spans)
        if covered >= 0.08 * page.width and covered >= 0.8 * (end - start):
            long_rows.append((middle, start, end))
    long_rows.sort(key=lambda row: -row[0])
    staves, index = [], 0
    while index < len(long_rows) - 1:
        gap = long_rows[index][0] - long_rows[index + 1][0]
        end = index + 1
        while (end + 1 < len(long_rows) and abs((long_rows[end][0] - long_rows[end + 1][0]) - gap) <= 0.08 * gap
               and abs(long_rows[end + 1][1] - long_rows[index][1]) < 2 * gap
               and abs(long_rows[end + 1][2] - long_rows[index][2]) < 2 * gap):
            end += 1
        run = long_rows[index:end + 1]
        if len(run) in STAFF_LINES and gap < page.height / 20:
            staves.append(Staff(number, [row[0] for row in run], min(row[1] for row in run), max(row[2] for row in run)))
        index = end + 1 if len(run) >= 4 else index + 1
    return staves


def _union(spans: list[tuple[float, float]]) -> tuple[float, float, float]:
    covered, reach = 0.0, None
    for start, end in sorted(spans):
        if reach is None or start > reach:
            covered += end - start
            reach = end
        elif end > reach:
            covered += end - reach
            reach = end
    return covered, min(start for start, _ in spans), max(end for _, end in spans)


def _near_line(staff: Staff, y: float) -> tuple[int, float]:
    index = min(range(len(staff.lines)), key=lambda line: abs(staff.lines[line] - y))
    return index, y - staff.lines[index]


def _inside(staff: Staff, glyph: Glyph) -> bool:
    return (staff.x0 - staff.gap <= glyph.x <= staff.x1 + staff.gap
            and staff.bottom - staff.gap <= glyph.y <= staff.top + staff.gap)


def _fret_font(pages: list[Page], staves: list[Staff]) -> tuple[str, float, float] | None:
    seen, offsets = Counter(), {}
    for staff in staves:
        for glyph in pages[staff.page].glyphs:
            if glyph.text.isdigit() and _inside(staff, glyph):
                _, offset = _near_line(staff, glyph.y)
                key = (glyph.font, round(glyph.size, 1))
                seen[key] += 1
                offsets.setdefault(key, []).append(offset / staff.gap)
    if not seen:
        return None
    font, size = seen.most_common(1)[0][0]
    shift = statistics.median(offsets[(font, size)])
    if sum(abs(offset - shift) < 0.25 for offset in offsets[(font, size)]) < 0.6 * len(offsets[(font, size)]):
        return None
    return font, size, shift


def _is_fret_glyph(glyph: Glyph, fret_font) -> bool:
    font, size, _ = fret_font
    return glyph.font == font and abs(glyph.size - size) <= 0.03 * size


def _frets(page: Page, staff: Staff, fret_font) -> list[Fret]:
    shift = fret_font[2] * staff.gap
    marks = []
    for glyph in page.glyphs:
        if (glyph.text.isdigit() or glyph.text in "()") and _is_fret_glyph(glyph, fret_font) and _inside(staff, glyph):
            line, offset = _near_line(staff, glyph.y - shift)
            if abs(offset) < 0.35 * staff.gap:
                marks.append((line, glyph))
    marks.sort(key=lambda mark: (mark[0], mark[1].x0))
    frets, merged = [], []
    for line, glyph in marks:
        if merged and merged[-1][0] == line and glyph.x0 - merged[-1][-1].x1 < 0.3 * (glyph.x1 - glyph.x0):
            merged[-1].append(glyph)
        else:
            merged.append([line, glyph])
    for line, *glyphs in merged:
        text = "".join(glyph.text for glyph in glyphs)
        digits = text.strip("()")
        if digits.isdigit():
            number = [glyph for glyph in glyphs if glyph.text.isdigit()]
            frets.append(Fret(line + 1, int(digits), (number[0].x0 + number[-1].x1) / 2, text.startswith("(")))
    return frets


def _page_texts(pages: list[Page]) -> str:
    lines = []
    for page in pages:
        rows = []
        for glyph in sorted(page.glyphs, key=lambda glyph: (-round(glyph.y0), glyph.x0)):
            if rows and abs(rows[-1][0].y0 - glyph.y0) < 0.3 * glyph.size:
                rows[-1].append(glyph)
            else:
                rows.append([glyph])
        for row in rows:
            row.sort(key=lambda glyph: glyph.x0)
            text = row[0].text
            for before, glyph in zip(row, row[1:]):
                text += (" " if glyph.x0 - before.x1 > 0.2 * glyph.size else "") + glyph.text
            lines.append(text)
    return "\n".join(lines)


def _tuning(text: str, pages: list[Page], staves: list[Staff], fret_font) -> tuple[list[str], bool]:
    standard = STANDARD_TUNINGS[len(staves[0].lines)]
    named = TUNING_TEXT.search(text)
    letters = re.findall(r"[A-G][#b♯♭]?", named.group(1)) if named else []
    if len(letters) == len(standard):
        return _octaves(list(reversed(letters)), standard), True
    at_staff = _letters_at_staff(pages[staves[0].page], staves[0], fret_font)
    if at_staff:
        return _octaves(at_staff, standard), True
    drop = DROP_TEXT.search(text)
    if drop:
        return _octaves(standard[:-1] + [drop.group(1)], standard), True
    return standard, False


def _letters_at_staff(page: Page, staff: Staff, fret_font) -> list[str] | None:
    first = min((glyph.x0 for glyph in page.glyphs if glyph.text.isdigit() and _is_fret_glyph(glyph, fret_font)
                 and _inside(staff, glyph)), default=staff.x1)
    found = {}
    for glyph in page.glyphs:
        if glyph.text in NAMES and glyph.x1 <= first and staff.bottom - staff.gap < glyph.y < staff.top + staff.gap:
            line, offset = _near_line(staff, glyph.y)
            if abs(offset) < 0.35 * staff.gap and line not in found:
                after = [other for other in page.glyphs if other.text in "#b♯♭" and 0 <= other.x0 - glyph.x1 < 0.3 * glyph.size
                         and abs(other.y - glyph.y) < 0.5 * staff.gap]
                found[line] = glyph.text + (after[0].text if after else "")
    return [found[line] for line in range(len(staff.lines))] if len(found) == len(staff.lines) else None


def _octaves(letters: list[str], standard: list[str]) -> list[str]:
    names = []
    for letter, default in zip(letters, standard):
        target = _midi(default)
        pitch_class = (NAMES[letter[0]] + (1 if letter[1:] in ("#", "♯") else -1 if letter[1:] in ("b", "♭") else 0)) % 12
        midi = min((octave * 12 + 12 + pitch_class for octave in range(0, 8)), key=lambda value: (abs(value - target), value))
        names.append(f"{letter.replace('♯', '#').replace('♭', 'b')}{(midi - pitch_class) // 12 - 1}")
    return names


def _midi(name: str) -> int:
    letter, accidental, octave = name[0], name[1:-1], int(name[-1])
    return 12 * (octave + 1) + NAMES[letter] + (1 if accidental == "#" else -1 if accidental == "b" else 0)


def _capo(text: str) -> int:
    found = CAPO_TEXT.search(text)
    if not found:
        return 0
    value = found.group(1).upper()
    if value.isdigit():
        return int(value)
    total = 0
    for index, letter in enumerate(value):
        number = ROMAN[letter]
        total += -number if index + 1 < len(value) and ROMAN[value[index + 1]] > number else number
    return total


def _verticals(page: Page, staff: Staff) -> list[Shape]:
    return [shape for shape in page.shapes if shape.width <= max(shape.height / 8, 0.25 * staff.gap)
            and shape.height >= 0.5 * staff.gap and staff.x0 - staff.gap <= shape.x0 <= staff.x1 + staff.gap
            and shape.y0 < staff.top + 8 * staff.gap and shape.y1 > staff.bottom - 8 * staff.gap]


def _is_bar_line(shape: Shape, staff: Staff, tops: list[float]) -> bool:
    near = 0.35 * staff.gap
    return abs(shape.y0 - staff.bottom) < near and (abs(shape.y1 - staff.top) < near or any(abs(shape.y1 - top) < near for top in tops))


def _stem(shape: Shape, staff: Staff) -> Stem | None:
    beyond = 0.5 * staff.gap
    up, down = shape.y1 > staff.top + beyond, shape.y0 < staff.bottom - beyond
    if up == down:
        return None
    x = (shape.x0 + shape.x1) / 2
    if up:
        return Stem(x, True, shape.y1, shape.y1 - max(shape.y0, staff.top), shape.y0)
    return Stem(x, False, shape.y0, min(shape.y1, staff.bottom) - shape.y0, shape.y1)


def _zone(page: Page, staff: Staff, every_staff: list[Staff]) -> Page:
    reach = 8 * staff.gap
    neighbours = [other for other in every_staff if other.page == staff.page]
    above = min((other.bottom for other in neighbours if other.bottom > staff.top), default=staff.top + 2 * reach)
    below = max((other.top for other in neighbours if other.top < staff.bottom), default=staff.bottom - 2 * reach)
    high, low = min(staff.top + reach, (staff.top + above) / 2), max(staff.bottom - reach, (staff.bottom + below) / 2)
    return Page([glyph for glyph in page.glyphs if low <= glyph.origin_y <= high],
                [shape for shape in page.shapes if low <= (shape.y0 + shape.y1) / 2 <= high], page.width, page.height)


def _full_reach(zones: dict[int, Page], staves: list[Staff], tops: dict[int, list[float]]) -> float:
    reaches = sorted(stem.reach / staff.gap for staff in staves for shape in _verticals(zones[id(staff)], staff)
                     if not _is_bar_line(shape, staff, tops[staff.page]) and (stem := _stem(shape, staff)))
    return reaches[int(0.75 * (len(reaches) - 1))] if reaches else 0


def _read_staff(page: Page, staff: Staff, frets: list[Fret], fret_font, full_reach, tops: list[float], bars, meters, repeats):
    gap = staff.gap
    verticals = _verticals(page, staff)
    bar_xs = _clusters(sorted((shape.x0 + shape.x1) / 2 for shape in verticals if _is_bar_line(shape, staff, tops)), 1.2 * gap)
    stems = [stem for shape in verticals if not _is_bar_line(shape, staff, tops) and (stem := _stem(shape, staff))]
    stems = _distinct_stems(stems, gap)
    _beams_and_flags(page, staff, stems)
    _dots(page, staff, stems, bar_xs)
    _ties(page, staff, frets)
    rests = _rests(page, staff)
    numbers = _numbers(page, staff, fret_font)
    edges = [staff.x0] + [x for x in bar_xs if staff.x0 + gap < x < staff.x1 - gap] + [staff.x1]
    pending = None
    for left, right in zip(edges, edges[1:]):
        inside = [fret for fret in frets if left < fret.x < right]
        bar_rests = [rest for rest in rests if left < rest[0] < right]
        meter = _time_signature(page, staff, left, right, fret_font) or pending
        if not inside and not bar_rests and left == staff.x0 and right - left < 8 * gap:
            pending = meter
            continue
        pending = None
        position = len(bars)
        if meter:
            meters[position] = meter
        bar_stems = [stem for stem in stems if left < stem.x < right]
        _tuplets(numbers, bar_stems, staff)
        bars.append(_items(inside, bar_stems, bar_rests, staff, full_reach))
        repeat = _repeat_marks(page, staff, left, right, bar_xs)
        if repeat:
            repeats[position] = repeat


def _clusters(values: list[float], within: float) -> list[float]:
    groups = []
    for value in values:
        if groups and value - groups[-1][-1] <= within:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [statistics.mean(group) for group in groups]


def _distinct_stems(stems: list[Stem], gap: float) -> list[Stem]:
    kept = []
    for stem in sorted(stems, key=lambda stem: (stem.up, stem.x)):
        if kept and kept[-1].up == stem.up and abs(kept[-1].x - stem.x) < 0.15 * gap:
            if stem.reach > kept[-1].reach:
                kept[-1] = stem
            continue
        kept.append(stem)
    return kept


def _beams_and_flags(page: Page, staff: Staff, stems: list[Stem]) -> None:
    gap = staff.gap
    beams = [shape for shape in page.shapes if not shape.curved and shape.width >= 0.4 * gap and 0.15 * gap <= shape.thickness <= 0.9 * gap
             and shape.height <= max(shape.width, gap) and (shape.y0 > staff.top + 0.3 * gap or shape.y1 < staff.bottom - 0.3 * gap)]
    flag_shapes = [shape for shape in page.shapes if shape.curved and 0.3 * gap <= shape.width <= 1.5 * gap
                   and shape.height >= 0.8 * gap]
    joined = {}
    for index, stem in enumerate(stems):
        reach = (stem.outer - 0.4 * gap, stem.outer + 2.5 * gap) if not stem.up else (stem.outer - 2.5 * gap, stem.outer + 0.4 * gap)
        touching = [shape for shape in beams if shape.x0 - 0.25 * gap <= stem.x <= shape.x1 + 0.25 * gap
                    and shape.y1 >= reach[0] and shape.y0 <= reach[1]]
        stem.beams = len(_clusters(sorted((shape.y0 + shape.y1) / 2 for shape in touching), 0.25 * gap))
        if touching:
            nearest = min(abs((shape.y0 + shape.y1) / 2 - stem.outer) for shape in touching)
            for shape in touching:
                if abs((shape.y0 + shape.y1) / 2 - stem.outer) <= nearest + 0.25 * gap:
                    joined.setdefault(id(shape), []).append(index)
        smufl = [SMUFL_FLAGS[glyph.text] for glyph in page.glyphs if glyph.text in SMUFL_FLAGS
                 and abs(glyph.origin_x - stem.x) < 0.5 * gap and abs(glyph.origin_y - stem.outer) < 0.5 * gap]
        drawn = [shape for shape in flag_shapes if abs(shape.x0 - stem.x) < 0.3 * gap and shape.y1 >= reach[0] and shape.y0 <= reach[1]]
        stem.flags = max(smufl, default=0) or len(_clusters(sorted(shape.y0 for shape in drawn), 0.25 * gap))
    for members in joined.values():
        groups = {stems[index].group for index in members if stems[index].group is not None}
        group = min(groups, default=members[0])
        for stem in stems:
            if stem.group in groups:
                stem.group = group
        for index in members:
            stems[index].group = group


def _round_dots(page: Page, staff: Staff) -> list[tuple[float, float]]:
    gap = staff.gap
    dots = [(glyph.origin_x, glyph.origin_y) for glyph in page.glyphs if glyph.text == SMUFL_DOT]
    dots += [((shape.x0 + shape.x1) / 2, (shape.y0 + shape.y1) / 2) for shape in page.shapes
             if shape.curved and 0.1 * gap <= shape.width <= 0.45 * gap and 0.6 <= shape.width / max(shape.height, 1e-6) <= 1.6]
    return [(x, y) for x, y in dots if staff.x0 - gap <= x <= staff.x1 + gap and staff.bottom - 8 * gap <= y <= staff.top + 8 * gap]


def _dots(page: Page, staff: Staff, stems: list[Stem], bar_xs: list[float]) -> None:
    gap = staff.gap
    for x, y in _round_dots(page, staff):
        if any(abs(x - bar) < 1.2 * gap for bar in bar_xs) and staff.bottom < y < staff.top:
            continue
        candidates = [stem for stem in stems if 0 < x - stem.x < 1.5 * gap
                      and min(stem.outer, stem.inner) - gap <= y <= max(stem.outer, stem.inner) + gap]
        if candidates:
            min(candidates, key=lambda stem: (not min(stem.outer, stem.inner) <= y <= max(stem.outer, stem.inner), x - stem.x)).dots += 1


def _ties(page: Page, staff: Staff, frets: list[Fret]) -> None:
    gap = staff.gap
    for shape in page.shapes:
        opening = shape.x0 < staff.x0 + 3 * gap
        if not shape.curved or shape.width < (0.3 if opening else 0.5) * gap or shape.height > 0.8 * gap:
            continue
        if not (staff.x0 - gap <= shape.x0 <= staff.x1 and staff.bottom - 1.5 * gap <= shape.y0 <= staff.top + gap):
            continue
        middle = (shape.y0 + shape.y1) / 2
        after = [fret for fret in frets if shape.x1 - 0.5 * gap <= fret.x <= shape.x1 + 1.5 * gap]
        before = [fret for fret in frets if shape.x0 - 1.5 * gap <= fret.x <= shape.x0 + 0.5 * gap]
        pairs = [(first, second) for first in before for second in after if not second.tie_stop
                 and first.string == second.string and first.fret == second.fret and first is not second]
        if not pairs and opening:
            pairs = [(None, second) for second in after if not second.tie_stop]
        if not pairs:
            continue
        first, second = min(pairs, key=lambda pair: abs(staff.lines[pair[1].string - 1] - middle))
        if abs(staff.lines[second.string - 1] - middle) > 1.2 * gap:
            continue
        second.tie_stop = True
        if first:
            first.tie_start = True
    ordered = sorted(frets, key=lambda fret: (fret.string, fret.x))
    for previous, fret in zip(ordered, ordered[1:]):
        if fret.bracketed and previous.string == fret.string and previous.fret == fret.fret:
            previous.tie_start, fret.tie_stop = True, True


def _rests(page: Page, staff: Staff) -> list[tuple[float, float, Fraction, int]]:
    gap = staff.gap
    found = []
    for glyph in page.glyphs:
        if (glyph.text in SMUFL_RESTS and staff.x0 <= glyph.x <= staff.x1
                and staff.bottom - 4 * gap <= glyph.origin_y <= staff.top + 4 * gap):
            dots = sum(1 for x, y in _round_dots(page, staff)
                       if 0 < x - glyph.origin_x < 2 * gap and abs(y - glyph.origin_y) < 1.5 * gap)
            found.append((glyph.x, glyph.origin_y, SMUFL_RESTS[glyph.text] * (2 - Fraction(1, 2 ** dots)), dots))
    return found


def _numbers(page: Page, staff: Staff, fret_font) -> list[tuple[float, float, int]]:
    gap = staff.gap
    digits = sorted((glyph for glyph in page.glyphs if (glyph.text.isdigit() or glyph.text in SMUFL_TUPLET_DIGITS)
                     and not _is_fret_glyph(glyph, fret_font) and staff.x0 <= glyph.x <= staff.x1
                     and (staff.top + 0.5 * gap < glyph.y < staff.top + 6 * gap
                          or staff.bottom - 6 * gap < glyph.y < staff.bottom - 0.5 * gap)),
                    key=lambda glyph: (round(glyph.y0), glyph.x0))
    numbers, current = [], []
    for glyph in digits:
        if current and (abs(glyph.y0 - current[-1].y0) > 0.2 * glyph.size or glyph.x0 - current[-1].x1 > 0.3 * glyph.size):
            numbers.append(current)
            current = []
        current.append(glyph)
    if current:
        numbers.append(current)
    return [((group[0].x0 + group[-1].x1) / 2, statistics.mean(glyph.y for glyph in group),
             int("".join(SMUFL_TUPLET_DIGITS.get(glyph.text, glyph.text) for glyph in group))) for group in numbers]


def _tuplets(numbers, stems: list[Stem], staff: Staff) -> None:
    gap = staff.gap
    for x, y, value in numbers:
        if value not in TUPLETS:
            continue
        up = y > staff.top
        side = [stem for stem in stems if stem.up == up and abs(stem.outer - y) < 3 * gap]
        group = sorted(sorted(side, key=lambda stem: abs(stem.x - x))[:value], key=lambda stem: stem.x)
        if len(group) == value and group[0].x - 0.5 * gap <= x <= group[-1].x + 0.5 * gap:
            for stem in group:
                stem.tuplet = Fraction(TUPLETS[value], value)


def _stem_length(stem: Stem, staff: Staff, full_reach) -> Fraction:
    if stem.beams or stem.flags:
        length = Fraction(1, 2 ** max(stem.beams, stem.flags))
    elif stem.reach / staff.gap < 0.75 * full_reach:
        length = Fraction(2)
    else:
        length = Fraction(1)
    return length * (2 - Fraction(1, 2 ** stem.dots)) * stem.tuplet


def _items(frets: list[Fret], stems: list[Stem], rests, staff: Staff, full_reach) -> list[Item]:
    gap = staff.gap
    columns = []
    for fret in sorted(frets, key=lambda fret: fret.x):
        if columns and fret.x - columns[-1][-1].x < 0.6 * gap:
            columns[-1].append(fret)
        else:
            columns.append([fret])
    two_voices = any(stem.up for stem in stems) and any(not stem.up for stem in stems)
    items = []
    for column in columns:
        x = statistics.mean(fret.x for fret in column)
        own = [stem for stem in stems if abs(stem.x - x) < 0.9 * gap]
        up = [stem for stem in own if stem.up]
        down = [stem for stem in own if not stem.up]
        if two_voices and up and down:
            low = _low_part(column, down[0], staff)
            items.append(Item(x, [fret for fret in column if fret not in low], _stem_length(up[0], staff, full_reach), 1,
                              tuplet=up[0].tuplet, stem=up[0]))
            items.append(Item(x, low, _stem_length(down[0], staff, full_reach), 2, tuplet=down[0].tuplet, stem=down[0]))
        elif own:
            stem = own[0]
            items.append(Item(x, column, _stem_length(stem, staff, full_reach), 2 if two_voices and not stem.up else 1,
                              tuplet=stem.tuplet, stem=stem))
        else:
            items.append(Item(x, column, None, 1))
    middle = (staff.top + staff.bottom) / 2
    for x, y, length, _ in rests:
        items.append(Item(x, [], length, 2 if two_voices and y < middle else 1, rest=True))
    for item in items:
        item.gap = gap
    return sorted(items, key=lambda item: (item.voice, item.x))


def _low_part(column: list[Fret], down: Stem, staff: Staff) -> list[Fret]:
    if staff.bottom + 0.3 * staff.gap < down.inner < staff.top - 0.3 * staff.gap:
        low = [fret for fret in column if staff.lines[fret.string - 1] <= down.inner + 0.8 * staff.gap]
        if low and len(low) < len(column):
            return low
    return [max(column, key=lambda fret: fret.string)]


def _time_signature(page: Page, staff: Staff, left: float, right: float, fret_font) -> tuple[int, int] | None:
    gap = staff.gap
    first_note = min((glyph.x0 for glyph in page.glyphs if glyph.text.isdigit() and _is_fret_glyph(glyph, fret_font)
                      and _inside(staff, glyph) and left < glyph.x < right), default=right)
    signs = [glyph for glyph in page.glyphs if left < glyph.x < first_note and staff.bottom - gap < glyph.y < staff.top + gap
             and (glyph.text in SMUFL_TIME_DIGITS or glyph.text in SMUFL_TIME_WHOLE
                  or (glyph.text.isdigit() and glyph.size >= 1.5 * fret_font[1]))]
    whole = [SMUFL_TIME_WHOLE[glyph.text] for glyph in signs if glyph.text in SMUFL_TIME_WHOLE]
    if whole:
        return whole[0]
    if not signs:
        return None
    middle = (staff.top + staff.bottom) / 2
    upper = sorted((glyph for glyph in signs if _sign_middle(glyph, staff) > middle), key=lambda glyph: glyph.x0)
    lower = sorted((glyph for glyph in signs if _sign_middle(glyph, staff) <= middle), key=lambda glyph: glyph.x0)
    if not upper or not lower:
        return None
    beats = int("".join(SMUFL_TIME_DIGITS.get(glyph.text, glyph.text) for glyph in upper))
    unit = int("".join(SMUFL_TIME_DIGITS.get(glyph.text, glyph.text) for glyph in lower))
    return (beats, unit) if beats and unit in (1, 2, 4, 8, 16, 32) else None


def _sign_middle(glyph: Glyph, staff: Staff) -> float:
    return glyph.origin_y if glyph.text in SMUFL_TIME_DIGITS else glyph.y


def _repeat_marks(page: Page, staff: Staff, left: float, right: float, bar_xs: list[float]) -> tuple[bool, bool]:
    gap = staff.gap
    marks = [glyph.origin_x for glyph in page.glyphs if glyph.text in SMUFL_REPEAT_DOTS and staff.x0 <= glyph.x <= staff.x1
             and staff.bottom <= glyph.origin_y <= staff.top]
    marks += [x for x, y in _round_dots(page, staff) if staff.bottom < y < staff.top and any(abs(x - bar) < 1.2 * gap for bar in bar_xs)]
    start = any(0 < x - left < 1.5 * gap for x in marks)
    end = any(0 < right - x < 1.5 * gap for x in marks)
    return (start, end) if start or end else None


def _bar_length(meter: tuple[int, int]) -> Fraction:
    return Fraction(4 * meter[0], meter[1])


def _meter(meters: dict[int, tuple[int, int]], bars: list[list[Item]]) -> tuple[tuple[int, int], bool]:
    if 0 in meters:
        return meters[0], True
    totals = Counter()
    for bar in bars:
        voice = _voice(bar, 1)
        if voice and all(item.length is not None for item in voice):
            totals[sum((item.length for item in voice), Fraction(0))] += 1
    if not totals:
        return (4, 4), False
    total = totals.most_common(1)[0][0]
    if total.denominator == 1:
        return (int(total), 4), False
    if (total * 2).denominator == 1:
        return (int(total * 2), 8), False
    return (4, 4), False


def _meter_at(meters, position: int, meter) -> tuple[int, int]:
    known = [at for at in meters if at <= position]
    return meters[max(known)] if known else meter


def _voice(bar: list[Item], voice: int) -> list[Item]:
    return [item for item in bar if item.voice == voice]


def _settle(bar: list[Item], meter: tuple[int, int]) -> bool:
    full = _bar_length(meter)
    doubtful = False
    for voice in {item.voice for item in bar}:
        items = _voice(bar, voice)
        unknown = [item for item in items if item.length is None]
        if not unknown:
            continue
        left = full - sum((item.length for item in items if item.length is not None), Fraction(0))
        if len(unknown) == 1 and left > 0 and _note_type(left):
            unknown[0].length = left
            continue
        share = left / len(unknown) if left > 0 else Fraction(1)
        for item in unknown:
            item.length = share
        doubtful = True
    return doubtful


def _note_type(length: Fraction) -> tuple[str, int] | None:
    for base, name in NOTE_TYPES.items():
        for dots in (0, 1, 2):
            if base * (2 - Fraction(1, 2 ** dots)) == length:
                return name, dots
    return None


def _key(midis: list[int]) -> int:
    counts = Counter(midi % 12 for midi in midis)

    def outside(fifths: int) -> int:
        scale = {(7 * (fifths + step) + 12 * 7) % 12 for step in range(-1, 6)}
        return sum(count for pitch_class, count in counts.items() if pitch_class not in scale)

    return min(range(-6, 7), key=lambda fifths: (outside(fifths), abs(fifths)))


def _spelling(midi: int, fifths: int) -> tuple[str, int, int]:
    pitch_class = midi % 12
    scale = {(7 * (fifths + step)) % 12: step for step in range(-1, 6)}
    names = SHARP_NAMES if fifths > 0 else FLAT_NAMES
    if pitch_class not in scale:
        minor_tonic = (7 * fifths + 9) % 12
        names = SHARP_NAMES if fifths >= 0 or (pitch_class + 1) % 12 == minor_tonic else FLAT_NAMES
        if fifths == 0 and pitch_class == 10:
            names = FLAT_NAMES
    else:
        letter_order = "FCGDAEB"
        letter = letter_order[(fifths + scale[pitch_class] + 1) % 7]
        alter = (pitch_class - NAMES[letter] + 6) % 12 - 6
        octave = (midi - alter) // 12 - 1
        return letter, alter, octave
    name = names[pitch_class]
    alter = 1 if name.endswith("#") else -1 if name.endswith("b") else 0
    return name[0], alter, (midi - alter) // 12 - 1


def _musicxml(bars: list[list[Item]], meters, meter, numbers: list[int], pickup: bool, repeats, open_strings: list[int],
              strings: int) -> bytes:
    midis = [open_strings[fret.string - 1] + fret.fret for bar in bars for item in bar for fret in item.frets]
    fifths = _key(midis)
    lengths = [item.length for bar in bars for item in bar] + [_bar_length(meter) for meter in [meter, *meters.values()]]
    divisions = math.lcm(1, *(length.denominator for length in lengths))
    root = ET.Element("score-partwise", version="4.0")
    score_part = ET.SubElement(ET.SubElement(root, "part-list"), "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Bass" if strings == 4 else "Guitar"
    part = ET.SubElement(root, "part", id="P1")
    current = None
    for position, (bar, number) in enumerate(zip(bars, numbers)):
        measure = ET.SubElement(part, "measure", number=str(number))
        if pickup and position == 0:
            measure.set("implicit", "yes")
        repeat = repeats.get(position)
        if repeat and repeat[0]:
            ET.SubElement(ET.SubElement(measure, "barline", location="left"), "repeat", direction="forward")
        bar_meter = _meter_at(meters, position, meter)
        if position == 0 or bar_meter != current:
            attributes = ET.SubElement(measure, "attributes")
            if position == 0:
                ET.SubElement(attributes, "divisions").text = str(divisions)
                ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(fifths)
            time = ET.SubElement(attributes, "time")
            ET.SubElement(time, "beats").text, ET.SubElement(time, "beat-type").text = str(bar_meter[0]), str(bar_meter[1])
            if position == 0:
                clef = ET.SubElement(attributes, "clef")
                sign, line = ("F", "4") if strings == 4 else ("G", "2")
                ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = sign, line
                ET.SubElement(clef, "clef-octave-change").text = "-1"
            current = bar_meter
        if not bar:
            rest = ET.SubElement(measure, "note")
            ET.SubElement(rest, "rest", measure="yes")
            ET.SubElement(rest, "duration").text = str(int(_bar_length(bar_meter) * divisions))
            ET.SubElement(rest, "voice").text = "1"
        voices = sorted({item.voice for item in bar})
        leading = max(voices, key=lambda voice: (sum((item.length for item in _voice(bar, voice)), Fraction(0)), -voice), default=1)
        grid = min((item.length for item in bar), default=Fraction(1))
        written = Fraction(0)
        for voice in voices:
            items = _voice(bar, voice)
            if written:
                ET.SubElement(ET.SubElement(measure, "backup"), "duration").text = str(int(written * divisions))
            columns = _onsets(_voice(bar, leading)) if voice != leading else []
            written = Fraction(0)
            beams = _beam_marks(items)
            for item in items:
                placed = _placed(columns, item, grid) if columns else written
                if placed > written:
                    forward = ET.SubElement(measure, "forward")
                    ET.SubElement(forward, "duration").text = str(int((placed - written) * divisions))
                    ET.SubElement(forward, "voice").text = str(voice)
                    written = placed
                _write_item(measure, item, voice, divisions, open_strings, fifths, beams.get(id(item), []))
                written += item.length
        if repeat and repeat[1]:
            ET.SubElement(ET.SubElement(measure, "barline", location="right"), "repeat", direction="backward")
        correct._write_accidentals(measure, fifths)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _placed(columns: list[tuple[Item, Fraction]], item: Item, grid: Fraction) -> Fraction:
    shared = [at for other, at in columns if abs(other.x - item.x) < 0.6 * item.gap]
    if shared:
        return shared[0]
    before = [(other.x, at) for other, at in columns if other.x < item.x]
    after = [(other.x, at) for other, at in columns if other.x > item.x]
    if not before or not after:
        return Fraction(0)
    (x0, at0), (x1, at1) = before[-1], after[0]
    estimate = at0 + (at1 - at0) * Fraction(item.x - x0) / Fraction(x1 - x0)
    return round(estimate / grid) * grid


def _onsets(items: list[Item]) -> list[tuple[Item, Fraction]]:
    onsets, onset = [], Fraction(0)
    for item in items:
        onsets.append((item, onset))
        onset += item.length
    return onsets


def _beam_marks(items: list[Item]) -> dict[int, list[tuple[int, str]]]:
    marks = {}
    runs = []
    for item in items:
        group = item.stem.group if item.stem and item.stem.beams else None
        if group is not None and runs and runs[-1][0] == group:
            runs[-1][1].append(item)
        else:
            runs.append((group, [item]))
    for group, run in runs:
        if group is None or len(run) < 2:
            continue
        for level in range(1, max(item.stem.beams for item in run) + 1):
            reaching = [item.stem.beams >= level for item in run]
            for position, item in enumerate(run):
                if not reaching[position]:
                    continue
                before = position > 0 and reaching[position - 1]
                after = position + 1 < len(run) and reaching[position + 1]
                value = ("continue" if before and after else "end" if before else "begin" if after
                         else "forward hook" if position + 1 < len(run) else "backward hook")
                marks.setdefault(id(item), []).append((level, value))
    return marks


def _write_item(measure: ET.Element, item: Item, voice: int, divisions: int, open_strings: list[int], fifths: int,
                beams: list[tuple[int, str]]) -> None:
    kind = _note_type(item.length / item.tuplet)
    for position, fret in enumerate(item.frets or [None]):
        note = ET.SubElement(measure, "note")
        if position:
            ET.SubElement(note, "chord")
        if fret is None:
            ET.SubElement(note, "rest")
        else:
            step, alter, octave = _spelling(open_strings[fret.string - 1] + fret.fret, fifths)
            pitch = ET.SubElement(note, "pitch")
            ET.SubElement(pitch, "step").text = step
            if alter:
                ET.SubElement(pitch, "alter").text = str(alter)
            ET.SubElement(pitch, "octave").text = str(octave)
        ET.SubElement(note, "duration").text = str(int(item.length * divisions))
        if fret is not None and fret.tie_stop:
            ET.SubElement(note, "tie", type="stop")
        if fret is not None and fret.tie_start:
            ET.SubElement(note, "tie", type="start")
        ET.SubElement(note, "voice").text = str(voice)
        if kind:
            ET.SubElement(note, "type").text = kind[0]
            for _ in range(kind[1]):
                ET.SubElement(note, "dot")
        if item.tuplet != 1:
            modification = ET.SubElement(note, "time-modification")
            factor = item.tuplet
            ET.SubElement(modification, "actual-notes").text = str(factor.denominator)
            ET.SubElement(modification, "normal-notes").text = str(factor.numerator)
        if position == 0:
            for level, value in beams:
                ET.SubElement(note, "beam", number=str(level)).text = value
        if fret is not None:
            notations = ET.SubElement(note, "notations")
            if fret.tie_stop:
                ET.SubElement(notations, "tied", type="stop")
            if fret.tie_start:
                ET.SubElement(notations, "tied", type="start")
            technical = ET.SubElement(notations, "technical")
            ET.SubElement(technical, "string").text = str(fret.string)
            ET.SubElement(technical, "fret").text = str(fret.fret)
