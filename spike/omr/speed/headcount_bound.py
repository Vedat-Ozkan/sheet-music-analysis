import collections, json, sys
from pathlib import Path
HERE = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed")
OMR = HERE.parent
sys.path[:0] = [str(OMR.parents[1]), str(OMR), str(OMR / "bench")]
from compare import align
from engine_check import load
from engine.read_pdf import problem_spots
from engine.score import ScoreIndex
from engine.render import load_toolkit
from score_one import fill
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]
def heads(data):
    return [(sum(1 for e in m.events if e.pitch and not e.grace), sum(1 for e in m.events if e.pitch and e.grace))
            for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
def pitches(bar):
    c = collections.Counter()
    for (p, _), n in bar.items(): c[p] += n
    return c
tally = collections.Counter()
for name in SETS:
    manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
    for reading in sorted((HERE / "cache" / "runs" / sys.argv[1]).glob(f"{name}--*.musicxml")):
        stem = reading.stem.split("--", 1)[1]
        piece, engraver = stem.rsplit("--", 1)
        engraver = "scan" if "scan" in engraver else "ly" if engraver.startswith("lilypond") else engraver
        data = reading.read_bytes(); tdata = (OMR / name / manifest[piece]["truth"]).read_bytes()
        truth, _, _ = load(tdata); omr, _, _ = load(data)
        th, oh = heads(tdata), heads(data)
        pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
        numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
        flagged = set(problem_spots(data)[0]); paired = dict(pairs)
        for i, want in enumerate(truth):
            j = paired.get(i); got = omr[j] if j is not None else collections.Counter()
            flag = j is not None and j < len(numbers) and numbers[j] in flagged
            if got == want: state = "right"
            elif pitches(got) == pitches(want): state = "timing"
            else:
                miss, extra = pitches(want) - pitches(got), pitches(got) - pitches(want)
                state = "pitch:missing-only" if miss and not extra else "pitch:other"
            state += ",flagged" if flag else ",silent"
            tn, tg = th[i] if i < len(th) else (0, 0)
            on, og = oh[j] if j is not None and j < len(oh) else (0, 0)
            short_normal, short_grace = on < tn, og < tg
            catch = "normal short" if short_normal else "grace short only" if short_grace else "not short"
            for key in (state, f"{state} [{engraver}]"):
                tally[(key, catch)] += 1
keys = sorted({k for k, _ in tally})
for key in keys:
    row = {c: tally[(key, c)] for c in ("normal short", "grace short only", "not short")}
    print(f"{key:40} total {sum(row.values()):5}  " + "  ".join(f"{c} {n:4}" for c, n in row.items()))
