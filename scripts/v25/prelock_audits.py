"""v25 pre-lock audits (lock section 0). Run BEFORE the locking commit.

0a settlement key: booleans and aggregate rates ONLY (E12a firewall): per-market
   agreement under key D vs key D-1, straddle counts, near-tie precision flags. No
   prices, no trade joins, no P&L-like quantities are printed.
0b power/fire-rate + E8 threshold decision inputs: print counts, band histograms,
   OUTCOME-BLIND model-vs-print divergence distribution, projected fire counts and
   mean model-conditional net edge at thresholds 0.08 and 0.12, H2 feasibility counts.
0c ledger item: in-sample pass-through R^2 at 7 and 14 day horizons (AAA + FRED only).

Kalshi `result` is read ONLY inside audit 0a and only reduced to booleans.

Run: .venv/Scripts/python.exe scripts/v25/prelock_audits.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from gas_model import (  # noqa: E402
    BAND_HI, BAND_LO, H2_NO_BAND, H2_YES_BAND, HAIRCUT, Model, evaluate_fires,
    iso_week_utc, load_data, load_markets, taker_fee,
)

DATA = os.path.join("data", "v25")


def audit_0a(markets: dict, aaa_raw: dict) -> None:
    print("=== AUDIT 0a: settlement key (booleans/rates only) ===")
    aaa = {date.fromisoformat(k): v for k, v in aaa_raw.items()}
    agree = {"D": 0, "Dm1": 0}
    total = 0
    straddle = []
    near_tie_flags = 0
    for tk, m in sorted(markets.items()):
        k = m.get("floor_strike")
        res = m.get("result")
        if k is None or res not in ("yes", "no") or m.get("strike_type") != "greater":
            continue
        d = date.fromisoformat(m["close_time"][:10])
        v_d, v_dm1 = aaa.get(d), aaa.get(d - timedelta(days=1))
        if v_d is None or v_dm1 is None:
            continue
        total += 1
        ok_d = ("yes" if v_d > k else "no") == res
        ok_dm1 = ("yes" if v_dm1 > k else "no") == res
        agree["D"] += ok_d
        agree["Dm1"] += ok_dm1
        if ok_d != ok_dm1:
            straddle.append((tk, ok_d, ok_dm1))
        if min(abs(v_d - k), abs(v_dm1 - k)) < 0.0015:
            near_tie_flags += 1
    print(f"testable markets (both AAA days present): {total}")
    for key in ("D", "Dm1"):
        print(f"  key={key}: consistency {agree[key]}/{total} = {agree[key] / total:.4f}" if total else "  no data")
    print(f"  straddle (decisive) markets: {len(straddle)}; near-tie precision flags: {near_tie_flags}")
    d_wins = sum(1 for _, a, b in straddle if a)
    dm1_wins = sum(1 for _, a, b in straddle if b)
    print(f"  straddle agreement: key D {d_wins}/{len(straddle)}, key D-1 {dm1_wins}/{len(straddle)}")
    for tk, a, b in straddle:
        print(f"    {tk}: D_agrees={a} Dm1_agrees={b}")


def audit_0b(markets: dict) -> None:
    print("\n=== AUDIT 0b: power, divergence distribution, threshold decision (outcome-blind) ===")
    data = load_data()
    model = Model(data)
    # evaluate at the LOWER candidate threshold; the 0.12 projection reuses the same fires
    fires, funnel = evaluate_fires(data, model, threshold=0.08, verbose=True)
    print(f"funnel: {funnel}")
    for thr in (0.08, 0.12):
        sel = [f for f in fires if abs(f.divergence) >= thr]
        clusters = {f.cluster for f in sel}
        edges = []
        for f in sel:
            cost = (f.p_print if f.side == "yes" else 1 - f.p_print) + HAIRCUT
            p_true = f.p_model if f.side == "yes" else 1 - f.p_model
            edges.append(p_true - cost - taker_fee(cost))
        mean_edge = sum(edges) / len(edges) if edges else float("nan")
        print(f"threshold {thr}: fires={len(sel)} fired_clusters={len(clusters)} "
              f"mean model-conditional net edge={mean_edge:.4f}")
    # E8 decision rule
    sel08 = [f for f in fires if abs(f.divergence) >= 0.08]
    edges08 = []
    for f in sel08:
        cost = (f.p_print if f.side == "yes" else 1 - f.p_print) + HAIRCUT
        p_true = f.p_model if f.side == "yes" else 1 - f.p_model
        edges08.append(p_true - cost - taker_fee(cost))
    m08 = sum(edges08) / len(edges08) if edges08 else 0.0
    decision = 0.08 if m08 >= 0.08 else 0.12
    print(f"E8 THRESHOLD DECISION: mean conditional edge at 0.08 = {m08:.4f} -> binding threshold {decision}")
    # divergence distribution deciles (over all evaluable dedup prints, pre-threshold)
    divs = sorted(abs(f.divergence) for f in fires)
    if divs:
        qs = [divs[int(q * (len(divs) - 1))] for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95)]
        print(f"|divergence| quantiles among fires@0.08 (10/25/50/75/90/95): {[round(x, 3) for x in qs]}")
    # H2 feasibility: count prints in repaired bands (no model gate here, upper bound)
    h2y = h2n = 0
    h2_clusters = set()
    from gas_model import iter_trades
    for t in iter_trades():
        m = markets.get(t["ticker"])
        if m is None:
            continue
        p = float(t["yes_price_dollars"])
        if H2_YES_BAND[0] <= p <= H2_YES_BAND[1]:
            h2y += 1
            h2_clusters.add(iso_week_utc(m["close_time"]))
        elif H2_NO_BAND[0] <= p <= H2_NO_BAND[1]:
            h2n += 1
            h2_clusters.add(iso_week_utc(m["close_time"]))
    print(f"H2 upper-bound print counts: yes-band={h2y} no-band={h2n} clusters={len(h2_clusters)}")
    print("(H2 keep/drop decided against its floor 30 fires / 8 clusters AFTER the model+200-err gate,")
    print(" which can only shrink these; if the upper bound already fails the floor, H2 is dropped.)")
    # power arithmetic
    for n_c in (20, 30, 40, 60, 90):
        print(f"  CI half-width at sigma_c=0.40, n_clusters={n_c}: {1.96 * 0.40 / math.sqrt(n_c):.3f}")
    h2_keep = (h2y + h2n) >= 30 and len(h2_clusters) >= 8
    print(f"H2 KEEP/DROP (E7 feasibility upper bound vs floor 30/8): {'KEEP' if h2_keep else 'DROP'}")
    json.dump(
        {"fires_at_008": len(sel08), "clusters_at_008": len({f.cluster for f in sel08}),
         "mean_cond_edge_008": m08, "decision": decision, "h2_keep": h2_keep},
        open(os.path.join(DATA, "audit_0b_decision.json"), "w", encoding="utf-8"),
    )


def audit_0c_r2() -> None:
    print("\n=== 0c ledger: in-sample pass-through R^2 (AAA+FRED only) ===")
    import numpy as np
    data = load_data()
    model = Model(data)
    for h in (7, 14):
        pred, real = [], []
        for u in data.aaa_dates:
            r_u = data.r(u)
            r_h = data.r(u + timedelta(days=h))
            if r_u is None or r_h is None:
                continue
            path = model.path(u, h)
            if path is None:
                continue
            pred.append(path[h - 1] - r_u)
            real.append(r_h - r_u)
        if len(pred) > 10:
            pred_a, real_a = np.array(pred), np.array(real)
            ss_res = float(np.sum((real_a - pred_a) ** 2))
            ss_tot = float(np.sum((real_a - real_a.mean()) ** 2))
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
            corr = float(np.corrcoef(pred_a, real_a)[0, 1])
            print(f"h={h}: n={len(pred)} R^2={r2:.3f} corr={corr:.3f}")
        else:
            print(f"h={h}: insufficient pairs ({len(pred)})")


def main() -> None:
    from gas_model import assert_aaa_coverage
    markets = load_markets()
    aaa_raw = json.load(open(os.path.join(DATA, "aaa_daily.json"), encoding="utf-8"))
    print(f"markets={len(markets)} aaa_days={len(aaa_raw)}")
    if "--allow-partial" not in sys.argv:
        assert_aaa_coverage(aaa_raw)
    audit_0a(markets, aaa_raw)
    audit_0b(markets)
    audit_0c_r2()


if __name__ == "__main__":
    main()
