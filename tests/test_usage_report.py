"""Replay locally emitted server logs through the command-line report, without cloud access."""

import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from starlette.requests import Request

from engine.annotations import AnnotationList
from engine import notes
from engine import correct
from engine.render import load_toolkit
from engine.score import ScoreIndex
from server import app

ROOT = Path(__file__).parent.parent
TOOL = ROOT / 'tools/usage_report.py'


def run_report(path=None, stdin=None):
    return subprocess.run([sys.executable, str(TOOL), *([str(path)] if path else [])],
                          input=stdin, capture_output=True, text=True, env={**os.environ, 'PATH': ''})


def test_report_real_server_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path / 'store'))
    score = (ROOT / 'tests/data/part_writing_motion.musicxml').read_bytes()
    app.store.put('scores/REAL', score)
    annotations = AnnotationList(annotations=[])
    chatgpt = SimpleNamespace(headers={'user-agent': 'OpenAI'})
    claude = SimpleNamespace(headers={'user-agent': 'Claude'})
    captured = io.StringIO()

    async def calls():
        result = await app.draft_analysis(chatgpt, score_id='REAL', measure_range='1-2', student_analysis='key: C major; m1 I')
        assert not result.is_error
        assert 'PART-WRITING CHECK (' in result.content[0].text
        result = await app.draft_from_notes(claude, notes.encode(ScoreIndex(load_toolkit(score).getMEI())))
        assert not result.is_error
        for piano in (False, True):
            result = await app.render_analysis(chatgpt, 'REAL', annotations, measure_range='1-2', view='voice_leading', piano=piano)
            assert not result.is_error
            for field in ('pdf_url', 'musicxml_url'):
                name = result.structured_content[field].rsplit('/', 1)[1]
                response = await app.files(Request({'type': 'http', 'path_params': {'name': name},
                                                    'headers': [(b'user-agent', b'OpenAI')]}))
                assert response.status_code == 200
        malformed = (ROOT / 'tests/data/export_placement.musicxml').read_bytes().replace(b'Treble', b'Treble & Solo')
        app.store.put('scores/BADXML', malformed)
        result = await app.render_analysis(chatgpt, 'BADXML', AnnotationList.model_validate({'annotations': [
            {'type': 'harmony', 'at': {'measure': 1}, 'label': 'I'},
        ]}), view='harmony')
        assert not result.is_error and 'musicxml_url' not in result.structured_content
        result = await app.render_analysis(chatgpt, 'MISSING', annotations, measure_range='3-4', view='harmony')
        assert result.is_error
        result = await app.draft_analysis(chatgpt, score_id='REAL', student_analysis='I V I')
        assert result.is_error
        await app.files(Request({'type': 'http', 'path_params': {'name': 'missing.pdf'},
                                 'headers': [(b'user-agent', b'Claude')]}))
        day = app.datetime.now(app.timezone.utc).strftime('%Y-%m-%d')
        app.store.put(f'usage/{day}.json', json.dumps({'render': app.DAILY_LIMITS['render']}).encode())
        result = await app.render_analysis(claude, 'REAL', annotations, measure_range='5-6', view='form', piano=True)
        assert result.is_error

    with redirect_stdout(captured):
        asyncio.run(calls())
    payloads = [json.loads(line) for line in captured.getvalue().splitlines()]
    entries = [{'timestamp': '2026-10-11T23:59:00Z', 'jsonPayload': payload}
               for payload in payloads if payload.get('platform') == 'chatgpt']
    entries += [{'timestamp': '2026-10-12T00:01:00Z', 'textPayload': json.dumps(payload)}
                for payload in payloads if payload.get('platform') == 'claude']
    fixture = tmp_path / 'server.jsonl'
    fixture.write_text('\n'.join(json.dumps(entry) for entry in entries) + '\n')
    ran = run_report(fixture)
    assert ran.returncode == 0, ran.stderr
    rows = ran.stdout.splitlines()
    chat = next(row for row in rows if '2026-10-11  ChatGPT' in row)
    assert 'drafts 1  fresh drafts 1  cached drafts 0  renders 3  piano 1  corrections 0' in chat
    assert 'checks 1  part-writing 1' in chat
    assert 'exports 8  downloads 4' in chat
    assert 'limits 0  errors 3  questions 1' in chat
    assert 'views [harmony x2, voice_leading x2]' in chat
    assert 'ranges [1-2 x3, 3-4 x1, all x2]' in chat
    claude_row = next(row for row in rows if '2026-10-12  Claude' in row)
    assert 'drafts 1  fresh drafts 1  cached drafts 0  renders 0  piano 0  corrections 0' in claude_row
    assert 'checks 0  part-writing 1' in claude_row
    assert 'limits 1  errors 1' in claude_row
    assert 'views [form x1]' in claude_row and 'ranges [5-6 x1]' in claude_row
    array = run_report(stdin=json.dumps(entries, indent=2))
    assert array.returncode == 0 and array.stdout == ran.stdout
    raw = run_report(stdin=captured.getvalue())
    assert raw.returncode == 0, raw.stderr
    assert 'ChatGPT' in raw.stdout and 'Claude' in raw.stdout
    (tmp_path / 'usage.txt').write_text(ran.stdout)


