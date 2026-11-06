"""Plan test on cached sma.6 readings (MusicXML only: types, dots, beams, default-x, voices).
Pre-registered in NOTES (t4 stop rule) before the first run."""
import collections, hashlib, itertools, math, pickle, random, statistics, sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
import numpy as np

S = Path(__file__).parent
t1 = pickle.loads((S / "t1.pkl").read_bytes())
flag = collections.defaultdict(dict)
obars = {}
for r in t1:
    if r.get("summary"):
        obars[(r["set"], r["stem"])] = r["obars"]
    elif r["j"] is not None and r["i"] is not None:
        flag[(r["set"], r["stem"])][r["j"]] = (r["of"], r["tf"], r["i"])

VALID = {F(n, d) for n in (1, 3, 7) for d in (1, 2, 4, 8, 16, 32, 64)} | {F(2), F(4), F(6), F(3), F(8)}

def voices_of(bar):
    v = collections.defaultdict(list)
    for e in bar.events:
        v[(e.part, e.voice)].append(e)
    for k in v:
        v[k].sort(key=lambda e: e.onset)
    return v

def clone(e, **kw):
    d = dict(e.__dict__)
    d.update(kw)
    return Ev(**d)

def expected(e):
    if e.typ not in LEN:
        return None
    return LEN[e.typ] * (2 - F(1, 2 ** e.dots))

def why(bar):
    out = set()
    for e in bar.events:
        x = expected(e)
        if x is not None and not e.tuplet and not e.rest and abs(x - e.dur) > F(1, 200):
            out.add("type!=dur")
    if bar.full is None:
        return out
    v = voices_of(bar)
    longest = collections.defaultdict(lambda: F(0))
    for k, es in v.items():
        longest[k[0]] = max(longest[k[0]], max(e.onset + e.dur for e in es))
    for p, l in longest.items():
        if l > bar.full:
            out.add("too long")
        elif l < bar.full:
            out.add("short")
    return out

def relaid(es, start):
    out, t = [], start
    for e in es:
        out.append(clone(e, onset=t))
        t += e.dur
    return out

def candidates(voice, full):
    start = voice[0].onset
    end = max(e.onset + e.dur for e in voice)
    excess = end - full
    cands = []
    if excess == 0:
        return cands
    for i, e in enumerate(voice):
        if e.tuplet or e.measure_rest:
            continue
        d = e.dur
        for name, nd in (("x2", d * 2), ("half", d / 2), ("add dot", d * F(3, 2)), ("drop dot", d * F(2, 3)), ("add 2 dots", d * F(7, 4))):
            if nd - d == -excess:
                if name == "drop dot" and not e.dots:
                    continue
                if name == "add dot" and e.dots:
                    continue
                es = list(voice)
                es[i] = clone(e, dur=nd)
                cands.append((name + (" rest" if e.rest else ""), relaid(es, start)))
        if e.rest and e.dur == excess:
            cands.append(("drop rest", relaid(voice[:i] + voice[i + 1:], start)))
        if not e.rest and e.dur == excess:
            es = voice[:i] + voice[i + 1:]
            cands.append(("to other voice", relaid(es, start) + [clone(e, voice=e.voice + "*")]))
    if excess < 0 and -excess in VALID:
        for i in range(len(voice) + 1):
            rest = Ev(voice[0].part, voice[0].staff, voice[0].voice, F(0), -excess, None, 0, True, False, False, [], [], None, None, False, None)
            cands.append(("add rest", relaid(voice[:i] + [rest] + voice[i:], start)))
    if excess > 0:
        runs = [i for i in range(len(voice) - 2) if voice[i].typ == voice[i + 1].typ == voice[i + 2].typ and voice[i].dur == voice[i + 1].dur == voice[i + 2].dur
                and not any(voice[i + k].tuplet or voice[i + k].dots for k in range(3)) and voice[i].dur * 1 == excess]
        for i in runs:
            es = list(voice)
            for k in range(3):
                es[i + k] = clone(voice[i + k], dur=voice[i + k].dur * F(2, 3), tuplet=True)
            cands.append(("triplet", relaid(es, start)))
    return cands

