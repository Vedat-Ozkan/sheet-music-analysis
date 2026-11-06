import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, parse, pitches, exact, score_pdf
from barparse import align_bars
SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
c = json.loads((SCR / "scan-diag/classified.json").read_text())
truth = {}
for n in json.loads((OMR / "bench-olimpic/split.json").read_text())["inspect"]:
    truth[n] = OMR / "bench-olimpic/truth" / f"{n}.musicxml"
m = json.loads((OMR / "bench-real/manifest.json").read_text())
for e in m["pdfs"]:
    truth[e["pdf"].rsplit("/", 1)[-1][:-4]] = OMR / "bench-real" / m["pieces"][e["piece"]]["truth"]
bucket = {k.split(":", 1)[1]: {b["bar"] for b in v if b.get("first") == "clef"} for k, v in c.items()}
def unz(d):
    if d[:2] != b"PK": return d
    import zipfile, io
    z = zipfile.ZipFile(io.BytesIO(d))
    return z.read(next(x for x in z.namelist() if x.endswith((".xml", ".musicxml")) and "META" not in x))
def run(tag):
    out = {}
    for n, t in truth.items():
        d = SCR / "clefs/runs" / tag / n
        mx = list(d.glob("*.mxl"))
        r = collections.Counter()
        td = unz(t.read_bytes())
        if not mx:
            r["bars"] = len(parse(td)); r["noread"] = 1; out[n] = (r, {}); continue
        od = unz(mx[0].read_bytes())
        try:
            score_pdf(td, od, r)
            tb, ob = parse(td), parse(od)
        except ZeroDivisionError:
            r.clear(); r["bars"] = len(parse(td)); r["noread"] = 1; out[n] = (r, {}); continue
        pr = dict(align_bars(tb, ob))
        bars = {i: (pr.get(i) is not None and exact(tb[i], ob[pr[i]], True), pr.get(i) is not None and sum((pitches(tb[i]) & pitches(ob[pr[i]])).values()), sum(pitches(tb[i]).values())) for i in range(len(tb))}
        out[n] = (r, bars)
    return out
base = run(sys.argv[1])
for tag in sys.argv[2:]:
    v = run(tag)
    T0, T1, B = collections.Counter(), collections.Counter(), collections.Counter()
    rows = []
    for n in truth:
        r0, b0 = base[n]; r1, b1 = v[n]
        T0.update(r0); T1.update(r1)
        if r0["exact"] != r1["exact"] or r0["pitch_notes"] != r1["pitch_notes"] or r0["timed_notes"] != r1["timed_notes"]:
            rows.append((n.replace("olimpic-", "")[:22], r0["exact"], r1["exact"], r0["pitch_notes"], r1["pitch_notes"], r0["timed_notes"], r1["timed_notes"], r0["notes"]))
        for i in bucket.get(n, ()):
            if i in b0 and i in b1:
                B["bars"] += 1; B["e0"] += b0[i][0]; B["e1"] += b1[i][0]; B["p0"] += b0[i][1]; B["p1"] += b1[i][1]; B["n"] += b0[i][2]
    print(tag, "ALL exact", T0["exact"], "->", T1["exact"], "of", T0["bars"], "pitch", T0["pitch_notes"], "->", T1["pitch_notes"], "timed", T0["timed_notes"], "->", T1["timed_notes"], "of", T0["notes"])
    print("  27-bucket", dict(B))
    for x in rows: print("   ", x)
