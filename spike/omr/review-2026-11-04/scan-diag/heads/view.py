import json, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent)]
from crops import montage
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
tag, pat, out = sys.argv[1:4]
rows = [r for r in json.load(open(S / f"detail-{tag}.json")) if r["kind"] == "missing" and pat in (r.get("sub") or "")]
pick = []
for n, r in enumerate(rows):
    best = None
    for l in open(S / "runs" / tag / r["name"] / "trace.txt"):
        t = l.split()
        if t[0] in ("EXPORT",) and int(t[1]) == r["sheet"] and int(t[4]) == r["staff"]:
            x, y, h, p = int(t[6]), int(t[7]) + int(t[9]) / 2, int(t[9]), int(t[5])
            d = abs(x - r["x"])
            if best is None or d < best[0]:
                best = (d, y, p)
    if best is None: continue
    r["yy"] = best[1] + (r["p"] - best[2]) * r["hh"] / 2
    r["label"] = f'{n} {r["name"][8:20]} b{r["bar"]} m{r["midi"]} {r.get("typ")} p{r["p"]} {r["conf"][:3]}'
    pick.append(r)
montage(pick[:int(sys.argv[4]) if len(sys.argv) > 4 else 20], out, cols=5, size=230)
print(len(pick))
