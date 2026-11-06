import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pikepdf

SMUFL = {
    0xE0A0: "head", 0xE0A2: "head", 0xE0A3: "head", 0xE0A4: "head", 0xE0A9: "head", 0xE0FA: "head", 0xE0FB: "head",
    0xE050: "clef:G", 0xE052: "clef:G8vb", 0xE053: "clef:G8va", 0xE07A: "clef:G",
    0xE062: "clef:F", 0xE07C: "clef:F", 0xE05C: "clef:C", 0xE07B: "clef:C",
    0xE260: "acc:-1", 0xE261: "acc:0", 0xE262: "acc:1", 0xE263: "acc:2", 0xE264: "acc:-2",
}
EMMENTALER = {
    "noteheads.s0": "head", "noteheads.s1": "head", "noteheads.s2": "head", "noteheads.sM1": "head",
    "clefs.G": "clef:G", "clefs.G_change": "clef:G", "clefs.F": "clef:F", "clefs.F_change": "clef:F",
    "clefs.C": "clef:C", "clefs.C_change": "clef:C",
    "accidentals.flat": "acc:-1", "accidentals.natural": "acc:0", "accidentals.sharp": "acc:1",
    "accidentals.doublesharp": "acc:2", "accidentals.flatflat": "acc:-2",
}
BOTTOM_LINE = {"G": 2 + 7 * 4, "G8vb": 2 + 7 * 3, "G8va": 2 + 7 * 5, "F": 4 + 7 * 2, "C": 3 + 7 * 3}
STEP_SEMITONES = [0, 2, 4, 5, 7, 9, 11]
SHARP_ORDER, FLAT_ORDER = [3, 0, 4, 1, 5, 2, 6], [6, 2, 5, 1, 4, 0, 3]


def multiply(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2],
            a[2] * b[1] + a[3] * b[3], a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


@dataclass
class Font:
    two_byte: bool
    names: dict
    widths: dict
    default_width: float


def to_unicode(stream) -> dict:
    text = stream.read_bytes().decode("latin1")
    found = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for code, value in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", block):
            found[int(code, 16)] = int(value[:4], 16)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for low, high, value in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", block):
            for offset in range(int(high, 16) - int(low, 16) + 1):
                found[int(low, 16) + offset] = int(value[:4], 16) + offset
        for low, values in re.findall(r"<([0-9a-fA-F]+)>\s*<[0-9a-fA-F]+>\s*\[([^\]]*)\]", block):
            for offset, value in enumerate(re.findall(r"<([0-9a-fA-F]+)>", values)):
                found[int(low, 16) + offset] = int(value[:4], 16)
    return found


def load_font(font) -> Font:
    base = str(font.get("/BaseFont", "")).split("+")[-1]
    if font.get("/Subtype") == "/Type0":
        descendant = font.DescendantFonts[0]
        widths, w = {}, list(descendant.get("/W", []))
        i = 0
        while i < len(w):
            if isinstance(w[i + 1], pikepdf.Array):
                for k, value in enumerate(w[i + 1]):
                    widths[int(w[i]) + k] = float(value)
                i += 2
            else:
                for cid in range(int(w[i]), int(w[i + 1]) + 1):
                    widths[cid] = float(w[i + 2])
                i += 3
        unicode = to_unicode(font.ToUnicode) if "/ToUnicode" in font else {}
        names = {cid: SMUFL.get(value) for cid, value in unicode.items()}
        return Font(True, names, widths, float(descendant.get("/DW", 1000)))
    names = {}
    encoding = font.get("/Encoding")
    if isinstance(encoding, pikepdf.Dictionary) and "/Differences" in encoding:
        code = 0
        for item in encoding.Differences:
            if isinstance(item, pikepdf.Name):
                names[code] = EMMENTALER.get(str(item)[1:]) if "Emmentaler" in base else None
                code += 1
            else:
                code = int(item)
    first = int(font.get("/FirstChar", 0))
    widths = {first + k: float(value) for k, value in enumerate(font.get("/Widths", []))}
    return Font(False, names, widths, 0.0)


