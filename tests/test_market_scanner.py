"""Tests for the live market scanner."""

from __future__ import annotations

import pandas as pd

from kalshi_bot.strategy.market_scanner import (
    DEFAULT_SERIES_DENYLIST,
    EXPANDED_SERIES_DENYLIST,
    PERSIST_SERIES_ALLOWLIST,
    ScannerConfig,
    extract_series_prefix,
    filter_candidates,
    parse_snapshot,
)


def _raw_market(
    ticker: str = "KXTEST-1",
    yes_bid: str = "0.30",
    yes_ask: str = "0.32",
    volume: str = "100.0",
    open_offset_days: int = 60,
    close_offset_days: int = 0,
    status: str = "open",
) -> dict:
    open_t = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=open_offset_days)
    close_t = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=close_offset_days)
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "series_ticker": "KXTEST",
        "yes_bid_dollars": yes_bid,
        "yes_ask_dollars": yes_ask,
        "last_price_dollars": yes_bid,
        "volume_fp": volume,
        "open_time": open_t.isoformat(),
        "close_time": close_t.isoformat(),
        "status": status,
        "title": "test market",
    }


def test_parse_snapshot_basic() -> None:
    raw = _raw_market()
    snap = parse_snapshot(raw)
    assert snap is not None
    assert snap.ticker == "KXTEST-1"
    assert snap.yes_bid == 0.30
    assert snap.yes_ask == 0.32


def test_parse_snapshot_handles_missing_ticker() -> None:
    raw = _raw_market()
    raw["ticker"] = ""
    assert parse_snapshot(raw) is None


