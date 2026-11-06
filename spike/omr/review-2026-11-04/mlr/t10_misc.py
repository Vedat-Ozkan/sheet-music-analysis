import collections, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
from t7_key_fn import scan
ORDER_SHARP, ORDER_FLAT = "FCGDAEB", "BEADGCF"
MID = {"G2": 71, "F4": 50, "C3": 60, "C4": 57, "C1": 64, "C2": 60}
A = collections.Counter(); B = collections.Counter(); keyrows = []
kw = []
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    t0 = next(iter(tb[0].key.values()), 0) if tb and tb[0].key else 0
    o0 = next(iter(ob[0].key.values()), 0) if ob and ob[0].key else 0
    red, nat, pk = scan(data)
    nxt = None
    if o0 <= 0 and -o0 < 7:
        nxt = (o0, ORDER_FLAT[-o0])
    if o0 >= 0 and o0 < 7:
        nxt2 = (o0, ORDER_SHARP[o0])
    n_next = red.get((o0, ORDER_FLAT[-o0]), 0) if o0 <= 0 else 0
    n_next_s = red.get((o0, ORDER_SHARP[o0]), 0) if 0 <= o0 < 7 else 0
    cand = max(n_next, n_next_s)
    distinct_keys = sorted({v for p in pk for v in p})
    keyrows.append((cand, t0 != o0, stem, t0, o0, distinct_keys[:5], max(len(p) for p in pk) if pk else 0))
    # stems: one voice vs two voices per staff-bar in the truth
    clefs = {}
    for k, b in enumerate(tb):
        clefs.update(b.clef)
        st = collections.defaultdict(list)
        for e in b.events:
            if e.midis and not e.rest:
                st[(e.part, e.staff)].append(e)
        for key, es in st.items():
            two = len({e.voice for e in es}) > 1 and any(a.voice != c.voice and a.onset < c.onset + c.dur and c.onset < a.onset + a.dur for a in es for c in es)
            clef = clefs.get(key)
            mid = MID.get(f"{clef[0]}{clef[1]}") if clef else None
            viol = False
            for group, members in _groups(es) if False else [(None, [e]) for e in es]:
                pass
            singles = [e for e in es if e.beam is None and e.stem in ("up", "down")]
            viol_single = 0
            if mid is not None:
                for e in singles:
                    hi, lo = max(e.midis), min(e.midis)
                    further = (hi - mid) >= (mid - lo)
                    want = "down" if further else "up"
                    if e.stem != want and abs((hi - mid) - (mid - lo)) > 2:
                        viol_single += 1
            sameonset = len(es) > len({e.onset for e in es})
            A["staffbars"] += 1
            A["two" if two else "one"] += 1
            tag = "two" if two else "one"
            A[f"{tag} viol"] += viol_single > 0
            A[f"{tag} same onset"] += sameonset
            A[f"{tag} viol or same"] += viol_single > 0 or sameonset
            ups = {e.stem for e in es if e.stem}
            A[f"{tag} mixed stems"] += len(ups) > 1
print(dict(A))
wrong = [r for r in keyrows if r[1]]
print("bar-1 key wrong:", [(r[2][:34], r[3], r[4], "next-step redundant", r[0]) for r in wrong])
print("next-step redundant naturals >=5 among right-key PDFs:", [(r[2][:30], r[4], r[0]) for r in keyrows if not r[1] and r[0] >= 5])
print("PDFs read with >1 distinct key value:", sum(1 for r in keyrows if len(r[5]) > 1))