def page_items(pdf_page):
    glyphs, horizontals, verticals = [], [], []
    fonts = {}

    def run(stream, resources, ctm):
        state, stack = {"ctm": ctm, "font": None, "size": 1.0, "leading": 0.0, "width": 1.0}, []
        tm = lm = [1, 0, 0, 1, 0, 0]
        path, start, current = [], None, None

        def show(data):
            nonlocal tm
            font = state["font"]
            step = 2 if font.two_byte else 1
            for i in range(0, len(data), step):
                code = int.from_bytes(data[i:i + step], "big")
                trm = multiply(tm, state["ctm"])
                kind = font.names.get(code)
                if kind:
                    x, y = apply(trm, 0, 0)
                    scale = abs(state["size"] * (trm[3] if abs(trm[3]) > 1e-9 else trm[1]))
                    glyphs.append((kind, x, y, scale))
                advance = font.widths.get(code, font.default_width) / 1000 * state["size"]
                tm = multiply([1, 0, 0, 1, advance, 0], tm)

        for operands, operator in pikepdf.parse_content_stream(stream):
            op = str(operator)
            if op == "q":
                stack.append(dict(state))
            elif op == "Q":
                state = stack.pop()
            elif op == "cm":
                state["ctm"] = multiply([float(v) for v in operands], state["ctm"])
            elif op == "w":
                state["width"] = float(operands[0])
            elif op == "BT":
                tm = lm = [1, 0, 0, 1, 0, 0]
            elif op == "Tf":
                name = str(operands[0])
                if name not in fonts:
                    fonts[name] = load_font(resources.Font[name])
                state["font"], state["size"] = fonts[name], float(operands[1])
            elif op == "TL":
                state["leading"] = float(operands[0])
            elif op == "Tm":
                tm = lm = [float(v) for v in operands]
            elif op in ("Td", "TD"):
                if op == "TD":
                    state["leading"] = -float(operands[1])
                lm = multiply([1, 0, 0, 1, float(operands[0]), float(operands[1])], lm)
                tm = lm
            elif op in ("T*", "'", '"'):
                lm = multiply([1, 0, 0, 1, 0, -state["leading"]], lm)
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
                        tm = multiply([1, 0, 0, 1, -float(item) / 1000 * state["size"], 0], tm)
            elif op == "m":
                start = current = apply(state["ctm"], float(operands[0]), float(operands[1]))
            elif op == "l":
                point = apply(state["ctm"], float(operands[0]), float(operands[1]))
                path.append((current, point))
                current = point
            elif op == "re":
                x, y, w, h = (float(v) for v in operands)
                corners = [apply(state["ctm"], x + dx, y + dy) for dx, dy in ((0, 0), (w, 0), (w, h), (0, h))]
                xs, ys = [c[0] for c in corners], [c[1] for c in corners]
                path.append(("box", (min(xs), min(ys), max(xs), max(ys))))
            elif op in ("S", "s", "B", "B*", "b", "b*", "f", "F", "f*", "n"):
                if op != "n":
                    for segment in path:
                        if segment[0] == "box":
                            x0, y0, x1, y1 = segment[1]
                            if x1 - x0 > 20 * (y1 - y0) and x1 - x0 > 30:
                                horizontals.append(((y0 + y1) / 2, x0, x1))
                            elif y1 - y0 > 4 * (x1 - x0):
                                verticals.append(((x0 + x1) / 2, y0, y1))
                        elif abs(segment[0][1] - segment[1][1]) < 0.05 and abs(segment[0][0] - segment[1][0]) > 30:
                            horizontals.append((segment[0][1], min(segment[0][0], segment[1][0]), max(segment[0][0], segment[1][0])))
                        elif abs(segment[0][0] - segment[1][0]) < 0.05:
                            verticals.append((segment[0][0], min(segment[0][1], segment[1][1]), max(segment[0][1], segment[1][1])))
                path = []
            elif op == "Do":
                xobject = resources.XObject[str(operands[0])]
                if xobject.get("/Subtype") == "/Form":
                    matrix = [float(v) for v in xobject.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                    run(xobject, xobject.get("/Resources", resources), multiply(matrix, state["ctm"]))

    run(pdf_page.obj, pdf_page.obj.Resources, [1, 0, 0, 1, 0, 0])
    return glyphs, horizontals, verticals


def joined(horizontals):
    lines = []
    for y, x0, x1 in sorted(horizontals, key=lambda line: (round(line[0], 1), line[1])):
        if lines and abs(lines[-1][0] - y) < 0.2 and x0 <= lines[-1][2] + 2:
            lines[-1] = (lines[-1][0], lines[-1][1], max(lines[-1][2], x1))
        else:
            lines.append((y, x0, x1))
    return lines


def staves(horizontals):
    lines = sorted(joined(horizontals))
    widest = max((x1 - x0 for _, x0, x1 in lines), default=0)
    lines = [line for line in lines if line[2] - line[1] > 0.3 * widest]
    found, used = [], set()
    for i, (y, x0, x1) in enumerate(lines):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(lines)):
            if len(group) == 5:
                break
            yj, a, b = lines[j]
            gap = yj - lines[group[-1]][0]
            if gap < 0.5 or min(b, x1) - max(a, x0) < 0.5 * (x1 - x0):
                continue
            if len(group) == 1 or abs(gap - (lines[group[1]][0] - lines[group[0]][0])) < 0.15 * gap:
                group.append(j)
            elif gap > 1.5 * (lines[group[1]][0] - lines[group[0]][0] if len(group) > 1 else gap):
                break
        if len(group) == 5:
            used.update(group)
            ys = [lines[k][0] for k in group]
            found.append({"low": min(ys), "high": max(ys), "space": (max(ys) - min(ys)) / 4, "x0": x0, "x1": x1})
    return found


