import collections,json,pathlib,sys,tempfile
from lib import *
import fair_run as FR
import merge3
rows=[]
for s,st in FIVE:
    td=truth(s,st);pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300"/f"{s}--{st}.musicxml"
    data,info=merge3.merge(pa,ph)
    rows.append(dict(id=st,status=info["reason"],current=FR.score(td,pa.read_bytes()),homr=FR.score(td,ph.read_bytes()),merged=FR.score(td,data),renders=True))
print(json.dumps(FR.verdict(rows)))
