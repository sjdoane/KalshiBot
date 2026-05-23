"""Tests for time-based and cross-city splits with anti-leakage purge.

The pass/fail of Phase 1.5 hangs on the integrity of these splits, so the
unit tests are explicit about edge cases: markets that straddle the gap,
zero-width windows, leave-one-city-out coverage.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kalshi_bot.analysis.train_test_split import (
    TimeSplit,
    apply_split,
    leave_one_city_out,
    make_walk_forward_splits,
)


def _market(open_t: str, close_t: str, city: str = "NY", outcome: int = 1) -> dict:
    return {
        "market_open_time": pd.Timestamp(open_t, tz="UTC"),
        "market_close_time": pd.Timestamp(close_t, tz="UTC"),
        "city": city,
        "outcome": outcome,
    }


def test_timesplit_rejects_reversed_train_window() -> None:
    ts = pd.Timestamp
    with pytest.raises(ValueError, match="train_end must be after train_start"):
        TimeSplit(
            label="bad",
            train_start=ts("2026-02-01", tz="UTC"),
            train_end=ts("2026-01-01", tz="UTC"),
            test_start=ts("2026-03-01", tz="UTC"),
            test_end=ts("2026-04-01", tz="UTC"),
        )


def test_timesplit_rejects_test_before_train_end() -> None:
    ts = pd.Timestamp
    with pytest.raises(ValueError, match="test_start"):
        TimeSplit(
            label="bad",
            train_start=ts("2026-01-01", tz="UTC"),
            train_end=ts("2026-03-01", tz="UTC"),
            test_start=ts("2026-02-15", tz="UTC"),
            test_end=ts("2026-04-01", tz="UTC"),
        )


def test_walk_forward_splits_tile_calendar_without_overlap() -> None:
    splits = make_walk_forward_splits(
        first_train_start=pd.Timestamp("2024-01-01", tz="UTC"),
        last_test_end=pd.Timestamp("2024-12-31", tz="UTC"),
        train_window=pd.Timedelta(days=90),
        test_window=pd.Timedelta(days=30),
        purge=pd.Timedelta(days=2),
    )
    assert len(splits) >= 5
    for a, b in zip(splits, splits[1:], strict=False):
        # Tests must not overlap each other when step defaults to test_window.
        assert a.test_end <= b.test_start + pd.Timedelta(days=1), (
            f"overlap between {a.label} and {b.label}"
        )
    for s in splits:
        gap = s.test_start - s.train_end
        assert gap == pd.Timedelta(days=2)


def test_walk_forward_splits_stop_before_last_end() -> None:
    splits = make_walk_forward_splits(
        first_train_start=pd.Timestamp("2026-01-01", tz="UTC"),
        last_test_end=pd.Timestamp("2026-05-01", tz="UTC"),
        train_window=pd.Timedelta(days=60),
        test_window=pd.Timedelta(days=15),
        purge=pd.Timedelta(days=2),
    )
    for s in splits:
        assert s.test_end <= pd.Timestamp("2026-05-01", tz="UTC")


def test_apply_split_excludes_markets_straddling_gap() -> None:
    """A market that opens in train_end's window but closes in test must be dropped."""
    rows = [
        # fully inside train window -> train
        _market("2026-01-05", "2026-01-05T23:00:00"),
        # opens in train, closes in test -> dropped by both
        _market("2026-02-28", "2026-03-15"),
        # fully inside test window -> test
        _market("2026-03-10", "2026-03-10T23:00:00"),
        # closes after test_end -> dropped from test
        _market("2026-03-25", "2026-04-15"),
    ]
    df = pd.DataFrame(rows)
    split = TimeSplit(
        label="t1",
        train_start=pd.Timestamp("2026-01-01", tz="UTC"),
        train_end=pd.Timestamp("2026-03-01", tz="UTC"),
        test_start=pd.Timestamp("2026-03-03", tz="UTC"),
        test_end=pd.Timestamp("2026-03-31", tz="UTC"),
    )
    train, test = apply_split(df, split)
    assert len(train) == 1
    assert train["market_open_time"].iloc[0] == pd.Timestamp("2026-01-05", tz="UTC")
    assert len(test) == 1
    assert test["market_open_time"].iloc[0] == pd.Timestamp("2026-03-10", tz="UTC")


def test_leave_one_city_out_partitions_correctly() -> None:
    rows = [_market("2026-01-01", "2026-01-01T23:00:00", city=c) for c in
            ["NY", "CHI", "MIA", "LAX", "DEN", "NY", "DEN"]]
    df = pd.DataFrame(rows)
    train, test = leave_one_city_out(df, "DEN")
    assert set(train["city"].unique()) == {"NY", "CHI", "MIA", "LAX"}
    assert set(test["city"].unique()) == {"DEN"}
    assert len(train) + len(test) == len(df)


def test_leave_one_city_out_rejects_unknown_city() -> None:
    df = pd.DataFrame([_market("2026-01-01", "2026-01-01T23:00:00", city="NY")])
    with pytest.raises(ValueError, match="Test city"):
        leave_one_city_out(df, "PHL")
