import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import parse
from barparse import align_bars
from pathlib import Path
import collections
items = json.loads(Path("items/real-z1/items.json").read_text())
SC = dict(zip("CDEFGAB", range(7)))
for it in items:
    tb, ob = parse(Path(it["truth"]).read_bytes()), parse(Path("runs/real-z1", it["name"] + ".musicxml").read_bytes())
    pairs = dict(align_bars(tb, ob))
    tst = []; c = {}
    for b in tb: c.update(b.clef); tst.append(dict(c))
    ost = []; c = {}
    for b in ob: c.update(b.clef); ost.append(dict(c))
    res = collections.Counter()
    for i, j in pairs.items():
        for k, v in tst[i].items():
            o = ost[j].get(k)
            if o is None or o[:2] != v[:2]:
                res[f"staff{k[1]} truth {v[0]}{v[1]} read {o[0]+o[1] if o else None}"] += 1
    print(it["name"][:30], dict(res))
