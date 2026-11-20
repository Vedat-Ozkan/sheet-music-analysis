import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from engine import annotate, correct, notes, piano, reduce
from engine.annotate import render
from engine.annotations import Alternative, AnnotationList
from engine.check_analysis import ClarificationNeeded, from_musicxml, from_text, student_labels
from engine.check_analysis import as_text as student_check
from engine.export import _document, export_musicxml
from engine.part_writing import applies, as_text, check
from engine.performance import marked_index, perform
from engine.overlay import PageLayout
from engine.read_pdf import problem_spots
from engine.render import Engraving, load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / "data"
SCORES = {
    "pickup-repeat-split": DATA / "part_writing_bwv303.musicxml",
    "key-change-tuplets": DATA / "triplet_brahms_fruhlingstrost.musicxml",
    "compound-6-8-grace": DATA / "export-mozart-k458.musicxml",
    "compound-9-8": DATA / "export-debussy-clair.musicxml",
    "tuplets-6-8": DATA / "triplet_hensel.musicxml",
    "tuplets-4-4": DATA / "triplet_mayer.musicxml",
    "grace-mixed-meter": DATA / "chopin_nocturne_op9_no2.mxl",
    "cross-staff": DATA / "export-brahms-118-2.musicxml",
    "two-parts": DATA / "cadential_64.musicxml",
    "four-parts-pickup": DATA / "part_writing_motion.musicxml",
    "pdf-reading-prelude": DATA / "chopin_prelude_op28_no4_reading.musicxml",
    "pdf-reading-overrun": DATA / "awkward" / "kinkel-op8-5-trennung-reading.musicxml",
    "additive-and-mixed-meters": DATA / "awkward" / "additive-and-mixed-meters.musicxml",
}
KNOWN: dict[tuple[str, str], str] = {
    ("clear_strip", "grace-mixed-meter"): "with every bar marked, the marks of two systems still meet; so they did before the gaps followed the marks",
    ("clear_strip", "key-change-tuplets"): "with every bar marked, the marks of two systems still meet; so they did before the gaps followed the marks",
}
HALF_A_STAFF = 24

score_ids = pytest.mark.parametrize("name", list(SCORES))


def known(request, test, name):
    if reason := KNOWN.get((test, name)):
        request.applymarker(pytest.mark.xfail(reason=reason, strict=False))


def load(name):
    data = SCORES[name].read_bytes()
    return data, ScoreIndex(load_toolkit(data).getMEI())


@score_ids
def test_index_loads(name):
    _, index = load(name)
    assert index.measures


@score_ids
def test_every_bar_has_the_time_signature_the_file_gives_it(name):
    _, index = load(name)
    assert all(measure.meter for measure in index.measures)


def test_additive_and_mixed_time_signatures_are_read_as_their_sum():
    _, index = load("additive-and-mixed-meters")
    eighth = Fraction(1, 2)
    assert [(measure.meter, measure.beat_length, measure.declared_length) for measure in index.measures] == [
        ("5/8", eighth, 5 * eighth), ("5/8", eighth, 5 * eighth), ("7/8", eighth, 7 * eighth), ("7/8", eighth, 7 * eighth),
        ("8/8", eighth, 8 * eighth), ("8/8", eighth, 8 * eighth), ("5/8", eighth, 5 * eighth), ("5/8", eighth, 5 * eighth)]
    assert [measure.number for measure in index.measures] == list(range(1, 9))


def test_numerals_on_late_beats_of_summed_time_signatures_are_read_back_on_those_beats():
    data, index = load("additive-and-mixed-meters")
    placed = [(1, 4.0), (3, 5.0), (5, 7.0), (6, 8.0)]
    analysis = {"annotations": [{"type": "harmony", "at": {"measure": bar, "beat": beat}, "key": "C", "label": "V"} for bar, beat in placed]}
    exported = export_musicxml(data, analysis)
    assert [(label.measure, label.beat) for label in from_musicxml(exported, index=index)] == placed
    assert [(label.measure, label.beat) for label in from_musicxml(exported)] == placed


@score_ids
def test_numerals_written_into_the_score_are_read_back_at_their_bar_and_beat(name):
    data, index = load(name)
    sounding = [[event for event in measure.events if event.pitch and not event.grace] for measure in index.measures[1:4]]
    placed = [(events[0].measure, float(index.measure(events[0].measure).beat_of(min(event.onset for event in events))))
              for events in sounding if events]
    analysis = {"annotations": [{"type": "harmony", "at": {"measure": bar, "beat": beat}, "key": "C", "label": "I"} for bar, beat in placed]}
    exported = export_musicxml(data, analysis)
    assert [(label.measure, label.beat) for label in from_musicxml(exported, index=index)] == placed


