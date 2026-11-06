import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import score_pdf, OMR, HERE, parse, pitches
m = json.loads((OMR / "bench/manifest.json").read_text())
groups = collections.defaultdict(collections.Counter); per = {}
for e in m["pdfs"]:
    stem = e["pdf"].rsplit("/", 1)[-1][:-4]
    r = HERE / "cache/runs/marks1" / f"bench--{stem}.musicxml"
    if not r.exists(): continue
    c = collections.Counter(); td = (OMR / "bench" / m["pieces"][e["piece"]]["truth"]).read_bytes()
    try:
        score_pdf(td, r.read_bytes(), c)
    except Exception as x:
        continue
    per[stem] = c
    tag = stem.split("--")[1]
    groups[tag].update(c)
def line(l, t):
    b, n = t["bars"] or 1, t["notes"] or 1
    return f"{l:42} pdfs {t['pdfs']} bars {t['bars']} exact {100*t['exact']/b:.1f} pt {100*t['pitch_timing_bars']/b:.1f} pitch {100*t['pitch_notes']/n:.1f} timing {100*t['timed_notes']/n:.1f} notes/bar {n/b:.1f}"
for g, t in sorted(groups.items()): print(line(g, t))
scanpieces = {s.split("--")[0] for s in per if s.endswith("--scan")}
for p in sorted(scanpieces):
    for s in per:
        if s.startswith(p + "--") : print(line(s, per[s]))
for p in ("chopin-prelude-4", "mozart-k545-1"):
    for s in per:
        if s.startswith(p + "--") and ("mutopia" in s or "real-scan" in s): pass
