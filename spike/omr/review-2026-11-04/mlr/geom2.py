import pickle,collections,sys,math
M="/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr/"
R=pickle.load(open(sys.argv[1] if len(sys.argv)>1 else M+"geom.pkl","rb"))
rows=[r for r in R if r["tie"] and r.get("lbox") and r.get("rbox")]
def dist(px,py,b):
    x,y,w,h=b
    dx=max(x-px,0,px-(x+w)); dy=max(y-py,0,py-(y+h))
    return dx,dy
for r in rows:
    il=r["il"]
    d1=dist(r["x1"],r["y1"],r["lbox"]); d2=dist(r["x2"],r["y2"],r["rbox"])
    r["dmax"]=max(math.hypot(*d1),math.hypot(*d2))/il
    r["dymax"]=max(d1[1],d2[1])/il
    r["dxmax"]=max(d1[0],d2[0])/il
    r["label"]="FP" if r.get("extra_here",0)>0 and r.get("true_here",0)==0 else ("TP" if r.get("true_here",0)>0 and r.get("extra_here",0)==0 else "mix" if r.get("true_here",0) else "unk")
for lab in("TP","mix","FP"):
    c=collections.Counter()
    for r in rows:
        if r["label"]==lab:
            c[min(int(r["dmax"]*5)/5,3)]+=1
    print(lab,sorted(c.items()))
pickle.dump(rows,open(M+"geomrows.pkl","wb"))
print("TP with dmax>=0.8")
for r in rows:
    if r["label"]=="TP" and r["dmax"]>=.8: print(r["stem"][:24],r["sheet"],r["sys"],r["box"],"d %.2f dy %.2f dx %.2f"%(r["dmax"],r["dymax"],r["dxmax"]),r["ltime"])
print("FP with dmax<0.8")
for r in rows:
    if r["label"]=="FP" and r["dmax"]<.8: print(r["stem"][:24],r["sheet"],r["sys"],r["box"],"d %.2f dy %.2f dx %.2f"%(r["dmax"],r["dymax"],r["dxmax"]),r["ltime"],r.get("tt"),r.get("ot"))
