from __future__ import annotations

import io
import logging
import math
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import pikepdf

from engine import text, tint
from engine.overlay import S, Box, PageLayout
from engine.render import Engraving, ScoreError, load_toolkit
from engine.score import TOLERANCE, ScoreIndex
from engine.triplets import infer_triplets
from engine.tuplet_rests import infer_tuplet_rests

log = logging.getLogger(__name__)

AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")
TIMEOUT = 240
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
CHECK = "This is what I read from your PDF; check it against your copy before I analyse it."
SCAN_WARNING = "Scanned pages often have reading mistakes, so please check carefully."
SLURS_LEFT_OUT = "Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
SHOWN = 4
_LENGTH = {"whole": 4, "half": 2, "quarter": 1, "eighth": Fraction(1, 2),
           "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}
_SWITCH = "org.audiveris.omr.sheet.ProcessingSwitches."
_REST = ["-option", "org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0"]
_SMALL = ["-option", _SWITCH + "smallHeads=true", "-option", _SWITCH + "smallBeams=true"]
SETTINGS = [_REST, _REST + _SMALL, _REST + _SMALL + ["-option", _SWITCH + "implicitTuplets=true"]]
READER = "5.11.0-sma.2-best3-tuplet-rests-ocr-r6"
MIN_NOTES = 0.95
RETRY_ABOVE = 3

class ReadError(ValueError):
    pass


@dataclass
class PdfReading:
    musicxml: bytes
    pages: int
    scan: bool
    skipped: list[int] = field(default_factory=list)

def notice(score: bytes, scan: bool, skipped: list[int], slurs_kept: bool, spots=None) -> str:
    text = CHECK + (" " + SCAN_WARNING if scan else "")
    if skipped:
        pages = ", ".join(str(page) for page in skipped)
        text += f" Page{'s' if len(skipped) > 1 else ''} {pages} could not be read (no staves were found), so that music is missing."
    uneven, guessed = spots or problem_spots(score)
    if guessed:
        text += " No time signature was read, so bars were checked against the most common bar length."
    if uneven:
        verb = "doesn't" if len(uneven) == 1 else "don't"
        who = f"The shaded bars ({_numbers(uneven)[5:]})" if len(uneven) > SHOWN else f"{_numbers(uneven)} (shaded)"
        text += f" {who} {verb} add up to a full bar, so a note or triplet may be misread there."
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
    for part in ET.fromstring(score).iter("part"):
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
            cursor = Fraction(0)
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
    return sorted(set(uneven) | (timing_errors if timing else set())), inferred


PREVIEW_OPTIONS = {**tint.BOXES, "spacingSystem": 7}
BAR_NUMBER_SIZE = 500
TOP_CLEARANCE = 3 * tint.SPACE


def preview(score: bytes, tall: bool = False, spots=None) -> Engraving:
    tall_page = {"adjustPageHeight": True, "pageHeight": 60000} if tall else {}
    spots = spots or problem_spots(score)
    engraving = shade(load_toolkit(score, {**PREVIEW_OPTIONS, **tall_page}, labelled_bars=spots[0]), spots)
    return Engraving([_stacked(engraving.svgs)]) if tall and engraving.page_count > 1 else engraving


def _stacked(svgs: list[str]) -> str:
    pages, top = [], 0.0
    for svg in svgs:
        _, _, width, height = map(float, re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg).groups())
        pages.append(svg[svg.index("<svg"):].replace("<svg ", f'<svg y="{top:g}" width="{width:g}" height="{height:g}" ', 1))
        top += height
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {top:g}">{"".join(pages)}</svg>'


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


def is_scan(pdf: pikepdf.Pdf) -> bool:

    def paints(stream, seen: set) -> bool:
        if any(str(operator) in PAINT_OPERATORS for _, operator in pikepdf.parse_content_stream(stream)):
            return True
        for xobject in (stream.get("/Resources", {}).get("/XObject", {}) or {}).values():
            if xobject.get("/Subtype") == "/Form" and xobject.objgen not in seen:
                seen.add(xobject.objgen)
                if paints(xobject, seen):
                    return True
        return False

    return not any(paints(page.obj, set()) for page in pdf.pages)


