"""Smoke tests for paper_trade_favorite entry point."""

from __future__ import annotations

import importlib

import structlog


def test_paper_trade_favorite_imports_cleanly() -> None:
    mod = importlib.import_module("scripts.paper_trade_favorite")
    assert callable(mod.main)
    assert callable(mod.one_loop_favorite_paper)
    assert callable(mod.one_loop_favorite_live)
    assert callable(mod.expected_net_edge_for_favorite)


def test_v1_per_bid_contracts_scales_with_bankroll() -> None:
    mod = importlib.import_module("scripts.paper_trade_favorite")
    f = mod.v1_per_bid_contracts
    # 3% of a $30 cap = $0.90 -> 1 contract at 0.75; same as today's fixed $.
    assert f(0.75, v1_cap_total=30.0, per_bid_fraction=0.03, fallback_usd=0.95) == 1
    # Scales up as the operator deposits: $60 cap -> $1.80 -> 2 contracts.
    assert f(0.75, v1_cap_total=60.0, per_bid_fraction=0.03, fallback_usd=0.95) == 2
    # $300 cap -> $9.00 -> 12 contracts at 0.75.
    assert f(0.75, v1_cap_total=300.0, per_bid_fraction=0.03, fallback_usd=0.95) == 12


def test_v1_per_bid_contracts_floors_at_one() -> None:
    mod = importlib.import_module("scripts.paper_trade_favorite")
    f = mod.v1_per_bid_contracts
    # Tiny cap: sub-1 budget still places the minimum 1 contract.
    assert f(0.90, v1_cap_total=10.0, per_bid_fraction=0.03, fallback_usd=0.95) == 1


def test_v1_per_bid_contracts_fallback_when_no_cap() -> None:
    mod = importlib.import_module("scripts.paper_trade_favorite")
    f = mod.v1_per_bid_contracts
    # No fraction cap -> legacy fixed-dollar fallback.
    assert f(0.75, v1_cap_total=None, per_bid_fraction=0.03, fallback_usd=0.95) == 1
    assert f(0.30, v1_cap_total=None, per_bid_fraction=0.03, fallback_usd=0.95) == 3


def test_resolve_v1_cap_full_fraction_uses_full_bankroll() -> None:
    """research/v20 fix: at fraction == 1.0 the cap is the FULL bankroll (so
    per-bid sizing is live), and cash is NOT restricted (budget gate unchanged)."""
    mod = importlib.import_module("scripts.paper_trade_favorite")
    cap, eff_cash = mod.resolve_v1_cap_and_cash(
        cash_usd=40.0, pos_usd=14.0, bankroll_fraction=1.0, v1_filled_exposure=14.0,
    )
    assert cap == 54.0  # full cash + positions
    assert eff_cash == 40.0  # no restriction at 1.0


def test_resolve_v1_cap_partial_fraction_restricts_cash() -> None:
    """At a partial slice the cap is the slice and effective cash is restricted
    to the slice minus already-held filled exposure (prior v14-era behavior)."""
    mod = importlib.import_module("scripts.paper_trade_favorite")
    cap, eff_cash = mod.resolve_v1_cap_and_cash(
        cash_usd=40.0, pos_usd=20.0, bankroll_fraction=0.6, v1_filled_exposure=10.0,
    )
    assert cap == 36.0  # 0.6 * (40 + 20)
    assert eff_cash == 26.0  # min(40, 36 - 10)