def test_filter_candidates_mid_band() -> None:
    cfg = ScannerConfig(category="Politics", min_lifetime_days=30)
    raws = [
        _raw_market(ticker="KX-A", yes_bid="0.10", yes_ask="0.12"),  # below mid band
        _raw_market(ticker="KX-B", yes_bid="0.30", yes_ask="0.32"),  # in lower band
        _raw_market(ticker="KX-C", yes_bid="0.50", yes_ask="0.52"),  # dead zone
        _raw_market(ticker="KX-D", yes_bid="0.70", yes_ask="0.72"),  # in upper band
        _raw_market(ticker="KX-E", yes_bid="0.90", yes_ask="0.92"),  # above mid band
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-A" not in tickers
    assert "KX-B" in tickers
    assert "KX-C" not in tickers
    assert "KX-D" in tickers
    assert "KX-E" not in tickers


def test_filter_candidates_lifetime() -> None:
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raws = [
        _raw_market(ticker="KX-short", open_offset_days=20, close_offset_days=5),  # 25 days
        _raw_market(ticker="KX-long", open_offset_days=60, close_offset_days=30),  # 90 days
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-short" not in tickers
    assert "KX-long" in tickers


def test_filter_candidates_volume() -> None:
    cfg = ScannerConfig(category="Politics", min_lifetime_days=30, min_volume=100.0)
    raws = [
        _raw_market(ticker="KX-thin", volume="50.0"),
        _raw_market(ticker="KX-thick", volume="500.0"),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-thin" not in tickers
    assert "KX-thick" in tickers


def test_filter_candidates_status() -> None:
    cfg = ScannerConfig(category="Politics", min_lifetime_days=30)
    raws = [
        _raw_market(ticker="KX-open", status="open"),
        _raw_market(ticker="KX-closed", status="settled"),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-open" in tickers
    assert "KX-closed" not in tickers


def test_filter_candidates_handles_degenerate_orderbook() -> None:
    cfg = ScannerConfig(category="Politics", min_lifetime_days=30)
    raws = [
        _raw_market(ticker="KX-zero-bid", yes_bid="0.0", yes_ask="0.40"),
        _raw_market(ticker="KX-normal", yes_bid="0.30", yes_ask="0.40"),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-zero-bid" not in tickers
    assert "KX-normal" in tickers


def test_filter_candidates_max_lifetime_excludes_long_horizon() -> None:
    """research/time-scale-analysis.md: cap at 180d to avoid the
    catastrophic-tail bucket. Test that markets with total lifetime
    above the cap are excluded."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=30, max_lifetime_days=180,
    )
    raws = [
        # short market: 60d open + 30d to close = 90d lifetime, passes
        _raw_market(ticker="KX-short", open_offset_days=60, close_offset_days=30),
        # long market: 200d open + 200d to close = 400d lifetime, excluded
        _raw_market(ticker="KX-long", open_offset_days=200, close_offset_days=200),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-short" in tickers
    assert "KX-long" not in tickers


def test_filter_candidates_max_lifetime_none_keeps_long_horizon() -> None:
    """max_lifetime_days=None disables the filter; long markets pass."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=30, max_lifetime_days=None,
    )
    raws = [
        _raw_market(ticker="KX-long", open_offset_days=200, close_offset_days=200),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-long" in tickers


def test_filter_candidates_max_lifetime_boundary() -> None:
    """Cap is inclusive on the upper side: lifetime == max passes,
    lifetime == max+1 excluded."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=30, max_lifetime_days=180,
    )
    raws = [
        # 180d exactly (90 + 90): passes
        _raw_market(ticker="KX-180", open_offset_days=90, close_offset_days=90),
        # 181d (90 + 91): excluded
        _raw_market(ticker="KX-181", open_offset_days=90, close_offset_days=91),
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KX-180" in tickers
    assert "KX-181" not in tickers


# ---------- W1 series denylist tests (v4 V4-H closure) ----------

def test_extract_series_prefix_from_series_ticker() -> None:
    """When the API returns series_ticker, use it directly."""
    assert extract_series_prefix("KXNFLWINS-SEA-25B-T8", "KXNFLWINS") == "KXNFLWINS"


def test_extract_series_prefix_fallback_to_ticker_head() -> None:
    """When series_ticker is empty (as Kalshi sometimes returns), derive
    the prefix from the substring before the first dash."""
    assert extract_series_prefix("KXNFLWINS-SEA-25B-T8", "") == "KXNFLWINS"
    assert extract_series_prefix("KXMLBPLAYOFFS-25-NYM", "") == "KXMLBPLAYOFFS"


def test_extract_series_prefix_empty_inputs() -> None:
    assert extract_series_prefix("", "") == ""
    assert extract_series_prefix("KXNOSEP", "") == "KXNOSEP"


def test_default_series_denylist_contains_v4_h_finding() -> None:
    """The default denylist must contain the three series V4-H stress
    tested where v1's measured edge does NOT generalize."""
    assert "KXNFLWINS" in DEFAULT_SERIES_DENYLIST
    assert "KXNFLPLAYOFF" in DEFAULT_SERIES_DENYLIST
    assert "KXMLBPLAYOFFS" in DEFAULT_SERIES_DENYLIST


def test_default_denylist_contains_low_fill_series() -> None:
    """2026-05-30 fill-efficiency denylist: the proven never-fill series must
    be excluded by default so v1 stops wasting bids on them."""
    from kalshi_bot.strategy.market_scanner import LOW_FILL_DENYLIST
    for prefix in ("KXWCGAME", "KXUFCFIGHT", "KXPGAMAKECUT"):
        assert prefix in LOW_FILL_DENYLIST
        assert prefix in DEFAULT_SERIES_DENYLIST


def test_filter_candidates_denies_low_fill_series() -> None:
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raws = [
        {**_raw_market(ticker="KXWCGAME-26-ARG", yes_bid="0.78", yes_ask="0.80"),
         "series_ticker": "KXWCGAME"},
        {**_raw_market(ticker="KXNBAWINS-LAL-26-T55", yes_bid="0.75", yes_ask="0.77"),
         "series_ticker": "KXNBAWINS"},
    ]
    tickers = [snap.ticker for _, snap in filter_candidates(raws, cfg)]
    assert "KXWCGAME-26-ARG" not in tickers


def test_filter_candidates_denies_kxnflwins() -> None:
    """Default ScannerConfig must skip KXNFLWINS markets (W1 closure)."""
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raws = [
        # In v1's eligible band but denylisted series: must be excluded
        {**_raw_market(ticker="KXNFLWINS-SEA-25B-T8", yes_bid="0.85", yes_ask="0.87"),
         "series_ticker": "KXNFLWINS"},
        # In v1's eligible band, allowed series: must pass
        {**_raw_market(ticker="KXNBAWINS-LAL-26-T55", yes_bid="0.75", yes_ask="0.77"),
         "series_ticker": "KXNBAWINS"},
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KXNFLWINS-SEA-25B-T8" not in tickers
    assert "KXNBAWINS-LAL-26-T55" in tickers


def test_filter_candidates_denies_kxnflplayoff_and_kxmlbplayoffs() -> None:
    """All three default-denied series are excluded by default."""
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raws = [
        {**_raw_market(ticker="KXNFLPLAYOFF-26-PIT", yes_bid="0.80", yes_ask="0.82"),
         "series_ticker": "KXNFLPLAYOFF"},
        {**_raw_market(ticker="KXMLBPLAYOFFS-25-NYM", yes_bid="0.74", yes_ask="0.76"),
         "series_ticker": "KXMLBPLAYOFFS"},
        {**_raw_market(ticker="KXMLBWINS-NYY-26-T90", yes_bid="0.78", yes_ask="0.80"),
         "series_ticker": "KXMLBWINS"},
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KXNFLPLAYOFF-26-PIT" not in tickers
    assert "KXMLBPLAYOFFS-25-NYM" not in tickers
    assert "KXMLBWINS-NYY-26-T90" in tickers


def test_filter_candidates_denylist_handles_empty_series_ticker() -> None:
    """Kalshi sometimes returns empty series_ticker on /markets; ensure
    we derive the prefix from the full ticker so the denylist still
    applies."""
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raws = [
        {**_raw_market(ticker="KXNFLWINS-SEA-25B-T8", yes_bid="0.85", yes_ask="0.87"),
         "series_ticker": ""},
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KXNFLWINS-SEA-25B-T8" not in tickers


def test_filter_candidates_denylist_can_be_overridden() -> None:
    """Operator-level override: empty denylist re-admits all series.

    Mid 0.76 falls inside the default upper band (0.55, 0.80) so the
    market only fails on denylist when the denylist is active.
    """
    cfg_default = ScannerConfig(category="Sports", min_lifetime_days=30)
    cfg_override = ScannerConfig(
        category="Sports", min_lifetime_days=30,
        series_denylist=frozenset(),
    )
    raw = {**_raw_market(ticker="KXNFLWINS-SEA-25B-T8", yes_bid="0.75", yes_ask="0.77"),
           "series_ticker": "KXNFLWINS"}
    # With default denylist: excluded
    candidates = filter_candidates([raw], cfg_default)
    assert "KXNFLWINS-SEA-25B-T8" not in [snap.ticker for _, snap in candidates]
    # With empty denylist override: re-admitted
    candidates = filter_candidates([raw], cfg_override)
    assert "KXNFLWINS-SEA-25B-T8" in [snap.ticker for _, snap in candidates]


# ---------- Round 15b: expanded denylist and PERSIST allowlist ----------

def test_expanded_denylist_includes_oos_null_prefixes() -> None:
    """The EXPANDED_SERIES_DENYLIST must include all OOS_NULL prefixes
    from the Becker post-Oct-2024 validation (research/v10a/12-v1-validation.json).
    """
    for prefix in DEFAULT_SERIES_DENYLIST:
        assert prefix in EXPANDED_SERIES_DENYLIST
    # New additions
    for prefix in [
        "KXNFLSPREAD", "KXNFLTOTAL",
        "KXMLBSPREAD", "KXMLBTOTAL", "KXMLBWINS",
        "KXNHLSPREAD",
        "KXNCAAFSPREAD", "KXNCAAFTOTAL",
        "KXNCAAMBTOTAL", "KXNCAAMBSPREAD",
        "KXEPLGAME", "KXUCLGAME",
    ]:
        assert prefix in EXPANDED_SERIES_DENYLIST, f"missing {prefix}"


def test_persist_allowlist_has_five_validated_prefixes() -> None:
    """The PERSIST_SERIES_ALLOWLIST is the five Round 15b validated prefixes."""
    assert PERSIST_SERIES_ALLOWLIST == frozenset({
        "KXMLBGAME", "KXATPMATCH", "KXNFLGAME", "KXNCAAFGAME", "KXWTAMATCH",
    })


def test_filter_candidates_allowlist_default_disabled() -> None:
    """When series_allowlist is None (default), all non-denied prefixes pass."""
    cfg = ScannerConfig(category="Sports", min_lifetime_days=30)
    raw = {**_raw_market(ticker="KXNHLGAME-26MAY28-PHI", yes_bid="0.75", yes_ask="0.77"),
           "series_ticker": "KXNHLGAME"}
    candidates = filter_candidates([raw], cfg)
    assert "KXNHLGAME-26MAY28-PHI" in [snap.ticker for _, snap in candidates]


def test_filter_candidates_allowlist_restricts_universe() -> None:
    """When series_allowlist is set, only those prefixes pass."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=30,
        series_allowlist=PERSIST_SERIES_ALLOWLIST,
    )
    raws = [
        # In allowlist: passes
        {**_raw_market(ticker="KXMLBGAME-26JUL01-NYY", yes_bid="0.75", yes_ask="0.77"),
         "series_ticker": "KXMLBGAME"},
        # In denylist + not in allowlist: excluded
        {**_raw_market(ticker="KXNHLGAME-26MAY28-PHI", yes_bid="0.75", yes_ask="0.77"),
         "series_ticker": "KXNHLGAME"},
        # In allowlist: passes (tennis match)
        {**_raw_market(ticker="KXATPMATCH-26JUN-ABC", yes_bid="0.70", yes_ask="0.72"),
         "series_ticker": "KXATPMATCH"},
    ]
    candidates = filter_candidates(raws, cfg)
    tickers = [snap.ticker for _, snap in candidates]
    assert "KXMLBGAME-26JUL01-NYY" in tickers
    assert "KXATPMATCH-26JUN-ABC" in tickers
    assert "KXNHLGAME-26MAY28-PHI" not in tickers


def test_filter_candidates_allowlist_overrides_denylist() -> None:
    """If a prefix is in BOTH denylist and allowlist, denylist wins (the
    denylist check is first in filter_candidates). Defensive coding: an
    operator should not configure overlapping sets."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=30,
        series_denylist=frozenset({"KXMLBGAME"}),
        series_allowlist=frozenset({"KXMLBGAME", "KXATPMATCH"}),
    )
    raw = {**_raw_market(ticker="KXMLBGAME-26JUL01-NYY", yes_bid="0.75", yes_ask="0.77"),
           "series_ticker": "KXMLBGAME"}
    candidates = filter_candidates([raw], cfg)
    assert "KXMLBGAME-26JUL01-NYY" not in [snap.ticker for _, snap in candidates]


def test_filter_candidates_min_minutes_to_close_skip_imminent() -> None:
    """Market closing in 30 minutes should be skipped if cutoff is 60 minutes."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=0,  # disable min-lifetime check
        min_minutes_to_close=60,
    )
    # close in 30 minutes from now
    close_t = pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=30)
    open_t = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
    raw = {
        "ticker": "KXMLBGAME-IMMINENT",
        "event_ticker": "KXMLBGAME-IMMINENT",
        "series_ticker": "KXMLBGAME",
        "yes_bid_dollars": "0.75",
        "yes_ask_dollars": "0.77",
        "last_price_dollars": "0.76",
        "volume_fp": "100.0",
        "open_time": open_t.isoformat(),
        "close_time": close_t.isoformat(),
        "status": "open",
        "title": "test",
    }
    candidates = filter_candidates([raw], cfg)
    assert "KXMLBGAME-IMMINENT" not in [snap.ticker for _, snap in candidates]


def test_filter_candidates_min_minutes_to_close_passes_distant() -> None:
    """Market closing in 24 hours should pass with cutoff at 60 minutes."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=0,
        min_minutes_to_close=60,
    )
    close_t = pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=24)
    open_t = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
    raw = {
        "ticker": "KXMLBGAME-DISTANT",
        "event_ticker": "KXMLBGAME-DISTANT",
        "series_ticker": "KXMLBGAME",
        "yes_bid_dollars": "0.75",
        "yes_ask_dollars": "0.77",
        "last_price_dollars": "0.76",
        "volume_fp": "100.0",
        "open_time": open_t.isoformat(),
        "close_time": close_t.isoformat(),
        "status": "open",
        "title": "test",
    }
    candidates = filter_candidates([raw], cfg)
    assert "KXMLBGAME-DISTANT" in [snap.ticker for _, snap in candidates]


def test_filter_candidates_min_minutes_to_close_disabled() -> None:
    """min_minutes_to_close=None disables the pre-close cutoff filter."""
    cfg = ScannerConfig(
        category="Sports", min_lifetime_days=0,
        min_minutes_to_close=None,
    )
    close_t = pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=10)
    open_t = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
    raw = {
        "ticker": "KXMLBGAME-IMMINENT",
        "event_ticker": "KXMLBGAME-IMMINENT",
        "series_ticker": "KXMLBGAME",
        "yes_bid_dollars": "0.75",
        "yes_ask_dollars": "0.77",
        "last_price_dollars": "0.76",
        "volume_fp": "100.0",
        "open_time": open_t.isoformat(),
        "close_time": close_t.isoformat(),
        "status": "open",
        "title": "test",
    }
    candidates = filter_candidates([raw], cfg)
    assert "KXMLBGAME-IMMINENT" in [snap.ticker for _, snap in candidates]
