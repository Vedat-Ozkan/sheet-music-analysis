"""Render a score with an annotation list drawn on it."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from engine import notation, slurs
from engine.annotations import AnnotationList, Cadence, Callout, Harmony, NoteRef, NonChordTone, Phrase, Region, VoiceLeading
from engine.overlay import PageLayout
from engine.render import Engraving, incoming_ties, load_toolkit, shorten_ties
from engine.score import PositionError, ScoreIndex

if TYPE_CHECKING:
    from engine.comparison import Label

# A page is an annotated excerpt for study, never a stand-in for the whole score (users send copyrighted music).
MAX_BARS = 32

# Room for the rows of labels under each system and the brackets above it.
ANNOTATED_OPTIONS = {
    "svgBoundingBoxes": True,
    "svgAdditionalAttribute": ["staff@n"],  # a staff is found by its number even when empty staves are hidden
    "adjustPageHeight": True,
    "spacingSystem": 26,
    "pageMarginTop": 230,  # two stacked brackets with labels fit above the first system
    "pageMarginBottom": 260,
}


CHECK_SPACING = 34
CHECK_MARGIN = 500


class AnnotationError(ValueError):
    """One or more annotations point at places that are not in the score."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def check(annotations: AnnotationList, index: ScoreIndex) -> None:
    """Resolve every position against the score and report all problems at once."""
    problems = []
    key = None
    for harmony in sorted((a for a in annotations.annotations if isinstance(a, Harmony)),
                          key=lambda h: (h.at.measure, h.at.beat)):
        key = harmony.key or key
        if annotations.style == "figured_bass":
            try:
                notation.numeral(harmony.label, key, annotations.style, 440)
            except ValueError as error:
                problems.append(f"harmony at measure {harmony.at.measure} beat {harmony.at.beat}: {error}")
    for number, annotation in enumerate(annotations.annotations):
        try:
            if isinstance(annotation, (Harmony, Cadence, Callout)):
                index.measure(annotation.at.measure).offset_of(annotation.at.beat)
            elif isinstance(annotation, (Phrase, Region)):
                index.measure(annotation.start.measure).offset_of(annotation.start.beat)
                end = index.measure(annotation.end.measure)
                if annotation.end.beat is not None:
                    end.offset_of(annotation.end.beat)
            elif isinstance(annotation, NonChordTone):
                index.find_note(**annotation.note.model_dump())
            elif isinstance(annotation, VoiceLeading):
                index.find_note(**annotation.from_note.model_dump())
                index.find_note(**annotation.to_note.model_dump())
        except PositionError as error:
            problems.append(f"annotations[{number}] ({annotation.type}): {error}")
    if problems:
        raise AnnotationError(problems)


def render(
    score: bytes,
    annotations: AnnotationList,
    measures: tuple[int, int] | None = None,
    view: str = "all",
    role: str | None = None,
    piano: bool = False,
    student_labels: list[Label] | None = None,
) -> Engraving:
    """Engrave `measures` (printed numbers, inclusive; the whole score by default, if it is short enough) with annotations drawn on.

    With `piano`, the passage is drawn as a two-staff piano reduction; the annotations still describe the original.
    With `student_labels`, the overlay is replaced by the student's labels checked against the annotations."""
    if piano:
        score, annotations = _piano_version(score, annotations, measures)
    options = ANNOTATED_OPTIONS
    if student_labels is not None:
        # The tool's row and the notes sit under the student's row, which is all Verovio reserves.
        options = {**options, "spacingSystem": CHECK_SPACING, "pageMarginBottom": CHECK_MARGIN}
    toolkit = load_toolkit(score, options)
    index = ScoreIndex(toolkit.getMEI())
    check(annotations, index)
    results = None
    if student_labels is not None:
        from engine import check_analysis, check_display
        results = check_analysis.compare(student_labels, annotations.model_dump(exclude_none=True), index)
        annotations = check_display.reserve(results)
    first, last = measures or (index.measures[0].number, index.measures[-1].number)
    bars = sum(1 for measure in index.measures if first <= measure.number <= last and measure.number > 0)
    if bars > MAX_BARS:
        raise PositionError(
            f"A page can show at most {MAX_BARS} bars and measures {first}-{last} have {bars}. "
            f"Draw the analysis passage by passage, {MAX_BARS} bars or fewer each."
        )
    ties = incoming_ties(toolkit, index, measures[0]) if measures else set()
    _reserve_numeral_room(toolkit, index, annotations)
    _reserve_staff_bracket_room(toolkit, index, annotations)
    if measures:
        toolkit.setOptions({"pageHeight": 60000})  # an excerpt is one tall image
        toolkit.select({"measureRange": index.measure_range(*measures)})
        toolkit.redoLayout()
    _balance_systems(toolkit, index, measures, annotations)

    def relayout(mei: str) -> None:
        toolkit.loadData(mei)
        if measures:
            toolkit.select({"measureRange": index.measure_range(*measures)})
        toolkit.redoLayout()

    slurs.untangle(toolkit, relayout)
    _move_text_off_stems(toolkit, relayout)
    pages = []
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(shorten_ties(toolkit.renderToSVG(page), ties), index)
        if results is None:
            layout.draw(annotations, view, role)
        else:
            check_display.draw(layout, results)
        pages.append(layout.to_svg())
    return Engraving(pages)


