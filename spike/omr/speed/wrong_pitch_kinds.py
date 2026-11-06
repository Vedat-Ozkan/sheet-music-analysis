import collections, json, sys
from pathlib import Path
HERE = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed")
OMR = HERE.parent
sys.path[:0] = [str(OMR.parents[1]), str(OMR), str(OMR / "bench")]
from compare import align
from engine_check import load, midi
from engine.read_pdf import problem_spots
from engine.score import ScoreIndex
from engine.render import load_toolkit
from score_one import fill
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]
STEPS = "CDEFGAB"
def notes(data):
    out = []
    for m in ScoreIndex(load_toolkit(data).getMEI()).measures:
        bar = []
        for e in m.events:
            if e.pitch and not e.grace:
                octave = int(e.pitch.lstrip("ABCDEFG#bx").lstrip("-") or 0) if False else int("".join(c for c in e.pitch[1:] if c.isdigit() or c == "-"))
                bar.append((e.onset, octave * 7 + STEPS.index(e.pitch[0]), midi(e.pitch)))
        out.append(bar)
    return out
def kind(dstep, dmidi):
    if dstep == 0: return "accidental"
    if abs(dstep) in (7, 14): return "octave" if dmidi % 12 == 0 else "octave+accidental"
    if abs(dstep) == 1: return "one step"
    if abs(dstep) == 2: return "two steps"
    if abs(dstep) in (12, 5, 6, 1): return "clef-like"
    return "other"
def classify(want, got):
    w, g = collections.Counter(want), collections.Counter(got)
    miss, extra = list((w - g).elements()), list((g - w).elements())
    kinds = collections.Counter()
    for m in sorted(miss):
        same = [x for x in extra if x[0] == m[0]] or extra
        if not same:
            kinds["missing"] += 1; continue
        x = min(same, key=lambda x: abs(x[1] - m[1])); extra.remove(x)
        kinds[kind(x[1] - m[1], x[2] - m[2]) + (" (same onset)" if x[0] == m[0] else " (moved)")] += 1
    kinds["extra"] += len(extra)
    return kinds, (min(m[1] for m in want) if want else 0)
def pitches(bar):
    c = collections.Counter()
    for (p, _), n in bar.items(): c[p] += n
    return c
bars = collections.Counter(); notes_by = collections.Counter(); per_piece = collections.Counter(); examples = collections.defaultdict(list)
shifts = collections.Counter(); rows = []
for name in SETS:
    manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
    for reading in sorted((HERE / "cache" / "runs" / sys.argv[1]).glob(f"{name}--*.musicxml")):
        stem = reading.stem.split("--", 1)[1]
        piece, engraver = stem.rsplit("--", 1)
        data = reading.read_bytes(); tdata = (OMR / name / manifest[piece]["truth"]).read_bytes()
        truth, _, _ = load(tdata); omr, _, _ = load(data)
        tn, on = notes(tdata), notes(data)
        pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
        numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
        flagged = set(problem_spots(data)[0]); paired = dict(pairs)
        for i, want in enumerate(truth):
            j = paired.get(i); got = omr[j] if j is not None else collections.Counter()
            flag = j is not None and j < len(numbers) and numbers[j] in flagged
            if got == want or pitches(got) == pitches(want) or flag: continue
            k, _ = classify(tn[i] if i < len(tn) else [], on[j] if j is not None and j < len(on) else [])
            if sum(v for key, v in k.items() if key not in ("missing", "extra")) == 0: continue
            top = k.most_common(1)[0][0]
            label = top.split(" (")[0]
            bars[label] += 1
            for key, v in k.items(): notes_by[key] += v
            per_piece[(stem, label)] += 1
            rows.append(f"{label}	{name}	{stem}	bar {i+1}	{dict(k)}")
            if len(examples[label]) < 6: examples[label].append(f"{name}/{stem} bar {i+1} {dict(k)}")
print("silent wrong-pitch bars by main kind:", bars.most_common())
print("notes by kind:", notes_by.most_common())
for label, ex in examples.items():
    print(label); [print("   ", e) for e in ex]
print("pieces with most bars per kind:")
for (stem, label), n in per_piece.most_common(25): print(f"  {n:3} {label:20} {stem}")

open(sys.argv[2], "w").write("\n".join(rows) + "\n")
