import collections,json,sys,warnings,xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from barparse import OMR,root_of
R=OMR/"speed/cache/runs"
SETS=["bench","bench-tune2","bench-oldly","bench-real"]
def shape(data):
    r=root_of(data)
    out=[]
    for p in r.findall("part"):
        ns=0
        for at in p.iter("staves"):
            ns=max(ns,int(at.text))
        st={n.findtext("staff","1") for n in p.iter("note")}
        out.append(max(ns,len(st),1))
    return tuple(out)
def names(data):
    r=root_of(data)
    return [(s.get("id"),(s.findtext("part-name") or "").strip()) for s in r.iter("score-part")]
T=collections.Counter();rows=[]
for s in SETS:
    man=json.loads((OMR/s/"manifest.json").read_text())
    for e in man["pdfs"]:
        st=e["pdf"].rsplit("/",1)[-1][:-4]
        piece=e["piece"]
        tb=(OMR/s/man["pieces"][piece]["truth"]).read_bytes()
        ts=shape(tb)
        f=R/"marks1"/f"{s}--{st}.musicxml"
        if not f.exists() or not f.stat().st_size:
            rows.append((s,st,ts,None,None));continue
        os_=shape(f.read_bytes())
        h=R/"homr300clean"/f"{s}--{st}.musicxml"
        hs=shape(h.read_bytes()) if h.exists() and h.stat().st_size else None
        rows.append((s,st,ts,os_,hs))
json.dump(rows,open(sys.argv[1],"w"))
c=collections.Counter((str(r[2]),str(r[3])) for r in rows)
for k,v in sorted(c.items(),key=lambda x:-x[1])[:50]:print(v,k)
