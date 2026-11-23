import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from engine.performance import marked_index, performance_text

pytestmark = pytest.mark.xdist_group("cards_browser")

ROOT = Path(__file__).parent.parent
PDF = ROOT / "tests/data/chopin-28-4-mutopia.pdf"
MUSICXML = ROOT / "tests/data/chopin_nocturne_op9_no2.mxl"
PAGE_PNG = ROOT / "tests/golden/chopin_m1-8_all.png"
UPLOAD_HEADERS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
                  "Access-Control-Allow-Headers": "content-type"}

HOST = """<!doctype html><meta charset=utf-8><iframe id=f style="width:600px;height:60px;border:0"></iframe>
<script>
const f = document.getElementById("f");
window.received = []; window.replies = {}; window.held = []; window.hold = false;
function reply(m) {
  const r = window.replies[m.method];
  f.contentWindow.postMessage(r && r.error ? { jsonrpc: "2.0", id: m.id, error: r.error }
                                           : { jsonrpc: "2.0", id: m.id, result: r ? r.result : {} }, "*");
}
addEventListener("message", (e) => {
  if (e.source !== f.contentWindow) return;
  const m = e.data;
  received.push(m);
  if (m.method === "ui/notifications/size-changed") f.style.height = m.params.height + "px";
  if (m.id === undefined) return;
  if (m.method === "ui/initialize")
    return f.contentWindow.postMessage({ jsonrpc: "2.0", id: m.id, result: { hostContext: { theme: "dark" } } }, "*");
  if (window.hold) held.push(m); else reply(m);
});
window.release = () => held.splice(0).forEach(reply);
window.deliver = (params) => f.contentWindow.postMessage({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params }, "*");
f.src = new URLSearchParams(location.search).get("card");
</script>"""

OPENAI_STUB = """if (window !== window.top) window.openai = {
  openExternal: (a) => window.top.external_links.push(a.href),
  setWidgetState: (s) => window.top.widget_states.push(s),
};
if (window === window.top) { window.external_links = []; window.widget_states = []; }"""


