import collections, glob, io, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
SHAPE = {"whole": "WHOLE_REST", "half": "HALF_REST", "quarter": "QUARTER_REST", "eighth": "EIGHTH_REST", "16th": "ONE_16TH_REST", "32nd": "ONE_32ND_REST", "64th": "ONE_64TH_REST"}
THETAS = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95)

def bounds(e):
    b = e.find("bounds")
    return int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))

def load_book(path):
    z = zipfile.ZipFile(path)
    sheets = sorted({int(m.group(1)) for n in z.namelist() if (m := re.match(r"sheet#(\d+)/sheet#\d+\.xml", n))})
    out = []
    for sn in sheets:
        root = ET.fromstring(z.read(f"sheet#{sn}/sheet#{sn}.xml"))
        img = np.array(Image.open(io.BytesIO(z.read(f"sheet#{sn}/BINARY.png"))).convert("L")) < 128
        il = int(root.find("scale/interline").get("main"))
        for sys_ in root.iter("system"):
            parts = sys_.findall("part")
            staves = {}
            order = {}
            for pi, part in enumerate(parts):
                for si, st in enumerate(part.findall("staff"), start=1):
                    ys = [float(l.find("point").get("y")) for l in st.find("lines").findall("line")]
                    if len(ys) != 5:
                        continue
                    staves[st.get("id")] = (pi, si, sum(ys) / 5)
                    order[(pi, str(si))] = st.get("id")
            inters = sys_.find("sig/inters")
            rests, heads = [], []
            if inters is not None:
                for e in inters:
                    if e.tag == "rest":
                        rests.append((e.get("shape"), e.get("staff"), *bounds(e), float(e.get("grade") or 0)))
                    elif e.tag in ("head", "stem", "beam", "flag", "alter", "key-alter", "clef", "barline", "augmentation-dot", "articulation", "dynamics", "time-number", "time-whole", "time-pair", "fermata", "ornament", "tuplet", "word", "sentence", "pedal", "wedge", "slur", "bracket", "brace", "ledger", "small-flag", "beam-hook", "small-beam", "marker", "repeat-dot"):
                        if e.find("bounds") is not None and e.tag not in ("slur", "ledger", "bracket", "brace", "wedge"):
                            heads.append(bounds(e))
            for st_ in sys_.findall("stack"):
                out.append(dict(sheet=sn, img=img, il=il, left=int(st_.get("left")), right=int(st_.get("right")), staves=staves, order=order, rests=rests, heads=heads))
    return out

def scores(img, tmpl, x0, x1, y):
    h, w = tmpl.shape
    if y < 0 or y + h > img.shape[0] or x1 <= x0:
        return None
    sub = img[y:y + h, x0:min(x1 + w, img.shape[1])]
    if sub.shape[1] < w:
        return None
    win = np.lib.stride_tricks.sliding_window_view(sub, (h, w))[0]
    keep = tmpl.mean(axis=1) < 0.85
    if keep.sum() < 3:
        return None
    win = win[:, keep, :]
    t = tmpl[keep, :]
    inter = (win & t).sum(axis=(1, 2))
    return 2 * inter / (win.sum(axis=(1, 2)) + t.sum() + 1e-6)