def read_page(pdf_page) -> list[int]:
    glyphs, horizontals, verticals = page_items(pdf_page)
    systems = staves(horizontals)
    if not systems:
        return []
    by_staff = {i: [] for i in range(len(systems))}
    for kind, x, y, size in glyphs:
        def distance(staff):
            if not staff["x0"] - 3 * staff["space"] <= x <= staff["x1"] + staff["space"]:
                return float("inf")
            return 0 if staff["low"] <= y <= staff["high"] else min(abs(y - staff["low"]), abs(y - staff["high"]))
        index = min(range(len(systems)), key=lambda i: distance(systems[i]))
        if distance(systems[index]) < 7 * systems[index]["space"]:
            by_staff[index].append((x, kind, y))
    for index, staff in enumerate(systems):
        tolerance = 0.3 * staff["space"]
        for x, y0, y1 in verticals:
            if (staff["x0"] < x < staff["x1"] + tolerance and y0 < staff["low"] + tolerance
                    and y1 > staff["high"] - tolerance and (y0 > staff["low"] - tolerance or y1 < staff["high"] + tolerance
                                                            or y1 - y0 > 6 * staff["space"])):
                by_staff[index].append((x, "bar", 0.0))
    pitches = []
    for index, items in by_staff.items():
        staff = systems[index]
        half = staff["space"] / 2
        items.sort()
        clef, key, seen_head, key_open = "G", [0] * 7, False, False
        pending, in_bar = [], {}
        for x, kind, y in items:
            if kind == "bar":
                pending, in_bar = [], {}
                continue
            position = round((y - staff["low"]) / half) if staff["low"] < staff["high"] else 0
            if kind.startswith("clef:"):
                clef = kind[5:]
                key_open = not seen_head
                continue
            step = BOTTOM_LINE[clef] + position
            if kind.startswith("acc:"):
                if key_open:
                    key[step % 7] = int(kind[4:])
                else:
                    pending.append((x, position, int(kind[4:])))
                continue
            seen_head, key_open = True, False
            alter = in_bar.get(step, key[step % 7])
            for ax, aposition, value in pending:
                if aposition == position and 0 < x - ax < 3 * staff["space"]:
                    alter = in_bar[step] = value
            octave, degree = divmod(step, 7)
            pitches.append(12 * (octave + 1) + STEP_SEMITONES[degree] + alter)
    return pitches


def truth_pitches(path: Path) -> list[int]:
    from music21 import converter
    score = converter.parse(str(path))
    return [pitch.midi for element in score.recurse().notes for pitch in element.pitches]


def main():
    parser = argparse.ArgumentParser(description="Read noteheads, clefs, keys and accidentals straight from a born-digital PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results" / "vector_notes.jsonl")
    args = parser.parse_args()
    started = time.perf_counter()
    pdf = pikepdf.open(args.pdf)
    pitches = [p for page in pdf.pages for p in read_page(page)]
    seconds = time.perf_counter() - started
    record = {"pdf": args.pdf.name, "pages": len(pdf.pages), "seconds": round(seconds, 2), "heads": len(pitches)}
    if args.truth:
        truth = Counter(truth_pitches(args.truth))
        read = Counter(pitches)
        shared = sum((truth & read).values())
        record.update(truth_notes=sum(truth.values()), shared_pitches=shared,
                      pitch_multiset_agreement=round(shared / max(sum(truth.values()), 1), 4),
                      pitch_class_agreement=round(sum((Counter(p % 12 for p in truth.elements()) & Counter(p % 12 for p in read.elements())).values()) / max(sum(truth.values()), 1), 4))
    print(json.dumps(record))
    with args.out.open("a") as sink:
        sink.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
