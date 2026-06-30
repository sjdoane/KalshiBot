"""v24 weather external-forecast TAKER: kill-filter backtest.

Per research/v24/05-weather-taker-methodology-lock.md + 05b amendments.

This is an EXPLICITLY-OPTIMISTIC KILL FILTER:
- Forecast lead is uncontrolled (Open-Meteo historical-forecast, ~0-1 day,
  optimistic for a 1-2 day strategy) -> documented, not claimed clean.
- Conservative 3c spread haircut (lift-the-ask) so it is not doubly optimistic.
- TRAIN-only per-city station-offset correction (grid -> NWS settlement, inferred
  from Becker strike crossings).
- Season-stratified per-city forecast-error sigma (TRAIN only).
- Worst-case taker fee ceil(0.07*P*(1-P)).
- Event-cluster bootstrap by (city, ISO-week) to absorb day-to-day weather serial
  correlation.

Decision: if W-2/W-3 fail (CI lower bound not > 0 net of worst-case fee + 3c
spread on TRAIN and OOS), KILL weather (cannot win even with look-ahead). A PASS
is necessary-not-sufficient and only earns the live ramp.

Run: the project venv DuckDB (pandas is broken there); forecasts pre-fetched to
the scratchpad json via PowerShell (Bash has no network).
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime

import duckdb

sys.path.insert(0, "src")
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract  # noqa: E402

BASE = r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/prediction-market-analysis/data/kalshi"
FORECASTS = r"C:/Users/SamJD/AppData/Local/Temp/claude/C--Users-SamJD-OneDrive-Desktop-AI-Projects/6f4cdb0b-4fda-43e5-94a1-c905df9be740/scratchpad/v24_forecasts.json"

SERIES_TO_CITY = {
    "KXHIGHNY": "NY", "KXHIGHCHI": "CHI", "KXHIGHMIA": "MIA", "KXHIGHLAX": "LAX",
    "KXHIGHDEN": "DEN", "KXHIGHAUS": "AUS", "KXHIGHPHIL": "PHIL", "KXHIGHHOU": "HOU",
}

TRAIN_END = date(2025, 8, 15)
OOS_START = date(2025, 8, 22)
# Trade window (hours before close); overridable via argv for look-ahead diagnostic.
WIN_LO_H = int(sys.argv[1]) if len(sys.argv) > 1 else 24
WIN_HI_H = int(sys.argv[2]) if len(sys.argv) > 2 else 72
DIVERGENCE = 0.08
BAND_LO, BAND_HI = 0.10, 0.90
SPREAD_HAIRCUT = 0.03  # conservative lift-the-ask on thin weather books

_MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def parse_occ_date(event_ticker: str) -> date | None:
    m = re.match(r"^(?:KX)?HIGH[A-Z]+-(\d{2})([A-Z]{3})(\d{2})$", event_ticker)
    if not m:
        return None
    yy, mmm, dd = m.groups()
    mo = _MONTHS.get(mmm)
    if not mo:
        return None
    try:
        return date(2000 + int(yy), mo, int(dd))
    except ValueError:
        return None


def parse_title(title: str):
    """Return (kind, a, b): 'gt'/'lt' use a=N; 'band' uses a,b integer edges."""
    if not title:
        return None
    t = title.replace("°", "")
    m = re.search(r"be\s*>\s*(\d+)", t)
    if m:
        return ("gt", int(m.group(1)), None)
    m = re.search(r"be\s*<\s*(\d+)", t)
    if m:
        return ("lt", int(m.group(1)), None)
    m = re.search(r"be\s*(\d+)\s*-\s*(\d+)", t)
    if m:
        return ("band", int(m.group(1)), int(m.group(2)))
    return None


def season(d: date) -> str:
    return {12:"DJF",1:"DJF",2:"DJF",3:"MAM",4:"MAM",5:"MAM",6:"JJA",7:"JJA",8:"JJA",9:"SON",10:"SON",11:"SON"}[d.month]


def p_yes_model(kind, a, b, f, sigma):
    if sigma <= 0:
        sigma = 1e-6
    if kind == "gt":
        bd = a + 0.5
        return 1.0 - norm_cdf((bd - f) / sigma)
    if kind == "lt":
        bd = a - 0.5
        return norm_cdf((bd - f) / sigma)
    # band [a,b] inclusive integers
    return norm_cdf((b + 0.5 - f) / sigma) - norm_cdf((a - 0.5 - f) / sigma)


def main() -> None:
    with open(FORECASTS, encoding="utf-8-sig") as fh:
        forecasts = json.load(fh)  # {city: {iso_date: high_F}}

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")

    # Per-market rows + slow-window (24-72h before close) VWAP of yes_price.
    rows = con.execute(f"""
        WITH m AS (
            SELECT ticker, event_ticker, title, result, close_time,
                   regexp_extract(ticker, '^([A-Z0-9]+)', 1) AS series
            FROM read_parquet('{BASE}/markets/*.parquet')
            WHERE ticker LIKE 'KXHIGH%' AND result IN ('yes','no') AND close_time IS NOT NULL
        ),
        tr AS (
            SELECT t.ticker,
                   sum(t.yes_price * t.count)::DOUBLE / nullif(sum(t.count),0) AS vwap_yes_c,
                   sum(t.count) AS vol, count(*) AS n_slow
            FROM read_parquet('{BASE}/trades/*.parquet') t
            JOIN m ON t.ticker = m.ticker
            WHERE date_diff('hour', t.created_time, m.close_time) BETWEEN {WIN_LO_H} AND {WIN_HI_H}
            GROUP BY t.ticker
        )
        SELECT m.ticker, m.event_ticker, m.title, m.result, m.series,
               tr.vwap_yes_c, tr.n_slow
        FROM m LEFT JOIN tr ON m.ticker = tr.ticker
    """).fetchall()

    # ---- assemble per-market records ----
    recs = []
    obs_by_day: dict[tuple[str, date], list] = defaultdict(lambda: [-math.inf, math.inf])
    n_total = n_parsed = n_haveforecast = 0
    for ticker, ev, title, result, series, vwap_c, n_slow in rows:
        n_total += 1
        city = SERIES_TO_CITY.get(series)
        if city is None:
            continue
        od = parse_occ_date(ev)
        parsed = parse_title(title)
        if od is None or parsed is None:
            continue
        n_parsed += 1
        kind, a, b = parsed
        # accumulate observed-high bounds from this market's settlement
        lo, hi = obs_by_day[(city, od)]
        if kind == "gt":
            if result == "yes":
                lo = max(lo, a + 1)
            else:
                hi = min(hi, a)
        elif kind == "lt":
            if result == "yes":
                hi = min(hi, a - 1)
            else:
                lo = max(lo, a)
        else:  # band
            if result == "yes":
                lo = max(lo, a); hi = min(hi, b)
        obs_by_day[(city, od)] = [lo, hi]
        f = forecasts.get(city, {}).get(od.isoformat())
        if f is None:
            continue
        n_haveforecast += 1
        recs.append({
            "ticker": ticker, "city": city, "od": od, "kind": kind, "a": a, "b": b,
            "result": result, "vwap_c": vwap_c, "n_slow": n_slow, "f_grid": float(f),
        })

    # observed-high point per (city, day)
    obs_point: dict[tuple[str, date], float] = {}
    for k, (lo, hi) in obs_by_day.items():
        if math.isfinite(lo) and math.isfinite(hi) and lo <= hi:
            obs_point[k] = (lo + hi) / 2.0

    # ---- TRAIN-only station offset per city (obs - f_grid) ----
    train_off = defaultdict(list)
    for r in recs:
        if r["od"] < TRAIN_END:
            op = obs_point.get((r["city"], r["od"]))
            if op is not None:
                train_off[r["city"]].append(op - r["f_grid"])
    offset = {c: sorted(v)[len(v)//2] for c, v in train_off.items() if len(v) >= 10}

    # ---- TRAIN-only sigma per (city, season), fallback per city ----
    err_cs = defaultdict(list); err_c = defaultdict(list)
    for r in recs:
        if r["od"] < TRAIN_END and r["city"] in offset:
            op = obs_point.get((r["city"], r["od"]))
            if op is not None:
                fc = r["f_grid"] + offset[r["city"]]
                err_cs[(r["city"], season(r["od"]))].append(op - fc)
                err_c[r["city"]].append(op - fc)

    def _std(v):
        if len(v) < 2:
            return None
        mu = sum(v) / len(v)
        return math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1))

    sigma_cs = {k: _std(v) for k, v in err_cs.items() if len(v) >= 10}
    sigma_c = {c: _std(v) for c, v in err_c.items() if len(v) >= 10}

    # Persist FROZEN TRAIN params so the live signal generator uses identical params.
    params_path = "research/v24/weather_frozen_params.json"
    with open(params_path, "w", encoding="utf-8") as fh:
        json.dump({
            "offset": offset,
            "sigma_cs": {f"{c}|{s}": v for (c, s), v in sigma_cs.items()},
            "sigma_c": sigma_c,
            "divergence": DIVERGENCE, "band_lo": BAND_LO, "band_hi": BAND_HI,
            "spread_haircut": SPREAD_HAIRCUT, "train_end": TRAIN_END.isoformat(),
        }, fh, indent=2)
    print(f"frozen params -> {params_path}")

    # ---- trade selection + net P&L ----
    def window(od):
        if od < TRAIN_END:
            return "train"
        if od >= OOS_START:
            return "oos"
        return "purge"

    out = {"train": [], "oos": []}          # net per $1
    clusters = {"train": [], "oos": []}     # (city, iso-week)
    meta = {"train": [], "oos": []}         # (city, kind, p_model, p_mkt, win)
    n_no_forecast_city = 0
    discard_no_trade = 0
    considered = 0

    for r in recs:
        w = window(r["od"])
        if w == "purge":
            continue
        if r["city"] not in offset:
            n_no_forecast_city += 1
            continue
        sig = sigma_cs.get((r["city"], season(r["od"]))) or sigma_c.get(r["city"])
        if not sig:
            continue
        considered += 1
        if r["n_slow"] is None or r["n_slow"] < 1 or r["vwap_c"] is None:
            discard_no_trade += 1
            continue
        p_mkt = r["vwap_c"] / 100.0
        if not (BAND_LO <= p_mkt <= BAND_HI):
            continue
        fc = r["f_grid"] + offset[r["city"]]
        pm = p_yes_model(r["kind"], r["a"], r["b"], fc, sig)
        pm = min(max(pm, 0.0), 1.0)
        g = pm - p_mkt
        if abs(g) < DIVERGENCE:
            continue
        yes_side = g > 0
        if yes_side:
            entry = min(p_mkt + SPREAD_HAIRCUT, 0.99)
            win = r["result"] == "yes"
        else:
            entry = min((1.0 - p_mkt) + SPREAD_HAIRCUT, 0.99)
            win = r["result"] == "no"
        fee = kalshi_taker_fee_per_contract(entry)
        net = (1.0 - entry if win else -entry) - fee
        iso = r["od"].isocalendar()
        out[w].append(net)
        clusters[w].append(f"{r['city']}-{iso[0]}W{iso[1]:02d}")
        meta[w].append((r["city"], r["kind"], pm, p_mkt, win))

    # ---- verdict ----
    print("=" * 70)
    print("v24 WEATHER EXTERNAL-FORECAST TAKER  (optimistic KILL-FILTER backtest)")
    print("=" * 70)
    print(f"markets total={n_total} parsed={n_parsed} have-forecast={n_haveforecast}")
    print(f"cities with TRAIN station offset: {sorted(offset)}")
    print(f"  offsets(F): " + ", ".join(f"{c}:{offset[c]:+.1f}" for c in sorted(offset)))
    print(f"considered(post-offset,non-purge)={considered}  discard_no_slow_trade={discard_no_trade} "
          f"({100*discard_no_trade/max(considered,1):.0f}%)")
    print()
    for w in ("train", "oos"):
        vals = out[w]; cl = clusters[w]
        n_fills = len(vals)
        n_clusters = len(set(cl))
        print(f"--- {w.upper()} ---  fills={n_fills}  clusters(city-week)={n_clusters}")
        if n_fills >= 2 and n_clusters >= 2:
            mean, lo, hi, k = cluster_bootstrap_mean_ci(vals, cl, n_resamples=5000, ci=0.95, rng_seed=42)
            print(f"  net/contract mean={mean*100:+.2f}pp  95% CI [{lo*100:+.2f}, {hi*100:+.2f}]pp  k={k}")
            print(f"  PASS(CI lower>0): {lo > 0}")
            wins = sum(1 for m in meta[w] if m[4])
            print(f"  hit rate={100*wins/n_fills:.1f}%  (adverse-selection check: model on selected days)")
        else:
            print("  insufficient fills/clusters")
        print()

    # capacity (OOS): $ net per week at $1 notional
    if out["oos"]:
        net_total = sum(out["oos"])
        span_weeks = max(1, (max(r["od"] for r in recs) - OOS_START).days / 7)
        print(f"CAPACITY(OOS): total net (per $1 notional, 1 contract/fill) = ${net_total:.2f} "
              f"over ~{span_weeks:.0f} weeks = ${net_total/span_weeks:.3f}/week")

    # per-strike-type split (OOS), diagnostic only
    for typ in ("gt", "lt", "band"):
        v = [out["oos"][i] for i, m in enumerate(meta["oos"]) if m[1] == typ]
        if v:
            print(f"  OOS {typ}: n={len(v)} mean={100*sum(v)/len(v):+.2f}pp")


if __name__ == "__main__":
    main()
