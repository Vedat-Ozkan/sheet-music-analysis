import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
OMR = Path("/home/kema/projects/sheet-music-plugin/spike/omr")
TR = Path(__file__).resolve().parent.parent / "heads/trace.sh"
tag, jobs, which = sys.argv[1], int(sys.argv[2]), sys.argv[3]
aud, extra = sys.argv[4], sys.argv[5:]
items = {}
for n in json.loads((OMR / "bench-olimpic/split.json").read_text())["inspect"]:
    items[n] = OMR / "bench-olimpic/pdfs" / f"{n}--scan.pdf"
m = json.loads((OMR / "bench-real/manifest.json").read_text())
for e in m["pdfs"]:
    items[e["pdf"].rsplit("/", 1)[-1][:-4]] = OMR / "bench-real" / e["pdf"]
names = sorted(items) if which == "all" else which.split(",")
def one(n):
    o = SCR / "clefs/runs" / tag / n
    if not list(o.glob("*.mxl")):
        subprocess.run([str(TR), str(o), str(items[n]), *extra], env={**os.environ, "AUD": aud})
with ThreadPoolExecutor(jobs) as p:
    list(p.map(one, names))
print("done", tag, sum(bool(list((SCR / "clefs/runs" / tag / n).glob("*.mxl"))) for n in names), "of", len(names))
