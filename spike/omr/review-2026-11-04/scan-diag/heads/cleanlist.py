import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.argv = ["x", "noop"]
from pathlib import Path
SD = Path("/home/kema/projects/sheet-music-plugin/spike/omr/review-2026-11-04/scan-diag")
src = (SD / "classify.py").read_text().split("def main():")[0]
exec(src)
C = HERE / "cache/runs/marks1"
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-tune2", "bench-oldly"]
out = []
tot = collections.Counter()
for s in SETS:
    m = json.loads((OMR / s / "manifest.json").read_text())
    for e in m["pdfs"]:
        stem = e["pdf"].rsplit("/", 1)[-1][:-4]
        if "scan" in stem: continue
        f = C / f"{s}--{stem}.musicxml"
        if not f.exists(): continue
        rows = classify_piece((OMR / s / m["pieces"][e["piece"]]["truth"]).read_bytes(), f.read_bytes())
        tot["pdfs"] += 1; tot["bars"] += len(rows); tot["wrong"] += sum(not r["ok"] for r in rows)
        w = [r["bar"] for r in rows if r.get("first") == "note_missing_or_extra"]
        tot["bucket"] += len(w)
        if w:
            out.append(dict(name=f"{s}--{stem}", set=s, pdf=str(OMR / s / e["pdf"]), truth=str(OMR / s / m["pieces"][e["piece"]]["truth"]), reading=str(f), bars=w, pages=e.get("pages")))
print(dict(tot), len(out), sum(o["pages"] or 1 for o in out))
Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads/clean.json").write_text(json.dumps(out))
