import asyncio
import base64
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from starlette.requests import Request

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.check_analysis import from_musicxml
from engine.render import load_toolkit
from engine.score import MEI, XML_ID, ScoreIndex
from server import app

ROOT = Path(__file__).parent.parent


def check_export(data, annotations):
    mei = load_toolkit(data).getMEI()
    index = ScoreIndex(mei)
    nodes = {node.get(XML_ID): node for node in ET.fromstring(mei).iter()}
    actual = []
    for bar in index.measures:
        for event in bar.events:
            for verse in nodes[event.id].findall(f'{MEI}verse[@label="roman-analysis"]'):
                assert event.staff == 2
                actual.append((bar.number, bar.beat_of(event.onset), ''.join(verse.itertext()).strip()))
    expected, key = [], None
    for harmony in annotations.annotations:
        if harmony.type != 'harmony':
            continue
        text = harmony.label
        if harmony.key and harmony.key != key:
            key = harmony.key
            text = f'{key}: {text}'
        expected.append((harmony.at.measure, harmony.at.beat, text))
    assert sorted(actual) == sorted(expected)


@pytest.mark.parametrize('style', [None, 'current', 'abrsm', 'figured_bass'])
def test_server_render_style_and_musicxml(chopin, chopin_annotations, tmp_path, monkeypatch, style):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/REAL', chopin)
    annotations = chopin_annotations.model_copy(update={'style': style}) if style else chopin_annotations

    async def run():
        result = await app.render_analysis(None, 'REAL', annotations, measure_range='1-8')
        assert not result.is_error
        assert base64.b64decode(result.content[0].data) == render(
            chopin, annotations, measures=(1, 8)
        ).png(1)
        assert 'harmony labels (open in MuseScore' in result.content[1].text
        assert 'standard Roman numerals' in result.content[1].text
        for extension, signature in [('png', b'\x89PNG'), ('pdf', b'%PDF'), ('musicxml', b'<?xml')]:
            url = result.structured_content[f'{"image" if extension == "png" else extension}_url']
            name = url.rsplit('/', 1)[1]
            request = Request({'type': 'http', 'path_params': {'name': name}})
            response = await app.files(request)
            assert response.status_code == 200
            assert response.body.startswith(signature)
            disposition = 'inline' if extension == 'png' else 'attachment'
            assert response.headers['content-disposition'] == f'{disposition}; filename="analysis.{extension}"'
            assert response.headers['content-security-policy'] == 'sandbox'
            assert response.headers['x-content-type-options'] == 'nosniff'
            if extension == 'musicxml':
                assert response.media_type == 'application/vnd.recordare.musicxml+xml'
                check_export(response.body, annotations)

    asyncio.run(run())


def test_server_musicxml_download_is_sandboxed_and_text_is_accurate(tmp_path, monkeypatch):
    script = b'<credit page="1"><credit-words><h:script xmlns:h="http://www.w3.org/1999/xhtml">alert(1)</h:script></credit-words></credit>'
    score = (ROOT / 'tests/data/export_placement.musicxml').read_bytes().replace(b'<part-list>', script + b'<part-list>', 1)
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/XSS', score)

    async def run(annotations):
        result = await app.render_analysis(None, 'XSS', AnnotationList.model_validate(annotations))
        assert not result.is_error
        name = result.structured_content['musicxml_url'].rsplit('/', 1)[1]
        return result, await app.files(Request({'type': 'http', 'path_params': {'name': name}}))

    result, response = asyncio.run(run({'annotations': [{'type': 'harmony', 'at': {'measure': 1}, 'label': 'I'}]}))
    assert b':script' in response.body
    assert response.headers['content-disposition'] == 'attachment; filename="analysis.musicxml"'
    assert response.headers['content-security-policy'] == 'sandbox'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert 'harmony labels' in result.content[1].text
    result, _ = asyncio.run(run({'annotations': [{'type': 'cadence', 'at': {'measure': 1}, 'label': 'PAC'}]}))
    assert 'MusicXML (open in MuseScore' in result.content[1].text
    assert 'harmony labels' not in result.content[1].text


def test_legacy_latin1_render_and_export(tmp_path, monkeypatch):
    score = (ROOT / 'tests/data/export_placement.musicxml').read_bytes()
    score = score.replace(b' encoding="utf-8"', b'', 1).replace(
        b'<part-list>', b'<work><work-title>Caf\xe9</work-title></work><part-list>', 1
    )
    annotations = AnnotationList.model_validate({'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'key': 'G', 'label': 'I'},
    ]})
    expected_png = render(score, annotations).png(1)
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/LEGACY', score)

    async def run():
        result = await app.render_analysis(None, 'LEGACY', annotations)
        assert not result.is_error
        assert base64.b64decode(result.content[0].data) == expected_png
        name = result.structured_content['musicxml_url'].rsplit('/', 1)[1]
        response = await app.files(Request({'type': 'http', 'path_params': {'name': name}}))
        assert response.status_code == 200
        return response.body

    exported = asyncio.run(run())
    assert ET.fromstring(exported).findtext('work/work-title') == 'Café'
    labels = from_musicxml(exported)
    assert [(label.measure, label.beat, label.figure) for label in labels] == [(1, 1, 'I')]
    assert ScoreIndex(load_toolkit(exported).getMEI()).measure(1)


