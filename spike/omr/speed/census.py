import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pikepdf

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from engine.read_pdf import is_scan  # noqa: E402

MUSIC_FONTS = ("leland", "bravura", "emmentaler", "feta", "petaluma", "sebastian", "gootville", "musejazz", "finale",
               "maestro", "opus", "engraver", "jazz", "november", "lilyjazz", "gonville", "beethoven", "haydn", "mtf",
               "smufl", "musescore", "fughetta", "golden", "aloisen", "sonata", "petrucci", "mscore")


def fonts_of(resources, seen: set) -> Counter:
    found = Counter()
    if not isinstance(resources, pikepdf.Dictionary):
        return found
    for font in (resources.get("/Font") or {}).values():
        name = str(font.get("/BaseFont", font.get("/Name", "?"))).lstrip("/")
        found[(name.split("+")[-1], str(font.get("/Subtype", "?")).lstrip("/"))] += 1
    for xobject in (resources.get("/XObject") or {}).values():
        if xobject.get("/Subtype") == "/Form" and xobject.objgen not in seen:
            seen.add(xobject.objgen)
            found += fonts_of(xobject.get("/Resources"), seen)
    return found


def describe(path: Path) -> dict:
    pdf = pikepdf.open(path)
    info = {str(key).lstrip("/"): str(value) for key, value in pdf.docinfo.items() if key in ("/Producer", "/Creator")}
    fonts = Counter()
    images = 0
    for page in pdf.pages:
        fonts += fonts_of(page.obj.get("/Resources"), set())
        images += sum(1 for x in (page.obj.get("/Resources", {}).get("/XObject", {}) or {}).values()
                      if x.get("/Subtype") == "/Image")
    music = sorted({f"{name} ({kind})" for name, kind in fonts if any(key in name.lower() for key in MUSIC_FONTS)})
    return {"pdf": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name, "pages": len(pdf.pages),
            "scan": is_scan(pdf), "images": images, "music_fonts": music,
            "fonts": sorted({f"{name} ({kind})" for name, kind in fonts}), **info}


def main():
    parser = argparse.ArgumentParser(description="Which PDFs are born digital, and do they carry music-font glyphs?")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = [describe(path) for path in args.pdfs]
    for row in rows:
        kind = "scan" if row["scan"] else ("glyphs" if row["music_fonts"] else "paths only")
        print(f"{row['pdf']:70} {row['pages']:3} {kind:10} {', '.join(row['music_fonts'])[:60]:60} {row.get('Producer', '')[:40]}")
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
