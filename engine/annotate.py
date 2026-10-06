"""Render a score with an annotation list drawn on it."""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

from engine.annotations import AnnotationList, Cadence, Callout, Harmony, NonChordTone, Phrase, Region, VoiceLeading
from engine.overlay import PageLayout
from engine.render import Engraving, load_toolkit
from engine.score import PositionError, ScoreIndex

# A page is an annotated excerpt for study, never a stand-in for the whole score (users send copyrighted music).
MAX_BARS = 32

# Room for the rows of labels under each system and the brackets above it.
ANNOTATED_OPTIONS = {
    "svgBoundingBoxes": True,
    "adjustPageHeight": True,
    "spacingSystem": 26,
    "pageMarginTop": 230,  # two stacked brackets with labels fit above the first system
    "pageMarginBottom": 260,
}


class AnnotationError(ValueError):
    """One or more annotations point at places that are not in the score."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def check(annotations: AnnotationList, index: ScoreIndex) -> None:
    """Resolve every position against the score and report all problems at once."""
    problems = []
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
) -> Engraving:
    """Engrave `measures` (printed numbers, inclusive; the whole score by default, if it is short enough) with annotations drawn on."""
    toolkit = load_toolkit(score, ANNOTATED_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    check(annotations, index)
    first, last = measures or (index.measures[0].number, index.measures[-1].number)
    bars = sum(1 for measure in index.measures if first <= measure.number <= last and measure.number > 0)
    if bars > MAX_BARS:
        raise PositionError(
            f"A page can show at most {MAX_BARS} bars and measures {first}-{last} have {bars}. "
            f"Draw the analysis passage by passage, {MAX_BARS} bars or fewer each."
        )
    _reserve_numeral_room(toolkit, index, annotations)
    if measures:
        toolkit.setOptions({"pageHeight": 60000})  # an excerpt is one tall image
        toolkit.select({"measureRange": index.measure_range(*measures)})
        toolkit.redoLayout()
    pages = []
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(toolkit.renderToSVG(page), index)
        layout.draw(annotations, view, role)
        pages.append(layout.to_svg())
    return Engraving(pages)


def _reserve_numeral_room(toolkit, index: ScoreIndex, annotations: AnnotationList) -> None:
    """Verovio spaces bars by their notes alone, so a bar with several chords squeezes its numerals together.
    A hidden chord symbol per numeral makes it widen such bars; the overlay removes them before drawing."""
    mei = toolkit.getMEI()
    bottom_staff = max(int(n) for n in re.findall(r'<staffDef\b[^>]*?\bn="(\d+)"', mei))
    added: dict[str, list[str]] = {}
    for harmony in annotations.annotations:
        if not isinstance(harmony, Harmony):
            continue
        measure = index.measure(harmony.at.measure)
        offset = measure.offset_of(harmony.at.beat)
        segment = measure.segment_at(offset)
        unit = int(measure.meter.split("/")[1]) if measure.meter else 4
        tstamp = 1 + (offset - segment.start) * unit / 4
        # Verovio sets chord symbols smaller than our numerals, hence the padding.
        added.setdefault(segment.id, []).append(
            f'<harm staff="{bottom_staff}" tstamp="{float(tstamp):g}" place="below">{escape(harmony.label)}\u00a0\u00a0</harm>'
        )
    if not added:
        return
    for measure_id, harms in added.items():
        # MEI measures never nest, so the first closing tag after the opening one is this measure's.
        end = mei.index("</measure>", mei.index(f'xml:id="{measure_id}"'))
        mei = mei[:end] + "".join(harms) + mei[end:]
    toolkit.loadData(mei)
