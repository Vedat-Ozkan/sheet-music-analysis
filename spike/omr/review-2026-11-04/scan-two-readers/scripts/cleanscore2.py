import sys,json,collections,warnings,pathlib
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from barparse import OMR,parse,align_bars,pitches,timed
from whole_bars import exact
from mergexml import merge,RUNS
items=json.load(open(pathlib.Path(__file__).parent/"homr300clean.items.json"))
T=collections.defaultdict(collections.Counter);better=collections.Counter()
for s,st in items:
    man=json.loads((OMR/s/"manifest.json").read_text());piece=st.rsplit("--",1)[0]
    t=parse((OMR/s/man["pieces"][piece]["truth"]).read_bytes())
    pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300clean"/f"{s}--{st}.musicxml"
    vals={}
    nparts=len({e.part for b in t for e in b.events});nstaves=len({(e.part,e.staff) for b in t for e in b.events})
    grp="piano-like (1 part)" if nparts==1 else "several parts"
    srcs={"audiveris":pa.read_bytes() if pa.exists() and pa.stat().st_size else None,"homr":ph.read_bytes() if ph.exists() and ph.stat().st_size else None}
    srcs["merged"]=merge(pa,ph)[0] if srcs["homr"] else srcs["audiveris"]
    for v,d in srcs.items():
        c=T[(grp,v)];c["pdfs"]+=1;c["bars"]+=len(t);c["notes"]+=sum(sum(pitches(b).values()) for b in t)
        if d is None:c["failed"]+=1;vals[v]=0;continue
        o=parse(d);p=dict(align_bars(t,o))
        e=sum(1 for i,b in enumerate(t) if i in p and exact(b,o[p[i]],True));c["exact"]+=e;vals[v]=e
        c["wrongcount"]+=len(o)!=len(t)
        c["pitch"]+=sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(t) if i in p)
        c["timed"]+=sum(sum((timed(b)&timed(o[p[i]])).values()) for i,b in enumerate(t) if i in p)
    better["homr better" if vals["homr"]>vals["audiveris"] else "audiveris better" if vals["homr"]<vals["audiveris"] else "tie"]+=1
for v,c in T.items():print(v,"pdfs",c["pdfs"],"exact",c["exact"],"/",c["bars"],f"{100*c['exact']/c['bars']:.1f}% pitch {100*c['pitch']/c['notes']:.1f} timing {100*c['timed']/c['notes']:.1f} failed {c['failed']} wrongbarcount {c['wrongcount']}")
print(dict(better))