def beat_of(full):
    if full is None:
        return F(1)
    if (full * 2) % 3 == 0 and full * 2 >= 3 and (full * 2).denominator == 1 and full != 3:
        return F(3, 2)
    return F(1)

def beam_penalty(es, full):
    beat = beat_of(full)
    bad, groups = 0, 0
    cur = []
    for e in es:
        if e.beam in ("begin",):
            cur = [e]
        elif e.beam == "continue" and cur:
            cur.append(e)
        elif e.beam == "end" and cur:
            cur.append(e)
            groups += 1
            a = cur[0].onset
            z = cur[-1].onset + cur[-1].dur
            if a % beat != 0 and math.floor(a / beat) != math.ceil(z / beat) - 1:
                bad += 1
            if z % (beat / 2) != 0 and not any(c.tuplet for c in cur):
                bad += 0.5
            cur = []
    return bad, groups

def columns(events):
    cols = collections.defaultdict(list)
    for e in events:
        if e.x is not None:
            cols[e.onset].append(e.x)
    return sorted((t, statistics.median(x)) for t, x in cols.items())

def align_score(events):
    good = bad = 0
    ev = [e for e in events if e.x is not None]
    for a, b in itertools.combinations(ev, 2):
        if (a.part, a.voice) == (b.part, b.voice):
            continue
        dx = abs(a.x - b.x)
        if a.onset == b.onset:
            if dx <= 12:
                good += 1
            else:
                bad += 1
        else:
            first, second = (a, b) if a.onset < b.onset else (b, a)
            if second.x < first.x - 5:
                bad += 1
            elif dx <= 4:
                bad += 1
    return (good - bad) / (good + bad + 1), bad

class Space:
    def __init__(self):
        self.samples = collections.defaultdict(list)
    def add_bar(self, bar):
        cols = columns(bar.events)
        for (t1_, x1), (t2_, x2) in zip(cols, cols[1:]):
            if x2 > x1:
                self.samples[t2_ - t1_].append(x2 - x1)
    def freeze(self):
        self.t = {d: statistics.median(v) for d, v in self.samples.items() if len(v) >= 3}
    def predict(self, d):
        if d in self.t:
            return self.t[d]
        if not self.t:
            return None
        ks = sorted(self.t)
        ld = math.log2(d)
        best = min(ks, key=lambda k: abs(math.log2(k) - ld))
        return self.t[best] * (1 + 0.35 * (ld - math.log2(best)))

def space_residual(events, sp):
    cols = columns(events)
    ratios, pairs = [], []
    for (t1_, x1), (t2_, x2) in zip(cols, cols[1:]):
        p = sp.predict(t2_ - t1_)
        if p and p > 0:
            if x2 <= x1:
                return 2.0
            pairs.append((x2 - x1, p))
            ratios.append((x2 - x1) / p)
    if len(ratios) < 2:
        return 0.5
    s = statistics.median(ratios)
    return sum(abs(math.log(max(r / s, 1e-3))) for r in ratios) / len(ratios)

def pattern(es):
    return tuple((e.onset, e.dur, e.rest) for e in sorted(es, key=lambda e: e.onset))

def rep_score(new, key, k, bars, flagged):
    pat = pattern(new)
    near = 0.0
    for dist in range(1, 9):
        for kk in (k - dist, k + dist):
            if 0 <= kk < len(bars) and kk not in flagged:
                for vk, es in voices_of(bars[kk]).items():
                    if vk[0] == key[0] and pattern(es) == pat:
                        return 1.0 / (1 + 0.1 * dist)
    for vk, es in voices_of(bars[k]).items():
        if vk != key and pattern(es) == pat:
            return 0.8
    for kk in range(len(bars)):
        if kk not in flagged and abs(kk - k) > 8:
            for vk, es in voices_of(bars[kk]).items():
                if vk[0] == key[0] and pattern(es) == pat:
                    return 0.4
    return 0.0

EDITS = ["x2", "half", "add dot", "drop dot", "add 2 dots", "x2 rest", "half rest", "add dot rest", "drop dot rest", "add 2 dots rest", "drop rest", "to other voice", "add rest", "triplet"]

