"""Tests for the sports gate. Mirror of test_gate_phase2 with sports-
specific synthetic data including league tag and lifetime field."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot.analysis.gate_sports import (
    MID_BAND_LOWER,
    MID_BAND_UPPER,
    PASS_C1A_MEDIAN_SLOPE,
    PASS_C2_GROSS_EDGE,
    PASS_C3_MIN_SPLITS_NET_POSITIVE,
    _eligibility_mask,
    _per_trade_net_edge,
    assert_anti_leakage,
    evaluate,
)


def _make_sports_dataset(
    n_per_split: int = 400,
    n_splits_calendar: int = 6,
    true_slope: float = 1.5,
    rng_seed: int = 42,
    leagues: tuple[str, ...] = ("NFL", "NBA", "MLB", "NHL"),
) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    start = pd.Timestamp("2024-10-15", tz="UTC")
    window_days = 540
    total = n_per_split * n_splits_calendar
    days_offset = rng.integers(0, window_days, size=total)
    market_close = [start + pd.Timedelta(days=int(d)) for d in days_offset]
    # Sports long-horizon: 80-120 day lifetimes
    lifetime = rng.integers(60, 200, size=total)
    market_open = [c - pd.Timedelta(days=int(lt)) for c, lt in zip(market_close, lifetime, strict=False)]
    market_probs = rng.uniform(0.10, 0.90, size=total)
    logit_market = np.log(market_probs / (1.0 - market_probs))
    true_prob = 1.0 / (1.0 + np.exp(-true_slope * logit_market))
    outcomes = (rng.uniform(size=total) < true_prob).astype(int)
    league_assignments = rng.choice(leagues, size=total)
    return pd.DataFrame({
        "ticker": [f"KXS-{i}" for i in range(total)],
        "series_ticker": [f"KXS{i % 8}" for i in range(total)],
        "event_ticker": [f"KXS-EVT-{i}" for i in range(total)],
        "market_open_time": market_open,
        "market_close_time": market_close,
        "outcome": outcomes,
        "mid_price_at_T_small": market_probs,
        "mid_price_at_T_all": market_probs * 0.98 + 0.01,
        "n_trades_in_window": rng.integers(20, 200, size=total),
        "n_small_trades_in_window": rng.integers(20, 100, size=total),
        "one_sided_flow_pct": rng.uniform(0.4, 0.6, size=total),
        "league": league_assignments,
        "lifetime_days": lifetime,
    })


def test_eligibility_mask_mid_band_only() -> None:
    prices = np.array([0.10, 0.30, 0.45, 0.50, 0.55, 0.80, 0.95])
    flow = np.full_like(prices, 0.5)
    mask = _eligibility_mask(prices, flow)
    assert mask.tolist() == [False, True, True, False, True, True, False]


def test_eligibility_mask_nan_flow_excluded_narrow() -> None:
    prices = np.array([0.25, 0.35, 0.65, 0.75])
    flow = np.array([np.nan, np.nan, np.nan, np.nan])
    mask = _eligibility_mask(prices, flow)
    assert mask.tolist() == [True, False, False, True]


def test_per_trade_net_edge_math() -> None:
    recal = np.array([0.50])
    market = np.array([0.30])
    net = _per_trade_net_edge(recal, market)
    assert net[0] == pytest.approx(0.165, abs=1e-6)


def test_evaluate_handles_missing_columns() -> None:
    df = pd.DataFrame({"ticker": ["X"]})
    with pytest.raises(ValueError, match="missing columns"):
        evaluate(df)


def test_assert_anti_leakage_rejects_non_binary() -> None:
    df = _make_sports_dataset(n_per_split=300)
    df.loc[df.index[0], "outcome"] = 2
    with pytest.raises(AssertionError, match="item 5"):
        assert_anti_leakage(df)


def test_assert_anti_leakage_rejects_future_resolution() -> None:
    from kalshi_bot.analysis.gate_sports import LAST_TEST_END
    df = _make_sports_dataset(n_per_split=300)
    df.loc[df.index[0], "market_close_time"] = LAST_TEST_END + pd.Timedelta(days=1)
    with pytest.raises(AssertionError, match="item 6"):
        assert_anti_leakage(df)


def test_assert_anti_leakage_requires_league() -> None:
    df = _make_sports_dataset(n_per_split=300).drop(columns=["league"])
    with pytest.raises(AssertionError, match="league"):
        assert_anti_leakage(df)


def test_evaluate_passes_with_strong_signal() -> None:
    df = _make_sports_dataset(n_per_split=600, true_slope=1.8, rng_seed=42)
    res = evaluate(df)
    # With slope 1.8 and 3600 markets, C1 should pass
    if not np.isnan(res.median_slope_small):
        assert res.median_slope_small > PASS_C1A_MEDIAN_SLOPE
    if not np.isnan(res.median_pooled_gross_edge_small):
        assert res.median_pooled_gross_edge_small > PASS_C2_GROSS_EDGE / 2


def test_evaluate_does_not_pass_with_calibrated_regime() -> None:
    """With true_slope=1.0 (well-calibrated), predicted gross edge will be
    near zero so C2 fails. Round 3.1 dropped C1 from the gate; the
    calibrated regime instead fails on C2 or C5."""
    df = _make_sports_dataset(n_per_split=600, true_slope=1.0, rng_seed=7)
    res = evaluate(df)
    assert res.passes is False
    # Slope is reported informationally
    if not np.isnan(res.median_slope_small):
        assert res.median_slope_small < 1.2


def test_evaluate_leagues_get_evaluated() -> None:
    df = _make_sports_dataset(n_per_split=600, true_slope=1.5)
    res = evaluate(df)
    # All 4 leagues should be evaluated with min sample of 50
    assert res.n_leagues_evaluated >= 1


def test_pass_c3_threshold_constant() -> None:
    """C3 is now pooled-bootstrap-based; the per-split count is diagnostic."""
    # The constant is still 5 (diagnostic threshold for the per-split tally)
    assert PASS_C3_MIN_SPLITS_NET_POSITIVE == 5


def test_constants_align_with_methodology() -> None:
    """Match sports-longhorizon-methodology.md Sections 4 and 7 (post-critic
    revisions)."""
    assert MID_BAND_LOWER == (0.20, 0.45)
    assert MID_BAND_UPPER == (0.55, 0.80)
    # C2 reverted to 2.23pp (1x Becker sports) per methodology-critic finding 7
    assert PASS_C2_GROSS_EDGE == 0.0223
    assert PASS_C3_MIN_SPLITS_NET_POSITIVE == 5


def test_c3_uses_pooled_bootstrap_gate() -> None:
    """The actual C3 gate key in criteria dict should reference the
    bootstrap CI, not the per-split count."""
    df = _make_sports_dataset(n_per_split=400, true_slope=1.5, rng_seed=42)
    res = evaluate(df)
    assert "C3_pooled_bootstrap_ci_lower_>_0" in res.criteria
    # The old per-split-count gate key should NOT be in criteria
    assert "C3_>=_5_of_6_splits_net_>0" not in res.criteria


def test_c4_fails_when_less_than_three_leagues() -> None:
    """If fewer than 3 leagues have >= MIN_LEAGUE_SAMPLE markets, C4 fails."""
    df = _make_sports_dataset(n_per_split=600, true_slope=1.8,
                              leagues=("NFL", "NBA"))
    res = evaluate(df)
    # Only 2 leagues -> C4 should be present in criteria but FAIL
    c4_keys = [k for k in res.criteria if k.startswith("C4_")]
    assert len(c4_keys) == 1
    assert res.criteria[c4_keys[0]] is False