class Server(ThreadingHTTPServer):
    upload_reply: tuple[int, dict] | None
    uploads: list


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *args):
        pass

    def answer(self, status, body=b"", kind="text/html", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        port = self.server.server_address[1]
        if path == "/host":
            self.answer(200, HOST.encode())
        elif path.startswith("/cards/"):
            html = (ROOT / "server" / path.removeprefix("/cards/")).read_text()
            html = html.replace("__UPLOAD_URL__", f"http://127.0.0.1:{port}/upload").replace(
                "__SAMPLES__", f"http://127.0.0.1:{port}/piano/")
            self.answer(200, html.encode())
        elif path == "/page.png":
            self.answer(200, PAGE_PNG.read_bytes(), "image/png")
        else:
            self.answer(404)

    def do_OPTIONS(self):
        self.answer(204, headers=UPLOAD_HEADERS)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.uploads.append((parse_qs(urlsplit(self.path).query), body))
        if self.server.upload_reply is None:
            self.close_connection = True
            return
        status, reply = self.server.upload_reply
        self.answer(status, json.dumps(reply).encode(), "application/json", UPLOAD_HEADERS)


@pytest.fixture(scope="module")
def server():
    httpd = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()


@pytest.fixture
def upload_server(server):
    server.uploads, server.upload_reply = [], (200, {"kind": "pdf"})
    return server


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(color_scheme="light")
    yield context.new_page()
    context.close()


def base(server):
    return f"http://localhost:{server.server_address[1]}"


def open_card(page, server, card, openai=False):
    if openai:
        page.add_init_script(OPENAI_STUB)
    page.goto(f"{base(server)}/host?card=/cards/{card}")
    page.wait_for_function("received.some((m) => m.method === 'ui/notifications/initialized')")
    return page.frame_locator("#f")


def sent(page, method):
    return page.evaluate("(method) => received.filter((m) => m.method === method)", method)


def first_sent(page, method):
    page.wait_for_function("(method) => received.some((m) => m.method === method)", arg=method)
    return sent(page, method)[0]


def deliver(page, structured, meta=None):
    page.evaluate("(p) => deliver(p)", {"structuredContent": structured, "_meta": meta or {}})


def card_frame(page):
    return page.main_frame.child_frames[0]


def test_upload_card_starts_with_its_instructions(page, upload_server):
    card = open_card(page, upload_server, "upload-card.html")
    expect(card.locator("#choose")).to_be_visible()
    expect(card.locator("#choose")).to_have_text("Choose your score")
    expect(card.get_by_role("status")).to_have_text(
        "A MusicXML file (.mxl, .musicxml) or a PDF of printed music. After you choose it, press Enter to send the "
        "message that appears in your reply box.")
    assert sent(page, "ui/notifications/size-changed")[-1]["params"]["height"] > 0


def test_upload_card_refuses_a_file_over_10_mb_without_sending_it(page, upload_server):
    card = open_card(page, upload_server, "upload-card.html")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(
        files=[{"name": "big.pdf", "mimeType": "application/pdf", "buffer": b"%PDF" + b"0" * (10 * 1024 * 1024)}])
    expect(card.locator("#status")).to_have_text("This file is larger than 10 MB. Choose a smaller one.")
    expect(card.locator("#status")).to_have_class("error")
    expect(card.locator("#choose")).to_be_visible()
    assert upload_server.uploads == []
    assert sent(page, "ui/message") == []


def test_upload_card_sends_a_pdf_and_puts_the_message_in_the_reply_box(page, upload_server):
    card = open_card(page, upload_server, "upload-card.html")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(str(PDF))
    status = card.get_by_role("status")
    expect(status.locator("strong")).to_have_text(
        f"Got {PDF.name}. Press Enter to send the message in your reply box and start reading it.")
    expect(status).to_contain_text("A PDF usually takes a minute or two to read")
    expect(status).to_contain_text("If your reply box is empty, type \"I've chosen it\" and send that.")
    expect(card.locator("#status")).to_have_class("got")
    expect(card.locator("#choose")).to_be_hidden()
    [(query, body)] = upload_server.uploads
    device = card_frame(page).evaluate("localStorage.getItem('device')")
    assert re.fullmatch(r"[0-9a-f]{32}", device)
    assert query == {"id": ["ABC123"], "device": [device]}
    assert body == PDF.read_bytes()
    [message] = sent(page, "ui/message")
    assert message["params"] == {"role": "user", "content": [{"type": "text", "text": f"I've chosen my score: {PDF.name}"}]}


def test_upload_card_words_a_musicxml_file_for_analysis(page, upload_server):
    upload_server.upload_reply = (200, {"kind": "musicxml"})
    card = open_card(page, upload_server, "upload-card.html")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(str(MUSICXML))
    status = card.get_by_role("status")
    expect(status.locator("strong")).to_have_text(
        f"Got {MUSICXML.name}. Press Enter to send the message in your reply box and start the analysis.")
    expect(status).not_to_contain_text("PDF")
    assert sent(page, "ui/message")[0]["params"]["content"][0]["text"] == f"I've chosen my score: {MUSICXML.name}"


def test_upload_card_shows_the_server_error_and_offers_the_button_again(page, upload_server):
    refusal = "A file was already chosen in this card. To choose another, ask Claude for a new card."
    upload_server.upload_reply = (409, {"error": refusal})
    card = open_card(page, upload_server, "upload-card.html")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(str(PDF))
    expect(card.locator("#status")).to_have_text(refusal)
    expect(card.locator("#status")).to_have_class("error")
    expect(card.locator("#choose")).to_be_visible()
    assert sent(page, "ui/message") == []


def test_upload_card_says_to_check_the_connection_when_the_upload_fails(page, upload_server):
    upload_server.upload_reply = None
    card = open_card(page, upload_server, "upload-card.html")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(str(PDF))
    expect(card.locator("#status")).to_have_text(
        "The file could not be sent. Check your connection and choose it again.")
    expect(card.locator("#status")).to_have_class("error")
    expect(card.locator("#choose")).to_be_visible()


def test_upload_card_asks_to_tell_claude_when_the_host_refuses_the_message(page, upload_server):
    card = open_card(page, upload_server, "upload-card.html")
    page.evaluate("replies['ui/message'] = { error: { code: -32000, message: 'refused' } }")
    deliver(page, {"upload_id": "ABC123"})
    card.locator("#file").set_input_files(str(PDF))
    expect(card.get_by_role("status")).to_have_text(f"Got {PDF.name}. Now tell Claude in the chat that you have chosen it.")


def test_upload_card_status_is_a_polite_live_region(page, upload_server):
    status = open_card(page, upload_server, "upload-card.html").locator("#status")
    expect(status).to_have_attribute("role", "status")
    expect(status).to_have_attribute("aria-live", "polite")


def links(server, **changes):
    files = f"{base(server)}/files/chopin"
    result = {"image_url": f"{base(server)}/page.png", "pdf_url": f"{files}.pdf", "musicxml_url": f"{files}.musicxml",
              "worksheet_url": f"{files}-worksheet.pdf", "midi_url": f"{files}.mid", "romantext_url": f"{files}.txt",
              "caption": "Analysis of bars 1–8", "shaded_bars": []}
    result.update(changes)
    return {name: value for name, value in result.items() if value is not None}


EXTRAS = {"musicxml": "MusicXML", "worksheet": "Blank worksheet", "midi": "MIDI", "romantext": "Analysis as text"}


def opened(page):
    return [message["params"]["url"] for message in sent(page, "ui/open-link")]


def test_analysis_card_shows_a_full_result_and_opens_every_download(page, server):
    card = open_card(page, server, "card.html")
    result = links(server)
    deliver(page, result)
    expect(card.get_by_text("Analysis of bars 1–8")).to_be_visible()
    expect(card.locator("#shading")).to_be_hidden()
    expect(card.locator("#rating")).to_be_hidden()
    expect(card.locator("#suggest")).to_be_visible()
    card.get_by_role("button", name="Open the page full size: Analysis of bars 1–8").click()
    card.get_by_role("button", name="Download PDF").click()
    expect(card.locator("#more")).to_be_visible()
    for name, label in EXTRAS.items():
        card.get_by_role("button", name=label, exact=True).click()
    page.wait_for_function("received.filter((m) => m.method === 'ui/open-link').length === 6")
    assert opened(page) == [result["image_url"], result["pdf_url"], *(result[f"{name}_url"] for name in EXTRAS)]


def test_analysis_card_opens_links_through_openai_when_it_is_there(page, server):
    card = open_card(page, server, "card.html", openai=True)
    result = links(server)
    deliver(page, result)
    card.locator("#open-page").click()
    card.locator("#pdf").click()
    page.wait_for_function("external_links.length === 2")
    assert page.evaluate("external_links") == [result["image_url"], result["pdf_url"]]
    assert opened(page) == []


def test_analysis_card_hides_downloads_it_has_no_url_for(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server, musicxml_url=None, worksheet_url=None, romantext_url=None))
    expect(card.locator("#midi")).to_be_visible()
    for name in ("musicxml", "worksheet", "romantext"):
        expect(card.locator(f"#{name}")).to_be_hidden()
    deliver(page, links(server, **{f"{name}_url": None for name in EXTRAS}))
    expect(card.locator("#more")).to_be_hidden()


