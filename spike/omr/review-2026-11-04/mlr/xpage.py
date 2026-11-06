import sys,json,collections,warnings
warnings.filterwarnings("ignore")
M="/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr"
sys.path.insert(0,M); sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
from barparse import root_of
from tie_cand import notes
C=collections.Counter()
for name in SETS:
    man=json.loads((OMR/name/"manifest.json").read_text())
    for en in man["pdfs"]:
        stem=en["pdf"].rsplit("/",1)[-1][:-4]
        r=HERE/"cache/runs/pitch51"/f"{name}--{stem}.musicxml"
        tb=parse((OMR/name/man["pieces"][en["piece"]]["truth"]).read_bytes()); ob=parse(r.read_bytes())
        on=notes(root_of(r.read_bytes()))
        pairs=dict(align_bars(tb,ob)); inv={j:i for i,j in pairs.items()}
        for j,b in enumerate(on):
            if j+1>=len(ob): continue
            k="page" if ob[j+1].new_page else "sys" if ob[j+1].new_system else "bar"
            starts=[a for a in b if a["tstart"]]
            ends=[e for e in on[j+1] if e["tstop"]]
            for a in starts:
                if any(e["part"]==a["part"] and e["midi"]==a["midi"] and e["onset"]==0 for e in ends) and not any(x["part"]==a["part"] and x["midi"]==a["midi"] and x["tstop"] and x["onset"]>a["onset"] for x in b):
                    C["read tie crossing",k]+=1
            i=inv.get(j)
            if i is None: continue
            t=ties(tb[i],True); o=ties(ob[j],True)
            # truth ties in bar i that cross into next bar
            tnotes=tb[i]
            for (key,midi,onset),c in t.items():
                # crossing: note ends at bar end in truth
                ev=[e for e in tb[i].events if (e.part,e.staff)==key and e.onset==onset and midi in e.midis]
                if not ev: continue
                nextstart=any(e.onset==0 and midi in e.midis and (midi,"stop") in e.ties and e.part==key[0] for e in (tb[i+1].events if i+1<len(tb) else []))
                insame=any(e.onset>onset and midi in e.midis and (midi,"stop") in e.ties and e.part==key[0] for e in tb[i].events)
                if nextstart and not insame:
                    C["truth tie crossing",k]+=c
                    if o[(key,midi,onset)]>0: C["truth crossing found",k]+=min(c,o[(key,midi,onset)])
print(sorted(C.items()))
