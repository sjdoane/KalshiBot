"""Tests for the v16 lead-lag Gate A / Gate B evaluation core and the
night/week cluster bootstrap that backs it.
"""

from __future__ import annotations

import pytest

from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci
from kalshi_bot.analysis.lead_lag_gates import (
    GateResult,
    clv_dollars,
    evaluate_gate,
    is_fillable_marketable,
    marketable_settlement_pnl,
    season_verdict,
)


# --- cluster bootstrap -----------------------------------------------------
def test_cluster_bootstrap_positive_excludes_zero() -> None:
    # 20 all-positive nights with real across-night spread (0.03 vs 0.07): the
    # night-cluster CI is a genuine interval with its lower bound above zero.
    values: list[float] = []
    nights: list[str] = []
    for n in range(20):
        base = 0.03 if n % 2 == 0 else 0.07
        for j in range(2):
            values.append(base + (0.001 if j else -0.001))
            nights.append(f"night{n}")
    mean, lo, hi, k = cluster_bootstrap_mean_ci(values, nights, rng_seed=0)
    assert k == 20
    assert abs(mean - 0.05) < 1e-6
    assert lo > 0.0
    assert hi > lo


def test_cluster_bootstrap_straddles_zero() -> None:
    # Alternating large +/- clusters: mean ~0, CI must include zero.
    values: list[float] = []
    nights: list[str] = []
    for n in range(20):
        values.append(1.0 if n % 2 == 0 else -1.0)
        nights.append(f"night{n}")
    _mean, lo, hi, k = cluster_bootstrap_mean_ci(values, nights, rng_seed=0)
    assert k == 20
    assert lo < 0.0 < hi


def test_cluster_bootstrap_reproducible() -> None:
    values = [0.1, -0.2, 0.3, 0.0, 0.05]
    nights = ["a", "a", "b", "b", "c"]
    r1 = cluster_bootstrap_mean_ci(values, nights, rng_seed=42)
    r2 = cluster_bootstrap_mean_ci(values, nights, rng_seed=42)
    assert r1 == r2


def test_cluster_bootstrap_drops_nan() -> None:
    values = [0.1, float("nan"), 0.2]
    nights = ["a", "a", "b"]
    mean, _lo, _hi, k = cluster_bootstrap_mean_ci(values, nights, rng_seed=0)
    assert k == 2  # the NaN's cluster 'a' still present via the 0.1 obs
    assert abs(mean - 0.15) < 1e-9


def test_cluster_bootstrap_raises() -> None:
    with pytest.raises(ValueError):
        cluster_bootstrap_mean_ci([], [], rng_seed=0)
    with pytest.raises(ValueError):
        cluster_bootstrap_mean_ci([0.1, 0.2], ["a"], rng_seed=0)


# --- per-fire gate quantities ----------------------------------------------
def test_clv_dollars() -> None:
    assert clv_dollars(0.48, 0.52) == pytest.approx(0.04)
    assert clv_dollars(0.50, 0.45) == pytest.approx(-0.05)
    assert clv_dollars(None, 0.5) is None
    assert clv_dollars(0.5, None) is None


def test_is_fillable_marketable() -> None:
    # ask below the sportsbook level and enough depth -> fillable
    assert is_fillable_marketable(0.45, 0.50, 100.0, size=1.0) is True
    # ask above the sportsbook level -> not fillable (we would not overpay)
    assert is_fillable_marketable(0.52, 0.50, 100.0, size=1.0) is False
    # ask equal to target is fillable (<=)
    assert is_fillable_marketable(0.50, 0.50, 1.0, size=1.0) is True
    # insufficient depth -> not fillable
    assert is_fillable_marketable(0.45, 0.50, 0.0, size=1.0) is False
    assert is_fillable_marketable(None, 0.5, 10.0) is False


