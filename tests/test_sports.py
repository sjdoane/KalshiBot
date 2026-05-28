"""Tests for the sports league-tagger and binary-detection helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from kalshi_bot.data.sports import (
    LEAGUE_KEYWORDS,
    classify_league,
    classify_market_league,
    count_contracts_per_event,
    is_binary_market,
    tag_league,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Will the Lakers win the NBA championship?", "NBA"),
        ("KXNBA-25-LAKERS", "NBA"),
        ("Will the Chiefs win the Super Bowl?", "NFL"),
        ("KXNFL-25-CHIEFS", "NFL"),
        ("Will the Yankees win the World Series?", "MLB"),
        ("KXMLB-25-YANKEES", "MLB"),
        ("Will the Bruins win the Stanley Cup?", "NHL"),
        ("Who will win March Madness 2026?", "NCAA-BB"),
        ("CFP semifinal: Will Ohio State win?", "NCAA-FB"),
        ("UFC 300 main event winner", "UFC"),
        ("Tiger Woods to win the Masters", "PGA"),
        ("Formula 1 race in Monaco", "F1"),
        ("Will Trump win Iowa?", None),  # political, no sports
        ("Bitcoin to close above $150k", None),
        ("FOMC rate decision", None),
        ("", None),
    ],
)
def test_classify_league(text: str, expected: str | None) -> None:
    assert classify_league(text) == expected


def test_classify_league_none_input() -> None:
    assert classify_league(None) is None


def test_classify_market_league_disjunction() -> None:
    """A market is tagged by ANY text field matching a league pattern."""
    assert classify_market_league(
        {"ticker": "KXFOO", "title": "Will the Bruins win Stanley Cup?"}
    ) == "NHL"
    assert classify_market_league(
        {"ticker": "KXNBALAKERS", "title": "irrelevant"}
    ) == "NBA"
    assert classify_market_league(
        {"ticker": "KXFOO", "title": "x", "category": "Sports: NFL"}
    ) == "NFL"
    # No match anywhere -> OTHER
    assert classify_market_league(
        {"ticker": "KXBTC25", "title": "Bitcoin above $150k"}
    ) == "OTHER"


def test_classify_market_league_missing_fields() -> None:
    assert classify_market_league({}) == "OTHER"
    assert classify_market_league({"ticker": "KXFOO"}) == "OTHER"


def test_tag_league_vectorized() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXNBALAKERS-25-CHAMP", "title": "Lakers win NBA championship"},
            {"ticker": "KXSENATE", "title": "Senate confirms judge"},
            {"ticker": "KXNFL-26", "title": "Super Bowl winner 2026"},
            {"ticker": "KXFOO", "title": "Foo bar baz"},
        ]
    )
    tagged = tag_league(df)
    assert tagged.tolist() == ["NBA", "OTHER", "NFL", "OTHER"]
    assert tagged.name == "league"


def test_tag_league_handles_missing_columns() -> None:
    df = pd.DataFrame([{"ticker": "KXNBA-LAKERS"}, {"ticker": "KXFOO"}])
    tagged = tag_league(df)
    assert tagged.tolist() == ["NBA", "OTHER"]


def test_tag_league_no_text_columns() -> None:
    df = pd.DataFrame({"only_numeric": [1, 2, 3]})
    tagged = tag_league(df)
    assert tagged.tolist() == ["OTHER", "OTHER", "OTHER"]


def test_league_keywords_priority_ordering() -> None:
    """More specific keywords should appear BEFORE less specific ones so
    classify_league returns the most accurate label first."""
    keywords = [k for k, _ in LEAGUE_KEYWORDS]
    # ncaaf should come before ncaa (more specific first)
    assert keywords.index("ncaaf") < keywords.index("ncaa")
    # super bowl should come before generic
    assert "super bowl" in keywords
    # F1 specific before generic
    assert keywords.index("kxf1") < keywords.index("formula 1")


def test_count_contracts_per_event() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXNBACHAMP-25-LAL", "event_ticker": "KXNBACHAMP-25"},
            {"ticker": "KXNBACHAMP-25-BOS", "event_ticker": "KXNBACHAMP-25"},
            {"ticker": "KXNFLCHAMP-25-KC", "event_ticker": "KXNFLCHAMP-25"},
            {"ticker": "KXNFLCHAMP-25-PHI", "event_ticker": "KXNFLCHAMP-25"},
            {"ticker": "KXSINGLE-Y", "event_ticker": "KXSINGLE"},
        ]
    )
    counts = count_contracts_per_event(df)
    assert counts["KXNBACHAMP-25"] == 2
    assert counts["KXNFLCHAMP-25"] == 2
    assert counts["KXSINGLE"] == 1


def test_is_binary_market_flags_single_contract_events() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "KXNBA-LAL", "event_ticker": "KXNBA-CHAMP"},  # multi
            {"ticker": "KXNBA-BOS", "event_ticker": "KXNBA-CHAMP"},  # multi
            {"ticker": "KXBINARY-YES", "event_ticker": "KXBINARY"},  # binary
        ]
    )
    binary = is_binary_market(df)
    assert binary.tolist() == [False, False, True]
