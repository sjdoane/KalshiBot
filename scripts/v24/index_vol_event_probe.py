"""v24 EVENT-VOL probe (pivot): is the vol-selling edge larger on FOMC days?

The handoff's designated pivot if the always-on index leg stalls: the variance risk
premium is larger / less arbed around scheduled events. On KXINX (settles 4pm ET) the
only cleanly PRE-event same-day window is FOMC days: the FOMC announcement is 2:00pm ET,
AFTER the 11:00-13:00 ET trade window and BEFORE the 4pm settle, so the 11:00 window
prices the FOMC uncertainty that then resolves by settle. (CPI/NFP release 8:30am ET =
before the window = post-event, not harvestable same-day, so excluded.)

Reuses the artifact-free same-day pipeline (as-of intraday SPY spot + correct horizon).
Reports the realized-model + VIX-control edge on FOMC days vs non-FOMC days. HONEST
caveat: ~14 FOMC settlement days in 2024-10..2026-06 = thin; this is an exploratory
read, not a powered gate. A striking positive on FOMC days motivates a deeper look; a
flat/negative read confirms the financial-vol wall.

Run: .venv/Scripts/python.exe scripts/v24/index_vol_event_probe.py
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "src")
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

SCRATCH = r"C:/Users/SamJD/AppData/Local/Temp/claude/C--Users-SamJD-OneDrive-Desktop-AI-Projects/f815708f-7e33-4720-923a-6914b4ca23ca/scratchpad"
FRED = SCRATCH + "/fred_sp500_vix.json"
PULL = SCRATCH + "/kxinx_pull.json"
SPY = SCRATCH + "/spy_intraday.json"
ET = ZoneInfo("America/New_York")

# FOMC announcement (meeting end) dates 2024-10 .. 2026-06 (public scheduled calendar)
FOMC_DAYS = {
    "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
}

DIVERGENCE = 0.05
BAND_LO, BAND_HI = 0.10, 0.90
SPREAD_HAIRCUT = 0.02
R = 0.04
RV_WINDOW = 10
CLOSE_ET_HOUR = 16
START_ET_HOUR = 11
WIN_HOURS = 2.0
TRADING_HRS = 6.5


def et_to_utc_ts(diso, et_hour):
    y, m, d = (int(x) for x in diso.split("-"))
    return datetime(y, m, d, et_hour, 0, tzinfo=ET).timestamp()


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

    def rvol(sd):
        i = idx.get(sd)
        if i is None or i < RV_WINDOW: return None
        rets = [math.log(sp[days[j]] / sp[days[j-1]]) for j in range(i-RV_WINDOW+1, i+1)]
        mu = sum(rets)/len(rets)
        return math.sqrt(sum((r-mu)**2 for r in rets)/(len(rets)-1) * 252)

    def prev_day(diso):
        for dd in reversed(days):
            if dd < diso: return dd
        return None

    def ratio_asof(diso):
        d = prev_day(diso); steps = 0
        while d is not None and steps < 8:
            spc = sp.get(d); spyc = spy.get(d, {}).get(str(CLOSE_ET_HOUR))
            if spc is not None and spyc: return spc / spyc
            d = prev_day(d); steps += 1
        return None

    def mprob(kind, a, b, spot, sig, T):
        den = sig*math.sqrt(T)
        def pa(K): return ncdf((math.log(spot/K)+(R-0.5*sig*sig)*T)/den)
        if kind == "gt": return min(max(pa(a), 0), 1)
        if kind == "lt": return min(max(1-pa(a), 0), 1)
        return min(max(pa(a)-pa(b), 0), 1)

    T = (CLOSE_ET_HOUR - START_ET_HOUR) / (TRADING_HRS * 252.0)
    # group -> {realized:{pnl,cl}, vix:{pnl,cl}}
    groups = {"FOMC": {"r": ([], []), "v": ([], [])},
              "non-FOMC": {"r": ([], []), "v": ([], [])}}

    for tk, m in pull.items():
        p = parse_title(m["title"])
        if not p: continue
        kind, a, b = p
        res = m["result"]
        cd = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        settle = cd.date().isoformat()
        ws = et_to_utc_ts(settle, START_ET_HOUR)
        we = ws + WIN_HOURS * 3600
        tc = tp = 0.0
        for ts, c, yp in m["trades"]:
            tt = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if ws <= tt <= we: tc += c; tp += c*yp
        if tc <= 0: continue
        pm = tp/tc
        spyv = spy.get(settle, {}).get(str(START_ET_HOUR)); ratio = ratio_asof(settle)
        if spyv is None or ratio is None: continue
        spot = spyv*ratio
        pd = prev_day(settle)
        if pd is None: continue
        rv = rvol(pd); vx = vix.get(pd)
        if rv is None or vx is None: continue
        vx = vx/100.0
        if not (BAND_LO <= pm <= BAND_HI): continue
        grp = "FOMC" if settle in FOMC_DAYS else "non-FOMC"
        for tag, sig in (("r", rv), ("v", vx)):
            mp = mprob(kind, a, b, spot, sig, T)
            g = mp - pm
            if abs(g) >= DIVERGENCE:
                if g > 0: entry = min(pm+SPREAD_HAIRCUT, 0.99); win = (res == "yes")
                else: entry = min((1-pm)+SPREAD_HAIRCUT, 0.99); win = (res == "no")
                pnl = ((1-entry) if win else -entry) - fee(entry, 0.035)
                groups[grp][tag][0].append(pnl); groups[grp][tag][1].append(settle)

    print("=" * 70)
    print("v24 EVENT-VOL probe: FOMC-day vs non-FOMC same-day 11:00-13:00 ET "
          "(pre-2pm), reduced fee 0.035")
    print("=" * 70)
    print("HONEST CAVEAT: FOMC settlement days are few (~14); this is an exploratory "
          "read, not a powered gate.\n")
    for grp in ("FOMC", "non-FOMC"):
        print(f"[{grp}]")
        for tag, name in (("r", "realized model"), ("v", "VIX control ")):
            vals, cl = groups[grp][tag]
            k = len(set(cl))
            line = f"  {name}: fills={len(vals):4d} days={k:3d}"
            if len(vals) >= 2 and k >= 2:
                mean, lo, hi, _ = cluster_bootstrap_mean_ci(vals, cl, n_resamples=5000, ci=0.95, rng_seed=42)
                line += f" net={mean*100:+.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}]pp"
            print(line)
    print("\nInterpretation: a real event-VRP would show FOMC-day realized/VIX net "
          "MATERIALLY ABOVE non-FOMC (and ideally > 0).")


if __name__ == "__main__":
    main()
