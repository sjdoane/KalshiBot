"""Full-pull v5 crypto probe for the top-cadence series.

Drains pages for ~12 high-volume crypto series with NO page cap. Writes
data/v5/crypto_full_<series>.parquet per series and computes v1-eligible
band counts.

This complements probe_crypto_inventory.py which capped at 50 pages.

Run as: uv run python -m scripts.v5.probe_crypto_full
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FULL_SERIES: list[str] = [
    "KXBTC",     # hourly BTC range (above/below/between thresholds)
    "KXBTCD",   # hourly BTC directional (above only)
    "KXETH",    # hourly ETH
    "KXETHD",
    "KXSOLD",
    "KXSOLE",
    "KXDOGED",
    "KXDOGE",
    "KXXRPD",
    "KXXRP",
    "KXSHIBA",
    "KXSHIBAD",
    "KXBTC15M",  # 15-minute BTC
    "KXETH15M",
    "KXSOL15M",
]

KEEP = [
    "ticker", "series_ticker", "event_ticker", "open_time", "close_time",
    "status", "result", "last_price_dollars", "volume_fp",
    "settlement_value_dollars",
]


def main() -> int:
    settings = Settings()
    started = pd.Timestamp.utcnow()
    rows_all: list[dict[str, Any]] = []
    print(f"Started {started.isoformat()}", flush=True)
    with KalshiClient(settings) as client:
        for s in FULL_SERIES:
            t0 = time.time()
            rows: list[dict[str, Any]] = []
            for m in client.paginate(
                "/historical/markets", item_key="markets",
                limit=1000, max_pages=2000, series_ticker=s,
            ):
                rows.append({k: m.get(k) for k in KEEP})
            elapsed = time.time() - t0
            print(f"  {s:12s} n={len(rows):7d}  ({elapsed:.1f}s)", flush=True)
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            df["series_ticker"] = s
            df["close_time"] = pd.to_datetime(df["close_time"], utc=True, errors="coerce")
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
            df["last_price"] = pd.to_numeric(df["last_price_dollars"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume_fp"], errors="coerce")
            df["lifetime_hours"] = (
                (df["close_time"] - df["open_time"]).dt.total_seconds() / 3600.0
            )
            # Drop non-binary
            df = df[df["status"].isin(["finalized", "settled"])]
            df = df[df["result"].isin(["yes", "no"])]
            df.to_parquet(OUT_DIR / f"crypto_full_{s}.parquet", index=False)
            rows_all.extend(df.to_dict("records"))

    if not rows_all:
        print("No data fetched", flush=True)
        return 1

    big = pd.DataFrame(rows_all)
    big["close_time"] = pd.to_datetime(big["close_time"], utc=True, errors="coerce")
    big.to_parquet(OUT_DIR / "crypto_full_all.parquet", index=False)

    print()
    print("=" * 72, flush=True)
    print(f"Total markets across full series: {len(big)}", flush=True)
    print("Per-series v1-eligible counts (price 0.70-0.95):", flush=True)
    for s in FULL_SERIES:
        sub = big[big["series_ticker"] == s]
        if sub.empty:
            continue
        v1 = sub[sub["last_price"].between(0.70, 0.95, inclusive="both")]
        n = len(v1)
        yes_rate = float((v1["result"] == "yes").mean()) if n > 0 else None
        n_2025 = int((v1["close_time"].dt.year == 2025).sum())
        n_2026 = int((v1["close_time"].dt.year == 2026).sum())
        # Distinct events
        n_events = sub["event_ticker"].nunique()
        n_v1_events = v1["event_ticker"].nunique()
        print(
            f"  {s:10s} n={len(sub):7d} v1_band={n:6d} "
            f"v1_events={n_v1_events:5d} "
            f"v1_yes={yes_rate} v1_25={n_2025:5d} v1_26={n_2026:5d} "
            f"events_total={n_events:6d}",
            flush=True,
        )

    # Total v1-eligible across all
    v1_all = big[big["last_price"].between(0.70, 0.95, inclusive="both")]
    print()
    print(f"Total v1-eligible (across all FULL_SERIES): {len(v1_all)}",
          flush=True)
    print(f"  YES rate: {float((v1_all['result']=='yes').mean()):.3f}",
          flush=True)
    print(f"  Distinct events containing >=1 v1 contract: {v1_all['event_ticker'].nunique()}",
          flush=True)
    # By close-month
    print()
    print("v1-band by close-month:", flush=True)
    months = v1_all["close_time"].dt.to_period("M")
    for m, c in months.value_counts().sort_index().items():
        print(f"  {m}: {c}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
