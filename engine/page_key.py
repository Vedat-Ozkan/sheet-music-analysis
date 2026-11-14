from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from engine import part_writing, piano, text, tint
from engine.overlay import ARROW, ERROR, FUNCTION_NAMES, INK, LABEL_PAD, LABEL_SIZE, LINE, S, Box, PageLayout

PLACES = ("first", "last")
SIZE = LABEL_SIZE
LINE_STEP = 500
GAP = 900
DOT = "·"
SAMPLE = 520

NCT_WORDS = {"PT": "passing note", "NT": "neighbour note", "SUS": "suspension", "APP": "appoggiatura", "ET": "escape tone",
             "RET": "retardation", "ANT": "anticipation", "PED": "pedal note"}
CADENCE_WORDS = {"PAC": "perfect authentic cadence", "IAC": "imperfect authentic cadence", "HC": "half cadence", "DC": "deceptive cadence"}
FUNCTION_WORDS = {"T": "tonic", "PD": "pre-dominant", "D": "dominant"}
CUE_WORDS = {piano.TUTTI: "the whole orchestra", piano.STRINGS_CUE: "the strings"}


def _spaced(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).lower()


def fault_words() -> dict[str, str]:
    words: dict[str, list[str]] = {}
    for rule, code in part_writing.LABELS.items():
        words.setdefault(code, []).append(rule.replace("_", " "))
    return {code: " or ".join(names) for code, names in words.items()}


def cue_words() -> dict[str, str]:
    return {**{code: _spaced(family) for family, code in piano.ABBREVIATIONS.items()}, **CUE_WORDS}


@dataclass
class Entry:
    sample: str
    meaning: str
    noun: str = ""
    codes: list[tuple[str, str]] = field(default_factory=list)
    code_colour: str = INK
    boxed: bool = False


def entries(shown: set[tuple[str, str]], cues: list[str] = ()) -> list[Entry]:
    found: dict[str, list[str]] = {}
    for kind, code in sorted(shown):
        found.setdefault(kind, []).append(code)
    result = []
    if "key" in found:
        result.append(Entry("", "the key (capital major, small minor)", found["key"][0]))
    if "function" in found:
        letters = [f for f in FUNCTION_NAMES if f in found["function"]]
        named = [f for f in FUNCTION_NAMES if FUNCTION_NAMES[f] in found["function"]]
        jobs = [(f, FUNCTION_WORDS[f]) for f in letters] + [(FUNCTION_NAMES[f], "") if FUNCTION_NAMES[f] == FUNCTION_WORDS[f]
                                                               else (FUNCTION_NAMES[f], f"({FUNCTION_WORDS[f]})") for f in named]
        result.append(Entry("function", "the chord’s job", codes=jobs))
    if "cadence" in found:
        result += [Entry("", "", codes=[(code, CADENCE_WORDS[code])], boxed=True) for code in CADENCE_WORDS if code in found["cadence"]]
    if "alternative" in found:
        result.append(Entry("alternative", "another reading a teacher would accept"))
    if "nct" in found:
        result.append(Entry("nct", "not part of the chord",
                            codes=[(code, words) for code, words in NCT_WORDS.items() if code in found["nct"]]))
    if "arrow" in found:
        result.append(Entry("arrow", "where a note moves"))
    if "fault" in found:
        known = fault_words()
        result.append(Entry("fault", "red marks are part-writing faults",
                            codes=[(code, words) for code, words in known.items() if code in found["fault"]], code_colour=ERROR))
    if "phrase" in found:
        result.append(Entry("phrase", "a phrase"))
    if "region" in found:
        result.append(Entry("region", "a passage named by what it is built on"))
    if "callout" in found:
        result.append(Entry("callout", "see that number in the reply"))
    if cues:
        known = cue_words()
        result.append(Entry("", "who plays it in the original", "names above the staff",
                            codes=[(cue, known[cue]) for cue in dict.fromkeys(cues) if cue in known]))
    if "shaded" in found:
        result.append(Entry("shaded", "may be misread from the PDF; check it against the original"))
    return result


def cues_on(layouts: list[PageLayout]) -> list[str]:
    known = cue_words()
    found = []
    for layout in layouts:
        for group in layout.root.iter(f"{S}g"):
            if group.get("class") == "dir":
                said = "".join(group.itertext()).strip()
                found += [cue for cue in (re.sub(r" (I|II|III|IV)$", "", part) for part in said.split(", ")) if cue in known]
    return found


def draw(layouts: list[PageLayout], place: str, cues: list[str] = ()) -> None:
    shown = set().union(*(layout.shown for layout in layouts))
    pieces = entries(shown, cues)
    if not pieces:
        return
    layout = layouts[0] if place == "first" else layouts[-1]
    over = layout.over
    layout.over = ET.SubElement(over, f"{S}g", {"class": "page-key"})
    left = min(system.left for system in layout.systems)
    right = max(system.right for system in layout.systems)
    last = layout.systems[-1]
    y = max([box.bottom for box in last.content + last.words] + [last.staff_bottom]) + GAP
    pen = _Pen(layout, left, right, y)
    for number, entry in enumerate(pieces):
        lead = [] if number == 0 else [("text", DOT, INK)]
        if entry.sample:
            head = lead + [("sample", entry.sample, INK)]
            head += [("text", entry.meaning + (":" if entry.codes else ""), INK)] if entry.meaning else []
        else:
            said = f"{entry.noun} = {entry.meaning}" if entry.noun else entry.meaning
            head = lead + ([("text", said + (":" if entry.codes else ""), INK)] if said else [])
        pen.keep([head + _code_piece(entry, 0)] + [_code_piece(entry, position) for position in range(1, len(entry.codes))])
    layout.over = over
    _grow_page(layout, pen.y + SIZE)


