import collections
import re
import sys
from pathlib import Path

import pikepdf

SMUFL = ("bravura", "leland", "petaluma", "finalemaestro", "finale maestro", "finalebroadway", "finale broadway",
         "finalejazz", "finale jazz", "finaleash", "sebastian", "gootville", "musejazz", "leipzig", "november2",
         "golden age", "ekmelos", "smufl", "edwin")
LEGACY = ("opus", "maestro", "petrucci", "engraver", "jazz", "helsinki", "reprise", "inkpen", "norfolk", "broadway",
          "kosmos", "toccata", "emmentaler", "feta", "mscore", "gonville", "lilyjazz", "musicalsymbols", "capella",
          "noteworthy", "sonata", "anastasia", "musical", "mus", "allegro")
PAINT = {"f", "F", "f*", "B", "B*", "b", "b*", "S", "s"}


def music_kind(name: str):
    low = name.lower().split("+")[-1].lstrip("/")
    if any(key in low for key in SMUFL):
        return "smufl"
    if any(low.startswith(key) or key in low for key in LEGACY):
        return "legacy"
    return None


def census(path: Path):
    pdf = pikepdf.open(path)
    info = pdf.docinfo
    creator = " / ".join(str(info.get(k, "")) for k in ("/Creator", "/Producer") if info.get(k))
    fonts, type3 = {}, 0
    for item in pdf.objects:
        if isinstance(item, pikepdf.Dictionary) and item.get("/Type") == "/Font":
            name = str(item.get("/BaseFont", item.get("/Name", "")))
            if item.get("/Subtype") == "/Type3":
                type3 += 1
            fonts[name] = str(item.get("/Subtype"))
    music = sorted({(n.split("+")[-1].lstrip("/"), music_kind(n)) for n in fonts if music_kind(n)})
    ops = collections.Counter()
    images = 0
    for page in pdf.pages[:2]:
        def walk(stream, resources, seen):
            nonlocal images
            xobjects = resources.get("/XObject", {}) or {}
            for operands, operator in pikepdf.parse_content_stream(stream):
                op = str(operator)
                if op in ("Tj", "TJ", "'", '"'):
                    ops["text"] += 1
                elif op in PAINT:
                    ops["paint"] += 1
                elif op == "INLINE IMAGE":
                    images += 1
                elif op == "Do" and operands and str(operands[0]) in xobjects:
                    x = xobjects[str(operands[0])]
                    if x.get("/Subtype") == "/Image":
                        images += 1
                    elif x.get("/Subtype") == "/Form" and x.objgen not in seen:
                        seen.add(x.objgen)
                        walk(x, x.get("/Resources", resources), seen)
        res = page.obj.get("/Resources")
        node = page.obj
        while res is None and node.get("/Parent") is not None:
            node = node.Parent
            res = node.get("/Resources")
        walk(page.obj, res or {}, set())
    if images and ops["paint"] < 50:
        kind = "scan"
    elif any(k == "smufl" for _, k in music):
        kind = "music font (SMuFL)"
    elif any(k == "legacy" for _, k in music):
        kind = "music font (older, own layout)"
    elif type3:
        kind = "Type3 font (drawn glyphs)"
    else:
        kind = "shapes only"
    return creator, music, type3, dict(ops), images, kind


def main():
    summary = collections.Counter()
    for path in sorted(Path(sys.argv[1]).glob("*.pdf")):
        try:
            creator, music, type3, ops, images, kind = census(path)
        except Exception as error:
            print(path.name, "ERROR", type(error).__name__)
            continue
        summary[kind] += 1
        print(f"{path.name[:40]:40} | {kind:30} | {creator[:60]:60} | {[m for m, _ in music][:4]} t3={type3} {ops} img={images}")
    print()
    for kind, count in summary.most_common():
        print(f"{count:3}  {kind}")


main()
