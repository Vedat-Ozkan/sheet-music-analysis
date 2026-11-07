import hashlib
import json
import statistics
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[2]
sys.path[:0] = [str(WORKTREE), str(HERE)]
import engine.read_pdf as reader  # noqa: E402

assert reader.__file__.startswith(str(WORKTREE)), reader.__file__
from barparse import OMR, align_bars, parse, timed  # noqa: E402
from whole_bars import exact, shaded  # noqa: E402

VARIANT, SIGNATURE = "marks1", "speed-marks179d53acf"
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real", "bench-oldly", "bench-olimpic",
        "bench-pitch", "bench-tune2"]
CACHE = OMR / "speed" / "cache"
OUT = CACHE / "wrong_bars" / f"{VARIANT}.jsonl"
MAJOR = {0, 2, 4, 5, 7, 9, 11}


def data_set(set_name: str, engraver: str) -> str:
    if set_name == "bench-real" or engraver.startswith("real-scan"):
        return "real scan"
    if set_name == "bench-olimpic":
        return "olimpic scan"
    return "made scan" if engraver == "scan" else "engraved"


def group_of(piece: str) -> str:
    return piece.rsplit("-", 2)[0] if piece.startswith("olimpic-") else piece.removeprefix("real-")


def marks1_options(setting: int, leland: bool) -> list[str]:
    options = reader.audiveris_options(setting, leland)
    at = options.index("org.audiveris.omr.sheet.ProcessingSwitches.indentations=false")
    return options[:at - 1] + options[at + 1:]


def raw_setting(set_name: str, pdf: bytes, setting: int):
    for leland in (False, True):
        key = hashlib.sha256(pdf + SIGNATURE.encode() + " ".join(marks1_options(setting, leland)).encode()).hexdigest()[:32]
        meta = CACHE / set_name / f"{key}.json"
        if meta.exists() and "skipped" in json.loads(meta.read_text()):
            return parse((meta.with_suffix(".mxl")).read_bytes())
    return None


def staff_lengths(bar) -> dict:
    lengths = {}
    for event in bar.events:
        key = (event.part, event.staff, event.voice)
        lengths[key] = lengths.get(key, 0) + event.dur
    by_staff = {}
    for (part, staff, _), length in lengths.items():
        by_staff[(part, staff)] = max(by_staff.get((part, staff), 0), length)
    return by_staff


def staff_pitch(bar) -> dict:
    notes = {}
    for event in bar.events:
        notes.setdefault((event.part, event.staff), []).extend(event.midis)
    return {staff: statistics.mean(midis) for staff, midis in notes.items() if midis}


def differs_between_settings(read, first, second) -> list[int]:
    if first is None or second is None:
        return [0] * len(read)
    to_first, to_second = dict(align_bars(read, first)), dict(align_bars(read, second))
    return [int(j not in to_first or j not in to_second or timed(first[to_first[j]]) != timed(second[to_second[j]]))
            for j in range(len(read))]


