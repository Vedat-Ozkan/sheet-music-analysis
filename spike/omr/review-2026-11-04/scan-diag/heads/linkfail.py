import json, collections
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r.get("sub") and "nostem" in r["sub"]]
seen = set()
for r in rows:
    if (r["name"], r["head"]) in seen: continue
    seen.add((r["name"], r["head"]))
    tr = open(S / "runs/link" / r["name"] / "trace.txt").read().splitlines()
    add = [l for l in tr if l.startswith(f'HSADD {r["sheet"]} {r["head"]} ')]
    if add: continue
    fail = [l for l in tr if l.startswith(f'LINKFAIL {r["sheet"]} {r["head"]} ')]
    print(r["name"][8:20], r["bar"], r["head"], "fails", len(fail))
    if fail: print("  ", fail[-1][:520].replace("org.audiveris.omr.", ""))
