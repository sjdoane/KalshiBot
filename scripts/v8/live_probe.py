"""v8 Angle A: continuous live orderbook + naive_p_yes probe for KXBTCD.

Per the v7 Phase 3 critic verdict (research/v7/07-naive-p-yes-critic.md), the
+0.20842 Brier improvement of naive_p_yes over kalshi_mid_at_t is REAL against
the stale last-trade-print baseline but UNCERTAIN against the orderbook
quote baseline. The 188-contract live snapshot at 2026-05-26 19:16 UTC found
0 contracts with strong signals (|naive_p - book_mid| >= 0.10), suggesting
the MMs actively maintain quotes against spot. v8-A's job is to confirm this
via 4-6 hours of continuous recording.

Per-iteration (every 5 min):
  1. Pull /markets?series_ticker=KXBTCD&status=open via existing client.
  2. Pull current Coinbase BTC-USD spot.
  3. Pull 120 min of 1m Coinbase candles, compute log-return sigma_1m.
  4. For each open KXBTCD contract closing in 0-60 min:
     a. parse_strike from ticker
     b. pull /markets/{ticker}/orderbook
     c. compute naive_p_yes via Normal-CDF on current spot vs strike,
        sigma scaled by sqrt(mins_to_close)
     d. compute kalshi_mid_from_book = (yes_best_bid + yes_best_ask) / 2
     e. pull /markets/trades for ticker (limit 5), find most recent trade
        and compute kalshi_mid_from_trades + time_since_last_trade_min
     f. compute signal_p_yes_minus_book_mid and _trades_mid
     g. append row to per-run parquet
  5. Write heartbeat with iteration count + timestamp.

Outputs:
  - data/v8/live_probe_YYYYMMDDTHHMMSS.parquet (one file per run, appended each iter)
  - data/v8/heartbeat.txt (overwritten each iteration)
  - data/v8/live_probe_YYYYMMDDTHHMMSS.log (stdout/stderr)

Run:
  .venv-kronos/Scripts/python.exe -m scripts.v8.live_probe --hours 4.0

This script is READ-ONLY against Kalshi (/markets, /markets/.../orderbook,
/markets/trades) and Coinbase public REST. It NEVER calls /portfolio/orders.
"""

from __future__ import annotations

import argparse
import math
import os
import signal
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot_v7.kronos_features import parse_strike  # noqa: E402


OUT_DIR = REPO_ROOT / "data" / "v8"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEARTBEAT_PATH = OUT_DIR / "heartbeat.txt"

# Per the v7 critic, /markets/{ticker}/orderbook returns
# {"orderbook_fp": {"yes_dollars": [[price_str, size_str], ...],
#                   "no_dollars": [[price_str, size_str], ...]}}
# Both arrays are sorted ascending by price. yes_best_bid is the highest
# yes_dollars price; yes_best_ask is derived as 1 - lowest no_dollars price.
# We deliberately use BOTH sides of the book: a thinly populated yes_dollars
# side does not mean the ask is unobservable; the ask is implied by the
# best no_dollars bid via parity (no_bid_dollars + yes_ask_dollars = 1.00).


def log(msg: str) -> None:
    """Stdout logger with iso-utc timestamp."""
    print(f"[{pd.Timestamp.now('UTC').isoformat()}] {msg}", flush=True)


# --- Coinbase helpers (mirroring scripts/v7/critic_live_probe.py) ---


def get_coinbase_spot() -> float:
    """Current Coinbase BTC-USD price."""
    r = requests.get(
        "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        timeout=20,
    )
    r.raise_for_status()
    return float(r.json()["price"])


def get_coinbase_1m_window(end_ts: pd.Timestamp, minutes: int = 120) -> pd.DataFrame:
    """1m candles ending at end_ts, last `minutes` minutes."""
    end_iso = end_ts.isoformat()
    start_iso = (end_ts - pd.Timedelta(minutes=minutes)).isoformat()
    r = requests.get(
        "https://api.exchange.coinbase.com/products/BTC-USD/candles",
        params={"start": start_iso, "end": end_iso, "granularity": 60},
        timeout=30,
    )
    r.raise_for_status()
    candles = r.json()
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(
        candles, columns=["time", "low", "high", "open", "close", "volume"]
    )
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("time").reset_index(drop=True)


