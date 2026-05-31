"""Record-only lead-lag shadow logger core (Round 21 / v16).

Pure, network-free helpers for the forward shadow study that measures
whether Kalshi lags the sportsbook and whether that lag is capturable at
EXECUTABLE Kalshi prices. The locked gate design is in
research/v16/01-methodology-lock.md.

This module NEVER places or cancels orders and performs NO network IO. It
only computes derived quantities and assembles record rows. The IO loop
(odds pull, orderbook pull, parquet append, scheduling) lives in
scripts/v16/shadow_logger.py.

Phase 1 captures, at each v14-equivalent fire (and near-miss), the live
executable Kalshi book (yes_bid / yes_ask / depth) alongside the sportsbook
implied probability, so Gate A (does the lag exist) can be computed once the
closing-line snapshot and settlement are joined in. Every field needed to
later compute the executable entry leg (yes_ask at T0) is recorded here; the
executable exit leg (closing yes_bid) is a separate re-snapshot.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from datetime import datetime

# Frozen strategy parameters (identical to the live v14 daemon, so the shadow
# log captures exactly the population the daemon would have traded). The 60bp
# threshold was set on prior v12 data and is NOT re-tuned on the forward
# sample; see research/v16/01-methodology-lock.md.
X_THRESHOLD = 0.006  # 60 bp fire threshold
NEAR_MISS_THRESHOLD = 0.003  # 30 bp: logged with fired=False for later threshold study
EXEC_WINDOW_MIN_H = 1.0
EXEC_WINDOW_MAX_H = 3.0
LOOKBACK_HOURS = 3

_ET = ZoneInfo("America/New_York")

# Ordered schema for the entries parquet. The runner writes rows as dicts with
# exactly these keys (see build_entry_row).
ENTRY_COLUMNS: list[str] = [
    "captured_ts",  # UTC ISO, the instant the Kalshi book was read (T0)
    "night_id",  # US/Eastern game date (cluster key), NOT UTC date
    "week_id",  # US/Eastern ISO year-week (secondary cluster key)
    "game_id",  # the-odds-api game id
    "home_team",
    "away_team",
    "side",  # "home" or "away": the side the sportsbook moved toward
    "series_prefix",
    "ticker",  # matched Kalshi ticker for the side, or "" if unmatched
    "classification",  # "fire" (|delta| >= X) or "near_miss" (>= NEAR_MISS)
    "fired",  # bool: True iff classification == "fire"
    "fire_seq",  # 0 for the first capture of a (game, side, night) key
    "delta_sb_home",  # current home implied minus 3h-ago home implied
    "sportsbook_home_implied",  # p_cur (no-vig home implied, current)
    "sportsbook_home_implied_3hago",  # p_hist
    "odds_snapshot_ts",  # the-odds-api historical snapshot timestamp (hourly)
    "target_implied",  # sportsbook implied for the side taken (p_cur or 1-p_cur)
    "commence_ts",  # game commence (UTC ISO)
    "close_time",  # Kalshi market close_time (UTC ISO) if known, else ""
    "hours_to_commence",
    "minutes_to_commence",
    # Executable Kalshi book at T0 (the matched-ticker market):
    "yes_bid",
    "yes_ask",  # the executable ENTRY price for Gate A (taker pays this)
    "yes_depth",  # contracts at best yes bid
    "no_depth",  # contracts at best no bid (backs the parity-derived ask)
    "mid",
    "is_parity_derived",  # yes_ask derived from 1 - best_no_bid
    "book_empty",  # both sides empty: no executable price exists
    "book_status",  # "ok" / "empty" / "fetch_error" / "no_ticker": separates a
    # genuinely empty Kalshi book from a failed read or an unmatched ticker, so
    # Gate A never pools "no book existed" with "we could not read it".
]


def home_implied_median(game: dict) -> float | None:
    """No-vig home-team implied probability, median across bookmakers.

    Mirrors the live v14 daemon's home_implied_median so the shadow log
    captures the same signal. Each h2h bookmaker market gives decimal odds
    for home and away; we invert to raw implied, normalize the two-outcome
    overround away (p_h / (p_h + p_a)), and take the median across books.
    Returns None when no usable two-outcome h2h market is present.
    """
    home = game.get("home_team")
    away = game.get("away_team")
    if not home or not away:
        return None
    home_imps: list[float] = []
    for bk in game.get("bookmakers", []) or []:
        for mk in bk.get("markets", []) or []:
            if mk.get("key") != "h2h":
                continue
            outs = mk.get("outcomes", []) or []
            if len(outs) != 2:
                continue
            p_h, p_a = None, None
            for o in outs:
                price = o.get("price")
                if not price or price <= 0:
                    continue
                if o.get("name") == home:
                    p_h = 1.0 / float(price)
                elif o.get("name") == away:
                    p_a = 1.0 / float(price)
            if p_h is None or p_a is None:
                continue
            s = p_h + p_a
            if s <= 0:
                continue
            home_imps.append(p_h / s)
    if not home_imps:
        return None
    return float(statistics.median(home_imps))


def classify_delta(delta: float) -> str | None:
    """Bucket an absolute sportsbook move into the logged classes.

    Returns "fire" when |delta| >= X_THRESHOLD (the daemon would have traded),
    "near_miss" when |delta| >= NEAR_MISS_THRESHOLD (logged so the 60bp
    threshold can be re-evaluated later without a second season of waiting),
    or None when below the near-miss floor (not logged).
    """
    a = abs(delta)
    if a >= X_THRESHOLD:
        return "fire"
    if a >= NEAR_MISS_THRESHOLD:
        return "near_miss"
    return None


def in_exec_window(hours_to_commence: float) -> bool:
    """True when the game commences within the [T-3h, T-1h] execution window."""
    return EXEC_WINDOW_MIN_H <= hours_to_commence <= EXEC_WINDOW_MAX_H


def eastern_date_str(dt: datetime) -> str:
    """US/Eastern calendar date of dt as YYYY-MM-DD (the night cluster key).

    A 22:00 ET first pitch and a 19:00 ET game the same night share a night_id
    even though they straddle the UTC date boundary. Clustering on this, not on
    the UTC date, is what keeps the bootstrap CI honest (plan critic H3).
    """
    return dt.astimezone(_ET).strftime("%Y-%m-%d")


def iso_week_id(dt: datetime) -> str:
    """US/Eastern ISO year-week of dt as 'YYYY-Www' (secondary cluster key)."""
    iso = dt.astimezone(_ET).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def dedup_key(game_id: str, side: str, night_id: str) -> str:
    """Stable key for one (game, side, night). The first capture is binding;
    later captures of the same key are versioned via fire_seq."""
    return f"{game_id}|{side}|{night_id}"


def _best_level(side: list) -> tuple[float | None, float]:
    """Return (best_price, depth_at_best) for one orderbook side.

    Kalshi `*_dollars` entries are [price_str, qty_str] sorted ascending, so
    the best (highest) bid is the LAST entry. Returns (None, 0.0) for an empty
    or unparseable side.
    """
    if not side:
        return None, 0.0
    best_price: float | None = None
    best_depth = 0.0
    for entry in side:
        if not entry or len(entry) < 1:
            continue
        try:
            price = float(entry[0])
        except (ValueError, TypeError):
            continue
        if best_price is None or price > best_price:
            best_price = price
            try:
                best_depth = float(entry[1]) if len(entry) >= 2 else 0.0
            except (ValueError, TypeError):
                best_depth = 0.0
    return best_price, best_depth


def parse_orderbook(payload: dict) -> dict:
    """Parse a Kalshi /markets/{ticker}/orderbook payload into executable
    prices and depth. Pure function; never raises on malformed input.

    Returns a dict with keys: yes_bid, yes_ask, yes_depth, no_depth, mid,
    is_parity_derived, book_empty. yes_ask is derived by parity from the best
    NO bid (yes_ask = 1 - best_no_bid). book_empty is True when neither side
    has a usable level, in which case prices are None and depths are 0.0. A
    missing price is ALWAYS an explicit None with book_empty context, never a
    silent default, so dropped rows stay auditable (methodology lock L1).
    """
    ob = payload.get("orderbook_fp") or payload.get("orderbook") or payload or {}
    yes_side = ob.get("yes_dollars") or ob.get("yes") or []
    no_side = ob.get("no_dollars") or ob.get("no") or []

    yes_bid, yes_depth = _best_level(yes_side)
    if yes_bid is not None and yes_bid <= 0:
        yes_bid, yes_depth = None, 0.0

    best_no, no_depth = _best_level(no_side)
    # A NO bid must sit strictly in (0, 1); a degenerate bid at/above 1.00 (or
    # at/below 0) would imply a yes_ask <= 0 or >= 1, which is not a real
    # executable price, so discard it rather than record a nonsense ask.
    if best_no is not None and not 0.0 < best_no < 1.0:
        best_no, no_depth = None, 0.0

    yes_ask: float | None = None
    is_parity_derived = False
    if best_no is not None:
        yes_ask = round(1.0 - best_no, 4)
        is_parity_derived = True

    book_empty = yes_bid is None and yes_ask is None
    if book_empty:
        return {
            "yes_bid": None, "yes_ask": None, "yes_depth": 0.0, "no_depth": 0.0,
            "mid": None, "is_parity_derived": False, "book_empty": True,
        }

    if yes_bid is not None and yes_ask is not None:
        mid: float | None = round((yes_bid + yes_ask) / 2.0, 4)
    elif yes_bid is not None:
        mid = yes_bid
    else:
        mid = yes_ask

    return {
        "yes_bid": round(yes_bid, 4) if yes_bid is not None else None,
        "yes_ask": yes_ask,
        "yes_depth": yes_depth,
        "no_depth": no_depth,
        "mid": mid,
        "is_parity_derived": is_parity_derived,
        "book_empty": False,
    }


# --- Phase 2: re-snapshot scheduling + trade-tape summarization -----------
# Intra-window re-snapshot offsets from the fire time (T0), in minutes, plus a
# closing snapshot taken CLOSE_SNAPSHOT_LEAD_MIN before the market's close_time
# (before finalization, since settled-market orderbooks return empty). These
# capture the convergence path the Gate A CLV calculation needs.
INTRA_SNAPSHOT_OFFSETS_MIN: dict[str, float] = {"t5": 5.0, "t30": 30.0}
CLOSE_SNAPSHOT_LEAD_MIN = 2.0
SNAPSHOT_LABELS: tuple[str, ...] = ("t5", "t30", "close")


def snapshot_target_time(
    label: str, fire_ts: datetime, close_dt: datetime | None
) -> datetime | None:
    """Target wall-clock time for a re-snapshot label.

    "t5"/"t30" are fire_ts plus the offset; "close" is close_dt minus the lead.
    Returns None for an unknown label or a "close" with no close_dt (so the
    runner records it as unschedulable rather than guessing).
    """
    if label == "close":
        if close_dt is None:
            return None
        return close_dt - timedelta(minutes=CLOSE_SNAPSHOT_LEAD_MIN)
    offset = INTRA_SNAPSHOT_OFFSETS_MIN.get(label)
    if offset is None:
        return None
    return fire_ts + timedelta(minutes=offset)


def parse_trade_yes_cents(trade: dict) -> float | None:
    """Yes price of one Kalshi trade in cents (0 to 100). Handles both the
    integer-cents `yes_price` field and the dollar-string `yes_price_dollars`
    field (post-March-2026 API), mirroring the live fill parser. Returns None
    when neither is parseable, so a bad record is skipped, never coerced."""
    dollars = trade.get("yes_price_dollars")
    if dollars is not None:
        try:
            return float(dollars) * 100.0
        except (TypeError, ValueError):
            return None
    cents = trade.get("yes_price")
    if cents is not None:
        try:
            return float(cents)
        except (TypeError, ValueError):
            return None
    return None


def summarize_yes_prices(prices_cents: list[float]) -> dict:
    """Min / max / mean and count of yes trade prices (cents) in an interval.

    An empty interval returns n_trades=0 with None statistics, so "no trades
    happened" is explicit and never confused with a real price of zero. This
    is the raw material for a later, post-registration fill model (e.g. did the
    market trade at or through a passive bid); recording the distribution keeps
    the study free to evaluate any limit without a baked-in threshold.
    """
    if not prices_cents:
        return {
            "n_trades": 0, "min_yes_cents": None,
            "max_yes_cents": None, "mean_yes_cents": None,
        }
    return {
        "n_trades": len(prices_cents),
        "min_yes_cents": round(min(prices_cents), 2),
        "max_yes_cents": round(max(prices_cents), 2),
        "mean_yes_cents": round(statistics.mean(prices_cents), 2),
    }


# --- Phase 3: passive-fill probe limit (tiny live resting orders) ----------
def passive_probe_limit_cents(book: dict, *, min_spread: float = 0.02) -> int | None:
    """Passive (maker) buy-YES limit, in integer cents, for the Phase 3 probe.

    The probe tests whether a passive resting bid at the lagging Kalshi level
    actually fills (the only honest test of passive-maker harvestability, which
    record-only snapshots cannot measure). To stay a clean MAKER that never
    crosses the ask, return the current best yes_bid only when the book is
    two-sided with a spread >= min_spread. Returns None for an empty, one-sided,
    or too-tight book, or a bid outside [1, 99] cents, in which case the probe
    skips that fire rather than risk a marketable (taker) fill.
    """
    if book.get("book_empty"):
        return None
    yes_bid = book.get("yes_bid")
    yes_ask = book.get("yes_ask")
    if yes_bid is None or yes_ask is None:
        return None
    if yes_ask - yes_bid < min_spread:
        return None
    cents = int(round(yes_bid * 100))
    if not 1 <= cents <= 99:
        return None
    return cents


def build_entry_row(
    *,
    captured_ts: datetime,
    game: dict,
    delta_sb_home: float,
    p_cur: float,
    p_hist: float,
    odds_snapshot_ts: str,
    take_home_side: bool,
    classification: str,
    ticker: str,
    commence: datetime,
    close_time: str,
    book: dict,
    fire_seq: int,
    book_status: str = "ok",
) -> dict:
    """Assemble one entry row matching ENTRY_COLUMNS. Pure; no IO.

    `book` is the dict returned by parse_orderbook. `take_home_side` mirrors the
    daemon: True when the sportsbook moved the home implied UP. target_implied is
    the sportsbook implied for the side actually bet (p_cur for home, 1-p_cur for
    away), so it can be compared against the executable yes_ask (lag at entry)
    and the later closing yes_bid (closing-line value).
    """
    hours_to_commence = (commence - captured_ts).total_seconds() / 3600.0
    side = "home" if take_home_side else "away"
    target_implied = p_cur if take_home_side else 1.0 - p_cur
    night_id = eastern_date_str(commence)
    return {
        "captured_ts": captured_ts.isoformat(),
        "night_id": night_id,
        "week_id": iso_week_id(commence),
        "game_id": game.get("id", ""),
        "home_team": game.get("home_team", ""),
        "away_team": game.get("away_team", ""),
        "side": side,
        "series_prefix": "KXMLBGAME",
        "ticker": ticker,
        "classification": classification,
        "fired": classification == "fire",
        "fire_seq": fire_seq,
        "delta_sb_home": round(delta_sb_home, 6),
        "sportsbook_home_implied": round(p_cur, 6),
        "sportsbook_home_implied_3hago": round(p_hist, 6),
        "odds_snapshot_ts": odds_snapshot_ts,
        "target_implied": round(target_implied, 6),
        "commence_ts": commence.isoformat(),
        "close_time": close_time,
        "hours_to_commence": round(hours_to_commence, 4),
        "minutes_to_commence": round(hours_to_commence * 60.0, 2),
        "yes_bid": book.get("yes_bid"),
        "yes_ask": book.get("yes_ask"),
        "yes_depth": book.get("yes_depth", 0.0),
        "no_depth": book.get("no_depth", 0.0),
        "mid": book.get("mid"),
        "is_parity_derived": book.get("is_parity_derived", False),
        "book_empty": book.get("book_empty", True),
        "book_status": book_status,
    }