def test_report_pdf_and_legacy_logs(tmp_path):
    captured = io.StringIO()
    # These are the read_pdf success/refusal log calls; downloading the attachment
    # and running Audiveris are deliberately outside this offline report test.
    with redirect_stdout(captured):
        app.log('read_pdf', platform='chatgpt', pages=3, seconds=2.1, scan=False, skipped=[], cached=False, keep_slurs=False)
        app.log('read_pdf', platform='chatgpt', pages=3, seconds=0.2, scan=False, skipped=[], cached=True, keep_slurs=True)
        app.log('read_pdf', platform='chatgpt', busy=True)
        app.log('read_pdf', platform='chatgpt', error='too many pages', pages=13)
        app.log('limit', tool='read_pdf', platform='chatgpt', pages=2)
        app.log('draft_analysis', platform='chatgpt', input='score_id', score_bytes=100, measure_range='all', seconds=0.1)
        app.log('render_analysis', platform='chatgpt', export_error='bad XML')
        app.log('render_analysis', platform='chatgpt', annotations=0, png_bytes=100, piano=True, view='all', measure_range='all')
    entries = [{'timestamp': '2026-10-10T10:00:00Z', 'jsonPayload': json.loads(line)}
               for line in captured.getvalue().splitlines()]
    entries += [{'timestamp': '2026-10-10T10:00:00Z', 'textPayload': 'Starting server'},
                {'timestamp': '2026-10-10T10:00:00Z', 'jsonPayload': {'message': 'unrelated'}}]
    fixture = tmp_path / 'pdf-legacy.json'
    fixture.write_text(json.dumps(entries, indent=2))
    ran = run_report(fixture)
    assert ran.returncode == 0, ran.stderr
    assert 'drafts 1  fresh drafts 0  cached drafts 0  renders 1  piano 1  corrections 0' in ran.stdout
    assert 'unknown draft cache 1' in ran.stdout
    assert 'pdf reads 2  pages 6  cached 1  busy 1  uncached pages 3' in ran.stdout
    assert 'limits 1  errors 2' in ran.stdout
    assert 'views [all x1]  ranges [all x2]' in ran.stdout
    assert 'unknown checks 1  part-writing 1  exports 3' in ran.stdout


def test_report_invalid_input():
    ran = run_report(path='-', stdin='{"event":')
    assert ran.returncode != 0
    assert 'Invalid JSON on line 1' in ran.stderr
    assert 'Traceback' not in ran.stderr


def test_report_recorded_fixture():
    # Payloads came from the calls above; Cloud envelope dates are illustrative.
    # PDF/legacy payloads replay log calls without downloading or invoking OMR.
    fixture = ROOT / 'tests/data/usage_report.jsonl'
    expected = (ROOT / 'tests/data/usage_report.txt').read_text()
    for ran in (run_report(fixture), run_report(stdin=fixture.read_text()),
                run_report(path='-', stdin=json.dumps([json.loads(line) for line in fixture.read_text().splitlines()]))):
        assert ran.returncode == 0, ran.stderr
        assert ran.stdout == expected


def test_download_without_headers_keeps_file_response(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    score = (ROOT / 'tests/data/export_placement.musicxml').read_bytes()
    app.store.put('files/real.musicxml', score)

    async def calls():
        for name, status in [('real.musicxml', 200), ('expired.pdf', 404)]:
            response = await app.files(Request({'type': 'http', 'path_params': {'name': name}}))
            assert response.status_code == status
            if status == 200:
                assert response.body == score

    asyncio.run(calls())
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(payload['event'], payload['platform'], payload['status']) for payload in payloads] == [
        ('download', 'other', 200), ('download', 'other', 404),
    ]


