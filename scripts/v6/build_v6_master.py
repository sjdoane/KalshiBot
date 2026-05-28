"""Build the v6 master dataset.

Per phase-1.5-methodology.md Section 4 + 10. For each eligible KXBTCD
contract at horizons N in {15, 30} minutes before close_time, compute:

Kalshi-internal features:
- kalshi_cvd_N (F1)
- kalshi_trade_count_N (F2)
- kalshi_time_since_last_trade_at_t (F3, single value)
- kalshi_price_drift_N (F4, with K1b guard)
- kalshi_mid_at_t (baseline; last yes_price_dollars at most recent trade <= t)

External features (from cached external sources, joined as-of t):
- funding_rate_level_at_t, funding_rate_delta_4h_at_t (F5)
- coinbase_realized_vol_N, coinbase_vwap_dev_N (F6, F7)
- dvol_delta_1h_at_t (F8)
- basis_delta_1h_at_t (F9)
- nan_pct_in_window (F6 audit)

Eligibility (Section 4.1):
- close_time > 2024-10-01
- lifetime_hours in [0.5, 4]
- status == 'finalized', result in {'yes','no'}
- at least 1 trade in [t - N, t] for that horizon

Random sample is stratified by close_date and band-of-interest to keep the
pilot tractable. Caller can scale by raising --target-n.

Run:
    uv run python -m scripts.v6.build_v6_master --target-n 500
    uv run python -m scripts.v6.build_v6_master --target-n 5000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Force unbuffered stdout for live progress when redirected
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import (  # noqa: E402
    KalshiClient,
    KalshiHTTPError,
)
from kalshi_bot_v6.v6_features import (  # noqa: E402
    coerce_trade_dtypes,
    kalshi_cvd_N,
    kalshi_mid_at_t,
    kalshi_price_drift_N,
    kalshi_time_since_last_trade,
    kalshi_trade_count_N,
)

OUT_DIR = REPO_ROOT / "data" / "v6"
CACHE_DIR = OUT_DIR / "cache"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FLIP_DATE = pd.Timestamp("2024-10-01", tz="UTC")
HORIZONS = [15, 30]
HORIZON_FETCH_MAX_MIN = 60  # pull last 60 min so we cover both T-30 and T-15
SEED = 42


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.utcnow().isoformat()}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Eligibility + sampling
# ---------------------------------------------------------------------------

def load_eligible_contracts() -> pd.DataFrame:
    """Filter v5 KXBTCD parquet to v6-eligible contracts."""
    src = REPO_ROOT / "data" / "v5" / "crypto_full_KXBTCD.parquet"
    df = pd.read_parquet(src)
    log(f"loaded {len(df):,} KXBTCD contracts from {src.name}")

    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)

    # post-flip
    post = df[df["close_time"] >= FLIP_DATE].copy()
    # lifetime in [0.5, 4]
    elig = post[
        (post["lifetime_hours"] >= 0.5) & (post["lifetime_hours"] <= 4)
    ].copy()
    # status finalized + result yes/no
    elig = elig[elig["status"] == "finalized"].copy()
    elig = elig[elig["result"].isin(["yes", "no"])].copy()
    # contract must have traded at all (volume > 0); otherwise no trades to fetch
    elig = elig[elig["volume"] > 0].copy()

    log(f"  post-Oct-2024 + lifetime [0.5, 4] + finalized + traded: {len(elig):,}")
    return elig.reset_index(drop=True)


def stratify_sample(
    elig: pd.DataFrame,
    target_n: int,
    seed: int = SEED,
) -> pd.DataFrame:
    """Sample contracts stratified by close_date + midband-ness.

    We oversample contracts whose `last_price_dollars` is in [0.55, 0.80] so
    the midband train/test slices have sufficient mass. (Note we still
    record the actual mid AT SAMPLE TIME `t` post-fetch; this is just a
    proxy for stratification.)
    """
    rng = np.random.default_rng(seed)
    elig = elig.copy()
    last_price = pd.to_numeric(elig["last_price_dollars"], errors="coerce")
    is_midband = (last_price >= 0.55) & (last_price <= 0.80)
    elig["_stratum"] = np.where(is_midband, "mid", "out")

    # Take ALL midband settlement-band contracts (small pool), plus the rest from
    # the "out" pool. Many out-pool contracts will be midband at T-30/T-15 (i.e.
    # last_price_dollars is final, kalshi_mid_at_t is at sample time).
    target_mid = int(round(target_n * 0.70))
    target_out = target_n - target_mid

    mid_pool = elig[elig["_stratum"] == "mid"]
    out_pool = elig[elig["_stratum"] == "out"]

    take_mid = min(target_mid, len(mid_pool))
    take_out = min(target_out, len(out_pool))

    log(
        f"stratification: midband pool n={len(mid_pool):,}, others "
        f"n={len(out_pool):,}; sampling {take_mid} mid + {take_out} out",
    )

    chosen_mid = mid_pool.sample(n=take_mid, random_state=seed)
    chosen_out = out_pool.sample(n=take_out, random_state=seed + 1)
    chosen = pd.concat([chosen_mid, chosen_out], ignore_index=True)
    chosen = chosen.sort_values("close_time").reset_index(drop=True)
    log(f"  sampled n={len(chosen)} contracts")
    return chosen


# ---------------------------------------------------------------------------
# Kalshi trade fetching with caching
# ---------------------------------------------------------------------------

def trades_cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"trades_{ticker}.parquet"


def fetch_trades_for_ticker(
    client: KalshiClient,
    ticker: str,
    close_time: pd.Timestamp,
) -> pd.DataFrame:
    """Pull last HORIZON_FETCH_MAX_MIN minutes of trades for one ticker."""
    cache = trades_cache_path(ticker)
    if cache.exists():
        try:
            return pd.read_parquet(cache)
        except Exception:  # noqa: BLE001
            pass

    window_start = close_time - pd.Timedelta(minutes=HORIZON_FETCH_MAX_MIN)
    window_end = close_time + pd.Timedelta(minutes=2)
    rows: list[dict[str, Any]] = []
    try:
        for r in client.paginate(
            "/historical/trades",
            item_key="trades",
            limit=1000,
            max_pages=20,
            ticker=ticker,
            min_ts=int(window_start.timestamp()),
            max_ts=int(window_end.timestamp()),
        ):
            rows.append(r)
    except KalshiHTTPError as e:
        log(f"  trade fetch failed for {ticker}: status={e.status}")
        df = pd.DataFrame()
        df.to_parquet(cache, index=False)
        return df
    except Exception as e:  # noqa: BLE001
        log(f"  trade fetch error for {ticker}: {type(e).__name__}: {e}")
        df = pd.DataFrame()
        df.to_parquet(cache, index=False)
        return df

    df = pd.DataFrame(rows)
    df.to_parquet(cache, index=False)
    return df


# ---------------------------------------------------------------------------
# External data caches: Coinbase, Deribit funding, DVOL, BTC-PERP
# ---------------------------------------------------------------------------

def coinbase_candles_in_range(
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: int = 60,
) -> list[list[float]]:
    """Fetch Coinbase BTC-USD 1m candles in [start, end] (up to 300 / call)."""
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": granularity,
    }
    try:
        r = requests.get(
            url,
            params=params,
            timeout=30,
            headers={"User-Agent": "ProjectKalshiV6/1.0"},
        )
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:  # noqa: BLE001
        return []


def fetch_coinbase_candles_for_dates(dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Fetch Coinbase 1m candles around each unique close_time.

    For each close_time, we need [close - 65 min, close] (covers T-30 and T-15).
    We dedupe the requests and run them in parallel (ThreadPoolExecutor).
    """
    import concurrent.futures as cf

    if not dates:
        return pd.DataFrame()
    cache = CACHE_DIR / "coinbase_1m.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            return df.sort_values("time").reset_index(drop=True)
        except Exception:  # noqa: BLE001
            pass

    unique_closes = sorted({pd.Timestamp(d).tz_convert("UTC") for d in dates})
    log(f"  coinbase: fetching 1m candles across {len(unique_closes)} close-times")

    fetched_windows: set[tuple[pd.Timestamp, pd.Timestamp]] = set()
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for c in unique_closes:
        start = c - pd.Timedelta(minutes=65)
        end = c + pd.Timedelta(minutes=1)
        key = (start.floor("min"), end.ceil("min"))
        if key in fetched_windows:
            continue
        fetched_windows.add(key)
        windows.append((start, end))

    log(f"  coinbase: {len(windows)} unique windows after dedup")
    all_candles: list[list[float]] = []
    n_done = [0]
    t_start = time.time()

    def fetch_one(args: tuple[pd.Timestamp, pd.Timestamp]) -> list[list[float]]:
        start, end = args
        return coinbase_candles_in_range(start, end, granularity=60)

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for cs in ex.map(fetch_one, windows):
            all_candles.extend(cs)
            n_done[0] += 1
            if n_done[0] % 200 == 0:
                elapsed = time.time() - t_start
                eta = elapsed / n_done[0] * (len(windows) - n_done[0])
                log(
                    f"    coinbase {n_done[0]}/{len(windows)} closes "
                    f"({elapsed:.0f}s elapsed, ~{eta:.0f}s eta)",
                )
    if not all_candles:
        log("  coinbase: empty")
        return pd.DataFrame()
    df = pd.DataFrame(
        all_candles,
        columns=["time", "low", "high", "open", "close", "volume"],
    )
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df.to_parquet(cache, index=False)
    log(f"  coinbase: wrote {cache.name} ({len(df):,} 1m bars)")
    return df


