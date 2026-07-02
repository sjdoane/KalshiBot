"""v25: pull daily wholesale gasoline / crude series from FRED (fredgraph.csv, no key).

Series:
  DGASNYH    Conventional gasoline, NY Harbor, regular, $/gal, daily (EIA via FRED)
  DGASUSGULF Conventional gasoline, US Gulf Coast, regular, $/gal, daily
  DCOILWTICO WTI crude, $/bbl, daily

Writes data/v25/fred_wholesale.json: {series: {"YYYY-MM-DD": float}}.
Values publish with roughly a one-business-day lag; the AS-OF rule (a trade on day t may
only see values with date <= t-1 business day) is enforced downstream in the backtest,
not here.

Run: .venv/Scripts/python.exe scripts/v25/pull_fred_wholesale.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.request

OUT = os.path.join("data", "v25", "fred_wholesale.json")
SERIES = ["DGASNYH", "DGASUSGULF", "DCOILWTICO"]
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2023-01-01"
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out: dict[str, dict[str, float]] = {}
    for sid in SERIES:
        req = urllib.request.Request(URL.format(sid=sid), headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
        rows = list(csv.reader(io.StringIO(text)))
        header, data = rows[0], rows[1:]
        assert header[0].lower() in ("date", "observation_date"), header
        vals = {}
        for d, v in data:
            if v not in (".", ""):
                vals[d] = float(v)
        out[sid] = vals
        print(f"{sid}: {len(vals)} obs, {min(vals)} .. {max(vals)}", flush=True)
        time.sleep(1.0)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
