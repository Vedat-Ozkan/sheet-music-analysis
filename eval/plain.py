"""Ask a plain chat model for a Roman numeral analysis, with the MusicXML pasted in and nothing else.

    .venv/bin/python -m eval.plain --only ID [--only ID] [--model sonnet] [--runs 2]

No method, no skill, no tools, no note table, no draft: a one-line system prompt and an empty Claude Code
config folder (holding only the login), so no CLAUDE.md, memory or skills reach the model. The only help is
the output format, RomanText, so that the answer can be scored. The bars asked for are the passages the
held-out review covered (out/eval/reviewed/opus-medium-2026-10-24/<id>.json), and both are scored on those
bars. Replies go to out/eval/plain/<model>-<run>/<id>.txt; scores print at the end.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces
from eval.review import fresh_claude, musicxml, record_spend

OUT = pieces.OUT / "plain"
PASSAGES = pieces.OUT / "reviewed" / "opus-medium-2026-10-24"
COLUMNS = ("key", "root", "chord_and_bass", "function", "full")

PROMPT = """Here is a MusicXML file of {title}.

<file>
{xml}
</file>

Give a Roman numeral analysis of {bars}. Write it in RomanText format, one line per bar, with b<N> for the beat \
and the key wherever it changes, for example:
m1 C: I b3 V6
m2 I b2 IV b3 G: V7"""


def ask(prompt: str, model: str) -> dict:
    with fresh_claude() as environment, tempfile.TemporaryDirectory() as folder:
        process = subprocess.run(
            ["claude", "-p", "--model", model, "--system-prompt", "You are Claude, a helpful AI assistant.", "--tools", "", "--disable-slash-commands", "--strict-mcp-config", "--output-format", "json"],
            input=prompt, capture_output=True, text=True, cwd=folder, env=environment, timeout=1800,
        )  # fmt: skip
    if process.returncode != 0:
        raise RuntimeError(f"claude exited {process.returncode}: {(process.stdout or process.stderr)[-300:]}")
    answer = json.loads(process.stdout)
    record_spend(f"plain {model} (subscription, estimated)", answer)
    return answer


def run(piece: pieces.Piece, model: str, number: int) -> Path:
    path = OUT / f"{model}-{number}" / f"{piece.id}.txt"
    if not path.exists():
        bars = json.loads((PASSAGES / f"{piece.id}.json").read_text())["passages"]
        wanted = " and ".join(f"bars {first} to {last}" for first, last in bars)
        xml = musicxml(pieces.without_harmony(pieces.score(piece))).decode("utf-8", "ignore")
        answer = ask(PROMPT.format(title=piece.title, xml=xml, bars=wanted), model)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(answer["result"])
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", required=True, help="held-out piece to ask about (repeatable)")
    parser.add_argument("--model", action="append", help="sonnet, opus or a full model id (repeatable; default both)")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    jobs = [(pieces.BY_ID[name], model, number) for name in args.only for model in args.model or ["sonnet", "opus"] for number in range(1, args.runs + 1)]
    with ThreadPoolExecutor(len(jobs)) as pool:
        list(pool.map(lambda job: run(*job), jobs))
    for model in args.model or ["sonnet", "opus"]:
        for number in range(1, args.runs + 1):
            totals, weight = dict.fromkeys(COLUMNS, 0.0), 0
            for name in args.only:
                piece = pieces.BY_ID[name]
                index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
                reference = [compare.Label(label.measure + piece.bar_offset, label.beat, label.key, label.figure) for label in compare.from_romantext(pieces.labels(piece))]
                bars = [tuple(passage) for passage in json.loads((PASSAGES / f"{name}.json").read_text())["passages"]]
                reading = compare.from_romantext((OUT / f"{model}-{number}" / f"{name}.txt").read_text())
                result = compare.compare(reference, reading, index, bars)
                size = sum(last - first + 1 for first, last in bars)
                weight += size
                for column in COLUMNS:
                    totals[column] += (result[column] or 0) * size
                print(f"{model}-{number} {name[8:50]:42s} full {result['full']:.2f}  function {result['function']:.2f}  key {result['key']:.2f}  ({result['reading_chords']} chords read)")
            print(f"{model}-{number} all  " + "  ".join(f"{column} {totals[column] / weight:.2f}" for column in COLUMNS))


if __name__ == "__main__":
    main()
