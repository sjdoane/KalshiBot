"""Unit tests for v5 combined filter module.

Mirrors `tests/v4/test_filter.py` structure with additional tests for
the sportsbook-fade rule (A3) and the OR-logic combination across all
three rules.
"""
from __future__ import annotations

from kalshi_bot_v5.filter_combined import (
    FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
    FADE_THRESHOLD_CENTS_POLY_DEFAULT,
    MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
    CombinedFilterDecision,
    evaluate_market_combined,
    is_ladder_series,
    parse_ladder_ticker,
    series_prefix_of,
)


def test_series_prefix_of():
    assert series_prefix_of("KXNFLWINS-IND-25B-T8") == "KXNFLWINS"
    assert series_prefix_of("KXMLBPLAYOFFS-25-NYY") == "KXMLBPLAYOFFS"
    assert series_prefix_of("KXMLBGAME-26MAY24WSHATL-ATL") == "KXMLBGAME"


def test_parse_ladder_ticker_valid():
    assert parse_ladder_ticker("KXNFLWINS-IND-25B-T8") == ("KXNFLWINS-IND-25B", 8)
    assert parse_ladder_ticker("KXNBAWINS-CHA-25-T35") == ("KXNBAWINS-CHA-25", 35)


def test_parse_ladder_ticker_invalid():
    assert parse_ladder_ticker("KXMLBPLAYOFFS-25-NYY") is None
    assert parse_ladder_ticker("KXWCGAME-26JUN23ENGGHA-ENG") is None
    assert parse_ladder_ticker("KXMLBGAME-26MAY24WSHATL-ATL") is None


def test_is_ladder_series():
    assert is_ladder_series("KXNFLWINS")
    assert is_ladder_series("KXNBAWINS")
    assert is_ladder_series("KXMLBWINS")
    assert not is_ladder_series("KXMLBPLAYOFFS")
    assert not is_ladder_series("KXWCGAME")
    assert not is_ladder_series("KXMLBGAME")


def test_no_filter_inputs_passes():
    """With no inputs at all, filter abstains and v1 proceeds."""
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
    )
    assert d.should_trade is True
    assert d.reason == "no_match"
    assert d.poly_mid is None
    assert d.sportsbook_implied is None
    assert d.cross_market_implied is None
    assert d.fired_rules == ()


# --- A1: Polymarket-fade ---

def test_polymarket_fade_fires():
    """Kalshi 0.92 vs Polymarket 0.73 -> 19c divergence > 7c -> SKIP."""
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},
    )
    assert d.should_trade is False
    assert d.reason == "polymarket_fade"
    assert d.poly_mid == 0.73
    assert d.confidence > 0.0
    assert d.fired_rules == ("polymarket_fade",)


def test_polymarket_no_fade_when_close():
    """Kalshi 0.74 vs Polymarket 0.72 -> 2c divergence < 7c -> PASS."""
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-TOR",
        kalshi_price=0.74,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-TOR": 0.72},
    )
    assert d.should_trade is True
    assert d.reason == "pass"
    assert d.poly_mid == 0.72


def test_polymarket_no_match_passes():
    """If poly_lookup returns None for this ticker, A1 abstains."""
    d = evaluate_market_combined(
        ticker="KXBOXING-26SEP12-CAL",
        kalshi_price=0.80,
        series_ticker="KXBOXING-26SEP",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},
    )
    assert d.should_trade is True
    assert d.reason == "no_poly_match"


# --- A3: Sportsbook-fade ---

def test_sportsbook_fade_fires():
    """Kalshi 0.80 vs sportsbook 0.70 -> 10c divergence > 5c -> SKIP."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.80,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup={"KXMLBGAME-26MAY24WSHATL-ATL": 0.70},
    )
    assert d.should_trade is False
    assert d.reason == "sportsbook_fade"
    assert d.sportsbook_implied == 0.70
    assert d.confidence > 0.0
    assert d.fired_rules == ("sportsbook_fade",)


def test_sportsbook_no_fade_when_close():
    """Kalshi 0.74 vs sportsbook 0.72 -> 2c divergence < 5c -> PASS."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.74,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup={"KXMLBGAME-26MAY24WSHATL-ATL": 0.72},
    )
    assert d.should_trade is True
    assert d.reason == "pass"
    assert d.sportsbook_implied == 0.72