def bar_rows(read, flags, differ, scan, second_available):
    pitch = [staff_pitch(bar) for bar in read]
    medians = {}
    for means in pitch:
        for staff, mean in means.items():
            medians.setdefault(staff, []).append(mean)
    medians = {staff: statistics.median(values) for staff, values in medians.items()}
    shaded_share = len(flags) / max(len(read), 1)
    key, rows = 0, []
    for j, bar in enumerate(read):
        key = next(iter(bar.key.values()), key)
        scale = {(pc + 7 * key) % 12 for pc in MAJOR}
        midis = [m for event in bar.events for m in event.midis]
        notes = [event for event in bar.events if event.midis]
        lengths = staff_lengths(bar)
        fills = [length / bar.full for length in lengths.values()] if bar.full and lengths else [1]
        previous = pitch[j - 1] if j else {}
        durations = [event.dur for event in bar.events if event.dur]
        rows.append({
            "shaded": int(j in flags),
            "near_shaded": int(j - 1 in flags or j + 1 in flags),
            "piece_shaded_share": shaded_share,
            "scan": int(scan),
            "second_reading": int(second_available),
            "settings_differ": differ[j],
            "notes": len(midis),
            "rests": sum(event.rest for event in bar.events),
            "chord_max": max((len(event.midis) for event in notes), default=0),
            "voices": len({(event.part, event.voice) for event in bar.events}),
            "staves": len(lengths),
            "grace": bar.grace,
            "tuplets": sum(event.tuplet for event in bar.events),
            "dotted": sum(event.dots > 0 for event in bar.events),
            "ties": sum(len(event.ties) for event in bar.events),
            "fill_min": float(min(fills)),
            "fill_max": float(max(fills)),
            "no_time": int(bar.full is None),
            "clef_change": int(bool(bar.clef) and j > 0),
            "key_change": int(bool(bar.key) and j > 0),
            "octave_line": int(bool(bar.octave)),
            "out_of_key": sum(m % 12 not in scale for m in midis) / max(len(midis), 1),
            "very_low": sum(m < 36 for m in midis),
            "very_high": sum(m > 88 for m in midis),
            "off_register": float(max((abs(mean - medians[staff]) for staff, mean in pitch[j].items()), default=0)),
            "jump": float(max((abs(mean - previous[staff]) for staff, mean in pitch[j].items() if staff in previous), default=0)),
            "shortest": float(min(durations, default=1)),
            "short_notes": sum(bool(event.dur) and event.dur <= 0.25 for event in bar.events),
            "marks": sum(len(event.marks) for event in bar.events) + bar.fingerings,
            "texts": len(bar.texts),
            "new_system": int(bar.new_system),
            "edge": int(j == 0 or j == len(read) - 1),
        })
    return rows


def pdf_rows(set_name, entry, manifest):
    stem = Path(entry["pdf"]).stem
    reading = CACHE / "runs" / VARIANT / f"{set_name}--{stem}.musicxml"
    if not reading.exists() or not reading.stat().st_size:
        return []
    piece = entry["piece"]
    truth = parse((OMR / set_name / manifest["pieces"][piece]["truth"]).read_bytes())
    data = reading.read_bytes()
    read = parse(data)
    flags = shaded(data)
    pdf = (OMR / set_name / entry["pdf"]).read_bytes()
    first, second = raw_setting(set_name, pdf, 0), raw_setting(set_name, pdf, 1)
    differ = differs_between_settings(read, first, second)
    kind = data_set(set_name, entry["engraver"])
    rows = bar_rows(read, flags, differ, kind.endswith("scan"), second is not None)
    to_truth = {j: i for i, j in align_bars(truth, read)}
    for j, row in enumerate(rows):
        i = to_truth.get(j)
        row.update({
            "set": set_name, "pdf": stem, "piece": piece, "group": group_of(piece), "data_set": kind, "bar": j,
            "paired": int(i is not None),
            "wrong": int(i is None or timed(truth[i]) != timed(read[j])),
            "wrong_exact": int(i is None or not exact(truth[i], read[j], False)),
            "wrong_notes": -1 if i is None else sum(((timed(truth[i]) - timed(read[j])) + (timed(read[j]) - timed(truth[i]))).values()),
            "truth_bars": len(truth), "truth_unpaired": len(truth) - len(to_truth),
        })
    return rows


def main():
    only = set(sys.argv[1:])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = OUT if not only else OUT.with_name(f"{VARIANT}-sample.jsonl")
    with out.open("w") as sink:
        for set_name in SETS:
            manifest = json.loads((OMR / set_name / "manifest.json").read_text())
            for entry in manifest["pdfs"]:
                if only and Path(entry["pdf"]).stem not in only:
                    continue
                try:
                    rows = pdf_rows(set_name, entry, manifest)
                except Exception as error:
                    print("FAILED", set_name, entry["pdf"], repr(error)[:200], flush=True)
                    continue
                for row in rows:
                    sink.write(json.dumps(row) + "\n")
                print(set_name, entry["pdf"], len(rows), sum(r["wrong"] for r in rows), sum(r["shaded"] for r in rows), flush=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
