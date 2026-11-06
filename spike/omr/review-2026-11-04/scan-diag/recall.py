import sys, json, warnings, collections
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import parse, pitches
from barparse import align_bars
from pathlib import Path
def ledger(m, clef):
    if clef and clef[0] == "F": return m < 43 or m > 57
    return m < 64 or m > 77
for tag in ("native-inspect", "real-z1"):
    items = json.loads(Path(f"items/{tag}/items.json").read_text())
    S = collections.defaultdict(collections.Counter)
    for it in items:
        r = Path("runs", tag, it["name"] + ".musicxml")
        if not r.exists(): continue
        tb, ob = parse(Path(it["truth"]).read_bytes()), parse(r.read_bytes())
        pairs = dict(align_bars(tb, ob)); c = {}
        for i, t in enumerate(tb):
            c.update(t.clef)
            j = pairs.get(i)
            if j is None: continue
            left = pitches(ob[j]).copy()
            for e in t.events:
                size = len(e.midis)
                for m in e.midis:
                    hit = left[m] > 0
                    if hit: left[m] -= 1
                    cl = c.get((0, e.staff))
                    for key in (("type", "hollow" if e.typ in ("half", "whole", "breve") else "black"), ("chord", min(size, 4)), ("ledger", ledger(m, cl)), ("beamed", bool(e.beam)), ("short", e.typ in ("16th", "32nd", "64th"))):
                        S[key][hit] += 1
    print(tag)
    for k in sorted(S, key=str):
        v = S[k]; n = v[True] + v[False]
        print(" ", k, n, f"{100*v[True]/n:.1f}")
