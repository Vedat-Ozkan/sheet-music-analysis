import re
from xml.sax.saxutils import escape

import pytest

from engine.render import _short_name, load_toolkit


def _score(names: list[str], *, directions: tuple[str, ...] = (), group: str = "") -> bytes:
    parts = "".join(f'<score-part id="P{i}"><part-name>{escape(n)}</part-name></score-part>' for i, n in enumerate(names))
    bodies = "".join(
        f'<part id="P{i}"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>'
        f'<clef><sign>G</sign><line>2</line></clef></attributes>'
        + (
            "".join(f"<direction placement=\"below\"><direction-type><words>{d}</words></direction-type></direction>" for d in directions)
            if i == 0
            else ""
        )
        + '<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>'
        for i in range(len(names))
    )
    return f'<?xml version="1.0"?><score-partwise version="3.1"><part-list>{group}{parts}</part-list>{bodies}</score-partwise>'.encode()


def _mei(names: list[str], **kwargs) -> str:
    return load_toolkit(_score(names, **kwargs)).getMEI()


@pytest.mark.parametrize(
    "name,short",
    [
        ("Violin", "Vln."),
        ("Violin 2", "Vln. II"),
        ("1st Violin", "Vln. I"),
        ("Violino I", "Vln. I"),
        ("Violoncello", "Vc."),
        ("Contrabbasso", "D.B."),
        ("Violoncellos", "Vc."),
        ("Contrabasses", "D.B."),
        ("Oboi", "Ob."),
        ("Clarinetto in B", "Cl."),
        ("Horns in F 1 & 2", "Hn. I, II"),
        ("Bass Clarinet", "B. Cl."),
        ("Alto Saxophone", "A. Sax."),
        ("Tenor Trombone", "Trb."),
        ("Soprano", "S."),
        ("T", "T."),
        ("Choir", "Ch."),
        ("VIOLA", "Vla."),
    ],
)
def test_known_part_names_get_the_standard_abbreviation(name, short):
    assert _short_name(name) == short


@pytest.mark.parametrize("name", ["Right hand", "Left hand", "Violn", "Synth Pad", "Cowbell", "Staff 1", ""])
def test_unknown_names_get_no_short_name(name):
    assert _short_name(name) == ""


def test_short_names_reach_the_mei_only_for_known_parts():
    mei = _mei(["Violin 1", "Cowbell"])
    assert re.findall(r"<labelAbbr\b[^>]*>(?:<[^>]+>)*([^<]*)", mei) == ["Vln. I"]


def test_quartet_gets_one_whole_ensemble_bracket():
    mei = _mei(["Violin 1", "Violin 2", "Viola", "Cello"])
    assert len(re.findall(r'<grpSym\b[^>]*symbol="bracket"', mei)) == 1


def test_large_ungrouped_score_gets_no_bracket():
    mei = _mei([f"Part {i}" for i in range(9)])
    assert "<grpSym" not in mei


def test_piano_gets_no_added_bracket():
    mei = _mei(["Piano", "Piano"])
    assert 'symbol="bracket"' not in mei


def test_file_that_defines_a_group_is_untouched():
    group = '<part-group type="start" number="1"><group-symbol>brace</group-symbol></part-group>'
    stop = '<part-group type="stop" number="1"/>'
    names = ["Violin 1", "Violin 2", "Viola", "Cello"]
    parts = "".join(f'<score-part id="P{i}"><part-name>{n}</part-name></score-part>' for i, n in enumerate(names))
    score = _score(names).decode().replace(parts, group + parts + stop).encode()
    mei = load_toolkit(score).getMEI()
    assert 'symbol="brace"' in mei and 'symbol="bracket"' not in mei


@pytest.mark.parametrize("word", ["Ped.", "2. Ped", "Ped. simile", "Pedal", "*"])
def test_pedal_words_and_release_marks_are_removed(word):
    assert word not in re.sub(r"<[^>]+>", "|", _mei(["Violin"], directions=(word,))).split("|")


def test_other_directions_stay():
    mei = _mei(["Violin"], directions=("dolce", "Pedro", "Ped.", "*"))
    text = re.sub(r"<[^>]+>", "|", mei)
    assert "dolce" in text and "Pedro" in text


def test_only_large_scores_hide_resting_staves():
    assert 'optimize="true"' not in _mei(["Violin 1", "Violin 2", "Viola", "Cello"])
    assert 'optimize="true"' in _mei([f"Part {i}" for i in range(9)])
