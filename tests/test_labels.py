from engine import notation, text


def test_special_labels_and_qualities_are_the_ones_docs_labels_md_maps_for_cadence_finder():
    assert set(notation.SPECIAL) == {"N", "N6", "Cad64", "It6", "Fr6", "Fr43", "Ger6", "Ger65"}
    assert set(text.QUALITIES) == {"o", "°", "/o", "ø", "%", "+"}
