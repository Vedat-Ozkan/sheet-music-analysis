import argparse
import collections
import json
import os
import statistics
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

warnings.filterwarnings("ignore")
from barparse import OMR, SETS, align_bars, parse  # noqa: E402
from whole_bars import HERE, score_pdf  # noqa: E402

from engine import draft, notes  # noqa: E402
from engine.comparison import Timeline, compare, from_draft  # noqa: E402
from engine.render import load_toolkit  # noqa: E402
from engine.score import ScoreIndex  # noqa: E402
from eval.pdf_compare import FOLDER as ENTRY85, lined_up, passages  # noqa: E402

DRAFTS = HERE / "cache" / "drafts"
QUICK = {tuple(line.split()) for line in (HERE / "quick.txt").read_text().splitlines() if line.strip()}
MEASURES = ("full", "key", "root")
REAL_SCANS = {"real-scan-peters", "real-scan-schirmer"}


def kind(set_name, engraver):
    if set_name == "bench-real" or engraver in REAL_SCANS:
        return "real scan"
    return "rendered scan" if engraver == "scan" else "clean"


def index_of(path):
    return ScoreIndex(load_toolkit(path.read_bytes()).getMEI())


def drafted(cache, source):
    index = index_of(source)
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(draft.run_analysisgnn(notes.encode(index).encode(), "notes")))
    return index, draft.build(json.loads(cache.read_text()), index)


def entry85_ids():
    found = {}
    manifest = json.loads((OMR / "bench-real" / "manifest.json").read_text())
    for piece, entry in manifest["pieces"].items():
        found[piece] = entry["source"].split()[3].rstrip(";")
    return found


def jobs(variant, sets, quick):
    work = []
    to85 = entry85_ids()
    for set_name in sets:
        manifest = json.loads((OMR / set_name / "manifest.json").read_text())
        for entry in manifest["pdfs"]:
            stem = Path(entry["pdf"]).stem
            if quick and (set_name, stem) not in QUICK:
                continue
            truth = OMR / set_name / manifest["pieces"][entry["piece"]]["truth"]
            if variant == "truth":
                reading = truth
            elif variant == "entry85":
                if set_name != "bench-real":
                    continue
                reading = ENTRY85 / "real" / f"{to85[entry['piece']]}.musicxml"
            else:
                reading = HERE / "cache" / "runs" / variant / f"{set_name}--{stem}.musicxml"
            bars = passages(to85[entry["piece"]]) if set_name == "bench-real" else None
            work.append(dict(set=set_name, pdf=stem, piece=entry["piece"], kind=kind(set_name, entry["engraver"]),
                             truth=str(truth), reading=str(reading), bars=bars,
                             truth_draft=str(DRAFTS / "truth" / f"{set_name}--{entry['piece']}.json"),
                             reading_draft=str(DRAFTS / "truth" / f"{set_name}--{entry['piece']}.json") if variant == "truth"
                             else str(DRAFTS / variant / f"{set_name}--{stem}.json")))
    return work


def beat_lengths(index):
    found = {}
    for measure in index.measures:
        found.setdefault(measure.number, measure.beat_length)
    return found


def lined_up_in_time(labels, read, truth):
    read_beat, truth_beat = beat_lengths(read), beat_lengths(truth)
    in_quarters = [replace(label, beat=1 + (label.beat - 1) * read_beat[label.measure]) for label in labels]
    return [replace(label, beat=float(1 + (label.beat - 1) / truth_beat[label.measure])) for label in lined_up(in_quarters, read, truth)]


def draft_truth(job):
    try:
        drafted(Path(job["truth_draft"]), Path(job["truth"]))
    except Exception as error:  # noqa: BLE001
        return f"{type(error).__name__}: {error}"


