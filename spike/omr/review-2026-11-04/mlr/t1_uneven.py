import collections, json, sys, pickle
from pathlib import Path
R = Path("/home/kema/projects/sheet-music-plugin")
OMR = R / "spike/omr"
sys.path[:0] = [str(R), str(OMR), str(OMR / "bench")]
from compare import align
from engine_check import load
from engine.read_pdf import problem_spots
from engine.score import ScoreIndex
from engine.render import load_toolkit
from score_one import fill
from features import read_xml

SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real", "bench-tune2", "bench-oldly"]
RUNS = OMR / "speed/cache/runs/pitch39"
OUT = Path(sys.argv[1])

def pitches(bar):
    c = collections.Counter()
    for (p, _), n in bar.items():
        c[p] += n
    return c

rows = []
for name in SETS:
    man = json.loads((OMR / name / "manifest.json").read_text())
    pieces = man["pieces"]
    eng = {Path(p["pdf"]).stem: p["engraver"] for p in man["pdfs"]}
    for reading in sorted(RUNS.glob(f"{name}--*.musicxml")):
        stem = reading.stem.split("--", 1)[1]
        piece = stem.rsplit("--", 1)[0]
        if piece not in pieces:
            continue
        data = reading.read_bytes()
        tdata = read_xml((OMR / name / pieces[piece]["truth"]).read_bytes())
        try:
            truth, _, _ = load(tdata)
            omr, _, _ = load(data)
            tnum = [m.number for m in ScoreIndex(load_toolkit(tdata).getMEI()).measures]
            onum = [m.number for m in ScoreIndex(load_toolkit(data).getMEI()).measures]
            tflag, oflag = set(problem_spots(tdata)[0]), set(problem_spots(data)[0])
        except Exception as e:
            print("ERR", name, stem, e, file=sys.stderr)
            continue
        pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
        paired = dict(pairs)
        back = {j: i for i, j in pairs}
        for i, want in enumerate(truth):
            j = paired.get(i)
            got = omr[j] if j is not None else None
            rows.append(dict(set=name, stem=stem, eng=eng.get(stem, stem.rsplit("--", 1)[1]), i=i, j=j, tn=tnum[i],
                             on=(onum[j] if j is not None else None),
                             tf=tnum[i] in tflag, of=(j is not None and onum[j] in oflag),
                             exact=(got == want) if got is not None else False,
                             pok=(pitches(got) == pitches(want)) if got is not None else False,
                             tnotes=sum(want.values()), onotes=(sum(got.values()) if got is not None else 0)))
        for j in range(len(omr)):
            if j not in back:
                rows.append(dict(set=name, stem=stem, eng=eng.get(stem, ""), i=None, j=j, tn=None, on=onum[j], tf=False,
                                 of=onum[j] in oflag, exact=False, pok=False, tnotes=0, onotes=sum(omr[j].values())))
        rows.append(dict(set=name, stem=stem, summary=True, oflag=len(oflag), tflag=len(tflag), tbars=len(truth), obars=len(omr)))
OUT.write_bytes(pickle.dumps(rows))
print("rows", len(rows))
