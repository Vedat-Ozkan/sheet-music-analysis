import pickle, hashlib, statistics, collections, sys
from pathlib import Path
import numpy as np
S = Path(__file__).parent
samples, C, byeng, why_c, ruler_c, space_stats = pickle.loads((S / "t4.pkl").read_bytes())
print("bars with candidates ranked", len(samples), "covered", sum(s["lenient"] for s in samples), "pitch-ok bars", sum(s["pit_ok"] for s in samples), "covered|pitch-ok", sum(s["lenient"] for s in samples if s["pit_ok"]))
print("candidates per bar median", statistics.median(len(s["rows"]) for s in samples), "p90", sorted(len(s["rows"]) for s in samples)[int(0.9 * len(samples))])
print("right candidates per covered bar median", statistics.median(sum(r[1] for r in s["rows"]) for s in samples if s["lenient"]))
print("single candidate bars", sum(len(s["rows"]) == 1 for s in samples), "of which right", sum(len(s["rows"]) == 1 and s["lenient"] for s in samples))
print("random-pick precision", round(sum(sum(r[1] for r in s["rows"]) / len(s["rows"]) for s in samples) / len(samples), 3))
X = lambda s: np.array([r[0] for r in s["rows"]], float)
Y = lambda s: np.array([r[1] for r in s["rows"]], float)
def split(p): return int(hashlib.sha256(p.encode()).hexdigest(), 16) % 2
def fit(train, steps=800, lr=0.3, l2=0.01):
    n = len(train[0]["rows"][0][0])
    w = np.zeros(n)
    use = [s for s in train if s["lenient"]]
    for _ in range(steps):
        g = -l2 * w
        for s in use:
            x, y = X(s), Y(s)
            p = np.exp(x @ w - (x @ w).max()); p /= p.sum()
            g += (x * (y / y.sum())[:, None]).sum(0) - (x * p[:, None]).sum(0)
        w += lr * g / max(len(use), 1)
    return w
def ev(test, w, name):
    res = []
    for s in test:
        sc = X(s) @ w
        order = np.argsort(-sc)
        top = order[0]
        margin = float(sc[order[0]] - sc[order[1]]) if len(order) > 1 else 9.0
        p = np.exp(sc - sc.max()); p /= p.sum()
        res.append((float(p[top]), margin, bool(s["rows"][top][1]), s["lenient"], s["eng"], s["rows"][top][3]))
    return res
all_res = []
ws = []
for fold in (0, 1):
    tr = [s for s in samples if split(s["piece"]) != fold]
    te = [s for s in samples if split(s["piece"]) == fold]
    w = fit(tr)
    ws.append(w)
    all_res += ev(te, w, "all")
names = ["align", "space", "beam", "repeat"]
print("weights", [round(float(v), 2) for v in (ws[0] + ws[1])[:4] / 2])
N = len(all_res)
cov = [r for r in all_res if r[3]]
print(f"held-out: top-1 right on all {N}: {sum(r[2] for r in all_res)} ({100*sum(r[2] for r in all_res)/N:.1f}%); top-1 right on covered {len(cov)}: {sum(r[2] for r in cov)} ({100*sum(r[2] for r in cov)/max(len(cov),1):.1f}%)")
for thr in (0.3, 0.5, 0.7, 0.9, 0.97):
    sel = [r for r in all_res if r[0] >= thr]
    if sel:
        print(f"  conf>={thr}: repaired {len(sel)} right {sum(r[2] for r in sel)} precision {100*sum(r[2] for r in sel)/len(sel):.0f}%")
for i, nm in enumerate(names):
    good = 0
    tot = 0
    for s in samples:
        if not s["lenient"]:
            continue
        x = X(s)[:, i]
        top = int(np.argmax(x))
        tot += 1
        good += s["rows"][top][1]
    print(f"  clue alone, ties broken by order: {nm} top-1 on covered {good}/{tot} ({100*good/max(tot,1):.0f}%)")
byeng = collections.defaultdict(lambda: [0, 0])
for r in all_res:
    byeng[r[4]][0] += 1
    byeng[r[4]][1] += r[2]
print("by engraver top-1 right:", dict(byeng))
kinds = collections.Counter()
for r in all_res:
    for k in r[5]:
        kinds[(k, r[2])] += 1
print(sorted(kinds.items(), key=lambda kv: -kv[1])[:14])
# spacing law on right bars
for eng, rows in space_stats.items():
    if len(rows) < 200:
        continue
    by = collections.defaultdict(list)
    for d, dx, stem, j in rows:
        by[d].append(dx)
    want = [0.25, 0.5, 1.0, 2.0]
    meds = {d: statistics.median(by[d]) for d in want if len(by[d]) > 20}
    q = {d: (sorted(by[d])[len(by[d]) // 4], sorted(by[d])[3 * len(by[d]) // 4]) for d in meds}
    ratios = [round(meds[b] / meds[a], 2) for a, b in zip(want, want[1:]) if a in meds and b in meds]
    # overlap: chance a d gap beats a 2d gap
    over = []
    rng = np.random.default_rng(1)
    for a, b in zip(want, want[1:]):
        if a in meds and b in meds:
            A = rng.choice(by[a], 4000); B = rng.choice(by[b], 4000)
            over.append(round(float((A >= B).mean()), 2))
    print(eng, "median gap", {k: round(v) for k, v in meds.items()}, "IQR", {k: tuple(round(x) for x in v) for k, v in q.items()}, "doubling ratio", ratios, "P(short gap >= double gap)", over)

# absolute gates and note-level gain, top-1 by held-out logit
tops = []
for fold in (0, 1):
    te = [s for s in samples if split(s["piece"]) == fold]
    for s in te:
        sc = X(s) @ ws[fold]
        r = s["rows"][int(np.argmax(sc))]
        tops.append((r[1], r[4], r[5], r[6], r[7], s["base_al"][1], s["eng"], len(s["rows"]), s["base_sr"]))
print("top-1 applied everywhere: note gain", sum(t[1] for t in tops), "bars better", sum(t[1] > 0 for t in tops), "worse", sum(t[1] < 0 for t in tops), "same", sum(t[1] == 0 for t in tops))
for name, cond in (
    ("no misalignment left after edit", lambda t: t[4] == 0),
    ("no misalignment left, had some before", lambda t: t[4] == 0 and t[5] > 0),
    ("align>=0.5 and spacing residual<0.25", lambda t: t[2] >= 0.5 and t[3] < 0.25),
    ("no misalignment left and spacing better than before", lambda t: t[4] == 0 and t[3] < t[8]),
    ("no misalignment, had some, spacing better", lambda t: t[4] == 0 and t[5] > 0 and t[3] < t[8]),
):
    sel = [t for t in tops if cond(t)]
    if sel:
        print(f"  gate {name}: applied {len(sel)} right {sum(t[0] for t in sel)} ({100*sum(t[0] for t in sel)/len(sel):.0f}%), note gain {sum(t[1] for t in sel)}, better {sum(t[1]>0 for t in sel)} worse {sum(t[1]<0 for t in sel)}")
