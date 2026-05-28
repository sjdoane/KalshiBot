"""V4 Phase 2 / Agent V4-E: retrospective backtest of the unified
Track A1 + Track A2 filter on v1's eligible universe.

Pipeline:
    1. Load v1's eligible universe from data/v3/probe_inventory_all_markets.parquet
       (147 markets, favorite_price >= 0.70, lifetime ok).
    2. Build Polymarket lookup at T-35d from data/v3/poly_kalshi_pairs.parquet
       (13 markets with poly mid, 5 in eligible-wide subset).
    3. Build per-team-season ladder data from the inventory's
       vwap_t35_wide column for ladder-series markets.
    4. For each eligible market:
        - Bare v1: trade YES at vwap_t35_wide; compute realized P&L.
        - Filter+v1: apply filter; if should_trade, trade as above.
    5. Compare distributions: mean, hit rate, count, bootstrap CI of
       (filter mean - v1 mean).
    6. Decompose per-filter contribution: A1 only, A2 only, combined.
    7. Apply pre-registered TA1-TA5 criteria.

Pre-registered thresholds (LOCKED at run time; do NOT post-hoc tune):
    FADE_THRESHOLD_CENTS = 7.0     (master plan)
    MONOTONICITY_THRESHOLD_CENTS = 5.0    (master plan)

Pre-registered hypothesis tests:
    TA1 (coverage): filter activates on >= 30% of v1's eligible markets.
        Activation = filter has at least one input (poly_mid or
        sibling ladder data) for the candidate ticker.
    TA2 (improvement): mean(filter+v1 P&L) - mean(v1 P&L) >= +1pp.
    TA3 (volume preservation): filter does not skip more than 50%
        of v1's eligible trades.
    TA4 (statistical): bootstrap 95% CI of (filter mean - v1 mean)
        excludes zero, one-sided lower bound > 0.
    TA5 (per-series): TA2 holds for at least 2 distinct series-prefixes.

Read-only Kalshi data, no live calls, no operator action required.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V3 = REPO_ROOT / "data" / "v3"
DATA_V4 = REPO_ROOT / "data" / "v4"
DATA_V4.mkdir(parents=True, exist_ok=True)

# Make sure src/ is on the path. Project uses pyproject editable install,
# but for safety re-add.
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract  # noqa: E402
from kalshi_bot.strategy.favorite_maker import (  # noqa: E402
    FAVORITE_THRESHOLD,
    FAVORITE_UPPER_CAP,
    SLIPPAGE_ALLOWANCE,
)
from kalshi_bot_v4.filter import (  # noqa: E402
    FADE_THRESHOLD_CENTS_DEFAULT,
    MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
    evaluate_market,
    parse_ladder_ticker,
    series_prefix_of,
)


# Pre-registered hypothesis-test criteria
TA1_COVERAGE_FLOOR = 0.30
TA2_IMPROVEMENT_PP = 0.01
TA3_VOLUME_SKIP_CEILING = 0.50
TA4_BOOTSTRAP_CI = 0.95
TA4_BOOTSTRAP_N = 5000
TA4_BOOTSTRAP_SEED = 42
TA5_MIN_SERIES_PREFIXES = 2


@dataclass
class BacktestStats:
    """Per-strategy summary stats (bare v1 or filter+v1)."""
    n_trades: int
    mean_pnl: float
    median_pnl: float
    sd_pnl: float
    hit_rate: float
    ci_lower: float
    ci_upper: float


@dataclass
class FilterArmResult:
    """Stats for one filter arm (e.g., A1-only, A2-only, combined)."""
    arm_name: str
    fade_threshold_cents: float
    monotonicity_threshold_cents: float
    v1_stats: BacktestStats
    filter_stats: BacktestStats
    diff_mean_pp: float
    diff_ci_lower: float
    diff_ci_upper: float
    n_v1_eligible: int
    n_filter_traded: int
    n_filter_skipped: int
    skip_rate: float
    n_filter_activated: int  # filter had inputs (poly or ladder) for this market
    coverage: float
    skip_reason_counts: dict[str, int]
    per_series_diff_pp: dict[str, float]
    per_series_n: dict[str, int]
    per_series_n_filter_fired: dict[str, int]
    criteria: dict[str, bool]
    passes_all: bool


def realized_pnl_per_contract(yes_price: float, outcome: int) -> float:
    """v1's realized P&L formula: gross - round-trip maker fee - slippage."""
    gross = outcome - yes_price
    fee = 2.0 * kalshi_maker_fee_per_contract(yes_price)
    return gross - fee - SLIPPAGE_ALLOWANCE


