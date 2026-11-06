import sys, collections, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.argv = ["x"]
import importlib.util
src = (Path(__file__).parent / "t4_cands.py").read_text().split("samples = []")[0]
exec(src)

def rulers_of(bar, full):
    v = voices_of(bar)
    out = []
    for k, es in v.items():
        if es[0].onset == 0 and sum(e.dur for e in es) == full and all(a.onset + a.dur == b.onset for a, b in zip(es, es[1:])) and all(e.x is not None for e in es):
            if not any(expected(e) is not None and not e.tuplet and not e.rest and expected(e) != e.dur for e in es):
                out.append((k, es))
    return out

def conservative(bar, ruler):
    k, es = ruler
    cols = sorted((e.x, e.onset) for e in es)
    moved = 0
    out = []
    supported = 0
    for e in bar.events:
        if (e.part, e.voice) == k or e.x is None:
            out.append(e); continue
        x0, t0 = min(cols, key=lambda c: abs(c[0] - e.x))
        if abs(x0 - e.x) <= 8:
            if e.onset != t0:
                moved += 1
                out.append(clone(e, onset=t0))
            else:
                supported += 1
                out.append(e)
        else:
            out.append(e)
    return out, moved, supported

def conflicts(bar):
    ev = [e for e in bar.events if e.x is not None and e.midis]
    n = 0
    for a, b in itertools.combinations(ev, 2):
        if (a.part, a.voice) != (b.part, b.voice) and a.onset != b.onset and abs(a.x - b.x) <= 3:
            n += 1
    far = 0
    for a, b in itertools.combinations(ev, 2):
        if (a.part, a.voice) != (b.part, b.voice) and a.onset == b.onset and abs(a.x - b.x) > 25:
            far += 1
    return n, far

C = collections.Counter()
det = collections.defaultdict(collections.Counter)
for name, stem, piece, eng, data, tdata in readings():
    fl = flag.get((name, stem))
    if not fl:
        continue
    tb, ob = parse(tdata), parse(data)
    if len(ob) != obars.get((name, stem)):
        continue
    for j, (of, tf, i) in sorted(fl.items()):
        bar, tr = ob[j], tb[i]
        if tf:
            continue
        base = strict(bar.events)
        want = strict(tr.events)
        shared0 = sum((base & want).values())
        tright = onsets_only(bar.events) == onsets_only(tr.events)
        n, far = conflicts(bar)
        grp = "flagged" if of else "unflagged"
        d = det[grp]
        d["bars"] += 1
        d["timing wrong"] += not tright
        if n:
            d["same-x conflict"] += 1
            d["same-x conflict & timing wrong"] += not tright
        if far:
            d["same-onset far-x"] += 1
            d["same-onset far-x & timing wrong"] += not tright
        if n or far:
            d["any"] += 1
            d["any & timing wrong"] += not tright
        if bar.full is None or base == want and of:
            continue
        rs = rulers_of(bar, bar.full)
        if not of or not rs:
            C[grp + " no ruler" if of else "unflagged skipped"] += 1
            continue
        best = None
        for r in rs:
            evs, moved, sup = conservative(bar, r)
            if moved and (best is None or sup > best[2]):
                best = (evs, moved, sup, len(r[1]))
        C["flagged with ruler"] += 1
        if best is None:
            C["ruler moves nothing"] += 1
            continue
        evs, moved, sup, rl = best
        gain = sum((strict(evs) & want).values()) - shared0
        C["applied"] += 1
        C["gain"] += gain
        C["better"] += gain > 0
        C["worse"] += gain < 0
        C["now exact"] += strict(evs) == want
        if sup >= moved:
            C["confident applied"] += 1
            C["confident gain"] += gain
            C["confident better"] += gain > 0
            C["confident worse"] += gain < 0
            C["confident exact"] += strict(evs) == want
print(dict(C))
for k, v in det.items():
    print(k, dict(v))