def test_sportsbook_fade_threshold_at_5c():
    """Kalshi 0.755 vs sportsbook 0.70 -> 5.5c divergence > 5c -> SKIP."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.755,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup={"KXMLBGAME-26MAY24WSHATL-ATL": 0.70},
    )
    assert d.should_trade is False
    assert d.reason == "sportsbook_fade"


def test_sportsbook_no_match_passes():
    """If sportsbook_lookup returns None, A3 abstains."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.80,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup={"KXOTHER-XX": 0.50},
    )
    assert d.should_trade is True
    assert d.reason == "no_book_match"


def test_sportsbook_under_priced_does_not_fire():
    """Kalshi 0.65 vs sportsbook 0.75 -> Kalshi UNDER-priced, do NOT skip.
    Defensive overlay only fires on over-pricing."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.65,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup={"KXMLBGAME-26MAY24WSHATL-ATL": 0.75},
    )
    assert d.should_trade is True
    assert d.sportsbook_implied == 0.75


def test_sportsbook_callable_lookup():
    """sportsbook_lookup may be a callable."""
    def lookup(t):
        return 0.50 if "ATL" in t else None
    d = evaluate_market_combined(
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        kalshi_price=0.80,
        series_ticker="KXMLBGAME-26MAY24WSHATL",
        sportsbook_lookup=lookup,
    )
    assert d.should_trade is False
    assert d.reason == "sportsbook_fade"
    assert d.sportsbook_implied == 0.50


# --- A2: Monotonicity ---

def test_monotonicity_violation_fires():
    cross_market = {
        "KXNFLWINS-IND-25B": {
            3: 0.96, 4: 0.86, 5: 0.86, 6: 0.82, 7: 0.37,
            8: 0.77, 9: 0.73, 10: 0.84,
        },
    }
    d = evaluate_market_combined(
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
    cross_market = {
        "KXNBAWINS-CHA-25": {
            30: 0.98, 35: 0.96, 40: 0.85, 45: 0.50, 50: 0.20,
        },
    }
    d = evaluate_market_combined(
        ticker="KXNBAWINS-CHA-25-T40",
        kalshi_price=0.85,
        series_ticker="KXNBAWINS-CHA",
        cross_market_data=cross_market,
    )
    assert d.should_trade is True
    assert d.cross_market_implied is not None


def test_non_ladder_series_a2_inactive():
    cross_market = {"KXMLBPLAYOFFS-25": {1: 0.40, 2: 0.95}}
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.95,
        series_ticker="KXMLBPLAYOFFS-25",
        cross_market_data=cross_market,
    )
    assert d.should_trade is True
    assert d.cross_market_implied is None


# --- Multi-rule combinations ---

def test_both_poly_and_sportsbook_fire():
    """A1 and A3 both fire -> reason 'any_fade_rule_fires', fired_rules
    includes both."""
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},
        sportsbook_lookup={"KXMLBPLAYOFFS-25-NYY": 0.80},
    )
    assert d.should_trade is False
    assert d.reason == "any_fade_rule_fires"
    assert "polymarket_fade" in d.fired_rules
    assert "sportsbook_fade" in d.fired_rules


def test_all_three_rules_fire():
    """A1, A2, and A3 all fire."""
    d = evaluate_market_combined(
        ticker="KXNFLWINS-XX-25B-T8",
        kalshi_price=0.80,
        series_ticker="KXNFLWINS-XX",
        poly_lookup={"KXNFLWINS-XX-25B-T8": 0.50},
        sportsbook_lookup={"KXNFLWINS-XX-25B-T8": 0.65},
        cross_market_data={"KXNFLWINS-XX-25B": {7: 0.30, 8: 0.80}},
    )
    assert d.should_trade is False
    assert d.reason == "any_fade_rule_fires"
    assert set(d.fired_rules) == {
        "polymarket_fade", "sportsbook_fade", "monotonicity_violation",
    }


def test_only_sportsbook_fires_when_poly_close():
    """Polymarket 6c divergence < 7c (no fire), sportsbook 8c > 5c -> fires."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-X",
        kalshi_price=0.80,
        series_ticker="KXMLBGAME-X",
        poly_lookup={"KXMLBGAME-X": 0.74},  # 6c < 7c
        sportsbook_lookup={"KXMLBGAME-X": 0.72},  # 8c > 5c
    )
    assert d.should_trade is False
    assert d.reason == "sportsbook_fade"
    assert d.fired_rules == ("sportsbook_fade",)


