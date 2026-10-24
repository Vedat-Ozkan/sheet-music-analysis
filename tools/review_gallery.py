"""Make every owner-review picture from the manifest, before and after, and a review page to go with them.

    .venv/bin/python -m tools.review_gallery --out DIR [--after REF] [--before REF] [--items 1,3]
                                             [--manifest tools/review_manifest.json]

Each manifest picture names a real input (a hand-checked analysis in examples/, a real score in tests/data, or a
real PDF read through the real PDF path) and is drawn through the server's own tool functions, at two git refs:
"before" (the commit the owner flagged, per item, unless --before is given) and "after" (--after, default HEAD).
Each ref is checked out with `git worktree add` into a temporary folder and drawn by a separate Python process
that imports only that checkout's code; the folder is removed afterwards. Every image is saved at full size and at
chat width (700 px), with its input, bars, ref and commit stamped in a strip below the music.

Any picture that cannot be drawn stops the run with an error, and no review page is written: a picture that
silently goes missing (as the bar 12 "R" once did) is worse than no page. Items waiting for an owner decision
are listed as such on the page, never stood in for by another example.

PDFs are read from Audiveris's cached output (the benchmark's cache, keyed as spike/omr/bench/run.py keys it);
everything after Audiveris (cleaning, choosing a reading, clean-up, preview) runs from the ref's code. A cache
miss is an error: run the benchmark on that PDF first.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent
MANIFEST = ROOT / "tools" / "review_manifest.json"
CHAT_WIDTH = 700
ENTRIES = {"render_analysis", "check_page", "correct_bars", "read_pdf", "ledger_note"}
SHOWS = {"render_analysis": {"card_image", "card_ui"}, "check_page": {"card_image"}, "correct_bars": {"card_image"},
         "read_pdf": {"card_image", "model_pages", "card_ui"}, "ledger_note": {"text"}}
PICTURE_KEYS = {"id", "caption", "entry", "input", "analysis", "student", "replacement", "bars", "view", "style",
                "piano", "show", "pages"}
ITEM_KEYS = {"item", "title", "look_at", "before", "after", "status", "pictures", "notes"}


class GalleryError(Exception):
    pass



def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    seen = set()
    for item in manifest["items"]:
        if set(item) - ITEM_KEYS:
            raise GalleryError(f"item {item.get('item')}: unknown keys {sorted(set(item) - ITEM_KEYS)}")
        status = item.get("status", "ready")
        if status != "ready":
            if item.get("pictures"):
                raise GalleryError(f"item {item['item']}: status {status!r} but pictures are listed")
            continue
        if not item.get("pictures") or not item.get("before"):
            raise GalleryError(f"item {item['item']}: a ready item needs a before ref and pictures")
        for picture in item["pictures"]:
            where = f"item {item['item']} picture {picture.get('id')!r}"
            if set(picture) - PICTURE_KEYS:
                raise GalleryError(f"{where}: unknown keys {sorted(set(picture) - PICTURE_KEYS)}")
            for key in ("id", "caption", "entry", "input", "bars", "show"):
                if key not in picture:
                    raise GalleryError(f"{where}: missing {key!r}")
            if not re.fullmatch(r"[a-z0-9.-]+", picture["id"]) or picture["id"] in seen:
                raise GalleryError(f"{where}: id must be unique, lowercase letters, digits, dots and dashes")
            seen.add(picture["id"])
            if picture["entry"] not in ENTRIES:
                raise GalleryError(f"{where}: unknown entry {picture['entry']!r}")
            if picture["show"] not in SHOWS[picture["entry"]]:
                raise GalleryError(f"{where}: {picture['entry']} cannot show {picture['show']!r}")
            if picture["entry"] in {"render_analysis", "check_page"} and "analysis" not in picture:
                raise GalleryError(f"{where}: missing 'analysis'")
            if picture["entry"] == "check_page" and "student" not in picture:
                raise GalleryError(f"{where}: missing 'student'")
            if "pages" in picture and not (picture["entry"] == "render_analysis" and picture["pages"] == "all"
                                           or picture["entry"] == "read_pdf" and picture["show"] == "model_pages"):
                raise GalleryError(f"{where}: 'pages' is \"all\" for render_analysis or a list for read_pdf model pages")
            if picture["entry"] == "correct_bars" and "replacement" not in picture:
                raise GalleryError(f"{where}: missing 'replacement'")
    return manifest


def main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


def resolve(spec: str, manifest: dict) -> Path:
    if spec.startswith("bench:"):
        path = main_checkout() / manifest["bench"] / spec.removeprefix("bench:")
    elif spec.startswith("music21:"):
        from music21 import corpus
        path = Path(os.path.dirname(corpus.__file__)) / spec.removeprefix("music21:")
    else:
        path = ROOT / spec
    if not path.is_file():
        raise GalleryError(f"input {spec!r} not found at {path}")
    return path



def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def commit_of(ref: str) -> tuple[str, str]:
    try:
        sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        raise GalleryError(f"unknown git ref {ref!r}") from None
    return sha, git("show", "-s", "--format=%ad %s", "--date=format:%Y-%m-%d %H:%M", sha)



DRAW = re.compile(r'\s+draw (\w+) (\{.*?\})(?: -> (\{.*?\}))?(?: label "([^"]*)")?(?: direction "(\w+)")?$')
ARROW = re.compile(r'\s+arrow (\{.*?\}) -> (\{.*?\}) label "([^"]*)"$')
CALLOUT = re.compile(r'(\d+)\. m\S+ b\S+, callout at (\{.*\})$')


def draft_marks(text: str) -> list[dict]:
    marks, number = [], 0
    for line in text.splitlines():
        if re.match(r"\d+\. ", line):
            found = CALLOUT.match(line)
            if not found:
                raise GalleryError(f"unparsed draft spot line: {line!r}")
            number = int(found.group(1))
            at = json.loads(found.group(2))
            marks.append({"type": "callout", "at": {"measure": at["measure"], "beat": at["beat"]}, "number": number})
        elif line.lstrip().startswith("draw "):
            found = DRAW.match(line)
            if not found:
                raise GalleryError(f"unparsed draft draw line: {line!r}")
            kind, start, end, label, direction = found.groups()
            marks.append({"type": "voice_leading", "kind": kind, "from_note": json.loads(start), "label": label or "",
                          "callout": number, **({"to_note": json.loads(end)} if end else {}),
                          **({"direction": direction} if direction else {})})
        elif line.lstrip().startswith("arrow "):
            found = ARROW.match(line)
            if not found:
                raise GalleryError(f"unparsed draft arrow line: {line!r}")
            marks.append({"type": "voice_leading", "from_note": json.loads(found.group(1)),
                          "to_note": json.loads(found.group(2)), "label": found.group(3), "callout": number})
    return marks


def child(job_file: Path) -> None:
    job = json.loads(job_file.read_text())
    root = Path(job["root"])
    sys.path[0] = str(root)
    os.chdir(root)
    asyncio.run(draw_all(job, root))


async def draw_all(job: dict, root: Path) -> None:
    from engine import read_pdf as reader
    from engine.annotations import AnnotationList
    from engine.render import load_toolkit
    from engine.score import ScoreIndex
    from server import app

    data_dir = Path(os.environ["DATA_DIR"])
    out = Path(job["out"])
    cache = Path(job["audiveris_cache"])
    signature = job["audiveris_signature"]

    def cached_audiveris(data, audiveris, options, deadline):
        key = hashlib.sha256(data + signature.encode() + " ".join(options).encode()).hexdigest()[:32]
        meta = cache / f"{key}.json"
        if not meta.exists():
            raise GalleryError(f"no cached Audiveris output for settings {options} (key {key}); read this PDF with "
                               "spike/omr/bench/run.py first")
        saved = json.loads(meta.read_text())
        if "error" in saved:
            raise reader.ReadError(saved["error"])
        if saved.get("timeout"):
            return None
        return (cache / f"{key}.mxl").read_bytes(), saved["skipped"]

    reader.audiveris_read = cached_audiveris

    def local(url: str) -> Path:
        path = data_dir / "files" / url.rsplit("/files/", 1)[1]
        if not path.is_file():
            raise GalleryError(f"published file missing: {url}")
        return path

    def checked(result, what):
        if getattr(result, "is_error", False):
            raise GalleryError(f"{what} returned an error: {result.content[0].text}")
        return result

    async def read(picture) -> tuple:
        pdf = Path(picture["input_path"]).read_bytes()

        async def download(url):
            return pdf
        app.download = download
        attached = app.AttachedFile(download_url="https://review.invalid/score.pdf", file_id="review")
        return checked(await app.read_pdf(None, attached), "read_pdf")

    def score_id(data: bytes) -> str:
        code = "R" + hashlib.sha256(data).hexdigest()[:8].upper()
        app.store.put(f"scores/{code}", data)
        return code

    results = {}
    for picture in job["pictures"]:
        name, entry, show = picture["id"], picture["entry"], picture["show"]
        bars = picture["bars"]
        record = {"images": [], "text": None, "card": None}
        try:
            if entry == "render_analysis":
                score = Path(picture["input_path"]).read_bytes()
                if picture["analysis"] == "draft:part-writing":
                    from engine.part_writing import as_text
                    marks = draft_marks(as_text(ScoreIndex(load_toolkit(score).getMEI())))
                    if not any(mark["type"] == "voice_leading" for mark in marks):
                        raise GalleryError("the part-writing draft lists no marks for this score")
                    annotations = AnnotationList.model_validate({"annotations": marks})
                    record["marks"] = sum(mark["type"] == "voice_leading" for mark in marks)
                else:
                    annotations = AnnotationList.model_validate_json(Path(picture["analysis_path"]).read_text())
                if picture.get("style"):
                    annotations = annotations.model_copy(update={"style": picture["style"]})
                result = checked(await app.render_analysis(None, score_id(score), annotations, bars,
                                                           picture.get("view", "all"), picture.get("piano", False)),
                                 "render_analysis")
                content = result.structured_content
                if show == "card_ui":
                    record["card"] = card_output(content, local, out, name)
                else:
                    target = out / f"{name}-p1.png"
                    shutil.copy(local(content["image_url"]), target)
                    record["images"].append(target.name)
                if picture.get("pages") == "all":
                    from engine.annotate import render
                    engraving = render(score, annotations, measures=app.parse_measures(bars),
                                       view=picture.get("view", "all"), piano=picture.get("piano", False))
                    if engraving.png(1, width=2800, colors=256) != local(content["image_url"]).read_bytes():
                        raise GalleryError("the engine's page 1 differs from the tool's card image")
                    for number in range(2, engraving.page_count + 1):
                        target = out / f"{name}-p{number}.png"
                        target.write_bytes(engraving.png(number, width=2800, colors=256))
                        record["images"].append(target.name)
            elif entry == "check_page":
                from engine.annotate import render
                from engine.check_analysis import from_text
                score = Path(picture["input_path"]).read_bytes()
                annotations = AnnotationList.model_validate_json(Path(picture["analysis_path"]).read_text())
                index = ScoreIndex(load_toolkit(score).getMEI())
                labels = from_text(Path(picture["student_path"]).read_text(), index=index)
                first, _, last = bars.partition("-")
                page = render(score, annotations, measures=(int(first), int(last or first)), student_labels=labels)
                target = out / f"{name}-p1.png"
                target.write_bytes(page.png(1, width=2800, colors=256))
                record["images"].append(target.name)
            elif entry == "read_pdf":
                result = await read(picture)
                content = result.structured_content
                if show == "card_image":
                    target = out / f"{name}-p1.png"
                    shutil.copy(local(content["image_url"]), target)
                    record["images"].append(target.name)
                elif show == "card_ui":
                    record["card"] = card_output(content, local, out, name)
                else:
                    pages = [part for part in result.content if part.type == "image"]
                    for number in picture.get("pages", [1]):
                        if number > len(pages):
                            raise GalleryError(f"page {number} asked for, but the reading has {len(pages)} pages")
                        target = out / f"{name}-p{number}.png"
                        target.write_bytes(base64.b64decode(pages[number - 1].data))
                        record["images"].append(target.name)
                record["text"] = next(part.text for part in result.content if part.type == "text")
            elif entry == "correct_bars":
                reading = await read(picture)
                reading_id = re.search(r"score_id: (\S+)", reading.content[-1].text).group(1)
                replacement = picture["replacement_text"]
                result = checked(await app.correct_bars(None, reading_id, replacement), "correct_bars")
                content = result.structured_content
                if not content["image_urls"]:
                    raise GalleryError("correct_bars changed no bars")
                for number, url in enumerate(content["image_urls"], 1):
                    target = out / f"{name}-p{number}.png"
                    shutil.copy(local(url), target)
                    record["images"].append(target.name)
                record["text"] = "\n".join(content["notes"].values())
            elif entry == "ledger_note":
                from engine import ledger
                if picture["input_path"].endswith(".pdf"):
                    reading = reader.read_pdf(Path(picture["input_path"]).read_bytes(), audiveris="cached")
                    score = reader.without_slurs(reading.musicxml)
                else:
                    score = Path(picture["input_path"]).read_bytes()
                mei = load_toolkit(score).getMEI()
                first, last = (None, None) if bars == "all" else (int(bars.partition("-")[0]), int(bars.partition("-")[2] or bars.partition("-")[0]))
                record["text"] = ledger.as_text(mei, ScoreIndex(mei), first, last)
                if not record["text"]:
                    raise GalleryError("the ledger note is empty for this input")
        except Exception as error:
            raise GalleryError(f"picture {name!r} ({entry}) at {root}: {type(error).__name__}: {error}") from error
        results[name] = record
    (out / "result.json").write_text(json.dumps(results, indent=1))


def card_output(content: dict, local, out: Path, name: str) -> dict:
    image = out / f"{name}-card-source.png"
    shutil.copy(local(content["image_url"]), image)
    return {**content, "image_url": image.as_uri()}



SHOOT = r"""
import json, sys
from playwright.sync_api import sync_playwright
card, data, target, scale = sys.argv[1], json.loads(open(sys.argv[2]).read()), sys.argv[3], int(sys.argv[4])
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": %d, "height": 900}, device_scale_factor=scale)
    page.add_init_script("window.openai = {toolOutput: %%s, openExternal: function () {}}" %% json.dumps(data))
    page.goto("file://" + card)
    page.wait_for_function("document.getElementById('page').complete && document.getElementById('page').naturalWidth > 0")
    page.screenshot(path=target, full_page=True)
    browser.close()
