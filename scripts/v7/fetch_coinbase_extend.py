"""Extend Coinbase 1m cache backward so Kronos can see a 120-min context.

v6's cache fetched [close - 65 min, close + 1 min] per contract. Kronos wants
120 min ending at t = close - horizon. For T-30 with horizon=30, we need
[close - 150, close - 30]. The cache has only [close - 65, close + 1].

Per the task brief, v6 data files MUST NOT be modified. This script writes
the SUPPLEMENTAL minutes to a NEW cache at data/v7/cache/coinbase_1m_v7.parquet.
The Kronos runner reads BOTH caches and unions them at load-time.

Usage:
    .venv-kronos/Scripts/python.exe -m scripts.v7.fetch_coinbase_extend
"""

from __future__ import annotations

import concurrent.futures as cf
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
V6_CACHE = REPO_ROOT / "data" / "v6" / "cache" / "coinbase_1m.parquet"
V7_CACHE_DIR = REPO_ROOT / "data" / "v7" / "cache"
V7_CACHE_DIR.mkdir(parents=True, exist_ok=True)
V7_CACHE = V7_CACHE_DIR / "coinbase_1m_v7.parquet"
V6_MASTER = REPO_ROOT / "data" / "v6" / "v6_master.parquet"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [coinbase-extend] {msg}", flush=True)


def fetch_window(start: pd.Timestamp, end: pd.Timestamp) -> list[list[float]]:
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": 60,
    }
    try:
        r = requests.get(
            url,
            params=params,
            timeout=30,
            headers={"User-Agent": "ProjectKalshiV7/1.0"},
        )
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:  # noqa: BLE001
        return []


def main() -> int:
    if not V6_CACHE.exists():
        log(f"missing {V6_CACHE}")
        return 1
    df_master = pd.read_parquet(V6_MASTER)
    closes = sorted({pd.Timestamp(c).tz_convert("UTC")
                     for c in df_master["close_time"]})
    log(f"loaded {len(closes)} unique close_times")

    # Read v6 cache (READ-ONLY).
    cache_v6 = pd.read_parquet(V6_CACHE)
    cache_v6["time"] = pd.to_datetime(cache_v6["time"], utc=True)
    cached_minutes = set(cache_v6["time"].dt.floor("min"))
    log(f"v6 cache has {len(cache_v6)} bars, {len(cached_minutes)} distinct minutes")

    # Read existing v7 supplemental cache if any.
    if V7_CACHE.exists():
        cache_v7 = pd.read_parquet(V7_CACHE)
        cache_v7["time"] = pd.to_datetime(cache_v7["time"], utc=True)
        cached_minutes |= set(cache_v7["time"].dt.floor("min"))
        log(f"v7 supp cache has {len(cache_v7)} bars; "
            f"union distinct minutes={len(cached_minutes)}")
    else:
        cache_v7 = pd.DataFrame()

    # For each close, the extended window we want: [close - 155, close + 1].
    # We fetch the FULL window per close (Coinbase will skip duplicates on
    # union); robust to internal gaps. Cost: ~300 minutes per close is below
    # the 300-candle limit per Coinbase call.
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for c in closes:
        ext_start = c - pd.Timedelta(minutes=155)
        ext_end = c + pd.Timedelta(minutes=1)
        expected = pd.date_range(
            start=ext_start, end=ext_end, freq="1min", tz="UTC",
        )
        # if more than 90% already cached, skip
        n_cached = sum(1 for m in expected if m in cached_minutes)
        if n_cached / len(expected) >= 0.95:
            continue
        windows.append((ext_start, ext_end))

    # dedupe overlapping windows by merging
    windows.sort()
    merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for s, e in windows:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    log(f"need to fetch {len(merged)} merged windows "
        f"(from {len(windows)} raw)")

    if not merged:
        log("nothing to fetch; cache already complete")
        return 0

    # Cap each window at 200 min (Coinbase limit 300, leave headroom)
    chunks: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for s, e in merged:
        while s < e:
            chunk_end = min(s + pd.Timedelta(minutes=200), e)
            chunks.append((s, chunk_end))
            s = chunk_end
    log(f"fetching {len(chunks)} chunks of <=200 min each")

    all_new: list[list[float]] = []
    n_done = 0
    t0 = time.time()

    def fetch_one(arg):
        s, e = arg
        return fetch_window(s, e)

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for cs in ex.map(fetch_one, chunks):
            all_new.extend(cs)
            n_done += 1
            if n_done % 50 == 0:
                elapsed = time.time() - t0
                eta = elapsed / n_done * (len(chunks) - n_done)
                log(f"  {n_done}/{len(chunks)} ({elapsed:.0f}s, ~{eta:.0f}s eta)")

    if not all_new:
        log("got no new data")
        return 0

    new_df = pd.DataFrame(
        all_new,
        columns=["time", "low", "high", "open", "close", "volume"],
    )
    new_df["time"] = pd.to_datetime(new_df["time"], unit="s", utc=True)
    # Filter to keep only minutes NOT already in v6 cache (to keep v6 read-only)
    v6_minutes_set = set(cache_v6["time"].dt.floor("min"))
    new_df["minute_floor"] = new_df["time"].dt.floor("min")
    new_df = new_df[~new_df["minute_floor"].isin(v6_minutes_set)].drop(
        columns=["minute_floor"],
    )
    # Union with existing v7 cache
    if len(cache_v7):
        v7_combined = pd.concat([cache_v7, new_df], ignore_index=True)
    else:
        v7_combined = new_df
    v7_combined = (
        v7_combined.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    )
    log(f"v7 supp cache will now hold: {len(v7_combined)} bars "
        f"(was {len(cache_v7)})")

    tmp = V7_CACHE.with_suffix(".parquet.tmp")
    v7_combined.to_parquet(tmp, index=False)
    os.replace(tmp, V7_CACHE)
    log(f"wrote {V7_CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
