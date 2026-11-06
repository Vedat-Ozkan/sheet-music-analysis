import collections, pickle, sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
t1 = pickle.loads((S / "t1.pkl").read_bytes())
flag = collections.defaultdict(dict)
for r in t1:
    if not r.get("summary") and r["j"] is not None and r["i"] is not None:
        flag[(r["set"], r["stem"])][r["j"]] = (r["of"], r["tf"], r["i"])
C = collections.Counter()
for name, stem, piece, eng, data, tdata in readings():
    fl = flag.get((name, stem))
    if not fl:
        continue
    tb, ob = parse(tdata), parse(data)
    for j, (of, tf, i) in fl.items():
        if of or tf or j >= len(ob) or i >= len(tb):
            continue
        b = ob[j]
        if b.full is None:
            continue
        ends = collections.defaultdict(lambda: F(0))
        for e in b.events:
            ends[(e.part, e.staff)] = max(ends[(e.part, e.staff)], e.onset + e.dur)
        tends = collections.defaultdict(lambda: F(0))
        for e in tb[i].events:
            tends[(e.part, e.staff)] = max(tends[(e.part, e.staff)], e.onset + e.dur)
        short = [k for k, v in ends.items() if v < b.full]
        tright = timed(b) == timed(tb[i])
        trest = collections.Counter((e.part, e.onset) for e in tb[i].events if e.rest and not e.hidden)
        orest = collections.Counter((e.part, e.onset) for e in b.events if e.rest)
        rok = trest == orest
        C["unflagged bars"] += 1
        C["timing wrong"] += not tright
        C["rests wrong"] += not rok
        if short:
            C["a staff short"] += 1
            C["short & timing wrong"] += not tright
            C["short & rests wrong"] += not rok
            C["short & any wrong"] += not (tright and rok)
            C["short & truth also short"] += any(tends[k] < b.full for k in short)
print(dict(C))
