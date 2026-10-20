import asyncio
import base64
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import venv

import pytest

from engine import correct
from engine.render import load_toolkit
from engine.score import ScoreIndex
from server import app

ROOT = Path(__file__).parent.parent
READING = ROOT / 'tests/data/chopin_prelude_op28_no4_reading.musicxml'


def replacement():
    lines = correct.bars_from_musicxml(READING.read_bytes(), 18).splitlines()
    return '\n'.join(lines[:2] + ['1.1: 12 D5 C5 8 E5 E4 A4 36 F#4 12 A4']
                     + [line for line in lines if line.startswith('2.')])


def check_correction(after):
    before = READING.read_bytes()
    review = correct.review_correction(before, after)
    assert review.changed_bars == [18]
    assert 'three eighth notes are now a triplet' in review.notes[18]
    old = ScoreIndex(load_toolkit(before).getMEI())
    new = ScoreIndex(load_toolkit(after).getMEI())
    signature = lambda bar: [(e.staff, e.onset, e.duration, e.pitch) for e in bar.events]
    assert [signature(m) for m in old.measures if m.number != 18] == [
        signature(m) for m in new.measures if m.number != 18]


def test_server_correct_real_triplet_and_draft_score_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/READ18', READING.read_bytes())
    result = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': 'READ18', 'replacement_bars': replacement()}))
    assert not result.is_error
    data = result.structured_content
    assert data['score_id'] != 'READ18'
    assert data['changed_bars'] == [18]
    assert 'three eighth notes are now a triplet' in data['notes']['18']
    assert len(data['image_urls']) == 1
    png = app.store.get('files/' + data['image_urls'][0].rsplit('/', 1)[1])
    assert png.startswith(b'\x89PNG')
    images = [item for item in result.content if item.type == 'image']
    assert len(images) == 1
    assert base64.b64decode(images[0].data).startswith(b'\x89PNG')
    text = next(item.text for item in result.content if item.type == 'text')
    assert 'your suggestion' in text
    assert 'only after confirmation' in text
    assert 'If they decline, keep using score_id READ18.' in text
    tools = asyncio.run(app.mcp.list_tools())
    description = next(tool.description for tool in tools if tool.name == 'correct_bars')
    assert 'read_pdf flagged' in description
    assert 'you can see is misread' in description
    assert 'confident' in description
    assert 'your suggestion' in description
    assert 'If they decline, keep using the original score_id.' in description
    after, given = asyncio.run(app.resolve_score(None, data['score_id']))
    assert given == 'score_id'
    check_correction(after)
    assert app.store.get('scores/READ18') == READING.read_bytes()
    assert app.store.get(f"scores/{data['score_id']}.draft.json") is None
    counts = json.loads(next((tmp_path / 'usage').glob('*.json')).read_text())
    assert counts['render'] == 1
    assert 'draft' not in counts


@pytest.mark.parametrize('bad, message', [
    ('', 'N1 div='),
    ('N1 ts=2/2 ks=1s\nm18 len=96\n1.1: 96 D5', 'div='),
    (None, 'voice 1.1 adds up to 7/2; expected 4 quarter notes'),
    ('N1 div=24 ts=4/0 ks=0\nm18 len=96\n1.1: 96 D5\n2.1: 96 r', 'meter denominator'),
])
def test_server_correct_invalid_bars_are_actionable(tmp_path, monkeypatch, bad, message):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/READ18', READING.read_bytes())
    text = replacement().replace('36 F#4', '24 F#4') if bad is None else bad
    result = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': 'READ18', 'replacement_bars': text}))
    assert result.is_error
    assert message in result.content[0].text
    assert [p.name for p in (tmp_path / 'scores').iterdir()] == ['READ18']
    assert not (tmp_path / 'files').exists()


