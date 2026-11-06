import pickle, zipfile, collections
import xml.etree.ElementTree as ET
from pathlib import Path
M = Path(__file__).parent
lab = pickle.load(open(M / "lab_done.pkl", "rb"))
root = M / "marksdiag"
cache = {}
def texts(stem, n):
    if (stem, n) in cache: return cache[(stem, n)]
    z = zipfile.ZipFile(next((root / stem).glob("*.omr")))
    x = ET.fromstring(z.read(f"sheet#{n}/sheet#{n}.xml"))
    out = []
    for e in x.iter():
        if e.tag in ("word", "lyric-item"):
            b = e.find("bounds")
            out.append((e.tag, e.get("value"), float(e.get("ctx-grade") or e.get("grade") or 0), int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))))
    cache[(stem, n)] = out
    return out
T = collections.defaultdict(collections.Counter)
ex = collections.defaultdict(list)
for m in lab:
    hit = [t for t in texts(m["stem"], m["sheet"]) if m["x"] < t[3] + t[5] and t[3] < m["x"] + m["w"] and m["y"] < t[4] + t[6] and t[4] < m["y"] + m["h"]]
    if not hit:
        k = "none"
    else:
        t = hit[0]
        k = t[0] + ("<=3" if len(t[1]) <= 3 else ">3")
    T[m["lab"]][k] += 1
    if hit: ex[m["lab"]].append((hit[0][1], hit[0][2]))
for k, v in sorted(T.items()):
    print(k, dict(v), ex[k][:14])
