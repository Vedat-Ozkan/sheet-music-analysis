import sys, json, hashlib, collections
from pathlib import Path
from fractions import Fraction
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from attribute import rx
import tripletfix as F
bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); man = json.load(open(bd / "manifest.json")); sub = sys.argv[3]
p = next(p for p in man["pdfs"] if sub in p["pdf"])
key = hashlib.sha256((bd / p["pdf"]).read_bytes() + res["audiveris_install"].encode()).hexdigest()[:32]
root = rx((bd / "cache" / f"{key}.musicxml").read_bytes()); c = collections.Counter(); shown = 0
for pi, part in enumerate(root.iter("part")):
    div = 1; ts = None
    for m in part.findall("measure"):
        a = m.find("attributes")
        if a is not None:
            if a.find("divisions") is not None: div = int(float(a.findtext("divisions")))
            t = a.find("time")
            if t is not None: ts = Fraction(int(t.findtext("beats")), int(t.findtext("beat-type")))
        for key2, evs in F._events(m).items():
            tot = sum(Fraction(int(float(e[0].findtext("duration") or 0)), div) for e in evs)
            if tot > ts * 4 and m.get("implicit") != "yes":
                s = " ".join(("r" if e[0].find("rest") is not None else "") + {"eighth": "8", "16th": "16", "quarter": "4", "half": "2", "whole": "1", "32nd": "32"}.get(e[0].findtext("type"), "?") + "." * len(e[0].findall("dot")) + (e[0].find("beam").text[0] if e[0].find("beam") is not None else "") for e in evs)
                if shown < int(sys.argv[4]): print("bar", m.get("number"), "part", pi, key2, "over", tot - ts * 4, "|", s); shown += 1
