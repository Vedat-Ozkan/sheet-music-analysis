import pytest

from engine import harmony


def names(chord):
    return sorted(harmony.NAMES[pc] for pc in chord.tones), harmony.NAMES[chord.bass]


@pytest.mark.parametrize(
    "key, label, tones, bass",
    [
        ("C", "V7", ["B", "D", "F", "G"], "G"),
        ("C", "IV7", ["A", "C", "E", "F"], "F"),
        ("C", "iv7", ["Ab", "C", "Eb", "F"], "F"),
        ("Eb", "V65/vi", ["B", "D", "F", "G"], "B"),
        ("c", "viio7", ["Ab", "B", "D", "F"], "B"),
        ("c", "VII", ["Bb", "D", "F"], "Bb"),
        ("F", "#viio7/vi", ["Bb", "Db", "E", "G"], "Db"),
        ("f", "bVI6", ["Ab", "Db", "F"], "F"),
        ("C", "iiø65", ["Ab", "C", "D", "F"], "F"),
        ("C", "ii/o7", ["Ab", "C", "D", "F"], "D"),
        ("C", "Cad64", ["C", "E", "G"], "G"),
        ("c", "Ger65", ["Ab", "C", "Eb", "F#"], "Ab"),
    ],
)
def test_labels_are_read_as_music21_reads_them(key, label, tones, bass):
    assert names(harmony.chord(key, label)) == (tones, bass)


def test_unreadable_labels_give_none():
    assert harmony.chord("C", "Gmaj7") is None
    assert harmony.chord("C", "") is None
