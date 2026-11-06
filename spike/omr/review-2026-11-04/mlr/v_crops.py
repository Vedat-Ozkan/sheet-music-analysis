import collections, hashlib, io, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
out = S / "crops"
out.mkdir(exist_ok=True)
pool = []
books = {}
for name, stem, eng in json.load(open(S / "probe_set.json")):
    d = S / "books" / stem
    omr = sorted(d.glob("*.omr")); mxl = sorted(d.glob("*.mxl"))
    if not omr or not mxl:
        continue
    man = json.loads((OMR / name / "manifest.json").read_text())
    piece = stem.rsplit("--", 1)[0]
    tb = parse((OMR / name / man["pieces"][piece]["truth"]).read_bytes())
    ob = parse(mxl[0].read_bytes())
    z = zipfile.ZipFile(omr[0])
    sheets = sorted({int(m.group(1)) for n in z.namelist() if (m := re.match(r"sheet#(\d+)/sheet#\d+\.xml", n))})
    stacks = []
    for sn in sheets:
        root = ET.fromstring(z.read(f"sheet#{sn}/sheet#{sn}.xml"))
        il = int(root.find("scale/interline").get("main"))
        for sys_ in root.iter("system"):
            ys = [float(p.get("y")) for st in sys_.iter("staff") if st.find("lines") is not None for l in st.find("lines").findall("line") for p in l.findall("point")]
            nst = sum(1 for st in sys_.iter("staff") if st.find("lines") is not None)
            for st_ in sys_.findall("stack"):
                stacks.append((sn, int(st_.get("left")), int(st_.get("right")), min(ys), max(ys), il, nst))
    if len(stacks) != len(ob):
        continue
    if len({e.part for b in tb for e in b.events}) != len({e.part for b in ob for e in b.events}):
        continue
    clefs, keys, full = {}, 0, None
    pairs = dict((j, i) for i, j in align_bars(tb, ob))
    for j, b in enumerate(ob):
        clefs.update(b.clef)
        for v in b.key.values():
            keys = v
        i = pairs.get(j)
        if i is None or b.full is None:
            continue
        v = collections.defaultdict(lambda: F(0))
        for e in b.events:
            v[(e.part, e.voice)] = max(v[(e.part, e.voice)], e.onset + e.dur)
        longest = collections.defaultdict(lambda: F(0))
        for (p, _), l in v.items():
            longest[p] = max(longest[p], l)
        if any(l != b.full for l in longest.values()) and timed(b) != timed(tb[i]) and pitches(b) and b.full == tb[i].full:
            pool.append((hashlib.sha256(f"{stem}{j}".encode()).hexdigest(), name, stem, eng, j, i, dict(clefs), keys, b.full))
    books[stem] = (omr[0], stacks, ob, tb)
pool.sort()
sel, per = [], collections.Counter()
for r in pool:
    if per[r[2]] < 3 and len(sel) < 24:
        sel.append(r); per[r[2]] += 1
print("pool", len(pool), "selected", len(sel), collections.Counter(r[3] for r in sel))
meta = []
STEP = "C C# D Eb E F F# G Ab A Bb B".split()
for n, (h, name, stem, eng, j, i, clefs, key, full) in enumerate(sel):
    omr, stacks, ob, tb = books[stem]
    sn, left, right, top, bot, il, nst = stacks[j]
    z = zipfile.ZipFile(omr)
    img = Image.open(io.BytesIO(z.read(f"sheet#{sn}/BINARY.png"))).convert("L")
    x0 = max(0, left - 3 * il)
    x1 = min(img.size[0], right + 3 * il)
    y0 = max(0, int(top) - 6 * il)
    y1 = min(img.size[1], int(bot) + 6 * il)
    crop = img.crop((x0, y0, x1, y1))
    if crop.size[0] < 700:
        f = 700 / crop.size[0]
        crop = crop.resize((700, int(crop.size[1] * f)))
    crop.save(out / f"{n:02d}.png")
    lines = [f"Bar length: {full} quarter notes. Key signature fifths in force: {key}. Clefs in force (part, staff -> sign, line): " + str({f'{k[0]}/{k[1]}': v[:2] for k, v in clefs.items()})]
    staves = collections.defaultdict(list)
    for e in sorted(ob[j].events, key=lambda e: (e.part, e.staff, e.voice, e.onset)):
        what = "rest" if e.rest else "+".join(f"{STEP[m % 12]}{m // 12 - 1}" for m in e.midis)
        staves[(e.part, e.staff, e.voice)].append(f"t={float(e.onset):g} {what} dur={float(e.dur):g} ({e.typ})")
    for k, v in staves.items():
        lines.append(f"part {k[0]} staff {k[1]} voice {k[2]}: " + "; ".join(v))
    (out / f"{n:02d}.txt").write_text("\n".join(lines) + "\n")
    meta.append(dict(n=n, stem=stem, set=name, eng=eng, j=j, i=i, nstaves=len({(e.part, e.staff) for e in ob[j].events})))
json.dump(meta, open(S / "crops_meta.json", "w"))
