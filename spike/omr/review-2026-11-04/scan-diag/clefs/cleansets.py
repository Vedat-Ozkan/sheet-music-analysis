import collections, json, sys
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads") / sys.argv[1] / sys.argv[2] / "rows.json"
R = json.loads(S.read_text())
T = collections.defaultdict(collections.Counter)
for r in R:
    for k in ("e0","e1","b","p0","p1","t0","t1","failed"):
        T[r["s"]][k] += r[k]; T["ALL"][k] += r[k]
    T[r["s"]]["n"] += 1; T["ALL"]["n"] += 1
for s, c in T.items():
    print(f"{s:15} pdfs={c['n']:3} bars={c['b']:5} exact {c['e0']}->{c['e1']} ({100*c['e0']/max(c['b'],1):.2f}->{100*c['e1']/max(c['b'],1):.2f}) pitch {c['p0']}->{c['p1']} timed {c['t0']}->{c['t1']} failed={c['failed']}")
print("changed:", [(r['stem'][:34], r['e0'], r['e1'], r['p1']-r['p0'], r['t1']-r['t0']) for r in R if r['e0']!=r['e1'] or r['p0']!=r['p1'] or r['t0']!=r['t1']])
