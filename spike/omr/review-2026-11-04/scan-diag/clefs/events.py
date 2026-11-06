import json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse
from barparse import align_bars
C = HERE / "cache/runs/marks1"
items = []
for n in json.loads((OMR / "bench-olimpic/split.json").read_text())["inspect"]:
    items.append((n, OMR / "bench-olimpic/truth" / f"{n}.musicxml", C / f"bench-olimpic--{n}--scan.musicxml"))
m = json.loads((OMR / "bench-real/manifest.json").read_text())
for e in m["pdfs"]:
    s = e["pdf"].rsplit("/", 1)[-1][:-4]
    items.append((s, OMR / "bench-real" / m["pieces"][e["piece"]]["truth"], C / f"bench-real--{s}.musicxml"))
for n, t, r in items:
    if not r.exists() or not r.stat().st_size:
        continue
    tb, ob = parse(t.read_bytes()), parse(r.read_bytes())
    pairs = dict(align_bars(tb, ob))
    tc, oc, bad = {}, {}, []
    rows = []
    jmap = {j: i for i, j in pairs.items()}
    for i, b in enumerate(tb):
        ch = {k[1]: v[:2] for k, v in b.clef.items() if tc.get(k[1]) != v[:2]}
        tc.update(ch)
        j = pairs.get(i)
        if j is not None:
            och = {k[1]: v[:2] for k, v in ob[j].clef.items() if oc.get(k[1]) != v[:2]}
            oc.update(och)
        else:
            och = {}
        wrong = [s for s in tc if tc[s] != oc.get(s)]
        if ch and i or och and i or wrong:
            rows.append(f"  bar{i} j={j} tchg={ch} ochg={och} wrong={wrong}")
    if any("wrong=['" in x for x in rows) or any(("tchg={'" in x or "ochg={'" in x) for x in rows):
        print(n, len(tb), len(ob), "first t", {k[1]: v[:2] for k, v in tb[0].clef.items()})
        print("\n".join(rows))