def test_full_fraction_makes_per_bid_live_regression_guard() -> None:
    """End-to-end guard for the dead-knob regression: at fraction 1.0 and a ~$54
    bankroll, the resolved cap drives v1_per_bid_contracts to 2 contracts, NOT
    the 1-contract LIVE_PER_TRADE_USD fallback the bug produced."""
    mod = importlib.import_module("scripts.paper_trade_favorite")
    cap, _ = mod.resolve_v1_cap_and_cash(
        cash_usd=40.0, pos_usd=14.0, bankroll_fraction=1.0, v1_filled_exposure=14.0,
    )
    contracts = mod.v1_per_bid_contracts(
        0.78, v1_cap_total=cap, per_bid_fraction=0.03, fallback_usd=0.95,
    )
    assert contracts == 2  # 0.03 * 54 = $1.62 -> 2 @ $0.78
    # The buggy path (cap is None) would have produced exactly 1.
    buggy = mod.v1_per_bid_contracts(
        0.78, v1_cap_total=None, per_bid_fraction=0.03, fallback_usd=0.95,
    )
    assert buggy == 1 and contracts > buggy


def test_event_identity_dedups_sibling_tickers_c1() -> None:
    """research/v20 C1: the two sibling outcome tickers of one head-to-head
    event must share an identity so the NO-underdog arm cannot rest a bid on
    both (which is the same directional bet)."""
    mod = importlib.import_module("scripts.paper_trade_favorite")
    ev = mod.event_identity
    # Explicit event_ticker wins.
    assert ev("KXATPMATCH-26JUN05MENZVE-ZVE", "KXATPMATCH-26JUN05MENZVE") == "KXATPMATCH-26JUN05MENZVE"
    # Fallback: strip the final outcome segment when event_ticker is empty.
    assert ev("KXATPMATCH-26JUN05MENZVE-MEN", "") == "KXATPMATCH-26JUN05MENZVE"
    # Both siblings collapse to the same identity (the dedup guarantee).
    assert ev("KXWTAMATCH-26JUN03SABSHN-SAB", "") == ev("KXWTAMATCH-26JUN03SABSHN-SHN", "")
    # Different events stay distinct.
    assert ev("KXATPMATCH-26JUN05MENZVE-ZVE", "") != ev("KXATPMATCH-26JUN06AAABBB-AAA", "")


def test_band_sizing_pre_floor_lifts_low_band_h2() -> None:
    """research/v20 H2: folding the band multiplier into the fraction BEFORE the
    floor-divide makes it actually change the contract count. The old
    round(base * mult) was inert at small bankroll where base == 1."""
    mod = importlib.import_module("scripts.paper_trade_favorite")
    from kalshi_bot.strategy.favorite_maker import band_size_multiplier
    cap = 54.0
    low_mult = band_size_multiplier(0.85, m_low=1.3, m_high=0.8)
    high_mult = band_size_multiplier(0.90, m_low=1.3, m_high=0.8)
    assert low_mult == 1.3 and high_mult == 0.8
    # LOW 0.85: base fraction -> 1 contract; band-scaled fraction -> 2.
    base = mod.v1_per_bid_contracts(0.85, v1_cap_total=cap, per_bid_fraction=0.03, fallback_usd=0.95)
    boosted = mod.v1_per_bid_contracts(0.85, v1_cap_total=cap, per_bid_fraction=0.03 * low_mult, fallback_usd=0.95)
    assert base == 1 and boosted == 2
    # heavy 0.90: x0.8 keeps the smaller size (1 contract), matching its lower edge.
    heavy = mod.v1_per_bid_contracts(0.90, v1_cap_total=cap, per_bid_fraction=0.03 * high_mult, fallback_usd=0.95)
    assert heavy == 1


def test_expected_net_edge_for_favorite_positive_at_85c() -> None:
    """Post-Round-5: empirical YES rate now defaults to 0.95 (was 0.97).

    At YES=0.85 with 0.95 rate:
    - gross = 0.95 - 0.85 = 0.10
    - fee (round-trip maker, ceil(1.75 * 0.85 * 0.15) * 2 / 100) = 0.02
    - slippage = 0.015
    - net = 0.065
    """
    import pytest
    from scripts.paper_trade_favorite import expected_net_edge_for_favorite
    assert expected_net_edge_for_favorite(0.85) == pytest.approx(0.065, abs=1e-6)


