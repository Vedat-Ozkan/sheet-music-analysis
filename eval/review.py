"""Have the chat model review the draft, as the skill does inside Claude, and keep what it writes.

    .venv/bin/python -m eval.review [--only ID] [--model opus] [--effort medium] [--tag NAME] [--bars 24] [--jobs 4]

For each passage the model is given what the skill gives it (the method from skill/SKILL.md, the
annotation format, the note table and the model's draft) and nothing else: no tools, no reference
analyses. Its annotation list is checked against the score the way the renderer would, with one
chance to correct what does not resolve. Passages are merged into out/eval/reviewed/<model>[-<effort>]/<id>.json,
with the commentary beside it in <id>.md. Finished passages are kept, so a stopped run resumes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine import draft, harmony, reduce, render
from engine.annotate import check
from engine.annotations import AnnotationList
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import pieces
from eval.run import cached_draft

REVIEWED = pieces.OUT / "reviewed"
SKILL = (pieces.ROOT / "skill" / "SKILL.md").read_text()
METHOD = SKILL[SKILL.index("## Method") : SKILL.index("## Limits")]
SPEC = (pieces.ROOT / "docs" / "annotation-spec.md").read_text()
NO_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Agent,Task,Skill,NotebookEdit,ToolSearch"

PROMPT = """You analyse a score the way a composer or theory teacher would. You never draw: you write an \
annotation list that says what to mark and where in the music, and a script engraves it.

{method}
# Annotation list format

{spec}

# The task

The score is {title}. Analyse bars {first} to {last} (the piece runs from bar {start} to bar {end}), for a student.

Note table for these bars. Each row is one beat: the lowest note, the pitch classes sounding, and every note as pitch@beat.

{table}

{draft}
{overview}{image}
Reply with the annotation list for bars {first} to {last} as one ```json block, then the commentary as plain \
text. Give `key` on the first harmony. You have no tools here; do not ask questions."""

SELFCHECK = """

Your previous reply was:

{reply}

A script compared each chord label in it with the notes that sound while the chord lasts. These labels
contradict the notes:

{problems}

For each one, either correct the label (or its inversion), or keep it if your reading explains it (a
non-chord tone, an implied note, a pedal, a seventh that only arrives later). Do not change anything else.
Reply again in full: the corrected annotation list as one ```json block, then the commentary."""

RETRY = """

Your previous reply was:

{reply}

The renderer could not use that annotation list:

{problems}

Reply again in full with those problems fixed."""


def passages(index: ScoreIndex, bars: int) -> list[tuple[int, int]]:
    numbers = [measure.number for measure in index.measures]
    chunks = [numbers[i : i + bars] for i in range(0, len(numbers), bars)]
    if len(chunks) > 1 and len(chunks[-1]) < bars // 3:  # no sliver at the end
        chunks[-2:] = [chunks[-2] + chunks[-1]]
    return [(chunk[0], chunk[-1]) for chunk in chunks]


def ask(prompt: str, model: str, effort: str | None = None, files: dict[str, bytes] | None = None) -> dict:
    """One answer from Claude Code, in an empty folder so no project context loads.

    Without `files` it has no tools. With them, the files are put in the folder and it may only Read."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("CLAUDE")}
    with tempfile.TemporaryDirectory() as folder:
        for name, data in (files or {}).items():
            (Path(folder) / name).write_bytes(data)
        blocked = NO_TOOLS.replace("Read,", "") if files else NO_TOOLS
        process = subprocess.run(
            ["claude", "-p", "--model", model, *(["--effort", effort] if effort else []), "--output-format", "json", "--disallowedTools", blocked, *(["--allowedTools", "Read"] if files else [])],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=folder,
            env=environment,
            timeout=900,
        )
    if process.returncode != 0:
        try:  # the JSON's `result` holds the reason (a usage limit, say); its tail is only statistics
            reason = json.loads(process.stdout)["result"]
        except (ValueError, KeyError, TypeError):
            reason = (process.stderr or process.stdout)[-300:]
        raise RuntimeError(f"claude exited {process.returncode}: {reason}")
    return json.loads(process.stdout)


