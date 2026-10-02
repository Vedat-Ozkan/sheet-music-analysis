"""Draw an annotation list onto one page of Verovio's SVG.

Verovio is asked for bounding boxes, so every drawn element has a known place.
The overlay reads those boxes, adds its own SVG elements in the same coordinate
system, and removes the helper boxes again before the page is rasterised.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

from engine import text
from engine.annotations import AnnotationList, Cadence, Callout, Harmony, NonChordTone, Phrase, VoiceLeading
from engine.score import TOLERANCE, Event, PositionError, ScoreIndex

SVG_NS = "http://www.w3.org/2000/svg"
S = f"{{{SVG_NS}}}"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Paul Tol's "bright" scheme, which stays distinguishable with colour-vision deficiencies.
FUNCTION_COLORS = {"T": "#4477AA", "PD": "#228833", "D": "#EE6677"}
FUNCTION_NAMES = {"T": "tonic", "PD": "predominant", "D": "dominant"}
INK = "#1a1a1a"
MUTED = "#555555"
NCT_COLOR = "#CC3311"
VOICE_COLOR = "#AA3377"

# Lengths are in Verovio's SVG units; a staff space is 180.
NUMERAL_SIZE = 440
LABEL_SIZE = 330
SMALL_SIZE = 280
LINE = 26
BAND_OPACITY = "0.16"
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
        self._remove("fing")  # fingering is clutter on an analysis page
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
            (measure for measure in index.measures if measure.id in self.measures), key=lambda measure: measure.index
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
        for child in group:
            if child.tag == f"{S}g":
                self._visit(child, system, measure)
            elif child.tag == f"{S}text":  # text keeps its boxes inside its tspans
                system.content.extend(filter(None, (self._rect_box(rect) for rect in child.iter(f"{S}rect"))))

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
            for other in system.content
        )

    @staticmethod
    def _reserve(system: System, box: Box, pad: float = LABEL_PAD) -> None:
        """Mark the box, plus clear space around it, as taken so later elements keep away."""
        system.content.append(Box(box.x - pad, box.y - pad, box.width + 2 * pad, box.height + 2 * pad))

    def _reserve_line(self, system: System, x0: float, y0: float, x1: float, y1: float, steps: int = 8) -> None:
        for step in range(steps):
            xa, xb = x0 + (x1 - x0) * step / steps, x0 + (x1 - x0) * (step + 1) / steps
            ya, yb = y0 + (y1 - y0) * step / steps, y0 + (y1 - y0) * (step + 1) / steps
            self._reserve(system, Box(min(xa, xb), min(ya, yb), abs(xb - xa), abs(yb - ya)), pad=30)

    def _place_label(self, system: System, anchor: Box, width: float, height: float, below: bool = False) -> tuple[float, float]:
        """Centre for a label near `anchor`: the closest spot whose padded box touches nothing drawn."""

        def above(distance: float) -> tuple[float, float]:
            return anchor.cx, anchor.y - distance - height / 2

        def under(distance: float) -> tuple[float, float]:
            return anchor.cx, anchor.bottom + distance + height / 2

        near, far = (under, above) if below else (above, under)
        left = (anchor.x - 90 - width / 2, anchor.cy)
        right = (anchor.right + 90 + width / 2, anchor.cy)
        spots = [near(90), near(200), left, right, near(330), far(90), far(200), near(480), near(650), far(330), near(850)]
        for cx, cy in spots:
            padded = Box(cx - width / 2 - LABEL_PAD, cy - height / 2 - LABEL_PAD, width + 2 * LABEL_PAD, height + 2 * LABEL_PAD)
            if self._is_free(system, padded):
                return cx, cy
        return spots[0]

    # ---- musical position -> page position --------------------------------------------

    def x_at(self, measure_number: int, offset: Fraction) -> tuple[System, float]:
        measure = self.index.measure(measure_number)
        geometry = self.measures.get(measure.id)
        if geometry is None:
            raise NotOnPage
        points: dict[Fraction, float] = {}
        end = Fraction(0)
        for event in measure.events:
            box = self.boxes.get(event.id)
            if box is None or event.grace:
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
        measure = self.index.measure(ref.measure)
        if event.id not in self.boxes or measure.id not in self.measures:
            raise NotOnPage
        return self.systems[self.measures[measure.id].system], self.boxes[event.id], event

    def _content_left(self, system: System) -> float:
        first = self.index.measure_by_id(system.measures[0].id)
        return self.x_at(first.number, Fraction(0))[1] - 90

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
                geometry = self.measures.get(self.index.measure(end.measure).id)
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
            if self.index.measure(end.measure).index < self.index.measure_by_id(self.systems[0].measures[0].id).index:
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
        banded = [h for h in harmonies if annotations.visible("function", h, view, role)]
        used_functions = self._draw_function_bands(banded)
        self._draw_harmonies(harmonies)
        for cadence in shown("cadence", Cadence):
            self._draw_cadence(cadence)
        for nct in shown("nct", NonChordTone):
            self._draw_nct(nct)
        for line in shown("voice_leading", VoiceLeading):
            self._draw_voice_leading(line)
        for callout in shown("callout", Callout):
            self._draw_callout(callout)
        for phrase in shown("phrase", Phrase):
            self._draw_phrase(phrase)
        if used_functions:
            self._draw_legend(used_functions)

    def _draw_function_bands(self, harmonies: list[Harmony]) -> list[str]:
        used: list[str] = []
        position = 0
        while position < len(harmonies):
            first = harmonies[position]
            following = position + 1
            while following < len(harmonies) and harmonies[following].function == first.function:
                following += 1
            if first.function:
                last = harmonies[following - 1]
                end = harmonies[following].at if following < len(harmonies) else _MeasureEnd(last.at.measure)
                try:
                    pieces = self.segments(first.at, end, gap=0)
                except NotOnPage:
                    pieces = []
                if pieces and first.function not in used:
                    used.append(first.function)
                for piece in pieces:
                    top, bottom = piece.system.staff_top - 90, piece.system.staff_bottom + 90
                    self._add(
                        "rect",
                        self.under,
                        x=round(piece.x0 - 60),
                        y=round(top),
                        width=round(piece.x1 - piece.x0),
                        height=round(bottom - top),
                        fill=FUNCTION_COLORS[first.function],
                        fill_opacity=BAND_OPACITY,
                    )
            position = following
        return used

    def _draw_harmonies(self, harmonies: list[Harmony]) -> None:
        by_system: dict[int, list[tuple[float, Harmony]]] = {}
        key_at_start: dict[int, str] = {}
        key = None
        for harmony in harmonies:
            key = harmony.key or key
            try:
                system, x = self.x_of(harmony.at)
            except NotOnPage:
                continue
            by_system.setdefault(system.index, []).append((x, harmony))
            key_at_start.setdefault(system.index, key)
        for system_index, labels in by_system.items():
            system = self.systems[system_index]
            baseline = system.bottom() + 170 + NUMERAL_SIZE * 0.75
            if key_at_start[system_index]:
                self._text(system.left + 80, baseline, text.pretty_key(key_at_start[system_index]) + ":", NUMERAL_SIZE, bold=True)
            cursor = 0.0
            for position, (x, harmony) in enumerate(labels):
                label = harmony.label
                x = max(x - 30, cursor)
                if harmony.key and position:  # a key change inside the system is written in line
                    box = self._text(x, baseline, text.pretty_key(harmony.key) + ":", NUMERAL_SIZE, bold=True)
                    x = box.right + 90
                chunks, total = text.numeral(label, NUMERAL_SIZE)
                for chunk in chunks:
                    self._text(x + chunk.dx, baseline + chunk.dy, chunk.text, chunk.size, bold=chunk.bold)
                cursor = x + total + 110
            system.content.append(Box(system.left, baseline - NUMERAL_SIZE * 0.8, system.right - system.left, NUMERAL_SIZE * 1.05))

    def _draw_cadence(self, cadence: Cadence) -> None:
        try:
            system, x = self.x_of(cadence.at)
        except NotOnPage:
            return
        width = text.width(cadence.label, LABEL_SIZE, bold=True) + 160
        top = system.bottom(x - 60, x - 60 + width) + 90
        height = LABEL_SIZE * 1.3
        self._add("rect", x=round(x - 60), y=round(top), width=round(width), height=round(height), rx=60,
                  fill="#ffffff", stroke=INK, stroke_width=LINE)
        self._text(x - 60 + width / 2, top + height * 0.73, cadence.label, LABEL_SIZE, bold=True, anchor="middle")
        self._reserve(system, Box(x - 60, top, width, height), pad=30)

    def _draw_nct(self, nct: NonChordTone) -> None:
        try:
            system, box, event = self.note_box(nct.note)
        except NotOnPage:
            return
        rx, ry = box.width / 2 + 60, box.height / 2 + 60
        circle = Box(box.cx - rx, box.cy - ry, 2 * rx, 2 * ry)
        self._add("ellipse", cx=round(box.cx), cy=round(box.cy), rx=round(rx), ry=round(ry),
                  fill="none", stroke=NCT_COLOR, stroke_width=LINE + 6)
        width, height = text.width(nct.label, SMALL_SIZE, bold=True), SMALL_SIZE * 0.68
        cx, cy = self._place_label(system, circle, width, height, below=event.staff > 1)
        label = Box(cx - width / 2, cy - height / 2, width, height)
        if label.bottom < circle.y - 260 or label.y > circle.bottom + 260:  # too far to read as a pair: join them
            above = label.bottom < circle.y
            self._add("line", x1=round(circle.cx), y1=round(circle.y if above else circle.bottom),
                      x2=round(cx), y2=round(label.bottom + 45 if above else label.y - 45),
                      stroke=NCT_COLOR, stroke_width=LINE - 8)
        self._text(cx, label.bottom, nct.label, SMALL_SIZE, bold=True, fill=NCT_COLOR, anchor="middle", halo=True)
        self._reserve(system, circle, pad=30)
        self._reserve(system, label)

    def _draw_voice_leading(self, line: VoiceLeading) -> None:
        try:
            system_a, a, _ = self.note_box(line.from_note)
            system_b, b, _ = self.note_box(line.to_note)
        except NotOnPage:
            return
        if system_a is system_b:
            shafts = [(system_a, a.right + 50, a.cy, b.x - 50, b.cy)]
        else:  # across a system break: run off the right edge and come back in from the left
            shafts = [
                (system_a, a.right + 50, a.cy, system_a.right - 40, a.cy),
                (system_b, self._content_left(system_b) - 250, b.cy, b.x - 50, b.cy),
            ]
        for system, x0, y0, x1, y1 in shafts:
            self._arrow(x0, y0, x1, y1)
            self._reserve_line(system, x0, y0, x1, y1)
        if line.label:
            system, x0, y0, x1, y1 = shafts[0]
            width, height = text.width(line.label, SMALL_SIZE, bold=True), SMALL_SIZE * 0.68
            middle = Box((x0 + x1) / 2 - 20, (y0 + y1) / 2 - 20, 40, 40)
            cx, cy = self._place_label(system, middle, width, height)
            self._text(cx, cy + height / 2, line.label, SMALL_SIZE, bold=True, fill=VOICE_COLOR, anchor="middle", halo=True)
            self._reserve(system, Box(cx - width / 2, cy - height / 2, width, height))

    def _arrow(self, x0: float, y0: float, x1: float, y1: float) -> None:
        length = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        head, half = 190, 75
        bx, by = x1 - ux * head, y1 - uy * head
        self._add("line", x1=round(x0), y1=round(y0), x2=round(bx), y2=round(by),
                  stroke=VOICE_COLOR, stroke_width=LINE + 10, stroke_linecap="round")
        points = [(x1, y1), (bx - uy * half, by + ux * half), (bx + uy * half, by - ux * half)]
        self._add("polygon", points=" ".join(f"{round(px)},{round(py)}" for px, py in points), fill=VOICE_COLOR)

    def _draw_callout(self, callout: Callout) -> None:
        try:
            system, x = self.x_of(callout.at)
        except NotOnPage:
            return
        radius = 190
        cx = x + 110
        cy = system.top(cx - radius, cx + radius) - 90 - radius
        self._add("circle", cx=round(cx), cy=round(cy), r=radius, fill=INK)
        self._text(cx, cy + LABEL_SIZE * 0.34, str(callout.number), LABEL_SIZE, bold=True, fill="#ffffff", anchor="middle")
        self._reserve(system, Box(cx - radius, cy - radius, 2 * radius, 2 * radius))

    def _draw_phrase(self, phrase: Phrase) -> None:
        try:
            pieces = self.segments(phrase.start, phrase.end)
        except NotOnPage:
            return
        tick = 150
        label_width = text.width(phrase.label, LABEL_SIZE, bold=True) + 150
        labelled = next((piece for piece in pieces if piece.x1 - piece.x0 >= label_width), pieces[0]) if pieces else None
        for piece in pieces:
            y = piece.system.top(piece.x0, piece.x1) - 230
            path = f"M{round(piece.x0)},{round(y + tick) if piece.starts else round(y)} "
            path += f"L{round(piece.x0)},{round(y)} L{round(piece.x1)},{round(y)}"
            if piece.ends:
                path += f" L{round(piece.x1)},{round(y + tick)}"
            self._add("path", d=path, fill="none", stroke=INK, stroke_width=LINE + 4, stroke_linejoin="round")
            box = Box(piece.x0, y, piece.x1 - piece.x0, tick)
            if phrase.label and piece is labelled:
                # A label wider than its piece is pulled left so it never runs off the page.
                x = min(piece.x0 + 20, piece.system.right - label_width + 150)
                label = self._text(x, y - 90, phrase.label, LABEL_SIZE, bold=True, italic=True)
                box = Box(piece.x0, label.y, piece.x1 - piece.x0, y + tick - label.y)
            piece.system.content.append(box)

    def _draw_legend(self, functions: list[str]) -> None:
        system = self.systems[-1]
        x, y = system.left, system.bottom() + 420
        for function in functions:
            self._add("rect", x=round(x), y=round(y - 210), width=260, height=260,
                      fill=FUNCTION_COLORS[function], fill_opacity="0.45")
            label = self._text(x + 330, y, FUNCTION_NAMES[function], SMALL_SIZE, fill=MUTED)
            x = label.right + 330

    def to_svg(self) -> str:
        return ET.tostring(self.root, encoding="unicode")


@dataclass
class _MeasureEnd:
    """A range end at the end of a measure, for the last function band."""

    measure: int
    beat: None = None
