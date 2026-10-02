"""The harmony model's draft, condensed for the chat model to review.

A draft model labels every note. This module turns that into what an analyst
works with: chord spans, cadences, phrase ends, pedal points and suspected
non-chord tones, each addressed by measure and beat like the annotation list.
The model behind it is swappable; `MODELS` maps a name to a function that
returns raw per-note predictions.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from engine import notes as note_list
from engine.annotations import AnnotationList
from engine.score import Measure, ScoreIndex

ROOT = Path(__file__).parent.parent
ANALYSISGNN_PYTHON = os.environ.get("ANALYSISGNN_PYTHON", str(ROOT / ".venv-agnn/bin/python"))
ANALYSISGNN_CHECKPOINT = os.environ.get("ANALYSISGNN_CHECKPOINT", str(ROOT / "artifacts/models/model.ckpt"))

ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI", "7": "VII"}
SEVENTH_OF = {  # triad label -> the seventh chords that extend it
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
FUNCTIONS = {"1": "T", "3": "T", "6": "T", "2": "PD", "4": "PD", "5": "D", "7": "D"}
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class DraftError(RuntimeError):
    """The draft model could not analyse the score."""


@dataclass
class Chord:
    measure: int
    beat: float
    key: str  # "Eb" for E-flat major, "f" for F minor
    label: str  # RomanText, e.g. "V65/vi"
    confidence: float
    beats: float  # length, in beats
    function: str | None
    bass: str = ""
    pitches: list[str] = field(default_factory=list)
    melody: list[str] = field(default_factory=list)


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


# ---- running the model ----------------------------------------------------------------


def run_analysisgnn(score: bytes, kind: str = "musicxml") -> dict:
    """Raw per-note predictions from AnalysisGNN, which runs in its own environment.

    `kind` is "musicxml" for a score file or "notes" for a note list (engine/notes.py).
    """
    runner = Path(__file__).parent / "models" / "analysisgnn_runner.py"
    with tempfile.TemporaryDirectory() as folder:
        name = "score.notes" if kind == "notes" else "score.mxl" if score[:2] == b"PK" else "score.musicxml"
        source = Path(folder) / name
        source.write_bytes(score)
        result_path = Path(folder) / "raw.json"
        process = subprocess.run(
            [ANALYSISGNN_PYTHON, str(runner), ANALYSISGNN_CHECKPOINT, str(source), str(result_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if process.returncode != 0 or not result_path.exists():
            raise DraftError(f"AnalysisGNN failed: {process.stderr.strip().splitlines()[-1:] or 'no output'}")
        return json.loads(result_path.read_text())


MODELS = {"analysisgnn": run_analysisgnn}


# ---- raw predictions -> draft ---------------------------------------------------------


def numeral(degree: str, secondary: str | None, quality: str, inversion: int, key: str) -> str:
    """RomanText label from the model's separate degree, quality and inversion outputs."""
    if quality in AUGMENTED_SIXTHS:
        return AUGMENTED_SIXTHS[quality]
    # "#7" is the raised leading tone of a minor key, which Roman numerals write as plain vii
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


def _midi(pitch: str) -> int:
    accidental = pitch[1:-1] if pitch[-2] != "-" else pitch[1:-2]
    return STEPS[pitch[0]] + accidental.count("#") - accidental.count("b") + 12 * (int(pitch[len(accidental) + 1 :]) + 1)


