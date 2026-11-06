import sys,warnings,json,collections,copy,dataclasses
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from fractions import Fraction as F
from barparse import OMR,parse,align_bars,pitches,timed
from whole_bars import exact
REAL=[("bench-real","real-bach-wtc1-22-prelude--scan"),("bench-real","real-beethoven-op2no1-iii--scan"),("bench-real","real-grieg-op38no7--scan"),("bench","chopin-prelude-4--real-scan-schirmer"),("bench","mozart-k545-1--real-scan-peters")]
def staves(b):
    d=collections.defaultdict(list)
    for e in b.events:d[(e.part,e.staff)].append(e)
    return d
def fill(ev,full):
    if full is None or not ev:return False
    return max(e.onset+e.dur for e in ev)==full
def sound(ev):
    return collections.Counter((m) for e in ev for m in e.midis)
def chords(ev):
    d=collections.defaultdict(list)
    for e in ev:
        if e.midis:d[e.onset].append(e)
    return [d[k] for k in sorted(d)]
def merged(ba,bh,o):
    out=copy.copy(ba);out.events=[];sa,sh=staves(ba),staves(bh)
    ka,kh=sorted(sa,key=str),sorted(sh,key=str)
    if len(ka)!=len(kh):return ba,False
    full=ba.full or bh.full or o.get("mode")
    changed=False
    for x,y in zip(ka,kh):
        ea,eh=sa[x],sh[y]
        same=sound(ea)==sound(eh)
        fa,fh=fill(ea,full),fill(eh,full)
        use=None
        if not same and fh:use="H"
        elif not same and not fa and not fh and o.get("neither"):use="H"
        elif same and not fa and fh and o["unfill"]:use="H"
        elif not same and fa and not fh and o["graft"]:
            ca,ch=chords(ea),chords(eh)
            if len(ca)==len(ch) and all(len(a)==1 and len(b)==1 for a,b in zip(ca,ch)) and all(sum(len(e.midis) for e in a)==sum(len(e.midis) for e in b) for a,b in zip(ca,ch)):
                use="G"
        if use=="H":
            ties={(m,e.onset) for e in ea for m,t in e.ties if t=="start"} if o["ties"] else set()
            new=[]
            for e in eh:
                n=dataclasses.replace(e,part=x[0],staff=x[1])
                if o["ties"]:
                    n.ties=[(m,t) for m,t in e.ties if t!="start"]+[(m,"start") for m in e.midis if (m,e.onset) in ties]
                new.append(n)
            out.events+=new;changed=True
        elif use=="G":
            for a,b in zip(chords(ea),chords(eh)):
                pass
            mp={id(a[0]):b[0] for a,b in zip(chords(ea),chords(eh))}
            for e in ea:
                if id(e) in mp:
                    b=mp[id(e)];out.events.append(dataclasses.replace(e,midis=list(b.midis),ties=[(m,"start") for m in b.midis if (m,"start") in [(q,t) for q,t in e.ties]]))
                else:out.events.append(e)
            changed=True
        else:out.events+=ea
    return out,changed
def run(files,A,H,o):
    per=[];taken=0;total=0;base=0
    for s,st in files:
        man=json.loads((OMR/s/"manifest.json").read_text())
        t=parse((OMR/s/man["pieces"][st.rsplit("--",1)[0]]["truth"]).read_bytes())
        total+=len(t)
        pa=OMR/"speed/cache/runs"/A/f"{s}--{st}.musicxml";ph=OMR/"speed/cache/runs"/H/f"{s}--{st}.musicxml"
        if not pa.exists() or not pa.stat().st_size:
            if o.get("fallback") and ph.exists() and ph.stat().st_size:
                h=parse(ph.read_bytes());th=dict(align_bars(t,h))
                per.append(sum(1 for i,x in enumerate(t) if i in th and exact(x,h[th[i]],True)))
            else:per.append(0)
            continue
        a=parse(pa.read_bytes())
        ta=dict(align_bars(t,a))
        if not ph.exists() or not ph.stat().st_size:
            n=sum(1 for i,x in enumerate(t) if i in ta and exact(x,a[ta[i]],True));per.append(n);base+=n;continue
        h=parse(ph.read_bytes());ah=dict(align_bars(a,h))
        res=[]
        if o.get("infer"):
            ends=[max(e.onset+e.dur for e in b.events) for b in a+h if b.events]
            o=dict(o,mode=collections.Counter(ends).most_common(1)[0][0] if ends else None)
        for j,b in enumerate(a):
            if j in ah:
                m,c=merged(b,h[ah[j]],o);res.append(m);taken+=c
            else:res.append(b)
        per.append(sum(1 for i,x in enumerate(t) if i in ta and exact(x,res[ta[i]],True)))
        base+=sum(1 for i,x in enumerate(t) if i in ta and exact(x,a[ta[i]],True))
    return base,sum(per),total,taken,per
if __name__=="__main__":
    A,H=sys.argv[1],sys.argv[2]
    files=REAL
    if len(sys.argv)>3 and sys.argv[3]=="olimpic":
        sp=json.load(open(OMR/"bench-olimpic/split.json"))["inspect"];files=[("bench-olimpic",f"{p}--scan") for p in sp]
    base=dict(unfill=1,ties=0,graft=0)
    for name,o in [("prev",base),("infer",dict(base,infer=1)),("infer+fallback",dict(base,infer=1,fallback=1)),("infer+fb+neither",dict(base,infer=1,fallback=1,neither=1))]:
        b,s,n,tk,p=run(files,A,H,o);print(f"{name:18} base {b} -> {s}/{n} = {100*s/n:.1f}% staves changed {tk}",p if len(p)<8 else "")
