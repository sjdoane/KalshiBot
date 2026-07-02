"""v25: reconstruct the AAA national average regular gas price DAILY history from
Wayback Machine snapshots of gasprices.aaa.com.

Method (verified by the v25 data scout, research/v25/scout-data-sources.md):
  1. One CDX query lists snapshots 2024-09-01..today, collapsed to one per day.
  2. Fetch each snapshot, parse the national average with the scout's regex, and KEY THE
     VALUE ON THE PAGE'S OWN "Price as of" DATE (not the UTC snapshot timestamp; early-UTC
     snapshots show the prior day's price).
  3. Write data/v25/aaa_daily.json: {"YYYY-MM-DD": price_float}. Later dates win on
     duplicate as-of keys (pages are same-day consistent; the average updates once daily).

Display precision changed from 3 to 4 decimals in 2026; regex accepts both.
This is data infrastructure only. No Kalshi price data is joined here (pre-lock no-peek).

Run: .venv/Scripts/python.exe scripts/v25/pull_aaa_history.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

OUT = os.path.join("data", "v25", "aaa_daily.json")
CDX = (
    "https://web.archive.org/cdx/search/cdx?url=gasprices.aaa.com/"
    "&from=20240901&to=20260703&output=json&filter=statuscode:200"
    "&collapse=timestamp:8&fl=timestamp"
)
PRICE_RE = re.compile(
    r"National Average.{0,400}?\$(\d\.\d{3,4}).{0,400}?Price as of\s*(\d+)/(\d+)/(\d+)",
    re.S,
)
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}


def fetch(url: str, tries: int = 4, timeout: int = 45) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - retry any transient failure
            last = e
            time.sleep(8.0 * (i + 1))
    raise RuntimeError(f"failed after {tries}: {url}: {last}")


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    existing: dict[str, float] = {}
    if os.path.exists(OUT):
        existing = json.load(open(OUT, encoding="utf-8"))
        print(f"resuming with {len(existing)} existing dates", flush=True)

    rows = json.loads(fetch(CDX))
    stamps = [r[0] for r in rows[1:]]
    print(f"CDX snapshots (1/day): {len(stamps)}", flush=True)

    out = dict(existing)
    done_days = {k.replace("-", "")[:8] for k in existing}
    todo = [ts for ts in stamps if ts[:8] not in done_days]
    print(f"to fetch: {len(todo)}", flush=True)

    import threading

    lock = threading.Lock()
    counters = {"new": 0, "fail": 0, "done": 0}

    def work(ts: str) -> None:
        url = f"https://web.archive.org/web/{ts}/https://gasprices.aaa.com/"
        try:
            html = fetch(url).decode("utf-8", errors="replace")
            m = PRICE_RE.search(html)
        except RuntimeError as e:
            with lock:
                counters["fail"] += 1
                counters["done"] += 1
                print(f"MISS {ts}: {e}", flush=True)
            return
        with lock:
            counters["done"] += 1
            if not m:
                counters["fail"] += 1
                print(f"NOPARSE {ts}", flush=True)
            else:
                price = float(m.group(1))
                mo, dy, yr = int(m.group(2)), int(m.group(3)), int(m.group(4))
                yr = yr + 2000 if yr < 100 else yr
                out[f"{yr:04d}-{mo:02d}-{dy:02d}"] = price
                counters["new"] += 1
                if counters["new"] % 25 == 0:
                    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
                    print(f"progress {counters['done']}/{len(todo)}: {len(out)} dates", flush=True)

    sem = threading.Semaphore(2)

    def gated(ts: str) -> None:
        with sem:
            work(ts)
            time.sleep(1.0)

    threads = [threading.Thread(target=gated, args=(ts,)) for ts in todo]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
    print(
        f"DONE: {len(out)} dates ({counters['new']} new, {counters['fail']} miss/parse-fail)",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
