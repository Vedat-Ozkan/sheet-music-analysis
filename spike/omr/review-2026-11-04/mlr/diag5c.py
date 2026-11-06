import collections, json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed/vector_ceiling")
import voices_triplets as vt
from voices_triplets import assembly, ceiling
manifest = json.loads((ceiling.BENCH / "manifest.json").read_text())["pieces"]
def displaced(bar):
    return any(max(m[2] for m in e["members"]) - min(m[2] for m in e["members"]) > 0.5 * e["space"] for e in bar if "tuplet" not in e)
c = collections.Counter()
for pdf in sorted((ceiling.BENCH / "pdfs").glob("*--*.pdf")):
    piece, engraver = pdf.stem.rsplit("--", 1)
    if engraver not in ("ms", "ly"): continue
    tp = ceiling.BENCH / manifest[piece]["truth"]
    st = ceiling.truth_bars(tp); timing = assembly.truth_timing(tp); rows = ceiling.read_pdf(pdf); n = len(st)
    if n == 0 or len(rows) % n or len(timing) != n: continue
    systems = [rows[k:k+n] for k in range(0, len(rows), n)]
    bars = [[b for s in systems for b in s[i]] for i in range(n)]
    sysof = [[ix for ix, s in enumerate(systems) for _ in s[i]] for i in range(n)]
    exact = []
    for i in range(n):
        rs = [ceiling.symbols(b) for b in bars[i]]
        exact.append({t: r for r, t in ceiling.align(rs, st[i]) if rs[r] == st[i][t] and st[i][t]})
    for i in range(n):
        for t, r in exact[i].items():
            want, content, _ = timing[i][t]
            merged, clocks = {}, []
            for j in range(n):
                if j == i or t not in exact[j] or sysof[j][exact[j][t]] != sysof[i][r]: continue
                cb = bars[j][exact[j][t]]
                k = vt.clock_columns(cb, timing[j][t][1])
                if k:
                    clocks.append(cb)
                    for time, x in k.items(): merged[time] = min(merged.get(time, float("inf")), x)
            base = vt.counter_of(vt.voices_of(bars[i][r], content)[0]) == want
            placed, g, _ = vt.voices_of(bars[i][r], content, columns=merged or None)
            ok = vt.counter_of(placed) == want
            d = displaced(bars[i][r]) or any(displaced(b) for b in clocks)
            if not vt.has_triplet_length(want) and g:
                c[("non-triplet fire", "worse" if base and not ok else "other", "displaced head in bar or clock" if d else "no displaced head")] += 1
print(c)
