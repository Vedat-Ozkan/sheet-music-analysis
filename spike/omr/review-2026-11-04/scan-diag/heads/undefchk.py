import json, collections
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r.get("sub") and "nostem" in r["sub"]]
C = collections.Counter(); B = collections.defaultdict(set)
for r in rows:
    tr = open(S / "runs/undef0" / r["name"] / "trace.txt").read().splitlines()
    u = [l for l in tr if l.startswith(f'UNDEF {r["sheet"]} {r["head"]} ')]
    add = any(l.startswith(f'HSADD {r["sheet"]} {r["head"]} ') for l in tr)
    k = ("undef-seed" if any("seed=true" in x for x in u) else "undef-stump") if u else ("linked-later-cut" if add else "linkfail")
    C[k] += 1; B[k].add((r["name"], r["bar"]))
for k, v in C.most_common(): print(k, v, len(B[k]))
