import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList


@pytest.mark.parametrize('style,expected', [('abrsm', 'b'), ('figured_bass', '♮3')])
def test_real_analysis_uses_notation_style(chopin, chopin_annotations, style, expected):
    data = chopin_annotations.model_dump()
    data['style'] = style
    annotations = AnnotationList.model_validate(data)
    svg = render(chopin, annotations, measures=(1, 8)).svgs[0]
    assert f'>{expected}<' in svg
    assert '>PAC<' in svg and '>4–3<' in svg


@pytest.mark.parametrize('label,letter,target', [
    ('V7', '', ''), ('V7/vi', '', 'vi'), ('V65/vi', 'b', 'vi'),
    ('V43', 'c', ''), ('V42/V', 'd', 'V'), ('viio65', 'b', ''),
    ('ii/o43/V', 'c', 'V'), ('V65/vi 4–3', 'b', 'vi'),
])
def test_abrsm_sevenths_are_consistently_raised(chopin, label, letter, target):
    annotations = AnnotationList.model_validate({'style': 'abrsm', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': label},
    ]})
    svg = render(chopin, annotations, measures=(1, 1)).svgs[0]
    nodes = list(ET.fromstring(svg).iter('{http://www.w3.org/2000/svg}text'))
    seventh = next(node for node in nodes if ''.join(node.itertext()) == '7')
    root = next(node for node in nodes if ''.join(node.itertext()) == label.split('o')[0].split('/')[0].rstrip('764532'))
    assert float(seventh.get('y')) < float(root.get('y'))
    assert float(seventh.get('font-size').removesuffix('px')) == round(
        float(root.get('font-size').removesuffix('px')) * 0.58)
    if letter:
        inversion = next(node for node in nodes if ''.join(node.itertext()) == letter)
        assert inversion.get('y') == root.get('y')
        assert inversion.get('font-size') == root.get('font-size')
        assert float(inversion.get('x')) > float(seventh.get('x'))
    if target:
        slash = next(node for node in nodes if ''.join(node.itertext()) == '/')
        assert slash.get('y') == root.get('y')
        assert float(slash.get('x')) > float(seventh.get('x'))
        assert any(''.join(node.itertext()) == target for node in nodes)
    if ' ' in label:
        assert any(''.join(node.itertext()) == '4–3' for node in nodes)


def test_current_style_is_byte_identical(chopin, chopin_annotations):
    explicit = AnnotationList.model_validate({**chopin_annotations.model_dump(), 'style': 'current'})
    assert render(chopin, explicit, measures=(1, 8)).png(1) == render(chopin, chopin_annotations, measures=(1, 8)).png(1)


def test_figured_bass_reports_missing_key(chopin):
    annotations = AnnotationList.model_validate({'style': 'figured_bass', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'V65'},
    ]})
    with pytest.raises(AnnotationError, match='active key'):
        render(chopin, annotations, measures=(1, 1))


@pytest.mark.parametrize('style', ['current', 'abrsm', 'figured_bass'])
def test_skill_script_style_override(chopin_annotations, tmp_path, style):
    import sys

    annotations = tmp_path / 'annotations.json'
    annotations.write_text(chopin_annotations.model_dump_json())
    command = [sys.executable, 'skill/scripts/render_analysis.py', 'tests/data/chopin_nocturne_op9_no2.mxl',
               str(annotations), '--measures', '1-8', '--out-dir', str(tmp_path), '--style', style]
    result = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(Path.cwd())})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'analysis.png').read_bytes() == render(
        Path(command[2]).read_bytes(), chopin_annotations.model_copy(update={'style': style}), measures=(1, 8)
    ).png(1, width=1600)
    assert (tmp_path / 'analysis.pdf').read_bytes().startswith(b'%PDF')


def test_hidden_key_change_carries_into_figures(chopin):
    annotations = AnnotationList.model_validate({'style': 'figured_bass', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'I', 'key': 'Eb', 'views': ['form']},
        {'type': 'harmony', 'at': {'measure': 2}, 'label': 'V7/ii'},
    ]})
    svg = render(chopin, annotations, measures=(2, 2), view='harmony').svgs[0]
    assert '>♮3<' in svg and '>E♭:<' in svg


