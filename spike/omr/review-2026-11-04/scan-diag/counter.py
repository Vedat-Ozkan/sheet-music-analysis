import sys, json, warnings, collections, re, zipfile
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import parse, OMR, HERE, pitches
from barparse import align_bars, SEMI
from pathlib import Path
STEP = "CDEFGAB"
LINE = {("G","2"):0, ("F","4"):-12, ("C","3"):-6, ("C","4"):-8, ("G","1"):2}
def dia(m, s):
    return 7 * round((m - SEMI[s]) / 12) + STEP.index(s)
def states(bars):
    out=[]; c={}
    for b in bars: c.update(b.clef); out.append(dict(c))
    return out
def run(label, pairs_list):
    tot = collections.Counter()
    for tdata, odata in pairs_list:
        tb = parse(tdata)
        tot["bars"] += len(tb)
        if odata is None: continue
        ob = parse(odata); pairs = dict(align_bars(tb, ob)); ts, os_ = states(tb), states(ob)
        for i, j in pairs.items():
            t, o = tb[i], ob[j]
            def ons(b, shift):
                c = collections.Counter()
                for e in b.events:
                    for m, s in zip(e.midis, e.steps):
                        c[(e.staff, e.onset, dia(m, s) + shift.get(e.staff, 0))] += 1
                return c
            bad = {}
            for k, v in ts[i].items():
                o_c = os_[j].get(k, ("G", "2", None))
                if o_c[:2] != v[:2] and v[:2] in LINE and o_c[:2] in LINE:
                    bad[k[1]] = LINE[v[:2]] - LINE[o_c[:2]]
            if not bad: continue
            tot["clef_diff_bars"] += 1
            a = ons(t, {})
            before = sum((a & ons(o, {})).values()) ; after = sum((a & ons(o, bad)).values()); n = sum(a.values())
            tot["n"] += n; tot["match_before"] += before; tot["match_after"] += after
            tot["bars_all_right_before"] += before == n
            tot["bars_all_right_after"] += after == n
            tot["bars_better"] += after > before
    print(label, dict(tot))
items = json.loads(Path("items/real-z1/items.json").read_text())
run("real5", [(Path(i["truth"]).read_bytes(), Path("runs/real-z1", i["name"] + ".musicxml").read_bytes()) for i in items])
split = json.load(open(OMR / "bench-olimpic/split.json"))
L=[]
for n in split["inspect"]:
    r = Path("runs/native-inspect", n + ".musicxml")
    L.append(((OMR / "bench-olimpic/truth" / f"{n}.musicxml").read_bytes(), r.read_bytes() if r.exists() else None))
run("inspect", L)
