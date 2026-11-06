import collections
import copy
import json
import sys
import warnings
import xml.etree.ElementTree as ET
from fractions import Fraction as F

warnings.filterwarnings("ignore")
from barparse import OMR, SETS, align_bars, parse, pitches, timed  # noqa: E402
from pitch_causes import HERE  # noqa: E402

sys.path[:0] = [str(OMR.parents[1])]
from engine.read_pdf import problem_spots  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402

LENGTH = {"whole": F(4), "half": F(2), "quarter": F(1), "eighth": F(1, 2), "16th": F(1, 4), "32nd": F(1, 8), "64th": F(1, 16)}
NEAR = 8


def walk(measure, divisions):
    cursor, onset = F(0), F(0)
    items = []
    for element in measure:
        if element.tag == "attributes" and element.findtext("divisions"):
            divisions = int(float(element.findtext("divisions")))
        if element.tag == "backup":
            cursor -= F(element.findtext("duration")) / divisions
        elif element.tag == "forward":
            cursor += F(element.findtext("duration")) / divisions
        elif element.tag == "note":
            grace = element.find("grace") is not None
            if element.find("chord") is None and not grace:
                onset = cursor
                cursor += F(element.findtext("duration") or 0) / divisions
            items.append((onset, element))
        else:
            items.append((cursor, element))
    return items, divisions


def chords(items):
    out, last = [], None
    for onset, e in items:
        if e.tag != "note" or e.find("grace") is not None:
            last = None
            continue
        if e.find("chord") is not None and last is not None:
            last["notes"].append(e)
            continue
        last = {"onset": onset, "notes": [e], "voice": e.findtext("voice", "1"), "x": float(e.get("default-x")) if e.get("default-x") else None,
                "dur": None, "pitched": e.find("pitch") is not None}
        out.append(last)
    return out


def ruler_voices(all_chords, full, divisions_of):
    for key, group in all_chords.items():
        group = sorted(group, key=lambda c: c["onset"])
        if not group or group[0]["onset"] != 0:
            continue
        end, ok = F(0), True
        for c in group:
            e = c["notes"][0]
            d = F(e.findtext("duration") or 0) / divisions_of[key[0]]
            want = LENGTH.get(e.findtext("type"))
            if c["onset"] != end or want is None or e.find("time-modification") is not None \
                    or want * (2 - F(1, 2 ** len(e.findall("dot")))) != d:
                ok = False
                break
            end += d
        if ok and end == full:
            yield key, group


def rewrite(measure, items, moved, divisions):
    keep_first = [e for _, e in items if e.tag in ("print", "attributes") or (e.tag == "barline" and e.get("location") == "left")]
    keep_last = [e for _, e in items if e.tag == "barline" and e.get("location") != "left"]
    groups = collections.defaultdict(list)
    current = None
    directions = []
    for onset, e in items:
        if e.tag == "note":
            if e.find("chord") is None:
                current = id(e)
                groups[e.findtext("voice", "1")].append([moved.get(id(e), onset), [e]])
            elif groups[e.findtext("voice", "1")]:
                groups[e.findtext("voice", "1")][-1][1].append(e)
        elif e.tag == "direction":
            directions.append((onset, e))
    for v in groups.values():
        v.sort(key=lambda g: g[0])
    for voice, seq in groups.items():
        end = F(0)
        for onset, notes in seq:
            if notes[0].find("grace") is None:
                if onset < end:
                    return False
                end = onset + F(notes[0].findtext("duration") or 0) / divisions
    for child in list(measure):
        measure.remove(child)
    for e in keep_first:
        measure.append(e)
    cursor = F(0)
    pending = sorted(directions, key=lambda d: d[0])
    first = True

    def to(t, voice):
        nonlocal cursor
        if t > cursor:
            f = ET.SubElement(measure, "forward")
            ET.SubElement(f, "duration").text = str(int((t - cursor) * divisions))
            ET.SubElement(f, "voice").text = voice
        elif t < cursor:
            b = ET.SubElement(measure, "backup")
            ET.SubElement(b, "duration").text = str(int((cursor - t) * divisions))
        cursor = t

    for voice, seq in groups.items():
        for onset, notes in seq:
            while first and pending and pending[0][0] <= onset:
                t, d = pending.pop(0)
                to(t, voice)
                measure.append(d)
            to(onset, voice)
            for n in notes:
                measure.append(n)
            if notes[0].find("grace") is None:
                cursor += F(notes[0].findtext("duration") or 0) / divisions
        while first and pending:
            t, d = pending.pop(0)
            to(t, voice)
            measure.append(d)
        first = False
    for e in keep_last:
        measure.append(e)
    return True


