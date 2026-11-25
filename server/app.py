from __future__ import annotations

import asyncio
import base64
import contextvars
import functools
import hashlib
import hmac
import io
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sys
import threading
import time
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import anyio
import httpx
import uvicorn
from uvicorn.main import STARTUP_FAILURE
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
from starlette.responses import JSONResponse, Response

from engine import correct, draft, from_notes, read_ahead, verovio_workers
from engine import notes as note_list
from engine import read_pdf as pdf_reader
from engine import check_analysis, ledger, part_writing, reduce
from engine.annotate import AnnotationError, by_number, leave_out_rejected, render
from engine.performance import marked_index, performance_text, unclear_tempos
from engine.annotations import AnnotationList, view_named
from engine.errors import UserError
from engine.export import export_midi, export_musicxml, export_romantext
from engine.render import ScoreError, engrave, load_toolkit, parse_measures, xml_text
from engine.score import PositionError, ScoreIndex
from server import IMPORTS_BEGUN, SERVER_FILES

PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
BUCKET = os.environ.get("BUCKET")
MAX_SCORE_BYTES = 10 * 1024 * 1024
DOWNLOAD_SECONDS = 30
MAX_REDIRECTS = 5
RATING_AFTER_ANALYSES = 3
PERSON_SCORE_LIMIT = int(os.environ.get("PERSON_SCORE_LIMIT", "10"))
DAILY_LIMITS = {"score": 100, "draft": 300, "render": 200, "pdf_page": 150} | json.loads(os.environ.get("DAILY_LIMITS", "{}"))
CARD_URI = "ui://sheet-music-analysis/card-v3.html"
PDF_CARD_URI = "ui://sheet-music-analysis/pdf-card-v3.html"
HELD_CARD_URIS = {"ui://sheet-music-analysis/card-v2.html": "Analysis card",
                  "ui://sheet-music-analysis/pdf-card-v2.html": "PDF reading card"}
PLAYER_URI = "ui://sheet-music-analysis/player-v3.html"
UPLOAD_CARD_URI = "ui://sheet-music-analysis/upload-card-v1.html"
CONNECTOR_URL = os.environ.get("CONNECTOR_URL", "https://mcp.sheetmusicanalysis.com/mcp")
PROXY_KEYS = [key.encode() for key in (os.environ.get("PROXY_KEY"), os.environ.get("PROXY_KEY_PREVIOUS")) if key]
REFUSED_BODY_SECONDS = 3
OWN_ADDRESS = os.environ.get("OWN_ADDRESS", "").rstrip("/")
CLAUDE_UI_DOMAIN = hashlib.sha256(CONNECTOR_URL.encode()).hexdigest()[:32] + ".claudemcpcontent.com"
HERE = Path(__file__).parent

def read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def stores(title: str, open_world: bool = False, again: bool = False) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=False, destructive_hint=False, idempotent_hint=again, open_world_hint=open_world)


class LocalStore:
    def __init__(self, folder: Path):
        self.folder = folder
        self.writing = threading.Lock()

    def put(self, key: str, data: bytes) -> None:
        path = self.folder / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self.folder / key
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        (self.folder / key).unlink(missing_ok=True)

    def get_versioned(self, key: str) -> tuple[bytes | None, int]:
        path = self.folder / key
        return (path.read_bytes(), path.stat().st_mtime_ns) if path.is_file() else (None, 0)

    def put_if(self, key: str, data: bytes, version: int) -> bool:
        with self.writing:
            if self.get_versioned(key)[1] != version:
                return False
            self.put(key, data)
            return True

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

    def delete(self, key: str) -> None:
        try:
            self.bucket.blob(key).delete()
        except NotFound:
            pass

    def get_versioned(self, key: str) -> tuple[bytes | None, int]:
        blob = self.bucket.get_blob(key)
        if blob is None:
            return None, 0
        try:
            return blob.download_as_bytes(if_generation_match=blob.generation), blob.generation
        except (NotFound, PreconditionFailed):
            return self.get_versioned(key)

    def put_if(self, key: str, data: bytes, version: int) -> bool:
        try:
            self.bucket.blob(key).upload_from_string(data, if_generation_match=version)
            return True
        except PreconditionFailed:
            return False

    def add(self, key: str, data: bytes) -> None:
        try:
            self.bucket.blob(key).upload_from_string(data, if_generation_match=0)
        except PreconditionFailed:
            pass


store = BucketStore(BUCKET) if BUCKET else LocalStore(Path(os.environ.get("DATA_DIR", "out/server")))
counter_lock = asyncio.Lock()
pdf_lock = asyncio.Lock()
score_work = anyio.CapacityLimiter(1)
DRAWING_WAIT = 60


async def in_turn(function, *args):
    await anyio.to_thread.run_sync(verovio_workers.claim)
    return await anyio.to_thread.run_sync(function, *args, limiter=score_work)


@asynccontextmanager
async def verovio_request(wait: float):
    request = verovio_workers.Request(wait)
    token = verovio_workers.current.set(request)
    try:
        yield
    finally:
        verovio_workers.current.reset(token)
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(request.release)


def platform(ctx: Context | None) -> str:
    try:
        headers = ctx.headers if ctx else None
    except Exception:
        headers = None
    return client_of(headers)


def for_product(texts: dict[str, str], source: str) -> str:
    return texts["claude" if source == "claude" else "other"]


pseudonym_key: bytes | None = None
months_recorded: set[str] = set()


def pseudonym(value: str) -> str:
    global pseudonym_key
    if pseudonym_key is None:
        store.add("pseudonym-key", secrets.token_bytes(32))
        pseudonym_key = store.get("pseudonym-key")
        if not pseudonym_key:
            raise ValueError("no pseudonym key")
    return hmac.new(pseudonym_key, value.encode(), hashlib.sha256).hexdigest()[:16]


def user_code(subject: str) -> str:
    code = pseudonym(subject)
    month_record = f"users/{code}/{datetime.now(timezone.utc):%Y-%m}"
    if month_record not in months_recorded:
        store.add(month_record, b"")
        months_recorded.add(month_record)
    return code


def client_of(headers) -> str:
    agent = (dict(headers or {}).get("user-agent") or "").lower()
    return "claude" if "claude" in agent else "chatgpt" if "openai" in agent else "other"


PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "sheet-music-analysis")
STARTED = time.monotonic()
SEVERITY = {"ok": "INFO", "degraded": "ERROR", "user_error": "WARNING", "limit": "WARNING", "busy": "WARNING", "server_error": "ERROR", "cancelled": "WARNING"}
current_call: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_call", default=None)
calls_served = 0


def write_line(entry: dict) -> None:
    print(json.dumps(entry), file=sys.stdout, flush=True)


def logged(error: Exception) -> dict:
    return {"error": type(error).__name__, **({"reason": str(error)} if type(error) is ScoreError else {})}


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


def only_through_the_proxy(app):
    refusal = Response(f"This address is not public; use {CONNECTOR_URL}", status_code=403)

    async def checking_the_key(scope, receive, send):
        if PROXY_KEYS and scope["type"] == "http" and scope["path"] != "/health":
            sent = dict(scope["headers"]).get(b"x-proxy-key", b"")
            if not any([hmac.compare_digest(sent, key) for key in PROXY_KEYS]):
                with anyio.move_on_after(REFUSED_BODY_SECONDS):
                    while (await receive()).get("more_body"):
                        pass
                return await refusal(scope, receive, send)
        return await app(scope, receive, send)

    return checking_the_key


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
                call["user"] = await anyio.to_thread.run_sync(user_code, str(subject))
            except Exception as error:
                call["user_code_error"] = f"{type(error).__name__}: {error}"
        calls_served += 1
        timings = {}
        call_token, timings_token = current_call.set(call), draft.timings.set(timings)
        started = time.perf_counter()
        result = None
        try:
            with trace.use_span(span, end_on_exit=False):
                async with verovio_request(DRAWING_WAIT):
                    result = await fn(ctx, *args, **kwargs)
        except verovio_workers.WorkersBusy:
            call["busy"] = True
            result = busy()
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
        return our_error(call["reference"], tool, call["platform"]) if outcome == "server_error" else result

    return wrapper


async def take(kind: str, source: str, amount: int = 1) -> bool:
    return await count(f"usage/{today()}.json", kind, amount, DAILY_LIMITS[kind], f"{kind}:{source}")


async def take_for(person: str | None, amount: int = 1) -> bool:
    return person is None or await count(f"limits/{today()}.json", person, amount, PERSON_SCORE_LIMIT)


async def take_score(person: str | None, source: str) -> str | None:
    if not await take_for(person):
        return "person"
    if not await take("score", source):
        await take_for(person, -1)
        return "shared"
    return None


async def give_back_score(person: str | None, source: str) -> None:
    await take_for(person, -1)
    await take("score", source, -1)


def sent_key(person: str, data: bytes) -> str:
    return f"scores/sent-{pseudonym(f'{person}/{hashlib.sha256(data).hexdigest()}')}"


async def sent_before(person: str | None, data: bytes) -> str | None:
    kept = person and await anyio.to_thread.run_sync(store.get, sent_key(person, data))
    return kept.decode() if kept else None


async def remember_sent(person: str | None, data: bytes, code: str) -> None:
    if person:
        await anyio.to_thread.run_sync(store.put, sent_key(person, data), code.encode())


def caller() -> str | None:
    return (current_call.get() or {}).get("user")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def count(key: str, name: str, amount: int, limit: int, also: str | None = None) -> bool:
    with stage("counter"):
        async with counter_lock:
            while True:
                raw, version = await anyio.to_thread.run_sync(store.get_versioned, key)
                counts = json.loads(raw) if raw else {}
                if counts.get(name, 0) + amount > limit:
                    return False
                for field in filter(None, (name, also)):
                    counts[field] = counts.get(field, 0) + amount
                if await anyio.to_thread.run_sync(store.put_if, key, json.dumps(counts).encode(), version):
                    return True


OUR_ERROR_MESSAGE = (
    "Something went wrong on our side, not with the user's score or request (reference {reference}). "
    "Apologise to the user for us, and tell them that if they would like to tell us what happened or get help, "
    "they can email support@sheetmusicanalysis.com and mention reference {reference}; a link to this chat, made "
    "with the chat's Share button, helps us see what happened, as long as the chat holds no personal details. "
    "We read every message and their feedback helps us fix it."
)
OUR_ERROR_FOR_CARD = "Something went wrong on our side, not with your score."
UNREAD_PDF_FOR_CARD = (
    "The music in this PDF could not be read. A PDF exported from notation software reads best; a scan should be "
    "straight and sharp. A MusicXML file needs no reading at all."
)
FAILED_CALL = "This call failed and produced nothing, so there is no result to describe. "
UNREAD_PDF = "This call failed: no music was read, so there is no score_id and nothing to analyse. "
READING_SHOWN = "This is what I read from your PDF."
CARD_SHOWS_PROBLEM = " The card shows the user this problem with a button that sends it to us."
FAILURES_IN_CARD = {"read_pdf", "render_analysis"}

UPLOAD_LIMIT_MESSAGE = "Today's limit of new scores has been reached; it resets at midnight UTC. Please try again tomorrow."
PERSON_LIMIT_MESSAGE = (
    f"The user has reached today's limit of {PERSON_SCORE_LIMIT} new scores per person; it resets at midnight UTC. "
    "Tell them plainly and that they can analyse the scores they already sent, or try again tomorrow."
)
UPLOAD_PERSON_MESSAGE = (f"You have reached today's limit of {PERSON_SCORE_LIMIT} new scores; it resets at midnight UTC. "
                         "Scores you already sent can still be analysed, and choosing one of them again does not count.")
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
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    return all(ipaddress.ip_address(address).is_global for address in addresses)


IMSLP_REFUSED = (
    "This is an IMSLP link. IMSLP asks each person to accept its copyright notice and, without a membership, to wait "
    "before a download starts, so this server does not download from IMSLP. Tell the user to open the link in their "
    "browser and download the PDF there, then put it in Google Drive or Dropbox, share it so anyone with the link can "
    "view it, and send you that link."
)
FOLDER_REFUSED = "This is a link to a folder. Ask the user for the link to the score file itself."


def is_imslp(host: str) -> bool:
    labels = host.lower().split(".")
    return "imslp" in labels or any(label.startswith("petruccimusiclibrary") for label in labels)


