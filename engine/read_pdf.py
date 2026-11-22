from __future__ import annotations

import contextvars
import copy
import difflib
import inspect
import io
import logging
import math
import os
import re
import statistics
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from pathlib import Path

import pikepdf
from music21 import instrument

from engine import text, tint, verovio_workers
from engine.errors import UserError
from engine.overlay import S, Box, PageLayout
from engine.render import Engraving, ScoreError, load_toolkit
from engine.score import NOTE_TYPE_LENGTH, TOLERANCE, ScoreIndex, bar_length, musicxml_meter
from engine.triplets import infer_triplets
from engine.tuplet_rests import infer_tuplet_rests

log = logging.getLogger(__name__)

AUDIVERIS = "/opt/audiveris/bin/Audiveris"
TIMEOUT = 480
SECOND_PASS_SECONDS = 400
READ_PAGES = 8
READER_DPI = 300
MOST_DRAWN_PIXELS = 19_900_000
A4_DRAWN_PIXELS = 8_700_000
READABLE_INTERLINE = 20
SHARP_SCAN_INTERLINE = 11
NOTHING_READ = "No music could be read from this PDF"
NEXT_STEP = (
    ". Tell the user plainly, and suggest what may work: a PDF exported from notation software reads best; a scan "
    "should be straight, sharp and about 300 dpi; a long PDF can be sent a few pages at a time; a MusicXML file "
    "(.mxl or .musicxml) needs no reading at all."
)
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CHECK = "This is what I read from your PDF; check it against your copy before I analyse it."
SCAN_WARNING = "Scanned pages often have reading mistakes, so please check carefully."
SLURS_LEFT_OUT = "Slurs are not read, because they are often misread from PDFs."
SHOWN = 4
DEFAULT_PART_NAMES = {"Voice", "NoName"}
INSTRUMENT_NAMES = sorted({kind().instrumentName for _, kind in inspect.getmembers(instrument, inspect.isclass)
                           if issubclass(kind, instrument.Instrument) and kind().instrumentName} - DEFAULT_PART_NAMES)
SAME_BAR_WIDTH = 0.02
DOUBLE_BARS = {"light-light", "light-heavy", "heavy-light", "heavy-heavy"}
_SWITCH = "org.audiveris.omr.sheet.ProcessingSwitches."
_BASE = ["-option", _SWITCH + "indentations=false",
         "-option", "org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0",
         "-option", "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8",
         "-option", _SWITCH + "tremolos=true", "-option", _SWITCH + "fingerings=true",
         "-option", "org.audiveris.omr.sig.relation.ChordGraceRelation.xGapMax=4.0"]
_SMALL = ["-option", _SWITCH + "smallHeads=true", "-option", _SWITCH + "smallBeams=true"]
SETTINGS = [_BASE, _BASE + _SMALL + ["-option", _SWITCH + "implicitTuplets=true"]]
THIN_BEAM_SETTINGS = [setting + ["-option", "org.audiveris.omr.sheet.ScaleBuilder.beamMinFraction=0.2"]
                      for setting in SETTINGS]
_LELAND = ["-option", "org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland"]
READER = "5.11.0-sma.8-best2-tuplet-rests-eight-leland-ocr-r9-page-size-marks-thin-beams-fingering"
MIN_NOTES = 0.95
RETRY_ABOVE = 3

class ReadError(UserError):
    def __init__(self, message: str, passes: list[dict] | None = None, *, lasting: bool = False):
        super().__init__(message)
        self.passes = passes or []
        self.lasting = lasting


class ScanTooSmall(ReadError):
    pass


@dataclass
class PdfReading:
    musicxml: bytes
    pages: int
    scan: bool
    skipped: list[int] = field(default_factory=list)
    passes: list[dict] = field(default_factory=list)
    low_resolution: bool = False

SCAN_TOO_SMALL = ("This scan is too small to read: its staff lines are only about {} apart, and a sharp scan "
                  "has at least {}. Scanning the pages again at a higher resolution should let them be read")
LOW_RESOLUTION_WARNING = ("This scan is too small to read well, so expect many mistakes, including in bars that are "
                          "not shaded. A sharper scan will read much better.")


def notice(score: bytes, scan: bool, skipped: list[int], spots=None, low_resolution: bool = False,
           opening: str = CHECK) -> str:
    text = opening + (" " + SCAN_WARNING if scan else "") + (" " + LOW_RESOLUTION_WARNING if low_resolution else "")
    if skipped:
        pages = ", ".join(str(page) for page in skipped)
        text += f" Page{'s' if len(skipped) > 1 else ''} {pages} could not be read, so that music is missing."
    uneven, guessed = spots or problem_spots(score)
    if guessed:
        text += " No time signature was read, so bars were checked against the most common bar length."
    if uneven:
        verb = "looks" if len(uneven) == 1 else "look"
        who = f"The shaded bars ({_numbers(uneven)[5:]})" if len(uneven) > SHOWN else f"{_numbers(uneven)} (shaded)"
        text += f" {who} {verb} misread: the beats don't add up, or notes that should line up don't."
    return text + " " + SLURS_LEFT_OUT


def _numbers(bars: list[int]) -> str:
    shown = [str(bar) for bar in bars[:SHOWN]]
    if len(bars) == 1:
        return f"Bar {shown[0]}"
    if len(bars) <= SHOWN:
        return f"Bars {', '.join(shown[:-1])} and {shown[-1]}"
    return f"Bars {', '.join(shown)} and {len(bars) - SHOWN} more"


def problem_spots(score: bytes) -> tuple[list[int], str | None]:
    return _problem_spots(score, timing=True)


