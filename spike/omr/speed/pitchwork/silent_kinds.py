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
def pitches(bar):
    c = collections.Counter()
    for (p, _), n in bar.items(): c[p] += n
    return c
def states(variant):
    out = {}
    for name in SETS:
        manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
        for reading in sorted((HERE / "cache" / "runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece, engraver = stem.rsplit("--", 1)
            data = reading.read_bytes()
            truth, _, _ = load((OMR / name / manifest[piece]["truth"]).read_bytes())
            omr, _, _ = load(data)
            pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
            numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
            flagged = set(problem_spots(data)[0]); paired = dict(pairs)
            for i, want in enumerate(truth):
                j = paired.get(i); got = omr[j] if j is not None else collections.Counter()
                flag = j is not None and j < len(numbers) and numbers[j] in flagged
                out[(name, stem, i)] = (got == want, flag, pitches(want) - pitches(got), pitches(got) - pitches(want), engraver)
    return out
a, b = states(sys.argv[1]), states(sys.argv[2])
print("sample pitch repr:", next(iter(k for v in b.values() for k in v[2]), None))
kinds = collections.Counter(); low = collections.Counter(); trans = collections.Counter()
for key, (ok, flag, miss, extra, eng) in b.items():
    if ok or flag or not (miss or extra): continue
    kind = "missing only" if miss and not extra else "extra only" if extra and not miss else "both"
    kinds[kind] += 1
    trans[("old right" if a[key][0] else "old wrong", kind)] += 1
    for p in miss.elements(): low[str(p)] += 1
print(kinds); print(trans)
with open(sys.argv[3], "w") as f:
    for key, (ok, flag, miss, extra, eng) in sorted(b.items()):
        if ok or flag or not miss or extra: continue
        f.write(f"{'regression' if a[key][0] else 'old'}\t{key[0]}\t{key[1]}\tbar {key[2]+1}\tmissing {sorted(miss.elements())}\n")
print("most missed pitches:", low.most_common(25))
