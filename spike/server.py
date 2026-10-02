"""Throwaway server for the platform spike (plan step 1).

It answers two questions in Claude and in ChatGPT, with no analysis involved:
how does a score file get from the conversation to a hosted tool, and how does
the engraved page show up in the chat? Every way in and every way out is
offered side by side so the owner can compare real examples.

Run:  PUBLIC_BASE_URL=https://<tunnel-host> .venv/bin/python -m spike.server
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import anyio
import httpx
import uvicorn
from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response

from engine import draft
from engine import notes as note_list
from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList
from engine.render import Engraving, ScoreError, engrave, load_toolkit
from engine.score import PositionError, ScoreIndex

PORT = int(os.environ.get("PORT", "8765"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
DATA_DIR = Path(os.environ.get("SPIKE_DATA_DIR", "out/spike"))
SCORES_DIR = DATA_DIR / "scores"
FILES_DIR = DATA_DIR / "files"
CALL_LOG = DATA_DIR / "calls.log"
MAX_SCORE_BYTES = 10 * 1024 * 1024
# Hosts keep a card's HTML by its address, so the version goes up whenever the HTML changes.
CARD_URI = "ui://score-spike/card-v2.html"
PICKER_URI = "ui://score-spike/picker-v2.html"
ROOT = Path(__file__).parent.parent

for directory in (SCORES_DIR, FILES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

SCORE_INPUT_HELP = (
    "Give the score in exactly one way. score_file: a file the user attached to the chat. "
    "score_id: the id you were given after the user picked a file with choose_score, or by draft_analysis. "
    "score_url: a public https link to a .mxl or .musicxml file. "
    "Never encode, paste or retype a file's contents: if an attached file cannot be passed as score_file, "
    "call choose_score straight away."
)


class AttachedFile(BaseModel):
    """A chat attachment as ChatGPT passes it for parameters listed in openai/fileParams."""

    model_config = ConfigDict(extra="ignore")

    download_url: str
    file_id: str
    mime_type: str | None = None
    file_name: str | None = None


def log_call(tool: str, ctx: Context | None, **details) -> None:
    headers = {}
    try:
        headers = dict(ctx.headers or {}) if ctx else {}
    except Exception:
        pass
    entry = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool,
        "user_agent": headers.get("user-agent"),
        **details,
    }
    with CALL_LOG.open("a") as log:
        log.write(json.dumps(entry) + "\n")


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
        raise ScoreError("The score link must be a public https URL")
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        response = await client.get(url)
    response.raise_for_status()
    if len(response.content) > MAX_SCORE_BYTES:
        raise ScoreError("The score file is larger than 10 MB")
    return response.content


async def resolve_score(
    score_file: AttachedFile | None,
    score_id: str | None,
    score_url: str | None,
) -> tuple[bytes, str]:
    """Return the score bytes and which input path supplied them."""
    if score_file:
        return await download(score_file.download_url), "score_file"
    if score_id:
        path = SCORES_DIR / re.sub(r"[^A-Za-z0-9]", "", score_id).upper()
        if not path.is_file():
            raise ScoreError(f"No uploaded score has the code {score_id!r}")
        return path.read_bytes(), "score_id"
    if score_url:
        return await download(score_url), "score_url"
    raise ScoreError("No score was provided. Call choose_score so the user can pick the file.")


def publish(data: bytes, extension: str) -> str:
    name = f"{secrets.token_urlsafe(12)}.{extension}"
    (FILES_DIR / name).write_bytes(data)
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


def image_result(tool: str, ctx: Context, engraving: Engraving, caption: str, inline: bool, **log) -> CallToolResult:
    png = engraving.png(1)
    png_url, pdf_url = publish(png, "png"), publish(engraving.pdf(), "pdf")
    log_call(tool, ctx, png_bytes=len(png), inline=inline, **log)
    content: list = [TextContent(type="text", text=f"{caption}. PNG: {png_url} PDF: {pdf_url}")]
    if inline:
        content.insert(0, ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"))
    return CallToolResult(content=content)


def card_result(tool: str, ctx: Context, engraving: Engraving, caption: str, **log) -> CallToolResult:
    png = engraving.png(1)
    image_url, pdf_url = publish(png, "png"), publish(engraving.pdf(), "pdf")
    log_call(tool, ctx, png_bytes=len(png), **log)
    return CallToolResult(
        content=[TextContent(type="text", text=f"{caption}, shown in a card. PDF: {pdf_url}")],
        structured_content={"image_url": image_url, "pdf_url": pdf_url, "caption": caption},
    )


def demo_engraving() -> Engraving:
    """The hand-annotated opening of Chopin's Nocturne Op. 9 No. 2: what a finished analysis page looks like."""
    annotations = AnnotationList.model_validate_json((ROOT / "examples/chopin_op9_no2_m1-8.json").read_text())
    return render((ROOT / "tests/data/chopin_nocturne_op9_no2.mxl").read_bytes(), annotations, measures=(1, 8))