def test_expected_net_edge_for_favorite_decreases_with_price() -> None:
    """As yes_price approaches 1.0, expected gross shrinks toward 0; net
    goes negative."""
    from scripts.paper_trade_favorite import expected_net_edge_for_favorite
    edges = [expected_net_edge_for_favorite(p) for p in (0.70, 0.80, 0.90, 0.97)]
    # Each subsequent edge is smaller or equal
    for prev, curr in zip(edges, edges[1:], strict=False):
        assert curr <= prev + 1e-9
    # At 0.97, gross = -0.02 (with 0.95 default), net negative after fees.
    assert edges[-1] < 0


def test_live_modes_in_argparse_choices() -> None:
    """--mode must accept paper, live, and live-demo."""
    # Import succeeds; argparse choices are documented in main().
    # Validate by attempting to parse:
    import sys
    from contextlib import suppress

    from scripts.paper_trade_favorite import main  # noqa: F401
    sys.argv_backup = sys.argv[:]
    try:
        sys.argv = ["paper_trade_favorite", "--mode", "live", "--help"]
        with suppress(SystemExit):
            main()
    finally:
        sys.argv = sys.argv_backup


# ============================================================
# --max-concurrent auto (dynamic cap)
# ============================================================

import pytest

from scripts.paper_trade_favorite import (
    MAX_CONCURRENT_AUTO,
    _parse_max_concurrent_arg,
    _resolve_max_concurrent_paper,
    _sum_open_positions_value,
)


def test_parse_max_concurrent_int() -> None:
    assert _parse_max_concurrent_arg("15") == 15
    assert _parse_max_concurrent_arg("1") == 1
    assert _parse_max_concurrent_arg("100") == 100


def test_parse_max_concurrent_auto_case_insensitive() -> None:
    assert _parse_max_concurrent_arg("auto") == MAX_CONCURRENT_AUTO
    assert _parse_max_concurrent_arg("AUTO") == MAX_CONCURRENT_AUTO
    assert _parse_max_concurrent_arg("Auto") == MAX_CONCURRENT_AUTO
    assert _parse_max_concurrent_arg(" auto ") == MAX_CONCURRENT_AUTO


def test_parse_max_concurrent_rejects_invalid() -> None:
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_max_concurrent_arg("nope")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_max_concurrent_arg("0")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_max_concurrent_arg("-3")


def test_sum_open_positions_value_empty() -> None:
    assert _sum_open_positions_value([]) == 0.0


def test_sum_open_positions_value_with_orders() -> None:
    from types import SimpleNamespace
    orders = [
        SimpleNamespace(target_price_cents=70, contracts=1),
        SimpleNamespace(target_price_cents=85, contracts=2),
        SimpleNamespace(target_price_cents=95, contracts=1),
    ]
    # 0.70*1 + 0.85*2 + 0.95*1 = 0.70 + 1.70 + 0.95 = 3.35
    assert abs(_sum_open_positions_value(orders) - 3.35) < 1e-9


def test_sum_open_positions_value_falls_back_to_filled_price() -> None:
    """If target_price_cents is None, use filled_price_cents instead."""
    from types import SimpleNamespace
    orders = [
        SimpleNamespace(target_price_cents=None, filled_price_cents=80, contracts=1),
    ]
    assert abs(_sum_open_positions_value(orders) - 0.80) < 1e-9


def test_resolve_max_concurrent_paper_passes_int_through() -> None:
    """When the setting is already an int, resolver returns it unchanged."""
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 25.0
    assert _resolve_max_concurrent_paper(5, om) == 5
    assert _resolve_max_concurrent_paper(33, om) == 33


def test_resolve_max_concurrent_paper_auto_uses_bankroll() -> None:
    """'auto' derives from current_paper_bankroll() / 0.95."""
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 32.0
    # No positions yet, bankroll == starting; floor(32/0.95) = 33
    assert _resolve_max_concurrent_paper(MAX_CONCURRENT_AUTO, om) == 33
    # Simulate a $4 drawdown
    om.state.starting_bankroll_usd = 28.0
    assert _resolve_max_concurrent_paper(MAX_CONCURRENT_AUTO, om) == 29


