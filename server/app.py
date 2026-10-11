"""The production MCP server for Sheet Music Analysis.

Claude users reach it through the plugin's skill, which sends a note list to `draft_from_notes`.
ChatGPT users send the attached score itself to `draft_analysis` and see the page in a card.

Run locally:  .venv/bin/python -m server.app
On Cloud Run: see server/deploy.sh. Set BUCKET to keep scores, pages and daily counts in Cloud Storage.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import anyio
import httpx
import uvicorn
from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Icon, ImageContent, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import Response

from engine import draft
from engine import notes as note_list
from engine import read_pdf as pdf_reader
from engine import reduce
from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList
from engine.render import ScoreError, engrave, engrave_tall, load_toolkit
from engine.score import PositionError, ScoreIndex

PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
BUCKET = os.environ.get("BUCKET")
MAX_SCORE_BYTES = 10 * 1024 * 1024
# Keeps a month's work inside Cloud Run's free tier (owner's $5 limit, 2026-10-06). Counts reset at midnight UTC.
# A PDF read counts its pages (owner, 2026-10-11; cost in log 32).
DAILY_LIMITS = {"draft": 100, "render": 200, "pdf_page": 150}
MAX_PDF_PAGES = 12
# Hosts keep a card's HTML by its address, so the version goes up whenever the HTML changes. The PDF card is the
# same file under its own address: the notice above the page was added for it, and render results never set one,
# so hosts still holding the v1 HTML show analyses exactly as before.
CARD_URI = "ui://sheet-music-analysis/card-v1.html"
PDF_CARD_URI = "ui://sheet-music-analysis/pdf-card-v1.html"
HERE = Path(__file__).parent

def read_only(title: str) -> ToolAnnotations:
    # Directories read the name from annotations.title, chat hosts from the tool's own title.
    return ToolAnnotations(title=title, read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


class LocalStore:
    def __init__(self, folder: Path):
        self.folder = folder

    def put(self, key: str, data: bytes) -> None:
        path = self.folder / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self.folder / key
        return path.read_bytes() if path.is_file() else None


class BucketStore:
    """Cloud Run's disk lives in memory and is lost when the instance stops, so everything goes to a bucket.
    The bucket deletes objects after a day (lifecycle rule set in server/deploy.sh)."""

    def __init__(self, name: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(name)

    def put(self, key: str, data: bytes) -> None:
        self.bucket.blob(key).upload_from_string(data)

    def get(self, key: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            return self.bucket.blob(key).download_as_bytes()
        except NotFound:
            return None


store = BucketStore(BUCKET) if BUCKET else LocalStore(Path(os.environ.get("DATA_DIR", "out/server")))
counter_lock = asyncio.Lock()
# Audiveris peaks at about 1.3 GB beside up to four drafts in 4 GiB (log 32), so one PDF is read at a time.
pdf_lock = asyncio.Lock()


def platform(ctx: Context | None) -> str:
    try:
        headers = ctx.headers if ctx else None
    except Exception:
        headers = None
    return client_of(headers)


def client_of(headers) -> str:
    agent = (dict(headers or {}).get("user-agent") or "").lower()
    return "claude" if "claude" in agent else "chatgpt" if "openai" in agent else "other"


def log(event: str, **details) -> None:
    """One JSON line per event; Cloud Run keeps stdout as the log. Never log score contents or chat text."""
    print(json.dumps({"event": event, **details}), file=sys.stdout, flush=True)


async def take(kind: str, source: str, amount: int = 1) -> bool:
    """Count `amount` units of work for today; False if they would go over the day's limit for that kind.
    The day's file is also the usage record (per kind and platform), so it is kept outside the day-old cleanup."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"usage/{day}.json"
    async with counter_lock:
        raw = await anyio.to_thread.run_sync(store.get, key)
        counts = json.loads(raw) if raw else {}
        if counts.get(kind, 0) + amount > DAILY_LIMITS[kind]:
            return False
        counts[kind] = counts.get(kind, 0) + amount
        counts[f"{kind}:{source}"] = counts.get(f"{kind}:{source}", 0) + amount
        await anyio.to_thread.run_sync(store.put, key, json.dumps(counts).encode())
    return True


LIMIT_MESSAGE = (
    "Sheet Music Analysis has reached its daily limit; it resets at midnight UTC. "
    "Tell the user plainly that the free service is at capacity for today and to try again tomorrow."
)

