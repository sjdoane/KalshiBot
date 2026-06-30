"""v24 index volatility-mispricing taker: kill-filter backtest (KXINX / S&P 500).

Per the plan critic (PROCEED-WITH-CHANGES, ~6%): index-only (crypto dead per v23),
cheap kill-filter not a 6-feature build, HALF taker fee (0.035), and the decisive
test is whether Kalshi prices vol like the market (capture phantom) vs leaves a
harvestable variance-risk-premium net of the half-fee.

Two outputs:
  (A) CAPTURE-PHANTOM DIAGNOSTIC: back out the Kalshi-implied vol per threshold
      market (day-before window), compare to VIX (the market's vol) and trailing
      realized vol. If Kalshi-implied ~ VIX, the vol is already priced (NULL).
  (B) VRP / vol-mispricing BACKTEST: trade toward a realized-vol model's P(strike)
      vs the Kalshi price, net of the HALF taker fee, OOS, event-clustered by
      settlement date.

Data: Becker KXINX (prices/outcomes) + FRED SP500 (the actual index, 4pm-aligned
to settlement) + FRED VIXCLS. Trade window = 12-36h before the 4pm close (the
day-before window, where FRED's daily close is an accurate spot; same-day KXINX is
the most MM-saturated window = acute capture phantom, excluded).
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import duckdb

sys.path.insert(0, "src")
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

BASE = r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/prediction-market-analysis/data/kalshi"
FRED = r"C:/Users/SamJD/AppData/Local/Temp/claude/C--Users-SamJD-OneDrive-Desktop-AI-Projects/6f4cdb0b-4fda-43e5-94a1-c905df9be740/scratchpad/fred_sp500_vix.json"
_MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
TRAIN_END = date(2025, 7, 1)
DIVERGENCE = 0.05
BAND_LO, BAND_HI = 0.10, 0.90
SPREAD_HAIRCUT = 0.02  # index books; conservative
RV_WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 10  # trailing days for realized vol


def ncdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
def ninv(p):
    # Acklam inverse normal CDF
    p = min(max(p, 1e-9), 1 - 1e-9)
    a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00]
    b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,6.680131188771972e+01,-1.328068155288572e+01]
    c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,-2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00]
    d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00]
    pl=0.02425
    if p<pl:
        q=math.sqrt(-2*math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p<=1-pl:
        q=p-0.5; r=q*q; return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q=math.sqrt(-2*math.log(1-p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def parse_title(t):
    if not t: return None
    m=re.search(r"be above ([\d.]+)",t)
    if m: return ("gt",float(m.group(1)),None)
    m=re.search(r"be below ([\d.]+)",t)
    if m: return ("lt",float(m.group(1)),None)
    m=re.search(r"between ([\d.]+) and ([\d.]+)",t)
    if m: return ("band",float(m.group(1)),float(m.group(2)))
    return None


def taker_fee_half(p):  # index reduced taker 0.035 quadratic, worst-case
    return math.ceil(3.5 * p * (1 - p)) / 100.0


def main():
    raw = json.load(open(FRED, encoding="utf-8-sig"))
    sp = {d: v for d, v in raw["SP500"].items()}
    vix = {d: v for d, v in raw["VIXCLS"].items()}
    days = sorted(sp)  # trading days
    idx = {d: i for i, d in enumerate(days)}

    def prior_trading_day(dt: date):
        s = dt.isoformat()
        # largest trading day strictly before dt
        lo, hi = 0, len(days) - 1; ans = None
        for dd in reversed(days):
            if dd < s:
                ans = dd; break
        return ans

    def realized_vol(tradeday):
        i = idx.get(tradeday)
        if i is None or i < RV_WINDOW: return None
        rets = [math.log(sp[days[j]] / sp[days[j-1]]) for j in range(i - RV_WINDOW + 1, i + 1)]
        mu = sum(rets)/len(rets)
        var = sum((r-mu)**2 for r in rets)/(len(rets)-1)
        return math.sqrt(var * 252)  # annualized

    con = duckdb.connect(); con.execute("SET TimeZone='UTC'")
    rows = con.execute(f"""
        WITH m AS (
            SELECT ticker, title, result, close_time
            FROM read_parquet('{BASE}/markets/*.parquet')
            WHERE ticker LIKE 'KXINX-%' AND result IN ('yes','no') AND close_time IS NOT NULL
        ),
        tr AS (
            SELECT t.ticker,
                   sum(t.yes_price*t.count)::DOUBLE/nullif(sum(t.count),0) AS vwap_c, count(*) AS n
            FROM read_parquet('{BASE}/trades/*.parquet') t JOIN m USING (ticker)
            WHERE date_diff('hour', t.created_time, m.close_time) BETWEEN 12 AND 36
            GROUP BY t.ticker
        )
        SELECT m.ticker, m.title, m.result, m.close_time, tr.vwap_c, tr.n
        FROM m LEFT JOIN tr ON m.ticker=tr.ticker
    """).fetchall()

    diag_pmkt_minus_vix=[]; diag_rv_minus_vix=[]  # capture-phantom diagnostic
    out={"train":[],"oos":[]}; clusters={"train":[],"oos":[]}        # realized-vol model
    outv={"train":[],"oos":[]}; clustersv={"train":[],"oos":[]}      # VIX model (control)
    n_have=0; n_traded=0
    def model_prob(kind,a,b,spot,sig_h):
        def p_above(K): return 1.0-ncdf((math.log(K/spot)+0.5*sig_h*sig_h)/sig_h)
        if kind=="gt": mp=p_above(a)
        elif kind=="lt": mp=1.0-p_above(a)
        else: mp=max(p_above(a)-p_above(b),0.0)
        return min(max(mp,0.0),1.0)
    for ticker,title,result,close_time,vwap_c,n in rows:
        p=parse_title(title)
        if not p or vwap_c is None or n is None or n<1: continue
        kind,a,b=p
        settle_date=close_time.date()
        tradeday=prior_trading_day(settle_date)
        if tradeday is None: continue
        spot=sp.get(tradeday)
        if spot is None: continue
        rv=realized_vol(tradeday)
        vx=vix.get(tradeday)
        if rv is None or vx is None: continue
        vx=vx/100.0
        n_have+=1
        T=1.0/252.0
        p_mkt=vwap_c/100.0
        model_p=model_prob(kind,a,b,spot,rv*math.sqrt(T))      # realized-vol model
        vix_p  =model_prob(kind,a,b,spot,vx*math.sqrt(T))      # VIX (market) model
        # diagnostic: does Kalshi price at VIX (capture phantom) and is realized < VIX (VRP)?
        diag_pmkt_minus_vix.append(p_mkt-vix_p)
        diag_rv_minus_vix.append(model_p-vix_p)
        if not (BAND_LO<=p_mkt<=BAND_HI): continue
        w="train" if settle_date<TRAIN_END else "oos"
        # realized-vol model trade
        g=model_p-p_mkt
        if abs(g)>=DIVERGENCE:
            n_traded+=1
            if g>0: entry=min(p_mkt+SPREAD_HAIRCUT,0.99); win=(result=="yes")
            else: entry=min((1.0-p_mkt)+SPREAD_HAIRCUT,0.99); win=(result=="no")
            out[w].append((1.0-entry if win else -entry)-taker_fee_half(entry)); clusters[w].append(settle_date.isoformat())
        # VIX model trade (control: does the edge persist using the MARKET's own vol?)
        gv=vix_p-p_mkt
        if abs(gv)>=DIVERGENCE:
            if gv>0: entry=min(p_mkt+SPREAD_HAIRCUT,0.99); win=(result=="yes")
            else: entry=min((1.0-p_mkt)+SPREAD_HAIRCUT,0.99); win=(result=="no")
            outv[w].append((1.0-entry if win else -entry)-taker_fee_half(entry)); clustersv[w].append(settle_date.isoformat())

    import statistics as st
    print("="*70)
    print(f"v24 INDEX VOL-MISPRICING TAKER (KXINX / S&P 500, half-fee)  RV_WINDOW={RV_WINDOW}")
    print("="*70)
    print(f"markets with day-before price + FRED spot/RV/VIX: {n_have}; realized-model traded: {n_traded}")
    if diag_pmkt_minus_vix:
        print(f"\n(A) CAPTURE-PHANTOM DIAGNOSTIC (n={len(diag_pmkt_minus_vix)} markets):")
        print(f"  median (Kalshi_price - VIX_model_P) = {st.median(diag_pmkt_minus_vix)*100:+.2f}pp "
              f"(near 0 => Kalshi prices the range at the VIX-implied vol = capture phantom)")
        print(f"  median (realized_model_P - VIX_model_P) = {st.median(diag_rv_minus_vix)*100:+.2f}pp "
              f"(the VRP wedge: realized vol vs VIX)")
    def report(label, o, c):
        print(f"\n({label}) net of HALF taker fee + {SPREAD_HAIRCUT} spread:")
        for w in ("train","oos"):
            vals=o[w]; cl=c[w]; k=len(set(cl))
            line=f"  {w.upper()}: fills={len(vals)} clusters(days)={k}"
            if len(vals)>=2 and k>=2:
                mean,lo,hi,kk=cluster_bootstrap_mean_ci(vals,cl,n_resamples=5000,ci=0.95,rng_seed=42)
                line+=f"  net={mean*100:+.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}]pp PASS(lo>0)={lo>0}"
            print(line)
    report("B: REALIZED-vol model (the strategy)", out, clusters)
    report("C: VIX model CONTROL (trade toward the MARKET's own vol; if this also wins, Kalshi misprices vs VIX too)", outv, clustersv)


if __name__ == "__main__":
    main()
