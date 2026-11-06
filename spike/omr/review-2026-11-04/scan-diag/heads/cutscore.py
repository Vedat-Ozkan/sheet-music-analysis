import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from barparse import parse, align_bars, pitches
from whole_bars import exact
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
items = {it["name"]: it for it in json.load(open(S.parent / "scan-diag/items/native-inspect/items.json"))}
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r.get("sub") and "nostem" in r["sub"]]
for d in sorted((S / "runs/cut").iterdir()):
    m = list(d.glob("*.mxl"))
    if not m: print(d.name, "no reading"); continue
    t = Path(items[d.name]["truth"]).read_bytes()
    a = next((S / "runs/base" / d.name).glob("*.mxl")).read_bytes(); b = m[0].read_bytes()
    tb, ab, bb = parse(t), parse(a), parse(b); pa, pb = dict(align_bars(tb, ab)), dict(align_bars(tb, bb))
    sc = lambda ob, pr: [(int(exact(tb[i], ob[pr[i]], True)), sum((pitches(tb[i]) & pitches(ob[pr[i]])).values())) if pr.get(i) is not None else None for i in range(len(tb))]
    back = tot = 0
    for r in rows:
        if r["name"] == d.name:
            tot += 1; i = r["bar"]; j = pb.get(i)
            if j is not None and pitches(bb[j])[r["midi"]] > pitches(ab[pa[i]])[r["midi"]]: back += 1
    print(d.name[8:24], "heads back", back, "of", tot, "base", sc(ab, pa), "cut", sc(bb, pb), "n", [sum(pitches(x).values()) for x in tb])
