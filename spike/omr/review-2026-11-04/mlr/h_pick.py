import hashlib, json, sys
from pathlib import Path
O = Path("/home/kema/projects/sheet-music-plugin/spike/omr")
rows = []
for s in ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]:
    m = json.loads((O / s / "manifest.json").read_text())
    for p in m["pdfs"]:
        if p["pages"] <= 5:
            rows.append((hashlib.sha256(Path(p["pdf"]).stem.encode()).hexdigest(), s, p["pdf"], p["pages"], p["engraver"]))
rows.sort()
sel = rows[:12]
print(sum(r[3] for r in sel), [r[2][5:30] + ":" + r[4] for r in sel])
json.dump([[r[1], r[2]] for r in sel], open(Path(__file__).parent / "h_set.json", "w"))
