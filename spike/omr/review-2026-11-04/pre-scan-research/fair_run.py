import argparse,collections,json,pathlib,random,sys,time
sys.dont_write_bytecode=True
ROOT=pathlib.Path("/home/kema/projects/sheet-music-plugin")
sys.path.insert(0,str(ROOT))
from lib import *
from whole_bars import exact
import merge3,homrjoin
from engine import read_pdf as reader
import pikepdf
import levels2_lite as L
AUD=str(OMR/"speed/launchers/marks1/bin/Audiveris")
def pages_pdf(src,a,b,dest):
    p=pikepdf.open(src);q=pikepdf.Pdf.new()
    for i in range(a-1,b):q.pages.append(p.pages[i])
    q.save(dest)
def score(td,data):
    tb=parse(td);o=parse(data);p=dict(align_bars(tb,o));tm,om=canon_map(td),canon_map(data)
    bt,bo=L.barinfo(td),L.barinfo(data)
    s=set();st=set();ti=set()
    for i,b in enumerate(tb):
        if i not in p:continue
        j=p[i]
        if exact(b,o[j],True):st.add(i)
        if bar_exact(b,o[j],tm,om):
            s.add(i)
            if sum(bt[i]["stops"].values())==sum(bo[j]["stops"].values()):ti.add(i)
    n=sum(sum(pitches(b).values()) for b in tb)
    pit=sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
    tim=sum(sum((timed(b)&timed(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
    return dict(bars=len(tb),read=len(o),exact=sorted(s),strict=len(st),ties=sorted(ti),notes=n,pitch=pit,timed=tim,shape=str(shape(data)))
def one(e,out):
    d=out/str(e["id"]);d.mkdir(parents=True,exist_ok=True);pdf=d/"piece.pdf"
    if not pdf.exists():pages_pdf(e["pdf"],e["pages"][0],e["pages"][1],pdf)
    td=pathlib.Path(e["truth"]).read_bytes()
    cur=d/"current.musicxml"
    if not cur.exists():
        try:
            r=reader.read_pdf(pdf.read_bytes(),audiveris=AUD);cur.write_bytes(r.musicxml)
        except reader.ReadError:
            cur.write_bytes(b"")
    hm=d/"homr.musicxml"
    if not hm.exists():
        rows=homrjoin.read_pages(pdf,d,"4");json.dump(homrjoin.join(rows,hm),open(d/"join.json","w"),default=str)
    if not hm.exists():
        return dict(id=e["id"],status="homr failed")
    data,info=merge3.merge(cur,hm);(d/"merged.musicxml").write_bytes(data)
    res=dict(id=e["id"],status=info["reason"],current=score(td,cur.read_bytes()) if cur.stat().st_size else None,homr=score(td,hm.read_bytes()),merged=score(td,data))
    try:
        reader.problem_spots(data);res["renders"]=True
    except Exception as ex:
        res["renders"]=False;res["render_error"]=type(ex).__name__
    return res
def boot(rows,key,seed=20261104,n=10000):
    rng=random.Random(seed);out=[]
    for _ in range(n):
        s=[rows[rng.randrange(len(rows))] for _ in rows]
        out.append(100*sum(len(r["merged"][key])-len(r["current"][key]) for r in s)/sum(r["merged"]["bars"] for r in s))
    out.sort();return out[int(.05*n)],out[int(.95*n)]
def verdict(rows):
    ok=[r for r in rows if r.get("current")]
    bars=sum(r["merged"]["bars"] for r in rows)
    v={"pieces":len(rows),"bars":bars,"merge_ran_on":sum(r["status"]=="merged" for r in rows)}
    for key in ("exact","ties"):
        c=sum(len(r["current"][key]) if r.get("current") else 0 for r in rows);m=sum(len(r["merged"][key]) for r in rows);h=sum(len(r["homr"][key]) for r in rows)
        v[key]=dict(current=c,homr=h,merged=m,current_pct=round(100*c/bars,1),merged_pct=round(100*m/bars,1),gain_points=round(100*(m-c)/bars,1))
    g=l=0;worse=0
    for r in rows:
        a=set(r["current"]["ties"]) if r.get("current") else set();b=set(r["merged"]["ties"])
        g+=len(b-a);l+=len(a-b)
        worse+=len(a)-len(b)>max(2,0.05*r["merged"]["bars"])
    v["pieces_net_down_too_far"]=worse
    v["gross_gained"]=g;v["gross_lost"]=l
    full=[{**r,"current":r.get("current") or dict(r["merged"],ties=[],exact=[])} for r in rows]
    lo,hi=boot(full,"ties");v["gain_ci90"]=(round(lo,1),round(hi,1))
    tg=sum(len(r["merged"]["ties"])-len(r["current"]["ties"]) for r in full)
    v["loo_min_gain_points"]=round(min(100*(tg-(len(r["merged"]["ties"])-len(r["current"]["ties"])))/max(bars-r["merged"]["bars"],1) for r in full),1)
    v["largest_share_of_gross_gain"]=round(max(len(set(r["merged"]["ties"])-set(r["current"]["ties"])) for r in full)/max(g,1),2)
    v["renders_all"]=all(r.get("renders") for r in rows)
    fails=[]
    if len(rows)<15 or bars<400:fails.append("too few pieces or bars: no verdict")
    if v["merge_ran_on"]<0.8*len(rows):fails.append("merge ran on under 80% of pieces")
    if v["ties"]["gain_points"]<5 or lo<2:fails.append("gain test")
    if l>0.25*max(g,1):fails.append("losses over a quarter of gains")
    if v["loo_min_gain_points"]<2:fails.append("leave one out")
    if v["largest_share_of_gross_gain"]>0.5:fails.append("one piece over half of gains")
    if worse:fails.append("a piece fell by over 2 bars or 5%")
    if not v["renders_all"]:fails.append("a merged file does not render")
    v["fails"]=fails
    return v
if __name__=="__main__":
    A=argparse.ArgumentParser();A.add_argument("manifest");A.add_argument("--half",required=True);A.add_argument("--out",required=True)
    a=A.parse_args();out=pathlib.Path(a.out)
    split=json.loads((OMR/"bench-scan/split.json").read_text())
    man=json.load(open(a.manifest))
    want=[e for e in man if (e["id"] in split[a.half]) or (a.half=="tuning" and e.get("off_split"))]
    rows=[]
    for e in want:
        r=one(e,out);rows.append(r)
        if a.half=="tuning":
            c=r.get("current");print(r["id"],r["status"],"current",len(c["exact"]) if c else None,"homr",len(r["homr"]["exact"]) if r.get("homr") else None,"merged",len(r["merged"]["exact"]) if r.get("merged") else None,"of",r["merged"]["bars"] if r.get("merged") else None,flush=True)
    json.dump(rows,open(out/f"results-{a.half}.json","w"))
    rows=[r for r in rows if r.get("merged")]
    print(json.dumps(verdict(rows),indent=0) if rows else "no results")
