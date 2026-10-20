import sys, json, hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from attribute import rx
bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); sub = sys.argv[3]
man = json.load(open(bd / "manifest.json")); p = next(p for p in man["pdfs"] if sub in p["pdf"])
key = hashlib.sha256((bd / p["pdf"]).read_bytes() + res["audiveris_install"].encode()).hexdigest()[:32]
def bars(root):
    out = {}
    for pi, part in enumerate(root.iter("part")):
        for k, m in enumerate(part.iter("measure")):
            v = {}
            for n in m.iter("note"):
                if n.find("grace") is not None: continue
                nm = (n.findtext("staff"), n.findtext("voice"))
                t = n.findtext("type") or "?"
                s = {"eighth": "8", "16th": "16", "quarter": "4", "half": "2", "whole": "1", "32nd": "32"}.get(t, t)
                s += "." * len(n.findall("dot"))
                if n.find("rest") is not None: s = "r" + s
                tm = n.find("time-modification")
                if tm is not None: s += "{%s:%s}" % (tm.findtext("actual-notes"), tm.findtext("normal-notes"))
                if n.find("chord") is not None: s = "+"
                b = n.find("beam"); 
                if b is not None: s += {"begin": "[", "end": "]"}.get(b.text, "")
                if n.find("notations/tuplet") is not None: s += "T"
                v.setdefault(nm, []).append(s)
            out[(pi, k)] = v
    return out
T = bars(rx((bd / man["pieces"][p["piece"]]["truth"]).read_bytes())); O = bars(rx((bd / "cache" / f"{key}.musicxml").read_bytes()))
for k in sorted(T):
    if len(sys.argv) > 6 and str(k[0]) != sys.argv[6]: continue
    if len(sys.argv) > 4 and k[1] not in range(int(sys.argv[4]), int(sys.argv[5])): continue
    print("bar", k[1] + 1); print("  T", {a: " ".join(b) for a, b in T[k].items()}); print("  O", {a: " ".join(b) for a, b in O.get(k, {}).items()})