def problems_in(reply: str, index: ScoreIndex) -> tuple[dict | None, str]:
    block = re.search(r"```json\s*(.*?)```", reply, re.DOTALL)
    if not block:
        return None, "No ```json block found."
    try:
        data = json.loads(block.group(1))
        check(AnnotationList.model_validate(data), index)
    except Exception as error:  # whatever is wrong goes back to the model in words
        return None, str(error)[:3000]
    return data, ""


def run_name(model: str, effort: str | None, tag: str | None = None) -> str:
    """The folder a run's results go in: the model, the effort when one was set, and a tag for a variant."""
    return "-".join(part for part in (model, effort, tag) if part)


OVERVIEW = """
The whole piece at a glance, from the draft (the draft's keys are right about 80% of the time; use this for the
large-scale plan, and judge the bars in front of you from their notes):

{overview}
"""


def overview(drafted: draft.Draft) -> str:
    """The draft's key plan and its cadences and phrase ends across the whole piece, in a few lines."""
    runs: list[list] = []  # [key, first measure, last measure]
    for chord in drafted.chords:
        if runs and runs[-1][0] == chord.key:
            runs[-1][2] = chord.measure
        else:
            runs.append([chord.key, chord.measure, chord.measure])
    runs = [run for run in runs if run[2] - run[1] >= 1 or run is runs[0]]  # a one-bar flicker is a tonicization
    keys = "Key areas: " + ", ".join(f"m{a}-{b} {k}" for k, a, b in runs)
    cadences = "Cadences: " + ("; ".join(f"m{c.measure} {c.label}" for c in drafted.cadences if c.confidence >= 0.5) or "none found")
    phrases = "Phrase ends: " + (", ".join(f"m{c.measure}" for c in drafted.phrase_ends if c.confidence >= 0.5) or "none found")
    return "\n".join((keys, cadences, phrases))


IMAGE = """
The engraved score of these bars is in this folder as {pages}. Before anything else, open every one of these pages \
with the Read tool and look at it: the layout shows voices, register, rests and phrasing that the table does not. \
Do not start the analysis until you have seen all of them. Use the table for exact measure numbers, beats and pitches.
"""


