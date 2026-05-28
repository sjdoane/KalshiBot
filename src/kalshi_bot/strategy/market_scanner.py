"""Live market scanner for the paper / live trading bot.

Polls Kalshi `/markets?status=open` for the configured category, filters
by the same Section 2.2 / Section 4 criteria the gate validated against,
and returns candidate market snapshots ready for pricing.decide().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd
import structlog

from kalshi_bot.strategy.pricing import MarketSnapshot

if TYPE_CHECKING:
    from kalshi_bot.data.kalshi_client import KalshiClient

log = structlog.get_logger(__name__)


# Series-prefix denylist (W1 closure, applied 2026-05-24 after v4 V4-H
# stress test). v1's claimed +12.47pp measured edge on
# data/processed/sports_dataset.parquet (n=39) did NOT generalize to
# KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS. V4-H rebuild on those series
# (research/v4/09-v1-stress-test.md): KXNFLWINS mean -1.03pp on n=95,
# KXNFLPLAYOFF -10.18pp on n=9, KXMLBPLAYOFFS -27.84pp on n=5. Aggregate
# -3.02pp with bootstrap CI [-9.73pp, +3.10pp] including zero. The
# original measurement excluded these series structurally; the live bot
# trades them via the full /series?category=Sports scan. Denylisting
# them removes the untested exposure pending W2 (re-measure v1's edge
# on the denylisted-residual universe).
DEFAULT_SERIES_DENYLIST: frozenset[str] = frozenset({
    "KXNFLWINS",
    "KXNFLPLAYOFF",
    "KXMLBPLAYOFFS",
})


# Round 15b extension (2026-05-27): Becker post-October-2024 cluster
# bootstrap on v1's exact regime (buy YES as maker at yes_price >= 0.70)
# showed these prefixes are OOS_NULL: train and/or OOS event-mean P&L is
# negative or includes zero with negative point estimate after Kalshi
# maker fees. Adding to the denylist prevents v1 from accumulating
# losses on prop / spread / total markets where favorite-longshot bias
# does NOT operate (sharper pricing, no retail YES-overbet structure).
# See research/v10a/12-v1-validation.json and TEST-AND-CONFIRM.md.
EXPANDED_SERIES_DENYLIST: frozenset[str] = DEFAULT_SERIES_DENYLIST | frozenset({
    # NFL props
    "KXNFLSPREAD",
    "KXNFLTOTAL",
    # MLB props (not game lines)
    "KXMLBSPREAD",
    "KXMLBTOTAL",
    "KXMLBWINS",  # also flagged in W2 v3-only CI watchlist
    # NHL props
    "KXNHLSPREAD",
    # NCAA football props
    "KXNCAAFSPREAD",
    "KXNCAAFTOTAL",
    # NCAA basketball props
    "KXNCAAMBTOTAL",
    "KXNCAAMBSPREAD",
    # Soccer game lines (OOS_NULL despite EPL train edge)
    "KXEPLGAME",
    "KXUCLGAME",
})


# Round 15b PERSIST allowlist (validated 2026-05-27): these five prefixes
# show event-level cluster bootstrap CI lower > 0 on BOTH train
# (Nov 2024 to Sep 2025) AND OOS (Sep 2025 to Nov 2025) on v1's exact
# regime. n_events ranges from 164 (NFL) to 717 (NCAA-F) in OOS. Edge
# magnitude +2.5% to +4.3% net per fill. Use as the active allowlist
# (config.series_allowlist) to restrict the bot to validated universe.
PERSIST_SERIES_ALLOWLIST: frozenset[str] = frozenset({
    "KXMLBGAME",
    "KXATPMATCH",
    "KXNFLGAME",
    "KXNCAAFGAME",
    "KXWTAMATCH",
})


def extract_series_prefix(ticker: str, series_ticker: str = "") -> str:
    """Return the canonical series-prefix for a market ticker.

    Prefer the API-provided series_ticker (e.g., 'KXNFLWINS'); fall back
    to the substring before the first '-' in the full ticker
    ('KXNFLWINS-SEA-25B-T8' -> 'KXNFLWINS'). Returns the empty string if
    neither yields a value.
    """
    if series_ticker:
        return series_ticker
    if not ticker:
        return ""
    head, _sep, _tail = ticker.partition("-")
    return head


@dataclass(frozen=True)
class ScannerConfig:
    """Filter parameters that the scanner applies to each open market."""

    category: str  # "Politics", "Sports", etc.
    min_lifetime_days: int
    mid_band_lower: tuple[float, float] = (0.20, 0.45)
    mid_band_upper: tuple[float, float] = (0.55, 0.80)
    min_volume: float = 50.0
    # Upper bound on market total lifetime (open_time to close_time). None
    # disables the filter. Per research/time-scale-analysis.md, the
    # favorite-maker edge is clean below 180d (n=39, 100% YES rate, zero
    # losses) and noisy above 180d (n=8, one -81pp realized loss). The
    # 180d cap also aligns with ~8x capital-efficiency improvement vs
    # long-horizon trades.
    max_lifetime_days: int | None = None
    # Series-prefix denylist applied to every candidate. Default contains
    # the three series V4-H showed v1's edge does NOT generalize to. Pass
    # frozenset() to disable; pass a custom set to override. To apply the
    # Round 15b expanded denylist (also excludes spread/total/prop
    # markets where Becker OOS shows null/negative edge), pass
    # EXPANDED_SERIES_DENYLIST.
    series_denylist: frozenset[str] = field(
        default_factory=lambda: DEFAULT_SERIES_DENYLIST,
    )
    # Series-prefix allowlist. When non-empty, ONLY markets with a series
    # prefix in this set will pass the scanner. Default None disables the
    # filter (denylist alone is used). Pass PERSIST_SERIES_ALLOWLIST to
    # restrict to the five Becker-validated PERSIST prefixes (KXMLBGAME,
    # KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH). This is the
    # safest scoping post Round 15b. See research/v10a/TEST-AND-CONFIRM.md.
    series_allowlist: frozenset[str] | None = None
    # Optional pre-close cutoff in MINUTES. When set, any market that
    # closes within this many minutes from "now" will be skipped, to
    # avoid the high-information-flow window where adverse selection
    # peaks for resting maker quotes. None disables the filter. Suggested
    # value: 60 (one hour). Live observation 2026-05-27 found mean
    # post-fill mid drift of -4.93pp across 15 still-open v1 fills,
    # consistent with adverse selection near close. See
    # scripts/v10a/analyze_v1_live.py output.
    min_minutes_to_close: int | None = None


def parse_snapshot(market: dict) -> MarketSnapshot | None:
    """Convert a Kalshi /markets response row to a MarketSnapshot."""
    try:
        yes_bid = float(market.get("yes_bid_dollars", 0) or 0)
        yes_ask = float(market.get("yes_ask_dollars", 0) or 0)
        last = float(market.get("last_price_dollars", 0) or 0)
        volume = float(market.get("volume_fp", 0) or 0)
    except (TypeError, ValueError):
        return None
    ticker = market.get("ticker", "")
    if not ticker:
        return None
    return MarketSnapshot(
        ticker=ticker,
        event_ticker=market.get("event_ticker", ""),
        series_ticker=market.get("series_ticker", ""),
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        last_price=last,
        volume=volume,
        open_time=market.get("open_time", ""),
        close_time=market.get("close_time", ""),
        title=market.get("title", "") or market.get("subtitle", ""),
    )


def filter_candidates(
    markets: list[dict],
    config: ScannerConfig,
    *,
    now: pd.Timestamp | None = None,
) -> list[tuple[dict, MarketSnapshot]]:
    """Apply Section 2.2 + Section 4 filters to a list of raw markets.

    Returns list of (raw_market_dict, parsed_snapshot) tuples for markets
    that pass all filters. The raw dict is preserved so the caller can
    examine fields not captured in MarketSnapshot (e.g., title for
    league tagging).
    """
    if now is None:
        now = pd.Timestamp.now(tz="UTC")
    candidates: list[tuple[dict, MarketSnapshot]] = []
    for m in markets:
        if m.get("status") != "open" and m.get("status") != "active":
            continue
        snap = parse_snapshot(m)
        if snap is None:
            continue
        # W1 closure: skip markets in series where v1's measured edge
        # has not been demonstrated. See DEFAULT_SERIES_DENYLIST docstring
        # above. Reading the prefix defensively because Kalshi sometimes
        # returns an empty series_ticker on /markets responses.
        series_prefix = extract_series_prefix(snap.ticker, snap.series_ticker)
        if config.series_denylist and series_prefix in config.series_denylist:
            log.debug("scanner_denylist_skip", ticker=snap.ticker,
                      series_prefix=series_prefix)
            continue
        # Round 15b allowlist gate: if a series_allowlist is configured,
        # only markets in those prefixes pass.
        if config.series_allowlist is not None and series_prefix not in config.series_allowlist:
            log.debug("scanner_allowlist_skip", ticker=snap.ticker,
                      series_prefix=series_prefix)
            continue
        if snap.volume < config.min_volume:
            continue
        try:
            open_t = pd.Timestamp(snap.open_time)
            close_t = pd.Timestamp(snap.close_time)
        except (TypeError, ValueError):
            continue
        lifetime_days = (close_t - open_t).total_seconds() / 86400.0
        if lifetime_days < config.min_lifetime_days:
            continue
        if (
            config.max_lifetime_days is not None
            and lifetime_days > config.max_lifetime_days
        ):
            continue
        # Round 15b pre-close cutoff: skip markets very close to
        # close_time to avoid the adverse-selection window where MMs
        # tighten and orderflow becomes information-rich.
        if config.min_minutes_to_close is not None:
            minutes_to_close = (close_t - now).total_seconds() / 60.0
            if minutes_to_close < config.min_minutes_to_close:
                log.debug("scanner_pre_close_skip", ticker=snap.ticker,
                          minutes_to_close=minutes_to_close)
                continue
        # Apply mid-band filter on yes_bid (proxy for current mid)
        if snap.yes_bid <= 0 or snap.yes_ask <= 0:
            continue
        mid = (snap.yes_bid + snap.yes_ask) / 2.0
        in_lower = config.mid_band_lower[0] <= mid <= config.mid_band_lower[1]
        in_upper = config.mid_band_upper[0] <= mid <= config.mid_band_upper[1]
        if not (in_lower or in_upper):
            continue
        candidates.append((m, snap))
    return candidates


def scan(client: KalshiClient, config: ScannerConfig) -> list[tuple[dict, MarketSnapshot]]:
    """Poll Kalshi for open markets in the category and filter them.

    Implementation note: Kalshi's `/markets` endpoint does NOT accept a
    `category` query param (the documented filters are
    `series_ticker`, `event_ticker`, `tickers`, `status`,
    `min_close_ts`, `max_close_ts`). We discover series first via
    `/series?category=...`, then iterate `/markets?series_ticker=...&status=open`
    for each. This matches the pattern in the offline fetcher scripts.
    """
    log.info("scan_start", category=config.category)
    raw_markets: list[dict] = []
    # 1) Discover series in the category (use a single page; most categories
    #    fit in 200 series)
    series_list: list[str] = []
    for s in client.paginate(
        "/series", item_key="series", limit=200, category=config.category, max_pages=10,
    ):
        ticker = s.get("ticker") or s.get("series_ticker")
        if ticker:
            series_list.append(ticker)
    # 2) For each series, pull open markets. Skip empty results silently.
    for series_ticker in series_list:
        try:
            for m in client.paginate(
                "/markets", item_key="markets", limit=200,
                status="open", series_ticker=series_ticker, max_pages=2,
            ):
                raw_markets.append(m)
        except Exception as exc:
            log.warning("series_scan_failed", series=series_ticker, error=str(exc))
            continue
    candidates = filter_candidates(raw_markets, config)
    log.info("scan_done", category=config.category,
             n_series=len(series_list), n_raw=len(raw_markets),
             n_candidates=len(candidates))
    return candidates
