import collections, io, zipfile
import xml.etree.ElementTree as ET

KINDS = ("tuplet_notes", "ornaments", "grace", "octave_lines", "clef_changes")
ORNAMENTS = ("turn", "delayed-turn", "inverted-turn", "trill-mark", "mordent", "inverted-mordent")


def read_xml(data: bytes) -> bytes:
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return z.read(name)
    return data


def per_bar(data: bytes) -> list[collections.Counter]:
    root = ET.fromstring(read_xml(data))
    parts = [list(p.iter("measure")) for p in root.iter("part")]
    bars = [collections.Counter() for _ in range(max((len(p) for p in parts), default=0))]
    for measures in parts:
        clef = {}
        for k, m in enumerate(measures):
            c = bars[k]
            for cl in m.findall("attributes/clef"):
                key = cl.get("number", "1")
                sign = (cl.findtext("sign"), cl.findtext("line"), cl.findtext("clef-octave-change"))
                if key in clef and clef[key] != sign:
                    c["clef_changes"] += 1
                clef[key] = sign
            for n in m.iter("note"):
                if n.find("grace") is not None:
                    c["grace"] += 1
                if n.find("time-modification") is not None and n.find("rest") is None:
                    c["tuplet_notes"] += 1
            for tag in ORNAMENTS:
                c["ornaments"] += len(list(m.iter(tag)))
            for o in m.iter("octave-shift"):
                if o.get("type") in ("up", "down"):
                    c["octave_lines"] += 1
    return bars


def totals(data: bytes) -> dict:
    t = collections.Counter()
    for b in per_bar(data):
        t.update(b)
    return {k: t[k] for k in KINDS}