def build(raw: dict, index: ScoreIndex, model: str = "analysisgnn") -> Draft:
    notes, tasks = raw["notes"], raw["tasks"]
    count = len(notes["measure"])

    def best(task: str, i: int) -> tuple[str, float]:
        return str(tasks[task]["labels"][0][i]), tasks[task]["probabilities"][0][i]

    # partitura places a pickup's notes at the end of an imagined full bar; the score index counts
    # from the pickup's first note. Shift any measure whose offsets overrun its real length.
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
        """The measure and onset of model note i, snapped to an onset the score actually has.

        Files that write tuplets in rounded units give onsets like 21/128 for a sixth of a beat,
        so the model's positions are matched to the nearest real onset instead of compared exactly.
        """
        number = notes["measure"][i]  # counted from 1 in the order of the note list, pickup included
        offset = Fraction(notes["offset"][i]) - shifts[number]
        nearest = min(known_onsets[number - 1], key=lambda onset: abs(onset - offset), default=offset)
        return index.measures[number - 1], nearest if abs(nearest - offset) <= Fraction(1, 32) else offset

    starts: list[Fraction] = []  # absolute start of each measure, in quarters
    total = Fraction(0)
    for measure in index.measures:
        starts.append(total)
        total += measure.length

    # one row per onset, in score order
    placed = [place(i) for i in range(count)]
    onsets: dict[tuple[int, Fraction], list[int]] = {}
    for i in range(count):
        onsets.setdefault((notes["measure"][i], placed[i][1]), []).append(i)
    ordered = sorted(onsets)

    # check the model's note list lines up with the engraved score before trusting positions
    in_score = [False] * count
    for (order, offset), members in onsets.items():
        here = {event.pitch for event in index.measures[order - 1].events if event.onset == offset}
        for i in members:
            in_score[i] = notes["pitch"][i] in here
    if sum(in_score) < 0.9 * count:
        raise DraftError(f"Only {sum(in_score)} of {count} model notes line up with the engraved score")

    chords: list[Chord] = []
    spans: list[tuple[tuple, list[tuple[int, Fraction]]]] = []
    for position in ordered:
        i = onsets[position][0]
        key = (best("localkey", i)[0], best("degree1", i)[0], best("degree2", i)[0])
        if key[1] == "None" and spans:
            spans[-1][1].append(position)
        elif spans and spans[-1][0] == key:
            spans[-1][1].append(position)
        else:
            spans.append((key, [position]))

    for number, ((local_key, degree, secondary), positions) in enumerate(spans):
        if degree == "None":
            continue
        first = onsets[positions[0]][0]
        votes: dict[str, float] = {}
        for position in positions:
            quality, probability = best("quality", onsets[position][0])
            votes[quality] = votes.get(quality, 0) + probability
        quality = max(votes, key=votes.get)
        # an arpeggiated seventh chord reads as a triad until its seventh sounds
        sevenths = [q for q in SEVENTH_OF.get(quality, ()) if votes.get(q, 0) >= 0.5]
        if sevenths:
            quality = max(sevenths, key=votes.get)
        inversion = int(float(best("inversion", first)[0]))
        key = local_key.replace("-", "b")
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
        confidence = min(best("degree1", first)[1], votes[quality] / max(1, sum(1 for p in positions if best("quality", onsets[p][0])[0] == quality)))
        chords.append(
            Chord(
                measure=measure.number,
                beat=round(measure.beat_of(positions[0][1]), 2),
                key=key,
                label=numeral(degree, secondary, quality, inversion, key),
                confidence=round(min(confidence, 1.0), 2),
                beats=round(float((end - start) / measure.beat_length), 2),
                function=FUNCTIONS.get(degree) if secondary == "None" else None,
                bass=lowest.pitch if lowest else "",
                pitches=names,
                melody=[e.pitch for e in sounding if e.staff == 1][:8],
            )
        )

    def marks(task: str, per_note: bool = False, positive=lambda label: label not in ("0", "None", "False")) -> list[Mark]:
        found: dict[tuple, Mark] = {}
        for i in range(count):
            label, probability = best(task, i)
            # a note mark must point at a note the score index can find again: no grace notes, no strays
            if not positive(label) or (per_note and (notes["duration"][i] == 0 or not in_score[i])):
                continue
            measure, offset = placed[i]
            mark = Mark(measure.number, round(measure.beat_of(offset), 2), label, round(probability, 2))
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
    """Draft for a score we have indexed ourselves.

    The model is given our own note list rather than the file, so that it sees exactly the notes
    the index holds: sounding pitches, every instrument on one timeline, split bars joined.
    """
    return build(MODELS[model](note_list.encode(index).encode(), "notes"), index, model)


def draft_from_notes(text: str, model: str = "analysisgnn") -> Draft:
    """Draft from a note list, for hosts that cannot send the score file itself."""
    return build(MODELS[model](text.encode(), "notes"), note_list.decode(text), model)


# ---- draft -> what the chat model reads -----------------------------------------------


def as_text(result: Draft, first: int | None = None, last: int | None = None) -> str:
    """The draft as a compact table. `first`/`last` limit it to a range of measures."""

    def wanted(measure: int) -> bool:
        return (first is None or measure >= first) and (last is None or measure <= last)

    lines = [
        f"Draft analysis from {result.model}. The model's full chord labels are exactly right only about half",
        "the time on its benchmark, so check every line against the notes listed beside it.",
        "",
        "CHORDS: measure.beat | key | numeral | confidence | length in beats | bass | pitch classes | melody",
    ]
    for chord in result.chords:
        if wanted(chord.measure):
            lines.append(
                f"m{chord.measure} b{chord.beat:g} | {chord.key} | {chord.label} | {chord.confidence:.2f} | {chord.beats:g} | "
                f"{chord.bass} | {' '.join(chord.pitches)} | {' '.join(chord.melody)}"
            )
    for title, items, show in (
        ("CADENCES", result.cadences, lambda m: f"m{m.measure} b{m.beat:g} {m.label} ({m.confidence:.2f})"),
        ("PHRASE ENDS", result.phrase_ends, lambda m: f"m{m.measure} b{m.beat:g} ({m.confidence:.2f})"),
        ("PEDAL POINTS", result.pedals, lambda m: f"m{m.measure} b{m.beat:g} {m.pitch} staff {m.staff} ({m.confidence:.2f})"),
        ("POSSIBLE NON-CHORD TONES", result.non_chord_tones, lambda m: f"m{m.measure} b{m.beat:g} {m.pitch} staff {m.staff}"),
    ):
        shown = [show(item) for item in items if wanted(item.measure)]
        lines += ["", f"{title}: " + ("; ".join(shown) if shown else "none found")]
    return "\n".join(lines)


def as_annotations(result: Draft, first: int | None = None, last: int | None = None) -> AnnotationList:
    """The unreviewed draft as an annotation list, so it can be drawn as it stands."""

    def wanted(measure: int) -> bool:
        return (first is None or measure >= first) and (last is None or measure <= last)

    items: list[dict] = []
    key = None
    for chord in result.chords:
        if not wanted(chord.measure):
            continue
        item = {"type": "harmony", "at": {"measure": chord.measure, "beat": chord.beat}, "label": chord.label}
        if chord.function:
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