def compute_sigma_1m(candles: pd.DataFrame) -> float:
    """Stdev of 1-min log returns over the supplied candle window."""
    if len(candles) < 30:
        return float("nan")
    closes = candles["close"].to_numpy()
    if (closes <= 0).any():
        return float("nan")
    log_returns = np.diff(np.log(closes))
    return float(np.std(log_returns, ddof=1))


# --- naive_p_yes (matches v7 critic_live_probe.py and kronos_features.kronos_to_p_yes_det) ---


def naive_p_yes(spot: float, strike: float, sigma_1m: float, horizon_min: float) -> float:
    """Normal-CDF p_yes from current spot vs strike, vol scaled by sqrt(horizon)."""
    if (
        not math.isfinite(spot)
        or not math.isfinite(strike)
        or not math.isfinite(sigma_1m)
        or not math.isfinite(horizon_min)
        or spot <= 0
        or strike <= 0
        or sigma_1m <= 0
        or horizon_min <= 0
    ):
        return float("nan")
    sigma_h = sigma_1m * math.sqrt(horizon_min)
    if sigma_h <= 0:
        return float("nan")
    z = (math.log(strike) - math.log(spot)) / sigma_h
    p = 1.0 - norm.cdf(z)
    return float(np.clip(p, 1e-3, 1.0 - 1e-3))


# --- orderbook helpers ---


def parse_orderbook(ob: dict) -> dict:
    """Convert /markets/{ticker}/orderbook payload to a flat dict.

    Kalshi returns prices in DOLLARS as strings (e.g. '0.0100'). Both arrays
    are sorted ASCENDING by price. The best YES bid is the highest yes_dollars
    price (last element of yes_dollars). The best NO bid is similarly the
    highest no_dollars price (last element of no_dollars). Best YES ask is
    derived via parity: yes_ask = 1.00 - best_no_bid.

    yes_bid_size_fp = size resting at best yes bid; yes_ask_size_fp = size
    resting at best no bid (since taker of yes-ask hits resting no-bid).

    Returns NaN sentinels if a side is empty.
    """
    obfp = ob.get("orderbook_fp") or {}
    yes_levels = obfp.get("yes_dollars") or []
    no_levels = obfp.get("no_dollars") or []

    # yes_dollars sorted ascending: best yes bid is the LAST entry
    if yes_levels:
        yes_best_bid = float(yes_levels[-1][0])
        yes_best_bid_size = float(yes_levels[-1][1])
        total_depth_yes_bid = float(sum(float(s) for _, s in yes_levels))
    else:
        yes_best_bid = float("nan")
        yes_best_bid_size = float("nan")
        total_depth_yes_bid = 0.0

    # no_dollars sorted ascending: best no bid is the LAST entry
    if no_levels:
        no_best_bid = float(no_levels[-1][0])
        no_best_bid_size = float(no_levels[-1][1])
        # yes_ask = 1.00 - no_best_bid
        yes_best_ask = round(1.0 - no_best_bid, 4)
        yes_best_ask_size = no_best_bid_size
        total_depth_yes_ask = float(sum(float(s) for _, s in no_levels))
    else:
        yes_best_ask = float("nan")
        yes_best_ask_size = float("nan")
        total_depth_yes_ask = 0.0

    return {
        "kalshi_yes_bid": yes_best_bid,
        "kalshi_yes_ask": yes_best_ask,
        "kalshi_yes_bid_size": yes_best_bid_size,
        "kalshi_yes_ask_size": yes_best_ask_size,
        "total_depth_yes_bid": total_depth_yes_bid,
        "total_depth_yes_ask": total_depth_yes_ask,
    }


def fetch_recent_trade(client: KalshiClient, ticker: str) -> tuple[float, float]:
    """Return (kalshi_mid_from_trades, time_since_last_trade_min) for ticker.

    Pulls /markets/trades?ticker=...&limit=1. The most recent trade's
    yes_price_dollars is the proxy for kalshi_mid_from_trades. If no recent
    trades, both fields are NaN.

    Note: this MIRRORS the v6 build_v6_master logic, which uses the last
    yes_price_dollars at the most recent trade <= t. The v7 critic verified
    this is a legitimate AS-OF price (not post-settlement).
    """
    try:
        resp = client.get("/markets/trades", ticker=ticker, limit=1)
    except Exception as e:  # noqa: BLE001
        log(f"  trades fetch failed for {ticker}: {type(e).__name__}: {e}")
        return float("nan"), float("nan")
    trades = resp.get("trades") or []
    if not trades:
        return float("nan"), float("nan")
    last = trades[0]
    try:
        last_px = float(last.get("yes_price_dollars"))
        created = pd.to_datetime(last.get("created_time"), utc=True)
        now = pd.Timestamp.now("UTC")
        tslt_min = float((now - created).total_seconds() / 60.0)
        return last_px, tslt_min
    except Exception:  # noqa: BLE001
        return float("nan"), float("nan")


