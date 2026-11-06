import json
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parent / "bench"))

import run as bench  # noqa: E402
from engine import read_pdf as reader  # noqa: E402

from variants import AUDIVERIS, PRODUCTION_SIGNATURE, SETS  # noqa: E402


def main():
    sig = PRODUCTION_SIGNATURE
    rows = []
    for set_name in SETS:
        folder = HERE.parent / set_name
        manifest = json.loads((folder / "manifest.json").read_text())
        for p in manifest["pdfs"]:
            data = (folder / p["pdf"]).read_bytes()
            calls = []
            cached = bench.cached_raw(folder / "cache" / "raw", sig, threading.Semaphore(1), calls)
            first = cached(data, str(AUDIVERIS), reader.SETTINGS[0], 0, None)
            cached(data, str(AUDIVERIS), reader.SETTINGS[1], 0, None)
            seconds = [call[1] for call in calls]
            uneven = None
            if first.mxl is not None:
                uneven = len(reader._problem_spots(reader.clean(first.mxl), timing=False)[0])
            rows.append({"set": set_name, "pdf": p["pdf"], "pages": p["pages"], "setting0_uneven": uneven,
                         "waits_for_second": uneven is None or uneven > reader.RETRY_ABOVE, "cached_seconds": seconds})
    waits = sum(row["waits_for_second"] for row in rows)
    print(f"{waits} of {len(rows)} PDFs wait for the second setting (setting 0 has more than {reader.RETRY_ABOVE} uneven bars or failed)")
    (HERE / "results" / "second_setting.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