def test_analysis_card_hides_download_pdf_without_a_pdf_url(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server, pdf_url=None))
    expect(card.locator("#open-page")).to_be_visible()
    expect(card.locator("#pdf")).to_be_hidden(timeout=2000)


def test_analysis_card_keys_the_shaded_bars_and_names_them_on_the_image(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server, caption="What I read from your PDF, every bar", shaded_bars=[18, 19]))
    expect(card.locator("#shading")).to_be_visible()
    expect(card.locator("#shading")).to_have_text("Shaded bars may be misread; check them against your copy.")
    description = "What I read from your PDF, every bar. Shaded bars, which may be misread: 18, 19"
    expect(card.get_by_role("button", name=f"Open the page full size: {description}")).to_be_visible()
    expect(card.get_by_role("img", name=description)).to_be_visible()


def test_analysis_card_still_shows_an_old_result_without_caption_or_shading(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server, caption=None, shaded_bars=None))
    expect(card.locator("#caption")).to_be_hidden()
    expect(card.locator("#shading")).to_be_hidden()
    expect(card.get_by_role("img", name="Engraved score")).to_be_visible()
    expect(card.get_by_role("button", name="Download PDF")).to_be_visible()


def test_analysis_card_sends_a_rating_and_says_thanks(page, server):
    card = open_card(page, server, "card.html", openai=True)
    deliver(page, links(server), {"ask_for_rating": True})
    expect(card.get_by_text("Was this analysis helpful?")).to_be_visible()
    page.evaluate("hold = true")
    card.get_by_role("button", name="Yes, helpful").click()
    expect(card.get_by_role("button", name="Yes, helpful")).to_be_disabled()
    expect(card.get_by_role("button", name="Not helpful")).to_be_disabled()
    assert first_sent(page, "tools/call")["params"] == {"name": "rate_analysis", "arguments": {"helpful": True}}
    page.evaluate("release()")
    expect(card.locator("#rating-status")).to_have_text("Thanks for telling us.")
    for element in ("#question", "#up", "#down"):
        expect(card.locator(element)).to_be_hidden()
    assert page.evaluate("widget_states") == [{"rated": True}]


