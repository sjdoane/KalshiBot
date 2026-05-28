"""V1 stress test on previously-excluded series (V4-H, Phase 4).

Closes the v3 W1 / v4 critic Finding 6.1 / 8.5 finding: v1's measured
+12.47pp edge was computed on data/processed/sports_dataset.parquet
(n=39 eligible) which contains ZERO markets from the five target series
that v1 actually trades in production. This script rebuilds v1's
baseline measurement on those five series using the V3-A probe
inventory (n=2828 markets, wide-window T-35d VWAP).

Hard constraints:
- READ-only. No Kalshi API calls. No modifications to v1 bot.
- Uses existing cached data: data/v3/probe_inventory_all_markets.parquet
  and data/processed/sports_dataset.parquet (v1's original measurement
  set, for comparison).
- Same fee formula as src/kalshi_bot_v2/gate.py realized_pnl_per_contract.

Outputs:
- data/v4/v1_stress_test_per_market.parquet: per-market eligible rows
- data/v4/v1_stress_test_summary.json: per-series and aggregate stats
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci
from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

# v1 fee + slippage model (matches src/kalshi_bot_v2/gate.py)
SLIPPAGE_ALLOWANCE = 0.015
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_CI = 0.95
BOOTSTRAP_SEED = 42

# v1 eligibility (matches src/kalshi_bot/strategy/favorite_maker.py +
# CLAUDE.md Round 7 time-scale filter)
PRICE_LOW = 0.70
PRICE_HIGH = 0.95
LIFETIME_MIN_DAYS = 30
LIFETIME_MAX_DAYS = 180

TARGET_PREFIXES = [
    "KXNFLWINS",
    "KXNFLPLAYOFF",
    "KXNCAAFFINALIST",
    "KXNCAAF",
    "KXMLBPLAYOFFS",
]

ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = ROOT / "data" / "v3" / "probe_inventory_all_markets.parquet"
V1_DATASET_PATH = ROOT / "data" / "processed" / "sports_dataset.parquet"
OUT_PARQUET = ROOT / "data" / "v4" / "v1_stress_test_per_market.parquet"
OUT_JSON = ROOT / "data" / "v4" / "v1_stress_test_summary.json"


def realized_pnl_per_contract(yes_price: float, outcome: int) -> float:
    """Identical formula to src/kalshi_bot_v2/gate.py: gross - 2*maker_fee - slippage."""
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


def main() -> None:
    print(f"Loading probe inventory from {PROBE_PATH}")
    probe = pd.read_parquet(PROBE_PATH)
    print(f"  shape: {probe.shape}")

    probe = probe.copy()
    probe["prefix"] = probe["series_ticker"].str.split("-").str[0]

    # Section 1: series enumeration
    print()
    print("=" * 70)
    print("SECTION 1: SERIES ENUMERATION")
    print("=" * 70)

    series_summary = []
    for prefix in TARGET_PREFIXES:
        sub = probe[probe["prefix"] == prefix].copy()
        total = len(sub)
        resolved_mask = sub["result"].isin(["yes", "no"])
        n_resolved = int(resolved_mask.sum())
        has_wide = int(sub["vwap_t35_wide"].notna().sum())
        has_narrow = int(sub["vwap_t35_narrow"].notna().sum())

        eligible_mask = (
            resolved_mask
            & (sub["lifetime_days"] >= LIFETIME_MIN_DAYS)
            & (sub["lifetime_days"] <= LIFETIME_MAX_DAYS)
            & (sub["vwap_t35_wide"] >= PRICE_LOW)
            & (sub["vwap_t35_wide"] <= PRICE_HIGH)
        )
        eligible = sub[eligible_mask].copy()
        n_elig = int(len(eligible))

        if n_elig > 0:
            yes_rate = float(eligible["outcome"].mean())
            mean_price = float(eligible["vwap_t35_wide"].mean())
            mean_lifetime = float(eligible["lifetime_days"].mean())
            time_min = eligible["close_time"].min()
            time_max = eligible["close_time"].max()
            time_span = (
                f"{time_min.date().isoformat()} to {time_max.date().isoformat()}"
            )
        else:
            yes_rate = float("nan")
            mean_price = float("nan")
            mean_lifetime = float("nan")
            time_span = "n/a"

        row = {
            "series_prefix": prefix,
            "total_markets": total,
            "n_resolved": n_resolved,
            "has_vwap_wide": has_wide,
            "has_vwap_narrow": has_narrow,
            "n_v1_eligible": n_elig,
            "yes_rate": yes_rate,
            "mean_price_at_T_35d_wide": mean_price,
            "mean_lifetime_days": mean_lifetime,
            "time_span": time_span,
        }
        series_summary.append(row)
        print(
            f"{prefix:20s}  total={total:4d}  resolved={n_resolved:4d}  "
            f"v1-eligible={n_elig:3d}  yes_rate={yes_rate if not np.isnan(yes_rate) else 'n/a'}  "
            f"window={time_span}"
        )

    # Section 2: per-series v1 baseline measurement
    print()
    print("=" * 70)
    print("SECTION 2: PER-SERIES V1 BASELINE")
    print("=" * 70)

    # Build the full eligible frame across target series
    eligible_mask_all = (
        probe["prefix"].isin(TARGET_PREFIXES)
        & probe["result"].isin(["yes", "no"])
        & (probe["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (probe["lifetime_days"] <= LIFETIME_MAX_DAYS)
        & (probe["vwap_t35_wide"] >= PRICE_LOW)
        & (probe["vwap_t35_wide"] <= PRICE_HIGH)
    )
    eligible_all = probe[eligible_mask_all].copy()
    eligible_all["realized_pnl"] = eligible_all.apply(
        lambda r: realized_pnl_per_contract(
            float(r["vwap_t35_wide"]), int(r["outcome"])
        ),
        axis=1,
    )
    eligible_all["used_price"] = eligible_all["vwap_t35_wide"]
    eligible_all["target_series"] = True

    print()
    series_pnl_table = []
    for prefix in TARGET_PREFIXES:
        sub = eligible_all[eligible_all["prefix"] == prefix]
        n = len(sub)
        if n == 0:
            print(f"{prefix:20s}  n=0  (no v1-eligible markets)")
            series_pnl_table.append(
                {
                    "series_prefix": prefix,
                    "n_eligible": 0,
                    "mean_pnl_pp": float("nan"),
                    "median_pnl_pp": float("nan"),
                    "sd_pp": float("nan"),
                    "hit_rate": float("nan"),
                    "ci_lower_pp": float("nan"),
                    "ci_upper_pp": float("nan"),
                    "max_team_share": float("nan"),
                    "top_entity": "n/a",
                }
            )
            continue

        pnl = sub["realized_pnl"].to_numpy()
        mean = float(pnl.mean())
        median = float(np.median(pnl))
        sd = float(pnl.std())
        hit_rate = float((pnl > 0).mean())
        _, lo, hi = bootstrap(pnl)

        entity_counts = sub["entity"].value_counts()
        max_share = float(entity_counts.iloc[0] / n)
        top_entity = str(entity_counts.index[0])

        print(
            f"{prefix:20s}  n={n:3d}  mean={mean*100:+6.2f}pp  median={median*100:+6.2f}pp  "
            f"sd={sd*100:5.2f}pp  hit={hit_rate*100:5.1f}%  "
            f"CI=[{lo*100:+6.2f}pp, {hi*100:+6.2f}pp]  top_entity={top_entity}({entity_counts.iloc[0]}/{n})"
        )
        series_pnl_table.append(
            {
                "series_prefix": prefix,
                "n_eligible": int(n),
                "mean_pnl_pp": mean * 100,
                "median_pnl_pp": median * 100,
                "sd_pp": sd * 100,
                "hit_rate": hit_rate,
                "ci_lower_pp": lo * 100,
                "ci_upper_pp": hi * 100,
                "max_team_share": max_share,
                "top_entity": top_entity,
            }
        )

    # Section 3: aggregate across (new + original)
    print()
    print("=" * 70)
    print("SECTION 3: CROSS-SERIES AGGREGATE (new + original)")
    print("=" * 70)

    # Load v1's original dataset for the aggregate; reuse its eligibility
    v1 = pd.read_parquet(V1_DATASET_PATH)
    v1_elig = v1[
        (v1["mid_price_at_T_small"] >= PRICE_LOW)
        & (v1["mid_price_at_T_small"] <= PRICE_HIGH)
        & (v1["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (v1["lifetime_days"] <= LIFETIME_MAX_DAYS)
    ].copy()
    v1_elig["realized_pnl"] = v1_elig.apply(
        lambda r: realized_pnl_per_contract(
            float(r["mid_price_at_T_small"]), int(r["outcome"])
        ),
        axis=1,
    )
    v1_elig["used_price"] = v1_elig["mid_price_at_T_small"]
    v1_elig["target_series"] = False
    v1_elig["vwap_t35_wide"] = v1_elig["mid_price_at_T_small"]
    v1_elig["prefix"] = v1_elig["series_ticker"].str.split("-").str[0]

    n_orig = len(v1_elig)
    pnl_orig = v1_elig["realized_pnl"].to_numpy()
    mean_orig = float(pnl_orig.mean())
    hit_orig = float((pnl_orig > 0).mean())
    _, lo_orig, hi_orig = bootstrap(pnl_orig)
    print(
        f"ORIGINAL (17 prefixes, sports_dataset.parquet): n={n_orig}  "
        f"mean={mean_orig*100:+6.2f}pp  hit={hit_orig*100:5.1f}%  "
        f"CI=[{lo_orig*100:+6.2f}pp, {hi_orig*100:+6.2f}pp]"
    )

    # Combined
    pnl_target = eligible_all["realized_pnl"].to_numpy()
    n_target = len(pnl_target)
    mean_target = float(pnl_target.mean()) if n_target > 0 else float("nan")
    hit_target = float((pnl_target > 0).mean()) if n_target > 0 else float("nan")
    _, lo_target, hi_target = bootstrap(pnl_target)
    print(
        f"NEW (5 target prefixes, probe inventory wide T-35d): n={n_target}  "
        f"mean={mean_target*100:+6.2f}pp  hit={hit_target*100:5.1f}%  "
        f"CI=[{lo_target*100:+6.2f}pp, {hi_target*100:+6.2f}pp]"
    )

    pnl_combined = np.concatenate([pnl_orig, pnl_target])
    n_combined = len(pnl_combined)
    mean_combined = float(pnl_combined.mean())
    hit_combined = float((pnl_combined > 0).mean())
    _, lo_combined, hi_combined = bootstrap(pnl_combined)
    print(
        f"AGGREGATE (new + original): n={n_combined}  "
        f"mean={mean_combined*100:+6.2f}pp  hit={hit_combined*100:5.1f}%  "
        f"CI=[{lo_combined*100:+6.2f}pp, {hi_combined*100:+6.2f}pp]"
    )
    print(
        f"  vs original +12.47pp claim: AGGREGATE is "
        f"{(mean_combined - mean_orig)*100:+5.2f}pp lower than original-only"
    )

    # Section 4: per-series comparison vs original
    print()
    print("=" * 70)
    print("SECTION 4: PER-SERIES VS ORIGINAL +12.47PP")
    print("=" * 70)

    threshold_consistent = 0.05  # +/- 5pp consistent
    threshold_fragile = -0.05  # > 5pp worse = fragile

    print(
        f"{'series':22s} {'n':>4} {'mean_pp':>10} {'diff_vs_orig':>14} {'verdict':>22}"
    )
    rows_compare = []
    for row in series_pnl_table:
        prefix = row["series_prefix"]
        n = row["n_eligible"]
        if n == 0:
            verdict = "untradable"
            diff_pp = float("nan")
            mean_pp = float("nan")
        else:
            mean_pp = row["mean_pnl_pp"]
            diff_pp = mean_pp - mean_orig * 100
            if diff_pp >= threshold_consistent * 100:
                verdict = "consistent_or_better"
            elif diff_pp <= threshold_fragile * 100:
                verdict = "FRAGILE_(<-5pp)"
            else:
                verdict = "similar"
        print(
            f"{prefix:22s} {n:>4} {mean_pp:>10.2f} {diff_pp:>14.2f} {verdict:>22}"
        )
        rows_compare.append(
            {
                "series_prefix": prefix,
                "n_eligible": n,
                "mean_pnl_pp": mean_pp,
                "diff_vs_original_pp": diff_pp,
                "verdict": verdict,
            }
        )

    # Section 5: persist outputs
    print()
    print("=" * 70)
    print("WRITING OUTPUTS")
    print("=" * 70)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    # Concat per-market data: eligible_all (target series) and v1_elig (original)
    target_cols = ["ticker", "series_ticker", "prefix", "entity",
                   "open_time", "close_time", "lifetime_days",
                   "vwap_t35_wide", "used_price", "outcome", "result",
                   "realized_pnl", "target_series"]
    target_df = eligible_all[target_cols].copy() if len(eligible_all) else pd.DataFrame(columns=target_cols)

    # v1_elig has different schema; only keep overlapping fields
    v1_cols_map = {
        "ticker": "ticker",
        "series_ticker": "series_ticker",
        "prefix": "prefix",
        "market_open_time": "open_time",
        "market_close_time": "close_time",
        "lifetime_days": "lifetime_days",
        "mid_price_at_T_small": "vwap_t35_wide",
        "used_price": "used_price",
        "outcome": "outcome",
        "realized_pnl": "realized_pnl",
        "target_series": "target_series",
    }
    v1_keep = v1_elig[list(v1_cols_map.keys())].rename(columns=v1_cols_map).copy()
    v1_keep["entity"] = None
    v1_keep["result"] = v1_keep["outcome"].map({1: "yes", 0: "no"})
    v1_keep = v1_keep[target_cols]

    combined_df = pd.concat([target_df, v1_keep], ignore_index=True)
    combined_df.to_parquet(OUT_PARQUET)
    print(f"  per-market: {OUT_PARQUET} ({len(combined_df)} rows)")

    summary = {
        "config": {
            "price_band": [PRICE_LOW, PRICE_HIGH],
            "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
            "slippage_allowance": SLIPPAGE_ALLOWANCE,
            "bootstrap_n_resamples": BOOTSTRAP_N_RESAMPLES,
            "bootstrap_ci": BOOTSTRAP_CI,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "target_prefixes": TARGET_PREFIXES,
            "probe_path": str(PROBE_PATH.relative_to(ROOT)),
            "v1_dataset_path": str(V1_DATASET_PATH.relative_to(ROOT)),
        },
        "section_1_series_enumeration": series_summary,
        "section_2_per_series_v1_baseline": series_pnl_table,
        "section_3_aggregate": {
            "original_n": int(n_orig),
            "original_mean_pp": mean_orig * 100,
            "original_hit_rate": hit_orig,
            "original_ci_lower_pp": lo_orig * 100,
            "original_ci_upper_pp": hi_orig * 100,
            "new_n": int(n_target),
            "new_mean_pp": mean_target * 100,
            "new_hit_rate": hit_target,
            "new_ci_lower_pp": lo_target * 100,
            "new_ci_upper_pp": hi_target * 100,
            "combined_n": int(n_combined),
            "combined_mean_pp": mean_combined * 100,
            "combined_hit_rate": hit_combined,
            "combined_ci_lower_pp": lo_combined * 100,
            "combined_ci_upper_pp": hi_combined * 100,
        },
        "section_4_per_series_comparison": rows_compare,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  summary JSON: {OUT_JSON}")


if __name__ == "__main__":
    main()
