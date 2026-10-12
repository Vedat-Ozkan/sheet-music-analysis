"""Rings, brackets, lines, key labels, cadence boxes and function brackets as drawn on the page."""

import io
import re
from pathlib import Path

import pytest
from PIL import Image

from engine import overlay, text
from engine.annotate import render
from engine.annotations import AnnotationList
from engine.overlay import ARROW, ERROR, NUMERAL_SIZE, PageLayout

RED, MAGENTA = (0xD5, 0x00, 0x00), (0xAA, 0x33, 0x77)


@pytest.fixture
def layouts(monkeypatch):
    """The PageLayouts that drew the page (the last is the one rasterised)."""
    drawn = []
    original = PageLayout.to_svg

    def spy(self):
        drawn.append(self)
        return original(self)

    monkeypatch.setattr(PageLayout, "to_svg", spy)
    return drawn


def _count(png: bytes, colour: tuple[int, int, int], tolerance: int = 40) -> int:
    pixels = Image.open(io.BytesIO(png)).convert("RGB").getdata()  # noqa
    return sum(1 for p in pixels if all(abs(a - b) <= tolerance for a, b in zip(p, colour)))


def _ref(measure, beat, staff, pitch):
    return {"measure": measure, "beat": beat, "staff": staff, "pitch": pitch}


EB4, D4 = _ref(4, 1.33, 2, "Eb4"), _ref(4, 2.33, 2, "D4")


def _page(chopin, items, **kwargs):
    return render(chopin, AnnotationList.model_validate({"annotations": items}), measures=(1, 8), **kwargs)


def test_fault_marks_are_red_and_analysis_arrows_are_not(chopin):
    fault = [
        {"type": "voice_leading", "kind": "ring", "from_note": EB4, "label": "r"},
        {"type": "voice_leading", "kind": "line", "from_note": EB4, "to_note": D4},
        {"type": "voice_leading", "kind": "arrow", "from_note": EB4, "to_note": D4, "label": "R"},
    ]
    analysis = [{"type": "voice_leading", "kind": "arrow", "from_note": EB4, "to_note": D4, "label": "4–3"}]
    red, plain = _page(chopin, fault), _page(chopin, analysis)
    assert _count(red.png(1), RED) > 200 and _count(red.png(1), MAGENTA) < 20
    assert _count(plain.png(1), MAGENTA) > 200 and _count(plain.png(1), RED) < 20
    assert ARROW in plain.svgs[0] and ERROR not in plain.svgs[0]


def test_bracket_and_ring_are_drawn_in_red_pixels(chopin):
    page = _page(chopin, [
        {"type": "voice_leading", "kind": "bracket", "from_note": EB4, "to_note": D4, "label": "S"},
        {"type": "voice_leading", "kind": "ring", "from_note": D4, "label": "r"},
    ])
    assert _count(page.png(1), RED) > 120  # the codes are one letter, so the ring and bracket carry the pixels


def test_identical_marks_on_the_same_notes_are_drawn_once(chopin):
    ring = {"type": "voice_leading", "kind": "ring", "from_note": EB4, "label": "r"}
    once = _page(chopin, [ring]).svgs[0]
    twice = _page(chopin, [ring, ring]).svgs[0]
    assert twice.count("<ellipse") == once.count("<ellipse") and twice.count(">r<") == once.count(">r<") == 2  # a halo and the word itself


def test_two_callouts_on_one_note_sit_side_by_side(chopin):
    at = {"measure": 3, "beat": 2}
    svg = _page(chopin, [{"type": "callout", "at": at, "number": 1}, {"type": "callout", "at": at, "number": 2}]).svgs[0]
    centres = sorted(int(float(x)) for x in re.findall(r'<circle[^>]* cx="([-\d.]+)"', svg))
    assert len(centres) == 2 and centres[1] - centres[0] >= 380


