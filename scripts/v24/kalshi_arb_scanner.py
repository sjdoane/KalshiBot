"""Cross-market structural-arbitrage scanner + monitor for Kalshi (read-only, $0).

A non-informational edge that escapes BOTH project walls: within one event (same
underlying + settlement) the outcome markets must be mutually consistent. A LOCKED
dutch book (a basket guaranteed to pay >= $1 for a cost < $1 net of the worst-case
taker fee) is risk-free, so it dodges the capture phantom (no forecast) and adverse
selection (both legs taken at once). Static snapshots are consistent (verified); the
live value is TRANSIENT arbs during fast moves, when MMs pull/lag quotes. Kalshi is
not HFT-speed, so a retail taker can capture these; they cannot be backtested (no
orderbook history), which is why they may persist.

Uses structured fields (floor_strike / cap_strike / strike_type) for exact YES
intervals, so it handles threshold ladders (above/below/over) and partition ladders
(weather bands). Detects the pair arb: two positions whose YES-intervals union to R,
buyable for < $1 net of fee.

Modes:
  one-shot (default): scan the series list once, print any locked arb.
  --monitor N --interval S: poll N times every S seconds, log every locked arb seen
    (ticker legs, edge, executable size). Never places orders (alert-only).

Run:
  .venv/Scripts/python.exe scripts/v24/kalshi_arb_scanner.py [SERIES...]
  .venv/Scripts/python.exe scripts/v24/kalshi_arb_scanner.py --monitor 30 --interval 20 KXBTCD KXETHD
"""
from __future__ import annotations

import math
import sys
import time
from collections import defaultdict

sys.path.insert(0, "src")
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

NEG, POS = float("-inf"), float("inf")
DEFAULT_SERIES = [
    "KXINXU", "KXINXD", "KXNASDAQ100U", "KXNASDAQ100D", "KXBTCD", "KXETHD",
    "KXMLBTOTAL", "KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA",
]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def yes_interval(m):
    st = m.get("strike_type")
    fl = f(m.get("floor_strike")); cp = f(m.get("cap_strike"))
    if st in ("greater", "greater_or_equal") and fl is not None:
        return (fl, POS)
    if st in ("less", "less_or_equal") and cp is not None:
        return (NEG, cp)
    if st == "between" and fl is not None and cp is not None:
        return (fl, cp)
    return None


def taker_fee(p, coeff):
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
        ya = f(m.get("yes_ask_dollars")); na = f(m.get("no_ask_dollars"))
        yas = f(m.get("yes_ask_size_fp")) or 0.0
        nas = f(m.get("no_ask_size_fp")) or 0.0
        tk = m.get("ticker")
        if ya is not None and 0 < ya < 1:
            pos.append((lo, hi, ya, yas, tk, "YES"))
        if na is not None and 0 < na < 1:
            if lo == NEG:
                pos.append((hi, POS, na, nas, tk, "NO"))
            elif hi == POS:
                pos.append((NEG, lo, na, nas, tk, "NO"))
    arbs = []
    n = len(pos)
    for i in range(n):
        lo1, hi1, a1, s1, t1, sd1 = pos[i]
        for j in range(i + 1, n):
            lo2, hi2, a2, s2, t2, sd2 = pos[j]
            lows = []; highs = []
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


def scan_once(cli, series):
    total = 0
    hits = []
    for ser in series:
        try:
            mkts = list(cli.paginate("/markets", item_key="markets", limit=200,
                                     series_ticker=ser, status="open"))
        except Exception as e:
            print(f"{ser}: ERR {e!r}")
            continue
        byev = defaultdict(list)
        for m in mkts:
            byev[m.get("event_ticker")].append(m)
        coeff = 0.035 if ser.startswith(("KXINX", "KXNASDAQ100")) else 0.07
        ser_arbs = []
        for ev, ems in byev.items():
            for a in scan_event(ems, coeff):
                a["series"] = ser; a["event"] = ev
                ser_arbs.append(a)
        total += len(ser_arbs)
        hits += ser_arbs
        if ser_arbs:
            for a in sorted(ser_arbs, key=lambda z: -z["edge"])[:5]:
                print(f"  ARB {a['series']} {a['event']} edge={a['edge']*100:+.2f}pp "
                      f"size~{a['size']:.0f}  {a['leg1']} + {a['leg2']}")
    return total, hits


def main():
    argv = sys.argv[1:]
    monitor_n = 0; interval = 20
    series = []
    i = 0
    while i < len(argv):
        if argv[i] == "--monitor":
            monitor_n = int(argv[i + 1]); i += 2
        elif argv[i] == "--interval":
            interval = int(argv[i + 1]); i += 2
        else:
            series.append(argv[i]); i += 1
    if not series:
        series = DEFAULT_SERIES
    s = Settings()
    with KalshiClient(s) as cli:
        if monitor_n <= 0:
            total, _ = scan_once(cli, series)
            print(f"TOTAL locked arbs: {total}")
            return
        print(f"MONITOR: {monitor_n} polls x {interval}s on {series}")
        ever = 0
        for k in range(monitor_n):
            total, hits = scan_once(cli, series)
            tag = f"[poll {k+1}/{monitor_n}]"
            if total:
                ever += total
                print(f"{tag} {total} locked arb(s) THIS POLL")
            else:
                print(f"{tag} clean")
            if k < monitor_n - 1:
                time.sleep(interval)
        print(f"MONITOR DONE: {ever} arb-sightings over {monitor_n} polls")


if __name__ == "__main__":
    main()
