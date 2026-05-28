"""Tests for the Phase 2 gate (Politics x H).

The gate operates on a synthetic dataset whose schema matches the
phase-2 build_dataset.py output. We construct datasets with known
calibration regimes and verify:

- the slope estimator recovers the regime
- the gross/net edge math matches manual computation
- the criteria correctly accept TRUE-EDGE data and reject ZERO-EDGE data
- the strategy filters (mid-band, one-sided-flow) shape the eligible set
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot.analysis.gate_phase2 import (
    EVENT_WINDOWS,
    MID_BAND_LOWER,
    MID_BAND_UPPER,
    ONE_SIDED_FLOW_MAX,
    PASS_C1A_MEDIAN_SLOPE,
    PASS_C2_GROSS_EDGE,
    _eligibility_mask,
    _per_trade_net_edge,
    evaluate,
)


def _make_dataset(
    n_per_split: int = 300,
    n_splits_calendar: int = 17,
    true_slope: float = 1.5,
    rng_seed: int = 42,
    federal_election_rate: float = 0.5,
) -> pd.DataFrame:
    """Generate a synthetic politics dataset with the Phase 2 schema.

    Markets are spread across the 2024-10-01 to 2026-04-30 window, each
    with a small lifetime (~30 days) so the lifetime-straddle filter does
    not eliminate them. Outcomes are drawn from a logistic model with
    `true_slope` so the strategy thesis is empirically realized.
    """
    rng = np.random.default_rng(rng_seed)
    start = pd.Timestamp("2024-10-15", tz="UTC")
    window_days = 540  # approximately the corpus
    total = n_per_split * n_splits_calendar

    # Spread resolution times approximately uniformly
    days_offset = rng.integers(0, window_days, size=total)
    market_close = [start + pd.Timedelta(days=int(d)) for d in days_offset]
    # Short-lifetime markets: open 25 days before close
    market_open = [c - pd.Timedelta(days=25) for c in market_close]

    # Market price uniform in [0.10, 0.90]
    market_probs = rng.uniform(0.10, 0.90, size=total)
    # Outcome from compressed regime: logit(true) = slope * logit(price)
    logit_market = np.log(market_probs / (1.0 - market_probs))
    true_prob = 1.0 / (1.0 + np.exp(-true_slope * logit_market))
    outcomes = (rng.uniform(size=total) < true_prob).astype(int)

    # Federal election tag: random Bernoulli with the requested rate
    fed_tag = rng.uniform(size=total) < federal_election_rate

    return pd.DataFrame(
        {
            "ticker": [f"KXTEST-{i}" for i in range(total)],
            "series_ticker": [f"KXTEST{i % 5}" for i in range(total)],
            "event_ticker": [f"KXTEST-EVT-{i}" for i in range(total)],
            "market_open_time": market_open,
            "market_close_time": market_close,
            "outcome": outcomes,
            "mid_price_at_T_small": market_probs,
            # All-trade VWAP slightly different to mimic trade-size scale effect
            "mid_price_at_T_all": market_probs * 0.98 + 0.01,
            "n_trades_in_window": rng.integers(20, 200, size=total),
            "n_small_trades_in_window": rng.integers(20, 100, size=total),
            "one_sided_flow_pct": rng.uniform(0.4, 0.6, size=total),
            "is_federal_election_market": fed_tag,
        }
    )


def test_eligibility_mask_mid_band_lower() -> None:
    prices = np.array([0.10, 0.20, 0.30, 0.45, 0.50, 0.55, 0.80, 0.90])
    flow = np.full_like(prices, 0.5)  # below threshold
    mask = _eligibility_mask(prices, flow)
    # Inside lower band [0.20, 0.45]: indices 1, 2, 3
    # Inside upper band [0.55, 0.80]: indices 5, 6
    assert mask.tolist() == [False, True, True, True, False, True, True, False]


def test_eligibility_mask_price_conditional_one_sided_flow() -> None:
    """One-sided-flow > 65% only excludes if price in narrow [0.30, 0.70]."""
    prices = np.array([0.25, 0.35, 0.65, 0.75])
    flow = np.full_like(prices, 0.70)  # ABOVE threshold
    mask = _eligibility_mask(prices, flow)
    # 0.25 in lower band, NOT in narrow [0.30, 0.70] -> KEEP
    # 0.35 in lower band, IN narrow -> EXCLUDE
    # 0.65 in upper band, IN narrow -> EXCLUDE
    # 0.75 in upper band, NOT in narrow -> KEEP
    assert mask.tolist() == [True, False, False, True]


def test_eligibility_mask_low_flow_keeps_everything_in_band() -> None:
    prices = np.array([0.30, 0.45, 0.55, 0.70])
    flow = np.full_like(prices, 0.5)  # well below threshold
    mask = _eligibility_mask(prices, flow)
    assert mask.tolist() == [True, True, True, True]


def test_per_trade_net_edge_math() -> None:
    """Net edge = gross - round_trip_maker_fee - 1.5pp slippage."""
    # gross = |recalibrated - market|
    recal = np.array([0.50])
    market = np.array([0.30])
    # Gross = 0.20
    # round-trip maker fee at P=0.30 = 2 * ceil(0.0175 * 100 * 0.30 * 0.70) / 100
    #                                = 2 * ceil(0.3675) / 100 = 2 * 1 / 100 = 0.02
    # Slippage = 0.015
    # Net = 0.20 - 0.02 - 0.015 = 0.165
    net = _per_trade_net_edge(recal, market)
    assert net[0] == pytest.approx(0.165, abs=1e-6)


def test_evaluate_passes_with_strong_compressed_regime() -> None:
    """A synthetic dataset with slope=1.8 (above 1.2 threshold) and enough
    rows should pass C1; the other criteria may or may not all pass
    depending on per-split sample variance."""
    df = _make_dataset(
        n_per_split=400, n_splits_calendar=17, true_slope=1.8, rng_seed=7,
    )
    res = evaluate(df)
    # C1a should pass (true slope = 1.8 >> 1.2)
    assert res.median_slope_small > PASS_C1A_MEDIAN_SLOPE
    # C2: pooled gross edge should clear 2.04pp
    assert res.median_pooled_gross_edge_small > PASS_C2_GROSS_EDGE


def test_evaluate_fails_c1_with_calibrated_regime() -> None:
    """A synthetic dataset with slope=1.0 (well-calibrated) should fail C1
    because there's no compression."""
    df = _make_dataset(
        n_per_split=400, n_splits_calendar=17, true_slope=1.0, rng_seed=7,
    )
    res = evaluate(df)
    # C1a should fail (true slope = 1.0 < 1.2 threshold)
    assert not res.criteria["C1a_median_slope_>=_1.2"]
    # Strategy should not pass overall
    assert res.passes is False


