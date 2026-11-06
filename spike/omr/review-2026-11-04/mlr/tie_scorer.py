import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
C = collections.Counter(); nbars = collections.Counter(); ex = collections.Counter()
variant = sys.argv[1]
for name in SETS:
    man = json.loads((OMR / name / "manifest.json").read_text())
    for en in man["pdfs"]:
        stem = en["pdf"].rsplit("/", 1)[-1][:-4]
        r = HERE / "cache/runs" / variant / f"{name}--{stem}.musicxml"
        if not r.exists() or not r.stat().st_size:
            continue
        tb = parse((OMR / name / man["pieces"][en["piece"]]["truth"]).read_bytes()); ob = parse(r.read_bytes())
        pairs = dict(align_bars(tb, ob))
        partdiff = len({e.part for b in tb for e in b.events}) != len({e.part for b in ob for e in b.events})
        for i, t in enumerate(tb):
            j = pairs.get(i)
            nbars[name] += 1
            if j is None:
                continue
            o = ob[j]
            tt, ot = ties(t, True), ties(o, True)
            pt, po = ties(t, False), ties(o, False)
            C["paired"] += 1
            C["strict_missing"] += sum((tt - ot).values()); C["strict_extra"] += sum((ot - tt).values())
            C["pooled_missing"] += sum((pt - po).values()); C["pooled_extra"] += sum((po - pt).values())
            if partdiff:
                C["partdiff_strict_missing"] += sum((tt - ot).values()); C["partdiff_strict_extra"] += sum((ot - tt).values())
                C["partdiff_pooled_missing"] += sum((pt - po).values()); C["partdiff_pooled_extra"] += sum((po - pt).values())
            same_notes = sounding(t, True) == sounding(o, True) and rests(t, True) == rests(o, True)
            C["exact"] += same_notes and tt == ot
            if same_notes and tt != ot:
                miss, extra = sum((tt - ot).values()), sum((ot - tt).values())
                k = "both" if miss and extra else "missing_only" if miss else "extra_only"
                C["only_" + k] += 1
                ex[name, k] += 1
print(dict(C))
print(sorted(ex.items()))
print(nbars)