def test_server_correct_disjoint_bars_and_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    before = READING.read_bytes()
    app.store.put('scores/READ18', before)
    bar2 = correct.bars_from_musicxml(before, 2).replace('B4', 'A4')
    text = bar2 + '\n' + '\n'.join(replacement().splitlines()[1:])
    result = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': 'READ18', 'replacement_bars': text}))
    assert not result.is_error
    data = result.structured_content
    assert data['changed_bars'] == [2, 18]
    assert len(data['image_urls']) == 2
    assert len([item for item in result.content if item.type == 'image']) == 2
    after, _ = asyncio.run(app.resolve_score(None, data['score_id']))
    assert correct.review_correction(before, after).changed_bars == [2, 18]
    stored = sorted(p.name for p in (tmp_path / 'scores').iterdir())
    unchanged = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': data['score_id'], 'replacement_bars': text}))
    assert not unchanged.is_error
    assert unchanged.structured_content['changed_bars'] == []
    assert unchanged.structured_content['image_urls'] == []
    assert f"keep using score_id {data['score_id']}" in unchanged.content[0].text
    assert sorted(p.name for p in (tmp_path / 'scores').iterdir()) == stored


def test_server_correct_missing_score_and_render_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    result = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': 'MISSING', 'replacement_bars': replacement()}))
    assert result.is_error
    assert "No score has the id 'MISSING'" in result.content[0].text
    assert not (tmp_path / 'usage').exists()
    app.store.put('scores/READ18', READING.read_bytes())
    asyncio.run(app.take('render', 'other'))
    usage = next((tmp_path / 'usage').glob('*.json'))
    usage.write_text(json.dumps({'render': app.DAILY_LIMITS['render']}))
    limited = asyncio.run(app.mcp.call_tool('correct_bars', {
        'score_id': 'READ18', 'replacement_bars': replacement()}))
    assert limited.is_error
    assert limited.content[0].text == app.LIMIT_MESSAGE
    assert [p.name for p in (tmp_path / 'scores').iterdir()] == ['READ18']
    assert not (tmp_path / 'files').exists()


def run_script(text, tmp_path):
    corrections = tmp_path / 'bars.txt'
    corrections.write_text(text)
    return subprocess.run([
        sys.executable, str(ROOT / 'skill/scripts/correct_score.py'), str(READING),
        str(corrections), '--out-dir', str(tmp_path / 'result')],
        cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, text=True)


def test_skill_correct_real_triplet_subprocess(tmp_path):
    result = run_script(replacement(), tmp_path)
    assert result.returncode == 0, result.stderr
    check_correction((tmp_path / 'result/corrected.musicxml').read_bytes())
    assert (tmp_path / 'result/corrected.png').read_bytes().startswith(b'\x89PNG')
    assert 'Bar 18: three eighth notes are now a triplet' in result.stdout
    assert 'confirm against their copy' in result.stdout