def test_analysis_card_asks_to_rate_again_when_the_rating_fails(page, server):
    card = open_card(page, server, "card.html")
    page.evaluate("replies['tools/call'] = { result: { isError: true } }")
    deliver(page, links(server), {"ask_for_rating": True})
    card.get_by_role("button", name="Not helpful").click()
    expect(card.locator("#rating-status")).to_have_text("It could not be sent; please try again.")
    expect(card.get_by_role("button", name="Yes, helpful")).to_be_enabled()
    expect(card.get_by_role("button", name="Not helpful")).to_be_enabled()
    assert first_sent(page, "tools/call")["params"]["arguments"] == {"helpful": False}


REPORT = {"report": {"text": "Something went wrong on our side, not with your score.", "reference": "a1b2c3d4"}}


def test_analysis_card_sends_a_problem_report(page, server):
    card = open_card(page, server, "card.html", openai=True)
    deliver(page, {}, REPORT)
    expect(card.get_by_text(REPORT["report"]["text"])).to_be_visible()
    expect(card.locator("#sending")).to_have_text(
        "Sends us reference a1b2c3d4 so we can look into it. Nothing from your chat is sent.")
    expect(card.locator("#open-page")).to_be_hidden()
    page.evaluate("hold = true")
    card.get_by_role("button", name="Send this problem to us").click()
    expect(card.locator("#send")).to_be_disabled()
    assert first_sent(page, "tools/call")["params"] == {"name": "report_problem", "arguments": {"reference": "a1b2c3d4"}}
    page.evaluate("release()")
    expect(card.locator("#report-status")).to_have_text("Sent. Thank you; we look at every report.")
    expect(card.locator("#send")).to_be_hidden()
    expect(card.locator("#sending")).to_be_hidden()
    assert page.evaluate("widget_states") == [{"reported": True}]


def test_analysis_card_gives_the_reference_when_a_report_cannot_be_sent(page, server):
    card = open_card(page, server, "card.html")
    page.evaluate("replies['tools/call'] = { result: { isError: true } }")
    deliver(page, {}, REPORT)
    card.get_by_role("button", name="Send this problem to us").click()
    expect(card.locator("#report-status")).to_have_text(
        "It could not be sent from here. You can email support@sheetmusicanalysis.com and mention reference a1b2c3d4.")
    expect(card.locator("#send")).to_be_hidden()


