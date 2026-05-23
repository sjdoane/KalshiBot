"""Integration smoke test for the Phase 1.5 gate evaluator.

The component-level tests (train_test_split, metrics, calibration) cover
the building blocks. This file just verifies that evaluate() composes
those components correctly and produces a GateResult with the expected
shape on a small synthetic biased dataset.

Earlier attempts at synthetic PASS/FAIL tests revealed a subtlety: my
"noise" baseline (uniform prices + fixed 50% outcomes) is actually a real
arbitrage opportunity, not noise. The gate correctly identified it.
The proper "no edge" baseline is a perfectly calibrated market, but a
finite-sample calibrated market still produces enough fluctuation that
deterministic PASS/FAIL assertions are fragile. We rely on the real
Kalshi data to validate the gate end-to-end.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from kalshi_bot.analysis.gate import evaluate

CITIES = ["NY", "CHI", "MIA", "LAX", "DEN"]
START = pd.Timestamp("2024-01-01", tz="UTC")


def _row(
    *, ticker: str, city: str, occurrence: pd.Timestamp, mid: float, outcome: int
) -> dict:
    open_t = occurrence - pd.Timedelta(hours=24)
    close_t = occurrence + pd.Timedelta(hours=8)
    return {
        "ticker": ticker,
        "series_ticker": f"KXHIGH{city}",
        "city": city,
        "occurrence_date": occurrence.date(),
        "market_open_time": open_t,
        "market_close_time": close_t,
        "strike_F": 60.0,
        "observed_high_F": 60.0,
        "outcome": outcome,
        "mid_price_at_T": mid,
        "n_trades_in_window": 10,
        "volume_in_window": 1000.0,
    }


def _synthetic_biased_dataset(*, n_days: int, seed: int) -> pd.DataFrame:
    """Outcomes follow a hidden true_p; the displayed mid is true_p + 0.10."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for day in range(n_days):
        occurrence = START + pd.Timedelta(days=day)
        for city in CITIES:
            for k in range(4):
                ticker = (
                    f"KXHIGH{city}-"
                    f"{occurrence.date().strftime('%y%b%d').upper()}-T{50 + k}"
                )
                true_p = float(rng.uniform(0.05, 0.85))
                mid = float(np.clip(true_p + 0.10, 0.01, 0.99))
                outcome = int(rng.binomial(1, true_p))
                rows.append(
                    _row(
                        ticker=ticker,
                        city=city,
                        occurrence=occurrence,
                        mid=mid,
                        outcome=outcome,
                    )
                )
    return pd.DataFrame(rows)


def test_evaluate_produces_expected_shape() -> None:
    df = _synthetic_biased_dataset(n_days=540, seed=1)
    result = evaluate(df)

    # The criteria dict has the locked-in keys regardless of pass/fail.
    assert set(result.criteria) == {
        "C1_median_ECE_ratio_>=_5x",
        "C2_median_shoulder_gross_edge_>=_2pp",
        "C3_at_least_4_splits_with_>=_3x",
        "C4_LOCO_positive_in_>=_3_of_5",
        "C5_shoulder_net_edge_positive",
    }
    # passes attribute is a bool derived from the criteria.
    assert result.passes == all(result.criteria.values())
    # Walk-forward and LOCO ran something.
    assert len(result.walk_forward) >= 4
    assert len(result.loco) >= 3