def read_pdf(data: bytes, audiveris: str = AUDIVERIS, raw=None) -> PdfReading:
    pdf = open_pdf(data)
    pages, scan = len(pdf.pages), is_scan(pdf)
    deadline = time.monotonic() + TIMEOUT
    raw = raw or audiveris_read
    best = _read(data, audiveris, SETTINGS[0], deadline, raw)
    if best is None:
        raise ReadError("Reading this PDF took too long")
    if len(best[2]) > RETRY_ABOVE and deadline - time.monotonic() > 30:
        with ThreadPoolExecutor(len(SETTINGS) - 1) as pool:
            others = list(pool.map(lambda options: _retry(data, audiveris, options, deadline, raw), SETTINGS[1:]))
        readings = [best, *(other for other in others if other)]
        counts = [_pitched_notes(reading[0]) for reading in readings]
        complete = [reading for reading, count in zip(readings, counts) if count >= MIN_NOTES * max(counts)]
        best = min(complete, key=lambda reading: (len(reading[1]), len(reading[2])))
    musicxml, skipped, _ = best
    for repair in (infer_tuplet_rests, infer_triplets):
        try:
            musicxml = repair(musicxml)
        except Exception:
            log.exception("PDF reading repair %s failed", repair.__name__)
    return PdfReading(musicxml, pages, scan, skipped)


def _pitched_notes(musicxml: bytes) -> int:
    return sum(1 for note in ET.fromstring(musicxml).iter("note") if note.find("pitch") is not None)


def _retry(data: bytes, audiveris: str, options: list[str], deadline: float, raw):
    try:
        return _read(data, audiveris, options, deadline, raw)
    except (ReadError, ScoreError, zipfile.BadZipFile, ET.ParseError):
        return None


def _read(data: bytes, audiveris: str, options: list[str], deadline: float, raw):
    read = raw(data, audiveris, options, deadline)
    if read is None:
        return None
    mxl, skipped = read
    musicxml = clean(mxl)
    return musicxml, skipped, _problem_spots(musicxml, timing=False)[0]


def audiveris_read(data: bytes, audiveris: str, options: list[str], deadline: float) -> tuple[bytes, list[int]] | None:
    with tempfile.TemporaryDirectory(prefix="read_pdf_") as work:
        source = Path(work) / "score.pdf"
        source.write_bytes(data)
        env = {key: value for key, value in os.environ.items() if key != "FONTCONFIG_FILE"}
        env.setdefault("TESSDATA_PREFIX", str(Path(audiveris).parent.parent / "tessdata"))
        env.update(HOME=work, _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
        try:
            output = run(audiveris, options, source, work, env, deadline)
            books = sorted(Path(work).glob("*.omr"))
            if not list(Path(work).glob("*.mxl")) and books:
                run(audiveris, options, books[0], work, env, deadline)
        except subprocess.TimeoutExpired:
            return None
        scores = sorted(Path(work).glob("*.mxl"))
        if not scores:
            raise ReadError("No music could be read from this PDF")
        skipped = sorted({int(page) for page in re.findall(r"Sheet \S+#(\d+) flagged as invalid", output)})
        return scores[0].read_bytes(), skipped


def run(audiveris: str, options: list[str], source: Path, work: str, env: dict, deadline: float) -> str:
    command = [audiveris, "-batch", *options, "-export", "-output", work, str(source)]
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, 0)
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=remaining)
    return result.stdout + result.stderr


def clean(mxl: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(mxl)) as archive:
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        root = ET.fromstring(archive.read(name))
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
            for direction in measure.findall("direction"):
                shift = direction.find("direction-type/octave-shift")
                if shift is None:
                    continue
                number = shift.get("number", "1")
                if shift.get("type") == "stop":
                    open_lines.pop(number, None)
                else:
                    if number in open_lines:
                        unclosed.append(open_lines[number])
                    open_lines[number] = (measure, direction)
        for measure, direction in unclosed + list(open_lines.values()):
            measure.remove(direction)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


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
