import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OMR = HERE.parent
sys.path.insert(0, str(OMR.parents[1]))
sys.path.insert(0, str(OMR))
sys.path.insert(0, str(OMR / "bench"))
from compare import align  # noqa: E402
from engine_check import load  # noqa: E402
from engine.read_pdf import problem_spots  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from score_one import fill  # noqa: E402

VARIANT = sys.argv[1]
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]


def pitches(bar):
    counter = collections.Counter()
    for (pitch, _), count in bar.items():
        counter[pitch] += count
    return counter


def main():
    totals = collections.Counter()
    by_engraver = collections.defaultdict(collections.Counter)
    sizes, examples = collections.Counter(), []
    for name in SETS:
        manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
        for reading in sorted((HERE / "cache" / "runs" / VARIANT).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece, engraver = stem.rsplit("--", 1)
            data = reading.read_bytes()
            truth, _, _ = load((OMR / name / manifest[piece]["truth"]).read_bytes())
            omr, _, _ = load(data)
            pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
            numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
            flagged = set(problem_spots(data)[0])
            paired = {i: j for i, j in pairs}
            for i, want in enumerate(truth):
                j = paired.get(i)
                got = omr[j] if j is not None else collections.Counter()
                flag = j is not None and j < len(numbers) and numbers[j] in flagged
                if got == want:
                    state = "right, flagged" if flag else "right"
                elif pitches(got) == pitches(want):
                    state = "timing only wrong, flagged" if flag else "timing only wrong, silent"
                else:
                    state = "pitch wrong, flagged" if flag else "pitch wrong, silent"
                totals[state] += 1
                if state == "pitch wrong, silent":
                    diff = sum(((pitches(want) - pitches(got)) + (pitches(got) - pitches(want))).values())
                    sizes[min(diff, 6)] += 1
                    if len(examples) < 8 and diff <= 2:
                        examples.append((name, stem, i + 1, sorted((pitches(want) - pitches(got)).elements()), sorted((pitches(got) - pitches(want)).elements())))
                by_engraver["scan" if "scan" in engraver else engraver][state] += 1
    print("silent pitch bars by notes different (6 = 6+):", sorted(sizes.items()))
    for example in examples:
        print("  e.g.", example)
    bars = sum(totals.values())
    print(f"{VARIANT}: {bars} truth bars")
    for state, count in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {state:30} {count:5}  {count / bars:.1%}")
    for engraver, counts in sorted(by_engraver.items()):
        wrong = sum(v for k, v in counts.items() if not k.startswith("right"))
        silent = sum(v for k, v in counts.items() if k.endswith("silent"))
        print(f"  {engraver:20} bars {sum(counts.values()):5}  wrong {wrong:4}  silent {silent:4}")


main()
