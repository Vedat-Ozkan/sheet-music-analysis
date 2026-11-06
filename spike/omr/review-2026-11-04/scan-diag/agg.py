import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import score_pdf, OMR, HERE, parse, pitches
B = OMR / "bench-olimpic"
split = json.loads((B / "split.json").read_text())
old = set(json.load(open(Path(__file__).parent / "manifest40.json"))["pieces"])
rows = {}
for n in split["inspect"] + split["unseen"]:
    c = collections.Counter(); tdata = (B / "truth" / f"{n}.musicxml").read_bytes()
    r = HERE / "cache/runs/marks1" / f"bench-olimpic--{n}--scan.musicxml"
    if r.exists() and r.stat().st_size:
        score_pdf(tdata, r.read_bytes(), c)
    else:
        bars = parse(tdata); c.update(pdfs=1, failed=1, bars=len(bars), wrong=len(bars), notes=sum(sum(pitches(b).values()) for b in bars))
    rows[n] = c
def show(label, names, skip=()):
    t = collections.Counter()
    for n in names:
        t.update(rows[n])
    b, nn = t["bars"], t["notes"]
    print(f"{label:16} pdfs {t['pdfs']} bars {b} exact {100*t['exact']/b:.1f} pt {100*t['pitch_timing_bars']/b:.1f} pitch {100*t['pitch_notes']/nn:.1f} timing {100*t['timed_notes']/nn:.1f} failed {t['failed']} failbars {sum(rows[n]['bars'] for n in names if rows[n]['failed'])}")
show("old40", [n for n in rows if n in old]); show("new40", [n for n in rows if n not in old]); show("inspect", split["inspect"]); show("unseen", split["unseen"]); show("all80", list(rows))
show("nonfail80", [n for n in rows if not rows[n]['failed']])
print("inspect fails", [n[8:] for n in split["inspect"] if rows[n]["failed"]])
json.dump({n: rows[n] for n in split["inspect"]}, open(Path(__file__).parent / "marks1-inspect.json", "w"))