def _piano_version(score: bytes, annotations: AnnotationList, measures: tuple[int, int] | None) -> tuple[bytes, AnnotationList]:
    """The piano reduction, and the annotations pointed at it: a marked note is found again by bar, beat
    and pitch on whichever piano staff it landed, and a bracket tied to one instrument's staff spans the system."""
    from engine import piano as piano_reduction  # music21 is loaded only for a reduction; the skill installs it then

    original = ScoreIndex(load_toolkit(score).getMEI())
    check(annotations, original)
    refs = [ref for a in annotations.annotations for ref in _note_refs(a)]
    found = [original.find_note(**ref.model_dump()) for ref in refs]
    keep = [(ref.measure, event.onset, event.pitch, event.duration) for ref, event in zip(refs, found)]
    reduced = piano_reduction.reduce(score, measures, keep)
    index = ScoreIndex(load_toolkit(reduced).getMEI())
    moved = {}
    for ref, event in zip(refs, found):
        try:
            staff = index.find_note(ref.measure, ref.beat, pitch=event.pitch).staff
        except PositionError:
            staff = None  # check() below reports the note as missing
        moved[id(ref)] = ref.model_copy(update={"staff": staff, "pitch": event.pitch})
    pointed = []
    for annotation in annotations.annotations:
        if isinstance(annotation, NonChordTone):
            annotation = annotation.model_copy(update={"note": moved[id(annotation.note)]})
        elif isinstance(annotation, VoiceLeading):
            annotation = annotation.model_copy(update={"from_note": moved[id(annotation.from_note)], "to_note": moved[id(annotation.to_note)]})
        elif isinstance(annotation, Region) and annotation.staff:
            annotation = annotation.model_copy(update={"staff": None})
        pointed.append(annotation)
    return reduced, annotations.model_copy(update={"annotations": pointed})


def _note_refs(annotation) -> list[NoteRef]:
    if isinstance(annotation, NonChordTone):
        return [annotation.note]
    if isinstance(annotation, VoiceLeading):
        return [annotation.from_note, annotation.to_note]
    return []


DIR = re.compile(r'<g id="([^"]+)" class="dir">(.*?)</text>', re.S)
RECT = r'class="{}{}bounding-box"[^>]*>\s*<rect x="([-\d.]+)" y="([-\d.]+)" height="([-\d.]+)" width="([-\d.]+)"'


def _move_text_off_stems(toolkit, relayout) -> None:
    """Words that a stem runs through go to the other side of their staff.

    Verovio keeps directions clear of the notes around them but not of a stem reaching across
    from the other staff, as a cross-staff beam's does."""
    mei = toolkit.getMEI()
    crossed = set()
    for page in range(1, toolkit.getPageCount() + 1):
        svg = toolkit.renderToSVG(page)
        stems = [tuple(map(float, box)) for box in re.findall(RECT.format("stem", " "), svg)]
        for id, body in DIR.findall(svg):
            for x, y, h, w in (tuple(map(float, box)) for box in re.findall(RECT.format("text", " "), body)):
                if any(sx < x + w and x < sx + sw and sy < y + h and y < sy + sh for sx, sy, sh, sw in stems):
                    crossed.add(id)
    for id in crossed:
        tag = re.search(rf'<dir\b(?![^>]*type="analysis-room")[^>]*xml:id="{re.escape(id)}"[^>]*>', mei)
        if tag and (side := re.search(r'\bplace="(above|below)"', tag.group(0))):
            flipped = tag.group(0).replace(side.group(0), f'place="{"below" if side.group(1) == "above" else "above"}"')
            mei = mei.replace(tag.group(0), flipped, 1)
    if crossed:
        relayout(mei)


