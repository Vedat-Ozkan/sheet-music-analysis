import collections, sys, json, pickle, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import parse, align_bars, readings, SETS, F
warnings.filterwarnings("ignore")

def units(bar):
    out = []
    for e in bar.events:
        if e.rest:
            continue
        for k in set(e.marks):
            out.append((k, e))
    return out

def classify(t, o, T, rows, key):
    truth_marks = collections.defaultdict(list)
    for k, e in units(t):
        truth_marks[(k, e.onset)].append(e)
    truth_notes = collections.defaultdict(set)
    for e in t.events:
        if not e.rest:
            truth_notes[e.onset].update(e.midis)
    used = collections.Counter()
    for k, e in units(o):
        same = truth_notes.get(e.onset, set()) & set(e.midis)
        T[k]["read"] += 1
        if not same:
            T[k]["on_wrong_note"] += 1
            continue
        hits = truth_marks.get((k, e.onset), [])
        if any(set(h.midis) & set(e.midis) for h in hits):
            T[k]["true"] += 1
        elif hits:
            T[k]["true_other_note"] += 1
        else:
            T[k]["false"] += 1
            rows.append((*key, k, str(e.onset), e.part, e.staff, e.x, e.midis))
    for k, e in units(t):
        T[k]["truth"] += 1
        found = any(k2 == k and e2.onset == e.onset and set(e2.midis) & set(e.midis) for k2, e2 in units(o))
        T[k]["found"] += found

def run(variant, only=None):
    T = collections.defaultdict(collections.Counter)
    S = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    rows = []
    for name, stem, piece, eng, data, tdata in readings(variant):
        if only and not any(s in stem for s in only):
            continue
        try:
            tb, ob = parse(tdata), parse(data)
        except Exception as ex:
            print("ERR", stem, ex); continue
        for i, j in align_bars(tb, ob):
            if j is None:
                continue
            classify(tb[i], ob[j], T, rows, (name, stem, i, j))
            classify(tb[i], ob[j], S[name], [], (name, stem, i, j))
            classify(tb[i], ob[j], S["eng:" + ("scan" if name == "bench-real" else eng)], [], (name, stem, i, j))
    return T, S, rows

if __name__ == "__main__":
    v = sys.argv[1]
    only = sys.argv[2:] or None
    T, S, rows = run(v, only)
    tot = collections.Counter()
    print("kind read true other wrongnote false | truth found")
    for k in sorted(T, key=lambda k: -T[k]["false"]):
        t = T[k]; tot.update(t)
        print(k, t["read"], t["true"], t["true_other_note"], t["on_wrong_note"], t["false"], "|", t["truth"], t["found"])
    print("ALL", tot["read"], tot["true"], tot["true_other_note"], tot["on_wrong_note"], tot["false"], "|", tot["truth"], tot["found"])
    for g in sorted(S):
        c = collections.Counter()
        for k in S[g]: c.update(S[g][k])
        print(g, "read", c["read"], "true", c["true"], "other", c["true_other_note"], "wrongnote", c["on_wrong_note"], "false", c["false"], "truth", c["truth"], "found", c["found"])
    Path(__file__).with_name(f"marks_rows_{v}.pkl").write_bytes(pickle.dumps(rows))
    print("rows", len(rows), "pdfs", len({r[1] for r in rows}))
    by = collections.Counter(r[1] for r in rows)
    print(by.most_common(25))
