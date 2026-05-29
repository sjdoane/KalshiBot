"""v14 daemon: live MLB-night sportsbook lead-lag trader.

Runs an in-process loop that:
1. Polls the-odds-api for current MLB odds and a 3-hour-ago snapshot.
2. Filters to games commencing in T-1h to T-3h.
3. For each qualifying game with |home_implied_delta| >= X_THRESHOLD (60bp),
   determines the side to take (YES on home if delta > 0, YES on away if < 0).
4. Looks up the exact Kalshi ticker via ticker_match (queries /markets).
5. Skips if v1 already has the ticker in state.json OR if v14 already has
   the ticker in v14_state.json (de-dup).
6. Self-meters capital: places only if (current v14 exposure + new order
   cost) <= V14_CAPITAL_CAP_USD (12.80) AND new order cost <= Kalshi cash.
7. Places via LiveOrderManager (writes to data/v14/v14_state.json).
8. Logs each fire + each placement to data/v14/v14_trades.jsonl.
9. Enforces minimal kill triggers: $2.56 drawdown OR 5 consecutive losses
   OR daily order cap of 10 OR STOP file.

Manual launch (operator):

    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v14.v14_daemon

It will loop every 15 minutes during 18:00 to 06:00 UTC; sleeps during
off-hours.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
import structlog
from dotenv import load_dotenv

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))
sys.path.insert(0, str(BASE / "scripts" / "v11"))

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.live_order_manager import LiveOrderManager, LiveOrderStatus
from kalshi_bot_v14.ticker_match import find_kalshi_ticker_for_side

try:
    from kalshi_bot.alerts.discord import (
        format_loop_heartbeat,
        post as _discord_post,
    )
except Exception:
    _discord_post = None
    format_loop_heartbeat = None  # type: ignore[assignment]

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def discord_notify(content: str) -> None:
    """Best-effort Discord webhook ping. Silent on failure (no exception)."""
    if not DISCORD_WEBHOOK_URL or _discord_post is None:
        return
    try:
        _discord_post(DISCORD_WEBHOOK_URL, content=content, username="v14 MLB-night")
    except Exception:
        pass


log = structlog.get_logger(__name__)


# Locked v14 strategy parameters
X_THRESHOLD = 0.006
HAIRCUT = 0.0007
SAFETY_BUFFER = 0.005
# v14 per-fire USD budget. Used as BOTH the headroom floor check AND the
# size input (contracts = int(V14_PER_TRADE_USD // target_price)). Default
# 0.95 reproduces the pre-2026-05-28 single-contract behavior at typical
# $0.47 mean execution price. Operator can override via env to concentrate
# more capital per fire since v14 fires rarely (1-2/day expected) vs v1's
# high frequency. At V14_PER_TRADE_USD=5.00 each fire is ~10 contracts.
V14_PER_TRADE_USD = float(os.environ.get("V14_PER_TRADE_USD", "0.95"))
V14_MAX_DAILY_ORDERS = int(os.environ.get("V14_MAX_DAILY_ORDERS", "10"))
V14_CONSECUTIVE_LOSS_KILL = 5

# Capital allocation: fraction of LIVE Kalshi total bankroll (cash + filled
# positions) controlled by v14. v1 gets the complementary fraction. Read
# from env so operator can tune without code edit. Defaults: 40% v14, 60% v1.
V14_BANKROLL_FRACTION = float(os.environ.get("V14_BANKROLL_FRACTION", "0.40"))

# Drawdown kill = 20% drop from v14's all-time-high realized + unrealized P&L.
# Dynamic; not hardcoded to a dollar threshold.
V14_DRAWDOWN_KILL_FRACTION = float(
    os.environ.get("V14_DRAWDOWN_KILL_FRACTION", "0.20")
)

# Stale-order rotation thresholds.
V14_STALE_AGE_HOURS = float(os.environ.get("V14_STALE_AGE_HOURS", "2.0"))
V14_NEAR_CLOSE_MIN = float(os.environ.get("V14_NEAR_CLOSE_MIN", "30"))

# Market drift cancel: cancel a v14 resting order if the current Kalshi
# yes_ask has moved >= this many cents away from our target price (i.e.,
# our bid is no longer competitive).
V14_DRIFT_CANCEL_CENTS = float(os.environ.get("V14_DRIFT_CANCEL_CENTS", "3"))

# Timing
LOOP_INTERVAL_SECONDS = 15 * 60
ACTIVE_HOUR_UTC_START = 18  # 18:00 UTC = 2 PM ET
ACTIVE_HOUR_UTC_END = 6     # 06:00 UTC = 2 AM ET (next day)
LOOKBACK_HOURS = 3
EXEC_WINDOW_MIN_H = 1.0
EXEC_WINDOW_MAX_H = 3.0

# Paths
DATA_DIR = BASE / "data" / "v14"
DATA_DIR.mkdir(parents=True, exist_ok=True)
V14_STATE_PATH = DATA_DIR / "v14_state.json"
V14_TRADES_LOG = DATA_DIR / "v14_trades.jsonl"
V1_STATE_PATH = BASE / "data" / "live_trades" / "state.json"
STOP_FILE = DATA_DIR / "STOP"
PAUSE_FILE = DATA_DIR / "PAUSE"
PAPER_MODE_FILE = DATA_DIR / "PAPER_MODE"

KEY = os.environ.get("THE_ODDS_API_KEY")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_active_hour(dt: datetime) -> bool:
    h = dt.hour
    if ACTIVE_HOUR_UTC_START < ACTIVE_HOUR_UTC_END:
        return ACTIVE_HOUR_UTC_START <= h < ACTIVE_HOUR_UTC_END
    # wrap-around case (18..24 OR 0..6)
    return h >= ACTIVE_HOUR_UTC_START or h < ACTIVE_HOUR_UTC_END


def log_event(payload: dict) -> None:
    payload.setdefault("ts_utc", now_utc().isoformat())
    V14_TRADES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with V14_TRADES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def sync_with_kalshi_orders(om: LiveOrderManager, kc: KalshiClient) -> dict:
    """Poll Kalshi /portfolio/orders and reconcile v14 state.json with reality.

    Detects v14 orders that no longer exist on Kalshi (operator-cancelled,
    expired, or system-cancelled). Moves them to the closed pool so v14
    state matches truth.

    Note: this does NOT detect fills - LiveOrderManager has separate fill
    reconcile logic for that. This handles cancellations specifically.
    """
    summary = {"externally_cancelled": 0, "errors": []}
    try:
        resp = kc.get("/portfolio/orders", status="resting", limit=200)
    except Exception as e:
        summary["errors"].append(f"poll_orders: {type(e).__name__}: {e}")
        return summary
    kalshi_resting_ids = {
        o.get("order_id") for o in (resp.get("orders") or []) if o.get("order_id")
    }
    to_remove: list[str] = []
    for intent_id, order in list(om.state.resting.items()):
        if not order.order_id:
            continue
        if order.order_id not in kalshi_resting_ids:
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = now_utc().isoformat()
            om.state.closed[intent_id] = order
            to_remove.append(intent_id)
            summary["externally_cancelled"] += 1
            log_event({
                "event": "external_cancel_detected",
                "ticker": order.ticker, "order_id": order.order_id,
                "intent_id": intent_id,
            })
    for iid in to_remove:
        del om.state.resting[iid]
    if to_remove:
        om._save()
    return summary


def cancel_v14_stale_orders(
    om: LiveOrderManager, kc: KalshiClient, open_markets: list[dict],
) -> dict:
    """Cancel v14 resting orders that should rotate out. Three rules,
    any one of which triggers cancellation:

    1. Market is within V14_NEAR_CLOSE_MIN minutes of close.
    2. Order age exceeds V14_STALE_AGE_HOURS.
    3. Current Kalshi yes_ask has drifted >= V14_DRIFT_CANCEL_CENTS from
       our target price (i.e., our bid is no longer competitive).

    All thresholds are env-tunable. Rotation keeps v14 capital fluid so
    new fires can place orders that actually fill.
    """
    summary = {
        "cancelled_near_close": 0,
        "cancelled_stale_age": 0,
        "cancelled_drift": 0,
        "errors": [],
    }
    market_by_ticker = {m.get("ticker"): m for m in open_markets}
    now = now_utc()
    to_remove: list[str] = []

    for intent_id, order in list(om.state.resting.items()):
        if not order.order_id:
            continue
        reason = None
        m = market_by_ticker.get(order.ticker)

        # Rule 1: near close
        if m is not None:
            close_str = m.get("close_time")
            if close_str:
                try:
                    close_dt = pd.Timestamp(close_str).tz_convert("UTC").to_pydatetime()
                    minutes_to_close = (close_dt - now).total_seconds() / 60.0
                    if minutes_to_close < V14_NEAR_CLOSE_MIN:
                        reason = ("near_close", round(minutes_to_close, 1))
                except Exception:
                    pass

        # Rule 2: order age
        if reason is None and order.placed_ts:
            try:
                placed = pd.Timestamp(order.placed_ts).tz_convert("UTC").to_pydatetime()
                age_h = (now - placed).total_seconds() / 3600.0
                if age_h >= V14_STALE_AGE_HOURS:
                    reason = ("stale_age", round(age_h, 2))
            except Exception:
                pass

        # Rule 3: market drift (only if the market is still in our cached
        # open_markets list; otherwise we'd need a separate API call which
        # we skip for cost reasons)
        if reason is None and m is not None:
            live_ask = fetch_kalshi_orderbook_yes_ask(kc, order.ticker)
            if live_ask is not None:
                our_price = float(order.target_price_cents or 0) / 100.0
                drift_cents = (live_ask - our_price) * 100.0
                if abs(drift_cents) >= V14_DRIFT_CANCEL_CENTS:
                    reason = ("drift", round(drift_cents, 1))

        if reason is None:
            continue

        try:
            kc.delete(f"/portfolio/orders/{order.order_id}")
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = now.isoformat()
            om.state.closed[intent_id] = order
            to_remove.append(intent_id)
            key = {
                "near_close": "cancelled_near_close",
                "stale_age": "cancelled_stale_age",
                "drift": "cancelled_drift",
            }[reason[0]]
            summary[key] += 1
            log_event({
                "event": "v14_stale_cancel",
                "ticker": order.ticker,
                "reason": reason[0],
                "metric": reason[1],
            })
        except Exception as e:
            summary["errors"].append(
                f"cancel {order.ticker}: {type(e).__name__}: {e}"
            )
    for iid in to_remove:
        del om.state.resting[iid]
    if to_remove:
        om._save()
    return summary


def v1_holds_ticker(ticker: str) -> bool:
    """Check if v1 currently has an intent / resting / filled position on
    the ticker (read-only).
    """
    if not V1_STATE_PATH.exists():
        return False
    try:
        v1 = json.loads(V1_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    for pool_name in ("intents", "resting", "filled"):
        pool = v1.get(pool_name) or {}
        for record in pool.values():
            if record.get("ticker") == ticker:
                return True
    return False


def fetch_odds_snapshot(
    client: httpx.Client, key: str, when: datetime | None = None
) -> tuple[list[dict], int]:
    """Pull h2h MLB odds. If when is None, current; else historical at when.

    Returns (game_list, credits_remaining).
    """
    if when is None:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
        params = {
            "apiKey": key, "regions": "us", "markets": "h2h",
            "oddsFormat": "decimal",
        }
    else:
        iso = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
        url = "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds"
        params = {
            "apiKey": key, "regions": "us", "markets": "h2h",
            "date": iso, "oddsFormat": "decimal",
        }
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    games = body if when is None else body.get("data", [])
    remaining = int(r.headers.get("x-requests-remaining", -1))
    return games, remaining


def home_implied_median(game: dict) -> float | None:
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
    return float(pd.Series(home_imps).median())


def fetch_kalshi_open_mlb_markets(kc: KalshiClient) -> list[dict]:
    """Page through Kalshi /markets for currently-open KXMLBGAME markets."""
    out: list[dict] = []
    cursor = ""
    for _ in range(20):
        params: dict = {"series_ticker": "KXMLBGAME", "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = kc.get("/markets", **params)
        markets = resp.get("markets", [])
        if not markets:
            break
        out.extend(markets)
        cursor = resp.get("cursor") or ""
        if not cursor:
            break
    return out


def fetch_kalshi_balance(kc: KalshiClient) -> tuple[float, float]:
    """Returns (cash_usd, positions_value_usd) from Kalshi /portfolio/balance.

    cash = free cash available for new orders (Kalshi does NOT lock cash on
    resting maker bids; only on filled positions).
    positions_value = notional value of currently-filled positions.
    total bankroll = cash + positions_value.
    """
    resp = kc.get("/portfolio/balance")
    bal = resp.get("balance")
    if bal is None:
        bal = resp.get("portfolio_balance", 0)
    cash = float(int(bal or 0)) / 100.0
    pos = float(int(resp.get("portfolio_value", 0) or 0)) / 100.0
    return cash, pos


def fetch_kalshi_cash_usd(kc: KalshiClient) -> float:
    """Back-compat shim: returns just cash from /portfolio/balance."""
    cash, _ = fetch_kalshi_balance(kc)
    return cash


def fetch_kalshi_orderbook_yes_ask(kc: KalshiClient, ticker: str) -> float | None:
    """Returns the current best YES ask price (in dollars) for a ticker.

    YES ask is computed as 1.0 - best_NO_bid per Kalshi convention.
    Returns None if the orderbook is empty or call fails.
    """
    try:
        resp = kc.get(f"/markets/{ticker}/orderbook")
    except Exception:
        return None
    ob = resp.get("orderbook_fp") or resp.get("orderbook") or {}
    no_book = ob.get("no_dollars") or []
    if not no_book:
        return None
    try:
        best_no_bid = float(no_book[-1][0])
        return 1.0 - best_no_bid
    except (IndexError, TypeError, ValueError):
        return None


def compute_v14_exposure(om: LiveOrderManager) -> float:
    """Sum of resting + filled exposure in USD."""
    exposure = 0.0
    for o in om.state.resting.values():
        exposure += (o.target_price_cents or 0) * (o.contracts or 0) / 100.0
    for o in om.state.filled.values():
        price = o.filled_price_cents or o.target_price_cents or 0
        count = o.filled_count or o.contracts or 0
        exposure += price * count / 100.0
    return exposure


def v14_holds_ticker(om: LiveOrderManager, ticker: str) -> bool:
    for pool in (om.state.intents, om.state.resting, om.state.filled):
        for o in pool.values():
            if o.ticker == ticker:
                return True
    return False


def check_kill_triggers(
    om: LiveOrderManager, v14_cap_usd: float,
) -> tuple[bool, str]:
    """Return (tripped, reason). Drawdown threshold is dynamic:
    V14_DRAWDOWN_KILL_FRACTION of the CURRENT v14 cap, not a hardcoded $.
    """
    drawdown_threshold = -V14_DRAWDOWN_KILL_FRACTION * v14_cap_usd
    realized = om.state.realized_pnl_total_usd or 0.0
    if realized <= drawdown_threshold:
        return True, (
            f"drawdown_killed_realized_pnl_{realized:.2f}_below_"
            f"{drawdown_threshold:.2f}_({V14_DRAWDOWN_KILL_FRACTION:.0%}_of_cap)"
        )

    # Consecutive losses: scan closed pool in reverse, count from latest
    closed_orders = list(om.state.closed.values())
    closed_orders.sort(key=lambda o: o.resolution_ts or "", reverse=True)
    streak = 0
    for o in closed_orders:
        pnl = o.realized_pnl_usd
        if pnl is None or pnl >= 0:
            break
        streak += 1
        if streak >= V14_CONSECUTIVE_LOSS_KILL:
            return True, f"consecutive_losses_{streak}"

    # Daily order cap: how many placements today (UTC)
    today_str = now_utc().strftime("%Y-%m-%d")
    placed_today = 0
    for pool in (om.state.intents, om.state.resting, om.state.filled, om.state.closed):
        for o in pool.values():
            placed_ts = o.placed_ts or ""
            if placed_ts.startswith(today_str):
                placed_today += 1
    if placed_today >= V14_MAX_DAILY_ORDERS:
        return True, f"daily_cap_hit_{placed_today}_orders"

    return False, ""


def one_loop(
    odds_client: httpx.Client, kc: KalshiClient, om: LiveOrderManager, dry_run: bool
) -> dict:
    summary = {
        "ts": now_utc().isoformat(), "fires": 0, "placements": 0,
        "skipped_v1_collision": 0, "skipped_v14_dedup": 0,
        "skipped_no_ticker": 0, "skipped_no_cash": 0,
        "skipped_kill": 0, "skipped_outside_window": 0,
        "skipped_no_historical": 0, "credits_remaining": -1, "errors": [],
    }
    if STOP_FILE.exists():
        summary["errors"].append("STOP file present; daemon should exit")
        return summary

    paused = PAUSE_FILE.exists()

    # Pull Kalshi balance early (also used below). Compute dynamic v14 cap.
    try:
        cash_usd, positions_usd = fetch_kalshi_balance(kc)
    except Exception as e:
        summary["errors"].append(f"balance_read_error: {type(e).__name__}: {e}")
        return summary
    total_bankroll = cash_usd + positions_usd
    v14_cap_usd = V14_BANKROLL_FRACTION * total_bankroll
    summary["kalshi_cash_usd"] = round(cash_usd, 2)
    summary["kalshi_positions_usd"] = round(positions_usd, 2)
    summary["kalshi_total_bankroll_usd"] = round(total_bankroll, 2)
    summary["v14_dynamic_cap_usd"] = round(v14_cap_usd, 2)

    # Kill trigger check (uses dynamic v14 cap, not hardcoded)
    tripped, reason = check_kill_triggers(om, v14_cap_usd)
    if tripped:
        summary["skipped_kill"] = 1
        summary["errors"].append(f"kill_tripped: {reason}")
        log_event({"event": "kill_trigger", "reason": reason})
        discord_notify(f"v14 KILL TRIGGER: {reason}")
        return summary

    # Pull odds
    now = now_utc()
    historical_target = now - timedelta(hours=LOOKBACK_HOURS)
    try:
        current_games, rem1 = fetch_odds_snapshot(odds_client, KEY)
        hist_games, rem2 = fetch_odds_snapshot(odds_client, KEY, when=historical_target)
        summary["credits_remaining"] = rem2
    except httpx.HTTPStatusError as e:
        summary["errors"].append(f"odds_api_error: {e.response.status_code}")
        return summary
    hist_by_id = {g.get("id"): g for g in hist_games if g.get("id")}

    # Pull Kalshi open MLB markets
    try:
        open_markets = fetch_kalshi_open_mlb_markets(kc)
    except Exception as e:
        summary["errors"].append(f"kalshi_markets_error: {type(e).__name__}: {e}")
        return summary

    # Sync state.json with Kalshi reality + rotate stale orders
    sync_summary = sync_with_kalshi_orders(om, kc)
    if sync_summary.get("externally_cancelled", 0) > 0:
        summary["externally_cancelled"] = sync_summary["externally_cancelled"]
    stale_summary = cancel_v14_stale_orders(om, kc, open_markets)
    for k in ("cancelled_near_close", "cancelled_stale_age", "cancelled_drift"):
        if stale_summary.get(k, 0) > 0:
            summary[k] = stale_summary[k]
    for err in sync_summary.get("errors", []) + stale_summary.get("errors", []):
        summary["errors"].append(err)

    summary["kalshi_open_mlb_markets"] = len(open_markets)
    v14_exposure = compute_v14_exposure(om)
    summary["v14_current_exposure_usd"] = round(v14_exposure, 2)
    headroom_v14 = v14_cap_usd - v14_exposure
    summary["v14_headroom_usd"] = round(headroom_v14, 2)

    # Headroom floor: need at least enough room for ONE contract at typical
    # MLB-night execution price ($0.40 to $0.55). $0.55 is a conservative
    # floor; below this v14 can't even place a single contract. We DO NOT
    # require V14_PER_TRADE_USD of headroom here, because the per-fire
    # sizing logic below will scale contracts down to whatever fits.
    if headroom_v14 < 0.55:
        summary["errors"].append(
            f"v14_headroom_below_one_contract: {headroom_v14:.2f} < 0.55"
        )
        return summary

    for g in current_games:
        gid = g.get("id")
        commence_str = g.get("commence_time")
        if not gid or not commence_str:
            continue
        commence = pd.Timestamp(commence_str).tz_convert("UTC").to_pydatetime()
        hours_to_commence = (commence - now).total_seconds() / 3600.0
        if not (EXEC_WINDOW_MIN_H <= hours_to_commence <= EXEC_WINDOW_MAX_H):
            summary["skipped_outside_window"] += 1
            continue
        hist_g = hist_by_id.get(gid)
        if hist_g is None:
            summary["skipped_no_historical"] += 1
            continue
        p_cur = home_implied_median(g)
        p_hist = home_implied_median(hist_g)
        if p_cur is None or p_hist is None:
            continue
        delta = p_cur - p_hist
        if abs(delta) < X_THRESHOLD:
            continue
        summary["fires"] += 1
        take_home_side = delta > 0
        ticker = find_kalshi_ticker_for_side(
            open_markets, g.get("home_team"), g.get("away_team"),
            commence, take_home_side,
        )
        if ticker is None:
            summary["skipped_no_ticker"] += 1
            log_event({
                "event": "fire_skipped_no_ticker",
                "home": g.get("home_team"), "away": g.get("away_team"),
                "commence": commence_str, "delta_sb_home": round(delta, 4),
                "take_home_side": take_home_side,
            })
            continue
        if v1_holds_ticker(ticker):
            summary["skipped_v1_collision"] += 1
            log_event({"event": "fire_skipped_v1_collision", "ticker": ticker})
            continue
        if v14_holds_ticker(om, ticker):
            summary["skipped_v14_dedup"] += 1
            log_event({"event": "fire_skipped_v14_dedup", "ticker": ticker})
            continue
        # Compute target price
        target_implied = p_cur if take_home_side else 1.0 - p_cur
        target_price = min(0.99, target_implied + HAIRCUT + SAFETY_BUFFER)
        target_price = max(0.01, target_price)
        # Size from per-fire budget: aim for V14_PER_TRADE_USD of total
        # exposure on this fire. Floor at 1 contract so the strategy still
        # fires even if budget < target_price (preserves pre-2026-05-28
        # behavior when V14_PER_TRADE_USD ~= 0.95 ~= target_price).
        contracts = max(1, int(V14_PER_TRADE_USD // target_price))
        # Trim if either cash or v14 headroom is tighter than the budget,
        # so we still place SOMETHING rather than skip on borderline cash.
        per_contract_cost = target_price
        max_by_cash = int(cash_usd // per_contract_cost)
        max_by_v14 = int(headroom_v14 // per_contract_cost)
        contracts = min(contracts, max_by_cash, max_by_v14)
        if contracts < 1:
            summary["skipped_no_cash"] += 1
            log_event({
                "event": "fire_skipped_no_cash",
                "ticker": ticker, "per_contract_cost": per_contract_cost,
                "kalshi_cash": cash_usd, "v14_headroom": headroom_v14,
                "budget_usd": V14_PER_TRADE_USD,
            })
            continue
        order_cost = per_contract_cost * contracts
        # Place
        log_event({
            "event": "fire_placement_attempt",
            "ticker": ticker, "side": "yes_buy",
            "target_price": round(target_price, 4),
            "contracts": contracts, "order_cost_usd": round(order_cost, 4),
            "home": g.get("home_team"), "away": g.get("away_team"),
            "take_home_side": take_home_side, "delta_sb_home": round(delta, 4),
            "dry_run": dry_run,
        })
        if dry_run:
            summary["placements"] += 1
            continue
        try:
            order = om.place_live_order(
                ticker=ticker,
                series_ticker="KXMLBGAME",
                event_ticker=ticker.rsplit("-", 1)[0],
                target_price=target_price,
                contracts=contracts,
                expected_net_edge=0.15,  # v14 expected mean per backtest
                market_mid_at_placement=target_implied,
            )
            summary["placements"] += 1
            log_event({
                "event": "fire_placement_result",
                "ticker": ticker, "intent_id": order.intent_id,
                "status": order.status.value,
                "order_id": order.order_id,
                "contracts": contracts,
                "order_cost_usd": round(order_cost, 4),
            })
            discord_notify(
                f"v14 PLACED {ticker} YES BUY {contracts}c @ ${target_price:.2f} "
                f"= ${order_cost:.2f} (delta_sb {delta:+.4f}; "
                f"status {order.status.value})"
            )
            cash_usd -= order_cost
            headroom_v14 -= order_cost
        except Exception as e:
            summary["errors"].append(f"place_error: {type(e).__name__}: {e}")
            log_event({"event": "fire_placement_failed", "ticker": ticker, "error": str(e)})
            discord_notify(
                f"v14 PLACE FAILED {ticker}: {type(e).__name__}: {e}"
            )

    return summary


def _v14_post_loop_heartbeat(om: LiveOrderManager, summary: dict) -> None:
    """Post a per-loop Discord heartbeat in the same format as v1.

    Uses the live Kalshi balance numbers already in `summary` (read at
    the top of one_loop), so no extra API calls. Skip-counts surface
    every non-zero skip reason from the loop. Safe-no-op if Discord
    isn't configured.
    """
    if not DISCORD_WEBHOOK_URL or format_loop_heartbeat is None:
        return
    skip_counts: dict[str, int] = {}
    skip_map = {
        "skipped_outside_window": "outside_window",
        "skipped_no_historical": "no_historical",
        "skipped_no_ticker": "no_ticker",
        "skipped_v1_collision": "v1_collision",
        "skipped_v14_dedup": "v14_dedup",
        "skipped_no_cash": "no_cash",
        "skipped_kill": "kill",
    }
    for src, label in skip_map.items():
        v = int(summary.get(src) or 0)
        if v:
            skip_counts[label] = v
    extras = [
        f"fires={summary.get('fires', 0)} "
        f"placements={summary.get('placements', 0)} "
        f"open_mkts={summary.get('kalshi_open_mlb_markets', 0)} "
        f"credits={summary.get('credits_remaining', 0)}",
        f"v14_exposure=${summary.get('v14_current_exposure_usd', 0):.2f} "
        f"/ cap ${summary.get('v14_dynamic_cap_usd', 0):.2f} "
        f"(headroom ${summary.get('v14_headroom_usd', 0):.2f})",
        f"resting={len(om.state.resting)} "
        f"filled={len(om.state.filled)} "
        f"closed={len(om.state.closed)} "
        f"realized_pnl=${om.state.realized_pnl_total_usd:+.2f}",
    ]
    errors = summary.get("errors") or []
    if errors:
        extras.append(f"errors: {'; '.join(str(e) for e in errors[:3])}")
    msg = format_loop_heartbeat(
        bot_name="v14",
        cash_usd=summary.get("kalshi_cash_usd"),
        positions_usd=summary.get("kalshi_positions_usd"),
        placed=int(summary.get("placements") or 0),
        skip_counts=skip_counts,
        extra_lines=extras,
    )
    discord_notify(msg)


def main() -> int:
    if not KEY:
        print("FATAL: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
        return 2
    dry_run = PAPER_MODE_FILE.exists()
    print(f"v14 daemon starting (dry_run={dry_run})", flush=True)
    discord_notify(
        f"v14 STARTED (dry_run={dry_run}); fraction={V14_BANKROLL_FRACTION:.0%}; "
        f"X_threshold={X_THRESHOLD*10000:.0f}bp"
    )
    settings = Settings()
    with KalshiClient(settings) as kc:
        # intent_id_prefix '14' tags every v14-placed order's client_order_id.
        # Visible on Kalshi as the first 2 hex chars of order_id; survives
        # any state.json loss as a stable bot-ownership marker.
        om = LiveOrderManager(
            kc, state_path=V14_STATE_PATH, intent_id_prefix="14",
        )
        # Initialize starting_bankroll on first run by reading Kalshi total
        if om.state.starting_bankroll_usd in (None, 25.0, 0.0):
            try:
                init_cash, init_pos = fetch_kalshi_balance(kc)
                init_total = init_cash + init_pos
                init_cap = V14_BANKROLL_FRACTION * init_total
                om.state.starting_bankroll_usd = init_cap
                om._save()
                log_event({
                    "event": "v14_state_initialized",
                    "kalshi_total_bankroll": round(init_total, 2),
                    "v14_initial_cap": round(init_cap, 2),
                    "fraction": V14_BANKROLL_FRACTION,
                })
            except Exception as exc:
                log_event({
                    "event": "v14_init_balance_read_failed",
                    "error": str(exc),
                })

        with httpx.Client() as oddsc:
            while True:
                if STOP_FILE.exists():
                    print("STOP file present; exiting cleanly", flush=True)
                    log_event({"event": "daemon_stopped_via_stop_file"})
                    break
                if not is_active_hour(now_utc()):
                    print(f"  {now_utc().isoformat()} outside active hours; sleeping", flush=True)
                    time.sleep(LOOP_INTERVAL_SECONDS)
                    continue
                try:
                    summary = one_loop(oddsc, kc, om, dry_run)
                    print(f"  loop summary: {summary}", flush=True)
                    log_event({"event": "loop_summary", **summary})
                    _v14_post_loop_heartbeat(om, summary)
                except Exception as e:
                    print(f"  loop error: {e}", flush=True)
                    log_event({"event": "loop_error", "error": str(e), "type": type(e).__name__})
                    discord_notify(f"v14 LOOP ERROR: {type(e).__name__}: {e}")
                time.sleep(LOOP_INTERVAL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
