"""v24 weather taker: resolve station bias (methodology-critic BLOCKING #3) with
RECENT real NWS settlements, then re-run the live signal with a correct offset.

For each city: pull recently-SETTLED KXHIGH markets, infer the realized NWS high
per (city,day) from strike crossings (this IS the settlement ground truth), and
compare to the Open-Meteo grid forecast for those days -> the true current
per-city station offset. Then recompute the live divergences with the corrected
offset. If the firing signals collapse, the apparent edge was station bias (NULL);
if real divergence survives, there may be an edge.

Read-only. Run via PowerShell (network).
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import httpx

sys.path.insert(0, "src")
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract  # noqa: E402

CITIES = {
    "NY": (40.7794,-73.9692,"America/New_York"), "CHI": (41.9742,-87.9073,"America/Chicago"),
    "MIA": (25.7959,-80.2870,"America/New_York"), "LAX": (33.9416,-118.4085,"America/Los_Angeles"),
    "DEN": (39.8561,-104.6737,"America/Denver"), "AUS": (30.1975,-97.6664,"America/Chicago"),
    "PHIL": (39.8729,-75.2437,"America/New_York"), "HOU": (29.9902,-95.3368,"America/Chicago"),
}
_MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
DIVERGENCE, BAND_LO, BAND_HI = 0.08, 0.10, 0.90
SIGMA = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0


def norm_cdf(x): return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))
def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

def parse_title(t):
    if not t: return None
    t = t.replace("°","")
    for pat, kind in ((r"be\s*>\s*(\d+)","gt"),(r"be\s*<\s*(\d+)","lt")):
        m = re.search(pat,t)
        if m: return (kind,int(m.group(1)),None)
    m = re.search(r"be\s*(\d+)\s*-\s*(\d+)",t)
    if m: return ("band",int(m.group(1)),int(m.group(2)))
    return None

def occ(ticker):
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})-",ticker)
    if not m: return None
    yy,mmm,dd = m.groups(); return f"20{yy}-{_MONTHS[mmm]:02d}-{int(dd):02d}"

def p_yes(kind,a,b,f,sig):
    if kind=="gt": return 1.0-norm_cdf((a+0.5-f)/sig)
    if kind=="lt": return norm_cdf((a-0.5-f)/sig)
    return norm_cdf((b+0.5-f)/sig)-norm_cdf((a-0.5-f)/sig)


def main():
    now = datetime.now(timezone.utc)
    hc = httpx.Client(timeout=30.0)
    s = Settings()
    # ---- 1. infer realized NWS high per (city,day) from recently settled markets ----
    realized_bounds = defaultdict(lambda: [-math.inf, math.inf])  # (city,od) -> [lo,hi]
    with KalshiClient(s) as cli:
        for city in CITIES:
            n = 0
            for m in cli.paginate("/markets", item_key="markets",
                                  series_ticker=f"KXHIGH{city}", status="settled",
                                  limit=200, max_pages=3):
                res = m.get("result")
                if res not in ("yes","no"): continue
                od = occ(m["ticker"])
                if not od: continue
                # only recent ~14 days
                try:
                    ct = datetime.fromisoformat(m.get("close_time","").replace("Z","+00:00"))
                except Exception:
                    continue
                if (now-ct).days > 16: continue
                p = parse_title(m.get("title",""))
                if not p: continue
                kind,a,b = p
                lo,hi = realized_bounds[(city,od)]
                if kind=="gt":
                    if res=="yes": lo=max(lo,a+1)
                    else: hi=min(hi,a)
                elif kind=="lt":
                    if res=="yes": hi=min(hi,a-1)
                    else: lo=max(lo,a)
                else:
                    if res=="yes": lo=max(lo,a); hi=min(hi,b)
                realized_bounds[(city,od)] = [lo,hi]; n+=1
        # collect (city,od)->realized point
        realized = {k:(lo+hi)/2 for k,(lo,hi) in realized_bounds.items()
                    if math.isfinite(lo) and math.isfinite(hi) and lo<=hi}

        # ---- 2. grid forecast (historical-forecast) for those days; offset=median(realized-grid) ----
        by_city_days = defaultdict(list)
        for (c,od) in realized: by_city_days[c].append(od)
        offset_recent = {}
        grid_cache = {}
        for c,(lat,lon,tz) in CITIES.items():
            ds = sorted(by_city_days.get(c,[]))
            if not ds: continue
            r = hc.get("https://historical-forecast-api.open-meteo.com/v1/forecast", params={
                "latitude":lat,"longitude":lon,"start_date":ds[0],"end_date":ds[-1],
                "daily":"temperature_2m_max","temperature_unit":"fahrenheit","timezone":tz})
            d = r.json().get("daily",{})
            g = dict(zip(d.get("time",[]), d.get("temperature_2m_max",[])))
            grid_cache[c] = g
            diffs = [realized[(c,od)] - g[od] for od in ds if g.get(od) is not None]
            if len(diffs) >= 3:
                offset_recent[c] = sorted(diffs)[len(diffs)//2]

        print("="*70)
        print("STATION OFFSET from RECENT real NWS settlements (realized - grid):")
        for c in sorted(offset_recent):
            ds = by_city_days.get(c,[])
            print(f"  {c}: offset={offset_recent[c]:+.1f}F  (n_days={len(ds)})")
        print()

        # ---- 3. live signal with CORRECTED offset ----
        fc = {}
        for c,(lat,lon,tz) in CITIES.items():
            r = hc.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude":lat,"longitude":lon,"daily":"temperature_2m_max",
                "temperature_unit":"fahrenheit","timezone":tz,"forecast_days":4})
            d = r.json().get("daily",{}); fc[c]=dict(zip(d.get("time",[]),d.get("temperature_2m_max",[])))

        fires = 0; crossable = 0; gmax = 0.0; n_mk = 0
        for city in CITIES:
            if city not in offset_recent: continue
            for m in cli.paginate("/markets", item_key="markets",
                                  series_ticker=f"KXHIGH{city}", status="open", limit=200):
                ya,yb,na = _f(m.get("yes_ask_dollars")),_f(m.get("yes_bid_dollars")),_f(m.get("no_ask_dollars"))
                if not ya or not yb or ya>=1.0 or yb<=0.0: continue
                try: ct=datetime.fromisoformat(m.get("close_time","").replace("Z","+00:00"))
                except Exception: continue
                hrs=(ct-now).total_seconds()/3600.0
                if not (12<=hrs<=60): continue
                od=occ(m["ticker"]); f=fc.get(city,{}).get(od)
                if f is None: continue
                p=parse_title(m.get("title",""))
                if not p: continue
                kind,a,b=p
                n_mk+=1
                fcorr=f+offset_recent[city]
                mid=(ya+yb)/2.0
                pm=min(max(p_yes(kind,a,b,fcorr,SIGMA),0.0),1.0)
                g=pm-mid
                if abs(g)>=DIVERGENCE and BAND_LO<=mid<=BAND_HI:
                    fires+=1; gmax=max(gmax,abs(g))
                    if g>0: edge=(pm-ya)-kalshi_taker_fee_per_contract(ya)
                    else:
                        noa=na or (1-yb); edge=((1-pm)-noa)-kalshi_taker_fee_per_contract(noa)
                    if edge>0: crossable+=1
        print(f"AFTER correct station offset: markets={n_mk} FIRING(|g|>=8pp)={fires} "
              f"crossable={crossable} max|g|={gmax:.3f}")
        print("\n(If firing collapses vs the 29 from the leaky offset, the 'edge' was station bias = NULL.)")


if __name__ == "__main__":
    main()
