import collections, hashlib, json, os, subprocess, sys, warnings, re
warnings.filterwarnings("ignore")
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path("/home/kema/projects/sheet-music-plugin")
sys.path[:0] = [str(ROOT / "spike/omr/speed"), str(ROOT), str(Path(__file__).parent)]
from engine import read_pdf as reader
from barparse import parse, timed
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
items = sorted(json.loads((S / "clean.json").read_text()), key=lambda i: hashlib.sha256(i["name"].encode()).hexdigest())[:int(sys.argv[1])]
def one(it):
    o = S / "cleantrace" / it["name"]
    if not list(o.glob("*.mxl")):
        lel = reader.uses_leland(reader.open_pdf(Path(it["pdf"]).read_bytes()))
        extra = ["-option", "org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland"] if lel else []
        subprocess.run([str(Path(__file__).parent / "trace.sh"), str(o), it["pdf"], *extra], env={**os.environ, "AUD": str(S / "aud3")}, stderr=subprocess.DEVNULL)
    m = list(o.glob("*.mxl"))
    if not m: return it["name"], "nomxl"
    a, b = parse(m[0].read_bytes()), parse(Path(it["reading"]).read_bytes())
    same = len(a) == len(b) and all(timed(x) == timed(y) for x, y in zip(a, b))
    return it["name"], same
with ThreadPoolExecutor(6) as p:
    res = dict(p.map(one, items))
(S / "cleantrace.json").write_text(json.dumps(res))
print(collections.Counter(res.values()))