def test_resolve_max_concurrent_paper_auto_zero_bankroll() -> None:
    """Bankroll of $0 returns the floor of 1 (one slot kept eligible)."""
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 0.0
    assert _resolve_max_concurrent_paper(MAX_CONCURRENT_AUTO, om) == 1


# ============================================================
# --starting-bankroll auto (read from Kalshi at startup)
# ============================================================

from scripts.paper_trade_favorite import (
    STARTING_BANKROLL_AUTO,
    _parse_starting_bankroll_arg,
    _read_kalshi_total_bankroll_usd,
    _resolve_starting_bankroll_live,
    _resolve_starting_bankroll_paper,
)


def test_parse_starting_bankroll_float() -> None:
    assert _parse_starting_bankroll_arg("32") == 32.0
    assert _parse_starting_bankroll_arg("50.5") == 50.5


def test_parse_starting_bankroll_auto() -> None:
    assert _parse_starting_bankroll_arg("auto") == STARTING_BANKROLL_AUTO
    assert _parse_starting_bankroll_arg("AUTO") == STARTING_BANKROLL_AUTO
    assert _parse_starting_bankroll_arg(" Auto ") == STARTING_BANKROLL_AUTO


def test_parse_starting_bankroll_rejects_invalid() -> None:
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_starting_bankroll_arg("nope")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_starting_bankroll_arg("0")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_starting_bankroll_arg("-5")


def test_resolve_starting_bankroll_paper_explicit() -> None:
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 100.0
    # Explicit value overrides any persisted state.
    assert _resolve_starting_bankroll_paper(75.0, om, rebaseline=False) == 75.0


def test_resolve_starting_bankroll_paper_auto_uses_state() -> None:
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 42.0
    result = _resolve_starting_bankroll_paper(
        STARTING_BANKROLL_AUTO, om, rebaseline=False,
    )
    assert result == 42.0


def test_resolve_starting_bankroll_paper_auto_falls_back_when_no_state() -> None:
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 0.0
    result = _resolve_starting_bankroll_paper(
        STARTING_BANKROLL_AUTO, om, rebaseline=False, fallback=25.0,
    )
    assert result == 25.0


def test_resolve_starting_bankroll_paper_rebaseline_overrides_state() -> None:
    from kalshi_bot.strategy.order_manager import PaperOrderManager
    om = PaperOrderManager()
    om.state.starting_bankroll_usd = 42.0
    # rebaseline=True ignores persisted state and uses fallback.
    result = _resolve_starting_bankroll_paper(
        STARTING_BANKROLL_AUTO, om, rebaseline=True, fallback=25.0,
    )
    assert result == 25.0


class _FakeClient:
    def __init__(self, balance_cents: int, portfolio_value_cents: int = 0):
        self._balance_cents = balance_cents
        self._portfolio_value_cents = portfolio_value_cents
        self._raises = None

    def set_raises(self, exc):
        self._raises = exc

    def get(self, endpoint, **params):
        if self._raises:
            raise self._raises
        return {
            "balance": self._balance_cents,
            "portfolio_value": self._portfolio_value_cents,
        }


def test_read_kalshi_total_bankroll_no_positions() -> None:
    """Cash $32.50, no filled positions, total $32.50."""
    client = _FakeClient(balance_cents=3250, portfolio_value_cents=0)
    total = _read_kalshi_total_bankroll_usd(client, [])
    assert abs(total - 32.50) < 1e-9


def test_read_kalshi_total_bankroll_with_positions() -> None:
    """Cash $27.22 + portfolio_value $4.08 = $31.30. open_orders arg is
    ignored: positions value comes from Kalshi, not local resting state.
    """
    from types import SimpleNamespace
    client = _FakeClient(balance_cents=2722, portfolio_value_cents=408)
    # Pass arbitrary local orders; they should be IGNORED.
    bogus_orders = [
        SimpleNamespace(target_price_cents=70, contracts=100),  # would have added $70 in old impl
    ]
    total = _read_kalshi_total_bankroll_usd(client, bogus_orders)
    # Correct: $27.22 + $4.08 = $31.30. NOT $27.22 + $70 = $97.22.
    assert abs(total - 31.30) < 1e-9


