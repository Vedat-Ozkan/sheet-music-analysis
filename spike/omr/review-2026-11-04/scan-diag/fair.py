import collections, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse, pitches, rests, ties, sounding, exact
from barparse import align_bars
split = json.load(open(OMR/"bench-olimpic/split.json"))
for half in ("inspect","unseen"):
    c = collections.Counter()
    for n in split[half]:
        tb = parse((OMR/"bench-olimpic/truth"/f"{n}.musicxml").read_bytes())
        c["bars"] += len(tb)
        last = tb[-1]
        dangling = sum(ties(last, False).values())
        rp = HERE/"cache/runs/marks1"/f"bench-olimpic--{n}--scan.musicxml"
        if not (rp.exists() and rp.stat().st_size): continue
        ob = parse(rp.read_bytes()); pairs = dict(align_bars(tb, ob))
        for i, t in enumerate(tb):
            j = pairs.get(i)
            if j is None: continue
            o = ob[j]
            s = sounding(t, True) == sounding(o, True) and rests(t, True) == rests(o, True)
            ex = s and ties(t, True) == ties(o, True)
            c["exact"] += ex
            if i == len(tb) - 1:
                c["lastbars"] += 1
                c["last_with_tie"] += bool(sum(ties(t, False).values()))
                c["last_only_tie_wrong"] += (s and not ex)
            c["sounding_rest_ok"] += s
            c["sounding_ok"] += sounding(t, True) == sounding(o, True)
            c["sounding_pool_ok"] += sounding(t, False) == sounding(o, False)
    print(half, dict(c))
