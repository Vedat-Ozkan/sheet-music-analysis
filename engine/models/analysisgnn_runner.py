"""Run AnalysisGNN on one score and write its raw predictions as JSON.

This file runs inside the model's own environment (.venv-agnn: PyTorch, PyG,
graphmuse from GitHub main). From the engine it imports only the note-list
module, which needs nothing beyond the standard library.

    .venv-agnn/bin/python engine/models/analysisgnn_runner.py CHECKPOINT SCORE OUT.json
    .venv-agnn/bin/python engine/models/analysisgnn_runner.py --serve CHECKPOINT   # stays loaded; see engine/draft.py

SCORE is a MusicXML file, or a note list (engine/notes.py) when its name ends in .notes.
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import partitura as pt  # noqa: E402
import torch  # noqa: E402
from analysisgnn.models.analysis import ContinualAnalysisGNN  # noqa: E402
from analysisgnn.utils.chord_representations import available_representations  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from engine import notes as note_list  # noqa: E402

# The checkpoint's Roman numeral head has more classes than the repository's decoder, so its
# output is unusable; the numeral is rebuilt from the degree, quality and inversion heads instead.
SKIP = {"romanNumeral"}
# predict() averages these heads per onset and then applies softmax to the probabilities twice
# more, which flattens them to near-uniform. The labels survive but the confidences do not.
DOUBLE_SOFTMAXED = {"quality", "inversion", "degree1", "degree2"}
ALTERS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
TOP = 3


def undo_softmax(output: torch.Tensor) -> torch.Tensor:
    """Recover a probability vector p from softmax(p), using the fact that p sums to 1."""
    logs = torch.log(output.double())
    return (logs + (1 - logs.sum(-1, keepdim=True)) / output.shape[-1]).clamp(0, 1).float()


FIFTHS = {"f": -1, "s": 1}


def score_from_notes(text: str):
    """A partitura score holding the notes, meters and measures of a note list."""
    index = note_list.decode(text)
    div = index.ppq
    part = pt.score.Part("P1", quarter_duration=div)
    signature = index.key_signature
    fifths = 0 if signature in ("", "0") else int(signature[:-1]) * FIFTHS.get(signature[-1], 0)
    part.add(pt.score.KeySignature(fifths, "major"), 0)
    start, meter = 0, None
    voices: dict[tuple[int, int], int] = {}
    pending: dict[tuple[int, int, str], object] = {}  # a tied note waiting for its continuation
    for measure in index.measures:
        if measure.meter != meter:
            meter = measure.meter
            beats, beat_type = (int(value) for value in meter.split("/"))
            part.add(pt.score.TimeSignature(beats, beat_type), start)
        length = int(measure.declared_length * div)
        part.add(pt.score.Measure(number=measure.index), start, start + length)
        for event in measure.events:
            voice = voices.setdefault((event.staff, event.layer), len(voices) + 1)
            step, accidental, octave = event.pitch[0], event.pitch[1:-1], int(event.pitch[-1])
            alter = accidental.count("#") - accidental.count("b")
            onset = start + int(event.onset * div)
            details = dict(step=step, octave=octave, alter=alter or None, voice=voice, staff=event.staff)
            if event.grace:
                part.add(pt.score.GraceNote(grace_type="acciaccatura", **details), onset, onset)
                continue
            note = pt.score.Note(**details)
            part.add(note, onset, onset + int(event.duration * div))
            key = (event.staff, event.layer, event.pitch)
            if key in pending:
                previous = pending.pop(key)
                previous.tie_next, note.tie_prev = note, previous
            if event.tied:
                pending[key] = note
        start += length
    return pt.score.Score(partlist=[part])


def note_table(score) -> np.ndarray:
    """The note array in exactly the order the model's predict() uses."""
    notes = score.note_array(
        include_time_signature=True,
        include_pitch_spelling=True,
        include_key_signature=True,
        include_staff=True,
        include_metrical_position=True,
    )
    return np.sort(notes, order=["onset_div", "pitch"])


