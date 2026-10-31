from __future__ import annotations

import json
import os
import select
import subprocess
import tempfile
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from engine import notes as note_list
from engine.annotations import AnnotationList
from engine.comparison import FUNCTIONS
from engine.score import Measure, ScoreIndex, in_range

ROOT = Path(__file__).parent.parent
ANALYSISGNN_PYTHON = os.environ.get("ANALYSISGNN_PYTHON", str(ROOT / ".venv-agnn/bin/python"))
ANALYSISGNN_CHECKPOINT = os.environ.get("ANALYSISGNN_CHECKPOINT", str(ROOT / "artifacts/models/model.ckpt"))

timings: ContextVar[dict[str, int] | None] = ContextVar("timings", default=None)


def add_timing(name: str, seconds: float) -> None:
    found = timings.get()
    if found is not None:
        found[name] = found.get(name, 0) + round(seconds * 1000)


ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI", "7": "VII"}
SEVENTH_OF = {
    "major triad": ("dominant seventh chord", "major seventh chord", "incomplete dominant-seventh chord"),
    "minor triad": ("minor seventh chord",),
    "diminished triad": ("diminished seventh chord", "half-diminished seventh chord"),
}
LOWERCASE = {"minor triad", "minor seventh chord", "diminished triad", "diminished seventh chord", "half-diminished seventh chord"}
QUALITY_MARK = {"diminished triad": "o", "diminished seventh chord": "o", "half-diminished seventh chord": "ø", "augmented triad": "+"}
AUGMENTED_SIXTHS = {
    "Italian augmented sixth chord": "It6",
    "German augmented sixth chord": "Ger65",
    "French augmented sixth chord": "Fr43",
    "augmented sixth": "It6",
}
TRIAD_FIGURES = ["", "6", "64", "64"]
SEVENTH_FIGURES = ["7", "65", "43", "42"]
DIATONIC_LOWERCASE = {"major": {"2", "3", "6", "7"}, "minor": {"1", "2", "4"}}
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MINOR_STEPS = {"3": 3, "6": 8, "7": 10}
MAJOR_STEPS = {"3": 4, "6": 9, "7": 11}


class DraftError(RuntimeError):
    pass


@dataclass
class Chord:
    measure: int
    beat: float
    key: str
    label: str
    confidence: float
    beats: float
    function: str | None
    bass: str = ""
    pitches: list[str] = field(default_factory=list)
    melody: list[str] = field(default_factory=list)
    alternative: str = ""
    alternative_confidence: float = 0.0


@dataclass
class Mark:
    measure: int
    beat: float
    label: str
    confidence: float
    staff: int | None = None
    pitch: str | None = None


@dataclass
class Draft:
    model: str
    chords: list[Chord]
    cadences: list[Mark]
    phrase_ends: list[Mark]
    pedals: list[Mark]
    non_chord_tones: list[Mark]


