import collections
import io
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
OMR = HERE.parent
sys.path[:0] = [str(OMR.parents[1]), str(OMR), str(OMR / "bench")]
from compare import align  # noqa: E402
from engine_check import load  # noqa: E402
from engine.read_pdf import problem_spots  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402
from score_one import fill  # noqa: E402

STEPS = "CDEFGAB"
SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def xml_root(data: bytes):
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(io.BytesIO(data))
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        data = archive.read(name)
    return ET.fromstring(data)


def bars(root):
    out = None
    for part_index, part in enumerate(root.iter("part")):
        divisions, clef, key, shift, octave_change = 1, {}, 0, {}, 0
        measures = []
        for measure in part.iter("measure"):
            cursor, last = Fraction(0), Fraction(0)
            notes, accidentals_in_bar = [], []
            for child in measure:
                if child.tag == "attributes":
                    divisions = int(child.findtext("divisions") or divisions)
                    for k in child.iter("key"):
                        if k.findtext("fifths") is not None:
                            key = int(k.findtext("fifths"))
                    for c in child.iter("clef"):
                        line = int(c.findtext("line") or 0)
                        clef[c.get("number", "1")] = (c.findtext("sign"), line, int(c.findtext("clef-octave-change") or 0))
                elif child.tag == "direction":
                    for o in child.iter("octave-shift"):
                        staff = child.findtext("staff") or "1"
                        if o.get("type") == "stop":
                            shift.pop(staff, None)
                        else:
                            size = int(o.get("size", "8"))
                            steps = 7 if size == 8 else 14
                            shift[staff] = steps if o.get("type") == "down" else -steps
                elif child.tag == "backup":
                    cursor -= Fraction(int(child.findtext("duration")), divisions)
                elif child.tag == "forward":
                    cursor += Fraction(int(child.findtext("duration")), divisions)
                elif child.tag == "note":
                    grace = child.find("grace") is not None
                    duration = Fraction(int(child.findtext("duration") or 0), divisions)
                    start = last if child.find("chord") is not None else cursor
                    if child.find("chord") is None and not grace:
                        last = cursor
                        start = cursor
                        cursor += duration
                    pitch = child.find("pitch")
                    if pitch is None:
                        continue
                    step, octave = pitch.findtext("step"), int(pitch.findtext("octave"))
                    alter = int(float(pitch.findtext("alter") or 0))
                    staff = child.findtext("staff") or "1"
                    notes.append({"start": start, "step": step, "octave": octave, "alter": alter, "grace": grace,
                                  "diatonic": octave * 7 + STEPS.index(step), "midi": (octave + 1) * 12 + SEMI[step] + alter,
                                  "staff": (part_index, staff), "clef": clef.get(staff), "key": key,
                                  "shift": shift.get(staff, 0), "accidental": child.findtext("accidental")})
            measures.append(notes)
        if out is None:
            out = measures
        else:
            for i, notes in enumerate(measures[:len(out)]):
                out[i] = out[i] + notes
    return out or []


def clef_steps(clef):
    if clef is None or clef[0] not in ("G", "F", "C"):
        return None
    sign, line, change = clef
    anchor = {"G": 4 * 7 + 4, "F": 3 * 7 + 3, "C": 4 * 7}[sign]
    return anchor - 2 * (line - 1) + change * 7


def cause(t, r, bar_truth):
    dstep = r["diatonic"] - t["diatonic"]
    if r["midi"] == t["midi"]:
        return None
    if t["grace"] or r["grace"]:
        return "grace note itself"
    if dstep in (7, -7, 14, -14) and (r["midi"] - t["midi"]) % 12 == 0:
        return "octave line" if t["shift"] else "octave (no line in truth)"
    tc, rc = clef_steps(t["clef"]), clef_steps(r["clef"])
    if tc is not None and rc is not None and tc != rc and dstep == rc - tc:
        return "clef"
    if dstep == 0:
        if t["key"] != r["key"]:
            return "key signature"
        graces = [g for g in bar_truth if g["grace"] and g["accidental"] and g["start"] <= t["start"]
                  and g["step"] == t["step"]]
        if graces:
            return "grace-note accidental"
        return "accidental"
    if abs(dstep) <= 2:
        return "step off"
    return "other"


