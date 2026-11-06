import collections,json,sys
from lib import *
from merge3 import sub_bars
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
from merge2 import fill,sound
def rows(items,hvar):
    out=[]
    for s,st in items:
        pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/hvar/f"{s}--{st}.musicxml"
        if not (pa.exists() and pa.stat().st_size and ph.exists() and ph.stat().st_size):continue
        td=truth(s,st);tb=parse(td);da=pa.read_bytes();dh=clean(ph.read_bytes())
        ab,hb=parse(da),parse(dh);ot,oa,oh=staff_order(td),staff_order(da),staff_order(dh)
        if not (len(ot)==len(oa)==len(oh)):continue
        ends=[max(e.onset+e.dur for e in b.events) for b in ab+hb if b.events]
        mode=collections.Counter(ends).most_common(1)[0][0] if ends else None
        groups=collections.defaultdict(list)
        for z,y in enumerate(oh):groups[y[0]].append(z)
        rec=[];agree=n=0
        for hp,idx in groups.items():
            ka={oa[z] for z in idx};kh={oh[z] for z in idx};kt={ot[z] for z in idx}
            sa,sh,stb=sub_bars(ab,ka),sub_bars(hb,kh),sub_bars(tb,kt)
            ah=dict(align_bars(sa,sh));tp=dict(align_bars(sa,stb))
            for j,k in ah.items():
                for z in idx:
                    ea=[e for e in ab[j].events if (e.part,e.staff)==oa[z]]
                    eh=[e for e in hb[k].events if (e.part,e.staff)==oh[z]]
                    if not ea and not eh:continue
                    same=sound(ea)==sound(eh);n+=1;agree+=same
                    if j in tp and not same:
                        full=ab[j].full or hb[k].full or mode
                        if fill(ea,full) and fill(eh,full):
                            et=[e for e in tb[tp[j]].events if (e.part,e.staff)==ot[z]]
                            rec.append((staff_exact(et,ea),staff_exact(et,eh)))
        out.append((st,agree/max(n,1),rec))
    return out
def show(name,rs):
    b=collections.defaultdict(collections.Counter)
    for st,ag,rec in rs:
        k="agree<60" if ag<.6 else "60-80" if ag<.8 else "80-90" if ag<.9 else ">=90"
        b[k]["pdfs"]+=1
        for ar,hr in rec:
            b[k]["n"]+=1;b[k]["homr only"]+=hr and not ar;b[k]["current only"]+=ar and not hr;b[k]["both wrong"]+=not ar and not hr
    print(name,{k:dict(v) for k,v in sorted(b.items())})
    print("  per pdf agreement",[(st[:14],round(ag,2),sum(h and not a for a,h in rec),sum(a and not h for a,h in rec)) for st,ag,rec in rs][:5] if len(rs)<=5 else "")
show("five",rows(FIVE,"homr300"))
sp=json.load(open(OMR/"bench-olimpic/split.json"))
show("inspect",rows([("bench-olimpic",f"{p}--scan") for p in sp["inspect"]],"homr300ol"))
items=json.load(open(HERE/"clean60.items.json"))
show("clean",rows([tuple(x) for x in items],"homr300clean"))
