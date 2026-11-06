import collections, glob, json, os, re, sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
meta = {m["n"]: m for m in json.load(open(S / "crops_meta.json"))}
answers, bad = [], []
for f in sorted(glob.glob(str(S / "crops/answers/*.json"))):
    try:
        answers.append(json.load(open(f)))
    except Exception as e:
        bad.append((os.path.basename(f), str(e)[:60]))
json.dump(answers, open(S / "crops/answers.json", "w"))
print("answers", len(answers), "unreadable", bad, "numbers", sorted(a["n"] for a in answers))
def midi(n):
    m = re.match(r"([A-G])(#{1,2}|b{1,2}|x|n)?(-?\d)", n.strip())
    if not m:
        return None
    a = {"#": 1, "##": 2, "x": 2, "b": -1, "bb": -2, "n": 0, None: 0}[m.group(2)]
    return (int(m.group(3)) + 1) * 12 + SEMI[m.group(1)] + a
rows = []
for a in answers:
    m = meta[a["n"]]
    s = json.loads((OMR / m["set"] / "manifest.json").read_text())
    tb = parse((OMR / m["set"] / s["pieces"][m["stem"].rsplit("--", 1)[0]]["truth"]).read_bytes())
    ob = parse(sorted((S / "books" / m["stem"]).glob("*.mxl"))[0].read_bytes())
    t, o = tb[m["i"]], ob[m["j"]]
    want = timed(t); draft = timed(o)
    got = collections.Counter(); ons = collections.Counter(); want_on = collections.Counter(); draft_on = collections.Counter()
    for key, evs in a["staves"].items():
        for e in evs:
            on = F(str(e[0])).limit_denominator(96)
            for p in e[1]:
                mm = midi(p)
                if mm is not None:
                    got[(mm, on)] += 1; ons[on] += 1
    for (mm, on), n in want.items():
        want_on[on] += n
    for (mm, on), n in draft.items():
        draft_on[on] += n
    rows.append(dict(n=a["n"], eng=m["eng"], stem=m["stem"], conf=a.get("confidence") or 0, exact=got == want, dexact=draft == want, on=ons == want_on, don=draft_on == want_on,
                     sv=sum((got & want).values()), sd=sum((draft & want).values()), tot=sum(want.values()), inv=sum((got - want).values()), dinv=sum((draft - want).values())))
def show(name, sel):
    if not sel:
        print(name, "none"); return
    N = len(sel); hi = [r for r in sel if r["conf"] >= 0.8]
    print(f"{name}: bars {N} exact {sum(r['exact'] for r in sel)} ({100*sum(r['exact'] for r in sel)/N:.0f}%) | draft exact {sum(r['dexact'] for r in sel)} | onsets right {sum(r['on'] for r in sel)} draft {sum(r['don'] for r in sel)} | better {sum(r['sv']>r['sd'] for r in sel)} worse {sum(r['sv']<r['sd'] for r in sel)} ({100*sum(r['sv']<r['sd'] for r in sel)/N:.0f}%) same {sum(r['sv']==r['sd'] for r in sel)} | notes right {sum(r['sv'] for r in sel)} vs draft {sum(r['sd'] for r in sel)} of {sum(r['tot'] for r in sel)} | invented {sum(r['inv'] for r in sel)} vs draft {sum(r['dinv'] for r in sel)} | conf>=0.8: {len(hi)} bars, exact {sum(r['exact'] for r in hi)} | mean conf {sum(r['conf'] for r in sel)/N:.2f}")
show("5-bar group (normal effort)", [r for r in rows if r["n"] <= 4])
show("19-bar group (low effort)", [r for r in rows if r["n"] >= 5])
show("TOTAL", rows)
for e in sorted({r["eng"] for r in rows}):
    show("  " + e, [r for r in rows if r["eng"] == e])
print("exact bars:", [(r["n"], r["eng"], r["tot"]) for r in rows if r["exact"]])
print("worst worse:", sorted(((r["sv"] - r["sd"], r["n"], r["eng"]) for r in rows))[:5])
