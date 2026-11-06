import sys, json, collections
sys.path[:0]=["/home/kema/projects/sheet-music-plugin", "/home/kema/projects/sheet-music-plugin/spike/omr", "/home/kema/projects/sheet-music-plugin/spike/omr/bench", "/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from pitch_causes import bars, xml_root, pair, cause
OMR="/home/kema/projects/sheet-music-plugin/spike/omr/"
rows=[l.rstrip("\n").split("\t") for l in open(sys.argv[2]) if l.startswith("accidental")]
kinds=collections.Counter(); ex=collections.defaultdict(list)
cache={}
for _, setname, stem, bar, _ in rows:
    b=int(bar.split()[1])
    if (setname,stem) not in cache:
        m=json.load(open(OMR+setname+"/manifest.json"))["pieces"]
        cache[(setname,stem)]=(bars(xml_root(open(OMR+setname+"/"+m[stem.rsplit("--",1)[0]]["truth"],"rb").read())), bars(xml_root(open(f"cache/runs/{sys.argv[1]}/{setname}--{stem}.musicxml","rb").read())))
    t,r=cache[(setname,stem)]
    for a,bb in pair(t[b-1],r[b-1]):
        if cause(a,bb,t[b-1])!="accidental": continue
        if a["accidental"] and not bb["accidental"]: k="printed sign missed"
        elif bb["accidental"] and not a["accidental"]: k="sign read where none printed"
        elif a["accidental"] and bb["accidental"]: k="sign read as another sign"
        elif a["start"]==0 or True: k="no sign either side (carry or key)"
        kinds[k]+=1
        if len(ex[k])<6: ex[k].append((stem,b,str(a["start"]),a["step"]+str(a["octave"]),a["alter"],a["accidental"],"->",bb["alter"],bb["accidental"]))
print(kinds)
for k,v in ex.items():
    print(k); [print("  ",x) for x in v]
