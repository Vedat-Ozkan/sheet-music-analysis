import json, sys, collections
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = json.load(open(S / "attrib-base.json"))
out = collections.defaultdict(list)
for r in rows:
    if r["kind"] == "missing" and r["stage"] in ("no_candidate", "candidate_seedconflict", "removed"):
        pad = r["tol"] + 1.5 * r["hh"]
        out[r["name"]].append(f'{r["sheet"]} {r["staff"]} {r["p"]} {int(r["x"] - pad)} {int(r["x"] + pad)}')
(S / "runs/probe").mkdir(parents=True, exist_ok=True)
for k, v in out.items():
    (S / "runs/probe" / (k + ".txt")).write_text("\n".join(v) + "\n")
print(len(out))
