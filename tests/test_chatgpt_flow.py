import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import anyio
import pikepdf
import pytest
from mcp.client.client import Client
from PIL import Image

from engine import draft, tint
from engine.annotate import render
from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
PDF = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
READING = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()
NOCTURNE = (DATA / "chopin_nocturne_op9_no2.mxl").read_bytes()
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}


@pytest.fixture
def server(monkeypatch, tmp_path):
    async def download(url):
        return PDF

    def read(data):
        return pdf_reader.PdfReading(READING, 1, False, [], [{"setting": 0, "outcome": "done"}])

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    return app.store


def call(name, arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def charged(store, kind):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = store.get(f"usage/{day}.json")
    return json.loads(raw).get(kind, 0) if raw else 0


def score_id_of(result):
    return text_of(result).split("score_id: ", 1)[1].split()[0]


def test_a_pdf_reading_states_its_bars_so_the_model_can_ask_for_real_ranges(server, capsys):
    result = call("read_pdf", ATTACHED)
    assert "The score has measures 0 to 24" in text_of(result)
    line = [line for line in logged(capsys, "read_pdf") if line.get("event") == "read_pdf_work"][-1]
    assert (line["bars"], line["bars_shaded"]) == (25, 1)
    assert line["page_points"] and line["image_pixels"] and "scan" in line


def test_drawing_with_no_marks_tells_the_model_to_analyse_first(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": []}, "measure_range": "1-4"})
    assert not result.is_error
    assert "call draft_analysis with score_id" in text_of(result)


def test_marks_that_fit_are_drawn_and_the_rest_are_listed(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"},
             {"type": "harmony", "at": {"measure": 99, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert not result.is_error
    assert "annotations[1] (harmony): Measure 99 does not exist" in text_of(result)


def test_a_request_turned_away_before_any_work_is_not_charged(server):
    result = call("render_analysis", {"score_id": "NOSUCHSCORE", "annotations": {"annotations": []}})
    assert result.is_error and "No score has the id" in text_of(result)
    assert charged(server, "render") == 0


def test_when_the_draft_model_fails_the_notes_table_still_comes_back(server, monkeypatch):
    monkeypatch.setattr(app, "SEND_DRAFT", True)
    def broken(*args):
        raise draft.DraftError("AnalysisGNN failed: injected")

    monkeypatch.setitem(app.draft.MODELS, "analysisgnn", broken)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("draft_analysis", {"score_id": score_id, "measure_range": "1-4"})
    assert not result.is_error
    assert "DRAFT UNAVAILABLE" in text_of(result) and "NOTES (one row per beat" in text_of(result)


def test_a_failed_correction_shows_the_bars_as_they_are_now(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("correct_bars", {"score_id": score_id, "replacement_bars": "N1 div=24 ts=2/2 ks=1\nm3 len=96\n1.1: 24 C4\n"})
    assert result.is_error
    assert "The score's current notes for measures 3-3" in text_of(result)
    assert "\nm3 len=" in text_of(result)


def test_a_pdf_that_cannot_be_read_says_what_to_try_next(server, monkeypatch):
    def unreadable(data):
        raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}])

    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable)
    result = call("read_pdf", ATTACHED)
    assert "a MusicXML file" in text_of(result)
    assert text_of(result).startswith("This call failed: no music was read, so there is no score_id")
    assert server.get(f"failed/{hashlib.sha256(PDF).hexdigest()}.pdf") == PDF


def test_losing_the_copy_of_an_unread_pdf_does_not_change_what_the_user_is_told(server, monkeypatch, capsys):
    def unreadable(data):
        raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}])

    def no_failed_copies(key, data, keep=server.put):
        if key.startswith("failed/"):
            raise OSError("bucket down")
        keep(key, data)

    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable)
    monkeypatch.setattr(server, "put", no_failed_copies)
    result = call("read_pdf", ATTACHED)
    assert "a MusicXML file" in text_of(result) and report_of(result)
    assert [line for line in logged(capsys, "read_pdf") if line.get("event") == "read_pdf_work"][-1]["failed_copy_lost"]


