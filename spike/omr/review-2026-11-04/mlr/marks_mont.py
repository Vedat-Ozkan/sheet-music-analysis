import sys, pickle, random, collections, zipfile, io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
M = Path(__file__).parent
root = M / "marksdiag"
rows = pickle.load(open(str(root) + "_ink.pkl", "rb"))
Image.MAX_IMAGE_PIXELS = None
def crop(m, cache, size=170):
    key = (m["stem"], m["sheet"])
    if key not in cache:
        z = zipfile.ZipFile(next((root / m["stem"]).glob("*.omr")))
        cache[key] = Image.open(io.BytesIO(z.read(f"sheet#{m['sheet']}/BINARY.png"))).convert("RGB")
    im = cache[key]
    il = m["il"]
    cx, cy = m["x"] + m["w"] // 2, m["y"] + m["h"] // 2
    r = int(3.5 * il)
    box = (cx - r, cy - r, cx + r, cy + r)
    c = im.crop(box).copy()
    d = ImageDraw.Draw(c)
    p = max(2, il // 8)
    d.rectangle((m["x"] - box[0] - p, m["y"] - box[1] - p, m["x"] + m["w"] - box[0] + p, m["y"] + m["h"] - box[1] + p), outline=(255, 0, 0), width=max(1, il // 12))
    c = c.resize((size, size), Image.LANCZOS)
    return c
def sheet(sel, path, cols=8, size=170):
    rowsn = (len(sel) + cols - 1) // cols
    W = Image.new("RGB", (cols * (size + 4), rowsn * (size + 18)), "white")
    d = ImageDraw.Draw(W)
    cache = {}
    for i, m in enumerate(sel):
        x, y = (i % cols) * (size + 4), (i // cols) * (size + 18)
        W.paste(crop(m, cache, size), (x, y + 14))
        d.text((x + 1, y), f"{i} {m['tag'][:6]} {m['stem'][:14]}", fill=(0, 0, 200))
    W.save(path)
if __name__ == "__main__":
    rng = random.Random(7)
    by = collections.defaultdict(list)
    for m in rows:
        if m["cls"] == "false":
            by[m["stem"]].append(m)
    groups = {"ms": [], "vr": [], "ly": [], "old": [], "scan": []}
    for stem, r in by.items():
        eng = stem.rsplit("--", 1)[1]
        g = {"ms": "ms", "vr": "vr", "ly": "ly", "ly-old": "old"}.get(eng, "scan")
        rng.shuffle(r)
        groups[g] += r[:6]
    picked = {}
    for g, r in groups.items():
        rng.shuffle(r)
        r = r[:40]
        picked[g] = r
        sheet(r, M / f"mont_{g}.png")
    pickle.dump(picked, open(M / "mont_picked.pkl", "wb"))
    print({g: len(r) for g, r in picked.items()})
