import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import httpx
import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
FILES = {
    "/public/nocturne.mxl": (DATA / "chopin_nocturne_op9_no2.mxl").read_bytes(),
    "/public/prelude.pdf": (DATA / "chopin-28-4-mutopia.pdf").read_bytes(),
    "/public/reading.musicxml": (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes(),
    "/public/sign-in": b"<!DOCTYPE html><html><body>Sign in to continue</body></html>",
}
REDIRECTS = {"/public/moved": "/public/nocturne.mxl", "/public/to-imslp": "https://imslp.org/wiki/Special:ImagefromIndex/1"}


class Files(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in REDIRECTS:
            self.send_response(302)
            self.send_header("Location", REDIRECTS[self.path])
            self.end_headers()
        elif self.path in FILES:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(FILES[self.path])
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def server(monkeypatch, tmp_path):
    def read(data):
        return pdf_reader.PdfReading(FILES["/public/reading.musicxml"], 1, False, [], [{"setting": 0, "outcome": "done"}])

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "is_public_https", lambda url: "/public/" in url)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    return app.store


def call(name, arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def id_of(result, name):
    return text_of(result).split(f"{name}: ", 1)[1].split()[0]


def charged(store, kind):
    raw = store.get(f"usage/{datetime.now(timezone.utc):%Y-%m-%d}.json")
    return json.loads(raw).get(kind, 0) if raw else 0


@pytest.mark.xdist_group("draft_model")
def test_a_musicxml_link_is_drafted_and_counted_like_an_attached_score(server, site):
    fetched = call("fetch_score", {"url": f"{site}/public/moved"})
    assert not fetched.is_error and "Call draft_analysis" in text_of(fetched)
    score_id = id_of(fetched, "score_id")
    drafted = call("draft_analysis", {"score_id": score_id, "measure_range": "1-2"})
    assert not drafted.is_error and text_of(drafted).startswith(f"score_id: {score_id}")
    assert charged(server, "draft") == 1


def test_a_pdf_link_is_read_and_its_pages_counted_like_an_attached_pdf(server, site):
    fetched = call("fetch_score", {"url": f"{site}/public/prelude.pdf"})
    assert "Call read_fetched_pdf" in text_of(fetched)
    read = call("read_fetched_pdf", {"pdf_id": id_of(fetched, "pdf_id")})
    assert not read.is_error and "The score has measures 0 to 24" in text_of(read)
    assert "call read_fetched_pdf again with the same pdf_id and keep_slurs=true" in text_of(read)
    assert charged(server, "pdf_page") == 1


def test_a_pdf_chosen_in_the_card_is_read_and_its_pages_counted_like_an_attached_pdf(server):
    async def send():
        transport = httpx.ASGITransport(app=app.mcp.streamable_http_app(stateless_http=True))
        async with httpx.AsyncClient(transport=transport, base_url="http://card") as browser:
            return await browser.post("/upload", content=FILES["/public/prelude.pdf"],
                                      headers={"Origin": "https://abc.claudemcpcontent.com"})

    sent = anyio.run(send).json()
    read = call("read_fetched_pdf", {"pdf_id": sent["next"].split("pdf_id: ", 1)[1].split()[0]})
    assert not read.is_error and "The score has measures 0 to 24" in text_of(read)
    assert charged(server, "pdf_page") == 1


def test_a_web_page_instead_of_a_score_says_how_to_share_the_file(server, site):
    result = call("fetch_score", {"url": f"{site}/public/sign-in"})
    assert result.is_error and "anyone with the link can view it" in text_of(result)


def test_a_missing_file_reports_the_status(server, site):
    result = call("fetch_score", {"url": f"{site}/public/gone"})
    assert result.is_error and "HTTP 404" in text_of(result)


def test_a_redirect_to_imslp_is_refused_without_contacting_it(server, site):
    result = call("fetch_score", {"url": f"{site}/public/to-imslp"})
    assert result.is_error and "download the PDF there" in text_of(result)


@pytest.mark.parametrize("url", [
    "https://imslp.org/wiki/Nocturnes,_Op.9_(Chopin,_Fr%C3%A9d%C3%A9ric)",
    "https://imslp.org/wiki/Special:ImagefromIndex/12345",
    "https://cn.imslp.org/images/b/be/S548.pdf",
    "https://imslp.eu/files/imglnks/euimg/a/a1/IMSLP1-PMLP1.pdf",
    "https://petruccimusiclibrary.ca/files/imglnks/caimg/a/a1/IMSLP1.pdf",
])
def test_imslp_links_are_refused_before_any_download(url):
    with pytest.raises(app.ScoreError, match="does not download from IMSLP"):
        app.direct_link(url)


@pytest.mark.parametrize("url, direct", [
    ("https://drive.google.com/file/d/1AbC-d_E/view?usp=sharing",
     "https://drive.google.com/uc?export=download&id=1AbC-d_E"),
    ("https://drive.google.com/open?id=1AbC-d_E", "https://drive.google.com/uc?export=download&id=1AbC-d_E"),
    ("https://drive.google.com/file/d/1AbC/view?usp=drive_link&resourcekey=0-xyz",
     "https://drive.google.com/uc?export=download&id=1AbC&resourcekey=0-xyz"),
    ("https://www.dropbox.com/scl/fi/abc123/nocturne.mxl?rlkey=k9&dl=0",
     "https://www.dropbox.com/scl/fi/abc123/nocturne.mxl?rlkey=k9&dl=1"),
    ("https://www.dropbox.com/s/abc123/prelude.pdf", "https://www.dropbox.com/s/abc123/prelude.pdf?dl=1"),
    ("https://example.com/scores/prelude.pdf?v=2", "https://example.com/scores/prelude.pdf?v=2"),
])
def test_share_links_become_direct_downloads(url, direct):
    assert app.direct_link(url) == direct


@pytest.mark.parametrize("url", [
    "https://drive.google.com/drive/folders/1AbC?usp=sharing",
    "https://www.dropbox.com/scl/fo/abc123/xyz?rlkey=k9&dl=0",
    "https://www.dropbox.com/sh/abc123/xyz?dl=0",
])
def test_folder_links_are_refused(url):
    with pytest.raises(app.ScoreError, match="link to a folder"):
        app.direct_link(url)


@pytest.mark.parametrize("url", ["https://a..b/score.pdf", "https://[::1/score.pdf", "not a link"])
def test_a_malformed_link_is_the_user_s_mistake_not_ours(server, url):
    result = call("fetch_score", {"url": url})
    assert result.is_error and "on our side" not in text_of(result)


PUBLIC = "https://93.184.215.14"


@pytest.fixture
def remote(monkeypatch, tmp_path):
    asked = []

    def answer(request):
        asked.append(str(request.url))
        if request.url.path == "/to-private":
            return httpx.Response(302, headers={"Location": "https://10.0.0.5/score.mxl"})
        if request.url.path == "/large.mxl":
            return httpx.Response(200, content=b"PK" + bytes(app.MAX_SCORE_BYTES))
        return httpx.Response(200, content=FILES["/public/nocturne.mxl"])

    class Mocked(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(answer), **kwargs)

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app.httpx, "AsyncClient", Mocked)
    return asked


def test_a_public_link_that_redirects_to_a_private_address_is_refused(remote):
    result = call("fetch_score", {"url": f"{PUBLIC}/to-private"})
    assert result.is_error and "not a public https URL" in text_of(result)
    assert remote == [f"{PUBLIC}/to-private"]


def test_a_download_over_10_mb_is_refused(remote):
    result = call("fetch_score", {"url": f"{PUBLIC}/large.mxl"})
    assert result.is_error and "larger than 10 MB" in text_of(result)