""" % CHAT_WIDTH


def shoot_card(card_html: Path, content: dict, folder: Path, name: str) -> tuple[Path, Path]:
    if not card_html.is_file():
        raise GalleryError(f"no card page at {card_html}")
    data = folder / f"{name}-card.json"
    data.write_text(json.dumps(content))
    shots = []
    for scale in (2, 1):
        target = folder / f"{name}-card-x{scale}.png"
        done = subprocess.run(["/usr/bin/python3", "-c", SHOOT, str(card_html), str(data), str(target), str(scale)],
                              capture_output=True, text=True, timeout=120)
        if done.returncode or not target.is_file():
            raise GalleryError(f"card screenshot failed for {name}: {done.stderr.strip()[-800:]}")
        shots.append(target)
    return shots[0], shots[1]



def stamp(image_path: Path, lines: list[str], target: Path, width: int | None = None) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.open(image_path).convert("RGB")
    if width and image.width != width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    size = max(11, round(image.width / 120))
    font = ImageFont.load_default(size=size)
    pad = round(size * 0.6)
    strip = pad * 2 + len(lines) * round(size * 1.3)
    out = Image.new("RGB", (image.width, image.height + strip), "white")
    out.paste(image, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.line([(0, image.height), (image.width, image.height)], fill="#c8c8c8", width=1)
    for number, line in enumerate(lines):
        draw.text((pad, image.height + pad + number * round(size * 1.3)), line, fill="#555555", font=font)
    out.save(target, optimize=True)



def run(args) -> int:
    manifest = load_manifest(args.manifest)
    wanted = {int(n) for n in args.items.split(",")} if args.items else None
    items = [item for item in manifest["items"] if wanted is None or item["item"] in wanted]
    if wanted and {item["item"] for item in items} != wanted:
        raise GalleryError(f"no such items: {sorted(wanted - {item['item'] for item in items})}")
    out = args.out.resolve()
    images = out / "img"
    if images.exists() and any(images.iterdir()):
        raise GalleryError(f"{images} already has files; choose a new folder")
    images.mkdir(parents=True, exist_ok=True)

    refs = {}
    jobs = {}
    for item in items:
        if item.get("status", "ready") != "ready":
            continue
        sides = {"before": args.before or item["before"], "after": args.after or item.get("after") or "HEAD"}
        item["_refs"] = {}
        for side, ref in sides.items():
            sha, about = commit_of(ref)
            refs[sha] = about
            item["_refs"][side] = (ref, sha)
            for picture in item["pictures"]:
                resolved = dict(picture)
                resolved["input_path"] = str(resolve(picture["input"], manifest))
                for key in ("analysis", "student"):
                    if key in picture and not picture[key].startswith("draft:"):
                        resolved[f"{key}_path"] = str(resolve(picture[key], manifest))
                if "replacement" in picture:
                    resolved["replacement_text"] = replacement_text(picture["replacement"], manifest)
                jobs.setdefault(sha, {})[picture["id"]] = resolved

    scratch = Path(tempfile.mkdtemp(prefix="review-gallery-"))
    trees = {}
    try:
        cache = main_checkout() / manifest["audiveris"]["cache"]
        processes = {}
        for sha, pictures in jobs.items():
            tree = scratch / f"tree-{sha[:10]}"
            git("worktree", "add", "--detach", str(tree), sha)
            trees[sha] = tree
            work = scratch / f"out-{sha[:10]}"
            data_dir = scratch / f"data-{sha[:10]}"
            work.mkdir()
            job = {"root": str(tree), "out": str(work), "pictures": list(pictures.values()),
                   "audiveris_cache": str(cache), "audiveris_signature": manifest["audiveris"]["signature"]}
            job_file = scratch / f"job-{sha[:10]}.json"
            job_file.write_text(json.dumps(job))
            env = {**os.environ, "DATA_DIR": str(data_dir), "PYTHONPATH": str(tree)}
            env.pop("BUCKET", None)
            print(f"drawing {len(pictures)} pictures at {sha[:10]} {refs[sha]}", flush=True)
            processes[sha] = subprocess.Popen([sys.executable, str(HERE), "--child", str(job_file)], cwd=tree, env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        failed = []
        for sha, process in processes.items():
            output, _ = process.communicate()
            if process.returncode:
                failed.append(f"--- at {sha[:10]}:\n{output.strip()[-3000:]}")
        if failed:
            raise GalleryError("could not draw every picture; no review page was written.\n" + "\n".join(failed))

        sources = []
        for item in items:
            if item.get("status", "ready") != "ready":
                continue
            item["_shown"] = []
            for picture in item["pictures"]:
                pair = {}
                for side in ("before", "after"):
                    ref, sha = item["_refs"][side]
                    work = scratch / f"out-{sha[:10]}"
                    record = json.loads((work / "result.json").read_text())[picture["id"]]
                    pair[side] = finish(picture, record, side, ref, sha, refs[sha], work, trees[sha], images, manifest)
                    sources.extend(pair[side]["sources"])
                item["_shown"].append((picture, pair))
        (out / "sources.json").write_text(json.dumps(sources, indent=1, ensure_ascii=False))
        (out / "index.html").write_text(page(manifest, items, out.name), encoding="utf-8")
    finally:
        for tree in trees.values():
            subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT, capture_output=True)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"review page: {out / 'index.html'}")
    return 0


def replacement_text(spec: dict, manifest: dict) -> str:
    from engine.correct import bars_from_musicxml
    first, _, last = spec["bars"].partition("-")
    return bars_from_musicxml(resolve(spec["from"], manifest).read_bytes(), int(first), int(last) if last else None)


def describe(picture: dict) -> str:
    parts = [picture["input"]]
    if picture.get("analysis"):
        parts.append("marks from the part-writing draft" if picture["analysis"] == "draft:part-writing" else picture["analysis"])
    if picture.get("student"):
        parts.append(f"student numerals {picture['student']}")
    if picture.get("replacement"):
        parts.append(f"bar {picture['replacement']['bars']} from {picture['replacement']['from']}")
    return " + ".join(parts)


def finish(picture, record, side, ref, sha, about, work, tree, images, manifest) -> dict:
    view = ", ".join(filter(None, [f"view {picture.get('view', 'all')}" if picture["entry"] == "render_analysis" else "",
                                   f"style {picture['style']}" if picture.get("style") else "",
                                   "piano" if picture.get("piano") else "", picture["entry"]]))
    head = f"{describe(picture)} | bars {picture['bars']} | {view}"
    tail = f"{side}: ref {ref} = commit {sha[:10]} ({about[:16]})"
    shown = {"images": [], "text": record.get("text"), "sources": [], "marks": record.get("marks")}
    files = []
    if record.get("card"):
        tree_card = tree / "server" / "card.html"
        full, chat = shoot_card(tree_card, record["card"], work, picture["id"])
        files.append(("card", full, chat))
    for name in record["images"]:
        files.append((name.removesuffix(".png").rsplit("-", 1)[1], work / name, work / name))
    if picture["entry"] != "ledger_note" and not files:
        raise GalleryError(f"picture {picture['id']!r} at {sha[:10]} produced no image")
    for part, full_source, chat_source in files:
        base = f"{picture['id']}-{part}-{side}"
        lines = [head, tail + {"card": " | card as shown in the chat", "p1": ""}.get(part, f" | page {part[1:]}")]
        stamp(full_source, lines, images / f"{base}-full.png")
        stamp(chat_source, lines, images / f"{base}-700.png", width=CHAT_WIDTH)
        digest = hashlib.sha256(full_source.read_bytes()).hexdigest()
        shown["images"].append({"full": f"img/{base}-full.png", "chat": f"img/{base}-700.png", "part": part,
                                "digest": digest})
        shown["sources"].append({"image": f"img/{base}-full.png", "chat_image": f"img/{base}-700.png",
                                 "stamp": lines, "item_picture": picture["id"], "side": side, "ref": ref,
                                 "commit": sha, "input": picture["input"],
                                 "input_sha256": hashlib.sha256(resolve(picture["input"], manifest).read_bytes()).hexdigest()})
    if picture["entry"] == "ledger_note":
        shown["sources"].append({"text": picture["id"], "stamp": [head, tail], "side": side, "ref": ref, "commit": sha,
                                 "input": picture["input"]})
    shown["stamp"] = [head, tail]
    return shown



def page(manifest: dict, items: list[dict], folder: str) -> str:
    esc = html.escape
    body = []
    for item in items:
        status = item.get("status", "ready")
        parts = [f'<section class="item" id="item-{item["item"]}"><h2><span class="num">{item["item"]}</span>{esc(item["title"])}</h2>']
        if item.get("look_at"):
            parts.append(f"<p>{esc(item['look_at'])}</p>")
        if status != "ready":
            parts.append(f'<div class="missing"><strong>{esc(status)}.</strong> {esc(item.get("notes", ""))}</div>')
        else:
            (bref, bsha), (aref, asha) = item["_refs"]["before"], item["_refs"]["after"]
            parts.append(f'<p class="status">Before: <code>{esc(bref)}</code> ({bsha[:10]}). After: <code>{esc(aref)}</code> ({asha[:10]}).'
                         f'{" " + esc(item["notes"]) if item.get("notes") else ""}</p>')
            for picture, pair in item["_shown"]:
                parts.append(f'<h3>{esc(picture["caption"])}</h3><p class="src">{esc(pair["after"]["stamp"][0])}</p>')
                if picture["entry"] == "ledger_note":
                    parts.append('<div class="pair">' + "".join(
                        f'<figure><figcaption class="{side[0]}">{side.title()}</figcaption><pre>{esc(pair[side]["text"] or "")}</pre>'
                        f'<p class="stamp">{esc(pair[side]["stamp"][1])}</p></figure>' for side in ("before", "after")) + "</div>")
                    continue
                before, after = pair["before"]["images"], pair["after"]["images"]
                for number in range(max(len(before), len(after))):
                    left = before[number] if number < len(before) else None
                    right = after[number] if number < len(after) else None
                    same = left and right and left["digest"] == right["digest"]
                    label = (left or right)["part"]
                    if max(len(before), len(after)) > 1:
                        parts.append(f'<p class="part">{esc(label)}</p>')
                    parts.append('<div class="pair">' + figure("Before", "b", left) + figure("After", "a", right) + "</div>")
                    if same:
                        parts.append('<p class="same">Before and after are the same picture (identical pixels).</p>')
                if pair["after"]["text"] and picture["entry"] in {"read_pdf", "correct_bars"}:
                    parts.append('<details><summary>What the model is told (before / after)</summary><div class="pair">'
                                 + "".join(f'<pre>{esc(pair[side]["text"] or "")}</pre>' for side in ("before", "after"))
                                 + "</div></details>")
        parts.append(f'<label for="note-{item["item"]}">Your notes on item {item["item"]}</label>'
                     f'<textarea id="note-{item["item"]}" data-item="{item["item"]}"></textarea></section>')
        body.append("".join(parts))
    return PAGE.replace("{{BODY}}", "\n".join(body)).replace("{{KEY}}", json.dumps(f"review-gen-{folder}-note-")).replace(
        "{{TITLE}}", esc(manifest.get("title", "Review")))


def figure(caption: str, css: str, image: dict | None) -> str:
    if not image:
        return f'<figure><figcaption class="{css}">{caption}</figcaption><div class="missing">No such page on this side.</div></figure>'
    return (f'<figure><figcaption class="{css}">{caption} <a href="{image["full"]}" target="_blank">full size</a></figcaption>'
            f'<a class="pic" href="{image["full"]}" target="_blank"><img src="{image["chat"]}" alt="{caption}" loading="lazy"></a></figure>')


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root { --bg:#fbfaf7; --panel:#fff; --text:#1d1d1f; --muted:#5b5b63; --line:#dddad3; --accent:#8a3b12;
  --before:#a33a2a; --after:#2f6b3a; --img-bg:#fff; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#17171a; --panel:#212126; --text:#ebebef;
  --muted:#a8a8b3; --line:#36363d; --accent:#e3a27a; --before:#f08a7a; --after:#8fd19c; } }
:root[data-theme="dark"] { --bg:#17171a; --panel:#212126; --text:#ebebef; --muted:#a8a8b3; --line:#36363d;
  --accent:#e3a27a; --before:#f08a7a; --after:#8fd19c; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:1240px; margin:0 auto; padding:24px 16px 90px; }
h1 { font-size:1.7rem; margin:0 0 6px; } h2 { font-size:1.3rem; margin:0 0 8px; }
h3 { font-size:1rem; margin:22px 0 2px; color:var(--muted); }
.intro, .status, .src, .stamp, .part { color:var(--muted); } .src, .stamp { font-size:.8rem; margin:0 0 8px; word-break:break-word; }
.item { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:20px; margin:26px 0; }
.num { display:inline-block; min-width:2em; padding:0 8px; margin-right:8px; border-radius:99px; background:var(--accent);
  color:var(--bg); text-align:center; font-weight:700; }
.pair { display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }
@media (max-width:760px) { .pair { grid-template-columns:1fr; } }
figure { margin:0; } figcaption { font-size:.85rem; font-weight:700; margin-bottom:4px; }
figcaption a { font-weight:400; color:var(--muted); margin-left:8px; }
figcaption.b { color:var(--before); } figcaption.a { color:var(--after); }
a.pic { display:block; background:var(--img-bg); border:1px solid var(--line); border-radius:6px; padding:4px; }
a.pic img { display:block; width:100%; height:auto; }
pre { white-space:pre-wrap; background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:10px; font-size:.85rem; }
.missing { padding:14px; border:2px dashed var(--line); border-radius:6px; color:var(--muted); }
.same { color:var(--muted); font-style:italic; }
label { display:block; font-weight:600; margin:16px 0 4px; }
textarea { width:100%; min-height:90px; padding:10px; font:inherit; color:var(--text); background:var(--bg);
  border:1px solid var(--line); border-radius:6px; resize:vertical; }
button { font:inherit; font-weight:600; padding:10px 18px; border-radius:8px; border:0; background:var(--accent); color:var(--bg); cursor:pointer; }
button.quiet { background:none; color:var(--muted); border:1px solid var(--line); }
.bar { position:sticky; bottom:0; background:var(--bg); border-top:1px solid var(--line); padding:10px 16px; display:flex;
  gap:12px; align-items:center; justify-content:center; flex-wrap:wrap; }
#copied { color:var(--muted); font-size:.9rem; }
</style></head>
<body><main>
<h1>{{TITLE}}</h1>
<p class="intro">Each "before" is the version you flagged; each "after" is the new version. Every picture was drawn by
<code>tools/review_gallery.py</code> from the inputs in <code>tools/review_manifest.json</code>, through the same code
users get, and the strip under each picture names its input, bars, version and commit. Click a picture to open it full
size. Type your notes in the box under each item (they stay in this browser), then press "Copy all my notes" and paste
them into the chat.</p>
{{BODY}}
</main>
<div class="bar"><button id="copy">Copy all my notes</button><button id="theme" class="quiet">Light / dark</button><span id="copied"></span></div>
<script>
(function () {
  var KEY = {{KEY}};
  var boxes = document.querySelectorAll("textarea[data-item]");
  boxes.forEach(function (box) {
    try { var saved = localStorage.getItem(KEY + box.dataset.item); if (saved) box.value = saved; } catch (e) {}
    box.addEventListener("input", function () {
      try { localStorage.setItem(KEY + box.dataset.item, box.value); } catch (e) {}
    });
  });
  var root = document.documentElement;
  try { var theme = localStorage.getItem(KEY + "theme"); if (theme) root.dataset.theme = theme; } catch (e) {}
  document.getElementById("theme").addEventListener("click", function () {
    var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem(KEY + "theme", root.dataset.theme); } catch (e) {}
  });
  var message = document.getElementById("copied");
  document.getElementById("copy").addEventListener("click", function () {
    var parts = [];
    boxes.forEach(function (box) { parts.push("Item " + box.dataset.item + ": " + (box.value.trim() || "(no notes)")); });
    var text = document.title + " notes\\n\\n" + parts.join("\\n\\n");
    function fallback() {
      var area = document.createElement("textarea");
      area.value = text; document.body.appendChild(area); area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(area);
      message.textContent = ok ? "Copied. Paste it into the chat." : "Could not copy automatically; select the notes and copy by hand.";
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { message.textContent = "Copied. Paste it into the chat."; }, fallback);
    } else { fallback(); }
  });
})();
</script>
</body></html>
"""


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="folder for the images and index.html (new or empty)")
    parser.add_argument("--after", help="git ref for the after pictures (default: each item's after, else HEAD)")
    parser.add_argument("--before", help="git ref for every before picture (default: each item's flagged commit)")
    parser.add_argument("--items", help="comma-separated item numbers (default: all)")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        return run(args)
    except GalleryError as error:
        print(f"review_gallery: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
