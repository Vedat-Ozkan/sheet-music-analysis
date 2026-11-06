import collections
import json
import sys
import warnings

warnings.filterwarnings("ignore")
from barparse import OMR, SETS, align_bars, parse, pitches, timed  # noqa: E402
from pitch_causes import HERE  # noqa: E402

sys.path[:0] = [str(OMR.parents[1])]
from engine.read_pdf import problem_spots  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402


def sounding(bar, by_part):
    c = collections.Counter()
    for e in bar.events:
        for m in e.midis:
            c[((e.part, e.staff) if by_part else None, m, e.onset, e.dur)] += 1
    return c


def rests(bar, by_part):
    return collections.Counter(((e.part, e.staff) if by_part else e.part, e.onset, e.dur)
                               for e in bar.events if e.rest and not e.hidden)


def ties(bar, by_part):
    return collections.Counter(((e.part, e.staff) if by_part else None, m, e.onset)
                               for e in bar.events for m, t in e.ties if t == "start")


def exact(t, o, by_part):
    return sounding(t, by_part) == sounding(o, by_part) and rests(t, by_part) == rests(o, by_part) \
        and ties(t, by_part) == ties(o, by_part)


def shaded(data):
    numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
    flagged = set(problem_spots(data)[0])
    return {i for i, n in enumerate(numbers) if n in flagged}


def score_pdf(tdata, data, totals):
    tb, ob = parse(tdata), parse(data)
    pairs = dict(align_bars(tb, ob))
    flags = shaded(data)
    totals["pdfs"] += 1
    totals["bars"] += len(tb)
    totals["wrong_bar_count"] += len(tb) != len(ob)
    totals["wrong_part_count"] += len({e.part for b in tb for e in b.events}) != len({e.part for b in ob for e in b.events})
    for i, t in enumerate(tb):
        j = pairs.get(i)
        notes = sum(pitches(t).values())
        totals["notes"] += notes
        if j is None:
            totals["unpaired"] += 1
            totals["wrong"] += 1
            totals["wrong_unwarned"] += 1
            continue
        o = ob[j]
        totals["pitch_notes"] += sum((pitches(t) & pitches(o)).values())
        totals["timed_notes"] += sum((timed(t) & timed(o)).values())
        totals["pitch_timing_bars"] += timed(t) == timed(o)
        pooled = exact(t, o, False)
        totals["exact_pooled"] += pooled
        strict = exact(t, o, True)
        totals["exact"] += strict
        if not pooled:
            totals["wrong"] += 1
            totals["wrong_unwarned"] += j not in flags
        elif j in flags:
            totals["right_but_shaded"] += 1


def main():
    variant = sys.argv[1]
    sets = sys.argv[2].split(",") if len(sys.argv) > 2 else SETS
    rows = {}
    for name in sets + ["all"]:
        rows[name] = collections.Counter()
    for name in sets:
        manifest = json.loads((OMR / name / "manifest.json").read_text())
        for entry in manifest["pdfs"]:
            stem = entry["pdf"].rsplit("/", 1)[-1][:-4]
            reading = HERE / "cache" / "runs" / variant / f"{name}--{stem}.musicxml"
            tdata = (OMR / name / manifest["pieces"][entry["piece"]]["truth"]).read_bytes()
            for totals in (rows[name], rows["all"]):
                if not reading.exists() or not reading.stat().st_size:
                    bars = parse(tdata)
                    totals.update(pdfs=1, failed=1, bars=len(bars), wrong=len(bars), wrong_unwarned=len(bars),
                                  notes=sum(sum(pitches(b).values()) for b in bars))
                else:
                    score_pdf(tdata, reading.read_bytes(), totals)
    print(f"{variant}: exact bars (all parts right) / pooled / pitch+timing bars | wrong unwarned | notes pitch timing | failed, wrong bar count, wrong part count")
    for name, t in rows.items():
        b, n = t["bars"] or 1, t["notes"] or 1
        print(f"{name:15} pdfs {t['pdfs']:3} bars {t['bars']:5} exact {100*t['exact']/b:5.1f} pooled {100*t['exact_pooled']/b:5.1f} "
              f"pt {100*t['pitch_timing_bars']/b:5.1f} | unwarned {100*t['wrong_unwarned']/(t['wrong'] or 1):5.1f} | "
              f"pitch {100*t['pitch_notes']/n:5.1f} timing {100*t['timed_notes']/n:5.1f} | {t['failed']} {t['wrong_bar_count']} {t['wrong_part_count']}")


if __name__ == "__main__":
    main()
