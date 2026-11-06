import collections,json,sys,warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,'.')
from whole_bars import *
C=collections.Counter(); per=collections.Counter(); kinds=collections.Counter()
for name in SETS:
    man=json.loads((OMR/name/"manifest.json").read_text())
    for en in man["pdfs"]:
        stem=en["pdf"].rsplit("/",1)[-1][:-4]
        r=HERE/"cache/runs/pitch51"/f"{name}--{stem}.musicxml"
        if not r.exists() or not r.stat().st_size: continue
        tb=parse((OMR/name/man["pieces"][en["piece"]]["truth"]).read_bytes()); ob=parse(r.read_bytes())
        pairs=dict(align_bars(tb,ob))
        for i,t in enumerate(tb):
            j=pairs.get(i)
            if j is None: continue
            o=ob[j]; C['bars']+=1
            s=sounding(t,True)==sounding(o,True); R=rests(t,True)==rests(o,True); T=ties(t,True)==ties(o,True)
            kinds[(s,R,T)]+=1
            tt,ot=ties(t,True),ties(o,True)
            C['true_ties']+=sum(tt.values()); C['found']+=sum((tt&ot).values()); C['missing']+=sum((tt-ot).values()); C['extra']+=sum((ot-tt).values())
            if s and R and not T:
                C['only_ties']+=1; per[name+'/'+stem]+=1
                C['only_missing']+=sum((tt-ot).values()); C['only_extra']+=sum((ot-tt).values())
print(dict(C))
for k,v in kinds.most_common(): print('notes/rests/ties right',k,v)
print(per.most_common(15))
