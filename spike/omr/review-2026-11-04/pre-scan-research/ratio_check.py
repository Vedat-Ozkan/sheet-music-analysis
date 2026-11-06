import collections,json,sys
from lib import *
sp=json.load(open(OMR/"bench-olimpic/split.json"))
items=[tuple(x) for x in json.load(open(HERE/"clean60.items.json"))]
SETS={"five":(FIVE,"homr300"),"inspect":([("bench-olimpic",f"{p}--scan") for p in sp["inspect"]],"homr300ol"),"clean60":(items,"homr300clean"),"unseen":([("bench-olimpic",f"{p}--scan") for p in sp["unseen"]],"homr300un")}
for n,(its,hv) in SETS.items():
    c=collections.Counter();mn=9;mx=0
    for s,st in its:
        pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/hv/f"{s}--{st}.musicxml"
        if not pa.exists() or not pa.stat().st_size or not ph.exists() or not ph.stat().st_size:c["no pair"]+=1;continue
        a,h=parse(pa.read_bytes()),parse(ph.read_bytes());r=len(a)/max(len(h),1);c["n"]+=1;mn=min(mn,r);mx=max(mx,r)
        c["<0.5"]+=r<.5;c[">1.5"]+=r>1.5;c["<0.75"]+=r<.75;c[">1.25"]+=r>1.25
    print(n,dict(c),"range",round(mn,2),round(mx,2))
