"""Tests for the Polymarket cross-validation module (offline only)."""

from __future__ import annotations

from kalshi_bot.data.polymarket import (
    POLYMARKET_BASE,
    PolymarketMarket,
    match_kalshi_to_polymarket,
)


def _pm(question: str) -> PolymarketMarket:
    return PolymarketMarket(
        id="x", slug="x", question=question, end_date_iso="2025-01-01",
        closed=True, resolved_outcome="Yes", last_trade_price=0.5,
        volume_total_usd=1000.0,
    )


def test_base_url_constant() -> None:
    assert POLYMARKET_BASE == "https://gamma-api.polymarket.com"


def test_match_finds_overlap() -> None:
    pm_markets = [
        _pm("Will the Lakers win the NBA championship 2026"),
        _pm("Will Bitcoin close above 150k by end of 2025"),
        _pm("Will the Senate confirm the new judge"),
    ]
    match = match_kalshi_to_polymarket(
        "Will the Lakers win the NBA Finals in 2026?",
        pm_markets, min_word_overlap=3,
    )
    assert match is not None
    assert "Lakers" in match.question


def test_match_returns_none_when_no_overlap() -> None:
    pm_markets = [_pm("Will it rain in Seattle tomorrow")]
    match = match_kalshi_to_polymarket(
        "Will the Knicks win their next game",
        pm_markets, min_word_overlap=3,
    )
    assert match is None


def test_match_returns_none_on_empty_kalshi_question() -> None:
    pm_markets = [_pm("anything")]
    assert match_kalshi_to_polymarket("", pm_markets) is None


def test_match_picks_best_overlap() -> None:
    pm_markets = [
        _pm("Will the Lakers win"),  # 2 word overlap
        _pm("Will the Lakers win the NBA championship 2026"),  # 5 word overlap
    ]
    match = match_kalshi_to_polymarket(
        "Will the Lakers win the NBA championship in 2026",
        pm_markets, min_word_overlap=3,
    )
    assert match is not None
    assert "championship" in match.question
