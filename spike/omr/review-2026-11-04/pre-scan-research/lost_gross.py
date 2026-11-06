import collections,json,sys
from lib import *
from whole_bars import exact
sp=json.load(open(OMR/"bench-olimpic/split.json"))
for half,v in (("inspect","m4ins"),("unseen","m4un")):
    T=collections.Counter()
    for p in sp[half]:
        s,st="bench-olimpic",f"{p}--scan"
        td=truth(s,st);tb=parse(td)
        def ex(f):
            if not f.exists() or not f.stat().st_size:return set()
            o=parse(f.read_bytes());q=dict(align_bars(tb,o));return {i for i,b in enumerate(tb) if i in q and exact(b,o[q[i]],True)}
        a,m=ex(RUNS/"marks1"/f"{s}--{st}.musicxml"),ex(RUNS/v/f"{s}--{st}.musicxml")
        T["bars"]+=len(tb);T["base"]+=len(a);T["merged"]+=len(m);T["gained"]+=len(m-a);T["lost"]+=len(a-m)
    print(half,dict(T))
