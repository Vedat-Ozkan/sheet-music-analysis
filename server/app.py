from __future__ import annotations

import asyncio
import base64
import contextvars
import functools
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import anyio
import httpx
import uvicorn
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage
from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Icon, ImageContent, TextContent, ToolAnnotations
from opentelemetry import context as trace_context
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import NonRecordingSpan, SpanContext, StatusCode, TraceFlags
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import Response

from engine import correct, draft, read_ahead
from engine import notes as note_list
from engine import read_pdf as pdf_reader
from engine import check_analysis, ledger, part_writing, reduce
from engine.annotate import AnnotationError, render
from engine.performance import performance_text, unclear_tempos
from engine.annotations import AnnotationList
from engine.export import export_midi, export_musicxml, export_romantext
from engine.render import ScoreError, engrave, load_toolkit
from engine.score import PositionError, ScoreIndex
from server import IMPORTS_BEGUN, SERVER_FILES

PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
BUCKET = os.environ.get("BUCKET")
MAX_SCORE_BYTES = 10 * 1024 * 1024
DOWNLOAD_SECONDS = 30
MAX_REDIRECTS = 5
RATING_AFTER_ANALYSES = 3
DAILY_LIMITS = {"draft": 100, "render": 200, "pdf_page": 150} | json.loads(os.environ.get("DAILY_LIMITS", "{}"))
MAX_PDF_PAGES = 12
CARD_URI = "ui://sheet-music-analysis/card-v2.html"
PDF_CARD_URI = "ui://sheet-music-analysis/pdf-card-v2.html"
PLAYER_URI = "ui://sheet-music-analysis/player-v3.html"
CONNECTOR_URL = os.environ.get("CONNECTOR_URL", "https://mcp.sheetmusicanalysis.com/mcp")
HERE = Path(__file__).parent

def read_only(title: str) -> ToolAnnotations:
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

    def add(self, key: str, data: bytes) -> None:
        path = self.folder / key
        path.parent.mkdir(parents=True, exist_ok=True)
        draft_path = path.with_name(f"{path.name}.{secrets.token_hex(8)}")
        draft_path.write_bytes(data)
        try:
            os.link(draft_path, path)
        except FileExistsError:
            pass
        finally:
            draft_path.unlink()


class BucketStore:

    def __init__(self, name: str):
        self.bucket = storage.Client().bucket(name)

    def put(self, key: str, data: bytes) -> None:
        self.bucket.blob(key).upload_from_string(data)

    def get(self, key: str) -> bytes | None:
        try:
            return self.bucket.blob(key).download_as_bytes()
        except NotFound:
            return None

    def add(self, key: str, data: bytes) -> None:
        try:
            self.bucket.blob(key).upload_from_string(data, if_generation_match=0)
        except PreconditionFailed:
            pass


store = BucketStore(BUCKET) if BUCKET else LocalStore(Path(os.environ.get("DATA_DIR", "out/server")))
counter_lock = asyncio.Lock()
pdf_lock = asyncio.Lock()
score_work = anyio.CapacityLimiter(1)


async def in_turn(function, *args):
    return await anyio.to_thread.run_sync(function, *args, limiter=score_work)


def platform(ctx: Context | None) -> str:
    try:
        headers = ctx.headers if ctx else None
    except Exception:
        headers = None
    return client_of(headers)


day_keys: dict[str, bytes] = {}


def daily_code(value: str) -> str:
    day = datetime.now(timezone.utc).date().isoformat()
    key = day_keys.get(day)
    if key is None:
        store.add(f"keys/{day}", secrets.token_bytes(32))
        key = store.get(f"keys/{day}")
        if not key:
            raise ValueError(f"no user key for {day}")
        day_keys.clear()
        day_keys[day] = key
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]


def client_of(headers) -> str:
    agent = (dict(headers or {}).get("user-agent") or "").lower()
    return "claude" if "claude" in agent else "chatgpt" if "openai" in agent else "other"


PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "sheet-music-analysis")
STARTED = time.monotonic()
SEVERITY = {"ok": "INFO", "user_error": "WARNING", "limit": "WARNING", "busy": "WARNING", "server_error": "ERROR", "cancelled": "WARNING"}
current_call: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_call", default=None)
calls_served = 0


def write_line(entry: dict) -> None:
    print(json.dumps(entry), file=sys.stdout, flush=True)


def log(event: str, **details) -> None:
    call = current_call.get()
    if call is None:
        write_line({"event": event, **details})
        return
    call["event"] = event
    call.update(details)
    if details.get("outcome") == "server_error":
        call["stack_trace"] = traceback.format_exc()


tracer = trace.get_tracer("sheet-music-analysis")


def remote_parent(headers: dict[str, str]) -> SpanContext:
    trace_hex, span = uuid.uuid4().hex, 0
    if match := re.fullmatch(r"[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}", headers.get("traceparent", "")):
        trace_hex, span = match[1], int(match[2], 16)
    elif match := re.match(r"([0-9a-f]{32})(?:/(\d{1,20}))?", headers.get("x-cloud-trace-context", "")):
        trace_hex, span = match[1], int(match[2] or 0) % 2**64
    return SpanContext(int(trace_hex, 16), span or secrets.randbits(63) + 1, is_remote=True,
                       trace_flags=TraceFlags(TraceFlags.SAMPLED))


