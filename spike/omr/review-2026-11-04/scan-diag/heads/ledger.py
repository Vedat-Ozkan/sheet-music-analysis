import collections, json, sys
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
tag = sys.argv[1]
rows = [r for r in json.load(open(S / "detail-probe1.json")) if "not_scanned" in (r.get("sub") or "")]
C = collections.Counter()
for r in rows:
    led, st, se = [], [], []
    sid, sh = r["staff"], r["sheet"]
    il = r["hh"]
    idx = (abs(r["p"]) - 4 + 1) // 2 * (1 if r["p"] > 0 else -1)
    for l in open(S / "runs" / tag / r["name"] / "trace.txt"):
        t = l.split()
        if t[0] == "LEDGER" and int(t[1]) == sh and int(t[2]) == sid:
            x, w = int(t[4]), int(t[6])
            if x < r["x"] + 1.5 * il and x + w > r["x"] - 1.5 * il:
                led.append((int(t[3]), x, int(t[5]), w, int(t[7]), t[8], (t[9] if len(t) > 9 else "-")[:70]))
    print(r["name"][8:20], "b", r["bar"], "p", r["p"], "idx", idx, "x", r["x"], "il", il, [q for q in led if q[0] == idx][:3], "others", [q[0] for q in led if q[0] != idx][:3])
