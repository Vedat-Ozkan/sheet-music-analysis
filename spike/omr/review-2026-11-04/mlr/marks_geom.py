import pickle, collections, zipfile, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path
M = Path(__file__).parent
rows = pickle.load(open(M / "marksdiag_ink.pkl", "rb"))
root = M / "marksdiag"
cache = {}
def load(stem, n):
    if (stem, n) in cache:
        return cache[(stem, n)]
    z = zipfile.ZipFile(next((root / stem).glob("*.omr")))
    x = ET.fromstring(z.read(f"sheet#{n}/sheet#{n}.xml"))
    rel = {}
    ferm = []
    for r in x.iter("relation"):
        for c in r:
            if c.tag == "chord-articulation":
                rel[int(r.get("target"))] = (float(c.get("dx", 0)), float(c.get("dy", 0)), float(c.get("grade", 0)))
    for f in x.iter("fermata"):
        b = f.find("bounds")
        if b is not None:
            ferm.append((int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))))
    cache[(stem, n)] = (rel, ferm)
    return cache[(stem, n)]
for m in rows:
    rel, ferm = load(m["stem"], m["sheet"])
    m["rel"] = rel.get(m["inter"])
    cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
    m["in_fermata"] = any(f[0] <= cx <= f[0] + f[2] and f[1] <= cy <= f[1] + f[3] for f in ferm)
pickle.dump(rows, open(M / "marksdiag_ink.pkl", "wb"))
ED = ("lilypond-mutopia", "real-scan-peters", "real-scan-schirmer")
def eng(m): return m["stem"].rsplit("--", 1)[1]
for tagset, name in [(("staccato",), "staccato"), (("tenuto",), "tenuto"), (("accent",), "accent"), (("staccatissimo", "strong-accent"), "stacc/marc")]:
    for cls in ("true", "false"):
        r = [m for m in rows if m["cls"] == cls and m["tag"] in tagset and m["rel"] and eng(m) not in ED]
        h = collections.Counter(min(int(m["rel"][1] * 2) / 2, 5) for m in r)
        print(name, cls, len(r), "dy:", sorted(h.items()))
        hx = collections.Counter(min(int(abs(m["rel"][0]) * 5) / 5, 1) for m in r)
        print("    dx:", sorted(hx.items()))
print("no rel", collections.Counter((m["cls"], m["tag"]) for m in rows if not m["rel"]).most_common(12))
print("in fermata", collections.Counter((m["cls"], m["tag"]) for m in rows if m["in_fermata"]).most_common(10))
