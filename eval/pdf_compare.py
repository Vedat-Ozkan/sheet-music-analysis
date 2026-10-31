"""Plain chat against our setup, both given the same PDF of a held-out piece.

    .venv/bin/python -m eval.pdf_compare --kind real|engraved [--model sonnet] [--model opus] [--model fable]

Each PDF is out/eval/pdf_compare/<kind>/<id>.pdf ("real": pages cut from a published edition; "engraved": our own
engraving of the source file), with our reader's MusicXML of it beside it (<id>.musicxml, from engine.read_pdf).
Plain: the PDF attached (the Read tool only), a one-line system prompt and the RomanText question of eval.plain.
Ours: the reading drafted and reviewed as eval.review does. Both run at the model's default effort in a fresh config
on the subscription, cover the passages of the 2026-10-24 held-out review, and are scored on the expert's labels of
the source file over those bars. Ours is scored twice: as read, and with each read bar matched back to the source bar
with the same notes ("lined up"), since a misread bar line shifts every later bar number; runs of misread bars between matched ones pair up when both
sides have the same number of bars, and are dropped otherwise. Prints agreement, tokens
and estimated cost per model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces
from eval.plain import COLUMNS, PASSAGES, PROMPT as PLAIN_PROMPT
from eval.review import REVIEWED, fresh_claude, record_spend, review, run_name, tokens

FOLDER = pieces.OUT / "pdf_compare"
PIECES = ["heldout-bach-_johann_sebastian-the_well-tempered_clavier_i-22", "heldout-beethoven_piano_sonatas-01-3", "heldout-grieg_lyric_pieces-op38n07"]
PROMPT = "The attached file score.pdf is a score of {title}." + PLAIN_PROMPT[PLAIN_PROMPT.index("</file>") + len("</file>"):]


def passages(name: str) -> list[tuple[int, int]]:
    return [tuple(passage) for passage in json.loads((PASSAGES / f"{name}.json").read_text())["passages"]]


def wanted(name: str) -> str:
    return " and ".join(f"bars {first} to {last}" for first, last in passages(name))


def plain(kind: str, name: str, model: str) -> dict:
    path = FOLDER / kind / "plain" / model / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    with fresh_claude() as environment, tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "score.pdf").write_bytes((FOLDER / kind / f"{name}.pdf").read_bytes())
        process = subprocess.run(
            ["claude", "-p", "--model", model, "--system-prompt", "You are Claude, a helpful AI assistant.", "--tools", "Read", "--allowedTools", "Read", "--disable-slash-commands", "--strict-mcp-config", "--output-format", "json"],
            input=PROMPT.format(title=pieces.BY_ID[name].title, bars=wanted(name)), capture_output=True, text=True, cwd=folder, env=environment, timeout=1800,
        )  # fmt: skip
    if process.returncode != 0:
        raise RuntimeError(f"claude exited {process.returncode}: {(process.stdout or process.stderr)[-300:]}")
    answer = json.loads(process.stdout)
    record_spend(f"pdf_compare plain {model} (subscription, estimated)", answer)
    result = {"reply": answer["result"], "cost_usd": answer.get("total_cost_usd") or 0, "tokens": tokens(answer)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return result


def reading(kind: str, name: str) -> tuple[ScoreIndex, draft.Draft]:
    index = ScoreIndex(load_toolkit((FOLDER / kind / f"{name}.musicxml").read_bytes()).getMEI())
    path = FOLDER / kind / f"{name}.draft.json"
    if not path.exists():
        path.write_text(json.dumps(draft.run_analysisgnn(notes.encode(index).encode(), "notes")))
    return index, draft.build(json.loads(path.read_text()), index)


def ours(kind: str, name: str, model: str, read: tuple[ScoreIndex, draft.Draft], first: int, last: int) -> dict:
    return review(pieces.BY_ID[name], read[0], read[1], first, last, model, None, f"pdf-{kind}")


def source_index(name: str) -> ScoreIndex:
    return ScoreIndex(load_toolkit(pieces.score(pieces.BY_ID[name])).getMEI())


def lined_up(labels: list[compare.Label], read: ScoreIndex, source: ScoreIndex) -> list[compare.Label]:
    def pitches(index: ScoreIndex) -> list[tuple[str, ...]]:
        return [tuple(sorted({event.pitch for event in measure.events if event.pitch})) for measure in index.measures]

    numbers = {}
    for tag, a, a_end, b, b_end in SequenceMatcher(None, pitches(read), pitches(source), autojunk=False).get_opcodes():
        if tag == "equal" or tag == "replace" and a_end - a == b_end - b:
            for k in range(a_end - a):
                numbers[read.measures[a + k].number] = source.measures[b + k].number
    return [replace(label, measure=numbers[label.measure]) for label in labels if label.measure in numbers]


def score(name: str, labels: list[compare.Label]) -> dict:
    piece = pieces.BY_ID[name]
    index = source_index(name)
    reference = [compare.Label(label.measure + piece.bar_offset, label.beat, label.key, label.figure) for label in compare.from_romantext(pieces.labels(piece))]
    return compare.compare(reference, labels, index, passages(name))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("real", "engraved"))
    parser.add_argument("--model", action="append", help="sonnet, opus, fable or a full model id (repeatable; default all three)")
    args = parser.parse_args()
    models = args.model or ["sonnet", "opus", "fable"]
    readings = {name: reading(args.kind, name) for name in PIECES}
    jobs = [(plain, (args.kind, name, model)) for name in PIECES for model in models]
    jobs += [(ours, (args.kind, name, model, readings[name], first, last)) for name in PIECES for model in models for first, last in passages(name)]
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda job: job[0](*job[1]), jobs))
    size = {name: sum(last - first + 1 for first, last in passages(name)) for name in PIECES}
    print(f"{'':20s} " + "  ".join(f"{column:>8s}" for column in COLUMNS) + "    tokens  cost US$   per piece, full")
    for model in models:
        for setup in ("plain", "ours", "ours lined up"):
            totals, per, cost, used = dict.fromkeys(COLUMNS, 0.0), [], 0.0, 0
            for name in PIECES:
                if setup == "plain":
                    answer = plain(args.kind, name, model)
                    labels = compare.from_romantext(answer["reply"])
                    cost, used = cost + answer["cost_usd"], used + answer["tokens"]
                else:
                    folder = REVIEWED / run_name(model, None, f"pdf-{args.kind}") / "passages"
                    parts = [json.loads((folder / f"{name}_{first}-{last}.json").read_text()) for first, last in passages(name)]
                    labels = compare.from_annotations({"annotations": [item for part in parts for item in part["annotations"]]})
                    if setup == "ours lined up":
                        labels = lined_up(labels, readings[name][0], source_index(name))
                    cost, used = cost + sum(part["cost_usd"] for part in parts), used + sum(part.get("tokens", 0) for part in parts)
                result = score(name, labels)
                for column in COLUMNS:
                    totals[column] += (result[column] or 0) * size[name]
                per.append(f"{result['full']:.2f}")
            weight = sum(size.values())
            print(f"{model + ' ' + setup:20s} " + "  ".join(f"{totals[column] / weight:8.2f}" for column in COLUMNS) + f"  {used:8d}  {cost:8.2f}   " + " / ".join(per))


if __name__ == "__main__":
    main()
