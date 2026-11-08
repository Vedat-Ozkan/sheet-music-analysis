from __future__ import annotations

import contextvars
import copy
import io
import logging
import math
import os
import re
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

from engine import text, tint
from engine.overlay import S, Box, PageLayout
from engine.render import Engraving, ScoreError, load_toolkit
from engine.score import TOLERANCE, ScoreIndex
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
MAX_PAGES = 12
NOTHING_READ = "No music could be read from this PDF"
NEXT_STEP = (
    ". Tell the user plainly, and suggest what may work: a PDF exported from notation software reads best; a scan "
    "should be straight, sharp and about 300 dpi; a long PDF can be sent a few pages at a time; a MusicXML file "
    "(.mxl or .musicxml) needs no reading at all."
)
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CHECK = "This is what I read from your PDF; check it against your copy before I analyse it."
SCAN_WARNING = "Scanned pages often have reading mistakes, so please check carefully."
SLURS_LEFT_OUT = "Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
SHOWN = 4
_LENGTH = {"whole": 4, "half": 2, "quarter": 1, "eighth": Fraction(1, 2),
           "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}
_SWITCH = "org.audiveris.omr.sheet.ProcessingSwitches."
_BASE = ["-option", _SWITCH + "indentations=false",
         "-option", "org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0",
         "-option", "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8"]
_SMALL = ["-option", _SWITCH + "smallHeads=true", "-option", _SWITCH + "smallBeams=true"]
SETTINGS = [_BASE, _BASE + _SMALL + ["-option", _SWITCH + "implicitTuplets=true"]]
_LELAND = ["-option", "org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland"]
READER = "5.11.0-sma.7-best2-tuplet-rests-eight-leland-ocr-r9-page-size"
MIN_NOTES = 0.95
RETRY_ABOVE = 3

class ReadError(ValueError):
    def __init__(self, message: str, passes: list[dict] | None = None):
        super().__init__(message)
        self.passes = passes or []


@dataclass
class PdfReading:
    musicxml: bytes
    pages: int
    scan: bool
    skipped: list[int] = field(default_factory=list)
    passes: list[dict] = field(default_factory=list)
    low_resolution: bool = False

LOW_RESOLUTION_WARNING = ("This scan is too small to read well, so expect many mistakes, including in bars that are "
                          "not shaded. A sharper scan will read much better.")


def notice(score: bytes, scan: bool, skipped: list[int], slurs_kept: bool, spots=None, low_resolution: bool = False) -> str:
    text = CHECK + (" " + SCAN_WARNING if scan else "") + (" " + LOW_RESOLUTION_WARNING if low_resolution else "")
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
    return text + ("" if slurs_kept else " " + SLURS_LEFT_OUT)


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
    for part_index, part in enumerate(ET.fromstring(score).iter("part")):
        divisions, full = 1, None
        part_bars, guessed = [], False
        for position, measure in enumerate(part.iter("measure"), start=1):
            if measure.find("attributes/divisions") is not None:
                divisions = int(measure.find("attributes/divisions").text)
            time = measure.find("attributes/time")
            beats = time.findtext("beats", "") if time is not None else ""
            if beats and all(count.strip().isdigit() for count in beats.split("+")):
                full = Fraction(sum(int(count) for count in beats.split("+")) * 4, int(time.findtext("beat-type")))
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
                    expected = _LENGTH.get(element.findtext("type"))
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
                    length = Fraction(round(float(element.findtext("duration"))), divisions)
                    cursor += Fraction(element.findtext("duration")) / divisions
                    if element.tag == "forward" and voices.get(voice, 0) == gap.get(voice, 0):
                        gap[voice] = gap.get(voice, 0) + length
                    voices[voice] = voices.get(voice, 0) + length
                    staff_of.setdefault(voice, element.findtext("staff", "1"))
            voices = {(staff_of[voice], voice, gap.get(voice, 0)): length for voice, length in voices.items()}
            if voices:
                part_bars.append((position, number_at.get(position), full, voices))
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
        first, last = position == 1, position == max(bar[0] for bar in bars)
        pickup = max(bars[0][3].values()) if max(bars[0][3].values()) < bars[0][2] else Fraction(0)
        completes = last and abs(pickup + longest - full) <= TOLERANCE
        if longest > full + TOLERANCE or overlapping or (short and not (first or completes or halves)):
            if number is not None and number not in uneven:
                uneven.append(number)
    timing_errors.update(number_at[position] for position, notes in columns.items()
                         if position in number_at and _columns_disagree(notes))
    return sorted(set(uneven) | (timing_errors if timing else set())), inferred


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


def _courtesy_x(layout: PageLayout) -> dict[str, float]:
    found = {}
    for group in layout.root.iter(f"{S}g"):
        if "measure" in group.get("class", "").split() and group.get("id") in layout.measures:
            for staff in group.findall(f"{S}g"):
                kids = [kid for kid in staff.findall(f"{S}g") if kid.get("class") in {"layer", "keySig"}]
                for after, kid in zip(kids, kids[1:]):
                    if kid.get("class") == "keySig" and after.get("class") == "layer" and kid.get("id") in layout.boxes:
                        found[group.get("id")] = min(found.get(group.get("id"), 1e9), layout.boxes[kid.get("id")].x)
    return found


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
        string = str(measure.number)
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
        courtesy = _courtesy_x(layout) if uneven else {}
        for number in uneven:
            for segment in index.measure(number).segments:
                geometry = layout.measures.get(segment.id)
                if geometry:
                    top = min(box.y for box in geometry.lines)
                    bottom = max(box.bottom for box in geometry.lines)
                    right = courtesy.get(segment.id, geometry.x1)
                    tint.tint(layout, Box(geometry.x0, top, right - geometry.x0, bottom - top),
                              tint.FLAG_BAR, tint.FLAG_OPACITY, radius=0)
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
        raise ReadError("This file could not be opened as a PDF") from error


def too_many_pages(pages: int) -> str:
    return (f"This PDF has {pages} pages; the most that can be read is {MAX_PAGES}. Tell the user plainly, "
            "and suggest they attach a PDF of just the pages they want analysed.")


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
        return _read_with_every_setting(data, audiveris, raw, pages, scan, leland, deadline)
    except ReadError as error:
        interlines = [value for record in error.passes for value in record.get("too_close_interlines", []) if value]
        if not interlines:
            raise
        first_passes = error.passes
    enlarged = enlarged_for_interline(data, min(interlines))
    try:
        reading = _read_with_every_setting(enlarged, audiveris, raw, pages, scan, leland, deadline)
    except ReadError as error:
        error.passes = [*first_passes, *error.passes]
        raise
    reading.passes = [*first_passes, *reading.passes]
    reading.low_resolution = True
    return reading


def _read_with_every_setting(data: bytes, audiveris: str, raw, pages: int, scan: bool, leland: bool,
                             deadline: float) -> PdfReading:
    raw = raw or audiveris_read
    stop = threading.Event()
    with ThreadPoolExecutor(len(SETTINGS)) as pool:
        second = min(deadline, time.monotonic() + SECOND_PASS_SECONDS)
        futures = [pool.submit(contextvars.copy_context().run, _read, data, audiveris, setting, leland,
                               deadline if setting == 0 else second, raw, stop)
                   for setting in range(len(SETTINGS))]
        try:
            first = futures[0].result()
            if first[1] is not None and not first[1][1] and len(first[1][2]) <= RETRY_ABOVE:
                stop.set()
            results = [first, *(future.result() for future in futures[1:])]
        finally:
            stop.set()
    passes = [record for record, _ in results]
    readings = [reading for _, reading in results if reading is not None]
    if not readings:
        timed_out = any(record["outcome"] == "timeout" for record in passes)
        raise ReadError("Reading this PDF took too long" if timed_out else NOTHING_READ, passes)
    counts = [_pitched_notes(reading[0]) for reading in readings]
    complete = [reading for reading, count in zip(readings, counts) if count >= MIN_NOTES * max(counts)]
    musicxml, skipped, _ = min(complete, key=lambda reading: (len(reading[1]), len(reading[2])))
    for repair in (infer_tuplet_rests, infer_triplets):
        try:
            musicxml = repair(musicxml)
        except Exception:
            log.exception("PDF reading repair %s failed", repair.__name__)
    return PdfReading(musicxml, pages, scan, skipped, passes)


_TEMPO_NUMBER = re.compile(r"=\s*\d|\bca\.?\s*\d")
_OCTAVE_TEXT = re.compile(r"(8|15)\s*[v0o]?(a|b|ma|mb)?[\s,.'\"_|—–-]*$", re.IGNORECASE)
_ROMAN_NUMERAL = re.compile(r"[ivIV]+[o+]?[\d()/ivIVo+]*$")
_EXPRESSION = re.compile(r"(?:de)?cresc|dim|rit|rall|dolce|espr|legato|sempre|poco", re.IGNORECASE)
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
    except (ScoreError, zipfile.BadZipFile, ET.ParseError) as error:
        record["outcome"] = f"unusable output ({type(error).__name__})"
        return record, None


def audiveris_options(setting: int, leland: bool) -> list[str]:
    return SETTINGS[setting] + (_LELAND if leland else [])


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
        part.extend(_silent_bar(bar) for bar in bars_beside)


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
    added.extend(_silent_bar(bar) for bar in bars_before)
    added.find("measure/attributes").extend(
        copy.deepcopy(element) for element in part.findall("measure[1]/attributes/*") if element.tag in ("staves", "clef"))
    return added


def _silent_bar(beside: ET.Element) -> ET.Element:
    bar = ET.Element("measure", number=beside.get("number"))
    attributes = ET.SubElement(bar, "attributes")
    attributes.extend(copy.deepcopy(element) for element in beside.findall("attributes/*") if element.tag in ("divisions", "key", "time"))
    rest = ET.SubElement(bar, "note")
    ET.SubElement(rest, "rest", measure="yes")
    ET.SubElement(rest, "duration").text = str(_bar_length(beside))
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
    command = ([] if setting == 0 else ["nice", "-n", "19"]) + [
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
            "pages_done": len(re.findall(r"\|\s+PAGE\s*$", output, re.M)),
            "invalid_pages": output.count("flagged as invalid"),
            "problems": sorted(problems), "step_seconds": run_.step_seconds}


def clean(mxl: bytes) -> bytes:
    root = _archived_score(mxl)
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
    _keep_meaningful_text(root)
    _lyrics_to_directions(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


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
