import pickle, zipfile, sys
import xml.etree.ElementTree as ET
from pathlib import Path
M = Path(__file__).parent
lab = pickle.load(open(M / "lab_done.pkl", "rb"))
root = M / "marksdiag"
def inters(stem, n):
    z = zipfile.ZipFile(next((root / stem).glob("*.omr")))
    x = ET.fromstring(z.read(f"sheet#{n}/sheet#{n}.xml"))
    out = []
    for e in x.iter():
        b = e.find("bounds")
        if b is not None:
            out.append((e.tag, e.get("value"), e.get("shape"), int(e.get("glyph") or 0), e.get("grade"), e.get("ctx-grade"), int(e.get("id") or 0), int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))))
    gl = {}
    for g in x.iter("glyph"):
        gl[g.get("id")] = (g.get("group"), g.get("left"), g.get("top"), g.get("width"), g.get("height"))
    return out, gl
seen = set()
for want in sys.argv[1:]:
    k = 0
    for m in lab:
        if m["lab"] != want: continue
        k += 1
        if k > 8: break
        out, gl = inters(m["stem"], m["sheet"])
        il = m["il"]
        print("---", want, m["stem"], "sheet", m["sheet"], m["tag"], m["shape"], "box", m["x"], m["y"], m["w"], m["h"], "grade", m["grade"], m["ctx"], "glyph", m["glyph"], gl.get(m["glyph"]), "rel", m["rel"])
        for o in out:
            if o[7] < m["x"] + m["w"] + 2*il and m["x"] - 2*il < o[7] + o[9] and o[8] < m["y"] + m["h"] + il and m["y"] - il < o[8] + o[10] and o[0] not in ("staff","system","part","measure","stack","head-chord","beam-group"):
                print("   ", o[:9], o[9:], gl.get(str(o[3])))