def fetch_deribit_funding(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetch Deribit BTC-PERPETUAL funding interest_1h across full range.

    Endpoint paginates by start/end timestamps; we walk in chunks.
    """
    cache = CACHE_DIR / "deribit_funding.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            return df.sort_values("time").reset_index(drop=True)
        except Exception:  # noqa: BLE001
            pass

    log("  deribit funding: fetching")
    rows: list[dict] = []
    cursor = start
    chunk = pd.Timedelta(days=10)
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        params = {
            "instrument_name": "BTC-PERPETUAL",
            "start_timestamp": int(cursor.timestamp() * 1000),
            "end_timestamp": int(chunk_end.timestamp() * 1000),
        }
        try:
            r = requests.get(
                "https://www.deribit.com/api/v2/public/get_funding_rate_history",
                params=params,
                timeout=30,
            )
            if r.status_code == 200:
                rows.extend(r.json().get("result", []))
        except Exception:  # noqa: BLE001
            pass
        cursor = chunk_end
        time.sleep(0.20)
    if not rows:
        log("  deribit funding: empty")
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["interest_1h"] = pd.to_numeric(df["interest_1h"], errors="coerce")
    df = df.drop_duplicates("timestamp").sort_values("time").reset_index(drop=True)
    df.to_parquet(cache, index=False)
    log(f"  deribit funding: wrote {len(df):,} rows")
    return df


def fetch_deribit_dvol(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetch Deribit BTC DVOL hourly across full range."""
    cache = CACHE_DIR / "deribit_dvol.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            return df.sort_values("time").reset_index(drop=True)
        except Exception:  # noqa: BLE001
            pass

    log("  deribit dvol: fetching")
    rows: list[dict] = []
    cursor = start
    chunk = pd.Timedelta(days=30)
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        params = {
            "currency": "BTC",
            "resolution": 3600,
            "start_timestamp": int(cursor.timestamp() * 1000),
            "end_timestamp": int(chunk_end.timestamp() * 1000),
        }
        try:
            r = requests.get(
                "https://www.deribit.com/api/v2/public/get_volatility_index_data",
                params=params,
                timeout=30,
            )
            if r.status_code == 200:
                payload = r.json().get("result", {})
                # payload.data is list of [ts, open, high, low, close]
                for entry in payload.get("data", []):
                    rows.append(
                        {
                            "time": pd.to_datetime(entry[0], unit="ms", utc=True),
                            "dvol_open": entry[1],
                            "dvol_high": entry[2],
                            "dvol_low": entry[3],
                            "dvol_close": entry[4],
                        },
                    )
        except Exception:  # noqa: BLE001
            pass
        cursor = chunk_end
        time.sleep(0.20)
    if not rows:
        log("  deribit dvol: empty")
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df.to_parquet(cache, index=False)
    log(f"  deribit dvol: wrote {len(df):,} rows")
    return df


def fetch_deribit_perp_hourly(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch Deribit BTC-PERPETUAL hourly price for basis_delta."""
    cache = CACHE_DIR / "deribit_perp_hourly.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            return df.sort_values("time").reset_index(drop=True)
        except Exception:  # noqa: BLE001
            pass

    log("  deribit perp: fetching hourly")
    rows: list[dict] = []
    cursor = start
    chunk = pd.Timedelta(days=30)
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        params = {
            "instrument_name": "BTC-PERPETUAL",
            "start_timestamp": int(cursor.timestamp() * 1000),
            "end_timestamp": int(chunk_end.timestamp() * 1000),
            "resolution": "60",
        }
        try:
            r = requests.get(
                "https://www.deribit.com/api/v2/public/get_tradingview_chart_data",
                params=params,
                timeout=30,
            )
            if r.status_code == 200:
                d = r.json().get("result", {})
                ticks = d.get("ticks", [])
                closes = d.get("close", [])
                for ts, cl in zip(ticks, closes):
                    rows.append(
                        {
                            "time": pd.to_datetime(ts, unit="ms", utc=True),
                            "perp_close": float(cl),
                        },
                    )
        except Exception:  # noqa: BLE001
            pass
        cursor = chunk_end
        time.sleep(0.20)
    if not rows:
        log("  deribit perp: empty")
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df.to_parquet(cache, index=False)
    log(f"  deribit perp: wrote {len(df):,} rows")
    return df


# ---------------------------------------------------------------------------
# External feature extraction (as-of t)
# ---------------------------------------------------------------------------

def coinbase_features_at(
    cb: pd.DataFrame,
    t: pd.Timestamp,
    horizon_min: int,
) -> tuple[float, float, float]:
    """(realized_vol, vwap_dev, nan_pct) over [t - horizon_min, t]."""
    if cb is None or cb.empty:
        return float("nan"), float("nan"), float("nan")
    window_start = t - pd.Timedelta(minutes=horizon_min)
    sub = cb[(cb["time"] > window_start) & (cb["time"] <= t)].sort_values("time")
    expected_bars = horizon_min
    obs_bars = len(sub)
    if expected_bars <= 0:
        nan_pct = float("nan")
    else:
        nan_pct = max(0.0, 1.0 - obs_bars / expected_bars)
    if obs_bars < 5:
        return float("nan"), float("nan"), float(nan_pct)
    closes = sub["close"].astype(float).to_numpy()
    vols = sub["volume"].astype(float).to_numpy()
    logrets = np.diff(np.log(closes))
    realized_vol = float(np.std(logrets))
    total_vol = float(vols.sum())
    if total_vol <= 0:
        vwap_dev = float("nan")
    else:
        vwap = float((closes * vols).sum() / total_vol)
        spot = closes[-1]
        vwap_dev = (vwap / spot) - 1.0
    return realized_vol, vwap_dev, float(nan_pct)


def asof_lookup(
    df: pd.DataFrame,
    time_col: str,
    value_col: str,
    t: pd.Timestamp,
) -> float:
    """Last row in df with df[time_col] <= t, returns df[value_col]."""
    if df is None or df.empty:
        return float("nan")
    sub = df[df[time_col] <= t]
    if sub.empty:
        return float("nan")
    return float(sub.iloc[-1][value_col])


def funding_features_at(
    funding: pd.DataFrame,
    t: pd.Timestamp,
) -> tuple[float, float]:
    """(funding_level_at_t, funding_delta_4h)."""
    level = asof_lookup(funding, "time", "interest_1h", t)
    level_4h = asof_lookup(funding, "time", "interest_1h", t - pd.Timedelta(hours=4))
    if np.isnan(level) or np.isnan(level_4h):
        return level, float("nan")
    return level, level - level_4h


def dvol_features_at(dvol: pd.DataFrame, t: pd.Timestamp) -> float:
    """DVOL delta over 1h."""
    now = asof_lookup(dvol, "time", "dvol_close", t)
    prev = asof_lookup(dvol, "time", "dvol_close", t - pd.Timedelta(hours=1))
    if np.isnan(now) or np.isnan(prev):
        return float("nan")
    return now - prev


def basis_features_at(
    perp: pd.DataFrame,
    cb: pd.DataFrame,
    t: pd.Timestamp,
) -> float:
    """basis_delta_1h = (perp/spot at t) - (perp/spot at t-1h)."""
    if perp is None or perp.empty or cb is None or cb.empty:
        return float("nan")
    perp_now = asof_lookup(perp, "time", "perp_close", t)
    spot_now_arr = cb[cb["time"] <= t]
    if spot_now_arr.empty:
        return float("nan")
    spot_now = float(spot_now_arr.iloc[-1]["close"])
    perp_prev = asof_lookup(perp, "time", "perp_close", t - pd.Timedelta(hours=1))
    spot_prev_arr = cb[cb["time"] <= t - pd.Timedelta(hours=1)]
    if spot_prev_arr.empty:
        return float("nan")
    spot_prev = float(spot_prev_arr.iloc[-1]["close"])
    if (
        np.isnan(perp_now)
        or np.isnan(perp_prev)
        or spot_now <= 0
        or spot_prev <= 0
    ):
        return float("nan")
    return (perp_now / spot_now) - (perp_prev / spot_prev)


# ---------------------------------------------------------------------------
# Master build
# ---------------------------------------------------------------------------

def prefetch_trades_parallel(
    contracts: pd.DataFrame,
    client: KalshiClient,
    max_workers: int = 4,
) -> None:
    """Pre-fetch trades into cache in parallel. Idempotent (cache check)."""
    import concurrent.futures as cf

    todo = [
        (r["ticker"], r["close_time"])
        for _, r in contracts.iterrows()
        if not trades_cache_path(r["ticker"]).exists()
    ]
    if not todo:
        log(f"  trades: all {len(contracts)} cached, skip prefetch")
        return
    log(f"  trades: prefetching {len(todo)}/{len(contracts)} (uncached) in parallel")
    n_done = [0]
    t_start = time.time()

    def _one(args: tuple[str, pd.Timestamp]) -> None:
        ticker, close_time = args
        fetch_trades_for_ticker(client, ticker, close_time)
        n_done[0] += 1
        if n_done[0] % 200 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / n_done[0] * (len(todo) - n_done[0])
            log(
                f"    trades {n_done[0]}/{len(todo)} ({elapsed:.0f}s, eta {eta:.0f}s)",
            )

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(_one, todo))
    log(f"  trades: prefetched {len(todo)} in {time.time() - t_start:.0f}s")


def build_sample_rows(
    contracts: pd.DataFrame,
    client: KalshiClient,
    coinbase: pd.DataFrame,
    funding: pd.DataFrame,
    dvol: pd.DataFrame,
    perp: pd.DataFrame,
    horizons: list[int],
    build_log: dict[str, Any],
) -> pd.DataFrame:
    """For each contract x horizon, build a feature row if eligible."""
    # Prefetch trades in parallel before computing features (single-threaded post)
    prefetch_trades_parallel(contracts, client, max_workers=4)
    rows: list[dict[str, Any]] = []
    n = len(contracts)
    t_start = time.time()
    horizon_drop_counts = defaultdict(int)
    success = 0

    for i, row in contracts.iterrows():
        ticker = row["ticker"]
        close_time = row["close_time"]
        open_time = row["open_time"]
        outcome_yes = 1 if row["result"] == "yes" else 0
        trades_raw = fetch_trades_for_ticker(client, ticker, close_time)
        trades = coerce_trade_dtypes(trades_raw)
        if not trades.empty:
            # Filter to this ticker just in case (defensive against any caller bug)
            trades = trades[trades["ticker"] == ticker].copy()

        for h in horizons:
            t = close_time - pd.Timedelta(minutes=h)
            # Section 4.1 eligibility: at least 1 trade in [t - h, t]
            tc = kalshi_trade_count_N(trades, t, h)
            if tc < 1:
                horizon_drop_counts[f"no_trade_in_window_T-{h}"] += 1
                continue
            mid = kalshi_mid_at_t(trades, t)
            if np.isnan(mid):
                horizon_drop_counts[f"no_mid_at_t_T-{h}"] += 1
                continue
            tslt = kalshi_time_since_last_trade(trades, t)
            cvd = kalshi_cvd_N(trades, t, h)
            drift = kalshi_price_drift_N(trades, t, h, open_time)
            cb_vol, cb_vwap_dev, nan_pct = coinbase_features_at(coinbase, t, h)
            funding_level, funding_delta = funding_features_at(funding, t)
            dvol_delta = dvol_features_at(dvol, t)
            basis_delta = basis_features_at(perp, coinbase, t)

            rec: dict[str, Any] = {
                "ticker": ticker,
                "event_ticker": row["event_ticker"],
                "open_time": open_time,
                "close_time": close_time,
                "outcome_yes": outcome_yes,
                "horizon_min": h,
                "t": t,
                "kalshi_mid_at_t": mid,
                "time_since_last_trade_at_t": tslt,
                f"kalshi_cvd_{h}": cvd,
                f"kalshi_trade_count_{h}": tc,
                f"kalshi_price_drift_{h}": drift,
                "funding_rate_level_at_t": funding_level,
                "funding_rate_delta_4h_at_t": funding_delta,
                f"coinbase_realized_vol_{h}": cb_vol,
                f"coinbase_vwap_dev_{h}": cb_vwap_dev,
                "dvol_delta_1h_at_t": dvol_delta,
                "basis_delta_1h_at_t": basis_delta,
                "nan_pct_in_window": nan_pct,
            }
            rows.append(rec)
            success += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / (i + 1) * (n - i - 1)
            log(
                f"  build {i + 1}/{n}: emit_rows={success}, elapsed={elapsed:.0f}s, "
                f"eta={eta:.0f}s",
            )

    build_log["horizon_drop_counts"] = dict(horizon_drop_counts)
    build_log["rows_emitted"] = success
    return pd.DataFrame(rows)


def consolidate_to_wide(rows: pd.DataFrame) -> pd.DataFrame:
    """Each row is one (ticker, horizon) sample. The methodology lists the
    set of columns plainly; one row per (ticker, horizon) is the natural
    layout. We keep one-row-per-(ticker, horizon) but the per-horizon
    feature columns are sparse (only set for that horizon).

    Strategy: keep horizon_min as an explicit column and merge per-horizon
    feature columns into 'kalshi_cvd_N' with horizon suffix preserved.
    Downstream code filters by horizon_min and selects the matching columns.
    """
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-n", type=int, default=500)
    parser.add_argument("--horizons", type=int, nargs="+", default=HORIZONS)
    parser.add_argument(
        "--out",
        default=str(OUT_DIR / "v6_master.parquet"),
    )
    parser.add_argument(
        "--no-external", action="store_true",
        help="Skip Coinbase / Deribit fetches (pilot-only Kalshi-internal mode)",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    build_log: dict[str, Any] = {
        "run_started": pd.Timestamp.utcnow().isoformat(),
        "target_n": args.target_n,
        "horizons": args.horizons,
        "seed": SEED,
    }

    elig = load_eligible_contracts()
    build_log["n_eligible"] = int(len(elig))
    sample = stratify_sample(elig, args.target_n)
    build_log["n_sampled"] = int(len(sample))

    # Date range for external fetches
    date_min = sample["close_time"].min() - pd.Timedelta(hours=4)
    date_max = sample["close_time"].max() + pd.Timedelta(hours=1)
    log(f"date range: {date_min} -> {date_max}")
    build_log["date_range"] = [str(date_min), str(date_max)]

    if not args.no_external:
        # External caches first (single fetch across all dates)
        all_dates = sample["close_time"].tolist()
        coinbase = fetch_coinbase_candles_for_dates(all_dates)
        funding = fetch_deribit_funding(date_min, date_max)
        dvol = fetch_deribit_dvol(date_min, date_max)
        perp = fetch_deribit_perp_hourly(date_min, date_max)
    else:
        log("skipping external fetches (--no-external)")
        coinbase = pd.DataFrame()
        funding = pd.DataFrame()
        dvol = pd.DataFrame()
        perp = pd.DataFrame()

    build_log["data_sources"] = {
        "coinbase_n_minutes": int(len(coinbase)),
        "deribit_funding_n_obs": int(len(funding)),
        "deribit_dvol_n_obs": int(len(dvol)),
        "deribit_perp_n_obs": int(len(perp)),
    }

    with KalshiClient(settings) as client:
        rows = build_sample_rows(
            sample,
            client,
            coinbase,
            funding,
            dvol,
            perp,
            args.horizons,
            build_log,
        )

    log(f"emitted {len(rows)} feature rows")
    rows = consolidate_to_wide(rows)
    out_path = Path(args.out)
    rows.to_parquet(out_path, index=False)
    log(f"wrote {out_path}")

    # Coverage summary
    build_log["row_counts"] = {
        "total": int(len(rows)),
        "by_horizon": {
            h: int((rows["horizon_min"] == h).sum()) for h in args.horizons
        },
        "by_outcome": {
            int(v): int(c) for v, c in rows["outcome_yes"].value_counts().items()
        },
    }
    if len(rows):
        midband_mask = (rows["kalshi_mid_at_t"] >= 0.55) & (
            rows["kalshi_mid_at_t"] <= 0.80
        )
        widerband_mask = (rows["kalshi_mid_at_t"] >= 0.20) & (
            rows["kalshi_mid_at_t"] <= 0.80
        )
        build_log["band_counts"] = {
            "midband_total": int(midband_mask.sum()),
            "widerband_total": int(widerband_mask.sum()),
            "midband_by_horizon": {
                h: int((midband_mask & (rows["horizon_min"] == h)).sum())
                for h in args.horizons
            },
            "midband_yes_rate": (
                float(rows.loc[midband_mask, "outcome_yes"].mean())
                if midband_mask.any() else None
            ),
            "widerband_yes_rate": (
                float(rows.loc[widerband_mask, "outcome_yes"].mean())
                if widerband_mask.any() else None
            ),
        }

    build_log["run_completed"] = pd.Timestamp.utcnow().isoformat()
    log_path = OUT_DIR / "v6_build_log.json"
    with open(log_path, "w") as f:
        json.dump(build_log, f, indent=2, default=str)
    log(f"wrote {log_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