def test_analysis_card_sends_a_suggestion(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server))
    card.get_by_role("button", name="Suggest something").click()
    text = card.get_by_label("What would you like it to do? Ideas, problems, anything.")
    expect(text).to_be_focused()
    send = card.get_by_role("button", name="Send", exact=True)
    expect(send).to_be_disabled()
    text.fill("   ")
    expect(send).to_be_disabled()
    text.fill("  Show key changes  ")
    expect(send).to_be_enabled()
    page.evaluate("hold = true")
    send.click()
    expect(send).to_be_disabled()
    expect(card.get_by_role("button", name="Cancel")).to_be_disabled()
    assert first_sent(page, "tools/call")["params"] == {"name": "send_suggestion", "arguments": {"text": "Show key changes"}}
    page.evaluate("release()")
    expect(card.locator("#suggest-status")).to_have_text("Sent. Thank you; we read every message.")
    expect(card.locator("#suggest-form")).to_be_hidden()


def test_analysis_card_cancel_closes_the_suggestion_form(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server))
    card.get_by_role("button", name="Suggest something").click()
    expect(card.locator("#suggest-form")).to_be_visible()
    card.get_by_role("button", name="Cancel").click()
    expect(card.locator("#suggest-form")).to_be_hidden()
    expect(card.get_by_role("button", name="Suggest something")).to_be_focused()


def test_analysis_card_says_how_to_send_a_suggestion_that_failed(page, server):
    card = open_card(page, server, "card.html")
    page.evaluate("replies['tools/call'] = { result: { isError: true } }")
    deliver(page, links(server))
    card.get_by_role("button", name="Suggest something").click()
    card.locator("#suggestion").fill("Show key changes")
    card.get_by_role("button", name="Send", exact=True).click()
    expect(card.locator("#suggest-status")).to_have_text(
        "It could not be sent from here. You can copy your message and email it to support@sheetmusicanalysis.com.")
    expect(card.locator("#suggest-send")).to_be_hidden()
    expect(card.get_by_role("button", name="Cancel")).to_be_enabled()
    expect(card.locator("#suggestion")).to_have_value("Show key changes")


STILL_READING = "Still reading your PDF: 1 min 40 s so far. What I read appears next, then the analysis."


def test_reading_card_shows_only_a_status_line_for_a_result_without_an_image(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, {"status": STILL_READING})
    expect(card.get_by_text(STILL_READING)).to_be_visible()
    for element in ("#caption", "#shading", "#open-page", "#actions", "#more", "#rating", "#report", "#suggest"):
        expect(card.locator(element)).to_be_hidden()
    page.wait_for_function("received.filter((m) => m.method === 'ui/notifications/size-changed').at(-1).params.height > 20")


def test_reading_card_status_line_gives_way_to_the_reading(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, {"status": STILL_READING})
    expect(card.get_by_text(STILL_READING)).to_be_visible()
    deliver(page, links(server, caption="What I read from your PDF, every bar"))
    expect(card.get_by_text("What I read from your PDF, every bar")).to_be_visible()
    expect(card.get_by_text(STILL_READING)).to_be_hidden()


CARD_CONTENT = ("#caption", "#shading", "#open-page", "#actions", "#more", "#rating", "#suggest")


def test_reading_card_status_after_a_reading_hides_the_old_reading(page, server):
    card = open_card(page, server, "card.html")
    deliver(page, links(server, shaded_bars=[3]), {"ask_for_rating": True})
    expect(card.locator("#open-page")).to_be_visible()
    deliver(page, {"status": STILL_READING})
    expect(card.get_by_text(STILL_READING)).to_be_visible()
    for element in CARD_CONTENT:
        expect(card.locator(element)).to_be_hidden()


def test_reading_card_status_after_a_reading_hides_the_old_reading_in_chatgpt(page, server):
    page.add_init_script("if (window !== window.top) window.openai = { toolOutput: %s };" % json.dumps(links(server)))
    card = open_card(page, server, "card.html")
    expect(card.locator("#open-page")).to_be_visible()
    card_frame(page).evaluate("""(status) => {
        window.openai.toolOutput = { status };
        window.dispatchEvent(new Event("openai:set_globals"));
    }""", STILL_READING)
    expect(card.get_by_text(STILL_READING)).to_be_visible()
    for element in CARD_CONTENT:
        expect(card.locator(element)).to_be_hidden()