# --- per-iteration loop ---


def fetch_open_markets(client: KalshiClient) -> pd.DataFrame:
    """Paginate /markets?series_ticker=KXBTCD&status=open. Up to 5 pages."""
    rows: list[dict] = []
    cursor = None
    for _ in range(5):
        params = {"series_ticker": "KXBTCD", "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = client.get("/markets", **params)
        rows.extend(resp.get("markets") or [])
        cursor = resp.get("cursor")
        if not cursor:
            break
    return pd.DataFrame(rows)


def run_iteration(
    client: KalshiClient,
    iter_idx: int,
    out_path: Path,
    max_horizon_min: float,
    inter_contract_sleep_s: float,
) -> dict:
    """Single 5-min iteration. Returns iteration stats dict."""
    iter_ts = pd.Timestamp.now("UTC")
    log(f"iteration {iter_idx} start at {iter_ts.isoformat()}")

    # 1. Coinbase spot
    try:
        spot = get_coinbase_spot()
    except Exception as e:  # noqa: BLE001
        log(f"  coinbase spot failed: {type(e).__name__}: {e}")
        return {"iter_idx": iter_idx, "n_rows": 0, "error": "coinbase_spot"}

    # 2. Coinbase 120m candles -> sigma_1m
    try:
        candles = get_coinbase_1m_window(iter_ts, minutes=120)
        sigma_1m = compute_sigma_1m(candles)
    except Exception as e:  # noqa: BLE001
        log(f"  coinbase candles failed: {type(e).__name__}: {e}")
        sigma_1m = float("nan")
    log(f"  spot=${spot:,.2f} sigma_1m={sigma_1m:.6f} candles={len(candles) if isinstance(candles, pd.DataFrame) else 0}")

    # 3. Open KXBTCD markets
    try:
        markets = fetch_open_markets(client)
    except Exception as e:  # noqa: BLE001
        log(f"  /markets failed: {type(e).__name__}: {e}")
        return {"iter_idx": iter_idx, "n_rows": 0, "error": "markets"}
    if markets.empty:
        log("  no open KXBTCD markets")
        return {"iter_idx": iter_idx, "n_rows": 0, "error": "no_markets"}

    markets["close_dt"] = pd.to_datetime(markets["close_time"], utc=True)
    markets["mins_to_close"] = (
        (markets["close_dt"] - iter_ts).dt.total_seconds() / 60.0
    )
    # Focus on contracts closing in (0, max_horizon_min]. This is the regime
    # where naive_p_yes is best calibrated and most likely tradeable.
    nearclose = markets[
        (markets["mins_to_close"] > 0) & (markets["mins_to_close"] <= max_horizon_min)
    ].copy()
    log(f"  open markets total={len(markets)} near-close (0,{max_horizon_min}]={len(nearclose)}")

    rows: list[dict] = []
    spreads: list[float] = []
    signals: list[float] = []
    for _, m in nearclose.iterrows():
        ticker = m["ticker"]
        try:
            strike = parse_strike(ticker)
        except Exception:  # noqa: BLE001
            continue

        # Orderbook
        try:
            ob = client.get(f"/markets/{ticker}/orderbook")
            ob_parsed = parse_orderbook(ob)
        except Exception as e:  # noqa: BLE001
            log(f"  orderbook failed for {ticker}: {type(e).__name__}: {e}")
            continue

        # Recent trade (optional)
        kalshi_mid_from_trades, tslt_min = fetch_recent_trade(client, ticker)

        # naive_p_yes
        np_yes = naive_p_yes(spot, strike, sigma_1m, m["mins_to_close"])

        # Book mid
        yb = ob_parsed["kalshi_yes_bid"]
        ya = ob_parsed["kalshi_yes_ask"]
        if math.isfinite(yb) and math.isfinite(ya):
            book_mid = (yb + ya) / 2.0
            book_spread = ya - yb
        elif math.isfinite(ya):
            book_mid = ya
            book_spread = float("nan")
        elif math.isfinite(yb):
            book_mid = yb
            book_spread = float("nan")
        else:
            book_mid = float("nan")
            book_spread = float("nan")

        signal_book = (
            np_yes - book_mid
            if math.isfinite(np_yes) and math.isfinite(book_mid)
            else float("nan")
        )
        signal_trades = (
            np_yes - kalshi_mid_from_trades
            if math.isfinite(np_yes) and math.isfinite(kalshi_mid_from_trades)
            else float("nan")
        )

        row = {
            "iter_idx": iter_idx,
            "iter_timestamp": iter_ts,
            "ticker": ticker,
            "event_ticker": m.get("event_ticker"),
            "close_time": m["close_dt"],
            "time_to_close_min": float(m["mins_to_close"]),
            "strike": float(strike),
            "coinbase_spot": float(spot),
            "sigma_1m": float(sigma_1m) if math.isfinite(sigma_1m) else float("nan"),
            "naive_p_yes": float(np_yes) if math.isfinite(np_yes) else float("nan"),
            "kalshi_yes_bid": ob_parsed["kalshi_yes_bid"],
            "kalshi_yes_ask": ob_parsed["kalshi_yes_ask"],
            "kalshi_yes_bid_size": ob_parsed["kalshi_yes_bid_size"],
            "kalshi_yes_ask_size": ob_parsed["kalshi_yes_ask_size"],
            "kalshi_mid_from_book": float(book_mid)
            if math.isfinite(book_mid)
            else float("nan"),
            "kalshi_mid_from_trades": float(kalshi_mid_from_trades)
            if math.isfinite(kalshi_mid_from_trades)
            else float("nan"),
            "time_since_last_trade_min": float(tslt_min)
            if math.isfinite(tslt_min)
            else float("nan"),
            "signal_p_yes_minus_book_mid": float(signal_book)
            if math.isfinite(signal_book)
            else float("nan"),
            "signal_p_yes_minus_trades_mid": float(signal_trades)
            if math.isfinite(signal_trades)
            else float("nan"),
            "book_spread": float(book_spread)
            if math.isfinite(book_spread)
            else float("nan"),
            "total_depth_yes_bid": ob_parsed["total_depth_yes_bid"],
            "total_depth_yes_ask": ob_parsed["total_depth_yes_ask"],
            # +2c-take simulated fill price = current best yes ask (already at ask)
            "sim_take_fill_yes_ask": ob_parsed["kalshi_yes_ask"],
        }
        rows.append(row)
        if math.isfinite(book_spread):
            spreads.append(book_spread)
        if math.isfinite(signal_book):
            signals.append(abs(signal_book))

        # Polite gap between orderbook fetches
        time.sleep(inter_contract_sleep_s)

    if not rows:
        log(f"  iteration {iter_idx}: 0 rows collected")
        return {"iter_idx": iter_idx, "n_rows": 0, "error": "no_rows"}

    df_out = pd.DataFrame(rows)
    # Append to per-run parquet. We rewrite the full file each iteration
    # since pyarrow append-mode is annoying; this is fine for n<5000.
    if out_path.exists():
        prior = pd.read_parquet(out_path)
        df_out = pd.concat([prior, df_out], ignore_index=True)
    df_out.to_parquet(out_path, index=False)

    n_strong_05 = int((df_out.iloc[-len(rows):]["signal_p_yes_minus_book_mid"].abs() >= 0.05).sum())
    n_strong_10 = int((df_out.iloc[-len(rows):]["signal_p_yes_minus_book_mid"].abs() >= 0.10).sum())
    mean_spread = float(np.mean(spreads)) if spreads else float("nan")
    mean_abs_signal = float(np.mean(signals)) if signals else float("nan")
    log(
        f"  iteration {iter_idx} done: n_rows={len(rows)} mean_spread={mean_spread:.4f} "
        f"mean_abs_signal={mean_abs_signal:.4f} strong_05={n_strong_05} strong_10={n_strong_10}"
    )

    # Heartbeat
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            f.write(
                f"iter_idx={iter_idx}\n"
                f"iter_timestamp_utc={iter_ts.isoformat()}\n"
                f"n_rows_this_iter={len(rows)}\n"
                f"total_rows={len(df_out)}\n"
                f"mean_spread={mean_spread:.4f}\n"
                f"mean_abs_signal={mean_abs_signal:.4f}\n"
                f"strong_05={n_strong_05}\n"
                f"strong_10={n_strong_10}\n"
                f"pid={os.getpid()}\n"
                f"out_path={out_path}\n"
            )
    except Exception as e:  # noqa: BLE001
        log(f"  heartbeat write failed: {type(e).__name__}: {e}")

    return {
        "iter_idx": iter_idx,
        "n_rows": len(rows),
        "mean_spread": mean_spread,
        "mean_abs_signal": mean_abs_signal,
        "strong_05": n_strong_05,
        "strong_10": n_strong_10,
        "error": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hours",
        type=float,
        default=4.0,
        help="Wall-clock hours to run (default 4.0).",
    )
    parser.add_argument(
        "--iter-secs",
        type=int,
        default=300,
        help="Seconds between iteration starts (default 300 = 5 min).",
    )
    parser.add_argument(
        "--max-horizon-min",
        type=float,
        default=60.0,
        help="Only sample contracts closing in (0, this] minutes.",
    )
    parser.add_argument(
        "--inter-contract-sleep-s",
        type=float,
        default=0.10,
        help="Sleep between per-contract orderbook fetches (rate-limit guard).",
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        default=None,
        help="Optional iteration count cap (overrides --hours if reached first).",
    )
    parser.add_argument(
        "--output-tag",
        type=str,
        default="",
        help="Optional suffix appended to output filename for distinguishing runs.",
    )
    args = parser.parse_args(argv)

    start_ts = pd.Timestamp.now("UTC")
    stamp = start_ts.strftime("%Y%m%dT%H%M%S")
    tag = f"_{args.output_tag}" if args.output_tag else ""
    out_path = OUT_DIR / f"live_probe_{stamp}{tag}.parquet"
    log(f"v8-A live probe starting at {start_ts.isoformat()}")
    log(f"hours={args.hours} iter_secs={args.iter_secs} max_horizon_min={args.max_horizon_min}")
    log(f"output: {out_path}")
    log(f"pid: {os.getpid()}")

    end_ts = start_ts + pd.Timedelta(hours=args.hours)
    log(f"wall-clock end (scheduled): {end_ts.isoformat()}")

    # Ctrl-C graceful stop
    stop_flag = {"stop": False}

    def handle_signal(signum, frame):  # noqa: ARG001
        log(f"received signal {signum}; stopping after current iteration")
        stop_flag["stop"] = True

    try:
        signal.signal(signal.SIGINT, handle_signal)
    except Exception:  # noqa: BLE001
        pass
    try:
        signal.signal(signal.SIGTERM, handle_signal)
    except Exception:  # noqa: BLE001
        pass

    settings = Settings()
    iter_idx = 0
    with KalshiClient(settings) as client:
        while True:
            iter_idx += 1
            now = pd.Timestamp.now("UTC")
            if now >= end_ts:
                log(f"reached wall-clock cap at {now.isoformat()}; exiting")
                break
            if args.max_iters is not None and iter_idx > args.max_iters:
                log(f"reached --max-iters {args.max_iters}; exiting")
                break

            iter_start = time.time()
            try:
                stats = run_iteration(
                    client=client,
                    iter_idx=iter_idx,
                    out_path=out_path,
                    max_horizon_min=args.max_horizon_min,
                    inter_contract_sleep_s=args.inter_contract_sleep_s,
                )
                log(f"  iteration {iter_idx} stats: {stats}")
            except Exception as e:  # noqa: BLE001
                log(f"  iteration {iter_idx} CRASHED: {type(e).__name__}: {e}")
                traceback.print_exc()

            if stop_flag["stop"]:
                log("stop_flag set; exiting after iteration")
                break

            iter_elapsed = time.time() - iter_start
            sleep_s = max(0.0, args.iter_secs - iter_elapsed)
            if sleep_s > 0:
                # Sleep in chunks so we react to signals promptly
                slept = 0.0
                while slept < sleep_s and not stop_flag["stop"]:
                    chunk = min(5.0, sleep_s - slept)
                    time.sleep(chunk)
                    slept += chunk

    log(f"v8-A live probe finished at {pd.Timestamp.now('UTC').isoformat()}")
    log(f"output: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
