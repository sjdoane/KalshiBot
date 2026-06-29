"""Direction A (NO-underdog moderate-band tennis maker) Becker backtest.

Runs EXACTLY against research/v23/00-methodology-lock.md (+ critic amendments).

Gate universe: WTA-NO only. taker_side='yes' (maker on NO), no_price in [70,86).
Settlement on the SAME traded ticker (AMEND-9). Event cluster = derived event_ticker.
Assignment by event-first-trade-of-any-kind (matches critic-verified 669/374).
Fee modes: (a) dated-zero (tennis = ALL_OTHER/zero whole window per v22 fee_table),
           (b) worst-case ceil(1.75*P*(1-P)) cents (flat 1c in this band).
Inference: cluster_bootstrap_mean_ci(values, cluster_ids, n_resamples=5000,
           ci=0.95, rng_seed=42). values = per-fill net per $1. cluster = event_ticker.

ATP-NO is computed as a watch-only diagnostic and reported BEFORE the WTA verdict
(AMEND-7). It cannot rescue a WTA failure.

Read-only on the data. No orders. Per-fill (not contract-weighted) nets, matching
the lock's per-fill estimand and the prior cluster bootstrap.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
MARKETS = (REPO / "prediction-market-analysis/data/kalshi/markets/*.parquet").as_posix()
TRADES = (REPO / "prediction-market-analysis/data/kalshi/trades/*.parquet").as_posix()

# Import the LOCKED inference primitive from the repo (the exact callable in the lock).
sys.path.insert(0, (REPO / "src").as_posix())
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

# Locked split (Direction A).
TRAIN_LO, TRAIN_HI = "2025-06-18", "2025-09-08"   # [lo, hi)
PURGE_LO, PURGE_HI = "2025-09-08", "2025-09-15"   # dropped
OOS_LO, OOS_HI = "2025-09-15", "2025-12-01"       # [lo, hi)

N_RESAMPLES, CI, RNG_SEED = 5000, 0.95, 42


def worst_case_fee_dollars(no_px: float) -> float:
    """ceil(1.75*P*(1-P)) cents -> dollars. P in [0,1]. Flat 1c across [0.70,0.86)."""
    cents = math.ceil(1.75 * no_px * (1.0 - no_px))
    return cents / 100.0


def fetch_fills(series_like: str):
    """Return list of dicts: one row per qualifying NO-maker fill.

    Fields: event_ticker, ticker, date_token, no_px (dollars), result, window.
    Window assigned by EVENT first-trade-of-any-kind (all trades on the event).
    """
    con = duckdb.connect()
    sql = f"""
    WITH ev_first AS (
      SELECT regexp_replace(ticker,'-[^-]*$','') AS event_ticker,
             min(created_time) AS first_trade
      FROM '{TRADES}'
      WHERE ticker LIKE '{series_like}'
      GROUP BY 1
    ),
    fills AS (
      SELECT
        regexp_replace(t.ticker,'-[^-]*$','') AS event_ticker,
        t.ticker AS ticker,
        t.no_price AS no_px_cents,
        m.result AS result,
        t.created_time::DATE AS trade_date
      FROM '{TRADES}' t
      INNER JOIN '{MARKETS}' m ON t.ticker = m.ticker
      WHERE t.ticker LIKE '{series_like}'
        AND t.taker_side = 'yes'                 -- maker on NO
        AND t.no_price >= 70 AND t.no_price < 86 -- moderate band [70,86)
        AND m.result IN ('yes','no')             -- settled on the TRADED leg (AMEND-9)
    )
    SELECT
      f.event_ticker,
      f.ticker,
      regexp_extract(f.event_ticker, '{series_like[:-1]}([0-9]{{2}}[A-Z]{{3}}[0-9]{{2}})', 1) AS date_token,
      f.no_px_cents,
      f.result,
      f.trade_date,
      CASE
        WHEN ef.first_trade::DATE >= DATE '{TRAIN_LO}' AND ef.first_trade::DATE < DATE '{TRAIN_HI}' THEN 'TRAIN'
        WHEN ef.first_trade::DATE >= DATE '{PURGE_LO}' AND ef.first_trade::DATE < DATE '{PURGE_HI}' THEN 'PURGE'
        WHEN ef.first_trade::DATE >= DATE '{OOS_LO}' AND ef.first_trade::DATE < DATE '{OOS_HI}' THEN 'OOS'
        ELSE 'OUTSIDE'
      END AS window
    FROM fills f
    INNER JOIN ev_first ef ON f.event_ticker = ef.event_ticker
    """
    rows = con.execute(sql).fetchall()
    # SELECT order: event_ticker, ticker, date_token, no_px_cents, result, trade_date, window
    out = []
    for ev, tk, dt, npx_c, res, tdate, win in rows:
        no_px = npx_c / 100.0
        out.append({
            "event_ticker": ev, "ticker": tk, "date_token": dt,
            "no_px": no_px, "result": res, "trade_date": tdate, "window": win,
        })
    return out


import datetime as _dt
# Dated tennis fee per v22 fee_table.json: KXATPMATCH/KXWTAMATCH carry ceil_175 ONLY
# in [2025-07-08, 2025-07-13); zero before (pre-designation) and from 2025-07-13 on.
_TENNIS_FEE_LO = _dt.date(2025, 7, 8)
_TENNIS_FEE_HI = _dt.date(2025, 7, 13)


def dated_tennis_fee_dollars(no_px: float, trade_date) -> float:
    if _TENNIS_FEE_LO <= trade_date < _TENNIS_FEE_HI:
        return worst_case_fee_dollars(no_px)
    return 0.0


def per_fill_net(no_px: float, result: str, fee_mode: str, trade_date=None) -> float:
    """Net per $1 for a held-to-settlement NO maker. result on traded leg.

    fee_mode 'dated' = the v22-dated tennis schedule (zero except the Jul8-Jul13
    ceil_175 slice). fee_mode 'worst' = flat ceil_175 (1c in-band) on every fill.
    """
    gross = (1.0 - no_px) if result == "no" else (-no_px)
    if fee_mode == "worst":
        fee = worst_case_fee_dollars(no_px)
    else:  # 'dated'
        fee = dated_tennis_fee_dollars(no_px, trade_date)
    return gross - fee


def window_stats(fills, fee_mode):
    """Compute event-cluster bootstrap stats + concentration for one window."""
    if not fills:
        return None
    vals = np.array([per_fill_net(f["no_px"], f["result"], fee_mode, f.get("trade_date")) for f in fills], dtype=float)
    cids = np.array([f["event_ticker"] for f in fills], dtype=object)
    n_events = len(set(cids.tolist()))
    mean, lo, hi, k = cluster_bootstrap_mean_ci(
        vals, cids, n_resamples=N_RESAMPLES, ci=CI, rng_seed=RNG_SEED,
    )
    # Event-mean (mean of per-event means) for the decay guard A-5 (lock wording).
    ev_to_vals = {}
    for v, c in zip(vals, cids.tolist()):
        ev_to_vals.setdefault(c, []).append(v)
    event_means = np.array([np.mean(ev_to_vals[c]) for c in ev_to_vals], dtype=float)
    event_mean = float(event_means.mean())
    # Concentration A-6: largest tournament-day token share of ABSOLUTE P&L.
    tok_abs = {}
    total_abs = 0.0
    for f, v in zip(fills, vals):
        tok = f["date_token"] or "UNK"
        tok_abs[tok] = tok_abs.get(tok, 0.0) + abs(v)
        total_abs += abs(v)
    max_tok = max(tok_abs, key=tok_abs.get)
    conc_share = (tok_abs[max_tok] / total_abs) if total_abs > 0 else 0.0
    return {
        "n_fills": int(len(vals)),
        "n_events": int(n_events),
        "fill_mean_net": float(vals.mean()),
        "event_mean_net": event_mean,
        "cluster_mean": float(mean),
        "cluster_lo": float(lo),
        "cluster_hi": float(hi),
        "k_clusters": int(k),
        "conc_token": max_tok,
        "conc_share": float(conc_share),
    }


def report_cell(label, train_fills, oos_fills):
    print(f"\n{'='*92}\n{label}\n{'='*92}")
    for fee_mode in ("dated", "worst"):
        tr = window_stats(train_fills, fee_mode)
        oo = window_stats(oos_fills, fee_mode)
        tag = "DATED FEE (v22: zero except Jul8-Jul13 1c slice)" if fee_mode == "dated" else "WORST-CASE ceil(1.75P(1-P)) = flat 1c"
        print(f"\n  --- Fee mode: {tag} ---")
        for wname, s in (("TRAIN", tr), ("OOS", oo)):
            if s is None:
                print(f"    {wname}: NO FILLS")
                continue
            print(f"    {wname}: n_fills={s['n_fills']:>6} n_events={s['n_events']:>4} "
                  f"k={s['k_clusters']:>4}  fill_mean={s['fill_mean_net']*100:+.3f}pp  "
                  f"event_mean={s['event_mean_net']*100:+.3f}pp  "
                  f"cluster_CI=[{s['cluster_lo']*100:+.3f}, {s['cluster_hi']*100:+.3f}]pp")
            print(f"          concentration: top date-token {s['conc_token']} = "
                  f"{s['conc_share']*100:.1f}% of |P&L|")
        yield fee_mode, tr, oo


def main():
    print("DIRECTION A BACKTEST (NO-underdog moderate-band tennis maker)")
    print(f"Split: TRAIN [{TRAIN_LO},{TRAIN_HI})  PURGE [{PURGE_LO},{PURGE_HI})  OOS [{OOS_LO},{OOS_HI})")
    print(f"Inference: cluster_bootstrap_mean_ci n_resamples={N_RESAMPLES} ci={CI} seed={RNG_SEED}")
    print("Per-fill net per $1 = (result=='no' ? 1-no_px : -no_px) - fee. Cluster=event_ticker.")

    # ---- ATP-NO DIAGNOSTIC FIRST (AMEND-7) ----
    atp = fetch_fills("KXATPMATCH-%")
    atp_tr = [f for f in atp if f["window"] == "TRAIN"]
    atp_oo = [f for f in atp if f["window"] == "OOS"]
    print("\n" + "#"*92)
    print("# ATP-NO WATCH-ONLY DIAGNOSTIC (written BEFORE the WTA verdict; cannot rescue WTA)")
    print("#"*92)
    list(report_cell("ATP-NO moderate band [70,86) (DIAGNOSTIC, NOT THE GATE)", atp_tr, atp_oo))

    # ---- WTA-NO GATE ----
    wta = fetch_fills("KXWTAMATCH-%")
    wta_tr = [f for f in wta if f["window"] == "TRAIN"]
    wta_oo = [f for f in wta if f["window"] == "OOS"]
    print("\n" + "#"*92)
    print("# WTA-NO GATE (the firable cell)")
    print("#"*92)
    results = list(report_cell("WTA-NO moderate band [70,86) (THE GATE)", wta_tr, wta_oo))

    # ---- Adjudicate A-1..A-6 on WTA-NO ----
    print("\n" + "="*92)
    print("WTA-NO GATE ADJUDICATION (A-1 .. A-6)")
    print("="*92)
    res = {fm: (tr, oo) for fm, tr, oo in results}
    tr_z, oo_z = res["dated"]
    tr_w, oo_w = res["worst"]

    if tr_z is None or oo_z is None:
        print("FATAL: no fills in a window. INCONCLUSIVE.")
        return

    # A-1 min-n
    a1 = (tr_z["n_events"] >= 60) and (oo_z["n_events"] >= 60)
    print(f"A-1 min-n>=60 both windows: TRAIN n_events={tr_z['n_events']}, OOS n_events={oo_z['n_events']} -> {'PASS' if a1 else 'FAIL'}")

    # A-2 train sign (both fee modes)
    a2_z = tr_z["cluster_lo"] > 0
    a2_w = tr_w["cluster_lo"] > 0
    print(f"A-2 TRAIN cluster CI lower > 0:  dated-fee lo={tr_z['cluster_lo']*100:+.3f}pp ({'PASS' if a2_z else 'FAIL'}); "
          f"worst-fee lo={tr_w['cluster_lo']*100:+.3f}pp ({'PASS' if a2_w else 'FAIL'})")

    # A-3 OOS sign (both fee modes)
    a3_z = oo_z["cluster_lo"] > 0
    a3_w = oo_w["cluster_lo"] > 0
    print(f"A-3 OOS   cluster CI lower > 0:  dated-fee lo={oo_z['cluster_lo']*100:+.3f}pp ({'PASS' if a3_z else 'FAIL'}); "
          f"worst-fee lo={oo_w['cluster_lo']*100:+.3f}pp ({'PASS' if a3_w else 'FAIL'})")

    # A-4 net-of-fee under BOTH modes
    a4 = a2_z and a3_z and a2_w and a3_w
    print(f"A-4 A-2 and A-3 hold under BOTH fee modes -> {'PASS' if a4 else 'FAIL'}")

    # A-5 decay guard (report both means + ratio; AMEND-3: also require OOS>0 and not stat-below 50%)
    for fm, tr, oo in (("dated", tr_z, oo_z), ("worst", tr_w, oo_w)):
        tmean, omean = tr["event_mean_net"], oo["event_mean_net"]
        ratio = (omean / tmean) if tmean != 0 else float("nan")
        a5 = (omean > 0) and (tmean > 0) and (omean >= 0.5 * tmean)
        print(f"A-5 decay ({fm}): train_event_mean={tmean*100:+.3f}pp OOS_event_mean={omean*100:+.3f}pp "
              f"ratio={ratio:.2f} (>=0.50 & OOS>0) -> {'PASS' if a5 else 'FAIL'}")

    # A-6 concentration < 50% each window (use worst-fee abs P&L; sign-mode-invariant for share roughly)
    a6 = (tr_w["conc_share"] < 0.50) and (oo_w["conc_share"] < 0.50)
    print(f"A-6 largest date-token < 50% |P&L|: TRAIN {tr_w['conc_share']*100:.1f}% ({tr_w['conc_token']}), "
          f"OOS {oo_w['conc_share']*100:.1f}% ({oo_w['conc_token']}) -> {'PASS' if a6 else 'FAIL'}")

    # Overall (the binding gate = pass A-1..A-6, with A-2/A-3 binding under BOTH fee modes)
    a5_z = (oo_z["event_mean_net"] > 0) and (tr_z["event_mean_net"] > 0) and (oo_z["event_mean_net"] >= 0.5*tr_z["event_mean_net"])
    a5_w = (oo_w["event_mean_net"] > 0) and (tr_w["event_mean_net"] > 0) and (oo_w["event_mean_net"] >= 0.5*tr_w["event_mean_net"])
    overall = a1 and a4 and a5_z and a5_w and a6
    print("\n" + "-"*92)
    print(f"WTA-NO GATE VERDICT: {'PASS (earns forward shadow)' if overall else 'FAIL -> KILL Direction A at the Becker screen, NULL'}")
    print("-"*92)


if __name__ == "__main__":
    main()
