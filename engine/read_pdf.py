"""Read a PDF of printed music into MusicXML with Audiveris (optical music recognition)."""

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

# Where the Docker image unpacks the .deb; the skill and the tests pass their own copy.
AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")
# For all readings of one PDF together: the Cloud Run request ends at 300 s, and a stuck run would hold the
# one-read-at-a-time lock.
TIMEOUT = 240
PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
# Shown above the engraved result in both hosts (owner's wording, 2026-10-11).
CHECK = "This is what I read from your PDF; check it against your copy before I analyse it."
SCAN_WARNING = "Scanned pages often have reading mistakes, so please check carefully."
SLURS_LEFT_OUT = "Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
SHOWN = 4  # problem spots named in the message; the rest are counted
_LENGTH = {"whole": 4, "half": 2, "quarter": 1, "eighth": Fraction(1, 2),
           "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}
_SWITCH = "org.audiveris.omr.sheet.ProcessingSwitches."
# Audiveris drops a rest within half a staff space of a note as a smudge, which loses the rests of a second voice and
# mistimes the notes after them (log 35). Then the settings tried, in order: grace notes need small heads, and implicit
# tuplets finds triplets printed without a "3"; each helps some pieces and hurts others, so they are only alternatives.
_REST = ["-option", "org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0"]
_SMALL = ["-option", _SWITCH + "smallHeads=true", "-option", _SWITCH + "smallBeams=true"]
SETTINGS = [_REST, _REST + _SMALL, _REST + _SMALL + ["-option", _SWITCH + "implicitTuplets=true"]]
# Changes when the reading changes (Audiveris build, settings or the repairs after it), so cached readings made before are not reused.
READER = "5.11.0-sma.1-best3-tuplet-rests-r4"
MIN_NOTES = 0.95  # a reading with fewer notes than this share of the fullest reading is never chosen
RETRY_ABOVE = 3  # bars that don't add up before the other settings are tried; fewer gained nothing (log 35)


class ReadError(ValueError):
    """The PDF could not be opened or no music could be read from it."""


@dataclass
class PdfReading:
    musicxml: bytes  # plain MusicXML, cleaned for Verovio (see `clean`)
    pages: int
    scan: bool
    skipped: list[int] = field(default_factory=list)  # page numbers Audiveris found no staves on


def notice(score: bytes, scan: bool, skipped: list[int], slurs_kept: bool, spots=None) -> str:
    """The message shown above the engraved reading: what to check, and where reading mistakes are likely."""
    text = CHECK + (" " + SCAN_WARNING if scan else "")
    if skipped:
        pages = ", ".join(str(page) for page in skipped)
        text += f" Page{'s' if len(skipped) > 1 else ''} {pages} could not be read (no staves were found), so that music is missing."
    uneven, guessed = spots or problem_spots(score)
    if guessed:
        # The meter is not named: a bar length cannot tell 6/8 from 3/4 or 2/2 from 4/4.
        text += " No time signature was read, so bars were checked against the most common bar length."
    if uneven:
        verb = "doesn't" if len(uneven) == 1 else "don't"
        # With some bars left out of the list, "(shaded)" after "and 4 more" read as if only those 4 were shaded.
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
    """Where a reading is likely wrong, by the bar numbers the engraving prints (a pickup is 0).

    Bars that don't add up: a voice runs past the bar's meter, or a short voice runs on into the place where another
    voice of the same staff starts after a hidden gap (the reader split one line of music into two that overlap,
    like five eighths where a triplet and two eighths were printed). A voice that just stops early is not counted:
    that is nearly always a rest the reader left out, with the notes right. A bar shorter than its meter in every voice is
    fine as the opening pickup, as a last bar that completes it, or as one half of a bar split in two (at a repeat
    sign) when the two halves add up to one full bar. A duration inconsistent with its written note value also points to
    misread timing. A backup that runs before the start of the bar means some of its music is missing.

    A part with no time signature (a "C" read as a note) is checked against its most common bar length instead; the
    second value is whether any part had to be checked that way. (Replacing a meter that was read, because most
    bars disagreed with it, lost 3 readings 3-5% in the benchmark: the mode is often a misread bar length.)"""
    return _problem_spots(score, timing=True)


def _problem_spots(score: bytes, *, timing: bool) -> tuple[list[int], bool]:
    measures = ScoreIndex(load_toolkit(score).getMEI()).measures
    number_at = {segment.index: measure.number for measure in measures for segment in measure.segments}
    bars = []  # (printed number, full length, voice totals) per measure of the file, in order
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
            if beats and all(count.strip().isdigit() for count in beats.split("+")):  # "3+2" is a meter too
                full = Fraction(sum(int(count) for count in beats.split("+")) * 4, int(time.findtext("beat-type")))
            voices, staff_of, gap = {}, {}, {}  # gap: the hidden space a voice starts with
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
        # A guessed meter says nothing about short bars: a piece that changes meter has them (benchmark: Hensel).
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


# The picture the user checks the reading against. Verovio numbers the first bar of each system; `number_bars` adds the
# rest in clear spots, so "check bar 12" can be followed without a number printed over a trill, volta or ledger note.
# Verovio spaces the systems for its own marks only; a number raised over a volta needs one and a half staff spaces more
# (spacingSystem is in half staff spaces; Verovio's default is 4).
PREVIEW_OPTIONS = {**tint.BOXES, "spacingSystem": 7}
BAR_NUMBER_SIZE = 500  # ~10 px tall on a 700 px card; 300 was ~6 px


def preview(score: bytes, tall: bool = False, spots=None) -> Engraving:
    """The reading engraved for checking: every bar numbered and bars that don't add up shaded pale yellow, which the
    notice names. `tall` puts every bar on one page, for the card."""
    tall_page = {"adjustPageHeight": True, "pageHeight": 60000} if tall else {}
    return shade(load_toolkit(score, {**PREVIEW_OPTIONS, **tall_page}), score, spots)


def _courtesy_x(layout: PageLayout) -> dict[str, float]:
    """Where the courtesy key signature starts in each measure that ends a system with one: the key signature drawn
    after the music, not before it."""
    found = {}
    for group in layout.root.iter(f"{S}g"):
        if "measure" in group.get("class", "").split() and group.get("id") in layout.measures:
            for staff in group.findall(f"{S}g"):
                kids = [kid for kid in staff.findall(f"{S}g") if kid.get("class") in {"layer", "keySig"}]
                for after, kid in zip(kids, kids[1:]):
                    if kid.get("class") == "keySig" and after.get("class") == "layer" and kid.get("id") in layout.boxes:
                        found[group.get("id")] = min(found.get(group.get("id"), 1e9), layout.boxes[kid.get("id")].x)
    return found


def number_bars(layout: PageLayout, index: ScoreIndex) -> None:
    """A number above every bar after the first, raised until it is clear of the music."""
    # Verovio's own numbers (first bar of each system) are small and fixed; every number is drawn here, the same size.
    for parent in list(layout.root.iter()):
        for child in [c for c in parent if "mNum" in (c.get("class") or "").split()]:
            parent.remove(child)
    for measure in index.measures:
        geometry = layout.measures.get(measure.segments[0].id)
        if geometry is None or measure.number < 2:
            continue
        system = layout.systems[geometry.system]
        string = str(measure.number)
        width, height = text.width(string, BAR_NUMBER_SIZE), BAR_NUMBER_SIZE
        top = min(box.y for box in geometry.lines)
        # Gould (Behind Bars): above the top staff at the barline, raised clear of what is there. Never sideways, where
        # a number beside noteheads reads as a fingering or tuplet number.
        spots = [(geometry.x0 + 60, top - 90 - rise) for rise in range(0, 2400, 100)]

        def padded(spot):
            return Box(spot[0] - 20, spot[1] - height * 0.75 - 20, width + 40, height + 40)

        # Raised over a volta or a high note, a number can reach the music hanging below the system above.
        neighbours = layout.systems[max(system.index - 1, 0) : system.index + 1]
        spot = next((s for s in spots if all(layout._is_free(n, padded(s)) for n in neighbours)), None) \
            or min(spots, key=lambda s: sum(layout._overlap(n, padded(s)) for n in neighbours))
        box = layout._text(*spot, string, BAR_NUMBER_SIZE, italic=True)
        layout._reserve(system, box, pad=20)


def shade(toolkit, score: bytes, spots=None) -> Engraving:
    """Every page of a toolkit loaded with PREVIEW_OPTIONS, marked as `preview` says. `spots` is `problem_spots(score)`
    when the caller already has it."""
    uneven, _ = spots or problem_spots(score)
    index = ScoreIndex(toolkit.getMEI())
    layouts = []
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(toolkit.renderToSVG(page), index)
        number_bars(layout, index)
        courtesy = _courtesy_x(layout) if uneven else {}
        for number in uneven:
            for segment in index.measure(number).segments:
                geometry = layout.measures.get(segment.id)
                if geometry:
                    # Staff line to staff line, as SmartScore shades; the staves' own boxes also take in ledger lines.
                    top = min(box.y for box in geometry.lines)
                    bottom = max(box.bottom for box in geometry.lines)
                    right = courtesy.get(segment.id, geometry.x1)
                    tint.tint(layout, Box(geometry.x0, top, right - geometry.x0, bottom - top),
                              tint.FLAG_BAR, tint.FLAG_OPACITY, radius=0)
        layouts.append(layout)
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
    """A PDF that paints no vector path (staff lines, stems, beams) on any page holds only pictures of pages.
    Text is not counted: scanned books often carry an invisible OCR text layer, and engravers draw staff lines."""

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
    """Read with the default settings; when that reading has many bars that don't add up, also read with the other
    settings and keep whichever has fewest (log 35: right pitch and timing 82.0% -> 84.3% on the benchmark).

    `raw` stands in for `audiveris_read`: the benchmark passes one that caches Audiveris's output, so a change to the
    code after it (cleaning, choosing, triplets) is measured without reading every PDF again."""
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
        # A reading that lost pages is never preferred for having fewer bars that don't add up
        readings = [best, *(other for other in others if other)]
        # Fewest problem bars alone can pick a reading that dropped notes (Hensel's Nachtwanderer: a fifth of them)
        counts = [_pitched_notes(reading[0]) for reading in readings]
        complete = [reading for reading, count in zip(readings, counts) if count >= MIN_NOTES * max(counts)]
        best = min(complete, key=lambda reading: (len(reading[1]), len(reading[2])))
    musicxml, skipped, _ = best
    for repair in (infer_tuplet_rests, infer_triplets):
        try:
            musicxml = repair(musicxml)
        except Exception:
            # A repair is an improvement, not a requirement: if it fails, keep the reading as Audiveris gave it.
            log.exception("PDF reading repair %s failed", repair.__name__)
    return PdfReading(musicxml, pages, scan, skipped)


def _pitched_notes(musicxml: bytes) -> int:
    return sum(1 for note in ET.fromstring(musicxml).iter("note") if note.find("pitch") is not None)


def _retry(data: bytes, audiveris: str, options: list[str], deadline: float, raw):
    try:
        return _read(data, audiveris, options, deadline, raw)
    except (ReadError, ScoreError, zipfile.BadZipFile, ET.ParseError):  # the first reading stands
        return None


def _read(data: bytes, audiveris: str, options: list[str], deadline: float, raw):
    """One reading: (cleaned MusicXML, skipped pages, bars that don't add up), or None if it ran out of time."""
    read = raw(data, audiveris, options, deadline)
    if read is None:
        return None
    mxl, skipped = read
    musicxml = clean(mxl)
    # The added timing warnings were measured on fixed readings; using them to
    # rank alternatives can choose a less accurate reading (Haydn canzonet).
    return musicxml, skipped, _problem_spots(musicxml, timing=False)[0]


def audiveris_read(data: bytes, audiveris: str, options: list[str], deadline: float) -> tuple[bytes, list[int]] | None:
    """Audiveris's own .mxl and the pages it found no staves on, or None if it ran out of time."""
    with tempfile.TemporaryDirectory(prefix="read_pdf_") as work:
        source = Path(work) / "score.pdf"
        source.write_bytes(data)
        # Audiveris writes settings under $HOME, which is read-only in some sandboxes. Its startup asks GTK for the
        # screen scale unless one is given, and fails where GTK is not installed (the server image). The heap is
        # capped so a read stays near the 1.3 GB measured beside the server (log 32); its own default is 8 GB.
        # It also needs the system's fonts, not the engine's FONTCONFIG_FILE (engine/render.py), which it rejects.
        env = {key: value for key, value in os.environ.items() if key != "FONTCONFIG_FILE"}
        env.update(HOME=work, _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
        try:
            output = run(audiveris, options, source, work, env, deadline)
            books = sorted(Path(work).glob("*.omr"))
            if not list(Path(work).glob("*.mxl")) and books:
                # A page with no staff system ("No system found") stops the export of the whole book, but the
                # other pages were read and saved in the .omr; exporting from it gives those (spike/omr/RESULTS.md).
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
    """Fix habits of Audiveris's MusicXML that make Verovio lose or misdraw music (log 33), and drop marks it invents.

    It repeats <beam> on every note of a chord; Verovio then drops the chord notes ("Chord starting point has not
    been found"). It starts octave lines it never stops; Verovio draws the rest of the piece an octave off (the note
    pitches are sounding pitches either way, so dropping an unclosed line only changes the display). And it changes
    <divisions> partway through a part; Verovio keeps the first value but writes later durations in the new units,
    so every onset after the change is wrong for ScoreIndex. One value per part avoids that."""
    with zipfile.ZipFile(io.BytesIO(mxl)) as archive:
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        root = ET.fromstring(archive.read(name))
    for note in root.iter("note"):
        if note.find("chord") is not None:
            for beam in note.findall("beam"):
                note.remove(beam)
    # Without a repeat sign an ending is a phantom (8 of 11 PDFs that had endings); the original has none.
    if root.find(".//barline/repeat") is None:
        for measure in root.iter("measure"):
            for barline in measure.findall("barline"):
                endings = barline.findall("ending")
                for ending in endings:
                    barline.remove(ending)
                # Only a barline that held nothing but endings goes; segno and coda marks sit on barlines too.
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
    """Audiveris restates the key at page breaks (59 of 80 readings); a key that equals the current one is not a change.

    A key without a number covers every staff, so it also resets each staff's current key; otherwise it is compared
    with a stale one and a return to the home key after a single-staff key is dropped (Schubert, Die Stadt)."""
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