class _Worker:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def _start(self) -> None:
        runner = Path(__file__).parent / "models" / "analysisgnn_runner.py"
        self.process = subprocess.Popen(
            [ANALYSISGNN_PYTHON, str(runner), "--serve", ANALYSISGNN_CHECKPOINT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        if self._reply(300) != "ready":
            self._stop()
            raise DraftError("AnalysisGNN failed to load")

    def _reply(self, timeout: float) -> str:
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        return self.process.stdout.readline().strip() if ready else ""

    def _stop(self) -> None:
        if self.process:
            self.process.kill()
            self.process = None

    def run(self, source: Path, result: Path) -> None:
        waiting = time.perf_counter()
        with self.lock:
            add_timing("gnn_wait", time.perf_counter() - waiting)
            if self.process is None or self.process.poll() is not None:
                starting = time.perf_counter()
                self._start()
                add_timing("gnn_start", time.perf_counter() - starting)
            self.process.stdin.write(f"{source}\t{result}\n")
            self.process.stdin.flush()
            reply = self._reply(180)
            if not reply:
                self._stop()
                raise DraftError("AnalysisGNN did not answer in time")
            status, _, detail = reply.partition(" ")
            if status != "ok":
                raise DraftError(f"AnalysisGNN failed: {detail}")
            add_timing("gnn", float(detail))


_worker = _Worker()


def run_analysisgnn(score: bytes, kind: str = "musicxml") -> dict:
    with tempfile.TemporaryDirectory() as folder:
        name = "score.notes" if kind == "notes" else "score.mxl" if score[:2] == b"PK" else "score.musicxml"
        source = Path(folder) / name
        source.write_bytes(score)
        result_path = Path(folder) / "raw.json"
        _worker.run(source, result_path)
        return json.loads(result_path.read_text())


MODELS = {"analysisgnn": run_analysisgnn}


def numeral(degree: str, secondary: str | None, quality: str, inversion: int, key: str) -> str:
    if quality in AUGMENTED_SIXTHS:
        return AUGMENTED_SIXTHS[quality]
    accidental = "" if degree == "#7" else degree[:-1].replace("-", "b")
    root = ROMAN[degree[-1]]
    if quality in LOWERCASE:
        root = root.lower()
    is_seventh = "seventh" in quality
    figures = (SEVENTH_FIGURES if is_seventh else TRIAD_FIGURES)[inversion]
    if quality == "major seventh chord":
        figures = "M" + figures
    label = accidental + root + QUALITY_MARK.get(quality, "") + figures
    if secondary and secondary != "None":
        mode = "minor" if key[0].islower() else "major"
        target = ROMAN[secondary[-1]]
        if secondary[-1] in DIATONIC_LOWERCASE[mode] and len(secondary) == 1:
            target = target.lower()
        label += "/" + secondary[:-1].replace("-", "b") + target
    return label


SPECIAL_RN = {"It": "It6", "Ger": "Ger65", "Fr": "Fr43"}
MINOR_RN = {"i", "iv", "VI", "III", "VII", "iio", "iiø7", "i7", "iv7", "III+"}
MAJOR_RN = {"I", "IV", "vi", "iii", "ii", "ii7", "vi7", "IV7", "IM7", "IVM7", "iii7"}


def numeral_with_inversion(rn: str, inversion: int) -> str:
    if rn in SPECIAL_RN:
        return SPECIAL_RN[rn]
    if rn.startswith("Cad"):
        return rn
    head, _, target = rn.replace("%", "ø").partition("/")
    if head == "N":
        head = "bII"
    if head.endswith("M7"):
        base, figures = head[:-2], "M" + SEVENTH_FIGURES[inversion]
    elif head.endswith("7"):
        base, figures = head[:-1], SEVENTH_FIGURES[inversion]
    else:
        base, figures = head, TRIAD_FIGURES[inversion]
    return base + figures + (f"/{target}" if target else "")


def _midi(pitch: str) -> int:
    accidental = pitch[1:-1] if pitch[-2] != "-" else pitch[1:-2]
    return STEPS[pitch[0]] + accidental.count("#") - accidental.count("b") + 12 * (int(pitch[len(accidental) + 1 :]) + 1)


def build(raw: dict, index: ScoreIndex, model: str = "analysisgnn") -> Draft:
    notes, tasks = raw["notes"], raw["tasks"]
    count = len(notes["measure"])

    def best(task: str, i: int) -> tuple[str, float]:
        return str(tasks[task]["labels"][0][i]), tasks[task]["probabilities"][0][i]

    def ranked(task: str, i: int, depth: int = 2) -> list[tuple[str, float]]:
        found = tasks[task]["labels"]
        return [(str(found[k][i]), tasks[task]["probabilities"][k][i]) for k in range(min(depth, len(found)))]

    def alternative(degree: str, secondary: str, label: str, i: int, key: str) -> tuple[str, float]:
        options = {}
        for d, pd in ranked("degree1", i):
            for q, pq in ranked("quality", i):
                for v, pv in ranked("inversion", i):
                    if d == "None":
                        continue
                    try:
                        text = numeral(d, secondary, q, int(float(v)), key)
                    except (KeyError, IndexError, ValueError):
                        continue
                    options[text] = max(options.get(text, 0.0), pd * pq * pv)
        options.pop(label, None)
        if not options:
            return "", 0.0
        text = max(options, key=options.get)
        return (text, round(options[text], 2)) if options[text] >= 0.3 else ("", 0.0)

    shifts: dict[int, Fraction] = {}
    for i in range(count):
        number = notes["measure"][i]
        offset = Fraction(notes["offset"][i])
        shifts[number] = min(shifts.get(number, offset), offset)
    for number, earliest in shifts.items():
        measure = index.measures[number - 1]
        first_event = min((event.onset for event in measure.events), default=Fraction(0))
        shifts[number] = earliest - first_event if earliest >= measure.length else Fraction(0)

    known_onsets = [sorted({event.onset for event in measure.events}) for measure in index.measures]

    def place(i: int) -> tuple[Measure, Fraction]:
        number = notes["measure"][i]
        offset = Fraction(notes["offset"][i]) - shifts[number]
        nearest = min(known_onsets[number - 1], key=lambda onset: abs(onset - offset), default=offset)
        return index.measures[number - 1], nearest if abs(nearest - offset) <= Fraction(1, 32) else offset

    starts: list[Fraction] = []
    total = Fraction(0)
    for measure in index.measures:
        starts.append(total)
        total += measure.length

    placed = [place(i) for i in range(count)]
    onsets: dict[tuple[int, Fraction], list[int]] = {}
    for i in range(count):
        onsets.setdefault((notes["measure"][i], placed[i][1]), []).append(i)
    ordered = sorted(onsets)

    in_score = [False] * count
    for (order, offset), members in onsets.items():
        here = {event.pitch for event in index.measures[order - 1].events if event.onset == offset}
        for i in members:
            in_score[i] = notes["pitch"][i] in here
    if sum(in_score) < 0.9 * count:
        raise DraftError(f"Only {sum(in_score)} of {count} model notes line up with the engraved score")

    chords: list[Chord] = []
    spans: list[tuple[tuple, list[tuple[int, Fraction]]]] = []
    has_rn = "romanNumeral" in tasks
    for position in ordered:
        i = onsets[position][0]
        if has_rn:
            key = (best("localkey", i)[0], best("romanNumeral", i)[0], "RN")
        else:
            key = (best("localkey", i)[0], best("degree1", i)[0], best("degree2", i)[0])
        if key[1] == "None" and spans:
            spans[-1][1].append(position)
        elif spans and spans[-1][0] == key:
            spans[-1][1].append(position)
        else:
            spans.append((key, [position]))

    def cadential_split(local_key: str, positions: list) -> int:
        tonic = (STEPS[local_key[0]] + local_key.count("#") - local_key.count("-")) % 12
        def sounding(position):
            measure = index.measures[position[0] - 1]
            return [e for e in measure.events if e.pitch and not e.grace and e.onset <= position[1] < e.onset + e.duration]
        first = sounding(positions[0])
        measure = index.measures[positions[0][0] - 1]
        if not first or measure.beat_of(positions[0][1]) % 1:
            return 0
        pcs = {_midi(e.pitch) % 12 for e in first}
        bass = _midi(min(first, key=lambda e: _midi(e.pitch)).pitch) % 12
        thirds = {(tonic + 3) % 12, (tonic + 4) % 12}
        if bass != (tonic + 7) % 12 or tonic not in pcs or not pcs & thirds or (tonic + 11) % 12 in pcs:
            return 0
        for number, position in enumerate(positions[1:], 1):
            if (tonic + 11) % 12 in {_midi(e.pitch) % 12 for e in sounding(position)}:
                return number
        return 0

    split_spans = []
    for key, positions in spans:
        local_key, degree, secondary = key
        at = cadential_split(local_key, positions) if degree == "5" and secondary == "None" else 0
        if at:
            split_spans += [((local_key, "Cad", "None"), positions[:at]), (key, positions[at:])]
        else:
            split_spans.append((key, positions))
    spans = split_spans

    def mode_evidence(local_key: str, degree: str, secondary: str, positions: list) -> int:
        if degree == "Cad":
            return 0
        if secondary == "RN":
            rn = degree.replace("%", "ø").split("/")[0]
            if "/" in degree:
                return 0
            return (2 if rn in ("i", "i7") else 1) if rn in MINOR_RN else (-2 if rn in ("I", "IM7") else -1) if rn in MAJOR_RN else 0
        if secondary != "None":
            return 0
        if degree == "#7":
            return 2
        if degree in ("-3", "-6", "-7"):
            return -1
        if degree == "1":
            quality = best("quality", onsets[positions[0]][0])[0]
            return 2 if quality in ("minor triad", "minor seventh chord") else -2 if quality in ("major triad", "major seventh chord") else 0
        if degree in MINOR_STEPS:
            tonic = STEPS[local_key[0]] + local_key.count("#") - local_key.count("-")
            heard = {_midi(e.pitch) % 12 for p in positions for e in index.measures[p[0] - 1].events if e.onset == p[1] and e.pitch}
            as_minor, as_major = (tonic + MINOR_STEPS[degree]) % 12 in heard, (tonic + MAJOR_STEPS[degree]) % 12 in heard
            return as_minor - as_major
        return 0

    evidence = [mode_evidence(*key, positions) for key, positions in spans]
    minor: list[bool] = []
    for number, ((local_key, _, _), _) in enumerate(spans):
        near = [e for e, (key, _) in zip(evidence[max(0, number - 8) : number + 9], spans[max(0, number - 8) : number + 9]) if key[0] == local_key]
        whole = [e for e, (key, _) in zip(evidence, spans) if key[0] == local_key]
        same_key_before = bool(minor) and spans[number - 1][0][0] == local_key
        minor.append(sum(near) > 0 if abs(sum(near)) >= 3 else minor[-1] if same_key_before else sum(whole) > 0)

    for number, ((local_key, degree, secondary), positions) in enumerate(spans):
        if degree == "None":
            continue
        first = onsets[positions[0]][0]
        votes: dict[str, float] = {}
        for position in positions:
            quality, probability = best("quality", onsets[position][0])
            votes[quality] = votes.get(quality, 0) + probability
        quality = max(votes, key=votes.get)
        sevenths = [q for q in SEVENTH_OF.get(quality, ()) if votes.get(q, 0) >= 0.5]
        if sevenths:
            quality = max(sevenths, key=votes.get)
        inversion = int(float(best("inversion", first)[0]))
        key = local_key.replace("-", "b")
        if minor[number]:
            key = key[0].lower() + key[1:]
        measure = index.measures[positions[0][0] - 1]
        start = starts[positions[0][0] - 1] + positions[0][1]
        following = spans[number + 1][1][0] if number + 1 < len(spans) else None
        end = starts[following[0] - 1] + following[1] if following else total
        sounding = [
            event
            for position in positions
            for event in index.measures[position[0] - 1].events
            if event.onset == position[1] and event.pitch and not event.grace
        ]
        lowest = min((e for e in sounding if e.onset == positions[0][1] and e.measure == measure.number), key=lambda e: _midi(e.pitch), default=None)
        names: list[str] = []
        for event in sorted(sounding, key=lambda e: _midi(e.pitch)):
            if event.pitch[:-1] not in names:
                names.append(event.pitch[:-1])
        if degree == "Cad":
            label = "Cad64"
        else:
            label = numeral_with_inversion(degree, inversion) if secondary == "RN" else numeral(degree, secondary, quality, inversion, key)
        other, other_confidence = alternative(degree, secondary, label, first, key) if secondary != "RN" and degree != "Cad" else ("", 0.0)
        confidence = min(best("degree1", first)[1], votes[quality] / max(1, sum(1 for p in positions if best("quality", onsets[p][0])[0] == quality)))
        chords.append(
            Chord(
                measure=measure.number,
                beat=measure.beat_of(positions[0][1]),
                key=key,
                label=label,
                confidence=round(min(confidence, 1.0), 2),
                beats=round(float((end - start) / measure.beat_length), 2),
                function="D" if degree == "Cad" else (FUNCTIONS.get(best("degree1", first)[0]) if "/" not in degree else None) if secondary == "RN" else FUNCTIONS.get(degree) if secondary == "None" else None,
                bass=lowest.pitch if lowest else "",
                pitches=names,
                melody=[e.pitch for e in sounding if e.staff == 1][:8],
                alternative=other,
                alternative_confidence=other_confidence,
            )
        )

    def marks(task: str, per_note: bool = False, positive=lambda label: label not in ("0", "None", "False")) -> list[Mark]:
        found: dict[tuple, Mark] = {}
        for i in range(count):
            label, probability = best(task, i)
            if not positive(label) or (per_note and (notes["duration"][i] == 0 or not in_score[i])):
                continue
            measure, offset = placed[i]
            mark = Mark(measure.number, measure.beat_of(offset), label, round(probability, 2))
            if per_note:
                mark.staff, mark.pitch = notes["staff"][i], notes["pitch"][i]
            identity = (notes["measure"][i], offset, mark.pitch)
            if identity not in found or found[identity].confidence < mark.confidence:
                found[identity] = mark
        return [found[identity] for identity in sorted(found, key=lambda k: (k[0], k[1], k[2] or ""))]

    return Draft(
        model=model,
        chords=chords,
        cadences=marks("cadence"),
        phrase_ends=marks("phrase") if "phrase" in tasks else [],
        pedals=marks("organ_point", per_note=True) if "organ_point" in tasks else [],
        non_chord_tones=marks("tpc_in_label", per_note=True, positive=lambda label: label == "0") if "tpc_in_label" in tasks else [],
    )


def draft(index: ScoreIndex, model: str = "analysisgnn") -> Draft:
    return build(MODELS[model](note_list.encode(index).encode(), "notes"), index, model)


def draft_from_notes(text: str, model: str = "analysisgnn") -> Draft:
    return build(MODELS[model](text.encode(), "notes"), note_list.decode(text), model)


def as_text(result: Draft, first: int | None = None, last: int | None = None, alternatives: bool = False) -> str:
    def wanted(measure: int) -> bool:
        return in_range(measure, first, last)

    lines = [
        f"Draft analysis from {result.model}. The model's full chord labels are exactly right only about half",
        "the time on its benchmark, so check every line against the notes listed beside it.",
        "",
        "CHORDS: measure.beat | key | numeral | confidence | length in beats | bass | pitch classes | melody"
        + (" | or: the model's runner-up where it is a close call" if alternatives else ""),
    ]
    for chord in result.chords:
        if wanted(chord.measure):
            lines.append(
                f"m{chord.measure} b{round(chord.beat, 2):g} | {chord.key} | {chord.label} | {chord.confidence:.2f} | {chord.beats:g} | "
                f"{chord.bass} | {' '.join(chord.pitches)} | {' '.join(chord.melody)}"
                + (f" | or {chord.alternative} ({chord.alternative_confidence:.2f})" if alternatives and chord.alternative else "")
            )
    for title, items, show in (
        ("CADENCES", result.cadences, lambda m: f"m{m.measure} b{round(m.beat, 2):g} {m.label} ({m.confidence:.2f})"),
        ("PHRASE ENDS", result.phrase_ends, lambda m: f"m{m.measure} b{round(m.beat, 2):g} ({m.confidence:.2f})"),
        ("PEDAL POINTS", result.pedals, lambda m: f"m{m.measure} b{round(m.beat, 2):g} {m.pitch} staff {m.staff} ({m.confidence:.2f})"),
        ("POSSIBLE NON-CHORD TONES", result.non_chord_tones, lambda m: f"m{m.measure} b{round(m.beat, 2):g} {m.pitch} staff {m.staff}"),
    ):
        shown = [show(item) for item in items if wanted(item.measure)]
        lines += ["", f"{title}: " + ("; ".join(shown) if shown else "none found")]
    return "\n".join(lines)


def as_annotations(result: Draft, first: int | None = None, last: int | None = None, functions: bool = False) -> AnnotationList:
    def wanted(measure: int) -> bool:
        return in_range(measure, first, last)

    items: list[dict] = []
    key = None
    for chord in result.chords:
        if not wanted(chord.measure):
            continue
        item = {"type": "harmony", "at": {"measure": chord.measure, "beat": chord.beat}, "label": chord.label}
        if functions and chord.function:
            item["function"] = chord.function
        if chord.key != key:
            item["key"] = key = chord.key
        items.append(item)
    for cadence in result.cadences:
        if wanted(cadence.measure):
            items.append({"type": "cadence", "at": {"measure": cadence.measure, "beat": cadence.beat}, "label": cadence.label})
    for tone in result.non_chord_tones:
        if wanted(tone.measure):
            note = {"measure": tone.measure, "beat": tone.beat, "staff": tone.staff, "pitch": tone.pitch}
            items.append({"type": "nct", "note": note, "label": "NCT"})
    return AnnotationList.model_validate({"annotations": items})