def diagnose(truth, reading):
    tb, ob = parse(truth.read_bytes()), parse(reading.read_bytes())
    pairs = align_bars(tb, ob)
    totals = collections.Counter()
    score_pdf(truth.read_bytes(), reading.read_bytes(), totals)
    staves = lambda bars: len({(e.part, e.staff) for b in bars for e in b.events})
    meters = lambda bars: sorted({str(b.full) for b in bars if b.full is not None})
    return dict(truth_bars=len(tb), read_bars=len(ob), paired=len(pairs),
                exact=totals["exact"] / len(tb) if tb else None,
                pitch=totals["pitch_notes"] / totals["notes"] if totals["notes"] else None,
                timing=totals["timed_notes"] / totals["notes"] if totals["notes"] else None,
                bar_length_wrong=sum(tb[i].full != ob[j].full for i, j in pairs) / max(1, len(pairs)),
                truth_meters=meters(tb), read_meters=meters(ob),
                truth_keys=sorted(set(tb[0].key.values())) if tb else [], read_keys=sorted(set(ob[0].key.values())) if ob else [],
                truth_clefs=sorted(map(str, tb[0].clef.values())) if tb else [], read_clefs=sorted(map(str, ob[0].clef.values())) if ob else [],
                truth_staves=staves(tb), read_staves=staves(ob))


def score_one(job):
    row = {key: job[key] for key in ("set", "pdf", "piece", "kind")}
    truth, reading = Path(job["truth"]), Path(job["reading"])
    try:
        truth_index, truth_draft = drafted(Path(job["truth_draft"]), truth)
        timeline = Timeline(truth_index)
        row["weight"] = float(sum(timeline.starts[last] + timeline.measures[last].length - timeline.starts[first] for first, last in job["bars"])
                              if job["bars"] else timeline.total)
        if not reading.exists() or not reading.stat().st_size:
            row["error"] = "no reading"
            return row
        read_index, read_draft = drafted(Path(job["reading_draft"]), reading)
        reference, labels = from_draft(truth_draft), from_draft(read_draft)
        as_read = compare(reference, labels, truth_index, job["bars"])
        lined = compare(reference, lined_up_in_time(labels, read_index, truth_index), truth_index, job["bars"])
        row.update({f"{measure} as read": as_read[measure] for measure in MEASURES})
        row.update({f"{measure} lined up": lined[measure] for measure in MEASURES})
    except Exception as error:  # noqa: BLE001
        row["error"] = f"{type(error).__name__}: {str(error)[:200]}"
        return row
    try:
        row.update(diagnose(truth, reading))
    except Exception as error:  # noqa: BLE001
        row["diagnose_error"] = f"{type(error).__name__}: {str(error)[:200]}"
    return row


def pooled(rows, column, failed_as_zero):
    used = [(row["weight"], row.get(column) or 0) for row in rows
            if "weight" in row and (row.get(column) is not None or failed_as_zero and "error" in row)]
    return sum(w * v for w, v in used) / sum(w for w, _ in used) if used else None


def spread(rows, column):
    values = sorted(row[column] for row in rows if row.get(column) is not None)
    if not values:
        return ""
    quartiles = statistics.quantiles(values, n=4) if len(values) > 1 else values * 3
    return f"min {values[0]:.2f} q1 {quartiles[0]:.2f} median {quartiles[1]:.2f} q3 {quartiles[2]:.2f} max {values[-1]:.2f}"


def summary(rows):
    groups = {"all": rows} | {name: [row for row in rows if row["kind"] == name] for name in ("clean", "rendered scan", "real scan")}
    lines = []
    for name, group in groups.items():
        if not group:
            continue
        scored = sum(1 for row in group if row.get("full as read") is not None)
        lines.append(f"{name}: {len(group)} PDFs, {scored} scored")
        for column in [f"{m} {how}" for how in ("as read", "lined up") for m in MEASURES]:
            lines.append(f"  {column:16} pooled {pooled(group, column, False):.3f} (failed as 0: {pooled(group, column, True):.3f}) | {spread(group, column)}")
    return lines


