"""v29 transient dutch-book sentinel (read-only, $0; self-expires 2026-09-01).

Charter and pre-committed gates: research/v29/00-sentinel-charter.md. Detection is
the v24 pair rule (two taker positions whose YES intervals cover R for < $1 net of
worst-case taker fees) on structured strikes. Burst-polls target ladders ~2.5s for
up to 8 minutes during volatility windows (equity open, macro releases, Wednesday
2pm, BTC 0.4 percent 5-minute moves); single calm pass otherwise. Never places
orders. Exit 0 always (a sentinel must not crash-loop).

Remove: Unregister-ScheduledTask -TaskName KalshiV29ArbSentinel
Run: .venv/Scripts/python.exe scripts/v29/arb_sentinel.py [--once]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

BASE = "https://api.elections.kalshi.com/trade-api/v2"
ET = ZoneInfo("America/New_York")
V29 = os.path.join("data", "v29")
LOG = os.path.join(V29, "arb_sentinel_log.jsonl")
STATE = os.path.join(V29, "sentinel_state.json")
EXPIRY = date(2026, 9, 1)
UA = {"User-Agent": "Mozilla/5.0 (research)", "Accept": "application/json"}
NEG, POS = float("-inf"), float("inf")

CALM_SERIES = ["KXBTCD", "KXETHD", "KXINXU", "KXNASDAQ100U",
               "KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA"]
CRYPTO_SERIES = ["KXBTCD", "KXETHD"]
EQUITY_SERIES = ["KXINXU", "KXNASDAQ100U", "KXBTCD", "KXETHD"]
BURST_SECONDS = 8 * 60
BURST_SPACING = 2.5
BTC_TRIGGER = 0.004


def log_row(row: dict) -> None:
    row["logged_utc"] = datetime.now(timezone.utc).isoformat()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def yes_interval(m):
    st = m.get("strike_type")
    fl, cp = fnum(m.get("floor_strike")), fnum(m.get("cap_strike"))
    if st in ("greater", "greater_or_equal") and fl is not None:
        return (fl, POS)
    if st in ("less", "less_or_equal") and cp is not None:
        return (NEG, cp)
    if st == "between" and fl is not None and cp is not None:
        return (fl, cp)
    return None


def taker_fee(p: float, coeff: float) -> float:
    if p is None or p <= 0 or p >= 1:
        return 999.0
    return math.ceil(coeff * 100.0 * p * (1.0 - p)) / 100.0


def scan_event(mkts, coeff):
    pos = []
    for m in mkts:
        iv = yes_interval(m)
        if iv is None:
            continue
        lo, hi = iv
        ya, na = fnum(m.get("yes_ask_dollars")), fnum(m.get("no_ask_dollars"))
        yas = fnum(m.get("yes_ask_size_fp")) or 0.0
        nas = fnum(m.get("no_ask_size_fp")) or 0.0
        tk = m.get("ticker")
        if ya is not None and 0 < ya < 1:
            pos.append((lo, hi, ya, yas, tk, "YES"))
        if na is not None and 0 < na < 1:
            if lo == NEG:
                pos.append((hi, POS, na, nas, tk, "NO"))
            elif hi == POS:
                pos.append((NEG, lo, na, nas, tk, "NO"))
    arbs = []
    for i in range(len(pos)):
        lo1, hi1, a1, s1, t1, sd1 = pos[i]
        for j in range(i + 1, len(pos)):
            lo2, hi2, a2, s2, t2, sd2 = pos[j]
            lows, highs = [], []
            for (lo, hi) in ((lo1, hi1), (lo2, hi2)):
                if lo == NEG and hi != POS:
                    lows.append(hi)
                elif hi == POS and lo != NEG:
                    highs.append(lo)
            if len(lows) == 1 and len(highs) == 1 and lows[0] >= highs[0]:
                cost = a1 + a2 + taker_fee(a1, coeff) + taker_fee(a2, coeff)
                if cost < 1.0:
                    arbs.append({"edge": round(1 - cost, 4), "size": min(s1, s2),
                                 "leg1": f"{sd1} {t1}@{a1}", "leg2": f"{sd2} {t2}@{a2}"})
    return arbs


def scan_series(series_list) -> int:
    hits = 0
    for ser in series_list:
        try:
            r = get_json(f"{BASE}/markets?series_ticker={ser}&status=open&limit=200")
        except Exception as e:  # noqa: BLE001
            log_row({"kind": "error", "where": ser, "err": str(e)[:200]})
            continue
        byev = defaultdict(list)
        for m in r.get("markets") or []:
            byev[m.get("event_ticker")].append(m)
        coeff = 0.035 if ser.startswith(("KXINX", "KXNASDAQ100")) else 0.07
        for ev, ems in byev.items():
            for a in scan_event(ems, coeff):
                a.update({"kind": "LOCKED_ARB", "series": ser, "event": ev})
                log_row(a)
                hits += 1
    return hits


def btc_move() -> float | None:
    try:
        spot = float(get_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])
    except Exception as e:  # noqa: BLE001
        log_row({"kind": "error", "where": "coinbase", "err": str(e)[:200]})
        return None
    st = {}
    if os.path.exists(STATE):
        st = json.load(open(STATE, encoding="utf-8"))
    prev = st.get("btc_spot")
    st["btc_spot"] = spot
    json.dump(st, open(STATE, "w", encoding="utf-8"))
    if prev:
        return abs(spot - prev) / prev
    return None


def burst_reason(now_et: datetime, move: float | None) -> tuple[str | None, list[str]]:
    wd, hm = now_et.weekday(), now_et.hour * 60 + now_et.minute
    if wd < 5 and 9 * 60 + 28 <= hm <= 9 * 60 + 50:
        return "equity_open", EQUITY_SERIES
    if wd < 5 and 8 * 60 + 28 <= hm <= 8 * 60 + 45:
        return "macro_release", EQUITY_SERIES
    if wd == 2 and 13 * 60 + 58 <= hm <= 14 * 60 + 25:
        return "fomc_window", EQUITY_SERIES
    if move is not None and move >= BTC_TRIGGER:
        return f"btc_move_{move:.4f}", CRYPTO_SERIES
    return None, []


def main() -> int:
    if date.today() > EXPIRY:
        return 0
    os.makedirs(V29, exist_ok=True)
    now_et = datetime.now(ET)
    move = btc_move()
    reason, series = burst_reason(now_et, move)
    if reason is None or "--once" in sys.argv:
        n = scan_series(CALM_SERIES)
        log_row({"kind": "heartbeat", "mode": "calm", "hits": n,
                 "btc_move": move, "et": now_et.isoformat()})
        return 0
    t0 = time.time()
    polls = total = 0
    while time.time() - t0 < BURST_SECONDS:
        total += scan_series(series)
        polls += 1
        time.sleep(BURST_SPACING)
    log_row({"kind": "burst_done", "reason": reason, "polls": polls, "hits": total,
             "series": series, "et": now_et.isoformat()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
