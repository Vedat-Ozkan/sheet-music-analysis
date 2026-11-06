import sys,json,warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
for name,stem in (("bench-heldout","h-schubert-erlkonig--ly"),("bench","kinkel-op8-5-trennung--ms")):
    man=json.loads((OMR/name/"manifest.json").read_text())
    piece=stem.rsplit("--",1)[0]
    tb=parse((OMR/name/man["pieces"][piece]["truth"]).read_bytes())
    a=parse((HERE/"cache/runs/pitch51"/f"{name}--{stem}.musicxml").read_bytes()); b=parse((HERE/"cache/runs/tie2"/f"{name}--{stem}.musicxml").read_bytes())
    pa,pb=dict(align_bars(tb,a)),dict(align_bars(tb,b))
    for i,t in enumerate(tb):
        ja,jb=pa.get(i),pb.get(i)
        if ja is None or jb is None: continue
        x=sum((timed(t)&timed(a[ja])).values()); y=sum((timed(t)&timed(b[jb])).values())
        if x!=y:
            print(stem,"bar",t.number,"timed",x,"->",y,"of",sum(timed(t).values()),"ties",sum(ties(t,True).values()),"read",sum(ties(a[ja],True).values()),"->",sum(ties(b[jb],True).values()),"lost",[(m,str(o)) for (m,o) in (timed(a[ja])-timed(b[jb]))][:4],"gained",[(m,str(o)) for (m,o) in (timed(b[jb])-timed(a[ja]))][:4])
