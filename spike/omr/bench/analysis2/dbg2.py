import sys, json, hashlib, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from attribute2 import events2
from attribute import rx, align
import tripletfix as F
bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); man = json.load(open(bd / "manifest.json"))
p = next(p for p in man["pdfs"] if sys.argv[3] in p["pdf"])
key = hashlib.sha256((bd / p["pdf"]).read_bytes() + res["audiveris_install"].encode()).hexdigest()[:32]
T, _ = events2((bd / man["pieces"][p["piece"]]["truth"]).read_bytes()); data = (bd / "cache" / f"{key}.musicxml").read_bytes()
O0, _ = events2(data); root = rx(data); F.fix(root); O1, _ = events2(root)
pairs, _ = align([(collections.Counter((m, 0) for m, _, _ in b),) for b in T], [(collections.Counter((m, 0) for m, _, _ in b),) for b in O0])
for i, j in pairs:
    tc = collections.Counter((m, o) for m, o, _ in T[i]); a = tc & collections.Counter((m, o) for m, o, _ in O0[j]); b = tc & collections.Counter((m, o) for m, o, _ in O1[j])
    if sum(a.values()) != sum(b.values()): print("truth bar", i + 1, "omr bar", j + 1, "before", sum(a.values()), "after", sum(b.values()), "of", len(T[i]))
i, j = pairs[0]
tc = collections.Counter((m, o) for m, o, _ in T[i]); a = tc & collections.Counter((m, o) for m, o, _ in O0[j]); b = tc & collections.Counter((m, o) for m, o, _ in O1[j])
print("gained", sorted((b - a).elements(), key=lambda x: x[1])); print("regressed", sorted((a - b).elements(), key=lambda x: x[1]))
print("T", sorted((m, str(o)) for m, o, _ in T[i] if o < 1)[:12]); print("O0", sorted((m, str(o)) for m, o, _ in O0[j] if o < 1)[:12]); print("O1", sorted((m, str(o)) for m, o, _ in O1[j] if o < 1)[:12])
