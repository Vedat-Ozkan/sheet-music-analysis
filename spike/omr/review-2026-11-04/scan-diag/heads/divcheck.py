import collections, glob, json, re, sys, zipfile
from fractions import Fraction as F
from pathlib import Path
import xml.etree.ElementTree as ET
C = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed/cache")
SCR = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/scan-diag/runs/"
LEN = {"breve": F(8), "whole": F(4), "half": F(2), "quarter": F(1), "eighth": F(1, 2), "16th": F(1, 4), "32nd": F(1, 8), "64th": F(1, 16), "128th": F(1, 32)}
def check(data):
    root = ET.fromstring(data)
    zero = trunc = n = 0
    divs = []
    for part in root.iter("part"):
        d = None
        for m in part.iter("measure"):
            for el in m:
                if el.tag == "attributes" and el.find("divisions") is not None:
                    d = int(el.find("divisions").text); divs.append(d)
                    zero += d == 0
                if el.tag == "note" and el.find("duration") is not None and el.find("type") is not None and d:
                    if el.find("time-modification") is not None or el.find("type").text not in LEN:
                        continue
                    dots = len(el.findall("dot"))
                    want = LEN[el.find("type").text] * (2 - F(1, 2 ** dots))
                    n += 1
                    trunc += F(el.find("duration").text) / d != want
    return zero, trunc, n, divs
def score(p):
    z = zipfile.ZipFile(p)
    return z.read(next(x for x in z.namelist() if x.endswith(".xml") and "META" not in x))
T = collections.defaultdict(collections.Counter); ex = []
srcs = [(s, glob.glob(str(C / s / "*.mxl"))) for s in ("bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-tune2", "bench-oldly", "bench-real")]
srcs.append(("olimpic-inspect-raw", glob.glob(SCR + "native-inspect/*.mxl")))
for s, fs in srcs:
    for f in fs:
        try:
            z, t, n, d = check(score(f))
        except Exception as e:
            T[s]["unreadable"] += 1; continue
        T[s]["raw"] += 1; T[s]["zero"] += z > 0; T[s]["wrongdur"] += t > 0
        T[s]["low"] += any(x % 1 or x < 1 for x in d)
        if z or t: ex.append((s, Path(f).name[:30], z, t, n, sorted(set(d))))
for k, v in T.items(): print(k, dict(v))
for e in ex[:40]: print(e)
print(len(ex))
