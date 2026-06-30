"""v24 weather taker: one-shot LIVE read-only feasibility check (NO orders).

Per research/v24/06-weather-backtest-results.md + lock 05/05b (AMEND-D).
Resolves the two binding questions the look-ahead-contaminated backtest cannot:
  1) With a REALISTIC 1-2 day forecast sigma (the Becker-fitted sigma ~1F is
     leaky/near-analysis and must NOT be used live), does the locked signal
     (|p_model - p_mkt| >= 8pp, p_mkt in [0.10,0.90]) fire on any CURRENT open
     KXHIGH market in the 24-48h-to-close window?
  2) Is the live ask already at the forecast (capture phantom)? i.e. even where a
     signal fires, is there a crossable gap left after the worst-case taker fee?

Read-only: lists markets, reads orderbook, pulls the live public forecast. Places
NO orders. Run via PowerShell (network).
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timezone

import httpx

sys.path.insert(0, "src")
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract  # noqa: E402

CITIES = {
    "NY":  (40.7794, -73.9692, "America/New_York"),
    "CHI": (41.9742, -87.9073, "America/Chicago"),
    "MIA": (25.7959, -80.2870, "America/New_York"),
    "LAX": (33.9416, -118.4085, "America/Los_Angeles"),
    "DEN": (39.8561, -104.6737, "America/Denver"),
    "AUS": (30.1975, -97.6664, "America/Chicago"),
    "PHIL":(39.8729, -75.2437, "America/New_York"),
    "HOU": (29.9902, -95.3368, "America/Chicago"),
}
PARAMS = json.load(open("research/v24/weather_frozen_params.json", encoding="utf-8"))
OFFSET = PARAMS["offset"]
DIVERGENCE, BAND_LO, BAND_HI = PARAMS["divergence"], PARAMS["band_lo"], PARAMS["band_hi"]
# REALISTIC 1-2 day daily-high forecast sigma (physical prior; the Becker-fitted
# ~1F is leaky). Report a sensitivity band.
SIGMAS = [2.5, 3.0, 3.5]
_MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}


def norm_cdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def parse_title(title):
    if not title:
        return None
    t = title.replace("°", "")
    m = re.search(r"be\s*>\s*(\d+)", t)
    if m: return ("gt", int(m.group(1)), None)
    m = re.search(r"be\s*<\s*(\d+)", t)
    if m: return ("lt", int(m.group(1)), None)
    m = re.search(r"be\s*(\d+)\s*-\s*(\d+)", t)
    if m: return ("band", int(m.group(1)), int(m.group(2)))
    return None


def p_yes(kind, a, b, f, sig):
    if kind == "gt": return 1.0 - norm_cdf((a + 0.5 - f) / sig)
    if kind == "lt": return norm_cdf((a - 0.5 - f) / sig)
    return norm_cdf((b + 0.5 - f) / sig) - norm_cdf((a - 0.5 - f) / sig)


def occ_from_ticker(ticker):
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})-", ticker)
    if not m: return None
    yy, mmm, dd = m.groups()
    return f"20{yy}-{_MONTHS[mmm]:02d}-{int(dd):02d}"


def main():
    now = datetime.now(timezone.utc)
    hc = httpx.Client(timeout=30.0)
    # 1) live forecasts (current run) for all cities, next ~4 days
    fc = {}
    for c, (lat, lon, tz) in CITIES.items():
        r = hc.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit", "timezone": tz, "forecast_days": 4})
        d = r.json().get("daily", {})
        fc[c] = dict(zip(d.get("time", []), d.get("temperature_2m_max", [])))

    s = Settings()
    candidates = []
    n_markets = 0
    with KalshiClient(s) as cli:
        for city in CITIES:
            for m in cli.paginate("/markets", item_key="markets",
                                  series_ticker=f"KXHIGH{city}", status="open", limit=200):
                def _f(x):
                    try:
                        return float(x)
                    except (TypeError, ValueError):
                        return 0.0
                ya = _f(m.get("yes_ask_dollars"))   # dollars
                yb = _f(m.get("yes_bid_dollars"))
                na = _f(m.get("no_ask_dollars"))
                if not ya or not yb or ya >= 1.0 or yb <= 0.0:
                    continue  # no usable two-sided quote
                n_markets += 1
                close = m.get("close_time", "")
                try:
                    ct = datetime.fromisoformat(close.replace("Z", "+00:00"))
                except Exception:
                    continue
                hrs = (ct - now).total_seconds() / 3600.0
                if not (12 <= hrs <= 60):  # the slow 1-2 day window, live
                    continue
                od = occ_from_ticker(m["ticker"])
                f = fc.get(city, {}).get(od)
                if f is None:
                    continue
                parsed = parse_title(m.get("title", ""))
                if parsed is None:
                    continue
                kind, a, b = parsed
                fcorr = f + OFFSET.get(city, 0.0)
                mid = (float(ya) + float(yb)) / 2.0  # yes mid in dollars
                yes_ask = float(ya)
                no_ask = float(na) if na else (1.0 - float(yb))
                for sig in [3.0]:  # primary sigma for firing
                    pm = min(max(p_yes(kind, a, b, fcorr, sig), 0.0), 1.0)
                    g = pm - mid
                    if abs(g) >= DIVERGENCE and BAND_LO <= mid <= BAND_HI:
                        if g > 0:  # buy YES at yes_ask
                            entry, fee = yes_ask, kalshi_taker_fee_per_contract(yes_ask)
                            edge_after = (pm - entry) - fee
                            side = "YES"
                        else:      # buy NO at no_ask
                            entry, fee = no_ask, kalshi_taker_fee_per_contract(no_ask)
                            edge_after = ((1 - pm) - entry) - fee
                            side = "NO"
                        candidates.append({
                            "ticker": m["ticker"], "city": city, "hrs": round(hrs, 1),
                            "kind": kind, "f": round(fcorr, 1), "p_model": round(pm, 3),
                            "yes_mid": round(mid, 3), "side": side, "entry": round(entry, 3),
                            "g": round(g, 3), "edge_after_fee": round(edge_after, 3),
                            "spread_c": round((float(ya) - float(yb)) * 100),
                        })

    print("=" * 70)
    print(f"v24 WEATHER LIVE FEASIBILITY (read-only)  {now.isoformat()}")
    print("=" * 70)
    print(f"open KXHIGH markets with two-sided quote: {n_markets}")
    print(f"sigma(live, physical prior 1-2d lead) = 3.0F; locked |g|>=8pp, band [0.10,0.90]")
    print(f"FIRING candidates (signal exceeds threshold): {len(candidates)}")
    print()
    crossable = [c for c in candidates if c["edge_after_fee"] > 0]
    print(f"of which CROSSABLE net of worst-case taker fee (edge_after_fee>0): {len(crossable)}")
    print()
    for c in sorted(candidates, key=lambda x: -x["edge_after_fee"])[:25]:
        print(f"  {c['ticker']:<24} {c['city']:>4} {c['hrs']:>5}h {c['kind']:>4} "
              f"f={c['f']:>5} p_model={c['p_model']:.2f} yes_mid={c['yes_mid']:.2f} "
              f"{c['side']:>3}@{c['entry']:.2f} g={c['g']:+.2f} edge_net={c['edge_after_fee']:+.3f} sprd={c['spread_c']}c")
    # capture-phantom read: distribution of |g| (how close is the live mid to the forecast?)
    if candidates:
        gs = sorted(abs(c["g"]) for c in candidates)
        print(f"\n|g| among firing: min={gs[0]:.3f} med={gs[len(gs)//2]:.3f} max={gs[-1]:.3f}")
    print("\nNO ORDERS PLACED (read-only feasibility).")


if __name__ == "__main__":
    main()
