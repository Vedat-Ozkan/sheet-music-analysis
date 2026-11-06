import collections, json, subprocess, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from imgs import to_pdf
from crops import page
from PIL import ImageDraw
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r.get("sub") and "nostem" in r["sub"] and r["name"].startswith("olimpic")]
by = collections.defaultdict(list)
for r in rows:
    tr = (S / "runs/undef0" / r["name"] / "trace.txt").read_text().splitlines()
    u = [l for l in tr if l.startswith(f'UNDEF {r["sheet"]} {r["head"]} ') and "seed=true" in l]
    rem = next((l.split() for l in tr if l.startswith(f'REMOVE {r["sheet"]} {r["head"]} ')), None)
    if u and rem:
        x, y, w, h = map(int, u[0].split("stump=")[1].split("/")[0].split(","))
        hy = int(rem[7]) + int(rem[9]) / 2
        by[r["name"]].append((x, y, w, h, hy, int(rem[9]), r["bar"], r["midi"]))
out = S / "ink"; out.mkdir(exist_ok=True)
for n, cuts in by.items():
    im = page(n, 1).copy().convert("L")
    d = ImageDraw.Draw(im)
    for x, y, w, h, hy, hh, *_ in set(cuts):
        below = (y + h) - hy
        above = hy - y
        cy = hy + 0.75 * hh if below < above else hy - 0.75 * hh
        d.rectangle((x - 1, cy, x + w + 1, cy + 4), fill=255)
    to_pdf(im, out / f"{n}.pdf")
    subprocess.run([str(HERE / "trace.sh"), str(S / "runs/cut" / n), str(out / f"{n}.pdf")], env={**__import__("os").environ, "AUD": str(S / "aud3")}, stderr=subprocess.DEVNULL)
    print(n, len(cuts), sorted({c[6] for c in cuts}))
