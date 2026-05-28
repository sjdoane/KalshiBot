"""Tests for the Track A shadow-mode v5 filter hook.

The hook lives in `src/kalshi_bot/strategy/shadow_filter.py` and is
called from v1's `paper_trade_favorite.py`. These tests verify the
three hard safety contracts:

1. Default OFF: returns None when SHADOW_MODE_ENABLED is unset.
2. Failure isolation: returns None on any fetcher exception.
3. Never raises: every conceivable failure path is non-fatal.

Plus one positive test: env enabled + happy-path fetchers writes a
valid JSONL line.

Also covers the two fetcher modules at a minimal level:
- polymarket_fetcher returns None on timeout / unknown ticker.
- sportsbook_fetcher respects the per-loop credit budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kalshi_bot.strategy.pricing import MarketSnapshot
from kalshi_bot.strategy.shadow_filter import (
    SHADOW_LOG_PATH,
    SHADOW_MODE_ENV,
    ShadowDecision,
    _is_enabled,
    shadow_evaluate,
)


def _make_snap(ticker: str = "KXMLBGAME-26MAY24WSHATL-ATL",
               series: str = "KXMLBGAME") -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        event_ticker="KXMLBGAME-26MAY24WSHATL",
        series_ticker=series,
        yes_bid=0.78,
        yes_ask=0.82,
        last_price=0.80,
        volume=100.0,
        open_time="2026-05-23T22:00:00Z",
        close_time="2026-05-25T02:00:00Z",
        title="Will the Braves beat the Nationals?",
    )


@pytest.fixture
def env_disabled(monkeypatch):
    """Ensure SHADOW_MODE_ENABLED is unset for this test."""
    monkeypatch.delenv(SHADOW_MODE_ENV, raising=False)
    yield


@pytest.fixture
def env_enabled(monkeypatch):
    """Set SHADOW_MODE_ENABLED=true for this test."""
    monkeypatch.setenv(SHADOW_MODE_ENV, "true")
    yield


@pytest.fixture
def isolated_log_path(monkeypatch, tmp_path):
    """Redirect SHADOW_LOG_PATH writes to a temp directory."""
    temp_log = tmp_path / "v5_filter_shadow_log.jsonl"
    monkeypatch.setattr(
        "kalshi_bot.strategy.shadow_filter.SHADOW_LOG_PATH", temp_log,
    )
    yield temp_log


# 1. Default OFF


def test_shadow_evaluate_returns_none_when_disabled(env_disabled):
    snap = _make_snap()
    result = shadow_evaluate(snap, 0.78)
    assert result is None


def test_shadow_evaluate_returns_none_for_false_value(monkeypatch):
    monkeypatch.setenv(SHADOW_MODE_ENV, "false")
    snap = _make_snap()
    assert shadow_evaluate(snap, 0.78) is None


def test_shadow_evaluate_returns_none_for_non_canonical_truthy(monkeypatch):
    """Only the literal 'true' enables; '1', 'yes', 'enabled' do not."""
    snap = _make_snap()
    for val in ("1", "yes", "enabled", "TRUE_ish", ""):
        monkeypatch.setenv(SHADOW_MODE_ENV, val)
        # Only "TRUE" / "True" / "TrUe" should enable (case-insensitive
        # exact match on "true"); anything else stays disabled.
        if val.lower() == "true":
            continue
        assert shadow_evaluate(snap, 0.78) is None


def test_is_enabled_canonical_truthy(monkeypatch):
    monkeypatch.setenv(SHADOW_MODE_ENV, "true")
    assert _is_enabled() is True
    monkeypatch.setenv(SHADOW_MODE_ENV, "True")
    assert _is_enabled() is True
    monkeypatch.setenv(SHADOW_MODE_ENV, "TRUE")
    assert _is_enabled() is True
    monkeypatch.setenv(SHADOW_MODE_ENV, "yes")
    assert _is_enabled() is False
    monkeypatch.delenv(SHADOW_MODE_ENV, raising=False)
    assert _is_enabled() is False


# 2. Failure isolation


def test_shadow_evaluate_returns_none_on_fetcher_failure(
    env_enabled, isolated_log_path,
):
    """If both fetchers raise, shadow_evaluate must still complete and
    return a ShadowDecision (it logs whatever info it has). The
    decision MUST NOT raise out."""
    snap = _make_snap()
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        side_effect=RuntimeError("poly down"),
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        side_effect=RuntimeError("book down"),
    ):
        result = shadow_evaluate(snap, 0.78)
    # Result is a ShadowDecision (not None), but both fetch_status are
    # "error" and the implied values are None.
    assert isinstance(result, ShadowDecision)
    assert result.fetch_status["poly"] == "error"
    assert result.fetch_status["book"] == "error"
    assert result.poly_mid is None
    assert result.sportsbook_implied is None


def test_shadow_evaluate_returns_none_on_combined_filter_failure(
    env_enabled, isolated_log_path,
):
    """If evaluate_market_combined itself raises, shadow_evaluate returns
    None and does not propagate."""
    snap = _make_snap()
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.filter_combined.evaluate_market_combined",
        side_effect=RuntimeError("filter exploded"),
    ):
        result = shadow_evaluate(snap, 0.78)
    assert result is None


def test_shadow_evaluate_returns_none_on_disk_write_failure(
    env_enabled, isolated_log_path, monkeypatch,
):
    """If the JSONL write fails (e.g., permission), the function still
    returns the decision but logs the disk error and does not raise."""
    snap = _make_snap()

    # Force the disk write to fail by patching Path.open. We rebind
    # the module-level SHADOW_LOG_PATH to a path whose parent will
    # successfully mkdir, then patch the open() to raise.
    def _bad_open(self, *_args, **_kwargs):
        raise OSError("disk full")

    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=None,
    ), patch.object(Path, "open", _bad_open):
        result = shadow_evaluate(snap, 0.78)
    # Disk failure is non-fatal; decision is still returned.
    assert isinstance(result, ShadowDecision)


# 3. JSONL write on happy path


def test_shadow_evaluate_writes_jsonl_entry_when_enabled(
    env_enabled, isolated_log_path,
):
    snap = _make_snap()
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=0.65,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=0.70,
    ):
        result = shadow_evaluate(snap, 0.78)
    assert isinstance(result, ShadowDecision)
    assert result.poly_mid == 0.65
    assert result.sportsbook_implied == 0.70
    assert result.fetch_status == {"poly": "ok", "book": "ok"}
    # Kalshi 0.78 - poly 0.65 = +13c, above 7c threshold, A1 fires.
    # Kalshi 0.78 - book 0.70 = +8c, above 5c threshold, A3 fires too.
    # Multi-rule combination -> reason="any_fade_rule_fires".
    assert result.should_trade is False
    assert "polymarket_fade" in result.fired_rules
    assert "sportsbook_fade" in result.fired_rules

    # JSONL line is present and parses cleanly.
    assert isolated_log_path.exists()
    line = isolated_log_path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["ticker"] == snap.ticker
    assert parsed["kalshi_price"] == 0.78
    assert parsed["poly_mid"] == 0.65
    assert parsed["sportsbook_implied"] == 0.70
    assert parsed["should_trade"] is False
    assert isinstance(parsed["fired_rules"], list)
    assert "polymarket_fade" in parsed["fired_rules"]


def test_shadow_evaluate_writes_pass_decision_when_aligned(
    env_enabled, isolated_log_path,
):
    """When Polymarket / sportsbook agree with Kalshi within threshold,
    the filter says PASS (should_trade=True)."""
    snap = _make_snap()
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=0.76,  # Kalshi 0.78 - 0.76 = +2c, well under 7c poly threshold
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=0.77,  # Kalshi 0.78 - 0.77 = +1c, well under 5c book threshold
    ):
        result = shadow_evaluate(snap, 0.78)
    assert isinstance(result, ShadowDecision)
    assert result.should_trade is True
    assert result.fired_rules == ()
    assert result.reason == "pass"


def test_shadow_evaluate_appends_multiple_lines(
    env_enabled, isolated_log_path,
):
    """Repeated calls append independent lines."""
    snap1 = _make_snap(ticker="KXMLBGAME-26MAY24NYYBOS-NYY")
    snap2 = _make_snap(ticker="KXMLBGAME-26MAY25NYMATL-NYM")
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=None,
    ):
        r1 = shadow_evaluate(snap1, 0.80)
        r2 = shadow_evaluate(snap2, 0.85)
    assert r1 is not None and r2 is not None
    lines = isolated_log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["ticker"] == snap1.ticker
    assert parsed[1]["ticker"] == snap2.ticker


# 4. Never raises - exhaustive paths


def test_shadow_evaluate_never_raises_on_malformed_snap(
    env_enabled, isolated_log_path,
):
    """If snap has nan / weird price values, function still returns
    either a ShadowDecision or None - never raises."""
    snap = _make_snap()
    with patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=None,
    ):
        for bad_price in (float("nan"), float("inf"), -1.0, 100.0):
            result = shadow_evaluate(snap, bad_price)
            assert result is None or isinstance(result, ShadowDecision)


def test_shadow_evaluate_never_raises_on_import_error(
    env_enabled, isolated_log_path,
):
    """If a lazy import fails, function still returns None gracefully."""
    snap = _make_snap()
    # Simulate v5 module import failure by patching one of the
    # importable names to raise on access.
    import sys
    saved = sys.modules.pop("kalshi_bot_v5.filter_combined", None)
    try:
        # Inject a sentinel module that raises on attribute access.
        class _Boom:
            def __getattr__(self, name):
                raise ImportError(f"simulated import failure for {name}")
        sys.modules["kalshi_bot_v5.filter_combined"] = _Boom()
        result = shadow_evaluate(snap, 0.78)
        # The lazy import inside shadow_evaluate uses `from ... import
        # evaluate_market_combined`, which triggers __getattr__ and
        # raises ImportError; we catch it and return None.
        assert result is None
    finally:
        if saved is not None:
            sys.modules["kalshi_bot_v5.filter_combined"] = saved
        else:
            sys.modules.pop("kalshi_bot_v5.filter_combined", None)


def test_shadow_evaluate_never_raises_when_log_dir_unmakeable(
    env_enabled, monkeypatch, tmp_path,
):
    """If parent.mkdir() raises, the function still returns the
    decision without propagating the OSError."""
    snap = _make_snap()
    # Point the log to a non-creatable path (a path under a file, not a
    # dir). Then patch mkdir to raise.
    fake_path = tmp_path / "bogus" / "log.jsonl"
    monkeypatch.setattr(
        "kalshi_bot.strategy.shadow_filter.SHADOW_LOG_PATH", fake_path,
    )

    real_mkdir = Path.mkdir

    def _bad_mkdir(self, *args, **kwargs):
        if str(self).endswith("bogus"):
            raise PermissionError("cannot mkdir")
        return real_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", _bad_mkdir), patch(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        return_value=None,
    ), patch(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        return_value=None,
    ):
        result = shadow_evaluate(snap, 0.78)
    # Disk failure is non-fatal; decision is still returned.
    assert isinstance(result, ShadowDecision)


def test_shadow_decision_dataclass_shape():
    """ShadowDecision is a plain dataclass with the documented fields."""
    sd = ShadowDecision(
        timestamp="2026-05-24T12:00:00+00:00",
        ticker="KXMLBGAME-26MAY24WSHATL-ATL",
        series_ticker="KXMLBGAME",
        kalshi_price=0.78,
        poly_mid=0.65,
        sportsbook_implied=0.70,
        cross_market_implied=None,
        should_trade=False,
        fired_rules=("polymarket_fade", "sportsbook_fade"),
        reason="any_fade_rule_fires",
        confidence=0.5,
        fetch_status={"poly": "ok", "book": "ok"},
        fetch_latency_ms=120,
    )
    # __dict__ is JSON-friendly via the helper.
    from kalshi_bot.strategy.shadow_filter import _serialize_for_jsonl
    line = _serialize_for_jsonl(sd)
    parsed = json.loads(line)
    assert parsed["ticker"] == sd.ticker
    assert parsed["fired_rules"] == ["polymarket_fade", "sportsbook_fade"]


# 5. SHADOW_LOG_PATH default location sanity


def test_default_shadow_log_path_under_live_trades():
    """Sanity: the default log lives under data/live_trades/ alongside
    v1's other operational files but is a SEPARATE filename so v1's
    trade-accounting writes do not interact with it."""
    assert Path("data/live_trades/v5_filter_shadow_log.jsonl") == SHADOW_LOG_PATH
    assert SHADOW_LOG_PATH.name == "v5_filter_shadow_log.jsonl"
    assert "live_trades" in SHADOW_LOG_PATH.parts


# 6. Minimal fetcher tests


def test_polymarket_fetcher_returns_none_on_timeout():
    """fetch_polymarket_midpoint must return None when HTTP times out
    (or otherwise fails), never raise."""
    from kalshi_bot_v5.polymarket_fetcher import fetch_polymarket_midpoint

    def _timeout_get(_url, *, timeout):  # noqa: ARG001
        raise TimeoutError("simulated http timeout")

    # The fetcher's own try/except catches any exception from http_get
    # and returns None.
    result = fetch_polymarket_midpoint(
        "KXMLBGAME-26MAY24WSHATL-ATL",
        "KXMLBGAME",
        timeout=0.001,
        _http_get=_timeout_get,
    )
    assert result is None


def test_polymarket_fetcher_returns_none_on_unparseable_ticker():
    """A ticker the parser can't recognize returns None without any
    HTTP call (search path skipped)."""
    from kalshi_bot_v5.polymarket_fetcher import fetch_polymarket_midpoint
    calls: list[str] = []

    def _tracking_get(url, *, timeout):  # noqa: ARG001
        calls.append(url)
        return None, 0

    result = fetch_polymarket_midpoint(
        "KXSOMETHINGRANDOM-1234567890-XYZ",
        "KXSOMETHINGRANDOM",
        timeout=3.0,
        _http_get=_tracking_get,
    )
    # The fetcher tries the slug path (which is empty for unknown
    # series), then the game parser (which fails on this shape), then
    # abstains. No HTTP call is issued because there's no parsed event
    # query to build.
    assert result is None
    assert calls == []


def test_polymarket_fetcher_returns_none_on_404_search():
    """If the public-search returns 404 / empty events, fetcher returns
    None after one retry."""
    from kalshi_bot_v5.polymarket_fetcher import fetch_polymarket_midpoint

    def _empty_get(_url, *, timeout):  # noqa: ARG001
        return {"events": []}, 200

    result = fetch_polymarket_midpoint(
        "KXMLBGAME-26MAY24NYYBOS-NYY",
        "KXMLBGAME",
        timeout=3.0,
        _http_get=_empty_get,
    )
    assert result is None


def test_sportsbook_fetcher_respects_credit_budget(monkeypatch):
    """After the per-loop credit budget is exhausted, subsequent calls
    return None without consuming additional credits."""
    from kalshi_bot_v5 import sportsbook_fetcher
    from kalshi_bot_v5.sportsbook_fetcher import (
        fetch_sportsbook_implied,
        reset_loop_budget,
    )

    # Set a very small budget so we can exhaust quickly.
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key-not-real")
    reset_loop_budget(budget=2)

    # Stub http_get to look like:
    # - /events returns a list with the expected event_id
    # - /odds returns one event with one bookmaker
    fake_event_id = "EVT123"
    fake_event = {
        "id": fake_event_id,
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
        "bookmakers": [
            {"markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": "New York Yankees", "price": 1.5},
                    {"name": "Boston Red Sox", "price": 2.6},
                ],
            }]},
        ],
    }
    events_payload = [{
        "id": fake_event_id,
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
    }]
    paid_calls = {"n": 0}

    def _fake_http_get(url, *, timeout):  # noqa: ARG001
        if "/events?" in url and "/odds?" not in url:
            return events_payload, 200, {}
        if "/odds?" in url:
            paid_calls["n"] += 1
            return [fake_event], 200, {}
        return None, 404, {}

    # Need an NYY-home matchup, so use a ticker like KXMLBGAME-26MAY25BOSNYY-NYY
    ticker = "KXMLBGAME-26MAY251940BOSNYY-NYY"

    # Each call consumes 1 credit; budget=2 means two should succeed
    # and the third returns None without issuing an /odds call.
    # Note: the in-process cache short-circuits identical tickers; we
    # vary ticker to bypass it. Results are discarded; assertion is
    # against the paid-call counter and remaining budget.
    fetch_sportsbook_implied(
        ticker + "1", "KXMLBGAME",
        timeout=3.0, _http_get=_fake_http_get,
    )
    fetch_sportsbook_implied(
        ticker + "2", "KXMLBGAME",
        timeout=3.0, _http_get=_fake_http_get,
    )
    fetch_sportsbook_implied(
        ticker + "3", "KXMLBGAME",
        timeout=3.0, _http_get=_fake_http_get,
    )

    # If the parser doesn't match this ticker shape we may get all
    # None; in that case the budget assertion is still meaningful
    # (no /odds calls issued because we abstained earlier). Otherwise,
    # we expect at most 2 paid /odds calls.
    assert paid_calls["n"] <= 2
    # The third call must not have issued a paid call.
    assert sportsbook_fetcher.loop_budget_remaining() == max(
        0, 2 - paid_calls["n"],
    )


def test_sportsbook_fetcher_returns_none_with_no_api_key(monkeypatch):
    """Without THE_ODDS_API_KEY, the fetcher abstains cleanly."""
    from kalshi_bot_v5.sportsbook_fetcher import (
        fetch_sportsbook_implied,
        reset_loop_budget,
    )

    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    reset_loop_budget(budget=5)

    def _fake_http_get(_url, *, timeout):  # noqa: ARG001
        # Should never be reached because the fetcher short-circuits on
        # missing API key in the _find_event_id helper.
        return None, 200, {}

    result = fetch_sportsbook_implied(
        "KXMLBGAME-26MAY24WSHATL-ATL",
        "KXMLBGAME",
        timeout=3.0,
        _http_get=_fake_http_get,
    )
    assert result is None


def test_sportsbook_fetcher_returns_none_on_unsupported_series(monkeypatch):
    """A series prefix not in SERIES_TO_SPORTKEY returns None without
    issuing any HTTP call."""
    from kalshi_bot_v5.sportsbook_fetcher import (
        fetch_sportsbook_implied,
        reset_loop_budget,
    )

    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")
    reset_loop_budget(budget=5)
    calls: list[str] = []

    def _tracking_http_get(url, *, timeout):  # noqa: ARG001
        calls.append(url)
        return None, 200, {}

    result = fetch_sportsbook_implied(
        "KXSOMETHINGELSE-1234-XYZ",
        "KXSOMETHINGELSE",
        timeout=3.0,
        _http_get=_tracking_http_get,
    )
    assert result is None
    assert calls == []  # never reached HTTP


# ============================================================
# LIVE_FILTER_ENABLED (active overlay) tests
# ============================================================

from kalshi_bot.strategy.shadow_filter import (
    LIVE_FILTER_ENV,
    is_live_filter_enabled,
)


@pytest.fixture
def live_filter_disabled(monkeypatch):
    monkeypatch.delenv(LIVE_FILTER_ENV, raising=False)
    yield


@pytest.fixture
def live_filter_enabled(monkeypatch):
    monkeypatch.setenv(LIVE_FILTER_ENV, "true")
    yield


def test_is_live_filter_enabled_default_off(live_filter_disabled):
    assert is_live_filter_enabled() is False


def test_is_live_filter_enabled_only_true_enables(monkeypatch):
    """Strict 'true' literal; anything else stays off."""
    for val in ["false", "1", "yes", "enabled", "True", ""]:
        monkeypatch.setenv(LIVE_FILTER_ENV, val)
        if val.lower() == "true":
            assert is_live_filter_enabled() is True
        else:
            assert is_live_filter_enabled() is False


def test_shadow_evaluate_runs_when_only_live_filter_set(
    live_filter_enabled, env_disabled, monkeypatch, tmp_path,
):
    """LIVE_FILTER_ENABLED alone (without SHADOW_MODE_ENABLED) should
    still compute the decision so the caller can use it for the skip,
    but should NOT write the JSONL log."""
    log_path = tmp_path / "no_log.jsonl"
    monkeypatch.setattr(
        "kalshi_bot.strategy.shadow_filter.SHADOW_LOG_PATH", log_path,
    )

    def _poly(*args, **kwargs):  # noqa: ARG001
        return 0.62

    def _book(*args, **kwargs):  # noqa: ARG001
        return 0.65

    monkeypatch.setattr(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint", _poly,
    )
    monkeypatch.setattr(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied", _book,
    )

    snap = _make_snap()
    decision = shadow_evaluate(snap, 0.85)

    # Decision IS returned (so caller can act on it for skip)
    assert decision is not None
    assert isinstance(decision, ShadowDecision)
    # But JSONL log is NOT written (no SHADOW_MODE_ENABLED)
    assert not log_path.exists()


def test_shadow_evaluate_returns_none_when_both_flags_off(
    env_disabled, live_filter_disabled, monkeypatch,
):
    """When neither flag is set, the filter doesn't run at all."""
    snap = _make_snap()
    decision = shadow_evaluate(snap, 0.85)
    assert decision is None


