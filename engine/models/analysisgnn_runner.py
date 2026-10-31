from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from engine import read_ahead  # noqa: E402

warnings.filterwarnings("ignore")
STARTED = time.monotonic()
MODEL_FILES = Path(__file__).with_name("model-files.txt")

if sys.argv[1:2] == ["--list-files"]:
    read_ahead.record()
else:
    read_ahead.start(MODEL_FILES)

import numpy as np  # noqa: E402
import partitura as pt  # noqa: E402
import torch  # noqa: E402
from analysisgnn.models.analysis import ContinualAnalysisGNN  # noqa: E402
from analysisgnn.utils.chord_representations import available_representations  # noqa: E402

from engine import notes as note_list  # noqa: E402

SKIP = {"romanNumeral"}
DOUBLE_SOFTMAXED = {"quality", "inversion", "degree1", "degree2"}
ALTERS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
TOP = 3


def undo_softmax(output: torch.Tensor) -> torch.Tensor:
    logs = torch.log(output.double())
    return (logs + (1 - logs.sum(-1, keepdim=True)) / output.shape[-1]).clamp(0, 1).float()


FIFTHS = {"f": -1, "s": 1}


def score_from_notes(text: str):
    index = note_list.decode(text)
    div = index.ppq
    part = pt.score.Part("P1", quarter_duration=div)
    start, meter, signature = 0, None, None
    voices: dict[tuple[int, int], int] = {}
    pending: dict[tuple[int, str], tuple[object, int]] = {}
    for measure in index.measures:
        if measure.key_signature != signature:
            signature = measure.key_signature
            fifths = 0 if signature in ("", "0") else int(signature[:-1]) * FIFTHS.get(signature[-1], 0)
            part.add(pt.score.KeySignature(fifths, "major"), start)
        if measure.meter and measure.meter != meter:
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
            end = onset + int(event.duration * div)
            part.add(note, onset, end)
            key = (event.staff, event.pitch)
            held = pending.pop(key, None)
            if held and held[1] == onset:
                held[0].tie_next, note.tie_prev = note, held[0]
            if event.tied:
                pending[key] = (note, end)
        start += length
    return pt.score.Score(partlist=[part])


def note_table(score) -> np.ndarray:
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
        if task in SKIP and (task not in available_representations or tensor.shape[1] != len(getattr(available_representations[task], "classList", ()))):
            continue
        flattened = task in DOUBLE_SOFTMAXED and float((tensor.max(-1).values - tensor.min(-1).values).max()) < 0.05
        probabilities = undo_softmax(undo_softmax(tensor)) if flattened else tensor
        top = torch.topk(probabilities, k=min(TOP, probabilities.shape[1]), dim=-1)
        result["tasks"][task] = {
            "classes": int(probabilities.shape[1]),
            "labels": [decode(task, top.indices[:, rank].cpu().numpy()) for rank in range(top.indices.shape[1])],
            "probabilities": [[round(float(p), 4) for p in top.values[:, rank]] for rank in range(top.values.shape[1])],
        }
    with open(out_path, "w") as out:
        json.dump(result, out)


def serve(checkpoint: str) -> None:
    replies = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    imported = time.monotonic()
    model = load(checkpoint)
    print(json.dumps({"severity": "INFO", "message": "analysisgnn ready", "imports_s": round(imported - STARTED, 1),
                      "model_load_s": round(time.monotonic() - imported, 1), "read_ahead": read_ahead.report}), file=sys.stderr)
    replies.write("ready\n")
    replies.flush()
    for line in sys.stdin:
        score_path, out_path = line.rstrip("\n").split("\t")
        try:
            begun = time.monotonic()
            analyse(model, score_path, out_path)
            replies.write(f"ok {time.monotonic() - begun:.3f}\n")
        except Exception as error:
            replies.write("error " + " ".join(f"{type(error).__name__}: {error}".split()) + "\n")
        replies.flush()


def list_files(checkpoint: str, out_path: str) -> None:
    model = load(checkpoint)
    folder = Path(out_path).parent
    sample, result = folder / "sample.notes", folder / "sample.json"
    sample.write_text("N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: 1 C4 E4 G4 C5\n2.1: 4 C3\n")
    try:
        analyse(model, str(sample), str(result))
    except Exception:
        pass
    sample.unlink(missing_ok=True)
    result.unlink(missing_ok=True)
    read_ahead.save(Path(out_path), [checkpoint])


if __name__ == "__main__":
    if sys.argv[1] == "--list-files":
        list_files(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "--serve":
        serve(sys.argv[2])
    else:
        analyse(load(sys.argv[1]), sys.argv[2], sys.argv[3])
