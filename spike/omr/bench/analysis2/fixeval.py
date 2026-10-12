"""usage: fixeval.py BENCHDIR RESULTS.json OUT.json : effect of tripletfix on (pitch,onset) matches; gained / regressed notes per PDF"""
import sys, json, hashlib, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from attribute2 import events2
from attribute import rx, align
import tripletfix
bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); man = json.load(open(bd / "manifest.json"))
rows = []; tot = collections.Counter()
for p in man["pdfs"]:
    key = hashlib.sha256((bd / p["pdf"]).read_bytes() + res["audiveris_install"].encode()).hexdigest()[:32]
    omrp = bd / "cache" / f"{key}.musicxml"
    if not omrp.exists(): continue
    T, _ = events2((bd / man["pieces"][p["piece"]]["truth"]).read_bytes())
    data = omrp.read_bytes(); O0, _ = events2(data)
    root = rx(data); before = dict(tripletfix.STATS); tripletfix.fix(root); O1, _ = events2(root)
    tk = [collections.Counter((m, 0) for m, _, _ in b) for b in T]
    pairs, _ = align([(b,) for b in tk], [(b,) for b in [collections.Counter((m, 0) for m, _, _ in b) for b in O0]])
    g = r = m0 = m1 = 0
    for i, j in pairs:
        tc = collections.Counter((m, o) for m, o, _ in T[i])
        a = tc & collections.Counter((m, o) for m, o, _ in O0[j]); b = tc & collections.Counter((m, o) for m, o, _ in O1[j])
        m0 += sum(a.values()); m1 += sum(b.values()); g += sum((b - a).values()); r += sum((a - b).values())
    tn = sum(len(b) for b in T)
    rows.append({"pdf": p["pdf"], "truth": tn, "matched_before": m0, "matched_after": m1, "gained": g, "regressed": r})
    tot.update({"truth": tn, "before": m0, "after": m1, "gained": g, "regressed": r})
print(dict(tot), "stats", tripletfix.STATS)
for x in rows:
    if x["gained"] or x["regressed"]: print(x["pdf"][-45:], x["gained"], x["regressed"], x["truth"])
json.dump({"total": dict(tot), "stats": tripletfix.STATS, "pdfs": rows}, open(sys.argv[3], "w"), indent=1)