def build_polymarket_lookup() -> dict[str, float]:
    """Build ticker -> poly_mid at T-35d.

    Source: data/v3/poly_kalshi_pairs.parquet. Returns only the rows
    with a non-null poly_mid_T_minus_35d.
    """
    pairs_path = DATA_V3 / "poly_kalshi_pairs.parquet"
    if not pairs_path.exists():
        print(f"WARNING: {pairs_path} missing; Polymarket lookup empty")
        return {}
    pairs = pd.read_parquet(pairs_path)
    valid = pairs.dropna(subset=["poly_mid_T_minus_35d"])
    return {
        str(row["ticker"]): float(row["poly_mid_T_minus_35d"])
        for _, row in valid.iterrows()
    }


def build_cross_market_data(inv: pd.DataFrame) -> dict[str, dict[int, float]]:
    """Build ladder_key -> {threshold: vwap_t35_wide} from the inventory.

    Only includes rows where the ticker parses as a ladder ticker AND
    vwap_t35_wide is non-null.

    The ladder data uses ALL siblings (eligible or not), since
    consistency violations are informative regardless of whether the
    sibling is itself v1-eligible.
    """
    out: dict[str, dict[int, float]] = {}
    for _, row in inv.iterrows():
        ticker = str(row["ticker"])
        vwap = row.get("vwap_t35_wide")
        if vwap is None or pd.isna(vwap):
            continue
        parsed = parse_ladder_ticker(ticker)
        if parsed is None:
            continue
        ladder_key, threshold = parsed
        out.setdefault(ladder_key, {})[threshold] = float(vwap)
    return out


def load_eligible_universe() -> pd.DataFrame:
    """Load v1's eligible universe from v3 inventory.

    Returns markets with:
        - eligible_wide=True (favorite >= 0.70 AND lifetime_ok)
        - non-null vwap_t35_wide
        - non-null outcome

    Adds:
        - 'series_prefix': first token of the ticker
        - 'effective_price': vwap_t35_wide (the price we'd have paid at
          T-35d). favorite_price in this inventory is from a different
          window; vwap is the trade-price proxy.
    """
    inv = pd.read_parquet(DATA_V3 / "probe_inventory_all_markets.parquet")
    elig = inv[
        inv["eligible_wide"]
        & inv["vwap_t35_wide"].notna()
        & inv["outcome"].notna()
    ].copy()
    elig["series_prefix"] = elig["ticker"].apply(series_prefix_of)
    elig["effective_price"] = elig["vwap_t35_wide"]
    # Filter the price band to v1's favorite range (>=0.70, <=0.95 per
    # favorite_maker upper cap added in Round 4 post-critic).
    elig = elig[
        (elig["effective_price"] >= FAVORITE_THRESHOLD)
        & (elig["effective_price"] <= FAVORITE_UPPER_CAP)
    ].copy()
    return elig.reset_index(drop=True)


