from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

GCLOUD = "gcloud"
PROJECT = "sheet-music-analysis"
REGION = "us-central1"
FREE_VCPU_SECONDS = 180_000
FREE_GIB_SECONDS = 360_000
PRICE_VCPU_SECOND = 0.000024
PRICE_GIB_SECOND = 0.0000025


def gcloud(*args: str) -> str:
    return subprocess.run([GCLOUD, *args], capture_output=True, text=True, check=True).stdout.strip()


def billable_seconds(start: datetime, end: datetime) -> dict[str, dict[str, float]]:
    query = urllib.parse.urlencode({
        "filter": 'metric.type="run.googleapis.com/container/billable_instance_time"',
        "interval.startTime": start.isoformat().replace("+00:00", "Z"),
        "interval.endTime": end.isoformat().replace("+00:00", "Z"),
        "aggregation.alignmentPeriod": "86400s",
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
        "aggregation.groupByFields": "resource.labels.service_name",
    })
    request = urllib.request.Request(
        f"https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?{query}",
        headers={"Authorization": f"Bearer {gcloud('auth', 'print-access-token')}"},
    )
    days: dict[str, dict[str, float]] = defaultdict(dict)
    for series in json.load(urllib.request.urlopen(request)).get("timeSeries", []):
        service = series["resource"]["labels"].get("service_name") or "jobs"
        for point in series["points"]:
            day = point["interval"]["startTime"][:10]
            days[day][service] = point["value"].get("doubleValue", 0.0)
    return days


def limits(service: str) -> tuple[float, float]:
    found = json.loads(gcloud("run", "services", "describe", service, f"--project={PROJECT}", f"--region={REGION}", "--format=json"))
    resources = found["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    return float(resources["cpu"]), float(resources["memory"].removesuffix("Gi"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = (today - timedelta(days=1)).replace(day=1)
    days = billable_seconds(min(month_start, today - timedelta(days=args.days)), today)
    services = sorted({service for day in days.values() for service in day})
    print("day         " + "  ".join(f"{service:>30}" for service in services))
    for day in sorted(days)[-args.days:]:
        print(f"{day}  " + "  ".join(f"{days[day].get(service, 0):>30.0f}" for service in services))

    cpu, memory = limits("sheet-music-analysis")
    month = sum(seconds for day, row in days.items() if day >= month_start.date().isoformat() for seconds in row.values())
    vcpu_seconds, gib_seconds = month * cpu, month * memory
    over = max(0, vcpu_seconds - FREE_VCPU_SECONDS) * PRICE_VCPU_SECOND + max(0, gib_seconds - FREE_GIB_SECONDS) * PRICE_GIB_SECOND
    print(
        f"\n{month_start:%B} to yesterday: {month:,.0f} instance-seconds at {cpu:g} vCPU and {memory:g} GiB; "
        f"free tier used {vcpu_seconds / FREE_VCPU_SECONDS:.0%} (vCPU) and {gib_seconds / FREE_GIB_SECONDS:.0%} (memory); "
        f"Cloud Run beyond it about US${over:.2f} at list price. Storage and Artifact Registry are not included."
    )


if __name__ == "__main__":
    main()
