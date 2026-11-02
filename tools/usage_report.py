from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict

GCLOUD = "gcloud"
PROJECT = "sheet-music-analysis"
BUCKET = "sheet-music-analysis-data"
EVENTS = ("draft_analysis", "draft_from_notes", "render_analysis", "read_pdf", "read_pdf_work", "limit")


def read_logs(days: int) -> list[dict]:
    events = " OR ".join(f'"{e}"' for e in EVENTS)
    query = f'resource.type="cloud_run_revision" AND jsonPayload.event=({events})'
    out = subprocess.run(
        [GCLOUD, "logging", "read", query, f"--project={PROJECT}", f"--freshness={days}d", "--format=json"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def read_active_months(bucket: str) -> dict[str, list[str]]:
    out = subprocess.run(
        [GCLOUD, "storage", "objects", "list", f"gs://{bucket}/users/**", f"--project={PROJECT}", "--format=value(name)"],
        capture_output=True, text=True, check=True,
    ).stdout
    months: dict[str, list[str]] = defaultdict(list)
    for name in out.split():
        _, code, month = name.split("/")
        months[code].append(month)
    return months


def print_monthly_users(bucket: str) -> None:
    months = read_active_months(bucket)
    first_month = {code: min(active) for code, active in months.items()}
    print(f"ChatGPT users since launch: {len(months)}")
    for month in sorted({m for active in months.values() for m in active}):
        active = [code for code, seen in months.items() if month in seen]
        new = sum(first_month[code] == month for code in active)
        print(f"{month}  active {len(active)}  new {new}  returning {len(active) - new}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--bucket", default=BUCKET)
    args = parser.parse_args()

    rows: dict[tuple[str, str], Counter] = defaultdict(Counter)
    ranges: dict[tuple[str, str], Counter] = defaultdict(Counter)
    users: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entry in read_logs(args.days):
        data = entry["jsonPayload"]
        key = (entry["timestamp"][:10], data.get("platform", "?"))
        counts = rows[key]
        if "user" in data:
            users[key].add(data["user"])
        event = data["event"]
        if event == "read_pdf_work":
            if data.get("outcome") == "ok" and not data.get("cached"):
                counts["pdf reads"] += 1
                counts["pdf pages"] += data.get("pages", 0)
        elif event == "limit":
            counts["limits"] += 1
        elif "error" in data or "problems" in data or data.get("outcome") in ("user_error", "server_error", "degraded"):
            counts["errors"] += 1
        elif event == "read_pdf":
            if data.get("reading"):
                counts["pdf still reading"] += 1
            elif data.get("busy"):
                counts["pdf busy"] += 1
            elif data.get("cached"):
                counts["pdf cached"] += 1
            elif "pages" in data:
                counts["pdf reads"] += 1
                counts["pdf pages"] += data["pages"]
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
            f"{key[0]}  {key[1]:8}  users {len(users[key]) if users[key] else '?'}  drafts {counts['drafts']}  renders {counts['renders']}  "
            f"piano {counts['piano renders']}  pdf reads {counts['pdf reads']} ({counts['pdf pages']} pages, "
            f"{counts['pdf cached']} cached, {counts['pdf busy']} busy, {counts['pdf still reading']} still reading)  limits {counts['limits']}  errors {counts['errors']}"
            f"  views [{views}]  ranges [{spans}]"
        )

    print()
    print_monthly_users(args.bucket)


if __name__ == "__main__":
    main()
