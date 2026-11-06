import collections,json,sys
from lib import *
from whole_bars import exact
import merge3 as M3
def same_classes(a,h,j,k,x,y):
    pc=lambda ev:collections.Counter(m%12 for e in ev for m in e.midis)
    return pc([e for e in a[j].events if (e.part,e.staff)==x])==pc([e for e in h[k].events if (e.part,e.staff)==y])
def run(items,hvar):
    T=collections.Counter()
    for s,st in items:
        pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/hvar/f"{s}--{st}.musicxml"
        if not ph.exists() or not ph.stat().st_size:continue
        td=truth(s,st);tb=parse(td)
        for name,v in (("as written",None),("octave veto",same_classes)):
            d,_=M3.merge(pa,ph,"as_written",v);o=parse(d);p=dict(align_bars(tb,o))
            n=sum(1 for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True));T[name]+=n
            if len(items)<8:T[name+" per piece"]=str(T.get(name+" per piece",""))+f" {n}"
    return dict(T)
print("five",run(FIVE,"homr300"))
sp=json.load(open(OMR/"bench-olimpic/split.json"))
print("inspect",run([("bench-olimpic",f"{p}--scan") for p in sp["inspect"]],"homr300ol"))
items=[tuple(x) for x in json.load(open(HERE/"clean60.items.json"))]
print("clean v+p",run([x for x in items if shape(truth(*x))==(1,2)],"homr300clean"))
