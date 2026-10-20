from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import replace
from fractions import Fraction

from engine.reduce import midi
from engine.score import ScoreIndex

SLUR = re.compile(r'<g id="([^"]+)" class="slur"[^>]*>\s*<path d="M([-\d.]+),([-\d.]+) C([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+)')
BOX = re.compile(r'class="(stem|note|tupletNum|tie) bounding-box"[^>]*>\s*<rect x="([-\d.]+)" y="([-\d.]+)" height="([-\d.]+)" width="([-\d.]+)"')
POLYGON = re.compile(r'<polygon points="([^"]+)"')
SVG = "{http://www.w3.org/2000/svg}"
END_ZONE = 0.15
CLEAR = 25
STEP = 40
UNIT = 180


def untangle(toolkit, relayout: Callable[[str], None]) -> None:
    mei = toolkit.getMEI()
    sides = _sides(mei, [toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)])
    for slur, side in sides.items():
        mei = _set(mei, slur, "curvedir", side)
    if sides:
        relayout(mei)
    lifted: dict[str, int] = {}
    for _ in range(4):
        lift = {slur: need for slur, need in _collisions(toolkit).items() if need > 0}
        if not lift:
            return
        for slur, (height, need) in _heights(toolkit, lift).items():
            step = math.ceil(need / UNIT)
            lifted[slur] = lifted[slur] + step if slur in lifted else math.ceil((height + need) / UNIT)
            mei = _set(mei, slur, "bulge", f"{lifted[slur]} 50")
        relayout(mei)


def _sides(mei: str, svgs: list[str]) -> dict[str, str]:
    index = ScoreIndex(mei)
    events, start = {}, {}
    time = Fraction(0)
    for measure in index.measures:
        for event in measure.events:
            events[event.id], start[event.id] = event, time + event.onset
        time += measure.length
    written = {id: (event.staff, event.layer) for id, event in events.items()}
    for match in re.finditer(r'<(chord|note)\b[^>]*\bstaff="(\d+)"(?:[^>]*/>|.*?</\1>)', mei, flags=re.S):
        staff = match.group(2)
        for id in re.findall(r'<note\b[^>]*xml:id="([^"]+)"', match.group(0)):
            if id in events:
                events[id] = replace(events[id], staff=int(staff))
    first_note = {chord: note for chord, note in re.findall(r'<chord\b[^>]*xml:id="([^"]+)"[^>]*>\s*<note\b[^>]*xml:id="([^"]+)"', mei)}
    crossing = []
    for first, last in re.findall(r'<beamSpan\b[^>]*startid="#([^"]+)"[^>]*endid="#([^"]+)"', mei):
        first, last = first_note.get(first, first), first_note.get(last, last)
        if first in events and last in events and events[first].staff != events[last].staff and written[first] == written[last]:
            crossing.append((written[first], start[first], start[last]))
    stems = _stem_directions(svgs)
    drawn = {slur for svg in svgs for slur, *_ in SLUR.findall(svg)}
    sides = {}
    for tag in re.findall(r"<slur\b[^>]*/>", mei):
        ids = dict(re.findall(r'\b(xml:id|startid|endid)="#?([^"]+)"', tag))
        if ids.get("xml:id") not in drawn or "startid" not in ids or "endid" not in ids:
            continue
        a, b = (events.get(first_note.get(ids[key], ids[key])) for key in ("startid", "endid"))
        if not a or not b or a.staff != b.staff or start[b.id] < start[a.id]:
            continue
        t0, t1 = start[a.id], start[b.id]
        voice = [e for e in events.values() if e.staff == a.staff and e.layer == a.layer and e.pitch and t0 <= start[e.id] <= t1]
        others = [
            e for e in events.values()
            if e.staff == a.staff and e.layer != a.layer and e.pitch and start[e.id] < t1 + (b.duration or 0) and start[e.id] + e.duration > t0
        ]
        if any(written[a.id] == line and written[b.id] == line and t_first <= t0 and t1 <= t_last for line, t_first, t_last in crossing):
            side = "above"
        elif others:
            side = "above" if _top_line(voice, start) >= _top_line(others, start) else "below"
        else:
            directions = {stems[e.id] for e in voice if e.id in stems}
            side = "below" if directions == {"up"} else "above"
        sides[ids["xml:id"]] = side
    return sides


def _top_line(events, start) -> float:
    tops: dict[Fraction, int] = {}
    for event in events:
        tops[start[event.id]] = max(tops.get(start[event.id], 0), midi(event.pitch))
    return sum(tops.values()) / len(tops)