def test_report_correction_exports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    score = (ROOT / 'tests/data/chopin_prelude_op28_no4_reading.musicxml').read_bytes()
    app.store.put('scores/READ18', score)
    lines = correct.bars_from_musicxml(score, 18).splitlines()
    replacement = '\n'.join(lines[:2] + ['1.1: 12 D5 C5 8 E5 E4 A4 36 F#4 12 A4']
                            + [line for line in lines if line.startswith('2.')])
    result = asyncio.run(app.correct_bars(SimpleNamespace(headers={'user-agent': 'Claude'}),
                                         'READ18', replacement))
    assert not result.is_error
    count = len(result.structured_content['image_urls'])
    assert count == 1
    captured = capsys.readouterr().out
    (tmp_path / 'correction.jsonl').write_text(captured)
    ran = run_report(stdin=captured)
    assert ran.returncode == 0, ran.stderr
    assert 'corrections 1' in ran.stdout
    assert f'exports {count}  downloads 0' in ran.stdout
    assert f'export formats [png x{count}]' in ran.stdout


def test_clarification_logs_keep_student_text_private(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    score = (ROOT / 'tests/data/part_writing_motion.musicxml').read_bytes()
    app.store.put('scores/REAL', score)
    ctx = SimpleNamespace(headers={'user-agent': 'Claude'})
    student = 'm1 PRIVATE_STUDENT_TOKEN'

    async def calls():
        results = [await app.draft_analysis(ctx, score_id='REAL', student_analysis=student),
                   await app.draft_from_notes(ctx, notes='', student_analysis=student)]
        for result in results:
            assert result.is_error
            assert 'PRIVATE_STUDENT_TOKEN' in result.content[0].text

    asyncio.run(calls())
    captured = capsys.readouterr().out
    assert 'PRIVATE_STUDENT_TOKEN' not in captured
    payloads = [json.loads(line) for line in captured.splitlines()]
    assert len(payloads) == 2
    assert all(payload['clarification'] and payload['error'] == 'clarification_needed'
               for payload in payloads)
    ran = run_report(stdin=captured)
    assert ran.returncode == 0, ran.stderr
    assert 'errors 2  questions 2' in ran.stdout


def test_report_legacy_correction_exports(tmp_path, capsys):
    # Main's correction logs omit exports even when preview PNGs were published.
    app.log('correct_bars', platform='chatgpt', changed=1, pages=1)
    app.log('correct_bars', platform='claude', changed=0)
    app.log('correct_bars', platform='other', error='invalid replacement')
    fixture = tmp_path / 'legacy-corrections.jsonl'
    fixture.write_text(capsys.readouterr().out)
    ran = run_report(fixture)
    assert ran.returncode == 0, ran.stderr
    rows = ran.stdout.splitlines()
    chat = next(row for row in rows if '  ChatGPT  ' in row)
    assert 'corrections 1' in chat
    assert 'exports 0  downloads 0' in chat
    assert chat.endswith('unknown checks 0  part-writing 0  exports 1  unknown draft cache 0')
    for host in ('Claude', 'Other'):
        row = next(row for row in rows if f'  {host}  ' in row)
        assert f'corrections {1 if host == "Claude" else 0}' in row
        assert row.endswith('unknown checks 0  part-writing 0  exports 0  unknown draft cache 0')


def test_request_fields_keep_free_text_private(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    score = (ROOT / 'tests/data/part_writing_motion.musicxml').read_bytes()
    app.store.put('scores/REAL', score)
    ctx = SimpleNamespace(headers={'user-agent': 'Claude'})
    private = 'the bars where Anna sings'
    empty = AnnotationList(annotations=[])
    bad_position = AnnotationList.model_validate({'annotations': [
        {'type': 'harmony', 'at': {'measure': 999}, 'label': 'I'},
    ]})

    async def calls():
        # Cover every refusal path, including failures before normal validation.
        for score_id, measure_range, view, annotations in [
            ('MISSING', private, private, empty),
            ('REAL', private, private, empty),
            ('REAL', '1-2', private, bad_position),
            ('REAL', '1-2', private, empty),
        ]:
            await app.render_analysis(ctx, score_id, annotations, measure_range=measure_range, view=view)
        for score_id, student in [('MISSING', None), ('REAL', None), ('REAL', 'I V I')]:
            result = await app.draft_analysis(ctx, score_id=score_id, measure_range=private,
                                              student_analysis=student)
            assert result.is_error
        day = app.datetime.now(app.timezone.utc).strftime('%Y-%m-%d')
        app.store.put(f'usage/{day}.json', json.dumps(app.DAILY_LIMITS).encode())
        for tool in (app.render_analysis, app.draft_analysis):
            kwargs = {'annotations': empty, 'view': private} if tool == app.render_analysis else {}
            result = await tool(ctx, score_id='REAL', measure_range=private, **kwargs)
            assert result.is_error

    asyncio.run(calls())
    captured = capsys.readouterr().out
    payloads = [json.loads(line) for line in captured.splitlines()]
    fields = [payload for payload in payloads if 'measure_range' in payload or 'view' in payload]
    assert len(fields) == 9
    assert private not in captured
    assert [payload['measure_range'] for payload in fields] == [
        'invalid', 'invalid', '1-2', '1-2', 'invalid', 'invalid', 'invalid', 'invalid', 'invalid',
    ]
    assert all(payload['view'] == 'invalid' for payload in fields if 'view' in payload)
    assert [payload['event'] for payload in fields] == [
        'render_analysis', 'render_analysis', 'render_analysis', 'render_analysis',
        'draft_analysis', 'draft_analysis', 'draft_analysis', 'limit', 'limit',
    ]
    assert fields[2]['problems'] and fields[6]['clarification']


def test_cached_drafts_are_reported_without_charging_limit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    score = (ROOT / 'tests/data/part_writing_motion.musicxml').read_bytes()
    app.store.put('scores/REAL', score)
    app.store.put('scores/FRESH', score)
    ctx = SimpleNamespace(headers={'user-agent': 'OpenAI'})

    async def calls():
        first = await app.draft_analysis(ctx, score_id='REAL', measure_range='1-2')
        assert not first.is_error
        day = app.datetime.now(app.timezone.utc).strftime('%Y-%m-%d')
        usage = f'usage/{day}.json'
        capped = json.dumps({'draft': app.DAILY_LIMITS['draft']}).encode()
        app.store.put(usage, capped)
        cached = await app.draft_analysis(ctx, score_id='REAL', measure_range='1-2')
        assert not cached.is_error and cached.content == first.content
        refused = await app.draft_analysis(ctx, score_id='FRESH', measure_range='1-2')
        assert refused.is_error
        assert app.store.get(usage) == capped

    asyncio.run(calls())
    captured = capsys.readouterr().out
    payloads = [json.loads(line) for line in captured.splitlines()]
    (tmp_path / 'drafts.jsonl').write_text(captured)
    assert [payload['cached'] for payload in payloads if payload['event'] == 'draft_analysis'] == [False, True]
    ran = run_report(stdin=captured)
    assert ran.returncode == 0, ran.stderr
    assert 'drafts 2  fresh drafts 1  cached drafts 1' in ran.stdout
    assert 'limits 1  errors 0' in ran.stdout
    assert 'unknown draft cache 0' in ran.stdout


def test_no_tool_input_reaches_the_log(tmp_path, monkeypatch, capsys):
    # Error messages quote their input; any free text the model passes must stay out of the log on every path.
    monkeypatch.setattr(app, 'store', app.LocalStore(tmp_path))
    app.store.put('scores/REAL', (ROOT / 'tests/data/part_writing_motion.musicxml').read_bytes())
    ctx = SimpleNamespace(headers={'user-agent': 'Claude'})
    marker = 'ANNA SECRET'
    labelled = AnnotationList.model_validate({'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': marker},
    ]})

    async def calls():
        for score_id in (marker, 'REAL'):
            await app.render_analysis(ctx, score_id, labelled, measure_range=marker, view=marker)
            await app.draft_analysis(ctx, score_id=score_id, measure_range=marker, student_analysis=marker)
            await app.correct_bars(ctx, score_id=score_id, replacement_bars=f'm1 {marker}4', part=marker)
            await app.correct_bars(ctx, score_id=score_id, replacement_bars=f'm1 {marker}4')
        await app.draft_from_notes(ctx, notes=marker)
        await app.draft_from_notes(ctx, notes=f'{marker}\nC4 E4 G4', student_analysis=marker)

    asyncio.run(calls())
    captured = capsys.readouterr().out
    assert captured.count('\n') >= 10
    assert marker not in captured