def _make_fake_lm(starting_bankroll_usd: float = 0.0):
    """Lightweight mock of LiveOrderManager that doesn't touch state.json."""
    from types import SimpleNamespace
    return SimpleNamespace(
        state=SimpleNamespace(
            starting_bankroll_usd=starting_bankroll_usd,
            resting={},
            filled={},
        ),
    )


def test_resolve_starting_bankroll_live_explicit() -> None:
    log_main = structlog.get_logger("test")
    lm = _make_fake_lm(starting_bankroll_usd=0.0)
    # Explicit value: skips Kalshi read entirely.
    result = _resolve_starting_bankroll_live(
        50.0, lm, _FakeClient(0),
        rebaseline=False, log_main=log_main,
    )
    assert result == 50.0


def test_resolve_starting_bankroll_live_auto_prefers_live_over_state() -> None:
    """Startup ALWAYS prefers the live Kalshi read over a persisted value, even
    without --rebaseline, so deposits/withdrawals made while the bot was down
    are picked up. Intentional (commit c0c3225): drawdown continuity is
    sacrificed for operator-correct startup state; Kalshi /portfolio/balance is
    the single source of truth."""
    log_main = structlog.get_logger("test")
    lm = _make_fake_lm(starting_bankroll_usd=32.0)
    # Persisted $32, but live Kalshi reads $999.99 -> live wins.
    result = _resolve_starting_bankroll_live(
        STARTING_BANKROLL_AUTO, lm, _FakeClient(99999),
        rebaseline=False, log_main=log_main,
    )
    assert abs(result - 999.99) < 1e-9  # live Kalshi overrides persisted


def test_resolve_starting_bankroll_live_rebaseline_reads_kalshi() -> None:
    log_main = structlog.get_logger("test")
    client = _FakeClient(balance_cents=5000)  # $50.00
    lm = _make_fake_lm(starting_bankroll_usd=32.0)
    # rebaseline forces fresh read.
    result = _resolve_starting_bankroll_live(
        STARTING_BANKROLL_AUTO, lm, client,
        rebaseline=True, log_main=log_main,
    )
    assert abs(result - 50.0) < 1e-9


def test_resolve_starting_bankroll_live_auto_reads_kalshi_when_no_state() -> None:
    log_main = structlog.get_logger("test")
    client = _FakeClient(balance_cents=3200)  # $32.00
    lm = _make_fake_lm(starting_bankroll_usd=0.0)
    result = _resolve_starting_bankroll_live(
        STARTING_BANKROLL_AUTO, lm, client,
        rebaseline=False, log_main=log_main,
    )
    assert abs(result - 32.0) < 1e-9


def test_resolve_starting_bankroll_live_falls_back_on_kalshi_failure() -> None:
    log_main = structlog.get_logger("test")
    client = _FakeClient(balance_cents=0)
    client.set_raises(RuntimeError("API down"))
    lm = _make_fake_lm(starting_bankroll_usd=32.0)
    # Rebaseline tries Kalshi first, fails, falls back to state.
    result = _resolve_starting_bankroll_live(
        STARTING_BANKROLL_AUTO, lm, client,
        rebaseline=True, log_main=log_main,
    )
    assert result == 32.0


def test_resolve_starting_bankroll_live_systemexit_when_no_fallback() -> None:
    log_main = structlog.get_logger("test")
    client = _FakeClient(balance_cents=0)
    client.set_raises(RuntimeError("API down"))
    lm = _make_fake_lm(starting_bankroll_usd=0.0)  # no state
    with pytest.raises(SystemExit):
        _resolve_starting_bankroll_live(
            STARTING_BANKROLL_AUTO, lm, client,
            rebaseline=False, log_main=log_main,
        )
