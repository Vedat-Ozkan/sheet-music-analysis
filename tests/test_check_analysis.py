import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine import check_analysis as check
from engine.draft import Chord, Draft
from engine.comparison import Label, from_annotations
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare as evaluation

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope='module')
def bach():
    data = (ROOT / 'spike/export/a-harmony.musicxml').read_bytes()
    return ScoreIndex(load_toolkit(data).getMEI())


def test_typed_eight_bars(chopin):
    index = ScoreIndex(load_toolkit(chopin).getMEI())
    reviewed = json.loads((ROOT / 'examples/chopin_op9_no2_m1-8.json').read_text())
    student = check.from_text(
        'key: Eb major; bar 1 I53 beat 2 viio7 beat 3 I6; '
        'bar 2 I beat 3 ii; bar 3 V7 beat 2 V65/vi beat 3 vi beat 4 viio7/V; '
        'bar 4 V7 beat 3 I; bar 5 I; bar 6 I; bar 7 I; bar 8 in Bb: I',
        index=index,
    )
    results = check.compare(student, reviewed, index)
    assert [item['classification'] for item in results[:5]] == [
        'same_chord_different_spelling', 'agrees', 'different_inversion', 'different_chord', 'agrees',
    ]
    assert results[-1]['classification'] == 'different_chord'
    assert not results[0]['is_error']
    assert results[2]['matches']['chord'] and not results[2]['matches']['chord_and_bass']
    assert results[3]['reviewed']['figure'] == 'V7/ii'
    assert {item['at']['measure'] for item in results} == set(range(1, 9))


def test_musicxml_variants(bach):
    reviewed = json.loads((ROOT / 'examples/engraving/bach-269.json').read_text())
    harmony = check.from_musicxml((ROOT / 'spike/export/a-harmony.musicxml').read_bytes(), index=bach)
    lyrics = check.from_musicxml((ROOT / 'spike/export/b-lyrics.musicxml').read_bytes(), index=bach)
    assert harmony == lyrics == [label for label in from_annotations(reviewed) if 1 <= label.measure <= 8]
    assert len(harmony) == 21
    assert Label(3, 2.5, 'G', 'ii7') in harmony
    assert all(item['classification'] == 'agrees' for item in check.compare(harmony, reviewed, bach))
    assert all(item['classification'] == 'agrees' for item in check.compare(lyrics, reviewed, bach))
    metrics = evaluation.compare(harmony, lyrics, bach)
    assert all(metrics[name] == 1 for name in ('key', 'root', 'chord', 'chord_and_bass', 'full'))


def test_chat_grammar():
    assert check.from_text('key: G major; bar 1 I, bar 2 V6 IV, bar 3 beat 3 ii65, bar 5 in D: V7/V') == [
        Label(1, 1, 'G', 'I'), Label(2, 1, 'G', 'V6'), Label(2, 2, 'G', 'IV'),
        Label(3, 3, 'G', 'ii65'), Label(5, 1, 'D', 'V7/V'),
    ]
    assert check.from_text('key: f minor; m.0 Ib, measure 1.2 V7c, b3 vii°7; bar 2 iiø65 V+ V 6') == [
        Label(0, 1, 'f', 'I6'), Label(1, 2, 'f', 'V43'), Label(1, 3, 'f', 'viio7'),
        Label(2, 1, 'f', 'iiø65'), Label(2, 2, 'f', 'V+'), Label(2, 3, 'f', 'V6'),
    ]
    assert check.from_text('m1 C: Vc V42 V65/ii ii/o65 bII6')[0].figure == 'V64'
    assert check.from_text('bar 1 I; bar 2 key: G I') == [Label(1, 1, 'C', 'I'), Label(2, 1, 'G', 'I')]


@pytest.mark.parametrize('text, message', [
    ('I V', 'bar number'), ('bar 1 potato', 'Cannot read Roman numeral'),
    ('bar 1 Igarbage', 'Cannot read Roman numeral'), ('bar 1 VIIX', 'Cannot read Roman numeral'),
    ('bar 1 Id', 'Invalid triad inversion'), ('bar 1 beat 0 I', 'Beat must'),
    ('bar 1 I; bar 1 V', 'Conflicting'), ('key: C', 'No Roman'),
])
def test_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        check.from_text(text)


def test_bad_position(bach):
    with pytest.raises(ValueError, match='does not exist'):
        check.from_text('bar 99 I', index=bach)
    with pytest.raises(ValueError, match='has no beat'):
        check.from_text('bar 1 beat 4 I', index=bach)


def test_reference_sustain_and_key_precedence(bach):
    reviewed = {'annotations': [{'type': 'harmony', 'at': {'measure': 1}, 'key': 'G', 'label': 'I'}]}
    result = check.compare(check.from_text('bar 2 beat 2 I; bar 3 in D: IV', default_key='G'), reviewed, bach)
    assert result[0]['classification'] == 'agrees'
    assert result[1]['classification'] == 'different_key'
    assert result[1]['matches']['chord_and_bass']
    before = check.compare(check.from_text('bar 1 I'), {'annotations': [
        {'type': 'harmony', 'at': {'measure': 2}, 'label': 'I'},
    ]}, bach)
    assert before[0]['classification'] == 'unchecked' and before[0]['reviewed'] is None


