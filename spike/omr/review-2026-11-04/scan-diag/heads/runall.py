import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).parent
OUT = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads/runs")
SD = HERE.parent
tag, jobs = sys.argv[1], int(sys.argv[2])
extra = sys.argv[3:]
c = json.loads((Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/scan-diag/classified.json")).read_text())
items = {}
ni = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/scan-diag/items/"
for t in ("native-inspect", "real-z1"):
    for it in json.loads(Path(ni + t + "/items.json").read_text()):
        items[it["name"]] = it
names = sorted({k.split(":", 1)[1] for k, v in c.items() if any(b.get("first") == "note_missing_or_extra" for b in v)})
def one(n):
    o = OUT / tag / n
    if list(o.glob("*.mxl")):
        return
    subprocess.run([str(HERE / "trace.sh"), str(o), items[n]["pdf"], *extra], env={**os.environ, **({"HEADPROBE": str(OUT / "probe" / (n + ".txt"))} if (OUT / "probe" / (n + ".txt")).exists() and tag.startswith("probe") else {})})
with ThreadPoolExecutor(jobs) as p:
    list(p.map(one, names))
for n in names:
    print(n, len(list((OUT / tag / n).glob("*.mxl"))), sum(1 for l in open(OUT / tag / n / "trace.txt") if l.startswith("EXPORT")))
