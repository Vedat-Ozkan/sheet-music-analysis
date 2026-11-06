import collections, json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from barparse import OMR, parse, align_bars
RUNS = OMR / "speed/cache/runs"
base, fix = sys.argv[1], sys.argv[2]
rows = json.load(open(sys.argv[3] if len(sys.argv) > 3 else "rests_set.json"))
def keys(b):
    return collections.Counter((e.part, e.onset, e.typ) for e in b.events if e.rest and not e.hidden)
tot = collections.Counter(); per = []
for _, st, stem, eng, pages, n in rows:
    m = json.loads((OMR / st / "manifest.json").read_text())
    piece = next(p["piece"] for p in m["pdfs"] if stem + ".pdf" in p["pdf"])
    tb = parse((OMR / st / m["pieces"][piece]["truth"]).read_bytes())
    try:
        ob = parse((RUNS / base / f"{st}--{stem}.musicxml").read_bytes()); fb = parse((RUNS / fix / f"{st}--{stem}.musicxml").read_bytes())
    except FileNotFoundError:
        per.append((stem, "missing")); continue
    pb, pf = align_bars(tb, ob), align_bars(tb, fb)
    jb, jf = dict(pb), dict(pf)
    c = collections.Counter()
    for i, t in enumerate(tb):
        if i not in jb or i not in jf:
            continue
        T, B, Fx = keys(t), keys(ob[jb[i]]), keys(fb[jf[i]])
        lost = T - B
        c["lost"] += sum(lost.values())
        c["found"] += sum((lost & Fx).values())
        c["false"] += sum(((Fx - T) - B).values())
        c["regained_lost"] += sum(((T - Fx) - (T - B)).values())
    per.append((stem, eng, dict(c))); tot.update(c)
for p in per: print(p)
print("TOTAL", dict(tot))
if per:
    big = max((p for p in per if len(p) == 3), key=lambda p: p[2].get("found", 0))
    print("largest", big[0], "without it recall", (tot["found"] - big[2].get("found", 0)) / max(1, tot["lost"] - big[2].get("lost", 0)))
print("recall", tot["found"] / max(1, tot["lost"]), "false/found", tot["false"] / max(1, tot["found"]))
for v in (base, fix):
    r = json.load(open(OMR / "speed/results" / f"bench-{v}-only.json"))
    a = collections.Counter()
    for s, t in r["totals"].items():
        for k in ("pdfs", "crashed", "pages_skipped", "pitch", "pitch_onset", "bar_duration_errors"):
            if isinstance(t.get(k), (int, float)): a[k] += t[k]
    print(v, dict(a), r["wall"])