def _problem_spots(score: bytes, *, timing: bool) -> tuple[list[int], bool]:
    measures = ScoreIndex(load_toolkit(score).getMEI()).measures
    number_at = {segment.index: measure.number for measure in measures for segment in measure.segments}
    bars = []
    timing_errors = set()
    inferred = False
    columns = defaultdict(list)
    empty, last_filled = [], 0
    for part_index, part in enumerate(ET.fromstring(score).iter("part")):
        divisions, full = 1, None
        part_bars, guessed = [], False
        for position, measure in enumerate(part.iter("measure"), start=1):
            if measure.find("attributes/divisions") is not None:
                divisions = int(measure.find("attributes/divisions").text)
            full = _full_bar(measure) or full
            voices, staff_of, gap = {}, {}, {}
            cursor = onset = Fraction(0)
            for element in measure:
                if element.tag == "backup" and element.findtext("duration"):
                    cursor -= Fraction(element.findtext("duration")) / divisions
                    if cursor < -TOLERANCE and (number := number_at.get(position)) is not None:
                        timing_errors.add(number)
                if (element.tag == "note" and element.find("pitch") is not None
                        and element.find("grace") is None and element.find("time-modification") is None
                        and element.findtext("duration")):
                    expected = NOTE_TYPE_LENGTH.get(element.findtext("type"))
                    if expected is not None:
                        expected *= 2 - Fraction(1, 2 ** len(element.findall("dot")))
                        if abs(Fraction(element.findtext("duration")) / divisions - expected) > TOLERANCE:
                            if (number := number_at.get(position)) is not None:
                                timing_errors.add(number)
                if element.tag == "note" and element.find("grace") is None:
                    if element.find("chord") is None:
                        onset = cursor
                    if element.find("pitch") is not None and element.get("default-x"):
                        columns[position].append((part_index, element.findtext("voice", "1"), onset, float(element.get("default-x"))))
                timed = element.tag == "forward" or (element.tag == "note" and element.find("chord") is None)
                if timed and element.find("grace") is None and element.findtext("duration"):
                    voice = element.findtext("voice", "1")
                    length = Fraction(element.findtext("duration")) / divisions
                    cursor += length
                    if element.tag == "forward" and voices.get(voice, 0) == gap.get(voice, 0):
                        gap[voice] = gap.get(voice, 0) + length
                    voices[voice] = voices.get(voice, 0) + length
                    staff_of.setdefault(voice, element.findtext("staff", "1"))
            voices = {(staff_of[voice], voice, gap.get(voice, 0)): length for voice, length in voices.items()}
            if voices:
                part_bars.append((position, number_at.get(position), full, voices))
                last_filled = max(last_filled, position)
            else:
                empty.append((position, number_at.get(position)))
        common = Counter(length for *_, voices in part_bars if (length := max(voices.values())) > 0).most_common(1)
        if common and not any(full for _, _, full, _ in part_bars):
            inferred = True
            guessed = True
            part_bars = [(position, number, common[0][0], voices) for position, number, _, voices in part_bars]
        bars.extend((*bar, guessed) for bar in part_bars if bar[2])
    uneven = []
    for i, (position, number, full, voices, guessed) in enumerate(bars):
        longest = max(voices.values())
        overlapping = any(
            staff == other_staff and voice != other and short_length < length - TOLERANCE and gap_after > 0
            and short_length > gap_after + TOLERANCE
            for (staff, voice, _), short_length in voices.items()
            for (other_staff, other, gap_after), length in voices.items()
        )
        short = longest < full - TOLERANCE and not guessed
        neighbours = [bars[j] for j in (i - 1, i + 1) if 0 <= j < len(bars) and bars[j][0] != position]
        halves = any(abs(longest + max(other[3].values()) - full) <= TOLERANCE for other in neighbours)
        first, last = position == 1 and measures[0].is_pickup, position == max(bar[0] for bar in bars)
        pickup = max(bars[0][3].values()) if measures[0].is_pickup and max(bars[0][3].values()) < bars[0][2] else Fraction(0)
        completes = last and abs(pickup + longest - full) <= TOLERANCE
        if longest > full + TOLERANCE or overlapping or (short and not (first or completes or halves)):
            if number is not None and number not in uneven:
                uneven.append(number)
    uneven += [number for position, number in empty if position <= last_filled and number is not None]
    timing_errors.update(number_at[position] for position, notes in columns.items()
                         if position in number_at and _columns_disagree(notes))
    return sorted(set(uneven) | (timing_errors if timing else set())), inferred


def _full_bar(measure: ET.Element) -> Fraction | None:
    meter = musicxml_meter(measure.find("attributes/time"))
    return bar_length(*meter) if meter else None


def _columns_disagree(notes: list[tuple[int, str, Fraction, float]]) -> bool:
    for (part, voice, onset, x), (other_part, other_voice, other_onset, other_x) in combinations(notes, 2):
        if (part, voice) == (other_part, other_voice):
            continue
        apart = abs(x - other_x)
        if (onset != other_onset and apart <= SAME_COLUMN) or (onset == other_onset and apart > SAME_TIME_APART):
            return True
    return False


SAME_COLUMN, SAME_TIME_APART = 3, 25
PREVIEW_OPTIONS = {**tint.BOXES, "spacingSystem": 7}
BAR_NUMBER_SIZE = 500
TOP_CLEARANCE = 3 * tint.SPACE


def preview(score: bytes, spots=None) -> Engraving:
    spots = spots or problem_spots(score)
    return shade(load_toolkit(score, PREVIEW_OPTIONS, labelled_bars=spots[0]), spots)


