"""Run the draft model on every When in Rome piece with a local score, to find systematic errors.

    .venv/bin/python -m eval.survey [--limit N]

The minor-mode fix (docs/engineering-log.md, challenge 1) came from noticing that the draft was wrong in
a systematic way. The 12-piece evaluation set is too small to see more such patterns, so this runs the draft
on the 300-odd pieces of When in Rome that have a score file beside the analysis, leaving out the evaluation
pieces themselves, and collects the same breakdown as the evaluation: where agreement is lost, and which
label pairs make up the loss. No chat model is involved. Raw model output is cached, so a stopped run
resumes. Note that the draft model was trained on part of this corpus, so its raw accuracy here is
optimistic; the point is the pattern of errors our own post-processing adds or leaves.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from collections import Counter
from fractions import Fraction

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces

ROME = "https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/"
OUT = pieces.OUT / "survey"
FIT = 0.70  # misaligned references sit near 0.5; dense figuration can bring a correct one down to the mid 0.7s
EVALUATION = ("Well-Tempered_Clavier_I/01", "K332/1", "K545/1", "Winterreise,_D.911/05", "Preludes%2C_Op.28/20", "Preludes,_Op.28/20", "Symphony_104/1")
CATEGORIES = ("key: same tonic, other mode", "key: other tonic", "bass/inversion", "seventh", "quality", "related chord", "different chord", "no label")


def categorise(r: compare.Sounding, h: compare.Sounding | None) -> str | None:
    if h is None:
        return "no label"
    same_chord = r.root == h.root and r.tones == h.tones
    same_key = (r.tonic, r.minor) == (h.tonic, h.minor)
    if same_chord and r.bass == h.bass:
        return None if same_key else "key: same tonic, other mode" if r.tonic == h.tonic else "key: other tonic"
    if same_chord:
        return "bass/inversion"
    if r.root == h.root:
        diff = r.tones ^ h.tones
        sevenths = {(r.root + 9) % 12, (r.root + 10) % 12, (r.root + 11) % 12}
        return "seventh" if diff and diff <= sevenths and abs(len(r.tones) - len(h.tones)) == len(diff) else "quality"
    return "related chord" if len(r.tones & h.tones) >= 2 else "different chord"


def survey(folder: str) -> dict | None:
    name = folder.removeprefix("Corpus/").replace("/", "__")
    score = pieces._download(ROME + urllib.parse.quote(folder + "/score.mxl"), OUT / "scores" / f"{name}.mxl")
    text = pieces._download(ROME + urllib.parse.quote(folder + "/analysis.txt"), OUT / "labels" / f"{name}.txt").decode("utf-8", "ignore")
    index = ScoreIndex(load_toolkit(pieces.without_harmony(score)).getMEI())
    raw_path = OUT / "raw" / f"{name}.json"
    if not raw_path.exists():
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(draft.run_analysisgnn(notes.encode(index).encode(), "notes")))
    drafted = draft.build(json.loads(raw_path.read_text()), index)
    timeline = compare.Timeline(index)
    best = None
    for shift in (0, 1, -1):  # a pickup bar is numbered 0 by some sources and 1 by others
        reference = [compare.Label(l.measure + shift, l.beat, l.key, l.figure) for l in compare.from_romantext(text)]
        try:
            spans, _ = timeline.spans(reference)
        except Exception:
            continue
        fit = timeline.fit(spans)
        if best is None or fit > best[0]:
            best = (fit, reference, spans)
    if best is None or best[0] < FIT:
        return {"piece": name, "dropped": f"fit {best[0]:.2f}" if best else "unreadable"}
    _, reference, ref_spans = best
    reading = compare.from_draft(drafted)
    hyp_spans, _ = timeline.spans(reading)
    scores = compare.compare(reference, reading, index)
    # loss by category, and the label pairs behind it, in quarter notes
    labelled_ref = list(zip(ref_spans, sorted((l for l in reference if l.measure in timeline.measures), key=lambda l: (l.measure, l.beat))))
    labelled_hyp = list(zip(hyp_spans, sorted((l for l in reading if l.measure in timeline.measures), key=lambda l: (l.measure, l.beat))))
    cuts = sorted({p for (s, e, _), _ in labelled_ref + labelled_hyp for p in (s, e)})
    at = lambda spans, t: next(((c, l) for (s, e, c), l in spans if s <= t < e), (None, None))
    loss, pairs, length = Counter(), Counter(), Fraction(0)
    for s, e in zip(cuts, cuts[1:]):
        (r, rl), (h, hl) = at(labelled_ref, s), at(labelled_hyp, s)
        if r is None:
            continue
        length += e - s
        kind = categorise(r, h)
        if kind:
            loss[kind] += float(e - s)
            if hl is not None:
                pairs[f"{kind} | {rl.figure} | {hl.figure}"] += float(e - s)
    return {"piece": name, "bars": len(index.measures), "length": float(length), "fit": round(best[0], 3), "scores": scores, "loss": dict(loss), "pairs": dict(pairs)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    paths = set(pieces.rome_tree())
    local = sorted(p.rsplit("/", 1)[0] for p in paths if p.endswith("/analysis.txt") and p.rsplit("/", 1)[0] + "/score.mxl" in paths)
    folders = [f for f in local if not any(e in f for e in EVALUATION)][: args.limit]
    results_path = OUT / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    for number, folder in enumerate(folders, 1):
        if folder in results:
            continue
        try:
            results[folder] = survey(folder)
        except Exception as error:  # a file that will not load is recorded and skipped
            results[folder] = {"piece": folder, "dropped": f"{type(error).__name__}: {str(error)[:100]}"}
        done = results[folder]
        print(f"{number:4d}/{len(folders)} {done['piece'][:60]:60s} " + (f"full {done['scores']['full']:.2f} fit {done['fit']:.2f}" if "scores" in done else done["dropped"]), flush=True)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