def direct_link(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    if is_imslp(host):
        raise ScoreError(IMSLP_REFUSED)
    if host in ("drive.google.com", "docs.google.com"):
        if "/folders/" in parsed.path:
            raise ScoreError(FOLDER_REFUSED)
        match = re.search(r"/file/d/([\w-]+)", parsed.path)
        file_id = match[1] if match else query.get("id", [None])[0]
        if file_id:
            kept = {"export": "download", "id": file_id} | {key: query[key][0] for key in ("resourcekey",) if key in query}
            return f"https://drive.google.com/uc?{urlencode(kept)}"
    if host in ("dropbox.com", "www.dropbox.com"):
        if parsed.path.startswith(("/sh/", "/scl/fo/")):
            raise ScoreError(FOLDER_REFUSED)
        kept = {key: values[0] for key, values in query.items() if key not in ("dl", "raw")} | {"dl": "1"}
        return parsed._replace(query=urlencode(kept)).geturl()
    return parsed.geturl()


async def download(url: str) -> bytes:
    try:
        with anyio.fail_after(DOWNLOAD_SECONDS):
            async with httpx.AsyncClient(timeout=20) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    if is_imslp(urlparse(url).hostname or ""):
                        raise ScoreError(IMSLP_REFUSED)
                    if not await anyio.to_thread.run_sync(is_public_https, url):
                        raise ScoreError("The file's link is not a public https URL")
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
        raise ScoreError(f"The file took longer than {DOWNLOAD_SECONDS} seconds to download") from error
    raise ScoreError("The file's link redirects too many times")


ATTACHMENT_ANSWERED = (
    "The attached file could not be downloaded from the chat (HTTP {status}). Ask the user to attach it again in a "
    "new message."
)
ATTACHMENT_UNREACHABLE = "The attached file could not be downloaded from the chat. Ask the user to attach it again in a new message."


async def download_attachment(url: str) -> bytes:
    try:
        return await download(url)
    except httpx.HTTPStatusError as error:
        log("download", host=urlparse(url).hostname, status=error.response.status_code)
        raise ScoreError(ATTACHMENT_ANSWERED.format(status=error.response.status_code)) from error
    except httpx.HTTPError as error:
        log("download", host=urlparse(url).hostname, download_error=type(error).__name__)
        raise ScoreError(ATTACHMENT_UNREACHABLE) from error


def clean_id(score_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", score_id).upper()


NO_SCORE_GIVEN = {
    "claude": "No score was provided. Call choose_score so the user can choose their score file in a card.",
    "other": "No score was provided. Ask the user to attach their MusicXML file (.mxl or .musicxml) to the chat.",
}


async def resolve_score(score_file: AttachedFile | None, score_id: str | None, source: str = "other") -> tuple[bytes, str]:
    with stage("fetch"):
        if score_file:
            data = await download_attachment(score_file.download_url)
            if data.startswith(b"%PDF"):
                raise ScoreError("This file is a PDF. Call read_pdf with it first, then use the score_id it returns.")
            return data, "score_file"
        if score_id:
            code = clean_id(score_id)
            data = await anyio.to_thread.run_sync(store.get, f"scores/{code}")
            if data is None:
                if await anyio.to_thread.run_sync(store.get, f"scores/{code}.pdf") is not None:
                    raise ScoreError(f"This score is a PDF. Call read_fetched_pdf with pdf_id {code} first, then use "
                                     "the score_id it returns.")
                if await anyio.to_thread.run_sync(store.get, f"scores/{code}.waiting") is not None:
                    raise NotChosenYet(NOT_CHOSEN_YET)
                raise ScoreError("No score has that id; scores are kept for 30 days")
            return data, "score_id"
    raise ScoreError(for_product(NO_SCORE_GIVEN, source))


def publish(data: bytes, extension: str, suffix: str = "") -> str:
    name = f"{secrets.token_urlsafe(12)}{suffix}.{extension}"
    store.put(f"files/{name}", data)
    return f"{PUBLIC_BASE_URL}/files/{name}"


def publish_worksheet(score: bytes, measures: tuple[int, int] | None, piano: bool) -> str:
    name = f"{secrets.token_urlsafe(12)}-worksheet.pdf"
    store.put(f"files/{name}.score", score)
    store.put(f"files/{name}.recipe", json.dumps({"measures": measures, "piano": piano}).encode())
    return f"{PUBLIC_BASE_URL}/files/{name}"


def make_worksheet(name: str) -> bytes | None:
    score, recipe = store.get(f"files/{name}.score"), store.get(f"files/{name}.recipe")
    if score is None or recipe is None:
        return None
    recipe = json.loads(recipe)
    measures = tuple(recipe["measures"]) if recipe["measures"] else None
    return render(score, AnnotationList(annotations=[]), measures=measures, piano=recipe["piano"]).pdf()


def waiting_for_choice(tool: str, source: str) -> CallToolResult:
    log(tool, platform=source, not_chosen=True)
    return CallToolResult(content=[TextContent(type="text", text=NOT_CHOSEN_YET)])


def error_result(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def failure(message: str, report: dict | None) -> CallToolResult:
    if not report:
        return error_result(message)
    return CallToolResult(content=[TextContent(type="text", text=message)], structured_content={}, meta={"report": report})


def our_error(reference: str, tool: str, source: str) -> CallToolResult:
    message = OUR_ERROR_MESSAGE.format(reference=reference)
    if tool not in FAILURES_IN_CARD or source == "claude":
        return error_result(message)
    return failure(FAILED_CALL + message + CARD_SHOWS_PROBLEM, {"text": OUR_ERROR_FOR_CARD, "reference": reference})


ANNOTATION_FORMAT = (
    "render_analysis annotations are nested objects, e.g. "
    "{\"type\": \"harmony\", \"at\": {\"measure\": 1, \"beat\": 1}, \"label\": \"I\", \"key\": \"F\"}, "
    "{\"type\": \"cadence\", \"at\": {\"measure\": 8, \"beat\": 1}, \"label\": \"PAC\"}, "
    "{\"type\": \"phrase\", \"start\": {\"measure\": 1, \"beat\": 1}, \"end\": {\"measure\": 8}}, "
    "{\"type\": \"callout\", \"at\": {\"measure\": 3, \"beat\": 2}, \"number\": 1}.\n"
)
DRAW_BUDGET = 2000


def drawing_plan(mei: str, index: ScoreIndex) -> str:
    staves = max(int(n) for n in re.findall(r'<staffDef\b[^>]*?\bn="(\d+)"', mei))
    if staves * len(index.measures) <= DRAW_BUDGET:
        return ('One render_analysis call draws any number of bars: for the whole piece pass measure_range "all", '
                "so the user gets one PDF.\n")
    return (f"This score is too large to draw whole in one call: call render_analysis on passages of at most "
            f"{DRAW_BUDGET // staves} bars.\n")


SKILL_RULES = re.sub(r"<!--.*?-->\n+", "", (HERE.parent / "skill" / "SKILL.md").read_text().split("## Method", 1)[1])
DRAW_STEP = (
    "call render_analysis with the score_id and your annotation list (its `view` argument draws one layer: "
    "harmony, voice_leading or form), show the page and write the commentary.\n"
)
GUIDE_RULES = (
    "Positions: `measure` is the bar as the NOTES table names it: its printed number, or a name like \"16a\" for a "
    "bar the printed copy does not number (a pickup is 0); `beat` is 1-based in the unit given above; "
    "`pitch` is like \"Eb4\" at sounding pitch; `staff` 1 is the top staff.\n\n"
    "If there is a PART-WRITING CHECK section (chorale-style scores only), your first reply must include one "
    "sentence offering to check the voice leading; draw nothing from it "
    "unless the user says yes or asked for it. When they want it, add "
    "one callout per numbered spot and the voice_leading marks listed under it (kind, notes and label exactly as given; use the NoteRefs "
    "given), and explain every finding of a spot in its numbered paragraph of the commentary, in terms of the notes. "
    "Call these strict classroom rules, not verdicts on a composer.\n\n"
    "If there is a STUDENT CHECK section, the user wants their own numerals checked: draw the "
    "page as usual from your own analysis (how their numerals are marked on it is not decided yet), and write the commentary as a second "
    "reader would, not as an answer key, following that section's guidance. This is for learning; if they say it is "
    "coursework, remind them to check their course's rules on AI help.\n"
)
NOTES_GUIDE = (
    "HOW TO ANALYSE THIS SCORE\n"
    "The user sees nothing while you work, so once per request (not for each passage of a long piece) write them one "
    "short sentence before you analyse, such as \"I have the notes and am working out the harmony now; this takes a "
    "minute or two.\", and one before your first render_analysis call, such as \"Now I'm drawing the analysis on the "
    "score.\"\n"
    "Analyse from the NOTES table below, following the method below. If the user asked for their own numerals to be "
    "checked and there is no STUDENT CHECK section, compare them with your reading of the NOTES table. Then "
    + DRAW_STEP + GUIDE_RULES
)
METHOD = "## Method" + SKILL_RULES


def make_draft(score: bytes, code: str, named: tuple[str, str] | None, student_analysis: str | None = None) -> str:
    with stage("parse"):
        mei = load_toolkit(score).getMEI()
        index = ScoreIndex(mei)
    with stage("build"):
        first, last = index.numbers(named) or (None, None)
        unit = index.measure(first or index.measures[-1].number).beat_length
        numbers = index.name_span
        sections = [
            ("part_writing", lambda: part_writing.as_text(index, None, first, last)),
            ("ledger", lambda: ledger.as_text(mei, index, first, last)),
            ("student_check", lambda: check_analysis.as_text(
                check_analysis.student_labels(student_analysis, score, index), index) if student_analysis else ""),
        ]
        return (
            f"score_id: {code}\nThe score has measures {numbers}. One beat = {float(unit):g} quarter notes.\n"
            + ANNOTATION_FORMAT + drawing_plan(mei, index) + "\n"
            + NOTES_GUIDE
            + "".join("\n" + text + "\n" for text in (optional(name, make) for name, make in sections) if text)
            + "\n\n" + METHOD
            + "\n\nNOTES (one row per beat: lowest note, pitch classes, every note as pitch@beat)\n"
            + reduce.as_text(index, first, last)
            + f"\n\nWhen you have analysed every bar the user asked for, draw them as this reply says above, with "
            f"render_analysis and score_id {code}; the analysis is not finished until the page is drawn."
        )


def optional(name: str, make) -> str:
    try:
        return make()
    except check_analysis.ClarificationNeeded:
        raise
    except Exception as error:
        log("draft_analysis", outcome="degraded", section_error=f"{name}: {type(error).__name__}",
            stack_trace=traceback.format_exc())
        return ""


apps = Apps()


def musicxml_text(url: str, annotations: AnnotationList) -> str:
    # Without harmony annotations the export is the unmodified original, so it has no labels to mention.
    if not any(item.type == "harmony" for item in annotations.annotations):
        return f"MusicXML (open in MuseScore, Sibelius or Dorico): {url}"
    return (f"MusicXML with the harmony labels (open in MuseScore, Sibelius or Dorico): {url}\n"
            "The file uses standard Roman numerals whatever the page style.")


EXTRA_FILES = {"midi": ("mid", ""), "romantext": ("rntxt", "")}
worksheet_lock = anyio.Lock()


def downloads_text(links: dict[str, str]) -> str:
    names = {"worksheet_url": "Blank worksheet (the same passage with no analysis, PDF)", "midi_url": "MIDI",
             "romantext_url": "Analysis as text (the key and the Roman numeral of each chord, bar by bar, as a text file)"}
    present = [f"{label}: {links[key]}" for key, label in names.items() if key in links]
    if not present:
        return ""
    return ("\nMore downloads, shown on the card under \"More downloads\"; mention them to the user once per "
            "conversation, not after every render, by the names given here:\n" + "\n".join(present))


CARD_PAGES = 2
MOSTLY_DOUBTFUL = 0.5


NOTHING_DRAWN = (
    "No analysis marks were drawn: the annotation list was empty, so the page shows only the score. To analyse, "
    "call draft_analysis with score_id {score_id}, review the draft, then call render_analysis with your annotation list."
)


VIEW_NAMES = {"all": "", "harmony": ", harmony only", "voice_leading": ", voice leading only", "form": ", form only"}


def card_caption(named: tuple[str, str] | None, view: str, piano: bool) -> str:
    bars = f"bars {named[0]}–{named[1]}" if named and named[0] != named[1] else f"bar {named[0]}" if named else "the whole score"
    return f"Analysis of {bars}{VIEW_NAMES[view]}" + (", piano reduction" if piano else "")


KEY_ON_PAGE = ("The page has a guide to the marks at its foot (under the last page the card shows, at the end of the last page "
               "in the PDF). It names the marks and codes drawn around the numerals: cadence labels, non-chord-tone and "
               "part-writing codes, alternative-reading brackets, callouts and shaded bars, so do "
               "not define those again. It does not explain Roman "
               "numerals, figures or inversions: for a student, still explain each numeral the first time it appears. Say "
               "what each numbered callout is about and explain the reasoning behind the labels.")


CALLOUTS_DRAWN = ("Numbered callouts drawn on the page: {numbers}. Number your commentary paragraphs to match exactly "
                  "these, one paragraph for each callout.")
NO_CALLOUTS = ("No numbered callouts are drawn on the page, so do not write the commentary as numbered points: the "
               "reader would look for numbers that are not there.")


def callouts_text(numbers: list[int]) -> str:
    return CALLOUTS_DRAWN.format(numbers=", ".join(map(str, numbers))) if numbers else NO_CALLOUTS


SHADED_ON_PAGE = ("Shaded bars ({bars}) may be misread from the PDF, so their analysis may be wrong. Mention this "
                  "briefly in your reply, and that the user can tell you what a misread bar should be.")


def shaded_key(score_id: str) -> str:
    return f"scores/{clean_id(score_id)}.shaded"


async def shaded_bars(score_id: str) -> list[int]:
    return json.loads(await anyio.to_thread.run_sync(store.get, shaded_key(score_id)) or b"[]")


async def draw(score: bytes, annotations: AnnotationList, index: ScoreIndex, measures: tuple[int, int] | None, view: str,
               piano: bool, shaded: list[int]):
    engraving, annotations, problems = await in_turn(
        lambda: leave_out_rejected(lambda kept: render(score, kept, measures=measures, view=view, piano=piano,
                                                       shaded_bars=shaded, key=True, preview_pages=CARD_PAGES),
                                     annotations, lambda given: by_number(given, index)))
    left_out = ["Left out, for the reason on each line (fix them and call again to add them; numbers refer to your "
                "list):\n" + "\n".join(problems)] if problems else []
    return engraving, annotations, left_out


@apps.tool(
    resource_uri=CARD_URI,
    title="Draw the analysis on the score",
    description=(
        "Use this after draft_analysis, once you have reviewed the draft, to draw your analysis on the engraved "
        "score. Takes the score_id and your annotation list and returns the page as an image plus PNG, PDF and MusicXML "
        "links, shown to the user in a card. A bar is its printed number or, for a bar the printed copy does not number "
        "(such as a second-time ending), the name the draft gives it, such as \"16a\"; measure_range takes the same, "
        "e.g. \"16a-20\". If a position does not exist in the score, the error lists each "
        "problem so you can fix the list and call again. Draw the whole stretch the user asked for in one call, "
        "even a whole piece, so they get one PDF; analyse a long piece passage by passage first. view is one of all, harmony, voice_leading, form. "
        "Set annotations.style to abrsm (letter inversions, Ib, Vc) when the user mentions ABRSM, figured_bass when they ask "
        "for figured bass, otherwise leave it out. "
        "Offer the MusicXML link once per conversation, not after every render: it downloads a file for "
        "MuseScore, Sibelius or Dorico; the result also lists the card's other downloads (Blank worksheet, MIDI, Analysis as text) to mention once. "
        "piano=true draws the same annotation list (written for the original score) on a two-staff piano reduction. "
        "For a score with more than four staves (an orchestra, band or large ensemble), draw the original first, then offer the user "
        "the piano reduction once; call again with piano=true only if they accept."
    ),
    annotations=stores("Draw the analysis on the score"),
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
    asked = len(annotations.annotations)
    try:
        score, _ = await resolve_score(None, score_id, source)
        named = parse_measures(measure_range)
        view = view_named(view)
        with stage("parse"):
            index = await in_turn(lambda: ScoreIndex(load_toolkit(score).getMEI()))
        measures = index.numbers(named)
        chosen = {measure.number for measure in index.select(*(measures or (None, None)), include_pickup=False)}
        shaded = [bar for bar in await shaded_bars(score_id) if bar in chosen]
        if not await take("render", source):
            log("limit", tool="render_analysis", platform=source)
            return error_result(LIMIT_MESSAGE)
        with stage("render"):
            engraving, annotations, left_out = await draw(score, annotations, index, measures, view, piano, shaded)
    except AnnotationError as error:
        log("render_analysis", platform=source, problems=len(error.problems))
        return error_result("Fix these annotations and call again:\n" + "\n".join(error.problems))
    except UserError as error:
        log("render_analysis", platform=source, **logged(error))
        return error_result(str(error))
    drawn = (index.name_of(measures[0]), index.name_of(measures[1])) if measures else None
    measure_range = f"{drawn[0]}-{drawn[1]}" if drawn else "all"
    musicxml, export_warning = None, None
    try:
        with stage("export"):
            musicxml = await in_turn(export_musicxml, score, annotations.model_dump())
    except Exception as error:
        export_warning = "MusicXML export unavailable for this score. PNG and PDF are available."
        log("render_analysis", platform=source, export_error=type(error).__name__)

    with stage("render"):
        png = await in_turn(lambda: engraving.preview.png(1, pages=CARD_PAGES))
    def publish_all():
        with stage("render"):
            image, pdf = engraving.preview.png(1, width=1400, colors=256, pages=CARD_PAGES), engraving.pdf()
        with stage("publish"):
            links = {"image_url": publish(image, "png"), "pdf_url": publish(pdf, "pdf")}
            if musicxml is not None:
                links["musicxml_url"] = publish(musicxml, "musicxml")
            if asked:
                links["worksheet_url"] = publish_worksheet(score, measures, piano)
                for name, make in (("midi", lambda: export_midi(score, measures)),
                                   ("romantext", lambda: export_romantext(score, annotations.model_dump(), measures))):
                    try:
                        data = make()
                    except Exception as error:
                        log("render_analysis", platform=source, extra_error=f"{name}: {type(error).__name__}")
                        continue
                    if data:
                        links[f"{name}_url"] = publish(data, *EXTRA_FILES[name])
        return links
    links = await in_turn(publish_all)
    pdf_url = links["pdf_url"]
    caption = f"Analysis, measures {measure_range}, view {view}" + (", piano reduction" if piano else "")
    more_pages = (f"\nThe card shows the first {CARD_PAGES} of the {engraving.page_count} pages; the PDF has them all. "
                  "Tell the user to open the PDF for the rest." if engraving.page_count > CARD_PAGES else "")
    log("render_analysis", platform=source, annotations=len(annotations.annotations), png_bytes=len(png), piano=piano,
        view=view, measure_range=measure_range, left_out=asked - len(annotations.annotations) or None)
    shaded = [index.measure(bar).printed for bar in shaded]
    structured_content = {**links, "caption": card_caption(drawn, view, piano), "shaded_bars": shaded}
    if not asked:
        left_out.append(NOTHING_DRAWN.format(score_id=score_id))
    else:
        left_out.append(callouts_text(engraving.callouts))
        if engraving.preview.key_drawn:
            left_out.append(KEY_ON_PAGE)
    if shaded:
        left_out.append(SHADED_ON_PAGE.format(bars=", ".join(map(str, shaded))))
    return CallToolResult(
        meta={"ask_for_rating": True} if await rating_is_due(ctx) else None,
        content=[
            ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"),
            TextContent(type="text", text="".join(f"{note}\n\n" for note in left_out)
                        + f"{caption}, shown in a card. PDF: {pdf_url}\nPNG: {links['image_url']}{more_pages}\n"
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
            key = f"chats/{pseudonym(str(chat))}"
            while True:
                raw, version = store.get_versioned(key)
                analyses = int(raw or 0) + 1
                if store.put_if(key, str(analyses).encode(), version):
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
    annotations=stores("Rate an analysis"),
)
@observed
async def rate_analysis(ctx: Context, helpful: bool) -> CallToolResult:
    log("rate_analysis", helpful=helpful)
    return CallToolResult(content=[TextContent(type="text", text="Thanks; the rating is recorded.")])


@apps.tool(
    resource_uri=CARD_URI,
    visibility=["app"],
    title="Report a problem",
    description="Records that the user sent us the problem shown in the card, by its reference.",
    annotations=stores("Report a problem"),
)
@observed
async def report_problem(ctx: Context, reference: str) -> CallToolResult:
    if not re.fullmatch(r"[0-9a-f]{8}", reference):
        return error_result("Not a reference.")
    log("report_problem", about=reference)
    return CallToolResult(content=[TextContent(type="text", text="Thanks; the report is recorded.")])


SUGGESTION_LENGTH = 1000


@apps.tool(
    resource_uri=CARD_URI,
    visibility=["app"],
    title="Send a suggestion",
    description="Records a suggestion the user typed into the card.",
    annotations=stores("Send a suggestion"),
)
@observed
async def send_suggestion(ctx: Context, text: str) -> CallToolResult:
    text = text.strip()
    if not 0 < len(text) <= SUGGESTION_LENGTH:
        return error_result(f"A suggestion is 1 to {SUGGESTION_LENGTH} characters.")
    log("send_suggestion", text=text)
    return CallToolResult(content=[TextContent(type="text", text="Thanks; the suggestion is recorded.")])


for uri, name, card in [(CARD_URI, "Analysis card", "card.html"), (PDF_CARD_URI, "PDF reading card", "card.html"),
                        *((uri, name, "card-v2.html") for uri, name in HELD_CARD_URIS.items())]:
    apps.add_html_resource(
        uri,
        (HERE / card).read_text(),
        name=name,
        csp=ResourceCsp(resource_domains=[PUBLIC_BASE_URL]),
        domain="https://sheetmusicanalysis.com",
        prefers_border=True,
    )

PDF_WAIT = "a PDF usually takes a minute or two to read; a long one can take several minutes"
BUSY_MESSAGE = (
    f"Another PDF is being read right now, and {PDF_WAIT}. Tell the user plainly that the "
    "service is busy reading another PDF and to send theirs again in a few minutes."
)
SAME_FILE_WAIT = 100
REQUEST_SECONDS = 900
STARTER_WAIT = REQUEST_SECONDS - DOWNLOAD_SECONDS - 15
READ_MARKER_SECONDS = REQUEST_SECONDS
READ_MINUTES = round((pdf_reader.TIMEOUT + 120) / 60)
POLL_SECONDS = 3
STILL_READING = (
    "This PDF is still being read ({elapsed} so far): " + PDF_WAIT + ", up to about {minutes} minutes. Tell the user in one "
    "short sentence how long it has been reading and that the card will show what was read, then you analyse it; "
    "then call {again}; each call waits up to {wait} s for the result."
)
STILL_READING_STATUS = "Still reading your PDF: {elapsed} so far. What I read appears next, then the analysis."
WAITING_FOR_TURN = (
    "The user's previous PDF is still being read, and this one is read after it: " + PDF_WAIT + ". Tell the user, then "
    "call {again} in a minute or two."
)
WAITING_FOR_TURN_STATUS = "Your previous PDF is still being read; this one is read after it."
BUSY_STATUS = "Another PDF is being read right now. Send yours again in a few minutes."
LOST_TURN = "lost the turn"
READ_NOT_TAKEN = {401, 403, 404, 429}
CALL_AGAIN = {"read_pdf": "read_pdf again with the same file", "read_fetched_pdf": "read_fetched_pdf again with the same pdf_id"}


def elapsed(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes} min {seconds} s" if minutes else f"{seconds} s"


def reading_status(text: str, status: str, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content={"status": status},
                          is_error=is_error)


def still_reading(since: float, tool: str) -> CallToolResult:
    so_far = elapsed(time.time() - since)
    return reading_status(STILL_READING.format(elapsed=so_far, again=CALL_AGAIN[tool], wait=SAME_FILE_WAIT, minutes=READ_MINUTES),
                          STILL_READING_STATUS.format(elapsed=so_far))


def busy() -> CallToolResult:
    return reading_status(BUSY_MESSAGE, BUSY_STATUS, is_error=True)
pdfs_reading: dict[str, tuple[asyncio.Task, float]] = {}
reads_held: dict[str, str] = {}
claiming = asyncio.Lock()


@apps.tool(
    resource_uri=PDF_CARD_URI,
    title="Read a PDF of sheet music",
    description=(
        "Use this when the user attaches a PDF of printed sheet music (born-digital or scanned) and wants it analysed. "
        "Reads the music from the PDF and shows the user the engraved result in a card, with bars that may be misread "
        "shaded. Returns a score_id. Then, unless the result tells you to ask the user a question first, go straight on without waiting for the user: call draft_analysis with that "
        f"score_id and continue as for a MusicXML file. Only the first {pdf_reader.READ_PAGES} pages are read. "
        "Slurs are not read, because they are often misread from PDFs; if the user asks for slurs, tell them so."
    ),
    annotations=stores("Read a PDF of sheet music", again=True),
    meta={"openai/outputTemplate": PDF_CARD_URI, "openai/fileParams": ["pdf_file"]},
)
@observed
async def read_pdf(ctx: Context, pdf_file: AttachedFile) -> CallToolResult:
    source, person = platform(ctx), caller()
    kept = None
    if person and pdf_file.file_id:
        attachment = await anyio.to_thread.run_sync(pseudonym, f"{person}/{pdf_file.file_id}")
        kept = f"scores/attached-{attachment}.pdf"
    try:
        with stage("fetch"):
            data = kept and await anyio.to_thread.run_sync(store.get, kept)
            if kept:
                log("read_pdf", attachment=attachment, attachment_kept=data is not None)
            if not data:
                data = await download_attachment(pdf_file.download_url)
                if kept and data.startswith(b"%PDF"):
                    await anyio.to_thread.run_sync(store.put, kept, data)
        if not data.startswith(b"%PDF"):
            raise ScoreError("This file is not a PDF. Ask the user to attach a PDF of the printed music or a MusicXML file.")
    except ScoreError as error:
        log("read_pdf", platform=source, **logged(error))
        return error_result(str(error))
    return await read_pdf_data(data, source, "read_pdf")


async def read_pdf_data(data: bytes, source: str, tool: str) -> CallToolResult:
    digest = hashlib.sha256(data).hexdigest()
    card_key = card_of(digest)
    if card := await anyio.to_thread.run_sync(store.get, card_key):
        card = json.loads(card)
        log(tool, platform=source, pages=card["pages"], cached="card")
        return pdf_card_result(card, tool, source)
    failed = json.loads(await anyio.to_thread.run_sync(store.get, failure_of(card_key)) or b"{}")
    if (unread := failed.get("unread")) and unread["final"]:
        log(tool, platform=source, outcome="user_error", error=failed["error"], reference=unread["reference"], cached="unread")
        return unread_result(unread, source)
    person, arrived_at = caller(), time.time()
    starter_wait = STARTER_WAIT if source != "claude" else SAME_FILE_WAIT
    while True:
        if not person or card_key in pdfs_reading or await turn_is_free(person, card_key):
            async with claiming:
                started_here = card_key not in pdfs_reading
                if started_here:
                    token, elsewhere = await claim_read(card_key)
                    if token is not None:
                        reads_held[card_key] = token
                    if token is not None and person and not await take_turn(person, card_key, token):
                        reads_held.pop(card_key, None)
                        await release_read(card_key, token)
                        token = LOST_TURN
                if started_here and token not in (None, LOST_TURN):
                    work = contextvars.copy_context()
                    work.run(current_call.set, None)
                    work.run(draft.timings.set, None)
                    task = asyncio.create_task(started_read(data, digest, source, card_key, token, tool == "read_pdf", person), context=work)
                    pdfs_reading[card_key] = task, time.time()
                    task.add_done_callback(lambda _: pdfs_reading.pop(card_key, None))
            if not (started_here and token == LOST_TURN):
                break
        if card := await anyio.to_thread.run_sync(store.get, card_key):
            card = json.loads(card)
            log(tool, platform=source, pages=card["pages"], cached="card")
            return pdf_card_result(card, tool, source)
        if time.time() - arrived_at >= min(SAME_FILE_WAIT, starter_wait):
            log(tool, platform=source, reading=True, waiting_turn=True)
            return reading_status(WAITING_FOR_TURN.format(again=CALL_AGAIN[tool]), WAITING_FOR_TURN_STATUS)
        await anyio.sleep(POLL_SECONDS)
    remaining = max(starter_wait - (time.time() - arrived_at), 0)
    if started_here and token is None:
        return await wait_for_other_machine(card_key, elsewhere, source, tool, min(SAME_FILE_WAIT, remaining))
    task, since = pdfs_reading[card_key]
    with anyio.move_on_after(min(starter_wait if started_here else SAME_FILE_WAIT, remaining)):
        await asyncio.shield(task)
    if not task.done():
        log(tool, platform=source, reading=True)
        return still_reading(since, tool)
    result, details = task.result()
    if started_here and (timings := draft.timings.get()) is not None:
        timings.update({name: value for name, value in details.get("timings_ms", {}).items() if name != "total"})
    if details["outcome"] == "server_error":
        current_call.get().update(event=tool, platform=source, outcome="server_error",
                                  reference=details["reference"], stack_trace=details["stack_trace"])
        return result
    if "reference" in details:
        current_call.get()["reference"] = details["reference"]
    if details.get("limit"):
        log("limit", tool=tool, platform=source, pages=details.get("pages"))
    else:
        log(tool, platform=source, outcome=details["outcome"],
            **{key: details[key] for key in ("busy", "error") if key in details})
    return pdf_card_result(result, tool, source) if isinstance(result, dict) else result


def card_of(digest: str) -> str:
    return f"scores/pdf-card-{pdf_reader.READER}-{digest}.json"


def marker_of(card_key: str) -> str:
    return card_key.replace("pdf-card-", "pdf-reading-")


def failure_of(card_key: str) -> str:
    return card_key.replace("pdf-card-", "pdf-failed-")


async def claim_read(card_key: str) -> tuple[str | None, float]:
    token, now = secrets.token_hex(8), time.time()
    mine = json.dumps({"token": token, "started": now}).encode()
    for _ in range(2):
        await anyio.to_thread.run_sync(store.add, marker_of(card_key), mine)
        found = json.loads(await anyio.to_thread.run_sync(store.get, marker_of(card_key)) or b"{}")
        if found.get("token") == token:
            return token, now
        if now - found.get("started", 0) <= READ_MARKER_SECONDS:
            return None, found["started"]
        await release_read(card_key, found.get("token"))
    return None, now


def person_reading(person: str) -> str:
    return f"scores/pdf-person-{person}.json"


async def turn_holder(person: str) -> tuple[dict, int]:
    found, version = await anyio.to_thread.run_sync(store.get_versioned, person_reading(person))
    return json.loads(found or b"{}"), version


async def holds_turn(holder: dict, card_key: str) -> bool:
    if holder.get("card") in (None, card_key):
        return False
    found = json.loads(await anyio.to_thread.run_sync(store.get, marker_of(holder["card"])) or b"{}")
    return found.get("token") == holder.get("token") and time.time() - found.get("started", 0) <= READ_MARKER_SECONDS


async def turn_is_free(person: str, card_key: str) -> bool:
    holder, _ = await turn_holder(person)
    return not await holds_turn(holder, card_key)


async def take_turn(person: str, card_key: str, token: str) -> bool:
    holder, version = await turn_holder(person)
    if await holds_turn(holder, card_key):
        return False
    turn = json.dumps({"card": card_key, "token": token}).encode()
    return await anyio.to_thread.run_sync(store.put_if, person_reading(person), turn, version)


def release_marker(card_key: str, token: str | None) -> None:
    found = json.loads(store.get(marker_of(card_key)) or b"{}")
    if found.get("token") == token:
        store.delete(marker_of(card_key))


async def release_read(card_key: str, token: str | None) -> None:
    await anyio.to_thread.run_sync(release_marker, card_key, token)


def release_reads_at_shutdown() -> None:
    released, failed = 0, 0
    for card_key, token in list(reads_held.items()):
        reads_held.pop(card_key, None)
        try:
            release_marker(card_key, token)
            released += 1
        except Exception:
            failed += 1
    if released or failed:
        write_line({"severity": "WARNING", "message": "released reads at shutdown", "reads": released, "failed": failed})


class HttpServer(uvicorn.Server):
    def handle_exit(self, sig, frame) -> None:
        asyncio.get_running_loop().call_soon_threadsafe(release_reads_at_shutdown)
        super().handle_exit(sig, frame)


async def wait_for_other_machine(card_key: str, since: float, source: str, tool: str, wait: float) -> CallToolResult:
    with anyio.move_on_after(wait):
        while True:
            if card := await anyio.to_thread.run_sync(store.get, card_key):
                log(tool, platform=source, other_machine=True)
                return pdf_card_result(json.loads(card), tool, source)
            found = json.loads(await anyio.to_thread.run_sync(store.get, failure_of(card_key)) or b"{}")
            if found.get("at", 0) >= since:
                if found["error"] == "limit":
                    log("limit", tool=tool, platform=source, other_machine=True)
                else:
                    log(tool, platform=source, other_machine=True, outcome=found.get("outcome"),
                        **({"busy": True} if found["error"] == "busy" else {"error": found["error"]}))
                if found["error"] == "busy":
                    return busy()
                return unread_result(found["unread"], source) if "unread" in found else failure(found["text"], found.get("report"))
            await anyio.sleep(POLL_SECONDS)
    log(tool, platform=source, reading=True, other_machine=True)
    return still_reading(since, tool)


def unread_result(unread: dict, source: str) -> CallToolResult:
    if source == "claude":
        return error_result(unread["reason"] + pdf_reader.NEXT_STEP)
    return failure(UNREAD_PDF + unread["reason"] + pdf_reader.NEXT_STEP + CARD_SHOWS_PROBLEM,
                   {"text": f"{unread['reason']}." if unread["too_small"] else UNREAD_PDF_FOR_CARD,
                    "reference": unread["reference"]})


class ReadNotTaken(Exception):
    pass


async def started_read(data: bytes, digest: str, source: str, card_key: str,
                       token: str, arrived: bool, person: str | None) -> tuple[dict | CallToolResult, dict]:
    if OWN_ADDRESS:
        reads_held.pop(card_key, None)
        try:
            return await read_in_its_own_request(data, source, token, arrived, person)
        except ReadNotTaken as refused:
            write_line({"severity": "WARNING", "message": "read_pdf_work was not taken as a request of its own; reading here",
                        "reason": str(refused)})
        except Exception:
            details = {"event": "read_pdf_work", "platform": source, "stack_trace": traceback.format_exc(),
                       "reference": secrets.token_hex(4)}
            return await recorded(data, digest, card_key, our_error(details["reference"], "read_pdf", source),
                                  "server_error", details, {}, time.perf_counter(), None)
    return await pdf_work(data, digest, source, card_key, token, arrived, person)


async def read_in_its_own_request(data: bytes, source: str, token: str, arrived: bool,
                                  person: str | None) -> tuple[dict | CallToolResult, dict]:
    asked = {"x-read-source": source, "x-read-token": token, "x-read-arrived": str(int(arrived)),
             **({"x-read-person": person} if person else {}), **({"x-proxy-key": PROXY_KEYS[0].decode()} if PROXY_KEYS else {})}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_SECONDS, connect=10)) as client:
            answer = await client.post(f"{OWN_ADDRESS}/read-work", content=data, headers=asked)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol, httpx.InvalidURL) as error:
        raise ReadNotTaken(type(error).__name__) from error
    if answer.status_code in READ_NOT_TAKEN:
        raise ReadNotTaken(f"status {answer.status_code}")
    answer.raise_for_status()
    sent = answer.json()
    return sent["card"] or CallToolResult.model_validate(sent["refusal"]), sent["details"]


async def pdf_work(data: bytes, digest: str, source: str, card_key: str,
                   token: str, arrived: bool, person: str | None) -> tuple[dict | CallToolResult, dict]:
    details = {"event": "read_pdf_work", "platform": source}
    timings = {}
    current_call.set(details)
    draft.timings.set(timings)
    reads_held[card_key] = token
    started = time.perf_counter()
    try:
        async with verovio_request(pdf_reader.TIMEOUT):
            return await pdf_outcome(data, digest, source, card_key, details, timings, started, arrived, person)
    finally:
        reads_held.pop(card_key, None)
        await release_read(card_key, token)


async def pdf_outcome(data: bytes, digest: str, source: str, card_key: str, details: dict,
                      timings: dict, started: float, arrived: bool, person: str | None) -> tuple[dict | CallToolResult, dict]:
    unread = None
    try:
        result = await read_pdf_card(data, digest, source, arrived, person)
        if isinstance(result, dict):
            await anyio.to_thread.run_sync(store.put, card_key, json.dumps(result).encode())
        outcome = "ok" if isinstance(result, dict) else "limit" if details.get("limit") else "busy" if details.get("busy") else "user_error"
    except pdf_reader.ReadError as error:
        details.update(error=type(error).__name__, passes=error.passes or None, reason=str(error),
                       reference=secrets.token_hex(4))
        unread = {"reason": str(error), "too_small": isinstance(error, pdf_reader.ScanTooSmall),
                  "reference": details["reference"], "final": error.lasting}
        result = unread_result(unread, source)
        outcome = "user_error"
    except verovio_workers.WorkersBusy:
        details["busy"] = True
        result = busy()
        outcome = "busy"
    except Exception as error:
        if isinstance(error, verovio_workers.VerovioFailed):
            details["verovio"] = error.reason
        details.update(stack_trace=traceback.format_exc(), reference=secrets.token_hex(4))
        result = our_error(details["reference"], "read_pdf", source)
        outcome = "server_error"
    return await recorded(data, digest, card_key, result, outcome, details, timings, started, unread)


async def recorded(data: bytes, digest: str, card_key: str, result: dict | CallToolResult, outcome: str, details: dict,
                   timings: dict, started: float, unread: dict | None) -> tuple[dict | CallToolResult, dict]:
    if "reference" in details:
        details["digest"] = digest
        try:
            await anyio.to_thread.run_sync(store.put, f"failed/{digest}.pdf", data)
        except Exception:
            details["failed_copy_lost"] = True
    if not isinstance(result, dict):
        failed = {"at": time.time(), "error": details.get("error", outcome), "outcome": outcome,
                  "text": result.content[0].text, "report": (result.meta or {}).get("report"),
                  **({"unread": unread} if unread else {})}
        await anyio.to_thread.run_sync(store.put, failure_of(card_key), json.dumps(failed).encode())
    timings["total"] = round((time.perf_counter() - started) * 1000)
    details["outcome"] = outcome
    details["timings_ms"] = timings
    write_line({**details, "outcome": outcome, "severity": SEVERITY[outcome], "message": f"read_pdf_work {outcome}",
                "timings_ms": timings})
    return result, details


async def read_pdf_card(data: bytes, digest: str, source: str, arrived: bool, person: str | None) -> dict | CallToolResult:
    cache_key = f"scores/pdf-{pdf_reader.READER}-{digest}.json"
    cached = await anyio.to_thread.run_sync(store.get, cache_key)
    passes = None
    if cached:
        reading = json.loads(cached)
    else:
        pages = len((await anyio.to_thread.run_sync(pdf_reader.open_pdf, data)).pages)
        read = min(pages, pdf_reader.READ_PAGES)
        if read < pages:
            data = await anyio.to_thread.run_sync(pdf_reader.first_pages, data, read)
        if pdf_lock.locked():
            log("read_pdf_work", busy=True)
            return busy()
        async with pdf_lock:
            refused = await take_score(person, source) if arrived else None
            if not refused and not await take("pdf_page", source, read):
                if arrived:
                    await give_back_score(person, source)
                refused = "shared"
            if refused:
                log("read_pdf_work", limit=refused, pages=read)
                return error_result(PERSON_LIMIT_MESSAGE if refused == "person" else LIMIT_MESSAGE)
            log("read_pdf_work", **await anyio.to_thread.run_sync(pdf_reader.file_facts, data))
            try:
                with stage("omr"):
                    result = await anyio.to_thread.run_sync(pdf_reader.read_pdf, data)
            except pdf_reader.ReadError:
                raise
            except Exception:
                if arrived:
                    await give_back_score(person, source)
                raise
        passes = result.passes
        reading = {"score_id": secrets.token_hex(8).upper(), "pages": result.pages, "scan": result.scan,
                   "skipped": result.skipped, "of_pages": pages, "low_resolution": result.low_resolution}
        await anyio.to_thread.run_sync(store.put, f"scores/{reading['score_id']}", result.musicxml)
        await anyio.to_thread.run_sync(store.put, cache_key, json.dumps(reading).encode())
    score, _ = await resolve_score(None, reading["score_id"])
    score_id = reading["score_id"] + "N"
    score = await in_turn(pdf_reader.without_slurs, score)
    await anyio.to_thread.run_sync(store.put, f"scores/{score_id}", score)

    def render():
        spots = pdf_reader.problem_spots(score)
        index = ScoreIndex(load_toolkit(score).getMEI())
        named = ([index.measure(bar).printed for bar in spots[0]], spots[1])
        return (pdf_reader.preview(score, spots=spots), engrave(score),
                pdf_reader.notice(score, reading["scan"], reading["skipped"], named, reading.get("low_resolution", False), opening=READING_SHOWN) + pdf_reader.unread_pages(reading["pages"], reading.get("of_pages", reading["pages"])),
                index.name_span, len(index.measures), spots[0], named[0])

    with stage("render"):
        shaded, engraving, notice, measures, bars, uneven, uneven_named = await in_turn(render)
    await anyio.to_thread.run_sync(store.put, shaded_key(score_id), json.dumps(uneven).encode())
    more_pages = shaded.page_count > CARD_PAGES
    if more_pages:
        notice += f" This shows the first {CARD_PAGES} pages; download the PDF to check the rest."

    def files():
        with ThreadPoolExecutor(4) as pool:
            image = pool.submit(shaded.png, 1, width=1400, colors=256, pages=CARD_PAGES)
            pdf = pool.submit(engraving.pdf)
            pages = list(pool.map(shaded.png, range(1, min(shaded.page_count, CARD_PAGES) + 1)))
            return image.result(), pdf.result(), pages

    with stage("publish"):
        image, pdf, pages = await in_turn(files)
        image_url, pdf_url = await in_turn(lambda: (publish(image, "png"), publish(pdf, "pdf")))
    log("read_pdf_work", pages=reading["pages"], scan=reading["scan"], skipped=reading["skipped"], cached=bool(cached),
        passes=passes, bars=bars, bars_shaded=len(uneven))
    if reading["scan"]:
        await anyio.to_thread.run_sync(store.put, scan_key(score_id), json.dumps({"pages": reading["pages"]}).encode())
    return {"score_id": score_id, "pages": reading["pages"], "scan": reading["scan"], "measures": measures, "bars": bars, "notice": notice, "image_url": image_url,
            "pdf_url": pdf_url, "more_pages": more_pages, "shaded_bars": uneven_named, "page_images": [base64.b64encode(png).decode() for png in pages]}


CAREFUL_COST = {"claude": " and uses a lot of your plan's usage allowance. As a guide, a 10-page piece can use most of a "
                          "five-hour allowance on a standard paid plan.",
                "other": "."}
CAREFUL_WARNING = ("Reading this scan carefully takes about 5 minutes a page{cost} "
                   "To do it I download and run a small measuring script from Sheet Music Analysis in this chat. "
                   "This piece has {pages}. Shall I go ahead?")
CAREFUL_OFFER = (
    " This PDF is a scan, and this reading is a quick one that makes many mistakes on scans. So make this the very "
    "last thing in your reply with the analysis, after any other closing line you have been asked for: tell the user "
    "in one sentence that the analysis rests on a quick reading of their scan and that you can read the scan "
    "carefully yourself instead, then say this, in these words: \"{warning}\" Ask "
    "this once for a score, after its first analysis, not again after later ones. Do not start the careful reading "
    "before the user says yes. The careful reading uses your code sandbox and helper agents (subagents); the user's "
    "yes to this question is their request to start them and to download and run the measuring script that "
    "careful_reading names. Leave the question out only if this chat has no code sandbox at all. If the user says "
    "yes, call careful_reading with this score_id and follow what it returns."
)
CAREFUL_STEPS = (
    "Careful reading of the user's scan ({pages}). Do these steps in order, in your code sandbox.\n"
    "1. The file: you need the user's PDF in the sandbox. If the user attached it to this chat, it is already "
    "there. If it is not there, ask the user to attach the same PDF to the chat and wait for it.\n"
    "2. The kit: in a working folder, download the three kit files into a folder named kit:\n"
    "   mkdir -p kit && for f in {files}; do {download}; done\n"
    "   The tool needs Python 3 with numpy, scipy, cv2 and pypdfium2; for any that is missing run "
    "pip install numpy scipy opencv-python-headless pypdfium2.\n"
    "3. The pages: python3 kit/notetool.py pages THE_PDF pages   writes pages/page1.png, pages/page2.png and so "
    "on. Use only the first {count} of them.\n"
    "4. One reader for each page: start a separate helper (a subagent) for each page, all at the same time if you "
    "can. {helpers} Tell each helper: \"Read kit/reader.md and do exactly what it says. Your page is "
    "pages/pageN.png, page N of {count}. Write your result to pageN.n1. {hint}\" Do not read the pages yourself "
    "if you can start helpers. If you cannot start helpers at all, tell the user so plainly, then read the pages "
    "yourself, one at a time, following kit/reader.md for each. Do not search the web for the piece and do not "
    "use what you remember of the music: only what is printed counts.\n"
    "5. Hand in: when every page file exists, call use_careful_reading with this score_id ({score_id}) and with "
    "pages set to the full text of page1.n1, page2.n1 and so on, in order and unchanged, leaving out any page whose "
    "helper wrote NO MUSIC. It returns a new "
    "score_id for the careful reading."
)
HELPER_SETTINGS = {"claude": "Give each helper the Sonnet model at medium effort.",
                   "other": "Give each helper your highest thinking setting."}
KIT = HERE.parent / "kit"
KIT_FILES = ("notetool.py", "tool.md", "reader.md")
KIT_ELSEWHERE = os.environ.get("KIT_ELSEWHERE", "").rstrip("/")
CAREFUL_PLATFORMS = set(os.environ.get("CAREFUL_READING", "").split(","))
CAREFUL_TOOLS = {"careful_reading", "use_careful_reading"}
ASK_BEFORE_THE_STEPS = (
    "Before any of these steps, ask the user, unless they have already said yes to exactly this question in this "
    "chat. Say this to them, in these words: \"{warning}\" Then end your reply and wait; do the steps only after "
    "their yes, and if they say no, stay with the quick reading: analyse it with draft_analysis if you have not yet.\n"
)
NOT_A_SCAN = ("A careful reading is offered only for a scanned PDF that read_pdf or read_fetched_pdf has read, with the "
              "score_id it returned.")


def scan_key(score_id: str) -> str:
    return f"scores/{clean_id(score_id)}.scan"


def page_count(pages: int) -> str:
    return "1 page" if pages == 1 else f"{pages} pages"


def careful_warning(pages: int, source: str) -> str:
    return CAREFUL_WARNING.format(cost=for_product(CAREFUL_COST, source), pages=page_count(pages))


def signatures_found(score: bytes) -> str:
    index = ScoreIndex(load_toolkit(score).getMEI())
    keys = [index.key_signature or "0"]
    for measure in index.measures:
        if measure.key_signature and measure.key_signature != keys[-1]:
            keys.append(measure.key_signature)
    spoken = [("no sharps or flats" if key == "0" else f"{key[:-1]} {'sharps' if key.endswith('s') else 'flats'}") for key in keys]
    return (f"An automatic reader found the time signature {index.meter} at the start of the piece, and these key "
            f"signatures in order through the piece: {', then '.join(spoken)}.")


def doubtful_reading(card: dict) -> str:
    shaded, bars = len(card.get("shaded_bars", [])), card.get("bars")
    if not bars or shaded < MOSTLY_DOUBTFUL * bars:
        return ""
    return (f"Open your reply with the analysis with this warning, before anything else: \"Much of this reading is doubtful: {shaded} of its "
            f"{bars} bars are shaded because their beats don't add up, notes are missing, or notes that should line up "
            "don't. The analysis may be wrong in those bars.\"\n")


def pdf_card_result(card: dict, tool: str, source: str) -> CallToolResult:
    more_pages = card.get("more_pages")
    shown = (f"the first {CARD_PAGES} pages of the engraved score read from their {card['pages']}-page PDF; the PDF has every bar"
             if more_pages else f"every bar of the engraved score read from their {card['pages']}-page PDF, in one image")
    text = (
        f"score_id: {card['score_id']}\n"
        f"The card shows the user {shown}. "
        f"The score has measures {card['measures']}.\n"
        f"{doubtful_reading(card)}"
        "Go straight on to the analysis without asking the user to check the reading: call draft_analysis with this score_id now"
        " and continue exactly as for an attached MusicXML file, drawing it with render_analysis. "
        "Bars shaded in the reading stay shaded on the drawn page. "
        f"The card does not show this note, so in your reply with the analysis pass on this note about the reading, briefly: \"{card['notice']}\""
        + (CAREFUL_OFFER.format(warning=careful_warning(card["pages"], source)) if card.get("scan") and source in CAREFUL_PLATFORMS else "")
    )
    go_on = "Now call draft_analysis with this score_id."
    return CallToolResult(
        content=[
            *(ImageContent(type="image", data=png, mime_type="image/png") for png in card["page_images"]),
            TextContent(type="text", text=f"{text}\nPDF of the engraved score: {card['pdf_url']}\n{go_on}"),
        ],
        structured_content={"image_url": card["image_url"], "pdf_url": card["pdf_url"],
                            "caption": f"What I read from your PDF, first {CARD_PAGES} pages" if more_pages else "What I read from your PDF, every bar",
                            "title": "What I read from your PDF", "shaded_bars": card.get("shaded_bars", [])},
    )




@apps.tool(
    resource_uri=PDF_CARD_URI,
    title="Read a chosen PDF of sheet music",
    description=(
        "Use this when choose_score or fetch_score gave a pdf_id, with that pdf_id. Reads the music from the PDF and shows the "
        "user the engraved result in a card. Returns a score_id. Then, unless the result tells you to ask the user a question "
        "first, go straight on to the analysis without waiting for the user: call draft_analysis with that score_id, and "
        "pass on the result's note about the reading in your "
        f"reply with the analysis. Only the first {pdf_reader.READ_PAGES} pages are read. "
        "Slurs are not read, because they are often misread from PDFs; if the user asks for slurs, tell them so."
    ),
    annotations=stores("Read a chosen PDF of sheet music", again=True),
)
@observed
async def read_fetched_pdf(ctx: Context, pdf_id: str) -> CallToolResult:
    source = platform(ctx)
    code = clean_id(pdf_id)
    data = await anyio.to_thread.run_sync(store.get, f"scores/{code}.pdf")
    if data is None:
        if await anyio.to_thread.run_sync(store.get, f"scores/{code}.waiting") is not None:
            return waiting_for_choice("read_fetched_pdf", source)
        if await anyio.to_thread.run_sync(store.get, f"scores/{code}") is not None:
            no_pdf = f"This score is a MusicXML file, not a PDF. Call draft_analysis with score_id {code}."
        else:
            no_pdf = "No PDF has that pdf_id; PDFs are kept for 30 days. Call choose_score so the user can choose the PDF again."
        log("read_fetched_pdf", platform=source, error="ScoreError", reason=no_pdf)
        return error_result(no_pdf)
    return await read_pdf_data(data, source, "read_fetched_pdf")


CLAUDE_TOOLS = {"choose_score", "fetch_score", "read_fetched_pdf", "draft_analysis", "correct_bars", "render_analysis", "play",
                "draft_from_notes", "send_suggestion", "careful_reading", "use_careful_reading"}
CLAUDE_ONLY_TOOLS = {"choose_score", "fetch_score", "read_fetched_pdf", "play", "draft_from_notes"}
NO_NOTE_LIST = (
    "No note list: draft_from_notes needs the compact note list (starting 'N1 div=') that the Sheet Music Analysis "
    "plugin's skill makes from the user's score file. Without the plugin, call choose_score so the user can choose "
    "their score file in a card."
)
NOTES_FROM_LIST = (
    "No automatic draft analysis is given with this reply, by design: nothing failed, so do not mention a draft to "
    "the user. Analyse from the note list you sent. If the user asked for their own numerals to be checked and there "
    "is no STUDENT CHECK section, compare them with your reading of the note list."
)
CLAUDE_HIDDEN_ARGUMENTS = {"draft_analysis": {"score_file"}}
CLAUDE_RESULT_CHARS = 100_000
IMAGES_LEFT_OUT = (
    "{count} image(s) were left out of this reply to keep it within Claude's size limit. The card shows the page to "
    "the user; where no card is shown, give the user the links in this reply."
)
QUESTION_FOR_USER = "Question for the user about their Roman numerals: "


def inline_definitions(schema: dict) -> dict:
    definitions = schema.get("$defs", {})

    def expand(node):
        if isinstance(node, list):
            return [expand(item) for item in node]
        if not isinstance(node, dict):
            return node
        rest = {key: expand(value) for key, value in node.items() if key not in ("$ref", "$defs", "discriminator")}
        if "$ref" in node:
            return {**expand(definitions[node["$ref"].rsplit("/", 1)[1]]), **rest}
        return rest

    return expand(schema)


def is_claude(ctx) -> bool:
    return client_of(getattr(ctx.request, "headers", None)) == "claude"


def without_arguments(schema: dict, hidden: set[str]) -> dict:
    return {**schema, "properties": {name: value for name, value in schema["properties"].items() if name not in hidden},
            "required": [name for name in schema.get("required", []) if name not in hidden]}


def with_claude_domain(meta: dict | None) -> dict | None:
    if not meta or "domain" not in meta.get("ui", {}):
        return meta
    return {**meta, "ui": {**meta["ui"], "domain": CLAUDE_UI_DOMAIN}}


def within_claude_limit(result):
    if not isinstance(result, CallToolResult):
        return result
    images = [item for item in result.content if isinstance(item, ImageContent)]
    left_out = 0
    while images and len(result.model_dump_json(by_alias=True, exclude_none=True)) > CLAUDE_RESULT_CHARS:
        result.content.remove(images.pop())
        left_out += 1
    if left_out:
        result.content.insert(len(images), TextContent(type="text", text=IMAGES_LEFT_OUT.format(count=left_out)))
    return result


class Server(MCPServer):
    async def _handle_list_tools(self, ctx, params):
        result = await super()._handle_list_tools(ctx, params)
        claude = is_claude(ctx)
        if claude:
            result.tools = [tool for tool in result.tools if tool.name in CLAUDE_TOOLS
                            and (tool.name not in CAREFUL_TOOLS or "claude" in CAREFUL_PLATFORMS)]
        else:
            result.tools = [tool for tool in result.tools if tool.name not in CLAUDE_ONLY_TOOLS]
        for tool in result.tools:
            tool.input_schema = inline_definitions(tool.input_schema)
            if claude and tool.name in CLAUDE_HIDDEN_ARGUMENTS:
                tool.input_schema = without_arguments(tool.input_schema, CLAUDE_HIDDEN_ARGUMENTS[tool.name])
            if claude and tool.name in CLAUDE_DESCRIPTIONS:
                tool.description = CLAUDE_DESCRIPTIONS[tool.name]
        return result

    async def _handle_call_tool(self, ctx, params):
        result = await super()._handle_call_tool(ctx, params)
        return within_claude_limit(result) if is_claude(ctx) else result

    async def _handle_list_resources(self, ctx, params):
        result = await super()._handle_list_resources(ctx, params)
        if is_claude(ctx):
            for resource in result.resources:
                resource.meta = with_claude_domain(resource.meta)
        return result

    async def _handle_read_resource(self, ctx, params):
        result = await super()._handle_read_resource(ctx, params)
        if is_claude(ctx) and hasattr(result, "contents"):
            for content in result.contents:
                content.meta = with_claude_domain(content.meta)
        return result


SITE = "https://sheetmusicanalysis.com"


@apps.tool(
    resource_uri=PLAYER_URI,
    title="Play the score",
    description=(
        "Shows the user a small piano player in the chat, with play, pause and a seek bar. Use it when the user "
        "wants to hear the passage or score. Pass the score_id that choose_score, fetch_score, read_fetched_pdf or "
        "correct_bars gave and the bars to play as measure_range, e.g. \"1-8\" or \"16a-20\" (\"all\" plays the whole score). It plays the "
        "score's tempo, dynamics, pedal marks and ornaments. tempo, in quarter notes per minute, is only for a tempo "
        "word whose speed play says is unclear: ask the user, then pass their answer. play_id and notes are only for "
        "older versions of the Sheet Music Analysis plugin (1.8.0 and earlier); in a new chat use score_id."
    ),
    annotations=read_only("Play the score"),
)
@observed
async def play(ctx: Context, score_id: str | None = None, measure_range: str = "all", tempo: float | None = None,
               play_id: str | None = None, notes: str | None = None) -> CallToolResult:
    source = platform(ctx)
    try:
        if score_id:
            score, _ = await resolve_score(None, score_id, source)
            named = parse_measures(measure_range)
            index = await in_turn(marked_index, score)
            measures = index.numbers(named)
        else:
            measures = None
            if play_id and (stored := await anyio.to_thread.run_sync(store.get, f"scores/{clean_id(play_id)}.notes")):
                notes = stored.decode()
            elif play_id and not notes:
                return error_result(f"No passage has the play_id {play_id!r}; they are kept for 30 days. Call "
                                    "draft_from_notes again, or pass the note list as notes.")
            if not notes or not notes.lstrip().startswith("N1"):
                return error_result(NO_PLAY_NOTES)
            index = await in_turn(note_list.decode, notes)
        unclear = unclear_tempos(index, measures)
        if unclear and not tempo:
            bar, word = unclear[0]
            log("play", platform=source, measure_range=measure_range, legacy=not score_id, asked_tempo=True)
            return CallToolResult(content=[TextContent(type="text", text=(
                f"Bar {bar} is marked '{word}' with a half-note beat, so how fast to play it is unclear. Ask the user how "
                "fast they want it, then call play again with the same arguments and tempo in quarter notes per minute."
            ))])
        performance = await in_turn(lambda: performance_text(index, measures, tempo=tempo))
    except UserError as error:
        log("play", platform=source, legacy=not score_id, **logged(error), outcome="user_error")
        return error_result(str(error))
    log("play", platform=source, measure_range=measure_range, legacy=not score_id)
    return CallToolResult(
        content=[TextContent(type="text", text="The user now has a player for this passage in the chat.")],
        structured_content={"performance": performance, "measures": played_bars(index, measures)},
    )


def played_bars(index, measures: tuple[int, int] | None) -> list[int | str]:
    first, last = measures or (index.measures[0].number, index.measures[-1].number)
    return [index.measure(first).printed, index.measure(last).printed]


apps.add_html_resource(
    PLAYER_URI,
    (HERE / "player.html").read_text().replace("__SAMPLES__", f"{SITE}/piano/"),
    name="Score player",
    csp=ResourceCsp(connect_domains=[SITE]),
    domain=CLAUDE_UI_DOMAIN,
    prefers_border=True,
)


NO_PLAY_NOTES = (
    "Nothing to play: pass the score_id that choose_score, fetch_score, read_fetched_pdf or correct_bars gave. Older plugin "
    "versions pass the play_id that draft_from_notes returned, or the compact note list (starting 'N1 div=') as notes."
)


NOT_CHOSEN_YET = ("The user has not chosen their file in the card yet. Ask them to click Choose your score in the "
                  "card and choose it.")


class NotChosenYet(ScoreError):
    pass


ATTACHED_FILE_SENTENCE = (
    "I can't pass a file attached to the chat to the analysis tool, so please choose the same file again in the card below."
)


@apps.tool(
    resource_uri=UPLOAD_CARD_URI,
    title="Choose a score file",
    description=(
        "Use this only when the user wants their score analysed and no score_id or link to the score is available yet "
        "in this conversation; never call it otherwise, and not again while a card you showed is still waiting for "
        "the user's file (ask them to use that card). It shows a small card in which the user chooses their score "
        "file, a MusicXML file (.mxl or .musicxml) or a PDF of printed music, which goes straight to this server. "
        "Files attached to the chat cannot be passed to this server, so if the user attached their score to the chat, "
        f"start your reply with this sentence and then call this tool: \"{ATTACHED_FILE_SENTENCE}\" It returns the "
        "id the file will be kept under; end your reply, and when the user's next message says they have chosen it, "
        "use that id as the result says. If the user gives a link to the score instead, call fetch_score with it."
    ),
    annotations=stores("Choose a score file"),
)
@observed
async def choose_score(ctx: Context) -> CallToolResult:
    log("choose_score", platform=platform(ctx))
    code = secrets.token_hex(8).upper()
    await anyio.to_thread.run_sync(store.put, f"scores/{code}.waiting", b"")
    return CallToolResult(content=[TextContent(type="text", text=(
        f"The user now sees a card in which to choose their score file, which will be kept under the id {code}. "
        "End your reply here. When their next message says they have chosen it: if the file name ends in .pdf, "
        f"write one short sentence saying you are reading the PDF now and that {PDF_WAIT}, then in the same reply "
        f"call read_fetched_pdf with pdf_id {code}; otherwise it is MusicXML, so call draft_analysis with "
        f"score_id {code}."))], structuredContent={"upload_id": code})


apps.add_html_resource(
    UPLOAD_CARD_URI,
    (HERE / "upload-card.html").read_text().replace("__UPLOAD_URL__", f"{PUBLIC_BASE_URL}/upload"),
    name="Score file chooser",
    csp=ResourceCsp(connect_domains=[PUBLIC_BASE_URL]),
    domain=CLAUDE_UI_DOMAIN,
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
        "Harmonic analysis of sheet music: Roman numerals, cadences, phrases and non-chord tones. The server reads "
        "MusicXML and PDF scores and draws the analysis on the engraved page. In Claude the user chooses their score file "
        "in a card that choose_score shows, or gives a link that fetch_score downloads, and play shows a small piano player for the passage in the chat."
    ),
    extensions=[apps],
)
del mcp._lowlevel_server._request_handlers["subscriptions/listen"]


DRAFT_ANALYSIS_USE = (
    "Use this when the user wants a harmonic analysis of a MusicXML score (.mxl or .musicxml): Roman numerals, "
    "cadences, phrases, non-chord tones. Returns the score's notes beat by beat as a table for you to analyse, "
    "plus a score_id. Follow it with render_analysis. If the user wants their own analysis checked, pass their "
    "Roman numerals as student_analysis, as they typed them (\"m1 I, m2 V6, m3 beat 3 ii65 ...\"), with a beat only "
    "where they gave one: never choose beats yourself, the server places them or asks. Or pass the word "
    "\"score\" when the numerals are written into their score file; the result then lists, for each of their "
    "labels, the notes at that beat and whether the numeral fits them. If the result is a question, ask the user "
    "that question and call again with their answer. "
)
CLAUDE_SCORE_INPUT_HELP = (
    "score_id: the id that choose_score, fetch_score, read_fetched_pdf or correct_bars gave. Never encode, paste or "
    "retype a file's contents. If there is no score_id yet, call choose_score so the user can choose their score file."
)


@mcp.tool(
    title="Draft a harmonic analysis from a note list",
    description=(
        "Only for older versions of the Sheet Music Analysis plugin (1.8.0 and earlier), whose skill passes a compact "
        "note list starting 'N1 div=' that it made in Claude's code sandbox. In a new chat do not use this: call "
        "choose_score so the user can choose their score file. Drafts a harmonic analysis from that note list, passed "
        "unchanged as `notes`, and returns the draft with a play_id for play."
    ),
    annotations=stores("Draft a harmonic analysis from a note list"),
)
@observed
async def draft_from_notes(ctx: Context, notes: str, student_analysis: str | None = None) -> CallToolResult:
    source = platform(ctx)
    if not notes.lstrip().startswith("N1"):
        return error_result(NO_NOTE_LIST)
    started = time.time()
    try:
        with stage("parse"):
            index = await in_turn(note_list.decode, notes)
        student = await in_turn(check_analysis.student_labels, student_analysis, None, index) if student_analysis else None
    except check_analysis.ClarificationNeeded as error:
        return error_result(QUESTION_FOR_USER + error.question)
    except UserError as error:
        log("draft_from_notes", platform=source, **logged(error), chars=len(notes), outcome="user_error")
        return error_result(str(error))
    if refused := await take_score(caller(), source):
        log("limit", tool="draft_from_notes", platform=source, per=refused)
        return error_result(PERSON_LIMIT_MESSAGE if refused == "person" else LIMIT_MESSAGE)

    def build() -> str:
        sections = [NOTES_FROM_LIST, optional("part_writing", lambda: part_writing.as_text(index)),
                    optional("student_check", lambda: check_analysis.as_text(student, index) if student else "")]
        return "\n\n".join(section for section in sections if section)

    with stage("build"):
        text = await in_turn(build)
    play_id = secrets.token_hex(8).upper()
    await anyio.to_thread.run_sync(store.put, f"scores/{play_id}.notes", notes.encode())
    text += f"\n\nPLAY: play_id {play_id} plays this passage. Call play with it when the user wants to hear it."
    log("draft_from_notes", platform=source, chars_in=len(notes), seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


@mcp.tool(
    title="Draft a harmonic analysis",
    description=DRAFT_ANALYSIS_USE + SCORE_INPUT_HELP,
    annotations=stores("Draft a harmonic analysis", again=True),
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
    """measure_range limits the table, e.g. "1-8" or "16a-20"; the default "all" returns the whole piece."""
    source = platform(ctx)
    started = time.time()
    code = None
    try:
        score, given = await resolve_score(score_file, score_id, source)
        named = parse_measures(measure_range)
        if student_analysis and student_analysis.strip().lower() != "score":
            await in_turn(check_analysis.from_text, student_analysis)
        if not await take("draft", source):
            log("limit", tool="draft_analysis", platform=source)
            return error_result(LIMIT_MESSAGE)
        if given == "score_id":
            code = clean_id(score_id)
        else:
            person = caller()
            if not (code := await sent_before(person, score)):
                if refused := await take_score(person, source):
                    await take("draft", source, -1)
                    log("limit", tool="draft_analysis", platform=source, per=refused)
                    return error_result(PERSON_LIMIT_MESSAGE if refused == "person" else LIMIT_MESSAGE)
                code = secrets.token_hex(8).upper()
                await remember_sent(person, score, code)
            await anyio.to_thread.run_sync(store.put, f"scores/{code}", score)
        text = await in_turn(make_draft, score, code, named, student_analysis)
    except check_analysis.ClarificationNeeded as error:
        kept = f"\nThe score is saved as score_id: {code}. Call again with it and the user's answer." if code else ""
        return error_result(QUESTION_FOR_USER + error.question + kept)
    except NotChosenYet:
        return waiting_for_choice("draft_analysis", source)
    except (UserError, httpx.HTTPError) as error:
        log("draft_analysis", platform=source, **logged(error), outcome="user_error")
        return error_result(str(error))
    log("draft_analysis", platform=source, input=given, score_bytes=len(score), measure_range=measure_range,
        seconds=round(time.time() - started, 1))
    return CallToolResult(content=[TextContent(type="text", text=text)])


async def current_bars(score: bytes | None, replacement_bars: str, part: str | None) -> str:
    names = re.findall(r"^\s*m(\d+[a-z]*)\b", replacement_bars, re.M | re.I)
    if score is None or not names or part is not None:
        return ""

    def bars() -> tuple[str, str, str]:
        index = marked_index(score)
        given = sorted({index.measures.index(index.bar(name)) for name in names})
        first, last = index.measures[given[0]], index.measures[min(given[-1], given[0] + 3)]
        return first.name, last.name, note_list.encode(index, first.number, last.number)

    try:
        first, last, text = await in_turn(bars)
    except Exception as error:
        log("correct_bars", current_bars_error=type(error).__name__)
        return ""
    return f"\nThe score's current notes for measures {first}-{last}, in the same format, to edit:\n{text}"


CORRECT_BARS_DESCRIPTION = (
    "Use this after read_pdf for a misread bar the user describes, or one read_pdf flagged or "
    "you can see is misread when you are confident what it should be. Pass its score_id and replacement_bars "
    "in N1 format, replacing every voice of each listed bar and including every staff. Example:\n"
    "N1 div=24 ts=4/4 ks=0\nm3 len=96\n1.1: 24 C4 D4 48 E4\n"
    "div is units per quarter note; m3 is printed bar 3 (m16a is the bar the draft names 16a); len is its length in those units. "
    "Each staff.voice line uses numbers to set the duration for following tokens, + for chords, r for rests, "
    "g for grace notes (u for slashed ones) and ~ for ties to the next note; pitches are sounding pitches (e.g. F#4, Bb3). "
    "Every voice must explicitly fill the existing bar, including rests. A bar line may also carry ts= or ks= where the meter or key signature changes. Header and bar-line key/meter do not change the score. "
    "Use part (a part id or name) in a score with multiple parts; staff numbers count within that part. Returns a new score_id, PNGs of only changed bars "
    "and a note per bar; runs no model. If you proposed the correction, say it is your suggestion. "
    "Show the redrawn bars and note; ask the user to confirm against their copy. "
    "Only after confirmation analyse with draft_analysis using the new score_id. "
    "If they decline, keep using the original score_id."
)


@mcp.tool(
    title="Correct misread bars",
    description=CORRECT_BARS_DESCRIPTION,
    annotations=stores("Correct misread bars"),
)
@observed
async def correct_bars(
    ctx: Context, score_id: str, replacement_bars: str, part: str | None = None,
) -> CallToolResult:
    source = platform(ctx)
    try:
        before, _ = await resolve_score(None, score_id, source)
    except ScoreError as error:
        log("correct_bars", platform=source, **logged(error))
        return error_result(str(error))
    if not await take("draft", source):
        log("limit", tool="correct_bars", platform=source)
        return error_result(LIMIT_MESSAGE)
    try:
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
            if await anyio.to_thread.run_sync(store.get, shaded_key(score_id)) is not None:
                uneven, _ = await in_turn(pdf_reader.problem_spots, after)
                await anyio.to_thread.run_sync(store.put, shaded_key(code), json.dumps(uneven).encode())
    except (correct.CorrectionError, ScoreError, PositionError) as error:
        log("correct_bars", platform=source, **logged(error))
        return error_result("Fix the replacement bars and call correct_bars again: " + str(error)
                            + await current_bars(before, replacement_bars, part))
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
    title="Start a careful reading of a scan",
    description=(
        "Use this only after read_pdf or read_fetched_pdf has read a scanned PDF and the user has said yes to the "
        "usage warning from its result. Returns the steps for reading the scan carefully with your own helpers, "
        "one page each, and handing the result in with use_careful_reading."
    ),
    annotations=read_only("Start a careful reading of a scan"),
)
@observed
async def careful_reading(ctx: Context, score_id: str) -> CallToolResult:
    source = platform(ctx)
    scan = await anyio.to_thread.run_sync(store.get, scan_key(score_id))
    if scan is None:
        log("careful_reading", platform=source, error="ScoreError", reason=NOT_A_SCAN)
        return error_result(NOT_A_SCAN)
    pages = json.loads(scan)["pages"]
    try:
        score, _ = await resolve_score(None, score_id, source)
    except ScoreError as error:
        log("careful_reading", platform=source, **logged(error))
        return error_result(str(error))
    hint = await in_turn(signatures_found, score)
    addresses = [f"{PUBLIC_BASE_URL}/kit", *([KIT_ELSEWHERE] if KIT_ELSEWHERE else [])]
    log("careful_reading", platform=source, pages=pages)
    ask = ASK_BEFORE_THE_STEPS.format(warning=careful_warning(pages, source))
    return CallToolResult(content=[TextContent(type="text", text=ask + CAREFUL_STEPS.format(
        pages=page_count(pages), count=pages, score_id=clean_id(score_id), files=" ".join(KIT_FILES), hint=hint,
        download=" || ".join(f"curl -fsSL {address}/$f -o kit/$f" for address in addresses),
        helpers=for_product(HELPER_SETTINGS, source)))])


@mcp.tool(
    title="Use a careful reading",
    description=(
        "Use this at the end of the steps careful_reading returned: hands in the pages your helpers read, one note "
        "list (starting 'N1 div=') for each page, in order. Builds the score from them and returns a new score_id; "
        "then call draft_analysis with it and continue as for a MusicXML file."
    ),
    annotations=stores("Use a careful reading"),
)
@observed
async def use_careful_reading(ctx: Context, score_id: str, pages: list[str]) -> CallToolResult:
    source = platform(ctx)
    scan = await anyio.to_thread.run_sync(store.get, scan_key(score_id))
    if scan is None:
        log("use_careful_reading", platform=source, error="ScoreError", reason=NOT_A_SCAN)
        return error_result(NOT_A_SCAN)
    if len(pages) > json.loads(scan)["pages"]:
        too_many = f"This scan has {page_count(json.loads(scan)['pages'])}; hand in one note list for each page, not {len(pages)}."
        log("use_careful_reading", platform=source, error="ScoreError", reason=too_many, pages=len(pages), outcome="user_error")
        return error_result(too_many)
    if not await take("draft", source):
        log("limit", tool="use_careful_reading", platform=source)
        return error_result(LIMIT_MESSAGE)
    try:
        with stage("parse"):
            score = await in_turn(lambda: from_notes.score_from_pages(pages))
            bars = await in_turn(lambda: [measure.name for measure in ScoreIndex(load_toolkit(score).getMEI()).measures])
    except UserError as error:
        log("use_careful_reading", platform=source, **logged(error), pages=len(pages), outcome="user_error")
        return error_result("Fix the page this is about and call use_careful_reading again with every page: " + str(error))
    code = secrets.token_hex(8).upper()
    await anyio.to_thread.run_sync(store.put, f"scores/{code}", score)
    log("use_careful_reading", platform=source, pages=len(pages), bars=len(bars), chars_in=sum(map(len, pages)))
    return CallToolResult(content=[TextContent(type="text", text=(
        f"score_id: {code}\nThe careful reading is stored: measures {bars[0]} to {bars[-1]}. Call draft_analysis with "
        "this score_id now and continue exactly as for an attached MusicXML file, drawing it with render_analysis. In "
        "your reply with the analysis, tell the user in one sentence that the page shows your careful reading of "
        "their scan and that it can still contain mistakes, so they should check it against their copy."))])


LINK_NOT_A_SCORE = (
    "The link gave something other than a MusicXML file or a PDF, usually a web page: a sign-in page when the file is "
    "not shared publicly, or a page about the file rather than the file itself. Ask the user to share the file so "
    "anyone with the link can view it, or for a direct link to the .mxl, .musicxml or .pdf file."
)
LINK_ANSWERED = (
    "The link answered with an error (HTTP {status}). Ask the user to check that the link opens in a private browser "
    "window, shared so anyone with the link can view it."
)


def score_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return "musicxml" if "META-INF/container.xml" in archive.namelist() else None
        except zipfile.BadZipFile:
            return None
    head = xml_text(data[:65536]).lstrip()
    return "musicxml" if head.startswith("<") and re.search(r"<score-(partwise|timewise)\b", head) else None


def link_host(url: str) -> str:
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except ValueError:
        return "other"
    if is_imslp(host):
        return "imslp"
    return {"drive.google.com": "google_drive", "docs.google.com": "google_drive", "dropbox.com": "dropbox",
            "www.dropbox.com": "dropbox"}.get(host, "other")


@mcp.tool(
    title="Open a score from a link",
    description=(
        "Use this first whenever the user gives a link to their score and wants it analysed: a direct link to a "
        "MusicXML file (.mxl or .musicxml) or a PDF of printed music, or a Google Drive or Dropbox share link to one. "
        "The server downloads the file (https only, at most 10 MB). For MusicXML it returns a score_id: call "
        "draft_analysis with it. For a PDF it returns a pdf_id: call read_fetched_pdf with it. IMSLP links are not "
        "downloaded; the result says what to tell the user. Without a link, call choose_score instead. Never download, open or search for the score "
        "yourself (no web search, no code sandbox): only this server fetches it, from a link the user gave."
    ),
    annotations=stores("Open a score from a link", open_world=True),
)
@observed
async def fetch_score(ctx: Context, url: str) -> CallToolResult:
    source, host = platform(ctx), link_host(url)
    try:
        with stage("fetch"):
            data = await download(direct_link(url))
    except httpx.HTTPStatusError as error:
        log("fetch_score", platform=source, host=host, error="HTTPStatusError", status=error.response.status_code)
        return error_result(LINK_ANSWERED.format(status=error.response.status_code))
    except ScoreError as error:
        log("fetch_score", platform=source, host=host, **logged(error))
        return error_result(str(error))
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
        log("fetch_score", platform=source, host=host, error=type(error).__name__)
        return error_result("The link could not be reached. Ask the user to check it opens in their browser.")
    kind = score_kind(data)
    if kind is None:
        log("fetch_score", platform=source, host=host, error="not a score", score_bytes=len(data))
        return error_result(LINK_NOT_A_SCORE)
    if not await take("score", source):
        log("limit", tool="fetch_score", platform=source)
        return error_result(LIMIT_MESSAGE)
    code = await keep_score(data, kind)
    log("fetch_score", platform=source, host=host, kind=kind, score_bytes=len(data))
    return CallToolResult(content=[TextContent(type="text", text=next_step(kind, code))])


async def keep_score(data: bytes, kind: str, code: str | None = None) -> str:
    code = code or secrets.token_hex(8).upper()
    await anyio.to_thread.run_sync(store.put, f"scores/{code}.pdf" if kind == "pdf" else f"scores/{code}", data)
    return code


def next_step(kind: str, code: str) -> str:
    if kind == "pdf":
        return (f"pdf_id: {code}\nIt is a PDF. Write one short sentence saying you are reading the PDF now and that "
                f"{PDF_WAIT}, then in the same reply call read_fetched_pdf with this pdf_id to read the music from it.")
    return f"score_id: {code}\nIt is a MusicXML score. Call draft_analysis with this score_id now."


CLAUDE_DESCRIPTIONS = {
    "draft_analysis": DRAFT_ANALYSIS_USE + CLAUDE_SCORE_INPUT_HELP,
    "correct_bars": CORRECT_BARS_DESCRIPTION.replace("read_pdf", "read_fetched_pdf"),
}


@mcp.custom_route("/files/{name}", methods=["GET"])
async def files(request: Request) -> Response:
    name = request.path_params["name"]
    data = None
    if re.fullmatch(r"[A-Za-z0-9_-]+\.(png|pdf|musicxml|mid|rntxt)", name):
        data = await anyio.to_thread.run_sync(store.get, f"files/{name}")
        if data is None and name.endswith("-worksheet.pdf"):
            async with worksheet_lock:
                data = await anyio.to_thread.run_sync(store.get, f"files/{name}")
                if data is None:
                    try:
                        async with verovio_request(DRAWING_WAIT):
                            data = await in_turn(make_worksheet, name)
                    except verovio_workers.WorkersBusy:
                        log("worksheet", outcome="busy")
                        return Response("The service is busy right now. Please try again in a minute.",
                                        status_code=503, headers={"Retry-After": "60"})
                    except Exception as error:
                        log("worksheet", error=type(error).__name__, stack_trace=traceback.format_exc())
                        return Response("This worksheet could not be made; the analysis PDF is unaffected.",
                                        status_code=500)
                    if data:
                        await anyio.to_thread.run_sync(store.put, f"files/{name}", data)
    if not data:
        return Response("This file has expired; pages are kept for 30 days.", status_code=404)
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


@mcp.custom_route("/kit/{name}", methods=["GET"])
async def kit(request: Request) -> Response:
    name = request.path_params["name"]
    if name not in KIT_FILES:
        return Response("No such file.", status_code=404)
    return Response((KIT / name).read_bytes(), media_type="text/plain; charset=utf-8", headers={"X-Content-Type-Options": "nosniff"})


UPLOAD_HEADERS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
                  "Access-Control-Allow-Headers": "content-type, x-device"}


def upload_refused(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=UPLOAD_HEADERS)


@mcp.custom_route("/upload", methods=["POST", "OPTIONS"])
async def upload(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=UPLOAD_HEADERS)
    source = "claude" if (request.headers.get("origin") or "").endswith(".claudemcpcontent.com") else "other"
    too_large = upload_refused("This file is larger than 10 MB. Choose a smaller one.", 413)
    announced = request.headers.get("content-length") or ""
    if announced.isdigit() and int(announced) > MAX_SCORE_BYTES:
        log("upload", platform=source, error="too large")
        return too_large
    data = bytearray()
    try:
        with anyio.fail_after(DOWNLOAD_SECONDS):
            async for chunk in request.stream():
                data += chunk
                if len(data) > MAX_SCORE_BYTES:
                    log("upload", platform=source, error="too large")
                    return too_large
    except TimeoutError:
        log("upload", platform=source, error="too slow", score_bytes=len(data))
        return upload_refused(f"The file took longer than {DOWNLOAD_SECONDS} seconds to arrive. Choose it again.", 408)
    code = clean_id(request.query_params.get("id", ""))
    if not code or await anyio.to_thread.run_sync(store.get, f"scores/{code}.waiting") is None:
        log("upload", platform=source, error="no card")
        return upload_refused("This card has expired. Ask Claude for a new one.", 404)
    for key in (f"scores/{code}", f"scores/{code}.pdf"):
        if await anyio.to_thread.run_sync(store.get, key) is not None:
            log("upload", platform=source, error="already chosen")
            return upload_refused("A file was already chosen in this card. To choose another, ask Claude for a new card.", 409)
    kind = score_kind(bytes(data))
    if kind is None:
        log("upload", platform=source, error="not a score", score_bytes=len(data))
        return upload_refused("This is not a MusicXML file or a PDF. Choose a .mxl, .musicxml or .pdf file.", 415)
    device = request.headers.get("x-device") or request.query_params.get("device", "")
    person = f"device:{device}" if re.fullmatch(r"[0-9a-f]{32}", device) else None
    if not await sent_before(person, bytes(data)):
        if refused := await take_score(person, source):
            log("upload", platform=source, error=f"{refused} limit")
            return upload_refused(UPLOAD_PERSON_MESSAGE if refused == "person" else UPLOAD_LIMIT_MESSAGE, 429)
        await remember_sent(person, bytes(data), code)
    await keep_score(bytes(data), kind, code)
    log("upload", platform=source, kind=kind, score_bytes=len(data))
    return JSONResponse({"kind": kind}, headers=UPLOAD_HEADERS)


@mcp.custom_route("/read-work", methods=["POST"])
async def read_work(request: Request) -> Response:
    data, asked = await request.body(), request.headers
    digest = hashlib.sha256(data).hexdigest()
    card_key = card_of(digest)
    held = json.loads(await anyio.to_thread.run_sync(store.get, marker_of(card_key)) or b"{}")
    if not asked.get("x-read-token") or held.get("token") != asked["x-read-token"]:
        return Response(status_code=403)
    result, details = await pdf_work(data, digest, asked["x-read-source"], card_key, asked["x-read-token"],
                                     asked["x-read-arrived"] == "1", asked.get("x-read-person"))
    card = isinstance(result, dict)
    return JSONResponse({"card": result if card else None, "refusal": None if card else result.model_dump(mode="json"),
                         "details": details})


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
        read_ahead.save(SERVER_FILES, verovio_workers.library_files())
        return
    verovio_workers.start()
    write_line({"severity": "INFO", "message": "server imported", "imports_s": round(STARTED - IMPORTS_BEGUN, 1),
                "read_ahead": read_ahead.report})
    if service := os.environ.get("K_SERVICE"):
        start_tracing(service)
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=False,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    tool_calls = logging.getLogger("mcp.server.mcpserver.server")
    tool_calls.setLevel(logging.INFO)
    tool_calls.addFilter(lambda record: record.levelno > logging.INFO or record.msg.startswith("Tool %r rejected arguments"))
    server = HttpServer(uvicorn.Config(traced(only_through_the_proxy(without_event_stream(app))), host="0.0.0.0", port=PORT, log_level="warning",
                                       log_config=None))
    server.run()
    if not server.started:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
