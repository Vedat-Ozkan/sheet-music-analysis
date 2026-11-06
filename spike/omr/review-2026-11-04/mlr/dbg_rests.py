import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
T = collections.defaultdict(collections.Counter)
ex = []
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    pairs = align_bars(tb, ob)
    c = T[eng]
    for i, j in pairs:
        for e in tb[i].events:
            if e.rest:
                c["t_rest_hidden" if e.hidden else "t_rest_shown"] += 1
                if e.measure_rest: c["t_measure_rest"] += 1
        for e in ob[j].events:
            if e.rest:
                c["o_rest"] += 1
                if e.measure_rest: c["o_measure_rest"] += 1
        # match by (part, staff, onset) ignoring dur
        ts = collections.Counter((e.part, e.onset) for e in tb[i].events if e.rest and not e.hidden)
        tsh = collections.Counter((e.part, e.onset) for e in tb[i].events if e.rest)
        os_ = collections.Counter((e.part, e.onset) for e in ob[j].events if e.rest)
        c["m_onset"] += sum((ts & os_).values())
        c["m_onset_hidden_too"] += sum((tsh & os_).values())
        if eng == "vr" and sum((os_ - tsh).values()) >= 2 and len(ex) < 4:
            ex.append((stem, i, [(e.part, e.staff, e.voice, str(e.onset), str(e.dur), e.typ) for e in tb[i].events if e.rest], [(e.part, e.staff, e.voice, str(e.onset), str(e.dur), e.typ, e.x) for e in ob[j].events if e.rest], str(tb[i].full)))
for k, c in T.items():
    print(k, dict(c))
for e in ex:
    print(e)
