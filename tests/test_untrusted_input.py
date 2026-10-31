import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from mcp.client.client import Client

from server import app

CHOPIN = Path(__file__).parent / "data/chopin_nocturne_op9_no2.mxl"


class Files(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.answer()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def answer(self):
        if self.path == "/public/redirect":
            self.send_response(302)
            self.send_header("Location", "/private")
            self.end_headers()
        elif self.path == "/public/huge":
            self.send_response(200)
            self.end_headers()
            chunk = b"x" * (1 << 20)
            for _ in range(20):
                self.wfile.write(chunk)
        elif self.path == "/public/slow":
            self.send_response(200)
            self.end_headers()
            for _ in range(20):
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.5)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"private")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def only_public_paths(monkeypatch):
    monkeypatch.setattr(app, "is_public_https", lambda url: "/public/" in url)


def fetch(url):
    return asyncio.run(app.download(url))


def test_a_redirect_to_a_private_address_is_refused(site, only_public_paths):
    with pytest.raises(app.ScoreError, match="not a public https URL"):
        fetch(f"{site}/public/redirect")


def test_a_download_stops_at_the_size_limit(site, only_public_paths):
    with pytest.raises(app.ScoreError, match="larger than 10 MB"):
        fetch(f"{site}/public/huge")


def test_a_slow_download_stops_at_the_deadline(site, only_public_paths, monkeypatch):
    monkeypatch.setattr(app, "DOWNLOAD_SECONDS", 2)
    started = time.monotonic()
    with pytest.raises(app.ScoreError, match="longer than 2 seconds"):
        fetch(f"{site}/public/slow")
    assert time.monotonic() - started < 5


def test_a_reversed_bar_range_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/ABC", CHOPIN.read_bytes())

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("render_analysis", {"score_id": "ABC", "measure_range": "8-1", "annotations": {"annotations": []}})

    result = asyncio.run(call())
    assert result.is_error and "start at the lower bar" in result.content[0].text
