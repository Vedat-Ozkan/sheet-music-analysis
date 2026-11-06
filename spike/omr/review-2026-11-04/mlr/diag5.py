import collections, json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed/vector_ceiling")
import voices_triplets as vt
from voices_triplets import assembly, ceiling
manifest = json.loads((ceiling.BENCH / "manifest.json").read_text())["pieces"]
false_rows, why, by_piece = [], collections.Counter(), collections.Counter()
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
            want, content, written = timing[i][t]
            merged = {}
            for j in range(n):
                if j == i or t not in exact[j] or sysof[j][exact[j][t]] != sysof[i][r]: continue
                c = vt.clock_columns(bars[j][exact[j][t]], timing[j][t][1])
                for time, x in (c or {}).items(): merged[time] = min(merged.get(time, float("inf")), x)
            base = vt.counter_of(vt.voices_of(bars[i][r], content)[0])
            placed, g, _ = vt.voices_of(bars[i][r], content, columns=merged or None)
            got = vt.counter_of(placed)
            trip = vt.has_triplet_length(want)
            if trip and got != want:
                ev = [e for e in bars[i][r] if "tuplet" not in e]
                stems = {e["up"] for e in ev if not e["rest"] and e["up"] is not None}
                lens = {l for _, l, _ in want if l.denominator % 3 == 0}
                c = "no group fired" if not g else "group fired, still wrong"
                c += ", mixed stems" if len(stems) > 1 else ", one stem direction"
                why[c] += 1; by_piece[pdf.stem] += 1
            if not trip and g:
                ok = got == want
                false_rows.append((pdf.stem, i, t, str(written), base == want, ok, [str(l) for _, l, _ in sorted(want)][:12], sorted(str(k) for k in merged)[:10]))
print(why); print(by_piece.most_common(10))
print(len(false_rows))
for row in false_rows[:27]: print(row)
print(collections.Counter(r[0] for r in false_rows).most_common())
