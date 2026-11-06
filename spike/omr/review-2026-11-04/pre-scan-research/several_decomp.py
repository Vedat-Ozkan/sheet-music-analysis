import collections,json,re,sys,types
from lib import *
from whole_bars import exact
import merge3 as M3
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
import mergexml as M1
src=(OMR/"review-2026-11-04/scan-two-readers/scripts/merge2.py").read_text()
guard='    if len(ET.fromstring(da).findall("part"))>1:return da,0,0\n'
assert guard in src
M2b=types.ModuleType("merge2b");M2b.__file__=str(OMR/"review-2026-11-04/scan-two-readers/scripts/merge2.py")
exec(compile(src.replace(guard,"").split('if __name__=="__main__":')[0],"merge2b","exec"),M2b.__dict__)
items=json.load(open(HERE/"clean60.items.json"))
def grp(ts):
    if ts==(1,2):return "voice+piano"
    if ts==(1,1,1,1):return "four single staves"
    return "other several"
T=collections.defaultdict(collections.Counter)
for s,st in items:
    td=truth(s,st);ts=shape(td)
    if len(ts)==1:continue
    g=grp(ts);tb=parse(td);tm=canon_map(td)
    pa,ph=RUNS/"marks1"/f"{s}--{st}.musicxml",RUNS/"homr300clean"/f"{s}--{st}.musicxml"
    v={"current":pa.read_bytes()}
    if ph.exists() and ph.stat().st_size:
        v["A old rule, first-part bug (mergexml)"]=M1.merge(pa,ph)[0]
        try:
            v["B new rule, first-part bug, no guard (merge2 minus guard)"]=M2b.merge(pa,ph)[0]
        except Exception as e:
            T[(g,"B new rule, first-part bug, no guard (merge2 minus guard)")]["crash"]+=1
        v["C new rule, staff by position (merge3 as written)"]=M3.merge(pa,ph,"as_written")[0]
        v["D take homr only when current's staff is short (merge3)"]=M3.merge(pa,ph,"only_if_current_short")[0]
    for k,d in v.items():
        o=parse(d);p=dict(align_bars(tb,o));om=canon_map(d)
        for gg in (g,"ALL several"):
            c=T[(gg,k)];c["bars"]+=len(tb)
            c["strict"]+=sum(1 for i,b in enumerate(tb) if i in p and exact(b,o[p[i]],True))
            c["pos"]+=sum(1 for i,b in enumerate(tb) if i in p and bar_exact(b,o[p[i]],tm,om))
for k in sorted(T):
    c=T[k];print(f"{k[0]:20} {k[1]:58} bars {c['bars']:5} strict {c['strict']:5} {100*c['strict']/max(c['bars'],1):5.1f}  by-position {c['pos']:5} {100*c['pos']/max(c['bars'],1):5.1f} crash {c['crash']}")