def test_parallel_pair_has_one_label_between_its_two_lines(chopin):
    pair = [{"type": "voice_leading", "kind": "line", "from_note": _ref(4, 1.33, 1, "D6"), "to_note": _ref(4, 2.33, 1, "G5")},
            {"type": "voice_leading", "kind": "line", "from_note": _ref(4, 1.33, 2, "F3"), "to_note": _ref(4, 2.33, 2, "F3"), "label": "P5"}]
    svg = _page(chopin, pair).svgs[0]
    assert svg.count(">P5<") == 2  # one word: a halo and the word itself
    ys = [float(y) for y in re.findall(r'<line[^>]* y1="([-\d.]+)"', svg)][-2:]
    text_y = float(re.search(r'<text[^>]* y="([-\d.]+)"[^>]*>P5<', svg).group(1))
    assert min(ys) < text_y < max(ys)


def test_nct_names_are_normalised_in_any_case(chopin):
    note = _ref(4, 2.67, 1, "C5")
    for given, shown in (("p", "PT"), ("pt", "PT"), ("PT", "PT"), ("app", "APP"), ("Neighbor", "NT"), ("sus", "SUS")):
        svg = _page(chopin, [{"type": "nct", "note": note, "label": given}]).svgs[0]
        assert f">{shown}<" in svg, given


def test_function_brackets_span_their_run_and_never_mix_words_with_abbreviations(chopin, chopin_annotations, layouts):
    render(chopin, chopin_annotations, measures=(1, 8), view="harmony")
    layout = layouts[-1]
    sequence = layout.numeral_seq
    brackets = [re.findall(r"M(\d+),[\d.]+ L\d+,[\d.]+ L(\d+),", path.get("d")) for path in layout.over.iter(f"{overlay.S}path")
                if path.get("stroke-linejoin") == "round" and path.get("d", "").count("L") == 3]
    spans = [(int(a), int(b)) for found in brackets for a, b in found]
    assert spans
    starts = {round(entry[4]) for entry in sequence}
    nexts = {round(entry[4]) - 60 for entry in sequence} | {round(layout.systems[entry[2]].right - 30) for entry in sequence}
    for x0, x1 in spans:
        assert x0 in starts          # from a numeral's left edge
        assert x1 in nexts           # to just before the next numeral, or the system's end
    function_words = {"tonic", "pre-dom.", "dominant"}
    for system in layout.systems:
        words = [t.text.strip("()") for t in layout.over.iter(f"{overlay.S}text") if t.text and t.text.strip("()") in function_words | {"T", "PD", "D"}
                 and system.bottom() > float(t.get("y")) > layout.numeral_rows[system.index]]
        assert all(w in function_words for w in words) or all(w in {"T", "PD", "D"} for w in words)


def test_no_brackets_without_function(chopin):
    items = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"},
             {"type": "harmony", "at": {"measure": 2, "beat": 1}, "label": "V7"}]
    svg = _page(chopin, items).svgs[0]
    assert "tonic" not in svg and "dominant" not in svg and ">T<" not in svg


def test_cadence_box_hangs_under_the_numeral_in_force(chopin, chopin_annotations, layouts):
    items = [a.model_dump(exclude_none=True) for a in chopin_annotations.annotations if a.type == "harmony"]
    items.append({"type": "cadence", "at": {"measure": 4, "beat": 3}, "label": "PAC"})  # the chord began earlier in the bar
    render(chopin, AnnotationList.model_validate({"annotations": items}), measures=(1, 8))
    layout = layouts[-1]
    rect = next(r for r in layout.over.iter(f"{overlay.S}rect") if r.get("fill") == "#ffffff")
    centre = float(rect.get("x")) + float(rect.get("width")) / 2
    earlier = [e for e in layout.numeral_seq if e[0] <= (layout.index.measure(4).index, 3)][-1]
    assert abs(centre - earlier[3]) < 5 and float(rect.get("y")) > earlier[6]


def test_key_label_sits_just_before_the_first_numeral(chopin, chopin_annotations, layouts):
    render(chopin, chopin_annotations, measures=(1, 8))
    layout = layouts[-1]
    label, box = next(item for item in layout.harmony_labels if item[0].endswith(":"))
    first = layout.numeral_seq[0][4]
    system = layout.systems[layout.numeral_seq[0][2]]
    assert box.x >= system.left + 80 - 1
    assert abs((first - box.right) - 0.4 * NUMERAL_SIZE) < 5 or box.x == pytest.approx(system.left + 80, abs=1)
    assert first - box.right < 6 * NUMERAL_SIZE