def run(variant, sets, quick, processes):
    os.environ.setdefault("OMP_NUM_THREADS", "3")
    work = jobs(variant, sets, quick)
    truths = list({job["truth_draft"]: job for job in work}.values())
    with ProcessPoolExecutor(processes) as pool:
        for job, error in zip(truths, pool.map(draft_truth, truths)):
            if error:
                print("truth draft failed:", job["set"], job["piece"], error)
        rows = list(pool.map(score_one, work))
    for row in sorted(rows, key=lambda row: row.get("full lined up") if row.get("full lined up") is not None else -1):
        if "error" in row:
            print(f"{row['set']:15} {row['pdf']:55} {row['error']}")
        else:
            print(f"{row['set']:15} {row['pdf']:55} full {row['full as read']:.2f}/{row['full lined up']:.2f} key {row['key as read']:.2f}/{row['key lined up']:.2f}"
                  f" | " + (row.get("diagnose_error") or f"exact {row['exact']:.2f} pitch {row['pitch']:.2f} bars {row['read_bars']}/{row['truth_bars']} meters {row['read_meters']}/{row['truth_meters']}"))
    lines = summary(rows)
    print("\n".join(lines))
    out = HERE / "results" / f"analysis-{variant}{'-quick' if quick else ''}.json"
    out.write_text(json.dumps({"variant": variant, "sets": sets, "summary": lines, "rows": rows}, indent=1))
    print("written", out)


def paired(before, after):
    load = lambda name: {(row["set"], row["pdf"]): row for row in json.loads((HERE / "results" / f"analysis-{name}.json").read_text())["rows"]}
    a, b = load(before), load(after)
    both = [(a[k], b[k]) for k in a.keys() & b.keys() if "exact" in a[k] and "exact" in b[k]]
    print(f"{len(both)} PDFs scored under both {before} and {after}")
    for column in ("full as read", "full lined up", "key lined up", "root lined up"):
        weight = sum(x["weight"] for x, _ in both)
        old = sum(x["weight"] * x[column] for x, _ in both) / weight
        new = sum(y["weight"] * y[column] for _, y in both) / weight
        print(f"  {column:14} {old:.3f} -> {new:.3f}")
    print(f"  exact (mean per PDF) {statistics.mean(x['exact'] for x, _ in both):.3f} -> {statistics.mean(y['exact'] for _, y in both):.3f}")
    for name, rows in ((before, [x for x, _ in both]), (after, [y for _, y in both])):
        print(f"  {name}: correlation of exact with full lined up {statistics.correlation([r['exact'] for r in rows], [r['full lined up'] for r in rows]):.2f},"
              f" with full as read {statistics.correlation([r['exact'] for r in rows], [r['full as read'] for r in rows]):.2f}")
    d_exact = [y["exact"] - x["exact"] for x, y in both]
    d_full = [y["full lined up"] - x["full lined up"] for x, y in both]
    print(f"  per PDF change, correlation of exact change with full lined up change {statistics.correlation(d_exact, d_full):.2f}")
    print(f"  PDFs with full lined up up / down / same (0.01): {sum(d > 0.01 for d in d_full)} / {sum(d < -0.01 for d in d_full)} / {sum(abs(d) <= 0.01 for d in d_full)}")
    stable = [(x, y) for x, y in both if x["exact"] >= 0.95 and y["exact"] >= 0.95 and x["read_bars"] == y["read_bars"]]
    if stable:
        gaps = [abs(y["full lined up"] - x["full lined up"]) for x, y in stable]
        print(f"  {len(stable)} PDFs at least 95% exact in both: full lined up moves by median {statistics.median(gaps):.3f}, max {max(gaps):.3f}")


def main():
    parser = argparse.ArgumentParser(description="Agreement of the draft analysis of a PDF reading with the draft of the true score.")
    parser.add_argument("variant", help="a folder in cache/runs, 'truth' (the reference against itself) or 'entry85' (entry 85's readings)")
    parser.add_argument("--set", nargs="*", default=SETS)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--processes", type=int, default=6)
    parser.add_argument("--against", help="compare saved results of this variant with the variant's, PDF by PDF")
    args = parser.parse_args()
    if args.against:
        paired(args.against, args.variant)
    else:
        run(args.variant, args.set, args.quick, min(args.processes, 6))


if __name__ == "__main__":
    main()
