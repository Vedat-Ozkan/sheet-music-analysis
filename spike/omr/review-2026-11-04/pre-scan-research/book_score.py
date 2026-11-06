import collections,glob,json,pathlib,sys
from lib import *
from whole_bars import exact
import merge3
from merge3 import sub_bars
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
from engine import read_pdf as reader
R=pathlib.Path(sys.argv[1])
def staffrates(td,d,T,label,per_part=False):
    tb=parse(td);o=parse(d);ot,oo=staff_order(td),staff_order(d)
    if len(ot)!=len(oo):
        T[label]["shape mismatch pieces"]+=1;return
    groups=collections.defaultdict(list)
    for z,y in enumerate(oo):groups[y[0] if per_part else 0].append(z)
    for g,idx in groups.items():
        kt={ot[z] for z in idx};ko={oo[z] for z in idx}
        pr=dict(align_bars(sub_bars(tb,kt),sub_bars(o,ko)))
        for z in idx:
            role="piano" if z>=len(ot)-2 else "voice"
            for i,b in enumerate(tb):
                te=[e for e in b.events if (e.part,e.staff)==ot[z]]
                oe=[e for e in o[pr[i]].events if (e.part,e.staff)==oo[z]] if i in pr else None
                T[label][role+" n"]+=1;T[label][role+" right"]+=oe is not None and staff_exact(te,oe)
tot=collections.Counter();ST=collections.defaultdict(collections.Counter);rows=[]
for k in range(1,14):
    d=R/"book"/f"{k:02d}" if k>1 else R/"parratt1-after-4cpu"
    if k>1 and not (d/"facts.json").exists():continue
    tf=glob.glob(str(pathlib.Path.home()/f"data/sheet-music-corpora/lieder/scores/Parratt*/Choral*/{k:02d}_*/lc*.mxl"))[0];td=open(tf,"rb").read()
    tb=parse(td);tm=canon_map(td)
    if k==1:
        mv=sorted(pathlib.Path(str(R.parent)+"/aud-parratt/p1").glob("score*.mxl"))
        mvd=[reader.clean(m.read_bytes()) for m in mv]
    else:
        mv=sorted(d.glob("score*.musicxml"));mvd=[m.read_bytes() for m in mv]
    hf=d/"homr.musicxml";dh=clean(hf.read_bytes()) if hf.exists() else None
    def ex(x):
        o=parse(x);p=dict(align_bars(tb,o));om=canon_map(x)
        return sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om)),sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(tb) if i in p),sum(sum((timed(b)&timed(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
    notes=sum(sum(pitches(b).values()) for b in tb)
    first=mvd[0] if mvd else None
    best=max(mvd,key=lambda x:len(parse(x))) if mvd else None
    row=dict(k=k,bars=len(tb),truth=shape(td),n_mvt=len(mvd),mvt=[(shape(x),len(parse(x))) for x in mvd][:4])
    if first:
        e,p,t=ex(first);row["first_exact"]=e;row["first_pitch"]=round(100*p/notes,1)
        e,p,t=ex(best);row["bestmvt_exact"]=e;row["bestmvt_pitch"]=round(100*p/notes,1);row["bestmvt_timing"]=round(100*t/notes,1)
        staffrates(td,best,ST,"current (largest movement)")
    if dh:
        e,p,t=ex(dh);row["homr_exact"]=e;row["homr_pitch"]=round(100*p/notes,1);row["homr_timing"]=round(100*t/notes,1);row["homr_shape"]=shape(dh);row["homr_part_bars"]=per_part_bars(dh)
        staffrates(td,dh,ST,"homr (per part aligned)",True)
    if best and dh:
        pth=pathlib.Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/_b.musicxml");pth.write_bytes(best)
        ph=hf
        data,info=merge3.merge(pth,ph);row["merge_reason"]=info["reason"]
        e,p,t=ex(data);row["merged_best_exact"]=e;row["merged_best_pitch"]=round(100*p/notes,1)
    rows.append(row);print(json.dumps(row,default=str)[:560],flush=True)
    for key in ("bars","first_exact","bestmvt_exact","homr_exact","merged_best_exact"):tot[key]+=row.get(key,0)
print(dict(tot))
for k,c in ST.items():print(k,{x:(c[x+" right"],c[x+" n"],round(100*c[x+" right"]/max(c[x+" n"],1),1)) for x in("voice","piano")},"shape mismatches",c["shape mismatch pieces"])
