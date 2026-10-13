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
# A line of the hidden room that moves two staves apart (annotate.py): measured on BWV 245.40 bar 5, where a third line
# moved the staves 363 units apart and a fourth 390 more. Verovio keeps a direction one unit (180) clear above and below
# (VEROVIO_OPTIONS defaultTopMargin, defaultBottomMargin).
ROOM_LINE, ROOM_MARGIN = 390, 2 * 180

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
    heads: list[Box] = field(default_factory=list)  # every notehead, also in `content`
    notes: list[Box] = field(default_factory=list)  # noteheads, accidentals and stems, which no label may touch

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
        # Rings, and ring codes, short of room between the staves: (the ringed note, "above" or "below" its staff, lines
        # of room to add once there is room, lines to ask for the first time), the gap that should open (annotate.py
        # opens it and lays the page out again).
        self.code_room: list[tuple[Event, str, int, int]] = []
        self.staff_marks: list[tuple[set[int], Box]] = []  # fermatas and dynamics, with the staves they belong to
        self.staff_of: dict[int, int] = {}  # id of a box in a system's content -> the staff it is drawn on, where known
        self.stems: dict[str, str] = {}  # note id -> "up" or "down", for the marks that sit opposite the stem
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

    def _visit(self, group: ET.Element, system: System, measure: MeasureGeometry | None, staff: int | None = None) -> None:
        classes = group.get("class", "").split()
        if "bounding-box" in classes:
            return
        if "staff" in classes and group.get("data-n", "").isdigit():
            staff = int(group.get("data-n"))
        drawn = len(system.content)
        box = self._own_box(group)
        if box and group.get("id"):
            self.boxes[group.get("id")] = box
        if box and group.get("data-staff"):
            self.staff_marks.append(({int(n) for n in group.get("data-staff").split() if n.isdigit()}, box))
        if "note" in classes or "chord" in classes:
            stems = self._read_stem(group)
            system.content.extend(stems)
            system.notes.extend(stems)
        if box and "note" in classes:  # a note's own box is its head; its stem and accidental have their own
            system.heads.append(box)
        if box and ("note" in classes or "accid" in classes):
            system.notes.append(box)
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
        if staff is not None:
            self.staff_of.update((id(box), staff) for box in system.content[drawn:])
        for child in group:
            if child.tag == f"{S}g":
                self._visit(child, system, measure, staff)
            elif child.tag == f"{S}text":  # text keeps its boxes inside its tspans
                boxes = list(filter(None, (self._rect_box(rect) for rect in child.iter(f"{S}rect"))))
                system.content.extend(boxes) if boxes else system.words.extend(self._text_boxes(child))

    def _read_stem(self, group: ET.Element) -> list[Box]:
        """A stem is drawn from its notehead end to its tip, so the way it runs is the way it points; a chord's
        one stem serves every note in it. Verovio reports no box for it, so its box is returned for the marks to avoid."""
        for child in group:
            if "stem" in child.get("class", "").split():
                path = child.find(f"{S}path")
                found = re.match(r"M([-\d.]+) ([-\d.]+) L[-\d.]+ ([-\d.]+)", path.get("d", "")) if path is not None else None
                if found:
                    x, start, end = (float(v) for v in found.groups())
                    direction = "up" if end < start else "down"
                    for note in [group, *group.iter(f"{S}g")]:
                        if "note" in note.get("class", "").split() and note.get("id"):
                            self.stems[note.get("id")] = direction
                    return [Box(x - 15, min(start, end), 30, abs(end - start))]
                return []
        return []

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
        The full word sits centred beneath; a run that crosses a system break is drawn open at the break and named
        again on the next line. Words and abbreviations never mix: if any piece on the page cannot hold its word,
        the whole page uses T, PD, D. A run ends where the key changes.
        Textbooks print no colour and no legend. Only chords that carry `function` get a bracket."""
        sequence = self.numeral_seq
        pieces: dict[int, list[tuple[float, float, str, bool, bool]]] = {}  # system -> (x0, x1, function, continued, runs on)
        position = 0
        while position < len(sequence):
            function = sequence[position][1]
            following = position + 1
            while following < len(sequence) and function and sequence[following][1] == function and sequence[following][-1] == sequence[position][-1]:
                following += 1
            if function:
                run = [entry[2:] for entry in sequence[position:following]]
                after = sequence[following][2:] if following < len(sequence) else None
                spans = list(dict.fromkeys(entry[0] for entry in run))
                for number, system_index in enumerate(spans):
                    entries = [entry for entry in run if entry[0] == system_index]
                    x0 = entries[0][2]
                    if after and after[0] == system_index and entries[-1] is run[-1]:
                        x1 = after[2] - 60
                    else:
                        x1 = self.systems[system_index].right - 30
                    pieces.setdefault(system_index, []).append((x0, max(x1, entries[-1][3]), function, number > 0, number < len(spans) - 1))
            position = following
        words = all(text.width(FUNCTION_NAMES[f], FUNCTION_SIZE) + 2 * LABEL_PAD <= x1 - x0 for row in pieces.values() for x0, x1, f, _, _ in row)
        for system_index, row in pieces.items():
            system = self.systems[system_index]
            hook = NUMERAL_SIZE * 0.2
            top = max(self.numeral_rows[system_index] + NUMERAL_SIZE * 0.25, self.cadence_bottom.get(system_index, -1e9) + 70)
            y = top + hook
            for x0, x1, function, continued, runs_on in row:
                name = FUNCTION_NAMES[function] if words else function
                start = f"M{round(x0)},{round(y)}" if continued else f"M{round(x0)},{round(y - hook)} L{round(x0)},{round(y)}"
                end = "" if runs_on else f" L{round(x1)},{round(y - hook)}"
                self._add("path", d=f"{start} L{round(x1)},{round(y)}{end}",
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
        banded = set(banded)
        for system_index, labels in by_system.items():
            # A cadential six-four's V goes on as ⁵₃ (or ⁷₃) over the next chord, not as a second "V" (FFF, OMT).
            # ABRSM-style analysis reads it as Ic, a tonic chord, followed by its own V ("Ic-Va", MyMusicTheory).
            key = key_at_start[system_index]
            for position, (centre, harmony) in enumerate(labels):
                if style != "abrsm" and position and re.fullmatch(r"(?i)cad6/?4", labels[position - 1][1].label) and harmony.label in ("V", "V7") \
                        and (harmony.key or labels[position - 1][1].key or key) == (labels[position - 1][1].key or key):
                    joined = harmony.model_copy(update={"label": "~53" if harmony.label == "V" else "~73"})
                    if id(harmony) in banded:
                        banded.add(id(joined))
                    labels[position] = (centre, joined)
                key = harmony.key or key
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
                                         harmony.function if id(harmony) in banded else None, *entry, key))
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
        them; the codes of rings on one chord are set together."""
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
        # Brackets first: they claim their line, and every fault word then keeps off it.
        entries = sorted(unique.values(), key=lambda entry: entry[0].kind != "bracket")
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
        rings: list[tuple[System, Box, list[str], Event]] = []  # words are placed once every other mark is down
        for entry in entries:
            mark, labels = entry
            if id(entry) in done:
                continue
            try:
                system_a, a, event = self.note_box(mark.from_note)
                system_b, b, _ = self.note_box(mark.to_note) if mark.to_note else (system_a, a, None)
            except NotOnPage:
                continue
            if mark.kind == "ring":
                ring = self._draw_ring(system_a, a)
                self.staff_of[id(system_a.content[-1])] = event.staff  # the ring's reserved box
                # A ring on a ledger note between the staves can all but touch another staff's marks (BWV 64.4 bar 6:
                # the alto's ring on the tenor's fermata); the gap then opens.
                staff = self.measures[event.segment].numbered.get(event.staff)
                if staff and not staff.y <= ring.cy <= staff.bottom:
                    side = "above" if ring.cy < staff.y else "below"
                    zone = Box(ring.x, ring.y - LABEL_PAD, ring.width, LABEL_PAD) if side == "above" else Box(ring.x, ring.bottom, ring.width, LABEL_PAD)
                    if any(event.staff not in staves and o.x < zone.right and o.right > zone.x and o.y < zone.bottom and o.bottom > zone.y
                           for staves, o in self.staff_marks):
                        self.code_room.append((event, side, 1, 1))
                rings.append((system_a, ring, labels, event))
                continue
            if mark.kind == "bracket":
                self._draw_square_bracket(labels, system_a, a, b)
            elif mark.kind == "line" and id(entry) in shared:
                group = shared[id(entry)]
                done.update(id(member) for member in group)
                self._draw_parallel_pair(group)
            else:
                self._draw_voice_line(mark, labels, system_a, a, system_b, b)
        self._place_ring_codes(rings)

    def _place_ring_codes(self, rings: list[tuple[System, Box, list[str], Event]]) -> None:
        """Each code sits beside its own ring. Rings of different voices stack a few staff spaces apart, so a spot is
        only taken when its own ring is the nearest one, and it may slide along the ring to dodge a staff line.
        Text across staff lines is not engraving practice (Gould: words and signs go outside the staff), so a spot off
        the staves comes first, just past the staff's edge if need be; where none is clear, the gap is noted in
        `code_room` for the staves to move apart, and meanwhile the code takes the nearest spot on the staff."""
        for system, ring, labels, event in rings:
            if not labels:
                continue
            word = " ".join(labels)
            width, height = text.width(word, LABEL_SIZE), LABEL_SIZE
            others = [other for other_system, other, _, _ in rings if other_system is system and other is not ring]
            unringed = [head for head in system.heads if abs(head.cx - ring.cx) < 1500 and abs(head.cy - ring.cy) < 1500
                        and not any(r.x <= head.cx <= r.right and r.y <= head.cy <= r.bottom for _, r, _, _ in rings)]
            slide = [0.0] + [sign * step for step in range(60, int(ring.height / 2 + height / 2), 60) for sign in (-1, 1)]
            bar = next(((m.x0, m.x1) for m in system.measures if m.x0 <= ring.cx <= m.x1), (ring.x, ring.right))
            staff = self.measures[event.segment].numbered.get(event.staff)  # the ringed note's own staff, also for a ledger note
            # The code stays on its ring's side of the staff: across the staff it would stand by another voice's notes.
            nearer = "above" if staff and ring.cy < staff.cy else "below"

            def box_at(spot, pad):
                return Box(spot[0] - width / 2 - pad, spot[1] - height / 2 - pad, width + 2 * pad, height + 2 * pad)

            def own(spot, skip=lambda other: False):
                """Nearer its own ring than any other ring or unringed note (clearly so when that is not level with the
                ring), and not over a barline: a code by another note reads as that note's (decision R)."""
                box = box_at(spot, 0)
                # Straight off its ring a code stacks outward from its note as an articulation does (Gould: marks stack
                # outward from a note), so it is that note's even with a neighbour's head diagonally nearer; only a head
                # in the same column then competes.
                heads = [h for h in unringed if h.x < box.right and h.right > box.x] if abs(spot[0] - ring.cx) < 1 else unringed
                return bar[0] <= box.x and box.right <= bar[1] and all(
                    ratio(other) * self._gap(box, ring) < self._gap(box, other) for other in others + heads if not skip(other))

            def ratio(other):
                return 1 if abs(other.cy - ring.cy) < ring.height / 2 else 1.5

            # Spots in order: right, left, above, below, past a fermata, above or below shifted; then just past the
            # nearer edge of the ring's staff.
            def spots_at(pad):
                gap = pad + 35  # the ring's own reserved margin is 30
                beside = [(ring.right + gap + width / 2, ring.cy + dy) for dy in slide] + [(ring.x - gap - width / 2, ring.cy + dy) for dy in slide]
                ends = (ring.y - gap - height / 2, ring.bottom + gap + height / 2)
                stack = []
                if staff:
                    # Straight off the ring past what stands on that side of it (a fermata), as marks stack outward from a
                    # note; stems are thin and pass by.
                    column = [o for o in system.content if o.width > 40 and o.x < ring.right and o.right > ring.x
                              and (ring.y - 600 < o.bottom <= ring.y + 30 if nearer == "above" else ring.bottom - 30 <= o.y < ring.bottom + 600)]
                    if column:
                        stack = [(ring.cx, min(o.y for o in column) - pad - 1 - height / 2 if nearer == "above"
                                  else max(o.bottom for o in column) + pad + 1 + height / 2)]
                spots = list(beside)
                for side, y in zip(("above", "below"), ends):
                    spots += [(ring.cx, y)] + (stack if side == nearer else []) + [(ring.cx + shift, y) for shift in (width / 2, -width / 2)]
                if staff:
                    # Just past the staff's edge on the ring's side: straight off the ring, then beside it, a little
                    # farther out past a dot or accidental.
                    y = staff.y - pad - 1 - height / 2 if nearer == "above" else staff.bottom + pad + 1 + height / 2
                    spots += [(ring.cx, y)] + [(ring.right + gap + width / 2 + shift, y) for shift in (0, 120, 240)]
                    spots += [(ring.x - gap - width / 2 - shift, y) for shift in (0, 120, 240)]
                    # Then outward through the gap, straight off the ring or half a code to either side, past the
                    # neighbouring notes, accidentals and ledger lines, up to the next staff: once the staves move
                    # apart, one of these is clear.
                    sign = -1 if nearer == "above" else 1
                    start = min(ends[0], y) if nearer == "above" else max(ends[1], y)
                    lines = [b for b in self.measures[event.segment].lines if (b.bottom < staff.y if nearer == "above" else b.y > staff.bottom)]
                    stop = (max(b.bottom for b in lines) if nearer == "above" else min(b.y for b in lines)) if lines else start + sign * 1500
                    for step in range(60, int(abs(stop - start)), 60):
                        cy = start + sign * step
                        if (cy - height / 2 - pad < stop) if nearer == "above" else (cy + height / 2 + pad > stop):
                            break
                        spots += [(ring.cx + shift, cy) for shift in (0, -width / 2, width / 2)]
                return spots

            def usable(spot, pad):
                return own(spot) and not self._touching(system, box_at(spot, pad))

            def off_staff(spot):
                return not self._on_staff(system, box_at(spot, 0))

            spot = next((s for s in spots_at(LABEL_PAD) if usable(s, LABEL_PAD) and off_staff(s)), None)
            if spot is None:
                if staff:
                    short, first = self._code_room(system, event, ring, staff, nearer, spots_at(LABEL_PAD), box_at, own, ratio, rings)
                    if short:
                        self.code_room.append((event, nearer, short, first))
                # Less clear space (the rings of a run may leave no more), still off the staves if possible; only then on one.
                spot = next((s for pad in (LABEL_PAD / 2, 0) for s in spots_at(pad) if usable(s, pad) and off_staff(s)), None) \
                    or next((s for pad in (LABEL_PAD, LABEL_PAD / 2, 0) for s in spots_at(pad) if usable(s, pad)), None) \
                    or self._least_covering(system, spots_at(0), box_at, own)
            self._error_text(system, *spot, word, width, height)

    def _code_room(self, system: System, event: Event, ring: Box, staff: Box, nearer: str, spots: list, box_at, own, ratio,
                   rings: list) -> tuple[int, int]:
        """How many lines of room the gap on the ring's side of its staff needs before its code fits off the staff: the
        lines that move the staves apart by the shortfall, once room is already there; and, the first time, those plus
        the lines the free space there takes without moving anything. (0, 0) when moving the staves apart would not help
        (only the same staff's notes are in the way). Room moves only what
        lies across the gap: the other staff, its notes and rings, and lyrics under the staff above."""
        lines = [b for b in self.measures[event.segment].lines if (b.bottom < staff.y if nearer == "above" else b.y > staff.bottom)]
        if not lines:
            return 1, 0  # past the outer staff there is no staff to move away: one line at a time
        edge = max(b.bottom for b in lines) if nearer == "above" else min(b.y for b in lines)
        middle = (edge + staff.y) / 2 if nearer == "above" else (edge + staff.bottom) / 2
        staves = {**self.staff_of, **{id(r): e.staff for s, r, _, e in rings if s is system}}

        def far(box):
            if id(box) in staves:
                return staves[id(box)] != event.staff
            # Wholly across the middle of the gap; a barline or a stem that spans the gap does not move away.
            return box.bottom < middle if nearer == "above" else box.y > middle

        near_things = [o for o in system.content if not far(o)] + (system.words if nearer == "below" else [])
        far_things = [o for o in system.content if far(o)] + (system.words if nearer == "above" else [])

        def meets(a, b):
            return b.x < a.right and b.right > a.x and b.y < a.bottom and b.bottom > a.y

        # The first spot that only what lies across the gap keeps from being clear.
        spot = next((c for c in spots if not self._on_staff(system, box_at(c, 0)) and own(c, skip=far)
                     and not any(meets(box_at(c, LABEL_PAD), o) for o in near_things)), None)
        if spot is None:
            return 0, 0
        box, bare = box_at(spot, LABEL_PAD), box_at(spot, 0)
        # How far the far side must move: out of the padded box, and far enough that the code is clearly its own ring's.
        move = [(o.bottom - box.y if nearer == "above" else box.bottom - o.y) for o in far_things if meets(box, o)]
        mine = self._gap(bare, ring)
        for other in [r for s, r, _, _ in rings if s is system and r is not ring and far(r)] + [h for h in system.heads if far(h)]:
            need = ratio(other) * mine + 1
            if self._gap(bare, other) < need:
                dx = max(bare.x - other.right, other.x - bare.right, 0)
                if dx < need:
                    dy = max(bare.y - other.bottom, other.y - bare.bottom, 0)
                    move.append(math.sqrt(need * need - dx * dx) - dy)
        shortfall = max(move, default=0)
        # Verovio sets the room's lines just past the notes at the ringed note and moves the staves apart only by what
        # the free space there cannot take, less the margins it keeps round the room.
        low, high = (edge, staff.y) if nearer == "above" else (staff.bottom, edge)
        column = [o for o in system.content if o.x < ring.right and o.right > ring.x and low <= o.cy <= high]
        if nearer == "above":
            free = min((o.y for o in column if not far(o)), default=staff.y) - max((o.bottom for o in column if far(o)), default=edge)
        else:
            free = min((o.y for o in column if far(o)), default=edge) - max((o.bottom for o in column if not far(o)), default=staff.bottom)
        return math.ceil(shortfall / ROOM_LINE), max(1, math.ceil((shortfall + free - ROOM_MARGIN) / ROOM_LINE))

    def _least_covering(self, system: System, spots: list, box_at, own) -> tuple[float, float]:
        """With no clear spot, the one that covers least, and never a notehead, accidental or stem (Gould, Layout: clear
        space round the notes); its own ring's spots first."""
        def cost(spot):
            box = box_at(spot, 0)
            notes = sum(o.x < box.right and o.right > box.x and o.y < box.bottom and o.bottom > box.y for o in system.notes)
            return notes, not own(spot), self._touching(system, box), self._covered(system, box)

        return min(spots, key=cost)

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
        centres, system, labels, staves = [], None, [], []
        for mark, own in group:
            system_a, a, event = self.note_box(mark.from_note)
            staves.append(event.staff)
            system_b, b, _ = self.note_box(mark.to_note)
            shafts = self._shafts(system_a, a, system_b, b)
            for number, (shaft_system, x0, y0, x1, y1) in enumerate(shafts):
                self._line_or_arrow(x0, y0, x1, y1, head=False, colour=ERROR)
                self._reserve_line(shaft_system, x0, y0, x1, y1)
            system, x0, y0, x1, y1 = shafts[0]
            centres.append(((x0 + x1) / 2, (y0 + y1) / 2))
            labels += [label for label in own if label not in labels]
        # Midway only when the voices share a staff or neighbour each other; across inner staves the gap holds other
        # voices' music, so the word goes under the lower line, where a reader looks for it.
        if abs(staves[0] - staves[1]) > 1:
            x, y = max(centres, key=lambda centre: centre[1])
        else:
            x, y = sum(c[0] for c in centres) / 2, sum(c[1] for c in centres) / 2
        middle = Box(x - 20, y - 20, 40, 40)
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
        if arrow and "R" in labels:
            self._draw_unresolved(line, system_a, a)
            return
        shafts = self._shafts(system_a, a, system_b, b)
        for number, (system, x0, y0, x1, y1) in enumerate(shafts):
            self._line_or_arrow(x0, y0, x1, y1, head=arrow and number == len(shafts) - 1, colour=colour)
            self._reserve_line(system, x0, y0, x1, y1)
        for label in labels:
            width, height = text.width(label, LABEL_SIZE), LABEL_SIZE
            if arrow:  # right of the tendency tone itself, riding just above its arrow (MT21C)
                spot = (a.right + 55 + width / 2, a.cy - 60 - height / 2)
                padded = Box(spot[0] - width / 2 - LABEL_PAD, spot[1] - height / 2 - LABEL_PAD, width + 2 * LABEL_PAD, height + 2 * LABEL_PAD)
                others = [box for box in self._obstacles(system_a) + system_a.words if not self._is_shaft_piece(box, shafts[0])]
                if not any(o.x < padded.right and o.right > padded.x and o.y < padded.bottom and o.bottom > padded.y for o in others):
                    self._error_text(system_a, *spot, label, width, height, colour=colour)
                else:
                    self._label_near(system_a, a, label, width, height, right=True, colour=colour)
                continue
            system, x0, y0, x1, y1 = shafts[0]
            middle = Box((x0 + x1) / 2 - 20, (y0 + y1) / 2 - 20, 40, 40)
            cx, cy = self._place_label(system, middle, width, height, below=True, limit=self._numeral_top(system))
            self._error_text(system, cx, cy, label, width, height)

    def _draw_unresolved(self, mark: VoiceLeading, system: System, note: Box) -> None:
        """Kelley's R: a small arrow on the sensitive note pointing the way it should have resolved, the code at its
        tail. In order of preference, taking the first spot with clear space (nothing within a stretch ahead
        of its head, no stem, note or lyric on it): (1) on the side of the notehead away from the stem, as an
        articulation sits, outside the staff, but no farther than two steps from the note, since a farther arrow
        belongs to nothing; (1b) for a note inside the staff, the same side just outside the staff, straight off the
        note; (2) the same side straight off the notehead, inside the staff; (3) just beside the
        notehead, on the side away from the stem (right unless the stem is up). With no clear spot, the least crowded."""
        up = mark.direction == "up"
        _, _, event = self.note_box(mark.from_note)
        stem = self.stems.get(event.id)
        sides = ["below", "above"] if stem == "up" else ["above", "below"]
        length, word = 420, text.width("R", LABEL_SIZE)
        pad = LABEL_PAD
        placements = []  # (x of the shaft, top, bottom, side the code takes, whether staff lines count as obstacles)
        for distance in (110, 220):
            for side in sides:
                near = note.y - distance if side == "above" else note.bottom + distance
                top = near - length if side == "above" else near
                placements += [(note.cx, top, top + length, beside, True) for beside in (1, -1)]
        # A note inside the staff is more than two steps from its edge: the arrow then starts just outside the staff,
        # still straight off its note, with the code at its tail also clear of the lines (decision S: outside the staff
        # where possible).
        staff = next((box for measure in system.measures for box in measure.lines
                      if box.x <= note.cx <= box.right and box.y <= note.cy <= box.bottom), None)
        if staff:
            tail_room, head_room = LABEL_SIZE / 2 + LABEL_PAD + 1, pad + 1
            if sides[0] == "below":
                top = staff.bottom + (head_room if up else tail_room)
            else:
                top = staff.y - (tail_room if up else head_room) - length
            placements += [(note.cx, top, top + length, beside, True) for beside in (1, -1)]
        # Next, straight off the notehead away from the stem even where that is inside the staff: still its own note's.
        for shaft in (length, 300):  # shorter when a note lies not far beyond the longer arrow's head
            top = note.y - 110 - shaft if sides[0] == "above" else note.bottom + 110
            placements += [(note.cx, top, top + shaft, beside, False) for beside in (1, -1)]
        for gap in (110, 60):  # the closer one only when the first crowds a neighbour
            for arrow_side in ((-1, 1) if stem == "up" else (1, -1)):
                x = note.right + gap + 75 if arrow_side == 1 else note.x - gap - 75
                top = note.cy - length / 2
                # Beside its own notehead the staff lines cannot be avoided; the code goes to whichever side of the arrow is freer.
                placements += [(x, top, top + length, beside, False) for beside in (arrow_side, -arrow_side)]
        candidates = []
        # The code at the tail; half way along the shaft only when that is crowded.
        for along, (x, top, bottom, beside, off_staff) in [(a, p) for a in (0, 0.5) for p in placements]:
            tail, head = (bottom, top) if up else (top, bottom)
            code_x = x + beside * (75 + word / 2 + LABEL_PAD)
            # An arrow points at whatever lies ahead of its head, so that stretch must be empty for a good way beyond it.
            ahead = 450
            arrow = Box(x - 100 - pad, top - pad, 200 + 2 * pad, bottom - top + 2 * pad)
            strip = Box(x - 100 - pad, top - ahead if up else bottom, 200 + 2 * pad, ahead)
            code_y = tail + (head - tail) * along
            code = Box(code_x - word / 2 - LABEL_PAD, code_y - LABEL_SIZE / 2 - LABEL_PAD, word + 2 * LABEL_PAD, LABEL_SIZE + 2 * LABEL_PAD)
            # Lyrics are not in the obstacles, and an arrow or code on a syllable is unreadable. A thin stem is a small
            # area but a real collision, so the number of things touched comes before the area.
            things = system.content + system.words + ([box for measure in system.measures for box in measure.lines] if off_staff else [])
            hits = sum((o.x < mark_box.right and o.right > mark_box.x and o.y < mark_box.bottom and o.bottom > mark_box.y)
                       for o in things for mark_box in (arrow, code, strip))
            area = self._covered(system, arrow) + self._covered(system, code)
            candidates.append((hits * 1e9 + area, arrow, x, code_x, code_y, tail, head))
        cost, arrow, x, code_x, code_y, tail, head = next((c for c in candidates if c[0] == 0), None) or min(candidates, key=lambda c: c[0])
        self._line_or_arrow(x, tail, x, head, head=True, colour=ERROR)
        self._reserve(system, Box(x - 100, min(tail, head), 200, abs(head - tail)), pad=30)
        self._error_text(system, code_x, code_y, "R", word, LABEL_SIZE)

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
                    colour: str = ERROR, shared: bool = True) -> Box | None:
        """A fault word beside its note or ring, never farther than the next side over.

        Beside its own note the word may sit on the staff lines, as in a teacher's markup; other marks, stems and
        lyrics block it. `right` tries the right side first (where the word is read after the note), else above.
        """
        near = [d for d, other in self._words if other is system and d[0] == string and abs(d[1].cy - anchor.cy) < 700
                and d[1].x - width < anchor.right and d[1].right + width > anchor.x]
        if near and shared:  # the same word already stands by the neighbouring notes: one word names the group
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
            return self._covered(system, padded(spot))

        def on_staff(spot):
            return self._on_staff(system, padded(spot))

        # A halo cutting the staff lines hides notes' lines, so the nearest spot clear of the staves wins; only when
        # every spot is on a staff does the word sit on the lines, as in a teacher's markup.
        clear = [spot for spot in sides if not hit(spot)]
        cx, cy = next((spot for spot in clear if not on_staff(spot)), None) or (clear[0] if clear else min(sides, key=hit))
        self._words.append(((string, Box(cx - width / 2, cy - height / 2, width, height)), system))
        return self._error_text(system, cx, cy, string, width, height, colour)

    @staticmethod
    def _gap(a: Box, b: Box) -> float:
        return math.hypot(max(a.x - b.right, b.x - a.right, 0), max(a.y - b.bottom, b.y - a.bottom, 0))

    def _covered(self, system: System, box: Box) -> float:
        """Area of the box lying on drawn content or lyrics."""
        return sum(max(0.0, min(box.right, o.right) - max(box.x, o.x)) * max(0.0, min(box.bottom, o.bottom) - max(box.y, o.y))
                   for o in system.content + system.words)

    @staticmethod
    def _touching(system: System, box: Box) -> int:
        """How many drawn things or lyrics the box meets; a thin stem is a small area but a real collision."""
        return sum(o.x < box.right and o.right > box.x and o.y < box.bottom and o.bottom > box.y for o in system.content + system.words)

    @staticmethod
    def _on_staff(system: System, box: Box) -> bool:
        return any(o.x < box.right and o.right > box.x and o.y < box.bottom and o.bottom > box.y
                   for measure in system.measures for o in measure.lines)

    def _draw_ring(self, system: System, note: Box) -> Box:
        rx, ry = max(180, note.width / 2 + 60), max(135, note.height / 2 + 45)
        ring = Box(note.cx - rx, note.cy - ry, 2 * rx, 2 * ry)
        self._add("ellipse", cx=round(note.cx), cy=round(note.cy), rx=round(rx), ry=round(ry),
                  fill="none", stroke=ERROR, stroke_width=30)
        self._reserve(system, ring, pad=30)
        return ring

    def _draw_square_bracket(self, labels: list[str], system: System, a: Box, b: Box) -> None:
        """MT21C's thin bracket right of a chord, spanning the two notes (a spacing fault). It keeps to the
        staves' side of any lyric, and its word stands beside it."""
        top, bottom = min(a.cy, b.cy), max(a.cy, b.cy)
        tick, base = 72, max(a.right, b.right) + 110
        stop = max(m.x1 for m in system.measures if m.x0 <= base <= m.x1 + 1) if any(m.x0 <= base <= m.x1 + 1 for m in system.measures) else base + 900

        def hits(box: Box) -> bool:
            return any(w.x < box.right and w.right > box.x and w.y < box.bottom and w.bottom > box.y for w in system.words)

        # Only the upright must clear a lyric (it may pass between two syllables); the ticks sit at note height.
        x = base
        for shift in range(0, 1200, 40):
            if base + shift + LABEL_PAD * 2 > stop:
                break
            if not hits(Box(base + shift - LABEL_PAD, top - LABEL_PAD, 2 * LABEL_PAD, bottom - top + 2 * LABEL_PAD)):
                x = base + shift
                break
        self._add("path", d=f"M{round(x - tick)},{round(top)} L{round(x)},{round(top)} L{round(x)},{round(bottom)} L{round(x - tick)},{round(bottom)}",
                  fill="none", stroke=ERROR, stroke_width=30, stroke_linejoin="round")
        self._reserve(system, Box(x - tick, top, tick, bottom - top), pad=30)
        # The anchor is the whole bracket, so no fallback spot can land on its own mark.
        for label in labels:
            self._label_near(system, Box(x, top, 0, bottom - top), label, text.width(label, LABEL_SIZE), LABEL_SIZE, right=True)

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
