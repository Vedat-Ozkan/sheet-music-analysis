import collections,json,sys
from lib import *
T=collections.Counter();low=[]
for s in ["bench","bench-tune2","bench-oldly","bench-real"]:
    man=json.loads((OMR/s/"manifest.json").read_text())
    for e in man["pdfs"]:
        st=e["pdf"].rsplit("/",1)[-1][:-4]
        f=RUNS/"marks1"/f"{s}--{st}.musicxml"
        if not f.exists() or not f.stat().st_size:T["no reading"]+=1;continue
        n=len(parse((OMR/s/man["pieces"][e["piece"]]["truth"]).read_bytes()));m=len(parse(f.read_bytes()))
        T["pdfs"]+=1
        if m<0.8*n:T["reading under 80% of bars"]+=1;low.append((s,st,m,n))
print(dict(T));print(low[:30])