def test_phrase_label_is_not_put_on_a_stub(chopin, chopin_annotations):
    svg = render(chopin, chopin_annotations, measures=(1, 8), view="form").svgs[0]
    assert svg.count("ornamented repeat") == 2  # the two systems wide enough to hold it, not the stub at the right edge


def test_fault_arrow_words_are_the_ones_part_writing_emits():
    from engine import part_writing
    from engine.annotations import FAULT_ARROW_LABELS

    assert {part_writing.LABELS[rule] for rule in part_writing.ARROWS} == FAULT_ARROW_LABELS


# ---- part-writing marks on the Bach chorales: marks keep off lyrics and off each other ----

DATA = Path(__file__).parent / "data"


def _chorale(name, marks, measures):
    score = (DATA / f"part_writing_{name}.musicxml").read_bytes()
    return render(score, AnnotationList.model_validate({"annotations": marks}), measures=measures)


def _vl(kind, a, b=None, label=""):
    return {"type": "voice_leading", "kind": kind, "from_note": a, "label": label, **({"to_note": b} if b else {})}


def _word(layout, string):
    """Box of a drawn word (its non-halo copy)."""
    node = [t for t in layout.over.iter(f"{overlay.S}text") if t.text == string][-1]
    width = text.width(string, overlay.LABEL_SIZE)
    y = float(node.get("y"))
    return overlay.Box(float(node.get("x")), y - overlay.LABEL_SIZE * 0.75, width, overlay.LABEL_SIZE)


def test_spacing_bracket_keeps_off_lyrics_and_its_word_off_the_bracket(layouts):
    _chorale("bwv245.14", [_vl("bracket", _ref(9, 3.0, 1, "E5"), _ref(9, 3.0, 2, "C#4"), "S")], (1, 16))
    layout = layouts[-1]
    path = next(p for p in layout.over.iter(f"{overlay.S}path") if p.get("d", "").count("L") == 3)
    x, ys = [float(v) for v in re.findall(r"L([-\d.]+),([-\d.]+)", path.get("d"))[0]][0], [float(v) for _, v in re.findall(r"L([-\d.]+),([-\d.]+)", path.get("d"))[:2]]
    words = [w for system in layout.systems for w in system.words]
    assert not any(w.x < x + 30 and w.right > x - 30 and w.y < max(ys) and w.bottom > min(ys) for w in words)
    word = _word(layout, "S")
    assert not (word.x - 30 < x < word.right + 30 and word.y < max(ys) and word.bottom > min(ys))


def test_overlap_rings_both_notes_with_one_code_and_no_leader(layouts):
    page = _chorale("bwv64.4", [_vl("ring", _ref(14, 4.0, 1, "A4"), label="VO"), _vl("ring", _ref(14, 1.0, 2, "B4"))], (13, 14))
    svg = page.svgs[0]
    assert len(re.findall(r'<ellipse[^>]*stroke="#D50000"', svg)) == 2 and svg.count(">VO<") == 2  # one code: a halo and the code
    assert 'stroke-width="20"' not in svg  # no leader line across the lyrics


def test_codes_of_rings_on_one_chord_sit_together(chopin):
    svg = _page(chopin, [{"type": "voice_leading", "kind": "ring", "from_note": _ref(1, 1.33, 2, "G3"), "label": "VC"},
                         {"type": "voice_leading", "kind": "ring", "from_note": _ref(1, 1.33, 2, "Eb4"), "label": "r"}]).svgs[0]
    assert svg.count(">r VC<") == 2 and ">VC<" not in svg  # one group of codes (a halo and the word), not one per note


def test_direct_octave_word_sits_under_the_lower_voice_when_the_staves_are_apart(layouts):
    _chorale("bwv418", [_vl("line", _ref(0, 1.0, 1, "E4"), _ref(1, 1.0, 1, "A4")),
                        _vl("line", _ref(0, 1.0, 4, "A2"), _ref(1, 1.0, 4, "A3"), "H8")], (0, 1))
    layout = layouts[-1]
    lower = max(float(line.get("y1")) for line in layout.over.iter(f"{overlay.S}line"))
    assert _word(layout, "H8").y > lower - 200


