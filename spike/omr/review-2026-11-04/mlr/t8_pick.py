import sys, collections, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
rows = []
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    if len({e.part for b in tb for e in b.events}) != len({e.part for b in ob for e in b.events}):
        continue
    pairs = align_bars(tb, ob)
    lost = found = 0
    for i, j in pairs:
        tr = collections.Counter((e.part, e.staff, e.onset, e.dur) for e in tb[i].events if e.rest and not e.hidden and not e.measure_rest)
        orr = collections.Counter((e.part, e.staff, e.onset, e.dur) for e in ob[j].events if e.rest)
        lost += sum((tr - orr).values())
        found += sum((tr & orr).values())
    rows.append((lost, found, name, stem, eng))
out = []
for eng, k in (("ms", 5), ("ly", 3), ("ly-old", 3), ("scan", 3), ("real-scan-peters", 1), ("real-scan-schirmer", 1), ("lilypond-mutopia", 0)):
    sel = sorted([r for r in rows if r[4] == eng and r[1] >= 5], reverse=True)[:k]
    out += sel
for r in out:
    print(r)
json.dump([[r[2], r[3], r[4]] for r in out], open(Path(__file__).parent / "probe_set.json", "w"))
