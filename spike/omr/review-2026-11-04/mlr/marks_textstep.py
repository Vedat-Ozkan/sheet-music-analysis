import pickle, zipfile, collections
import xml.etree.ElementTree as ET
from pathlib import Path
M = Path(__file__).parent
lab = pickle.load(open(M / "lab_done.pkl", "rb"))
for stem in [p.name for p in (M / "textstep").iterdir()]:
    z = zipfile.ZipFile(next((M / "textstep" / stem).glob("*.omr")))
    c = collections.Counter(); ex = []
    for m in lab:
        if m["stem"] != stem or m["lab"] not in "DLP": continue
        x = ET.fromstring(z.read(f"sheet#{m['sheet']}/sheet#{m['sheet']}.xml"))
        hit = None
        for e in x.iter():
            if e.tag in ("word", "lyric-item"):
                b = e.find("bounds")
                if m["x"] < int(b.get("x")) + int(b.get("w")) and int(b.get("x")) < m["x"] + m["w"] and m["y"] < int(b.get("y")) + int(b.get("h")) and int(b.get("y")) < m["y"] + m["h"]:
                    hit = (e.tag, e.get("value")); break
        c[(m["lab"], "ocr_hit" if hit else "no_ocr")] += 1
        if hit: ex.append(hit)
    print(stem, dict(c), ex[:6])