SCORE_INPUT_HELP = (
    "Give the score in exactly one way. score_file: a file the user attached to the chat. "
    "score_id: the id returned by an earlier draft_analysis or read_pdf. "
    "Never encode, paste or retype a file's contents. If the user has not attached a score, ask them to attach "
    "their MusicXML file (.mxl or .musicxml) to the chat."
)


class AttachedFile(BaseModel):
    """A chat attachment as ChatGPT passes it for parameters listed in openai/fileParams."""

    model_config = ConfigDict(extra="ignore")

    download_url: str
    file_id: str
    mime_type: str | None = None
    file_name: str | None = None


def is_public_https(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, 443)}
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(address).is_global for address in addresses)


async def download(url: str) -> bytes:
    if not is_public_https(url):
        raise ScoreError("The attached file's link is not a public https URL")
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        response = await client.get(url)
    response.raise_for_status()
    if len(response.content) > MAX_SCORE_BYTES:
        raise ScoreError("The score file is larger than 10 MB")
    return response.content


def clean_id(score_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", score_id).upper()


async def resolve_score(score_file: AttachedFile | None, score_id: str | None) -> tuple[bytes, str]:
    """Return the score bytes and which input path supplied them."""
    if score_file:
        data = await download(score_file.download_url)
        if data.startswith(b"%PDF"):
            raise ScoreError("This file is a PDF. Call read_pdf with it first, then use the score_id it returns.")
        return data, "score_file"
    if score_id:
        data = await anyio.to_thread.run_sync(store.get, f"scores/{clean_id(score_id)}")
        if data is None:
            raise ScoreError(f"No score has the id {score_id!r}; scores are kept for one day")
        return data, "score_id"
    raise ScoreError("No score was provided. Ask the user to attach their MusicXML file (.mxl or .musicxml) to the chat.")


def publish(data: bytes, extension: str) -> str:
    name = f"{secrets.token_urlsafe(12)}.{extension}"
    store.put(f"files/{name}", data)
    return f"{PUBLIC_BASE_URL}/files/{name}"


def error_result(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def parse_measures(measure_range: str) -> tuple[int, int] | None:
    if measure_range == "all":
        return None
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", measure_range)
    if not match:
        raise ScoreError('measure_range must look like "1-8", or be "all"')
    return int(match[1]), int(match[2])


# The analysis rules are the skill's own (from "## Method" on), so ChatGPT and Claude analyse the same way.
SKILL_RULES = re.sub(r"<!--.*?-->\n+", "", (HERE.parent / "skill" / "SKILL.md").read_text().split("## Method", 1)[1])
REVIEW_GUIDE = (
    "HOW TO USE THIS DRAFT\n"
    "The draft above is a neural model's starting point, right about half the time on full chord labels. Check "
    "each line against the NOTES table, analyse following the method below, then call render_analysis with the "
    "score_id and your annotation list (its `view` argument draws one layer: harmony, voice_leading or form), "
    "show the page and write the commentary.\n"
    "Positions: `measure` is the printed number (a pickup is 0); `beat` is 1-based in the unit given above; "
    "`pitch` is like \"Eb4\" at sounding pitch; `staff` 1 is the top staff.\n\n"
    "## Method" + SKILL_RULES
)


def make_draft(score: bytes, code: str, measures: tuple[int, int] | None) -> str:
    index = ScoreIndex(load_toolkit(score).getMEI())
    cached = store.get(f"scores/{code}.draft.json")
    if cached:
        raw = json.loads(cached)
    else:
        raw = draft.MODELS["analysisgnn"](note_list.encode(index).encode(), "notes")
        store.put(f"scores/{code}.draft.json", json.dumps(raw).encode())
    result = draft.build(raw, index)
    first, last = measures or (None, None)
    unit = index.measure(first or index.measures[-1].number).beat_length
    numbers = f"{index.measures[0].number} to {index.measures[-1].number}"
    return (
        f"score_id: {code}\nThe score has measures {numbers}. One beat = {float(unit):g} quarter notes.\n\n"
        + draft.as_text(result, first, last)
        + "\n\nNOTES (one row per beat: lowest note, pitch classes, every note as pitch@beat)\n"
        + reduce.as_text(index, first, last)
        + "\n\n"
        + REVIEW_GUIDE
    )


apps = Apps()


@apps.tool(
    resource_uri=CARD_URI,
    title="Draw the analysis on the score",
    description=(
        "Use this after draft_analysis, once you have reviewed the draft, to draw your analysis on the engraved "
        "score. Takes the score_id and your annotation list and returns the page as an image plus PNG and PDF "
        "links, shown to the user in a card. If a position does not exist in the score, the error lists each "
        "problem so you can fix the list and call again. A page shows at most 32 bars: for a longer piece, pass "
        "measure_range (e.g. 1-16) and draw it passage by passage. view is one of all, harmony, voice_leading, form. "
        "piano=true draws the same annotation list (written for the original score) on a two-staff piano reduction "
        "with instrument cues. For a score with more than four staves, draw the original first, then offer the user "
        "the piano reduction once; call again with piano=true only if they accept."
    ),
    annotations=read_only("Draw the analysis on the score"),
    meta={"openai/outputTemplate": CARD_URI},
)
async def render_analysis(
    ctx: Context,
    score_id: str,
    annotations: AnnotationList,
    measure_range: str = "all",
    view: str = "all",
    piano: bool = False,
) -> CallToolResult:
    source = platform(ctx)
    if not await take("render", source):
        log("limit", tool="render_analysis", platform=source)
        return error_result(LIMIT_MESSAGE)
    try:
        score, _ = await resolve_score(None, score_id)
        measures = parse_measures(measure_range)
        engraving = await anyio.to_thread.run_sync(lambda: render(score, annotations, measures=measures, view=view, piano=piano))
    except AnnotationError as error:
        log("render_analysis", platform=source, problems=len(error.problems))
        return error_result("Fix these annotations and call again:\n" + "\n".join(error.problems))
    except (ScoreError, PositionError) as error:
        log("render_analysis", platform=source, error=str(error))
        return error_result(str(error))
    png = engraving.png(1)
    # The card shows a double-resolution page, sharp on high-density screens; the model gets the small one.
    image_url, pdf_url = await anyio.to_thread.run_sync(
        lambda: (publish(engraving.png(1, width=2800, colors=256), "png"), publish(engraving.pdf(), "pdf"))
    )
    caption = f"Analysis, measures {measure_range}, view {view}" + (", piano reduction" if piano else "")
    log("render_analysis", platform=source, annotations=len(annotations.annotations), png_bytes=len(png), piano=piano,
        view=view, measure_range=measure_range)
    # The card shows the page to the user; the image lets the chat model check its own annotations.
    return CallToolResult(
        content=[
            ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"),
            TextContent(type="text", text=f"{caption}, shown in a card. PDF: {pdf_url}"),
        ],
        structured_content={"image_url": image_url, "pdf_url": pdf_url, "caption": caption},
    )


apps.add_html_resource(
    CARD_URI,
    (HERE / "card.html").read_text(),
    name="Analysis card",
    csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
    domain="https://sheetmusicanalysis.com",  # ChatGPT requires a dedicated origin for a submitted plugin's UI
    prefers_border=True,
)

BUSY_MESSAGE = (
    "Another PDF is being read right now. Tell the user plainly that the service is busy and to try again in a minute."
)


@apps.tool(
    resource_uri=PDF_CARD_URI,
    title="Read a PDF of sheet music",
    description=(
        "Use this when the user attaches a PDF of printed sheet music (born-digital or scanned) and wants it analysed. "
        "Reads the music from the PDF and shows the user the engraved result in a card, so they can check it against "
        "their copy. Returns a score_id. Do not analyse yet: wait until the user says to go ahead, then call "
        f"draft_analysis with that score_id. PDFs of more than {MAX_PDF_PAGES} pages are refused. Slurs are left out "
        "unless keep_slurs is true; set it only when the user asks for them."
    ),
    annotations=read_only("Read a PDF of sheet music"),
    meta={"openai/outputTemplate": PDF_CARD_URI, "openai/fileParams": ["pdf_file"]},
)
async def read_pdf(ctx: Context, pdf_file: AttachedFile, keep_slurs: bool = False) -> CallToolResult:
    source = platform(ctx)
    started = time.time()
    try:
        data = await download(pdf_file.download_url)
        if not data.startswith(b"%PDF"):
            raise ScoreError("This file is not a PDF. Ask the user to attach a PDF of the printed music or a MusicXML file.")
        # Kept by the file's hash, so the same PDF is never read twice (it expires with the scores, after a day).
        cache_key = f"scores/pdf-{hashlib.sha256(data).hexdigest()}.json"
        cached = await anyio.to_thread.run_sync(store.get, cache_key)
        if cached:
            reading = json.loads(cached)
        else:
            pages = len(pdf_reader.open_pdf(data).pages)
            if pages > MAX_PDF_PAGES:
                log("read_pdf", platform=source, error="too many pages", pages=pages)
                return error_result(
                    f"This PDF has {pages} pages; the most that can be read is {MAX_PDF_PAGES}. Tell the user plainly, "
                    f"and suggest they attach a PDF of just the pages they want analysed."
                )
            if pdf_lock.locked():
                log("read_pdf", platform=source, busy=True)
                return error_result(BUSY_MESSAGE)
            async with pdf_lock:
                if not await take("pdf_page", source, pages):
                    log("limit", tool="read_pdf", platform=source, pages=pages)
                    return error_result(LIMIT_MESSAGE)
                result = await anyio.to_thread.run_sync(pdf_reader.read_pdf, data)
            reading = {"score_id": secrets.token_hex(3).upper(), "pages": result.pages, "scan": result.scan,
                       "skipped": result.skipped}
            await anyio.to_thread.run_sync(store.put, f"scores/{reading['score_id']}", result.musicxml)
            await anyio.to_thread.run_sync(store.put, cache_key, json.dumps(reading).encode())
        # The cache holds the reading with its slurs; the slur choice is applied on each call, under its own id.
        score, _ = await resolve_score(None, reading["score_id"])
        score_id = reading["score_id"] if keep_slurs else reading["score_id"] + "N"
        if not keep_slurs:
            score = pdf_reader.without_slurs(score)
            await anyio.to_thread.run_sync(store.put, f"scores/{score_id}", score)
        # The card shows every bar in one tall image; the PDF keeps ordinary pages for printing.
        tall, engraving, notice = await anyio.to_thread.run_sync(
            lambda: (engrave_tall(score), engrave(score),
                     pdf_reader.notice(score, reading["scan"], reading["skipped"], keep_slurs))
        )
    except (ScoreError, pdf_reader.ReadError, httpx.HTTPError) as error:
        log("read_pdf", platform=source, error=str(error))
        return error_result(str(error))
    # The model gets ordinary pages: one tall image of a long score is shrunk by hosts until notes can't be read.
    pages = [engraving.png(page) for page in range(1, engraving.page_count + 1)]
    image_url, pdf_url = await anyio.to_thread.run_sync(
        lambda: (publish(tall.png(1, width=2800, colors=256), "png"), publish(engraving.pdf(), "pdf"))
    )
    caption = "What I read from your PDF, every bar"
    log("read_pdf", platform=source, pages=reading["pages"], seconds=round(time.time() - started, 1),
        scan=reading["scan"], skipped=reading["skipped"], cached=bool(cached), keep_slurs=keep_slurs)
    text = (
        f"score_id: {score_id}\n"
        f"The card shows the user every bar of the engraved score read from their {reading['pages']}-page PDF, in one "
        f"image, with this message above it: \"{notice}\"\n"
        "Say that message to the user in your reply, then stop and wait. Analyse only after the user says to go ahead: "
        "then call draft_analysis with this score_id and continue exactly as for an attached MusicXML file."
        + ("" if keep_slurs else " If the user asks to keep the slurs, call read_pdf again with the same file and "
           "keep_slurs=true, and use the score_id it returns.")
    )
    return CallToolResult(
        content=[
            *(ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png") for png in pages),
            TextContent(type="text", text=f"{text}\nPDF of the engraved score: {pdf_url}"),
        ],
        structured_content={"image_url": image_url, "pdf_url": pdf_url, "caption": caption, "notice": notice},
    )


apps.add_html_resource(
    PDF_CARD_URI,
    (HERE / "card.html").read_text(),
    name="PDF reading card",
    csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
    domain="https://sheetmusicanalysis.com",
    prefers_border=True,
)



# In Claude the plugin's skill reads the attached file in Claude's sandbox and needs only draft_from_notes;
# the owner wants no file button or server-side drawing there, so Claude is not offered the other tools.
CLAUDE_TOOLS = {"draft_from_notes"}


class Server(MCPServer):
    async def _handle_list_tools(self, ctx, params):
        result = await super()._handle_list_tools(ctx, params)
        if client_of(getattr(ctx.request, "headers", None)) == "claude":
            result.tools = [tool for tool in result.tools if tool.name in CLAUDE_TOOLS]
        return result


# The extension's tools are collected when the server is constructed, so this comes after them.
SITE = "https://sheetmusicanalysis.com"
mcp = Server(
    "sheet-music-analysis",
    title="Sheet Music Analysis",
    website_url=SITE,
    # `theme` names the background the icon is meant for: a dark clef for light hosts, a white one for dark.
    icons=[
        Icon(src=f"{SITE}/icons/clef-for-light-512.png", mime_type="image/png", sizes=["512x512"], theme="light"),
        Icon(src=f"{SITE}/icons/clef-for-dark-512.png", mime_type="image/png", sizes=["512x512"], theme="dark"),
    ],
    instructions=(
        "Harmonic analysis of MusicXML scores drawn on the engraved page. For an analysis, call draft_analysis, "
        "review the draft, then call render_analysis. In Claude, the sheet-music-analysis skill does the analysis "
        "and calls draft_from_notes."
    ),
    extensions=[apps],
)
# The 2026 protocol lets a client hold a `subscriptions/listen` stream open to hear of tool-list changes. Our tools
# never change, and Cloud Run bills every second a request is open: Claude's streams cost 4 hours a day (log, 21).
del mcp._lowlevel_server._request_handlers["subscriptions/listen"]


@mcp.tool(
    title="Draft a harmonic analysis",
    description=(
        "Use this when the user wants a harmonic analysis of a MusicXML score (.mxl or .musicxml): Roman numerals, "
        "cadences, phrases, non-chord tones. Returns a neural model's draft as a table for you to review and correct, "
        "plus a score_id. Follow it with render_analysis. " + SCORE_INPUT_HELP
    ),
    annotations=read_only("Draft a harmonic analysis"),
    meta={"openai/fileParams": ["score_file"]},
)
async def draft_analysis(
    ctx: Context,
    score_file: AttachedFile | None = None,
    score_id: str | None = None,
    measure_range: str = "all",
) -> CallToolResult:
    """measure_range limits the table, e.g. "1-8"; the default "all" returns the whole piece."""
    source = platform(ctx)
    started = time.time()
    try:
        score, given = await resolve_score(score_file, score_id)
        if given == "score_id":
            code = clean_id(score_id)
            fresh = await anyio.to_thread.run_sync(store.get, f"scores/{code}.draft.json") is None
        else:
            code = secrets.token_hex(3).upper()
            await anyio.to_thread.run_sync(store.put, f"scores/{code}", score)
            fresh = True
        # Only a new model run counts toward the limit; re-reading a cached draft is cheap.
        if fresh and not await take("draft", source):
            log("limit", tool="draft_analysis", platform=source)
            return error_result(LIMIT_MESSAGE)
        text = await anyio.to_thread.run_sync(make_draft, score, code, parse_measures(measure_range))
    except (ScoreError, PositionError, draft.DraftError, httpx.HTTPError) as error:
        log("draft_analysis", platform=source, error=str(error))
        return error_result(str(error))
    log("draft_analysis", platform=source, input=given, score_bytes=len(score), measure_range=measure_range,
        seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.tool(
    title="Draft a harmonic analysis from a note list",
    description=(
        "Use this when a skill has produced a compact note list of the user's score (it starts with a line like "
        "'N1 div=48 ts=12/8 ks=3f') because the score file itself cannot be sent. Pass that text unchanged as "
        "`notes`. Returns a neural model's draft analysis (chords, cadences, phrase ends, possible non-chord tones) "
        "as a table for you to review and correct before you annotate the score. Without such a note list you "
        "cannot analyse the score: tell the user that in Claude this needs the Sheet Music Analysis plugin "
        "(from Claude's directory) and Code execution and file creation turned on in Settings > Capabilities."
    ),
    annotations=read_only("Draft a harmonic analysis from a note list"),
)
async def draft_from_notes(ctx: Context, notes: str) -> CallToolResult:
    source = platform(ctx)
    if not await take("draft", source):
        log("limit", tool="draft_from_notes", platform=source)
        return error_result(LIMIT_MESSAGE)
    started = time.time()
    try:
        result = await anyio.to_thread.run_sync(draft.draft_from_notes, notes)
    except (note_list.NotesError, draft.DraftError) as error:
        log("draft_from_notes", platform=source, error=str(error), chars=len(notes))
        return error_result(str(error))
    text = draft.as_text(result)
    log("draft_from_notes", platform=source, chars_in=len(notes), seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.custom_route("/files/{name}", methods=["GET"])
async def files(request: Request) -> Response:
    name = request.path_params["name"]
    data = None
    if re.fullmatch(r"[A-Za-z0-9_-]+\.(png|pdf)", name):
        data = await anyio.to_thread.run_sync(store.get, f"files/{name}")
    if data is None:
        return Response("This file has expired; pages are kept for one day.", status_code=404)
    return Response(data, media_type="image/png" if name.endswith(".png") else "application/pdf")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return Response("ok")


def main() -> None:
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        # Requests arrive under the public hostname, so the localhost-only check is off.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
