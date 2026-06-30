"""v24 SAME-DAY intraday vol-mispricing test (KXINX / S&P 500), the decisive
artifact + capturable-window test.

The day-before backtest (index_vol_backtest_v2.py) showed a ~6pp OOS edge that BOTH
the realized model AND the VIX control catch equally (tied = NO realized-vol edge per
the pre-registered guardrail). Decomposition showed it is ~95% "buy NO on narrow
bands" fired by a model whose horizon comes from a 2-day-stale daily FRED spot (T=2d
when the trade is ~1d out), which over-disperses the model and makes near-spot bands
look under-priced (the naive-model-worse-than-market trap).

This script removes BOTH artifacts using the SAME-DAY window (90% of KXINX volume),
an AS-OF intraday spot, and the CORRECT short horizon:
  - As-of spot (SPX) = SPY at the window-start ET hour (Massive 5-min->hourly opens),
    converted via the PRIOR trading day's SPX/SPY ratio (FRED SP500 close / SPY 4pm).
    No look-ahead: the window-start price predates every trade in the window.
  - Horizon T = trading-hours from the window start to the 4pm close (e.g. 11:00->16:00
    = 5h), in trading-time years (6.5h/day, 252d/yr). NOT a 2-day daily horizon.
  - Vol input UNCHANGED (trailing 10-day daily RV, and VIX) to isolate the spot+horizon
    fix as the only difference from the day-before test.
  - Same band [0.10,0.90], divergence 0.05, OOS split 2025-07-01, cluster-by-day
    bootstrap, both fee bounds (reduced 0.035 + conservative full 0.07).

If the band-NO edge collapses here, it was the daily-stale-spot/T artifact. If it
survives with an as-of spot AND realized still does NOT beat the VIX control, it is at
most a general short-band-premium (short-variance) position, not a realized-vol edge,
and is the most MM-saturated (capture-phantom-prone) window. The VIX control remains
the lie detector.

Run: .venv/Scripts/python.exe scripts/v24/index_vol_intraday.py [START_ET_HOUR] [WIN_HOURS]
   defaults: START_ET_HOUR=11  WIN_HOURS=2  (trade window 11:00-13:00 ET, settle 16:00)
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

SCRATCH = r"C:/Users/SamJD/AppData/Local/Temp/claude/C--Users-SamJD-OneDrive-Desktop-AI-Projects/f815708f-7e33-4720-923a-6914b4ca23ca/scratchpad"
FRED = SCRATCH + "/fred_sp500_vix.json"
PULL = SCRATCH + "/kxinx_pull.json"
SPY = SCRATCH + "/spy_intraday.json"

TRAIN_END = "2025-07-01"
DIVERGENCE = 0.05
BAND_LO, BAND_HI = 0.10, 0.90
SPREAD_HAIRCUT = 0.02
R = 0.04
RV_WINDOW = 10
CLOSE_ET_HOUR = 16
START_ET_HOUR = int(sys.argv[1]) if len(sys.argv) > 1 else 11
WIN_HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
TRADING_HRS_PER_DAY = 6.5


def ncdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def parse_title(t):
    m = re.search(r"be above ([\d.]+)", t)
    if m: return ("gt", float(m.group(1)), None)
    m = re.search(r"be below ([\d.]+)", t)
    if m: return ("lt", float(m.group(1)), None)
    m = re.search(r"between ([\d.]+) and ([\d.]+)", t)
    if m: return ("band", float(m.group(1)), float(m.group(2)))
    return None


def fee(p, coeff): return math.ceil(coeff * 100.0 * p * (1 - p)) / 100.0


def main():
    raw = json.load(open(FRED, encoding="utf-8-sig"))
    sp = raw["SP500"]; vix = raw["VIXCLS"]
    days = sorted(sp); idx = {d: i for i, d in enumerate(days)}
    spy = json.load(open(SPY, encoding="utf-8"))
    pull = json.load(open(PULL, encoding="utf-8"))["markets"]

    def rvol(spot_day):
        i = idx.get(spot_day)
        if i is None or i < RV_WINDOW: return None
        rets = [math.log(sp[days[j]] / sp[days[j-1]]) for j in range(i-RV_WINDOW+1, i+1)]
        mu = sum(rets)/len(rets)
        return math.sqrt(sum((r-mu)**2 for r in rets)/(len(rets)-1) * 252)

    def prev_trading_day(diso):
        ans = None
        for dd in reversed(days):
            if dd < diso: ans = dd; break
        return ans

    def spx_spot(diso):
        """As-of SPX at START_ET_HOUR on day diso = SPY(diso, start_hour) * ratio,
        ratio = SPX_close/SPY_close on the most recent prior day (no look-ahead)."""
        day_spy = spy.get(diso)
        if not day_spy: return None
        sval = day_spy.get(str(START_ET_HOUR))
        if sval is None: return None
        # prior-day ratio
        pj = prev_trading_day(diso)
        # walk back until we have both FRED close and SPY 4pm on the same prior day
        d = pj
        ratio = None
        steps = 0
        while d is not None and steps < 8:
            sp_close = sp.get(d)
            sd = spy.get(d, {})
            spy_close = sd.get(str(CLOSE_ET_HOUR))
            if sp_close is not None and spy_close:
                ratio = sp_close / spy_close
                break
            d = prev_trading_day(d); steps += 1
        if ratio is None: return None
        return sval * ratio

    def model_prob(kind, a, b, spot, sig, T):
        den = sig*math.sqrt(T)
        def pa(K): return ncdf((math.log(spot/K)+(R-0.5*sig*sig)*T)/den)
        if kind == "gt": mp = pa(a)
        elif kind == "lt": mp = 1.0-pa(a)
        else: mp = max(pa(a)-pa(b), 0.0)
        return min(max(mp, 0.0), 1.0)

    T = (CLOSE_ET_HOUR - START_ET_HOUR) / (TRADING_HRS_PER_DAY * 252.0)

    fees = {"reduced_0.035": 0.035, "full_0.07": 0.07}
    out = {f: {"train": [], "oos": []} for f in fees}
    cl = {f: {"train": [], "oos": []} for f in fees}
    outv = {f: {"train": [], "oos": []} for f in fees}
    clv = {f: {"train": [], "oos": []} for f in fees}
    diag = []
    by_kind_side = {}
    n_have = 0; n_traded = 0; n_no_spot = 0

    for tk, m in pull.items():
        p = parse_title(m["title"])
        if not p: continue
        kind, a, b = p
        res = m["result"]
        cd = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        settle = cd.date().isoformat()
        cts = cd.timestamp()
        # same-day window: [close - (CLOSE-START)h, close - (CLOSE-START-WIN)h]
        win_start_ts = cts - (CLOSE_ET_HOUR - START_ET_HOUR) * 3600
        win_end_ts = win_start_ts + WIN_HOURS * 3600
        tot_c = tot_pc = 0.0
        for ts, c, yp in m["trades"]:
            tt = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if win_start_ts <= tt <= win_end_ts:
                tot_c += c; tot_pc += c * yp
        if tot_c <= 0: continue
        p_mkt = tot_pc / tot_c
        spot = spx_spot(settle)
        if spot is None:
            n_no_spot += 1
            continue
        spot_day = prev_trading_day(settle)  # for the trailing-RV / VIX (no look-ahead)
        if spot_day is None: continue
        rv = rvol(spot_day); vx = vix.get(spot_day)
        if rv is None or vx is None: continue
        vx = vx / 100.0
        n_have += 1
        model_p = model_prob(kind, a, b, spot, rv, T)
        vix_p = model_prob(kind, a, b, spot, vx, T)
        diag.append(p_mkt - vix_p)
        if not (BAND_LO <= p_mkt <= BAND_HI): continue
        w = "train" if settle < TRAIN_END else "oos"

        g = model_p - p_mkt
        if abs(g) >= DIVERGENCE:
            n_traded += 1
            if g > 0:
                entry = min(p_mkt+SPREAD_HAIRCUT, 0.99); win = (res == "yes"); side = "YES"
            else:
                entry = min((1-p_mkt)+SPREAD_HAIRCUT, 0.99); win = (res == "no"); side = "NO"
            gross = (1-entry) if win else -entry
            for fn, co in fees.items():
                out[fn][w].append(gross - fee(entry, co)); cl[fn][w].append(settle)
            if w == "oos":
                k = (kind, side)
                by_kind_side.setdefault(k, {"pnl": [], "cl": []})
                by_kind_side[k]["pnl"].append(gross - fee(entry, 0.035))
                by_kind_side[k]["cl"].append(settle)

        gv = vix_p - p_mkt
        if abs(gv) >= DIVERGENCE:
            if gv > 0:
                entry = min(p_mkt+SPREAD_HAIRCUT, 0.99); win = (res == "yes")
            else:
                entry = min((1-p_mkt)+SPREAD_HAIRCUT, 0.99); win = (res == "no")
            gross = (1-entry) if win else -entry
            for fn, co in fees.items():
                outv[fn][w].append(gross - fee(entry, co)); clv[fn][w].append(settle)

    print("=" * 74)
    print(f"v24 SAME-DAY INTRADAY vol-mispricing  window={START_ET_HOUR}:00-"
          f"{START_ET_HOUR+int(WIN_HOURS)}:00 ET  settle 16:00  T={T*252*TRADING_HRS_PER_DAY:.1f}h")
    print("=" * 74)
    print(f"markets with same-day price + as-of SPX spot + RV/VIX: {n_have}; "
          f"realized fires: {n_traded}; skipped(no SPY spot): {n_no_spot}")
    if diag:
        print(f"\nDIAGNOSTIC median(Kalshi_price - VIX_model_P) = {st.median(diag)*100:+.2f}pp "
              f"(n={len(diag)})")

    def report(label, o, c):
        print(f"\n({label})")
        for fn in fees:
            print(f"  fee={fn}:")
            for w in ("train", "oos"):
                vals = o[fn][w]; cids = c[fn][w]; k = len(set(cids))
                line = f"    {w.upper():5s}: fills={len(vals):4d} clusters={k:3d}"
                if len(vals) >= 2 and k >= 2:
                    mean, lo, hi, _ = cluster_bootstrap_mean_ci(vals, cids, n_resamples=5000, ci=0.95, rng_seed=42)
                    line += f"  net={mean*100:+.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}]pp PASS(lo>0)={lo>0}"
                print(line)

    report("B: REALIZED model (strategy)", out, cl)
    report("C: VIX control (must NOT match B OOS)", outv, clv)

    print("\nOOS realized-model edge by (kind, side):")
    for key in sorted(by_kind_side):
        bb = by_kind_side[key]; k = len(set(bb["cl"]))
        if len(bb["pnl"]) >= 2 and k >= 2:
            mean, lo, hi, _ = cluster_bootstrap_mean_ci(bb["pnl"], bb["cl"], n_resamples=4000, ci=0.95, rng_seed=42)
            print(f"  {key[0]:5s} {key[1]:4s} fills={len(bb['pnl']):4d} days={k:3d} {mean*100:+.2f}pp [{lo*100:+.2f},{hi*100:+.2f}]")
        else:
            print(f"  {key[0]:5s} {key[1]:4s} fills={len(bb['pnl']):4d} days={k:3d} (too few)")

    print("\n" + "=" * 74)
    print(f"BINDING GATE (reduced 0.035 fee, OOS), same-day window {START_ET_HOUR}:00 ET:")
    rb = out["reduced_0.035"]["oos"]; rbc = cl["reduced_0.035"]["oos"]
    vc = outv["reduced_0.035"]["oos"]; vcc = clv["reduced_0.035"]["oos"]
    if len(rb) >= 2 and len(set(rbc)) >= 2 and len(vc) >= 2 and len(set(vcc)) >= 2:
        rm, rlo, rhi, _ = cluster_bootstrap_mean_ci(rb, rbc, n_resamples=5000, ci=0.95, rng_seed=42)
        vm, vlo, vhi, _ = cluster_bootstrap_mean_ci(vc, vcc, n_resamples=5000, ci=0.95, rng_seed=42)
        print(f"  realized OOS net={rm*100:+.2f}pp CI[{rlo*100:+.2f},{rhi*100:+.2f}]  lower>0={rlo>0}")
        print(f"  VIX ctrl OOS net={vm*100:+.2f}pp CI[{vlo*100:+.2f},{vhi*100:+.2f}]")
        print(f"  realized beats VIX OOS: {rm>vm} (wedge {(rm-vm)*100:+.2f}pp)")
        print(f"  GATE PASS = {(rlo>0) and (rm>vm)}")
    else:
        print("  insufficient OOS clusters")


if __name__ == "__main__":
    main()