@score_ids
def test_problem_spots(name):
    data, _ = load(name)
    bars, _ = problem_spots(_document(data))
    assert all(isinstance(bar, int) for bar in bars)


@score_ids
def test_export_trivial_analysis(request, name):
    known(request, "export", name)
    data, index = load(name)
    first = index.measures[0]
    analysis = {"annotations": [{"type": "harmony", "at": {"measure": first.number, "beat": 1}, "key": "C", "label": "I"}]}
    assert export_musicxml(data, analysis)


@score_ids
def test_part_writing(request, name):
    known(request, "part_writing", name)
    _, index = load(name)
    if applies(index):
        check(index)
        as_text(index)


@score_ids
def test_engrave_a_range(request, name):
    known(request, "engrave", name)
    data, index = load(name)
    numbers = [m.number for m in index.measures if m.number > 0]
    first, last = numbers[0], numbers[min(3, len(numbers) - 1)]
    notes = AnnotationList.model_validate(
        {"annotations": [{"type": "harmony", "at": {"measure": first, "beat": 1}, "key": "C", "label": "I"}]})
    assert render(data, notes, measures=(first, last)).png(1)


@score_ids
def test_correct_roundtrip(request, name):
    known(request, "correct_roundtrip", name)
    data, index = load(name)
    part = ET.fromstring(_document(data)).find("part").get("id")
    flagged = problem_spots(_document(data))[0]
    numbers = [m.number for m in index.measures]
    failures = []
    for bar in dict.fromkeys([numbers[0], numbers[-1], *flagged[:4]]):
        try:
            correct.replace_bars(data, correct.bars_from_musicxml(data, bar, part=part), part=part)
        except Exception as error:
            failures.append(f"bar {bar}: {type(error).__name__}: {error}")
    assert not failures, failures


@score_ids
def test_student_check_finds_the_notes_of_every_beat(name):
    _, index = load(name)
    beats = [(measure.number, beat) for measure in index.measures
             for beat in range(1, int(measure.length / measure.beat_length + Fraction(95, 96)) + 1)]
    labels = from_text(" ".join(f"m{bar} b{beat} I" for bar, beat in beats), index=index)
    rows = [line for line in student_check(labels, index).splitlines() if re.match(r"m\d", line)]
    assert len(rows) == len(labels) == len(set(beats))
    assert all((row.split(" | ")[2] == "rest") == row.endswith("no notes in this beat") for row in rows)


@score_ids
def test_student_check_bass_is_the_lowest_note_sounding_as_the_beat_starts(name):
    _, index = load(name)
    beats = [(measure, beat) for measure in index.measures
             for beat in range(1, int(measure.length / measure.beat_length + Fraction(95, 96)) + 1)]
    labels = from_text(" ".join(f"m{measure.number} b{beat} I" for measure, beat in beats), index=index)
    rows = [line.split(" | ") for line in student_check(labels, index).splitlines() if re.match(r"m\d", line)]
    for (measure, beat), row in zip(beats, rows, strict=True):
        start = (beat - 1) * measure.beat_length
        sounding = [event.pitch for event in measure.events if event.pitch and not event.grace
                    and event.onset <= start < event.onset + event.duration]
        if sounding:
            assert row[2] == min(sounding, key=reduce.midi), (row, sounding)


SIGNATURE_KEYS = {
    "pickup-repeat-split": "D", "key-change-tuplets": "A", "compound-6-8-grace": "Bb", "compound-9-8": "Db",
    "tuplets-6-8": "F", "tuplets-4-4": "Eb", "grace-mixed-meter": "Eb", "cross-staff": "A", "two-parts": "C",
    "four-parts-pickup": "C", "pdf-reading-prelude": "G", "pdf-reading-overrun": "Ab",
    "additive-and-mixed-meters": "C",
}


@score_ids
def test_student_numerals_without_a_key_follow_the_key_signature(name):
    data, index = load(name)
    labels = student_labels(" ".join(f"m{measure.number} I" for measure in index.measures), data, index)
    assert {label.key for label in labels} == {SIGNATURE_KEYS[name]}


def test_student_numerals_without_a_key_follow_a_change_of_key_signature():
    data = (DATA / "ravel-oiseaux-tristes-scan-verovio-crashed-beam-setting0.mxl").read_bytes()
    index = ScoreIndex(load_toolkit(data).getMEI())
    assert [label.key for label in student_labels("m3 I m4 I", data, index)] == ["Bb", "Gb"]


@score_ids
def test_student_numerals_outside_the_score_ask(name):
    data, index = load(name)
    last = index.measures[-1]
    beats = int(last.length / last.beat_length + Fraction(95, 96))
    for text in (f"m{last.number} b{beats + 1} I", f"m{last.number + 1} I", f"m{index.measures[0].number - 1} I"):
        with pytest.raises(ClarificationNeeded):
            student_labels(text, data, index)


