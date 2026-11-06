import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path("/home/kema/projects/sheet-music-plugin")
sys.path[:0] = [str(ROOT / "spike/omr/speed"), str(ROOT), str(Path(__file__).parent)]
from whole_bars import OMR, HERE, score_pdf
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
T0, T1 = collections.Counter(), collections.Counter(); rows = []; bad = 0
for f in sorted((S / "clean/led3").glob("*.musicxml")):
    s, stem = f.name[:-9].split("--", 1)
    m = json.loads((OMR / s / "manifest.json").read_text())
    e = next(x for x in m["pdfs"] if x["pdf"].rsplit("/", 1)[-1][:-4] == stem)
    t = (OMR / s / m["pieces"][e["piece"]]["truth"]).read_bytes()
    a, b = collections.Counter(), collections.Counter()
    try:
        score_pdf(t, (HERE / "cache/runs/marks1" / f.name).read_bytes(), a); score_pdf(t, f.read_bytes(), b)
    except Exception:
        bad += 1; continue
    T0.update(a); T1.update(b); rows.append((b["exact"] - a["exact"], stem[:32], a["bars"]))
K = ("pdfs", "bars", "exact", "pitch_notes", "timed_notes", "notes")
print({k: T0[k] for k in K}); print({k: T1[k] for k in K}); print("unscored", bad, "better", sum(r[0] > 0 for r in rows), "worse", sum(r[0] < 0 for r in rows), sorted(r for r in rows if r[0])[:5])
def led(tr):
    a, d = set(), 0
    for l in tr:
        t = l.split()
        if t[0] == "LEDGER" and t[8] not in ("noref", "null") and float(t[8].split("/")[0]) >= float(t[8].split("/")[1]): a.add(tuple(t[1:8]))
        d += t[0] == "LEDGERDISCARD"
    return len(a), d
A = D = n = ns = 0
for p in (S / "cleantrace").glob("*/trace.txt"):
    if list(p.parent.glob("*.mxl")):
        tr = p.read_text().splitlines(); a, d = led(tr); A += a; D += d; n += 1; ns += sum(l.startswith("NOSTEM") for l in tr)
print("clean traces", n, "ledgers", A, "discarded", D, "nostem", ns)
A = D = ns = 0
for p in (S / "runs/link").glob("*/trace.txt"):
    tr = p.read_text().splitlines(); a, d = led(tr); A += a; D += d; ns += sum(l.startswith("NOSTEM") for l in tr)
print("scan traces 25 ledgers", A, "discarded", D, "nostem", ns)
