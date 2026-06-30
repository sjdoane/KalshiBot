"""v24 DAY-BEFORE window with a FRESH (as-of intraday) spot: the final artifact test.

The day-before backtest (index_vol_backtest_v2.py) used a daily FRED close that is ~2
trading days STALE relative to the trade, plus a 2-day horizon, and produced a fake
+6.94pp OOS edge (decomposed to ~95% "buy NO on narrow bands", driven by the model's
over-dispersion from the stale spot/long horizon). The same-day intraday test (with an
as-of spot) flipped that edge to NEGATIVE. This script applies the as-of fix to the
SAME priority-#1 day-before window: it restricts day-before trades to the PRIOR trading
session (settle_day-1, START_ET..START_ET+WIN ET), uses the prior-session SPY as the
as-of spot (no look-ahead: window-start price predates the trades), and uses the actual
trading-hour horizon to the next-day 4pm close.

If the +6.94pp collapses here too, the day-before edge is conclusively the stale-spot
artifact, not a real day-before-market inefficiency.

Run: .venv/Scripts/python.exe scripts/v24/index_vol_daybefore_freshspot.py [START_ET_HOUR] [WIN_HOURS]
   defaults: START_ET_HOUR=11 WIN_HOURS=2 (prior-session 11:00-13:00 ET trades).
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
from datetime import datetime, timezone

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

# UTC offset (hours) for ET on a given date: EDT=-4 (Mar..Nov), EST=-5 otherwise.
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")


def et_to_utc_ts(diso, et_hour):
    y, m, d = (int(x) for x in diso.split("-"))
    dt = datetime(y, m, d, et_hour, 0, tzinfo=ET)
    return dt.timestamp()


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
        for dd in reversed(days):
            if dd < diso: return dd
        return None

    def ratio_asof(diso):
        d = prev_trading_day(diso); steps = 0
        while d is not None and steps < 8:
            spc = sp.get(d); spyc = spy.get(d, {}).get(str(CLOSE_ET_HOUR))
            if spc is not None and spyc: return spc / spyc
            d = prev_trading_day(d); steps += 1
        return None

    def model_prob(kind, a, b, spot, sig, T):
        den = sig*math.sqrt(T)
        def pa(K): return ncdf((math.log(spot/K)+(R-0.5*sig*sig)*T)/den)
        if kind == "gt": mp = pa(a)
        elif kind == "lt": mp = 1.0-pa(a)
        else: mp = max(pa(a)-pa(b), 0.0)
        return min(max(mp, 0.0), 1.0)

    fees = {"reduced_0.035": 0.035, "full_0.07": 0.07}
    out = {f: {"train": [], "oos": []} for f in fees}
    cl = {f: {"train": [], "oos": []} for f in fees}
    outv = {f: {"train": [], "oos": []} for f in fees}
    clv = {f: {"train": [], "oos": []} for f in fees}
    diag = []; by_ks = {}
    n_have = 0; n_traded = 0; n_skip = 0

    for tk, m in pull.items():
        p = parse_title(m["title"])
        if not p: continue
        kind, a, b = p
        res = m["result"]
        cd = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        settle = cd.date().isoformat()
        # prior trading session = the day-before window
        pday = prev_trading_day(settle)
        if pday is None: continue
        # trade window on pday: START_ET .. START_ET+WIN
        win_start_ts = et_to_utc_ts(pday, START_ET_HOUR)
        win_end_ts = win_start_ts + WIN_HOURS * 3600
        tot_c = tot_pc = 0.0
        for ts, c, yp in m["trades"]:
            tt = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if win_start_ts <= tt <= win_end_ts:
                tot_c += c; tot_pc += c * yp
        if tot_c <= 0:
            continue
        p_mkt = tot_pc / tot_c
        # as-of spot: SPY at START_ET on pday * prior-day ratio
        spyv = spy.get(pday, {}).get(str(START_ET_HOUR))
        ratio = ratio_asof(pday)
        if spyv is None or ratio is None:
            n_skip += 1; continue
        spot = spyv * ratio
        rv = rvol(pday); vx = vix.get(pday)
        if rv is None or vx is None: continue
        vx = vx / 100.0
        # horizon: rest of pday session + full settle-day session(s)
        gap = idx[max(d for d in days if d <= settle)] - idx[pday]
        T_hours = (CLOSE_ET_HOUR - START_ET_HOUR) + TRADING_HRS_PER_DAY * (gap - 1) + TRADING_HRS_PER_DAY
        T = T_hours / (TRADING_HRS_PER_DAY * 252.0)
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
                key = (kind, side); by_ks.setdefault(key, {"pnl": [], "cl": []})
                by_ks[key]["pnl"].append(gross - fee(entry, 0.035)); by_ks[key]["cl"].append(settle)
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
    print(f"v24 DAY-BEFORE window, FRESH prior-session spot  window={START_ET_HOUR}:00 ET"
          f" (prior day)  settle next-day 16:00")
    print("=" * 74)
    print(f"markets with prior-session price + as-of spot + RV/VIX: {n_have}; "
          f"realized fires: {n_traded}; skipped(no SPY): {n_skip}")
    if diag:
        print(f"DIAGNOSTIC median(Kalshi_price - VIX_model_P) = {st.median(diag)*100:+.2f}pp (n={len(diag)})")

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

    report("B: REALIZED model", out, cl)
    report("C: VIX control", outv, clv)
    print("\nOOS realized edge by (kind, side):")
    for key in sorted(by_ks):
        bb = by_ks[key]; k = len(set(bb["cl"]))
        if len(bb["pnl"]) >= 2 and k >= 2:
            mean, lo, hi, _ = cluster_bootstrap_mean_ci(bb["pnl"], bb["cl"], n_resamples=4000, ci=0.95, rng_seed=42)
            print(f"  {key[0]:5s} {key[1]:4s} fills={len(bb['pnl']):4d} days={k:3d} {mean*100:+.2f}pp [{lo*100:+.2f},{hi*100:+.2f}]")
    rb = out["reduced_0.035"]["oos"]; rbc = cl["reduced_0.035"]["oos"]
    vc = outv["reduced_0.035"]["oos"]; vcc = clv["reduced_0.035"]["oos"]
    print("\nBINDING GATE (reduced fee, OOS):")
    if len(rb) >= 2 and len(set(rbc)) >= 2 and len(vc) >= 2 and len(set(vcc)) >= 2:
        rm, rlo, rhi, _ = cluster_bootstrap_mean_ci(rb, rbc, n_resamples=5000, ci=0.95, rng_seed=42)
        vm, vlo, vhi, _ = cluster_bootstrap_mean_ci(vc, vcc, n_resamples=5000, ci=0.95, rng_seed=42)
        print(f"  realized OOS={rm*100:+.2f}pp CI[{rlo*100:+.2f},{rhi*100:+.2f}] lower>0={rlo>0}")
        print(f"  VIX ctrl OOS={vm*100:+.2f}pp CI[{vlo*100:+.2f},{vhi*100:+.2f}]")
        print(f"  realized beats VIX: {rm>vm} (wedge {(rm-vm)*100:+.2f}pp); GATE PASS={(rlo>0) and (rm>vm)}")


if __name__ == "__main__":
    main()
