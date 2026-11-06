import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
C = collections.Counter(); per = []
for s, pdf in json.load(open(S / "h_set.json")):
    stem = Path(pdf).stem
    run = OMR / "speed/cache/runs/pitch39" / f"{s}--{stem}.musicxml"
    man = json.loads((OMR / s / "manifest.json").read_text())
    tb = parse((OMR / s / man["pieces"][stem.rsplit("--", 1)[0]]["truth"]).read_bytes())
    ob = parse(run.read_bytes())
    hb = []
    d = S / "homr" / stem
    pages = sorted(d.glob("*.musicxml"), key=lambda p: int(p.stem.rsplit("-p", 1)[1].split("_")[0]))
    for p in pages:
        try:
            hb += parse(p.read_bytes())
        except Exception as e:
            C["homr page unparsable"] += 1
    if not hb:
        C["no homr"] += 1
        continue
    to = dict(align_bars(tb, ob))
    oh = dict(align_bars(ob, hb))
    tnotes = sum(sum(pitches(b).values()) for b in tb)
    hshared = sum(sum((pitches(tb[i]) & pitches(hb[j])).values()) for i, j in align_bars(tb, hb))
    oshared = sum(sum((pitches(tb[i]) & pitches(ob[j])).values()) for i, j in align_bars(tb, ob))
    per.append((stem[:30], len(tb), len(ob), len(hb), round(100 * oshared / tnotes, 1), round(100 * hshared / tnotes, 1)))
    for i, j in to.items():
        k = oh.get(j)
        if k is None:
            C["bar not paired to homr"] += 1
            continue
        t, o, h = pitches(tb[i]), pitches(ob[j]), pitches(hb[k])
        wrong = t != o
        st, so, sh = set(t), set(o), set(h)
        diff = len(so ^ sh)
        C["bars"] += 1
        C["wrong" if wrong else "right"] += 1
        tag = "wrong" if wrong else "right"
        C[f"{tag} set-differs"] += diff > 0
        C[f"{tag} differs>=2"] += diff >= 2
        C[f"{tag} homr has note reader lacks"] += bool(sh - so)
        if wrong and diff > 0:
            C["wrong&differs: homr bar equal truth"] += sh == st
            C["wrong&differs: homr closer"] += len(sh ^ st) < len(so ^ st)
for r in per:
    print(r)
print(dict(C))
