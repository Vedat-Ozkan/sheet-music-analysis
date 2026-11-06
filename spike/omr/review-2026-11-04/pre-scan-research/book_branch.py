import collections,glob,json,pathlib,sys
from lib import *
import merge3 as M3
from merge3 import sub_bars
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
from engine import read_pdf as reader
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
from merge2 import fill,sound
from branch_value import branch
R=pathlib.Path(sys.argv[1]);TMP=R/"_tmp.musicxml"
BR=collections.defaultdict(collections.Counter);S=collections.defaultdict(collections.Counter);P=collections.Counter()
def staff_hits(td,d,label,per_part):
    tb=parse(td);o=parse(d);ot,oo=staff_order(td),staff_order(d)
    if len(ot)!=len(oo):return
    groups=collections.defaultdict(list)
    for z,y in enumerate(oo):groups[y[0] if per_part else 0].append(z)
    for g,idx in groups.items():
        pr=dict(align_bars(sub_bars(tb,{ot[z] for z in idx}),sub_bars(o,{oo[z] for z in idx})))
        for z in idx:
            role="piano" if z>=len(ot)-2 else "voice"
            for i,b in enumerate(tb):
                te=[e for e in b.events if (e.part,e.staff)==ot[z]]
                oe=[e for e in o[pr[i]].events if (e.part,e.staff)==oo[z]] if i in pr else None
                S[(label,role)]["n"]+=1;S[(label,role)]["right"]+=oe is not None and staff_exact(te,oe)
for k in range(1,14):
    d=R/"book"/f"{k:02d}" if k>1 else R/"parratt1-after-4cpu"
    if k>1 and not (d/"facts.json").exists():continue
    tf=glob.glob(str(pathlib.Path.home()/f"data/sheet-music-corpora/lieder/scores/Parratt*/Choral*/{k:02d}_*/lc*.mxl"))[0];td=open(tf,"rb").read()
    if k==1:mvd=[reader.clean(m.read_bytes()) for m in sorted((R.parent/"aud-parratt/p1").glob("score*.mxl"))]
    else:mvd=[m.read_bytes() for m in sorted(d.glob("score*.musicxml"))]
    da=max(mvd,key=lambda x:len(parse(x)));dh=clean((d/"homr.musicxml").read_bytes())
    ot,oa,oh=staff_order(td),staff_order(da),staff_order(dh)
    P["pieces"]+=1
    if not (len(ot)==len(oa)==len(oh)):
        P["staff count differs"]+=1;continue
    P["same staff count"]+=1;P["bars in those pieces"]+=len(parse(td))
    TMP.write_bytes(da);ph=d/"homr.musicxml"
    data,info=M3.merge(TMP,ph)
    staff_hits(td,da,"current",False);staff_hits(td,dh,"homr",True);staff_hits(td,data,"merged",False)
    tb=parse(td);ab,hb=parse(da),parse(dh)
    ends=[max(e.onset+e.dur for e in b.events) for b in ab+hb if b.events]
    mode=collections.Counter(ends).most_common(1)[0][0] if ends else None
    groups=collections.defaultdict(list)
    for z,y in enumerate(oh):groups[y[0]].append(z)
    for hp,idx in groups.items():
        ka={oa[z] for z in idx};kh={oh[z] for z in idx};kt={ot[z] for z in idx}
        ah=dict(align_bars(sub_bars(ab,ka),sub_bars(hb,kh)));tp=dict(align_bars(sub_bars(ab,ka),sub_bars(tb,kt)))
        for j,q in ah.items():
            if j not in tp:continue
            i=tp[j]
            for z in idx:
                ea=[e for e in ab[j].events if (e.part,e.staff)==oa[z]];eh=[e for e in hb[q].events if (e.part,e.staff)==oh[z]];et=[e for e in tb[i].events if (e.part,e.staff)==ot[z]]
                if not ea and not eh:continue
                full=ab[j].full or hb[q].full or mode
                same=sound(ea)==sound(eh);fa,fh=fill(ea,full),fill(eh,full);ar,hr=staff_exact(et,ea),staff_exact(et,eh)
                c=BR[branch(same,fa,fh)];c["n"]+=1;c["homr only"]+=hr and not ar;c["current only"]+=ar and not hr;c["both right"]+=ar and hr;c["both wrong"]+=not ar and not hr
print(dict(P))
for (l,r),c in sorted(S.items()):print(f"  {l:8} {r:6} staves right {c['right']} of {c['n']} = {100*c['right']/max(c['n'],1):.1f}%")
for k in sorted(BR):
    c=BR[k];print(f"  {k:32} n {c['n']:5} homr-only {c['homr only']:4} current-only {c['current only']:4} both-right {c['both right']:5} both-wrong {c['both wrong']:4}")
