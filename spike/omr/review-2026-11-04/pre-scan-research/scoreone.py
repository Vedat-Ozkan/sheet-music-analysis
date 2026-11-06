import collections,json,sys,glob,pathlib
from lib import *
from whole_bars import exact
def score(td,name,data):
    tb=parse(td);o=parse(data);p=dict(align_bars(tb,o));tm=canon_map(td);om=canon_map(data)
    st=sum(1 for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True))
    po=sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om))
    n=sum(sum(pitches(b).values()) for b in tb)
    pit=sum(sum((pitches(b)&pitches(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
    tim=sum(sum((timed(b)&timed(o[p[i]])).values()) for i,b in enumerate(tb) if i in p)
    print(f"{name:22} bars {len(tb)} read {len(o)} paired {len(p)} strict {st} by-position {po} pitch {100*pit/n:.1f} timing {100*tim/n:.1f} shape {shape(data)} part-bars {per_part_bars(data)}")
    return dict(strict=st,pos=po,bars=len(tb))
if __name__=="__main__":
    tf,*rest=sys.argv[1:]
    td=open(tf,"rb").read()
    print("truth shape",shape(td),"bars",len(parse(td)))
    for r in rest:
        f=pathlib.Path(r)
        if f.exists() and f.stat().st_size:score(td,f.name,f.read_bytes())
