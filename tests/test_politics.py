"""Tests for the politics-market tagger and binary-detection helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from kalshi_bot.data.politics import (
    FEDERAL_ELECTION_KEYWORDS,
    count_contracts_per_event,
    is_binary_market,
    is_federal_election_market,
    is_federal_election_text,
    tag_federal_election,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Direct keyword matches
        ("Will the Senate confirm the nominee?", True),
        ("2026 House races", True),
        ("Will Trump win Iowa?", True),
        ("Presidential primary in NH", True),
        ("Will the Republican candidate win?", True),
        ("FOMC announces 25bps cut", False),
        ("Bitcoin closes above $150k", False),
        ("Lakers vs Celtics", False),
        # Substring matching: "election" inside the sentence matches.
        ("Wins despite federal election forecast", True),
        # Substring behavior: jammed-together keywords inside tickers match.
        ("KXSENATEOH2026-NOV04-DEM", True),
        ("KXMIDTERMS2026", True),
        # Substring may produce false positives on benign text - these are
        # intentional (audit step in methodology corrects). "Trumpet"
        # contains "trump"; the keyword set was tuned to avoid the
        # most-common ones ("vote", "gop") that hit overly benign text.
        ("She played the trumpet beautifully", True),
        # Negative: text without any keywords
        ("Year-end recap, no politics here", False),
        # Mixed-case
        ("SENATE confirms", True),
        ("midterms approaching", True),
        # Punctuation embedded
        ("Election: 2026!", True),
    ],
)
def test_is_federal_election_text(text: str, expected: bool) -> None:
    assert is_federal_election_text(text) is expected


def test_is_federal_election_text_none_and_empty() -> None:
    assert is_federal_election_text(None) is False
    assert is_federal_election_text("") is False


def test_is_federal_election_market_disjunction() -> None:
    """A market is tagged if ANY text field matches."""
    # title hits
    assert is_federal_election_market(
        {"ticker": "KXFOO-25JAN", "title": "Will the Senate confirm X?"}
    ) is True
    # ticker hits
    assert is_federal_election_market(
        {"ticker": "KXSENATEOH2026-NOV04-DEM", "title": "irrelevant"}
    ) is True
    # subtitle hits
    assert is_federal_election_market(
        {"ticker": "KXFOO", "title": "x", "subtitle": "2026 midterms"}
    ) is True
    # category hits
    assert is_federal_election_market(
        {"ticker": "KXFOO", "title": "x", "category": "Politics: Senate"}
    ) is True
    # No match anywhere
    assert is_federal_election_market(
        {"ticker": "KXBTC25", "title": "Bitcoin > $150k", "category": "Crypto"}
    ) is False


def test_is_federal_election_market_missing_fields() -> None:
    """Missing fields are treated as empty strings (no match)."""
    assert is_federal_election_market({}) is False
    assert is_federal_election_market({"ticker": "KXFOO"}) is False


def test_is_federal_election_market_non_string_values() -> None:
    """Non-string field values do not raise; treated as no match."""
    row: dict[str, object] = {
        "ticker": "KXFOO",
        "title": None,
        "subtitle": 12345,
        "category": ["Politics", "Senate"],  # list, not string
    }
    # All non-string => no match.
    assert is_federal_election_market(row) is False


def test_tag_federal_election_vectorized() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXSENATEOH2026-NOV-DEM", "title": "Will Brown win Ohio Senate?"},
            {"ticker": "KXBTC25-MAR-150K", "title": "Bitcoin closes above $150k"},
            {"ticker": "KXNFL25-LAKERS", "title": "Lakers win Sunday"},
            {"ticker": "KXFOO", "title": "2026 midterm turnout > 50pct"},
        ]
    )
    tagged = tag_federal_election(df)
    assert tagged.tolist() == [True, False, False, True]
    assert tagged.name == "is_federal_election_market"


def test_tag_federal_election_handles_missing_columns() -> None:
    df = pd.DataFrame([{"ticker": "KXFOO"}, {"ticker": "KXSENATE2026"}])
    tagged = tag_federal_election(df)
    assert tagged.tolist() == [False, True]


def test_tag_federal_election_empty_dataframe_no_text_columns() -> None:
    df = pd.DataFrame({"only_numeric": [1, 2, 3]})
    tagged = tag_federal_election(df)
    assert tagged.tolist() == [False, False, False]


def test_count_contracts_per_event() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXEVT1-T55", "event_ticker": "KXEVT1"},
            {"ticker": "KXEVT1-T60", "event_ticker": "KXEVT1"},  # 5-strike event
            {"ticker": "KXEVT1-T65", "event_ticker": "KXEVT1"},
            {"ticker": "KXEVT1-T70", "event_ticker": "KXEVT1"},
            {"ticker": "KXEVT1-T75", "event_ticker": "KXEVT1"},
            {"ticker": "KXEVT2-YES", "event_ticker": "KXEVT2"},  # binary event
        ]
    )
    counts = count_contracts_per_event(df)
    assert counts["KXEVT1"] == 5
    assert counts["KXEVT2"] == 1


def test_count_contracts_per_event_requires_column() -> None:
    df = pd.DataFrame({"foo": [1, 2]})
    with pytest.raises(ValueError, match="event_ticker"):
        count_contracts_per_event(df)


def test_is_binary_market_flags_single_contract_events() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXEVT1-T55", "event_ticker": "KXEVT1"},
            {"ticker": "KXEVT1-T60", "event_ticker": "KXEVT1"},  # multi-strike
            {"ticker": "KXEVT2-YES", "event_ticker": "KXEVT2"},  # binary
            {"ticker": "KXEVT3-YES", "event_ticker": "KXEVT3"},  # binary
        ]
    )
    binary = is_binary_market(df)
    assert binary.tolist() == [False, False, True, True]
    assert binary.name == "is_binary_market"


def test_is_binary_market_requires_event_ticker() -> None:
    df = pd.DataFrame({"foo": [1, 2]})
    with pytest.raises(ValueError, match="event_ticker"):
        is_binary_market(df)


def test_federal_election_keywords_are_lowercase() -> None:
    """All FEDERAL_ELECTION_KEYWORDS entries are lowercase (regex uses
    re.IGNORECASE, but lowercase entries keep the constant readable)."""
    for k in FEDERAL_ELECTION_KEYWORDS:
        assert k == k.lower(), f"Keyword {k!r} is not lowercase"