def _reserve_numeral_room(toolkit, index: ScoreIndex, annotations: AnnotationList) -> None:
    """Verovio spaces bars by their notes alone, so a bar with several chords squeezes its numerals together.
    A hidden chord symbol per numeral makes it widen such bars; the overlay removes them before drawing."""
    mei = toolkit.getMEI()
    bottom_staff = max(int(n) for n in re.findall(r'<staffDef\b[^>]*?\bn="(\d+)"', mei))
    added: dict[str, list[str]] = {}
    key = None
    harmonies = [a for a in annotations.annotations if isinstance(a, Harmony)]
    if annotations.style != "current":
        harmonies.sort(key=lambda h: (index.measure(h.at.measure).index, h.at.beat))
    for harmony in harmonies:
        key = harmony.key or key
        label = harmony.label
        if annotations.style != "current":
            chunks, _ = notation.numeral(label, key, annotations.style, 440)
            label = " ".join(chunk.text for chunk in chunks)
        measure = index.measure(harmony.at.measure)
        offset = measure.offset_of(harmony.at.beat)
        segment = measure.segment_at(offset)
        unit = int(measure.meter.split("/")[1]) if measure.meter else 4
        tstamp = 1 + (offset - segment.start) * unit / 4
        # Verovio sets chord symbols smaller than our numerals, hence the padding.
        added.setdefault(segment.id, []).append(
            f'<harm staff="{bottom_staff}" tstamp="{float(tstamp):g}" place="below">{escape(label)}\u00a0\u00a0</harm>'
        )
    if not added:
        return
    for measure_id, harms in added.items():
        # MEI measures never nest, so the first closing tag after the opening one is this measure's.
        end = mei.index("</measure>", mei.index(f'xml:id="{measure_id}"'))
        mei = mei[:end] + "".join(harms) + mei[end:]
    toolkit.loadData(mei)


def _reserve_staff_bracket_room(toolkit, index: ScoreIndex, annotations: AnnotationList) -> None:
    """A bracket drawn at one staff needs room between that staff and the one above, which Verovio
    sets by the notes alone. A hidden two-line direction above the staff in each bar of the region
    makes it open the gap; the overlay removes them before drawing."""
    mei = toolkit.getMEI()
    added: dict[str, list[str]] = {}
    for region in annotations.annotations:
        if not isinstance(region, Region) or not region.staff:
            continue
        first, last = index.measure(region.start.measure).index, index.measure(region.end.measure).last_index
        for measure in index.measures:
            for segment in measure.segments:
                if first <= segment.index <= last:
                    added.setdefault(segment.id, []).append(
                        f'<dir staff="{region.staff}" tstamp="1" place="above" type="analysis-room">{escape(region.label or "-")}<lb/>-</dir>'
                    )
    if not added:
        return
    for measure_id, dirs in added.items():
        end = mei.index("</measure>", mei.index(f'xml:id="{measure_id}"'))
        mei = mei[:end] + "".join(dirs) + mei[end:]
    toolkit.loadData(mei)


