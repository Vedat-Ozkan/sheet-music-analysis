import collections,json,sys
from lib import *
from merge3 import sub_bars
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
sp=json.load(open(OMR/"bench-olimpic/split.json"))
INS=[("bench-olimpic",f"{p}--scan") for p in sp["inspect"]]
def staff_rates(items,hvar,lab):
    T=collections.defaultdict(collections.Counter);F=collections.Counter()
    for s,st in items:
        td=truth(s,st);tb=parse(td);pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/hvar/f"{s}--{st}.musicxml"
        da=pa.read_bytes() if pa.exists() and pa.stat().st_size else None
        dh=clean(ph.read_bytes()) if ph.exists() and ph.stat().st_size else None
        ot=staff_order(td)
        F["bars"]+=len(tb)
        if da is None:F["no current reading bars"]+=len(tb)
        ab=parse(da) if da else None;hb=parse(dh) if dh else None
        pa_=dict(align_bars(tb,ab)) if ab else {};ph_=dict(align_bars(tb,hb)) if hb else {}
        oa=staff_order(da) if da else [];oh=staff_order(dh) if dh else []
        for i,b in enumerate(tb):
            allA=allH=allE=True
            for z,tk in enumerate(ot):
                te=[e for e in b.events if (e.part,e.staff)==tk]
                ae=[e for e in ab[pa_[i]].events if z<len(oa) and (e.part,e.staff)==oa[z]] if i in pa_ else None
                he=[e for e in hb[ph_[i]].events if z<len(oh) and (e.part,e.staff)==oh[z]] if i in ph_ else None
                ra=ae is not None and staff_exact(te,ae);rh=he is not None and staff_exact(te,he)
                c=T["upper" if z==0 else "lower"];c["n"]+=1;c["cur"]+=ra;c["homr"]+=rh;c["either"]+=ra or rh
                allA&=ra;allH&=rh;allE&=ra or rh
            F["cur"]+=allA;F["homr"]+=allH;F["either"]+=allE
    print(lab,dict(F))
    for k,c in T.items():print(f"   {k}: current {100*c['cur']/c['n']:.1f} homr {100*c['homr']/c['n']:.1f} either {100*c['either']/c['n']:.1f} (n={c['n']})")
staff_rates(FIVE,"homr300","five real scans")
staff_rates(INS,"homr300ol","olimpic inspect half")
