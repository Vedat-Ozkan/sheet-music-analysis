import sys, json, time
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin")
from pathlib import Path
from engine import read_pdf as r
pdf = Path(sys.argv[1])
aud = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/aud-pitch39/bin/Audiveris"
t = time.time()
try:
    x = r.read_pdf(pdf.read_bytes(), aud)
    print(pdf.name, "OK", len(x.musicxml), x.skipped, [{k: p.get(k) for k in ("setting", "outcome", "problems", "exit_code", "seconds", "pages_done", "invalid_pages")} for p in x.passes])
except Exception as e:
    print(pdf.name, "EXC", type(e).__name__, str(e)[:200], [{k: p.get(k) for k in ("setting", "outcome", "problems", "exit_code", "seconds", "pages_done", "invalid_pages")} for p in getattr(e, "passes", [])])
print(round(time.time() - t))
