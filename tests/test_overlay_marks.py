"""Rings, brackets, lines, key labels, cadence boxes and function brackets as drawn on the page."""

import io
import re

import pytest
from PIL import Image

from engine import overlay
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
        {"type": "voice_leading", "kind": "ring", "from_note": EB4, "label": "range"},
        {"type": "voice_leading", "kind": "line", "from_note": EB4, "to_note": D4},
        {"type": "voice_leading", "kind": "arrow", "from_note": EB4, "to_note": D4, "label": "7th"},
    ]
    analysis = [{"type": "voice_leading", "kind": "arrow", "from_note": EB4, "to_note": D4, "label": "4–3"}]
    red, plain = _page(chopin, fault), _page(chopin, analysis)
    assert _count(red.png(1), RED) > 200 and _count(red.png(1), MAGENTA) < 20
    assert _count(plain.png(1), MAGENTA) > 200 and _count(plain.png(1), RED) < 20
    assert ARROW in plain.svgs[0] and ERROR not in plain.svgs[0]


def test_bracket_and_ring_are_drawn_in_red_pixels(chopin):
    page = _page(chopin, [
        {"type": "voice_leading", "kind": "bracket", "from_note": EB4, "to_note": D4, "label": "spacing"},
        {"type": "voice_leading", "kind": "ring", "from_note": D4, "label": "range"},
    ])
    assert _count(page.png(1), RED) > 300


def test_identical_marks_on_the_same_notes_are_drawn_once(chopin):
    ring = {"type": "voice_leading", "kind": "ring", "from_note": EB4, "label": "range"}
    once = _page(chopin, [ring]).svgs[0]
    twice = _page(chopin, [ring, ring]).svgs[0]
    assert twice.count("<ellipse") == once.count("<ellipse") and twice.count(">range<") == once.count(">range<") == 2  # a halo and the word itself


def test_two_callouts_on_one_note_sit_side_by_side(chopin):
    at = {"measure": 3, "beat": 2}
    svg = _page(chopin, [{"type": "callout", "at": at, "number": 1}, {"type": "callout", "at": at, "number": 2}]).svgs[0]
    centres = sorted(int(float(x)) for x in re.findall(r'<circle[^>]* cx="([-\d.]+)"', svg))
    assert len(centres) == 2 and centres[1] - centres[0] >= 380


def test_parallel_pair_has_one_label_between_its_two_lines(chopin):
    pair = [{"type": "voice_leading", "kind": "line", "from_note": _ref(4, 1.33, 1, "D6"), "to_note": _ref(4, 2.33, 1, "G5")},
            {"type": "voice_leading", "kind": "line", "from_note": _ref(4, 1.33, 2, "F3"), "to_note": _ref(4, 2.33, 2, "F3"), "label": "5–5"}]
    svg = _page(chopin, pair).svgs[0]
    assert svg.count(">5–5<") == 2  # one word: a halo and the word itself
    ys = [float(y) for y in re.findall(r'<line[^>]* y1="([-\d.]+)"', svg)][-2:]
    text_y = float(re.search(r'<text[^>]* y="([-\d.]+)"[^>]*>5–5<', svg).group(1))
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
