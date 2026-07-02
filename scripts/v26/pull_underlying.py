"""v26: pull the underlying public series.

1. TSA daily checkpoint screenings: tsa.gov/travel/passenger-volumes (current year)
   plus /<year> pages (2019-2025). Plain HTML tables, rows "M/D/YYYY | N,NNN,NNN".
   Output data/v26/tsa_daily.json {date: int}. NOTE: this is TODAY'S (possibly
   revised) view; the as-of integrity audit is separate per the lock.
2. ACIS daily precipitation for the 10 mapped stations (scout-data-sources.md),
   1970-01-01 (or station start) to today. "T" (trace) stored as 0.0 per the verified
   CLI summation convention; "M"/missing days stored as null.
   Output data/v26/acis_precip.json {station: {date: float|null}}.

Run: .venv/Scripts/python.exe scripts/v26/pull_underlying.py
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

OUT_DIR = os.path.join("data", "v26")
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}
STATIONS = ["KNYC", "KMDW", "KSEA", "KHOU", "KMIA", "KAUS", "KDEN", "KLAX", "KDFW", "KSFO"]
ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\D+?([\d,]{6,})")


def fetch(url: str, data: bytes | None = None, tries: int = 4) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, "Content-Type": "application/json"} if data else UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3.0 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def pull_tsa() -> None:
    out: dict[str, int] = {}
    urls = ["https://www.tsa.gov/travel/passenger-volumes"] + [
        f"https://www.tsa.gov/travel/passenger-volumes/{y}" for y in range(2019, 2026)
    ]
    for url in urls:
        html = fetch(url).decode("utf-8", errors="replace")
        n0 = len(out)
        for m in ROW_RE.finditer(html):
            mo, dy, yr, num = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            out[f"{yr:04d}-{mo:02d}-{dy:02d}"] = int(num.replace(",", ""))
        print(f"{url}: +{len(out) - n0} rows", flush=True)
        time.sleep(1.0)
    json.dump(out, open(os.path.join(OUT_DIR, "tsa_daily.json"), "w", encoding="utf-8"),
              indent=0, sort_keys=True)
    print(f"TSA: {len(out)} days {min(out)}..{max(out)}", flush=True)


def pull_acis() -> None:
    out: dict[str, dict] = {}
    for sid in STATIONS:
        body = json.dumps({
            "sid": sid, "sdate": "1970-01-01", "edate": "2026-07-02",
            "elems": [{"name": "pcpn"}],
        }).encode()
        r = json.loads(fetch("https://data.rcc-acis.org/StnData", data=body))
        vals = {}
        for d, v in r.get("data", []):
            if v in ("M", ""):
                vals[d] = None
            elif v == "T":
                vals[d] = 0.0
            else:
                try:
                    vals[d] = float(v)
                except ValueError:
                    vals[d] = None
        out[sid] = vals
        ok = sum(1 for v in vals.values() if v is not None)
        print(f"{sid}: {len(vals)} days, {ok} non-missing", flush=True)
        time.sleep(1.0)
    json.dump(out, open(os.path.join(OUT_DIR, "acis_precip.json"), "w", encoding="utf-8"),
              indent=0, sort_keys=True)
    print("ACIS done", flush=True)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pull_tsa()
    pull_acis()


if __name__ == "__main__":
    main()
