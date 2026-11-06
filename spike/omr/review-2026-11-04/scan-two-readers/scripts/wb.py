import sys,json,collections,warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
V=sys.argv[1]
ITEMS=[("bench-real","real-bach-wtc1-22-prelude--scan"),("bench-real","real-beethoven-op2no1-iii--scan"),("bench-real","real-grieg-op38no7--scan"),("bench","chopin-prelude-4--real-scan-schirmer"),("bench","mozart-k545-1--real-scan-peters")]
if len(sys.argv)>2:
    ITEMS=[("bench-olimpic",f"{p}--scan") for p in json.load(open(OMR/"bench-olimpic/split.json"))[sys.argv[2]]]
T=collections.Counter()
for s,st in ITEMS:
    man=json.loads((OMR/s/"manifest.json").read_text())
    t=(OMR/s/man["pieces"][st.rsplit("--",1)[0]]["truth"]).read_bytes()
    c=collections.Counter()
    f=HERE/"cache/runs"/V/f"{s}--{st}.musicxml"
    if f.exists() and f.stat().st_size:score_pdf(t,f.read_bytes(),c)
    else:
        b=parse(t);c.update(pdfs=1,failed=1,bars=len(b),wrong=len(b),wrong_unwarned=len(b),notes=sum(sum(pitches(x).values()) for x in b))
    if len(ITEMS)<8:print(st[:30],c["exact"],c["bars"],"pitch",round(100*c["pitch_notes"]/c["notes"],1),"timing",round(100*c["timed_notes"]/c["notes"],1),"wrong",c["wrong"],"unwarned",c["wrong_unwarned"],flush=True)
    T.update(c)
print("ALL",T["exact"],T["bars"],round(100*T["exact"]/T["bars"],1),"pitch",round(100*T["pitch_notes"]/T["notes"],1),"timing",round(100*T["timed_notes"]/T["notes"],1),"unwarned",T["wrong_unwarned"],"of",T["wrong"])
