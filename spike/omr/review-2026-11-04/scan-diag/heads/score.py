import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, parse, pitches, exact
from barparse import align_bars, timed
from pathlib import Path
SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
c = json.loads((SCR / "scan-diag/classified.json").read_text())
items = {}
for t in ("native-inspect", "real-z1"):
    for it in json.loads((SCR / "scan-diag/items" / t / "items.json").read_text()):
        items[it["name"]] = it
bucket = {k.split(":", 1)[1]: {b["bar"] for b in v if b.get("first") == "note_missing_or_extra"} for k, v in c.items()}
def scan(tag):
    out = {}
    for d in sorted((SCR / "heads/runs" / tag).iterdir()):
        m = list(d.glob("*.mxl"))
        if not m: continue
        n = d.name
        t = parse(Path(items[n]["truth"]).read_bytes()); o = parse(m[0].read_bytes())
        pr = dict(align_bars(t, o))
        out[n] = {i: (pr.get(i) is not None and exact(t[i], o[pr[i]], True), pr.get(i) is not None and sum((pitches(t[i]) & pitches(o[pr[i]])).values()), sum(pitches(t[i]).values())) for i in range(len(t))}
    return out
base = scan(sys.argv[1])
for tag in sys.argv[2:]:
    v = scan(tag)
    T = collections.Counter(); rows = []
    for n in base:
        if n not in v: T["missing_run"] += 1; continue
        for i, (e, p, tot) in base[n].items():
            e2, p2, _ = v[n].get(i, (False, 0, tot))
            T["bars"] += 1; T["e0"] += e; T["e1"] += e2; T["p0"] += p; T["p1"] += p2; T["n"] += tot
            if i in bucket.get(n, ()):
                T["bb"] += 1; T["be0"] += e; T["be1"] += e2; T["bp0"] += p; T["bp1"] += p2; T["bn"] += tot
            if e != e2: rows.append((n[8:24], i, "+" if e2 else "-", p, p2, tot))
    print(tag, dict(T))
    print("  gained", sum(r[2] == "+" for r in rows), "lost", sum(r[2] == "-" for r in rows), [r for r in rows if r[2] == "-"][:8])
