import json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed/vector_ceiling")
import voices_triplets as vt
from voices_triplets import assembly, ceiling
manifest = json.loads((ceiling.BENCH / "manifest.json").read_text())["pieces"]
for stem, i, t in (("joplin-maple-leaf-rag--ms", 1, 13), ("clara-schumann-polonaise-3--ms", 1, 40)):
    piece = stem.rsplit("--", 1)[0]
    tp = ceiling.BENCH / manifest[piece]["truth"]
    st = ceiling.truth_bars(tp); timing = assembly.truth_timing(tp); rows = ceiling.read_pdf(ceiling.BENCH / "pdfs" / f"{stem}.pdf"); n = len(st)
    systems = [rows[k:k+n] for k in range(0, len(rows), n)]
    bars = [[b for s in systems for b in s[q]] for q in range(n)]
    ex = []
    for q in range(n):
        rs = [ceiling.symbols(b) for b in bars[q]]
        ex.append({tt: r for r, tt in ceiling.align(rs, st[q]) if rs[r] == st[q][tt] and st[q][tt]})
    j = 1 - i if n == 2 else 0
    print(stem, "staves", n)
    bar = sorted(bars[i][ex[i][t]], key=lambda e: e["x"])
    print(" read:", [(round(vt.head_x(e)), e["value"], e["up"]) for e in bar])
    print(" truth:", sorted((str(a), str(b)) for a, b, _ in timing[i][t][0]))
    for j in range(n):
        if j == i or t not in ex[j]: continue
        cb = bars[j][ex[j][t]]
        cols = vt.clock_columns(cb, timing[j][t][1])
        print(" clock staff", j, "cols", sorted((str(k), round(v) if abs(v) != float("inf") else v) for k, v in (cols or {}).items()))
        print(" clock truth:", sorted((str(a), str(b)) for a, b, _ in timing[j][t][0]))
        print(" clock read:", [(round(vt.head_x(e)), e["value"], e["up"]) for e in sorted(cb, key=lambda e: e["x"])])
stem, t = "joplin-maple-leaf-rag--ms", 13
tp = ceiling.BENCH / manifest["joplin-maple-leaf-rag"]["truth"]
st = ceiling.truth_bars(tp); rows = ceiling.read_pdf(ceiling.BENCH / "pdfs" / f"{stem}.pdf"); n = len(st)
systems = [rows[k:k+n] for k in range(0, len(rows), n)]
bars = [[b for s in systems for b in s[q]] for q in range(n)]
for q in range(n):
    rs = [ceiling.symbols(b) for b in bars[q]]
    r = {tt: r for r, tt in ceiling.align(rs, st[q]) if rs[r] == st[q][tt]}[t]
    print("staff", q, "space", round(sorted(bars[q][r], key=lambda e: e["x"])[0]["space"], 2))
    for e in sorted(bars[q][r], key=lambda e: e["x"]):
        print("  stem", round(e["x"], 1), "up", e["up"], "heads", [(round(m[2], 1), round(m[3], 1)) for m in e["members"]])