def _functions(chopin, spec):
    items = [{"type": "harmony", "at": {"measure": m, "beat": b}, "label": label, "function": f, **({"key": k} if k else {})}
             for m, b, label, f, k in spec]
    return _page(chopin, items, view="harmony").svgs[0]


def _function_paths(svg):
    return [[tuple(map(float, point)) for point in re.findall(r"([-\d.]+),([-\d.]+)", d)]
            for d in re.findall(r'<path d="(M[\d,. L-]+)"[^>]*stroke-width="26"', svg) if "C" not in d]


def test_function_run_ends_where_the_key_changes(chopin):
    svg = _functions(chopin, [(1, 1, "I", "T", "Eb"), (2, 1, "I", "T", "Bb")])
    assert svg.count(">tonic<") == 2  # one bracket per key, not one run over both


def test_function_bracket_is_open_at_a_system_break_and_names_its_word_without_brackets(chopin):
    svg = _functions(chopin, [(1, 1, "I", "T", "Eb"), (3, 1, "I", "T", None)])  # bars 1-2 and 3-4 are on different systems
    first, second = _function_paths(svg)
    assert first[-1][1] == first[-2][1] and first[0][1] != first[1][1]  # closed at the left, open at the break
    assert second[0][1] == second[1][1] and second[-1][1] != second[-2][1]  # open where it resumes, closed at its end
    assert "(tonic)" not in svg and svg.count(">tonic<") == 2


def test_function_words_are_chosen_for_the_whole_page(chopin):
    # One crowded piece (two chords a beat apart) forces letters everywhere; a long run elsewhere must not keep its word.
    svg = _functions(chopin, [(1, 1, "I", "T", "Eb"), (1, 1.33, "V", "D", None), (3, 1, "I", "T", None), (4, 1, "V", "D", None)])
    assert ">tonic<" not in svg and ">dominant<" not in svg and ">T<" in svg and ">D<" in svg


def test_cadential_six_four_continues_into_the_next_dominant(chopin):
    items = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "Cad64", "key": "Eb"},
             {"type": "harmony", "at": {"measure": 1, "beat": 2}, "label": "V7"},
             {"type": "harmony", "at": {"measure": 2, "beat": 1}, "label": "I"}]
    svg = _page(chopin, items).svgs[0]
    assert svg.count(">V<") == 1 and ">cad.<" not in svg and svg.count(">-<") == 2  # V⁶₄ then dashed ⁷₃; no second V
    other = _page(chopin, [items[0], {**items[2], "at": {"measure": 1, "beat": 2}}]).svgs[0]
    assert other.count(">V<") == 1 and ">-<" not in other  # a following chord that is not V keeps its own numeral


def _unresolved(direction):
    score = (Path(__file__).parent / "data/part_writing_bwv336.musicxml").read_bytes()
    mark = {"type": "voice_leading", "kind": "arrow", "label": "R", "from_note": _ref(2, 3.0, 1, "G#4"),
            "to_note": _ref(2, 4.0, 1, "C#5"), **({"direction": direction} if direction else {})}
    return render(score, AnnotationList.model_validate({"annotations": [mark]}), measures=(1, 3)).svgs[0]


def test_unresolved_tendency_tone_gets_a_small_arrow_beside_it_pointing_where_it_should_go():
    up, down = _unresolved("up"), _unresolved("down")
    for svg, sign in ((up, -1), (down, 1)):
        shaft = re.search(rf'<line x1="(\d+)" y1="(\d+)" x2="(\d+)" y2="(\d+)" stroke="{ERROR}"', svg)
        x1, y1, x2, y2 = map(int, shaft.groups())
        assert x1 == x2 and abs(y2 - y1) < 400  # short and vertical, not a line to the note that follows
        assert (y2 - y1) * sign > 0  # head end is up for "up", down for "down"
    assert ">R<" in up  # the code stays at the tail