def decode(task: str, indices: np.ndarray) -> list:
    name = "hrhythm" if task == "hrythm" else task
    if name in available_representations:
        try:
            decoded = available_representations[name].decode(indices.reshape(-1, 1))
            return [None if value is None or value != value else str(value) for value in np.array(decoded).flatten()]
        except (IndexError, ValueError):
            pass
    return [int(index) for index in indices]


def load(checkpoint: str):
    model = ContinualAnalysisGNN.load_from_checkpoint(checkpoint, map_location="cpu")
    model.eval()
    return model


def analyse(model, score_path: str, out_path: str) -> None:
    if score_path.endswith(".notes"):
        score = score_from_notes(Path(score_path).read_text())
    else:
        score = pt.load_score(score_path)
    with torch.no_grad():
        # the RNHybrid paper's pipeline smooths predictions within each beat with a trained "voter"
        voter = os.environ.get("ANALYSISGNN_VOTER")
        if voter:
            predictions = model.predict(score, aggregation_spec={"mode": "voter_consistent_beat", "voter_path": voter})
        else:
            predictions = model.predict(score)

    notes = note_table(score)
    part = score[0]
    result = {
        "notes": {
            "measure": [int(number) for number in part.measure_number_map(notes["onset_div"])],
            "offset": [float(value) for value in notes["rel_onset_div"] / notes["divs_pq"]],
            "duration": [float(value) for value in notes["duration_div"] / notes["divs_pq"]],
            "onset_quarter": [float(value) for value in notes["onset_div"] / notes["divs_pq"]],
            "staff": [int(value) for value in notes["staff"]],
            "pitch": [f"{n['step']}{ALTERS.get(int(n['alter']), '')}{int(n['octave'])}" for n in notes],
            "midi": [int(value) for value in notes["pitch"]],
        },
        "tasks": {},
    }
    for task, tensor in predictions.items():
        if not torch.is_tensor(tensor) or tensor.dim() != 2 or tensor.shape[0] != len(notes):
            continue
        # the Roman numeral head is kept only where it matches the decoder (RNHybrid: 185 classes both)
        if task in SKIP and (task not in available_representations or tensor.shape[1] != len(getattr(available_representations[task], "classList", ()))):
            continue
        # only undo what was done: newer checkpoints (RNHybrid, the analysisgnn gradio branch) return these
        # heads as plain probabilities, which undoing would wreck
        flattened = task in DOUBLE_SOFTMAXED and float((tensor.max(-1).values - tensor.min(-1).values).max()) < 0.05
        probabilities = undo_softmax(undo_softmax(tensor)) if flattened else tensor
        top = torch.topk(probabilities, k=min(TOP, probabilities.shape[1]), dim=-1)
        result["tasks"][task] = {
            "classes": int(probabilities.shape[1]),
            # per note: the best few labels with their probabilities
            "labels": [decode(task, top.indices[:, rank].cpu().numpy()) for rank in range(top.indices.shape[1])],
            "probabilities": [[round(float(p), 4) for p in top.values[:, rank]] for rank in range(top.values.shape[1])],
        }
    with open(out_path, "w") as out:
        json.dump(result, out)


def serve(checkpoint: str) -> None:
    """Load the model once, then analyse one "score_path<TAB>out_path" line at a time from stdin.
    Loading takes most of a one-off run's time, so the server keeps this process alive between drafts."""
    # Replies get their own copy of stdout; everything else written to stdout, even by C code, goes to stderr.
    replies = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    model = load(checkpoint)
    replies.write("ready\n")
    replies.flush()
    for line in sys.stdin:
        score_path, out_path = line.rstrip("\n").split("\t")
        try:
            analyse(model, score_path, out_path)
            replies.write("ok\n")
        except Exception as error:  # report and keep serving; one bad score must not stop the worker
            replies.write("error " + " ".join(f"{type(error).__name__}: {error}".split()) + "\n")
        replies.flush()


if __name__ == "__main__":
    if sys.argv[1] == "--serve":
        serve(sys.argv[2])
    else:
        analyse(load(sys.argv[1]), sys.argv[2], sys.argv[3])
