import collections,json,sys
from lib import *
from whole_bars import exact
import merge3 as M3
from merge3 import sub_bars,staves as st_of
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
from merge2 import fill,sound
def eff_clefs(bars):
    cur={};out=[]
    for b in bars:
        start=dict(cur);cur.update(b.clef);out.append((start,dict(cur)))
    return out
def clef_at(eff,j,key):
    s,e=eff[j]
    return {s.get(key),e.get(key)}
def diff_kind(te,oe):
    pt,po=collections.Counter(m for e in te for m in e.midis),collections.Counter(m for e in oe for m in e.midis)
    if pt!=po:
        miss=sum((pt-po).values());ext=sum((po-pt).values())
        return "pitch(miss%d,extra%d)"%(miss,ext)
    if sounding(te)!=sounding(oe):
        on=collections.Counter((m,e.onset) for e in te for m in e.midis)==collections.Counter((m,e.onset) for e in oe for m in e.midis)
        return "duration" if on else "onset"
    if rests(te)!=rests(oe):return "rests"
    if ties(te)!=ties(oe):return "ties"
    return "same"
def analyse(set_,stem,variant,hvar,base="marks1"):
    td=truth(set_,stem);tb=parse(td)
    pm=RUNS/variant/f"{set_}--{stem}.musicxml";pa=RUNS/base/f"{set_}--{stem}.musicxml";ph=RUNS/hvar/f"{set_}--{stem}.musicxml"
    da,dh,dm=pa.read_bytes(),clean(ph.read_bytes()),pm.read_bytes()
    ab,hb,mb=parse(da),parse(dh),parse(dm)
    pta,pth,ptm=dict(align_bars(tb,ab)),dict(align_bars(tb,hb)),dict(align_bars(tb,mb))
    ot,oa,oh=staff_order(td),staff_order(da),staff_order(dh)
    sel,_,_,_=M3.plan(da,dh,"as_written")
    et,ea,eh=eff_clefs(tb),eff_clefs(ab),eff_clefs(hb)
    rows=[]
    for i,b in enumerate(tb):
        ax=i in pta and exact(b,ab[pta[i]],True);mx=i in ptm and exact(b,mb[ptm[i]],True);hx=i in pth and exact(b,hb[pth[i]],True)
        status="kept" if ax and mx else "gained" if mx else "lost" if ax else "both wrong"
        det=[]
        j=pta.get(i);k=pth.get(i)
        for z,tk in enumerate(ot):
            te=[e for e in b.events if (e.part,e.staff)==tk]
            ae=[e for e in ab[j].events if (e.part,e.staff)==oa[z]] if j is not None else []
            he=[e for e in hb[k].events if (e.part,e.staff)==oh[z]] if k is not None else []
            ar,hr=staff_exact(te,ae),staff_exact(te,he)
            full=b.full
            fa=fill(ae,(ab[j].full or full) if j is not None else None);fh=fill(he,(ab[j].full if j is not None and ab[j].full else hb[k].full if k is not None else full))
            swapped=j is not None and oa[z] in sel.get(j,{})
            ctruth=clef_at(et,i,tk);ca=clef_at(ea,j,oa[z]) if j is not None else set();ch=clef_at(eh,k,oh[z]) if k is not None else set()
            det.append(dict(staff=z,cur_right=ar,homr_right=hr,cur_adds=fa,homr_adds=fh,swapped=swapped,cur_kind=diff_kind(te,ae),homr_kind=diff_kind(te,he),cur_clef_wrong=bool(ca-ctruth),homr_clef_wrong=bool(ch-ctruth)))
        rows.append(dict(bar=i,status=status,homr_exact=hx,staves=det))
    return rows
def cause_gain(r):
    w=[d for d in r["staves"] if not d["cur_right"]]
    if any(d["cur_clef_wrong"] for d in w):return "current clef wrong"
    k=[d["cur_kind"] for d in w]
    if any(x.startswith("pitch") for x in k):return "current notes wrong or missing"
    if "onset" in k:return "current onsets"
    if "duration" in k:return "current durations"
    if "rests" in k:return "current rests"
    if "ties" in k:return "current ties"
    return "other"
def cause_loss(r):
    w=[d for d in r["staves"] if d["swapped"] and not d["homr_right"]]
    if not w:return "written merge differs, no bad swap"
    if any(d["homr_clef_wrong"] for d in w):return "homr clef wrong"
    k=[d["homr_kind"] for d in w]
    if any(x.startswith("pitch") for x in k):return "homr notes wrong"
    if "onset" in k:return "homr onsets"
    if "duration" in k:return "homr durations"
    if "rests" in k:return "homr rests"
    if "ties" in k:return "homr ties"
    return "other"
def cause_missed(r):
    wrong=[d for d in r["staves"] if not d["cur_right"]]
    both=[d for d in wrong if not d["homr_right"]]
    if both:
        if any(d["cur_clef_wrong"] or d["homr_clef_wrong"] for d in both):return "both wrong on a staff, a clef involved"
        return "both wrong on a staff"
    if any(not d["homr_adds"] for d in wrong):return "homr right but its staff does not add up"
    return "homr right, staff not taken: other"
if __name__=="__main__":
    ALL={}
    hv={"bench-real":"homr300","bench":"homr300"}
    tot=collections.Counter()
    for s,st in FIVE:
        rows=analyse(s,st,"m4five","homr300")
        ALL[st]=rows
        c=collections.Counter(r["status"] for r in rows)
        print(st[:30],dict(c),"homr exact",sum(r["homr_exact"] for r in rows),"oracle per staff",sum(all(d["cur_right"] or d["homr_right"] for d in r["staves"]) for r in rows),"of",len(rows))
        print("   gained",dict(collections.Counter(cause_gain(r) for r in rows if r["status"]=="gained")))
        print("   lost",dict(collections.Counter(cause_loss(r) for r in rows if r["status"]=="lost")),[r["bar"] for r in rows if r["status"]=="lost"])
        print("   still wrong",dict(collections.Counter(cause_missed(r) for r in rows if r["status"]=="both wrong")))
        tot.update(c)
    print(dict(tot))
    json.dump(ALL,open(HERE/"results/ledger_five.json","w"),indent=0)
