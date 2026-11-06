import sys,pathlib
from lib import *
from scoreone import score
sp=pathlib.Path(sys.argv[1])
for st in ["faisst-op18-2-lied-der-nacht--scan","kinkel-op8-5-trennung--scan","beethoven-op48-5-gottes-macht--scan"]:
    td=truth("bench",st);print(st,"truth shape",shape(td))
    score(td,"current",(RUNS/"marks1"/f"bench--{st}.musicxml").read_bytes())
    for n in ("homr","merged3"):
        f=sp/f"sim-{st}"/f"{n}.musicxml"
        if f.exists():score(td,n,f.read_bytes())
