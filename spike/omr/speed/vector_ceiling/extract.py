import re
import sys
from pathlib import Path

import pikepdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vector_notes as vn  # noqa: E402

HEADS = {0xE0A0: "breve", 0xE0A2: "whole", 0xE0A3: "half", 0xE0A4: "black"}
RESTS = {0xE4E2: "breve", 0xE4E3: "whole", 0xE4E4: "half", 0xE4E5: "quarter", 0xE4E6: "eighth", 0xE4E7: "16th",
         0xE4E8: "32nd", 0xE4E9: "64th", 0xE4F4: "whole", 0xE4F5: "half"}
REST_NAMES = {"M1": "breve", "0": "whole", "1": "half", "2": "quarter", "3": "eighth", "4": "16th", "5": "32nd", "6": "64th"}
EM_HEADS = {"s0": "whole", "s1": "half", "s2": "black", "sM1": "breve"}


def smufl_kind(code):
    if code in HEADS:
        return ("head", HEADS[code])
    if code in RESTS:
        return ("rest", RESTS[code])
    if 0xE240 <= code <= 0xE24F:
        return ("flag", (code - 0xE240) // 2 + 1)
    if code == 0xE1E7:
        return ("dot", None)
    if 0xE880 <= code <= 0xE889:
        return ("tuplet", code - 0xE880)
    return None


def emmentaler_kind(name):
    match = re.fullmatch(r"noteheads\.([ud]?)(s[0-2]|sM1)\w*", name)
    if match:
        return ("head", EM_HEADS[match.group(2)])
    match = re.fullmatch(r"rests\.(M1|\d)o?", name)
    if match:
        return ("rest", REST_NAMES[match.group(1)])
    match = re.fullmatch(r"flags\.[ud](\d)", name)
    if match:
        return ("flag", int(match.group(1)) - 2)
    if name == "dots.dot":
        return ("dot", None)
    return None


class Smufl(dict):
    def get(self, code, default=None):
        return smufl_kind(code)


class Emmentaler(dict):
    def get(self, name, default=None):
        return emmentaler_kind(name)


vn.SMUFL = Smufl()
vn.EMMENTALER = Emmentaler()


def page_drawing(pdf_page):
    glyphs, lines, polygons = [], [], []
    fonts = {}

    def run(stream, resources, ctm):
        state = {"ctm": ctm, "font": None, "size": 1.0, "leading": 0.0, "width": 1.0}
        stack = []
        tm = lm = [1, 0, 0, 1, 0, 0]
        subpaths, current = [], []

        def show(data):
            nonlocal tm
            font = state["font"]
            step = 2 if font.two_byte else 1
            for i in range(0, len(data), step):
                code = int.from_bytes(data[i:i + step], "big")
                trm = vn.multiply(tm, state["ctm"])
                kind = font.names.get(code)
                if kind:
                    x, y = vn.apply(trm, 0, 0)
                    scale = abs(state["size"] * (trm[3] if abs(trm[3]) > 1e-9 else trm[1]))
                    glyphs.append((kind[0], kind[1], x, y, scale))
                advance = font.widths.get(code, font.default_width) / 1000 * state["size"]
                tm = vn.multiply([1, 0, 0, 1, advance, 0], tm)

        def width_now():
            m = state["ctm"]
            return state["width"] * (abs(m[0]) + abs(m[3])) / 2

        for operands, operator in pikepdf.parse_content_stream(stream):
            op = str(operator)
            if op == "q":
                stack.append(dict(state))
            elif op == "Q":
                state = stack.pop()
            elif op == "cm":
                state["ctm"] = vn.multiply([float(v) for v in operands], state["ctm"])
            elif op == "w":
                state["width"] = float(operands[0])
            elif op == "BT":
                tm = lm = [1, 0, 0, 1, 0, 0]
            elif op == "Tf":
                name = str(operands[0])
                if name not in fonts:
                    fonts[name] = vn.load_font(resources.Font[name])
                state["font"], state["size"] = fonts[name], float(operands[1])
            elif op == "TL":
                state["leading"] = float(operands[0])
            elif op == "Tm":
                tm = lm = [float(v) for v in operands]
            elif op in ("Td", "TD"):
                if op == "TD":
                    state["leading"] = -float(operands[1])
                lm = vn.multiply([1, 0, 0, 1, float(operands[0]), float(operands[1])], lm)
                tm = lm
            elif op in ("T*", "'", '"'):
                lm = vn.multiply([1, 0, 0, 1, 0, -state["leading"]], lm)
                tm = lm
                if op != "T*":
                    show(bytes(operands[-1]))
            elif op == "Tj":
                show(bytes(operands[0]))
            elif op == "TJ":
                for item in operands[0]:
                    if isinstance(item, pikepdf.String):
                        show(bytes(item))
                    else:
                        tm = vn.multiply([1, 0, 0, 1, -float(item) / 1000 * state["size"], 0], tm)
            elif op == "m":
                if current:
                    subpaths.append(current)
                current = [vn.apply(state["ctm"], float(operands[0]), float(operands[1]))]
            elif op == "l":
                current.append(vn.apply(state["ctm"], float(operands[0]), float(operands[1])))
            elif op in ("c", "v", "y"):
                current.append(vn.apply(state["ctm"], float(operands[-2]), float(operands[-1])))
                current.append("curve")
            elif op == "re":
                if current:
                    subpaths.append(current)
                x, y, w, h = (float(v) for v in operands)
                subpaths.append([vn.apply(state["ctm"], x + dx, y + dy) for dx, dy in ((0, 0), (w, 0), (w, h), (0, h))]
                                + ["closed"])
                current = []
            elif op == "h":
                if current:
                    current.append("closed")
            elif op in ("S", "s", "B", "B*", "b", "b*", "f", "F", "f*", "n"):
                if current:
                    subpaths.append(current)
                filled = op not in ("S", "s", "n")
                for sub in subpaths:
                    points = [p for p in sub if isinstance(p, tuple)]
                    curved = "curve" in sub
                    if len(points) == 2 and not filled:
                        lines.append((points[0], points[1], width_now()))
                    elif len(points) >= 3 and not curved:
                        if filled:
                            polygons.append(points)
                        elif len(points) == 4 and "closed" in sub:
                            polygons.append(points)
                subpaths, current = [], []
            elif op == "Do":
                xobject = resources.XObject[str(operands[0])]
                if xobject.get("/Subtype") == "/Form":
                    matrix = [float(v) for v in xobject.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                    run(xobject, xobject.get("/Resources", resources), vn.multiply(matrix, state["ctm"]))

    run(pdf_page.obj, pdf_page.obj.Resources, [1, 0, 0, 1, 0, 0])
    return glyphs, lines, polygons


def segments(lines, polygons):
    horizontals, verticals, beams = [], [], []
    for (a, b, width) in lines:
        if abs(a[1] - b[1]) < 0.05 and abs(a[0] - b[0]) > 0.5:
            horizontals.append((a[1], min(a[0], b[0]), max(a[0], b[0])))
        elif abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) > 0.5:
            verticals.append(((a[0] + b[0]) / 2, min(a[1], b[1]), max(a[1], b[1]), width))
    for points in polygons:
        unique = []
        for p in points:
            if not unique or abs(p[0] - unique[-1][0]) > 1e-3 or abs(p[1] - unique[-1][1]) > 1e-3:
                unique.append(p)
        if len(unique) > 1 and abs(unique[0][0] - unique[-1][0]) < 1e-3 and abs(unique[0][1] - unique[-1][1]) < 1e-3:
            unique.pop()
        if len(unique) != 4:
            continue
        xs, ys = [p[0] for p in unique], [p[1] for p in unique]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        rect = len({round(x, 2) for x in xs}) == 2 and len({round(y, 2) for y in ys}) == 2
        if rect and w > 3 * h and h >= 1.0:
            beams.append((min(xs), max(xs), (min(ys) + max(ys)) / 2, (min(ys) + max(ys)) / 2, h))
        elif rect and w > 20 * h and w > 0.5:
            horizontals.append(((min(ys) + max(ys)) / 2, min(xs), max(xs)))
        elif rect and h > 3 * w:
            verticals.append(((min(xs) + max(xs)) / 2, min(ys), max(ys), w))
        else:
            left = sorted(unique, key=lambda p: p[0])[:2]
            right = sorted(unique, key=lambda p: p[0])[2:]
            if abs(left[0][0] - left[1][0]) < 0.05 and abs(right[0][0] - right[1][0]) < 0.05 and right[0][0] - left[0][0] > 0.5:
                thick_left, thick_right = abs(left[0][1] - left[1][1]), abs(right[0][1] - right[1][1])
                if abs(thick_left - thick_right) < 0.2 * max(thick_left, 0.01):
                    y_left = (left[0][1] + left[1][1]) / 2
                    y_right = (right[0][1] + right[1][1]) / 2
                    beams.append((left[0][0], right[0][0], y_left, y_right, thick_left))
    beams = sorted({tuple(round(value, 2) for value in beam) for beam in beams})
    return horizontals, verticals, beams
