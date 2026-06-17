"""Tests for live-mode pre-flight checklist."""

from __future__ import annotations

import email.utils
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from kalshi_bot.config import Settings
from kalshi_bot.strategy.live_order_manager import LiveOrderManager
from kalshi_bot.strategy.order_manager import OrderStatus, PaperOrderManager
from kalshi_bot.strategy.preflight import (
    PreflightFailureError,
    check_acceptance_criteria,
    check_balance,
    check_capital_cap,
    check_clock_skew,
    check_kalshi_env,
    check_live_enabled,
    check_no_orphan_resting,
    check_per_trade_size,
    check_trading_active,
    compute_acceptance_metrics,
    run_preflight,
)


class MockKalshiClient:
    """Mock with prestaged responses and pluggable Date header."""

    def __init__(self, server_dt: datetime | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.server_dt = server_dt or datetime.now(UTC)
        self.get_responses: list[dict[str, Any]] = []
        self.get_raises: list[Exception | None] = []
        self.paginate_responses: list[list[dict[str, Any]]] = []
        self.paginate_raises: list[Exception | None] = []

    def get_response_date_header(self) -> str | None:
        return email.utils.format_datetime(self.server_dt, usegmt=True)

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        self.calls.append(("GET", endpoint, dict(params)))
        exc = self.get_raises.pop(0) if self.get_raises else None
        if exc is not None:
            raise exc
        if not self.get_responses:
            raise AssertionError("no canned GET response staged")
        return self.get_responses.pop(0)

    def paginate(
        self, endpoint: str, *, item_key: str, **params: Any,
    ) -> Iterator[dict[str, Any]]:
        self.calls.append(("PAGINATE", endpoint, {"item_key": item_key, **params}))
        exc = self.paginate_raises.pop(0) if self.paginate_raises else None
        if exc is not None:
            raise exc
        if not self.paginate_responses:
            return iter([])
        return iter(self.paginate_responses.pop(0))


@pytest.fixture
def tmp_state_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def _make_settings(**overrides: Any) -> Settings:
    """Build a Settings with safe defaults for testing, ignoring .env."""
    defaults = {
        "LIVE_ENABLED": True,
        "LIVE_OVERRIDE_GATE": False,
        "LIVE_PER_TRADE_USD": 0.95,
        "LIVE_MAX_OPEN_POSITIONS": 5,
        "LIVE_MAX_CLOCK_SKEW_MS": 2000,
        "CAPITAL_CAP_USD": 25.0,
        "KALSHI_ENV": "prod",
        "ACCEPT_MIN_PAPER_FILLS": 50,
        "ACCEPT_MIN_LEAGUES": 3,
        "ACCEPT_MIN_YES_RATE": 0.90,
        "ACCEPT_MIN_MEAN_PNL_PP": 1.0,
        "ACCEPT_MIN_FILL_RATE": 0.40,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_check_live_enabled_passes_when_true() -> None:
    s = _make_settings(LIVE_ENABLED=True)
    assert check_live_enabled(s).passed is True


def test_check_live_enabled_fails_when_false() -> None:
    s = _make_settings(LIVE_ENABLED=False)
    assert check_live_enabled(s).passed is False


def test_check_kalshi_env_fails_on_mismatch() -> None:
    s = _make_settings(KALSHI_ENV="demo")
    assert check_kalshi_env(s, expected="prod").passed is False


def test_check_kalshi_env_allows_demo_when_expected() -> None:
    s = _make_settings(KALSHI_ENV="demo")
    assert check_kalshi_env(s, expected="demo").passed is True


def test_check_capital_cap_passes_at_default() -> None:
    s = _make_settings(CAPITAL_CAP_USD=25.0)
    assert check_capital_cap(s).passed is True


def test_check_capital_cap_no_ceiling_above_100() -> None:
    # 2026-06-16: the $100 ceiling was removed per operator; the config accepts
    # any non-negative value and the preflight check is informational (passes).
    s = _make_settings(CAPITAL_CAP_USD=1000.0)
    assert check_capital_cap(s).passed is True


def test_check_per_trade_size_fails_below_upper_cap() -> None:
    s = _make_settings(LIVE_PER_TRADE_USD=0.50)
    r = check_per_trade_size(s)
    assert r.passed is False
    assert "0.50" in r.detail


def test_check_per_trade_size_passes_at_upper_cap() -> None:
    s = _make_settings(LIVE_PER_TRADE_USD=0.95)
    assert check_per_trade_size(s).passed is True


def test_check_clock_skew_passes_when_within_tolerance() -> None:
    server = datetime.now(UTC)
    client = MockKalshiClient(server_dt=server)
    assert check_clock_skew(client, 2000).passed is True


def test_check_clock_skew_fails_when_drift_exceeds() -> None:
    server = datetime.now(UTC) - timedelta(seconds=10)
    client = MockKalshiClient(server_dt=server)
    r = check_clock_skew(client, 2000)
    assert r.passed is False
    assert "ms" in r.detail


def test_check_trading_active_passes() -> None:
    client = MockKalshiClient()
    client.get_responses.append({"trading_active": True, "exchange_active": True})
    assert check_trading_active(client).passed is True


def test_check_trading_active_fails_when_inactive() -> None:
    client = MockKalshiClient()
    client.get_responses.append({"trading_active": False})
    assert check_trading_active(client).passed is False


def test_check_balance_passes_above_floor() -> None:
    client = MockKalshiClient()
    client.get_responses.append({"balance": 3200})  # $32.00 in cents
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=5)
    assert r.passed is True


def test_check_balance_fails_below_floor() -> None:
    client = MockKalshiClient()
    client.get_responses.append({"balance": 50})  # $0.50 in cents
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=5)
    assert r.passed is False
    assert "balance" in r.detail