def _stem_directions(svgs: list[str]) -> dict[str, str]:
    result = {}
    for svg in svgs:
        root = ET.fromstring(svg)
        for group in root.iter(f"{SVG}g"):
            kind = group.get("class", "").split()
            if "note" not in kind and "chord" not in kind:
                continue
            stem = next((child for child in group if child.get("class") == "stem"), None)
            if stem is None:
                continue
            stem_box = _rect(stem, "stem")
            heads = [box for head in group.iter(f"{SVG}g") if (box := _rect(head, "note"))]
            if not stem_box or not heads:
                continue
            direction = "up" if stem_box[1] < min(head[1] for head in heads) - 10 else "down"
            notes = [group] if "note" in kind else [child for child in group.iter(f"{SVG}g") if child.get("class") == "note"]
            for note in notes:
                result[note.get("id")] = direction
    return result


def _rect(group: ET.Element, kind: str) -> tuple[float, float, float, float] | None:
    for box in group:
        if box.get("class") == f"{kind} bounding-box":
            rect = box.find(f"{SVG}rect")
            if rect is not None:
                return tuple(float(rect.get(key)) for key in ("x", "y", "width", "height"))
    return None


def _set(mei: str, slur: str, attribute: str, value: str) -> str:
    def replace(match: re.Match) -> str:
        tag = re.sub(rf'\s+{attribute}="[^"]*"', "", match.group(0))
        return tag.replace("<slur ", f'<slur {attribute}="{value}" ', 1)

    return re.sub(rf'<slur\b[^>]*xml:id="{re.escape(slur)}"[^>]*/>', replace, mei, count=1)


def _curves(toolkit):
    for page in range(1, toolkit.getPageCount() + 1):
        svg = toolkit.renderToSVG(page)
        boxes = [(kind, float(x), float(y), float(w), float(h)) for kind, x, y, h, w in BOX.findall(svg)]
        beams = [[tuple(map(float, point.split(","))) for point in points.split()] for points in POLYGON.findall(svg)]
        for slur, *numbers in SLUR.findall(svg):
            yield slur, tuple(map(float, numbers)), boxes, beams


def _collisions(toolkit) -> dict[str, float]:
    result = {}
    for slur, (x0, y0, x1, y1, x2, y2, x3, y3), boxes, beams in _curves(toolkit):
        steps = max(int(abs(x3 - x0) / STEP), 10)
        points = [_bezier(t / steps, x0, y0, x1, y1, x2, y2, x3, y3) for t in range(steps + 1)]
        middle = [p for p in points if x0 + (x3 - x0) * END_ZONE < p[0] < x3 - (x3 - x0) * END_ZONE]
        above = points[len(points) // 2][1] < (y0 + y3) / 2
        obstacles = [b for b in boxes if b[0] != "note" or not any(b[1] - CLEAR <= x <= b[1] + b[3] + CLEAR for x in (x0, x3))]
        need = 0.0
        for px, py in middle:
            for _, bx, by, bw, bh in obstacles:
                if bx - CLEAR <= px <= bx + bw + CLEAR and by - CLEAR <= py <= by + bh + CLEAR:
                    need = max(need, py - (by - CLEAR) if above else (by + bh + CLEAR) - py)
            for beam in beams:
                if any(_inside(px, py + dy, beam) for dy in (-CLEAR, 0, CLEAR)):
                    ys = [y for _, y in beam]
                    need = max(need, py - (min(ys) - CLEAR) if above else (max(ys) + CLEAR) - py)
        result[slur] = need
    return result


def _heights(toolkit, wanted: dict[str, float]) -> dict[str, tuple[float, float]]:
    result = {}
    for slur, (x0, y0, x1, y1, x2, y2, x3, y3), _, _ in _curves(toolkit):
        if slur in wanted:
            apex = _bezier(0.5, x0, y0, x1, y1, x2, y2, x3, y3)[1]
            result[slur] = (abs(apex - (y0 + y3) / 2), wanted[slur])
    return result


def _bezier(t, x0, y0, x1, y1, x2, y2, x3, y3) -> tuple[float, float]:
    a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t**2 * (1 - t), t**3
    return a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3


def _inside(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    for (xa, ya), (xb, yb) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ya > y) != (yb > y) and x < xa + (y - ya) * (xb - xa) / (yb - ya):
            inside = not inside
    return inside