def _ending_brackets(layout: PageLayout) -> list[Box]:
    found = []
    for group in layout.root.iter(f"{S}g"):
        if group.get("class") == "voltaBracket":
            points = [(float(x), float(y)) for path in group.findall(f"{S}path")
                      for x, y in re.findall(r"[ML]([-\d.]+) ([-\d.]+)", path.get("d", ""))]
            if points:
                xs, ys = [x for x, _ in points], [y for _, y in points]
                found.append(Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return found


def number_bars(layout: PageLayout, index: ScoreIndex) -> float | None:
    for parent in list(layout.root.iter()):
        for child in [c for c in parent if "mNum" in (c.get("class") or "").split()]:
            parent.remove(child)
    brackets = _ending_brackets(layout)
    highest = None
    for measure in index.measures:
        geometry = layout.measures.get(measure.segments[0].id)
        if geometry is None or measure.number < 2:
            continue
        system = layout.systems[geometry.system]
        string = measure.name
        width, height = text.width(string, BAR_NUMBER_SIZE), BAR_NUMBER_SIZE
        top = min(box.y for box in geometry.lines)
        spots = [(geometry.x0 + 60, top - 90 - rise) for rise in range(0, 2400, 100)]

        def padded(spot):
            return Box(spot[0] - 20, spot[1] - height * 0.75 - 20, width + 40, height + 40)

        over = [b for b in brackets if top - 2400 < b.y < top]

        def clear_of_brackets(box):
            return not any(b.x < box.right and b.right > box.x and box.bottom > b.y for b in over)

        neighbours = layout.systems[max(system.index - 1, 0) : system.index + 1]
        spot = next((s for s in spots if clear_of_brackets(padded(s)) and all(layout._is_free(n, padded(s)) for n in neighbours)), None) \
            or min(spots, key=lambda s: sum(layout._overlap(n, padded(s)) for n in neighbours))
        box = layout._text(*spot, string, BAR_NUMBER_SIZE, italic=True)
        layout._reserve(system, box, pad=20)
        highest = box.y if highest is None else min(highest, box.y)
    return highest


def fit_top_margin(toolkit, index: ScoreIndex) -> list[PageLayout]:
    for _ in range(3):
        layouts, highest = [], None
        for page in range(1, toolkit.getPageCount() + 1):
            layout = PageLayout(toolkit.renderToSVG(page), index)
            top = number_bars(layout, index)
            if top is not None:
                highest = top if highest is None else min(highest, top)
            layouts.append(layout)
        margin = toolkit.getOptions()["pageMarginTop"] * 10
        short = TOP_CLEARANCE - (margin + highest) if highest is not None else 0
        if short <= 0:
            break
        toolkit.setOptions({"pageMarginTop": math.ceil((margin + short) / 10)})
        toolkit.redoLayout()
    return layouts


def shade(toolkit, spots) -> Engraving:
    uneven, _ = spots
    index = ScoreIndex(toolkit.getMEI())
    layouts = fit_top_margin(toolkit, index)
    for layout in layouts:
        tint.flag_bars(layout, index, uneven)
    return tint.finish(layouts)


def without_slurs(score: bytes) -> bytes:
    root = ET.fromstring(score)
    for notations in root.iter("notations"):
        for slur in notations.findall("slur"):
            notations.remove(slur)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def open_pdf(data: bytes) -> pikepdf.Pdf:
    try:
        return pikepdf.open(io.BytesIO(data))
    except pikepdf.PdfError as error:
        raise ReadError("This file could not be opened as a PDF", lasting=True) from error


def unread_pages(read: int, total: int) -> str:
    if total <= read:
        return ""
    return (f" Only pages 1-{read} of the {total} were read, to keep the wait short; to analyse the rest, "
            "send those pages as a separate PDF.")


def first_pages(data: bytes, count: int) -> bytes:
    pdf = open_pdf(data)
    del pdf.pages[count:]
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def drawn_pixels(width: float, height: float) -> float:
    return width * height * (READER_DPI / 72) ** 2


def scale_page(page: pikepdf.Page, factor: float) -> None:
    media, crop = page.mediabox, page.cropbox
    page.contents_add(f"q {factor:.6f} 0 0 {factor:.6f} 0 0 cm\n".encode(), prepend=True)
    page.contents_add(b"\nQ")
    page.MediaBox = pikepdf.Array([float(edge) * factor for edge in media])
    page.CropBox = pikepdf.Array([float(edge) * factor for edge in crop])


def page_width_height(page: pikepdf.Page) -> tuple[float, float]:
    left, bottom, right, top = (float(edge) for edge in page.cropbox)
    return abs(right - left), abs(top - bottom)


UNUSUAL_PDF = (TypeError, ValueError, AttributeError, ArithmeticError, pikepdf.PdfError)


def scaled_pages(data: bytes, factor_of) -> bytes:
    try:
        pdf = open_pdf(data)
        factors = [factor_of(*page_width_height(page)) for page in pdf.pages]
        if all(factor == 1 for factor in factors):
            return data
        for page, factor in zip(pdf.pages, factors):
            if factor != 1:
                scale_page(page, factor)
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    except UNUSUAL_PDF:
        log.exception("Pages left at their own size")
        return data


def without_oversize_pages(data: bytes) -> bytes:
    def factor(width: float, height: float) -> float:
        drawn = drawn_pixels(width, height)
        return (A4_DRAWN_PIXELS / drawn) ** 0.5 if drawn > MOST_DRAWN_PIXELS else 1

    return scaled_pages(data, factor)


def enlarged_for_interline(data: bytes, interline: int) -> bytes:
    def factor(width: float, height: float) -> float:
        room = (MOST_DRAWN_PIXELS / drawn_pixels(width, height)) ** 0.5
        return max(1, min(READABLE_INTERLINE / interline, room))

    return scaled_pages(data, factor)


def file_facts(data: bytes) -> dict:
    try:
        pdf = open_pdf(data)
        return {"scan": is_scan(pdf),
                "page_points": [[round(side) for side in page_width_height(page)] for page in pdf.pages],
                "image_pixels": [[[int(image.Width), int(image.Height)] for image in page.get_images().values()]
                                 for page in pdf.pages]}
    except UNUSUAL_PDF:
        log.exception("File details not read")
        return {}


def is_scan(pdf: pikepdf.Pdf) -> bool:

    def inherited_resources(node):
        while node is not None and "/Resources" not in node:
            node = node.get("/Parent")
        return node.Resources if node is not None else {}

    def drawn(stream, resources, seen: set, found: set) -> set:
        xobjects = resources.get("/XObject", {}) or {}
        for operands, operator in pikepdf.parse_content_stream(stream):
            name = str(operator)
            if name in PAINT_OPERATORS:
                found.add("paths")
            elif name == "INLINE IMAGE":
                found.add("image")
            elif name == "Do" and operands and str(operands[0]) in xobjects:
                xobject = xobjects[str(operands[0])]
                if xobject.get("/Subtype") == "/Image":
                    found.add("image")
                elif xobject.get("/Subtype") == "/Form" and xobject.objgen not in seen:
                    seen.add(xobject.objgen)
                    drawn(xobject, xobject.get("/Resources", resources), seen, found)
        return found

    return not any(drawn(page.obj, inherited_resources(page.obj), set(), set()) == {"paths"} for page in pdf.pages)


def uses_leland(pdf: pikepdf.Pdf) -> bool:
    return any(isinstance(item, pikepdf.Dictionary) and item.get("/Type") == "/Font"
               and str(item.get("/BaseFont", "")).split("+")[-1].lstrip("/") == "Leland" for item in pdf.objects)


def read_pdf(data: bytes, audiveris: str = AUDIVERIS, raw=None) -> PdfReading:
    pdf = open_pdf(data)
    pages, scan, leland = len(pdf.pages), is_scan(pdf), uses_leland(pdf)
    data = without_oversize_pages(data)
    deadline = time.monotonic() + TIMEOUT
    try:
        return _resolution_checked(_read_with_every_setting(data, audiveris, raw, pages, scan, leland, deadline),
                                   data, scan)
    except ReadError as error:
        interlines = [value for record in error.passes for value in record.get("too_close_interlines", []) if value]
        if not interlines:
            raise _explained(error, scan, (data, error.passes))
        first_passes = error.passes
    enlarged = enlarged_for_interline(data, min(interlines))
    try:
        reading = _resolution_checked(_read_with_every_setting(enlarged, audiveris, raw, pages, scan, leland, deadline),
                                      enlarged, scan)
    except ReadError as error:
        retry_passes = error.passes
        error.passes = [*first_passes, *retry_passes]
        raise _explained(error, scan, (data, first_passes), (enlarged, retry_passes))
    reading.passes = [*first_passes, *reading.passes]
    return reading


def _resolution_checked(reading: PdfReading, data: bytes, scan: bool) -> PdfReading:
    spacing = scan_staff_spacing(data, [value for record in reading.passes for value in record.get("interlines", [])])
    reading.low_resolution = scan and spacing is not None and spacing < SHARP_SCAN_INTERLINE
    return reading


def _explained(error: ReadError, scan: bool, *attempts: tuple[bytes, list[dict]]) -> ReadError:
    spacings = [scan_staff_spacing(data, [value for record in passes for value in record.get("interlines", [])])
                for data, passes in attempts] if scan else []
    spacing = min((value for value in spacings if value), default=None)
    if spacing is None or spacing >= SHARP_SCAN_INTERLINE:
        return error
    return ScanTooSmall(SCAN_TOO_SMALL.format(_pixels(max(1, round(spacing))), SHARP_SCAN_INTERLINE), error.passes,
                        lasting=error.lasting)


def _pixels(count: int) -> str:
    return f"{count} pixel{'' if count == 1 else 's'}"


def scan_staff_spacing(data: bytes, drawn_interlines: list[int]) -> float | None:
    try:
        pdf = open_pdf(data)
        shares = [max(int(image.Width) for image in page.get_images().values())
                  / (page_width_height(page)[0] * READER_DPI / 72)
                  for page in pdf.pages if page.get_images()]
    except UNUSUAL_PDF:
        log.exception("Scan resolution not read")
        return None
    if not shares or not drawn_interlines:
        return None
    return statistics.median(drawn_interlines) * min(shares)


def _read_with_every_setting(data: bytes, audiveris: str, raw, pages: int, scan: bool, leland: bool,
                             deadline: float) -> PdfReading:
    raw = raw or audiveris_read
    results = _read_settings(data, audiveris, raw, leland, deadline, range(len(SETTINGS)))
    if not scan and _beams_unmeasured(results) and time.monotonic() < deadline:
        results += _read_settings(data, audiveris, raw, leland, deadline,
                                  range(len(SETTINGS), 2 * len(SETTINGS)))
    passes = [record for record, _ in results]
    readings = [reading for _, reading in results if reading is not None]
    if not readings:
        timed_out = any(record["outcome"] == "timeout" for record in passes)
        found_nothing = bool(passes) and all(record["outcome"] == "no music" and record.get("exit_code") == 0 for record in passes)
        raise ReadError("Reading this PDF took too long" if timed_out else NOTHING_READ, passes, lasting=found_nothing)
    counts = [_pitched_notes(reading[0]) for reading in readings]
    complete = [reading for reading, count in zip(readings, counts) if count >= MIN_NOTES * max(counts)]
    musicxml, skipped, _ = min(complete, key=lambda reading: (len(reading[1]), len(reading[2])))
    for repair in (infer_tuplet_rests, infer_triplets):
        try:
            musicxml = repair(musicxml)
        except Exception:
            log.exception("PDF reading repair %s failed", repair.__name__)
    return PdfReading(musicxml, pages, scan, skipped, passes)


def _read_settings(data: bytes, audiveris: str, raw, leland: bool, deadline: float, settings: range) -> list:
    stop = threading.Event()
    with ThreadPoolExecutor(len(settings)) as pool:
        second = min(deadline, time.monotonic() + SECOND_PASS_SECONDS)
        futures = [pool.submit(contextvars.copy_context().run, _read, data, audiveris, setting, leland,
                               deadline if setting == settings[0] else second, raw, stop)
                   for setting in settings]
        try:
            first = futures[0].result()
            if _good_enough(first[1]):
                stop.set()
            return [first, *(future.result() for future in futures[1:])]
        finally:
            stop.set()


def _good_enough(reading) -> bool:
    return reading is not None and not reading[1] and len(reading[2]) <= RETRY_ABOVE


def _beams_unmeasured(results: list) -> bool:
    return (any(record.get("beam_unmeasured") for record, _ in results)
            and not any(_good_enough(reading) for _, reading in results))


_TEMPO_NUMBER = re.compile(r"=\s*\d|\bca\.?\s*\d")
_OCTAVE_TEXT = re.compile(r"(8|15)\s*[v0o]?(a|b|ma|mb)?[\s,.'\"_|—–-]*$", re.IGNORECASE)
_ROMAN_NUMERAL = re.compile(r"[ivIV]+[o+]?[\d()/ivIVo+]*$")
_EXPRESSION = re.compile(r"(?:de)?cresc|dim|rit|rall|dolce|espr|legato|sempre|poco", re.IGNORECASE)
_RIGHT_HAND = re.compile(r"(?=.*[pima])[pima1][pima1\s.,]*$")
RIGHT_HAND_MARKS = 3
_DYNAMIC = re.compile(r"(?:p{1,4}|f{1,4}|mp|mf|fp|sf|sfz|sfp|fz|rf|rfz)\.?$", re.IGNORECASE)


def text_meaning(text: str) -> str:
    stripped = text.strip()
    if _TEMPO_NUMBER.search(stripped):
        return "tempo"
    letters = sum(char.isalpha() for char in stripped)
    if letters == 0:
        return "fingering" if any(char.isdigit() for char in stripped) else "stray"
    if _DYNAMIC.match(stripped):
        return "dynamic"
    if _OCTAVE_TEXT.match(stripped):
        return "octave"
    if _ROMAN_NUMERAL.match(stripped):
        return "numeral"
    return "words" if letters / len(stripped.replace(" ", "")) >= 0.5 else "stray"


def _keep_meaningful_text(root: ET.Element) -> None:
    for measure in root.iter("measure"):
        for direction in measure.findall("direction"):
            for kind in direction.findall("direction-type"):
                for words in kind.findall("words"):
                    meaning = text_meaning(words.text or "")
                    if meaning in {"fingering", "stray"}:
                        kind.remove(words)
                    elif meaning == "dynamic":
                        kind.remove(words)
                        ET.SubElement(ET.SubElement(kind, "dynamics"), (words.text or "").strip().rstrip(".").lower())
                if len(kind) == 0:
                    direction.remove(kind)
            if direction.find("direction-type") is None:
                measure.remove(direction)


def _lyrics_to_directions(root: ET.Element) -> None:
    for part in root.iter("part"):
        lyrics = [(measure, note, lyric) for measure in part.iter("measure") for note in measure.findall("note")
                  for lyric in note.findall("lyric")]
        marks = [item for item in lyrics if text_meaning(item[2].findtext("text") or "") == "dynamic"
                 or _EXPRESSION.match((item[2].findtext("text") or "").strip())]
        split = sum(item[2].findtext("syllabic") in {"begin", "middle", "end"} for item in lyrics)
        if 5 * split >= len(lyrics) and 2 * len(marks) < len(lyrics):
            continue
        for measure, note, lyric in marks:
            note.remove(lyric)
            text = (lyric.findtext("text") or "").strip()
            direction = ET.Element("direction", placement="below")
            kind = ET.SubElement(direction, "direction-type")
            if text_meaning(text) == "dynamic":
                ET.SubElement(ET.SubElement(kind, "dynamics"), text.rstrip(".").lower())
            else:
                ET.SubElement(kind, "words").text = text
            if note.find("staff") is not None:
                ET.SubElement(direction, "staff").text = note.findtext("staff")
            measure.insert(list(measure).index(note), direction)


def _pitched_notes(musicxml: bytes) -> int:
    return sum(1 for note in ET.fromstring(musicxml).iter("note") if note.find("pitch") is not None)


def _read(data: bytes, audiveris: str, setting: int, leland: bool, deadline: float, raw, stop: threading.Event):
    started = time.monotonic()
    read = raw(data, audiveris, setting, leland, deadline, stop)
    record = {"setting": setting, **read.facts, "seconds": round(time.monotonic() - started, 1)}
    if read.mxl is None:
        return record, None
    try:
        musicxml = clean(read.mxl)
        return record, (musicxml, read.skipped, _problem_spots(musicxml, timing=False)[0])
    except (ScoreError, verovio_workers.VerovioFailed, zipfile.BadZipFile, ET.ParseError) as error:
        record["outcome"] = f"unusable output ({type(error).__name__})"
        return record, None


def audiveris_options(setting: int, leland: bool) -> list[str]:
    return (SETTINGS + THIN_BEAM_SETTINGS)[setting] + (_LELAND if leland else [])


def audiveris_read(data: bytes, audiveris: str, setting: int, leland: bool, deadline: float,
                   stop: threading.Event) -> RawReading:
    options = audiveris_options(setting, leland)
    with tempfile.TemporaryDirectory(prefix="read_pdf_") as work:
        source = Path(work) / "score.pdf"
        source.write_bytes(data)
        env = {"PATH": os.defpath, "HOME": work, "TESSDATA_PREFIX": str(Path(audiveris).parent.parent / "tessdata"),
               "_JAVA_OPTIONS": "-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1"}
        run_ = run(audiveris, options, setting, source, work, env, deadline, stop)
        facts = audiveris_facts(run_)
        books = sorted(Path(work).glob("*.omr"))
        if run_.ending == "done" and not list(Path(work).glob("*.mxl")) and books:
            export = run(audiveris, options, setting, books[0], work, env, deadline, stop)
            facts["outcome"] = "done" if export.ending == "done" else export.ending
        scores = sorted(Path(work).glob("*.mxl"), key=_movement_number)
        if facts["outcome"] != "done":
            return RawReading(None, [], facts)
        if not scores:
            facts["outcome"] = "no music"
            return RawReading(None, [], facts)
        skipped = sorted({int(page) for page in re.findall(r"Sheet \S+#(\d+) flagged as invalid", run_.output)})
        facts["movements"] = len(scores)
        return RawReading(join_movements([score.read_bytes() for score in scores]), skipped, facts)


def _movement_number(score: Path) -> int:
    found = re.search(r"\.mvt(\d+)\.mxl$", score.name)
    return int(found.group(1)) if found else 0


def _archived_score(mxl: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(mxl)) as archive:
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        return ET.fromstring(archive.read(name))


def join_movements(movements: list[bytes]) -> bytes:
    if len(movements) == 1:
        return movements[0]
    joined, *following = [_archived_score(movement) for movement in movements]
    for movement in following:
        _append_movement(joined, movement)
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w") as archive:
        archive.writestr("score.xml", ET.tostring(joined, encoding="utf-8", xml_declaration=True))
    return sink.getvalue()


def _append_movement(joined: ET.Element, movement: ET.Element) -> None:
    parts = joined.findall("part")
    bars_before = _longest_part(joined)
    bars_beside = _longest_part(movement)
    offset = max(_bar_number(bar) for bar in bars_before) + 1 - min(_bar_number(bar) for bar in bars_beside)
    for bar in movement.iter("measure"):
        bar.set("number", re.sub(r"\d+", lambda number: str(int(number.group()) + offset), bar.get("number"), count=1))
    unmatched = list(parts)
    silent = list(parts)
    for part in movement.findall("part"):
        staves = _staves(part)
        target = next((candidate for candidate in unmatched if _staves(candidate) == staves), None)
        if target is None:
            target = _new_part(joined, movement, part, bars_before)
        else:
            unmatched = unmatched[unmatched.index(target) + 1:]
            silent = [other for other in silent if other is not target]
        target.extend(part.findall("measure"))
    for part in silent:
        part.extend(_silent_bar(bar, *state) for bar, state in zip(bars_beside, _in_force(bars_beside)))


def _longest_part(score: ET.Element) -> list[ET.Element]:
    return max((part.findall("measure") for part in score.findall("part")), key=len)


def _bar_number(bar: ET.Element) -> int:
    return int(re.match(r"\d*", bar.get("number")).group() or 0)


def _staves(part: ET.Element) -> int:
    return int(part.findtext("measure/attributes/staves", "1"))


def _new_part(joined: ET.Element, movement: ET.Element, part: ET.Element, bars_before: list[ET.Element]) -> ET.Element:
    part_id = f"P{len(joined.findall('part')) + 1}"
    listed = ET.SubElement(joined.find("part-list"), "score-part", id=part_id)
    named = next(entry for entry in movement.iter("score-part") if entry.get("id") == part.get("id"))
    ET.SubElement(listed, "part-name").text = named.findtext("part-name")
    added = ET.SubElement(joined, "part", id=part_id)
    added.extend(_silent_bar(bar, *state) for bar, state in zip(bars_before, _in_force(bars_before)))
    added.find("measure/attributes").extend(
        copy.deepcopy(element) for element in part.findall("measure[1]/attributes/*") if element.tag in ("staves", "clef"))
    return added


def _in_force(bars: list[ET.Element], divisions: int | None = None) -> list[tuple[int | None, tuple[int, int] | None]]:
    states, meter = [], None
    for bar in bars:
        divisions = int(bar.findtext("attributes/divisions") or divisions or 0) or None
        meter = musicxml_meter(bar.find("attributes/time")) or meter
        states.append((divisions, meter))
    return states


def _silent_bar(beside: ET.Element, divisions: int | None, meter: tuple[int, int] | None) -> ET.Element:
    bar = ET.Element("measure", number=beside.get("number"))
    attributes = ET.SubElement(bar, "attributes")
    attributes.extend(copy.deepcopy(element) for element in beside.findall("attributes/*") if element.tag in ("divisions", "key", "time"))
    rest = ET.SubElement(bar, "note")
    ET.SubElement(rest, "rest", measure="yes")
    length = bar_length(*meter) * divisions if divisions and meter else None
    ET.SubElement(rest, "duration").text = str(length if length is not None and length.denominator == 1 else _bar_length(beside))
    return bar


def _bar_length(bar: ET.Element) -> int:
    position = longest = 0
    for element in bar:
        position += _advance(element)
        longest = max(longest, position)
    return longest


@dataclass
class RawReading:
    mxl: bytes | None
    skipped: list[int]
    facts: dict


@dataclass
class AudiverisRun:
    ending: str
    exit_code: int | None
    output: str
    step_seconds: dict[str, float]


KNOWN_PROBLEMS = {
    "No regularly spaced lines found": "no staff lines found",
    "flagged as invalid": "page flagged as invalid",
    "Too large image": "page too large",
    "too low interline value": "staff lines too close",
    "too high interline value": "staff lines too far apart",
    "OutOfMemoryError": "out of memory",
}
STEP = re.compile(r"StepMonitoring\s+\d+\s+\|\s+([A-Z_]+)\s*$")


def run(audiveris: str, options: list[str], setting: int, source: Path, work: str, env: dict, deadline: float,
        stop: threading.Event) -> AudiverisRun:
    command = ([] if setting % len(SETTINGS) == 0 else ["nice", "-n", "19"]) + [
        audiveris, "-batch", *options, "-export", "-output", work, str(source)]
    output_path = Path(work) / f"audiveris-{source.suffix[1:]}.txt"
    steps: Counter = Counter()
    current, since, pending = "START", time.monotonic(), b""

    def follow(reader) -> None:
        nonlocal current, since, pending
        pending += reader.read()
        *lines, pending = pending.split(b"\n")
        for line in lines:
            if match := STEP.search(line.decode(errors="replace")):
                now = time.monotonic()
                steps[current] += now - since
                current, since = match.group(1), now

    with open(output_path, "wb") as sink, open(output_path, "rb") as reader:
        process = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT, env=env)
        ending = "done"
        try:
            while process.poll() is None:
                if stop.wait(0.25):
                    ending = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    ending = "timeout"
                    break
                follow(reader)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        follow(reader)
        steps[current] += time.monotonic() - since
    return AudiverisRun(ending, process.returncode, output_path.read_text(errors="replace"),
                        {name: round(seconds, 1) for name, seconds in steps.items()})


