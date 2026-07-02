"""v25: pull all trades for KXAAAGASW / KXAAAGASM settled markets, 2024-10 onward.

Inputs: the scratchpad hist_markets_*.json drains (created pre-lock) plus the live
settled endpoint for the recency window the historical endpoint misses.
Outputs (gitignored data/):
  data/v25/markets_all.json   consolidated market objects (both series, settled only)
  data/v25/trades.jsonl       one trade per line: {ticker, event_ticker, series,
                              created_time, yes_price_dollars, count_fp, taker_side}

Endpoint split (project gotcha): /historical/trades serves trades before 2026-05-01;
/markets/trades serves 2026-05-01 onward. Trade fields are count_fp and
yes_price_dollars (renamed from count / yes_price).

MUST NOT RUN before the methodology lock is committed (research/v25/02-methodology-lock.md).

Run: .venv/Scripts/python.exe scripts/v25/pull_kalshi_trades.py <scratchpad_dir>
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"
OUT_DIR = os.path.join("data", "v25")
SERIES = ["KXAAAGASW", "KXAAAGASM"]
UA = {"User-Agent": "Mozilla/5.0 (research)", "Accept": "application/json"}


def get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    last = None
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET {url} failed after 5: {last}")


def paged(path: str, params: dict, key: str):
    cursor = None
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        r = get(path, p)
        for item in r.get(key) or []:
            yield item
        cursor = r.get("cursor")
        if not cursor:
            return


def main() -> None:
    scratch = sys.argv[1]
    os.makedirs(OUT_DIR, exist_ok=True)

    markets: dict[str, dict] = {}
    for s in SERIES:
        fp = os.path.join(scratch, f"hist_markets_{s}.json")
        if os.path.exists(fp):
            for m in json.load(open(fp, encoding="utf-8-sig")):
                m["_series"] = s
                markets[m["ticker"]] = m
        # live settled endpoint covers the recency window the historical drain misses;
        # prefer whichever object carries a result (review M: a resultless drain object
        # must not shadow the settled live object)
        for m in paged("/markets", {"series_ticker": s, "status": "settled", "limit": 200}, "markets"):
            m["_series"] = s
            cur = markets.get(m["ticker"])
            if cur is None or cur.get("result") not in ("yes", "no"):
                markets[m["ticker"]] = m
    # settled + in-window only
    markets = {
        t: m
        for t, m in markets.items()
        if m.get("result") in ("yes", "no")
        and "2024-10-01" <= (m.get("close_time") or "") <= "2026-06-30T23:59:59Z"
    }
    json.dump(markets, open(os.path.join(OUT_DIR, "markets_all.json"), "w", encoding="utf-8"))
    print(f"settled in-window markets: {len(markets)}", flush=True)

    out_fp = os.path.join(OUT_DIR, "trades.jsonl")
    done: set[str] = set()
    if os.path.exists(out_fp + ".done"):
        done = set(json.load(open(out_fp + ".done", encoding="utf-8")))
    mode = "a" if done else "w"
    n_tr = 0
    with open(out_fp, mode, encoding="utf-8") as f:
        for i, (tk, m) in enumerate(sorted(markets.items())):
            if tk in done:
                continue
            rows = []
            for path in ("/historical/trades", "/markets/trades"):
                try:
                    for t in paged(path, {"ticker": tk, "limit": 1000}, "trades"):
                        rows.append(t)
                except RuntimeError as e:
                    print(f"WARN {tk} {path}: {e}", flush=True)
            seen = set()
            for t in rows:
                kid = t.get("trade_id") or (t.get("created_time"), t.get("yes_price_dollars"), t.get("count_fp"))
                if kid in seen:
                    continue
                seen.add(kid)
                f.write(json.dumps({
                    "ticker": tk,
                    "event_ticker": m.get("event_ticker"),
                    "series": m.get("_series"),
                    "created_time": t.get("created_time"),
                    "yes_price_dollars": t.get("yes_price_dollars") or t.get("yes_price"),
                    "count_fp": t.get("count_fp") or t.get("count"),
                    "taker_side": t.get("taker_side"),
                }) + "\n")
                n_tr += 1
            done.add(tk)
            if (i + 1) % 25 == 0:
                f.flush()
                json.dump(sorted(done), open(out_fp + ".done", "w", encoding="utf-8"))
                print(f"{i + 1}/{len(markets)} markets, {n_tr} trades", flush=True)
            time.sleep(0.15)
    json.dump(sorted(done), open(out_fp + ".done", "w", encoding="utf-8"))
    print(f"DONE: {len(done)} markets, {n_tr} new trades", flush=True)


if __name__ == "__main__":
    main()