def review(piece: pieces.Piece, index: ScoreIndex, drafted: draft.Draft, first: int, last: int, model: str, effort: str | None = None, tag: str | None = None, image: bool = False, whole: bool = False, alternatives: bool = False, selfcheck: bool = False, start_from: str | None = None) -> dict:
    path = REVIEWED / run_name(model, effort, tag) / "passages" / f"{piece.id}_{first}-{last}.json"
    if path.exists():
        return json.loads(path.read_text())
    prompt = PROMPT.format(
        method=METHOD, spec=SPEC, title=piece.title, first=first, last=last, start=index.measures[0].number, end=index.measures[-1].number,
        table=reduce.as_text(index, first, last), draft=draft.as_text(drafted, first, last, alternatives), image="{image}",
        overview=OVERVIEW.format(overview=overview(drafted)) if whole else "",
    )  # fmt: skip
    files = {}
    if image:
        # some source files print chord symbols or analysts' labels; the reviewer must not see them
        engraving = render.engrave_pages(pieces.without_harmony(pieces.score(piece)), (first, last))
        files = {f"page-{page}.png": engraving.png(page) for page in range(1, engraving.page_count + 1)}
    prompt = prompt.replace("{image}", IMAGE.format(pages=", ".join(files)) if files else "")
    started, answers = time.time(), []
    earlier = REVIEWED / start_from / "passages" / f"{piece.id}_{first}-{last}.json" if start_from else None
    if earlier and earlier.exists():
        # reuse an earlier run's first answer, so that only what follows it differs (and is paid for)
        before = json.loads(earlier.read_text())
        answers.append({"result": "```json\n" + json.dumps({"annotations": before["annotations"]}) + "\n```\n\n" + before["commentary"], "total_cost_usd": 0})
    else:
        answers.append(ask(prompt, model, effort, files))
    data, problems = problems_in(answers[-1]["result"], index)
    if data is None:
        answers.append(ask(prompt + RETRY.format(reply=answers[-1]["result"], problems=problems), model, effort, files))
        data, problems = problems_in(answers[-1]["result"], index)
    flagged = []
    if selfcheck and data is not None:
        flagged = harmony.mismatches(data["annotations"], index)
        if flagged:
            answers.append(ask(prompt + SELFCHECK.format(reply=answers[-1]["result"], problems="\n".join(flagged[:25])), model, effort, files))
            checked, still = problems_in(answers[-1]["result"], index)
            if checked is not None:
                data, problems = checked, still
            else:
                answers.pop()  # the revision did not validate; the first answer stands
    reply = answers[-1]["result"]
    result = {
        "first": first,
        "last": last,
        "annotations": data["annotations"] if data else [],
        "commentary": re.sub(r"```json.*?```", "", reply, flags=re.DOTALL).strip(),
        "problems": problems,
        "attempts": len(answers),
        "seconds": round(time.time() - started),
        "cost_usd": round(sum(answer.get("total_cost_usd") or 0 for answer in answers), 3),
        "models": sorted({name for answer in answers for name in answer.get("modelUsage", {})}),
        "effort": effort,
        "pages_shown": len(files),
        "selfcheck_flagged": len(flagged),
        "turns": [answer.get("num_turns") for answer in answers],  # above 1 when it used Read to look at the pages
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", help="review only this piece (repeatable)")
    parser.add_argument("--model", default="opus", help="the chat model that reviews: opus (chosen 2026-10-02), sonnet, or a full model id")
    parser.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max", "none"), help="reasoning effort; 'none' leaves the model's own")
    parser.add_argument("--bars", type=int, default=24, help="bars per passage")
    parser.add_argument("--jobs", type=int, default=4, help="passages reviewed at once")
    parser.add_argument("--tag", help="name for a variant run (a changed skill, say), kept in its own folder")
    parser.add_argument("--image", action="store_true", help="also give the reviewer the engraved pages of each passage to look at")
    parser.add_argument("--selfcheck", action="store_true", help="after the review, show it the labels that contradict the notes and let it correct or keep each")
    parser.add_argument("--start-from", help="reuse this run's first answers instead of reviewing afresh (with --selfcheck: tests the check alone)")
    parser.add_argument("--alternatives", action="store_true", help="show the draft model's runner-up reading where it is a close call")
    parser.add_argument("--overview", action="store_true", help="also give the reviewer the whole piece's draft key plan, cadences and phrase ends")
    args = parser.parse_args()
    if args.effort == "none":
        args.effort = None
    jobs = []
    for piece in [pieces.BY_ID[name] for name in args.only] if args.only else pieces.PIECES:
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        drafted = cached_draft(piece, index)
        jobs += [(piece, index, drafted, first, last, args.model, args.effort, args.tag, args.image, args.overview, args.alternatives, args.selfcheck, args.start_from) for first, last in passages(index, args.bars)]
    print(f"{len(jobs)} passages", flush=True)

    def one(job) -> tuple[pieces.Piece, dict]:
        try:
            result = review(*job)
        except Exception as error:  # a failed call leaves a gap that the next run fills
            result = {"first": job[3], "last": job[4], "annotations": [], "commentary": "", "problems": f"{type(error).__name__}: {error}", "failed": True}
        print(f"{job[0].id:26s} {result['first']:4d}-{result['last']:<4d} {len(result['annotations']):3d} annotations  {result.get('seconds', 0):4d}s  {result['problems'][:80]}", flush=True)
        return job[0], result

    with ThreadPoolExecutor(args.jobs) as pool:
        done = list(pool.map(one, jobs))
    folder = REVIEWED / run_name(args.model, args.effort, args.tag)
    for piece in {piece.id: piece for piece, _ in done}.values():
        parts = [result for owner, result in done if owner is piece]
        (folder / f"{piece.id}.json").write_text(json.dumps({"version": 1, "annotations": [a for part in parts for a in part["annotations"]]}, indent=1))
        (folder / f"{piece.id}.md").write_text(
            f"# {piece.title}\n\n" + "\n\n".join(f"## Bars {part['first']} to {part['last']}\n\n{part['commentary']}" for part in parts)
        )


if __name__ == "__main__":
    main()