def test_check_balance_handles_fetch_failure() -> None:
    client = MockKalshiClient()
    client.get_raises.append(RuntimeError("403 Forbidden"))
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=5)
    assert r.passed is False
    assert "scope" in r.detail.lower() or "auth" in r.detail.lower()


def test_check_balance_default_multiplier_is_1x(monkeypatch) -> None:
    """Default multiplier is 1.0 (not 2.0). Capacity is capped at
    PREFLIGHT_MAX_NEW_ORDERS (8), so for max_concurrent >= 8 the floor is
    1.0 * 0.95 * 8 = $7.60. Balance $10 passes at 1x but would fail at 2x
    ($15.20), so passing confirms the default is 1x. (research/v20 cap)
    """
    monkeypatch.delenv("BALANCE_PREFLIGHT_MULTIPLIER", raising=False)
    client = MockKalshiClient()
    client.get_responses.append({"balance": 1000})  # $10.00
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=27)
    assert r.passed is True
    assert "7.60" in r.detail


def test_check_balance_env_override_to_2x(monkeypatch) -> None:
    """BALANCE_PREFLIGHT_MULTIPLIER=2.0 doubles the floor. Capped capacity 8 ->
    2.0 * 0.95 * 8 = $15.20; balance $10 fails.
    """
    monkeypatch.setenv("BALANCE_PREFLIGHT_MULTIPLIER", "2.0")
    client = MockKalshiClient()
    client.get_responses.append({"balance": 1000})  # $10.00
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=27)
    assert r.passed is False
    assert "15.20" in r.detail


def test_check_balance_env_invalid_value_falls_back_to_default(monkeypatch) -> None:
    """A garbage env value (non-numeric, zero, negative) uses the
    1.0 default; the bot doesn't get stuck on a typo."""
    for bad in ["abc", "0", "-1.0", ""]:
        monkeypatch.setenv("BALANCE_PREFLIGHT_MULTIPLIER", bad)
        client = MockKalshiClient()
        client.get_responses.append({"balance": 2846})
        s = _make_settings()
        r = check_balance(client, s, max_concurrent=27)
        assert r.passed is True, f"value {bad!r} should fall back to default"


def test_check_balance_multiplier_buffer_below_floor(monkeypatch) -> None:
    """Balance below the capped 1x floor ($7.60) still fails."""
    monkeypatch.setenv("BALANCE_PREFLIGHT_MULTIPLIER", "1.0")
    client = MockKalshiClient()
    client.get_responses.append({"balance": 500})  # $5.00 < $7.60
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=27)
    assert r.passed is False


def test_check_balance_caps_capacity_unblocks_restart(monkeypatch) -> None:
    """research/v20 regression: the operator's live crash-loop. max_concurrent
    57 (from total bankroll) with 20 open positions = 37 free slots. UNCAPPED
    that required 1.0 * 0.95 * 37 = $35.15 and blocked restart at $34.09 cash.
    Capped at 8 it needs only $7.60, so $34.09 passes and the bot can start."""
    monkeypatch.delenv("BALANCE_PREFLIGHT_MULTIPLIER", raising=False)
    client = MockKalshiClient()
    client.get_responses.append({"balance": 3409})  # $34.09 cash
    s = _make_settings()
    r = check_balance(client, s, max_concurrent=57, currently_open=20)
    assert r.passed is True
    assert "7.60" in r.detail and "8 funded" in r.detail


