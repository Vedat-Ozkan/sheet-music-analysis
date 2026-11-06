import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str) -> dict:
    return json.loads((HERE / "results" / f"bench-{name}.json").read_text())


def main():
    base, other = load(sys.argv[1]), load(sys.argv[2])
    for set_name, rows in other["pdfs"].items():
        baseline = {row["pdf"]: row for row in base["pdfs"].get(set_name, [])}
        totals = {"truth": 0, "pitch": [0, 0], "onset": [0, 0], "uneven": [0, 0]}
        changed = []
        for row in rows:
            old = baseline.get(row["pdf"])
            if old is None:
                continue
            a, b = old["score"], row["score"]
            totals["truth"] += a.get("truth_notes", 0)
            for key, field in (("pitch", "shared_pitch"), ("onset", "shared_pitch_onset"), ("uneven", "uneven_bars_omr")):
                totals[key][0] += a.get(field, 0)
                totals[key][1] += b.get(field, 0)
            delta = (b.get("shared_pitch", 0) - a.get("shared_pitch", 0), b.get("shared_pitch_onset", 0) - a.get("shared_pitch_onset", 0),
                     b.get("uneven_bars_omr", 0) - a.get("uneven_bars_omr", 0))
            if any(delta) or row["crashed"] != old["crashed"] or row["pages_skipped"] != old["pages_skipped"]:
                changed.append((row["pdf"].split("/")[-1], a.get("truth_notes"), delta, old["crashed"], row["crashed"]))
        if not totals["truth"]:
            continue
        n = totals["truth"]
        print(f"{set_name}: {len(rows)} PDFs, {n} notes | pitch {totals['pitch'][0] / n:.4f} -> {totals['pitch'][1] / n:.4f}"
              f" | pitch+onset {totals['onset'][0] / n:.4f} -> {totals['onset'][1] / n:.4f}"
              f" | uneven bars {totals['uneven'][0]} -> {totals['uneven'][1]}")
        for name, truth, (pitch, onset, uneven), crashed_before, crashed_after in changed:
            print(f"    {name:52} notes {truth:5}  pitch {pitch:+5}  pitch+onset {onset:+5}  uneven {uneven:+4}"
                  f"{'  crashed ' + str(crashed_before) + '->' + str(crashed_after) if crashed_before != crashed_after else ''}")


if __name__ == "__main__":
    main()
