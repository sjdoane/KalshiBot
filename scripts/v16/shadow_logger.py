"""v16 lead-lag shadow logger: RECORD-ONLY (Round 21).

Standalone process that measures, F11-free and going forward, whether Kalshi
lags the sportsbook and whether the lag is capturable at EXECUTABLE prices.
It NEVER places or cancels orders and shares NO mutable state with the live
v14 daemon. It only reads the same odds and orderbook endpoints and appends
record rows to data/v16/shadow/*.parquet. The locked gate design is in
research/v16/01-methodology-lock.md.

Each loop (during MLB-night active hours):
1. Pull the-odds-api current + 3h-ago MLB odds (same as the v14 daemon).
2. Pull open KXMLBGAME markets (for ticker match + close_time).
3. For each game in the [T-3h, T-1h] window with a 3h-ago match, compute
   delta_sb_home. If |delta| >= 30bp, match the Kalshi ticker for the side
   the book moved toward, read the LIVE executable Kalshi book, and append an
   entry row (classification "fire" at >= 60bp, else "near_miss"). First
   capture per (game, side, night, classification) is binding.
4. Opportunistic close snapshot: for any logged FIRE whose close_time is near,
   read the book again and append a closes row (the Gate A exit leg). The
   robust close/intra-window poller is Phase 2; Phase 1 captures the scarce
   entry data plus a best-effort close.

Manual launch (operator):

    cd "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi"
    .venv\\Scripts\\python.exe scripts\\v16\\shadow_logger.py

Stop by creating data/v16/shadow/STOP. Single-instance locked.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))
sys.path.insert(0, str(BASE / "scripts" / "v11"))

load_dotenv(BASE / ".env")

from kalshi_bot.analysis.lead_lag_shadow import (  # noqa: E402
    LOOKBACK_HOURS,
    SNAPSHOT_LABELS,
    build_entry_row,
    classify_delta,
    dedup_key,
    eastern_date_str,
    home_implied_median,
    in_exec_window,
    parse_orderbook,
    parse_trade_yes_cents,
    snapshot_target_time,
    summarize_yes_prices,
)
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot.strategy.single_instance import (  # noqa: E402
    acquire_live_lock,
    release_live_lock,
)
from kalshi_bot_v14.ticker_match import find_kalshi_ticker_for_side  # noqa: E402

KEY = os.environ.get("THE_ODDS_API_KEY")

LOOP_INTERVAL_SECONDS = int(os.environ.get("V16_LOOP_SECONDS", str(5 * 60)))
# Odds fetches (the-odds-api credits) are throttled INDEPENDENTLY of the loop
# cadence: the loop runs every LOOP_INTERVAL for precise, free Kalshi
# re-snapshots, but the 2 odds calls per fetch are made at most once per
# ODDS_FETCH_INTERVAL. This keeps a season-long run inside the the-odds-api
# credit budget while preserving re-snapshot timing. Default 15 min matches the
# v14 daemon's proven-sustainable odds cadence; a fire is a 3h-slow signal so
# 15-min detection granularity loses nothing. Tune via V16_ODDS_SECONDS.
ODDS_FETCH_INTERVAL_SECONDS = int(os.environ.get("V16_ODDS_SECONDS", str(15 * 60)))
ACTIVE_HOUR_UTC_START = 18
ACTIVE_HOUR_UTC_END = 6
# A re-snapshot whose target time has passed by more than this many minutes
# without capture is recorded with snapshot_status="late" (still useful data,
# but flagged), and once a fire is past its close_time it is closed out so the
# scheduler stops revisiting it. The 5-min loop normally lands within grace.
SNAP_LATE_GRACE_MIN = 7.0

DATA_DIR = BASE / "data" / "v16" / "shadow"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ENTRIES_PATH = DATA_DIR / "entries.parquet"
SNAPSHOTS_PATH = DATA_DIR / "snapshots.parquet"
STATE_PATH = DATA_DIR / "logger_state.json"
EVENT_LOG = DATA_DIR / "events.jsonl"
STOP_FILE = DATA_DIR / "STOP"
LOCK_PATH = DATA_DIR / "shadow_logger.lock"
PID_PATH = DATA_DIR / "shadow_logger.pid"


def now_utc() -> datetime:
    return datetime.now(UTC)


def is_active_hour(dt: datetime) -> bool:
    h = dt.hour
    return h >= ACTIVE_HOUR_UTC_START or h < ACTIVE_HOUR_UTC_END


def log_event(payload: dict) -> None:
    payload.setdefault("ts_utc", now_utc().isoformat())
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def load_state() -> dict:
    """Persisted dedup + re-snapshot bookkeeping (NOT trade/order state).

    logged_keys: set of "{game}|{side}|{night}|{class}" already entry-logged.
    snap_state: per fire_key "{game}|{side}|{night}" -> {"captured": [labels],
    "last_snap_ts": iso}, tracking which re-snapshots (t5/t30/close) are done
    and the high-water trade-tape timestamp for non-overlapping interval stats.
    """
    if not STATE_PATH.exists():
        return {"logged_keys": [], "snap_state": {}, "last_odds_fetch_ts": ""}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"logged_keys": [], "snap_state": {}, "last_odds_fetch_ts": ""}
    raw.setdefault("logged_keys", [])
    raw.setdefault("snap_state", {})
    raw.setdefault("last_odds_fetch_ts", "")
    return raw


def _odds_due(state: dict, now: datetime) -> bool:
    """True when at least ODDS_FETCH_INTERVAL has elapsed since the last odds
    fetch (or none has happened). Decouples credit spend from the loop cadence."""
    last = state.get("last_odds_fetch_ts") or ""
    if not last:
        return True
    try:
        prev = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return True
    return (now - prev).total_seconds() >= ODDS_FETCH_INTERVAL_SECONDS


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATE_PATH)


def append_rows(path: Path, rows: list[dict]) -> None:
    """Append rows to a parquet file (read-concat-write). Volume is a handful
    of rows per night, so the simple path is fine and avoids a DB dependency
    (OneDrive forbids SQLite/WAL here)."""
    if not rows:
        return
    new = pd.DataFrame(rows)
    if path.exists():
        try:
            existing = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            # Never clobber accumulated history on a transient read error. Write
            # this loop's rows to an independent timestamped recovery sidecar the
            # operator can merge later, and leave the main file untouched. A
            # season of data is too costly to truncate on one bad read.
            recovery = path.with_name(
                f"{path.stem}.recovery.{now_utc().strftime('%Y%m%dT%H%M%S')}.parquet"
            )
            new.to_parquet(recovery, index=False)
            log_event({
                "event": "parquet_read_failed_recovery_written",
                "path": str(path), "recovery": str(recovery), "error": str(exc),
            })
            return
        combined = pd.concat([existing, new], ignore_index=True)
    else:
        combined = new
    tmp = path.with_suffix(".tmp.parquet")
    combined.to_parquet(tmp, index=False)
    tmp.replace(path)


def fetch_odds_snapshot(
    client: httpx.Client, when: datetime | None = None
) -> tuple[list[dict], int, str]:
    """Pull h2h MLB odds (current if when is None, else historical at the hour).

    Returns (games, credits_remaining, snapshot_ts_iso).
    """
    if when is None:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
        params = {"apiKey": KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal"}
        snap_ts = ""
    else:
        iso = when.astimezone(UTC).strftime("%Y-%m-%dT%H:00:00Z")
        url = "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds"
        params = {
            "apiKey": KEY, "regions": "us", "markets": "h2h",
            "date": iso, "oddsFormat": "decimal",
        }
        snap_ts = iso
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    games = body if when is None else body.get("data", [])
    remaining = int(r.headers.get("x-requests-remaining", -1))
    return games, remaining, snap_ts


def fetch_open_mlb_markets(kc: KalshiClient) -> list[dict]:
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


def read_book(kc: KalshiClient, ticker: str) -> dict:
    """Read and parse the live Kalshi orderbook for a ticker. Returns the
    parse_orderbook dict; on API failure returns an empty-book dict with an
    error flag so the row is auditable, never silently dropped."""
    try:
        payload = kc.get(f"/markets/{ticker}/orderbook")
    except Exception as exc:  # noqa: BLE001
        log_event({"event": "orderbook_fetch_failed", "ticker": ticker, "error": str(exc)})
        return {
            "yes_bid": None, "yes_ask": None, "yes_depth": 0.0, "no_depth": 0.0,
            "mid": None, "is_parity_derived": False, "book_empty": True,
            "fetch_error": True,
        }
    return parse_orderbook(payload)


def fetch_yes_trade_prices(
    kc: KalshiClient, ticker: str, since: datetime, until: datetime
) -> list[float]:
    """Pull recent trades for a ticker and return yes prices (cents) for
    trades whose created_time falls in (since, until]. Read-only; on failure
    returns an empty list (the snapshot row will record n_trades=0, which is
    distinguishable from a genuine zero-trade interval only via the logged
    fetch error, so failures are also logged)."""
    prices: list[float] = []
    try:
        # Bound the query server-side by min_ts (unix seconds) so a heavy
        # interval is not silently truncated to only the most-recent page of
        # trades; the client-side (since, until] filter below is the
        # authoritative half-open guard in case the server ignores min_ts.
        trades = list(kc.paginate(
            "/markets/trades", item_key="trades", limit=1000,
            ticker=ticker, min_ts=int(since.timestamp()), max_pages=20,
        ))
    except Exception as exc:  # noqa: BLE001
        log_event({"event": "trades_fetch_failed", "ticker": ticker, "error": str(exc)})
        return prices
    for t in trades:
        ct = t.get("created_time")
        if not ct:
            continue
        try:
            ts = pd.Timestamp(ct).tz_convert("UTC").to_pydatetime()
        except Exception:  # noqa: BLE001
            continue
        if since < ts <= until:
            yp = parse_trade_yes_cents(t)
            if yp is not None:
                prices.append(yp)
    return prices


def _snap_row(
    *, e: dict, label: str, target: datetime | None, now: datetime,
    book: dict, tsum: dict, book_status: str, snapshot_status: str,
) -> dict:
    """Assemble one fixed-schema re-snapshot row (consistent keys every time so
    the parquet append never drifts). book_status describes the book itself
    ("ok"/"empty"/"fetch_error"); snapshot_status describes the schedule outcome
    ("done"/"late"/"missed"/"unschedulable"). They are kept distinct so the Gate
    A exit-leg book validity is auditable separately from timing."""
    commence_ts = e.get("commence_ts") or ""
    close_time = e.get("close_time") or ""
    minutes_to_commence = None
    if commence_ts:
        try:
            cdt = pd.Timestamp(commence_ts).tz_convert("UTC").to_pydatetime()
            minutes_to_commence = round((cdt - now).total_seconds() / 60.0, 2)
        except Exception:  # noqa: BLE001
            minutes_to_commence = None
    minutes_to_close = None
    if close_time:
        try:
            cdt = pd.Timestamp(close_time).tz_convert("UTC").to_pydatetime()
            minutes_to_close = round((cdt - now).total_seconds() / 60.0, 2)
        except Exception:  # noqa: BLE001
            minutes_to_close = None
    minutes_late = None
    if target is not None:
        minutes_late = round((now - target).total_seconds() / 60.0, 2)
    return {
        "game_id": e.get("game_id") or "", "side": e.get("side") or "",
        "night_id": e.get("night_id") or "", "ticker": e.get("ticker") or "",
        "snapshot_label": label,
        "target_ts": target.isoformat() if target is not None else "",
        "captured_ts": now.isoformat(),
        "minutes_late": minutes_late,
        "minutes_to_commence": minutes_to_commence,
        "minutes_to_close": minutes_to_close,
        "yes_bid": book.get("yes_bid"), "yes_ask": book.get("yes_ask"),
        "yes_depth": book.get("yes_depth", 0.0), "no_depth": book.get("no_depth", 0.0),
        "mid": book.get("mid"),
        "is_parity_derived": book.get("is_parity_derived", False),
        "book_empty": book.get("book_empty", True),
        "book_status": book_status,
        "trade_n": tsum.get("n_trades", 0),
        "trade_min_yes_cents": tsum.get("min_yes_cents"),
        "trade_max_yes_cents": tsum.get("max_yes_cents"),
        "trade_mean_yes_cents": tsum.get("mean_yes_cents"),
        "snapshot_status": snapshot_status,
    }


_EMPTY_BOOK = {
    "yes_bid": None, "yes_ask": None, "yes_depth": 0.0, "no_depth": 0.0,
    "mid": None, "is_parity_derived": False, "book_empty": True,
}
_EMPTY_TSUM = {
    "n_trades": 0, "min_yes_cents": None, "max_yes_cents": None, "mean_yes_cents": None,
}


def _resnapshot_pass(
    kc: KalshiClient, now: datetime, snap_state: dict, summary: dict
) -> list[dict]:
    """Capture due re-snapshots (t5/t30/close) for logged fires. Mutates
    snap_state in place (per fire_key: captured labels + last_snap_ts high
    water). Returns the rows to append. Record-only; never places orders."""
    rows: list[dict] = []
    if not ENTRIES_PATH.exists():
        return rows
    try:
        entries_df = pd.read_parquet(ENTRIES_PATH)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"entries_read_failed: {exc}")
        return rows
    fires = entries_df[entries_df["fired"] == True]  # noqa: E712
    for _idx, e in fires.iterrows():
        ticker = e.get("ticker") or ""
        if not ticker:
            continue
        try:
            fire_ts = pd.Timestamp(e.get("captured_ts")).tz_convert("UTC").to_pydatetime()
        except Exception:  # noqa: BLE001
            continue
        close_dt: datetime | None = None
        close_str = e.get("close_time") or ""
        if close_str:
            try:
                close_dt = pd.Timestamp(close_str).tz_convert("UTC").to_pydatetime()
            except Exception:  # noqa: BLE001
                close_dt = None
        fire_key = f"{e.get('game_id')}|{e.get('side')}|{e.get('night_id')}"
        st = snap_state.setdefault(
            fire_key, {"captured": [], "last_snap_ts": fire_ts.isoformat()}
        )
        captured = set(st["captured"])
        if len(captured) >= len(SNAPSHOT_LABELS):
            continue
        try:
            since = pd.Timestamp(st["last_snap_ts"]).tz_convert("UTC").to_pydatetime()
        except Exception:  # noqa: BLE001
            since = fire_ts
        past_close = close_dt is not None and now > close_dt
        for label in SNAPSHOT_LABELS:
            if label in captured:
                continue
            target = snapshot_target_time(label, fire_ts, close_dt)
            if target is None:
                # Unschedulable (close label with no close_time). Record once
                # so the gap is auditable, then stop retrying.
                rows.append(_snap_row(
                    e=dict(e), label=label, target=None, now=now,
                    book=_EMPTY_BOOK, tsum=_EMPTY_TSUM,
                    book_status="empty", snapshot_status="unschedulable",
                ))
                captured.add(label)
                continue
            if now < target:
                continue  # not due yet; revisit next loop
            if past_close and label != "close":
                # The intra-window time is long gone (process was down). Record
                # an explicit missed row (no book) rather than a silent absence.
                rows.append(_snap_row(
                    e=dict(e), label=label, target=target, now=now,
                    book=_EMPTY_BOOK, tsum=_EMPTY_TSUM,
                    book_status="empty", snapshot_status="missed",
                ))
                captured.add(label)
                continue
            book = read_book(kc, ticker)
            prices = fetch_yes_trade_prices(kc, ticker, since, now)
            tsum = summarize_yes_prices(prices)
            minutes_late = (now - target).total_seconds() / 60.0
            if book.get("fetch_error"):
                book_status = "fetch_error"
            elif book.get("book_empty"):
                book_status = "empty"
            else:
                book_status = "ok"
            snapshot_status = "late" if minutes_late > SNAP_LATE_GRACE_MIN else "done"
            rows.append(_snap_row(
                e=dict(e), label=label, target=target, now=now,
                book=book, tsum=tsum,
                book_status=book_status, snapshot_status=snapshot_status,
            ))
            captured.add(label)
            since = now
            st["last_snap_ts"] = now.isoformat()
            summary["snapshots"] = summary.get("snapshots", 0) + 1
            log_event({
                "event": "resnapshot", "ticker": ticker, "label": label,
                "book_status": book_status, "snapshot_status": snapshot_status,
                "yes_bid": book.get("yes_bid"), "yes_ask": book.get("yes_ask"),
                "trade_n": tsum.get("n_trades", 0),
            })
        st["captured"] = sorted(captured)
    return rows


def _detect_and_log_fires(
    kc: KalshiClient,
    current_games: list[dict],
    hist_by_id: dict,
    open_markets: list[dict],
    snap_ts: str,
    now: datetime,
    state: dict,
    summary: dict,
) -> None:
    """Fire-detection pass: for each game in the [T-3h, T-1h] window with a
    3h-ago match and a >= 30bp move, log one entry row (first capture per
    game/side/night/class is binding). Appends to entries.parquet and updates
    state['logged_keys']. Record-only."""
    market_by_ticker = {m.get("ticker"): m for m in open_markets}
    logged_keys = set(state["logged_keys"])
    entry_rows: list[dict] = []
    for g in current_games:
        gid = g.get("id")
        commence_str = g.get("commence_time")
        if not gid or not commence_str:
            continue
        commence = pd.Timestamp(commence_str).tz_convert("UTC").to_pydatetime()
        hours_to_commence = (commence - now).total_seconds() / 3600.0
        if not in_exec_window(hours_to_commence):
            continue
        hist_g = hist_by_id.get(gid)
        if hist_g is None:
            continue
        p_cur = home_implied_median(g)
        p_hist = home_implied_median(hist_g)
        if p_cur is None or p_hist is None:
            continue
        delta = p_cur - p_hist
        classification = classify_delta(delta)
        if classification is None:
            continue
        summary["candidates"] += 1
        if classification == "fire":
            summary["fires"] += 1
        else:
            summary["near_misses"] += 1
        take_home_side = delta > 0
        side = "home" if take_home_side else "away"
        night_id = eastern_date_str(commence)
        key = f"{dedup_key(gid, side, night_id)}|{classification}"
        if key in logged_keys:
            continue
        ticker = find_kalshi_ticker_for_side(
            open_markets, g.get("home_team"), g.get("away_team"),
            commence, take_home_side,
        ) or ""
        book = read_book(kc, ticker) if ticker else {
            "yes_bid": None, "yes_ask": None, "yes_depth": 0.0, "no_depth": 0.0,
            "mid": None, "is_parity_derived": False, "book_empty": True,
        }
        if not ticker:
            book_status = "no_ticker"
        elif book.get("fetch_error"):
            book_status = "fetch_error"
        elif book.get("book_empty"):
            book_status = "empty"
        else:
            book_status = "ok"
        close_time = ""
        if ticker and ticker in market_by_ticker:
            close_time = market_by_ticker[ticker].get("close_time") or ""
        row = build_entry_row(
            captured_ts=now, game=g, delta_sb_home=delta, p_cur=p_cur, p_hist=p_hist,
            odds_snapshot_ts=snap_ts, take_home_side=take_home_side,
            classification=classification, ticker=ticker, commence=commence,
            close_time=close_time, book=book, fire_seq=0, book_status=book_status,
        )
        entry_rows.append(row)
        logged_keys.add(key)
        summary["entries_logged"] += 1
        log_event({
            "event": "entry_logged", "ticker": ticker, "side": side,
            "classification": classification, "delta_sb_home": round(delta, 4),
            "yes_ask": book.get("yes_ask"), "target_implied": row["target_implied"],
        })
    append_rows(ENTRIES_PATH, entry_rows)
    state["logged_keys"] = sorted(logged_keys)


def one_loop(odds_client: httpx.Client, kc: KalshiClient, state: dict) -> dict:
    summary = {
        "ts": now_utc().isoformat(), "candidates": 0, "fires": 0, "near_misses": 0,
        "entries_logged": 0, "snapshots": 0, "credits_remaining": -1, "errors": [],
    }
    if STOP_FILE.exists():
        summary["errors"].append("STOP file present")
        return summary

    now = now_utc()
    snap_state: dict = state["snap_state"]
    summary["odds_due"] = _odds_due(state, now)

    # Fire detection (the only odds-credit consumer) runs at most once per
    # ODDS_FETCH_INTERVAL. Re-snapshots below run EVERY loop regardless, since
    # they are free Kalshi reads and their timing must stay precise.
    if summary["odds_due"]:
        current_games: list[dict] | None
        try:
            current_games, rem1, _ = fetch_odds_snapshot(odds_client)
            hist_games, rem2, snap_ts = fetch_odds_snapshot(
                odds_client, when=now - timedelta(hours=LOOKBACK_HOURS)
            )
            # The CURRENT-odds endpoint returns x-requests-remaining; the
            # historical endpoint does not (returns -1), so prefer rem1.
            summary["credits_remaining"] = rem1 if rem1 >= 0 else rem2
            state["last_odds_fetch_ts"] = now.isoformat()
        except httpx.HTTPStatusError as e:
            summary["errors"].append(f"odds_api_error: {e.response.status_code}")
            current_games = None
        except Exception as e:  # noqa: BLE001
            summary["errors"].append(f"odds_error: {type(e).__name__}: {e}")
            current_games = None

        if current_games is not None:
            hist_by_id = {g.get("id"): g for g in hist_games if g.get("id")}
            try:
                open_markets: list[dict] | None = fetch_open_mlb_markets(kc)
            except Exception as e:  # noqa: BLE001
                summary["errors"].append(f"markets_error: {type(e).__name__}: {e}")
                open_markets = None
            if open_markets is not None:
                _detect_and_log_fires(
                    kc, current_games, hist_by_id, open_markets, snap_ts,
                    now, state, summary,
                )

    # Phase 2: scheduled re-snapshots (t5 / t30 / close) for logged FIRES, each
    # with the live executable book PLUS the trade tape since the previous
    # snapshot (non-overlapping intervals). The book path feeds Gate A (CLV to
    # the closing executable price); the trade tape feeds any later, post-
    # registration passive-fill model for Gate B. Record-only; runs every loop.
    snap_rows = _resnapshot_pass(kc, now, snap_state, summary)
    append_rows(SNAPSHOTS_PATH, snap_rows)

    state["snap_state"] = snap_state
    save_state(state)
    return summary


def main() -> int:
    if not KEY:
        print("FATAL: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
        return 2
    print("v16 shadow logger starting (record-only; no orders placed)", flush=True)
    acquire_live_lock(lock_path=LOCK_PATH, pid_path=PID_PATH)
    settings = Settings()
    state = load_state()
    try:
        with KalshiClient(settings) as kc, httpx.Client() as oddsc:
            while True:
                if STOP_FILE.exists():
                    print("STOP file present; exiting cleanly", flush=True)
                    log_event({"event": "stopped_via_stop_file"})
                    break
                if not is_active_hour(now_utc()):
                    time.sleep(LOOP_INTERVAL_SECONDS)
                    continue
                try:
                    summary = one_loop(oddsc, kc, state)
                    print(f"  loop: {summary}", flush=True)
                    log_event({"event": "loop_summary", **summary})
                except Exception as e:  # noqa: BLE001
                    print(f"  loop error: {e}", flush=True)
                    log_event({"event": "loop_error", "error": str(e), "type": type(e).__name__})
                time.sleep(LOOP_INTERVAL_SECONDS)
    finally:
        release_live_lock(lock_path=LOCK_PATH, pid_path=PID_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