def test_xml_timing_and_keys():
    xml = '''<score-partwise xmlns="urn:test"><part id="bass"><measure number="0">
    <attributes><divisions>2</divisions><key><fifths>0</fifths><mode>minor</mode></key>
    <time><beats>6</beats><beat-type>8</beat-type></time><staves>2</staves></attributes>
    <note><duration>3</duration><staff>1</staff><lyric><text>song</text></lyric></note>
    <backup><duration>3</duration></backup>
    <note><duration>3</duration><staff>2</staff><lyric><text>i</text></lyric></note>
    <note><chord/><duration>3</duration><staff>2</staff></note>
    <harmony><numeral><numeral-root text="V">5</numeral-root><numeral-alter>1</numeral-alter>
    <numeral-key><numeral-fifths>2</numeral-fifths><numeral-mode>major</numeral-mode></numeral-key>
    </numeral><kind>dominant</kind><inversion>2</inversion><offset>-1</offset></harmony>
    <forward><duration>1</duration></forward>
    <note><grace/><staff>2</staff><lyric><text>V</text></lyric></note>
    </measure></part></score-partwise>'''
    assert check.from_musicxml(xml) == [
        Label(0, 1, 'a', 'i'), Label(0, 5 / 3, 'D', '#V43'), Label(0, 7 / 3, 'D', 'V'),
    ]


def test_xml_rejects_unknown_kind():
    xml = '''<score-partwise><part><measure number="1"><harmony>
    <numeral><numeral-root>5</numeral-root></numeral><kind>other</kind>
    </harmony></measure></part></score-partwise>'''
    with pytest.raises(ValueError, match='Unsupported MusicXML'):
        check.from_musicxml(xml)


@pytest.mark.parametrize('address', ['beat 3', 'm1 beat 3', 'key: G'])
def test_detached_figure_cannot_cross_address(address):
    with pytest.raises(ValueError, match='Cannot read Roman numeral'):
        check.from_text(f'm1 I {address} 6 V')


@pytest.mark.parametrize('degree,alter,figure', [(7, 0, 'bviio'), (7, 1, 'viio'), (6, 0, 'bvio'), (3, -1, 'biiio')])
def test_xml_minor_numerals_follow_natural_scale(degree, alter, figure):
    xml = f'''<score-partwise><part><measure number="1">
    <attributes><key><fifths>-3</fifths><mode>minor</mode></key></attributes>
    <harmony><numeral><numeral-root>{degree}</numeral-root>
    <numeral-alter>{alter}</numeral-alter></numeral><kind>diminished</kind></harmony>
    </measure></part></score-partwise>'''
    assert check.from_musicxml(xml) == [Label(1, 1, 'c', figure)]


def test_xml_offset_direction_keys_follow_musical_order():
    xml = '''<score-partwise><part><measure number="1">
    <attributes><divisions>1</divisions></attributes>
    <direction placement="below"><direction-type><words>D: I</words></direction-type><offset>2</offset></direction>
    <direction placement="below"><direction-type><words>dolce</words></direction-type></direction>
    <note><duration>4</duration><lyric><text>G: I</text></lyric></note>
    </measure><measure number="2"><note><duration>4</duration><lyric><text>V</text></lyric></note>
    </measure></part></score-partwise>'''
    assert check.from_musicxml(xml) == [
        Label(1, 1, 'G', 'I'), Label(1, 3, 'D', 'I'), Label(2, 1, 'D', 'V'),
    ]


TYPED_INPUTS = json.loads((ROOT / 'tests/data/check_analysis/typed_inputs.json').read_text())


@pytest.mark.parametrize('case', TYPED_INPUTS, ids=lambda case: case['id'])
def test_realistic_typed_inputs(case):
    if 'question' in case:
        with pytest.raises(check.ClarificationNeeded) as error:
            check.from_text(case['text'])
        assert case['question'] in error.value.question
        assert error.value.question.endswith('?')
    else:
        assert check.from_text(case['text']) == [Label(*item) for item in case['expected']]


def test_musescore_mixed_harmonies():
    data = (ROOT / 'tests/data/check_analysis/musescore-mixed.musicxml').read_bytes()
    index = ScoreIndex(load_toolkit(data).getMEI())
    assert check.from_musicxml(data, index=index) == [Label(1, 1, 'G', 'I')]


def test_musescore_native_roman_export():
    data = (ROOT / 'tests/data/check_analysis/musescore-roman.musicxml').read_bytes()
    index = ScoreIndex(load_toolkit(data).getMEI())
    figures = ['I', 'V6', 'ii', 'V', 'vii', 'vii', 'bII6', 'N6', 'I6', 'Ger65', 'Fr43', 'I64']
    labels = check.from_musicxml(data, index=index)
    assert labels == [Label(bar, 1, 'G', figure) for bar, figure in enumerate(figures, 1)]
    native = ET.parse(
        ROOT / 'tests/data/check_analysis/musescore-roman.mscx',
    )
    original = [item.text for item in native.findall('.//harmonyInfo/name')]
    assert [bar for bar, (before, after) in enumerate(zip(original, figures), 1) if before != after] == [3, 4, 5, 6, 9]
    student = check.from_text('; '.join(f'bar {bar} {figure}' for bar, figure in enumerate(original, 1)), default_key='G', index=index)
    reviewed = {'annotations': [{'type': 'harmony', 'at': {'measure': item.measure}, 'key': item.key, 'label': item.figure} for item in student]}
    results = check.compare(labels, reviewed, index)
    assert [item['at']['measure'] for item in results if item['is_error']] == [3, 4, 5, 6, 9]


def test_student_check_marks_labels_with_no_draft_chord_before_them(bach):
    student = check.from_text('key: G major; bar 1 I bar 2 V', index=bach)
    later = Draft('analysisgnn', [Chord(2, 1.0, 'G', 'V', 0.9, 1, 'D')], [], [], [], [])
    text = check.as_text(student, later, bach)
    assert 'm1 b1 | G: I | none |  |  | unchecked' in text
    assert 'm2 b1 | G: V | G: V (0.90) |' in text
    empty = check.as_text(student, Draft('analysisgnn', [], [], [], [], []), bach)
    assert empty.count('| none |  |  | unchecked') == 2