@pytest.mark.parametrize('style', ['current', 'abrsm', 'figured_bass'])
def test_real_analysis_has_no_engraving_collisions(chopin, chopin_annotations, style):
    from tools import engraving_check

    engraving_check._layouts.clear()
    page = render(chopin, chopin_annotations.model_copy(update={'style': style}), measures=(1, 8))
    result = engraving_check.collisions(page.page_count)
    assert result['labels'] == 36
    assert result['overlapping'] == result['tight'] == result['music'] == []


def test_three_line_figures_keep_cadences_clear(chopin):
    from tools import engraving_check

    annotations = AnnotationList.model_validate({'style': 'figured_bass', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'bviio7 4–3', 'key': 'C'},
        {'type': 'cadence', 'at': {'measure': 1}, 'label': 'HC'},
        {'type': 'harmony', 'at': {'measure': 2}, 'label': 'Ger65'},
    ]})
    engraving_check._layouts.clear()
    page = render(chopin, annotations, measures=(1, 2))
    strings = [''.join(node.itertext()) for node in ET.fromstring(page.svgs[0]).iter('{http://www.w3.org/2000/svg}text')]
    assert all(line in ''.join(strings) for line in ('♭♭7', '♭5', '♭3', '4–3'))
    result = engraving_check.collisions(page.page_count)
    assert result['overlapping'] == result['tight'] == result['music'] == []


def test_double_accidentals_use_renderable_glyphs(chopin):
    from fontTools.ttLib import TTFont
    from engine import text
    from tools import engraving_check

    annotations = AnnotationList.model_validate({'style': 'figured_bass', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'bviio7', 'key': 'C'},
        {'type': 'cadence', 'at': {'measure': 1}, 'label': 'HC'},
        {'type': 'harmony', 'at': {'measure': 2}, 'label': 'V7', 'key': 'g#'},
    ]})
    engraving_check._layouts.clear()
    page = render(chopin, annotations, measures=(1, 2))
    nodes = list(ET.fromstring(page.svgs[0]).iter('{http://www.w3.org/2000/svg}text'))
    strings = ''.join(''.join(node.itertext()) for node in nodes)
    assert '♭♭7' in strings and '♯♯3' in strings
    for node in nodes:
        family = node.get('font-family')
        if family in (text.MAIN, text.FALLBACK):
            coverage = TTFont(text.FONT_DIR / text.FILES[(family, False)]).getBestCmap()
            assert all(ord(char) in coverage for char in ''.join(node.itertext()))
    assert page.png(1, width=1600).startswith(b'\x89PNG')
    result = engraving_check.collisions(page.page_count)
    assert result['overlapping'] == result['tight'] == result['music'] == []


@pytest.mark.parametrize('key', ['Cb#', 'C#####'])
def test_figured_bass_reports_invalid_key(chopin, key):
    annotations = AnnotationList.model_validate({'style': 'figured_bass', 'annotations': [
        {'type': 'harmony', 'at': {'measure': 1}, 'label': 'V7', 'key': key},
    ]})
    with pytest.raises(AnnotationError, match='Invalid active key'):
        render(chopin, annotations, measures=(1, 1))


def test_skill_script_reports_invalid_figured_bass_key(tmp_path):
    import sys

    annotations = tmp_path / 'annotations.json'
    annotations.write_text('{"style":"figured_bass","annotations":['
                           '{"type":"harmony","at":{"measure":1},"label":"V7","key":"Cb#"}]}')
    result = subprocess.run(
        [sys.executable, 'skill/scripts/render_analysis.py', 'tests/data/chopin_nocturne_op9_no2.mxl',
         str(annotations), '--measures', '1', '--out-dir', str(tmp_path / 'output')],
        capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(Path.cwd())},
    )
    assert result.returncode == 1
    assert 'Invalid active key' in result.stderr and 'Traceback' not in result.stderr
    assert not (tmp_path / 'output').exists()
