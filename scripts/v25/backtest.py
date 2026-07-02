"""v25 POST-LOCK backtest: joins Kalshi settlement results to the fire sets and applies
the locked gates (research/v25/02-methodology-lock.md sections 4-9).

MUST NOT RUN before the locking commit. Reads the binding threshold and the H2
keep/drop decision from data/v25/audit_0b_decision.json (recorded per E8/E7).

Run: .venv/Scripts/python.exe scripts/v25/backtest.py
Writes data/v25/backtest_results.json and prints the report.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "src")
from gas_model import (  # noqa: E402
    HAIRCUT, HAIRCUT_MATCHED, Model, assert_aaa_coverage, evaluate_fires, load_data,
    load_markets, taker_fee,
)
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

DATA = os.path.join("data", "v25")
N_RESAMPLES = 10_000
SHOCK_LO, SHOCK_HI = "2026-02-15", "2026-06-30"
BIND_LO, BIND_HI = "2025-01-01", "2026-06-30"
FALLBACK_DEGENERACY_SHARE = 0.20   # lock sec 3 (E4)


def in_window(fires):
    return [f for f in fires if BIND_LO <= f.close_time[:10] <= BIND_HI]


def pnl_rows(fires, markets, haircut=HAIRCUT, matched_only=False, monthly_haircut=None):
    rows = []
    for f in fires:
        if matched_only and not f.taker_side_matched:
            continue
        hc = haircut
        if monthly_haircut is not None and f.series == "KXAAAGASM":
            hc = monthly_haircut
        cost = (f.p_print if f.side == "yes" else 1.0 - f.p_print) + hc
        if cost > 1.0:
            raise AssertionError(f"unexecutable cost {cost} on {f.ticker} (lock E15c says unreachable)")
        fee = taker_fee(cost)
        res = markets[f.ticker]["result"]
        win = 1.0 if res == f.side else 0.0
        rows.append({
            "pnl": win - cost - fee, "cluster": f.cluster, "month": f.month_cluster,
            "series": f.series, "h": f.h, "side": f.side, "close": f.close_time,
            "ticker": f.ticker, "et_date": f.et_date, "div": f.divergence,
            "p_print": f.p_print, "p_model": f.p_model, "p_control": f.p_control,
            "matched": f.taker_side_matched,
        })
    return rows


def ci_of(rows, key="cluster"):
    if not rows:
        return None
    vals = [r["pnl"] for r in rows]
    cl = [r[key] for r in rows]
    mean, lo, hi, n_c = cluster_bootstrap_mean_ci(vals, cl, n_resamples=N_RESAMPLES, rng_seed=25)
    return {"mean": mean, "lo": lo, "hi": hi, "n_fires": len(rows), "n_clusters": n_c}


def loco(rows):
    by_c = defaultdict(float)
    for r in rows:
        by_c[r["cluster"]] += r["pnl"]
    if not by_c:
        return None, None
    best = max(by_c, key=by_c.get)
    rest = [r for r in rows if r["cluster"] != best]
    return best, ci_of(rest)


def regime_guards(rows, base_ci_ok):
    out = {}
    out["month_block"] = ci_of(rows, key="month")
    out["month_ok"] = bool(out["month_block"] and out["month_block"]["lo"] > 0) if base_ci_ok else None
    non_shock = [r for r in rows if not (SHOCK_LO <= r["close"][:10] <= SHOCK_HI)]
    out["ex_shock"] = ci_of(non_shock)
    out["ex_shock_ok"] = bool(out["ex_shock"] and out["ex_shock"]["lo"] > 0) if base_ci_ok else None
    return out


def gates_h1(rows, control_rows):
    out = {}
    out["binding"] = ci_of(rows)
    out["power_ok"] = bool(rows) and out["binding"]["n_fires"] >= 40 and out["binding"]["n_clusters"] >= 30
    out["ci_ok"] = out["power_ok"] and out["binding"]["lo"] > 0
    cci = ci_of(control_rows)
    out["control"] = cci
    control_meets_floor = cci is not None and cci["n_fires"] >= 40 and cci["n_clusters"] >= 30
    out["control_clears"] = bool(control_meets_floor and cci["lo"] > 0)
    out["control_ok"] = not out["control_clears"]
    best, loco_ci = loco(rows)
    out["loco_drop"] = best
    out["loco"] = loco_ci
    out["loco_ok"] = bool(loco_ci and loco_ci["lo"] > 0) if out["ci_ok"] else None
    out.update(regime_guards(rows, out["ci_ok"]))
    if not out["power_ok"]:
        v = "UNDERPOWERED-NULL" if rows else "NO-FIRES (market-matches-model NULL)"
    elif not out["ci_ok"]:
        v = "NULL"
    elif not out["control_ok"]:
        v = "NULL (control also clears; general-miscalibration claim, future lock)"
    elif out["loco_ok"] is False:
        v = "MARGINAL"
    elif out["month_ok"] is False:
        v = "FRAGILE-PASS"
    elif out["ex_shock_ok"] is False:
        v = "SHOCK-WINDOW PASS"
    else:
        v = "PASS"
    out["verdict"] = v
    return out


def gates_h2(rows):
    out = {}
    out["binding"] = ci_of(rows)
    out["power_ok"] = bool(rows) and out["binding"]["n_fires"] >= 30 and out["binding"]["n_clusters"] >= 8
    out["ci_ok"] = out["power_ok"] and out["binding"]["lo"] > 0
    best, loco_ci = loco(rows)
    out["loco_drop"], out["loco"] = best, loco_ci
    out["loco_ok"] = bool(loco_ci and loco_ci["lo"] > 0) if out["ci_ok"] else None
    out.update(regime_guards(rows, out["ci_ok"]))
    if not out["power_ok"]:
        v = "UNDERPOWERED-NULL" if rows else "NO-FIRES (starved or market-matches-model)"
    elif not out["ci_ok"]:
        v = "NULL"
    elif out["loco_ok"] is False:
        v = "MARGINAL"
    elif out["month_ok"] is False:
        v = "FRAGILE-PASS"
    elif out["ex_shock_ok"] is False:
        v = "SHOCK-WINDOW PASS"
    else:
        v = "PASS"
    out["verdict"] = v
    return out


def breakdowns(rows):
    def agg(keyfn):
        d = defaultdict(list)
        for r in rows:
            d[keyfn(r)].append(r["pnl"])
        return {k: {"n": len(v), "mean": sum(v) / len(v)} for k, v in sorted(d.items())}
    return {
        "series": agg(lambda r: r["series"]),
        "side": agg(lambda r: r["side"]),
        "h_bucket": agg(lambda r: "1-3" if r["h"] <= 3 else "4-7" if r["h"] <= 7 else "8-14" if r["h"] <= 14 else "15-35"),
        "moneyness": agg(lambda r: "low" if r["p_print"] < 1 / 3 else "mid" if r["p_print"] < 2 / 3 else "high"),
        "chrono": agg(lambda r: "pre-2025-10" if r["close"][:10] < "2025-10-01" else "from-2025-10"),
    }


def run_variant(data, markets, thr, lag=None, fallback=False, subsample=False):
    model = Model(data, **({"lag": lag} if lag else {}), fallback=fallback,
                  subsample_errors=subsample)
    fires, funnel = evaluate_fires(data, model, threshold=thr)
    return in_window(fires), funnel


def main() -> None:
    decision = json.load(open(os.path.join(DATA, "audit_0b_decision.json"), encoding="utf-8"))
    thr = decision["decision"]
    h2_keep = decision.get("h2_keep", False)
    print(f"binding threshold (locked 0b): {thr}; H2 kept: {h2_keep}")
    data = load_data()
    assert_aaa_coverage(json.load(open(os.path.join(DATA, "aaa_daily.json"), encoding="utf-8")))
    markets = load_markets()

    model = Model(data)
    fires_all, funnel = evaluate_fires(data, model, threshold=thr, verbose=True)
    fires = in_window(fires_all)
    print(f"H1 fires (binding set): {len(fires)}; funnel {funnel}")

    # E4 fallback rule: >20 percent of evaluable trade dates degenerate -> fallback spec
    deg_share = (funnel["fit_degenerate_days"] / funnel["fit_days"]) if funnel["fit_days"] else 0.0
    used_fallback = deg_share > FALLBACK_DEGENERACY_SHARE
    if used_fallback:
        print(f"FALLBACK SPEC ENGAGED: degenerate share {deg_share:.2%} > 20%")
        fires, funnel = run_variant(data, markets, thr, fallback=True)

    ctrl_fires_all, _ = evaluate_fires(data, Model(data, fallback=used_fallback),
                                       threshold=thr, signal_control=True)
    ctrl_fires = in_window(ctrl_fires_all)
    print(f"control-strategy fires: {len(ctrl_fires)}")

    rows = pnl_rows(fires, markets)
    ctrl_rows = pnl_rows(ctrl_fires, markets)
    res = {"threshold": thr, "h2_keep": h2_keep, "funnel": funnel,
           "degenerate_share": deg_share, "used_fallback": used_fallback,
           "h1": gates_h1(rows, ctrl_rows)}
    res["h1"]["breakdowns"] = breakdowns(rows)

    matched_rows = pnl_rows(fires, markets, haircut=HAIRCUT_MATCHED, matched_only=True)
    res["h1"]["reported_matched"] = ci_of(matched_rows)
    res["h1"]["attrition"] = (1.0 - len(matched_rows) / len(rows)) if rows else None
    if res["h1"]["attrition"] is not None and res["h1"]["attrition"] > 0.5:
        res["h1"]["attrition_note"] = "over 50 percent attrition: capacity story weaker, verdict must say so (E15d)"

    # non-binding sensitivities
    alt_thr = 0.12 if thr == 0.08 else 0.08
    alt_fires, _ = run_variant(data, markets, alt_thr, fallback=used_fallback)
    res["sens_threshold_alt"] = {"threshold": alt_thr, "ci": ci_of(pnl_rows(alt_fires, markets))}
    res["sens_monthly_5c"] = ci_of(pnl_rows(fires, markets, monthly_haircut=0.05))
    d3_fires, _ = run_variant(data, markets, thr, lag=3, fallback=used_fallback)
    res["sens_lag_d3"] = ci_of(pnl_rows(d3_fires, markets))
    gulf_data = load_data("DGASUSGULF")
    gulf_fires, _ = run_variant(gulf_data, markets, thr, fallback=used_fallback)
    res["sens_regressor_gulf"] = ci_of(pnl_rows(gulf_fires, markets))
    sub_fires, _ = run_variant(data, markets, thr, fallback=used_fallback, subsample=True)
    res["sens_subsampled_errors"] = ci_of(pnl_rows(sub_fires, markets))

    # H2 (only if kept at lock time; review H3)
    if h2_keep:
        h2_fires_all, h2_funnel = evaluate_fires(data, Model(data, fallback=used_fallback), mode="h2")
        h2_fires = in_window(h2_fires_all)
        res["h2"] = {"funnel": h2_funnel}
        res["h2"].update(gates_h2(pnl_rows(h2_fires, markets)))
    else:
        res["h2"] = {"verdict": "DROPPED-AT-LOCK (0b feasibility rule); not run"}

    json.dump(res, open(os.path.join(DATA, "backtest_results.json"), "w", encoding="utf-8"),
              indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
