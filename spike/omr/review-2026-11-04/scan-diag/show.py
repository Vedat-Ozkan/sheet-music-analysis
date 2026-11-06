import sys, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse
NAMES="C C# D D# E F F# G G# A A# B".split()
def nm(m): return NAMES[m%12]+str(m//12-1)
def ev(b):
    out=[]
    for e in sorted(b.events,key=lambda e:(e.staff,e.onset)):
        out.append(f"s{e.staff}v{e.voice}@{float(e.onset):g}:"+("r" if e.rest else "+".join(nm(m) for m in e.midis))+f"/{float(e.dur):g}")
    return " ".join(out)
n=sys.argv[1]
t=parse((OMR/"bench-olimpic/truth"/f"{n}.musicxml").read_bytes()); o=parse((HERE/"cache/runs/marks1"/f"bench-olimpic--{n}--scan.musicxml").read_bytes())
for i in map(int,sys.argv[2:]):
    print("T",i,t[i].clef,t[i].key,ev(t[i])); print("O",i,o[i].clef,o[i].key,ev(o[i]))