def _code_piece(entry: Entry, position: int) -> list[tuple[str, str, str]]:
    if not entry.codes:
        return []
    code, words = entry.codes[position]
    piece = [("boxed" if entry.boxed else "code", code, entry.code_colour)]
    tail = ("," if position < len(entry.codes) - 1 else "")
    if words:
        piece.append(("text", words + tail, INK))
    elif tail:
        piece[-1] = (piece[-1][0], code + tail, entry.code_colour)
    return piece


class _Pen:
    def __init__(self, layout: PageLayout, left: float, right: float, y: float):
        self.layout, self.left, self.right, self.x, self.y = layout, left, right, left, y

    def keep(self, pieces: list[list[tuple[str, str, str]]]) -> None:
        if len(pieces) > 2:
            pieces = pieces[:-2] + [pieces[-2] + pieces[-1]]
        for piece in pieces:
            self._put(piece)

    def _span(self, parts: list[tuple[str, str, str]]) -> float:
        return sum(self._width(kind, string) for kind, string, _ in parts) + text.width(" ", SIZE) * len(parts)

    def _break(self) -> None:
        self.x, self.y = self.left, self.y + LINE_STEP

    def _put(self, parts: list[tuple[str, str, str]]) -> None:
        if not parts:
            return
        space = text.width(" ", SIZE)
        if self.x > self.left and self.x + self._span(parts) > self.right:
            self._break()
            if parts[0] == ("text", DOT, INK):
                parts = parts[1:]
        for kind, string, colour in parts:
            if self.x > self.left:
                self.x += space
            self.x = self._draw(kind, string, colour)

    @staticmethod
    def _width(kind: str, string: str) -> float:
        if kind == "sample":
            return SAMPLE
        return text.width(string, SIZE) + (2 * LABEL_PAD if kind == "boxed" else 0)

    def _draw(self, kind: str, string: str, colour: str) -> float:
        layout, x, y = self.layout, self.x, self.y
        if kind == "sample":
            _sample(layout, string, Box(x, y - SIZE * 0.7, SAMPLE, SIZE * 0.8))
            return x + SAMPLE
        if kind == "boxed":
            width = text.width(string, SIZE) + 2 * LABEL_PAD
            layout._add("rect", x=round(x), y=round(y - SIZE * 0.78), width=round(width), height=round(SIZE * 0.98),
                        fill="#ffffff", stroke=INK, stroke_width=LINE)
            layout._text(x + LABEL_PAD, y, string, SIZE, fill=colour)
            return x + width
        return layout._text(x, y, string, SIZE, fill=colour).right


def _sample(layout: PageLayout, kind: str, box: Box) -> None:
    x0, x1, top, bottom, mid = box.x + 30, box.right - 30, box.y, box.bottom, box.cy
    if kind == "function":
        layout._add("path", d=f"M{x0:.0f},{top:.0f} L{x0:.0f},{mid:.0f} L{x1:.0f},{mid:.0f} L{x1:.0f},{top:.0f}",
                    fill="none", stroke=INK, stroke_width=LINE, stroke_linejoin="round")
    elif kind in ("phrase", "region"):
        dash = {"stroke_dasharray": "110 70"} if kind == "region" else {}
        layout._add("path", d=f"M{x0:.0f},{bottom:.0f} L{x0:.0f},{mid:.0f} L{x1:.0f},{mid:.0f} L{x1:.0f},{bottom:.0f}",
                    fill="none", stroke=INK, stroke_width=LINE, stroke_linejoin="round", **dash)
    elif kind == "alternative":
        layout._add("path", d=f"M{x0:.0f},{top:.0f} L{x0:.0f},{mid:.0f} L{x1:.0f},{mid:.0f} L{x1:.0f},{top:.0f}",
                    fill="none", stroke=INK, stroke_width=LINE * 2, stroke_linejoin="round", stroke_dasharray="1 70", stroke_linecap="round")
    elif kind == "nct":
        layout._add("ellipse", cx=round(box.cx), cy=round(mid), rx=150, ry=120, fill="none", stroke=INK, stroke_width=LINE)
    elif kind == "fault":
        layout._add("ellipse", cx=round(box.cx), cy=round(mid), rx=150, ry=120, fill="none", stroke=ERROR, stroke_width=30)
    elif kind == "arrow":
        layout._line_or_arrow(x0, mid, x1, mid, head=True, colour=ARROW)
    elif kind == "callout":
        layout._add("circle", cx=round(box.cx), cy=round(mid), r=170, fill=INK)
        layout._text(box.cx, mid + SIZE * 0.3, "1", SIZE * 0.9, bold=True, fill="#ffffff", anchor="middle")
    elif kind == "shaded":
        layout._add("rect", x=round(x0), y=round(top), width=round(x1 - x0), height=round(bottom - top),
                    fill=tint.FLAG_BAR, fill_opacity=tint.FLAG_OPACITY)


def _grow_page(layout: PageLayout, bottom: float) -> None:
    inner = layout.root.find(f"{S}svg")
    top = float(re.search(r"translate\([-\d.]+,\s*([-\d.]+)", layout.canvas.get("transform")).group(1))
    x, y, w, h = map(float, inner.get("viewBox").split())
    needed = top + bottom + 400
    if needed <= h:
        return
    ox, oy, ow, oh = map(float, layout.root.get("viewBox").split())
    inner.set("viewBox", f"{x:g} {y:g} {w:g} {needed:g}")
    layout.root.set("viewBox", f"{ox:g} {oy:g} {ow:g} {oh * needed / h:g}")
