import collections, io, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
rows = []
for name, stem, eng in json.load(open(S / "probe_set.json")):
    d = S / "books" / stem
    omr = sorted(d.glob("*.omr")); mxl = sorted(d.glob("*.mxl"))
    if not omr or not mxl:
        continue
    man = json.loads((OMR / name / "manifest.json").read_text())
    tb = parse((OMR / name / man["pieces"][stem.rsplit("--", 1)[0]]["truth"]).read_bytes())
    ob = parse(mxl[0].read_bytes())
    z = zipfile.ZipFile(omr[0])
    sheets = sorted({int(m.group(1)) for n in z.namelist() if (m := re.match(r"sheet#(\d+)/sheet#\d+\.xml", n))})
    bars = []
    for sn in sheets:
        root = ET.fromstring(z.read(f"sheet#{sn}/sheet#{sn}.xml"))
        il = int(root.find("scale/interline").get("main"))
        img = np.array(Image.open(io.BytesIO(z.read(f"sheet#{sn}/BINARY.png"))).convert("L")) < 128
        for sys_ in root.iter("system"):
            mask = img.copy()
            staves = []
            for st in sys_.iter("staff"):
                ln = st.find("lines")
                if ln is None:
                    continue
                ys = []
                for l in ln.findall("line"):
                    pts = [(float(p.get("x")), float(p.get("y"))) for p in l.findall("point")]
                    t = int(float(l.get("thickness", 2)))
                    ys.append(np.mean([p[1] for p in pts]))
                    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                        for x in range(int(x1), int(x2) + 1, 8):
                            yy = y1 + (y2 - y1) * (x - x1) / max(x2 - x1, 1)
                            mask[max(0, int(yy) - t):int(yy) + t + 1, x:x + 8] = False
                staves.append((min(ys), max(ys)))
            inters = sys_.find("sig/inters")
            if inters is not None:
                for e in inters:
                    b = e.find("bounds")
                    if b is None:
                        continue
                    x, y, w, h = int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))
                    if e.tag in ("slur",):
                        continue
                    mask[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2] = False
            for st_ in sys_.findall("stack"):
                left, right = int(st_.get("left")), int(st_.get("right"))
                score = 0
                nblobs = 0
                for top, bot in staves:
                    region = mask[max(0, int(top - 2 * il)):int(bot + 2 * il), left + 2:right - 2]
                    lab, n = ndimage.label(region)
                    if n == 0:
                        continue
                    for sl in ndimage.find_objects(lab):
                        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
                        if h >= 0.4 * il and w >= 0.3 * il and h <= 4 * il and w <= 3 * il:
                            nblobs += 1
                            score += h * w / il ** 2
                bars.append((nblobs, score))
    if len(bars) != len(ob):
        continue
    for i, j in align_bars(tb, ob):
        t, o = tb[i], ob[j]
        n, sc = bars[j]
        rows.append(dict(stem=stem, eng=eng, n=n, sc=sc, right=timed(t) == timed(o), pok=pitches(t) == pitches(o)))
json.dump(rows, open(S / "t12.json", "w"))
def auc(pos, neg):
    arr = np.array(pos + neg, float)
    u, inv, cnt = np.unique(arr, return_inverse=True, return_counts=True)
    rank = (np.cumsum(cnt) - (cnt - 1) / 2)[inv]
    n1, n0 = len(pos), len(neg)
    return (rank[:n1].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1)
for lab, key in (("pitch wrong", "pok"), ("pitch or timing wrong", "right")):
    pos = [r["sc"] for r in rows if not r[key]]; neg = [r["sc"] for r in rows if r[key]]
    print(lab, "bars", len(rows), "wrong", len(pos), "AUC", round(auc(pos, neg), 3))
    for g in ("ms", "ly", "ly-old", "scan"):
        p = [r["sc"] for r in rows if not r[key] and (r["eng"] == g or (g == "scan" and "scan" in r["eng"]))]
        n = [r["sc"] for r in rows if r[key] and (r["eng"] == g or (g == "scan" and "scan" in r["eng"]))]
        if p and n:
            th = sorted(n)[int(0.97 * len(n))]
            print("  ", g, "AUC", round(auc(p, n), 3), "wrong", len(p), "right", len(n), "at 3% false flags: th", round(th, 2), "caught", sum(v > th for v in p))
    th0 = sorted(neg)[int(0.97 * len(neg))]
    print("   overall at 3% false:", sum(v > th0 for v in pos), "of", len(pos))
