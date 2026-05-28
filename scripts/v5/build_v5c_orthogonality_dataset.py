"""Build the V5-C2 orthogonality dataset.

Selects ~200 KXBTCD v1-band markets stratified by close_date, then
samples 6-10 candidate features AS-OF open_time (chronologically
BEFORE last_price, which is observed during [open_time, close_time]).

Features sampled:
- F1 realized_vol_1h: stdev(log returns) of Coinbase BTC-USD 1m candles in [open_time-1h, open_time]
- F2 vwap_dev_1h: VWAP - spot deviation last hour (proxy buying pressure)
- F3 spot_futures_basis: (Deribit BTC-PERPETUAL / Coinbase spot) - 1 at open_time
- F4 funding_rate_8h: Deribit BTC-PERPETUAL funding rate as-of open_time
- F5 mempool_fee_proxy: mempool.space recommended fee at open_time (using closest historical block tip)
- F6 active_addr_delta_24h: Coin Metrics community AdrActCnt for BTC, today vs yesterday
- F7 dxy_24h_change: FRED DXY (DTWEXBGS or DEXUSEU as backup); 24h change as-of open_time
- F8 btc_dominance_24h_change: CoinGecko btc_market_cap / global / 24h delta

For BRTI tracking error analysis: each event's BRTI settlement is bracketed
by max(yes_threshold) < BRTI < min(no_threshold). We compute Coinbase
BTC-USD spot price at close_time and measure the tracking error.

Saves to data/v5/v5c_orthogonality_data.parquet.

Run: uv run python -m scripts.v5.build_v5c_orthogonality_dataset
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_SIZE = int(__import__("os").environ.get("V5C_SAMPLE_SIZE", "200"))
SEED = 42
THROTTLE_SEC = 0.35  # polite throttle across all public APIs

THRESHOLD_PATTERN = re.compile(r"-T(\d+\.\d+)$")


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.utcnow().isoformat()}] {msg}", flush=True)


def sample_markets() -> pd.DataFrame:
    """Load KXBTCD parquet, filter to v1-band, draw stratified sample.

    Stratification: each market's close_date so we don't overweight a
    single high-volume day. Aim for 200 markets across distinct
    close-dates if possible.
    """
    df = pd.read_parquet(OUT_DIR / "crypto_full_KXBTCD.parquet")
    log(f"Loaded KXBTCD parquet: {len(df):,} rows")

    df["last_price"] = pd.to_numeric(df["last_price_dollars"], errors="coerce")
    df["outcome"] = (df["result"] == "yes").astype(int)

    # Parse threshold from ticker
    df["threshold"] = df["ticker"].apply(
        lambda t: float(THRESHOLD_PATTERN.search(t).group(1))
        if THRESHOLD_PATTERN.search(t)
        else None,
    )

    # v1-band, 1h lifetime markets (the workhorse cadence)
    v1 = df[
        (df["last_price"] >= 0.70)
        & (df["last_price"] <= 0.95)
        & (df["lifetime_hours"] >= 0.9)
        & (df["lifetime_hours"] <= 1.1)
    ].copy()
    log(f"v1-band 1h KXBTCD markets: {len(v1):,}")

    # Stratified random sample across close_dates
    v1["close_date"] = v1["close_time"].dt.date
    rng = np.random.default_rng(SEED)
    grouped = v1.groupby("close_date")
    if len(grouped) >= SAMPLE_SIZE:
        # Pick one market per date until we have SAMPLE_SIZE
        dates = list(grouped.groups.keys())
        rng.shuffle(dates)
        chosen_idx: list[int] = []
        for d in dates[:SAMPLE_SIZE]:
            grp = grouped.get_group(d)
            pick = rng.choice(grp.index.tolist())
            chosen_idx.append(pick)
        sample = v1.loc[chosen_idx].copy()
    else:
        sample = v1.sample(n=min(SAMPLE_SIZE, len(v1)), random_state=SEED).copy()

    sample = sample.sort_values("close_time").reset_index(drop=True)
    log(f"Sampled n={len(sample)} markets across {sample['close_date'].nunique()} distinct dates")
    log(
        f"Sample date range: {sample['close_time'].min()} -> {sample['close_time'].max()}",
    )
    log(f"Sample yes_rate: {sample['outcome'].mean():.4f}")

    return sample


def derive_brti_bracket(sample: pd.DataFrame) -> pd.DataFrame:
    """For each row's event_ticker, find max(yes threshold) and min(no
    threshold) across siblings; the BRTI value is bracketed in between.
    """
    full = pd.read_parquet(OUT_DIR / "crypto_full_KXBTCD.parquet")
    full["last_price"] = pd.to_numeric(full["last_price_dollars"], errors="coerce")
    full["threshold"] = full["ticker"].apply(
        lambda t: float(THRESHOLD_PATTERN.search(t).group(1))
        if THRESHOLD_PATTERN.search(t)
        else None,
    )
    full["outcome"] = (full["result"] == "yes").astype(int)

    # For each event, max threshold where outcome=1 (YES, BRTI >= threshold)
    # min threshold where outcome=0 (NO, BRTI < threshold)
    by_event = full.groupby("event_ticker")
    yes_max = by_event.apply(
        lambda g: g.loc[g["outcome"] == 1, "threshold"].max()
        if (g["outcome"] == 1).any()
        else None,
        include_groups=False,
    )
    no_min = by_event.apply(
        lambda g: g.loc[g["outcome"] == 0, "threshold"].min()
        if (g["outcome"] == 0).any()
        else None,
        include_groups=False,
    )
    brackets = pd.DataFrame({"brti_lower": yes_max, "brti_upper": no_min})
    sample = sample.merge(brackets, left_on="event_ticker", right_index=True, how="left")
    sample["brti_estimate"] = (sample["brti_lower"] + sample["brti_upper"]) / 2.0
    return sample


def coinbase_candles_for_window(
    start_iso: str, end_iso: str, granularity: int = 60,
) -> list[list[float]]:
    """Fetch Coinbase Exchange BTC-USD candles for a time window.

    Returns list of [time, low, high, open, close, volume] rows.
    """
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    params = {"start": start_iso, "end": end_iso, "granularity": granularity}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def f1_realized_vol_1h(open_time: pd.Timestamp) -> float:
    """stdev of log returns of Coinbase BTC-USD 1m candles in
    [open_time-1h, open_time]. NaN if data unavailable.
    """
    start = (open_time - pd.Timedelta(hours=1)).isoformat()
    end = open_time.isoformat()
    candles = coinbase_candles_for_window(start, end, granularity=60)
    if len(candles) < 5:
        return float("nan")
    # candles: [time, low, high, open, close, volume] reverse-chrono
    closes = [c[4] for c in reversed(candles)]
    logrets = np.diff(np.log(closes))
    return float(np.std(logrets))


def f2_vwap_dev_1h(open_time: pd.Timestamp) -> float:
    """(VWAP last 1h) / (spot at open_time) - 1. Negative when last hour
    has been traded below spot (buying pressure).
    """
    start = (open_time - pd.Timedelta(hours=1)).isoformat()
    end = open_time.isoformat()
    candles = coinbase_candles_for_window(start, end, granularity=60)
    if len(candles) < 5:
        return float("nan")
    # candles reverse-chrono
    closes = [c[4] for c in reversed(candles)]
    vols = [c[5] for c in reversed(candles)]
    total_vol = sum(vols)
    if total_vol <= 0:
        return float("nan")
    vwap = sum(c * v for c, v in zip(closes, vols)) / total_vol
    spot = closes[-1]
    return float((vwap / spot) - 1.0)


def f3_spot_futures_basis(open_time: pd.Timestamp) -> float:
    """(Deribit BTC-PERPETUAL 1h candle close) / (Coinbase BTC-USD 1h
    candle close) - 1 at open_time.
    """
    # Coinbase spot
    end = open_time.isoformat()
    start = (open_time - pd.Timedelta(minutes=10)).isoformat()
    cb_candles = coinbase_candles_for_window(start, end, granularity=60)
    if len(cb_candles) < 1:
        return float("nan")
    spot = cb_candles[0][4]  # latest in reverse-chrono

    # Deribit BTC-PERPETUAL
    end_ms = int(open_time.timestamp() * 1000)
    start_ms = end_ms - 10 * 60 * 1000
    url = "https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
    params = {
        "instrument_name": "BTC-PERPETUAL",
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
        "resolution": "1",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return float("nan")
        data = r.json().get("result", {})
        closes = data.get("close", [])
        if not closes:
            return float("nan")
        fut = closes[-1]
        return float((fut / spot) - 1.0)
    except Exception:
        return float("nan")


def f4_funding_rate(open_time: pd.Timestamp) -> float:
    """Deribit BTC-PERPETUAL 1h interest rate AS-OF open_time. Returns
    NaN if endpoint fails.
    """
    end_ms = int(open_time.timestamp() * 1000)
    start_ms = end_ms - 8 * 3600 * 1000
    url = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
    params = {
        "instrument_name": "BTC-PERPETUAL",
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return float("nan")
        data = r.json().get("result", [])
        if not data:
            return float("nan")
        # latest 1h interest rate
        latest = data[-1]
        return float(latest.get("interest_1h", float("nan")))
    except Exception:
        return float("nan")


def coinbase_spot_at(open_time: pd.Timestamp) -> float:
    """Coinbase BTC-USD 1m candle close at open_time, for tracking
    error and as a price feature.
    """
    end = open_time.isoformat()
    start = (open_time - pd.Timedelta(minutes=5)).isoformat()
    candles = coinbase_candles_for_window(start, end, granularity=60)
    if not candles:
        return float("nan")
    return float(candles[0][4])


def coinbase_spot_at_close(close_time: pd.Timestamp) -> float:
    """Coinbase BTC-USD 1m candle close at close_time, for BRTI tracking
    error measurement.
    """
    end = close_time.isoformat()
    start = (close_time - pd.Timedelta(minutes=5)).isoformat()
    candles = coinbase_candles_for_window(start, end, granularity=60)
    if not candles:
        return float("nan")
    return float(candles[0][4])


# Cache for Coin Metrics community AdrActCnt
_cm_cache: pd.DataFrame | None = None


def get_cm_active_addr() -> pd.DataFrame:
    """Fetch Coin Metrics community daily AdrActCnt for BTC across full range."""
    global _cm_cache
    if _cm_cache is not None:
        return _cm_cache
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {
        "assets": "btc",
        "metrics": "AdrActCnt",
        "frequency": "1d",
        "start_time": "2024-01-01",
        "end_time": "2026-04-01",
        "page_size": 10000,
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            log(f"CM fetch fail: {r.status_code}")
            _cm_cache = pd.DataFrame()
            return _cm_cache
        data = r.json().get("data", [])
        df = pd.DataFrame(data)
        if df.empty:
            _cm_cache = pd.DataFrame()
            return _cm_cache
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["AdrActCnt"] = pd.to_numeric(df["AdrActCnt"], errors="coerce")
        df = df.sort_values("time").reset_index(drop=True)
        df["AdrActCnt_lag1"] = df["AdrActCnt"].shift(1)
        df["AdrActCnt_delta"] = df["AdrActCnt"] - df["AdrActCnt_lag1"]
        _cm_cache = df
        return _cm_cache
    except Exception as e:
        log(f"CM fetch err: {e}")
        _cm_cache = pd.DataFrame()
        return _cm_cache


def f6_active_addr_delta(open_time: pd.Timestamp) -> float:
    """Active address 24h delta AS-OF open_time.

    Strict AS-OF: use the last completed daily data BEFORE open_time, so
    we don't read same-day data.
    """
    df = get_cm_active_addr()
    if df.empty:
        return float("nan")
    cutoff = open_time - pd.Timedelta(hours=24)  # strict prior day
    sub = df[df["time"] <= cutoff]
    if sub.empty:
        return float("nan")
    delta = sub.iloc[-1]["AdrActCnt_delta"]
    if pd.isna(delta):
        return float("nan")
    return float(delta)


# Cache for FRED DXY
_dxy_cache: pd.DataFrame | None = None


def get_dxy_series() -> pd.DataFrame:
    """Fetch DXY series from Yahoo Finance (FRED requires key, Yahoo free).

    Yahoo: DX-Y.NYB daily. Returns daily closes.
    """
    global _dxy_cache
    if _dxy_cache is not None:
        return _dxy_cache
    url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
    params = {"range": "5y", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KalshiResearch/1.0)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            log(f"Yahoo DXY fail: {r.status_code}")
            _dxy_cache = pd.DataFrame()
            return _dxy_cache
        data = r.json()["chart"]["result"][0]
        ts = data["timestamp"]
        closes = data["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({"timestamp": ts, "close": closes})
        df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.sort_values("time").reset_index(drop=True)
        df["close_lag1"] = df["close"].shift(1)
        df["pct_chg_24h"] = (df["close"] / df["close_lag1"]) - 1.0
        _dxy_cache = df
        return _dxy_cache
    except Exception as e:
        log(f"Yahoo DXY err: {e}")
        _dxy_cache = pd.DataFrame()
        return _dxy_cache


def f7_dxy_24h_change(open_time: pd.Timestamp) -> float:
    """DXY 24h pct change AS-OF the most recent prior trading day before
    open_time. Uses the LAST observed daily close strictly before
    open_time (so weekends/holidays don't produce NaN as long as a
    prior trading day exists).
    """
    df = get_dxy_series()
    if df.empty:
        return float("nan")
    sub = df[df["time"] < open_time]
    if sub.empty:
        return float("nan")
    # find last non-null pct_chg
    sub_valid = sub[sub["pct_chg_24h"].notna()]
    if sub_valid.empty:
        return float("nan")
    return float(sub_valid.iloc[-1]["pct_chg_24h"])


# Cache for hash rate
_hashrate_cache: pd.DataFrame | None = None


def get_hashrate_series() -> pd.DataFrame:
    """blockchain.info hash-rate daily."""
    global _hashrate_cache
    if _hashrate_cache is not None:
        return _hashrate_cache
    url = "https://api.blockchain.info/charts/hash-rate"
    params = {"timespan": "2years", "format": "json"}
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            log(f"blockchain.info fail: {r.status_code}")
            _hashrate_cache = pd.DataFrame()
            return _hashrate_cache
        data = r.json().get("values", [])
        df = pd.DataFrame(data)
        if df.empty:
            _hashrate_cache = pd.DataFrame()
            return _hashrate_cache
        df["time"] = pd.to_datetime(df["x"], unit="s", utc=True)
        df["hash_rate"] = pd.to_numeric(df["y"], errors="coerce")
        df = df.sort_values("time").reset_index(drop=True)
        df["hash_lag1"] = df["hash_rate"].shift(1)
        df["hash_pct_chg_24h"] = (df["hash_rate"] / df["hash_lag1"]) - 1.0
        _hashrate_cache = df
        return _hashrate_cache
    except Exception as e:
        log(f"blockchain.info err: {e}")
        _hashrate_cache = pd.DataFrame()
        return _hashrate_cache


def f8_hashrate_24h_change(open_time: pd.Timestamp) -> float:
    df = get_hashrate_series()
    if df.empty:
        return float("nan")
    sub = df[df["time"] < open_time]
    if sub.empty:
        return float("nan")
    sub_valid = sub[sub["hash_pct_chg_24h"].notna()]
    if sub_valid.empty:
        return float("nan")
    return float(sub_valid.iloc[-1]["hash_pct_chg_24h"])


def main() -> int:
    log("Building V5-C2 orthogonality dataset")

    sample = sample_markets()
    sample = derive_brti_bracket(sample)
    log(
        f"BRTI bracket coverage: {sample['brti_estimate'].notna().sum()}"
        f" / {len(sample)} rows",
    )

    # Prefetch slow-changing series once (daily caches)
    get_cm_active_addr()
    get_dxy_series()
    get_hashrate_series()

    rows: list[dict[str, Any]] = []
    n = len(sample)
    t_start = time.time()
    for i, row in sample.iterrows():
        open_time = row["open_time"]
        close_time = row["close_time"]
        # F1, F2 use Coinbase candles in [open_time-1h, open_time]
        f1 = f1_realized_vol_1h(open_time)
        time.sleep(THROTTLE_SEC)
        f2 = f2_vwap_dev_1h(open_time)
        time.sleep(THROTTLE_SEC)
        f3 = f3_spot_futures_basis(open_time)
        time.sleep(THROTTLE_SEC)
        f4 = f4_funding_rate(open_time)
        time.sleep(THROTTLE_SEC)
        # F5 skipped (mempool.space lacks historical AS-OF; would need a paid
        # source or our own snapshot. Documented in research doc.)
        f6 = f6_active_addr_delta(open_time)
        f7 = f7_dxy_24h_change(open_time)
        f8 = f8_hashrate_24h_change(open_time)
        # Spot prices for tracking error
        coinbase_at_open = coinbase_spot_at(open_time)
        time.sleep(THROTTLE_SEC)
        coinbase_at_close = coinbase_spot_at_close(close_time)
        time.sleep(THROTTLE_SEC)

        rec = {
            "ticker": row["ticker"],
            "event_ticker": row["event_ticker"],
            "open_time": open_time,
            "close_time": close_time,
            "threshold": row["threshold"],
            "favorite_price": float(row["last_price"]),
            "outcome": int(row["outcome"]),
            "brti_lower": row["brti_lower"],
            "brti_upper": row["brti_upper"],
            "brti_estimate": row["brti_estimate"],
            "coinbase_at_open": coinbase_at_open,
            "coinbase_at_close": coinbase_at_close,
            "f1_realized_vol_1h": f1,
            "f2_vwap_dev_1h": f2,
            "f3_spot_futures_basis": f3,
            "f4_funding_rate_1h": f4,
            "f6_active_addr_delta": f6,
            "f7_dxy_24h_change": f7,
            "f8_hashrate_24h_change": f8,
        }
        rows.append(rec)

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / (i + 1) * (n - i - 1)
            log(f"  progress {i + 1}/{n} elapsed={elapsed:.0f}s eta={eta:.0f}s")

    out_df = pd.DataFrame(rows)
    out_path = OUT_DIR / "v5c_orthogonality_data.parquet"
    out_df.to_parquet(out_path, index=False)
    log(f"Wrote {out_path} (n={len(out_df)})")

    # Summary
    feature_cols = [
        "f1_realized_vol_1h",
        "f2_vwap_dev_1h",
        "f3_spot_futures_basis",
        "f4_funding_rate_1h",
        "f6_active_addr_delta",
        "f7_dxy_24h_change",
        "f8_hashrate_24h_change",
    ]
    coverage = {c: int(out_df[c].notna().sum()) for c in feature_cols}
    log(f"Feature coverage (n_non_null per column): {coverage}")
    meta = {
        "sample_size": len(out_df),
        "yes_rate": float(out_df["outcome"].mean()),
        "date_range": [
            str(out_df["close_time"].min()),
            str(out_df["close_time"].max()),
        ],
        "feature_coverage": coverage,
        "brti_bracket_coverage": int(out_df["brti_estimate"].notna().sum()),
        "coinbase_at_open_coverage": int(out_df["coinbase_at_open"].notna().sum()),
        "coinbase_at_close_coverage": int(out_df["coinbase_at_close"].notna().sum()),
    }
    meta_path = OUT_DIR / "v5c_orthogonality_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"Wrote {meta_path}")
    log(f"Total elapsed: {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
