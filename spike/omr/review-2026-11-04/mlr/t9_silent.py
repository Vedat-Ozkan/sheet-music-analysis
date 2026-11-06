import collections, math, pickle, re, sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
import numpy as np
S = Path(__file__).parent
t1 = pickle.loads((S / "t1.pkl").read_bytes())
flag = collections.defaultdict(dict)
for r in t1:
    if not r.get("summary") and r["j"] is not None and r["i"] is not None:
        flag[(r["set"], r["stem"])][r["j"]] = (r["of"], r["tf"], r["i"])
cause = {}
for line in open(S / "causes_all.txt"):
    f = line.rstrip("\n").split("\t")
    if len(f) >= 4 and f[3].startswith("bar "):
        cause[(f[1], f[2], int(f[3][4:]) - 1)] = f[0]

def alter(m, step):
    a = (m % 12 - SEMI[step] + 6) % 12 - 6
    return a

def sonorities(bar):
    onsets = sorted({e.onset for e in bar.events if e.midis})
    out = []
    for t in onsets:
        act = [e for e in bar.events if e.midis and e.onset <= t < e.onset + max(e.dur, F(1, 64))]
        pcs = sorted({m % 12 for e in act for m in e.midis})
        attack = [e for e in act if e.onset == t]
        dur = min(e.dur for e in attack)
        out.append((t, pcs, dur))
    return out

def normal(pcs):
    if not pcs:
        return ()
    best = None
    for r in pcs:
        t = tuple(sorted((p - r) % 12 for p in pcs))
        if best is None or t < best:
            best = t
    return best

pieces = {}
for name, stem, piece, eng, data, tdata in readings():
    if piece not in pieces:
        pieces[piece] = parse(tdata)
counts = collections.Counter()
per_piece = {}
for piece, bars in pieces.items():
    c = collections.Counter()
    for b in bars:
        for t, pcs, d in sonorities(b):
            if len(pcs) >= 2:
                c[normal(pcs)] += 1
    per_piece[piece] = c
    counts.update(c)
total = sum(counts.values())

def surprise(pcs, piece):
    k = normal(pcs)
    n = counts[k] - per_piece[piece][k]
    tot = total - sum(per_piece[piece].values())
    return -math.log((n + 0.5) / (tot + 100))

rows = []
for name, stem, piece, eng, data, tdata in readings():
    fl = flag.get((name, stem))
    if not fl:
        continue
    tb, ob = parse(tdata), parse(data)
    for j, (of, tf, i) in fl.items():
        if j >= len(ob) or i >= len(tb):
            continue
        b = ob[j]
        tp, op = pitches(tb[i]), pitches(b)
        wrong = tp != op
        sub = min(sum((tp - op).values()), sum((op - tp).values()))
        # D1 cross relation at same onset
        cr = 0
        by = collections.defaultdict(list)
        for e in b.events:
            for m, st in zip(e.midis, e.steps):
                by[e.onset].append((st, alter(m, st)))
        for t, ns in by.items():
            d = collections.defaultdict(set)
            for st, a in ns:
                d[st].add(a)
            cr += sum(1 for v in d.values() if len(v) > 1)
        # D1b any time in the bar across different octaves, sign difference within one beat
        cr2 = 0
        allnotes = [(e.onset, st, alter(m, st), m // 12) for e in b.events for m, st in zip(e.midis, e.steps)]
        for a in allnotes:
            for c in allnotes:
                if a < c and a[1] == c[1] and a[2] != c[2] and abs(a[0] - c[0]) <= 1 and a[3] != c[3]:
                    cr2 += 1
        son = sonorities(b)
        sp = [surprise(p, piece) for t, p, d in son if len(p) >= 3]
        sp_long = [surprise(p, piece) for t, p, d in son if len(p) >= 3 and d >= F(1, 2)]
        # D3 local rarity
        win = collections.Counter()
        for k in range(max(0, j - 2), min(len(ob), j + 3)):
            win.update({m % 12: c for m, c in pitches(ob[k]).items()})
        tot = sum(win.values()) or 1
        rar = max((1 - win[m % 12] / tot for m in op), default=0)
        rarcount = sum(c for m, c in op.items() if win[m % 12] / tot < 0.02)
        rows.append(dict(set=name, eng=eng, of=of, tf=tf, wrong=wrong, sub=sub, cause=cause.get((name, stem, i)), cr=cr, cr2=cr2, sp=max(sp, default=0), spl=max(sp_long, default=0), rar=rarcount))
pickle.dump(rows, open(S / "t9.pkl", "wb"))
def auc(pos, neg):
    all_ = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks = {}
    i = 0
    vals = [v for v, _ in all_]
    arr = np.array(vals, float)
    order = arr.argsort(kind="mergesort")
    rank = np.empty(len(arr))
    u, inv, cnt = np.unique(arr, return_inverse=True, return_counts=True)
    cum = np.cumsum(cnt)
    avg = cum - (cnt - 1) / 2
    rank = avg[inv]
    lab = np.array([l for _, l in all_])
    n1, n0 = lab.sum(), (1 - lab).sum()
    return (rank[lab == 1].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1)
sil = [r for r in rows if not r["of"] and not r["tf"]]
right = [r for r in sil if not r["wrong"]]
pos = [r for r in sil if r["wrong"] and r["sub"] > 0]
print("silent bars", len(sil), "right", len(right), "wrong with substitution", len(pos), "no-oldly", len([r for r in pos if r["set"] != "bench-oldly"]))
for key in ("cr", "cr2", "sp", "spl", "rar"):
    print(key, "AUC wrong vs right", round(auc([r[key] for r in pos], [r[key] for r in right]), 3), "no-oldly", round(auc([r[key] for r in pos if r["set"] != "bench-oldly"], [r[key] for r in right if r["set"] != "bench-oldly"]), 3))
    vals = sorted(r[key] for r in right)
    for q in (0.95, 0.99):
        th = vals[int(q * len(vals))]
        th = max(th, 1e-9)
        tp = sum(r[key] > th for r in pos)
        fp = sum(r[key] > th for r in right)
        by = collections.Counter(r["cause"] for r in pos if r[key] > th)
        allc = collections.Counter(r["cause"] for r in pos)
        print(f"   above right-bar q{q} (th {th:.2f}): caught {tp}/{len(pos)} false {fp}/{len(right)} precision {100*tp/max(tp+fp,1):.0f}%  by cause", {str(k)[:12]: f"{by[k]}/{allc[k]}" for k in allc})