def onsets_only(events):
    c = collections.Counter()
    for e in events:
        for m in e.midis:
            c[e.onset] += 1
    return c

def strict(events):
    c = collections.Counter()
    for e in events:
        for m in e.midis:
            c[(m, e.onset)] += 1
    return c

# ruler
def ruler_onsets(bar, full):
    v = voices_of(bar)
    rulers = []
    for k, es in v.items():
        if es[0].onset == 0 and sum(e.dur for e in es) == full and all(a.onset + a.dur == b.onset for a, b in zip(es, es[1:])):
            if all(e.x is not None for e in es) and not any(expected(e) is not None and not e.tuplet and not e.rest and expected(e) != e.dur for e in es):
                rulers.append((len(es), k, es))
    if not rulers:
        return None
    rulers.sort(key=lambda r: -r[0])
    return rulers[0]

def apply_ruler(bar, full, ruler):
    cols = sorted((e.x, e.onset) for e in ruler[2])
    grid = F(1, 24)
    out = []
    unresolved = 0
    for e in bar.events:
        if (e.part, e.voice) == ruler[1]:
            out.append(e); continue
        if e.x is None:
            out.append(e); continue
        x0, t0 = min(cols, key=lambda c: abs(c[0] - e.x))
        if abs(x0 - e.x) <= 12:
            out.append(clone(e, onset=t0)); continue
        lo = [c for c in cols if c[0] < e.x]
        hi = [c for c in cols if c[0] > e.x]
        a = lo[-1] if lo else (0.0, F(0))
        b = hi[0] if hi else (bar.width or (a[0] + 50), full)
        frac = (e.x - a[0]) / max(b[0] - a[0], 1)
        t = a[1] + (b[1] - a[1]) * F(frac).limit_denominator(64)
        t = round(t / grid) * grid
        out.append(clone(e, onset=t))
        unresolved += 1
    return out, unresolved