def test_marketable_settlement_pnl() -> None:
    # win at p=0.45: payoff 0.55 minus taker fee ceil(7*0.45*0.55)/100 = 0.02
    pnl_win = marketable_settlement_pnl(0.45, 1)
    assert pnl_win == pytest.approx(0.55 - 0.02)
    # loss at p=0.45: payoff -0.45 minus the same fee
    pnl_loss = marketable_settlement_pnl(0.45, 0)
    assert pnl_loss == pytest.approx(-0.45 - 0.02)
    assert marketable_settlement_pnl(None, 1) is None
    assert marketable_settlement_pnl(0.45, None) is None


# --- evaluate_gate ---------------------------------------------------------
def test_evaluate_gate_positive_passes() -> None:
    values: list[float | None] = []
    nights: list[str] = []
    weeks: list[str] = []
    for n in range(24):
        for j in range(2):
            values.append(0.06 + (0.002 if j else -0.002))
            nights.append(f"n{n}")
            weeks.append(f"w{n // 7}")
    res = evaluate_gate("A", values, nights, weeks, rng_seed=0)
    assert res is not None
    assert res.n_obs == 48
    assert res.n_nights == 24
    assert res.night_excludes_zero is True
    assert res.week_supports is True
    assert res.passed is True


def test_evaluate_gate_drops_none_and_handles_empty() -> None:
    values: list[float | None] = [None, 0.05, None]
    res = evaluate_gate("A", values, ["a", "a", "b"], ["w", "w", "w"], rng_seed=0)
    assert res is not None
    assert res.n_obs == 1
    assert evaluate_gate("A", [None, None], ["a", "b"], ["w", "w"]) is None


def test_evaluate_gate_straddle_fails() -> None:
    values: list[float | None] = []
    nights: list[str] = []
    weeks: list[str] = []
    for n in range(20):
        values.append(1.0 if n % 2 == 0 else -1.0)
        nights.append(f"n{n}")
        weeks.append(f"w{n // 4}")
    res = evaluate_gate("A", values, nights, weeks, rng_seed=0)
    assert res is not None
    assert res.passed is False


# --- season verdict --------------------------------------------------------
def _gate(name: str, *, n_nights: int, lower: float, upper: float, passed: bool) -> GateResult:
    return GateResult(
        name=name, n_obs=n_nights * 2, n_nights=n_nights, mean=(lower + upper) / 2,
        night_ci_lower=lower, night_ci_upper=upper, week_ci_lower=lower,
        week_ci_upper=upper, night_excludes_zero=lower > 0,
        week_supports=upper > 0, passed=passed,
    )


def test_season_verdict_branches() -> None:
    assert season_verdict(None, None)[0] == "NO_DATA"
    # underpowered: too few nights
    ga_few = _gate("A", n_nights=30, lower=-0.01, upper=0.05, passed=False)
    assert season_verdict(ga_few, None, min_nights=120)[0] == "UNDERPOWERED"
    # full sample, Gate A upper <= 0 -> kill
    ga_kill = _gate("A", n_nights=120, lower=-0.05, upper=-0.005, passed=False)
    assert season_verdict(ga_kill, None, min_nights=120)[0] == "KILL_NO_LAG"
    # full sample, sign-correct but straddles zero -> continue one season
    ga_straddle = _gate("A", n_nights=120, lower=-0.005, upper=0.03, passed=False)
    assert season_verdict(ga_straddle, None, min_nights=120)[0] == "CONTINUE_ONE_SEASON"
    # Gate A passes, Gate B fails -> lag not harvestable
    ga_pass = _gate("A", n_nights=120, lower=0.005, upper=0.03, passed=True)
    gb_fail = _gate("B", n_nights=120, lower=-0.01, upper=0.02, passed=False)
    assert season_verdict(ga_pass, gb_fail, min_nights=120)[0] == "LAG_NOT_HARVESTABLE"
    # both pass -> harvestable confirmed
    gb_pass = _gate("B", n_nights=120, lower=0.004, upper=0.02, passed=True)
    assert season_verdict(ga_pass, gb_pass, min_nights=120)[0] == "HARVESTABLE_CONFIRMED"
