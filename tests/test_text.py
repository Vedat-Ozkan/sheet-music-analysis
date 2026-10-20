from engine import text


def test_single_figure_is_raised():
    chunks, _ = text.numeral("V7", 400)
    assert [chunk.text for chunk in chunks] == ["V", "7"]
    assert chunks[1].dy < 0 and chunks[1].size < 400


def test_two_figures_are_stacked_before_the_secondary_numeral():
    chunks, width = text.numeral("V65/ii", 400)
    assert [chunk.text for chunk in chunks] == ["V", "6", "5", "/", "ii"]
    six, five = chunks[1], chunks[2]
    assert six.dx == five.dx and six.dy < five.dy
    assert chunks[4].dx > five.dx and width > chunks[4].dx


def test_quality_and_accidental_symbols():
    assert [chunk.text for chunk in text.numeral("viio7", 400)[0]] == ["vii", "°", "7"]
    assert [chunk.text for chunk in text.numeral("ii/o65", 400)[0]] == ["ii", "ø", "6", "5"]
    assert text.numeral("bII6", 400)[0][0].text == "♭II"


def test_flat_sign_stays_in_the_main_font():
    assert text.runs("E♭: V/♮") == [("E♭: V/♮", text.MAIN)]


def test_cadential_six_four_is_drawn_as_v_with_6_4_stacked():
    for label in ("Cad64", "cad64"):
        chunks, _ = text.numeral(label, 400)
        assert [c.text for c in chunks] == ["V", "6", "4"]


def test_cadential_continuation_is_dashed_figures_with_no_root():
    chunks, _ = text.numeral("~73", 400)
    assert sorted(c.text for c in chunks) == ["-", "-", "3", "7"]
