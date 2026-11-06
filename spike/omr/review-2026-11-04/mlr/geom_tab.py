import pickle,collections,sys
S="/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr/"
R=pickle.load(open(S+"geom.pkl","rb"))
rows=[r for r in R if r["tie"] and r.get("lbox") and r.get("rbox")]
print(len(rows))
tab=collections.Counter(); cov=[]
for r in rows:
    il=r["il"]; x,y,w,h=r["box"]; lb=r["lbox"]; rb=r["rbox"]
    gapL=(r["x1"]-(lb[0]+lb[2]))/il; gapR=(rb[0]-r["x2"])/il
    span=(rb[0]-(lb[0]+lb[2]))/il
    cover=(r["x2"]-r["x1"])/il/max(span,0.1)
    dy=min(abs(r["y1"]-(lb[1]+lb[3]/2)),abs(r["y2"]-(rb[1]+rb[3]/2)))/il
    r["label"]="FP" if r.get("extra_here",0)>0 and r.get("true_here",0)==0 else ("TP" if r.get("true_here",0)>0 and r.get("extra_here",0)==0 else "mix" if r.get("true_here",0) else "unk")
    r["cover"],r["gapL"],r["gapR"],r["dyL"],r["span"]=cover,gapL,gapR,dy,span
    b="<.3" if cover<.3 else "<.5" if cover<.5 else "<.7" if cover<.7 else ">=.7"
    tab[r["label"],b]+=1
for k in sorted(tab): print(k,tab[k])
for r in sorted(rows,key=lambda r:r["stem"]):
    if r["label"] in("FP",): print(r["stem"][:22],r["sheet"],r["sys"],r["box"],"cov %.2f gL %.1f gR %.1f dy %.1f sp %.1f g %.2f"%(r["cover"],r["gapL"],r["gapR"],r["dyL"],r["span"],r["grade"]),r["ltime"],r["lpitch"],r["rpitch"])
import statistics as st
def q(v):
    v=sorted(v); n=len(v)
    return " ".join("%.1f"%v[int(p*(n-1))] for p in (0,.05,.25,.5,.75,.95,1)) if v else ""
for lab in ("TP","FP"):
    x=[r for r in rows if r["label"]==lab]
    print(lab,len(x),"gL",q([r["gapL"] for r in x]),"| gR",q([r["gapR"] for r in x]),"| dy",q([r["dyL"] for r in x]),"| cov",q([r["cover"] for r in x]),"| grade",q([r["grade"] for r in x]))
for lab in ("TP","FP"):
    c=collections.Counter()
    for r in rows:
        if r["label"]==lab:
            hug = "overhead" if r["gapL"]<-.3 and r["gapR"]<-.3 else "between"
            c[r["stem"].split("--")[-1],hug,"dy>1.2" if r["dyL"]>1.2 else "near"]+=1
    print(lab,sorted(c.items()))
print("--- FP near")
for r in rows:
    if r["label"]=="FP" and r["dyL"]<=1.2: print(r["set"],r["stem"],r["sheet"],r["sys"],r["box"],"cov %.2f gL %.1f gR %.1f dy %.1f sp %.1f g %.2f"%(r["cover"],r["gapL"],r["gapR"],r["dyL"],r["span"],r["grade"]),r["ltime"],r["lpitch"],r["rpitch"],r.get("tt"),r.get("ot"))
print("--- TP far")
for r in rows:
    if r["label"]=="TP" and r["dyL"]>1.2: print(r["set"],r["stem"],r["sheet"],r["sys"],r["box"],"cov %.2f gL %.1f gR %.1f dy %.1f sp %.1f g %.2f"%(r["cover"],r["gapL"],r["gapR"],r["dyL"],r["span"],r["grade"]),r["ltime"],r["lpitch"],r["rpitch"])
