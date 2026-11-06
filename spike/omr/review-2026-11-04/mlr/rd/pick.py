import hashlib, json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from barparse import OMR, parse
S = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr/"
worst = {stem for _, stem, _ in json.load(open(S + "probe_set.json"))}
rows = []
for name in ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]:
    m = json.loads((OMR / name / "manifest.json").read_text())
    for p in m["pdfs"]:
        stem = p["pdf"].split("/")[-1][:-4]
        if stem in worst or p["pages"] > 10:
            continue
        bars = parse((OMR / name / m["pieces"][p["piece"]]["truth"]).read_bytes())
        n = sum(e.rest and not e.hidden for b in bars for e in b.events)
        if n >= 20:
            rows.append((hashlib.sha256(stem.encode()).hexdigest(), name, stem, p["engraver"], p["pages"], n))
rows.sort()
print(len(rows))
out = rows[:20]
json.dump(out, open(S + "rd/rests_set.json", "w"), indent=0)
for r in out:
    print(r[1:])