@score_ids
def test_student_numerals_without_beats_one_per_beat_or_ask(name):
    data, index = load(name)
    for measure in index.measures:
        beats = int(measure.length / measure.beat_length + Fraction(95, 96))
        bar = f"m{measure.number} "
        if beats >= 2:
            placed = student_labels(bar + " ".join(["I"] * beats), data, index)
            assert [label.beat for label in placed] == list(range(1, beats + 1))
        unclear = [bar + " ".join(["I"] * (beats + 1)), bar + "b2 I V"]
        if beats >= 3:
            unclear.append(bar + " ".join(["I"] * (beats - 1)))
        for text in unclear:
            with pytest.raises(ClarificationNeeded, match="Which beat"):
                student_labels(text, data, index)


@score_ids
def test_note_list_keeps_every_bar_key(name):
    _, index = load(name)
    decoded = notes.decode(notes.encode(index))
    assert [m.key_signature or "0" for m in decoded.measures] == [m.key_signature or "0" for m in index.measures]



@score_ids
def test_piano_reduction(name):
    data, index = load(name)
    numbers = [m.number for m in index.measures]
    assert piano.reduce(data, (numbers[0], numbers[-1]))



@score_ids
def test_notes_table_shows_the_bars_of_the_note_list(name):
    _, index = load(name)
    numbers = [m.number for m in index.measures if m.number > 0]
    first, last = numbers[0], numbers[min(3, len(numbers) - 1)]
    listed = [line.split()[0] for line in notes.encode(index, first, last).splitlines() if line.startswith("m")]
    table = reduce.as_text(index, first, last)
    assert [line.split()[0] for line in table.splitlines() if line.startswith("m")] == listed
    unit = float(index.measure(int(listed[0][1:])).beat_length)
    assert f"one beat = {unit:g} quarter note" in table.splitlines()[0]



@score_ids
def test_played_range_stops_before_the_next_bar(name):
    data, _ = load(name)
    index = marked_index(data)
    numbers = [m.number for m in index.measures]
    for first, last in zip(numbers, numbers[1:-1]):
        played, _, _ = perform(index, (first, last))
        _, _, next_bar = perform(index, (numbers[numbers.index(last) + 1],) * 2)
        if played:
            assert max(note.start for note in played) < next_bar, (first, last)


TYPED = [line for line in (DATA / "awkward" / "typed.txt").read_text().splitlines() if line.strip()]


def test_typed_answers_are_plentiful():
    assert len(TYPED) >= 40


@pytest.mark.parametrize("line", TYPED)
def test_typed_answer_parses_or_asks(line):
    try:
        labels = from_text(line)
    except ClarificationNeeded:
        return
    assert labels and all(re.fullmatch(r"\S+", label.figure) for label in labels)


@score_ids
def test_alternative_bracket_reaches_every_chord_it_replaces(request, name, monkeypatch):
    known(request, "alternative_bracket", name)
    data, index = load(name)
    bars = [measure.number for measure in index.measures if measure.number > 0][:3]
    harmonies = [{"type": "harmony", "at": {"measure": bar, "beat": 1}, "key": "C", "label": "I"} for bar in bars]
    alternative = Alternative.model_validate({"type": "alternative", "start": {"measure": bars[0]}, "end": {"measure": bars[-1], "beat": 1},
                                              "label": " ".join(["V"] * len(bars))})
    drawn = []
    to_svg = PageLayout.to_svg
    monkeypatch.setattr(PageLayout, "to_svg", lambda layout: drawn.append(layout) or to_svg(layout))
    render(data, AnnotationList.model_validate({"annotations": harmonies + [alternative.model_dump()]}), measures=(bars[0], bars[-1]))
    for layout in drawn:
        pieces = {piece.system.index: piece for piece in layout.segments(alternative.start, layout.alternative_end(alternative))}
        for system, centre, *_ in layout.numerals.values():
            assert system in pieces and pieces[system].x0 <= centre <= pieces[system].x1, (name, bars)


@score_ids
def test_one_chord_alternative_is_drawn(name):
    data, index = load(name)
    bars = [measure.number for measure in index.measures if measure.number > 0][:2]
    harmonies = [{"type": "harmony", "at": {"measure": bar, "beat": 1}, "key": "C", "label": "I"} for bar in bars]
    alternative = {"type": "alternative", "start": {"measure": bars[0], "beat": 1}, "end": {"measure": bars[0], "beat": 1}, "label": "V"}
    svg = render(data, AnnotationList.model_validate({"annotations": harmonies + [alternative]}), measures=(bars[0], bars[-1])).svgs[0]
    assert 'stroke-dasharray="1 70"' in svg and ">V<" in svg


