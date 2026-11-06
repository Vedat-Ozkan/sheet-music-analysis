import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
from barparse import root_of
from fractions import Fraction as F
import xml.etree.ElementTree as ET
import pickle

variant = sys.argv[1] if len(sys.argv) > 1 else "pitch51"
out = []
enc = collections.Counter()
for name in SETS:
    man = json.loads((OMR / name / "manifest.json").read_text())
    for en in man["pdfs"]:
        stem = en["pdf"].rsplit("/", 1)[-1][:-4]
        r = HERE / "cache/runs" / variant / f"{name}--{stem}.musicxml"
        if not r.exists() or not r.stat().st_size:
            continue
        tdata = (OMR / name / man["pieces"][en["piece"]]["truth"]).read_bytes()
        tb = parse(tdata); ob = parse(r.read_bytes())
        troot, oroot = root_of(tdata), root_of(r.read_bytes())
        for label, root in (("t", troot), ("o", oroot)):
            for n in root.iter("note"):
                snd = {t.get("type") for t in n.findall("tie")}
                nt = {t.get("type") for t in n.iter("tied")}
                for x in snd - nt: enc[label, "sound-only", x] += 1
                for x in nt - snd: enc[label, "notation-only", x] += 1
                for x in snd & nt: enc[label, "both", x] += 1
        pairs = dict(align_bars(tb, ob))
        for i, t in enumerate(tb):
            j = pairs.get(i)
            if j is None:
                continue
            o = ob[j]
            tt, ot = ties(t, True), ties(o, True)
            only = sounding(t, True) == sounding(o, True) and rests(t, True) == rests(o, True) and tt != ot
            for kind, c in (("missing", tt - ot), ("extra", ot - tt)):
                for key, count in c.items():
                    out.append(dict(set=name, stem=stem, eng=en["engraver"], piece=en["piece"], i=i, j=j, kind=kind, part=key[0][0], staff=key[0][1], midi=key[1], onset=key[2], count=count, only=only, tnum=t.number, onum=o.number))
pickle.dump(out, open(sys.argv[2], "wb"))
print(len(out), sum(x["count"] for x in out if x["kind"] == "missing"), sum(x["count"] for x in out if x["kind"] == "extra"))
for k, v in sorted(enc.items()): print(k, v)
