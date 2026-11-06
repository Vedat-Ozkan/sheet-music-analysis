import sys,json,pathlib,collections
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
import pikepdf
from engine.read_pdf import is_scan
O=pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr");c=collections.Counter()
for s in ["bench","bench-heldout","bench-heldout2","bench-heldout3","bench-tune2","bench-oldly","bench-real","bench-olimpic"]:
    for e in json.loads((O/s/"manifest.json").read_text())["pdfs"]:
        st=e["pdf"];sc="scan" in st
        with pikepdf.open(O/s/st) as p:r=is_scan(p)
        c[(s if s in("bench-real","bench-olimpic") else "clean-sets", "named scan" if sc else "named clean", "rule scan" if r else "rule not scan")]+=1
for k,v in sorted(c.items()):print(v,k)
