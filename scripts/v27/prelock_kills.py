"""v27 pre-lock cheap kill switches (plan critic A6/A7/A9, all outcome-blind except
A6 which reduces Kalshi results to bracket-agreement booleans, v25 E12a-style).

K1 (A6): vintage settlement reconciliation. For every settled KXTSAW event where all
    7 week days have vintage FIRST-published values: does the first-value weekly
    average reproduce the settled bracket? Failures = revision-affected weeks.
K2 (A7): evaluability. Fraction of in-band prints whose required published set
    (Mon-Fri publication rule) is SNAPSHOT-PROVEN at print time (vintage first_seen
    <= print time), no posting-schedule inference. Under 40 percent = kill.
K3 (A9): print-death. Per-week count of near-ATM (0.15-0.85) prints on ET Fri-Sun;
    median week must not be print-dead.

Run: .venv/Scripts/python.exe scripts/v27/prelock_kills.py
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
V26 = os.path.join("data", "v26")
V27 = os.path.join("data", "v27")


def load():
    markets = {t: m for t, m in json.load(open(os.path.join(V26, "markets_all.json"), encoding="utf-8")).items()
               if t.startswith("KXTSAW")}
    vint = json.load(open(os.path.join(V27, "tsa_vintages.json"), encoding="utf-8"))
    trades = []
    seen = set()
    with open(os.path.join(V26, "trades.jsonl"), encoding="utf-8") as f:
        for line in f:
            if '"KXTSAW"' not in line:
                continue
            t = json.loads(line)
            k5 = (t["ticker"], t["created_time"], t["yes_price_dollars"], t.get("count_fp"), t.get("taker_side"))
            if k5 in seen:
                continue
            seen.add(k5)
            trades.append(t)
    return markets, vint, trades


def week_days(close_time: str) -> list[date]:
    close_et = (datetime.strptime(close_time[:19], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=UTC).astimezone(ET))
    sunday = close_et.date()
    if sunday.weekday() != 6:
        sunday = sunday - timedelta(days=(sunday.weekday() - 6) % 7)
    return [sunday - timedelta(days=i) for i in range(6, -1, -1)]


def norm_strike(k: float) -> float:
    return k / 1_000_000.0 if k > 1000 else k


def k1(markets, vint) -> None:
    print("=== K1 (A6): vintage settlement reconciliation ===")
    by_event = defaultdict(list)
    for tk, m in markets.items():
        if m.get("result") in ("yes", "no") and m.get("strike_type") == "greater" and m.get("floor_strike") is not None:
            by_event[m["event_ticker"]].append(m)
    ok = bad = skip = 0
    bad_ev = []
    for ev, ms in sorted(by_event.items()):
        days = week_days(ms[0]["close_time"])
        vals = [vint.get(str(d), {}).get("first_value") for d in days]
        if any(v is None for v in vals):
            skip += 1
            continue
        avg = sum(vals) / 7.0 / 1_000_000.0
        agree = all(("yes" if avg > norm_strike(float(m["floor_strike"])) else "no") == m["result"] for m in ms)
        if agree:
            ok += 1
        else:
            bad += 1
            bad_ev.append(ev)
    print(f"events reproduced from FIRST-published vintages: {ok}/{ok + bad} (skipped {skip} lacking full vintages)")
    for ev in bad_ev:
        print(f"  REVISION-AFFECTED: {ev}")


def k2_k3(markets, vint, trades) -> None:
    print("\n=== K2 (A7): snapshot-proven evaluability; K3 (A9): print liveness ===")
    n_eval = n_tot = 0
    per_week_frisun = defaultdict(int)
    per_week_all = defaultdict(int)
    for t in trades:
        m = markets.get(t["ticker"])
        if m is None:
            continue
        p = float(t["yes_price_dollars"])
        t_et = (datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=UTC).astimezone(ET))
        days = week_days(m["close_time"])
        if not (0.15 <= p <= 0.85):
            continue
        per_week_all[m["event_ticker"]] += 1
        if t_et.weekday() >= 4:  # Fri, Sat, Sun
            per_week_frisun[m["event_ticker"]] += 1
        # required published set at print time: days whose first Mon-Fri day after
        # them is strictly before the print date (publication rule), i.e. should be out
        req = []
        for d in days:
            pub = d + timedelta(days=1)
            while pub.weekday() >= 5:
                pub += timedelta(days=1)
            if datetime(pub.year, pub.month, pub.day, 12, 0, tzinfo=ET) < t_et:
                req.append(d)
        n_tot += 1
        ok = True
        for d in req:
            rec = vint.get(str(d))
            if rec is None:
                ok = False
                break
            fs = rec["first_seen"]
            fs_dt = datetime.strptime(fs[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            if fs_dt > t_et.astimezone(UTC):
                ok = False
                break
        n_eval += ok
    print(f"K2 evaluability: {n_eval}/{n_tot} in-band prints snapshot-proven = {n_eval / max(n_tot, 1):.1%} (kill under 40 percent)")
    weeks = sorted(per_week_all)
    fri = sorted(per_week_frisun.values())
    alln = sorted(per_week_all.values())
    med_fri = fri[len(fri) // 2] if fri else 0
    med_all = alln[len(alln) // 2] if alln else 0
    print(f"K3: weeks with any in-band print: {len(weeks)}; median in-band prints/week: {med_all}; "
          f"weeks with Fri-Sun in-band prints: {len(per_week_frisun)}; median Fri-Sun prints/week: {med_fri}")


def main() -> None:
    markets, vint, trades = load()
    print(f"KXTSAW settled markets={len(markets)} vintage_days={len(vint)} deduped_prints={len(trades)}")
    k1(markets, vint)
    k2_k3(markets, vint, trades)


if __name__ == "__main__":
    main()
