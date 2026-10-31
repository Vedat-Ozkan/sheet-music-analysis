import collections
import gzip
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from engine import tint
from engine.overlay import Box, PageLayout
from engine.performance import marked_index
from engine.read_pdf import PREVIEW_OPTIONS, SETTINGS, clean, is_scan, notice, number_bars, open_pdf, preview, problem_spots, _problem_spots, read_pdf, without_slurs
from engine.render import MAX_PIXELS, engrave, load_toolkit
from engine.score import ScoreIndex
from engine.triplets import infer_triplets
from engine.tuplet_rests import infer_tuplet_rests

AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")


def notes_and_left_hand_chords(score: bytes, first: int, last: int) -> tuple[int, int]:
    index = ScoreIndex(load_toolkit(score).getMEI())
    notes = [e for m in index.measures if first <= m.number <= last for e in m.events if e.pitch and not e.grace]
    onsets = collections.Counter((e.measure, e.onset) for e in notes if e.staff == 2)
    return len(notes), sum(1 for count in onsets.values() if count > 1)


@pytest.mark.skipif(not os.path.exists(AUDIVERIS), reason="Audiveris is not installed; set AUDIVERIS")
def test_reads_an_engraved_pdf_back_into_a_score(chopin):
    engraving = engrave(chopin, (9, 12))
    reading = read_pdf(engraving.pdf(), audiveris=AUDIVERIS)

    assert (reading.pages, reading.scan, reading.skipped) == (1, False, [])
    notes, chords = notes_and_left_hand_chords(chopin, 9, 12)
    read_notes, read_chords = notes_and_left_hand_chords(reading.musicxml, 0, 99)
    assert abs(read_notes - notes) <= notes * 0.05
    assert read_chords >= chords - 2
    assert engrave(reading.musicxml).page_count == 1

    picture = io.BytesIO()
    Image.open(io.BytesIO(engraving.png(1))).convert("RGB").save(picture, "PDF")
    assert is_scan(open_pdf(picture.getvalue()))


@pytest.mark.skipif(not os.path.exists(AUDIVERIS), reason="Audiveris is not installed; set AUDIVERIS")
def test_a_tempo_word_printed_in_the_pdf_reaches_the_playback():
    reading = read_pdf((Path(__file__).parent / "data/chopin-28-4-mutopia.pdf").read_bytes(), audiveris=AUDIVERIS)

    first = marked_index(reading.musicxml).measures[0]
    assert [mark.value for mark in first.marks if mark.kind == "tempo"] == ["largo"]


def test_names_the_bars_a_reading_likely_got_wrong():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))

    assert problem_spots(score) == ([12, 18], False)
    assert b"<slur" not in score
    assert notice(score, False, [], False) == (
        "This is what I read from your PDF; check it against your copy before I analyse it. Bars 12 and 18 (shaded) don't "
        "add up to a full bar, so a note or triplet may be misread there. "
        "Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
    )


