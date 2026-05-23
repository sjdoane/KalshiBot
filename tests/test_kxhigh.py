"""Tests for KXHIGH event ticker and series parsing."""

from __future__ import annotations

from datetime import date

import pytest

from kalshi_bot.data.kxhigh import (
    SERIES_TO_CITY,
    city_from_series,
    parse_event_ticker,
    parse_occurrence_date,
)


@pytest.mark.parametrize(
    ("event_ticker", "expected_series", "expected_date"),
    [
        ("KXHIGHNY-26APR28", "KXHIGHNY", date(2026, 4, 28)),
        ("KXHIGHCHI-21AUG07", "KXHIGHCHI", date(2021, 8, 7)),
        ("KXHIGHMIA-24DEC31", "KXHIGHMIA", date(2024, 12, 31)),
        ("KXHIGHLAX-25JAN01", "KXHIGHLAX", date(2025, 1, 1)),
        ("KXHIGHDEN-26FEB29", "KXHIGHDEN", None),  # invalid date; 2026 not leap
        # Legacy prefix from before the late-2024 rename:
        ("HIGHNY-23JUL15", "KXHIGHNY", date(2023, 7, 15)),
        ("HIGHCHI-22DEC03", "KXHIGHCHI", date(2022, 12, 3)),
        ("HIGHMIA-24OCT23", "KXHIGHMIA", date(2024, 10, 23)),
    ],
)
def test_parse_event_ticker(
    event_ticker: str,
    expected_series: str,
    expected_date: date | None,
) -> None:
    parsed = parse_event_ticker(event_ticker)
    if expected_date is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed == (expected_series, expected_date)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "KXHIGHNY-26APR",         # truncated date
        "KXHIGHNY-26APR28-T66",   # full market ticker, not event
        "KXSNOWNYC-26JAN01",       # not a KXHIGH series
        "KXHIGHNY-26ZZZ28",        # bad month
    ],
)
def test_parse_event_ticker_rejects_bad_input(bad: str | None) -> None:
    assert parse_event_ticker(bad) is None
    assert parse_occurrence_date(bad) is None


def test_parse_occurrence_date_convenience_wrapper() -> None:
    assert parse_occurrence_date("KXHIGHNY-26APR28") == date(2026, 4, 28)


def test_city_from_series() -> None:
    assert city_from_series("KXHIGHNY") == "NY"
    assert city_from_series("KXHIGHCHI") == "CHI"
    assert city_from_series("KXHIGHUNKNOWN") is None


def test_series_to_city_covers_all_kxhigh() -> None:
    assert set(SERIES_TO_CITY) == {
        "KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHLAX", "KXHIGHDEN",
    }
