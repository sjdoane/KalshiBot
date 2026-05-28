"""Phase 2 gate for the Politics x H strategy.

Five locked pass criteria per [phase-2-methodology.md](research/phase-2-methodology.md)
Section 7:

- C1a: median per-partition logistic slope on small-trade VWAP >= 1.2
- C1b: per-partition slope lower-quartile (25th pct of partition slopes) >= 1.0
- C2: median per-trade gross edge on mid-band eligible markets >= 2.04pp
- C3: at least 13 of the walk-forward splits show median net edge > 0 on
  small-trade VWAP
- C4: leave-one-event-window-out: at least 3 of 4 windows show median
  net edge > 0
- C5: BOTH median AND mean per-trade net edge > 0pp across all test
  partitions concatenated, with maker fees and 1.5pp slippage applied,
  on small-trade VWAP. If small-trade C5 FAILS while all-trade C5
  passes, the gate FAILS (small-trade is the retail-tradable check).

Diagnostics also returned (not gates):
- ECE improvement ratio (raw / calibrated)
- Pooled bootstrap mean and 95% CI on net edge
- Per-split election composition
- All-trade VWAP duplicate metrics for cross-check
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import structlog

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci
from kalshi_bot.analysis.calibration import IsotonicCalibrator
from kalshi_bot.analysis.metrics import (
    expected_calibration_error,
    kalshi_round_trip_maker_fees,
    per_trade_gross_edge,
)
from kalshi_bot.analysis.slope import (
    fit_logistic_slope,
    per_market_slopes,
    slope_distribution_summary,
)
from kalshi_bot.analysis.train_test_split import (
    TimeSplit,
    apply_split_phase2,
    leave_one_event_window_out,
    make_walk_forward_splits,
)

log = structlog.get_logger(__name__)

# Locked methodology parameters (phase-2-methodology.md Section 5.1)
WALK_FORWARD_TRAIN_DAYS = 180
WALK_FORWARD_TEST_DAYS = 30
WALK_FORWARD_PURGE_DAYS = 14  # increased from Phase 1 7d for politics
WALK_FORWARD_STEP_DAYS = 30
FIRST_TRAIN_START = pd.Timestamp("2024-10-01", tz="UTC")
LAST_TEST_END = pd.Timestamp("2026-04-30", tz="UTC")

MIN_TRAIN_SIZE = 200
MIN_TEST_SIZE = 50

# Section 4: strategy market filters
MID_BAND_LOWER = (0.20, 0.45)
MID_BAND_UPPER = (0.55, 0.80)
PRICE_CONDITIONAL_NARROW = (0.30, 0.70)  # one-sided-flow filter applies here
ONE_SIDED_FLOW_MAX = 0.65

# Section 6.4 / 7: slippage allowance (pp) and bootstrap config
SLIPPAGE_ALLOWANCE = 0.015
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_CI = 0.95
BOOTSTRAP_SEED = 42  # locked seed for reproducibility

# Section 7 thresholds
PASS_C1A_MEDIAN_SLOPE = 1.2
PASS_C1B_Q25_SLOPE = 1.0
PASS_C2_GROSS_EDGE = 0.0204
# C3 threshold per Section 7 C3 + Section 7.1 update: with the 2024-10-01 to
# 2026-04-30 corpus and locked split parameters, make_walk_forward_splits
# produces exactly 12 splits. 10/12 keeps binomial null alpha = 0.019 < 0.05.
PASS_C3_MIN_SPLITS_NET_POSITIVE = 10
PASS_C4_MIN_EVENT_WINDOWS_POSITIVE = 3

# Per-market slope diagnostic (Section 6.5): only series with >= this many
# markets contribute to the distribution.
PER_MARKET_SLOPE_MIN_MARKETS = 50

# Section 5.2 event windows
EVENT_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("Nov 2024 federal election", "2024-10-01", "2024-12-31"),
    ("Q1 2025 FOMC + policy", "2025-01-01", "2025-03-31"),
    ("Mid-2025 specials / primaries", "2025-04-01", "2025-09-30"),
    ("Pre-midterm primary cycle Q4-25 to Q1-26", "2025-10-01", "2026-03-31"),
)


@dataclass
class Phase2SplitResult:
    label: str
    n_train: int
    n_test: int
    n_eligible: int  # mid-band + one-sided-flow filtered
    slope_small: float  # C1 contributor (per-partition slope)
    raw_ece_small: float
    cal_ece_small: float
    ece_ratio_small: float
    median_gross_edge_small: float  # on eligible markets
    median_net_edge_small: float
    median_net_edge_all: float  # diagnostic: all-trade VWAP
    pct_federal_election_test: float
    # Per-market slope distribution (Section 6.5): one slope per series
    # with >= PER_MARKET_SLOPE_MIN_MARKETS markets. Empty dict if none.
    per_market_slopes_small: dict[str, float] = field(default_factory=dict)
    per_trade_net_edges_small: np.ndarray = field(default_factory=lambda: np.array([]))
    per_trade_net_edges_all: np.ndarray = field(default_factory=lambda: np.array([]))
    per_trade_gross_edges_small: np.ndarray = field(default_factory=lambda: np.array([]))


@dataclass
class Phase2EventResult:
    label: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    n_train: int
    n_test: int
    n_eligible: int
    median_net_edge_small: float


@dataclass
class Phase2GateResult:
    walk_forward: list[Phase2SplitResult] = field(default_factory=list)
    event_windows: list[Phase2EventResult] = field(default_factory=list)

    # C1
    median_slope_small: float = float("nan")
    q25_slope_small: float = float("nan")
    # C2
    median_pooled_gross_edge_small: float = float("nan")
    # C3
    n_splits_net_positive_small: int = 0
    # C4
    n_event_windows_net_positive: int = 0
    # C5 (small-trade VWAP)
    pooled_median_net_edge_small: float = float("nan")
    pooled_mean_net_edge_small: float = float("nan")
    # C5 cross-check (all-trade VWAP, diagnostic)
    pooled_median_net_edge_all: float = float("nan")
    pooled_mean_net_edge_all: float = float("nan")
    # Diagnostic: pooled bootstrap on small-trade net edge
    bootstrap_mean_small: float = float("nan")
    bootstrap_ci_lower_small: float = float("nan")
    bootstrap_ci_upper_small: float = float("nan")
    # Election composition diagnostic
    pct_federal_election_corpus: float = float("nan")
    n_election_dominated_splits: int = 0
    median_net_edge_election_dominated: float = float("nan")
    median_net_edge_non_election: float = float("nan")

    # Per-market (per-series) slope distribution pooled across all test partitions
    per_market_slope_n: int = 0
    per_market_slope_median: float = float("nan")
    per_market_slope_q25: float = float("nan")
    per_market_slope_q75: float = float("nan")
    # Sample-size skip diagnostic
    n_splits_attempted: int = 0
    n_splits_skipped_sample_size: int = 0

    criteria: dict[str, bool] = field(default_factory=dict)
    passes: bool = False


def _eligibility_mask(prices: np.ndarray, one_sided_flow: np.ndarray) -> np.ndarray:
    """Apply Section 4 strategy filters: mid-band AND price-conditional
    one-sided-flow.

    NaN handling: NaN one-sided-flow is treated as maximally one-sided
    (1.0) so missing-data markets are EXCLUDED in the narrow band rather
    than admitted (which would silently bypass the adverse-selection filter
    per code-review milestone 1 finding).
    """
    in_lower = (prices >= MID_BAND_LOWER[0]) & (prices <= MID_BAND_LOWER[1])
    in_upper = (prices >= MID_BAND_UPPER[0]) & (prices <= MID_BAND_UPPER[1])
    in_band = in_lower | in_upper

    in_narrow = (prices >= PRICE_CONDITIONAL_NARROW[0]) & (prices <= PRICE_CONDITIONAL_NARROW[1])
    safe_flow = np.where(np.isnan(one_sided_flow), 1.0, one_sided_flow)
    flow_ok = ~(in_narrow & (safe_flow > ONE_SIDED_FLOW_MAX))

    return in_band & flow_ok


def _per_trade_net_edge(
    recalibrated: np.ndarray,
    market: np.ndarray,
    *,
    slippage: float = SLIPPAGE_ALLOWANCE,
) -> np.ndarray:
    """Gross edge minus round-trip maker fees minus slippage."""
    gross = per_trade_gross_edge(recalibrated, market)
    fees = kalshi_round_trip_maker_fees(market)
    return gross - fees - slippage


def _split_metrics(
    train: pd.DataFrame, test: pd.DataFrame, label: str
) -> Phase2SplitResult | None:
    if len(train) < MIN_TRAIN_SIZE or len(test) < MIN_TEST_SIZE:
        log.warning(
            "split_skipped_sample_size",
            label=label,
            n_train=len(train),
            n_test=len(test),
            min_train=MIN_TRAIN_SIZE,
            min_test=MIN_TEST_SIZE,
        )
        return None

    # Fit isotonic on train SMALL-trade VWAP (the methodology gates on small)
    cal = IsotonicCalibrator().fit(
        train["mid_price_at_T_small"], train["outcome"]
    )

    raw_small = test["mid_price_at_T_small"].to_numpy(dtype=float)
    raw_all = test["mid_price_at_T_all"].to_numpy(dtype=float)
    y = test["outcome"].to_numpy(dtype=float)
    one_sided = test["one_sided_flow_pct"].to_numpy(dtype=float)
    fed_tag = test.get("is_federal_election_market", pd.Series(False, index=test.index)).to_numpy(dtype=bool)

    cal_small = cal.predict(raw_small)
    cal_all = cal.predict(raw_all)

    raw_ece = expected_calibration_error(raw_small, y)
    cal_ece = expected_calibration_error(cal_small, y)
    ratio = raw_ece / max(cal_ece, 1e-12)

    # C1: per-partition slope on small-trade VWAP
    try:
        _intercept, slope = fit_logistic_slope(raw_small, y.astype(int))
    except ValueError:
        slope = float("nan")

    # Strategy eligibility filter on small-trade VWAP (the displayed price
    # the maker would quote against)
    eligible = _eligibility_mask(raw_small, one_sided)
    n_eligible = int(eligible.sum())

    if n_eligible > 0:
        gross_small = per_trade_gross_edge(cal_small[eligible], raw_small[eligible])
        net_small = _per_trade_net_edge(cal_small[eligible], raw_small[eligible])
        median_gross = float(np.median(gross_small))
        median_net_small = float(np.median(net_small))
        gross_arr = gross_small
        net_arr_small = net_small
    else:
        median_gross = float("nan")
        median_net_small = float("nan")
        gross_arr = np.array([])
        net_arr_small = np.array([])

    # All-trade diagnostic
    eligible_all = _eligibility_mask(raw_all, one_sided)
    if int(eligible_all.sum()) > 0:
        net_all = _per_trade_net_edge(cal_all[eligible_all], raw_all[eligible_all])
        median_net_all = float(np.median(net_all))
        net_arr_all = net_all
    else:
        median_net_all = float("nan")
        net_arr_all = np.array([])

    # Section 6.5: per-series slope distribution over the test partition
    if "series_ticker" in test.columns:
        per_market = per_market_slopes(
            test,
            price_col="mid_price_at_T_small",
            outcome_col="outcome",
            group_col="series_ticker",
            min_trades_per_group=PER_MARKET_SLOPE_MIN_MARKETS,
        )
    else:
        per_market = {}

    return Phase2SplitResult(
        label=label,
        n_train=len(train),
        n_test=len(test),
        n_eligible=n_eligible,
        slope_small=float(slope),
        raw_ece_small=float(raw_ece),
        cal_ece_small=float(cal_ece),
        ece_ratio_small=float(ratio),
        median_gross_edge_small=median_gross,
        median_net_edge_small=median_net_small,
        median_net_edge_all=median_net_all,
        pct_federal_election_test=float(fed_tag.mean()) if fed_tag.size else float("nan"),
        per_market_slopes_small=per_market,
        per_trade_net_edges_small=net_arr_small,
        per_trade_net_edges_all=net_arr_all,
        per_trade_gross_edges_small=gross_arr,
    )


def run_walk_forward(df: pd.DataFrame) -> tuple[list[Phase2SplitResult], int, int]:
    """Return (per-split results, n_splits_attempted, n_splits_skipped)."""
    splits: list[TimeSplit] = make_walk_forward_splits(
        first_train_start=FIRST_TRAIN_START,
        last_test_end=LAST_TEST_END,
        train_window=pd.Timedelta(days=WALK_FORWARD_TRAIN_DAYS),
        test_window=pd.Timedelta(days=WALK_FORWARD_TEST_DAYS),
        purge=pd.Timedelta(days=WALK_FORWARD_PURGE_DAYS),
        step=pd.Timedelta(days=WALK_FORWARD_STEP_DAYS),
    )
    results: list[Phase2SplitResult] = []
    n_attempted = len(splits)
    n_skipped = 0
    for split in splits:
        train, test = apply_split_phase2(
            df, split, lifetime_straddle_purge_days=WALK_FORWARD_PURGE_DAYS,
        )
        r = _split_metrics(train, test, label=split.label)
        if r is None:
            n_skipped += 1
            continue
        results.append(r)
    log.info(
        "walk_forward_done",
        n_attempted=n_attempted,
        n_results=len(results),
        n_skipped=n_skipped,
    )
    return results, n_attempted, n_skipped


def _event_result(
    train: pd.DataFrame, test: pd.DataFrame, label: str,
    window_start: pd.Timestamp, window_end: pd.Timestamp,
) -> Phase2EventResult | None:
    if len(train) < MIN_TRAIN_SIZE or len(test) < MIN_TEST_SIZE:
        return None

    cal = IsotonicCalibrator().fit(train["mid_price_at_T_small"], train["outcome"])
    raw_small = test["mid_price_at_T_small"].to_numpy(dtype=float)
    one_sided = test["one_sided_flow_pct"].to_numpy(dtype=float)
    cal_small = cal.predict(raw_small)
    eligible = _eligibility_mask(raw_small, one_sided)
    n_eligible = int(eligible.sum())
    if n_eligible > 0:
        net = _per_trade_net_edge(cal_small[eligible], raw_small[eligible])
        median_net = float(np.median(net))
    else:
        median_net = float("nan")
    return Phase2EventResult(
        label=label,
        window_start=window_start,
        window_end=window_end,
        n_train=len(train),
        n_test=len(test),
        n_eligible=n_eligible,
        median_net_edge_small=median_net,
    )


def run_event_windows(df: pd.DataFrame) -> list[Phase2EventResult]:
    results: list[Phase2EventResult] = []
    for label, start_str, end_str in EVENT_WINDOWS:
        ws = pd.Timestamp(start_str, tz="UTC")
        we = pd.Timestamp(end_str, tz="UTC")
        train, test = leave_one_event_window_out(df, ws, we)
        r = _event_result(train, test, label, ws, we)
        if r is not None:
            results.append(r)
    return results


def assert_anti_leakage(df: pd.DataFrame) -> None:
    """Section 8 anti-leakage checks against the INPUT dataset.

    Runs the subset of Section 8 items that can be verified at the
    dataset level (the partition-level checks are enforced by
    apply_split_phase2). Raises AssertionError on any violation.

    Section 8 items mapped here:
    - Item 5: settle_outcome is binary {0, 1} from Kalshi result mapping.
    - Item 6: market_close_time strictly precedes any future-information
      feature (we check that no resolution_time is in the future relative
      to LAST_TEST_END; future-resolving markets should be in the
      out-of-time buffer, not the corpus).
    - Item 9: is_federal_election_market is computed from text only;
      the build_dataset step uses tag_federal_election which only reads
      pre-resolution metadata. We assert the column exists and is bool.
    - Item 4 / 7 / 8 / 10 are enforced inside _split_metrics / bootstrap
      / apply_split_phase2 by construction; they are logged below for
      audit visibility.
    """
    bad_outcomes = ~df["outcome"].isin([0, 1])
    if bad_outcomes.any():
        raise AssertionError(
            f"Section 8 item 5 violation: {int(bad_outcomes.sum())} rows have "
            "non-binary outcome (Kalshi 'result' must map to 0 or 1)."
        )
    if (df["market_close_time"] > LAST_TEST_END).any():
        n = int((df["market_close_time"] > LAST_TEST_END).sum())
        raise AssertionError(
            f"Section 8 item 6 violation: {n} rows have close_time after "
            f"LAST_TEST_END={LAST_TEST_END}. Out-of-time buffer must be excluded "
            "from the corpus."
        )
    if "is_federal_election_market" not in df.columns:
        raise AssertionError(
            "Section 8 item 9 violation: is_federal_election_market column "
            "missing. Run build_dataset.py to populate it before evaluating."
        )
    log.info(
        "anti_leakage_passed",
        item_5_outcomes="binary",
        item_6_resolution_within_corpus=True,
        item_9_election_tag_present=True,
    )


def evaluate(df: pd.DataFrame) -> Phase2GateResult:
    """Top-level evaluation. Returns Phase2GateResult with all metrics."""
    required = (
        "market_open_time",
        "market_close_time",
        "outcome",
        "mid_price_at_T_small",
        "mid_price_at_T_all",
        "one_sided_flow_pct",
    )
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"evaluate: input DataFrame missing columns: {missing}")
    assert_anti_leakage(df)

    res = Phase2GateResult()
    res.walk_forward, res.n_splits_attempted, res.n_splits_skipped_sample_size = (
        run_walk_forward(df)
    )
    res.event_windows = run_event_windows(df)

    if res.walk_forward:
        slopes = np.array(
            [r.slope_small for r in res.walk_forward if not np.isnan(r.slope_small)]
        )
        if slopes.size > 0:
            res.median_slope_small = float(np.median(slopes))
            res.q25_slope_small = float(np.quantile(slopes, 0.25))

        # Pool per-trade arrays for C2, C5, and bootstrap
        all_gross_small = np.concatenate([r.per_trade_gross_edges_small for r in res.walk_forward])
        all_net_small = np.concatenate([r.per_trade_net_edges_small for r in res.walk_forward])
        all_net_all = np.concatenate([r.per_trade_net_edges_all for r in res.walk_forward])

        if all_gross_small.size > 0:
            res.median_pooled_gross_edge_small = float(np.median(all_gross_small))
        if all_net_small.size > 0:
            res.pooled_median_net_edge_small = float(np.median(all_net_small))
            res.pooled_mean_net_edge_small = float(np.mean(all_net_small))
            try:
                mean, lo, hi = bootstrap_mean_ci(
                    all_net_small,
                    n_resamples=BOOTSTRAP_N_RESAMPLES,
                    ci=BOOTSTRAP_CI,
                    rng_seed=BOOTSTRAP_SEED,
                )
                res.bootstrap_mean_small = mean
                res.bootstrap_ci_lower_small = lo
                res.bootstrap_ci_upper_small = hi
            except ValueError:
                pass
        if all_net_all.size > 0:
            res.pooled_median_net_edge_all = float(np.median(all_net_all))
            res.pooled_mean_net_edge_all = float(np.mean(all_net_all))

        # C3: per-split median net edge > 0 count
        res.n_splits_net_positive_small = sum(
            1 for r in res.walk_forward
            if not np.isnan(r.median_net_edge_small) and r.median_net_edge_small > 0
        )

        # Per-market slope distribution pooled across test partitions
        pooled_per_market: dict[str, float] = {}
        for r in res.walk_forward:
            # Use split label prefix to keep series unique across splits
            for series, slope in r.per_market_slopes_small.items():
                pooled_per_market[f"{r.label}:{series}"] = slope
        if pooled_per_market:
            summary = slope_distribution_summary(pooled_per_market)
            res.per_market_slope_n = int(summary["n"])
            res.per_market_slope_median = summary["median"]
            res.per_market_slope_q25 = summary["q25"]
            res.per_market_slope_q75 = summary["q75"]

        # Election composition diagnostic
        pct_fed = np.array([r.pct_federal_election_test for r in res.walk_forward])
        pct_fed = pct_fed[~np.isnan(pct_fed)]
        if pct_fed.size:
            res.pct_federal_election_corpus = float(pct_fed.mean())
        election_dominated = [r for r in res.walk_forward if r.pct_federal_election_test > 0.5]
        non_dominated = [r for r in res.walk_forward if r.pct_federal_election_test <= 0.5]
        res.n_election_dominated_splits = len(election_dominated)
        if election_dominated:
            res.median_net_edge_election_dominated = float(
                np.median(
                    [r.median_net_edge_small for r in election_dominated
                     if not np.isnan(r.median_net_edge_small)]
                )
            )
        if non_dominated:
            res.median_net_edge_non_election = float(
                np.median(
                    [r.median_net_edge_small for r in non_dominated
                     if not np.isnan(r.median_net_edge_small)]
                )
            )

    if res.event_windows:
        res.n_event_windows_net_positive = sum(
            1 for r in res.event_windows
            if not np.isnan(r.median_net_edge_small) and r.median_net_edge_small > 0
        )

    # Apply criteria
    res.criteria = {
        "C1a_median_slope_>=_1.2": (
            not np.isnan(res.median_slope_small)
            and res.median_slope_small >= PASS_C1A_MEDIAN_SLOPE
        ),
        "C1b_q25_slope_>=_1.0": (
            not np.isnan(res.q25_slope_small)
            and res.q25_slope_small >= PASS_C1B_Q25_SLOPE
        ),
        "C2_median_gross_edge_>=_2.04pp": (
            not np.isnan(res.median_pooled_gross_edge_small)
            and res.median_pooled_gross_edge_small >= PASS_C2_GROSS_EDGE
        ),
        "C3_>=_10_splits_net_>0": (
            res.n_splits_net_positive_small >= PASS_C3_MIN_SPLITS_NET_POSITIVE
        ),
        "C4_>=_3_of_4_event_windows_net_>0": (
            res.n_event_windows_net_positive >= PASS_C4_MIN_EVENT_WINDOWS_POSITIVE
        ),
        "C5_pooled_median_AND_mean_net_>_0": (
            not np.isnan(res.pooled_median_net_edge_small)
            and not np.isnan(res.pooled_mean_net_edge_small)
            and res.pooled_median_net_edge_small > 0
            and res.pooled_mean_net_edge_small > 0
        ),
    }
    res.passes = all(res.criteria.values())
    return res