def retime(data, stats):
    root = ET.fromstring(data)
    measures = ScoreIndex(load_toolkit(data).getMEI()).measures
    number_at = {s.index: m.number for m in measures for s in m.segments}
    flagged = set(problem_spots(data)[0])
    parts = list(root.iter("part"))
    divisions = [1] * len(parts)
    full = [None] * len(parts)
    state = [list(p.iter("measure")) for p in parts]
    for k in range(max((len(s) for s in state), default=0)):
        position = k + 1
        info = {}
        for pi, part_measures in enumerate(state):
            if k >= len(part_measures):
                continue
            m = part_measures[k]
            time = m.find("attributes/time")
            if time is not None and time.findtext("beat-type") and all(c.strip().isdigit() for c in time.findtext("beats", "").split("+")):
                full[pi] = F(sum(int(c) for c in time.findtext("beats").split("+")) * 4, int(time.findtext("beat-type")))
            items, divisions[pi] = walk(m, divisions[pi])
            info[pi] = (m, items)
        if number_at.get(position) not in flagged or not info:
            continue
        all_chords = collections.defaultdict(list)
        for pi, (m, items) in info.items():
            for c in chords(items):
                all_chords[(pi, c["voice"])].append(c)
        bar_full = next((full[p] for p in info if full[p]), None)
        if bar_full is None:
            continue
        best = None
        for key, group in ruler_voices(all_chords, bar_full, {p: divisions[p] for p in info}):
            cols = [(c["x"], c["onset"]) for c in group if c["x"] is not None]
            if not cols:
                continue
            moved, support = {}, 0
            for other, cs in all_chords.items():
                if other == key:
                    continue
                for c in cs:
                    if c["x"] is None or not c["pitched"]:
                        continue
                    x, t = min(cols, key=lambda z: abs(z[0] - c["x"]))
                    if abs(x - c["x"]) <= NEAR:
                        if c["onset"] != t:
                            moved[id(c["notes"][0])] = (other[0], t)
                        else:
                            support += 1
            if moved and (best is None or support > best[1]):
                best = (moved, support)
        if best is None:
            continue
        for pi, (m, items) in info.items():
            local = {i: t for i, (p, t) in best[0].items() if p == pi}
            if local:
                backup = copy.deepcopy(m)
                if rewrite(m, items, local, divisions[pi]):
                    stats["bars"] += 1
    return ET.tostring(root, encoding="unicode").encode()


def main():
    variant = sys.argv[1]
    totals = collections.defaultdict(collections.Counter)
    stats = collections.Counter()
    for name in SETS:
        manifest = json.loads((OMR / name / "manifest.json").read_text())
        for reading in sorted((HERE / "cache" / "runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece = stem.rsplit("--", 1)[0]
            if piece not in manifest["pieces"]:
                continue
            data = reading.read_bytes()
            t = parse((OMR / name / manifest["pieces"][piece]["truth"]).read_bytes())
            o = parse(data)
            try:
                n = parse(retime(data, stats))
            except Exception as error:
                stats["errors"] += 1
                print("ERR", stem, repr(error)[:100], file=sys.stderr)
                continue
            for label, bars in (("before", o), ("after", n)):
                row = totals[name]
                for i, j in align_bars(t, bars):
                    row[label + "_timed"] += sum((timed(t[i]) & timed(bars[j])).values())
                    row[label + "_pitch"] += sum((pitches(t[i]) & pitches(bars[j])).values())
            totals[name]["notes"] += sum(sum(pitches(b).values()) for b in t)
    print(dict(stats))
    for name, r in totals.items():
        print(name, "timing", r["before_timed"], "->", r["after_timed"], f"{100 * (r['after_timed'] - r['before_timed']) / r['notes']:+.2f} pt", "pitch", r["before_pitch"], "->", r["after_pitch"])
    a = sum(r["after_timed"] for r in totals.values()); b = sum(r["before_timed"] for r in totals.values()); n = sum(r["notes"] for r in totals.values())
    print("all", f"{100 * (a - b) / n:+.2f} pt")


if __name__ == "__main__":
    main()
