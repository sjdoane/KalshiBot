"""W2: re-measure v1's edge on the denylisted-residual universe.

Closes the open W2 item flagged in CLAUDE.md after Round 10 v4 (V4-H
applied denylist {KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS}). v4-H showed
v1 mean is -3.02pp on the denied series. W2 asks: on the UNION of (the
original n=39 universe) and (V3-A's n=147 inventory MINUS the denylist),
what is v1's measured edge?

Hard constraints:
- READ-only. No Kalshi API calls. No modifications to v1 bot.
- Uses existing cached data:
    data/v3/probe_inventory_eligible_with_team.parquet (n=147 eligible)
    data/processed/sports_dataset.parquet (n=423 v1 original measurement)
- Same fee + slippage formula as src/kalshi_bot_v2/gate.py
  realized_pnl_per_contract.

Outputs (debug only; the canonical write-up is research/w2-v1-residual-edge.md):
    data/v5/w2_residual_per_market.parquet
    data/v5/w2_residual_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci
from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

# --- locked constants (match src/kalshi_bot_v2/gate.py) ---
SLIPPAGE_ALLOWANCE = 0.015
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_CI = 0.95
BOOTSTRAP_SEED = 42

# v1 eligibility (per CLAUDE.md Round 7 + src/kalshi_bot/strategy/favorite_maker.py)
PRICE_LOW = 0.70
PRICE_HIGH = 0.95
LIFETIME_MIN_DAYS = 30
LIFETIME_MAX_DAYS = 180

# W1 denylist applied to v1 scanner in v4 (V4-H operator action)
DENYLIST = {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"}

ROOT = Path(__file__).resolve().parents[2]
V3_PATH = ROOT / "data" / "v3" / "probe_inventory_eligible_with_team.parquet"
V1_PATH = ROOT / "data" / "processed" / "sports_dataset.parquet"
OUT_PARQUET = ROOT / "data" / "v5" / "w2_residual_per_market.parquet"
OUT_JSON = ROOT / "data" / "v5" / "w2_residual_summary.json"


def realized_pnl_per_contract(yes_price: float, outcome: int) -> float:
    """Identical to src/kalshi_bot_v2/gate.py:realized_pnl_per_contract.

    gross = outcome - yes_price
    fee   = 2 * kalshi_maker_fee_per_contract(yes_price)
    slip  = 0.015
    pnl   = gross - fee - slip
    """
    gross = outcome - yes_price
    fee = 2.0 * kalshi_maker_fee_per_contract(yes_price)
    return gross - fee - SLIPPAGE_ALLOWANCE


def bootstrap(arr: np.ndarray) -> tuple[float, float, float]:
    if arr.size == 0:
        return float("nan"), float("nan"), float("nan")
    mean, lo, hi = bootstrap_mean_ci(
        arr,
        n_resamples=BOOTSTRAP_N_RESAMPLES,
        ci=BOOTSTRAP_CI,
        rng_seed=BOOTSTRAP_SEED,
    )
    return float(mean), float(lo), float(hi)


def describe(arr: np.ndarray) -> dict:
    if arr.size == 0:
        return {
            "n": 0,
            "mean_pp": float("nan"),
            "median_pp": float("nan"),
            "sd_pp": float("nan"),
            "hit_rate": float("nan"),
            "ci_lower_pp": float("nan"),
            "ci_upper_pp": float("nan"),
        }
    mean, lo, hi = bootstrap(arr)
    return {
        "n": int(arr.size),
        "mean_pp": mean * 100,
        "median_pp": float(np.median(arr)) * 100,
        "sd_pp": float(arr.std(ddof=0)) * 100,
        "hit_rate": float((arr > 0).mean()),
        "ci_lower_pp": lo * 100,
        "ci_upper_pp": hi * 100,
    }


def main() -> None:
    print("=" * 72)
    print("W2: V1 RESIDUAL EDGE MEASUREMENT")
    print("=" * 72)

    # --- 1. Load both universes ---
    print()
    print("Loading v3 inventory:", V3_PATH)
    v3 = pd.read_parquet(V3_PATH).copy()
    v3["prefix"] = v3["series_ticker"].str.split("-").str[0]
    print(f"  v3 inventory n = {len(v3)} (eligible_wide rows)")

    print("Loading v1 original dataset:", V1_PATH)
    v1 = pd.read_parquet(V1_PATH).copy()
    print(f"  v1 dataset n = {len(v1)} (all sports rows)")

    # v1 eligibility per task spec
    v1_elig_mask = (
        (v1["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (v1["lifetime_days"] <= LIFETIME_MAX_DAYS)
        & (v1["mid_price_at_T_small"] >= PRICE_LOW)
        & (v1["mid_price_at_T_small"] <= PRICE_HIGH)
        & (v1["outcome"].isin([0, 1]))
    )
    v1_elig = v1[v1_elig_mask].copy()
    v1_elig["prefix"] = v1_elig["series_ticker"].str.split("-").str[0]
    print(f"  v1 eligible n = {len(v1_elig)} (the original n=39 universe)")

    # --- 2. Residual universe construction ---
    print()
    print("=" * 72)
    print("STEP 1: RESIDUAL UNIVERSE ENUMERATION")
    print("=" * 72)

    # v3 residual: drop denylisted series
    v3_residual = v3[~v3["prefix"].isin(DENYLIST)].copy()
    print(f"v3 residual (denylist removed): n = {len(v3_residual)}")
    print(f"  Denylist applied: {sorted(DENYLIST)}")
    print()

    # v1 residual: also drop denylisted (should be 0 dropped since original had 0)
    v1_residual = v1_elig[~v1_elig["prefix"].isin(DENYLIST)].copy()
    print(f"v1 residual (denylist removed): n = {len(v1_residual)} (denylist subtracted {len(v1_elig) - len(v1_residual)} rows)")

    # Dedup by ticker. Keep v3 row when conflict (it uses wide T-35d VWAP which
    # is the same window v1 actually trades; v1's original dataset uses
    # mid_price_at_T_small which is a narrower window. Both target the same
    # T-35d entry but use different VWAP aggregation. Keeping the v3 row gives
    # us a single consistent VWAP definition across as much of the universe as
    # possible while still adding v1-unique rows where v3 has none.)
    v3_tickers = set(v3_residual["ticker"].tolist())
    v1_unique = v1_residual[~v1_residual["ticker"].isin(v3_tickers)].copy()
    overlap_tickers = sorted(set(v1_residual["ticker"]) & v3_tickers)
    print(f"Overlap between v3-residual and v1-residual (deduped, keep v3): n = {len(overlap_tickers)}")
    print(f"v1-only rows added to residual: n = {len(v1_unique)}")
    print()

    # --- 3. Build unified residual frame with consistent columns ---
    # v3 schema:   ticker, series_ticker, prefix, entity, open_time, close_time,
    #              lifetime_days, vwap_t35_wide, outcome, result, team
    # v1 schema:   ticker, series_ticker, market_open_time, market_close_time,
    #              outcome, mid_price_at_T_small, league, lifetime_days
    v3_keep = v3_residual[[
        "ticker", "series_ticker", "prefix", "open_time", "close_time",
        "lifetime_days", "vwap_t35_wide", "outcome", "result",
    ]].copy()
    v3_keep["used_price"] = v3_keep["vwap_t35_wide"]
    v3_keep["source"] = "v3_residual"

    v1_keep = v1_unique[[
        "ticker", "series_ticker", "prefix", "market_open_time",
        "market_close_time", "lifetime_days", "mid_price_at_T_small", "outcome",
    ]].rename(columns={
        "market_open_time": "open_time",
        "market_close_time": "close_time",
        "mid_price_at_T_small": "vwap_t35_wide",
    })
    v1_keep["used_price"] = v1_keep["vwap_t35_wide"]
    v1_keep["result"] = v1_keep["outcome"].map({1: "yes", 0: "no"}).astype(object)
    v1_keep["source"] = "v1_only"

    residual = pd.concat([v3_keep, v1_keep], ignore_index=True)
    residual["realized_pnl"] = residual.apply(
        lambda r: realized_pnl_per_contract(
            float(r["used_price"]), int(r["outcome"]),
        ),
        axis=1,
    )

    print(f"COMBINED RESIDUAL UNIVERSE: n = {len(residual)}")
    print(
        f"  from v3 residual: {(residual['source'] == 'v3_residual').sum()}; "
        f"from v1-only: {(residual['source'] == 'v1_only').sum()}"
    )
    print()
    print("Per-series breakdown (residual):")
    by_series = (
        residual.groupby(["prefix"])
        .size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
    )
    for _, row in by_series.iterrows():
        print(f"  {row['prefix']:24s} n={row['n']:4d}")
    print()

    # Date range
    print(f"Close-time range: {residual['close_time'].min()} to {residual['close_time'].max()}")
    print()

    # --- 4. v1 P&L measurement on the residual universe ---
    print("=" * 72)
    print("STEP 2: V1 P&L MEASUREMENT ON RESIDUAL UNIVERSE")
    print("=" * 72)
    pnl_full = residual["realized_pnl"].to_numpy()
    full_stats = describe(pnl_full)
    print()
    print("OVERALL RESIDUAL:")
    print(
        f"  n={full_stats['n']:4d}  mean={full_stats['mean_pp']:+6.2f}pp  "
        f"median={full_stats['median_pp']:+6.2f}pp  sd={full_stats['sd_pp']:5.2f}pp  "
        f"hit={full_stats['hit_rate']*100:5.1f}%  "
        f"CI=[{full_stats['ci_lower_pp']:+6.2f}pp, {full_stats['ci_upper_pp']:+6.2f}pp]"
    )

    # Per-subset
    print()
    print("BY SOURCE SUBSET:")
    subset_stats = {}
    for source in ["v3_residual", "v1_only"]:
        sub = residual[residual["source"] == source]
        s = describe(sub["realized_pnl"].to_numpy())
        subset_stats[source] = s
        print(
            f"  {source:14s}  n={s['n']:4d}  mean={s['mean_pp']:+6.2f}pp  "
            f"median={s['median_pp']:+6.2f}pp  sd={s['sd_pp']:5.2f}pp  "
            f"hit={s['hit_rate']*100:5.1f}%  "
            f"CI=[{s['ci_lower_pp']:+6.2f}pp, {s['ci_upper_pp']:+6.2f}pp]"
        )

    # --- 5. Per-series breakdown ---
    print()
    print("=" * 72)
    print("STEP 3: PER-SERIES BREAKDOWN (RESIDUAL)")
    print("=" * 72)
    per_series_rows = []
    for prefix, sub in residual.groupby("prefix"):
        s = describe(sub["realized_pnl"].to_numpy())
        s_row = {"prefix": prefix, **s}
        per_series_rows.append(s_row)
        fragile = (
            s["n"] >= 3
            and s["mean_pp"] < 0
            and not np.isnan(s["ci_lower_pp"])
            and s["ci_lower_pp"] <= 0
            and s["ci_upper_pp"] >= 0
        )
        flag = "  FRAGILE" if fragile else ""
        if s["n"] < 3:
            flag = "  (n<3, no CI inference)"
        print(
            f"  {prefix:24s} n={s['n']:4d}  mean={s['mean_pp']:+6.2f}pp  "
            f"hit={s['hit_rate']*100:5.1f}%  "
            f"CI=[{s['ci_lower_pp']:+6.2f}pp, {s['ci_upper_pp']:+6.2f}pp]{flag}"
        )

    per_series_rows.sort(key=lambda r: r["n"], reverse=True)

    # --- 6. Comparison to original +12.47pp ---
    print()
    print("=" * 72)
    print("STEP 4: COMPARISON TO ORIGINAL +12.47PP")
    print("=" * 72)

    # Original v1 (uncut) on the full n=39
    v1_all = v1_elig.copy()
    v1_all["realized_pnl"] = v1_all.apply(
        lambda r: realized_pnl_per_contract(
            float(r["mid_price_at_T_small"]), int(r["outcome"]),
        ),
        axis=1,
    )
    orig_stats = describe(v1_all["realized_pnl"].to_numpy())
    print()
    print("ORIGINAL v1 (n=39, sports_dataset.parquet):")
    print(
        f"  n={orig_stats['n']:4d}  mean={orig_stats['mean_pp']:+6.2f}pp  "
        f"median={orig_stats['median_pp']:+6.2f}pp  hit={orig_stats['hit_rate']*100:5.1f}%  "
        f"CI=[{orig_stats['ci_lower_pp']:+6.2f}pp, {orig_stats['ci_upper_pp']:+6.2f}pp]"
    )
    print()
    print("RESIDUAL v1 (this measurement):")
    print(
        f"  n={full_stats['n']:4d}  mean={full_stats['mean_pp']:+6.2f}pp  "
        f"hit={full_stats['hit_rate']*100:5.1f}%  "
        f"CI=[{full_stats['ci_lower_pp']:+6.2f}pp, {full_stats['ci_upper_pp']:+6.2f}pp]"
    )

    gap_pp = full_stats["mean_pp"] - orig_stats["mean_pp"]
    print()
    print(f"Gap: residual - original = {gap_pp:+.2f}pp")

    # --- 7. Operator-facing recommendation ---
    print()
    print("=" * 72)
    print("STEP 5: OPERATOR RECOMMENDATION")
    print("=" * 72)
    mean_pp = full_stats["mean_pp"]
    ci_low = full_stats["ci_lower_pp"]
    ci_high = full_stats["ci_upper_pp"]

    if mean_pp > 5.0 and ci_low > 0.0:
        verdict = "GREEN"
    elif mean_pp > 1.0 and mean_pp <= 5.0:
        verdict = "YELLOW"
    elif mean_pp < 0.0:
        verdict = "RED"
    else:
        # gap_pp between 0 and 1, or CI deeply spans zero
        if ci_low < -5.0:
            verdict = "RED"
        else:
            verdict = "YELLOW"
    print(f"Verdict: {verdict}")
    print(f"  mean: {mean_pp:+.2f}pp; CI: [{ci_low:+.2f}, {ci_high:+.2f}]")

    # --- 8. Persist outputs ---
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    residual.to_parquet(OUT_PARQUET)
    print()
    print(f"Wrote per-market parquet -> {OUT_PARQUET}")

    summary = {
        "config": {
            "denylist": sorted(DENYLIST),
            "price_band": [PRICE_LOW, PRICE_HIGH],
            "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
            "slippage_allowance": SLIPPAGE_ALLOWANCE,
            "bootstrap_n_resamples": BOOTSTRAP_N_RESAMPLES,
            "bootstrap_ci": BOOTSTRAP_CI,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "v3_path": str(V3_PATH.relative_to(ROOT)),
            "v1_path": str(V1_PATH.relative_to(ROOT)),
        },
        "residual_universe": {
            "n_v3_inventory_total": int(len(v3)),
            "n_v3_residual": int(len(v3_residual)),
            "n_v1_eligible_total": int(len(v1_elig)),
            "n_v1_residual_after_denylist": int(len(v1_residual)),
            "n_overlap_with_v3": int(len(overlap_tickers)),
            "n_v1_only_added": int(len(v1_unique)),
            "n_combined_residual": int(len(residual)),
            "per_prefix_counts": by_series.to_dict("records"),
            "close_time_min": str(residual["close_time"].min()),
            "close_time_max": str(residual["close_time"].max()),
            "overlap_tickers": overlap_tickers,
        },
        "overall_residual_stats": full_stats,
        "subset_stats": subset_stats,
        "per_series_stats": per_series_rows,
        "original_v1_stats": orig_stats,
        "gap_residual_minus_original_pp": gap_pp,
        "recommendation_verdict": verdict,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Wrote summary JSON  -> {OUT_JSON}")


if __name__ == "__main__":
    main()
