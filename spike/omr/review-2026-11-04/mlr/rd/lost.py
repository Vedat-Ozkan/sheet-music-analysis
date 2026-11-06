import sys, collections
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from barparse import *
truth, xml = sys.argv[1], sys.argv[2]
tb = parse(open(truth,'rb').read()); ob = parse(open(xml,'rb').read())
pairs = align_bars(tb, ob)
print(len(tb), len(ob), len(pairs))
tot=collections.Counter(); 
for i,j in pairs:
    t=collections.Counter((e.part,e.onset,e.typ) for e in tb[i].events if e.rest and not e.hidden)
    o=collections.Counter((e.part,e.onset,e.typ) for e in ob[j].events if e.rest and not e.hidden)
    tot['t']+=sum(t.values()); tot['o']+=sum(o.values())
    m=t-o; x=o-t
    tot['lost']+=sum(m.values()); tot['extra']+=sum(x.values())
    if m and len(sys.argv)>3: print(i,j,'lost',[(p,str(a),b) for (p,a,b) in m],'extra',[(p,str(a),b) for (p,a,b) in x])
print(dict(tot))
