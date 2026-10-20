from copy import deepcopy
import json
from pathlib import Path
import re
import zipfile

from lxml import etree as E

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
with zipfile.ZipFile(ROOT / "out/engraving/scores/bach-269.mxl") as z:
    score = E.fromstring(z.read("bwv269.xml"))
score.set("version", "4.0")
annotations = json.loads((ROOT / "examples/engraving/bach-269.json").read_text())
labels = [a for a in annotations["annotations"]
          if a["type"] == "harmony" and 1 <= a["at"]["measure"] <= 8]
(OUT / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")

for part in score.findall("part"):
    measures = {m.get("number"): m for m in part.findall("measure")}
    attributes = deepcopy(measures["0"].find("attributes"))
    for child in list(part):
        part.remove(child)
    for number in range(1, 9):
        measure = measures[str(number)]
        if number == 7:
            for note in measures["7a"].findall("note"):
                measure.append(deepcopy(note))
        part.append(measure)
    part[0].insert(0, attributes)
    for element in list(part.iter()):
        if element.tag in {"print", "barline", "harmony"}:
            element.getparent().remove(element)
        else:
            for attr in ("width", "default-x", "default-y", "relative-x", "relative-y"):
                element.attrib.pop(attr, None)
    if part is score.findall("part")[-1]:
        for lyric in list(part.iter("lyric")):
            lyric.getparent().remove(lyric)


def child(parent, tag, value, **attrs):
    node = E.SubElement(parent, tag, attrs)
    node.text = str(value)
    return node


for variant in ("a-harmony", "b-lyrics"):
    result = deepcopy(score)
    bass = result.findall("part")[-1]
    for measure in bass.findall("measure"):
        number = int(measure.get("number"))
        at = {int((a["at"]["beat"] - 1) * 10080): a
              for a in labels if a["at"]["measure"] == number}
        cursor = 0
        found = set()
        for note in list(measure.findall("note")):
            if cursor in at:
                a = at[cursor]
                label = a["label"]
                found.add(cursor)
                if variant == "b-lyrics":
                    lyric = E.SubElement(note, "lyric", number="1", name="analysis", placement="below")
                    child(lyric, "syllabic", "single")
                    child(lyric, "text", label)
                else:
                    roman, quality, figure = re.fullmatch(r"([ivIV]+)(o?)(\d*)", label).groups()
                    degree = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}[roman.lower()]
                    seventh = figure in ("7", "65", "43", "42")
                    kind = ("diminished" if quality else "minor" if roman.islower() else "major")
                    if seventh:
                        kind = "dominant" if roman == "V" else kind + "-seventh"
                    inv = {"": 0, "7": 0, "6": 1, "65": 1, "64": 2, "43": 2, "42": 3}[figure]
                    harmony = E.Element("harmony", placement="below", type="explicit")
                    numeral = E.SubElement(harmony, "numeral")
                    child(numeral, "numeral-root", degree, text=roman)
                    child(numeral, "numeral-alter", 0, **{"print-object": "no"})
                    key = E.SubElement(numeral, "numeral-key", **{"print-object": "no"})
                    child(key, "numeral-fifths", 1)
                    child(key, "numeral-mode", "major")
                    child(harmony, "kind", kind, text=quality + ("7" if seventh else ""))
                    child(harmony, "inversion", inv)
                    measure.insert(measure.index(note), harmony)
            cursor += int(note.findtext("duration", "0"))
        assert set(at) == found, (number, set(at) - found)
        assert cursor == 30240, (number, cursor)
    title = result.find("work/work-title")
    if title is not None:
        title.text = "BWV 269 — eight-bar Roman numeral import: " + variant
    E.ElementTree(result).write(str(OUT / (variant + ".musicxml")), encoding="utf-8", xml_declaration=True, pretty_print=True)


class SchemaResolver(E.Resolver):
    def resolve(self, url, public_id, context):
        if url.endswith(("/xml.xsd", "/xlink.xsd")):
            return self.resolve_filename(str(OUT / url.rsplit("/", 1)[-1]), context)


parser = E.XMLParser(no_network=True)
parser.resolvers.add(SchemaResolver())
schema = E.XMLSchema(E.parse(str(OUT / "musicxml.xsd"), parser))
for variant in ("a-harmony", "b-lyrics"):
    schema.assertValid(E.parse(str(OUT / (variant + ".musicxml"))))
    print(variant, "MusicXML 4.0 XSD VALID", len(labels), "labels; eight 3/4 bars")
