import collections,json,re,sys,warnings,pathlib,zipfile
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from barparse import OMR,root_of,parse
L=pathlib.Path.home()/"data/sheet-music-corpora/lieder"
split=json.loads((OMR/"bench-scan/split.json").read_text())
txt=(L/"data/scores.yaml").read_text()
meta={}
for blk in re.split(r"(?m)^(?=\d+:\s*$)",txt):
    m=re.match(r"(\d+):",blk)
    if not m:continue
    d={}
    for line in blk.splitlines()[1:]:
        mm=re.match(r"\s+(\w+):\s*(.*)",line)
        if mm:d[mm.group(1)]=mm.group(2).strip().strip("'\"")
    meta[int(m.group(1))]=d
def shape(root):
    out=[]
    for p in root.findall("part"):
        ns=0
        for at in p.iter("staves"):ns=max(ns,int(at.text))
        st={n.findtext("staff","1") for n in p.iter("note")}
        out.append(max(ns,len(st),1))
    return tuple(out)
def truth_path(i):
    d=L/"scores"/meta[i]["path"]
    return d/f"lc{i}.mxl"
if __name__=="__main__":
    agg=collections.defaultdict(collections.Counter);bars=collections.Counter();rows=[]
    for half in ("tuning","unseen"):
        for i in split[half]:
            f=truth_path(i)
            if not f.exists():agg[half]["missing"]+=1;continue
            data=f.read_bytes();root=root_of(data);s=shape(root);n=len(parse(data))
            ins=meta[i].get("instruments","")
            kind="voice+piano" if s==(1,2) else "piano+voices" if s[-1]==2 and len(s)>2 else "other"
            agg[half][(kind,s)]+=1;bars[half]+=n
            if half=="tuning":rows.append((i,meta[i]["path"].split("/")[-1][:32],s,n,ins,meta[i].get("imslp")))
    for r in rows:print(r)
    for h,c in agg.items():print(h,bars[h],dict(c))
