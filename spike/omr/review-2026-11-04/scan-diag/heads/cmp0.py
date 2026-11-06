import sys, json, warnings, collections
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import parse, pitches
from barparse import align_bars, timed
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads/runs")
C = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed/cache/runs/marks1")
tag = sys.argv[1]
for d in sorted((S / tag).iterdir()):
    m = list(d.glob("*.mxl"))
    if not m: print(d.name, "nomxl"); continue
    n = d.name
    f = C / (f"bench-olimpic--{n}--scan.musicxml" if n.startswith("oli") else f"bench-real--{n}.musicxml")
    a, b = parse(m[0].read_bytes()), parse(f.read_bytes())
    same = sum(timed(x) == timed(y) for x, y in zip(a, b))
    print(n[:34], len(a), len(b), same, sum(sum(pitches(x).values()) for x in a), sum(sum(pitches(x).values()) for x in b))
