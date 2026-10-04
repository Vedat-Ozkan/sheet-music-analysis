"""Check the reviewed analyses against what a teacher wrote about the same piece.

    .venv/bin/python -m eval.judge [--only ID] [--reviewer opus-medium] [--claims-from opus-medium [--repeats 3]] [--jobs 3]

Chord labels can be scored by a script (eval/run.py); a prose analysis cannot. Here a second
model reads the published analysis, lists the checkable claims it makes (keys, cadences, form,
notable chords, scales and regions), and marks whether our analysis agrees with each. The analyses
are downloaded and their text extracted here (cached in out/eval/prose/), since the model's own
web fetch cannot read most PDFs; an address that cannot be read here is left for it to fetch. Its verdicts
go to out/eval/judged/<reviewer>/<id>.json. They are a reader's judgement, not a measurement:
read the claims before quoting the counts.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby

from eval import pieces
from eval.review import REVIEWED

JUDGED = pieces.OUT / "judged"
VERDICTS = ("agree", "partly", "disagree", "not_addressed")
LIST_CLAIMS = """1. List the checkable claims the published analysis makes about this piece, most important first, at most 25: \
keys and modulations, cadences (type and bar), phrase and form boundaries, notable chords (Neapolitan, augmented \
sixth, borrowed chords, applied dominants), non-chord tones, pedal points, scales, modes and other named regions. \
Tie each to its bars. Use only what the published analysis says, not your own knowledge of the piece."""
GIVEN_CLAIMS = """1. The claims have already been listed from the published analysis. Use exactly these, in this order, \
with the same bars, kind and wording; do not add, drop or merge any:

{claims}"""

PROMPT = """You are checking a music-analysis tool's reading of a piece against a published human analysis.

The piece is {title}.
{note}
Published analysis: its text is given at the end, under "The published analysis". Addresses that could \
not be read in advance are listed here; fetch them yourself, and if one cannot be opened, say so and use the others:
{references}

{step1}
2. For each claim, compare it with the tool's analysis below and give a verdict: "agree", "partly", "disagree", \
or "not_addressed" when the tool says nothing about it. A different but equivalent label (V/V in C for V in G; \
perfect cadence for PAC) is agreement.

