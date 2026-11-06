import collections,json,pathlib,sys,warnings
warnings.filterwarnings("ignore")
sys.dont_write_bytecode=True
OMRD=pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr")
sys.path.insert(0,str(OMRD/"speed"))
from barparse import OMR,parse,align_bars,pitches,timed,root_of
RUNS=OMR/"speed/cache/runs"
HERE=pathlib.Path(__file__).parent
FIVE=[("bench-real","real-bach-wtc1-22-prelude--scan"),("bench-real","real-beethoven-op2no1-iii--scan"),("bench-real","real-grieg-op38no7--scan"),("bench","chopin-prelude-4--real-scan-schirmer"),("bench","mozart-k545-1--real-scan-peters")]
def truth(s,st):
    man=json.loads((OMR/s/"manifest.json").read_text())
    return (OMR/s/man["pieces"][st.rsplit("--",1)[0]]["truth"]).read_bytes()
def staff_order(data):
    root=root_of(data);order=[]
    for pi,p in enumerate(root.findall("part")):
        ns=0
        for at in p.iter("staves"):ns=max(ns,int(at.text))
        st={n.findtext("staff","1") for n in p.iter("note")}
        names=sorted(st|{str(i+1) for i in range(ns)},key=int) or ["1"]
        order+=[(pi,n) for n in names]
    return order
def shape(data):
    c=collections.Counter(p for p,_ in staff_order(data))
    return tuple(c[i] for i in sorted(c))
def canon_map(data):
    return {k:i for i,k in enumerate(staff_order(data))}
def sounding(ev):
    c=collections.Counter()
    for e in ev:
        for m in e.midis:c[(m,e.onset,e.dur)]+=1
    return c
def rests(ev):
    return collections.Counter((e.onset,e.dur) for e in ev if e.rest and not e.hidden)
def ties(ev):
    return collections.Counter((m,e.onset) for e in ev for m,t in e.ties if t=="start")
def by_staff(bar,cmap):
    d=collections.defaultdict(list)
    for e in bar.events:d[cmap.get((e.part,e.staff),(e.part,e.staff))].append(e)
    return d
def staff_exact(a,b):
    return sounding(a)==sounding(b) and rests(a)==rests(b) and ties(a)==ties(b)
def bar_exact(tb,ob,tm,om):
    d1,d2=by_staff(tb,tm),by_staff(ob,om)
    return all(staff_exact(d1.get(k,[]),d2.get(k,[])) for k in set(d1)|set(d2))
def per_part_bars(data):
    r=root_of(data)
    return [len(p.findall("measure")) for p in r.findall("part")]
