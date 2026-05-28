"""Unit tests for v4 filter module."""
from __future__ import annotations

from kalshi_bot_v4.filter import (
    FADE_THRESHOLD_CENTS_DEFAULT,
    MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
    FilterDecision,
    evaluate_market,
    is_ladder_series,
    parse_ladder_ticker,
    series_prefix_of,
)


def test_series_prefix_of():
    assert series_prefix_of("KXNFLWINS-IND-25B-T8") == "KXNFLWINS"
    assert series_prefix_of("KXMLBPLAYOFFS-25-NYY") == "KXMLBPLAYOFFS"


def test_parse_ladder_ticker_valid():
    out = parse_ladder_ticker("KXNFLWINS-IND-25B-T8")
    assert out == ("KXNFLWINS-IND-25B", 8)
    out = parse_ladder_ticker("KXNBAWINS-CHA-25-T35")
    assert out == ("KXNBAWINS-CHA-25", 35)


def test_parse_ladder_ticker_invalid():
    # Not a ladder series ticker
    assert parse_ladder_ticker("KXMLBPLAYOFFS-25-NYY") is None
    assert parse_ladder_ticker("KXWCGAME-26JUN23ENGGHA-ENG") is None


def test_is_ladder_series():
    assert is_ladder_series("KXNFLWINS")
    assert is_ladder_series("KXNBAWINS")
    assert is_ladder_series("KXMLBWINS")
    assert not is_ladder_series("KXMLBPLAYOFFS")
    assert not is_ladder_series("KXWCGAME")


def test_no_filter_inputs_passes():
    """When neither Polymarket nor cross-market data is provided, the
    filter abstains; should_trade=True."""
    d = evaluate_market(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
    )
    assert d.should_trade is True
    assert d.reason == "no_match"
    assert d.poly_mid is None
    assert d.cross_market_implied is None


def test_polymarket_fade_fires():
    """Kalshi at 0.92 vs Polymarket at 0.73 -> divergence 19c > 7c threshold,
    filter fires and skips."""
    d = evaluate_market(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},
    )
    assert d.should_trade is False
    assert d.reason == "polymarket_fade"
    assert d.poly_mid == 0.73
    assert d.confidence > 0.0


def test_polymarket_no_fade_when_close():
    """Kalshi 0.74 vs Polymarket 0.72 -> only 2c divergence, below 7c."""
    d = evaluate_market(
        ticker="KXMLBPLAYOFFS-25-TOR",
        kalshi_price=0.74,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-TOR": 0.72},
    )
    assert d.should_trade is True
    assert d.reason == "pass"
    assert d.poly_mid == 0.72


def test_polymarket_no_match_passes():
    """If the poly_lookup returns None for this ticker, A1 abstains."""
    d = evaluate_market(
        ticker="KXBOXING-26SEP12-CAL",
        kalshi_price=0.80,
        series_ticker="KXBOXING-26SEP",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},  # different ticker
    )
    assert d.should_trade is True
    assert d.reason == "no_poly_match"


def test_polymarket_callable_lookup():
    """poly_lookup may be a callable."""
    def lookup(t):
        return 0.50 if "NYY" in t else None
    d = evaluate_market(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup=lookup,
    )
    assert d.should_trade is False
    assert d.reason == "polymarket_fade"
    assert d.poly_mid == 0.50


def test_monotonicity_violation_fires():
    """KXNFLWINS-IND-25B-T8 at 0.77 with T7 at 0.37 in siblings.
    Gap 40c >> 5c threshold; filter fires."""
    cross_market = {
        "KXNFLWINS-IND-25B": {
            3: 0.96, 4: 0.86, 5: 0.86, 6: 0.82, 7: 0.37,
            8: 0.77, 9: 0.73, 10: 0.84,
        },
    }
    d = evaluate_market(
        ticker="KXNFLWINS-IND-25B-T8",
        kalshi_price=0.77,
        series_ticker="KXNFLWINS-IND",
        cross_market_data=cross_market,
    )
    assert d.should_trade is False
    assert d.reason == "monotonicity_violation"
    assert d.cross_market_implied is not None
    assert d.confidence > 0.0


def test_monotonicity_consistent_passes():
    """All siblings monotone in threshold direction; filter does not fire."""
    cross_market = {
        "KXNBAWINS-CHA-25": {
            30: 0.98, 35: 0.96, 40: 0.85, 45: 0.50, 50: 0.20,
        },
    }
    d = evaluate_market(
        ticker="KXNBAWINS-CHA-25-T40",
        kalshi_price=0.85,
        series_ticker="KXNBAWINS-CHA",
        cross_market_data=cross_market,
    )
    assert d.should_trade is True
    assert d.cross_market_implied is not None
    assert d.confidence == 0.0


def test_monotonicity_lower_than_higher_does_not_fire():
    """If candidate is UNDER-priced relative to higher-threshold siblings,
    we do NOT fire. Defensive overlay only skips over-priced markets,
    never adds buys v1 wouldn't make."""
    cross_market = {
        "KXNFLWINS-XX-25B": {
            5: 0.60, 6: 0.55, 7: 0.40, 8: 0.50,  # T7 looks under-priced vs T8
        },
    }
    d = evaluate_market(
        ticker="KXNFLWINS-XX-25B-T7",
        kalshi_price=0.40,
        series_ticker="KXNFLWINS-XX",
        cross_market_data=cross_market,
    )
    # T7 at 0.40 with T8 at 0.50: violation in opposite direction.
    # candidate is under-priced, defensive filter does NOT skip.
    assert d.should_trade is True


def test_non_ladder_series_a2_inactive():
    """A2 should never fire on non-ladder series like KXMLBPLAYOFFS."""
    cross_market = {
        "KXMLBPLAYOFFS-25": {1: 0.40, 2: 0.95},  # noise
    }
    d = evaluate_market(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.95,
        series_ticker="KXMLBPLAYOFFS-25",
        cross_market_data=cross_market,
    )
    # A2 should not even attempt
    assert d.should_trade is True
    assert d.cross_market_implied is None


def test_both_filters_fire():
    """Polymarket fade AND monotonicity violation -> reason='both'."""
    cross_market = {
        "KXNFLWINS-XX-25B": {7: 0.30, 8: 0.80},
    }
    d = evaluate_market(
        ticker="KXNFLWINS-XX-25B-T8",
        kalshi_price=0.80,
        series_ticker="KXNFLWINS-XX",
        poly_lookup={"KXNFLWINS-XX-25B-T8": 0.40},
        cross_market_data=cross_market,
    )
    assert d.should_trade is False
    assert d.reason == "both"
    assert d.poly_mid == 0.40


def test_thresholds_are_locked():
    """Pre-registered defaults must be exactly 7c and 5c."""
    assert FADE_THRESHOLD_CENTS_DEFAULT == 7.0
    assert MONOTONICITY_THRESHOLD_CENTS_DEFAULT == 5.0


def test_filter_decision_is_namedtuple():
    """Contract test: FilterDecision exposes expected fields."""
    d = FilterDecision(
        should_trade=True,
        reason="pass",
        poly_mid=0.5,
        kalshi_price=0.6,
        cross_market_implied=None,
        confidence=0.0,
    )
    assert d.should_trade is True
    assert d.kalshi_price == 0.6
