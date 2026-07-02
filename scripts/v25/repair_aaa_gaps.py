"""v25: second-pass gap repair for the AAA daily series.

The CDX collapse in pull_aaa_history.py keeps the FIRST snapshot per day, which is
often early-UTC (prior ET day's price), so some as-of dates stay missing after the
main crawl. For each missing date X in [2024-09-15, 2026-06-30], request the Wayback
snapshot nearest to X at 16:00 UTC (noon ET, after AAA's morning update); keep the
parsed value only if the page's own "Price as of" date equals X (or fills any other
still-missing date). One request per missing date, throttled.

Run: .venv/Scripts/python.exe scripts/v25/repair_aaa_gaps.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from pull_aaa_history import OUT, PRICE_RE, fetch  # noqa: E402


def main() -> None:
    out = json.load(open(OUT, encoding="utf-8"))
    have = set(out)
    d = date(2024, 9, 15)
    end = date(2026, 6, 30)
    missing = []
    while d <= end:
        if str(d) not in have:
            missing.append(d)
        d += timedelta(days=1)
    print(f"missing dates in window: {len(missing)}", flush=True)
    n_fixed = n_miss = 0
    for i, x in enumerate(missing):
        ts = x.strftime("%Y%m%d") + "160000"
        url = f"https://web.archive.org/web/{ts}/https://gasprices.aaa.com/"
        try:
            html = fetch(url, tries=3).decode("utf-8", errors="replace")
        except RuntimeError as e:
            print(f"MISS {x}: {e}", flush=True)
            n_miss += 1
            continue
        m = PRICE_RE.search(html)
        if not m:
            n_miss += 1
            continue
        price = float(m.group(1))
        mo, dy, yr = int(m.group(2)), int(m.group(3)), int(m.group(4))
        yr = yr + 2000 if yr < 100 else yr
        asof = f"{yr:04d}-{mo:02d}-{dy:02d}"
        if asof not in out:
            out[asof] = price
            if asof == str(x):
                n_fixed += 1
            print(f"FILL {asof} (target {x})", flush=True)
        if (i + 1) % 20 == 0:
            json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
            print(f"repair progress {i + 1}/{len(missing)}, filled-exact {n_fixed}", flush=True)
        time.sleep(1.2)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
    print(f"REPAIR DONE: {len(out)} dates total, exact fills {n_fixed}, misses {n_miss}", flush=True)


if __name__ == "__main__":
    main()
