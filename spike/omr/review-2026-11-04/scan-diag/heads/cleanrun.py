import collections, json, os, sys, time, warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path("/home/kema/projects/sheet-music-plugin")
sys.path[:0] = [str(ROOT / "spike/omr/speed"), str(ROOT)]
from whole_bars import OMR, HERE, score_pdf
sys.path[:0] = [str(ROOT / "spike/omr/bench")]
os.chdir(ROOT / "spike/omr/speed")
import hashlib
import run as bench
from engine import read_pdf as reader
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
name, jobs = sys.argv[1], int(sys.argv[2])
SETS = sys.argv[3].split(",") if len(sys.argv) > 3 else ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-tune2", "bench-oldly"]
wrap = str(S / "w" / name / "bin/Audiveris")
out = S / "clean" / name; out.mkdir(parents=True, exist_ok=True)
items = []
for s in SETS:
    m = json.loads((OMR / s / "manifest.json").read_text())
    for e in m["pdfs"]:
        stem = e["pdf"].rsplit("/", 1)[-1][:-4]
        if "scan" in stem: continue
        base = HERE / "cache/runs/marks1" / f"{s}--{stem}.musicxml"
        if base.exists():
            items.append((s, stem, OMR / s / e["pdf"], OMR / s / m["pieces"][e["piece"]]["truth"], base))
if os.environ.get("INSPECT"):
    items = []
    bo = json.loads((OMR / "bench-olimpic/split.json").read_text())["inspect"]
    for n in bo:
        base = HERE / "cache/runs/marks1" / f"bench-olimpic--{n}--scan.musicxml"
        items.append(("bench-olimpic", n + "--scan", OMR / "bench-olimpic/pdfs" / f"{n}--scan.pdf", OMR / "bench-olimpic/truth" / f"{n}.musicxml", base))
    m = json.loads((OMR / "bench-real/manifest.json").read_text())
    for e in m["pdfs"]:
        stem = e["pdf"].rsplit("/", 1)[-1][:-4]
        items.append(("bench-real", stem, OMR / "bench-real" / e["pdf"], OMR / "bench-real" / m["pieces"][e["piece"]]["truth"], HERE / "cache/runs/marks1" / f"bench-real--{stem}.musicxml"))
    out = S / "scan" / name; out.mkdir(parents=True, exist_ok=True)
items = sorted(items, key=lambda i: hashlib.sha256(i[1].encode()).hexdigest())[:int(os.environ.get("SAMPLE", "60"))]
def one(it):
    s, stem, pdf, truth, base = it
    f = out / f"{s}--{stem}.musicxml"
    t = truth.read_bytes()
    r0, r1 = collections.Counter(), collections.Counter()
    if base.exists():
        score_pdf(t, base.read_bytes(), r0)
    else:
        r0["bars"] = len(__import__("whole_bars").parse(t))
    try:
        if not f.exists():
            f.write_bytes(reader.read_pdf(pdf.read_bytes(), wrap, raw=bench.production_raw(reader.audiveris_read)).musicxml)
        score_pdf(t, f.read_bytes(), r1)
    except Exception as e:
        r1["failed"] = 1
    return s, stem, r0, r1
T0, T1 = collections.Counter(), collections.Counter(); rows = []
with ThreadPoolExecutor(jobs) as p:
    for s, stem, r0, r1 in p.map(one, items):
        T0.update(r0); T1.update(r1)
        rows.append(dict(s=s, stem=stem, e0=r0["exact"], e1=r1["exact"], b=r0["bars"], p0=r0["pitch_notes"], p1=r1["pitch_notes"], t0=r0["timed_notes"], t1=r1["timed_notes"], failed=r1["failed"]))
(out / "rows.json").write_text(json.dumps(rows))
print({k: T0[k] for k in ("pdfs", "bars", "exact", "pitch_notes", "timed_notes", "notes")})
print({k: T1[k] for k in ("pdfs", "bars", "exact", "pitch_notes", "timed_notes", "notes", "failed")})
print("better", sum(r["e1"] > r["e0"] for r in rows), "worse", sum(r["e1"] < r["e0"] for r in rows), sorted([(r["e1"] - r["e0"], r["stem"][:30], r["b"]) for r in rows if r["e1"] != r["e0"]])[:10])
