import collections,json,sys
from lib import *
from whole_bars import exact
import merge3 as M3
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from merge2 import key_alter
PC={"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
def scale(f):
    return {(PC[s]+key_alter(f,s))%12 for s in PC}
def fifths_at(bars,j,part):
    f=0
    for b in bars[:j+1]:
        for (p,n),v in b.key.items():
            if p==part:f=v
    return f
def out_of_key(a,h,j,k,x,y):
    f=fifths_at(a,j,x[0]);sc=scale(f)
    n=lambda ev:sum(1 for e in ev for m in e.midis if m%12 not in sc)
    return n([e for e in h[k].events if (e.part,e.staff)==y])>n([e for e in a[j].events if (e.part,e.staff)==x])
def jump(bars,j,key):
    me=[m for e in bars[j].events if (e.part,e.staff)==key for m in e.midis]
    nb=[m for q in (j-1,j+1) if 0<=q<len(bars) for e in bars[q].events if (e.part,e.staff)==key for m in e.midis]
    if not me or not nb:return 0
    return abs(sum(me)/len(me)-sum(nb)/len(nb))
def own_jump(a,h,j,k,x,y):
    return jump(h,k,y)>jump(a,j,x)
VARIANTS={"as written":("as_written",None),"keep current unless short":("only_if_current_short",None),"veto: homr has more out-of-key notes":("as_written",out_of_key),"veto: homr jumps more than current":("as_written",own_jump)}
def run(items,hvar):
    res=collections.defaultdict(dict)
    for s,st in items:
        pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/hvar/f"{s}--{st}.musicxml"
        if not ph.exists() or not ph.stat().st_size:continue
        td=truth(s,st);tb=parse(td);tm=canon_map(td)
        base=None
        if pa.exists() and pa.stat().st_size:
            o=parse(pa.read_bytes());p=dict(align_bars(tb,o));base={i for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True)}
        for name,(rule,veto) in VARIANTS.items():
            d,_=M3.merge(pa,ph,rule,veto)
            o=parse(d);p=dict(align_bars(tb,o));got={i for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True)}
            b0=base or set()
            res[st][name]=(len(got),len(got-b0),len(b0-got),len(tb),len(b0))
    return res
def show(label,res,per):
    print(label)
    names=list(VARIANTS)
    for n in names:
        tot=[0,0,0,0,0]
        for st,v in res.items():
            for i in range(5):tot[i]+=v[n][i]
        piece=" ".join(f"{v[n][0]}" for st,v in res.items()) if per else ""
        worst=max((v[n][2] for v in res.values()),default=0)
        print(f"  {n:38} exact {tot[0]:4} of {tot[3]:4} (base {tot[4]}) gained {tot[1]:3} lost {tot[2]:3} worst piece lost {worst} {piece}")
show("five (Bach Beethoven Grieg Chopin Mozart)",run(FIVE,"homr300"),True)
sp=json.load(open(OMR/"bench-olimpic/split.json"))
show("olimpic inspect half",run([("bench-olimpic",f"{p}--scan") for p in sp["inspect"]],"homr300ol"),False)
items=[tuple(x) for x in json.load(open(HERE/"clean60.items.json"))]
show("clean voice+piano (30)",run([x for x in items if shape(truth(*x))==(1,2)],"homr300clean"),False)