def test_evaluate_handles_missing_columns() -> None:
    """Missing required columns should raise a clear error."""
    df = pd.DataFrame({"ticker": ["X"]})
    with pytest.raises(ValueError, match="missing columns"):
        evaluate(df)


def test_evaluate_returns_per_split_election_composition() -> None:
    """Election composition diagnostic populated for each split."""
    df = _make_dataset(
        n_per_split=300, n_splits_calendar=17, true_slope=1.5,
        federal_election_rate=0.7, rng_seed=11,
    )
    res = evaluate(df)
    # With 70% federal-election rate the average should be near 0.7
    assert 0.5 < res.pct_federal_election_corpus < 0.9


def test_evaluate_bootstrap_ci_populated() -> None:
    df = _make_dataset(n_per_split=400, true_slope=1.5, rng_seed=42)
    res = evaluate(df)
    if res.walk_forward and any(r.per_trade_net_edges_small.size > 0 for r in res.walk_forward):
        # If any per-trade nets were computed, bootstrap should be set
        assert not np.isnan(res.bootstrap_mean_small)
        assert res.bootstrap_ci_lower_small <= res.bootstrap_mean_small <= res.bootstrap_ci_upper_small


def test_event_windows_constant_well_formed() -> None:
    """All event windows are valid ISO dates with start before end."""
    for label, start_str, end_str in EVENT_WINDOWS:
        assert isinstance(label, str) and label
        s = pd.Timestamp(start_str, tz="UTC")
        e = pd.Timestamp(end_str, tz="UTC")
        assert s < e