def test_only_poly_fires_when_sportsbook_close():
    """Polymarket 10c > 7c -> fires; sportsbook 3c < 5c -> no fire."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-X",
        kalshi_price=0.80,
        series_ticker="KXMLBGAME-X",
        poly_lookup={"KXMLBGAME-X": 0.70},
        sportsbook_lookup={"KXMLBGAME-X": 0.77},
    )
    assert d.should_trade is False
    assert d.reason == "polymarket_fade"
    assert d.fired_rules == ("polymarket_fade",)


def test_neither_fires_passes():
    """Both inputs present but neither divergence exceeds threshold."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-X",
        kalshi_price=0.74,
        series_ticker="KXMLBGAME-X",
        poly_lookup={"KXMLBGAME-X": 0.73},
        sportsbook_lookup={"KXMLBGAME-X": 0.72},
    )
    assert d.should_trade is True
    assert d.reason == "pass"


def test_no_book_match_but_poly_present():
    """sportsbook_lookup attempted but no match for this ticker; poly
    fires."""
    d = evaluate_market_combined(
        ticker="KXMLBPLAYOFFS-25-NYY",
        kalshi_price=0.92,
        series_ticker="KXMLBPLAYOFFS-25",
        poly_lookup={"KXMLBPLAYOFFS-25-NYY": 0.73},
        sportsbook_lookup={"KXOTHER": 0.50},
    )
    assert d.should_trade is False
    assert d.reason == "polymarket_fade"


# --- Threshold lock ---

def test_thresholds_are_locked():
    """Pre-registered defaults must be exactly 7c (poly) / 5c (book)
    / 5c (mono). Any change requires a new pre-registered test in
    research/v5/iterations.md."""
    assert FADE_THRESHOLD_CENTS_POLY_DEFAULT == 7.0
    assert FADE_THRESHOLD_CENTS_BOOK_DEFAULT == 5.0
    assert MONOTONICITY_THRESHOLD_CENTS_DEFAULT == 5.0


def test_combined_filter_decision_namedtuple_contract():
    d = CombinedFilterDecision(
        should_trade=True,
        reason="pass",
        poly_mid=0.5,
        sportsbook_implied=0.5,
        kalshi_price=0.6,
        cross_market_implied=None,
        confidence=0.0,
        fired_rules=(),
    )
    assert d.should_trade is True
    assert d.kalshi_price == 0.6
    assert d.fired_rules == ()


def test_no_poly_match_but_book_present_no_fire():
    """poly_lookup attempted but no match; book present but no fade.
    reason='pass' because book provided data."""
    d = evaluate_market_combined(
        ticker="KXMLBGAME-X",
        kalshi_price=0.74,
        series_ticker="KXMLBGAME-X",
        poly_lookup={"OTHER": 0.50},  # no match for our ticker
        sportsbook_lookup={"KXMLBGAME-X": 0.72},  # 2c < 5c, no fire
    )
    assert d.should_trade is True
    assert d.reason == "pass"  # at least one input had data


def test_only_poly_attempted_no_match():
    """Only poly_lookup attempted; no match for this ticker."""
    d = evaluate_market_combined(
        ticker="KXBOXING-X",
        kalshi_price=0.80,
        series_ticker="KXBOXING-X",
        poly_lookup={"OTHER": 0.50},
    )
    assert d.should_trade is True
    assert d.reason == "no_poly_match"


def test_only_book_attempted_no_match():
    """Only sportsbook_lookup attempted; no match for this ticker."""
    d = evaluate_market_combined(
        ticker="KXBOXING-X",
        kalshi_price=0.80,
        series_ticker="KXBOXING-X",
        sportsbook_lookup={"OTHER": 0.50},
    )
    assert d.should_trade is True
    assert d.reason == "no_book_match"
