import json
from pathlib import Path

import pytest

from engine import text
from engine.notation import abrsm, current, figured_bass

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads((ROOT / 'tests/data/notation_examples.json').read_text())


@pytest.mark.parametrize('label,key,chunks,letters,lines,bass,accidental,note', EXAMPLES)
def test_example_table(label, key, chunks, letters, lines, bass, accidental, note):
    actual, width = current(label, key, size=240, bold=True)
    assert [c.text for c in actual] == chunks
    assert (actual, width) == text.numeral(label, 240, True)
    assert abrsm(label, key) == letters
    figures = figured_bass(label, key)
    assert (figures.lines, figures.bass, figures.bass_accidental, figures.note) == (lines, bass, accidental, note)
    assert figures.text == '/'.join(lines)


def test_table_covers_every_example_label_and_active_key():
    found = set()
    for path in (ROOT / 'examples').rglob('*.json'):
        active_key = None
        for annotation in json.loads(path.read_text()).get('annotations', []):
            if annotation['type'] == 'harmony':
                active_key = annotation.get('key', active_key)
                found.add((annotation['label'], active_key))
    assert found == {(row[0], row[1]) for row in EXAMPLES}


@pytest.mark.parametrize('label,key,letters,figures,bass,accidental', [
    ('I', 'C', 'I', '', 'C', ''),
    ('I6', 'C', 'Ib', '6', 'E', ''),
    ('I64', 'C', 'Ic', '6/4', 'G', ''),
    ('V7', 'C', 'V7', '7', 'G', ''),
    ('V65', 'C', 'V7b', '6/5', 'B', ''),
    ('V43', 'C', 'V7c', '4/3', 'D', ''),
    ('V42', 'C', 'V7d', '4/2', 'F', ''),
    ('V2', 'C', 'V7d', '4/2', 'F', ''),
    ('V6/5/V', 'C', 'V7b/V', '6/5', 'F#', '♯'),
    ('viio7', 'c', 'vii°7', '7', 'B', '♮'),
    ('vii/o65', 'c', 'viiø7b', '♮6/♮5', 'D', ''),
    ('N6', 'c', '♭IIb', '♭6', 'F', ''),
    ('N', 'c', '♭IIb', '♭6', 'F', ''),
    ('bII6', 'C', '♭IIb', '♭6/♭3', 'F', ''),
    ('It6', 'C', 'It+6', '♯6/3', 'Ab', '♭'),
    ('Fr43', 'C', 'Fr+6', '♯6/4/3', 'Ab', '♭'),
    ('Fr6', 'C', 'Fr+6', '♯6/4/3', 'Ab', '♭'),
    ('Ger65', 'C', 'Ger+6', '♯6/♭5/3', 'Ab', '♭'),
    ('Ger6', 'c', 'Ger+6', '♯6/5/3', 'Ab', ''),
    ('Cad64', 'c', 'Ic', '6/4', 'G', ''),
    ('V7', 'f#', 'V7', '7/♯3', 'C#', ''),
    ('V7', 'b', 'V7', '7/♯3', 'F#', ''),
    ('V7/bII', 'C', 'V7/♭II', '♭7/♭5', 'Ab', '♭'),
    ('V7/#iv', 'C', 'V7/♯iv', '7/♯5/♯3', 'C#', '♯'),
    ('viio7', 'C', 'vii°7', '♭7', 'B', ''),
    ('V7', 'Gb', 'V7', '7', 'Db', ''),
    ('ii%43', 'C', 'iiø7c', '4/3', 'Ab', '♭'),
    ('vii°42/V', 'C', 'vii°7d/V', '4/♯2', 'Eb', '♭'),
    ('V7', 'g#', 'V7', '7/♯♯3', 'D#', ''),
    ('bviio7', 'C', '♭vii°7', '♭♭7/♭5/♭3', 'Bb', '♭'),
])
def test_edge_table(label, key, letters, figures, bass, accidental):
    assert abrsm(label, key) == letters
    result = figured_bass(label, key)
    assert (result.text, result.bass, result.bass_accidental) == (figures, bass, accidental)


@pytest.mark.parametrize('label', ['Gmaj7', 'C7(#11)', 'D9/A', 'V9', 'V99', '', 'garbage', 'V65/nope'])
def test_unsupported_forms(label):
    assert abrsm(label) == label
    assert current(label) == text.numeral(label, 400)
    with pytest.raises(ValueError, match='Unsupported'):
        figured_bass(label, 'C')


@pytest.mark.parametrize('key', ['', None, 'H', 'C major'])
def test_figures_require_active_key(key):
    with pytest.raises(ValueError, match='active key'):
        figured_bass('V7', key)


def test_suffix_and_unicode_and_no_shared_mutable_output():
    assert abrsm('♭II6 4–3') == '♭IIb 4–3'
    first = figured_bass('V7 4–3', 'E♭')
    assert first.note == '4–3' and first.lines == ['7']
    first.lines.append('99')
    assert figured_bass('V7 4–3', 'Eb').lines == ['7']


def test_cautionary_sharp_in_minor_figured_bass():
    result = figured_bass('#viio7', 'c')
    assert (result.bass, result.bass_accidental, result.text) == ('B', '♮', '7')
