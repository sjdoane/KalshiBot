"""Time-based train/test splits with purge buffers for calibration backtesting.

The pre-critic Zerve study fit isotonic regression on the same data it scored;
that does not test edge, only fit. Our Phase 1.5 gate requires honest
out-of-sample evaluation. Two complementary split families are implemented:

1. Walk-forward windows on a fixed series (e.g., KXHIGHNY). Multiple disjoint
   train/test windows in chronological order, with a purge buffer that drops
   any market whose lifespan crossed the train/test boundary.

2. Leave-one-city-out across {NY, CHI, MIA, LAX, DEN}. Trains on four cities,
   evaluates on the fifth. Forces the calibration to generalize across
   climates and away from any city-specific market microstructure.

The dataframe contract: rows are individual settled markets, with at least
the columns
  - market_open_time    (UTC pd.Timestamp)
  - market_close_time   (UTC pd.Timestamp)  # resolution timestamp
  - city                (str, one of the KXHIGH cities)

The purge logic uses the OPEN time relative to test_start (so we drop train
markets whose lifespan reached into the test window) and the CLOSE time
relative to train_end (so we drop test markets that started before train ended).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    """One train/test partition defined by absolute timestamp boundaries."""

    label: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def __post_init__(self) -> None:
        # Each window must be strictly ordered, and test must follow train.
        if self.train_end <= self.train_start:
            raise ValueError(f"{self.label}: train_end must be after train_start")
        if self.test_end <= self.test_start:
            raise ValueError(f"{self.label}: test_end must be after test_start")
        if self.test_start < self.train_end:
            raise ValueError(
                f"{self.label}: test_start ({self.test_start}) must be on or "
                f"after train_end ({self.train_end}); use the gap for purging"
            )


def make_walk_forward_splits(
    *,
    first_train_start: pd.Timestamp,
    last_test_end: pd.Timestamp,
    train_window: pd.Timedelta,
    test_window: pd.Timedelta,
    purge: pd.Timedelta,
    step: pd.Timedelta | None = None,
) -> list[TimeSplit]:
    """Generate disjoint walk-forward splits.

    Each split: `train_window` of training, then `purge` gap, then `test_window`
    of testing. Splits step forward by `step` (defaults to `test_window`, so
    test windows tile the calendar without overlap). Stops when the next test
    window would exceed `last_test_end`.

    Concretely, with train_window=180d, test_window=30d, purge=2d, step=30d,
    starting 2024-01-01 and ending 2026-05-01, you get ~24 splits, each
    180d-train + 2d-gap + 30d-test, no test windows overlapping. Each split
    is independently re-fit on its own training data, then scored on its
    own test window.
    """

    if step is None:
        step = test_window

    splits: list[TimeSplit] = []
    train_start = first_train_start
    n = 0
    while True:
        train_end = train_start + train_window
        test_start = train_end + purge
        test_end = test_start + test_window
        if test_end > last_test_end:
            break
        n += 1
        splits.append(
            TimeSplit(
                label=f"wf_{n:02d}_{train_start.date()}_to_{test_end.date()}",
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        train_start = train_start + step
    return splits


def apply_split(
    df: pd.DataFrame,
    split: TimeSplit,
    *,
    open_col: str = "market_open_time",
    close_col: str = "market_close_time",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (train, test) DataFrames for one split.

    Purge rule: a market belongs to train iff its close_time is strictly
    before train_end (so it fully resolved within the train window); to test
    iff its open_time is at or after test_start AND its close_time is at or
    before test_end (so it's fully inside the test window). Markets that
    straddle the purge gap are dropped from both.

    This is stricter than the popular naive split (assign by close_time only)
    because Kalshi market prices in the late hours of a market can leak from
    information arriving after train_end. Requiring full containment removes
    that leakage path.
    """
    train_mask = df[close_col] < split.train_end
    test_mask = (df[open_col] >= split.test_start) & (df[close_col] <= split.test_end)
    train = df[train_mask].copy()
    test = df[test_mask].copy()
    return train, test


def leave_one_city_out(
    df: pd.DataFrame,
    test_city: str,
    *,
    city_col: str = "city",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on all cities except `test_city`; test on `test_city`."""
    if test_city not in df[city_col].unique():
        raise ValueError(
            f"Test city {test_city!r} not in dataframe. Available: "
            f"{sorted(df[city_col].unique())}"
        )
    test = df[df[city_col] == test_city].copy()
    train = df[df[city_col] != test_city].copy()
    return train, test
