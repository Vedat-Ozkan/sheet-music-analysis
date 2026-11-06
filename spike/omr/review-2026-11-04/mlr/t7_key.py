import sys, collections, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
ORDER_SHARP = "FCGDAEB"
ORDER_FLAT = "BEADGCF"
def key_alter(fifths, step):
    if fifths > 0:
        return 1 if step in ORDER_SHARP[:fifths] else 0
    if fifths < 0:
        return -1 if step in ORDER_FLAT[:-fifths] else 0
    return 0
def scan(data):
    root = root_of(data)
    red = collections.Counter(); tot_nat = 0
    keys_seen = collections.Counter(); perpart = []
    for pi, part in enumerate(root.iter("part")):
        fifths = 0
        prev_bar_altered = set()
        pk = []
        for m in part.iter("measure"):
            mem = {}
            altered = set()
            for ch in m:
                if ch.tag == "attributes":
                    for k in ch.findall("key"):
                        f = k.findtext("fifths")
                        if f is not None:
                            fifths = int(f)
                            pk.append(fifths)
                elif ch.tag == "note":
                    p = ch.find("pitch")
                    if p is None:
                        continue
                    step, oc = p.findtext("step"), p.findtext("octave")
                    alter = int(round(float(p.findtext("alter") or 0)))
                    acc = ch.findtext("accidental")
                    if acc == "natural":
                        tot_nat += 1
                        if key_alter(fifths, step) == 0 and (step, oc) not in mem and step not in prev_bar_altered and not any(s == step for s, _ in mem):
                            red[(fifths, step)] += 1
                    if acc is not None or alter != key_alter(fifths, step):
                        mem[(step, oc)] = alter
                        if alter != key_alter(fifths, step):
                            altered.add(step)
            prev_bar_altered = altered
        perpart.append(pk)
    return red, tot_nat, perpart
rows = []
for name, stem, piece, eng, data, tdata in readings():
    tb, ob = parse(tdata), parse(data)
    tr = next((v for b in tb for v in b.key.values()), 0)
    orr = next((v for b in ob for v in b.key.values()), 0)
    red, nat, pk = scan(data)
    tred, tnat, tpk = scan(tdata)
    nextflat = None
    rows.append(dict(name=name, stem=stem, eng=eng, t=tr, o=orr, red=sum(red.values()), nat=nat, tred=sum(tred.values()), tnat=tnat, redtop=red.most_common(2), nbars=len(ob), pk=[len(p) for p in pk], tpk=[len(p) for p in tpk], pk0=[p[:3] for p in pk][:4]))
wrong = [r for r in rows if r["t"] != r["o"]]
print("PDFs", len(rows), "first key wrong", len(wrong))
for r in wrong:
    print(r["name"][6:], r["stem"][:38], "truth", r["t"], "read", r["o"], "redundant naturals", r["red"], "of", r["nat"], "top", r["redtop"], "truth-side red", r["tred"])
right = [r for r in rows if r["t"] == r["o"]]
red_rate = lambda r: r["red"] / max(r["nbars"], 1)
print("right-key PDFs: redundant naturals per bar, distribution:", [round(sorted(red_rate(r) for r in right)[int(len(right) * q)], 3) for q in (0.5, 0.75, 0.9, 0.95, 0.99)], "truth-file rate p95", round(sorted(r["tred"] / max(r["nbars"], 1) for r in rows)[int(len(rows) * 0.95)], 3))
print("wrong-key PDFs: rate", sorted(round(red_rate(r), 3) for r in wrong))
