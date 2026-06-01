"""Tests for the Kalshi dutch-book / no-arb analysis core."""

from __future__ import annotations

import pytest

from kalshi_bot.analysis.dutchbook import (
    analyze_group,
    annualized_return,
    parse_market_quote,
)


def test_parse_market_quote_full() -> None:
    m = {
        "ticker": "KX-A", "status": "active",
        "yes_bid_dollars": "0.45", "yes_ask_dollars": "0.48",
        "no_ask_dollars": "0.55", "yes_ask_size_fp": "100", "no_ask_size_fp": "50",
    }
    q = parse_market_quote(m)
    assert q["yes_bid"] == 0.45
    assert q["yes_ask"] == 0.48
    assert q["no_ask"] == 0.55
    assert q["yes_ask_size"] == 100.0
    assert q["no_ask_size"] == 50.0


def test_parse_market_quote_zero_and_missing_are_none() -> None:
    q = parse_market_quote({"yes_ask_dollars": "0", "no_ask_dollars": None})
    assert q["yes_ask"] is None
    assert q["no_ask"] is None
    assert q["yes_bid"] is None
    assert q["yes_ask_size"] == 0.0


def _q(yes_ask=None, no_ask=None, ya_size=10.0, na_size=10.0, yes_bid=None) -> dict:
    return {
        "ticker": "t", "status": "active", "yes_bid": yes_bid, "yes_ask": yes_ask,
        "no_ask": no_ask, "yes_ask_size": ya_size, "no_ask_size": na_size,
    }


def test_analyze_group_underround_positive() -> None:
    quotes = [_q(yes_ask=0.30), _q(yes_ask=0.30), _q(yes_ask=0.30)]
    r = analyze_group(quotes)
    assert r["n"] == 3
    u = r["underround"]
    assert u is not None
    assert u["cost"] == pytest.approx(0.90)
    assert u["gross_margin"] == pytest.approx(0.10)
    # taker fee at 0.30 = ceil(7*0.3*0.7)/100 = ceil(1.47)/100 = 0.02; x3 = 0.06
    assert u["total_fee"] == pytest.approx(0.06)
    assert u["net_margin"] == pytest.approx(0.04)
    assert u["min_depth"] == 10.0


def test_analyze_group_overround_positive() -> None:
    quotes = [_q(no_ask=0.60), _q(no_ask=0.60), _q(no_ask=0.60)]
    r = analyze_group(quotes)
    o = r["overround"]
    assert o is not None
    # cost 1.80; gross = (3-1) - 1.80 = 0.20; fee 0.02 x3 = 0.06; net = 0.14
    assert o["cost"] == pytest.approx(1.80)
    assert o["gross_margin"] == pytest.approx(0.20)
    assert o["net_margin"] == pytest.approx(0.14)


def test_analyze_group_missing_leg_blocks_lock() -> None:
    # One leg has no yes_ask -> underround uncomputable; no_ask present on all ->
    # overround computable.
    quotes = [_q(yes_ask=0.30, no_ask=0.60), _q(yes_ask=None, no_ask=0.60),
              _q(yes_ask=0.30, no_ask=0.60)]
    r = analyze_group(quotes)
    assert r["underround"] is None
    assert r["overround"] is not None


def test_analyze_group_no_lock_when_priced_fairly() -> None:
    # Asks sum > 1 (typical overround book): no underround. NO asks sum so that
    # (n-1) - sum < 0: no overround either.
    quotes = [_q(yes_ask=0.40, no_ask=0.65), _q(yes_ask=0.40, no_ask=0.65),
              _q(yes_ask=0.40, no_ask=0.65)]
    r = analyze_group(quotes)
    assert r["underround"]["net_margin"] < 0  # cost 1.20 > 1
    assert r["overround"]["net_margin"] < 0  # gross = 2 - 1.95 = 0.05, minus fees... check sign
    # 2 - 1.95 = 0.05 gross; fee(0.65)=ceil(7*0.65*0.35)/100=ceil(1.59)/100=0.02 x3=0.06; net=-0.01
    assert r["overround"]["net_margin"] == pytest.approx(-0.01)


def test_analyze_group_small_n() -> None:
    assert analyze_group([])["underround"] is None
    assert analyze_group([_q(yes_ask=0.5)])["overround"] is None


def test_annualized_return() -> None:
    # net 0.04 on cost 0.90 over 30 days -> (0.04/0.90)*(365/30)
    ar = annualized_return(0.04, 0.90, 30.0)
    assert ar == pytest.approx((0.04 / 0.90) * (365.0 / 30.0))
    assert annualized_return(0.04, 0.0, 30.0) is None
    assert annualized_return(0.04, 0.90, 0.0) is None