def _seed_paper_state(paper: PaperOrderManager, *, settled: list[dict]) -> None:
    """Populate closed_orders directly for acceptance-criteria tests."""
    from kalshi_bot.strategy.order_manager import PaperOrder
    for i, item in enumerate(settled):
        order = PaperOrder(
            order_id=f"paper-{i}",
            ticker=item.get("ticker", "KXMLBWINS-NYY-26"),
            series_ticker=item.get("series_ticker", "KXMLBWINS"),
            event_ticker=item.get("event_ticker", "KXMLBWINS-NYY-26"),
            side="yes",
            target_price=0.75,
            contracts=1,
            expected_net_edge=0.05,
            recalibrated_prob=0.95,
            market_mid_at_placement=0.75,
            placed_ts="2026-01-01T00:00:00Z",
            status=OrderStatus.PAPER_FILLED,
            filled_ts="2026-01-02T00:00:00Z",
            filled_price=0.75,
            resolution_ts="2026-02-01T00:00:00Z",
            resolution_outcome=item["outcome"],
            realized_pnl_usd=item["pnl_usd"],
        )
        paper.state.closed_orders[order.order_id] = order
    paper._save()  # noqa: SLF001


def test_acceptance_criteria_passes_when_all_met(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    # Build a state with 50 fills across 3 leagues, 95% YES, mean ~+2pp.
    items = []
    leagues_cycle = [
        ("KXMLBWINS", "KXMLBWINS-NYY-26"),
        ("KXNFL", "KXNFL-GB-26"),
        ("KXNBA", "KXNBA-LAL-26"),
    ]
    for i in range(50):
        league_ticker, event_ticker = leagues_cycle[i % 3]
        outcome = 1 if i < 47 else 0  # 47/50 YES = 94%
        # Realistic P&L: YES wins +$0.20 net, YES loses -$0.30 net (per
        # contract). Mean ~+14pp, easily above 1pp acceptance.
        pnl = 0.20 if outcome == 1 else -0.30
        items.append({
            "series_ticker": league_ticker,
            "ticker": f"{event_ticker}-{i}",
            "event_ticker": event_ticker,
            "outcome": outcome,
            "pnl_usd": pnl,
        })
    _seed_paper_state(paper, settled=items)
    paper.state.placement_attempts_total = 100  # 50% fill rate
    paper._save()  # noqa: SLF001
    s = _make_settings()
    r = check_acceptance_criteria(paper, s)
    assert r.passed is True


def test_acceptance_criteria_fails_on_too_few_fills(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    _seed_paper_state(paper, settled=[
        {"outcome": 1, "pnl_usd": 0.02, "series_ticker": "KXNBA"},
        {"outcome": 1, "pnl_usd": 0.02, "series_ticker": "KXNFL"},
        {"outcome": 1, "pnl_usd": 0.02, "series_ticker": "KXMLBWINS"},
    ])
    paper.state.placement_attempts_total = 10
    paper._save()  # noqa: SLF001
    s = _make_settings()
    r = check_acceptance_criteria(paper, s)
    assert r.passed is False
    assert "fills" in r.detail


def test_acceptance_criteria_fails_on_too_few_leagues(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    items = []
    for i in range(50):
        # Only NBA league
        items.append({
            "series_ticker": "KXNBA",
            "ticker": f"KXNBA-LAL-26-{i}",
            "event_ticker": "KXNBA-LAL-26",
            "outcome": 1,
            "pnl_usd": 0.02,
        })
    _seed_paper_state(paper, settled=items)
    paper.state.placement_attempts_total = 100
    paper._save()  # noqa: SLF001
    s = _make_settings()
    r = check_acceptance_criteria(paper, s)
    assert r.passed is False
    assert "leagues" in r.detail.lower()


def test_acceptance_criteria_override_passes_with_failures(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    _seed_paper_state(paper, settled=[
        {"outcome": 1, "pnl_usd": 0.02, "series_ticker": "KXNBA"},
    ])
    paper.state.placement_attempts_total = 5
    paper._save()  # noqa: SLF001
    s = _make_settings(LIVE_OVERRIDE_GATE=True)
    r = check_acceptance_criteria(paper, s)
    assert r.passed is True
    assert "OVERRIDE" in r.detail


def test_compute_acceptance_metrics_no_fills(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    m = compute_acceptance_metrics(paper)
    assert m.settled_count == 0
    assert m.fill_rate is None


def test_check_no_orphan_resting_passes_when_clean(tmp_state_path: Path) -> None:
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")  # noqa: F841
    client = MockKalshiClient()
    client.paginate_responses.append([])  # no resting on Kalshi
    live = LiveOrderManager(client=client, state_path=tmp_state_path / "live.json")
    r = check_no_orphan_resting(client, live)
    assert r.passed is True


def test_check_no_orphan_resting_fails_with_unknown_order(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.paginate_responses.append([
        {"order_id": "kalshi-orphan-1",
         "client_order_id": "unknown-intent-x",
         "ticker": "KXNBA-LAL-26"},
    ])
    live = LiveOrderManager(client=client, state_path=tmp_state_path / "live.json")
    r = check_no_orphan_resting(client, live)
    assert r.passed is False


def test_run_preflight_raises_on_first_failure(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    live = LiveOrderManager(client=client, state_path=tmp_state_path / "live.json")
    s = _make_settings(LIVE_ENABLED=False)
    with pytest.raises(PreflightFailureError):
        run_preflight(
            settings=s, client=client, paper=paper, live=live,
            expected_env="prod", max_concurrent=5,
        )


def test_run_preflight_skip_balance_and_acceptance_for_demo(tmp_state_path: Path) -> None:
    """live-demo mode: skip balance + acceptance, still enforce LIVE_ENABLED
    + clock skew + trading active + orphan-free."""
    client = MockKalshiClient()
    client.get_responses.append({"trading_active": True})
    client.paginate_responses.append([])
    paper = PaperOrderManager(state_path=tmp_state_path / "paper.json")
    live = LiveOrderManager(client=client, state_path=tmp_state_path / "live.json")
    s = _make_settings(KALSHI_ENV="demo")
    results = run_preflight(
        settings=s, client=client, paper=paper, live=live,
        expected_env="demo", max_concurrent=5,
        skip_acceptance=True, skip_balance=True,
    )
    assert all(r.passed for r in results)
    # Verify the skipped checks were NOT in the list.
    names = {r.name for r in results}
    assert "balance" not in names
    assert "acceptance_criteria" not in names


# ============================================================
# check_clock_skew retry behavior
# ============================================================

def test_check_clock_skew_retries_transient_dns_failure() -> None:
    """A transient DNS error on the first attempt should NOT fail
    preflight; the check retries with backoff and succeeds when the
    network comes up."""
    client = MockKalshiClient()
    # Patch the method to raise once then return a Date header.
    call_count = {"n": 0}
    real_date_header = lambda: email.utils.format_datetime(datetime.now(UTC))
    def flaky_get_response_date_header():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("[Errno 11001] getaddrinfo failed")
        return real_date_header()
    client.get_response_date_header = flaky_get_response_date_header
    r = check_clock_skew(client, max_skew_ms=5000, retries=3, initial_backoff_s=0.01)
    assert r.passed is True
    assert call_count["n"] == 2


def test_check_clock_skew_does_not_retry_permanent_failure() -> None:
    """A permanent (non-transient) error should fail immediately without
    burning retries."""
    client = MockKalshiClient()
    call_count = {"n": 0}
    def always_fails():
        call_count["n"] += 1
        raise RuntimeError("HTTP 403 Forbidden")
    client.get_response_date_header = always_fails
    r = check_clock_skew(client, max_skew_ms=5000, retries=3, initial_backoff_s=0.01)
    assert r.passed is False
    # Only 1 attempt because the error message doesn't match a transient marker.
    assert call_count["n"] == 1


def test_check_clock_skew_gives_up_after_max_retries() -> None:
    """Persistent transient failures exhaust retries and then fail clearly."""
    client = MockKalshiClient()
    call_count = {"n": 0}
    def always_dns_fails():
        call_count["n"] += 1
        raise OSError("[Errno 11001] getaddrinfo failed")
    client.get_response_date_header = always_dns_fails
    r = check_clock_skew(client, max_skew_ms=5000, retries=3, initial_backoff_s=0.01)
    assert r.passed is False
    assert "after 3 attempts" in r.detail
    assert call_count["n"] == 3


# Need this import for the test above
import email.utils
