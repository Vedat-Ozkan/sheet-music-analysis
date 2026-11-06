import sys, collections, pickle, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
t1 = pickle.loads((S / "t1.pkl").read_bytes())
flag = collections.defaultdict(dict)
for r in t1:
    if not r.get("summary") and r["j"] is not None and r["i"] is not None:
        flag[(r["set"], r["stem"])][r["i"]] = (r["of"], r["tf"], r["j"])
T = collections.defaultdict(collections.Counter)
parts = []
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    tp = len({e.part for b in tb for e in b.events}); op = len({e.part for b in ob for e in b.events})
    tstaves = len({(e.part, e.staff) for b in tb for e in b.events}); ostaves = len({(e.part, e.staff) for b in ob for e in b.events})
    phantom = sum(1 for b in ob for p in {e.part for e in b.events} if all(e.rest for e in b.events if e.part == p))
    tphantom = sum(1 for b in tb for p in {e.part for e in b.events} if all(e.rest for e in b.events if e.part == p))
    parts.append((name, stem, eng, tp, op, tstaves, ostaves, phantom, tphantom))
    pairs = align_bars(tb, ob)
    paired = dict(pairs)
    key = "scan" if name == "bench-real" or eng == "scan" else eng if eng in ("ms", "vr", "ly", "ly-old") else "other"
    fl = flag.get((name, stem), {})
    for grp in ("all", key):
        c = T[grp]
        for i, t in enumerate(tb):
            n = sum(pitches(t).values())
            c["notes"] += n
            j = paired.get(i)
            if j is None:
                c["n unpaired bar"] += n
                c["b unpaired"] += 1
                continue
            o = ob[j]
            of = fl.get(i, (False, False, j))[0]
            tag = "flag" if of else "silent"
            tp_, op_ = pitches(t), pitches(o)
            miss = sum((tp_ - op_).values()); extra = sum((op_ - tp_).values())
            sub = min(miss, extra)
            shared_p = sum((tp_ & op_).values())
            shared_t = sum((timed(t) & timed(o)).values())
            c[f"n miss {tag}"] += miss - sub
            c[f"n subst {tag}"] += sub
            c[f"n timing {tag}"] += shared_p - shared_t
            c[f"n ok {tag}"] += shared_t
            c["b " + tag] += 1
            if timed(t) == timed(o):
                c[f"b right {tag}"] += 1
            elif tp_ == op_:
                c[f"b timing-only {tag}"] += 1
            elif extra == 0:
                c[f"b missing-only {tag}"] += 1
            elif miss == 0:
                c[f"b extra-only {tag}"] += 1
            else:
                c[f"b wrong-pitch {tag}"] += 1
    if False:
        pass
(S / "t6.pkl").write_bytes(pickle.dumps((dict(T), parts)))
for g, c in T.items():
    N = c["notes"]
    print(g, "notes", N, " ".join(f"{k.replace('n ', '')}={100*c[k]/N:.2f}" for k in sorted(c) if k.startswith("n ")))
    print("   bars", " ".join(f"{k[2:]}={c[k]}" for k in sorted(c) if k.startswith("b ")))
off = [p for p in parts if p[3] != p[4] or p[5] != p[6]]
print("PDFs with part or staff count off:", len(off), "of", len(parts), "by eng", collections.Counter(p[2] for p in off))
print("examples", [(p[1], p[3], p[4], p[5], p[6], p[7]) for p in off[:12]])
print("phantom part-bars read", sum(p[7] for p in parts), "truth", sum(p[8] for p in parts))
