import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse, pitches, rests, ties, sounding
from barparse import align_bars
def fmt(c):
    return " ".join(f"{k[0] if isinstance(k[0],str) else (k[0] if k[0] is not None else '')}:{k[1]}@{k[2]}" + (f"/{k[3]}" if len(k)>3 else "") for k in sorted(c, key=str))
rows = json.load(open("classified.json"))
want = sys.argv[1]; limit = int(sys.argv[2])
shown = 0
for k, v in rows.items():
    if not k.startswith("ol:"): continue
    n = k[3:]
    for r in v:
        if r.get("first") == want or (want == "tielast" and r.get("tie") and r.get("last")):
            t = parse((OMR/"bench-olimpic/truth"/f"{n}.musicxml").read_bytes())[r["bar"]]
            o = parse((HERE/"cache/runs/marks1"/f"bench-olimpic--{n}--scan.musicxml").read_bytes())[r["j"]]
            print(n[8:], "bar", r["bar"], "of", len(v))
            print("  t-only rests", dict(rests(t,False)-rests(o,False)), " o-only", dict(rests(o,False)-rests(t,False)))
            print("  t-only ties", dict(ties(t,False)-ties(o,False)), " o-only", dict(ties(o,False)-ties(t,False)))
            shown += 1
            if shown >= limit: sys.exit()
