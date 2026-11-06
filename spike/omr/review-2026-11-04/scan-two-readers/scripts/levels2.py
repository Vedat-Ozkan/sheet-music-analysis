import sys,json,collections,warnings,xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
sys.path.insert(0,"/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/homr")
from barparse import OMR,parse,align_bars,root_of
from whole_bars import exact
import merge2 as MX
R=OMR/"speed/cache/runs"
FIVE=[("bench-real","real-bach-wtc1-22-prelude--scan"),("bench-real","real-beethoven-op2no1-iii--scan"),("bench-real","real-grieg-op38no7--scan"),("bench","chopin-prelude-4--real-scan-schirmer"),("bench","mozart-k545-1--real-scan-peters")]
sp=json.load(open(OMR/"bench-olimpic/split.json"))
INS=[("bench-olimpic",f"{p}--scan") for p in sp["inspect"]]
UNS=[("bench-olimpic",f"{p}--scan") for p in sp["unseen"]]
def truthb(s,st):
    man=json.loads((OMR/s/"manifest.json").read_text())
    return (OMR/s/man["pieces"][st.rsplit("--",1)[0]]["truth"]).read_bytes()
FIFTHS=["F","C","G","D","A","E","B"]
def keymap(f):
    return {s:1 for s in FIFTHS[:f]} if f>0 else {s:-1 for s in FIFTHS[::-1][:-f]} if f<0 else {}
def barinfo(data):
    "per bar index: page_wrong count, tie stops set, grace count, keys"
    r=root_of(data);out=collections.defaultdict(lambda:{"wrong":0,"stops":collections.Counter(),"grace":0,"signs":0})
    for pi,part in enumerate(r.findall("part")):
        div=1;keys={}
        for bi,m in enumerate(part.findall("measure")):
            notes,_,_,div=MX.walk(m,div)
            for at in m.findall("attributes"):
                for k in at.findall("key"):
                    if k.findtext("fifths") is not None:
                        if k.get("number") is None:keys.clear()
                        keys[k.get("number","*")]=int(k.findtext("fifths"))
            state={}
            for on,d,el in sorted(notes,key=lambda t:t[0]):
                st=el.findtext("staff","1");p=el.find("pitch")
                if el.find("grace") is not None:out[bi]["grace"]+=1
                if p is None:continue
                step,oc=p.findtext("step"),p.findtext("octave");al=int(round(float(p.findtext("alter") or 0)))
                base=keymap(keys.get(st,keys.get("*",0))).get(step,0);cur=state.get((st,step,oc),base)
                if el.find("accidental") is not None:state[(st,step,oc)]=al;out[bi]["signs"]+=1
                elif al!=cur:out[bi]["wrong"]+=1
                for t in el.findall("tie"):
                    if t.get("type")=="stop":out[bi]["stops"][(pi,st,step,oc,on)]+=1
    return out
def score(items,V):
    T=collections.Counter();per={}
    for s,st in items:
        td=truthb(s,st);t=parse(td);f=R/V/f"{s}--{st}.musicxml";T["bars"]+=len(t)
        if not f.exists() or not f.stat().st_size:continue
        d=f.read_bytes();o=parse(d);pairs=dict(align_bars(t,o));bt,bo=barinfo(td),barinfo(d);c=collections.Counter()
        for i,b in enumerate(t):
            j=pairs.get(i)
            if j is None or not exact(b,o[j],True):continue
            c["L0_exact"]+=1
            if bo[j]["wrong"]:continue
            c["L1_signs_ok"]+=1
            if sum(bt[i]["stops"].values())!=sum(bo[j]["stops"].values()):continue
            c["L2_tie_stops_ok"]+=1
            if bt[i]["grace"]!=bo[j]["grace"]:continue
            c["L3_grace_ok"]+=1
        per[st[:22]]=dict(c);T.update(c)
    return T,per

name={"five":FIVE,"inspect":INS,"unseen":UNS}[sys.argv[1]]
for V in sys.argv[2:]:
    T,per=score(name,V);print(sys.argv[1],V,dict(T))
    if sys.argv[1]=="five":
        for k,v in per.items():print("   ",k,v)