@score_ids
@pytest.mark.parametrize("excerpt", [False, True], ids=["whole", "excerpt"])
def test_every_system_holds_the_bars_chosen_for_it(name, excerpt, monkeypatch):
    data, index = load(name)
    numbers = [measure.number for measure in index.measures if measure.number > 0]
    chosen, choose = [], annotate._breaks

    def watched_choice(widths, *args):
        starts = choose(widths, *args)
        chosen.append([end - start for start, end in zip([0, *starts], [*starts, len(widths)])])
        return starts

    monkeypatch.setattr(annotate, "_breaks", watched_choice)
    engraving = render(data, AnnotationList.model_validate({"annotations": []}), measures=(numbers[0], numbers[min(7, len(numbers) - 1)]) if excerpt else None)
    drawn = [len(re.findall(r'class="measure"', system)) for svg in engraving.svgs for system in svg.split('class="system"')[1:]]
    assert not chosen or chosen[0] == drawn, name


@score_ids
def test_marks_of_neighbouring_systems_leave_a_clear_strip_between_them(name, request):
    known(request, "clear_strip", name)
    data, index = load(name)
    bars = [measure for measure in index.measures if measure.number > 0][:16]
    marks = [{"type": "harmony", "at": {"measure": bar.number, "beat": 1}, "label": "V", "function": "D", **({"key": "C"} if not number else {})}
             for number, bar in enumerate(bars)]
    for start in range(0, len(bars), 4):
        phrase = bars[start : start + 4]
        marks += [{"type": "phrase", "start": {"measure": phrase[0].number}, "end": {"measure": phrase[-1].number}, "label": "a"},
                  {"type": "cadence", "at": {"measure": phrase[-1].number, "beat": 1}, "label": "PAC"},
                  {"type": "callout", "at": {"measure": phrase[0].number, "beat": 1}, "number": start // 4 + 1}]
    engraving = render(data, AnnotationList.model_validate({"annotations": marks}), measures=(bars[0].number, bars[-1].number))
    for svg in engraving.svgs:
        page = Engraving([svg])._raster(1, 1400)
        inked = [bool(ImageChops.difference(page.crop((0, row, page.width, row + 1)), Image.new("RGB", (page.width, 1), "#ffffff")).getbbox())
                 for row in range(page.height)]
        first, last = inked.index(True), len(inked) - inked[::-1].index(True)
        strips = [len(run) for run in "".join(" x"[row] for row in inked[first:last]).split("x") if len(run) >= HALF_A_STAFF]
        assert len(strips) >= svg.count('class="system"') - 1, (name, strips, svg.count('class="system"'))


@score_ids
def test_page_key_sits_below_every_mark_of_the_last_system(name):
    data, index = load(name)
    bars = [measure for measure in index.measures if measure.number > 0][:4]
    last = bars[-1]
    lowest = max((event for event in last.events if event.pitch and not event.grace), key=lambda event: (event.staff, -reduce.midi(event.pitch)))
    marks = [{"type": "harmony", "at": {"measure": bar.number, "beat": 1}, "label": label, "function": job, **({"key": "C"} if not number else {})}
             for number, (bar, label, job) in enumerate(zip(bars, ["I", "IV", "V", "I"], ["T", "PD", "D", "T"]))]
    marks += [{"type": "cadence", "at": {"measure": last.number, "beat": 1}, "label": "PAC"},
              {"type": "callout", "at": {"measure": last.number, "beat": 1}, "number": 1},
              {"type": "phrase", "start": {"measure": bars[0].number}, "end": {"measure": last.number}, "label": "a"},
              {"type": "alternative", "start": {"measure": bars[-2].number}, "end": {"measure": last.number, "beat": 1}, "label": "vi V"},
              {"type": "nct", "note": {"measure": last.number, "beat": last.beat_of(lowest.onset), "staff": lowest.staff, "pitch": lowest.pitch},
               "label": "PT"}]
    engraving = render(data, AnnotationList.model_validate({"annotations": marks}), measures=(bars[0].number, last.number), key=True)
    for svg in (engraving.preview.svgs[0], engraving.svgs[-1]):
        root = ET.fromstring(svg)
        for parent in root.iter():
            for group in [child for child in parent if child.get("class") == "page-key"]:
                parent.remove(group)
        keyed, plain = (Engraving([page])._raster(1, 1400) for page in (svg, ET.tostring(root, encoding="unicode")))
        marks_bottom = ImageChops.difference(plain, Image.new("RGB", plain.size, "#ffffff")).getbbox()[3]
        key_box = ImageChops.difference(keyed, plain).getbbox()
        assert key_box and key_box[1] > marks_bottom, (name, key_box, marks_bottom)
