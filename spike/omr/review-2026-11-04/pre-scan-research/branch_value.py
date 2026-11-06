import collections,json,sys
from lib import *
import merge3 as M3
from merge3 import sub_bars
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
from merge2 import fill,sound
def branch(same,fa,fh):
    if same:return "same notes, only homr adds up" if (fh and not fa) else "same notes, other"
    if fa and fh:return "differ, both add up"
    if fh:return "differ, only homr adds up"
    if fa:return "differ, only current adds up"
    return "differ, neither adds up"
def table(items,hvar,afn=lambda s,st:RUNS/"marks1"/f"{s}--{st}.musicxml"):
    T=collections.defaultdict(collections.Counter)
    for s,st in items:
        pa,ph=afn(s,st),RUNS/hvar/f"{s}--{st}.musicxml"
        if not (pa.exists() and pa.stat().st_size and ph.exists() and ph.stat().st_size):continue
        td=truth(s,st);tb=parse(td);da=pa.read_bytes();dh=clean(ph.read_bytes())
        ab,hb=parse(da),parse(dh);ot,oa,oh=staff_order(td),staff_order(da),staff_order(dh)
        if not (len(ot)==len(oa)==len(oh)):continue
        ends=[max(e.onset+e.dur for e in b.events) for b in ab+hb if b.events]
        mode=collections.Counter(ends).most_common(1)[0][0] if ends else None
        groups=collections.defaultdict(list)
        for z,y in enumerate(oh):groups[y[0]].append(z)
        for hp,idx in groups.items():
            ka={oa[z] for z in idx};kh={oh[z] for z in idx};kt={ot[z] for z in idx}
            sa,sh,stb=sub_bars(ab,ka),sub_bars(hb,kh),sub_bars(tb,kt)
            ah=dict(align_bars(sa,sh));tp=dict(align_bars(sa,stb))
            for j,k in ah.items():
                if j not in tp:continue
                i=tp[j]
                for z in idx:
                    ea=[e for e in ab[j].events if (e.part,e.staff)==oa[z]]
                    eh=[e for e in hb[k].events if (e.part,e.staff)==oh[z]]
                    et=[e for e in tb[i].events if (e.part,e.staff)==ot[z]]
                    if not ea and not eh:continue
                    full=ab[j].full or hb[k].full or mode
                    same=sound(ea)==sound(eh);fa,fh=fill(ea,full),fill(eh,full)
                    ar,hr=staff_exact(et,ea),staff_exact(et,eh)
                    c=T[branch(same,fa,fh)]
                    c["n"]+=1;c["current right only"]+=ar and not hr;c["homr right only"]+=hr and not ar;c["both right"]+=ar and hr;c["both wrong"]+=not ar and not hr
    return T
def show(name,T):
    print(name)
    for k in sorted(T):
        c=T[k];print(f"  {k:32} n {c['n']:5} homr-only {c['homr right only']:4} current-only {c['current right only']:4} both-right {c['both right']:5} both-wrong {c['both wrong']:4}")
if __name__=="__main__":
    show("five real scans",table(FIVE,"homr300"))
    sp=json.load(open(OMR/"bench-olimpic/split.json"))
    show("olimpic inspect half",table([("bench-olimpic",f"{p}--scan") for p in sp["inspect"]],"homr300ol"))
    items=json.load(open(HERE/"clean60.items.json"))
    def g(s,st):
        return shape(truth(s,st))
    show("clean voice+piano",table([(s,st) for s,st in items if g(s,st)==(1,2)],"homr300clean"))
    show("clean one part",table([(s,st) for s,st in items if len(g(s,st))==1],"homr300clean"))
    show("clean four single staves",table([(s,st) for s,st in items if g(s,st)==(1,1,1,1)],"homr300clean"))
