import collections,json,sys
from lib import *
from whole_bars import exact
import merge3 as M3
from octave_veto_fn import same_classes
for name,v in (("as written",None),("octave veto",same_classes)):
    tot=collections.Counter();row=[]
    for s,st in FIVE:
        pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300"/f"{s}--{st}.musicxml"
        td=truth(s,st);tb=parse(td)
        def ex(d):
            o=parse(d);p=dict(align_bars(tb,o));return {i for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True)}
        a=ex(pa.read_bytes());m=ex(M3.merge(pa,ph,"as_written",v)[0])
        row.append((st[:8],len(a),len(m),len(m-a),len(a-m),sorted(a-m)));tot["g"]+=len(m-a);tot["l"]+=len(a-m);tot["m"]+=len(m)
    print(name,dict(tot),row)
