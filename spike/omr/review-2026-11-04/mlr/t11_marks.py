import collections, pickle, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
K = collections.defaultdict(collections.Counter)
DYN = re.compile(r"^(s?f+z?|p+|m[fp]|sf[zp]?|fz|rf[z]?|fp)\.?$", re.I)
txt = collections.Counter(); chord = collections.Counter(); words = collections.Counter()
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    g = "scan" if name == "bench-real" or eng == "scan" else eng if eng in ("ms", "vr", "ly", "ly-old") else "other"
    for i, j in align_bars(tb, ob):
        t, o = tb[i], ob[j]
        tm = collections.Counter((k, e.onset) for e in t.events for k in e.marks)
        om = collections.Counter((k, e.onset) for e in o.events for k in e.marks)
        for (k, _), n in (tm & om).items():
            K[k]["hit"] += n; K[k][g + " hit"] += n
        for (k, _), n in (tm - om).items():
            K[k]["missed"] += n
        for (k, _), n in (om - tm).items():
            K[k]["false"] += n; K[k][g + " false"] += n
        for w in o.texts:
            if DYN.match(w.strip()):
                txt["dynamic word as text (read)"] += 1
            words["read"] += 1
        for w in t.texts:
            if DYN.match(w.strip()):
                txt["dynamic word as text (truth)"] += 1
            words["truth"] += 1
        words["read fingers"] += o.fingerings; words["truth fingers"] += t.fingerings
        # chord ties
        def tied(bar):
            d = {}
            for e in bar.events:
                if len(e.midis) >= 2:
                    d[(e.onset, tuple(sorted(e.midis)))] = {m for m, ty in e.ties if ty == "start"}
            return d
        td, od = tied(t), tied(o)
        for key, ts in td.items():
            if len(ts) >= 2 and key in od:
                chord["truth chord with 2+ ties, chord matched"] += 1
                if od[key] == ts:
                    chord["all same"] += 1
                elif od[key] and od[key] < ts:
                    chord["only some ties read"] += 1
                elif not od[key]:
                    chord["no tie read"] += 1
                else:
                    chord["other"] += 1
for k, c in sorted(K.items(), key=lambda kv: -(kv[1]["hit"] + kv[1]["false"] + kv[1]["missed"])):
    print(k, "truth", c["hit"] + c["missed"], "hit", c["hit"], "false", c["false"], {g: c[g + " false"] for g in ("ms", "vr", "ly", "ly-old", "scan", "other")})
print(dict(txt), dict(words)); print(dict(chord))