Reply with one ```json block and nothing else:
{{"opened": ["addresses you could read"], "failed": ["addresses you could not"],
 "claims": [{{"bars": "12-16", "kind": "cadence", "claim": "...", "verdict": "agree", "tool_says": "..."}}],
 "summary": "two or three sentences on where the tool matches the published analysis and where it does not"}}

# The tool's analysis

{analysis}

# The published analysis

{published}
"""

PROSE = pieces.OUT / "prose"
LIMIT = 200_000  # characters kept from each analysis; a dissertation's text past this is mostly appendix and bibliography


def read_text(address: str) -> str:
    """The text of a published analysis, from a PDF or a web page. Raises if it cannot be had."""
    cached = PROSE / (hashlib.sha1(address.encode()).hexdigest()[:16] + ".txt")
    if cached.exists():
        return cached.read_text()
    request = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 (score-analysis evaluation)"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if data[:5] == b"%PDF-":
        from pypdf import PdfReader  # only needed here, so the rest of eval runs without it

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    else:
        page = data.decode("utf-8", errors="replace")
        page = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page)
        text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text)
    return text


def as_text(annotations: list[dict], commentary: str) -> str:
    """An annotation list as a few lines a reader can scan."""
    lines = []
    harmonies = sorted((a for a in annotations if a["type"] == "harmony"), key=lambda a: (a["at"]["measure"], a["at"].get("beat", 1)))
    for measure, group in groupby(harmonies, key=lambda a: a["at"]["measure"]):
        lines.append(f"m{measure}: " + " | ".join((f"[key {a['key']}] " if a.get("key") else "") + f"b{a['at'].get('beat', 1):g} {a['label']}" for a in group))
    for kind, show in (
        ("cadence", lambda a: f"m{a['at']['measure']} b{a['at'].get('beat', 1):g} {a['label']}"),
        ("phrase", lambda a: f"m{a['start']['measure']}-{a['end']['measure']} {a.get('label', '')}"),
        ("region", lambda a: f"m{a['start']['measure']}-{a['end']['measure']} {a.get('label', '')}"),
        ("nct", lambda a: f"m{a['note']['measure']} b{a['note'].get('beat', 1):g} {a['note'].get('pitch', '')} {a['label']}"),
    ):
        found = [show(a) for a in annotations if a["type"] == kind]
        lines.append(f"\n{kind.upper()}S: " + ("; ".join(found) if found else "none"))
    return "CHORDS (measure: beat label)\n" + "\n".join(lines) + "\n\nCOMMENTARY\n\n" + commentary


def judge(piece: pieces.Piece, reviewer: str, claims_from: str | None = None, repeat: int | None = None) -> dict:
    """Judge one piece. With `claims_from`, reuse that run's list of claims so two runs are marked on the same list.
    `repeat` numbers one of several independent markings, kept in their own folder (see `steady`)."""
    path = JUDGED / reviewer / (f"repeat{repeat}" if repeat is not None else "") / f"{piece.id}.json"
    if path.exists():
        return json.loads(path.read_text())
    annotations = json.loads((REVIEWED / reviewer / f"{piece.id}.json").read_text())["annotations"]
    commentary = (REVIEWED / reviewer / f"{piece.id}.md").read_text()
    texts, unread = [], []
    for address in piece.prose:
        try:
            text = read_text(address)
            # a short page is a contents page (teoria.com splits an analysis into linked pages) or a scan:
            # the model's fetch, which follows links, does better there
            if len(text) < 3000:
                raise ValueError(f"only {len(text)} characters of text")
            texts.append(f"## From {address}\n\n{text[:LIMIT]}")
        except Exception as error:
            print(f"{piece.id:26s} could not read {address}: {error}", flush=True)
            unread.append(address)
    if claims_from:
        given = [{key: claim[key] for key in ("bars", "kind", "claim")} for claim in json.loads((JUDGED / claims_from / f"{piece.id}.json").read_text())["claims"]]
        step1 = GIVEN_CLAIMS.format(claims=json.dumps(given, indent=1, ensure_ascii=False))
    else:
        step1 = LIST_CLAIMS
    prompt = PROMPT.format(
        step1=step1,
        title=piece.title,
        note=f"Note on bar numbers: {piece.note}\n" if piece.note else "",
        references="\n".join(f"- {address}" for address in unread) or "(none: all were read)",
        analysis=as_text(annotations, commentary),
        published="\n\n".join(texts) or "(none could be read in advance)",
    )
    environment = {name: value for name, value in os.environ.items() if not name.startswith("CLAUDE")}
    with tempfile.TemporaryDirectory() as folder:
        process = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--allowedTools", "WebFetch", "--disallowedTools", "Bash,Write,Edit,Agent,Task,Skill"],
            input=prompt, capture_output=True, text=True, cwd=folder, env=environment, timeout=1500,
        )  # fmt: skip
    answer = json.loads(process.stdout)
    block = re.search(r"```json\s*(.*?)```", answer["result"], re.DOTALL)
    result = json.loads(block.group(1) if block else answer["result"])
    result["cost_usd"] = round(answer.get("total_cost_usd") or 0, 3)
    result["read_in_advance"] = [address for address in piece.prose if address not in unread]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1))
    return result


def steady(piece: pieces.Piece, reviewer: str, claims_from: str, repeats: int) -> dict:
    """Mark the same claims several times and keep each claim's median verdict.

    One marking is noisy (a control in docs/engineering-log.md, challenge 8, changed 24 of 185
    verdicts with nothing else changed); the median of several is steadier."""
    runs = [judge(piece, reviewer, claims_from, repeat) for repeat in range(repeats)]
    order = ["disagree", "not_addressed", "partly", "agree"]
    claims = []
    for marked in zip(*(run["claims"] for run in runs)):
        verdicts = sorted((claim["verdict"] for claim in marked), key=order.index)
        claims.append({**marked[0], "verdict": verdicts[len(verdicts) // 2], "verdicts": [claim["verdict"] for claim in marked]})
    result = {"claims": claims, "repeats": repeats, "cost_usd": round(sum(run.get("cost_usd", 0) for run in runs), 3), "failed": runs[0].get("failed", [])}
    path = JUDGED / reviewer / f"{piece.id}.json"
    path.write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", help="judge only this piece (repeatable)")
    parser.add_argument("--reviewer", default="opus-medium", help="which reviewed run to judge: a folder in out/eval/reviewed/")
    parser.add_argument("--claims-from", help="reuse the claims listed in this judged run, so the two runs compare on one list")
    parser.add_argument("--repeats", type=int, default=1, help="with --claims-from: mark each claim this many times and keep the median verdict")
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    if args.repeats > 1 and not args.claims_from:
        parser.error("--repeats needs --claims-from: the markings must be of one list of claims")
    chosen = [pieces.BY_ID[name] for name in args.only] if args.only else [piece for piece in pieces.PIECES if piece.prose]

    def one(piece: pieces.Piece) -> None:
        try:
            result = steady(piece, args.reviewer, args.claims_from, args.repeats) if args.repeats > 1 else judge(piece, args.reviewer, args.claims_from)
            counts = {verdict: sum(1 for claim in result["claims"] if claim["verdict"] == verdict) for verdict in VERDICTS}
            print(f"{piece.id:26s} " + "  ".join(f"{verdict} {count:2d}" for verdict, count in counts.items()) + f"  unread: {len(result.get('failed', []))}", flush=True)
        except Exception as error:  # a failed call leaves a gap that the next run fills
            print(f"{piece.id:26s} FAILED {type(error).__name__}: {str(error)[:200]}", flush=True)

    with ThreadPoolExecutor(args.jobs) as pool:
        list(pool.map(one, chosen))


if __name__ == "__main__":
    main()
