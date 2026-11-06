import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
base, new = sys.argv[1], sys.argv[2]
rows = {v: collections.defaultdict(collections.Counter) for v in (base, new)}
perpdf = {}
for name in SETS:
    man = json.loads((OMR / name / "manifest.json").read_text())
    for en in man["pdfs"]:
        stem = en["pdf"].rsplit("/", 1)[-1][:-4]
        rn = HERE / "cache/runs" / new / f"{name}--{stem}.musicxml"
        if not rn.exists() or not rn.stat().st_size:
            continue
        tdata = (OMR / name / man["pieces"][en["piece"]]["truth"]).read_bytes()
        got = {}
        for v in (base, new):
            r = HERE / "cache/runs" / v / f"{name}--{stem}.musicxml"
            c = collections.Counter()
            score_pdf(tdata, r.read_bytes(), c)
            rows[v][name].update(c); rows[v]["all"].update(c)
            got[v] = c
        perpdf[f"{name}/{stem}"] = (got[base]["exact"], got[new]["exact"], got[base]["bars"], got[base]["pitch_notes"], got[new]["pitch_notes"], got[base]["timed_notes"], got[new]["timed_notes"], got[base]["notes"])
for name in SETS + ["all"]:
    for v in (base, new):
        t = rows[v][name]
        if not t["bars"]: continue
        b, n = t["bars"], t["notes"] or 1
        print(f"{name:15} {v:8} pdfs {t['pdfs']:3} bars {b:5} exact {100*t['exact']/b:6.2f} pooled {100*t['exact_pooled']/b:6.2f} pt {100*t['pitch_timing_bars']/b:6.2f} pitch {100*t['pitch_notes']/n:6.2f} timing {100*t['timed_notes']/n:6.2f} wrong {t['wrong']} unwarned {t['wrong_unwarned']} rightshaded {t['right_but_shaded']}")
print("PDFs that moved (exact base->new, pitch, timing):")
for k, v in sorted(perpdf.items(), key=lambda kv: kv[1][1] - kv[1][0]):
    if v[0] != v[1] or v[3] != v[4] or v[5] != v[6]:
        print(f"  {k:62} exact {v[0]}->{v[1]} of {v[2]}  pitch {v[3]}->{v[4]} timing {v[5]}->{v[6]}")
