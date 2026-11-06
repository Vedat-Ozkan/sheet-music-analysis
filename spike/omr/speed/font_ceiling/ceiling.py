import collections
import json
import re
import sys
from pathlib import Path

import pikepdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vector_notes as vn  # noqa: E402

PHASE0 = Path(sys.argv[1])
WINDOW = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
BENCH = HERE.parents[1] / "bench"
OUT = HERE / "rows.json"

SMUFL_KINDS = {**{code: "rest" for code in range(0xE4E0, 0xE4EB)}, 0xE4F4: "rest", 0xE4F5: "rest",
               **{code: "flag" for code in range(0xE240, 0xE250)}, 0xE1E7: "dot",
               **{code: "head" for code in (0xE0A0, 0xE0A2, 0xE0A3, 0xE0A4, 0xE0A9, 0xE0FA, 0xE0FB)}}
NEED = {"rest_missing": "rest", "rest_type": "rest", "dot_add": "dot", "flag_up": "flag", "flag_down": "flag",
        "head_fill": "head", "head_fill+flags": "head", "note_missing": "head", "grace_as_real": "head"}
ABSENT = {"note_extra": "head", "rest_extra": "rest"}


def emmentaler_kind(name: str):
    if name.startswith("rests."):
        return "rest"
    if name.startswith("flags.") and name[6:7] in "ud":
        return "flag"
    if name == "dots.dot":
        return "dot"
    if name.startswith("noteheads.s"):
        return "head"
    return None


class EmmentalerKinds(dict):
    def get(self, name, default=None):
        return emmentaler_kind(name)


vn.SMUFL = SMUFL_KINDS
vn.EMMENTALER = EmmentalerKinds()


def page_glyphs(page):
    glyphs, horizontals, _ = vn.page_items(page)
    staves = sorted(vn.staves(horizontals), key=lambda staff: -staff["high"])
    return glyphs, staves


def image_widths(run: Path) -> dict:
    text = (run / "audiveris-pdf.txt").read_text(errors="replace")
    widths = {int(n): int(w) for n, w in re.findall(r"Loaded image #(\d+) (\d+)x\d+", text)}
    for page, w in re.findall(r"\[[^#\]]*#(\d+)\][^\n]*Interline \d+ too small, image rendered again (\d+)x\d+", text):
        widths[int(page)] = int(w)
    return widths


def staff_of(y, staves):
    best, distance = None, float("inf")
    for index, staff in enumerate(staves):
        d = 0 if staff["low"] <= y <= staff["high"] else min(abs(y - staff["low"]), abs(y - staff["high"]))
        if d < distance:
            best, distance = index, d
    return best if best is not None and distance <= 6 * staves[best]["space"] else None


def main():
    rows = json.loads((PHASE0 / "rows.json").read_text())
    rows = [row for row in rows if row["engraver"] in ("ms", "ly")]
    cache = {}
    results = []
    for row in rows:
        stem = row["pdf"]
        pdf_path = BENCH / "pdfs" / f"{stem}.pdf"
        run = PHASE0 / "runs" / stem / f"s{row['chosen']}"
        if stem not in cache:
            pdf = pikepdf.open(pdf_path)
            pages = {}
            for number, page in enumerate(pdf.pages, 1):
                glyphs, staves = page_glyphs(page)
                width = float(page.mediabox[2]) - float(page.mediabox[0])
                placed = [(kind, x, staff_of(y, staves)) for kind, x, y, _ in glyphs]
                pages[number] = {"width": width, "glyphs": placed, "staves": staves}
            cache[stem] = (pages, image_widths(run))
        pages, widths = cache[stem]
        verdicts = []
        for item in row["items"]:
            sub = item.get("sub") or item["cause"]
            if item["need"] == "no_ink" or (sub not in NEED and sub not in ABSENT) or "page" not in item:
                verdicts.append({"sub": sub, "found": None})
                continue
            page = pages.get(item["page"])
            image_width = widths.get(item["page"])
            if not page or not image_width or not page["staves"]:
                verdicts.append({"sub": sub, "found": None, "why": "no page data"})
                continue
            scale = page["width"] / image_width
            x = item["x"] * scale
            space = page["staves"][0]["space"]
            staff = item["staff"] - 1
            kind = NEED.get(sub) or ABSENT[sub]
            near = [g for g in page["glyphs"] if g[0] == kind and abs(g[1] - x) <= WINDOW * space]
            strict = [g for g in near if g[2] == staff]
            loose = [g for g in near if g[2] is not None and abs(g[2] - staff) <= 1]
            same = [abs(g[1] - x) / space for g in page["glyphs"] if g[0] == kind and g[2] == staff]
            nearest = round(min(same), 1) if same else None
            if sub in ABSENT:
                verdicts.append({"sub": sub, "found": not strict, "loose": not loose})
            else:
                verdicts.append({"sub": sub, "found": bool(strict), "loose": bool(loose), "nearest": nearest})
        results.append({**{k: row[k] for k in ("pdf", "engraver", "bar", "bucket")}, "verdicts": verdicts})
    OUT.write_text(json.dumps(results, indent=0))

    def covered(result, key):
        verdicts = result["verdicts"]
        return bool(verdicts) and all(v.get(key) is True for v in verdicts)

    strict = sum(covered(r, "found") for r in results)
    loose = sum(covered(r, "loose") for r in results)
    any_strict = sum(any(v.get("found") is True for v in r["verdicts"]) for r in results)
    print(f"ms+ly flagged bars: {len(results)}")
    print(f"covered (same staff): {strict}; covered (staff +-1): {loose}; at least one item supplied: {any_strict}")
    print("bars with no items (voice-only or unresolved):", sum(not r["verdicts"] for r in results))
    print("bars needing a no-ink change:", sum(any(v["found"] is None for v in r["verdicts"]) for r in results))
    per = collections.Counter()
    for r in results:
        for v in r["verdicts"]:
            if v["found"] is not None:
                per[(v["sub"], v["found"])] += 1
    for key, count in sorted(per.items()):
        print(" ", key, count)


main()
