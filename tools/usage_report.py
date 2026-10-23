from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict

GCLOUD = "gcloud"
PROJECT = "sheet-music-analysis"
EVENTS = ("draft_analysis", "draft_from_notes", "render_analysis", "read_pdf", "limit")


def read_logs(days: int) -> list[dict]:
    events = " OR ".join(f'"{e}"' for e in EVENTS)
    query = f'resource.type="cloud_run_revision" AND jsonPayload.event=({events})'
    out = subprocess.run(
        [GCLOUD, "logging", "read", query, f"--project={PROJECT}", f"--freshness={days}d", "--format=json"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    rows: dict[tuple[str, str], Counter] = defaultdict(Counter)
    ranges: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for entry in read_logs(args.days):
        data = entry["jsonPayload"]
        key = (entry["timestamp"][:10], data.get("platform", "?"))
        counts = rows[key]
        event = data["event"]
        if event == "limit":
            counts["limits"] += 1
        elif "error" in data or "problems" in data or data.get("outcome") in ("user_error", "server_error"):
            counts["errors"] += 1
        elif event == "read_pdf":
            if data.get("busy"):
                counts["pdf busy"] += 1
            elif data.get("cached"):
                counts["pdf cached"] += 1
            else:
                counts["pdf reads"] += 1
                counts["pdf pages"] += data.get("pages", 0)
        elif event == "render_analysis":
            counts["piano renders" if data.get("piano") else "renders"] += 1
            if "view" in data:
                counts[f"view {data['view']}"] += 1
            if "measure_range" in data:
                ranges[key][data["measure_range"]] += 1
        else:
            counts["drafts"] += 1
            if "measure_range" in data:
                ranges[key][data["measure_range"]] += 1

    for key in sorted(rows):
        counts = rows[key]
        views = ", ".join(f"{k[5:]} {v}" for k, v in sorted(counts.items()) if k.startswith("view ") and v)
        spans = ", ".join(f"{k} x{v}" for k, v in ranges[key].items())
        print(
            f"{key[0]}  {key[1]:8}  drafts {counts['drafts']}  renders {counts['renders']}  "
            f"piano {counts['piano renders']}  pdf reads {counts['pdf reads']} ({counts['pdf pages']} pages, "
            f"{counts['pdf cached']} cached, {counts['pdf busy']} busy)  limits {counts['limits']}  errors {counts['errors']}"
            f"  views [{views}]  ranges [{spans}]"
        )


if __name__ == "__main__":
    main()
