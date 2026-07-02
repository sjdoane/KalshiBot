"""v26 live certainty-ask monitor (read-only, $0, self-expiring 2026-08-03).

Measures the ONE channel print-based backtests cannot see: RESTING top-of-book
quotes on already-determined outcomes. Every run:

1. RAIN: for each open KXRAIN*M market, read the latest archived CLI month-to-date
   (IEM AFOS, latest issuance per pil). If MTD > strike + 0.02 (YES determined),
   log the live yes bid/ask and sizes.
2. TSA: for each open KXTSAW market, compute published Mon-Sun week days from the
   live TSA page plus same-weekday extreme bounds (from data/v26/tsa_daily.json,
   widened 15 percent). If even the adverse extreme decides the outcome, log quotes.

Appends JSONL rows to data/v26/live_certainty_log.jsonl. Never places orders. All
failures are logged and swallowed (exit 0 always; a monitor must not crash-loop).

Remove the schedule with:
  schtasks /delete /tn KalshiV26CertaintyMonitor /f

Run: .venv/Scripts/python.exe scripts/v26/live_certainty_monitor.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA = os.path.join("data", "v26")
LOG = os.path.join(DATA, "live_certainty_log.jsonl")
EXPIRY = date(2026, 8, 3)
UA = {"User-Agent": "Mozilla/5.0 (research)", "Accept": "application/json"}
RAIN_PIL = {
    "KXRAINNYCM": "CLINYC", "KXRAINCHIM": "CLIMDW", "KXRAINSEAM": "CLISEA",
    "KXRAINHOUM": "CLIHOU", "KXRAINMIAM": "CLIMIA", "KXRAINAUSM": "CLIAUS",
    "KXRAINDENM": "CLIDEN", "KXRAINLAXM": "CLILAX", "KXRAINDALM": "CLIDFW",
    "KXRAINSFOM": "CLISFO",
}
MTD_RE = re.compile(r"MONTH TO DATE\s+(T|MM|\d+\.\d+)")
TSA_ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\D+?([\d,]{6,})")


def get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def log_row(row: dict) -> None:
    row["logged_utc"] = datetime.now(timezone.utc).isoformat()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def open_markets(series: str) -> list[dict]:
    try:
        r = json.loads(get(f"{BASE}/markets?series_ticker={series}&status=open&limit=100"))
        return r.get("markets") or []
    except Exception as e:  # noqa: BLE001
        log_row({"kind": "error", "where": f"open_markets:{series}", "err": str(e)})
        return []


def latest_mtd(pil: str) -> tuple[float | None, str | None]:
    try:
        txt = get("https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
                  f"?pil={pil}&fmt=text&limit=1").decode("utf-8", errors="replace")
        m = MTD_RE.search(txt)
        if not m:
            return None, None
        v = m.group(1)
        return (0.0 if v == "T" else None if v == "MM" else float(v)), txt[:40]
    except Exception as e:  # noqa: BLE001
        log_row({"kind": "error", "where": f"cli:{pil}", "err": str(e)})
        return None, None


def check_rain() -> None:
    for series, pil in RAIN_PIL.items():
        ms = open_markets(series)
        if not ms:
            continue
        mtd, hdr = latest_mtd(pil)
        if mtd is None:
            continue
        for m in ms:
            k = m.get("floor_strike")
            if k is None or m.get("strike_type") != "greater":
                continue
            if mtd > float(k) + 0.02:
                log_row({
                    "kind": "rain_determined_yes", "ticker": m["ticker"], "mtd": mtd,
                    "strike": float(k), "yes_bid": m.get("yes_bid_dollars"),
                    "yes_ask": m.get("yes_ask_dollars"),
                    "ask_size": m.get("yes_ask_size_fp"), "bid_size": m.get("yes_bid_size_fp"),
                    "volume": m.get("volume_fp"), "close": m.get("close_time"), "pil_hdr": hdr,
                })
        time.sleep(0.4)


def tsa_page_values() -> dict[date, int]:
    out: dict[date, int] = {}
    try:
        html = get("https://www.tsa.gov/travel/passenger-volumes").decode("utf-8", errors="replace")
        for m in TSA_ROW_RE.finditer(html):
            mo, dy, yr, num = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            out[date(yr, mo, dy)] = int(num.replace(",", ""))
    except Exception as e:  # noqa: BLE001
        log_row({"kind": "error", "where": "tsa_page", "err": str(e)})
    return out


def check_tsa() -> None:
    ms = open_markets("KXTSAW")
    if not ms:
        return
    live = tsa_page_values()
    hist = {date.fromisoformat(k): v for k, v in json.load(
        open(os.path.join(DATA, "tsa_daily.json"), encoding="utf-8")).items()}
    hist.update(live)
    for m in ms:
        k = m.get("floor_strike")
        if k is None or m.get("strike_type") != "greater":
            continue
        k = float(k)
        if k <= 1000:
            k *= 1_000_000.0
        close_utc = datetime.strptime(m["close_time"][:10], "%Y-%m-%d").date()
        sunday = close_utc - timedelta(days=1)  # close Mon 03:59Z = Sun ET
        days = [sunday - timedelta(days=i) for i in range(6, -1, -1)]
        pub = [live[d] for d in days if d in live]
        unpub = [d for d in days if d not in live]
        los, his = [], []
        ok = True
        for d in unpub:
            same = [v for h, v in hist.items() if h.weekday() == d.weekday()
                    and 0 < (d - h).days <= 730]
            if len(same) < 20:
                ok = False
                break
            los.append(min(same) * 0.85)
            his.append(max(same) * 1.15)
        if not ok or not pub:
            continue
        lo_avg = (sum(pub) + sum(los)) / 7.0
        hi_avg = (sum(pub) + sum(his)) / 7.0
        determined = "yes" if lo_avg > k else ("no" if hi_avg < k else None)
        if determined:
            log_row({
                "kind": f"tsa_determined_{determined}", "ticker": m["ticker"],
                "strike_raw": k, "lo_avg": round(lo_avg), "hi_avg": round(hi_avg),
                "pub_days": len(pub), "yes_bid": m.get("yes_bid_dollars"),
                "yes_ask": m.get("yes_ask_dollars"), "ask_size": m.get("yes_ask_size_fp"),
                "bid_size": m.get("yes_bid_size_fp"), "volume": m.get("volume_fp"),
                "close": m.get("close_time"),
            })


def main() -> int:
    if date.today() > EXPIRY:
        return 0
    os.makedirs(DATA, exist_ok=True)
    log_row({"kind": "heartbeat"})
    check_rain()
    check_tsa()
    return 0


if __name__ == "__main__":
    sys.exit(main())
