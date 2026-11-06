import collections,json,sys
from lib import *
from whole_bars import exact
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
import mergexml as M1
import merge2 as M2
items=json.load(open(HERE/"clean60.items.json"))
T=collections.defaultdict(collections.Counter)
def grp(ts):
    if len(ts)==1:return "one-part"
    if ts==(1,2):return "voice+piano"
    if all(x==1 for x in ts) and len(ts)==4:return "four single staves"
    return "other several"
for s,st in items:
    td=truth(s,st);tb=parse(td);tm=canon_map(td);ts=shape(td);g=grp(ts);old="one-part" if len(ts)==1 else "several"
    pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300clean"/f"{s}--{st}.musicxml"
    ha=pa.exists() and pa.stat().st_size;hh=ph.exists() and ph.stat().st_size
    src={"current":pa.read_bytes() if ha else None,"homr":ph.read_bytes() if hh else None}
    src["mergexml_old"]=M1.merge(pa,ph)[0] if hh else src["current"]
    src["merge2"]=M2.merge(pa,ph)[0] if hh else src["current"]
    for v,d in src.items():
        for key in ((g,v),(old,v),("all",v)):
            c=T[key];c["pdfs"]+=1;c["bars"]+=len(tb)
            c["notes"]+=sum(sum(pitches(b).values()) for b in tb)
        if d is None:
            for key in ((g,v),(old,v),("all",v)):T[key]["failed"]+=1
            continue
        o=parse(d);p=dict(align_bars(tb,o));om=canon_map(d)
        e=sum(1 for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True))
        ec=sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om))
        pit=sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
        tim=sum(sum((timed(b)&timed(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
        for key in ((g,v),(old,v),("all",v)):
            c=T[key];c["exact"]+=e;c["exact_pos"]+=ec;c["pitch"]+=pit;c["timed"]+=tim;c["shape_same"]+=shape(d)==ts
for k in sorted(T):
    c=T[k];print(f"{k[0]:20} {k[1]:13} pdfs {c['pdfs']:3} bars {c['bars']:5} strict {c['exact']:5} {100*c['exact']/c['bars']:5.1f}%  by-position {c['exact_pos']:5} {100*c['exact_pos']/c['bars']:5.1f}%  pitch {100*c['pitch']/c['notes']:5.1f} timing {100*c['timed']/c['notes']:5.1f} failed {c['failed']} same-shape {c['shape_same']}")
