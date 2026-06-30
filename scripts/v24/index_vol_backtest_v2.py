"""v24 index vol-mispricing taker, POWER-UP v2 (KXINX / S&P 500, half-fee).

Same pre-registered methodology as scripts/v24/index_vol_backtest.py, but reads the
FULL KXINX history pulled from the live Kalshi API (scratchpad/kxinx_pull.json,
post-2024-10, ~4200 near-money markets / ~440 settlement days) instead of the Becker
slice (~280 events). This is the primary power lever: roughly 4-5x more settlement-day
clusters, the cleanest way to tighten the OOS CI WITHOUT p-hacking.

What is unchanged from the prior (no criterion tuning):
  - Day-before window = trades 12-36h before the 4pm close; VWAP = count-weighted yes.
  - Clean no-look-ahead spot = last FRED close STRICTLY before the trade-window start.
  - Actual trading-day horizon spot_day -> settle_date; drift R=0.04.
  - Tradeable band [0.10, 0.90] on the Kalshi price; divergence threshold 0.05.
  - Spread haircut 0.02; cluster bootstrap by settlement day; OOS split 2025-07-01.
  - The VIX-model CONTROL is the honesty detector: a real realized-vol edge MUST beat
    the VIX control OOS, else there is no realized-vol edge (only a general VRP any
    vol model catches).

What is ADDED (correctness / honesty, not tuning):
  - Conservative full-0.07 taker-fee run reported alongside the reduced 0.035, per the
    handoff worst-case rule. The binding gate is on the reduced fee (the claimed KXINX
    taker); the full fee is the conservative bound.

Run: .venv/Scripts/python.exe scripts/v24/index_vol_backtest_v2.py [RV_WINDOW]
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

TRAIN_END = "2025-07-01"          # pre-registered OOS split (unchanged)
DIVERGENCE = 0.05                  # |model_p - p_mkt| to fire (unchanged)
BAND_LO, BAND_HI = 0.10, 0.90     # tradeable Kalshi-price band (unchanged)
SPREAD_HAIRCUT = 0.02             # conservative index-book spread (unchanged)
WIN_LO_H, WIN_HI_H = 12, 36       # day-before trade window in hours (unchanged)
R = 0.04                          # annualized drift (immaterial at short horizon)
RV_WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 10


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def parse_title(t):
    if not t:
        return None
    m = re.search(r"be above ([\d.]+)", t)
    if m:
        return ("gt", float(m.group(1)), None)
    m = re.search(r"be below ([\d.]+)", t)
    if m:
        return ("lt", float(m.group(1)), None)
    m = re.search(r"between ([\d.]+) and ([\d.]+)", t)
    if m:
        return ("band", float(m.group(1)), float(m.group(2)))
    return None


def taker_fee(p, coeff):
    """Kalshi taker fee per contract: ceil(coeff*100 * P*(1-P)) cents / 100.
    coeff 0.035 = reduced KXINX taker; coeff 0.07 = full taker (conservative)."""
    return math.ceil(coeff * 100.0 * p * (1.0 - p)) / 100.0


def main():
    raw = json.load(open(FRED, encoding="utf-8-sig"))
    sp = raw["SP500"]
    vix = raw["VIXCLS"]
    days = sorted(sp)
    idx = {d: i for i, d in enumerate(days)}

    def realized_vol(spot_day):
        i = idx.get(spot_day)
        if i is None or i < RV_WINDOW:
            return None
        rets = [math.log(sp[days[j]] / sp[days[j - 1]]) for j in range(i - RV_WINDOW + 1, i + 1)]
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var * 252)

    def model_prob(kind, a, b, spot, sig, T):
        den = sig * math.sqrt(T)

        def p_above(K):
            return ncdf((math.log(spot / K) + (R - 0.5 * sig * sig) * T) / den)

        if kind == "gt":
            mp = p_above(a)
        elif kind == "lt":
            mp = 1.0 - p_above(a)
        else:
            mp = max(p_above(a) - p_above(b), 0.0)
        return min(max(mp, 0.0), 1.0)

    pull = json.load(open(PULL, encoding="utf-8"))
    markets = pull["markets"]

    diag_pmkt_minus_vix = []
    diag_rv_minus_vix = []
    # per-fee structures: out[fee]["train"/"oos"] = list of pnl; clusters likewise
    fees = {"reduced_0.035": 0.035, "full_0.07": 0.07}
    out = {f: {"train": [], "oos": []} for f in fees}
    cl = {f: {"train": [], "oos": []} for f in fees}
    outv = {f: {"train": [], "oos": []} for f in fees}
    clv = {f: {"train": [], "oos": []} for f in fees}

    n_have = 0
    n_traded = 0
    for tk, m in markets.items():
        p = parse_title(m["title"])
        if not p:
            continue
        kind, a, b = p
        result = m["result"]
        close_dt = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        settle_date = close_dt.date().isoformat()
        close_ts = close_dt.timestamp()
        # day-before VWAP from trades in [12,36]h before close
        lo = close_ts - WIN_HI_H * 3600
        hi = close_ts - WIN_LO_H * 3600
        tot_c = 0.0
        tot_pc = 0.0
        for ts_iso, c, yp in m["trades"]:
            tts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp()
            if lo <= tts <= hi:
                tot_c += c
                tot_pc += c * yp
        if tot_c <= 0:
            continue
        p_mkt = tot_pc / tot_c

        # clean no-look-ahead spot: last FRED close strictly before window start
        window_start = (close_dt - timedelta(hours=WIN_HI_H)).date().isoformat()
        spot_day = None
        for dd in reversed(days):
            if dd < window_start:
                spot_day = dd
                break
        if spot_day is None:
            continue
        spot = sp[spot_day]
        rv = realized_vol(spot_day)
        vx = vix.get(spot_day)
        if rv is None or vx is None:
            continue
        vx = vx / 100.0
        # actual trading-day horizon
        settle_idx = None
        for dd in reversed(days):
            if dd <= settle_date:
                settle_idx = idx[dd]
                break
        if settle_idx is None:
            continue
        T_days = max(settle_idx - idx[spot_day], 1)
        T = T_days / 252.0

        n_have += 1
        model_p = model_prob(kind, a, b, spot, rv, T)
        vix_p = model_prob(kind, a, b, spot, vx, T)
        diag_pmkt_minus_vix.append(p_mkt - vix_p)
        diag_rv_minus_vix.append(model_p - vix_p)

        if not (BAND_LO <= p_mkt <= BAND_HI):
            continue
        w = "train" if settle_date < TRAIN_END else "oos"

        # realized-vol model trade
        g = model_p - p_mkt
        if abs(g) >= DIVERGENCE:
            n_traded += 1
            if g > 0:
                entry = min(p_mkt + SPREAD_HAIRCUT, 0.99)
                win = (result == "yes")
            else:
                entry = min((1.0 - p_mkt) + SPREAD_HAIRCUT, 0.99)
                win = (result == "no")
            gross = (1.0 - entry) if win else -entry
            for fname, coeff in fees.items():
                out[fname][w].append(gross - taker_fee(entry, coeff))
                cl[fname][w].append(settle_date)

        # VIX control trade
        gv = vix_p - p_mkt
        if abs(gv) >= DIVERGENCE:
            if gv > 0:
                entry = min(p_mkt + SPREAD_HAIRCUT, 0.99)
                win = (result == "yes")
            else:
                entry = min((1.0 - p_mkt) + SPREAD_HAIRCUT, 0.99)
                win = (result == "no")
            gross = (1.0 - entry) if win else -entry
            for fname, coeff in fees.items():
                outv[fname][w].append(gross - taker_fee(entry, coeff))
                clv[fname][w].append(settle_date)

    print("=" * 74)
    print(f"v24 INDEX VOL-MISPRICING TAKER v2 (FULL API HISTORY)  RV_WINDOW={RV_WINDOW}")
    print("=" * 74)
    print(f"data: {PULL}")
    print(f"markets stored={len(markets)}; with day-before price+FRED spot/RV/VIX: "
          f"{n_have}; realized-model fires: {n_traded}")
    if diag_pmkt_minus_vix:
        print(f"\n(A) CAPTURE-PHANTOM DIAGNOSTIC (n={len(diag_pmkt_minus_vix)} markets):")
        print(f"  median(Kalshi_price - VIX_model_P)  = {st.median(diag_pmkt_minus_vix)*100:+.2f}pp")
        print(f"  median(realized_P  - VIX_model_P)   = {st.median(diag_rv_minus_vix)*100:+.2f}pp "
              f"(the realized-vs-VIX wedge; ~0 => no informational advantage)")

    def report(label, o, c):
        print(f"\n({label})")
        for fname in fees:
            print(f"  fee={fname}:")
            for w in ("train", "oos"):
                vals = o[fname][w]
                cids = c[fname][w]
                k = len(set(cids))
                line = f"    {w.upper():5s}: fills={len(vals):4d} clusters(days)={k:3d}"
                if len(vals) >= 2 and k >= 2:
                    mean, loq, hiq, kk = cluster_bootstrap_mean_ci(
                        vals, cids, n_resamples=5000, ci=0.95, rng_seed=42)
                    passed = loq > 0
                    line += (f"  net={mean*100:+.2f}pp CI[{loq*100:+.2f},{hiq*100:+.2f}]pp"
                             f"  PASS(lo>0)={passed}")
                print(line)

    report("B: REALIZED-vol model (the strategy)", out, cl)
    report("C: VIX model CONTROL (must NOT match B OOS, else no realized edge)", outv, clv)

    # explicit binding-gate verdict on the reduced fee (pre-registered gate)
    print("\n" + "=" * 74)
    print("BINDING GATE (reduced 0.035 fee, OOS):")
    rb = out["reduced_0.035"]["oos"]
    rbc = cl["reduced_0.035"]["oos"]
    vc = outv["reduced_0.035"]["oos"]
    vcc = clv["reduced_0.035"]["oos"]
    if len(rb) >= 2 and len(set(rbc)) >= 2 and len(vc) >= 2 and len(set(vcc)) >= 2:
        rm, rlo, rhi, _ = cluster_bootstrap_mean_ci(rb, rbc, n_resamples=5000, ci=0.95, rng_seed=42)
        vm, vlo, vhi, _ = cluster_bootstrap_mean_ci(vc, vcc, n_resamples=5000, ci=0.95, rng_seed=42)
        beats = rm > vm
        print(f"  realized OOS net={rm*100:+.2f}pp CI[{rlo*100:+.2f},{rhi*100:+.2f}]  lower>0={rlo>0}")
        print(f"  VIX ctrl OOS net={vm*100:+.2f}pp CI[{vlo*100:+.2f},{vhi*100:+.2f}]")
        print(f"  realized beats VIX control OOS: {beats} (wedge {(rm-vm)*100:+.2f}pp)")
        print(f"  GATE PASS = {(rlo>0) and beats}")
    else:
        print("  insufficient OOS clusters for the gate")


if __name__ == "__main__":
    main()
