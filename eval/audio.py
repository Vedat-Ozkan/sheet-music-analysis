"""Audio research gate (docs/plans/audio-input.md, phase 1): score from a recording against the real score.

    .venv/bin/python -m eval.audio --onnx DIR --work DIR [--only ASAP_FOLDER] [--calibrate RECORDING]

Needs `uv sync --group audio-research` and DIR/onnx_pipeline.py with its models (phase 0). Recordings are
MAESTRO excerpts (CC BY-NC-SA, evaluation only) fetched over HTTP Range into --work, never into the repo.
Performance time is mapped to score position with ASAP's beat annotations; --calibrate runs Chopin
Op. 28 No. 4 against log 53 with DTW instead.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import urllib.parse
from fractions import Fraction
from pathlib import Path

import numpy as np

from engine import draft, notes
from engine.comparison import Label, Timeline, compare, from_draft, from_romantext
from engine.reduce import midi
from engine.render import load_toolkit
from engine.score import PositionError, ScoreIndex
from eval import pieces
from eval.run import cached_draft

MAESTRO = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
FIT = 0.70
MAX_BARS = 64
MAX_SECONDS = 150
SONATAS = "Piano_Sonatas/Beethoven,_Ludwig_van/"
TEST_SET = (
    ("Beethoven/Piano_Sonatas/8-1", SONATAS + "Op013(Pathetique)/1"),
    ("Beethoven/Piano_Sonatas/24-1_no_repeat", SONATAS + "Op078/1"),
    ("Beethoven/Piano_Sonatas/26-1_no_repeat", SONATAS + "Op081a(Les_Adieux)/1"),
    ("Beethoven/Piano_Sonatas/30-1", SONATAS + "Op109/1"),
    ("Beethoven/Piano_Sonatas/17-1_no_repeat", SONATAS + "Op031_No2/1"),
    ("Beethoven/Piano_Sonatas/18-1", SONATAS + "Op031_No3/1"),
    ("Beethoven/Piano_Sonatas/9-3", SONATAS + "Op014_No1/3"),
    ("Beethoven/Piano_Sonatas/28-1", SONATAS + "Op101/1"),
    ("Beethoven/Piano_Sonatas/4-1", SONATAS + "Op007/1"),
    ("Beethoven/Piano_Sonatas/16-2", SONATAS + "Op031_No1/2"),
    ("Beethoven/Piano_Sonatas/16-1", SONATAS + "Op031_No1/1"),
    ("Beethoven/Piano_Sonatas/24-2", SONATAS + "Op078/2"),
    ("Beethoven/Piano_Sonatas/3-2", SONATAS + "Op002_No3/2"),
    ("Beethoven/Piano_Sonatas/22-1", SONATAS + "Op054/1"),
    ("Beethoven/Piano_Sonatas/27-1", SONATAS + "Op090/1"),
    ("Mozart/Piano_Sonatas/12-1", "Piano_Sonatas/Mozart,_Wolfgang_Amadeus/K332/1"),
    ("Mozart/Piano_Sonatas/12-3", "Piano_Sonatas/Mozart,_Wolfgang_Amadeus/K332/3"),
    ("Liszt/Annees_de_pelerinage_2/1_Gondoliera", "Keyboard_Other/Liszt,_Franz/Années_de_pèlerinage/S162_1_Gondoliera"),
    ("Chopin/Etudes_op_10/1", "Keyboard_Other/Chopin,_Frédéric/Études_Op.10/1"),
    ("Bach/Prelude/bwv_846", "Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01"),
)
COLUMNS = ("key", "chord", "full")


def asap(name: str) -> Path:
    path = pieces.OUT / "asap" / name
    pieces._download(pieces.ASAP + urllib.parse.quote(name), path)
    return path


def interp(x, xp, fp):
    x = np.asarray(x, float)
    y = np.interp(x, xp, fp)
    y = np.where(x < xp[0], fp[0] + (x - xp[0]) * (fp[1] - fp[0]) / (xp[1] - xp[0]), y)
    return np.where(x > xp[-1], fp[-1] + (x - xp[-1]) * (fp[-1] - fp[-2]) / (xp[-1] - xp[-2]), y)


def measure_starts(index: ScoreIndex) -> np.ndarray:
    return np.cumsum([0.0] + [float(m.length) for m in index.measures])


def ground_truth(annotation: dict, index: ScoreIndex) -> dict:
    spans = [tuple(int(x) for x in str(token).split("-")) for token in annotation["downbeats_score_map"]]
    spans = [(s[0], s[-1]) for s in spans]
    downbeats, beats = annotation["performance_downbeats"], np.array(annotation["performance_beats"])
    n = 1
    while n < min(len(spans), MAX_BARS) and spans[n][0] == spans[n - 1][1] + 1 and downbeats[n] - downbeats[0] <= MAX_SECONDS:
        n += 1
    assert len(index.measures) > spans[n - 1][1], (len(index.measures), spans[n - 1])
    starts = measure_starts(index)
    end_t = downbeats[n] if n < len(downbeats) else beats[-1] + beats[-1] - beats[-2]
    end_q = starts[spans[n - 1][1] + 1]
    times, quarters, bars = [], [], []
    for i in range(n):
        t1 = downbeats[i + 1] if i + 1 < len(downbeats) else end_t
        inside = beats[(beats >= downbeats[i]) & (beats < t1)]
        q0, length = starts[spans[i][0]], starts[spans[i][1] + 1] - starts[spans[i][0]]
        if i == 0:
            before = beats[beats < downbeats[0]]
            times += before.tolist()
            quarters += [q0 - (len(before) - j) * length / len(inside) for j in range(len(before))]
        times += inside.tolist()
        quarters += [q0 + j * length / len(inside) for j in range(len(inside))]
        bars.append((index.measures[spans[i][0]].number, downbeats[i], t1, (t1 - downbeats[i]) / len(inside)))
    return {"t": np.array(times + [end_t]), "q": np.array(quarters + [end_q]), "bars": bars, "end_t": end_t, "pickup": spans[0][0] >= 1,
            "measures": index.measures[: spans[n - 1][1] + 1], "downbeats": np.array(downbeats[:n])}


def fetch(row: dict, seconds: float, path: Path) -> None:
    if path.exists():
        return
    import soundfile
    from remotezip import RemoteZip

    with RemoteZip(MAESTRO) as archive, archive.open("maestro-v3.0.0/" + row["maestro_audio_performance"].removeprefix("{maestro}/")) as member:
        head = member.read(1 << 16)
        info = soundfile.info(io.BytesIO(head))
        start = float(row["start"]) - 0.5 if row["start"] else 0.0
        need = int(len(head) + (start + seconds) * info.samplerate * info.channels * 2)
        data = head + member.read(need - len(head))
    audio, rate = soundfile.read(io.BytesIO(data), start=int(start * info.samplerate), frames=int(seconds * info.samplerate))
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, audio, rate, subtype="PCM_16")


def transcribe(onnx: Path, audio: Path, work: Path) -> tuple[dict, dict]:
    notes_path, beats_path = work / "notes.json", work / "beats.json"
    if not beats_path.exists():
        spec = importlib.util.spec_from_file_location("onnx_pipeline", onnx / "onnx_pipeline.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main(str(audio), str(notes_path), str(beats_path))
    return json.loads(notes_path.read_text()), json.loads(beats_path.read_text())


def quantise(values: np.ndarray) -> np.ndarray:
    out = np.empty(len(values), dtype=object)
    beat = np.floor(values).astype(int)
    for b in np.unique(beat):
        sel = beat == b
        best = None
        for div in (4, 3):
            err = np.abs(np.round(values[sel] * div) / div - values[sel]).sum() + (0.01 if div == 3 else 0)
            if best is None or err < best[0]:
                best = (err, div)
        out[sel] = [Fraction(int(round(v * best[1])), best[1]) for v in values[sel]]
    return out


def build_score(transcribed: dict, tracked: dict, path: Path) -> dict:
    import partitura.musicanalysis as analysis
    from music21 import chord, clef, duration, key, layout, meter, note, pitch, stream, tie

    rows = np.array(transcribed["notes"])
    onset, offset, pitches = rows[:, 0], rows[:, 1], rows[:, 2].astype(int)
    beats, downbeats = np.array(tracked["beats"]), np.array(tracked["downbeats"])
    numerator = int(max(2, round(np.median(np.diff(np.searchsorted(beats, downbeats))))))
    anchor = float(np.searchsorted(beats, downbeats[0]))
    position = np.arange(len(beats), dtype=float)
    to_q = lambda t: interp(t, beats, position) - anchor
    bar_q = Fraction(numerator)
    qo, qf = quantise(to_q(onset)), quantise(np.maximum(to_q(offset), to_q(onset) + 0.25))
    pickup = -min(qo) if min(qo) < 0 else Fraction(0)
    assert pickup <= bar_q, pickup
    table = np.array(list(zip(onset, offset - onset, pitches)), dtype=[("onset_sec", "f4"), ("duration_sec", "f4"), ("pitch", "i4")])
    spelled = analysis.estimate_spelling(table)
    found = analysis.estimate_key(table)
    hist = np.bincount(pitches, minlength=128)[55:71]
    split = 55 + int(np.argmin(hist)) if hist.min() < hist.max() else 60

    def make_pitch(i):
        step, alter, octave = spelled[i]
        p = pitch.Pitch(step)
        if alter:
            p.accidental = pitch.Accidental(int(alter))
        p.octave = int(octave)
        return p

    score = stream.Score()
    for staff, hand in ((1, pitches >= split), (2, pitches < split)):
        groups: dict = {}
        for i in np.where(hand)[0]:
            groups.setdefault(qo[i], []).append(i)
        starts = sorted(groups)
        flat = stream.Stream()
        for n, s in enumerate(starts):
            end = max(qf[i] for i in groups[s])
            if n + 1 < len(starts):
                end = min(end, starts[n + 1])
            cut = s
            while cut < end:
                stop = min(end, (cut // bar_q + 1) * bar_q)
                chosen = [make_pitch(i) for i in sorted(groups[s], key=lambda i: pitches[i])]
                element = note.Note(chosen[0]) if len(chosen) == 1 else chord.Chord(chosen)
                element.duration = duration.Duration(stop - cut)
                if (cut, stop) != (s, end):
                    element.tie = tie.Tie("start" if cut == s else "stop" if stop == end else "continue")
                flat.insert(cut + bar_q, element)
                cut = stop
        flat.insert(0, meter.TimeSignature(f"{numerator}/4"))
        flat.insert(0, key.Key(found.rstrip("m"), "minor" if found.endswith("m") else "major"))
        flat.insert(0, clef.TrebleClef() if staff == 1 else clef.BassClef())
        measured = flat.makeMeasures()
        measured.makeRests(fillGaps=True, inPlace=True, timeRangeFromBarDuration=True)
        measured.makeTies(inPlace=True)
        bars = list(measured.getElementsByClass(stream.Measure))
        if pickup:
            first = bars[0]
            for rest in list(first.getElementsByClass(note.Rest)):
                if rest.offset < float(bar_q - pickup):
                    first.remove(rest)
            for element in list(first.notesAndRests):
                element.offset -= float(bar_q - pickup)
            first.paddingLeft = float(bar_q - pickup)
        else:
            for element in bars[0].getElementsByClass(("TimeSignature", "KeySignature", "Clef")):
                bars[1].insert(0, element)
            bars = bars[1:]
        part = stream.PartStaff()
        for j, bar in enumerate(bars):
            bar.number = j if pickup else j + 1
            part.append(bar)
        score.insert(0, part)
    score.insert(0, layout.StaffGroup(list(score.parts), symbol="brace"))
    score.write("musicxml", path)
    index = ScoreIndex(load_toolkit(path.read_bytes()).getMEI())
    grid = np.linspace(0, onset.max() + 5, 40000)
    q = to_q(grid)
    return {"index": index, "to_sec": lambda o: np.interp(np.asarray(o, float) - float(pickup), q, grid), "meter": f"{numerator}/4",
            "key": found, "split": split, "pickup_q": float(pickup), "bars_written": len(bars), "downbeats": downbeats}


def run_draft(index: ScoreIndex, raw_path: Path) -> draft.Draft:
    if not raw_path.exists():
        raw_path.write_text(json.dumps(draft.run_analysisgnn(notes.encode(index).encode(), "notes")))
    return draft.build(json.loads(raw_path.read_text()), index)


def onto_score(labels: list[Label], audio: dict, truth: dict) -> list[Label]:
    timeline = Timeline(audio["index"])
    measures = truth["measures"]
    starts = np.cumsum([0.0] + [float(m.length) for m in measures])
    placed = []
    for label in labels:
        measure = timeline.measures.get(label.measure)
        if measure is None:
            continue
        try:
            offset = timeline.starts[label.measure] + measure.offset_of(label.beat)
        except PositionError:
            continue
        seconds = float(audio["to_sec"](float(offset)))
        if seconds >= truth["end_t"]:
            continue
        q = float(interp(seconds, truth["t"], truth["q"]))
        k = int(np.searchsorted(starts, q, side="right")) - 1
        if not 0 <= k < len(measures):
            continue
        inside = min(Fraction(q - starts[k]).limit_denominator(96), measures[k].length - Fraction(1, 96))
        placed.append(Label(measures[k].number, measures[k].beat_of(inside), label.key, label.figure))
    return placed


def bars_right(truth: dict, audio: dict) -> tuple[float, int]:
    timeline = Timeline(audio["index"])
    audio_bars = {number: (float(audio["to_sec"](float(timeline.starts[number]))), float(audio["to_sec"](float(timeline.starts[number] + m.length))))
                  for number, m in timeline.measures.items()}
    best = None
    for shift in (0, 1, -1):
        right = 0
        for ordinal, (_, t0, t1, beat) in enumerate(truth["bars"], 1):
            tolerance = max(0.3, beat / 4)
            found = audio_bars.get(ordinal + shift)
            right += bool(found and abs(found[0] - t0) <= tolerance and abs(found[1] - t1) <= tolerance)
        if best is None or right > best[0]:
            best = (right, shift)
    return best[0] / len(truth["bars"]), best[1]


def expert(piece: pieces.Piece, index: ScoreIndex) -> tuple[list[Label], int, float]:
    timeline, best = Timeline(index), None
    for shift in (0, 1, -1):
        reference = [Label(l.measure + shift, l.beat, l.key, l.figure) for l in from_romantext(pieces.labels(piece))]
        try:
            fit = timeline.fit(timeline.spans(reference)[0])
        except PositionError:
            continue
        if best is None or fit > best[2]:
            best = (reference, shift, fit)
    return best


def note_f1(transcribed: dict, reference: np.ndarray, end_t: float) -> float:
    import mir_eval

    est = np.array([n for n in transcribed["notes"] if n[0] < end_t])
    ref = reference[reference[:, 0] < end_t]
    intervals = lambda a: np.stack([a[:, 0], a[:, 0] + 0.1], 1)
    hz = lambda a: mir_eval.util.midi_to_hz(a[:, 2])
    return mir_eval.transcription.precision_recall_f1_overlap(intervals(ref), hz(ref), intervals(est), hz(est), onset_tolerance=0.05, offset_ratio=None)[2]


def evaluate(piece: pieces.Piece, index: ScoreIndex, truth: dict, transcribed: dict, tracked: dict, work: Path) -> dict:
    import mir_eval

    transcribed = {"notes": [n for n in transcribed["notes"] if n[0] < truth["end_t"]]}
    audio = build_score(transcribed, tracked, work / "audio.musicxml")
    audio_labels = onto_score(from_draft(run_draft(audio["index"], work / "audio.raw.json")), audio, truth)
    score_labels = from_draft(cached_draft(piece, index))
    excerpt = ScoreIndex.from_measures(truth["measures"], index.meter, index.key_signature)
    right, shift = bars_right(truth, audio)
    tracked_downbeats = audio["downbeats"][audio["downbeats"] < truth["end_t"]]
    result = {
        "bars": len(truth["bars"]), "bars_right": round(right, 3), "bar_shift": shift, "audio_meter": audio["meter"], "audio_key": audio["key"],
        "audio_pickup_q": audio["pickup_q"], "hand_split": audio["split"], "audio_bars_written": audio["bars_written"],
        "audio_measures": len(audio["index"].measures),
        "downbeat_f": round(mir_eval.beat.f_measure(truth["downbeats"], tracked_downbeats, 0.07), 3),
        "draft_vs_draft": {c: compare(score_labels, audio_labels, excerpt)[c] for c in COLUMNS},
    }
    if piece.labels:
        reference, label_shift, fit = expert(piece, index)
        result.update(label_shift=label_shift, label_fit=round(fit, 3))
        if fit >= FIT:
            result["score_path"] = {c: compare(reference, score_labels, excerpt)[c] for c in COLUMNS}
            result["audio_path"] = {c: compare(reference, audio_labels, excerpt)[c] for c in COLUMNS}
    return result


def run_asap(folder: str, rome: str, onnx: Path, work: Path) -> dict:
    import partitura

    rows = [r for r in csv.DictReader(asap("metadata.csv").open()) if r["folder"] == folder and r["maestro_audio_performance"]]
    row = rows[0]
    annotation = json.loads(asap("asap_annotations.json").read_text())[row["midi_performance"]]
    slug = "audio-" + folder.lower().replace("/", "-")
    piece = pieces.Piece(slug, folder, pieces.ASAP + urllib.parse.quote(row["xml_score"]), pieces.ROME + urllib.parse.quote(rome + "/analysis.txt"))
    index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
    truth = ground_truth(annotation, index)
    folder_work = work / slug
    folder_work.mkdir(parents=True, exist_ok=True)
    fetch(row, truth["end_t"] + 1, folder_work / "excerpt.wav")
    transcribed, tracked = transcribe(onnx, folder_work / "excerpt.wav", folder_work)
    performed = partitura.load_performance_midi(str(asap(row["midi_performance"]))).note_array()
    reference = np.stack([performed["onset_sec"], performed["onset_sec"] + performed["duration_sec"], performed["pitch"]], 1)
    meters = [v[0] for t, v in annotation["perf_time_signatures"].items() if float(t) < truth["end_t"]]
    result = {"performance": row["midi_performance"], "meter": ", ".join(dict.fromkeys(meters)), "pickup": truth["pickup"],
              "seconds": round(truth["end_t"], 1), "note_f1": round(note_f1(transcribed, reference, truth["end_t"]), 3)}
    result.update(evaluate(piece, index, truth, transcribed, tracked, folder_work))
    return result


def dtw_truth(transcribed: dict, index: ScoreIndex) -> dict:
    import librosa

    starts = measure_starts(index)
    events = np.array([(starts[i] + float(e.onset), starts[i] + float(e.onset + e.duration), midi(e.pitch))
                       for i, m in enumerate(index.measures) for e in m.events if e.pitch and not e.grace])
    played = np.array(transcribed["notes"])

    def features(on, off, pitch, step):
        n = int(np.ceil(off.max() / step)) + 2
        grid = np.full((24, n), 1e-3)
        for a, b, p in zip(on, off, pitch):
            i, j = int(a / step), max(int(b / step), int(a / step) + 1)
            k = np.arange(i, min(j, n))
            grid[int(p) % 12, k] += 0.3
            grid[12 + int(p) % 12, k] += np.exp(-(k - i) * step / 0.3)
        return grid / (np.linalg.norm(grid, axis=0, keepdims=True) + 1e-9)

    _, path = librosa.sequence.dtw(X=features(played[:, 0], played[:, 1], played[:, 2], 0.04), Y=features(events[:, 0], events[:, 1], events[:, 2], 1 / 24), metric="cosine")
    path = path[::-1]
    seconds = np.unique(path[:, 0]) * 0.04
    quarters = np.maximum.accumulate([path[path[:, 0] * 0.04 == s, 1].mean() / 24 for s in seconds])
    to_t = lambda q: float(np.interp(q, quarters, seconds))
    bars = []
    for i, m in enumerate(index.measures):
        if m.declared_length is None or m.length < Fraction(int(m.meter.split("/")[0]) * 4, int(m.meter.split("/")[1])):
            continue
        t0, t1 = to_t(starts[i]), to_t(starts[i + 1])
        bars.append((m.number, t0, t1, (t1 - t0) / int(m.meter.split("/")[0])))
    return {"t": seconds, "q": quarters, "bars": bars, "end_t": seconds[-1] + 1, "measures": index.measures,
            "downbeats": np.array([b[1] for b in bars])}


def run_calibration(recording: Path, onnx: Path, work: Path) -> dict:
    piece = pieces.BY_ID["chopin-prelude-4"]
    index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
    folder_work = work / "calibration-chopin-prelude-4"
    folder_work.mkdir(parents=True, exist_ok=True)
    transcribed, tracked = transcribe(onnx, recording, folder_work)
    truth = dtw_truth(transcribed, index)
    np.savez(folder_work / "truth.npz", t=truth["t"], q=truth["q"])
    return {"meter": index.meter, **evaluate(piece, index, truth, transcribed, tracked, folder_work)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--onnx", type=Path, required=True, help="folder with onnx_pipeline.py and models/")
    parser.add_argument("--work", type=Path, required=True, help="folder for recordings, transcriptions and drafts (outside the repo)")
    parser.add_argument("--only", action="append", help="run only this ASAP folder (repeatable)")
    parser.add_argument("--calibrate", type=Path, help="recording of Chopin Op. 28 No. 4 (log 53: Ilić, Wikimedia Commons)")
    args = parser.parse_args()
    report_path = args.work / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if args.calibrate:
        report["calibration"] = run_calibration(args.calibrate, args.onnx, args.work)
        print(json.dumps(report["calibration"], indent=1))
    else:
        for folder, rome in TEST_SET:
            if args.only and folder not in args.only:
                continue
            try:
                report[folder] = run_asap(folder, rome, args.onnx, args.work)
            except Exception as error:
                report[folder] = {"error": f"{type(error).__name__}: {str(error)[:300]}"}
            print(folder, json.dumps(report[folder]), flush=True)
    report_path.write_text(json.dumps(report, indent=1))
    done = [r for f, r in report.items() if f != "calibration" and "audio_path" in r]
    if done:
        passing = sum(r["bars_right"] >= 0.9 for r in done)
        gap = np.mean([r["score_path"]["full"] - r["audio_path"]["full"] for r in done])
        print(f"bars >= 90%: {passing}/{len(done)}; mean full-numeral gap score - audio: {gap * 100:.1f} points")


if __name__ == "__main__":
    main()