@pytest.mark.parametrize("update", [
    "",
    "window.openai.toolResponseMetadata = { ask_for_rating: true };",
    "window.openai.toolOutput = { result: { caption: 'Analysis of the whole score' } };",
])
def test_analysis_card_keeps_a_result_from_the_host_when_chatgpt_updates_its_globals_without_a_picture(page, server, update):
    card = open_card(page, server, "card.html", openai=True)
    deliver(page, links(server))
    expect(card.locator("#open-page")).to_be_visible()
    card_frame(page).evaluate(update + "window.dispatchEvent(new Event('openai:set_globals'))")
    for element in ("#caption", "#open-page", "#actions", "#more", "#suggest"):
        expect(card.locator(element)).to_be_visible()


def test_analysis_card_reports_its_size_once_however_often_chatgpt_updates_its_globals(page, server):
    page.add_init_script("if (window !== window.top) window.openai = { toolOutput: %s };" % json.dumps(links(server)))
    card = open_card(page, server, "card.html")
    expect(card.locator("#open-page")).to_be_visible()
    page.wait_for_function("received.filter((m) => m.method === 'ui/notifications/size-changed').at(-1).params.height > 200")
    page.wait_for_timeout(500)
    settled = len(sent(page, "ui/notifications/size-changed"))
    for _ in range(5):
        card_frame(page).evaluate("window.dispatchEvent(new Event('openai:set_globals'))")
    page.wait_for_timeout(500)
    assert len(sent(page, "ui/notifications/size-changed")) == settled


def test_reading_card_shows_the_status_chatgpt_opens_it_with(page, server):
    page.add_init_script("if (window !== window.top) window.openai = { toolOutput: { status: %s } };" % json.dumps(STILL_READING))
    card = open_card(page, server, "card.html")
    expect(card.get_by_text(STILL_READING)).to_be_visible()
    expect(card.locator("#open-page")).to_be_hidden()


def test_analysis_card_takes_the_theme_from_the_host(page, server):
    open_card(page, server, "card.html")
    frame = card_frame(page)
    frame.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    assert frame.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(33, 33, 33)"


@pytest.fixture(scope="module")
def performance():
    return performance_text(marked_index(MUSICXML.read_bytes()), (1, 8))


def total_clock(performance):
    now, total = 0, 0
    for token in performance.split()[1:]:
        if token[0] != "v":
            delta, length, _ = map(int, token.split("."))
            now += delta / 100
            total = max(total, now + length / 100)
    return f"{int(total) // 60}:{int(total) % 60:02d}"


def test_player_stays_hidden_until_a_performance_arrives(page, server, performance):
    card = open_card(page, server, "player.html")
    deliver(page, {"performance": "N1 div=4", "measures": [1, 8]})
    card_frame(page).wait_for_function("document.getElementById('bars').textContent === 'Bars 1–8'")
    expect(card.locator("#play")).to_be_hidden()
    deliver(page, {"performance": performance, "measures": [1, 8]})
    expect(card.locator("#play")).to_be_visible()


def test_player_shows_the_bars_the_time_and_a_44_px_play_button(page, server, performance):
    card = open_card(page, server, "player.html")
    deliver(page, {"performance": performance, "measures": [1, 8]})
    expect(card.locator("#bars")).to_have_text("Bars 1–8")
    play = card.get_by_role("button", name="Play")
    expect(play).to_be_enabled()
    box = play.bounding_box()
    assert (box["width"], box["height"]) == (44, 44)
    expect(card.locator("#time")).to_have_text(f"0:00 / {total_clock(performance)}")
    assert total_clock(performance) != "0:00"


def test_player_names_a_single_bar(page, server, performance):
    card = open_card(page, server, "player.html")
    deliver(page, {"performance": performance, "measures": [5, 5]})
    expect(card.locator("#bars")).to_have_text("Bar 5")


def test_player_shows_no_bar_label_without_measures(page, server, performance):
    card = open_card(page, server, "player.html")
    deliver(page, {"performance": performance})
    expect(card.locator("#play")).to_be_visible()
    expect(card.locator("#bars")).to_be_hidden()
