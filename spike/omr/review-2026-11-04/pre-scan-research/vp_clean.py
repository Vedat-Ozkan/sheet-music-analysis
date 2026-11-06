import collections,json,sys
from lib import *
from whole_bars import exact
import merge3 as M3
from merge3 import sub_bars
items=json.load(open(HERE/"clean60.items.json"))
ROLE={0:"voice",1:"piano upper",2:"piano lower"}
def grp(ts):
    if len(ts)==1:return "one-part"
    if ts==(1,2):return "voice+piano"
    if all(x==1 for x in ts) and len(ts)==4:return "four single staves"
    return "other several"
want=sys.argv[1] if len(sys.argv)>1 else "voice+piano"
S=collections.defaultdict(collections.Counter);B=collections.Counter();drift=collections.Counter();res=collections.defaultdict(collections.Counter)
for s,st in items:
    td=truth(s,st);ts=shape(td);g=grp(ts)
    if g!=want:continue
    pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300clean"/f"{s}--{st}.musicxml"
    if not (pa.exists() and pa.stat().st_size and ph.exists() and ph.stat().st_size):
        B["skipped"]+=1;continue
    da,dh=pa.read_bytes(),ph.read_bytes()
    tb=parse(td);ab=parse(da);hb=parse(dh);ot,oa,oh=staff_order(td),staff_order(da),staff_order(dh)
    pp=per_part_bars(dh);drift["homr parts differ in bar count" if len(set(pp))>1 else "homr parts same bar count"]+=1
    drift["homr bars total differ from truth" if len(hb)!=len(tb) else "homr bars total equal truth"]+=1
    if len(oa)!=len(ot) or len(oh)!=len(ot):
        B["shape_mismatch_pdfs"]+=1
    B["bars"]+=len(tb)
    pa_=dict(align_bars(tb,ab))
    hgroups=collections.defaultdict(list)
    for i,y in enumerate(oh[:len(ot)]):hgroups[y[0]].append(i)
    pos_h={}
    for hp,idx in hgroups.items():
        tk={ot[i] for i in idx};hk={oh[i] for i in idx}
        pr=dict(align_bars(sub_bars(tb,tk),sub_bars(hb,hk)))
        for i in idx:pos_h[i]=pr
    for i,b in enumerate(tb):
        ca=hc=orc=True
        for z,tkey in enumerate(ot):
            te=[e for e in b.events if (e.part,e.staff)==tkey]
            ae=[e for e in ab[pa_[i]].events if z<len(oa) and (e.part,e.staff)==oa[z]] if i in pa_ else None
            he=None
            if z in pos_h and i in pos_h[z]:
                he=[e for e in hb[pos_h[z][i]].events if (e.part,e.staff)==oh[z]]
            ra=ae is not None and staff_exact(te,ae)
            rh=he is not None and staff_exact(te,he)
            role=ROLE.get(z,str(z)) if want=="voice+piano" else ("upper" if z%2==0 else "lower") if want=="one-part" else f"staff{z}"
            c=S[role];c["bars"]+=1;c["current"]+=ra;c["homr"]+=rh;c["either"]+=ra or rh;c["homr_only"]+=rh and not ra;c["current_only"]+=ra and not rh;c["both"]+=ra and rh
            ca&=ra;hc&=rh;orc&=(ra or rh)
        B["current"]+=ca;B["homr"]+=hc;B["oracle"]+=orc
    for rule in M3.RULES:
        data,info=M3.merge(pa,ph,rule)
        o=parse(data);p=dict(align_bars(tb,o));om=canon_map(data);tm=canon_map(td)
        res[rule]["exact"]+=sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om))
        res[rule]["strict"]+=sum(1 for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True))
        res[rule]["pitch"]+=sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
        res[rule]["notes"]+=sum(sum(pitches(b).values()) for b in tb)
        res[rule][info["reason"]]+=1
        for k,v in info.get("decisions",{}).items():res[rule+"|dec"][k]+=v
print(want,dict(B),dict(drift))
for r,c in S.items():print(f"{r:12} bars {c['bars']:5} current {100*c['current']/c['bars']:5.1f} homr {100*c['homr']/c['bars']:5.1f} either {100*c['either']/c['bars']:5.1f}  homr-only {c['homr_only']} current-only {c['current_only']}")
for r,c in res.items():print(r,dict(c))
