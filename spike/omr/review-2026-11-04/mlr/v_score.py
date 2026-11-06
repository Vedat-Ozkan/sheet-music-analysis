import collections, json, re, sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
meta = {m["n"]: m for m in json.load(open(S / "crops_meta.json"))}
ans = json.load(open(S / "crops" / "answers.json"))
def midi(n):
    m = re.match(r"([A-G])(#{1,2}|b{1,2}|x|n)?(-?\d)", n.strip())
    if not m:
        return None
    a = {"#": 1, "##": 2, "x": 2, "b": -1, "bb": -2, "n": 0, None: 0}[m.group(2)]
    return (int(m.group(3)) + 1) * 12 + SEMI[m.group(1)] + a
C = collections.Counter(); rows = []
for a in ans:
    m = meta[a["n"]]
    s = json.loads((OMR / m["set"] / "manifest.json").read_text())
    piece = m["stem"].rsplit("--", 1)[0]
    tb = parse((OMR / m["set"] / s["pieces"][piece]["truth"]).read_bytes())
    ob = parse(sorted((S / "books" / m["stem"]).glob("*.mxl"))[0].read_bytes())
    t, o = tb[m["i"]], ob[m["j"]]
    want = timed(t)
    got = collections.Counter(); ons = collections.Counter()
    for key, evs in a["staves"].items():
        for e in evs:
            on = F(str(e[0])).limit_denominator(96)
            for p in e[1]:
                mm = midi(p)
                if mm is not None:
                    got[(mm, on)] += 1
                    ons[on] += 1
    want_on = collections.Counter(); 
    for (mm, on), n in want.items():
        want_on[on] += n
    draft = timed(o); draft_on = collections.Counter()
    for (mm, on), n in draft.items():
        draft_on[on] += n
    sv, sd, tot = sum((got & want).values()), sum((draft & want).values()), sum(want.values())
    C["bars"] += 1
    C["vision exact"] += got == want
    C["draft exact"] += draft == want
    C["vision onsets right"] += ons == want_on
    C["draft onsets right"] += draft_on == want_on
    C["vision better"] += sv > sd
    C["vision worse"] += sv < sd
    C["vision notes"] += sv; C["draft notes"] += sd; C["truth notes"] += tot
    C["invented"] += sum((got - want).values()); C["draft invented"] += sum((draft - want).values())
    rows.append((a["n"], m["eng"], tot, sd, sv, a.get("confidence"), got == want))
print(dict(C))
print(sorted(rows, key=lambda r: -(r[5] or 0)))
