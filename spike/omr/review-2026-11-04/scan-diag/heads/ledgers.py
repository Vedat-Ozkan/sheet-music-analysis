import collections, json, sys
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if "not_scanned" in (r.get("sub") or "")]
C = collections.Counter(); bars = collections.defaultdict(set)
for r in rows:
    il = r["hh"]; idx = (abs(r["p"]) - 4 + 1) // 2 * (1 if r["p"] > 0 else -1)
    lines = open(S / "runs/hs" / r["name"] / "trace.txt").read().splitlines()
    near = lambda x, w: x < r["x"] + 1.5 * il and x + w > r["x"] - 1.5 * il
    disc, led, stick = None, None, False
    for l in lines:
        t = l.split()
        if t[0] == "LEDGERDISCARD" and int(t[1]) == r["sheet"] and int(t[2]) == r["staff"] and near(int(t[4]), int(t[6])) and abs(int(t[3])) <= abs(idx):
            disc = (int(t[3]), " ".join(t[8:]))
        if t[0] == "LEDGER" and int(t[1]) == r["sheet"] and int(t[2]) == r["staff"] and int(t[3]) == idx and near(int(t[4]), int(t[6])) and t[8] != "noref":
            g = t[8].split("/")[0] if t[8] != "null" else "-1"
            if led is None or float(g) > led[0]: led = (float(g), t[9] if len(t) > 9 else "")
    if disc: k = "ledger accepted, then discarded by post-analysis: " + disc[1].split(" ")[0] if "noprev" in disc[1] else "ledger accepted, then discarded by post-analysis (+-1 sigma)"
    elif led and led[0] >= 0.08: k = "ledger accepted, kept (head not scanned?)"
    elif led: k = "ledger stick rejected (grade 0: LPitch/RPitch or length)"
    else: k = "no stick at that line"
    C[k] += 1; bars[k].add((r["name"], r["bar"]))
    print(r["name"][8:20], r["bar"], r["p"], k[:40], disc[1][:75] if disc else "", (led[1][-40:] if led else ""))
for k, v in C.most_common(): print(v, len(bars[k]), k)
