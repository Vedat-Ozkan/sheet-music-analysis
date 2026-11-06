import sys, pickle, json, re, collections, zipfile, io
sys.path.insert(0, "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/pymupdf_lib")
import fitz
import warnings
warnings.filterwarnings("ignore")
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageDraw
M = Path(__file__).parent
OMR = Path("/home/kema/projects/sheet-music-plugin/spike/omr")
root = M / (sys.argv[1] if len(sys.argv) > 1 else "marksdiag")
A = pickle.load(open(str(root) + ".pkl", "rb"))

def sheet_info(z, n):
    x = ET.fromstring(z.read(f"sheet#{n}/sheet#{n}.xml"))
    words, others = [], []
    pic = x.find("picture")
    W = int(pic.get("width"))
    il = x.find("scale").find("interline").get("main") if x.find("scale") is not None and x.find("scale").find("interline") is not None else None
    for w in x.iter("word"):
        b = w.find("bounds")
        words.append((w.get("value"), int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))))
    return W, int(il or 20), words

def overlap(a, b, margin=0):
    return a[0] < b[0] + b[2] + margin and b[0] < a[0] + a[2] + margin and a[1] < b[1] + b[3] + margin and b[1] < a[1] + a[3] + margin

rows = []
for stem, (name, marks) in A.items():
    d = root / stem
    z = zipfile.ZipFile(next(d.glob("*.omr")))
    pdf = fitz.open(OMR / name / "pdfs" / (stem + ".pdf"))
    info, chars = {}, {}
    for m in marks:
        if m["cls"] not in ("false", "true"):
            continue
        n = m["sheet"]
        if n not in info:
            info[n] = sheet_info(z, n)
            page = pdf[n - 1]
            sc = page.rect.width / info[n][0]
            ch = []
            for b in page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_ACCURATE_BBOXES)["blocks"]:
                for l in b.get("lines", []):
                    for sp in l["spans"]:
                        for c in sp["chars"]:
                            x0, y0, x1, y1 = c["bbox"]
                            ch.append((c["c"], sp["font"], x0 / sc, y0 / sc, (x1 - x0) / sc, (y1 - y0) / sc))
            chars[n] = ch
        W, il, words = info[n]
        box = (m["x"], m["y"], m["w"], m["h"])
        m["il"] = il
        m["word"] = [w[0] for w in words if overlap(box, w[1:], 0)]
        m["word_near"] = [w[0] for w in words if overlap(box, w[1:], il // 2)]
        m["pdfchars"] = [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in chars[n] if overlap(box, c[2:], 0)]
        m["stem"], m["set"] = stem, name
        rows.append(m)
pickle.dump(rows, open(str(root) + "_ink.pkl", "wb"))
