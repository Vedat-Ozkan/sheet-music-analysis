import json, sys, warnings, collections
import xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse
from barparse import align_bars
C = HERE / "cache/runs/marks1"
SC = dict(zip("CDEFGAB", range(7)))
SHIFT = {("G", "F"): -12, ("F", "G"): 12, ("G", "G"): 0, ("F", "F"): 0}
def unz(d):
    if d[:2] != b"PK": return d
    import zipfile, io
    z = zipfile.ZipFile(io.BytesIO(d))
    return z.read(next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and "META" not in n))
def measures(data):
    root = ET.fromstring(unz(data))
    out = []
    for part in root.findall("part"):
        for i, m in enumerate(part.findall("measure")):
            while len(out) <= i: out.append(collections.defaultdict(collections.Counter))
            for n in m.findall("note"):
                p = n.find("pitch")
                if p is None: continue
                s = n.findtext("staff", "1")
                out[i][s][int(p.findtext("octave")) * 7 + SC[p.findtext("step")]] += 1
    return out
c = json.loads(Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/scan-diag/classified.json").read_text())
split = json.loads((OMR / "bench-olimpic/split.json").read_text())["inspect"]
m = json.loads((OMR / "bench-real/manifest.json").read_text())
files = {}
for n in split: files["ol:" + n] = (OMR / "bench-olimpic/truth" / f"{n}.musicxml", C / f"bench-olimpic--{n}--scan.musicxml")
for e in m["pdfs"]:
    s = e["pdf"].rsplit("/", 1)[-1][:-4]
    files["real:" + s] = (OMR / "bench-real" / m["pieces"][e["piece"]]["truth"], C / f"bench-real--{s}.musicxml")
for k, v in c.items():
    if k not in files: continue
    rows = [r for r in v if r.get("first") == "clef"]
    if not rows: continue
    t, r = files[k]
    td, rd = t.read_bytes(), r.read_bytes()
    tm, om = measures(td), measures(rd)
    tb, ob = parse(td), parse(rd)
    pairs = dict(align_bars(tb, ob))
    print(k)
    for b in rows:
        i, j = b["bar"], b["j"]
        for s in sorted(set(tm[i]) | set(om[j])):
            tn = sum(tm[i][s].values())
            best = {}
            for sh in (0, -12, 12):
                ctr = collections.Counter({p + sh: n for p, n in om[j][s].items()})
                best[sh] = sum((tm[i][s] & ctr).values())
            print(f"  bar{i} j{j} staff{s} truth_notes={tn} read_notes={sum(om[j][s].values())} asread={best[0]} readG->F(-12)={best[-12]} readF->G(+12)={best[12]} flagged={s in b['clef']}")
