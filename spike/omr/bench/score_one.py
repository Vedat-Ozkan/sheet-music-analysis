import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from compare import align, bars as xml_bars  # noqa: E402
from engine_check import load, overlap  # noqa: E402
from engine.read_pdf import problem_spots  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402
from features import KINDS, per_bar, read_xml  # noqa: E402


def fill(pairs, nt, no):
    anchors = [(-1, -1)] + list(pairs) + [(nt, no)]
    out = list(pairs)
    for (i1, j1), (i2, j2) in zip(anchors, anchors[1:]):
        if i2 - i1 == j2 - j1:
            out += [(i1 + k, j1 + k) for k in range(1, i2 - i1)]
    return sorted(out)


CLEF_SHIFTS = range(19, 23)


def lengths(data):
    return [m.length for m in ScoreIndex(load_toolkit(data).getMEI()).measures]


def clef_shifted(truth_bar, omr_bar):
    lost, added = truth_bar - omr_bar, omr_bar - truth_bar
    count = 0
    for (pitch, onset), n in lost.items():
        for _ in range(n):
            twin = next(((p, onset) for d in CLEF_SHIFTS for p in (pitch + d, pitch - d) if added[(p, onset)] > 0), None)
            if twin:
                added[twin] -= 1
                count += 1
    return count


def main():
    truth_data = Path(sys.argv[1]).read_bytes()
    truth, _, _ = load(truth_data)
    omr_data = None if sys.argv[2] == "-" else Path(sys.argv[2]).read_bytes()
    omr, msgs = ([], []) if omr_data is None else load(omr_data)[::2]
    pairs, shared_pitch = align([(b,) for b in truth], [(b,) for b in omr])
    shared_onset = sum(overlap(truth[i], omr[j]) for i, j in pairs)
    tn, on = sum(sum(b.values()) for b in truth), sum(sum(b.values()) for b in omr)

    tb, ob = xml_bars(sys.argv[1], {}), (xml_bars(sys.argv[2], {}) if omr_data else [])
    bar_pairs = fill(align([(b[0],) for b in tb], [(b[0],) for b in ob])[0], len(tb), len(ob))
    t_bars, o_bars = per_bar(truth_data), (per_bar(omr_data) if omr_data else [])
    kinds = {}
    aligned_o = {j for _, j in bar_pairs}
    for k in KINDS:
        truth_total = sum(b[k] for b in t_bars)
        found = sum(min(t_bars[i][k], o_bars[j][k]) for i, j in bar_pairs)
        invented = sum(max(0, o_bars[j][k] - t_bars[i][k]) for i, j in bar_pairs)
        invented += sum(o_bars[j][k] for j in range(len(o_bars)) if j not in aligned_o)
        kinds[k] = {"truth": truth_total, "found": found, "invented": invented, "omr_total": sum(b[k] for b in o_bars)}
    index_pairs = fill(pairs, len(truth), len(omr))
    t_len, o_len = lengths(truth_data), (lengths(omr_data) if omr_data else [])
    bar_checks = {
        "missing_bars": len(truth) - len({i for i, _ in index_pairs}),
        "extra_bars": len(omr) - len({j for _, j in index_pairs}),
        "wrong_length_bars": sum(1 for i, j in index_pairs if t_len[i] != o_len[j]),
        "clef_shifted_notes": sum(clef_shifted(truth[i], omr[j]) for i, j in index_pairs),
        "time_signature_missing": int(b"<time" in read_xml(truth_data) and (omr_data is None or b"<time" not in read_xml(omr_data))),
    }
    print(json.dumps({**bar_checks, 
        "truth_notes": tn, "omr_notes": on, "truth_bars": len(truth), "omr_bars": len(omr),
        "xml_bars": [len(t_bars), len(o_bars)], "bars_paired": len(bar_pairs),
        "shared_pitch": shared_pitch, "shared_pitch_onset": shared_onset,
        "uneven_bars_omr": (len(problem_spots(omr_data)[0]) if omr_data else 0), "uneven_bars_truth": len(problem_spots(read_xml(truth_data))[0]),
        "kinds": kinds, "verovio_msgs": len(msgs)}))


if __name__ == "__main__":
    main()
