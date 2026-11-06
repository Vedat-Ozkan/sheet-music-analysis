import collections, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
C = collections.Counter(); L = collections.Counter()
DYN = re.compile(r"^(s?f+z?|p+|m[fp]|sf[zp]?|fz|rf[z]?|fp)\.?$", re.I)
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    root = root_of(data)
    for part in root.iter("part"):
        texts = [(l.findtext("text") or "").strip() for l in part.iter("lyric")]
        dyn = sum(1 for t in texts if DYN.match(t))
        words = len(texts) - dyn
        L["lyric items"] += len(texts); L["dynamic-looking lyric"] += dyn
        if words < 0.5 * max(len(texts), 1):
            L["part mostly not lyric, dynamic-looking"] += dyn
    for i, j in align_bars(tb, ob):
        def tieset(bars, k):
            c = collections.Counter()
            for e in bars[k].events:
                for m, ty in e.ties:
                    if ty == "start":
                        c[(m, e.onset)] += 1
            return c
        tt, ot = tieset(tb, i), tieset(ob, j)
        o = ob[j]
        nb = ob[j + 1] if j + 1 < len(ob) else None
        new = collections.Counter(ot)
        for e in o.events:
            have = {m for m, ty in e.ties if ty == "start"}
            if not have or len(e.midis) < 2:
                continue
            end = e.onset + e.dur
            nxt = [x for x in o.events if x.part == e.part and x.staff == e.staff and x.onset == end and x.midis]
            if not nxt and nb is not None and o.full is not None and end >= o.full:
                nxt = [x for x in nb.events if x.part == e.part and x.staff == e.staff and x.onset == 0 and x.midis]
            pool = {m for x in nxt for m in x.midis}
            for m in set(e.midis) - have:
                if m in pool:
                    new[(m, e.onset)] += 1
        C["truth"] += sum(tt.values()); C["read"] += sum(ot.values()); C["hit"] += sum((tt & ot).values())
        C["read2"] += sum(new.values()); C["hit2"] += sum((tt & new).values())
print({**C, "R": round(C["hit"] / C["truth"], 3), "P": round(C["hit"] / C["read"], 3), "R2": round(C["hit2"] / C["truth"], 3), "P2": round(C["hit2"] / C["read2"], 3), "added right": C["hit2"] - C["hit"], "added wrong": C["read2"] - C["read"] - (C["hit2"] - C["hit"])})
print(dict(L))
