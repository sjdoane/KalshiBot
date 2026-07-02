"""v27: reconstruct the AS-OF (vintage) TSA daily series from Wayback snapshots of
tsa.gov/travel/passenger-volumes.

Each snapshot shows the current-year table as of its capture time. For every day D we
keep the value from the EARLIEST snapshot that displays D (the originally-published
figure) plus the latest value (for revision measurement). Output:
  data/v27/tsa_vintages.json: {day: {"first_seen": ts, "first_value": int,
                                     "last_value": int, "n_vintages": int}}

Window: snapshots 2025-04-01 .. 2026-07-02 (covers the KXTSAW era with margin).
Throttle: 2 workers, gentle; Wayback blocks aggressive crawls (v25 lesson).

Run: .venv/Scripts/python.exe scripts/v27/build_tsa_vintages.py
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request

OUT = os.path.join("data", "v27", "tsa_vintages.json")
CDX = ("https://web.archive.org/cdx/search/cdx?url=tsa.gov/travel/passenger-volumes"
       "&from=20241101&to=20260702&output=json&filter=statuscode:200"
       "&collapse=timestamp:8&fl=timestamp")
ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\D+?([\d,]{6,})")
UA = {"User-Agent": "Mozilla/5.0 (research; contact sjdoane@usc.edu)"}


def fetch(url: str, tries: int = 4) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(8.0 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out: dict[str, dict] = {}
    if os.path.exists(OUT):
        out = json.load(open(OUT, encoding="utf-8"))
    done_snaps: set[str] = set(json.load(open(OUT + ".snaps", encoding="utf-8"))) if os.path.exists(OUT + ".snaps") else set()

    rows = json.loads(fetch(CDX))
    stamps = [r[0] for r in rows[1:] if r[0] not in done_snaps]
    print(f"snapshots to fetch: {len(stamps)} (done {len(done_snaps)})", flush=True)

    lock = threading.Lock()
    counters = {"done": 0, "fail": 0}

    def work(ts: str) -> None:
        url = f"https://web.archive.org/web/{ts}/https://www.tsa.gov/travel/passenger-volumes"
        try:
            html = fetch(url).decode("utf-8", errors="replace")
        except RuntimeError as e:
            with lock:
                counters["fail"] += 1
                counters["done"] += 1
                print(f"MISS {ts}: {e}", flush=True)
            return
        rows_found = []
        for m in ROW_RE.finditer(html):
            mo, dy, yr, num = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            rows_found.append((f"{yr:04d}-{mo:02d}-{dy:02d}", int(num.replace(",", ""))))
        with lock:
            for day, val in rows_found:
                rec = out.get(day)
                if rec is None:
                    out[day] = {"first_seen": ts, "first_value": val,
                                "last_value": val, "last_seen": ts, "n_vintages": 1}
                else:
                    if ts < rec["first_seen"]:
                        rec["first_seen"], rec["first_value"] = ts, val
                    if ts >= rec["last_seen"]:
                        rec["last_seen"], rec["last_value"] = ts, val
                    rec["n_vintages"] += 1
            done_snaps.add(ts)
            counters["done"] += 1
            if counters["done"] % 25 == 0:
                json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
                json.dump(sorted(done_snaps), open(OUT + ".snaps", "w", encoding="utf-8"))
                print(f"progress {counters['done']}/{len(stamps)}: {len(out)} days", flush=True)

    sem = threading.Semaphore(2)

    def gated(ts: str) -> None:
        with sem:
            work(ts)
            time.sleep(1.0)

    threads = [threading.Thread(target=gated, args=(ts,)) for ts in stamps]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=0, sort_keys=True)
    json.dump(sorted(done_snaps), open(OUT + ".snaps", "w", encoding="utf-8"))
    print(f"DONE: {len(out)} days, fails {counters['fail']}", flush=True)


if __name__ == "__main__":
    main()
