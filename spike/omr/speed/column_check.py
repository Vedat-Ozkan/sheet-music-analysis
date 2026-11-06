import collections
import itertools
import json
import sys
import warnings

warnings.filterwarnings("ignore")
from barparse import OMR, SETS, align_bars, parse, root_of, timed  # noqa: E402
from whole_bars import shaded  # noqa: E402
from pitch_causes import HERE  # noqa: E402

NEAR, FAR = 3, 25


def conflicts(bar):
    events = [e for e in bar.events if e.x is not None and e.midis]
    same_x = same_time = 0
    for a, b in itertools.combinations(events, 2):
        if (a.part, a.voice) == (b.part, b.voice):
            continue
        same_x += a.onset != b.onset and abs(a.x - b.x) <= NEAR
        same_time += a.onset == b.onset and abs(a.x - b.x) > FAR
    return same_x, same_time


def has_positions(data):
    notes = list(root_of(data).iter("note"))
    return notes and sum(1 for n in notes if n.get("default-x")) > 0.5 * len(notes)


def main():
    variant = sys.argv[1]
    sets = sys.argv[2].split(",") if len(sys.argv) > 2 else SETS
    control, c = collections.Counter(), collections.Counter()
    for name in sets:
        manifest = json.loads((OMR / name / "manifest.json").read_text())
        for piece in manifest["pieces"].values():
            data = (OMR / name / piece["truth"]).read_bytes()
            if has_positions(data):
                for bar in parse(data):
                    x, t = conflicts(bar)
                    control.update(bars=1, either=bool(x or t), same_x=bool(x), same_time=bool(t))
        for reading in sorted((HERE / "cache" / "runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece = stem.rsplit("--", 1)[0]
            if piece not in manifest["pieces"]:
                continue
            data = reading.read_bytes()
            tb, ob = parse((OMR / name / manifest["pieces"][piece]["truth"]).read_bytes()), parse(data)
            flags = shaded(data)
            for i, j in align_bars(tb, ob):
                right = timed(tb[i]) == timed(ob[j])
                x, t = conflicts(ob[j])
                group = "shaded" if j in flags else "unshaded"
                c[group, "bars"] += 1
                c[group, "right"] += right
                c[group, "fires"] += bool(x or t)
                c[group, "fires_wrong"] += bool(x or t) and not right
    print("references", dict(control), f"fires on {100 * control['either'] / (control['bars'] or 1):.2f}% of bars")
    u = lambda k: c["unshaded", k]
    print(f"unshaded bars {u('bars')}, timing wrong {u('bars') - u('right')}; fires {u('fires')}, right {u('fires_wrong')} "
          f"({100 * u('fires_wrong') / (u('fires') or 1):.1f}%), catches {100 * u('fires_wrong') / ((u('bars') - u('right')) or 1):.1f}% of silent timing errors, "
          f"false on right bars {100 * (u('fires') - u('fires_wrong')) / (u('right') or 1):.2f}%")


if __name__ == "__main__":
    main()
