"""Display rules checked on every page a user can get, measured from the SVG the engine produces.

    .venv/bin/python -m tools.display_check [--root TREE] [--only TEXT] [--crops DIR] [--jobs N] [--repin]

Draws the whole corpus through the real entry points (engine.annotate.render as the server's render_analysis calls it,
engine.read_pdf.preview as the server's read_pdf calls it, and the skill's skill/scripts/read_pdf.py pages()), then
measures each final page. The music's geometry comes from Verovio's own bounding boxes, beam polygons and staff and
ledger line paths; the analysis marks from what the overlay wrote into the page. Nothing here reuses the placers'
helpers (`_on_staff`, `_touching`, `own()`, `system.content`), so the check can disagree with them.

Corpus: the 20 part-writing chorales (tests/data/part_writing_*.musicxml), whole piece and each bar with a mark on
its own, with the part-writing draft's own marks and callouts; the hand-checked engraving passages (examples/engraving) and the Chopin example in all three
notation styles; the two check-page samples; and 12 PDF readings (the 4 review PDFs and the 8 whose plain layout ends
on a page of one or two bars), read through engine.read_pdf.read_pdf over the benchmark's cached Audiveris output.

Rules (docs/display-check.md says why each exists):
  staff-line     no analysis text (codes, numerals, figures, R, bar numbers, callouts) crosses a staff or ledger line
  collision      no analysis text (with its white knockout) or tendency arrow, callout disc or cadence box touches a
                 notehead, accidental, stem, beam, dot, rest, flag, fermata, dynamic, lyric, other score text or sign,
                 or another analysis text or mark; no ring comes within 40 of a dot, accidental, fermata, articulation,
                 flag, rest, dynamic, lyric, tie, slur or another notehead
  ring-code      each ring code is clearly nearer its own ring than any other ring or notehead (1.5 times as near)
  ring-own       a ring keeps clear of its own note's accidental and dot
  dropped        every mark the part-writing draft lists is drawn, by type and position
  excerpt-edge   a line, bracket or arrow (other than a tendency arrow) the draft lists runs past the bars drawn
  arrow-staff    a tendency arrow and its R stay off the staff lines
  pages          page count and bars on the last page of every PDF reading match tests/golden/display_check_pages.json
  bar-number     a bar number at an ending stands above the ending's bracket
  top-margin     a reading's pages keep a top margin (2.5% of the page width) above their first ink

--root runs the check against another checkout (read only); the corpus data, engine and skill come from there, the
page baseline from this checkout. --repin rewrites the page baseline from --root and prints what changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BASELINE = HERE / "tests" / "golden" / "display_check_pages.json"
BENCH = "spike/omr/bench"
RAW_SIGNATURE = "7d31a512375b5701sma2rel"
REVIEW_READINGS = ["chopin-prelude-4--ms", "joplin-maple-leaf-rag--ly", "mozart-k545-1--scan", "schubert-die-stadt--ly"]
SHORT_LAST_PAGE = ["clara-schumann-polonaise-3--ly", "lehmann-golden-bridges--ms", "mozart-quartet-k80--ms",
                   "mozart-quartet-k80--scan", "mozart-quartet-k80--vr", "bach-chorale-269--ms",
                   "chopin-prelude-4--scan", "chopin-prelude-4--lilypond-mutopia"]
STYLES = ("current", "abrsm", "figured_bass")

SVG = "{http://www.w3.org/2000/svg}"
ERROR = "#D50000"
WHITE = "#ffffff"
TOUCH = 8
TOP_MARGIN = 0.025



def corpus(root: Path) -> list[tuple[str, str]]:
    items = [("chorale", p.stem.replace("part_writing_", "")) for p in sorted((root / "tests/data").glob("part_writing_*.musicxml"))]
    items += [("excerpts", p.stem.replace("part_writing_", "")) for p in sorted((root / "tests/data").glob("part_writing_*.musicxml"))]
    items += [("harmony", f"{p.stem}:{style}") for p in sorted((root / "examples/engraving").glob("*.json")) for style in STYLES]
    items += [("harmony", f"chopin-op9-2:{style}") for style in STYLES]
    items += [("check-page", name) for name in ("bach", "chopin")]
    items += [("pdf", stem) for stem in REVIEW_READINGS + SHORT_LAST_PAGE]
    return items


def draft_marks(root: Path, name: str, callouts: bool = True) -> tuple[bytes, list[dict]]:
    from engine.part_writing import as_text
    from engine.render import load_toolkit
    from engine.score import ScoreIndex

    score = (root / f"tests/data/part_writing_{name}.musicxml").read_bytes()
    marks, spot = [], 0
    for line in as_text(ScoreIndex(load_toolkit(score).getMEI())).splitlines():
        heading = re.match(r"(\d+)\. m\S+ b\S+, callout at (\{.*\})$", line)
        if heading:
            spot = int(heading.group(1))
            if callouts:
                at = json.loads(heading.group(2))
                marks.append({"type": "callout", "at": {"measure": at["measure"], "beat": at["beat"]}, "number": spot, "spot": spot})
            continue
        found = re.match(r'\s+draw (\w+) (\{.*?\})(?: -> (\{.*?\}))?(?: label "([^"]*)")?(?: direction "(\w+)")?$', line)
        if found:
            kind, a, b, label, direction = found.groups()
            marks.append({"type": "voice_leading", "kind": kind, "label": label or "", "from_note": json.loads(a),
                          **({"to_note": json.loads(b)} if b else {}), **({"direction": direction} if direction else {}), "spot": spot})
    return score, marks


def _annotations(marks: list[dict]):
    from engine.annotations import AnnotationList
    return AnnotationList.model_validate({"annotations": [{k: v for k, v in m.items() if k != "spot"} for m in marks]})


class Capture:

    def __init__(self):
        from engine.overlay import PageLayout
        self.cls, self.pages = PageLayout, []
        self.init, self.to_svg = PageLayout.__init__, PageLayout.to_svg
        capture = self

        def init(layout, svg, *args, **kwargs):
            capture.init(layout, svg, *args, **kwargs)
            layout._display_check_source = svg

        def to_svg(layout):
            out = capture.to_svg(layout)
            capture.pages.append((layout._display_check_source, layout.index))
            return out

        PageLayout.__init__, PageLayout.to_svg = init, to_svg

    def take(self, engraving) -> list[tuple[str, str, object]]:
        drawn = self.pages[-engraving.page_count:]
        self.pages = []
        assert len(drawn) == engraving.page_count, "a page was not drawn through PageLayout.to_svg"
        return [(source, out, index) for (source, index), out in zip(drawn, engraving.svgs)]


def _read_pdf(root: Path, stem: str) -> bytes:
    from engine import read_pdf as reader

    bench = Path(os.environ.get("DISPLAY_CHECK_BENCH", _main_checkout(root) / BENCH))

    def raw(data, audiveris, options, deadline):
        key = hashlib.sha256(data + RAW_SIGNATURE.encode() + " ".join(options).encode()).hexdigest()[:32]
        meta, mxl = bench / "cache/raw" / f"{key}.json", bench / "cache/raw" / f"{key}.mxl"
        if not meta.exists():
            raise FileNotFoundError(f"no cached Audiveris reading of {stem} with settings {' '.join(options)} ({meta})")
        saved = json.loads(meta.read_text())
        if "error" in saved:
            raise reader.ReadError(saved["error"])
        return None if saved.get("timeout") else (mxl.read_bytes(), saved["skipped"])

    return reader.read_pdf((bench / "pdfs" / f"{stem}.pdf").read_bytes(), audiveris="(cached)", raw=raw).musicxml


def _main_checkout(root: Path) -> Path:
    import subprocess
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


def draw(root: Path, group: str, name: str) -> list[tuple[str, list, dict]]:
    from engine.annotate import render
    from engine.annotations import AnnotationList
    from engine.render import load_toolkit
    from engine.score import ScoreIndex

    capture = Capture()
    if group == "chorale":
        score, marks = draft_marks(root, name)
        index = ScoreIndex(load_toolkit(score).getMEI())
        bars = (index.measures[0].number, index.measures[-1].number)
        page = render(score, _annotations(marks), measures=bars)
        return [("render", capture.take(page), {"marks": marks})]
    if group == "excerpts":
        score, marks = draft_marks(root, name)
        annotations = _annotations(marks)
        found = []
        for bar in sorted({m["from_note"]["measure"] for m in marks if m["type"] == "voice_leading"}):
            page = render(score, annotations, measures=(bar, bar))
            found.append((f"bar {bar}", capture.take(page), {"marks": marks, "excerpt": True}))
        return found
    if group == "harmony":
        piece, style = name.split(":")
        if piece == "chopin-op9-2":
            score = (root / "tests/data/chopin_nocturne_op9_no2.mxl").read_bytes()
            annotations, bars = AnnotationList.model_validate_json((root / "examples/chopin_op9_no2_m1-8.json").read_text()), (1, 8)
        else:
            from tools import engraving_check, robustness
            from tools.robustness import fetch
            robustness.OUT = HERE / "out" / "robustness"
            source, bars = engraving_check.PIECES[piece]
            engraving_check._layouts.clear()
            score = fetch(piece, source) if isinstance(source, str) else source.read_bytes()
            annotations = AnnotationList.model_validate_json((root / f"examples/engraving/{piece}.json").read_text())
        page = render(score, annotations.model_copy(update={"style": style}), measures=bars)
        return [("render", capture.take(page), {})]
    if group == "check-page":
        from engine.check_analysis import from_text
        source, reviewed = {"chopin": ("tests/data/chopin_nocturne_op9_no2.mxl", "examples/chopin_op9_no2_m1-8.json"),
                            "bach": ("tests/data/part_writing_bwv404.musicxml", "tests/data/check_display/bach-reviewed.json")}[name]
        score = (root / source).read_bytes()
        annotations = AnnotationList.model_validate_json((root / reviewed).read_text())
        labels = from_text((root / f"tests/data/check_display/{name}.txt").read_text(), index=ScoreIndex(load_toolkit(score).getMEI()))
        page = render(score, annotations, measures=(1, 8), student_labels=labels)
        return [("render", capture.take(page), {})]
    if group == "pdf":
        from engine import read_pdf as reader
        sys.path.insert(0, str(root / "skill/scripts"))
        import read_pdf as skill_read_pdf

        score = reader.without_slurs(_read_pdf(root, name))
        spots = reader.problem_spots(score)
        found = []
        found.append(("preview-tall", capture.take(reader.preview(score, tall=True, spots=spots)), {"preview": True}))
        found.append(("preview", capture.take(reader.preview(score, spots=spots)), {"preview": True}))
        found.append(("pages", capture.take(skill_read_pdf.pages(score, spots)), {"preview": True}))
        return found
    raise ValueError(group)



@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    def grow(self, pad: float) -> "Box":
        return Box(self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)

    def touches(self, other: "Box", by: float = TOUCH) -> bool:
        return min(self.x1, other.x1) - max(self.x0, other.x0) > by and min(self.y1, other.y1) - max(self.y0, other.y0) > by

    def gap(self, other: "Box") -> float:
        return math.hypot(max(self.x0 - other.x1, other.x0 - self.x1, 0), max(self.y0 - other.y1, other.y0 - self.y1, 0))

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def rounded(self):
        return [round(self.x0), round(self.y0), round(self.x1), round(self.y1)]


@dataclass
class Shape:
    kind: str
    box: Box
    polygon: list[tuple[float, float]] | None = None
    segment: tuple[float, float, float, float, float] | None = None
    id: str = ""

    def hits(self, box: Box) -> bool:
        if not self.box.touches(box, 0):
            return False
        if self.segment:
            return _segment_box_distance(self.segment[:4], box) < self.segment[4] - TOUCH / 2
        if self.polygon:
            return _convex_overlap(self.polygon, box)
        return self.box.touches(box)


@dataclass
class Text:
    string: str
    ink: Box
    knockout: Box
    fill: str
    size: float
    x: float
    advance: float
    order: int
    group: int = 0


@dataclass
class Ellipse:
    cx: float
    cy: float
    rx: float
    ry: float
    stroke: float
    colour: str

    @property
    def box(self):
        return Box(self.cx - self.rx, self.cy - self.ry, self.cx + self.rx, self.cy + self.ry)

    def distance(self, box: Box) -> float:
        return max(0.0, self._distance(box) - self.stroke / 2)

    def _distance(self, box: Box) -> float:
        if box.contains(self.cx, self.cy):
            return 0.0
        best = math.inf
        for step in range(96):
            angle = 2 * math.pi * step / 96
            best = min(best, Box(*(2 * [self.cx + self.rx * math.cos(angle), self.cy + self.ry * math.sin(angle)])).gap(box))
        nx = min(max(self.cx, box.x0), box.x1)
        ny = min(max(self.cy, box.y0), box.y1)
        if ((nx - self.cx) / self.rx) ** 2 + ((ny - self.cy) / self.ry) ** 2 <= 1:
            return 0.0
        return best

    def stroke_hits(self, box: Box) -> bool:
        band = self.stroke / 2
        if not self.box.grow(band).touches(box, 0):
            return False
        for step in range(144):
            angle = 2 * math.pi * step / 144
            if box.grow(band - TOUCH / 2).contains(self.cx + self.rx * math.cos(angle), self.cy + self.ry * math.sin(angle)):
                return True
        return False


@dataclass
class Page:
    width: float
    top: float
    staff_lines: list[tuple[float, float, float, str]]
    music: list[Shape]
    noteheads: dict[str, Box]
    stems: dict[str, str]
    measures: list[tuple[str, Box]]
    systems: list[Box]
    voltas: list[Box]
    texts: list[Text]
    ellipses: list[Ellipse]
    marks: list[Shape]
    arrows: list[tuple[Shape, Shape | None]]
    index: object = None
    svg: str = ""
    extent: Box | None = None


def _font(root_fonts: Path, family: str, bold: bool, italic: bool, size: float):
    from PIL import ImageFont
    key = (family, bold, italic, round(size))
    if key not in _FONTS:
        names = {("Score Serif", False, False): "ScoreSerif-Regular.ttf", ("Score Serif", True, False): "ScoreSerif-Bold.ttf",
                 ("Score Serif", False, True): "ScoreSerif-Italic.ttf", ("Score Serif", True, True): "ScoreSerif-BoldItalic.ttf",
                 ("DejaVu Serif", False, False): "DejaVuSerif.ttf", ("DejaVu Serif", True, False): "DejaVuSerif-Bold.ttf"}
        name = names.get((family, bold, italic)) or names.get((family, bold, False)) or "ScoreSerif-Regular.ttf"
        _FONTS[key] = ImageFont.truetype(str(root_fonts / name), max(1, round(size)))
    return _FONTS[key]


_FONTS: dict = {}


def _ink(fonts: Path, string: str, x: float, y: float, size: float, family="Score Serif", bold=False, italic=False, anchor="start") -> tuple[Box, float]:
    font = _font(fonts, family, bold, italic, size)
    advance = font.getlength(string)
    x -= advance if anchor == "end" else advance / 2 if anchor == "middle" else 0
    left, top, right, bottom = font.getbbox(string, anchor="ls")
    return Box(x + left, y + top, x + right, y + bottom), advance


def _path_points(d: str) -> list[list[tuple[float, float]]]:
    out, current, x, y = [], [], 0.0, 0.0
    for command, args in re.findall(r"([MLHVCmlhvc])([^MLHVCmlhvcZz]*)", d):
        values = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", args)]
        step = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6}[command.upper()]
        for i in range(0, len(values), step):
            chunk = values[i:i + step]
            if len(chunk) < step:
                break
            rel = command.islower()
            if command.upper() in "ML":
                x, y = (x + chunk[0], y + chunk[1]) if rel else (chunk[0], chunk[1])
            elif command.upper() == "H":
                x = x + chunk[0] if rel else chunk[0]
            elif command.upper() == "V":
                y = y + chunk[0] if rel else chunk[0]
            else:
                x0, y0 = x, y
                c = [(x0 + chunk[j], y0 + chunk[j + 1]) if rel else (chunk[j], chunk[j + 1]) for j in (0, 2, 4)]
                for t in (0.25, 0.5, 0.75):
                    a, b, cc, dd = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3
                    current.append((a * x0 + b * c[0][0] + cc * c[1][0] + dd * c[2][0], a * y0 + b * c[0][1] + cc * c[1][1] + dd * c[2][1]))
                x, y = c[2]
            if command.upper() == "M" and i == 0:
                if len(current) > 1:
                    out.append(current)
                current = []
            current.append((x, y))
    if len(current) > 1:
        out.append(current)
    return out


def _segment_box_distance(segment, box: Box) -> float:
    x0, y0, x1, y1 = segment
    if any(box.contains(x0 + (x1 - x0) * t / 20, y0 + (y1 - y0) * t / 20) for t in range(21)):
        return 0.0
    best = math.inf
    for t in range(21):
        px, py = x0 + (x1 - x0) * t / 20, y0 + (y1 - y0) * t / 20
        best = min(best, Box(px, py, px, py).gap(box))
    return best


def _convex_overlap(polygon, box: Box) -> bool:
    inner = box.grow(-TOUCH / 2)
    rect = [(inner.x0, inner.y0), (inner.x1, inner.y0), (inner.x1, inner.y1), (inner.x0, inner.y1)]
    for shape in (polygon, rect):
        for (ax, ay), (bx, by) in zip(shape, shape[1:] + shape[:1]):
            nx, ny = ay - by, bx - ax
            if nx == 0 and ny == 0:
                continue
            p = [nx * px + ny * py for px, py in polygon]
            r = [nx * px + ny * py for px, py in rect]
            if max(p) <= min(r) or max(r) <= min(p):
                return False
    return True


MUSIC_KINDS = {
    "note": "notehead", "accid": "accidental", "stem": "stem", "dots": "dot", "rest": "rest", "mRest": "rest",
    "multiRest": "rest", "flag": "flag", "fermata": "fermata", "dynam": "dynamic", "hairpin": "hairpin",
    "artic": "articulation", "clef": "clef", "keyAccid": "key signature", "meterSig": "time signature",
    "tuplet": "tuplet", "trill": "ornament", "turn": "ornament", "mordent": "ornament", "arpeg": "arpeggio",
    "pedal": "pedal", "octave": "octave line", "breath": "breath mark", "label": "instrument name",
    "labelAbbr": "instrument name", "reh": "rehearsal mark", "fing": "fingering",
}


def parse_page(source: str, out: str, index, fonts: Path) -> Page:
    out_root = ET.fromstring(out)
    kept = set(re.findall(r'\bid="([^"]+)"', out))
    inner = next(e for e in out_root.iter(f"{SVG}svg") if e.get("class") == "definition-scale")
    width = float(inner.get("viewBox").split()[2])
    margin = next(g for g in out_root.iter(f"{SVG}g") if g.get("class") == "page-margin")
    top = float(re.search(r"translate\(\s*[-\d.]+[ ,]+([-\d.]+)", margin.get("transform", "translate(0,0)")).group(1))

    src = ET.fromstring(source)
    staff_lines, music, noteheads, stems, measures, systems, voltas = [], [], {}, {}, [], [], []

    def bbox(group):
        for child in group:
            if child.tag == f"{SVG}g" and "bounding-box" in child.get("class", ""):
                rect = child.find(f"{SVG}rect")
                if rect is not None:
                    x, y, w, h = (float(rect.get(k, 0)) for k in ("x", "y", "width", "height"))
                    if w > 0 and h > 0:
                        return Box(x, y, x + w, y + h)
        return None

    def visit(group, ancestors):
        classes = group.get("class", "").split()
        kind = classes[0] if classes else ""
        gid = group.get("id", "")
        if "bounding-box" in classes or (gid and gid not in kept):
            return
        box = bbox(group)
        if kind == "system" and box:
            systems.append(box)
        elif kind == "staff":
            measure = next((a[1] for a in ancestors[::-1] if a[0] == "measure"), None)
            if box and measure:
                known = dict(measures)
                if measure in known:
                    old = known[measure]
                    measures[[m for m, _ in measures].index(measure)] = (measure, Box(min(old.x0, box.x0), min(old.y0, box.y0), max(old.x1, box.x1), max(old.y1, box.y1)))
                else:
                    measures.append((measure, box))
            for path in group.findall(f"{SVG}path"):
                for line in _path_points(path.get("d", "")):
                    (x0, y0), (x1, y1) = line[0], line[-1]
                    if abs(y0 - y1) < 1:
                        staff_lines.append((min(x0, x1), max(x0, x1), y0, "staff"))
        elif kind == "ledgerLines":
            for path in group.findall(f"{SVG}path"):
                for line in _path_points(path.get("d", "")):
                    (x0, y0), (x1, y1) = line[0], line[-1]
                    staff_lines.append((min(x0, x1), max(x0, x1), y0, "ledger"))
        elif kind == "beam":
            for polygon in group.findall(f"{SVG}polygon"):
                points = [tuple(map(float, p.split(","))) for p in polygon.get("points", "").split()]
                xs, ys = [p[0] for p in points], [p[1] for p in points]
                music.append(Shape("beam", Box(min(xs), min(ys), max(xs), max(ys)), polygon=points, id=gid))
        elif kind == "barLine":
            for path in group.findall(f"{SVG}path"):
                for line in _path_points(path.get("d", "")):
                    (x0, y0), (x1, y1) = line[0], line[-1]
                    half = float(path.get("stroke-width", 27)) / 2
                    music.append(Shape("barline", Box(min(x0, x1) - half, min(y0, y1), max(x0, x1) + half, max(y0, y1)),
                                       segment=(x0, y0, x1, y1, half), id=gid))
        elif kind == "voltaBracket":
            points = [p for path in group.findall(f"{SVG}path") for line in _path_points(path.get("d", "")) for p in line]
            if points:
                voltas.append(Box(min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)))
        elif kind in ("slur", "tie"):
            for path in group.findall(f"{SVG}path"):
                for line in _path_points(path.get("d", "")):
                    for (x0, y0), (x1, y1) in zip(line, line[1:]):
                        music.append(Shape(kind, Box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)).grow(10),
                                           segment=(x0, y0, x1, y1, 20), id=gid))
        elif kind == "stem" and box:
            music.append(Shape("stem", box, id=gid))
            path = group.find(f"{SVG}path")
            found = re.match(r"M([-\d.]+) ([-\d.]+) L[-\d.]+ ([-\d.]+)", path.get("d", "")) if path is not None else None
            if found:
                direction = "up" if float(found.group(3)) < float(found.group(2)) else "down"
                for owner in ancestors[::-1]:
                    if owner[0] in ("note", "chord"):
                        stems[owner[1]] = direction
                        break
        elif kind == "note" and box:
            noteheads[gid] = box
            music.append(Shape("notehead", box, id=gid))
            for owner in ancestors[::-1]:
                if owner[0] == "chord" and owner[1] in stems:
                    stems.setdefault(gid, stems[owner[1]])
                    break
        elif kind in MUSIC_KINDS and box:
            music.append(Shape(MUSIC_KINDS[kind], box, id=gid))
        elif kind == "text" and box and not any(a[0] in ("mNum", "syl") for a in ancestors):
            music.append(Shape("score text", box, id=gid))
        for child in group:
            if child.tag == f"{SVG}g":
                visit(child, ancestors + [(kind, gid)])
            elif child.tag == f"{SVG}text" and any(a[0] in ("syl", "mNum") for a in ancestors + [(kind, gid)]):
                for span in child.iter(f"{SVG}tspan"):
                    size = span.get("font-size", "")
                    if span.text and span.text.strip() and size.endswith("px") and float(size[:-2]) > 0:
                        ink, _ = _ink(fonts, span.text, float(child.get("x", 0)), float(child.get("y", 0)), float(size[:-2]),
                                      italic=span.get("font-style") == "italic", anchor=child.get("text-anchor", "start"))
                        music.append(Shape("lyric" if any(a[0] == "syl" for a in ancestors + [(kind, gid)]) else "bar number (Verovio)", ink, id=gid))

    page_margin = next(g for g in src.iter(f"{SVG}g") if g.get("class") == "page-margin")
    for child in page_margin:
        if child.tag == f"{SVG}g":
            visit(child, [])
    for note_id in noteheads:
        stems.setdefault(note_id, stems.get(note_id))

    over = next((g for g in out_root.iter(f"{SVG}g") if g.get("class") == "analysis-over"), None)
    texts, ellipses, marks, arrows = [], [], [], []
    halos: dict[tuple, float] = {}
    lines, heads = [], []
    order = 0
    for element in (over.iter() if over is not None else []):
        tag = element.tag.replace(SVG, "")
        if tag == "text" and element.text:
            x, y = float(element.get("x", 0)), float(element.get("y", 0))
            size = float(element.get("font-size", "330px").rstrip("px"))
            key = (element.text, round(x), round(y))
            if element.get("fill", "").lower() == WHITE and element.get("stroke", "").lower() == WHITE:
                halos[key] = float(element.get("stroke-width", 0)) / 2
                continue
            ink, advance = _ink(fonts, element.text, x, y, size, element.get("font-family", "Score Serif"),
                                element.get("font-weight") == "bold", element.get("font-style") == "italic",
                                element.get("text-anchor", "start"))
            texts.append(Text(element.text, ink, ink.grow(halos.get(key, 0)), element.get("fill", "").upper(), size, x, advance, order))
            order += 1
        elif tag == "ellipse":
            ellipses.append(Ellipse(float(element.get("cx")), float(element.get("cy")), float(element.get("rx")), float(element.get("ry")),
                                    float(element.get("stroke-width", 0)), (element.get("stroke") or "").upper()))
        elif tag == "circle":
            cx, cy, r = float(element.get("cx")), float(element.get("cy")), float(element.get("r"))
            filled = element.get("fill", "none") not in ("none", "")
            kind = "callout disc" if filled else "numbered circle"
            marks.append(Shape(kind, Box(cx - r, cy - r, cx + r, cy + r)))
        elif tag == "line":
            x0, y0, x1, y1 = (float(element.get(k)) for k in ("x1", "y1", "x2", "y2"))
            half = float(element.get("stroke-width", 0)) / 2
            shape = Shape("analysis line", Box(min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half),
                          segment=(x0, y0, x1, y1, half), id=(element.get("stroke") or "").upper())
            lines.append(shape)
        elif tag == "polygon":
            points = [tuple(map(float, p.split(","))) for p in element.get("points", "").split()]
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            heads.append(Shape("arrowhead", Box(min(xs), min(ys), max(xs), max(ys)), polygon=points, id=(element.get("fill") or "").upper()))
        elif tag == "path":
            half = float(element.get("stroke-width", 26)) / 2
            for line in _path_points(element.get("d", "")):
                for (x0, y0), (x1, y1) in zip(line, line[1:]):
                    marks.append(Shape("underline" if "inversion-underline" in element.get("class", "") else "analysis bracket", Box(min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half),
                                       segment=(x0, y0, x1, y1, half)))
        elif tag == "rect":
            x, y, w, h = (float(element.get(k, 0)) for k in ("x", "y", "width", "height"))
            marks.append(Shape("analysis box", Box(x, y, x + w, y + h)))
    used = set()
    for line in lines:
        x0, y0, x1, y1, _ = line.segment
        head = next((h for h in heads if id(h) not in used and h.id == line.id and line.box.grow(200).touches(h.box, 0)
                     and min(abs(px - x1) + abs(py - y1) for px, py in h.polygon) < 200), None)
        if head:
            used.add(id(head))
        if head and abs(x0 - x1) < 1 and abs(y1 - y0) < 700 and line.id == ERROR:
            arrows.append((line, head))
        else:
            marks.append(line)
            if head:
                marks.append(head)
    marks += [h for h in heads if id(h) not in used]
    group = 0
    for previous, text in zip([None] + texts, texts):
        if previous is None or text.fill != previous.fill or previous.fill == ERROR or not (
                previous.x - 0.6 * previous.size <= text.x <= previous.x + previous.advance + 3
                and abs(text.ink.y1 - previous.ink.y1) <= max(text.size, previous.size)):
            group += 1
        text.group = group
    return Page(width, top, staff_lines, music, noteheads, stems, measures, systems, voltas, texts, ellipses, marks, arrows, index, out)



@dataclass
class Violation:
    rule: str
    item: str
    entry: str
    page: int
    bar: object
    message: str
    box: list = field(default_factory=list)

    def line(self) -> str:
        return f"{self.rule:12s} {self.item:34s} {self.entry:12s} p{self.page} bar {self.bar}: {self.message}"


def bar_at(page: Page, box: Box):
    if not page.measures:
        return "?"
    mid, _ = min(page.measures, key=lambda m: (0 if m[1].contains(box.cx, box.cy) else 1, m[1].gap(box)))
    try:
        return page.index.locate_segment(mid)[0].number
    except Exception:
        return mid


def crosses_lines(page: Page, ink: Box) -> list[tuple[float, float, float, str]]:
    return [line for line in page.staff_lines
            if min(ink.x1, line[1]) - max(ink.x0, line[0]) > TOUCH and ink.y0 + 2 < line[2] < ink.y1 - 2]


def _own_container(text: Text, mark: Shape) -> bool:
    return mark.kind in ("callout disc", "numbered circle", "analysis box") and mark.box.contains(text.ink.cx, text.ink.cy)


def check_page(page: Page, item: str, entry: str, number: int, context: dict) -> list[Violation]:
    found = []

    def add(rule, box, message):
        found.append(Violation(rule, item, entry, number, bar_at(page, box), message, box.rounded()))

    def describe(text):
        return f'"{text.string}" at ({round(text.ink.cx)}, {round(text.ink.cy)})'

    arrow_codes = set()
    for text in page.texts:
        crossed = crosses_lines(page, text.ink)
        if crossed:
            kinds = sorted({kind for *_, kind in crossed})
            add("staff-line", text.ink, f"{describe(text)} crosses {len(crossed)} {'/'.join(kinds)} line(s)")
    for text in page.texts:
        hit = sorted({shape.kind for shape in page.music if shape.hits(text.knockout)})
        if hit:
            add("collision", text.knockout, f"{describe(text)} touches {', '.join(hit)}")
        for other in page.texts:
            if other.order > text.order and other.group != text.group and (other.knockout.touches(text.ink) or text.knockout.touches(other.ink)):
                add("collision", text.ink, f"{describe(text)} touches analysis text {describe(other)}")
        marks = [mark for mark in page.marks if not _own_container(text, mark) and not _leader(text, mark) and mark.hits(text.knockout)]
        marks += [shape for shaft, head in page.arrows for shape in (shaft, head) if shape and shape.hits(text.knockout)]
        rings = [ring for ring in page.ellipses if ring.stroke_hits(text.knockout)]
        if marks or rings:
            add("collision", text.knockout, f"{describe(text)} touches {', '.join(sorted({m.kind for m in marks} | ({'ring'} if rings else set())))}")
    for shaft, head in page.arrows:
        for shape in (shaft, head):
            hit = sorted({m.kind for m in page.music if m.kind != "barline" and _shapes_touch(shape, m)})
            if hit:
                add("collision", shape.box, f"tendency arrow at ({round(shaft.box.cx)}, {round(shaft.box.cy)}) touches {', '.join(hit)}")
                break
    for mark in page.marks:
        if mark.kind == "analysis line" and mark.id == ERROR:
            hit = sorted({m.kind for m in page.music if m.kind in ("dot", "accidental") and _shapes_touch(mark, m)})
            if hit:
                add("collision", mark.box, f"line at ({round(mark.box.cx)}, {round(mark.box.cy)}) crosses {', '.join(hit)}")
        if mark.kind in ("callout disc", "analysis box"):
            hit = sorted({m.kind for m in page.music if m.hits(mark.box)})
            if hit:
                add("collision", mark.box, f"{mark.kind} at ({round(mark.box.cx)}, {round(mark.box.cy)}) touches {', '.join(hit)}")
    for shaft, head in page.arrows:
        x0, y0, x1, y1, half = shaft.segment
        line = Box(x0 - half, min(y0, y1, *(p[1] for p in head.polygon)) if head else min(y0, y1), x0 + half,
                   max(y0, y1, *(p[1] for p in head.polygon)) if head else max(y0, y1))
        crossed = crosses_lines(page, line)
        code = _arrow_code(page, shaft)
        code_crossed = crosses_lines(page, code.ink) if code else []
        if code:
            arrow_codes.add(id(code))
        if crossed or code_crossed:
            parts = ([f"arrow crosses {len(crossed)} line(s)"] if crossed else []) + ([f"its R crosses {len(code_crossed)} line(s)"] if code_crossed else [])
            add("arrow-staff", line, f"tendency arrow at ({round(x0)}, {round((y0 + y1) / 2)}) on the staff: {'; '.join(parts)}")
    for ring in page.ellipses:
        if ring.colour != ERROR:
            continue
        head = min(page.noteheads.values(), key=lambda b: abs(b.cx - ring.cx) + abs(b.cy - ring.cy))
        touched = [m for m in page.music if m.kind in RING_CLEAR and ring.stroke_hits(m.box.grow(RING_ROOM))
                   and not (m.kind == "notehead" and ring.box.contains(m.box.cx, m.box.cy))]
        beside = [m for m in touched if m.box.y0 < head.y1 and m.box.y1 > head.y0]
        own = [m for m in beside if m.kind == "accidental" and m.box.x1 <= head.x0 + 20
               or m.kind == "dot" and head.x1 - 10 <= m.box.x0 < head.x1 + 150]
        hit = sorted({m.kind for m in touched if not any(m is o for o in own)})
        if hit:
            add("collision", ring.box, f"ring at ({round(ring.cx)}, {round(ring.cy)}) within {RING_ROOM} of {', '.join(hit)}")
        if own:
            add("ring-own", ring.box, f"ring at ({round(ring.cx)}, {round(ring.cy)}) within {RING_ROOM} of its own note's {' and '.join(sorted({m.kind for m in own}))}")
    if context.get("marks"):
        found += check_marks(page, item, entry, number, context["marks"], context.get("excerpt", False))
    if context.get("preview"):
        for text in page.texts:
            if not re.fullmatch(r"\d+", text.string):
                continue
            for volta in page.voltas:
                if min(text.ink.x1, volta.x1) - max(text.ink.x0, volta.x0) > 0 and text.ink.y1 > volta.y0 and text.ink.y0 < volta.y1 + 400:
                    add("bar-number", text.ink, f"bar number {describe(text)} is not above the ending bracket at y {round(volta.y0)}")
        everything = [s.box for s in page.music] + [t.ink for t in page.texts] + [m.box for m in page.marks] + \
                     [Box(x0, y, x1, y) for x0, x1, y, _ in page.staff_lines]
        first = min(b.y0 for b in everything) + page.top
        if first < TOP_MARGIN * page.width:
            highest = min(everything, key=lambda b: b.y0)
            add("top-margin", highest, f"first ink {round(first)} units below the page top, under the {round(TOP_MARGIN * page.width)} the margin needs")
    return found


def _leader(text: Text, mark: Shape) -> bool:
    if mark.kind == "underline":
        return min(text.ink.x1, mark.box.x1) - max(text.ink.x0, mark.box.x0) > -60 and -120 <= mark.box.cy - text.ink.y1 < 150
    if not mark.segment or mark.segment[4] > 12:
        return False
    x0, y0, x1, y1, _ = mark.segment
    return min(Box(x0, y0, x0, y0).gap(text.ink), Box(x1, y1, x1, y1).gap(text.ink)) < 80


def _shapes_touch(shape: Shape, other: Shape) -> bool:
    if shape.segment and not other.segment and not other.polygon:
        return other.hits(shape.box) and _segment_box_distance(shape.segment[:4], other.box) < shape.segment[4] - TOUCH / 2
    if shape.polygon and not other.segment and not other.polygon:
        return _convex_overlap(shape.polygon, other.box)
    if other.polygon:
        return other.hits(shape.box)
    return other.hits(shape.box)


def _arrow_code(page: Page, shaft: Shape) -> Text | None:
    codes = [t for t in page.texts if t.string == "R" and t.fill == ERROR]
    return min(codes, key=lambda t: t.ink.gap(shaft.box), default=None) if codes else None


CODE_RATIO = 1.5
RING_ROOM = 40
RING_CLEAR = {"notehead", "accidental", "dot", "rest", "flag", "fermata", "dynamic", "articulation", "ornament",
              "lyric", "score text", "tie", "slur"}


def check_marks(page: Page, item: str, entry: str, number: int, marks: list[dict], excerpt: bool = False) -> list[Violation]:
    found = []
    index = page.index

    def add(rule, box, message):
        found.append(Violation(rule, item, entry, number, bar_at(page, box), message, box.rounded()))

    def note(ref):
        event = index.find_note(**ref)
        return event, page.noteheads.get(event.id)

    def where(ref):
        return f"m{ref['measure']} b{ref['beat']:g} staff {ref['staff']} {ref['pitch']}"

    unique: dict[tuple, dict] = {}
    for mark in marks:
        if mark["type"] != "voice_leading":
            continue
        first, first_head = note(mark["from_note"])
        second, second_head = note(mark["to_note"]) if mark.get("to_note") else (None, None)
        if excerpt and first_head is None:
            continue
        if excerpt and second and second_head is None and not (mark["kind"] == "arrow" and mark["label"] == "R"):
            add("excerpt-edge", first_head, f"{mark['kind']} {mark['label']!r} from {where(mark['from_note'])} goes to {where(mark['to_note'])}, outside the bars drawn")
            continue
        entry_ = unique.setdefault((mark["kind"], first.id, second.id if second else None), {**mark, "labels": [], "spots": set()})
        entry_["spots"].add(mark["spot"])
        if mark["label"] and mark["label"] not in entry_["labels"]:
            entry_["labels"].append(mark["label"])

    rings = []
    for (kind, first_id, _), mark in unique.items():
        head = page.noteheads.get(first_id)
        if head is None:
            add("dropped", Box(0, 0, 0, 0), f"{kind} at {where(mark['from_note'])}: its note is not on the page")
            continue
        if kind == "ring":
            ring = next((e for e in page.ellipses if e.colour == ERROR and abs(e.cx - head.cx) <= 3 and abs(e.cy - head.cy) <= 3), None)
            if ring is None:
                add("dropped", head, f"ring at {where(mark['from_note'])} not drawn")
                continue
            rings.append((ring, " ".join(mark["labels"]), mark["spots"], first_id, mark))
        elif kind == "arrow" and "R" in mark["labels"]:
            near = [a for a in page.arrows if abs(a[0].box.cx - head.cx) < 700 and abs(a[0].box.cy - head.cy) < 1500]
            if not near:
                add("dropped", head, f"tendency arrow at {where(mark['from_note'])} not drawn")
            elif not any(_arrow_code(page, shaft) and _arrow_code(page, shaft).ink.gap(shaft.box) < 400 for shaft, _ in near):
                add("dropped", head, f"the R of the tendency arrow at {where(mark['from_note'])} not drawn by its arrow")
        elif kind in ("line", "arrow"):
            drawn = [m for m in page.marks if m.kind == "analysis line" and m.segment and head.x1 + 47 <= m.segment[0] <= head.x1 + 300
                     and abs(m.segment[1] - head.cy) <= 3]
            if not drawn:
                add("dropped", head, f"{kind} from {where(mark['from_note'])} not drawn")
        elif kind == "bracket":
            if not any(m.kind == "analysis bracket" and m.box.gap(head) < 400 for m in page.marks):
                add("dropped", head, f"bracket at {where(mark['from_note'])} not drawn")
    pairs: dict[tuple, list] = {}
    for (kind, first_id, second_id), mark in unique.items():
        if kind == "line" and mark["labels"]:
            a, b = index.find_note(**mark["from_note"]), index.find_note(**mark["to_note"])
            pairs.setdefault((a.segment, a.onset, b.segment, b.onset), []).append(mark)
    def system_of(box):
        return min(range(len(page.systems)), key=lambda i: page.systems[i].gap(box)) if page.systems else 0
    listed: dict[tuple, int] = {}
    for group in pairs.values():
        labels = {label for mark in group for label in mark["labels"]}
        head = page.noteheads.get(index.find_note(**group[0]["from_note"]).id)
        for label in labels:
            listed[(system_of(head), label)] = listed.get((system_of(head), label), 0) + 1
    drawn: dict[tuple, int] = {}
    for text in page.texts:
        if text.fill == ERROR:
            for token in text.string.split():
                drawn[(system_of(text.ink), token)] = drawn.get((system_of(text.ink), token), 0) + 1
    for (system, label), count in listed.items():
        if drawn.get((system, label), 0) < count:
            add("dropped", page.systems[system] if page.systems else Box(0, 0, 0, 0),
                f'"{label}" listed {count} time(s) on system {system + 1}, drawn {drawn.get((system, label), 0)}')
    shown = {bar_at(page, box) for _, box in page.measures}
    callouts = sorted({m["number"] for m in marks if m["type"] == "callout" and (not excerpt or m["at"]["measure"] in shown)})
    if excerpt:
        placed = {m["number"]: m["at"]["measure"] for m in marks if m["type"] == "callout"}
        for spot in sorted({spot for mark in unique.values() for spot in mark["spots"]}):
            if spot in placed and placed[spot] not in shown:
                add("excerpt-edge", Box(0, 0, 0, 0), f"marks of callout {spot} are drawn, but the callout is at bar {placed[spot]}, outside the bars drawn")
    numbers = [t.string for t in page.texts if any(mk.kind == "callout disc" and mk.box.contains(t.ink.cx, t.ink.cy) for mk in page.marks)]
    for n in callouts:
        if numbers.count(str(n)) != 1:
            add("dropped", Box(0, 0, 0, 0), f"callout {n} drawn {numbers.count(str(n))} times")
    codes = [t for t in page.texts if t.fill == ERROR]
    labelled = [r for r in rings if r[1]]
    pairs_found = []
    taken = set()
    candidates = sorted(((ring[0].distance(code.ink), i, j) for i, ring in enumerate(labelled) for j, code in enumerate(codes)
                         if code.string == ring[1]), key=lambda c: c[0])
    matched = {}
    for distance, i, j in candidates:
        if i in matched or j in taken:
            continue
        matched[i] = j
        taken.add(j)
    for i, (ring, word, spots, head_id, mark) in enumerate(labelled):
        if i not in matched:
            add("dropped", ring.box, f'code "{word}" of the ring at {where(mark["from_note"])} not drawn')
            continue
        code = codes[matched[i]]
        own = ring.distance(code.ink)
        partners = [r for r in rings if not r[1] and r[2] & spots]
        partner_heads = {r[3] for r in partners}
        rivals = [(f"ring at ({round(r[0].cx)}, {round(r[0].cy)})", r[0].distance(code.ink)) for r in rings
                  if r[0] is not ring and not any(r is p for p in partners)]
        rivals += [(f"notehead at ({round(box.cx)}, {round(box.cy)})", box.gap(code.ink)) for nid, box in page.noteheads.items()
                   if nid != head_id and nid not in partner_heads and not (((box.cx - ring.cx) / ring.rx) ** 2 + ((box.cy - ring.cy) / ring.ry) ** 2 <= 1)]
        nearer = [(what, d) for what, d in rivals if d < CODE_RATIO * own]
        if nearer:
            what, d = min(nearer, key=lambda r: r[1])
            add("ring-code", code.ink, f'"{word}" of the ring at {where(mark["from_note"])} is {round(own)} from its ring but {round(d)} from the {what}')
    return found



def bars_per_page(pages) -> list[int]:
    return [len(re.findall(r'class="measure"', out)) for _, out, _ in pages]


def run_item(root: str, group: str, name: str, crops: str | None) -> dict:
    root = Path(root)
    started = time.time()
    item = f"{group}/{name}"
    result = {"item": item, "violations": [], "pins": {}, "error": None}
    try:
        import verovio
        verovio.enableLog(False)
        from engine import text as engine_text
        fonts = engine_text.FONT_DIR
        for entry, pages, context in draw(root, group, name):
            if group == "pdf":
                result["pins"][entry] = bars_per_page(pages)
            for number, (source, out, index) in enumerate(pages, 1):
                page = parse_page(source, out, index, fonts)
                found = check_page(page, item, entry, number, context)
                result["violations"] += [v.__dict__ for v in found]
                if crops and found:
                    _crop(out, page, found, Path(crops), item, entry, number)
    except Exception as error:
        import traceback
        result["error"] = f"{type(error).__name__}: {error}\n{traceback.format_exc(limit=-3)}"
    result["seconds"] = round(time.time() - started, 2)
    return result


def _crop(svg: str, page: Page, found: list[Violation], folder: Path, item: str, entry: str, number: int) -> None:
    from PIL import ImageDraw
    from engine.render import Engraving

    folder.mkdir(parents=True, exist_ok=True)
    outer = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
    pixels = 2800
    image = Engraving([svg])._raster(1, pixels)
    scale = image.width / page.width
    margin = re.search(r'class="page-margin" transform="translate\(([-\d.]+)[ ,]+([-\d.]+)', svg)
    left, top = float(margin.group(1)), float(margin.group(2))
    for n, violation in enumerate(found):
        x0, y0, x1, y1 = violation.box
        if x1 <= x0 and y1 <= y0:
            continue
        box = [(x0 + left) * scale, (y0 + top) * scale, (x1 + left) * scale, (y1 + top) * scale]
        pad = 900 * scale
        crop = image.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(image.width, box[2] + pad), min(image.height, box[3] + pad))).copy()
        ImageDraw.Draw(crop).rectangle([box[0] - max(0, box[0] - pad) - 6, box[1] - max(0, box[1] - pad) - 6,
                                        box[2] - max(0, box[0] - pad) + 6, box[3] - max(0, box[1] - pad) + 6], outline=(0, 140, 255), width=1)
        crop = crop.resize((crop.width * 2, crop.height * 2))
        safe = re.sub(r"[^\w.-]+", "_", f"{item}-{entry}-p{number}-bar{violation.bar}-{violation.rule}-{n}")
        crop.save(folder / f"{safe}.png")


def compare_pins(results: list[dict], baseline: dict) -> list[dict]:
    found = []
    for result in results:
        name = result["item"].split("/", 1)[1]
        for entry, bars in result["pins"].items():
            pinned = baseline.get("readings", {}).get(name, {}).get(entry)
            if pinned is None:
                found.append(Violation("pages", result["item"], entry, 0, "-", f"not pinned: {len(bars)} pages {bars}").__dict__)
            elif len(pinned) != len(bars) or pinned[-1] != bars[-1]:
                found.append(Violation("pages", result["item"], entry, len(bars), "-",
                                       f"{len(pinned)} pages {pinned} pinned, now {len(bars)} pages {bars}").__dict__)
    return found


def run(root: Path, only: list[str] | None = None, jobs: int | None = None, crops: str | None = None) -> dict:
    items = [(g, n) for g, n in corpus(root) if not only or any(o in f"{g}/{n}" for o in only)]
    started = time.time()
    jobs = jobs or min(len(items), os.cpu_count() or 1)
    if jobs > 1:
        import multiprocessing
        with ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("fork")) as pool:
            results = list(pool.map(run_item, [str(root)] * len(items), [g for g, _ in items], [n for _, n in items], [crops] * len(items)))
    else:
        results = [run_item(str(root), g, n, crops) for g, n in items]
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    pins = compare_pins(results, baseline)
    return {"root": str(root), "results": results, "pins": pins, "seconds": round(time.time() - started, 1)}


def repin(report: dict, ref: str) -> None:
    old = json.loads(BASELINE.read_text()) if BASELINE.exists() else {"readings": {}}
    readings = {r["item"].split("/", 1)[1]: r["pins"] for r in report["results"] if r["pins"]}
    for name, pins in sorted(readings.items()):
        for entry, bars in pins.items():
            before = old.get("readings", {}).get(name, {}).get(entry)
            if before != bars:
                print(f"repin {name} {entry}: {before} -> {bars}")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    merged = {**old.get("readings", {}), **readings}
    BASELINE.write_text(json.dumps({"ref": ref, "bars_per_page": "bars on each page, per entry point", "readings": merged}, indent=1) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=HERE, help="checkout to check (default: this one)")
    parser.add_argument("--only", nargs="*", help="items whose group/name contains any of these")
    parser.add_argument("--jobs", type=int, help="processes (default: one per item, up to the CPU count)")
    parser.add_argument("--crops", help="folder for a crop of every violation (default out/display-check/<ref>)")
    parser.add_argument("--no-crops", action="store_true")
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--repin", action="store_true", help="rewrite the page baseline from --root")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    import subprocess
    ref = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    crops = None if args.no_crops else (args.crops or str(HERE / "out" / "display-check" / ref))
    report = run(root, args.only, args.jobs, crops)
    report["ref"] = ref
    violations = [v for r in report["results"] for v in r["violations"]] + report["pins"]
    for v in violations:
        print(Violation(**v).line())
    errors = [r for r in report["results"] if r["error"]]
    for r in errors:
        print(f"ERROR {r['item']}: {r['error']}")
    counts: dict[str, int] = {}
    for v in violations:
        counts[v["rule"]] = counts.get(v["rule"], 0) + 1
    print(f"\n{ref}: {len(report['results'])} items, {len(violations)} violations {counts}, {len(errors)} errors, "
          f"{report['seconds']} s" + (f"; crops in {crops}" if crops and violations else ""))
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    if args.repin:
        repin(report, ref)
    return 1 if violations or errors else 0


if __name__ == "__main__":
    sys.exit(main())
