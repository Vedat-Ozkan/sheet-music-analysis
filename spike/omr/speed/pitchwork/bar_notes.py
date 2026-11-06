import sys, json
sys.path[:0]=["/home/kema/projects/sheet-music-plugin", "/home/kema/projects/sheet-music-plugin/spike/omr", "/home/kema/projects/sheet-music-plugin/spike/omr/bench", "/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from pitch_causes import bars, xml_root, pair, cause
OMR="/home/kema/projects/sheet-music-plugin/spike/omr/"
setname, stem, variant, *nums = sys.argv[1:]
man=json.load(open(OMR+setname+"/manifest.json"))["pieces"]
t=bars(xml_root(open(OMR+setname+"/"+man[stem.rsplit("--",1)[0]]["truth"],"rb").read()))
r=bars(xml_root(open(f"cache/runs/{variant}/{setname}--{stem}.musicxml","rb").read()))
for n in map(int,nums):
    for a,b in pair(t[n-1],r[n-1]):
        c=cause(a,b,t[n-1])
        if c: print(n, c, "at", a["start"], "staff", a["staff"][1], "truth", a["step"]+str(a["octave"]), a["alter"], a["accidental"], "| read", b["step"]+str(b["octave"]), b["alter"], b["accidental"])