def pair(truth, read):
    t_left = collections.Counter((n["start"], n["midi"]) for n in truth if not n["grace"])
    r_left = collections.Counter((n["start"], n["midi"]) for n in read if not n["grace"])
    common = t_left & r_left
    used_t, used_r = collections.Counter(common), collections.Counter(common)
    ts, rs = [], []
    for n in truth:
        if n["grace"]:
            continue
        key = (n["start"], n["midi"])
        if used_t[key]:
            used_t[key] -= 1
        else:
            ts.append(n)
    for n in read:
        if n["grace"]:
            continue
        key = (n["start"], n["midi"])
        if used_r[key]:
            used_r[key] -= 1
        else:
            rs.append(n)
    t_pitches = collections.Counter(n["midi"] for n in truth if not n["grace"])
    r_pitches = collections.Counter(n["midi"] for n in read if not n["grace"])
    moved_ok = t_pitches & r_pitches
    pairs = []
    for t in sorted(ts, key=lambda n: (n["start"], n["diatonic"])):
        if moved_ok[t["midi"]] > common[(t["start"], t["midi"])] and any(r["midi"] == t["midi"] for r in rs):
            r = next(r for r in rs if r["midi"] == t["midi"])
            rs.remove(r)
            continue
        same = [r for r in rs if r["start"] == t["start"]] or rs
        if not same:
            continue
        r = min(same, key=lambda r: (abs(r["diatonic"] - t["diatonic"]) % 7 != 0, abs(r["diatonic"] - t["diatonic"])))
        rs.remove(r)
        pairs.append((t, r))
    return pairs


def pitches(bar):
    c = collections.Counter()
    for (p, _), n in bar.items():
        c[p] += n
    return c


SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]


def main():
    variant = sys.argv[1]
    sets = sys.argv[2].split(",") if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else SETS
    rows_out = "--rows" in sys.argv
    bar_causes, note_causes = collections.Counter(), collections.Counter()
    pieces = collections.defaultdict(set)
    silent = 0
    for name in sets:
        manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
        for reading in sorted((HERE / "cache" / "runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece, engraver = stem.rsplit("--", 1)
            data = reading.read_bytes()
            tdata = (OMR / name / manifest[piece]["truth"]).read_bytes()
            truth, _, _ = load(tdata)
            omr, _, _ = load(data)
            tb, rb = bars(xml_root(tdata)), bars(xml_root(data))
            if len(tb) != len(truth) or len(rb) != len(omr):
                print("skip (bar count)", name, stem, len(tb), len(truth), len(rb), len(omr), file=sys.stderr)
                continue
            pairs_ = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
            numbers = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
            flagged = set(problem_spots(data)[0])
            paired = dict(pairs_)
            for i, want in enumerate(truth):
                j = paired.get(i)
                if j is None:
                    continue
                got = omr[j]
                if pitches(got) == pitches(want):
                    continue
                if j < len(numbers) and numbers[j] in flagged and "--all" not in sys.argv:
                    continue
                kinds = collections.Counter(c for t, r in pair(tb[i], rb[j]) if (c := cause(t, r, tb[i])))
                if not kinds:
                    continue
                silent += 1
                top = kinds.most_common(1)[0][0]
                bar_causes[top] += 1
                note_causes.update(kinds)
                pieces[top].add(piece)
                if rows_out:
                    print(f"{top}\t{name}\t{stem}\tbar {i + 1}\t{dict(kinds)}")
    print(f"{variant}: silent wrong-pitch bars {silent}")
    for c, n in bar_causes.most_common():
        print(f"  {c:28} bars {n:4}  pieces {len(pieces[c]):3}  notes {note_causes[c]:4}")


if __name__ == "__main__":
    main()
