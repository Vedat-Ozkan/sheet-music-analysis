import io
import re
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList
from engine.overlay import ARROW, ERROR

GOLDEN = Path(__file__).parent / "golden" / "chopin_m1-8_all.png"


def test_example_renders_on_one_page(chopin, chopin_annotations):
    page = render(chopin, chopin_annotations, measures=(1, 8))
    svg = page.svgs[0]
    assert page.page_count == 1
    assert "bounding-box" not in svg
    assert svg.count(">PAC<") == 2
    assert svg.count("<circle") == 4
    assert svg.count("<ellipse") >= 4


def test_views_show_different_layers(chopin, chopin_annotations):
    harmony = render(chopin, chopin_annotations, measures=(1, 8), view="harmony").svgs[0]
    voices = render(chopin, chopin_annotations, measures=(1, 8), view="voice_leading").svgs[0]
    form = render(chopin, chopin_annotations, measures=(1, 8), view="form").svgs[0]
    assert ">tonic<" in harmony and "fill-opacity" not in harmony and ERROR not in harmony
    assert ARROW in voices and ERROR not in voices and ">tonic<" not in voices and ">PAC<" not in voices
    assert ">PAC<" in form and "ornamented repeat" in form and ">vi<" not in form


def test_all_bad_positions_are_reported_together(chopin):
    annotations = AnnotationList.model_validate(
        {
            "annotations": [
                {"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I"},
                {"type": "harmony", "at": {"measure": 99, "beat": 1}, "label": "V"},
                {"type": "nct", "note": {"measure": 1, "beat": 4, "staff": 2, "pitch": "C2"}, "label": "P"},
            ]
        }
    )
    with pytest.raises(AnnotationError) as error:
        render(chopin, annotations)
    assert len(error.value.problems) == 2
    assert error.value.problems[0].startswith("annotations[1] (harmony): Measure 99 does not exist")
    assert "D2 (staff 2)" in error.value.problems[1]


def test_unknown_fields_are_rejected():
    with pytest.raises(ValueError):
        AnnotationList.model_validate({"annotations": [{"type": "harmony", "at": {"measure": 1}, "label": "I", "x": 3}]})


def test_matches_golden_image(chopin, chopin_annotations):
    png = render(chopin, chopin_annotations, measures=(1, 8)).png(1, width=800)
    if not GOLDEN.exists():
        GOLDEN.write_bytes(png)
        pytest.skip("golden image created")
    actual, expected = (Image.open(source).convert("L") for source in (io.BytesIO(png), GOLDEN))
    assert actual.size == expected.size
    assert ImageStat.Stat(ImageChops.difference(actual, expected)).mean[0] < 1.0


def test_renders_from_a_worker_thread(chopin, chopin_annotations):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(lambda _: render(chopin, chopin_annotations, measures=(1, 8)).page_count, range(2)))
    assert pages == [1, 1]


def test_chord_symbols_and_regions_for_music_roman_numerals_do_not_fit(chopin):
    annotations = AnnotationList.model_validate(
        {
            "annotations": [
                {"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "Ebmaj7"},
                {"type": "harmony", "at": {"measure": 2, "beat": 1}, "label": "C7(#11)/E"},
                {"type": "region", "start": {"measure": 1, "beat": 1}, "end": {"measure": 2}, "label": "pedal on Eb"},
            ]
        }
    )
    svg = render(chopin, annotations, measures=(1, 2)).svgs[0]
    assert ">Ebmaj7<" in svg and ">C7(#11)<" in svg and ">E<" in svg
    assert "stroke-dasharray" in svg and ">pedal on Eb<" in svg
    assert ">tonic<" not in svg and ">dominant<" not in svg


def test_alternative_reading_is_a_dotted_bracket_under_the_numerals(chopin, chopin_annotations):
    alternative = {"type": "alternative", "start": {"measure": 6, "beat": 1}, "end": {"measure": 6}, "label": "c: V7 i", "callout": 5}
    annotations = AnnotationList.model_validate(
        {"annotations": chopin_annotations.model_dump(exclude_none=True)["annotations"] + [alternative]})
    page = render(chopin, annotations, measures=(1, 8))
    assert page.page_count == 1
    assert ">c:<" in page.svgs[0] and 'stroke-dasharray="1 70"' in page.svgs[0]
    assert ">c:<" not in render(chopin, annotations, measures=(1, 8), view="form").svgs[0]


def test_shipped_examples_still_validate():
    for path in [Path("examples/chopin_op9_no2_m1-8.json"), *Path("examples/engraving").glob("*.json")]:
        AnnotationList.model_validate_json(path.read_text())


def test_piano_reduction_keeps_the_marked_notes():
    from tools.robustness import CORPUS

    score = (CORPUS / "mozart/k458/movement1.mxl").read_bytes()
    annotations = AnnotationList.model_validate_json(Path("examples/engraving/mozart-k458.json").read_text())
    engraving = render(score, annotations, measures=(0, 8), piano=True)
    assert engraving.page_count == 1
    assert set(re.findall(r'class="staff" data-n="(\d+)"', engraving.svgs[0])) == {"1", "2"}


def test_alternative_with_the_wrong_number_of_chords_is_sent_back(chopin, chopin_annotations):
    alternative = {"type": "alternative", "start": {"measure": 6, "beat": 1}, "end": {"measure": 6}, "label": "c: V7 i iv"}
    annotations = AnnotationList.model_validate(
        {"annotations": chopin_annotations.model_dump(exclude_none=True)["annotations"] + [alternative]})
    with pytest.raises(AnnotationError, match="has 3 chords but those bars have 2"):
        render(chopin, annotations, measures=(1, 8))
