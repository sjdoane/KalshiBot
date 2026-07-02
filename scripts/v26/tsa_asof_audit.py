"""v26 audit 0a2: TSA as-of integrity via Wayback spot checks (lock A3).

For >= 12 spot dates spanning May 2025 - Jun 2026, fetch the Wayback snapshot of
tsa.gov/travel/passenger-volumes nearest that date and compare the values it shows
for its most recent ~10 days against today's page (data/v26/tsa_daily.json). Any
in-window revision above 0.5 percent = H-A KILLED per the lock.

Run: .venv/Scripts/python.exe scripts/v26/tsa_asof_audit.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

DATA = os.path.join("data", "v26")
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}
ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\D+?([\d,]{6,})")
SPOTS = ["20250515", "20250615", "20250715", "20250815", "20250915", "20251015",
         "20251115", "20251215", "20260115", "20260215", "20260315", "20260415",
         "20260515", "20260615"]


def fetch(url: str, tries: int = 4) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(6.0 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def main() -> None:
    today = json.load(open(os.path.join(DATA, "tsa_daily.json"), encoding="utf-8"))
    n_checked = n_mismatch = n_snap = 0
    worst = (0.0, None)
    for ts in SPOTS:
        url = f"https://web.archive.org/web/{ts}120000/https://www.tsa.gov/travel/passenger-volumes"
        try:
            html = fetch(url).decode("utf-8", errors="replace")
        except RuntimeError as e:
            print(f"SNAP MISS {ts}: {e}", flush=True)
            continue
        n_snap += 1
        rows = []
        for m in ROW_RE.finditer(html):
            mo, dy, yr, num = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            rows.append((f"{yr:04d}-{mo:02d}-{dy:02d}", int(num.replace(",", ""))))
        rows = rows[:10]  # the snapshot's most recent rows
        for d, v_then in rows:
            v_now = today.get(d)
            if v_now is None:
                continue
            n_checked += 1
            rel = abs(v_now - v_then) / max(v_then, 1)
            if rel > worst[0]:
                worst = (rel, (d, v_then, v_now))
            if rel > 0.005:
                n_mismatch += 1
                print(f"REVISION {d}: then={v_then} now={v_now} rel={rel:.4f}", flush=True)
        time.sleep(2.0)
    print(f"snapshots={n_snap}/{len(SPOTS)} values_checked={n_checked} "
          f"revisions_over_0.5pct={n_mismatch} worst={worst}", flush=True)
    print("VERDICT:", "H-A KILLED (revisions in window)" if n_mismatch else "AS-OF CLEAN")


if __name__ == "__main__":
    main()