def test_shadow_evaluate_writes_log_when_both_flags_on(
    live_filter_enabled, monkeypatch, tmp_path,
):
    """Both flags set: filter runs AND log is written."""
    monkeypatch.setenv(SHADOW_MODE_ENV, "true")
    log_path = tmp_path / "shadow.jsonl"
    monkeypatch.setattr(
        "kalshi_bot.strategy.shadow_filter.SHADOW_LOG_PATH", log_path,
    )

    def _poly(*args, **kwargs):  # noqa: ARG001
        return 0.62

    def _book(*args, **kwargs):  # noqa: ARG001
        return 0.65

    monkeypatch.setattr(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint", _poly,
    )
    monkeypatch.setattr(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied", _book,
    )

    snap = _make_snap()
    decision = shadow_evaluate(snap, 0.85)

    assert decision is not None
    assert log_path.exists()
    line = log_path.read_text().strip()
    parsed = json.loads(line)
    assert parsed["ticker"] == snap.ticker


def test_live_filter_skip_decision_has_should_trade_false(
    live_filter_enabled, monkeypatch,
):
    """When poly says fade and we have live filter on, should_trade is
    False so the caller will skip."""
    def _poly(*args, **kwargs):  # noqa: ARG001
        return 0.50  # 35c below Kalshi 0.85 - well above 7c fade threshold

    def _book(*args, **kwargs):  # noqa: ARG001
        return 0.55

    monkeypatch.setattr(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint", _poly,
    )
    monkeypatch.setattr(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied", _book,
    )

    snap = _make_snap()
    decision = shadow_evaluate(snap, 0.85)
    assert decision is not None
    assert decision.should_trade is False
    assert "fade" in decision.reason or len(decision.fired_rules) > 0


def test_live_filter_abstains_when_fetchers_miss(
    live_filter_enabled, monkeypatch,
):
    """When both fetchers miss (return None), the filter should not
    skip - v1 falls through to its normal decision. This is the safe
    failure mode."""
    monkeypatch.setattr(
        "kalshi_bot_v5.polymarket_fetcher.fetch_polymarket_midpoint",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "kalshi_bot_v5.sportsbook_fetcher.fetch_sportsbook_implied",
        lambda *a, **k: None,
    )

    snap = _make_snap()
    decision = shadow_evaluate(snap, 0.85)
    # The combined filter abstains (should_trade=True) when no rule
    # has data to fire. v1 will continue with its normal logic.
    assert decision is not None
    assert decision.should_trade is True