def test_constants_align_with_methodology() -> None:
    """Verify locked constants match phase-2-methodology.md Sections 4 and 7."""
    assert MID_BAND_LOWER == (0.20, 0.45)
    assert MID_BAND_UPPER == (0.55, 0.80)
    assert ONE_SIDED_FLOW_MAX == 0.65
    assert PASS_C1A_MEDIAN_SLOPE == 1.2
    assert PASS_C2_GROSS_EDGE == 0.0204


def test_eligibility_mask_nan_flow_excluded_in_narrow_band() -> None:
    """NaN one-sided-flow is treated as maximally one-sided and EXCLUDED
    inside the narrow [0.30, 0.70] band."""
    prices = np.array([0.25, 0.35, 0.65, 0.75])
    flow = np.array([np.nan, np.nan, np.nan, np.nan])
    mask = _eligibility_mask(prices, flow)
    # 0.25, 0.75 NOT in narrow band -> kept regardless of flow
    # 0.35, 0.65 IN narrow band -> excluded because NaN treated as max one-sided
    assert mask.tolist() == [True, False, False, True]


def test_evaluate_anti_leakage_rejects_non_binary_outcome() -> None:
    from kalshi_bot.analysis.gate_phase2 import assert_anti_leakage
    df = _make_dataset(n_per_split=300, true_slope=1.5)
    df.loc[df.index[0], "outcome"] = 2  # break the binary invariant
    with pytest.raises(AssertionError, match="item 5"):
        assert_anti_leakage(df)


def test_evaluate_anti_leakage_rejects_future_resolution() -> None:
    from kalshi_bot.analysis.gate_phase2 import LAST_TEST_END, assert_anti_leakage
    df = _make_dataset(n_per_split=300, true_slope=1.5)
    df.loc[df.index[0], "market_close_time"] = LAST_TEST_END + pd.Timedelta(days=1)
    with pytest.raises(AssertionError, match="item 6"):
        assert_anti_leakage(df)


def test_evaluate_anti_leakage_requires_federal_election_column() -> None:
    from kalshi_bot.analysis.gate_phase2 import assert_anti_leakage
    df = _make_dataset(n_per_split=300, true_slope=1.5)
    df = df.drop(columns=["is_federal_election_market"])
    with pytest.raises(AssertionError, match="item 9"):
        assert_anti_leakage(df)


def test_evaluate_tracks_skipped_splits() -> None:
    """With a tiny corpus, all splits hit the MIN_TRAIN_SIZE skip; the
    result must record n_splits_attempted and n_splits_skipped_sample_size."""
    df = _make_dataset(n_per_split=10, n_splits_calendar=2, true_slope=1.5)
    res = evaluate(df)
    # All splits should be skipped (under MIN_TRAIN_SIZE=200)
    assert res.n_splits_attempted >= 1
    assert res.n_splits_skipped_sample_size == res.n_splits_attempted
    assert len(res.walk_forward) == 0
    # Gate must fail when no splits ran
    assert res.passes is False


def test_per_market_slope_distribution_populated() -> None:
    """With enough markets per series, the per-series slope diagnostic is
    populated in the result."""
    df = _make_dataset(n_per_split=500, n_splits_calendar=17, true_slope=1.5)
    res = evaluate(df)
    if any(r.per_market_slopes_small for r in res.walk_forward):
        assert res.per_market_slope_n > 0
        assert not np.isnan(res.per_market_slope_median)