agg = collections.Counter()
rows = []
for name, stem, eng in json.load(open(S / "probe_set.json")):
    d = S / "books" / stem
    omr = sorted(d.glob("*.omr")); mxl = sorted(d.glob("*.mxl"))
    if not omr or not mxl:
        rows.append((stem, "no output")); continue
    man = json.loads((OMR / name / "manifest.json").read_text())
    piece = stem.rsplit("--", 1)[0]
    tb = parse((OMR / name / man["pieces"][piece]["truth"]).read_bytes())
    ob = parse(mxl[0].read_bytes())
    stacks = load_book(omr[0])
    if len(stacks) != len(ob):
        rows.append((stem, "stack count", len(stacks), len(ob))); continue
    if len({e.part for b in tb for e in b.events}) != len({e.part for b in ob for e in b.events}):
        rows.append((stem, "parts differ")); continue
    pairs = align_bars(tb, ob)
    # templates: per book, per shape
    exemplars = collections.defaultdict(list)
    for st in stacks:
        for (shape, staff, x, y, w, h, g) in st["rests"]:
            if staff in st["staves"]:
                exemplars[shape].append((g, st["sheet"], x, y, w, h, st["staves"][staff][2], st["img"]))
    templates = {}
    for shape, ex in exemplars.items():
        ex.sort(key=lambda r: -r[0])
        seen, keep = set(), []
        for g, sn, x, y, w, h, mid, img in ex:
            key = (sn, x, y)
            if key in seen or g < 0.5:
                continue
            seen.add(key)
            keep.append((img[y:y + h, x:x + w].copy(), y - mid, g))
            if len(keep) >= 3:
                break
        if keep:
            templates[shape] = keep
    c = collections.Counter()
    done = set()
    for i, j in pairs:
        st = stacks[j]
        if j in done:
            continue
        done.add(j)
        tr = collections.Counter()
        for e in tb[i].events:
            if e.rest and not e.hidden:
                shape = "WHOLE_REST" if e.measure_rest or e.typ is None else SHAPE.get(e.typ)
                if shape:
                    tr[(e.part, e.staff, shape)] += 1
        for key, sid in st["order"].items():
            pi, sn = key
            mid = st["staves"][sid][2]
            for shape, tmpls in list(templates.items()) + [(s, None) for s in set(s for (p, n, s) in tr if p == pi and n == sn) - set(templates)]:
                want = tr[(pi, sn, shape)]
                fnd = [r for r in st["rests"] if r[0] == shape and r[1] == sid and st["left"] <= r[2] + r[4] / 2 <= st["right"]]
                lost = max(0, want - len(fnd))
                c["lost"] += lost
                c["found by reader"] += min(want, len(fnd))
                c["extra read"] += max(0, len(fnd) - want)
                if tmpls is None:
                    c["lost no template"] += lost
                    continue
                c["lost with template"] += lost
                raw = []
                for tmpl, rel, g in tmpls:
                    h, w = tmpl.shape
                    for k in (-2, -1, 0, 1, 2):
                        for jit in (-1, 0, 1):
                            y = int(round(mid + rel + k * st["il"])) + jit
                            sc = scores(st["img"], tmpl, st["left"] + 2, st["right"] - w, y)
                            if sc is None:
                                continue
                            for ix in np.where(sc >= THETAS[0])[0]:
                                x = st["left"] + 2 + int(ix)
                                cx, cy = x + w / 2, y + h / 2
                                if any(r[2] - 2 <= cx <= r[2] + r[4] + 2 and r[3] - 2 <= cy <= r[3] + r[5] + 2 for r in st["rests"]):
                                    continue
                                if any(a - 1 <= cx <= a + aw + 1 and b - 1 <= cy <= b + bh + 1 for a, b, aw, bh in st["heads"]):
                                    continue
                                raw.append((float(sc[ix]), cx, w))
                raw.sort(key=lambda r: -r[0])
                hits = []
                for sc_, cx_, w_ in raw:
                    if all(abs(cx_ - c2) > w_ * 0.8 for _, c2 in hits):
                        hits.append((sc_, cx_))
                for th in THETAS:
                    n = sum(1 for v, _ in hits if v >= th)
                    c[f"tp{th}"] += min(n, lost)
                    c[f"fp{th}"] += max(0, n - lost)
    c["staffbars"] = len(done)
    rows.append((stem, eng, dict(c)))
    agg.update(c)
    print(stem, eng, {k: c[k] for k in ("lost", "lost no template", "lost with template", "found by reader", "extra read", "tp0.8", "fp0.8", "tp0.9", "fp0.9", "tp0.95", "fp0.95")}, flush=True)
print("ALL", {k: agg[k] for k in sorted(agg)})
json.dump(rows, open(S / "t8.json", "w"))
