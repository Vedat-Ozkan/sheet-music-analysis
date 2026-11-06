import json, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent)]
from crops import montage
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
rows = [r for r in json.load(open(S / "detail-probe1.json")) if r["kind"] == "extra" and r["stage"] == "extra_head"]
for n, r in enumerate(rows):
    r["x"] = r["x"] + r["w"] // 2; r["yy"] = r["y"] + r["h"] // 2
    r["label"] = f'{n} {r["name"][8:18]} b{r["bar"]} m{r["midi"]} {r["shape"][9:14]} g{r["grade"]}'
montage(rows, S / "m-extra.png", cols=6, size=190)
