from fractions import Fraction
import json
from pathlib import Path
from lxml import etree as E

OUT = Path(__file__).resolve().parent
labels = json.loads((OUT / "labels.json").read_text())
expected = [(a["at"]["measure"], Fraction(str(a["at"]["beat"])), a["label"]) for a in labels]
durations = {"whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
             "eighth": Fraction(1, 2), "16th": Fraction(1, 4)}
results = {}
for variant in ("a-harmony", "b-lyrics"):
    tree = E.parse(str(OUT / (variant + ".mscx")))
    bass = tree.findall(".//Score/Staff")[-1]
    actual = []
    types = []
    for number, measure in enumerate(bass.findall("Measure"), 1):
        for voice in measure.findall("voice"):
            beat = Fraction(1)
            for element in voice:
                if element.tag == "Harmony":
                    actual.append((number, beat, element.findtext("harmonyInfo/name")))
                    types.append(element.findtext("harmonyType"))
                if element.tag in ("Chord", "Rest"):
                    for lyric in element.findall("Lyrics"):
                        actual.append((number, beat, lyric.findtext("text")))
                    duration = durations[element.findtext("durationType")]
                    dots = int(element.findtext("dots", "0"))
                    beat += duration * (2 - Fraction(1, 2 ** dots))
            assert beat == 4, (variant, number, beat)
    assert len(actual) == len(expected) == 21
    assert [(m, b) for m, b, _ in actual] == [(m, b) for m, b, _ in expected]
    mismatches = [dict(measure=m, beat=str(b), expected=e, actual=a)
                  for (m, b, e), (_, _, a) in zip(expected, actual) if e != a]
    if variant == "a-harmony":
        assert set(types) == {"1"}
        assert mismatches == [dict(measure=6, beat="2", expected="ii65", actual="ii76")]
    else:
        assert not mismatches
        assert not tree.findall(".//Harmony")
    results[variant] = dict(labels=21, beat_positions_preserved=21,
                            bass_harmony_types=sorted(set(types)),
                            exact_text=21-len(mismatches), mismatches=mismatches,
                            labels_by_position=[dict(measure=m, beat=str(b), text=t) for m,b,t in actual])
(OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({v: {k:x for k,x in r.items() if k != "labels_by_position"} for v,r in results.items()}, indent=2))