@pytest.mark.parametrize('original, replacement', [
    pytest.param(b'Treble', b'Treble & Solo', id='unescaped-ampersand'),
    pytest.param(b'<octave>4</octave>', b'', id='missing-octave'),
    pytest.param(b'<step>G</step>', b'', id='missing-step'),
])
def test_malformed_xml_keeps_render_when_export_fails(tmp_path, monkeypatch, original, replacement):
    score = (ROOT / 'tests/data/export_placement.musicxml').read_bytes().replace(
        original, replacement
    )
    annotations = AnnotationList.model_validate({'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'I'},
    ]})
    engraving = render(score, annotations)
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/MALFORMED', score)

    async def run():
        result = await app.render_analysis(None, 'MALFORMED', annotations)
        assert not result.is_error
        assert base64.b64decode(result.content[0].data) == engraving.png(1)
        assert 'MusicXML export unavailable' in result.content[1].text
        assert 'MuseScore' not in result.content[1].text
        assert 'Python' not in result.content[1].text and 'KeyError' not in result.content[1].text
        assert 'musicxml_url' not in result.structured_content
        for field, signature in [('image_url', b'\x89PNG'), ('pdf_url', b'%PDF')]:
            name = result.structured_content[field].rsplit('/', 1)[1]
            response = await app.files(Request({'type': 'http', 'path_params': {'name': name}}))
            assert response.status_code == 200
            assert response.body.startswith(signature)

    asyncio.run(run())


def pdf_text(data):
    import io
    from pypdf import PdfReader
    return ''.join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def check_extras(files, annotations, bars):
    import music21
    assert files['midi'][:4] == b'MThd'
    assert 'vii' not in pdf_text(files['worksheet'])
    assert 'vii' in pdf_text(files['pdf'])
    parsed = music21.converter.parse(files['romantext'].decode(), format='romantext')
    chords = list(parsed.recurse().getElementsByClass('RomanNumeral'))
    expected = [a for a in annotations.annotations if a.type == 'harmony' and bars[0] <= a.at.measure <= bars[1]]
    assert len(chords) == len(expected)
    assert [round(float(c.getOffsetInHierarchy(parsed)), 2) for c in chords][:3] == [0.0, 1.5, 3.0]
    assert_romantext_matches(chords, expected)


def assert_romantext_matches(chords, harmonies):
    import music21
    key = None
    for chord, harmony in zip(chords, harmonies):
        key = harmony.key or key
        expected = music21.key.Key(music21.pitch.Pitch(key).name, 'major' if key[0].isupper() else 'minor')
        assert chord.key.tonic.name == expected.tonic.name and chord.key.mode == expected.mode, (harmony.at, key)
        assert chord.figure == harmony.label.split()[0].replace('/o', 'ø'), harmony.at


def test_server_extra_downloads(chopin, chopin_annotations, tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/REAL', chopin)

    async def run():
        result = await app.render_analysis(None, 'REAL', chopin_annotations, measure_range='1-8')
        assert 'once per conversation' in result.content[1].text
        assert 'title' not in result.structured_content
        files = {}
        for key, extension, filename in [('pdf', 'pdf', 'analysis.pdf'), ('worksheet', 'pdf', 'worksheet.pdf'),
                                         ('midi', 'mid', 'analysis.mid'), ('romantext', 'rntxt', 'analysis.rntxt')]:
            name = result.structured_content[f'{key}_url'].rsplit('/', 1)[1]
            response = await app.files(Request({'type': 'http', 'path_params': {'name': name}}))
            assert response.status_code == 200 and name.endswith(f'.{extension}')
            assert response.headers['content-disposition'] == f'attachment; filename="{filename}"'
            assert response.headers['content-security-policy'] == 'sandbox'
            files[key] = response.body
        check_extras(files, chopin_annotations, (1, 8))

    asyncio.run(run())


def test_romantext_of_a_pickup_piece_with_a_key_change(tmp_path):
    from engine.export import export_romantext
    from engine.annotations import AnnotationList
    import music21
    h = lambda m, b, label, key=None: {'type': 'harmony', 'at': {'measure': m, 'beat': b}, 'label': label, **({'key': key} if key else {})}
    analysis = AnnotationList.model_validate({'annotations': [
        h(0, 1, 'i', 'g'), h(1, 1, 'iv6'), h(1, 2, 'Cad64'), h(1, 3, 'V7'), h(1, 4, 'i'), h(2, 1, 'V65/III'),
        h(2, 3, 'I', 'Bb'), h(2, 4, 'V43'), h(3, 1, 'I6')]})
    score = (ROOT / 'tests/data/part_writing_bwv102.7.musicxml').read_bytes()
    harmonies = analysis.annotations
    for measures, chosen in [(None, harmonies), ((1, 3), harmonies)]:
        text = export_romantext(score, analysis.model_dump(), measures).decode()
        chords = list(music21.converter.parse(text, format='romantext').recurse().getElementsByClass('RomanNumeral'))
        assert len(chords) == len(chosen)
        assert_romantext_matches(chords, chosen)
        assert [c.measureNumber for c in chords][:2] == [0, 1]
        assert [c.beat for c in chords][:3] == [4.0, 1.0, 2.0]