def test_a_whole_piece_comes_back_as_one_pdf_with_every_mark(server):
    server.put("scores/NOCTURNE", NOCTURNE)
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"},
             {"type": "harmony", "at": {"measure": 35, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": "NOCTURNE", "annotations": {"annotations": marks}})
    assert not result.is_error
    assert "Left out" not in text_of(result)
    pdf = pikepdf.open(io.BytesIO(server.get("files/" + result.structured_content["pdf_url"].rsplit("/", 1)[1])))
    assert len(pdf.pages) > 1


def test_numbers_of_marks_left_out_refer_to_the_list_the_model_sent(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 99, "beat": 1}, "label": "V"},
             {"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"},
             {"type": "harmony", "at": {"measure": 98, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert "annotations[0] (harmony): Measure 99" in text_of(result)
    assert "annotations[2] (harmony): Measure 98" in text_of(result)


def test_an_alternative_with_the_wrong_number_of_chords_is_left_out_and_the_rest_drawn(server, chopin, chopin_annotations, capsys):
    server.put("scores/NOCTURNE", NOCTURNE)
    marks = chopin_annotations.model_dump(exclude_none=True)["annotations"]
    alternative = {"type": "alternative", "start": {"measure": 6, "beat": 1}, "end": {"measure": 6}, "label": "c: V7 i iv"}
    result = call("render_analysis", {"score_id": "NOCTURNE", "annotations": {"annotations": marks + [alternative]}, "measure_range": "1-8"})
    assert not result.is_error
    assert f"annotations[{len(marks)}] (alternative): its label has 3 chords" in text_of(result)
    assert "Left out" in text_of(result) and "position" not in text_of(result)
    assert base64.b64decode(result.content[0].data) == render(chopin, chopin_annotations, measures=(1, 8)).png(1)
    assert logged(capsys, "render_analysis")[-1]["left_out"] == 1


def logged(capsys, tool):
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return [line for line in lines if line.get("tool") == tool or line.get("event") == f"{tool}_work"]


def test_a_crash_while_reading_a_pdf_is_a_server_error_with_the_reference_the_user_sees(server, monkeypatch, capsys):
    def crash(data):
        raise RuntimeError("injected")

    monkeypatch.setattr(app.pdf_reader, "read_pdf", crash)
    result = call("read_pdf", ATTACHED)
    lines = logged(capsys, "read_pdf")
    calls = [line for line in lines if line.get("tool") == "read_pdf"]
    assert calls[-1]["outcome"] == "server_error" and calls[-1]["severity"] == "ERROR"
    assert f"reference {calls[-1]['reference']}" in text_of(result)


def test_a_failed_draft_model_is_logged_as_degraded(server, monkeypatch, capsys):
    monkeypatch.setattr(app, "SEND_DRAFT", True)
    def broken(*args):
        raise draft.DraftError("AnalysisGNN failed: injected")

    monkeypatch.setitem(app.draft.MODELS, "analysisgnn", broken)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    capsys.readouterr()
    call("draft_analysis", {"score_id": score_id, "measure_range": "1-4"})
    line = logged(capsys, "draft_analysis")[-1]
    assert line["outcome"] == "degraded" and line["severity"] == "ERROR"


def test_a_long_pdf_reads_its_first_pages_and_says_which(server, monkeypatch):
    pages_read = []

    def read(data):
        pages_read.append(len(pdf_reader.open_pdf(data).pages))
        return pdf_reader.PdfReading(READING, pages_read[-1], False, [], [])

    def pdf_of(count):
        import io
        import pikepdf
        pdf = pikepdf.new()
        for _ in range(count):
            pdf.add_blank_page()
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()

    async def download(url):
        return pdf_of(10)

    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    result = call("read_pdf", ATTACHED)
    assert pages_read == [pdf_reader.READ_PAGES]
    assert f"Only pages 1-{pdf_reader.READ_PAGES} of the 10 were read" in text_of(result)
    assert charged(server, "pdf_page") == pdf_reader.READ_PAGES


@pytest.mark.xdist_group("draft_model")
def test_a_whole_score_draft_shows_the_drawing_format_before_the_long_tables(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    text = text_of(call("draft_analysis", {"score_id": score_id}))
    assert len(text) > 10000
    example = text.index('{"type": "harmony", "at": {"measure": 1')
    assert example < 500
    line = text[example:].split("\n", 1)[0].rstrip(".")
    marks = json.loads("[" + line + "]")
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-8"})
    assert not result.is_error
    assert "Left out" not in text_of(result)


def test_an_unknown_view_is_refused_before_it_is_charged(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4", "view": "full"})
    assert result.is_error and "view must be one of all, harmony, voice_leading, form" in text_of(result)
    assert charged(server, "render") == 0


def test_a_view_in_other_case_and_a_range_with_a_long_dash_are_drawn(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1–4", "view": "Harmony"})
    assert not result.is_error
    assert text_of(result).startswith("Analysis, measures 1-4, view harmony")


def test_a_drawing_with_no_marks_says_so_first_and_skips_the_extra_downloads(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": []}, "measure_range": "1-4"})
    assert text_of(result).startswith("No analysis marks were drawn")
    assert "worksheet" not in text_of(result).lower()


@pytest.mark.xdist_group("draft_model")
def test_a_whole_score_draft_gives_its_instructions_before_the_chords_and_the_notes_last(server, monkeypatch):
    monkeypatch.setattr(app, "SEND_DRAFT", True)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    text = text_of(call("draft_analysis", {"score_id": score_id}))
    assert text.index("HOW TO USE THIS DRAFT") < 1000
    assert text.index("HOW TO USE THIS DRAFT") < text.index("CHORDS:") < text.index("## Method") < text.index("NOTES (one row")


def test_the_worksheet_is_made_when_first_opened_and_the_other_downloads_with_the_drawing(server):
    from starlette.requests import Request

    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    links = result.structured_content
    names = {key: links[key].rsplit("/", 1)[1] for key in ("worksheet_url", "midi_url", "romantext_url")}
    assert server.get(f"files/{names['worksheet_url']}") is None
    assert server.get(f"files/{names['midi_url']}").startswith(b"MThd")
    assert server.get(f"files/{names['romantext_url']}").startswith(b"Time Signature")
    server.delete(f"scores/{score_id}")

    def opened(name):
        request = Request({"type": "http", "method": "GET", "path_params": {"name": name}, "headers": []})
        return anyio.run(app.files, request)

    response = opened(names["worksheet_url"])
    assert response.status_code == 200 and response.body.startswith(b"%PDF")
    assert server.get(f"files/{names['worksheet_url']}") == response.body


@pytest.mark.parametrize("name, plan", [
    ("chopin_nocturne_op9_no2.mxl", 'for the whole piece pass measure_range "all"'),
    ("piano/dvorak-9-2.mxl", "passages of at most 80 bars"),
])
def test_the_draft_says_whether_the_whole_score_can_be_drawn_in_one_call(server, monkeypatch, name, plan):
    def unavailable(*args):
        raise draft.DraftError("not needed here")

    monkeypatch.setitem(app.draft.MODELS, "analysisgnn", unavailable)
    text = app.make_draft((DATA / name).read_bytes(), "PLAN", None)
    assert plan in text[:1000]


def test_with_the_draft_parked_an_ordinary_score_gets_the_notes_without_starting_the_model(server, monkeypatch, capsys):
    def must_not_run(*args):
        raise AssertionError("the draft model was started")

    monkeypatch.setitem(app.draft.MODELS, "analysisgnn", must_not_run)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    capsys.readouterr()
    result = call("draft_analysis", {"score_id": score_id, "measure_range": "1-4"})
    text = text_of(result)
    assert not result.is_error
    assert "No automatic draft analysis" in text and "NOTES (one row per beat" in text
    assert "Draft analysis from" not in text and "DRAFT UNAVAILABLE" not in text and "HOW TO USE THIS DRAFT" not in text
    assert logged(capsys, "draft_analysis")[-1]["draft_sent"] is False


def test_with_the_draft_parked_a_score_is_charged_once_however_many_calls_ask_about_it(server, monkeypatch):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    for bars in ("1-4", "5-8", "1-8"):
        assert not call("draft_analysis", {"score_id": score_id, "measure_range": bars}).is_error
    assert charged(server, "draft") == 1


def test_the_sent_draft_is_logged(server, capsys, monkeypatch):
    monkeypatch.setattr(app, "SEND_DRAFT", True)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    capsys.readouterr()
    assert "Draft analysis from" in text_of(call("draft_analysis", {"score_id": score_id, "measure_range": "1-4"}))
    assert logged(capsys, "draft_analysis")[-1]["draft_sent"] is True


def report_of(result):
    return (result.meta or {}).get("report")


def test_an_unread_pdf_offers_the_user_a_report_that_finds_the_kept_file(server, monkeypatch, capsys):
    def unreadable(data):
        raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}])

    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable)
    result = call("read_pdf", ATTACHED)
    report = report_of(result)
    assert not result.is_error and report["text"] == app.UNREAD_PDF_FOR_CARD
    lines = logged(capsys, "read_pdf")
    assert [line for line in lines if line.get("tool") == "read_pdf"][-1]["outcome"] == "user_error"
    work = [line for line in lines if line.get("event") == "read_pdf_work"][-1]
    assert work["reference"] == report["reference"]
    assert server.get(f"failed/{work['digest']}.pdf") == PDF
    assert [line for line in lines if line.get("tool") == "read_pdf"][-1]["reference"] == report["reference"]
    assert not call("report_problem", {"reference": report["reference"]}).is_error
    reports = [line for line in logged(capsys, "report_problem") if line.get("event") == "report_problem"]
    assert reports[-1]["about"] == report["reference"]


def test_a_server_error_offers_a_report_with_the_reference_in_the_message(server, monkeypatch):
    def crash(data):
        raise RuntimeError("injected")

    monkeypatch.setattr(app.pdf_reader, "read_pdf", crash)
    result = call("read_pdf", ATTACHED)
    assert not result.is_error and f"reference {report_of(result)['reference']}" in text_of(result)
    assert text_of(result).startswith(app.FAILED_CALL)
    assert report_of(result)["text"] == app.OUR_ERROR_FOR_CARD


def test_a_crash_while_drawing_offers_a_report_and_is_logged_as_ours(server, monkeypatch, capsys):
    score_id = score_id_of(call("read_pdf", ATTACHED))

    def crash(*args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(app, "draw", crash)
    capsys.readouterr()
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": []}})
    assert not result.is_error and f"reference {report_of(result)['reference']}" in text_of(result)
    assert text_of(result).startswith(app.FAILED_CALL)
    line = logged(capsys, "render_analysis")[-1]
    assert (line["outcome"], line["severity"]) == ("server_error", "ERROR")


def test_a_crash_in_a_tool_with_no_card_stays_an_error(server, monkeypatch, capsys):
    score_id = score_id_of(call("read_pdf", ATTACHED))

    def crash(*args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(app, "make_draft", crash)
    capsys.readouterr()
    result = call("draft_analysis", {"score_id": score_id})
    assert result.is_error and report_of(result) is None and "support@sheetmusicanalysis.com" in text_of(result)
    assert logged(capsys, "draft_analysis")[-1]["outcome"] == "server_error"


def test_limits_and_mistakes_the_model_can_fix_offer_no_report(server, monkeypatch):
    assert report_of(call("render_analysis", {"score_id": "NOSUCHSCORE", "annotations": {"annotations": []}})) is None
    monkeypatch.setitem(app.DAILY_LIMITS, "pdf_page", 0)
    limited = call("read_pdf", ATTACHED)
    assert limited.is_error and app.LIMIT_MESSAGE in text_of(limited) and report_of(limited) is None


def test_only_the_card_can_send_a_report_and_only_a_reference(server):
    async def go():
        async with Client(app.mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            return tools["report_problem"], await client.call_tool("report_problem", {"reference": "see my chat"})

    tool, refused = anyio.run(go)
    assert tool.meta["ui"]["visibility"] == ["app"]
    assert refused.is_error


def test_cards_held_for_review_keep_their_old_page():
    async def go():
        async with Client(app.mcp) as client:
            return {uri: (await client.read_resource(uri)).contents[0].text
                    for uri in [app.CARD_URI, *app.HELD_CARD_URIS]}

    pages = anyio.run(go)
    assert "report_problem" in pages[app.CARD_URI]
    assert all("report_problem" not in pages[uri] for uri in app.HELD_CARD_URIS)


def shaded_pixels(result):
    page = Image.open(io.BytesIO(base64.b64decode(result.content[0].data))).convert("RGB")
    return sum(count for count, colour in page.getcolors(1 << 24)
               if all(abs(a - b) <= 2 for a, b in zip(colour, SHADE)))


SHADE = tuple(round(255 * (1 - float(tint.FLAG_OPACITY)) + int(tint.FLAG_BAR[i:i + 2], 16) * float(tint.FLAG_OPACITY))
              for i in (1, 3, 5))


def test_after_a_pdf_read_the_model_goes_straight_on_to_the_analysis(server):
    result = call("read_pdf", ATTACHED)
    text = text_of(result)
    assert "call draft_analysis with this score_id now" in text
    assert "wait" not in text.lower() and "go ahead" not in text.lower() and "check it against your copy" not in text
    assert "(shaded) looks misread" in text


def test_bars_shaded_in_the_reading_stay_shaded_on_the_analysis(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    shaded = json.loads(server.get(f"scores/{score_id}.shaded"))
    assert len(shaded) == 1
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]
    drawn = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}})
    assert f"Shaded bars ({shaded[0]}) may be misread" in text_of(drawn)
    assert shaded_pixels(drawn) > 1000
    elsewhere = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert "Shaded bars" not in text_of(elsewhere) and shaded_pixels(elsewhere) == 0


def test_a_musicxml_score_is_never_shaded(server):
    server.put("scores/NOCTURNE", NOCTURNE)
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"}]
    drawn = call("render_analysis", {"score_id": "NOCTURNE", "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert "Shaded bars" not in text_of(drawn) and shaded_pixels(drawn) == 0


def test_a_corrected_bar_is_no_longer_shaded(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    assert json.loads(server.get(f"scores/{score_id}.shaded")) == [18]
    bar = ("N1 div=24 ts=2/2 ks=1s\nm18 len=96\n1.1: 12 D5 C5 E5 E4 48 A4\n1.2: 48 r 36 F#4 12 A4\n"
           "2.1: 12 A3+C4+E4 A3+C4+E4 A2 E3+F#3+C4 B2+E3+B3 B2+E3+B3 C3+E3+A3 C3+E3+A3\n")
    corrected = call("correct_bars", {"score_id": score_id, "replacement_bars": bar})
    assert not corrected.is_error and "score_id: " in text_of(corrected), text_of(corrected)
    assert json.loads(server.get(f"scores/{score_id_of(corrected)}.shaded")) == []
