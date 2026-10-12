import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from attribute import rx
import tripletfix as F
bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); man = json.load(open(bd / "manifest.json"))
p = next(p for p in man["pdfs"] if sys.argv[3] in p["pdf"])
key = hashlib.sha256((bd / p["pdf"]).read_bytes() + res["audiveris_install"].encode()).hexdigest()[:32]
root = rx((bd / "cache" / f"{key}.musicxml").read_bytes())
orig = F.ET.Element
import itertools
old = F._candidates
def spy(evs):
    r = old(evs); print("  cands", r, "of", len(evs)); return r
F._candidates = spy
F.fix(root); print(F.STATS)
root = rx((bd / "cache" / f"{key}.musicxml").read_bytes())
part = list(root.iter("part"))[1]; m = part.findall("measure")[2]
for key2, evs in F._events(m).items():
    if len(evs) == 18:
        for e in evs[:10]: print([ (c.tag, c.text) for c in e[0] if c.tag in ("type","beam","dot","time-modification","duration","rest")], len(e))
        break
print([ (F._beam(e), e[0].findtext("duration"), len(e), e[0].find("rest") is not None) for e in evs])
print(F._candidates(evs))
