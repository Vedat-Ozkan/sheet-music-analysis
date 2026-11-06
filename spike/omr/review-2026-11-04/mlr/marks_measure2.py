import collections, sys, json, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from marks_walk import walk, truth_index, chord_midis, parse, align_bars, OMR
from mx import readings, SETS
EXTRA = ("breath-mark", "caesura")
EDITION = ("lilypond-mutopia", "real-scan", )

def score_pdf(tdata, data, T):
    tb, ob = parse(tdata), parse(data)
    tw, ow = collections.defaultdict(list), collections.defaultdict(list)
    for m in walk(tdata, EXTRA):
        tw[m["k"]].append(m)
    for m in walk(data, EXTRA):
        ow[m["k"]].append(m)
    rows = []
    for i, j in align_bars(tb, ob):
        if j is None:
            continue
        tm, tn = truth_index(tb[i], tw[i])
        om, on = truth_index(ob[j], ow[j])
        seen = set()
        for m in ow[j]:
            if m["grace"] or m["midi"] is None:
                continue
            cm = chord_midis(ob[j], m)
            key = (m["tag"], m["onset"], m["part"], min(cm))
            if key in seen:
                continue
            seen.add(key)
            T[m["tag"]]["read"] += 1
            if not (tn.get(m["onset"], set()) & cm):
                T[m["tag"]]["wrong_note"] += 1
            elif tm.get((m["tag"], m["onset"]), set()) & cm:
                T[m["tag"]]["true"] += 1
            elif tm.get((m["tag"], m["onset"])):
                T[m["tag"]]["other_note"] += 1
            else:
                T[m["tag"]]["false"] += 1
                rows.append((i, j, m["tag"], str(m["onset"]), m["part"], sorted(cm)))
        seen = set()
        for m in tw[i]:
            if m["grace"] or m["midi"] is None:
                continue
            cm = chord_midis(tb[i], m)
            key = (m["tag"], m["onset"], m["part"], min(cm))
            if key in seen:
                continue
            seen.add(key)
            T[m["tag"]]["truth"] += 1
            T[m["tag"]]["found"] += bool(om.get((m["tag"], m["onset"]), set()) & cm)
    return rows

def run(variant, only=None, stems=None):
    T = collections.defaultdict(collections.Counter)
    G = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    P = {}
    for name, stem, piece, eng, data, tdata in readings(variant):
        if only and not any(s in stem for s in only):
            continue
        if stems is not None and (name, stem) not in stems:
            continue
        one = collections.defaultdict(collections.Counter)
        try:
            rows = score_pdf(tdata, data, one)
        except Exception as ex:
            print("ERR", stem, ex)
            continue
        c = collections.Counter()
        for k in one:
            c.update(one[k])
        P[(name, stem)] = (dict(c), rows)
        edition = any(e in stem for e in EDITION)
        for k in one:
            T[k].update(one[k])
            G["set:" + name][k].update(one[k])
            G["eng:" + eng][k].update(one[k])
            G["edition" if edition else "same_source"][k].update(one[k])
    return T, G, P

def show(T, G, P):
    tot = collections.Counter()
    print("kind read true other wrongnote false | truth found")
    for k in sorted(T, key=lambda k: -T[k]["false"]):
        t = T[k]; tot.update(t)
        print(k, t["read"], t["true"], t["other_note"], t["wrong_note"], t["false"], "|", t["truth"], t["found"])
    print("ALL", tot["read"], tot["true"], tot["other_note"], tot["wrong_note"], tot["false"], "|", tot["truth"], tot["found"])
    for g in sorted(G):
        c = collections.Counter()
        for k in G[g]:
            c.update(G[g][k])
        print(g, "read", c["read"], "true", c["true"], "other", c["other_note"], "wrongnote", c["wrong_note"], "false", c["false"], "truth", c["truth"], "found", c["found"])
    print(sorted(((v[0].get("false", 0), s[1]) for s, v in P.items()), reverse=True)[:25])

if __name__ == "__main__":
    v = sys.argv[1]
    T, G, P = run(v, sys.argv[2:] or None)
    show(T, G, P)
    Path(__file__).with_name(f"marks2_{v}.pkl").write_bytes(pickle.dumps({k: (a, b) for k, (a, b) in P.items()}))
