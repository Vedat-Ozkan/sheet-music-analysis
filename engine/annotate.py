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

MAX_BARS = 32

ANNOTATED_OPTIONS = {
    "svgBoundingBoxes": True,
    "svgAdditionalAttribute": ["staff@n", "fermata@staff", "dynam@staff"],
    "adjustPageHeight": True,
    "spacingSystem": 26,
    "pageMarginTop": 230,
    "pageMarginBottom": 260,
}


class AnnotationError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def check(annotations: AnnotationList, index: ScoreIndex) -> None:
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
                if annotation.to_note:
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
    if piano:
        score, annotations = _piano_version(score, annotations, measures)
    toolkit = load_toolkit(score, ANNOTATED_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    check(annotations, index)
    results = None
    if student_labels is not None:
        from engine import check_analysis, check_display
        results = check_display.compare(student_labels, annotations.model_dump(exclude_none=True), index)
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
        toolkit.setOptions({"pageHeight": 60000})
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
    drawn = None
    if results is not None:
        _make_room_for_checks(toolkit, relayout, index, ties, results)
    else:
        drawn = _make_room_for_codes(toolkit, relayout, index, ties, annotations, view, role)
    if drawn:
        return Engraving([layout.to_svg() for layout in drawn])
    pages = []
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(shorten_ties(toolkit.renderToSVG(page), ties), index)
        if results is None:
            layout.draw(annotations, view, role)
        else:
            check_display.draw(layout, results, page == toolkit.getPageCount())
        pages.append(layout.to_svg())
    return Engraving(pages)


def _make_room_for_checks(toolkit, relayout, index, ties, results) -> None:
    from engine import check_display

    base = toolkit.getMEI()
    bottom_staff = max(int(n) for n in re.findall(r'<staffDef\b[^>]*?\bn="(\d+)"', base))
    lines: dict[str, int] = {}
    for _ in range(6):
        needs: dict[str, int] = {}
        for page in range(1, toolkit.getPageCount() + 1):
            layout = PageLayout(shorten_ties(toolkit.renderToSVG(page), ties), index)
            needs.update(check_display.draw(layout, results, page == toolkit.getPageCount()))
        if not needs:
            return
        for measure_id, more in needs.items():
            lines[measure_id] = lines.get(measure_id, 0) + more
        relayout(check_display.with_room(base, lines, bottom_staff))


def _make_room_for_codes(toolkit, relayout, index, ties, annotations, view, role) -> list[PageLayout] | None:
    if not any(isinstance(a, VoiceLeading) and (a.kind == "ring" and a.label or a.kind == "arrow" and "R" in (a.label or ""))
               for a in annotations.annotations):
        return None
    base = toolkit.getMEI()
    lines: dict[tuple[str, str, int, str], int] = {}
    asked: dict[tuple[str, str, int, str], int] = {}
    gaps: dict[tuple[str, int], tuple[str, str, int, str]] = {}
    for _ in range(7):
        needs: dict[tuple[str, str, int, str], int] = {}
        layouts = []
        for page in range(1, toolkit.getPageCount() + 1):
            layout = PageLayout(shorten_ties(toolkit.renderToSVG(page), ties), index)
            layout.draw(annotations, view, role)
            layouts.append(layout)
            for event, place, short, first in layout.code_room:
                measure = index.measure(event.measure)
                segment = next(segment for segment in measure.segments if segment.id == event.segment)
                unit = int(measure.meter.split("/")[1]) if measure.meter else 4
                need = (segment.id, f"{float(1 + (event.onset - segment.start) * unit / 4):g}", event.staff, place)
                need = gaps.setdefault((segment.id, event.staff if place == "below" else event.staff - 1), need)
                more = short if need in lines else first
                needs[need] = max(needs.get(need, 0), more)
        grown = {need: more for need, more in needs.items() if asked.get(need, 0) < 4}
        given_up = [need for need in needs if asked.get(need, 0) == 4]
        if not grown and not given_up:
            return layouts
        for need, more in grown.items():
            lines[need] = lines.get(need, 0) + more
            asked[need] = asked.get(need, 0) + 1
        for need in given_up:
            lines.pop(need, None)
            asked[need] = 5
        mei = base
        for (measure_id, tstamp, staff, place), count in lines.items():
            end = mei.index("</measure>", mei.index(f'xml:id="{measure_id}"'))
            room = f'<dir staff="{staff}" tstamp="{tstamp}" place="{place}" type="analysis-room">-{"<lb/>-" * (count - 1)}</dir>'
            mei = mei[:end] + room + mei[end:]
        relayout(mei)
    return None


def _piano_version(score: bytes, annotations: AnnotationList, measures: tuple[int, int] | None) -> tuple[bytes, AnnotationList]:
    from engine import piano as piano_reduction

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
            staff = None
        moved[id(ref)] = ref.model_copy(update={"staff": staff, "pitch": event.pitch})
    pointed = []
    for annotation in annotations.annotations:
        if isinstance(annotation, NonChordTone):
            annotation = annotation.model_copy(update={"note": moved[id(annotation.note)]})
        elif isinstance(annotation, VoiceLeading):
            annotation = annotation.model_copy(update={"from_note": moved[id(annotation.from_note)], "to_note": moved.get(id(annotation.to_note))})
        elif isinstance(annotation, Region) and annotation.staff:
            annotation = annotation.model_copy(update={"staff": None})
        pointed.append(annotation)
    return reduced, annotations.model_copy(update={"annotations": pointed})


def _note_refs(annotation) -> list[NoteRef]:
    if isinstance(annotation, NonChordTone):
        return [annotation.note]
    if isinstance(annotation, VoiceLeading):
        return [annotation.from_note, *([annotation.to_note] if annotation.to_note else [])]
    return []


DIR = re.compile(r'<g id="([^"]+)" class="dir">(.*?)</text>', re.S)
RECT = r'class="{}{}bounding-box"[^>]*>\s*<rect x="([-\d.]+)" y="([-\d.]+)" height="([-\d.]+)" width="([-\d.]+)"'


def _move_text_off_stems(toolkit, relayout) -> None:
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
    mei = toolkit.getMEI()
    bottom_staff = max(int(n) for n in re.findall(r'<staffDef\b[^>]*?\bn="(\d+)"', mei))
    added: dict[str, list[str]] = {}
    key = None
    harmonies = sorted((a for a in annotations.annotations if isinstance(a, Harmony)),
                       key=lambda h: (index.measure(h.at.measure).index, h.at.beat))
    for harmony in harmonies:
        key = harmony.key or key
        label = _widest_label(harmony.label, key)
        measure = index.measure(harmony.at.measure)
        offset = measure.offset_of(harmony.at.beat)
        segment = measure.segment_at(offset)
        unit = int(measure.meter.split("/")[1]) if measure.meter else 4
        tstamp = 1 + (offset - segment.start) * unit / 4
        added.setdefault(segment.id, []).append(
            f'<harm staff="{bottom_staff}" tstamp="{float(tstamp):g}" place="below">{escape(label)}\u00a0\u00a0</harm>'
        )
    if not added:
        return
    for measure_id, harms in added.items():
        end = mei.index("</measure>", mei.index(f'xml:id="{measure_id}"'))
        mei = mei[:end] + "".join(harms) + mei[end:]
    toolkit.loadData(mei)


def _widest_label(label: str, key: str | None) -> str:
    widest, widest_width = label, 0.0
    for style in ("current", "abrsm", "figured_bass"):
        try:
            chunks, total = notation.numeral(label, key, style, 440)
        except ValueError:
            continue
        if total > widest_width:
            widest, widest_width = "".join(chunk.text for chunk in chunks), total
    return widest


def _reserve_staff_bracket_room(toolkit, index: ScoreIndex, annotations: AnnotationList) -> None:
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
    if toolkit.getPageCount() != 1:
        return
    systems = PageLayout(toolkit.renderToSVG(1), index).systems
    if len(systems) < 2:
        return
    line = max(system.right - system.left for system in systems)
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
            good.add(start.measure if start.beat < 1.5 else start.measure + 1)
        elif isinstance(annotation, Cadence):
            good.add(annotation.at.measure + 1)
            if annotation.at.beat < 2:
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
    toolkit.setOptions({"breaks": "smart", "breaksSmartSb": 0.3, "minLastJustification": 0})
    toolkit.loadData(mei)
    if measures:
        toolkit.select({"measureRange": index.measure_range(*measures)})
    toolkit.redoLayout()


def _breaks(widths: list[float], line: float, penalty: list[float], opening: float = 0.0) -> list[int]:
    count = len(widths)
    best: list[tuple[float, int]] = [(0.0, -1)] + [(math.inf, -1)] * count
    for end in range(1, count + 1):
        for begin in range(end - 1, -1, -1):
            width = sum(widths[begin:end]) + (opening if begin else 0.0)
            if width > line and end - begin > 1:
                break
            fill = width / line
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
