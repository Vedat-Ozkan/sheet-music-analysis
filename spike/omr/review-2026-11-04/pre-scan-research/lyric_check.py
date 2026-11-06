import collections,json,sys
from lib import *
import merge3 as M3
from whole_bars import exact
items=[tuple(x) for x in json.load(open(HERE/"clean60.items.json"))]
T=collections.Counter()
for s,st in items:
    td=truth(s,st)
    if shape(td)!=(1,2):continue
    pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300clean"/f"{s}--{st}.musicxml"
    if not ph.exists() or not ph.stat().st_size:continue
    n=lambda d:sum(1 for _ in root_of(d).iter("lyric"))
    d,info=M3.merge(pa,ph);T["current lyrics"]+=n(pa.read_bytes());T["merged lyrics"]+=n(d)
    tb=parse(td);o=parse(d);p=dict(align_bars(tb,o));tm,om=canon_map(td),canon_map(d)
    T["merged exact"]+=sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om));T["bars"]+=len(tb)
print(dict(T))