def _balance_systems(toolkit, index: ScoreIndex, measures: tuple[int, int] | None, annotations: AnnotationList) -> None:
    """Choose where lines break, the way an engraver does for a study score: at the start of a phrase
    or just after a cadence, never between a cadence's two chords, with every line about as full as
    the others. Verovio fills each line greedily, which can split a cadence over two lines or leave
    a bar or two alone on the last one."""
    if toolkit.getPageCount() != 1:
        return
    systems = PageLayout(toolkit.renderToSVG(1), index).systems
    if len(systems) < 2:
        return
    line = max(system.right - system.left for system in systems)
    # Bars are measured at their natural width (justified, each line's bars add up to the full line),
    # all on one line, so that only the first carries the clef and key a line starts with. That
    # start costs as much again on every later line: the difference, for the bars that began lines
    # in Verovio's own layout, between their width there and on the single line.
    toolkit.setOptions({"noJustification": True})
    toolkit.redoLayout()
    starts_natural = {system.measures[0].id: system.measures[0].x1 - system.measures[0].x0 for system in PageLayout(toolkit.renderToSVG(1), index).systems[1:]}
    toolkit.setOptions({"breaks": "none"})
    toolkit.redoLayout()
    single = [measure for system in PageLayout(toolkit.renderToSVG(1), index).systems for measure in system.measures]
    toolkit.setOptions({"noJustification": False, "breaks": "auto"})
    bars = [(measure.id, measure.x1 - measure.x0) for measure in single]
    width = dict(bars)
    opening = [starts_natural[id] - width[id] for id in starts_natural if id in width]
    opening = sum(opening) / len(opening) if opening else 0.0
    # Verovio squeezes a line a little below its bars' natural width; the fullest line it chose
    # itself shows how far, and so how much a line can hold.
    fullest = max(
        sum(width.get(measure.id, 0.0) for measure in system.measures) + (opening if number else 0.0)
        for number, system in enumerate(systems)
    )
    line = max(line, fullest)
    number = {segment.id: measure.number for measure in index.measures for segment in measure.segments}
    good, bad = set(), set()
    for annotation in annotations.annotations:
        if isinstance(annotation, (Phrase, Region)):
            start = annotation.start
            # A phrase that begins with an upbeat starts its line at the next barline.
            good.add(start.measure if start.beat < 1.5 else start.measure + 1)
        elif isinstance(annotation, Cadence):
            good.add(annotation.at.measure + 1)
            if annotation.at.beat < 2:  # arriving on the downbeat, its approach chord is in the bar before
                bad.add(annotation.at.measure)
    first_bar = [position == 0 or number.get(bars[position - 1][0]) != number.get(bars[position][0]) for position in range(len(bars))]
    penalty = [
        0.0 if number.get(id) in good else 40.0 if number.get(id) in bad or not first_bar[position] else 6.0
        for position, (id, _) in enumerate(bars)
    ]
    starts = _breaks([width for _, width in bars], line, penalty, opening)
    mei = re.sub(r"<(sb|pb)\b[^>]*/>", "", toolkit.getMEI())
    for position in starts:
        start = mei.index(f'xml:id="{bars[position][0]}"')
        start = mei.rindex("<measure", 0, start)
        mei = mei[:start] + "<sb />" + mei[start:]
    # "smart" keeps our breaks (and still breaks an overfull line); "line" drops the last system of a selection
    # in Verovio 6.3. Every line now holds about the same music, so the last one is justified like the rest.
    toolkit.setOptions({"breaks": "smart", "breaksSmartSb": 0.3, "minLastJustification": 0})
    toolkit.loadData(mei)
    if measures:
        toolkit.select({"measureRange": index.measure_range(*measures)})
    toolkit.redoLayout()


def _breaks(widths: list[float], line: float, penalty: list[float], opening: float = 0.0) -> list[int]:
    """Indexes of the bars that start lines 2..n: each line fits, lines are evenly full, few lines,
    and breaks fall where `penalty` (per bar, for a line starting there) is low. `opening` is the
    width a line's clef and key add to the bar that starts it, already counted in the first bar."""
    count = len(widths)
    best: list[tuple[float, int]] = [(0.0, -1)] + [(math.inf, -1)] * count  # cost of bars[:i], start of its last line
    for end in range(1, count + 1):
        for begin in range(end - 1, -1, -1):
            width = sum(widths[begin:end]) + (opening if begin else 0.0)
            if width > line and end - begin > 1:
                break
            fill = width / line
            # Lines should be close to full. The last may be shorter, but a bar or two stretched
            # over a whole line looks worse than lines split evenly.
            shortfall = 2 * max(0.0, 0.75 - fill) if end == count else 1 - fill
            cost = best[begin][0] + 100 * shortfall**2 + 10 + (penalty[begin] if begin else 0)
            if cost < best[end][0]:
                best[end] = (cost, begin)
    starts, end = [], count
    while end:
        end = best[end][1]
        if end:
            starts.append(end)
    return sorted(starts)
