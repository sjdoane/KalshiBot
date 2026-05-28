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
    apply_split_phase2,
    leave_one_city_out,
    leave_one_event_window_out,
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


# Phase 2 split tests

def _phase2_market(open_t: str, close_t: str, outcome: int = 1) -> dict:
    """Politics-style market: long-horizon lifetime is normal."""
    return {
        "market_open_time": pd.Timestamp(open_t, tz="UTC"),
        "market_close_time": pd.Timestamp(close_t, tz="UTC"),
        "outcome": outcome,
    }


def test_apply_split_phase2_train_set_is_close_before_train_end() -> None:
    """Train: any market that closes before train_end, regardless of open time."""
    rows = [
        # opens long before train_start, closes within train -> train
        _phase2_market("2024-01-01", "2025-05-15"),
        # entirely within train -> train
        _phase2_market("2025-05-01", "2025-05-20"),
        # closes after train_end -> NOT train
        _phase2_market("2025-04-01", "2025-06-15"),
    ]
    df = pd.DataFrame(rows)
    split = TimeSplit(
        label="t1",
        train_start=pd.Timestamp("2024-12-01", tz="UTC"),
        train_end=pd.Timestamp("2025-06-01", tz="UTC"),
        test_start=pd.Timestamp("2025-06-15", tz="UTC"),  # 14d purge
        test_end=pd.Timestamp("2025-07-15", tz="UTC"),
    )
    train, _test = apply_split_phase2(df, split)
    assert len(train) == 2


def test_apply_split_phase2_test_requires_open_after_train_plus_purge() -> None:
    """Test markets must have open_time > train_end + purge_days."""
    rows = [
        # closes in test window, but opened during train -> NOT test (straddle)
        _phase2_market("2025-04-01", "2025-06-30"),
        # closes in test window, opened during purge buffer -> NOT test
        _phase2_market("2025-06-10", "2025-06-30"),
        # closes in test window, opened after purge ends -> TEST
        _phase2_market("2025-06-20", "2025-06-30"),
        # closes after test_end -> NOT test
        _phase2_market("2025-06-25", "2025-08-01"),
    ]
    df = pd.DataFrame(rows)
    split = TimeSplit(
        label="t1",
        train_start=pd.Timestamp("2024-12-01", tz="UTC"),
        train_end=pd.Timestamp("2025-06-01", tz="UTC"),
        test_start=pd.Timestamp("2025-06-15", tz="UTC"),
        test_end=pd.Timestamp("2025-07-15", tz="UTC"),
    )
    _train, test = apply_split_phase2(df, split, lifetime_straddle_purge_days=14)
    assert len(test) == 1
    assert test["market_open_time"].iloc[0] == pd.Timestamp("2025-06-20", tz="UTC")


def test_apply_split_phase2_long_horizon_markets_eligible_for_later_splits() -> None:
    """A 60-day-lifetime market that opens just after a split's purge IS in
    that split's test, even though its lifetime is long."""
    rows = [
        # Opens day 16 (after train_end + 14d), closes day 75 (within test)
        _phase2_market("2025-06-17", "2025-07-15"),
    ]
    df = pd.DataFrame(rows)
    split = TimeSplit(
        label="t1",
        train_start=pd.Timestamp("2024-12-01", tz="UTC"),
        train_end=pd.Timestamp("2025-06-01", tz="UTC"),
        test_start=pd.Timestamp("2025-06-15", tz="UTC"),
        test_end=pd.Timestamp("2025-07-31", tz="UTC"),
    )
    _train, test = apply_split_phase2(df, split, lifetime_straddle_purge_days=14)
    assert len(test) == 1


def test_apply_split_phase2_custom_purge_days() -> None:
    """The purge_days parameter is configurable."""
    rows = [
        _phase2_market("2025-06-10", "2025-06-30"),  # within 14d purge, outside 7d purge
    ]
    df = pd.DataFrame(rows)
    split = TimeSplit(
        label="t1",
        train_start=pd.Timestamp("2024-12-01", tz="UTC"),
        train_end=pd.Timestamp("2025-06-01", tz="UTC"),
        test_start=pd.Timestamp("2025-06-15", tz="UTC"),
        test_end=pd.Timestamp("2025-07-15", tz="UTC"),
    )
    _train, test_14d = apply_split_phase2(df, split, lifetime_straddle_purge_days=14)
    assert len(test_14d) == 0  # purge eats the market
    _train, test_7d = apply_split_phase2(df, split, lifetime_straddle_purge_days=7)
    assert len(test_7d) == 1  # 7d purge admits the market


def test_leave_one_event_window_out_basic() -> None:
    rows = [
        # In-window: held out as test
        _phase2_market("2024-09-01", "2024-11-05"),  # closes during election week
        _phase2_market("2024-10-15", "2024-11-15"),
        # Outside-window: train
        _phase2_market("2025-01-01", "2025-02-15"),
        _phase2_market("2024-06-01", "2024-09-30"),  # closes BEFORE window
    ]
    df = pd.DataFrame(rows)
    train, test = leave_one_event_window_out(
        df,
        window_start=pd.Timestamp("2024-10-01", tz="UTC"),
        window_end=pd.Timestamp("2024-12-31", tz="UTC"),
    )
    assert len(test) == 2
    assert len(train) == 2


def test_leave_one_event_window_out_rejects_reversed_window() -> None:
    df = pd.DataFrame([_phase2_market("2024-01-01", "2024-12-31")])
    with pytest.raises(ValueError, match="must be after"):
        leave_one_event_window_out(
            df,
            window_start=pd.Timestamp("2024-12-01", tz="UTC"),
            window_end=pd.Timestamp("2024-06-01", tz="UTC"),
        )
