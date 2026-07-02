"""v26 pre-lock audits (lock section 0). Run BEFORE the locking commit.

0a  settlement reproduction: TSA weekly means and ACIS monthly sums must reproduce
    every settled bracket (booleans/rates only; results reduced to agreement flags).
0b  outcome-blind fire projection: fire and fired-cluster counts per hypothesis at
    the frozen bands, from published-series arithmetic + prints only.

(0a2 TSA Wayback as-of audit is scripts/v26/tsa_asof_audit.py; 0a3 CLI correction
audit comes from the IEM AFOS reconstruction agent.)

Run: .venv/Scripts/python.exe scripts/v26/prelock_audits.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DATA = os.path.join("data", "v26")
ET = ZoneInfo("America/New_York")
STATION_OF = {
    "KXRAINNYCM": "KNYC", "KXRAINCHIM": "KMDW", "KXRAINSEAM": "KSEA",
    "KXRAINHOUM": "KHOU", "KXRAINMIAM": "KMIA", "KXRAINAUSM": "KAUS",
    "KXRAINDENM": "KDEN", "KXRAINLAXM": "KLAX", "KXRAINDALM": "KDFW",
    "KXRAINSFOM": "KSFO",
}
FIRE_BAND_YES = (0.03, 0.955)
H2_SAFETY = 0.02
BOUND_LOOKBACK_D = 730
BOUND_WIDEN = 0.15


def load():
    markets = json.load(open(os.path.join(DATA, "markets_all.json"), encoding="utf-8"))
    tsa = {date.fromisoformat(k): v for k, v in json.load(open(os.path.join(DATA, "tsa_daily.json"), encoding="utf-8")).items()}
    acis = json.load(open(os.path.join(DATA, "acis_precip.json"), encoding="utf-8"))
    return markets, tsa, acis


def week_days(close_time: str) -> list[date]:
    """KXTSAW week = Mon..Sun ending the Sunday before the close (close is Mon 03:59Z
    = Sun 23:59 ET; the rules name 'week ending <Sunday>')."""
    close_et = (datetime.strptime(close_time[:19], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=ZoneInfo("UTC")).astimezone(ET))
    sunday = close_et.date()
    if sunday.weekday() != 6:  # close lands Sun 23:59 ET; guard oddities
        sunday = sunday - timedelta(days=(sunday.weekday() - 6) % 7)
    return [sunday - timedelta(days=i) for i in range(6, -1, -1)]


def month_of(event_ticker: str) -> tuple[int, int] | None:
    # KXRAINNYCM-26JUL -> 2026-07
    tail = event_ticker.split("-")[-1]
    if len(tail) != 5:
        return None
    yy = 2000 + int(tail[:2])
    mon = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}.get(tail[2:])
    return (yy, mon) if mon else None


def audit_0a(markets, tsa, acis) -> None:
    print("=== 0a settlement reproduction (booleans/rates only) ===")
    ok = bad = skip = 0
    bad_rows = []
    for tk, m in sorted(markets.items()):
        if m.get("result") not in ("yes", "no") or m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            skip += 1
            continue
        k = float(m["floor_strike"])
        series = m.get("_series") or tk.split("-")[0]
        if series == "KXTSAW":
            if k > 1000:  # older events carry raw-count strikes, newer ones millions
                k /= 1_000_000.0
            days = week_days(m["close_time"])
            vals = [tsa.get(d) for d in days]
            if any(v is None for v in vals):
                skip += 1
                continue
            agg = sum(vals) / 7.0 / 1_000_000.0
        elif series in STATION_OF:
            ym = month_of(m.get("event_ticker") or "")
            if ym is None:
                skip += 1
                continue
            st = acis[STATION_OF[series]]
            vals = [v for d, v in st.items() if d.startswith(f"{ym[0]:04d}-{ym[1]:02d}")]
            if not vals or any(v is None for v in vals):
                skip += 1
                continue
            agg = sum(vals)
        else:
            skip += 1
            continue
        pred = "yes" if agg > k else "no"
        if pred == m["result"]:
            ok += 1
        else:
            bad += 1
            bad_rows.append((tk, round(agg, 4), k))
    print(f"reproduced {ok}/{ok + bad} (skipped {skip}: missing inputs/legacy)")
    for r in bad_rows[:20]:
        print(f"  MISMATCH {r[0]}: agg={r[1]} strike={r[2]}")


def tsa_visible(d: date, t_et: datetime) -> bool:
    """TSA value for day d visible at t (ET) iff the first Mon-Fri day strictly
    after d has passed 12:00 ET."""
    pub = d + timedelta(days=1)
    while pub.weekday() >= 5:
        pub += timedelta(days=1)
    return t_et > datetime(pub.year, pub.month, pub.day, 12, 0, tzinfo=ET)


def audit_0b(markets, tsa, acis) -> None:
    print("\n=== 0b outcome-blind fire projection ===")
    # ---- H-A: arithmetic-bound certainty on TSA weeklies ----
    tsa_sorted = sorted(tsa)
    fires_a = []
    taken = set()
    with open(os.path.join(DATA, "trades.jsonl"), encoding="utf-8") as f:
        seen = set()
        for line in f:
            t = json.loads(line)
            key5 = (t.get("ticker"), t.get("created_time"), t.get("yes_price_dollars"),
                    t.get("count_fp"), t.get("taker_side"))
            if key5 in seen:
                continue
            seen.add(key5)
            if t.get("series") != "KXTSAW":
                continue
            m = markets.get(t["ticker"])
            if m is None or m.get("floor_strike") is None:
                continue
            p = float(t["yes_price_dollars"])
            t_et = (datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S")
                    .replace(tzinfo=ZoneInfo("UTC")).astimezone(ET))
            dk = (t["ticker"], t_et.date().isoformat())
            if dk in taken:
                continue
            days = week_days(m["close_time"])
            pub = [tsa[d] for d in days if d in tsa and tsa_visible(d, t_et)]
            unpub = [d for d in days if not (d in tsa and tsa_visible(d, t_et))]
            if not pub:
                continue
            los, his = [], []
            for d in unpub:
                hist = [tsa[h] for h in tsa_sorted
                        if h.weekday() == d.weekday() and (d - h).days <= BOUND_LOOKBACK_D and h < d]
                if len(hist) < 20:
                    los = None
                    break
                los.append(min(hist) * (1 - BOUND_WIDEN))
                his.append(max(hist) * (1 + BOUND_WIDEN))
            if los is None:
                continue
            k = float(m["floor_strike"])
            if k <= 1000:  # strikes in millions on newer events
                k *= 1_000_000.0
            lo_avg = (sum(pub) + sum(los)) / 7.0
            hi_avg = (sum(pub) + sum(his)) / 7.0
            side = None
            if lo_avg > k and FIRE_BAND_YES[0] <= p <= FIRE_BAND_YES[1]:
                side = "yes"
            elif hi_avg < k and 0.045 <= p <= 0.97:
                side = "no"
            if side:
                fires_a.append({"ticker": t["ticker"], "cluster": m["close_time"][:10],
                                "p": p, "side": side, "et": t_et.isoformat()})
                taken.add(dk)
    cl_a = {f["cluster"] for f in fires_a}
    print(f"H-A projected fires: {len(fires_a)} across {len(cl_a)} weekly events "
          f"(floors: 30 fires / 12 clusters)")
    by_side = defaultdict(int)
    for f in fires_a:
        by_side[f["side"]] += 1
    print(f"  by side: {dict(by_side)}")

    # ---- H-B2: rain post-crossing (using AS-OF archived CLI if present, else ACIS
    # with next-day noon visibility as the PROJECTION proxy; the backtest uses CLI) ----
    cli_fp = os.path.join(DATA, "cli_asof.json")
    use_cli = os.path.exists(cli_fp)
    fires_b = []
    taken_b = set()
    with open(os.path.join(DATA, "trades.jsonl"), encoding="utf-8") as f:
        seen = set()
        for line in f:
            t = json.loads(line)
            key5 = (t.get("ticker"), t.get("created_time"), t.get("yes_price_dollars"),
                    t.get("count_fp"), t.get("taker_side"))
            if key5 in seen:
                continue
            seen.add(key5)
            s = t.get("series")
            if s not in STATION_OF:
                continue
            m = markets.get(t["ticker"])
            if m is None or m.get("floor_strike") is None:
                continue
            p = float(t["yes_price_dollars"])
            if not (FIRE_BAND_YES[0] <= p <= FIRE_BAND_YES[1]):
                continue
            t_et = (datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S")
                    .replace(tzinfo=ZoneInfo("UTC")).astimezone(ET))
            dk = (t["ticker"], t_et.date().isoformat())
            if dk in taken_b:
                continue
            ym = month_of(m.get("event_ticker") or "")
            if ym is None or (t_et.year, t_et.month) != ym:
                continue
            st = acis[STATION_OF[s]]
            cutoff = t_et.date() - timedelta(days=1)  # day d visible next day noon (proxy)
            if t_et.hour < 12:
                cutoff -= timedelta(days=1)
            mtd = 0.0
            okvals = True
            for dd in range(1, cutoff.day + 1) if cutoff.month == ym[1] else []:
                v = st.get(f"{ym[0]:04d}-{ym[1]:02d}-{dd:02d}")
                if v is None:
                    okvals = False
                    break
                mtd += v
            if not okvals or cutoff.month != ym[1]:
                continue
            k = float(m["floor_strike"])
            if mtd > k + H2_SAFETY:
                fires_b.append({"ticker": t["ticker"], "cluster": f"{ym[0]:04d}-{ym[1]:02d}",
                                "p": p, "mtd": round(mtd, 2), "k": k, "et": t_et.isoformat(),
                                "city": s})
                taken_b.add(dk)
    cl_b = {f["cluster"] for f in fires_b}
    cities = {f["city"] for f in fires_b}
    print(f"H-B2 projected fires ({'CLI' if use_cli else 'ACIS-proxy'}): {len(fires_b)} "
          f"across {len(cl_b)} month clusters, {len(cities)} cities "
          f"(floors: 30 fires / 10 clusters)")
    if fires_b:
        ps = sorted(f["p"] for f in fires_b)
        print(f"  print quantiles (10/50/90): {ps[len(ps)//10]:.2f} / {ps[len(ps)//2]:.2f} / {ps[9*len(ps)//10]:.2f}")
    json.dump({"h_a": {"fires": len(fires_a), "clusters": len(cl_a)},
               "h_b2": {"fires": len(fires_b), "clusters": len(cl_b), "cities": len(cities)}},
              open(os.path.join(DATA, "audit_0b_projection.json"), "w", encoding="utf-8"))


def main() -> None:
    markets, tsa, acis = load()
    print(f"markets={len(markets)} tsa_days={len(tsa)} acis_stations={len(acis)}")
    audit_0a(markets, tsa, acis)
    audit_0b(markets, tsa, acis)


if __name__ == "__main__":
    main()
