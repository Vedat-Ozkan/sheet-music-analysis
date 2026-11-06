import sys
from pathlib import Path
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin")
from engine import read_pdf as r
d = Path(sys.argv[1]).read_bytes()
try:
    x = r.clean(d)
    print("clean ok", len(x))
    print("spots", len(r._problem_spots(x, timing=False)[0]))
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:300])
