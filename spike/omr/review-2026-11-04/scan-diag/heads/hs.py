import json, collections
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r.get("sub") and "nostem" in r["sub"]]
C = collections.Counter()
for r in rows:
    add, cut, rm = [], [], None
    for l in open(S / "runs/hs" / r["name"] / "trace.txt"):
        t = l.split()
        if t[0] in ("HSADD", "HSCUT") and int(t[1]) == r["sheet"] and int(t[2]) == r["head"]:
            (add if t[0] == "HSADD" else cut).append((t[3], t[4].split(">")[1:4]))
        if t[0] == "STEMREMOVE" and int(t[1]) == r["sheet"] and t[8][6:].strip(",") and str(r["head"]) in t[8][6:].split(","):
            rm = t[9]
    k = "added" if add else "neveradded"
    if cut: k += " cut:" + ",".join(sorted({f.split(":")[0] for c in cut for f in c[1][:2]}))
    C[k] += 1
    print(r["name"][8:20], r["bar"], r["head"], k, len(add), rm[:90] if rm else "")
print(C)