def traced(app):
    async def with_trace(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        headers = {name.decode("latin-1"): value.decode("latin-1") for name, value in scope["headers"]}
        token = trace_context.attach(trace.set_span_in_context(NonRecordingSpan(remote_parent(headers))))
        try:
            await app(scope, receive, send)
        finally:
            trace_context.detach(token)

    return with_trace


def without_event_stream(app):
    refusal = Response("This server sends no event stream; use POST.", status_code=405, headers={"Allow": "POST"})

    async def refusing_get(scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == "/mcp":
            return await refusal(scope, receive, send)
        return await app(scope, receive, send)

    return refusing_get


@contextmanager
def stage(name: str):
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span(name):
            yield
    finally:
        draft.add_timing(name, time.perf_counter() - started)


def flush_traces() -> None:
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(5000)


def observed(fn):
    tool = fn.__name__

    @functools.wraps(fn)
    async def wrapper(ctx: Context, *args, **kwargs):
        global calls_served
        try:
            headers = ctx.headers
        except Exception:
            headers = None
        try:
            meta = dict(ctx.request_context.meta or {})
        except Exception:
            meta = {}
        span = tracer.start_span(tool)
        request_id = f"{span.get_span_context().trace_id:032x}"
        call = {"event": tool, "tool": tool, "platform": client_of(headers), "request_id": request_id,
                "logging.googleapis.com/trace": f"projects/{PROJECT}/traces/{request_id}",
                "logging.googleapis.com/spanId": f"{span.get_span_context().span_id:016x}",
                "cold": calls_served == 0, "uptime_s": round(time.monotonic() - STARTED),
                "meta_keys": sorted(meta), "header_names": sorted(dict(headers or {})), "reference": secrets.token_hex(4)}
        if subject := meta.get("openai/subject"):
            try:
                call["user"] = await anyio.to_thread.run_sync(daily_code, str(subject))
            except Exception as error:
                call["user_code_error"] = f"{type(error).__name__}: {error}"
        calls_served += 1
        timings = {}
        call_token, timings_token = current_call.set(call), draft.timings.set(timings)
        started = time.perf_counter()
        result = None
        try:
            with trace.use_span(span, end_on_exit=False):
                result = await fn(ctx, *args, **kwargs)
        except Exception:
            call["outcome"] = "server_error"
            call["stack_trace"] = traceback.format_exc()
        except BaseException:
            call["outcome"] = "cancelled"
            raise
        finally:
            current_call.reset(call_token)
            draft.timings.reset(timings_token)
            timings["total"] = round((time.perf_counter() - started) * 1000)
            outcome = call.pop("outcome", None) or (
                "limit" if call["event"] == "limit" else "busy" if call.get("busy")
                else "user_error" if result is not None and result.is_error else "ok")
            span.set_attributes({"outcome": outcome, "platform": call["platform"], "cold": call["cold"],
                                 **{f"timings_ms.{name}": value for name, value in timings.items()}})
            if outcome == "server_error":
                span.set_status(StatusCode.ERROR, call.get("error", ""))
            span.end()
            write_line({**call, "outcome": outcome, "severity": SEVERITY[outcome],
                        "message": f"{tool} {outcome}", "timings_ms": timings})
            with anyio.move_on_after(5):
                await anyio.to_thread.run_sync(flush_traces, abandon_on_cancel=True)
        return error_result(OUR_ERROR_MESSAGE.format(reference=call["reference"])) if outcome == "server_error" else result

    return wrapper


async def take(kind: str, source: str, amount: int = 1) -> bool:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"usage/{day}.json"
    with stage("counter"):
        async with counter_lock:
            raw = await anyio.to_thread.run_sync(store.get, key)
            counts = json.loads(raw) if raw else {}
            if counts.get(kind, 0) + amount > DAILY_LIMITS[kind]:
                return False
            counts[kind] = counts.get(kind, 0) + amount
            counts[f"{kind}:{source}"] = counts.get(f"{kind}:{source}", 0) + amount
            await anyio.to_thread.run_sync(store.put, key, json.dumps(counts).encode())
    return True


OUR_ERROR_MESSAGE = (
    "Something went wrong on our side, not with the user's score or request (reference {reference}). "
    "Apologise to the user for us, and tell them that if they would like to tell us what happened or get help, "
    "they can email support@sheetmusicanalysis.com and mention reference {reference}; we read every message "
    "and their feedback helps us fix it."
)

LIMIT_MESSAGE = (
    "Sheet Music Analysis has reached its daily limit; it resets at midnight UTC. "
    "Tell the user plainly that the free service is at capacity for today and to try again tomorrow."
)

SCORE_INPUT_HELP = (
    "Give the score in exactly one way. score_file: a file the user attached to the chat. "
    "score_id: the id returned by an earlier draft_analysis, read_pdf or correct_bars. "
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
    try:
        with anyio.fail_after(DOWNLOAD_SECONDS):
            async with httpx.AsyncClient(timeout=20) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    if not await anyio.to_thread.run_sync(is_public_https, url):
                        raise ScoreError("The attached file's link is not a public https URL")
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            url = str(response.url.join(response.headers["location"]))
                            continue
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data += chunk
                            if len(data) > MAX_SCORE_BYTES:
                                raise ScoreError("The score file is larger than 10 MB")
                        return bytes(data)
    except TimeoutError as error:
        raise ScoreError(f"The attached file took longer than {DOWNLOAD_SECONDS} seconds to download") from error
    raise ScoreError("The attached file's link redirects too many times")


def clean_id(score_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", score_id).upper()


async def resolve_score(score_file: AttachedFile | None, score_id: str | None) -> tuple[bytes, str]:
    with stage("fetch"):
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


def publish(data: bytes, extension: str, suffix: str = "") -> str:
    name = f"{secrets.token_urlsafe(12)}{suffix}.{extension}"
    store.put(f"files/{name}", data)
    return f"{PUBLIC_BASE_URL}/files/{name}"


def outcome_of(error: Exception) -> str:
    return "server_error" if isinstance(error, draft.DraftError) else "user_error"


def error_result(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def parse_measures(measure_range: str) -> tuple[int, int] | None:
    if measure_range == "all":
        return None
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", measure_range)
    if not match:
        raise ScoreError('measure_range must look like "1-8", or be "all"')
    first, last = int(match[1]), int(match[2])
    if first > last:
        raise ScoreError(f'measure_range must start at the lower bar, e.g. "{last}-{first}"')
    return first, last


SKILL_RULES = re.sub(r"<!--.*?-->\n+", "", (HERE.parent / "skill" / "SKILL.md").read_text().split("## Method", 1)[1])
REVIEW_GUIDE = (
    "HOW TO USE THIS DRAFT\n"
    "The draft above is a neural model's starting point, right about half the time on full chord labels. Check "
    "each line against the NOTES table, analyse following the method below, then call render_analysis with the "
    "score_id and your annotation list (its `view` argument draws one layer: harmony, voice_leading or form), "
    "show the page and write the commentary.\n"
    "Positions: `measure` is the printed number (a pickup is 0); `beat` is 1-based in the unit given above; "
    "`pitch` is like \"Eb4\" at sounding pitch; `staff` 1 is the top staff.\n\n"
    "If the draft has a PART-WRITING CHECK section (chorale-style scores only), your first reply must include one "
    "sentence offering to check the voice leading, even when it also asks which bars to analyse; draw nothing from it "
    "unless the user says yes or asked for it. When they want it, add "
    "one callout per numbered spot and the voice_leading marks listed under it (kind, notes and label exactly as given; use the NoteRefs "
    "given), and explain every finding of a spot in its numbered paragraph of the commentary, in terms of the notes. "
    "Call these strict classroom rules, not verdicts on a composer.\n\n"
    "If the draft has a STUDENT CHECK section, the user wants their own numerals checked: draw the "
    "page as usual from your reviewed analysis (how their numerals are marked on it is not decided yet), and write the commentary as a second "
    "reader would, not as an answer key, following that section's guidance. This is for learning; if they say it is "
    "coursework, remind them to check their course's rules on AI help.\n\n"
    "## Method" + SKILL_RULES
)


def make_draft(score: bytes, code: str, measures: tuple[int, int] | None, student_analysis: str | None = None) -> str:
    with stage("parse"):
        mei = load_toolkit(score).getMEI()
        index = ScoreIndex(mei)
    with stage("fetch"):
        cached = store.get(f"scores/{code}.draft.json")
    if cached:
        raw = json.loads(cached)
    else:
        with tracer.start_as_current_span("model"):
            raw = draft.MODELS["analysisgnn"](note_list.encode(index).encode(), "notes")
        with stage("publish"):
            store.put(f"scores/{code}.draft.json", json.dumps(raw).encode())
    with stage("build"):
        result = draft.build(raw, index)
        first, last = measures or (None, None)
        unit = index.measure(first or index.measures[-1].number).beat_length
        numbers = f"{index.measures[0].number} to {index.measures[-1].number}"
        return (
            f"score_id: {code}\nThe score has measures {numbers}. One beat = {float(unit):g} quarter notes.\n\n"
            + draft.as_text(result, first, last)
            + "\n\nNOTES (one row per beat: lowest note, pitch classes, every note as pitch@beat)\n"
            + reduce.as_text(index, first, last)
            + ("\n\n" + section if (section := part_writing.as_text(index, result.chords, first, last)) else "")
            + ("\n\n" + section if (section := ledger.as_text(mei, index, first, last)) else "")
            + (
                "\n\n" + check_analysis.as_text(check_analysis.student_labels(student_analysis, score, index), result, index)
                if student_analysis else ""
            )
            + "\n\n"
            + REVIEW_GUIDE
        )


apps = Apps()


def musicxml_text(url: str, annotations: AnnotationList) -> str:
    # Without harmony annotations the export is the unmodified original, so it has no labels to mention.
    if not any(item.type == "harmony" for item in annotations.annotations):
        return f"MusicXML (open in MuseScore, Sibelius or Dorico): {url}"
    return (f"MusicXML with the harmony labels (open in MuseScore, Sibelius or Dorico): {url}\n"
            "The file uses standard Roman numerals whatever the page style.")


EXTRA_FILES = {"worksheet": ("pdf", "-worksheet"), "midi": ("mid", ""), "romantext": ("rntxt", "")}


def downloads_text(links: dict[str, str]) -> str:
    names = {"worksheet_url": "worksheet (the same passage with no analysis, PDF)", "midi_url": "MIDI",
             "romantext_url": "RomanText (the harmony analysis as .rntxt)"}
    present = [f"{label}: {links[key]}" for key, label in names.items() if key in links]
    if not present:
        return ""
    return ("\nMore downloads, shown on the card under \"More downloads\"; mention them to the user once per "
            "conversation, not after every render:\n" + "\n".join(present))


@apps.tool(
    resource_uri=CARD_URI,
    title="Draw the analysis on the score",
    description=(
        "Use this after draft_analysis, once you have reviewed the draft, to draw your analysis on the engraved "
        "score. Takes the score_id and your annotation list and returns the page as an image plus PNG, PDF and MusicXML "
        "links, shown to the user in a card. If a position does not exist in the score, the error lists each "
        "problem so you can fix the list and call again. A page shows at most 32 bars: for a longer piece, pass "
        "measure_range (e.g. 1-16) and draw it passage by passage. view is one of all, harmony, voice_leading, form. "
        "Set annotations.style to abrsm (letter inversions, Ib, Vc) when the user mentions ABRSM, figured_bass when they ask "
        "for figured bass, otherwise leave it out. "
        "Offer the MusicXML link once per conversation, not after every render: it downloads a file for "
        "MuseScore, Sibelius or Dorico; the result also lists a worksheet PDF, MIDI and RomanText to mention once. "
        "piano=true draws the same annotation list (written for the original score) on a two-staff piano reduction "
        "with instrument cues. For a score with more than four staves (an orchestra, band or large ensemble), draw the original first, then offer the user "
        "the piano reduction once; call again with piano=true only if they accept."
    ),
    annotations=read_only("Draw the analysis on the score"),
    meta={"openai/outputTemplate": CARD_URI},
)
@observed
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
        with stage("render"):
            engraving = await in_turn(lambda: render(score, annotations, measures=measures, view=view, piano=piano))
    except AnnotationError as error:
        log("render_analysis", platform=source, problems=len(error.problems))
        return error_result("Fix these annotations and call again:\n" + "\n".join(error.problems))
    except ValueError as error:
        log("render_analysis", platform=source, error=type(error).__name__)
        return error_result(str(error))
    musicxml, export_warning = None, None
    try:
        with stage("export"):
            musicxml = await in_turn(export_musicxml, score, annotations.model_dump())
    except Exception as error:
        export_warning = "MusicXML export unavailable for this score. PNG and PDF are available."
        log("render_analysis", platform=source, export_error=type(error).__name__)

    def extras() -> dict[str, bytes]:
        found, errors = {}, []
        for name, make in (("worksheet", lambda: render(score, AnnotationList(annotations=[]), measures=measures, piano=piano).pdf()),
                           ("midi", lambda: export_midi(score, measures)),
                           ("romantext", lambda: export_romantext(score, annotations.model_dump(), measures))):
            try:
                with stage("export"):
                    data = make()
            except Exception as error:
                errors.append(f"{name}: {error}")
                continue
            if data:
                found[name] = data
        if errors:
            log("render_analysis", platform=source, extra_errors=errors)
        return found

    with stage("render"):
        png = await in_turn(engraving.png, 1)
    def publish_all():
        with stage("render"):
            image, pdf = engraving.png(1, width=2800, colors=256), engraving.pdf()
        files = extras()
        with stage("publish"):
            links = {"image_url": publish(image, "png"), "pdf_url": publish(pdf, "pdf")}
            if musicxml is not None:
                links["musicxml_url"] = publish(musicxml, "musicxml")
            for name, data in files.items():
                links[f"{name}_url"] = publish(data, *EXTRA_FILES[name])
        return links
    links = await in_turn(publish_all)
    pdf_url = links["pdf_url"]
    caption = f"Analysis, measures {measure_range}, view {view}" + (", piano reduction" if piano else "")
    log("render_analysis", platform=source, annotations=len(annotations.annotations), png_bytes=len(png), piano=piano,
        view=view, measure_range=measure_range)
    structured_content = {**links, "caption": caption}
    return CallToolResult(
        meta={"ask_for_rating": True} if await rating_is_due(ctx) else None,
        content=[
            ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"),
            TextContent(type="text", text=f"{caption}, shown in a card. PDF: {pdf_url}\n"
                        + (export_warning or musicxml_text(links["musicxml_url"], annotations)) + downloads_text(links)),
        ],
        structured_content=structured_content,
    )


async def rating_is_due(ctx: Context) -> bool:
    try:
        chat = dict(ctx.request_context.meta or {}).get("openai/session")
        if not chat:
            return False

        def count_analysis() -> int:
            key = f"chats/{daily_code(str(chat))}"
            analyses = int(store.get(key) or 0) + 1
            store.put(key, str(analyses).encode())
            return analyses

        return await anyio.to_thread.run_sync(count_analysis) == RATING_AFTER_ANALYSES
    except Exception as error:
        log("render_analysis", rating_error=f"{type(error).__name__}: {error}")
        return False


@apps.tool(
    resource_uri=CARD_URI,
    visibility=["app"],
    title="Rate an analysis",
    description="Records the user's thumbs up or down from the analysis card.",
    annotations=ToolAnnotations(title="Rate an analysis", read_only_hint=False, destructive_hint=False,
                                idempotent_hint=False, open_world_hint=False),
)
@observed
async def rate_analysis(ctx: Context, helpful: bool) -> CallToolResult:
    log("rate_analysis", helpful=helpful)
    return CallToolResult(content=[TextContent(type="text", text="Thanks; the rating is recorded.")])


apps.add_html_resource(
    CARD_URI,
    (HERE / "card.html").read_text(),
    name="Analysis card",
    csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
    domain="https://sheetmusicanalysis.com",
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
@observed
async def read_pdf(ctx: Context, pdf_file: AttachedFile, keep_slurs: bool = False) -> CallToolResult:
    source = platform(ctx)
    started = time.time()
    try:
        with stage("fetch"):
            data = await download(pdf_file.download_url)
        if not data.startswith(b"%PDF"):
            raise ScoreError("This file is not a PDF. Ask the user to attach a PDF of the printed music or a MusicXML file.")
        cache_key = f"scores/pdf-{pdf_reader.READER}-{hashlib.sha256(data).hexdigest()}.json"
        cached = await anyio.to_thread.run_sync(store.get, cache_key)
        if cached:
            reading = json.loads(cached)
        else:
            pages = len((await anyio.to_thread.run_sync(pdf_reader.open_pdf, data)).pages)
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
                with stage("omr"):
                    result = await anyio.to_thread.run_sync(pdf_reader.read_pdf, data)
            reading = {"score_id": secrets.token_hex(8).upper(), "pages": result.pages, "scan": result.scan,
                       "skipped": result.skipped}
            await anyio.to_thread.run_sync(store.put, f"scores/{reading['score_id']}", result.musicxml)
            await anyio.to_thread.run_sync(store.put, cache_key, json.dumps(reading).encode())
        score, _ = await resolve_score(None, reading["score_id"])
        score_id = reading["score_id"] if keep_slurs else reading["score_id"] + "N"
        if not keep_slurs:
            score = await in_turn(pdf_reader.without_slurs, score)
            await anyio.to_thread.run_sync(store.put, f"scores/{score_id}", score)
        def render():
            spots = pdf_reader.problem_spots(score)
            return (pdf_reader.preview(score, tall=True, spots=spots), pdf_reader.preview(score, spots=spots), engrave(score),
                    pdf_reader.notice(score, reading["scan"], reading["skipped"], keep_slurs, spots))

        with stage("render"):
            tall, shaded, engraving, notice = await in_turn(render)
    except (ScoreError, pdf_reader.ReadError, httpx.HTTPError) as error:
        log("read_pdf", platform=source, error=type(error).__name__)
        return error_result(str(error))
    with stage("render"):
        pages = await in_turn(lambda: [shaded.png(page) for page in range(1, shaded.page_count + 1)])
    with stage("publish"):
        image_url, pdf_url = await in_turn(
            lambda: (publish(tall.png(1, width=2800, colors=256), "png"), publish(engraving.pdf(), "pdf"))
        )
    caption = "What I read from your PDF, every bar"
    log("read_pdf", platform=source, pages=reading["pages"], seconds=round(time.time() - started, 1),
        scan=reading["scan"], skipped=reading["skipped"], cached=bool(cached), keep_slurs=keep_slurs)
    text = (
        f"score_id: {score_id}\n"
        f"The card shows the user every bar of the engraved score read from their {reading['pages']}-page PDF, in one "
        f"image. The card holds no text, so give the user this message in your reply: \"{notice}\"\n"
        "Then stop and wait. Analyse only after the user says to go ahead: "
        "then call draft_analysis with this score_id and continue exactly as for an attached MusicXML file."
        + ("" if keep_slurs else " If the user asks to keep the slurs, call read_pdf again with the same file and "
           "keep_slurs=true, and use the score_id it returns.")
    )
    return CallToolResult(
        content=[
            *(ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png") for png in pages),
            TextContent(type="text", text=f"{text}\nPDF of the engraved score: {pdf_url}"),
        ],
        structured_content={"image_url": image_url, "pdf_url": pdf_url, "caption": caption, "title": "What I read from your PDF"},
    )


apps.add_html_resource(
    PDF_CARD_URI,
    (HERE / "card.html").read_text(),
    name="PDF reading card",
    csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
    domain="https://sheetmusicanalysis.com",
    prefers_border=True,
)



CLAUDE_TOOLS = {"draft_from_notes", "play"}
CLAUDE_ONLY_TOOLS = {"play"}
NO_NOTE_LIST = (
    "No note list: draft_from_notes needs the compact note list (starting 'N1 div=') that the Sheet Music Analysis "
    "plugin's skill makes from the user's score file; this server cannot read the score in Claude. The plugin is "
    "installed from Claude's directory and needs Code execution and file creation on (Settings > Capabilities)."
)
QUESTION_FOR_USER = "Question for the user about their Roman numerals: "


class Server(MCPServer):
    async def _handle_list_tools(self, ctx, params):
        result = await super()._handle_list_tools(ctx, params)
        if client_of(getattr(ctx.request, "headers", None)) == "claude":
            result.tools = [tool for tool in result.tools if tool.name in CLAUDE_TOOLS]
        else:
            result.tools = [tool for tool in result.tools if tool.name not in CLAUDE_ONLY_TOOLS]
        return result


SITE = "https://sheetmusicanalysis.com"


NO_PLAY_NOTES = (
    "Nothing to play: pass the play_id that draft_from_notes returned, or, when there is no draft, the compact note "
    "list (starting 'N1 div=') that the Sheet Music Analysis plugin's skill prints, passed unchanged as notes."
)


@apps.tool(
    resource_uri=PLAYER_URI,
    title="Play the score",
    description=(
        "Shows the user a small piano player in the chat, with play, pause and a seek bar. Use it when the user "
        "wants to hear the passage or score. After draft_from_notes, pass the play_id it returned. Without a draft, "
        "pass the compact note list (starting 'N1 div=') that the Sheet Music Analysis plugin's skill prints, "
        "unchanged, as notes. It plays the score's tempo, dynamics, pedal marks and ornaments. tempo, in quarter notes "
        "per minute, is only for a tempo word whose speed play says is unclear: ask the user, then pass their answer."
    ),
    annotations=read_only("Play the score"),
)
@observed
async def play(ctx: Context, play_id: str | None = None, notes: str | None = None, tempo: float | None = None) -> CallToolResult:
    if play_id:
        stored = await anyio.to_thread.run_sync(store.get, f"scores/{clean_id(play_id)}.notes")
        notes = stored.decode() if stored else None
    if not notes or not notes.lstrip().startswith("N1"):
        return error_result(NO_PLAY_NOTES)
    try:
        index = await in_turn(note_list.decode, notes)
        unclear = unclear_tempos(index)
        if unclear and not tempo:
            bar, word = unclear[0]
            log("play", chars_in=len(notes), relayed=not play_id, asked_tempo=word)
            return CallToolResult(content=[TextContent(type="text", text=(
                f"Bar {bar} is marked '{word}' with a half-note beat, so how fast to play it is unclear. Ask the user how "
                "fast they want it, then call play again with the same arguments and tempo in quarter notes per minute."
            ))])
        performance = await in_turn(lambda: performance_text(index, tempo=tempo))
    except (note_list.NotesError, ValueError) as error:
        log("play", error=type(error).__name__, chars=len(notes), outcome=outcome_of(error))
        return error_result(str(error))
    log("play", chars_in=len(notes), relayed=not play_id)
    return CallToolResult(
        content=[TextContent(type="text", text="The user now has a player for this passage in the chat.")],
        structured_content={"performance": performance},
    )


apps.add_html_resource(
    PLAYER_URI,
    (HERE / "player.html").read_text().replace("__SAMPLES__", f"{SITE}/piano/"),
    name="Score player",
    csp=ResourceCsp(connect_domains=[SITE]),
    domain=hashlib.sha256(CONNECTOR_URL.encode()).hexdigest()[:32] + ".claudemcpcontent.com",
    prefers_border=True,
)


mcp = Server(
    "sheet-music-analysis",
    title="Sheet Music Analysis",
    website_url=SITE,
    icons=[
        Icon(src=f"{SITE}/icons/clef-for-light-512.png", mime_type="image/png", sizes=["512x512"], theme="light"),
        Icon(src=f"{SITE}/icons/clef-for-dark-512.png", mime_type="image/png", sizes=["512x512"], theme="dark"),
    ],
    instructions=(
        "Harmonic analysis of sheet music: Roman numerals, cadences, phrases and non-chord tones. draft_from_notes "
        "drafts the analysis from a compact note list of a score, which the Sheet Music Analysis plugin's skill makes "
        "from the user's score file in Claude; play then shows a small piano player for the passage in the chat. In other "
        "clients the server also reads MusicXML and PDF scores itself and draws the analysis on the engraved page."
    ),
    extensions=[apps],
)
del mcp._lowlevel_server._request_handlers["subscriptions/listen"]


@mcp.tool(
    title="Draft a harmonic analysis",
    description=(
        "Use this when the user wants a harmonic analysis of a MusicXML score (.mxl or .musicxml): Roman numerals, "
        "cadences, phrases, non-chord tones. Returns a neural model's draft as a table for you to review and correct, "
        "plus a score_id. Follow it with render_analysis. If the user wants their own analysis checked, pass their "
        "Roman numerals as student_analysis, as they typed them (\"m1 I, m2 V6, m3 beat 3 ii65 ...\"), or the word "
        "\"score\" when the numerals are written into their score file; the draft then lists, beat by beat, where "
        "they agree with it. If the result is a question, ask the user that question and call again with their answer. "
        + SCORE_INPUT_HELP
    ),
    annotations=read_only("Draft a harmonic analysis"),
    meta={"openai/fileParams": ["score_file"]},
)
@observed
async def draft_analysis(
    ctx: Context,
    score_file: AttachedFile | None = None,
    score_id: str | None = None,
    measure_range: str = "all",
    student_analysis: str | None = None,
) -> CallToolResult:
    """measure_range limits the table, e.g. "1-8"; the default "all" returns the whole piece."""
    source = platform(ctx)
    started = time.time()
    try:
        score, given = await resolve_score(score_file, score_id)
        if student_analysis and student_analysis.strip().lower() != "score":
            await in_turn(check_analysis.from_text, student_analysis)
        if given == "score_id":
            code = clean_id(score_id)
            fresh = await anyio.to_thread.run_sync(store.get, f"scores/{code}.draft.json") is None
        else:
            code = secrets.token_hex(8).upper()
            await anyio.to_thread.run_sync(store.put, f"scores/{code}", score)
            fresh = True
        if fresh and not await take("draft", source):
            log("limit", tool="draft_analysis", platform=source)
            return error_result(LIMIT_MESSAGE)
        text = await in_turn(make_draft, score, code, parse_measures(measure_range), student_analysis)
    except check_analysis.ClarificationNeeded as error:
        return error_result(error.question)
    except (ScoreError, PositionError, ValueError, draft.DraftError, httpx.HTTPError) as error:
        log("draft_analysis", platform=source, error=type(error).__name__, outcome=outcome_of(error))
        return error_result(str(error))
    log("draft_analysis", platform=source, input=given, score_bytes=len(score), measure_range=measure_range,
        seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.tool(
    title="Correct misread bars",
    description=(
        "Use this after read_pdf for a misread bar the user describes, or one read_pdf flagged or "
        "you can see is misread when you are confident what it should be. Pass its score_id and replacement_bars "
        "in N1 format, replacing every voice of each listed bar and including every staff. Example:\n"
        "N1 div=24 ts=4/4 ks=0\nm3 len=96\n1.1: 24 C4 D4 48 E4\n"
        "div is units per quarter note; m3 is printed bar 3; len is its length in those units. "
        "Each staff.voice line uses numbers to set the duration for following tokens, + for chords, r for rests, "
        "g for grace notes (u for slashed ones) and ~ for ties to the next note; pitches are sounding pitches (e.g. F#4, Bb3). "
        "Every voice must explicitly fill the existing bar, including rests. A bar line may also carry ts= or ks= where the meter or key signature changes. Header and bar-line key/meter do not change the score. "
        "Use part (a part id or name) in a score with multiple parts; staff numbers count within that part. Returns a new score_id, PNGs of only changed bars "
        "and a note per bar; runs no model. If you proposed the correction, say it is your suggestion. "
        "Show the redrawn bars and note; ask the user to confirm against their copy. "
        "Only after confirmation analyse with draft_analysis using the new score_id. "
        "If they decline, keep using the original score_id."
    ),
    annotations=read_only("Correct misread bars"),
)
@observed
async def correct_bars(
    ctx: Context, score_id: str, replacement_bars: str, part: str | None = None,
) -> CallToolResult:
    source = platform(ctx)
    try:
        before, _ = await resolve_score(None, score_id)
        with stage("parse"):
            after = await in_turn(lambda: correct.replace_bars(before, replacement_bars, part=part))
        if not await take("render", source):
            log("limit", tool="correct_bars", platform=source)
            return error_result(LIMIT_MESSAGE)
        with stage("render"):
            review = await in_turn(lambda: correct.review_correction(before, after, part=part))
        if not review.changed_bars:
            log("correct_bars", platform=source, changed=0)
            return CallToolResult(
                content=[TextContent(type="text", text=f"No bars changed: the replacement matches the score. "
                                     f"Nothing to confirm; keep using score_id {score_id}.")],
                structured_content={"score_id": score_id, "changed_bars": [], "image_urls": [], "notes": {}},
            )
        with stage("render"):
            pages = await in_turn(
                lambda: [engraving.png(page) for engraving in review.engravings
                         for page in range(1, engraving.page_count + 1)]
            )
        with stage("publish"):
            urls = await in_turn(
                lambda: [publish(engraving.png(page, width=2800, colors=256), "png")
                         for engraving in review.engravings for page in range(1, engraving.page_count + 1)]
            )
            code = secrets.token_hex(8).upper()
            await anyio.to_thread.run_sync(store.put, f"scores/{code}", after)
    except (correct.CorrectionError, ScoreError, PositionError) as error:
        log("correct_bars", platform=source, error=type(error).__name__)
        return error_result("Fix the replacement bars and call correct_bars again: " + str(error))
    log("correct_bars", platform=source, changed=len(review.changed_bars), pages=len(pages))
    descriptions = list(review.notes.values())
    text = (
        f"score_id: {code}\n" + "\n".join(descriptions)
        + "\nIf you proposed the correction, tell the user it is your suggestion. "
        "Show the redrawn bars and note. Ask them to confirm against their copy; "
        "only after confirmation call draft_analysis with this new score_id."
        + f" If they decline, keep using score_id {score_id}."
        + ("\nPNGs: " + " ".join(urls) if urls else "")
    )
    return CallToolResult(
        content=[*(ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png")
                   for png in pages), TextContent(type="text", text=text)],
        structured_content={"score_id": code, "changed_bars": review.changed_bars,
                            "image_urls": urls, "notes": {str(n): note for n, note in review.notes.items()}},
    )


@mcp.tool(
    title="Draft a harmonic analysis from a note list",
    description=(
        "Drafts a harmonic analysis from a compact note list of a score: text starting with a line like "
        "'N1 div=48 ts=12/8 ks=3f', which the Sheet Music Analysis plugin's skill makes from the user's score file, "
        "passed unchanged as `notes`. Returns a neural model's draft as a table: chords as Roman numerals, cadences, "
        "phrase ends and possible non-chord tones, with part-writing findings where they apply. With "
        "student_analysis, the user's own Roman numerals as the skill's script prints them, it also lists beat by "
        "beat where they agree with the draft. Without a note list, or when the user's numerals are ambiguous, the "
        "result is an error that says what is missing."
    ),
    annotations=read_only("Draft a harmonic analysis from a note list"),
)
@observed
async def draft_from_notes(ctx: Context, notes: str, student_analysis: str | None = None) -> CallToolResult:
    source = platform(ctx)
    if not notes.lstrip().startswith("N1"):
        return error_result(NO_NOTE_LIST)
    try:
        if student_analysis:
            await in_turn(check_analysis.student_labels, student_analysis, None, None)
    except check_analysis.ClarificationNeeded as error:
        return error_result(QUESTION_FOR_USER + error.question)
    except ValueError as error:
        return error_result(str(error))
    if not await take("draft", source):
        log("limit", tool="draft_from_notes", platform=source)
        return error_result(LIMIT_MESSAGE)
    started = time.time()
    try:
        with tracer.start_as_current_span("model"):
            result = await in_turn(draft.draft_from_notes, notes)
        with stage("parse"):
            index = await in_turn(note_list.decode, notes)
        if student_analysis:
            student = await in_turn(check_analysis.student_labels, student_analysis, None, index)
    except check_analysis.ClarificationNeeded as error:
        return error_result(QUESTION_FOR_USER + error.question)
    except (note_list.NotesError, draft.DraftError, PositionError, ValueError) as error:
        log("draft_from_notes", platform=source, error=type(error).__name__, chars=len(notes), outcome=outcome_of(error))
        return error_result(str(error))
    def build() -> str:
        text = draft.as_text(result)
        if section := part_writing.as_text(index, result.chords):
            text += "\n\n" + section
        if student_analysis:
            text += "\n\n" + check_analysis.as_text(student, result, index)
        return text

    with stage("build"):
        text = await in_turn(build)
    play_id = secrets.token_hex(8).upper()
    await anyio.to_thread.run_sync(store.put, f"scores/{play_id}.notes", notes.encode())
    text += f"\n\nPLAY: play_id {play_id} plays this passage. Call play with it when the user wants to hear it."
    log("draft_from_notes", platform=source, chars_in=len(notes), seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.custom_route("/files/{name}", methods=["GET"])
async def files(request: Request) -> Response:
    name = request.path_params["name"]
    data = None
    if re.fullmatch(r"[A-Za-z0-9_-]+\.(png|pdf|musicxml|mid|rntxt)", name):
        data = await anyio.to_thread.run_sync(store.get, f"files/{name}")
    if data is None:
        return Response("This file has expired; pages are kept for one day.", status_code=404)
    media_types = {"png": "image/png", "pdf": "application/pdf", "musicxml": "application/vnd.recordare.musicxml+xml",
                   "mid": "audio/midi", "rntxt": "text/plain; charset=utf-8"}
    extension = name.rsplit(".", 1)[1]
    friendly = "worksheet" if name.endswith("-worksheet.pdf") else "analysis"
    disposition = "inline" if extension == "png" else "attachment"
    return Response(data, media_type=media_types[extension], headers={
        "Content-Disposition": f'{disposition}; filename="{friendly}.{extension}"',
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    })


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return Response("ok")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"severity": record.levelname, "message": record.getMessage(), "logger": record.name}
        if record.exc_info:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def start_tracing(service: str) -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=PROJECT)))
    trace.set_tracer_provider(provider)


def main() -> None:
    if sys.argv[1:2] == ["--list-files"]:
        read_ahead.save(SERVER_FILES)
        return
    write_line({"severity": "INFO", "message": "server imported", "imports_s": round(STARTED - IMPORTS_BEGUN, 1),
                "read_ahead": read_ahead.report})
    if service := os.environ.get("K_SERVICE"):
        start_tracing(service)
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    uvicorn.run(traced(without_event_stream(app)), host="0.0.0.0", port=PORT, log_level="warning", log_config=None)


if __name__ == "__main__":
    main()
