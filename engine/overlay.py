"""Draw an annotation list onto one page of Verovio's SVG.

Verovio is asked for bounding boxes, so every drawn element has a known place.
The overlay reads those boxes, adds its own SVG elements in the same coordinate
system, and removes the helper boxes again before the page is rasterised.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

from engine import notation, text
from engine.annotations import FAULT_ARROW_LABELS, AnnotationList, Cadence, Callout, Harmony, NonChordTone, Phrase, Region, VoiceLeading
from engine.score import TOLERANCE, Event, PositionError, ScoreIndex

SVG_NS = "http://www.w3.org/2000/svg"
S = f"{{{SVG_NS}}}"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# As labelled in MT21C's function brackets.
FUNCTION_NAMES = {"T": "tonic", "PD": "pre-dom.", "D": "dominant"}
INK = "#1a1a1a"
MUTED = "#555555"
ERROR = "#D50000"  # faults only (part-writing findings)
ARROW = "#AA3377"  # analysis arrows the model draws (a resolution, a tendency): not faults

# Lengths are in Verovio's SVG units; a staff space is 180.
NUMERAL_SIZE = 440
LABEL_SIZE = 330  # the legibility floor: about 11 px at chat size
SMALL_SIZE = 280  # the check page's notes; raising it to 330 (the floor) is that page's change, its layout overflows the line at 330
LINE = 26
# Textbook abbreviations (Open Music Theory) for the labels the model may write; keys are upper case, short and long forms.
NCT_NAMES = {
    "P": "PT", "PT": "PT", "PASSING": "PT", "N": "NT", "NT": "NT", "NEIGHBOR": "NT", "NEIGHBOUR": "NT",
    "S": "SUS", "SUS": "SUS", "SUSPENSION": "SUS", "A": "APP", "APP": "APP", "APPOGGIATURA": "APP",
    "E": "ET", "ET": "ET", "ESCAPE": "ET", "R": "RET", "RET": "RET", "RETARDATION": "RET",
    "ANT": "ANT", "ANTICIPATION": "ANT", "PED": "PED", "PEDAL": "PED",
}
FUNCTION_SIZE = 400  # about the numeral's size, as MT21C sets its function words
PHRASE_LETTER_SIZE = NUMERAL_SIZE  # a phrase letter ("a", "a′") is read at the numeral's size
LABEL_PAD = 55  # clear space kept around every overlay label

CONTAINERS = {"system", "measure", "staff", "layer", "chord", "beam", "tuplet", "section", "score"}
CURVES = {"slur", "tie", "phrase"}


class NotOnPage(Exception):
    """The position is valid but belongs to another page or lies outside the excerpt."""


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class MeasureGeometry:
    id: str
    system: int
    staves: list[Box] = field(default_factory=list)
    lines: list[Box] = field(default_factory=list)  # each staff's five lines, without the ledger lines and clefs its box takes in
    numbered: dict[int, Box] = field(default_factory=dict)  # staff number -> its lines, for the staves drawn

    @property
    def x0(self) -> float:
        return min(box.x for box in self.staves)

    @property
    def x1(self) -> float:
        return max(box.right for box in self.staves)


@dataclass
class System:
    index: int
    measures: list[MeasureGeometry] = field(default_factory=list)
    content: list[Box] = field(default_factory=list)
    words: list[Box] = field(default_factory=list)  # lyrics and other score text, estimated; Verovio gives no box for them

    @property
    def left(self) -> float:
        return self.measures[0].x0

    @property
    def right(self) -> float:
        return self.measures[-1].x1

    @property
    def staff_top(self) -> float:
        return min(box.y for measure in self.measures for box in measure.staves)

    @property
    def staff_bottom(self) -> float:
        return max(box.bottom for measure in self.measures for box in measure.staves)

    def top(self, x0: float | None = None, x1: float | None = None) -> float:
        """Highest drawn point between x0 and x1 (the whole system by default)."""
        return min(box.y for box in self._between(x0, x1))

    def bottom(self, x0: float | None = None, x1: float | None = None) -> float:
        return max(box.bottom for box in self._between(x0, x1))

    def _between(self, x0: float | None, x1: float | None) -> list[Box]:
        staves = [box for measure in self.measures for box in measure.staves]
        if x0 is None or x1 is None:
            return self.content + staves
        return [box for box in self.content if box.right >= x0 and box.x <= x1] + staves


@dataclass
class Segment:
    """The part of a range that lies on one system."""

    system: System
    x0: float
    x1: float
    starts: bool  # False when the range continues from the previous system
    ends: bool  # False when it continues onto the next


class PageLayout:
    def __init__(self, svg: str, index: ScoreIndex):
        self.index = index
        self.root = ET.fromstring(svg)
        self.canvas = next(g for g in self.root.iter(f"{S}g") if g.get("class") == "page-margin")
        self.boxes: dict[str, Box] = {}
        self.measures: dict[str, MeasureGeometry] = {}
        self.systems: list[System] = []
        self.harmony_labels: list[tuple[str, Box]] = []
        # Each numeral as drawn, by (measure, beat): system, root-letter centre, label extent (x0, x1) and
        # the lowest point of its figures. Cadence boxes and function brackets hang from these.
        self.numerals: dict[tuple[int, float], tuple[int, float, float, float, float]] = {}
        # The same numerals in score order: ((measure index, beat), function or None, system, centre, x0, x1, low).
        self.numeral_seq: list[tuple] = []
        self._callout_x: dict[int, list[float]] = {}
        self.cadence_bottom: dict[int, float] = {}  # lowest cadence box on each system
        self.numeral_tops: dict[int, float] = {}  # the top of each system's numeral row
        self.numeral_rows: dict[int, float] = {}  # the lowest figure on each system's numeral row
        self.below_numerals: dict[int, int] = {}  # how many boxes a system held when its numerals were done
        self._words: list[tuple[tuple[str, Box], System]] = []  # fault words drawn so far
        self._remove("fing")  # fingering is clutter on an analysis page
        self._remove("harm")  # hidden placeholders that made Verovio leave room for the numerals (annotate.py)
        self._remove("analysis-room")  # and for brackets drawn at one staff
        for group in self.canvas.iter(f"{S}g"):
            if "system" in group.get("class", "").split() and "bounding-box" not in group.get("class", ""):
                system = System(len(self.systems))
                self._visit(group, system, None)
                if system.measures:
                    self.systems.append(system)
        self._strip_bounding_boxes()
        self._drop_foreign_boxes()
        self.under = ET.Element(f"{S}g", {"class": "analysis-under"})
        self.over = ET.SubElement(self.canvas, f"{S}g", {"class": "analysis-over"})
        self.canvas.insert(0, self.under)
        self._last_measure = max(
            (measure for measure in index.measures if any(segment.id in self.measures for segment in measure.segments)),
            key=lambda measure: measure.index,
        )

    # ---- reading Verovio's geometry -------------------------------------------------

    def _visit(self, group: ET.Element, system: System, measure: MeasureGeometry | None) -> None:
        classes = group.get("class", "").split()
        if "bounding-box" in classes:
            return
        box = self._own_box(group)
        if box and group.get("id"):
            self.boxes[group.get("id")] = box
        if CURVES & set(classes):
            # A slur's box covers everything under its arc; follow the curve itself instead.
            system.content.extend(self._curve_boxes(group) or ([box] if box else []))
        elif box and not CONTAINERS & set(classes):
            system.content.append(box)
        if "measure" in classes:
            measure = MeasureGeometry(group.get("id"), system.index)
            system.measures.append(measure)
            self.measures[measure.id] = measure
        elif "staff" in classes and measure and box:
            measure.staves.append(box)
            ys = [float(y) for path in group.findall(f"{S}path") for y in re.findall(r"^M[-\d.]+ ([-\d.]+) L", path.get("d", ""))]
            lines = Box(box.x, min(ys), box.width, max(ys) - min(ys)) if ys else box
            measure.lines.append(lines)
            if group.get("data-n", "").isdigit():
                measure.numbered[int(group.get("data-n"))] = lines
        for child in group:
            if child.tag == f"{S}g":
                self._visit(child, system, measure)
            elif child.tag == f"{S}text":  # text keeps its boxes inside its tspans
                boxes = list(filter(None, (self._rect_box(rect) for rect in child.iter(f"{S}rect"))))
                system.content.extend(boxes) if boxes else system.words.extend(self._text_boxes(child))

    @staticmethod
    def _text_boxes(element: ET.Element) -> list[Box]:
        """Verovio reports no box for lyrics and other score text, so estimate one from the font metrics."""
        boxes = []
        for span in element.iter(f"{S}tspan"):
            string, size = span.text or "", span.get("font-size", "")
            if not string.strip() or not size.endswith("px"):
                continue
            size = float(size[:-2])
            width = text.width(string, size)
            x, y = float(element.get("x", "0")), float(element.get("y", "0"))
            anchor = element.get("text-anchor", "start")
            x -= width if anchor == "end" else width / 2 if anchor == "middle" else 0
            boxes.append(Box(x, y - size * 0.8, width, size * 1.05))
        return boxes

    def _own_box(self, group: ET.Element) -> Box | None:
        for child in group:
            if child.tag == f"{S}g" and "bounding-box" in child.get("class", ""):
                rect = child.find(f"{S}rect")
                return self._rect_box(rect) if rect is not None else None
        return None

    @staticmethod
    def _curve_boxes(group: ET.Element, steps: int = 10) -> list[Box]:
        """Small boxes along the cubic Béziers of a slur or tie."""
        boxes: list[Box] = []
        for path in group.iter(f"{S}path"):
            tokens = re.findall(r"[MC]|-?\d+(?:\.\d+)?", path.get("d", ""))
            numbers: list[float] = []
            start = None
            command = None
            for token in tokens + ["M"]:
                if token in ("M", "C"):
                    command, numbers = token, []
                    continue
                numbers.append(float(token))
                if command == "M" and len(numbers) == 2:
                    start = (numbers[0], numbers[1])
                elif command == "C" and len(numbers) == 6 and start:
                    (x0, y0), (x1, y1, x2, y2, x3, y3) = start, numbers
                    points = []
                    for step in range(steps + 1):
                        t = step / steps
                        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t**2 * (1 - t), t**3
                        points.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))
                    for (xa, ya), (xb, yb) in zip(points, points[1:]):
                        boxes.append(Box(min(xa, xb), min(ya, yb), abs(xb - xa), abs(yb - ya)))
                    start, numbers = (x3, y3), []
        return boxes

    @staticmethod
    def _rect_box(rect: ET.Element) -> Box | None:
        box = Box(*(float(rect.get(name, "0")) for name in ("x", "y", "width", "height")))
        return box if box.width > 0 or box.height > 0 else None

    def _strip_bounding_boxes(self) -> None:
        for parent in self.root.iter():
            for child in list(parent):
                if "bounding-box" in child.get("class", ""):
                    parent.remove(child)

    def _remove(self, css_class: str) -> None:
        for parent in self.canvas.iter():
            for child in list(parent):
                if css_class in child.get("class", "").split():
                    parent.remove(child)

    def _drop_foreign_boxes(self) -> None:
        """A slur that crosses a system break reports the box of its second half under the first system."""
        for system in self.systems:
            upper = lower = None
            if system.index > 0:
                upper = (self.systems[system.index - 1].staff_bottom + system.staff_top) / 2
            if system.index + 1 < len(self.systems):
                lower = (system.staff_bottom + self.systems[system.index + 1].staff_top) / 2
            system.content = [
                box
                for box in system.content
                if (upper is None or box.bottom > upper) and (lower is None or box.y < lower)
            ]

    def _is_free(self, system: System, box: Box) -> bool:
        return not any(
            other.x < box.right and other.right > box.x and other.y < box.bottom and other.bottom > box.y
            for other in self._obstacles(system)
        )

    def _overlap(self, system: System, box: Box) -> float:
        return sum(
            max(0.0, min(box.right, other.right) - max(box.x, other.x)) * max(0.0, min(box.bottom, other.bottom) - max(box.y, other.y))
            for other in self._obstacles(system)
        )

    @staticmethod
    def _obstacles(system: System) -> list[Box]:
        # A label between the staff lines reads as part of the music, so the staves count as taken.
        return system.content + [box for measure in system.measures for box in measure.lines]

    @staticmethod
    def _reserve(system: System, box: Box, pad: float = LABEL_PAD) -> None:
        """Mark the box, plus clear space around it, as taken so later elements keep away."""
        system.content.append(Box(box.x - pad, box.y - pad, box.width + 2 * pad, box.height + 2 * pad))

    def _reserve_line(self, system: System, x0: float, y0: float, x1: float, y1: float, steps: int = 8) -> None:
        for step in range(steps):
            xa, xb = x0 + (x1 - x0) * step / steps, x0 + (x1 - x0) * (step + 1) / steps
            ya, yb = y0 + (y1 - y0) * step / steps, y0 + (y1 - y0) * (step + 1) / steps
            self._reserve(system, Box(min(xa, xb), min(ya, yb), abs(xb - xa), abs(yb - ya)), pad=30)

    def _place_label(self, system: System, anchor: Box, width: float, height: float, below: bool = False,
                     limit: float | None = None) -> tuple[float, float]:
        """Centre for a label near `anchor`: the closest spot whose padded box touches nothing drawn."""

        def above(distance: float) -> tuple[float, float]:
            return anchor.cx, anchor.y - distance - height / 2

        def under(distance: float) -> tuple[float, float]:
            return anchor.cx, anchor.bottom + distance + height / 2

        near, far = (under, above) if below else (above, under)
        left = (anchor.x - 90 - width / 2, anchor.cy)
        right = (anchor.right + 90 + width / 2, anchor.cy)
        spots = [near(90), near(200), left, right, near(330), far(90), far(200), near(480), near(650), far(330), near(850)]
        # Sideways shifts for when the space straight above or below is taken (a chord, a slur, another label).
        spots += [(cx + shift, cy) for cx, cy in spots[:2] + spots[4:7] for shift in (-width - 120, width + 120)]
        spots += [near(1050), far(480), far(650)]

        def padded(spot: tuple[float, float]) -> Box:
            cx, cy = spot
            return Box(cx - width / 2 - LABEL_PAD, cy - height / 2 - LABEL_PAD, width + 2 * LABEL_PAD, height + 2 * LABEL_PAD)

        if limit is not None:  # nothing may sit lower than `limit` (the numeral row)
            kept = [spot for spot in spots if padded(spot).bottom <= limit]
            spots = kept or spots
        for spot in spots:
            if self._is_free(system, padded(spot)):
                return spot
        # Nowhere is clear: take the spot that covers the least of what is already drawn.
        return min(spots, key=lambda spot: self._overlap(system, padded(spot)))

    # ---- musical position -> page position --------------------------------------------

    def x_at(self, measure_number: int, offset: Fraction) -> tuple[System, float]:
        measure = self.index.measure(measure_number)
        segment = measure.segment_at(offset)  # a bar split around a repeat is engraved as two measures
        geometry = self.measures.get(segment.id)
        if geometry is None:
            raise NotOnPage
        points: dict[Fraction, float] = {}
        end = Fraction(0)
        for event in measure.events:
            box = self.boxes.get(event.id)
            if box is None or event.grace or event.segment != segment.id:
                continue
            points[event.onset] = min(points.get(event.onset, box.x), box.x)
            end = max(end, event.onset + event.duration)
        system = self.systems[geometry.system]
        if not points:
            return system, geometry.x0
        onsets = sorted(points)
        if offset <= onsets[0]:
            return system, points[onsets[0]]
        ladder = [(onset, points[onset]) for onset in onsets] + [(max(end, onsets[-1] + TOLERANCE), geometry.x1)]
        for (onset_a, x_a), (onset_b, x_b) in zip(ladder, ladder[1:]):
            if abs(offset - onset_a) <= TOLERANCE:
                return system, x_a
            if offset < onset_b:
                return system, x_a + (x_b - x_a) * float((offset - onset_a) / (onset_b - onset_a))
        return system, geometry.x1

    def x_of(self, position) -> tuple[System, float]:
        return self.x_at(position.measure, self.index.measure(position.measure).offset_of(position.beat))

    def note_box(self, ref) -> tuple[System, Box, Event]:
        event = self.index.find_note(ref.measure, ref.beat, ref.staff, ref.pitch)
        if event.id not in self.boxes or event.segment not in self.measures:
            raise NotOnPage
        return self.systems[self.measures[event.segment].system], self.boxes[event.id], event

    def _content_left(self, system: System) -> float:
        measure, segment = self.index.locate_segment(system.measures[0].id)
        return self.x_at(measure.number, segment.start)[1] - 90

    def segments(self, start, end, gap: float = 70) -> list[Segment]:
        """Split a range into one piece per system. `end` is a position, or a RangeEnd without a beat."""
        try:
            first_system, x0 = self.x_of(start)
            starts = True
        except NotOnPage:
            if self.index.measure(start.measure).index > self._last_measure.index:
                raise
            first_system, x0, starts = self.systems[0], self._content_left(self.systems[0]), False
        try:
            if getattr(end, "beat", None) is None:
                geometry = self.measures.get(self.index.measure(end.measure).segments[-1].id)
                if geometry is None:
                    raise NotOnPage
                last_system, x1 = self.systems[geometry.system], geometry.x1 - gap
            else:
                last_system, x1 = self.x_of(end)
                x1 -= gap
                if x1 - self._content_left(last_system) < 250 and last_system.index > first_system.index:
                    # The range stops at the very start of a system: end it on the previous one instead.
                    last_system = self.systems[last_system.index - 1]
                    x1 = last_system.right - gap
            ends = True
        except NotOnPage:
            if self.index.measure(end.measure).last_index < self.index.locate_segment(self.systems[0].measures[0].id)[1].index:
                raise
            last_system, x1, ends = self.systems[-1], self.systems[-1].right, False
        pieces = []
        for system in self.systems[first_system.index : last_system.index + 1]:
            is_first, is_last = system is first_system, system is last_system
            pieces.append(
                Segment(
                    system,
                    x0 if is_first else self._content_left(system),
                    x1 if is_last else system.right,
                    starts and is_first,
                    ends and is_last,
                )
            )
        return [piece for piece in pieces if piece.x1 > piece.x0]

    # ---- drawing primitives -----------------------------------------------------------

    def _add(self, tag: str, parent: ET.Element | None = None, **attributes) -> ET.Element:
        names = {key.replace("_", "-"): str(value) for key, value in attributes.items()}
        if "stroke" in names:
            # Verovio's stylesheet sets stroke:currentColor on shapes, which beats a stroke attribute but not a style.
            names["style"] = f"stroke:{names['stroke']};" + names.get("style", "")
        return ET.SubElement(self.over if parent is None else parent, f"{S}{tag}", names)

    def _text(self, x, y, string, size, *, bold=False, italic=False, fill=INK, anchor="start", halo=False) -> Box:
        """Draw text; `halo` adds a white outline so it stays legible over staff lines and colour bands."""
        total = text.width(string, size, bold)
        left = x - (total if anchor == "end" else total / 2 if anchor == "middle" else 0)
        for outline in ([True, False] if halo else [False]):
            cursor = left
            for run, family in text.runs(string):
                attributes = dict(
                    x=round(cursor),
                    y=round(y),
                    font_family=family,
                    font_size=f"{round(size)}px",
                    fill="#ffffff" if outline else fill,
                    font_weight="bold" if bold else "normal",
                    font_style="italic" if italic and family == text.MAIN else "normal",
                )
                if outline:
                    attributes.update(stroke="#ffffff", stroke_width=round(size * 0.3), stroke_linejoin="round")
                self._add("text", **attributes).text = run
                cursor += text.width(run, size, bold)
        return Box(left, y - size * 0.75, total, size)

    # ---- annotation kinds -------------------------------------------------------------

    def draw(self, annotations: AnnotationList, view: str = "all", role: str | None = None) -> None:
        def shown(kind: str, cls: type) -> list:
            return [a for a in annotations.annotations if isinstance(a, cls) and annotations.visible(kind, a, view, role)]

        harmonies = sorted(shown("harmony", Harmony), key=lambda h: (self.index.measure(h.at.measure).index, h.at.beat))
        if annotations.style != "current":
            # A hidden key declaration still governs the chords visible in this view.
            active = None
            keys = {}
            for harmony in sorted((a for a in annotations.annotations if isinstance(a, Harmony)),
                                  key=lambda h: (self.index.measure(h.at.measure).index, h.at.beat)):
                active = harmony.key or active
                keys[id(harmony)] = active
            harmonies = [h.model_copy(update={"key": keys[id(h)]}) for h in harmonies]
        banded = {id(h) for h in harmonies if annotations.visible("function", h, view, role)}
        self._draw_harmonies(harmonies, annotations.style, banded)
        for cadence in shown("cadence", Cadence):  # directly under their numeral; the function row goes below
            self._draw_cadence(cadence)
        self._draw_function_brackets()
        self._draw_ncts(shown("nct", NonChordTone))
        self._draw_voice_marks(shown("voice_leading", VoiceLeading))
        for callout in shown("callout", Callout):
            self._draw_callout(callout)
        for region in shown("region", Region):
            self._draw_phrase(region, dashed=True)
        for phrase in shown("phrase", Phrase):
            self._draw_phrase(phrase)

    def _draw_function_brackets(self) -> None:
        """MT21C's function brackets: a thin black bracket under a run of numerals of one function, the whole
        music of the run: from its first numeral's left edge to just before the next numeral (or the system end).
        The full word sits centred beneath; on a later system the run's piece is named "(pre-dom.)". Words and
        abbreviations never mix: a system whose pieces cannot all hold their words uses T, PD, D throughout.
        Textbooks print no colour and no legend. Only chords that carry `function` get a bracket."""
        sequence = self.numeral_seq
        pieces: dict[int, list[tuple[float, float, str, bool]]] = {}  # system -> (x0, x1, function, continuation)
        position = 0
        while position < len(sequence):
            function = sequence[position][1]
            following = position + 1
            while following < len(sequence) and function and sequence[following][1] == function:
                following += 1
            if function:
                run = [entry[2:] for entry in sequence[position:following]]
                after = sequence[following][2:] if following < len(sequence) else None
                for number, system_index in enumerate(dict.fromkeys(entry[0] for entry in run)):
                    entries = [entry for entry in run if entry[0] == system_index]
                    x0 = entries[0][2]
                    if after and after[0] == system_index and entries[-1] is run[-1]:
                        x1 = after[2] - 60
                    else:
                        x1 = self.systems[system_index].right - 30
                    pieces.setdefault(system_index, []).append((x0, max(x1, entries[-1][3]), function, number > 0))
            position = following
        for system_index, row in pieces.items():
            system = self.systems[system_index]
            words = all(text.width(FUNCTION_NAMES[f], FUNCTION_SIZE) + 2 * LABEL_PAD <= x1 - x0 for x0, x1, f, _ in row)
            hook = NUMERAL_SIZE * 0.2
            top = max(self.numeral_rows[system_index] + NUMERAL_SIZE * 0.25, self.cadence_bottom.get(system_index, -1e9) + 70)
            y = top + hook
            for x0, x1, function, continued in row:
                name = FUNCTION_NAMES[function] if words else function
                name = f"({name})" if continued else name
                self._add("path", d=f"M{round(x0)},{round(y - hook)} L{round(x0)},{round(y)} L{round(x1)},{round(y)} L{round(x1)},{round(y - hook)}",
                          fill="none", stroke=INK, stroke_width=LINE, stroke_linejoin="round")
                label = self._text((x0 + x1) / 2, y + NUMERAL_SIZE * 0.2 + FUNCTION_SIZE * 0.68, name, FUNCTION_SIZE, anchor="middle")
                system.content.append(Box(x0, y - hook, x1 - x0, label.bottom - (y - hook)))

    def _bass_centre(self, position, x: float) -> float:
        """Centre of the bass notehead at a position: the point a numeral's root letters sit under."""
        measure = self.index.measure(position.measure)
        offset = measure.offset_of(position.beat)
        segment = measure.segment_at(offset).id
        bass = [e for e in measure.events
                if e.segment == segment and not e.grace and e.pitch and abs(e.onset - offset) <= TOLERANCE and e.id in self.boxes]
        if not bass:
            return x + 100  # between notes there is no notehead; about half of one
        lowest = max(bass, key=lambda e: (e.staff, self.boxes[e.id].y))
        return self.boxes[lowest.id].cx

    def _draw_harmonies(self, harmonies: list[Harmony], style: str = "current", banded: set[int] = frozenset()) -> None:
        by_system: dict[int, list[tuple[float, Harmony]]] = {}
        self.numeral_seq = []
        key_at_start: dict[int, str] = {}
        key = None
        for harmony in harmonies:
            key = harmony.key or key
            try:
                system, x = self.x_of(harmony.at)
            except NotOnPage:
                continue
            by_system.setdefault(system.index, []).append((self._bass_centre(harmony.at, x), harmony))
            key_at_start.setdefault(system.index, key)
        gap = NUMERAL_SIZE * 0.3  # at least a letter's width between labels
        previous = None  # the key in force at the end of the last line drawn
        for system_index, labels in by_system.items():
            system = self.systems[system_index]
            # Tall figure stacks (three rows in figured-bass style) reach above the capitals; the row sits lower for them.
            rise, row_key = NUMERAL_SIZE * 0.75, key_at_start[system_index]
            for _, harmony in labels:
                row_key = harmony.key or row_key
                rise = max([rise] + [chunk.size * 0.75 - chunk.dy for chunk in notation.numeral(harmony.label, row_key, style, NUMERAL_SIZE)[0]])
            baseline = system.bottom() + 170 + rise
            cursor = 0.0
            # A score names its key once; a later line repeats it only when the key has changed.
            if key_at_start[system_index] and key_at_start[system_index] != previous:
                label = text.pretty_key(key_at_start[system_index]) + ":"
                first_centre, first = labels[0]
                first_x = first_centre - text.root_centre(notation.numeral(first.label, first.key or key_at_start[system_index], style, NUMERAL_SIZE)[0])
                # Right-aligned to sit just before the first numeral, but never nearer the system's edge than the clef's room.
                left = max(system.left + 80, first_x - 0.4 * NUMERAL_SIZE - text.width(label, NUMERAL_SIZE))
                box = self._text(left, baseline, label, NUMERAL_SIZE)
                self.harmony_labels.append((label, box))
                cursor = box.right + 0.4 * NUMERAL_SIZE
            key = key_at_start[system_index]
            deepest = 0.0
            drawn: list[tuple[Harmony, float, float, float, float]] = []
            for position, (centre, harmony) in enumerate(labels):
                chunks, total = notation.numeral(harmony.label, harmony.key or key, style, NUMERAL_SIZE)
                x = centre - text.root_centre(chunks)
                # Chat models sometimes repeat the key on every chord; only a change is written in line.
                # It hangs to the left of its numeral, so the numeral stays under its chord.
                if harmony.key and harmony.key != key and position:
                    name = text.pretty_key(harmony.key) + ":"
                    room = text.width(name, NUMERAL_SIZE) + gap
                    x = max(x, cursor + room)
                    box = self._text(x - room, baseline, name, NUMERAL_SIZE)
                    self.harmony_labels.append((harmony.key + ":", box))
                else:
                    x = max(x, cursor)
                key = harmony.key or key
                boxes = [self._text(x + chunk.dx, baseline + chunk.dy, chunk.text, chunk.size, bold=chunk.bold) for chunk in chunks]
                if boxes:
                    top = min(box.y for box in boxes)
                    bottom = max(box.bottom for box in boxes)
                    self.harmony_labels.append((harmony.label, Box(x, top, total, bottom - top)))
                low = max(0.0, max(chunk.dy for chunk in chunks))
                deepest = max(deepest, low)
                entry = (system_index, x + text.root_centre(chunks), x, x + total, baseline + low)
                self.numerals[(harmony.at.measure, harmony.at.beat)] = entry
                self.numeral_seq.append(((self.index.measure(harmony.at.measure).index, harmony.at.beat),
                                         harmony.function if id(harmony) in banded else None, *entry))
                cursor = x + total + gap
            previous = key
            self.numeral_rows[system_index] = baseline + deepest
            self.numeral_tops[system_index] = baseline - rise
            system.content.append(Box(system.left, baseline - rise - NUMERAL_SIZE * 0.05, system.right - system.left,
                                      rise + NUMERAL_SIZE * 0.05 + max(NUMERAL_SIZE * 0.25, deepest + NUMERAL_SIZE * 0.1)))
            if style != "current":
                system.content.extend(box for _, box in self.harmony_labels if baseline - NUMERAL_SIZE < box.y < baseline + NUMERAL_SIZE)
            self.below_numerals[system_index] = len(system.content)

    def _draw_cadence(self, cadence: Cadence) -> None:
        """FFF's cadence label: a small square box, regular weight, centred under the arrival numeral."""
        try:
            system, x = self.x_of(cadence.at)
        except NotOnPage:
            return
        width = text.width(cadence.label, LABEL_SIZE) + 2 * NUMERAL_SIZE * 0.2
        height = LABEL_SIZE * 0.66 + 2 * NUMERAL_SIZE * 0.12  # capital height plus padding
        # The numeral in force at the cadence beat, not only one written exactly there (a cadence at beat 2 over a
        # chord that began on beat 1 still hangs under that chord).
        moment = (self.index.measure(cadence.at.measure).index, cadence.at.beat)
        before = [item[2:] for item in self.numeral_seq if item[0][0] < moment[0] or (item[0][0] == moment[0] and item[0][1] <= moment[1] + 1e-6)]
        entry = before[-1] if before else None
        if entry and entry[0] == system.index:
            centre = entry[1]
            top = entry[4] + NUMERAL_SIZE * 0.25 + LABEL_PAD  # clear of the numeral's own box
            # Whatever else hangs under the numerals here (function brackets, other labels) pushes it down.
            under = [box for box in system.content[self.below_numerals.get(system.index, 0):] if box.right > centre - width / 2 and box.x < centre + width / 2]
            top = max([top] + [box.bottom + 60 for box in under])
        else:
            centre = self._bass_centre(cadence.at, x)
            top = system.bottom(centre - width / 2, centre + width / 2) + 90
        left = centre - width / 2
        self._add("rect", x=round(left), y=round(top), width=round(width), height=round(height),
                  fill="#ffffff", stroke=INK, stroke_width=LINE)
        self._text(centre, top + height / 2 + LABEL_SIZE * 0.33, cadence.label, LABEL_SIZE, anchor="middle")
        self._reserve(system, Box(left, top, width, height), pad=30)
        self.cadence_bottom[system.index] = max(self.cadence_bottom.get(system.index, -1e9), top + height)

    def _draw_ncts(self, ncts: list[NonChordTone]) -> None:
        """Circle each non-chord tone; notes of one chord with the same label share a circle and a label."""
        groups: dict[tuple, list[tuple[System, Box, Event]]] = {}
        labels: dict[tuple, str] = {}
        for nct in ncts:
            try:
                system, box, event = self.note_box(nct.note)
            except NotOnPage:
                continue
            key = (event.segment, event.onset, event.staff, nct.label)
            groups.setdefault(key, []).append((system, box, event))
            labels[key] = nct.label
        for key, notes in groups.items():
            self._draw_nct(labels[key], *notes[0][::2], [box for _, box, _ in notes])

    def _draw_nct(self, string: str, system: System, event: Event, boxes: list[Box]) -> None:
        x0, y0 = min(box.x for box in boxes), min(box.y for box in boxes)
        x1, y1 = max(box.right for box in boxes), max(box.bottom for box in boxes)
        rx, ry = (x1 - x0) / 2 + 60, (y1 - y0) / 2 + 60
        circle = Box((x0 + x1) / 2 - rx, (y0 + y1) / 2 - ry, 2 * rx, 2 * ry)
        self._add("ellipse", cx=round(circle.cx), cy=round(circle.cy), rx=round(rx), ry=round(ry),
                  fill="none", stroke=INK, stroke_width=LINE)
        string = NCT_NAMES.get(string.strip().upper(), string)
        width, height = text.width(string, LABEL_SIZE), LABEL_SIZE  # the box _text reports: cap top to below the baseline
        cx, cy = self._place_label(system, circle, width, height, below=event.staff > 1)
        label = Box(cx - width / 2, cy - height / 2, width, height)
        over = label.x < circle.right and label.right > circle.x
        level = label.y < circle.bottom and label.bottom > circle.y
        gap_y = max(circle.y - label.bottom, label.y - circle.bottom)
        gap_x = max(circle.x - label.right, label.x - circle.right)
        if (over and gap_y <= 260) or (level and gap_x <= 260):
            line = None
        else:  # too far, or off to one side where it could be read as naming another note: join them
            ex = min(max(circle.cx, label.x - 45), label.right + 45)
            ey = min(max(circle.cy, label.y - 45), label.bottom + 45)
            dx, dy = ex - circle.cx, ey - circle.cy
            t = 1 / math.hypot(dx / rx, dy / ry)
            line = (circle.cx + dx * t, circle.cy + dy * t, ex, ey)
        if line:
            self._add("line", x1=round(line[0]), y1=round(line[1]), x2=round(line[2]), y2=round(line[3]),
                      stroke=INK, stroke_width=LINE - 8)
            self._reserve_line(system, *line)
        self._text(cx, label.bottom - LABEL_SIZE * 0.25, string, LABEL_SIZE, anchor="middle", halo=True)
        self._reserve(system, circle, pad=30)
        self._reserve(system, label)

    def _draw_voice_marks(self, marks: list[VoiceLeading]) -> None:
        """Draw the part-writing marks. Identical marks on the same notes are drawn once (a held note must not
        print its ring or word twice); the two lines of one parallel or direct pair share one word, set between
        them; the second ring of an overlap is joined to the word of the first."""
        unique: dict[tuple, list] = {}  # (kind, from event, to event) -> [mark, labels]
        for mark in marks:
            try:
                first = self.index.find_note(**mark.from_note.model_dump())
                second = self.index.find_note(**mark.to_note.model_dump()) if mark.to_note else None
            except PositionError:
                continue
            entry = unique.setdefault((mark.kind, first.id, second.id if second else None), [mark, []])
            if mark.label and mark.label not in entry[1]:
                entry[1].append(mark.label)
        entries = list(unique.values())
        # Lines of one pair: two lines between the same two moments.
        pairs: dict[tuple, list] = {}
        for entry in entries:
            if entry[0].kind == "line":
                try:
                    first, second = (self.index.find_note(**entry[0].from_note.model_dump()), self.index.find_note(**entry[0].to_note.model_dump()))
                except PositionError:
                    continue
                pairs.setdefault((first.segment, first.onset, second.segment, second.onset), []).append(entry)
        shared = {id(entry): group for group in pairs.values() if len(group) == 2 for entry in group}
        done: set[int] = set()
        last = None  # (system, ring box, word box, event) of the labelled ring just drawn
        for entry in entries:
            mark, labels = entry
            if id(entry) in done:
                continue
            try:
                system_a, a, _ = self.note_box(mark.from_note)
                system_b, b, _ = self.note_box(mark.to_note) if mark.to_note else (system_a, a, None)
            except NotOnPage:
                continue
            if mark.kind == "ring":
                join = last if not labels and last and last[0] is system_a and last[3] != (mark.from_note.measure, mark.from_note.beat) else None
                ring, word = self._draw_ring(labels, system_a, a, join)
                last = (system_a, ring, word, (mark.from_note.measure, mark.from_note.beat)) if labels else None
                continue
            last = None
            if mark.kind == "bracket":
                self._draw_square_bracket(labels, system_a, a, b)
            elif mark.kind == "line" and id(entry) in shared:
                group = shared[id(entry)]
                done.update(id(member) for member in group)
                self._draw_parallel_pair(group)
            else:
                self._draw_voice_line(mark, labels, system_a, a, system_b, b)

    def _shafts(self, system_a: System, a: Box, system_b: System, b: Box) -> list[tuple[System, float, float, float, float]]:
        if system_a is system_b:
            return [(system_a, a.right + 50, a.cy, b.x - 50, b.cy)]
        # across a system break: run off the right edge and come back in from the left, like a tie
        return [
            (system_a, a.right + 50, a.cy, system_a.right - 40, a.cy),
            (system_b, self._content_left(system_b) - 250, b.cy, b.x - 50, b.cy),
        ]

    def _draw_parallel_pair(self, group: list) -> None:
        """Both lines of a pair, and their word(s) once, midway between the two voices (never in the numeral row)."""
        centres, system, labels = [], None, []
        for mark, own in group:
            system_a, a, _ = self.note_box(mark.from_note)
            system_b, b, _ = self.note_box(mark.to_note)
            shafts = self._shafts(system_a, a, system_b, b)
            for number, (shaft_system, x0, y0, x1, y1) in enumerate(shafts):
                self._line_or_arrow(x0, y0, x1, y1, head=False, colour=ERROR)
                self._reserve_line(shaft_system, x0, y0, x1, y1)
            system, x0, y0, x1, y1 = shafts[0]
            centres.append(((x0 + x1) / 2, (y0 + y1) / 2))
            labels += [label for label in own if label not in labels]
        middle = Box(sum(x for x, _ in centres) / 2 - 20, sum(y for _, y in centres) / 2 - 20, 40, 40)
        for label in labels:
            width = text.width(label, LABEL_SIZE)
            cx, cy = self._place_label(system, middle, width, LABEL_SIZE, below=True, limit=self._numeral_top(system))
            self._error_text(system, cx, cy, label, width, LABEL_SIZE)

    def _numeral_top(self, system: System) -> float | None:
        """Marks of the part-writing view stay above the numeral row."""
        return self.numeral_tops.get(system.index)

    def _draw_voice_line(self, line: VoiceLeading, labels: list[str], system_a: System, a: Box, system_b: System, b: Box) -> None:
        arrow = line.kind == "arrow"
        # Red is for faults: every line, and the arrows part_writing draws for an unresolved seventh or leading tone.
        # A resolution arrow the model draws on its own is an analysis mark.
        fault = not arrow or any(label in FAULT_ARROW_LABELS for label in labels)
        colour = ERROR if fault else ARROW
        shafts = self._shafts(system_a, a, system_b, b)
        for number, (system, x0, y0, x1, y1) in enumerate(shafts):
            self._line_or_arrow(x0, y0, x1, y1, head=arrow and number == len(shafts) - 1, colour=colour)
            self._reserve_line(system, x0, y0, x1, y1)
        for label in labels:
            width, height = text.width(label, LABEL_SIZE), LABEL_SIZE
            if arrow:  # right of the tendency tone itself, riding just above its arrow (MT21C)
                spot = (a.right + 55 + width / 2, a.cy - 60 - height / 2)
                padded = Box(spot[0] - width / 2 - LABEL_PAD, spot[1] - height / 2 - LABEL_PAD, width + 2 * LABEL_PAD, height + 2 * LABEL_PAD)
                others = [box for box in system_a.content + system_a.words if not self._is_shaft_piece(box, shafts[0])]
                if not any(o.x < padded.right and o.right > padded.x and o.y < padded.bottom and o.bottom > padded.y for o in others):
                    self._error_text(system_a, *spot, label, width, height, colour=colour)
                else:
                    self._label_near(system_a, a, label, width, height, right=True, colour=colour)
                continue
            system, x0, y0, x1, y1 = shafts[0]
            middle = Box((x0 + x1) / 2 - 20, (y0 + y1) / 2 - 20, 40, 40)
            cx, cy = self._place_label(system, middle, width, height, below=True, limit=self._numeral_top(system))
            self._error_text(system, cx, cy, label, width, height)

    @staticmethod
    def _is_shaft_piece(box: Box, shaft) -> bool:
        """Whether a reserved box is one of the small padded pieces of this arrow's own shaft."""
        _, x0, y0, x1, y1 = shaft
        return box.width <= abs(x1 - x0) / 8 + 61 and box.height <= abs(y1 - y0) / 8 + 61 and box.x >= x0 - 40 and box.right <= x1 + 40 \
            and box.y >= min(y0, y1) - 40 and box.bottom <= max(y0, y1) + 40

    def _line_or_arrow(self, x0: float, y0: float, x1: float, y1: float, head: bool, colour: str = ERROR) -> None:
        length = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        size, half = (190, 75) if head else (0, 0)
        bx, by = x1 - ux * size, y1 - uy * size
        self._add("line", x1=round(x0), y1=round(y0), x2=round(bx), y2=round(by),
                  stroke=colour, stroke_width=45, stroke_linecap="round")
        if head:
            points = [(x1, y1), (bx - uy * half, by + ux * half), (bx + uy * half, by - ux * half)]
            self._add("polygon", points=" ".join(f"{round(px)},{round(py)}" for px, py in points), fill=colour)

    def _error_text(self, system: System, cx: float, cy: float, string: str, width: float, height: float, colour: str = ERROR) -> Box:
        self._text(cx, cy + LABEL_SIZE * 0.34, string, LABEL_SIZE, fill=colour, anchor="middle", halo=True)
        box = Box(cx - width / 2, cy - height / 2, width, height)
        self._reserve(system, box)
        return box

    def _label_near(self, system: System, anchor: Box, string: str, width: float, height: float, right: bool = False,
                    colour: str = ERROR) -> Box | None:
        """A fault word beside its note or ring, never farther than the next side over.

        Beside its own note the word may sit on the staff lines, as in a teacher's markup; other marks, stems and
        lyrics block it. `right` tries the right side first (where the word is read after the note), else above.
        """
        near = [d for d, other in self._words if other is system and d[0] == string and abs(d[1].cy - anchor.cy) < 700
                and d[1].x - width < anchor.right and d[1].right + width > anchor.x]
        if near:  # the same word already stands by the neighbouring notes: one word names the group
            return None
        gap = 90
        sides = [(anchor.right + gap + width / 2, anchor.cy), (anchor.x - gap - width / 2, anchor.cy),
                 (anchor.cx, anchor.y - gap - height / 2), (anchor.cx, anchor.bottom + gap + height / 2)]
        if not right:
            sides = sides[2:] + sides[:2]
        sides += [(cx, cy + dy) for cx, cy in sides[:2] for dy in (-height, height)]
        # Still near the note, but further out: higher or lower, and shifted past a stem on either side.
        up, down = anchor.y - gap - height / 2, anchor.bottom + gap + height / 2
        for extra in (150, 300, 450, 600):
            sides += [(anchor.cx, up - extra), (anchor.cx, down + extra)]
        sides += [(anchor.cx + sign * (width / 2 + shift), y) for shift in (120, 350, 600) for y in (up, down) for sign in (1, -1)]

        def padded(spot):
            return Box(spot[0] - width / 2 - LABEL_PAD, spot[1] - height / 2 - LABEL_PAD, width + 2 * LABEL_PAD, height + 2 * LABEL_PAD)

        def hit(spot):
            box = padded(spot)
            return sum(max(0.0, min(box.right, o.right) - max(box.x, o.x)) * max(0.0, min(box.bottom, o.bottom) - max(box.y, o.y))
                       for o in system.content + system.words)

        cx, cy = min(sides, key=hit) if all(hit(spot) for spot in sides) else next(spot for spot in sides if not hit(spot))
        self._words.append(((string, Box(cx - width / 2, cy - height / 2, width, height)), system))
        return self._error_text(system, cx, cy, string, width, height, colour)

    def _draw_ring(self, labels: list[str], system: System, note: Box, join: tuple | None = None) -> tuple[Box, Box | None]:
        """A red ring with its word(s) beside it. `join` is the labelled ring of an overlap: this ring is the
        other note of that pair, tied to the word by a thin leader."""
        rx, ry = max(180, note.width / 2 + 60), max(135, note.height / 2 + 45)
        ring = Box(note.cx - rx, note.cy - ry, 2 * rx, 2 * ry)
        self._add("ellipse", cx=round(note.cx), cy=round(note.cy), rx=round(rx), ry=round(ry),
                  fill="none", stroke=ERROR, stroke_width=30)
        self._reserve(system, ring, pad=30)
        word = None
        for label in labels:
            word = self._label_near(system, ring, label, text.width(label, LABEL_SIZE), LABEL_SIZE, right=True) or word
        if join and join[2]:
            _, other, target, _ = join
            # From the nearest points of this ring and of the word, so the leader never crosses the word's letters.
            ex = min(max(ring.cx, target.x), target.right)
            ey = min(max(ring.cy, target.y), target.bottom)
            dx, dy = ex - ring.cx, ey - ring.cy
            t = 1 / max(math.hypot(dx / rx, dy / ry), 1e-6)
            if t < 1:
                self._add("line", x1=round(ring.cx + dx * t), y1=round(ring.cy + dy * t), x2=round(ex), y2=round(ey),
                          stroke=ERROR, stroke_width=20, stroke_linecap="round")
                self._reserve_line(system, ring.cx + dx * t, ring.cy + dy * t, ex, ey)
        return ring, word

    def _draw_square_bracket(self, labels: list[str], system: System, a: Box, b: Box) -> None:
        """MT21C's thin bracket right of a chord, spanning the two notes (a spacing fault). It keeps to the
        staves' side of any lyric, and its word stands beside it."""
        top, bottom = min(a.cy, b.cy), max(a.cy, b.cy)
        tick, base = 72, max(a.right, b.right) + 110
        stop = max(m.x1 for m in system.measures if m.x0 <= base <= m.x1 + 1) if any(m.x0 <= base <= m.x1 + 1 for m in system.measures) else base + 900
        x = base
        for shift in range(0, 1200, 100):
            reach = Box(base + shift - tick - LABEL_PAD, top - LABEL_PAD, tick + 2 * LABEL_PAD, bottom - top + 2 * LABEL_PAD)
            if base + shift + LABEL_PAD * 2 > stop:
                break
            if not any(w.x < reach.right and w.right > reach.x and w.y < reach.bottom and w.bottom > reach.y for w in system.words):
                x = base + shift
                break
        self._add("path", d=f"M{round(x - tick)},{round(top)} L{round(x)},{round(top)} L{round(x)},{round(bottom)} L{round(x - tick)},{round(bottom)}",
                  fill="none", stroke=ERROR, stroke_width=30, stroke_linejoin="round")
        self._reserve(system, Box(x - tick, top, tick, bottom - top), pad=30)
        for label in labels:
            self._label_near(system, Box(x, (top + bottom) / 2, 0, 0), label, text.width(label, LABEL_SIZE), LABEL_SIZE, right=True)

    def _draw_callout(self, callout: Callout) -> None:
        try:
            system, x = self.x_of(callout.at)
        except NotOnPage:
            return
        radius = 190
        cx = x + 110
        taken = self._callout_x.setdefault(system.index, [])
        while any(abs(cx - other) < 2 * radius + 40 for other in taken):  # two on one note sit side by side, not stacked
            cx += 2 * radius + 60
        taken.append(cx)
        cy = system.top(cx - radius, cx + radius) - 90 - radius
        self._add("circle", cx=round(cx), cy=round(cy), r=radius, fill=INK)
        self._text(cx, cy + LABEL_SIZE * 0.34, str(callout.number), LABEL_SIZE, bold=True, fill="#ffffff", anchor="middle")
        self._reserve(system, Box(cx - radius, cy - radius, 2 * radius, 2 * radius))

    def _draw_phrase(self, phrase: Phrase | Region, dashed: bool = False) -> None:
        """A thin bracket above the music with a plain upright label centred on it, repeated on each system the
        bracket continues onto. Regions are dashed."""
        try:
            pieces = self.segments(phrase.start, phrase.end)
        except NotOnPage:
            return
        tick = 150
        size = PHRASE_LETTER_SIZE if re.fullmatch(r"[A-Za-z][′']?", phrase.label) else LABEL_SIZE
        label_width = text.width(phrase.label, size)
        # One bracket row: a piece too short to hold the label (a stub at a system's edge) stays unlabelled, and
        # every wider piece repeats it. When none is wide enough the widest takes it.
        wide = [piece for piece in pieces if piece.x1 - piece.x0 >= label_width + 2 * LABEL_PAD]
        labelled = wide or ([max(pieces, key=lambda piece: piece.x1 - piece.x0)] if pieces else [])
        for piece in pieces:
            y = self._bracket_top(piece, getattr(phrase, "staff", None)) - 230
            path = f"M{round(piece.x0)},{round(y + tick) if piece.starts else round(y)} "
            path += f"L{round(piece.x0)},{round(y)} L{round(piece.x1)},{round(y)}"
            if piece.ends:
                path += f" L{round(piece.x1)},{round(y + tick)}"
            style = {"stroke_dasharray": "110 70"} if dashed else {}
            self._add("path", d=path, fill="none", stroke=INK, stroke_width=LINE, stroke_linejoin="round", **style)
            box = Box(piece.x0, y, piece.x1 - piece.x0, tick)
            if phrase.label and piece in labelled:
                # A label wider than its piece is pulled in so it never runs off the page.
                middle = min(max((piece.x0 + piece.x1) / 2, piece.system.left + label_width / 2), piece.system.right - label_width / 2)
                # Centred, unless a barline or another label is in the way: then the nearest clear spot along the bracket.
                shifts = [0.0] + [sign * step for step in range(100, 1500, 100) for sign in (-1, 1)]
                x = next((middle + shift for shift in shifts if piece.x0 <= middle + shift - label_width / 2 and middle + shift + label_width / 2 <= piece.x1 + 1
                          and self._is_free(piece.system, Box(middle + shift - label_width / 2 - LABEL_PAD, y - 90 - size * 0.75 - LABEL_PAD,
                                                              label_width + 2 * LABEL_PAD, size + 2 * LABEL_PAD))), middle)
                label = self._text(x, y - 90, phrase.label, size, anchor="middle")
                box = Box(piece.x0, label.y, piece.x1 - piece.x0, y + tick - label.y)
            piece.system.content.append(box)

    def _bracket_top(self, piece: Segment, staff: int | None) -> float:
        """Highest drawn point a bracket must clear: over the whole system, or over one staff when one is named."""
        measures = [m for m in piece.system.measures if m.x1 > piece.x0 and m.x0 < piece.x1]
        if not staff or not measures or any(staff not in m.numbered for m in measures):
            return piece.system.top(piece.x0, piece.x1)
        line = min(m.numbered[staff].y for m in measures)
        higher = [box.bottom for m in measures for box in m.lines if box.bottom < m.numbered[staff].y]
        if not higher:
            return piece.system.top(piece.x0, piece.x1)
        above = max(higher)
        # What hangs below the staff above belongs to that staff; only the lower half of the gap is this staff's.
        middle = (above + line) / 2
        own = [b.y for b in piece.system.content if b.right > piece.x0 and b.x < piece.x1 and b.cy > middle and b.y < line]
        return min([line] + own)

    def to_svg(self) -> str:
        return ET.tostring(self.root, encoding="unicode")