DEMO_CAPTION = "Chopin, Nocturne Op. 9 No. 2, measures 1-8, sample analysis"

apps = Apps()


@apps.tool(
    resource_uri=CARD_URI,
    title="Engrave score (card)",
    description=(
        "Use this when the user asks to see the engraved score in a card. "
        "Shows the page in a read-only card with a PDF link. " + SCORE_INPUT_HELP
    ),
    annotations=READ_ONLY,
    meta={"openai/fileParams": ["score_file"], "openai/outputTemplate": CARD_URI},
)
async def engrave_score_card(
    ctx: Context,
    score_file: AttachedFile | None = None,
    score_id: str | None = None,
    score_url: str | None = None,
    measure_range: str = "1-8",
) -> CallToolResult:
    try:
        score, source = await resolve_score(score_file, score_id, score_url)
        engraving = engrave(score, parse_measures(measure_range))
    except (ScoreError, PositionError, httpx.HTTPError) as error:
        log_call("engrave_score_card", ctx, error=str(error))
        return error_result(str(error))
    return card_result("engrave_score_card", ctx, engraving, f"Measures {measure_range}", source=source, score_bytes=len(score))


@apps.tool(
    resource_uri=CARD_URI,
    title="Show sample analysis (card)",
    description="Use this when the user asks to see the sample analysis in a card. Needs no score file.",
    annotations=READ_ONLY,
    meta={"openai/outputTemplate": CARD_URI},
)
def sample_analysis_card(ctx: Context) -> CallToolResult:
    return card_result("sample_analysis_card", ctx, demo_engraving(), DEMO_CAPTION)