def test_skill_missing_music21_reports_setup_command(tmp_path):
    isolated = tmp_path / 'env'
    venv.EnvBuilder(with_pip=False).create(isolated)
    packages = next((isolated / 'lib').glob('python*/site-packages'))
    for source in map(Path, site.getsitepackages()):
        for package in source.iterdir():
            if not package.name.startswith('music21') and not (packages / package.name).exists():
                (packages / package.name).symlink_to(package)
    bars = tmp_path / 'bars.txt'
    bars.write_text(replacement())
    result = subprocess.run([
        str(isolated / 'bin/python'), str(ROOT / 'skill/scripts/correct_score.py'),
        str(READING), str(bars), '--out-dir', str(tmp_path / 'result')],
        cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'python3 -m pip install music21' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not (tmp_path / 'result').exists()


def test_skill_invalid_voice_writes_no_outputs(tmp_path):
    result = run_script(replacement().replace('36 F#4', '24 F#4'), tmp_path)
    assert result.returncode == 1
    assert 'voice 1.1 adds up to 7/2; expected 4 quarter notes' in result.stderr
    assert not (tmp_path / 'result').exists()


@pytest.mark.parametrize('text, message', [
    ('', 'N1 div='),
    ('N1 ts=2/2 ks=1s\nm18 len=96\n1.1: 96 D5', 'N1 div='),
    ('N1 div=bad ts=2/2 ks=1s\nm18 len=96\n1.1: 96 D5', 'N1 div='),
    ('N1 div=24 ts=4/0 ks=0\nm18 len=96\n1.1: 96 D5\n2.1: 96 r', 'meter denominator'),
])
def test_malformed_correction_has_actionable_error(text, message):
    with pytest.raises(correct.CorrectionError, match=message):
        correct.replace_bars(READING.read_bytes(), text)


KINKEL = ROOT / 'tests/data/awkward/kinkel-op8-5-trennung-reading.musicxml'
KINKEL_BAR = 'N1 div=2 ts=4/4 ks=4f\nm10 len=8\n1.1: 8 C5'


def call(tmp_path, monkeypatch, score, **arguments):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/SCORE1', score)
    return asyncio.run(app.mcp.call_tool('correct_bars', {'score_id': 'SCORE1', **arguments}))


@pytest.mark.parametrize('part, message', [
    (None, 'P1 Voice, P2 Piano'),
    ('Harp', 'P1 Voice, P2 Piano'),
])
def test_server_correct_multipart_error_lists_parts(tmp_path, monkeypatch, part, message):
    result = call(tmp_path, monkeypatch, KINKEL.read_bytes(), replacement_bars=KINKEL_BAR, part=part)
    assert result.is_error
    assert message in result.content[0].text


@pytest.mark.parametrize('part', ['P1', 'voice'])
def test_server_correct_multipart_by_id_or_name(tmp_path, monkeypatch, part):
    result = call(tmp_path, monkeypatch, KINKEL.read_bytes(), replacement_bars=KINKEL_BAR, part=part)
    assert not result.is_error, result.content[0].text
    assert result.structured_content['changed_bars'] == [10]


@pytest.mark.parametrize('text, message', [
    ('N1 div=24 ts=4/4 ks=0\n1.1: 96 D5', "Line 2: a voice line needs a bar line like 'm3 len=96' before it"),
    ('N1 div=24 ts=4/4 ks=0\nm18\n1.1: 96 D5', "bar line 'm18' needs len="),
    ('N1 div=24 ts=4/4 ks=0\nm18 len=96\n1.1 96 r', "Line 3: expected 'staff.voice: tokens', e.g. '1.1: 24 C4'"),
])
def test_server_correct_malformed_lines_say_what_to_fix(tmp_path, monkeypatch, text, message):
    result = call(tmp_path, monkeypatch, READING.read_bytes(), replacement_bars=text)
    assert result.is_error
    assert message in result.content[0].text


def test_server_correct_invalid_bars_cost_nothing(tmp_path, monkeypatch):
    result = call(tmp_path, monkeypatch, READING.read_bytes(),
                  replacement_bars=replacement().replace('36 F#4', '24 F#4'))
    assert result.is_error
    assert not (tmp_path / 'usage').exists()


def test_review_note_names_the_staff():
    before = READING.read_bytes()
    bars = correct.bars_from_musicxml(before, 18).splitlines()
    text = '\n'.join(bars[:2] + ['1.1: 96 D5'] + [line for line in bars if line.startswith('2.')])
    after = correct.replace_bars(before, text)
    note = correct.review_correction(before, after).notes[18]
    assert 'note groups on staff 1 changed' in note


def test_review_is_trimmed_to_the_music_and_backs_only_the_changed_notes():
    from PIL import Image
    import io
    before = READING.read_bytes()
    after = correct.replace_bars(before, replacement())
    review = correct.review_correction(before, after)
    svg = review.engravings[0].svgs[0]
    assert svg.count('fill="#FDD478"') == 3
    image = Image.open(io.BytesIO(review.engravings[0].png()))
    assert image.width < 700