def test_names_bars_with_durations_that_disagree_with_written_notes():
    score = (Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt_audiveris.musicxml').read_bytes()
    uneven, meter = problem_spots(score)
    assert {5, 7, 8, 10, 11} <= set(uneven)
    assert meter
    assert 'The shaded bars (1, 2, 3, 4 and 17 more) don' in notice(score, False, [], False)


def test_accepts_the_correct_schubert_with_dots_and_triplets():
    score = clean((Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt.mxl').read_bytes())
    assert problem_spots(score) == ([], False)


@pytest.mark.parametrize('filename', ['haydn_she_never_told_audiveris.musicxml',
                                     'lang_auf_der_reise_audiveris.musicxml'])
def test_names_bars_whose_backup_runs_before_the_start(filename):
    score = (Path(__file__).parent / 'data/pdf_warnings' / filename).read_bytes()
    assert 1 in problem_spots(score)[0]
    assert "(1, " in notice(score, False, [], False)


def test_warning_signals_preserve_haydn_reading_selection():
    folder = Path(__file__).parent / 'data/pdf_warnings'
    variants = [(folder / f'haydn_she_never_told_variant{i}.mxl').read_bytes() for i in range(3)]

    def raw(data, audiveris, options, deadline):
        return variants[SETTINGS.index(options)], []

    reading = read_pdf((folder / 'haydn_she_never_told.pdf').read_bytes(), raw=raw)
    assert reading.musicxml == infer_triplets(clean(variants[1]))
    assert 1 in problem_spots(reading.musicxml)[0]


def test_a_reading_that_dropped_notes_is_not_chosen_for_having_fewer_problem_bars():
    folder = Path(__file__).parent / 'data/pdf_warnings/hensel_vr'
    variants = [gzip.open(folder / f'setting{i}.mxl.gz').read() for i in range(3)]

    def pitched(score):
        return sum(1 for note in ET.fromstring(score).iter('note') if note.find('pitch') is not None)

    def raw(data, audiveris, options, deadline):
        return variants[SETTINGS.index(options)], []

    counts = [pitched(clean(variant)) for variant in variants]
    reading = read_pdf((folder / 'hensel_vr.pdf').read_bytes(), raw=raw)
    assert pitched(reading.musicxml) >= 0.95 * max(counts)


def test_fractional_durations_do_not_backup_before_the_bar():
    score = (Path(__file__).parent / 'data/pdf_warnings/fractional_durations.musicxml').read_bytes()
    assert problem_spots(score) == ([], False)


def test_kinkel_reading_missing_notes_is_not_chosen():
    folder = Path(__file__).parent / 'data/pdf_warnings'
    variants = [(folder / f'kinkel_trennung_variant{i}.mxl').read_bytes() for i in range(3)]

    def raw(data, audiveris, options, deadline):
        return variants[SETTINGS.index(options)], []

    reading = read_pdf((folder / 'kinkel_trennung_scan.pdf').read_bytes(), raw=raw)
    assert reading.musicxml == infer_triplets(infer_tuplet_rests(clean(variants[1])))


def test_preview_shades_the_named_bars_and_does_not_ring_the_double_sharp():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    svg = preview(score).svgs[0]
    assert svg.count('fill="#FFE066" fill-opacity="0.35"') == 2
    assert "#B07800" not in svg
    assert {str(n) for n in range(2, 25)} <= set(re.findall(r'<(?:text|tspan)[^>]*>(\d+)</', svg))


def test_preview_bar_numbers_stay_clear_of_the_music():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    toolkit = load_toolkit(score, PREVIEW_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    layout = PageLayout(toolkit.renderToSVG(1), index)
    before = [list(system.content) for system in layout.systems]
    number_bars(layout, index)
    placed = 0
    for system, old in zip(layout.systems, before):
        for box in system.content[len(old):]:
            placed += 1
            core = Box(box.x + 21, box.y + 21, box.width - 42, box.height - 42)
            assert not any(o.x < core.right and o.right > core.x and o.y < core.bottom and o.bottom > core.y for o in old), core
    assert placed >= 15


def test_preview_bar_numbers_rise_above_the_barline_instead_of_moving_beside_noteheads():
    score = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/mozart_k545_scan_reading.musicxml.gz").read_bytes())
    toolkit = load_toolkit(score, PREVIEW_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    layout = PageLayout(toolkit.renderToSVG(1), index)
    before = [len(system.content) for system in layout.systems]
    number_bars(layout, index)
    starts = [m.x0 for m in layout.measures.values()]
    added = [box for system, n in zip(layout.systems, before) for box in system.content[n:]]
    assert len(added) >= 8
    assert all(min(abs(box.x + 21 - x) for x in starts) <= 100 for box in added)


def test_preview_draws_the_tint_between_the_staff_lines():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    svg = preview(score).svgs[0]
    lines = {float(y) for y in re.findall(r'<path d="M[-\d.]+ ([-\d.]+) L', svg)}
    shaded = re.findall(r'<rect x="[-\d.]+" y="([-\d.]+)" width="[-\d.]+" height="([-\d.]+)" rx="0" fill="#FFE066"', svg)
    assert shaded
    for y, height in shaded:
        assert float(y) in lines and round(float(y) + float(height)) in {round(line) for line in lines}


def test_a_reading_with_no_problems_is_drawn_without_marks_but_with_every_bar_numbered():
    score = clean((Path(__file__).parent / "data/pdf_warnings/schubert_die_stadt.mxl").read_bytes())
    svg = preview(score).svgs[0]
    assert tint.FLAG_BAR not in svg and "bounding-box" not in svg
    assert {str(n) for n in range(2, 9)} <= set(re.findall(r'<(?:text|tspan)[^>]*>(\d+)</', svg))


def zipped(xml: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("score.xml", xml)
    return out.getvalue()


def test_a_reading_without_a_time_signature_is_checked_against_its_most_common_bar_length():
    score = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/mozart_k545_scan_reading.musicxml.gz").read_bytes())
    uneven, guessed = problem_spots(score)
    assert guessed
    assert uneven
    assert _problem_spots(score, timing=False)[0]
    assert ("No time signature was read, so bars were checked against the most common bar length. "
            "The shaded bars") in notice(score, True, [], False)


def test_clean_drops_a_key_that_only_restates_the_current_one():
    reading = (Path(__file__).parent / "data/chopin_prelude_op28_no4_reading.musicxml").read_bytes()
    assert reading.count(b"<key") == 2
    assert clean(zipped(reading)).count(b"<key") == 1


def test_clean_keeps_the_home_key_returning_after_a_single_staff_key():
    raw = (Path(__file__).parent / "data/pdf_warnings/schubert_die_stadt_ly_raw.mxl").read_bytes()
    part = ET.fromstring(clean(raw)).findall("part")[1]
    returns = [m.get("number") for m in part.iter("measure") for k in m.findall("attributes/key")
               if k.get("number") is None and k.findtext("fifths") == "-3"]
    assert returns[:6] == ["0", "4", "17", "19", "21", "23"]


def test_clean_drops_endings_when_the_reading_has_no_repeat():
    reading = (Path(__file__).parent / "data/chopin_prelude_op28_no4_reading.musicxml").read_bytes()
    assert b"<ending" in reading and b"<repeat" not in reading
    assert b"<ending" not in clean(zipped(reading))


def test_clean_keeps_real_endings_where_there_are_repeats():
    reading = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/joplin_maple_leaf_rag_reading.musicxml.gz").read_bytes())
    assert reading.count(b"<ending") == 14
    assert clean(zipped(reading)).count(b"<ending") == 14


def test_preview_bar_numbers_stay_clear_of_the_system_above():
    score = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/joplin_maple_leaf_rag_reading.musicxml.gz").read_bytes())
    toolkit = load_toolkit(without_slurs(score), PREVIEW_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    checked = 0
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(toolkit.renderToSVG(page), index)
        above = [list(system.content) for system in layout.systems]
        before = [len(system.content) for system in layout.systems]
        number_bars(layout, index)
        for system, n in zip(layout.systems[1:], before[1:]):
            for box in system.content[n:]:
                checked += 1
                core = Box(box.x + 21, box.y + 21, box.width - 42, box.height - 42)
                hit = [o for o in above[system.index - 1] if o.x < core.right and o.right > core.x and o.y < core.bottom and o.bottom > core.y]
                assert not hit, (page, core, hit)
    assert checked > 30


def _number_texts(svg: str) -> list[tuple[str, float, float]]:
    return [(n, float(x), float(y)) for x, y, n in re.findall(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*font-size="500px"[^>]*font-style="italic"[^>]*>(\d+)</text>', svg)]


@pytest.mark.parametrize("reading", ["joplin_maple_leaf_rag_reading", "mozart_k545_scan_reading"])
def test_preview_bar_numbers_keep_clear_of_the_top_edge_of_every_page(reading):
    score = without_slurs(gzip.decompress((Path(__file__).parent / f"data/pdf_warnings/{reading}.musicxml.gz").read_bytes()))
    engraving = preview(score)
    assert engraving.page_count > 1
    for page, svg in enumerate(engraving.svgs, 1):
        margin = float(re.search(r'class="page-margin" transform="translate\([-\d.]+, ([-\d.]+)\)"', svg).group(1))
        numbers = _number_texts(svg)
        assert numbers
        highest = min(numbers, key=lambda n: n[2])
        top = margin + highest[2] - 500 * 0.75
        assert top >= 0.025 * 21000, f"page {page}: bar {highest[0]} is {top:.0f} units from the top edge"


def test_preview_bar_numbers_at_an_ending_all_sit_above_its_bracket():
    score = without_slurs(gzip.decompress((Path(__file__).parent / "data/pdf_warnings/joplin_maple_leaf_rag_reading.musicxml.gz").read_bytes()))
    checked = 0
    for svg in preview(score).svgs:
        brackets = []
        for group in re.findall(r'<g class="voltaBracket">(.*?)</g>', svg, re.S):
            points = [(float(x), float(y)) for x, y in re.findall(r'M([-\d.]+) ([-\d.]+) L', group)]
            ends = [float(x) for x in re.findall(r'L([-\d.]+) [-\d.]+', group)]
            brackets.append((min(x for x, _ in points), max(ends), min(y for _, y in points)))
        for number, x, baseline in _number_texts(svg):
            for left, right, line in brackets:
                if left - 100 <= x <= right and abs(baseline - line) < 1200:
                    checked += 1
                    assert baseline < line - 40, f"bar {number} sits under its ending's bracket"
    assert checked >= 4


def test_skill_pages_keep_a_short_last_page_pulled_in_with_the_top_margin():
    import importlib.util

    spec = importlib.util.spec_from_file_location("skill_read_pdf", Path(__file__).parent.parent / "skill/scripts/read_pdf.py")
    skill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skill)
    score = without_slurs(gzip.decompress((Path(__file__).parent / "data/pdf_warnings/lehmann_golden_bridges_reading.musicxml.gz").read_bytes()))
    assert load_toolkit(score, PREVIEW_OPTIONS).getPageCount() == 2
    assert skill.pages(score, problem_spots(score)).page_count == 1


def test_the_every_bar_preview_of_a_long_score_is_one_bounded_image():
    from music21 import corpus
    score = corpus.getWork("beethoven/opus59no1/movement1").read_bytes()
    tall = preview(score, tall=True, spots=([], False))
    assert tall.page_count == 1
    assert tall.svgs[0].count('class="measure"') == len(ScoreIndex(load_toolkit(score).getMEI()).measures) == 400
    image = Image.open(io.BytesIO(tall.png(1, width=2800, colors=256)))
    assert image.width * image.height <= MAX_PIXELS
