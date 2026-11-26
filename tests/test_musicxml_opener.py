import asyncio
import codecs
import io
import zipfile
from pathlib import Path

import pytest

from engine import correct
from server import app

LABELLED = Path(__file__).parent / "data/check_analysis/musescore-roman.musicxml"
DECLARATION = b'<?xml version="1.0" encoding="UTF-8"?>'


def packed(score: bytes, media_type: str | None, rootfile: bool = True) -> bytes:
    kind = f' media-type="{media_type}"' if media_type else ""
    listed = f'<rootfile full-path="score.xml"{kind}/>' if rootfile else ""
    container = f'<?xml version="1.0"?><container><rootfiles>{listed}</rootfiles></container>'
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as mxl:
        mxl.writestr("META-INF/container.xml", container)
        mxl.writestr("score.xml", score)
    return archive.getvalue()


def utf16(score: bytes) -> bytes:
    return score.replace(DECLARATION, b'<?xml version="1.0" encoding="UTF-16"?>').decode("utf-8").encode("utf-16")


VARIANTS = {
    "mxl-application-xml": lambda score: packed(score, "application/xml"),
    "mxl-text-xml": lambda score: packed(score, "text/xml"),
    "mxl-musicxml-type": lambda score: packed(score, "application/vnd.recordare.musicxml+xml"),
    "mxl-no-type": lambda score: packed(score, None),
    "utf-8-bom": lambda score: codecs.BOM_UTF8 + score,
    "utf-16": utf16,
}


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))


def student_check(score_id: str) -> str:
    text = asyncio.run(app.draft_analysis(None, score_id=score_id, student_analysis="score")).content[0].text
    return text.split("STUDENT CHECK (", 1)[1].split("## Method", 1)[0]


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_way_a_musicxml_file_comes_is_read_as_the_plain_file(local_store, variant):
    plain = LABELLED.read_bytes()
    app.store.put("scores/PLAIN", plain)
    app.store.put("scores/VARIANT", VARIANTS[variant](plain))
    assert student_check("VARIANT") == student_check("PLAIN")
    bars = correct.bars_from_musicxml(plain, 1, 1)
    assert correct.bars_from_musicxml(VARIANTS[variant](plain), 1, 1) == bars
    changed = asyncio.run(app.mcp.call_tool("correct_bars", {
        "score_id": "VARIANT", "replacement_bars": bars.replace("1.1: 4 G4", "1.1: 4 A4")}))
    assert not changed.is_error, changed.content[0].text
    assert changed.structured_content["changed_bars"] == [1]


def test_an_mxl_without_a_rootfile_is_refused_as_not_musicxml(local_store):
    app.store.put("scores/EMPTY", packed(LABELLED.read_bytes(), None, rootfile=False))
    result = asyncio.run(app.draft_analysis(None, score_id="EMPTY"))
    assert result.is_error and "This file is not MusicXML: its .mxl archive could not be read" in result.content[0].text
