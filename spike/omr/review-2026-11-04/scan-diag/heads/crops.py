import json, sys, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw
SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
sys.path[:0] = [str(SCR / "pymupdf_lib")]
import fitz
items = {}
for t in ("native-inspect", "real-z1"):
    for it in json.loads((SCR / "scan-diag/items" / t / "items.json").read_text()):
        items[it["name"]] = it
def page(name, sheet, cache={}):
    k = (name, sheet)
    if k not in cache:
        d = fitz.open(items[name]["pdf"])
        pm = d[sheet - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        cache[k] = Image.frombytes("L", (pm.width, pm.height), pm.samples).convert("RGB")
    return cache[k]

def montage(rows, out, cols=4, size=260, T=None):
    W = cols * size; H = ((len(rows) + cols - 1) // cols) * size
    M = Image.new("RGB", (W, H), "white")
    for n, r in enumerate(rows):
        im = page(r["name"], r["sheet"])
        hh = r["hh"]; x = r["x"]; y = r.get("yy", r.get("y", 0))
        half = int(hh * 5)
        c = im.crop((int(x - half), int(y - half), int(x + half), int(y + half))).resize((size - 4, size - 4))
        d = ImageDraw.Draw(c); k = (size - 4) / (2 * half)
        cx = (x - (x - half)) * k; cy = half * k
        d.ellipse((cx - hh * k, cy - hh * k, cx + hh * k, cy + hh * k), outline="red", width=2)
        d.text((3, 3), r.get("label", ""), fill="blue")
        M.paste(c, ((n % cols) * size, (n // cols) * size))
    M.save(out)
