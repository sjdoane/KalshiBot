"""v27: BTS on-time prezip -> daily US flight aggregates (ground truth).

Downloads On_Time_Reporting_Carrier_On_Time_Performance monthly zips (no auth) and
aggregates to per-day: scheduled flights, cancellations, flown, and scheduled
departures for the day (schedule-known-in-advance proxy).

Output: data/v27/bts_daily.json {date: {"sched": int, "cancelled": int}}.
Window: 2024-10 .. 2026-05 (latest posted).

Run: .venv/Scripts/python.exe scripts/v27/pull_bts_daily.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.request
import zipfile

OUT = os.path.join("data", "v27", "bts_daily.json")
URL = ("https://transtats.bts.gov/PREZIP/"
       "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip")
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}
MONTHS = [(2024, 10), (2024, 11), (2024, 12)] + [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 6)]


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out: dict[str, dict] = {}
    if os.path.exists(OUT):
        out = json.load(open(OUT, encoding="utf-8"))
    for y, m in MONTHS:
        probe = f"{y:04d}-{m:02d}-15"
        if probe in out:
            print(f"skip {y}-{m} (already aggregated)", flush=True)
            continue
        url = URL.format(y=y, m=m)
        print(f"downloading {y}-{m} ...", flush=True)
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                blob = r.read()
        except Exception as e:  # noqa: BLE001
            print(f"MISS {y}-{m}: {e}", flush=True)
            continue
        zf = zipfile.ZipFile(io.BytesIO(blob))
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        agg: dict[str, dict] = {}
        with zf.open(name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            for row in reader:
                d = row.get("FlightDate")
                if not d:
                    continue
                a = agg.setdefault(d, {"sched": 0, "cancelled": 0})
                a["sched"] += 1
                if row.get("Cancelled") in ("1.00", "1.0", "1"):
                    a["cancelled"] += 1
        out.update(agg)
        json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
        print(f"{y}-{m}: {len(agg)} days, sample {sorted(agg.items())[0]}", flush=True)
        time.sleep(2.0)
    print(f"DONE: {len(out)} days total", flush=True)


if __name__ == "__main__":
    main()
