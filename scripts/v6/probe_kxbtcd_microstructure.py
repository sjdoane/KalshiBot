"""v6 Agent C: probe KXBTCD microstructure for spread / depth / trade timing.

The v5 crypto_full_KXBTCD parquet has only contract-level aggregates
(no bid/ask, no depth, no per-trade timestamps). This probe pulls:

1. /historical/trades for a sample of post-Oct-2024 KXBTCD contracts to
   profile trade timing in the T-30 / T-15 / T-5 min windows.
2. /markets/<ticker> for currently-open KXBTCD markets to snapshot a
   single live yes_bid / yes_ask / volume.

Outputs:
- data/v6/kxbtcd_sample_trades.parquet (one row per trade)
- data/v6/kxbtcd_live_orderbook_snapshot.parquet (one row per open market)

Polite: defaults to a 100-market sample, sequential pagination.

Run: uv run python -m scripts.v6.probe_kxbtcd_microstructure
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "v6"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FLIP_DATE = pd.Timestamp("2024-10-01", tz="UTC")


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.utcnow().isoformat()}] {msg}", flush=True)


def sample_contracts(n_per_band: int, seed: int = 42) -> pd.DataFrame:
    """Stratified random sample from post-flip KXBTCD 1h contracts.

    Strata = last_price band. Returns one row per chosen contract.
    """
    df = pd.read_parquet(REPO_ROOT / "data" / "v5" / "crypto_full_KXBTCD.parquet")
    df = df[df["close_time"] >= FLIP_DATE].copy()
    df = df[(df["lifetime_hours"] >= 0.9) & (df["lifetime_hours"] <= 1.1)].copy()
    # Restrict to contracts that actually traded; else trade-window stats
    # are dominated by deep-OTM zeros.
    df = df[df["volume"] > 0].copy()

    bands = {
        "extreme-low": (0.05, 0.20),
        "midband": (0.55, 0.80),
        "narrow": (0.70, 0.95),
        "extreme-high": (0.80, 0.95),
        "low-mid": (0.20, 0.55),
    }

    rng = np.random.default_rng(seed)
    picks: list[pd.DataFrame] = []
    for name, (lo, hi) in bands.items():
        sub = df[(df["last_price"] >= lo) & (df["last_price"] <= hi)]
        if len(sub) == 0:
            continue
        take = min(n_per_band, len(sub))
        idx = rng.choice(sub.index.to_numpy(), size=take, replace=False)
        chosen = sub.loc[idx].assign(band=name)
        picks.append(chosen)

    out = pd.concat(picks, ignore_index=True).drop_duplicates("ticker")
    log(f"Sampled {len(out)} unique contracts across bands")
    return out


def fetch_trades_for_ticker(
    client: KalshiClient,
    ticker: str,
    close_time: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> list[dict]:
    """Pull all trades in the [close - 60 min, close] window for one
    contract. Uses /historical/trades when window is before cutoff and
    /markets/trades when after.
    """
    window_start = close_time - pd.Timedelta(minutes=60)
    window_end = close_time + pd.Timedelta(minutes=5)
    rows: list[dict] = []
    try:
        if window_end <= cutoff:
            rows.extend(
                client.paginate(
                    "/historical/trades",
                    item_key="trades",
                    limit=1000,
                    max_pages=20,
                    ticker=ticker,
                    min_ts=int(window_start.timestamp()),
                    max_ts=int(window_end.timestamp()),
                )
            )
        elif window_start >= cutoff:
            rows.extend(
                client.paginate(
                    "/markets/trades",
                    item_key="trades",
                    limit=1000,
                    max_pages=20,
                    ticker=ticker,
                    min_ts=int(window_start.timestamp()),
                    max_ts=int(window_end.timestamp()),
                )
            )
        else:
            # straddles cutoff
            rows.extend(
                client.paginate(
                    "/historical/trades",
                    item_key="trades",
                    limit=1000,
                    max_pages=20,
                    ticker=ticker,
                    min_ts=int(window_start.timestamp()),
                    max_ts=int(cutoff.timestamp()),
                )
            )
            rows.extend(
                client.paginate(
                    "/markets/trades",
                    item_key="trades",
                    limit=1000,
                    max_pages=20,
                    ticker=ticker,
                    min_ts=int(cutoff.timestamp()),
                    max_ts=int(window_end.timestamp()),
                )
            )
    except Exception as e:  # noqa: BLE001
        log(f"  trades fetch failed for {ticker}: {type(e).__name__}: {e}")
    return rows


def snapshot_live_orderbook(client: KalshiClient, n: int = 30) -> pd.DataFrame:
    """Snapshot live KXBTCD market bids/asks. Pulls open markets in the
    series. n caps how many we look at to keep API usage modest.
    """
    rows: list[dict] = []
    try:
        for m in client.paginate(
            "/markets",
            item_key="markets",
            limit=200,
            max_pages=5,
            series_ticker="KXBTCD",
            status="open",
        ):
            rows.append(m)
            if len(rows) >= n:
                break
    except Exception as e:  # noqa: BLE001
        log(f"  /markets failed: {type(e).__name__}: {e}")
        return pd.DataFrame()

    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-band", type=int, default=20)
    parser.add_argument("--n-live", type=int, default=30)
    parser.add_argument("--skip-trades", action="store_true")
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings()

    with KalshiClient(settings) as client:
        # Cutoff for routing between /historical/trades and /markets/trades
        cutoff = pd.Timestamp(
            client.get("/historical/cutoff")["trades_created_ts"]
        ).tz_convert("UTC")
        log(f"trades historical cutoff: {cutoff.isoformat()}")

        if not args.skip_live:
            log("snapshotting live KXBTCD orderbook ...")
            live = snapshot_live_orderbook(client, n=args.n_live)
            if not live.empty:
                out_path = OUT_DIR / "kxbtcd_live_orderbook_snapshot.parquet"
                live.to_parquet(out_path, index=False)
                log(f"  wrote {out_path} ({len(live)} rows)")
                cols = [
                    "ticker", "yes_bid", "yes_ask", "no_bid", "no_ask",
                    "volume", "open_interest", "last_price",
                ]
                for c in cols:
                    if c not in live.columns:
                        live[c] = None
                summary = live[cols].copy()
                summary["spread"] = summary["yes_ask"] - summary["yes_bid"]
                log("  live orderbook (first 10):")
                print(summary.head(10).to_string(), flush=True)
            else:
                log("  no live KXBTCD markets returned")

        if not args.skip_trades:
            sample = sample_contracts(n_per_band=args.n_per_band)
            log(f"fetching trades for {len(sample)} sampled contracts ...")
            all_rows: list[dict] = []
            for i, row in enumerate(sample.itertuples(index=False), 1):
                rows = fetch_trades_for_ticker(
                    client,
                    ticker=row.ticker,
                    close_time=row.close_time,
                    cutoff=cutoff,
                )
                for r in rows:
                    r["_sample_ticker"] = row.ticker
                    r["_sample_band"] = row.band
                    r["_sample_close_time"] = row.close_time
                    r["_sample_last_price"] = row.last_price
                    r["_sample_volume_total"] = row.volume
                all_rows.extend(rows)
                if i % 20 == 0:
                    log(f"  {i}/{len(sample)} done, trades collected: {len(all_rows)}")
                time.sleep(0.05)

            trades = pd.DataFrame(all_rows)
            out_path = OUT_DIR / "kxbtcd_sample_trades.parquet"
            trades.to_parquet(out_path, index=False)
            log(f"wrote {out_path} ({len(trades)} trades from {len(sample)} contracts)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