samples = []
C = collections.Counter()
byeng = collections.defaultdict(collections.Counter)
why_c = collections.Counter()
ruler_c = collections.defaultdict(collections.Counter)
space_stats = collections.defaultdict(list)
for name, stem, piece, eng, data, tdata in readings():
    fl = flag.get((name, stem))
    if not fl:
        continue
    tb, ob = parse(tdata), parse(data)
    if len(ob) != obars.get((name, stem)):
        C["skipped pdf (bar count differs from ScoreIndex)"] += 1
        continue
    flagged = {j for j, (of, tf, i) in fl.items() if of}
    sp = Space()
    for j, (of, tf, i) in fl.items():
        if not of and timed(ob[j]) == timed(tb[i]):
            sp.add_bar(ob[j])
    sp.freeze()
    # spacing law on right bars
    for j, (of, tf, i) in fl.items():
        if not of and timed(ob[j]) == timed(tb[i]):
            cols = columns(ob[j].events)
            for (a, x1), (b, x2) in zip(cols, cols[1:]):
                if x2 > x1 and b - a > 0:
                    space_stats[eng].append((float(b - a), x2 - x1, stem, j))
    for j, (of, tf, i) in sorted(fl.items()):
        if not of or tf:
            continue
        bar, tr = ob[j], tb[i]
        C["flagged-only bars"] += 1
        e = byeng[eng if name != "bench-real" else "scan"]
        e["bars"] += 1
        for w in why(bar) or {"other"}:
            why_c[w] += 1
        if strict(bar.events) == strict(tr.events):
            C["already exact"] += 1; e["already exact"] += 1
            continue
        pit_ok = pitches(bar) == pitches(tr)
        C["pitch ok"] += pit_ok
        if bar.full is None or bar.full == 0:
            C["no meter"] += 1
            continue
        # ruler
        rl = ruler_onsets(bar, bar.full)
        rc = ruler_c[eng if name != "bench-real" else "scan"]
        rc["wrong bars"] += 1
        if rl:
            rc["has ruler"] += 1
            evs, un = apply_ruler(bar, bar.full, rl)
            if onsets_only(evs) == onsets_only(tr.events):
                rc["ruler onsets right"] += 1
            if strict(evs) == strict(tr.events):
                rc["ruler strict"] += 1
            if un == 0:
                rc["ruler all columns"] += 1
                if onsets_only(evs) == onsets_only(tr.events):
                    rc["ruler all columns right"] += 1
            if sum((strict(evs) & strict(tr.events)).values()) > sum((strict(bar.events) & strict(tr.events)).values()):
                rc["ruler notes better"] += 1
            elif sum((strict(evs) & strict(tr.events)).values()) < sum((strict(bar.events) & strict(tr.events)).values()):
                rc["ruler notes worse"] += 1
            rc["ruler note gain"] += sum((strict(evs) & strict(tr.events)).values()) - sum((strict(bar.events) & strict(tr.events)).values())
        v = voices_of(bar)
        parts_long = collections.defaultdict(lambda: F(0))
        for k, es in v.items():
            parts_long[k[0]] = max(parts_long[k[0]], max(x.onset + x.dur for x in es))
        bad = []
        for k, es in v.items():
            end = max(x.onset + x.dur for x in es)
            if end > bar.full or (end < bar.full and end == parts_long[k[0]]):
                bad.append(k)
        C[f"bad voices {min(len(bad),4)}"] += 1
        e[f"bad {min(len(bad),3)}"] += 1
        if not bad:
            C["no bad voice (type/dur mismatch or other)"] += 1
            continue
        lists = []
        for k in bad:
            lists.append([(n, ns, k) for n, ns in candidates(v[k], bar.full)])
        if any(not l for l in lists):
            C["a bad voice has no one-edit candidate"] += 1
            e["no candidate"] += 1
            continue
        combos = []
        tot = 1
        for l in lists:
            tot *= len(l)
        C["bars with candidates"] += 1
        e["with cand"] += 1
        if tot > 400:
            C["too many combos"] += 1
            continue
        for combo in itertools.product(*lists):
            used = {c[2] for c in combo}
            events = [x for x in bar.events if (x.part, x.voice) not in used]
            for c in combo:
                events += c[1]
            combos.append((combo, events))
        rows = []
        any_lenient = any_strict = False
        for combo, events in combos:
            al, albad = align_score(events)
            sr = space_residual(events, sp)
            bp, gr = 0, 0
            for c in combo:
                a, g = beam_penalty(c[1], bar.full)
                bp += a; gr += g
            rep = sum(rep_score(c[1], c[2], j, ob, flagged) for c in combo) / len(combo)
            f = [al, -sr, -bp / (gr + 1), rep]
            one = [0.0] * len(EDITS)
            for c in combo:
                one[EDITS.index(c[0])] += 1.0 / len(combo)
            len_ok = onsets_only(events) == onsets_only(tr.events)
            st_ok = strict(events) == strict(tr.events)
            any_lenient |= len_ok
            any_strict |= st_ok
            rows.append((f + one, len_ok, st_ok, tuple(c[0] for c in combo), sum((strict(events) & strict(tr.events)).values()) - sum((strict(bar.events) & strict(tr.events)).values()), al, sr, albad))
        C["candidates total"] += len(rows)
        samples.append(dict(name=name, stem=stem, eng=eng if name != "bench-real" else "scan", j=j, rows=rows, lenient=any_lenient, strict=any_strict, piece=piece, pit_ok=pit_ok, nbad=len(bad), base_al=align_score(bar.events), base_sr=space_residual(bar.events, sp)))
        if any_lenient:
            C["covered lenient"] += 1; e["covered"] += 1
        if any_strict:
            C["covered strict"] += 1
(S / "t4.pkl").write_bytes(pickle.dumps((samples, dict(C), {k: dict(v) for k, v in byeng.items()}, dict(why_c), {k: dict(v) for k, v in ruler_c.items()}, dict(space_stats))))
print(dict(C)); print(dict(why_c))
for k, v in byeng.items(): print(k, dict(v))
for k, v in ruler_c.items(): print("ruler", k, dict(v))
