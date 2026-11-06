import sys, json
sys.path[:0]=["/home/kema/projects/sheet-music-plugin", "/home/kema/projects/sheet-music-plugin/spike/omr", "/home/kema/projects/sheet-music-plugin/spike/omr/bench", "/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from pitch_causes import xml_root
OMR="/home/kema/projects/sheet-music-plugin/spike/omr/"
def keys(root):
    out=[]
    for pi,part in enumerate(root.iter("part")):
        for m in part.iter("measure"):
            for k in m.iter("key"):
                out.append((pi,m.get("number"),k.get("number"),k.findtext("fifths"),k.findtext("cancel")))
    return out
setname, stem, variant = sys.argv[1:4]
man=json.load(open(OMR+setname+"/manifest.json"))["pieces"]
print("truth", keys(xml_root(open(OMR+setname+"/"+man[stem.rsplit("--",1)[0]]["truth"],"rb").read())))
print("read ", keys(xml_root(open(f"cache/runs/{variant}/{setname}--{stem}.musicxml","rb").read())))