def compute_stats(pnl_arr: np.ndarray) -> BacktestStats:
    n = int(pnl_arr.size)
    if n == 0:
        return BacktestStats(
            n_trades=0, mean_pnl=float("nan"), median_pnl=float("nan"),
            sd_pnl=float("nan"), hit_rate=float("nan"),
            ci_lower=float("nan"), ci_upper=float("nan"),
        )
    mean_v = float(pnl_arr.mean())
    median_v = float(np.median(pnl_arr))
    sd_v = float(pnl_arr.std(ddof=1)) if n > 1 else 0.0
    hit_rate = float((pnl_arr > 0).mean())
    if n >= 2:
        _, lo, hi = bootstrap_mean_ci(
            pnl_arr, n_resamples=TA4_BOOTSTRAP_N, ci=TA4_BOOTSTRAP_CI,
            rng_seed=TA4_BOOTSTRAP_SEED,
        )
    else:
        lo, hi = mean_v, mean_v
    return BacktestStats(
        n_trades=n, mean_pnl=mean_v, median_pnl=median_v, sd_pnl=sd_v,
        hit_rate=hit_rate, ci_lower=float(lo), ci_upper=float(hi),
    )


def bootstrap_diff_ci(
    v1_pnl_paired: np.ndarray,
    filter_pnl_paired: np.ndarray,
) -> tuple[float, float, float]:
    """Bootstrap the difference (filter mean - v1 mean) on PAIRED data.

    The filter is a SKIP overlay; whenever filter skips, the
    realized capital for that trade slot is 0 (no trade, no P&L).
    For the diff to be apples-to-apples we evaluate on the SAME
    candidate set in both arms.

    Inputs are aligned arrays where v1_pnl[i] is what v1 would have
    realized at row i, filter_pnl[i] is what the filter+v1 system
    would have realized (0 if filter skipped, v1's P&L otherwise).

    Mean here is averaged over the SAME slot count, not over n_trades.
    This is the per-candidate expected P&L.
    """
    n = v1_pnl_paired.size
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    diff = filter_pnl_paired - v1_pnl_paired
    if n == 1:
        return float(diff[0]), float(diff[0]), float(diff[0])
    rng = np.random.default_rng(TA4_BOOTSTRAP_SEED)
    n_resamples = TA4_BOOTSTRAP_N
    batch_size = max(1, min(n_resamples, max(1, 10_000_000 // max(n, 1))))
    means_list: list[np.ndarray] = []
    remaining = n_resamples
    while remaining > 0:
        b = min(batch_size, remaining)
        idx = rng.integers(0, n, size=(b, n))
        means_list.append(diff[idx].mean(axis=1))
        remaining -= b
    means = np.concatenate(means_list)
    alpha = (1.0 - TA4_BOOTSTRAP_CI) / 2.0
    lower = float(np.quantile(means, alpha))
    upper = float(np.quantile(means, 1.0 - alpha))
    sample_diff = float(diff.mean())
    return sample_diff, lower, upper


def run_arm(
    elig: pd.DataFrame,
    *,
    arm_name: str,
    fade_threshold_cents: float,
    monotonicity_threshold_cents: float,
    poly_lookup: Optional[dict[str, float]],
    cross_market_data: Optional[dict[str, dict[int, float]]],
) -> FilterArmResult:
    """Run a single filter arm against the eligible universe.

    arm_name is a label like 'A1+A2', 'A1_only', 'A2_only', 'A1_only_5c',
    etc. The poly_lookup and cross_market_data inputs control which
    sub-filter is active; passing None disables that sub-filter.
    """
    v1_pnl_list: list[float] = []
    filter_pnl_list: list[float] = []
    activated_list: list[bool] = []  # did the filter have any inputs?
    skip_reasons: dict[str, int] = {}
    trade_decisions: list[dict] = []

    for _, row in elig.iterrows():
        ticker = str(row["ticker"])
        series_ticker = str(row["series_ticker"])
        price = float(row["effective_price"])
        outcome = int(row["outcome"])
        v1_pnl = realized_pnl_per_contract(price, outcome)
        v1_pnl_list.append(v1_pnl)

        decision = evaluate_market(
            ticker=ticker,
            kalshi_price=price,
            series_ticker=series_ticker,
            poly_lookup=poly_lookup,
            cross_market_data=cross_market_data,
            fade_threshold_cents=fade_threshold_cents,
            monotonicity_threshold_cents=monotonicity_threshold_cents,
        )

        # "Activated" means the filter had at least one input
        # available for this market (poly_mid or ladder data).
        has_poly = decision.poly_mid is not None
        has_ladder = decision.cross_market_implied is not None
        activated = has_poly or has_ladder
        activated_list.append(activated)

        skip_reasons[decision.reason] = skip_reasons.get(decision.reason, 0) + 1
        if decision.should_trade:
            filter_pnl_list.append(v1_pnl)
        else:
            filter_pnl_list.append(0.0)

        trade_decisions.append({
            "ticker": ticker,
            "series_prefix": series_prefix_of(ticker),
            "series_ticker": series_ticker,
            "effective_price": price,
            "outcome": outcome,
            "v1_pnl": v1_pnl,
            "filter_pnl": v1_pnl if decision.should_trade else 0.0,
            "filter_should_trade": decision.should_trade,
            "filter_reason": decision.reason,
            "filter_poly_mid": decision.poly_mid,
            "filter_cross_implied": decision.cross_market_implied,
            "filter_confidence": decision.confidence,
            "filter_activated": activated,
        })

    v1_pnl_arr = np.array(v1_pnl_list, dtype=float)
    filter_pnl_arr = np.array(filter_pnl_list, dtype=float)
    activated_arr = np.array(activated_list, dtype=bool)

    # Bare v1 stats: trades for every eligible candidate.
    v1_stats = compute_stats(v1_pnl_arr)

    # Filter+v1 stats: averaging realized P&L over the SAME slot count
    # (skipped trades count as P&L=0). This is the right comparison
    # because the operator deploys the SAME capital count per cycle;
    # what matters is mean P&L PER CANDIDATE, not per trade taken.
    filter_stats = compute_stats(filter_pnl_arr)

    # Paired diff
    sample_diff, diff_lo, diff_hi = bootstrap_diff_ci(v1_pnl_arr, filter_pnl_arr)

    n_filter_traded = int(sum(d["filter_should_trade"] for d in trade_decisions))
    n_filter_skipped = len(trade_decisions) - n_filter_traded
    skip_rate = n_filter_skipped / max(1, len(trade_decisions))
    n_activated = int(activated_arr.sum())
    coverage = n_activated / max(1, len(trade_decisions))

    # Per-series breakdown (for TA5)
    df_decisions = pd.DataFrame(trade_decisions)
    per_series_diff_pp: dict[str, float] = {}
    per_series_n: dict[str, int] = {}
    per_series_n_filter_fired: dict[str, int] = {}
    for sp, sub in df_decisions.groupby("series_prefix"):
        per_series_diff_pp[str(sp)] = float(
            (sub["filter_pnl"] - sub["v1_pnl"]).mean()
        )
        per_series_n[str(sp)] = int(len(sub))
        per_series_n_filter_fired[str(sp)] = int(
            (~sub["filter_should_trade"]).sum()
        )

    # Pre-registered criteria
    ta2_pass = sample_diff >= TA2_IMPROVEMENT_PP
    ta3_pass = skip_rate <= TA3_VOLUME_SKIP_CEILING
    ta4_pass = diff_lo > 0.0
    # TA5: count series-prefixes where filter FIRED at least once AND
    # the per-series diff is positive. Series with no filter activations
    # have diff=0 by construction and should NOT count toward TA5.
    ta5_series_count = sum(
        1 for sp, v in per_series_diff_pp.items()
        if v > 0 and per_series_n_filter_fired.get(sp, 0) > 0
    )
    ta5_pass = ta5_series_count >= TA5_MIN_SERIES_PREFIXES
    ta1_pass = coverage >= TA1_COVERAGE_FLOOR

    criteria = {
        f"TA1_coverage_>=_{TA1_COVERAGE_FLOOR}": bool(ta1_pass),
        f"TA2_improvement_>=_{TA2_IMPROVEMENT_PP * 100:.1f}pp": bool(ta2_pass),
        f"TA3_skip_rate_<=_{TA3_VOLUME_SKIP_CEILING}": bool(ta3_pass),
        "TA4_diff_ci_lower_>_0": bool(ta4_pass),
        f"TA5_>={TA5_MIN_SERIES_PREFIXES}_series_improved": bool(ta5_pass),
    }
    passes_all = all(criteria.values())

    return FilterArmResult(
        arm_name=arm_name,
        fade_threshold_cents=fade_threshold_cents,
        monotonicity_threshold_cents=monotonicity_threshold_cents,
        v1_stats=v1_stats,
        filter_stats=filter_stats,
        diff_mean_pp=sample_diff,
        diff_ci_lower=diff_lo,
        diff_ci_upper=diff_hi,
        n_v1_eligible=len(trade_decisions),
        n_filter_traded=n_filter_traded,
        n_filter_skipped=n_filter_skipped,
        skip_rate=skip_rate,
        n_filter_activated=n_activated,
        coverage=coverage,
        skip_reason_counts=skip_reasons,
        per_series_diff_pp=per_series_diff_pp,
        per_series_n=per_series_n,
        per_series_n_filter_fired=per_series_n_filter_fired,
        criteria=criteria,
        passes_all=passes_all,
    )


def fmt_pp(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nan"
    return f"{x * 100:+.2f}pp"


def fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nan"
    return f"{x * 100:.1f}%"


def print_arm(arm: FilterArmResult) -> None:
    print(f"--- {arm.arm_name} (fade={arm.fade_threshold_cents:.0f}c, mono={arm.monotonicity_threshold_cents:.0f}c) ---")
    print(f"  n_eligible={arm.n_v1_eligible}, n_filter_traded={arm.n_filter_traded}, n_skipped={arm.n_filter_skipped} (skip {fmt_pct(arm.skip_rate)})")
    print(f"  Filter activated on {arm.n_filter_activated} / {arm.n_v1_eligible} ({fmt_pct(arm.coverage)})")
    print(f"  Skip reasons: {arm.skip_reason_counts}")
    print(f"  v1     mean P&L: {fmt_pp(arm.v1_stats.mean_pnl)} CI=[{fmt_pp(arm.v1_stats.ci_lower)}, {fmt_pp(arm.v1_stats.ci_upper)}] hit={fmt_pct(arm.v1_stats.hit_rate)}")
    print(f"  filter mean P&L: {fmt_pp(arm.filter_stats.mean_pnl)} CI=[{fmt_pp(arm.filter_stats.ci_lower)}, {fmt_pp(arm.filter_stats.ci_upper)}] hit={fmt_pct(arm.filter_stats.hit_rate)}")
    print(f"  diff (filter - v1): {fmt_pp(arm.diff_mean_pp)} CI=[{fmt_pp(arm.diff_ci_lower)}, {fmt_pp(arm.diff_ci_upper)}]")
    print("  Per-series diff (top 5 by n):")
    sorted_series = sorted(arm.per_series_n.items(), key=lambda kv: -kv[1])
    for sp, n in sorted_series[:5]:
        diff_pp = arm.per_series_diff_pp[sp]
        n_fired = arm.per_series_n_filter_fired.get(sp, 0)
        print(f"    {sp:<20} n={n:>4} diff={fmt_pp(diff_pp)} n_filter_fired={n_fired}")
    print("  Criteria:")
    for c, ok in arm.criteria.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {c}")
    print(f"  Verdict: {'PASS' if arm.passes_all else 'FAIL'} ALL TA1-TA5")
    print()


def serialize_arm(arm: FilterArmResult) -> dict:
    d = asdict(arm)
    # Make tuples/numeric types JSON-friendly
    d["v1_stats"] = asdict(arm.v1_stats)
    d["filter_stats"] = asdict(arm.filter_stats)
    return d


def main() -> None:
    print("=" * 80)
    print("V4 Phase 2 / Agent V4-E: Track A1 + A2 unified filter backtest")
    print("=" * 80)
    print()
    print(
        f"Pre-registered thresholds (LOCKED): "
        f"fade={FADE_THRESHOLD_CENTS_DEFAULT}c, "
        f"mono={MONOTONICITY_THRESHOLD_CENTS_DEFAULT}c"
    )
    print()
    print("Loading eligible universe ...")
    elig = load_eligible_universe()
    print(f"  Eligible markets: {len(elig)}")
    print(f"  Series prefixes: {sorted(elig['series_prefix'].unique())}")
    print("  Per-series eligible counts:")
    for sp, n in elig['series_prefix'].value_counts().items():
        print(f"    {sp}: {n}")
    print()

    print("Building Polymarket lookup ...")
    poly_lookup = build_polymarket_lookup()
    print(f"  Total ticker -> poly_mid entries: {len(poly_lookup)}")
    n_elig_with_poly = sum(1 for t in elig["ticker"] if t in poly_lookup)
    print(f"  Of eligible: {n_elig_with_poly} / {len(elig)} have a poly mid")
    print()

    print("Building cross-market ladder data ...")
    # Use the full inventory (eligible AND non-eligible siblings) for
    # ladder construction; consistency violations are informative on
    # any priced threshold.
    inv = pd.read_parquet(DATA_V3 / "probe_inventory_all_markets.parquet")
    cross_market_data = build_cross_market_data(inv)
    print(f"  Total ladder keys with data: {len(cross_market_data)}")
    def _has_sibling_in_ladder(t: str) -> bool:
        parsed = parse_ladder_ticker(t)
        if parsed is None:
            return False
        ladder_key, threshold = parsed
        ladder = cross_market_data.get(ladder_key)
        if ladder is None:
            return False
        return any(k != threshold for k in ladder)

    n_elig_in_ladder = sum(1 for t in elig["ticker"] if _has_sibling_in_ladder(t))
    print(
        f"  Of eligible: {n_elig_in_ladder} / {len(elig)} have ladder data "
        f"with at least 1 sibling"
    )
    print()

    arms: list[FilterArmResult] = []

    # ---- Pre-registered headline runs ----
    # Headline arm: combined A1 + A2 at locked thresholds
    arm_combined = run_arm(
        elig,
        arm_name="A1+A2 combined (LOCKED 7c/5c)",
        fade_threshold_cents=FADE_THRESHOLD_CENTS_DEFAULT,
        monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        poly_lookup=poly_lookup,
        cross_market_data=cross_market_data,
    )
    arms.append(arm_combined)
    print_arm(arm_combined)

    # A1-only arm
    arm_a1 = run_arm(
        elig,
        arm_name="A1 only (Polymarket-fade, 7c)",
        fade_threshold_cents=FADE_THRESHOLD_CENTS_DEFAULT,
        monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        poly_lookup=poly_lookup,
        cross_market_data=None,
    )
    arms.append(arm_a1)
    print_arm(arm_a1)

    # A2-only arm
    arm_a2 = run_arm(
        elig,
        arm_name="A2 only (cross-market consistency, 5c)",
        fade_threshold_cents=FADE_THRESHOLD_CENTS_DEFAULT,
        monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        poly_lookup=None,
        cross_market_data=cross_market_data,
    )
    arms.append(arm_a2)
    print_arm(arm_a2)

    # ---- Pre-registered pivot variants (per operator section "pivots
    # when blocked"). Each is a SEPARATE pre-registered test. We log
    # ALL outputs and let the data speak. No post-hoc threshold tuning. ----
    print("=" * 80)
    print("Pivot variants (pre-registered per operator brief)")
    print("=" * 80)
    print()

    pivot_specs = [
        ("Pivot 1: fade=5c, mono=5c", 5.0, 5.0),
        ("Pivot 2: fade=10c, mono=5c", 10.0, 5.0),
        ("Pivot 3: fade=7c, mono=3c", 7.0, 3.0),
        ("Pivot 4: fade=7c, mono=8c", 7.0, 8.0),
        ("Pivot 5: fade=5c, mono=3c (most aggressive)", 5.0, 3.0),
        ("Pivot 6: fade=10c, mono=8c (most conservative)", 10.0, 8.0),
    ]

    for label, fade_c, mono_c in pivot_specs:
        arm = run_arm(
            elig,
            arm_name=label,
            fade_threshold_cents=fade_c,
            monotonicity_threshold_cents=mono_c,
            poly_lookup=poly_lookup,
            cross_market_data=cross_market_data,
        )
        arms.append(arm)
        print_arm(arm)

    # ---- Sensitivity arms (sanity checks for outlier dependency) ----
    print("=" * 80)
    print("Sensitivity arms: A2 confidence-gated (require larger gap to fire)")
    print("=" * 80)
    print()

    # A2 with higher monotonicity thresholds: 12c, 15c, 20c, 25c.
    # If the A2 gain is robust, the per-trade improvement should be
    # consistent across confidence levels (or grow with higher gap).
    # If it's outlier-driven, the gain collapses as we exclude marginal
    # firings.
    for mono_c in (12.0, 15.0, 20.0, 25.0):
        arm = run_arm(
            elig,
            arm_name=f"A2 high-confidence: fade=7c, mono={mono_c:.0f}c",
            fade_threshold_cents=FADE_THRESHOLD_CENTS_DEFAULT,
            monotonicity_threshold_cents=mono_c,
            poly_lookup=poly_lookup,
            cross_market_data=cross_market_data,
        )
        arms.append(arm)
        print_arm(arm)

    # Persist all outputs
    out_path = DATA_V4 / "filter_backtest_results.json"
    serializable = {
        "thresholds_locked": {
            "fade_threshold_cents": FADE_THRESHOLD_CENTS_DEFAULT,
            "monotonicity_threshold_cents": MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        },
        "n_eligible": int(len(elig)),
        "poly_lookup_size": len(poly_lookup),
        "n_eligible_with_poly": n_elig_with_poly,
        "n_eligible_in_ladder": n_elig_in_ladder,
        "arms": [serialize_arm(a) for a in arms],
    }
    out_path.write_text(json.dumps(serializable, indent=2, default=str))
    print(f"Wrote {out_path}")

    # Also write per-trade decisions for audit
    print()
    print("Re-running headline combined to dump per-trade decisions ...")
    per_trade_rows: list[dict] = []
    for _, row in elig.iterrows():
        ticker = str(row["ticker"])
        series_ticker = str(row["series_ticker"])
        price = float(row["effective_price"])
        outcome = int(row["outcome"])
        decision = evaluate_market(
            ticker=ticker,
            kalshi_price=price,
            series_ticker=series_ticker,
            poly_lookup=poly_lookup,
            cross_market_data=cross_market_data,
            fade_threshold_cents=FADE_THRESHOLD_CENTS_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        )
        v1_pnl = realized_pnl_per_contract(price, outcome)
        per_trade_rows.append({
            "ticker": ticker,
            "series_prefix": series_prefix_of(ticker),
            "series_ticker": series_ticker,
            "effective_price": price,
            "outcome": outcome,
            "v1_pnl": v1_pnl,
            "filter_pnl": v1_pnl if decision.should_trade else 0.0,
            "filter_should_trade": decision.should_trade,
            "filter_reason": decision.reason,
            "filter_poly_mid": decision.poly_mid,
            "filter_cross_implied": decision.cross_market_implied,
            "filter_confidence": decision.confidence,
        })
    decisions_df = pd.DataFrame(per_trade_rows)
    decisions_df.to_parquet(DATA_V4 / "filter_backtest_decisions.parquet", index=False)
    print(f"Wrote {DATA_V4 / 'filter_backtest_decisions.parquet'} ({len(decisions_df)} rows)")


if __name__ == "__main__":
    main()
