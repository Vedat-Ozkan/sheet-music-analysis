import collections, sys, json, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from marks_measure2 import run, show
from mx import parse, readings, OMR
base, new = sys.argv[1], sys.argv[2]
have = {tuple(p.stem.split("--", 1)) for p in (OMR / "speed/cache/runs" / new).glob("*.musicxml") if p.stat().st_size}
print("pdfs", len(have))
out = {}
for v in (base, new):
    T, G, P = run(v, stems=have)
    out[v] = (T, G, P)
    tot = collections.Counter()
    for k in T:
        tot.update(T[k])
    print(v, "ALL", dict(tot))
    for g in ("same_source", "edition"):
        c = collections.Counter()
        for k in G[g]:
            c.update(G[g][k])
        print("  ", g, "read", c["read"], "true", c["true"], "wrongnote", c["wrong_note"], "false", c["false"], "truth", c["truth"], "found", c["found"])
    print("  by kind same_source", {k: (G["same_source"][k]["false"], G["same_source"][k]["found"]) for k in sorted(G["same_source"], key=lambda x: -G["same_source"][x]["false"])})
    for g in sorted(G):
        if g.startswith("set:"):
            c = collections.Counter()
            for k in G[g]:
                c.update(G[g][k])
            print("  ", g, "false", c["false"], "found", c["found"], "truth", c["truth"])
dots = {}
for v in (base, new):
    c = collections.Counter()
    for name, stem, piece, eng, data, tdata in readings(v):
        if (name, stem) in have:
            for b in parse(data):
                for e in b.events:
                    if not e.rest:
                        c["notes"] += 1
                        c["dotted"] += e.dots
    dots[v] = c
print("dots", dots)
moved = []
for s in have:
    a, b = out[base][2].get(s), out[new][2].get(s)
    if not a or not b: continue
    if a[0].get("found", 0) != b[0].get("found", 0) or a[0].get("false", 0) != b[0].get("false", 0):
        moved.append((b[0].get("false", 0) - a[0].get("false", 0), b[0].get("found", 0) - a[0].get("found", 0), s[1], a[0].get("false", 0), a[0].get("found", 0), a[0].get("truth", 0)))
for r in sorted(moved)[:60]:
    print(r)
print("found-down", sorted(moved, key=lambda r: r[1])[:12])