def audiveris_facts(run_: AudiverisRun) -> dict:
    output = run_.output
    problems = set(re.findall(r"Error processing stub (?:\S+\.)?(\w+)", output))
    problems |= {label for marker, label in KNOWN_PROBLEMS.items() if marker in output}
    return {"outcome": run_.ending, "exit_code": run_.exit_code,
            "images": re.findall(r"Loaded image #\d+ (\d+x\d+)", output),
            "interlines": [int(value) for value in re.findall(r"interline\(\d+,(\d+),\d+\)", output)],
            "too_close_interlines": [int(value) for value in re.findall(r"too low interline value of (\d+)", output)],
            "beam_unmeasured": "No reliable beam height" in output or any(
                int(share) < 100 for share in re.findall(r"Beam measured height.* at (\d+)% of needed quorum", output)),
            "pages_done": len(re.findall(r"\|\s+PAGE\s*$", output, re.M)),
            "invalid_pages": output.count("flagged as invalid"),
            "problems": sorted(problems), "step_seconds": run_.step_seconds}


def clean(mxl: bytes) -> bytes:
    root = _archived_score(mxl)
    _drop_noteless_parts(root)
    _name_default_parts(root)
    _fill_absent_bars(root)
    for note in root.iter("note"):
        if note.find("chord") is not None:
            for beam in note.findall("beam"):
                note.remove(beam)
    if root.find(".//barline/repeat") is None:
        for measure in root.iter("measure"):
            for barline in measure.findall("barline"):
                endings = barline.findall("ending")
                for ending in endings:
                    barline.remove(ending)
                if endings and len(barline) == 0:
                    measure.remove(barline)
    for part in root.iter("part"):
        _one_division(part)
        _drop_restated_keys(part)
        open_lines, unclosed = {}, []
        for measure in part.iter("measure"):
            for direction in _octave_shifts_in_time_order(measure):
                shift = direction.find("direction-type/octave-shift")
                number = shift.get("number", "1")
                if shift.get("type") == "stop":
                    open_lines.pop(number, None)
                elif shift.get("type") != "continue":
                    if number in open_lines:
                        unclosed.append(open_lines[number])
                    open_lines[number] = (measure, direction)
        for measure, direction in unclosed + list(open_lines.values()):
            measure.remove(direction)
    _share_numbers_of_split_bars(root)
    _drop_fingering(root)
    _drop_right_hand_fingering(root)
    _keep_meaningful_text(root)
    _lyrics_to_directions(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fill_absent_bars(root: ET.Element) -> None:
    parts = root.findall("part")
    for part in parts:
        others = [other for other in parts if other is not part]
        if not others:
            return
        held = set.intersection(*({bar.get("number") for bar in other.findall("measure")} for other in others))
        beside = [bar for bar in others[0].findall("measure") if bar.get("number") in held]
        bars = part.findall("measure")
        own = {bar.get("number"): bar for bar in bars}
        if (len(own) < len(bars) or not held - own.keys() or not _same_columns(own, others)
                or [bar.get("number") for bar in bars] != [bar.get("number") for bar in beside if bar.get("number") in own]):
            continue
        filled = []
        unit = _opening_divisions(part)
        reference = others[0].findall("measure")
        for bar, (beside_unit, meter) in zip(reference, _in_force(reference, _opening_divisions(others[0]))):
            if bar.get("number") in own:
                filled.append(own[bar.get("number")])
                unit = int(filled[-1].findtext("attributes/divisions") or unit or 0) or None
            elif bar.get("number") in held:
                if unit is None or beside_unit is None:
                    break
                filled.append(_silent_bar_in_unit(bar, unit, beside_unit, meter, None if filled else part.find("measure/attributes/clef")))
        else:
            for bar in bars:
                part.remove(bar)
            part.extend(filled)


def _silent_bar_in_unit(beside: ET.Element, unit: int, beside_unit: int, meter: tuple[int, int] | None,
                        clef: ET.Element | None) -> ET.Element:
    bar = _silent_bar(beside, beside_unit, meter)
    bar.find("note/duration").text = str(int(bar.findtext("note/duration")) * unit // beside_unit)
    attributes = bar.find("attributes")
    for divisions in attributes.findall("divisions"):
        attributes.remove(divisions)
    attributes.insert(0, ET.Element("divisions"))
    attributes[0].text = str(unit)
    if clef is not None:
        attributes.append(copy.deepcopy(clef))
    return bar


def _same_columns(own: dict[str, ET.Element], others: list[ET.Element]) -> bool:
    pairs = [(float(own[bar.get("number")].get("width")), float(bar.get("width"))) for other in others for bar in other.findall("measure")
             if bar.get("number") in own and bar.get("width") and own[bar.get("number")].get("width")]
    return bool(pairs) and all(abs(width - other) <= SAME_BAR_WIDTH * other for width, other in pairs)


def _opening_divisions(part: ET.Element) -> int | None:
    opening = []
    for bar in part.findall("measure"):
        if bar.find("attributes/divisions") is not None:
            break
        opening.append(bar)
    if not opening:
        return int(part.findtext("measure/attributes/divisions"))
    units = {Fraction(note.findtext("duration")) / NOTE_TYPE_LENGTH[note.findtext("type")]
             for bar in opening for note in bar.iter("note")
             if note.findtext("type") in NOTE_TYPE_LENGTH and note.findtext("duration") and note.find("dot") is None
             and note.find("time-modification") is None and note.find("grace") is None}
    return int(units.pop()) if len(units) == 1 and next(iter(units)).denominator == 1 else None


def _drop_noteless_parts(root: ET.Element) -> None:
    noteless = [part for part in root.findall("part") if all(note.find("rest") is not None for note in part.iter("note"))]
    if len(noteless) == len(root.findall("part")):
        return
    part_list = root.find("part-list")
    for part in noteless:
        root.remove(part)
        part_list.remove(part_list.find(f"score-part[@id='{part.get('id')}']"))


def _name_default_parts(root: ET.Element) -> None:
    listed = root.findall("part-list/score-part")
    unnamed = [part for part in listed if part.findtext("part-name") in DEFAULT_PART_NAMES]
    if not unnamed:
        return
    heading = " / ".join(" ".join(words.text or "" for words in credit.findall("credit-words"))
                         for credit in root.findall("credit") if credit.get("page", "1") == "1")
    named = _instruments_named(heading) if len(listed) == 1 else set()
    for part in unnamed:
        part.find("part-name").text = next(iter(named)) if len(named) == 1 else ""
        for abbreviation in part.findall("part-abbreviation"):
            part.remove(abbreviation)


def _instruments_named(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_]+", text.lower())
    found = set()
    for name in INSTRUMENT_NAMES:
        wanted = name.lower().split()
        for start in range(len(words) - len(wanted) + 1):
            seen = words[start:start + len(wanted)]
            if seen == wanted or (len(wanted) > 1 and seen[0] == wanted[0]
                                  and difflib.SequenceMatcher(None, " ".join(seen), name.lower()).ratio() >= 0.8):
                found.add(name)
    return found


def _drop_fingering(root: ET.Element) -> None:
    for note in root.iter("note"):
        for notations in note.findall("notations"):
            for technical in notations.findall("technical"):
                for fingering in technical.findall("fingering"):
                    technical.remove(fingering)
                if len(technical) == 0:
                    notations.remove(technical)
            if len(notations) == 0:
                note.remove(notations)


def _drop_right_hand_fingering(root: ET.Element) -> None:
    marks = [(kind, words) for kind in root.iter("direction-type") for words in kind.findall("words")
             if _right_hand((words.text or "").strip())]
    if sum((words.text or "").strip() != "p" for _, words in marks) < RIGHT_HAND_MARKS:
        return
    for kind, words in marks:
        kind.remove(words)
    for parent in root.iter():
        for dynamics in parent.findall("dynamics"):
            if [child.tag for child in dynamics] == ["p"]:
                parent.remove(dynamics)
    for note in root.iter("note"):
        for lyric in note.findall("lyric"):
            if _right_hand((lyric.findtext("text") or "").strip().lower()):
                note.remove(lyric)


def _right_hand(text: str) -> bool:
    return bool(_RIGHT_HAND.match(text)) and (text == "p" or not _DYNAMIC.match(text))


def _share_numbers_of_split_bars(root: ET.Element) -> None:
    parts = root.findall("part")
    divisions = [int(part.findtext("measure/attributes/divisions") or 1) for part in parts]
    shift, full, before = 0, None, None
    for bars in zip(*(part.findall("measure") for part in parts)):
        full = _full_bar(bars[0]) or full
        length = max(Fraction(_bar_length(bar), each) for bar, each in zip(bars, divisions))
        if shift:
            for bar in bars:
                bar.set("number", re.sub(r"\d+", lambda number: str(int(number.group()) - shift), bar.get("number"), count=1))
        if before is not None and _second_half(before, (bars, length, full)):
            for bar in bars:
                bar.set("number", "X" + before[0][0].get("number"))
                bar.set("implicit", "yes")
            shift += 1
        before = (bars, length, full)


def _second_half(before: tuple, after: tuple) -> bool:
    bars, length, full = before
    later_bars, later_length, later_full = after
    label, later_label = bars[0].get("number", ""), later_bars[0].get("number", "")
    barlines = [barline for bar in bars for barline in bar.findall("barline") if barline.get("location", "right") == "right"]
    barlines += [barline for bar in later_bars for barline in bar.findall("barline") if barline.get("location") == "left"]
    return (full is not None and later_full == full and 0 < length < full and 0 < later_length < full
            and length + later_length == full
            and label.isdigit() and label != "0" and later_label.isdigit() and later_label != label
            and later_bars[0].get("implicit") != "yes"
            and any(barline.find("repeat") is not None or barline.findtext("bar-style") in DOUBLE_BARS for barline in barlines))


def _octave_shifts_in_time_order(measure: ET.Element) -> list[ET.Element]:
    timed, cursor = [], 0
    for element in list(measure):
        if element.tag == "direction" and element.find("direction-type/octave-shift") is not None:
            timed.append((cursor, len(timed), element))
            measure.remove(element)
        else:
            cursor += _advance(element)
    timed.sort(key=lambda item: item[:2])
    cursor, position, ordered = 0, 0, []
    for offset, _, direction in timed:
        while position < len(measure) and (cursor < offset or measure[position].tag in ("attributes", "print")):
            cursor += _advance(measure[position])
            position += 1
        measure.insert(position, direction)
        position += 1
        ordered.append(direction)
    return ordered


def _advance(element: ET.Element) -> int:
    if element.tag == "backup":
        return -int(element.findtext("duration"))
    if element.tag == "forward":
        return int(element.findtext("duration"))
    if element.tag == "note" and element.find("chord") is None and element.find("grace") is None:
        return int(element.findtext("duration") or 0)
    return 0


def _drop_restated_keys(part: ET.Element) -> None:
    whole, per_staff = None, {}
    for measure in part.iter("measure"):
        for attributes in measure.findall("attributes"):
            for key in attributes.findall("key"):
                state = [(child.tag, child.text) for child in key]
                staff = key.get("number")
                if staff is None:
                    restated = whole == state and all(other == state for other in per_staff.values())
                    whole, per_staff = state, {number: state for number in per_staff}
                else:
                    restated = per_staff.get(staff, whole) == state
                    per_staff[staff] = state
                if restated:
                    attributes.remove(key)
            if len(attributes) == 0:
                measure.remove(attributes)


def _one_division(part: ET.Element) -> None:
    changes = part.findall("measure/attributes/divisions")
    values = {int(element.text) for element in changes}
    if len(values) < 2:
        return
    common = math.lcm(*values)
    current = int(changes[0].text)
    for measure in part.iter("measure"):
        for element in measure:
            divisions = element.find("divisions") if element.tag == "attributes" else None
            if divisions is not None:
                current = int(divisions.text)
                divisions.text = str(common)
            for duration in element.findall("duration"):
                duration.text = str(round(float(duration.text) * common / current))
