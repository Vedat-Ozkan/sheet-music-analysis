import collections, json, os, re, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import align, bars as raw_bars  # noqa: E402
from engine.read_pdf import clean  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402

SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(p):
    acc = p[1:].rstrip("0123456789")
    return (int(p[1 + len(acc):]) + 1) * 12 + SEMI[p[0]] + acc.count("#") - acc.count("b") + 2 * acc.count("x")


def load(data):
    with tempfile.TemporaryFile() as err:
        saved = os.dup(2)
        os.dup2(err.fileno(), 2)
        try:
            mei = load_toolkit(data).getMEI()
        finally:
            os.dup2(saved, 2)
        err.seek(0)
        msgs = [l for l in err.read().decode(errors="replace").splitlines() if l.startswith(("[Error]", "[Warning]"))]
    index = ScoreIndex(mei)
    out = [collections.Counter((midi(e.pitch), e.onset) for e in m.events if e.pitch) for m in index.measures]
    shifted = sum(1 for n in re.finditer(r"<note\b[^>]*>", mei)
                  if (o := re.search(r'\boct="(\d)"', n.group())) and (g := re.search(r'\boct\.ges="(\d)"', n.group())) and o[1] != g[1])
    return out, shifted, msgs


def overlap(a, b):
    return sum((a & b).values())


def main():
    truth_path, omr_path = sys.argv[1], sys.argv[2]
    omr_data = Path(omr_path).read_bytes()
    if "--clean" in sys.argv:
        omr_data = clean(omr_data)
    truth, t_shift, _ = load(Path(truth_path).read_bytes())
    omr, o_shift, msgs = load(omr_data)
    pairs, shared_pitch = align([(b,) for b in truth], [(b,) for b in omr])
    shared_onset = sum(overlap(truth[i], omr[j]) for i, j in pairs)
    tn, on = sum(sum(b.values()) for b in truth), sum(sum(b.values()) for b in omr)
    raw = sum(sum(b[0].values()) for b in raw_bars(omr_path, {})) if omr_path.endswith((".mxl", ".xml", ".musicxml")) else None
    kinds = collections.Counter(re.sub(r"\b(measure|@xml:id|@startid|@endid|from measure|slur|tie|hairpin)\b.*", "", m).strip() for m in msgs)
    print(json.dumps({"omr": omr_path, "clean": "--clean" in sys.argv, "notes": f"{on}/{tn}", "raw": raw,
                      "pitch": round(shared_pitch / tn, 3), "pitch_onset": round(shared_onset / tn, 3),
                      "octave_display": f"{o_shift}/{t_shift}", "verovio_msgs": dict(kinds.most_common(6))}))


if __name__ == "__main__":
    main()
