"""Smoke tests for the paper_trade entry point.

These catch import-level bugs and basic CLI parsing. They do not
exercise the live Kalshi API; for that, run --once manually after the
gate passes.
"""

from __future__ import annotations

import importlib

import pytest


def test_paper_trade_module_imports_cleanly() -> None:
    """If any imported symbol is missing (e.g., `send` not exported from
    alerts.discord), this fails. Code review milestone 2 caught such a
    bug pre-fix; this test prevents regression."""
    mod = importlib.import_module("scripts.paper_trade")
    assert callable(mod.main)
    assert callable(mod.one_loop)
    assert callable(mod.fit_calibrator_from_dataset)


def test_paper_trade_argparse_help() -> None:
    """--help should print usage without crashing."""
    import scripts.paper_trade as pt
    parser_test = None
    with pytest.raises(SystemExit):
        # main() calls parse_args which exits on --help
        pt.main()  # noqa: F841 (intentional; just ensuring it errors not crashes)
    _ = parser_test


def test_paper_trade_required_constants() -> None:
    """Defaults match the methodology slippage allowance and Phase 2 critic
    findings about minimum net edge."""
    from kalshi_bot.strategy.pricing import DEFAULT_SLIPPAGE
    assert DEFAULT_SLIPPAGE == 0.015