@apps.tool(
    resource_uri=CARD_URI,
    title="Render an annotated score",
    description=(
        "Use this after draft_analysis, once you have reviewed the draft, to draw your analysis on the engraved "
        "score. Takes the score_id and your annotation list and returns the page as an image plus PNG and PDF "
        "links, shown to the user in a card. If a position does not exist in the score, the error lists each problem so you can fix the list "
        "and call again. view is one of all, harmony, voice_leading, form."
    ),
    annotations=READ_ONLY,
    meta={"openai/outputTemplate": CARD_URI},
)
async def render_analysis(
    ctx: Context,
    score_id: str,
    annotations: AnnotationList,
    measure_range: str = "all",
    view: str = "all",
) -> CallToolResult:
    try:
        score, _ = await resolve_score(None, score_id, None)
        measures = parse_measures(measure_range)
        engraving = await anyio.to_thread.run_sync(lambda: render(score, annotations, measures=measures, view=view))
    except AnnotationError as error:
        log_call("render_analysis", ctx, problems=len(error.problems))
        return error_result("Fix these annotations and call again:\n" + "\n".join(error.problems))
    except (ScoreError, PositionError) as error:
        log_call("render_analysis", ctx, error=str(error))
        return error_result(str(error))
    caption = f"Analysis, measures {measure_range}, view {view}"
    # The card shows the page to the user; the image lets the chat model check its own annotations.
    result = card_result("render_analysis", ctx, engraving, caption, annotations=len(annotations.annotations))
    png = engraving.png(1)
    result.content.insert(0, ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"))
    return result


@apps.tool(
    resource_uri=PICKER_URI,
    title="Choose a score file",
    description=(
        "Use this when the user wants a score engraved or analysed and you cannot pass their file as score_file "
        "(for example the attachment is not available to tools), and you have no sheet-music-analysis skill that reads "
        "the attached file itself. Shows a file button in the chat. After the user "
        "picks a file, their next message gives you the score_id to use."
    ),
    annotations=READ_ONLY,
    meta={"openai/outputTemplate": PICKER_URI},
)
def choose_score(ctx: Context) -> str:
    log_call("choose_score", ctx)
    return "A file button is now shown to the user. Wait for their next message; it will contain the score_id."


apps.add_html_resource(
    CARD_URI,
    (Path(__file__).parent / "card.html").read_text(),
    name="Score card",
    csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
    prefers_border=True,
)


apps.add_html_resource(
    PICKER_URI,
    (Path(__file__).parent / "picker.html").read_text().replace("__UPLOAD_URL__", f"{PUBLIC_BASE_URL}/upload"),
    name="Score picker",
    csp=ResourceCsp(connect_domains=[PUBLIC_BASE_URL]),
    prefers_border=True,
)


# The extension's tools are collected when the server is constructed, so this comes after them.
mcp = MCPServer(
    "score-spike",
    title="Score engraving spike",
    instructions=(
        "Harmonic analysis of MusicXML scores drawn on the engraved page. For an analysis, call draft_analysis, "
        "review the draft, then call render_analysis. Test server."
    ),
    extensions=[apps],
)


@mcp.tool(
    title="Engrave score (inline image)",
    description=(
        "Use this when the user wants a MusicXML score (.mxl or .musicxml) engraved and shown in the chat. "
        "Returns the page as an image plus links to the PNG and a PDF. " + SCORE_INPUT_HELP
    ),
    annotations=READ_ONLY,
    meta={"openai/fileParams": ["score_file"]},
)
async def engrave_score(
    ctx: Context,
    score_file: AttachedFile | None = None,
    score_id: str | None = None,
    score_url: str | None = None,
    measure_range: str = "1-8",
    inline_image: bool = True,
) -> CallToolResult:
    """measure_range is like "1-8"; pass "all" for the whole first page. inline_image=false returns links only."""
    try:
        score, source = await resolve_score(score_file, score_id, score_url)
        engraving = engrave(score, parse_measures(measure_range))
    except (ScoreError, PositionError, httpx.HTTPError) as error:
        log_call("engrave_score", ctx, error=str(error))
        return error_result(str(error))
    caption = f"Engraved measures {measure_range}"
    return image_result("engrave_score", ctx, engraving, caption, inline_image, source=source, score_bytes=len(score))


@mcp.tool(
    title="Show sample analysis (inline image)",
    description=(
        "Use this when the user asks to see the sample analysis. Needs no score file. "
        "Returns an annotated page (Roman numerals, function colours, cadences, phrase brackets) as an image "
        "plus PNG and PDF links. inline_image=false returns links only."
    ),
    annotations=READ_ONLY,
)
def sample_analysis(ctx: Context, inline_image: bool = True) -> CallToolResult:
    return image_result("sample_analysis", ctx, demo_engraving(), DEMO_CAPTION, inline_image)


REVIEW_GUIDE = """HOW TO USE THIS DRAFT
1. Check every chord against the pitch classes beside it. Function comes before labels: decide what each
   chord is doing (tonic, predominant, dominant) before settling its numeral.
2. Chords shorter than a beat are usually the model reacting to melody notes: fold them into their
   neighbours unless they are real harmonies. A chord over a held bass note keeps its own root.
3. Name each real non-chord tone (P passing, N neighbor, S suspension, APP appoggiatura, ANT anticipation)
   and drop the false ones.
4. Add phrases, cadences and a few numbered callouts for what is unusual; say what was expected and what
   the composer did instead in your written commentary, one numbered paragraph per callout.
5. Call render_analysis with the score_id below and your annotation list, then show the page.
Positions: `measure` is the printed number (a pickup is 0); `beat` is 1-based in the unit given below;
`pitch` is like "Eb4" at sounding pitch; `staff` 1 is the top staff."""


def stored_score(score: bytes, source: str, score_id: str | None) -> str:
    """Keep the score under a code so later calls can refer to it."""
    if source == "score_id" and score_id:
        return re.sub(r"[^A-Za-z0-9]", "", score_id).upper()
    code = secrets.token_hex(3).upper()
    (SCORES_DIR / code).write_bytes(score)
    return code


def make_draft(score: bytes, code: str, measures: tuple[int, int] | None) -> str:
    index = ScoreIndex(load_toolkit(score).getMEI())
    cache = SCORES_DIR / f"{code}.draft.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
    else:
        raw = draft.MODELS["analysisgnn"](score)
        cache.write_text(json.dumps(raw))
    result = draft.build(raw, index)
    first, last = measures or (None, None)
    unit = index.measure(first or index.measures[-1].number).beat_length
    numbers = f"{index.measures[0].number} to {index.measures[-1].number}"
    return (
        f"score_id: {code}\nThe score has measures {numbers}. One beat = {float(unit):g} quarter notes.\n\n"
        + draft.as_text(result, first, last)
        + "\n\n"
        + REVIEW_GUIDE
    )


@mcp.tool(
    title="Draft a harmonic analysis",
    description=(
        "Use this when the user wants a harmonic analysis of a MusicXML score (.mxl or .musicxml): Roman numerals, "
        "cadences, phrases, non-chord tones. Returns a neural model's draft as a table for you to review and correct, "
        "plus a score_id. Follow it with render_analysis. If the user attached a file that you cannot pass as "
        "score_file, call choose_score first. " + SCORE_INPUT_HELP
    ),
    annotations=READ_ONLY,
    meta={"openai/fileParams": ["score_file"]},
)
async def draft_analysis(
    ctx: Context,
    score_file: AttachedFile | None = None,
    score_id: str | None = None,
    score_url: str | None = None,
    measure_range: str = "all",
) -> CallToolResult:
    """measure_range limits the table, e.g. "1-8"; the default "all" returns the whole piece."""
    started = time.time()
    try:
        score, source = await resolve_score(score_file, score_id, score_url)
        code = stored_score(score, source, score_id)
        text = await anyio.to_thread.run_sync(make_draft, score, code, parse_measures(measure_range))
    except (ScoreError, PositionError, draft.DraftError, httpx.HTTPError) as error:
        log_call("draft_analysis", ctx, error=str(error))
        return error_result(str(error))
    log_call("draft_analysis", ctx, source=source, score_bytes=len(score), seconds=round(time.time() - started, 1), chars=len(text))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.tool(
    title="Draft a harmonic analysis from a note list",
    description=(
        "Use this when a skill has produced a compact note list of the user's score (it starts with a line like "
        "'N1 div=48 ts=12/8 ks=3f') because the score file itself cannot be sent. Pass that text unchanged as "
        "`notes`. Returns a neural model's draft analysis (chords, cadences, phrase ends, possible non-chord tones) "
        "as a table for you to review and correct before you annotate the score."
    ),
    annotations=READ_ONLY,
)
async def draft_from_notes(ctx: Context, notes: str) -> CallToolResult:
    started = time.time()
    try:
        result = await anyio.to_thread.run_sync(draft.draft_from_notes, notes)
    except (note_list.NotesError, draft.DraftError) as error:
        log_call("draft_from_notes", ctx, error=str(error), chars=len(notes))
        return error_result(str(error))
    text = draft.as_text(result)
    log_call("draft_from_notes", ctx, chars_in=len(notes), seconds=round(time.time() - started, 1), chars_out=len(text))
    return CallToolResult(content=[TextContent(type="text", text=text)])


UPLOAD_FORM = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Upload a score</title>
<body style="font:16px system-ui;max-width:28rem;margin:3rem auto;padding:0 1rem">
<h1 style="font-size:1.25rem">Upload a score</h1>
<form method="post" enctype="multipart/form-data">
<p><input type="file" name="file" accept=".mxl,.musicxml,.xml" required></p>
<p><button>Upload</button></p></form>{message}</body>"""


CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "content-type"}


@mcp.custom_route("/upload", methods=["GET", "POST", "OPTIONS"])
async def upload(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS)
    if request.method == "GET":
        return HTMLResponse(UPLOAD_FORM.format(message=""))
    if "multipart/form-data" in request.headers.get("content-type", ""):
        form = await request.form()
        data = await form["file"].read() if "file" in form else b""
    else:
        data = await request.body()
    if not data or len(data) > MAX_SCORE_BYTES:
        return JSONResponse({"error": "Send one score file of at most 10 MB"}, status_code=400, headers=CORS)
    code = secrets.token_hex(3).upper()
    (SCORES_DIR / code).write_bytes(data)
    log_call("http_upload", None, score_bytes=len(data), user_agent=request.headers.get("user-agent"))
    if "text/html" in request.headers.get("accept", ""):
        message = f"<p>Uploaded. Paste this code into the chat: <strong>{code}</strong></p>"
        return HTMLResponse(UPLOAD_FORM.format(message=message))
    return JSONResponse({"score_id": code}, headers=CORS)


@mcp.custom_route("/files/{name}", methods=["GET"])
async def files(request: Request) -> Response:
    name = request.path_params["name"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(png|pdf)", name) or not (FILES_DIR / name).is_file():
        return Response(status_code=404)
    return FileResponse(FILES_DIR / name)


class ProtocolLog:
    """Record each MCP request's method (and tool or resource) so card problems can be traced."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/mcp":
            return await self.app(scope, receive, send)
        chunks, more = [], True
        while more:
            message = await receive()
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        try:
            payload = json.loads(body)
            params = payload.get("params") or {}
            capabilities = (params.get("capabilities") or {}).get("extensions")
            entry = {"time": time.strftime("%H:%M:%S"), "method": payload.get("method"), "target": params.get("name") or params.get("uri")}
            if capabilities is not None:
                entry["client"] = params.get("clientInfo")
                entry["extensions"] = capabilities
            with (DATA_DIR / "protocol.log").open("a") as log:
                log.write(json.dumps(entry) + "\n")
        except (ValueError, AttributeError):
            pass
        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)


def main() -> None:
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        # The tunnel's hostname arrives in the Host header, so the localhost-only check is off.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    uvicorn.run(ProtocolLog(app), host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
