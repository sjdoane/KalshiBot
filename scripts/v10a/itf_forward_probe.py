"""Round 15c Track 2C: ITF tennis forward-record probe.

ITF (lower-tier tennis) was found in the Round 15b live-spread probe
to have 100% of sampled markets at 3c+ spread with hundreds of open
markets. Not in Becker (post-rebrand era), so no historical edge
measurement is possible. This script collects FORWARD-LOOKING data
that future analysis can use to estimate maker fill rate and edge.

Each cycle (default every 30 minutes for a configurable wall clock):
1. Pull all open KXITFMATCH and KXITFWMATCH markets.
2. Filter to mid in [0.30, 0.70].
3. For each market, snapshot orderbook (yes_bid, yes_ask, depth on
   both sides) and append to data/v10a/itf_orderbook_log.parquet.
4. Pull recent trades for each market, dedup by trade_id, and append
   to data/v10a/itf_trades_log.parquet.

After enough cycles (12+), the analyst can answer:
- What fraction of retail trade prints are at or beyond midprice
  (i.e., trades that a passive maker quote at mid would have caught)?
- What is the realistic spread persistence?
- What is the realized P&L of a synthetic maker strategy?

Defaults: 16 cycles at 30-minute spacing = 8 hours overnight.

Run with: .venv-kronos\Scripts\python.exe scripts\v10a\itf_forward_probe.py
  (uses kalshi_bot.data.kalshi_client which reads .env)

Override:
  --cycles N           Total cycles to run (default 16)
  --interval-min N     Minutes between cycles (default 30)
  --out-dir PATH       Output dir (default data/v10a)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient

PREFIXES = ["KXITFMATCH", "KXITFWMATCH"]


def parse_orderbook(ob_payload: dict) -> dict:
    ob = ob_payload.get("orderbook_fp", {}) or {}
    yes_levels = ob.get("yes_dollars", []) or []
    no_levels = ob.get("no_dollars", []) or []
    yes_bid = 0.0
    yes_ask = 1.0
    yes_depth_at_bid = 0.0
    no_depth_at_bid = 0.0
    yes_depth_total = 0.0
    no_depth_total = 0.0
    if yes_levels:
        prices = [float(p) for p, _ in yes_levels]
        yes_bid = max(prices)
        for p, sz in yes_levels:
            yes_depth_total += float(sz)
            if float(p) == yes_bid:
                yes_depth_at_bid += float(sz)
    if no_levels:
        prices = [float(p) for p, _ in no_levels]
        no_bid = max(prices)
        yes_ask = 1.0 - no_bid
        for p, sz in no_levels:
            no_depth_total += float(sz)
            if float(p) == no_bid:
                no_depth_at_bid += float(sz)
    spread = yes_ask - yes_bid
    mid = (yes_bid + yes_ask) / 2.0 if yes_levels and no_levels else None
    return {
        "yes_bid": yes_bid, "yes_ask": yes_ask, "spread": spread, "mid": mid,
        "yes_depth_at_bid": yes_depth_at_bid, "no_depth_at_bid": no_depth_at_bid,
        "yes_depth_total": yes_depth_total, "no_depth_total": no_depth_total,
    }


def fetch_open_markets(client: KalshiClient, prefix: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for m in client.paginate("/markets", item_key="markets", limit=200,
                                  status="open", series_ticker=prefix, max_pages=10):
            rows.append(m)
    except Exception as exc:
        print(f"  [WARN] paginate failed for {prefix}: {exc}", file=sys.stderr)
    return rows


def run_cycle(client: KalshiClient, cycle_idx: int,
              orderbook_path: Path, trades_path: Path) -> None:
    ts = datetime.now(UTC).isoformat()
    ob_rows = []
    tr_rows = []
    for prefix in PREFIXES:
        markets = fetch_open_markets(client, prefix)
        print(f"  cycle {cycle_idx} {prefix}: {len(markets)} open markets")
        for m in markets:
            ticker = m.get("ticker", "")
            if not ticker:
                continue
            try:
                ob_payload = client.get(f"/markets/{ticker}/orderbook")
            except Exception:
                continue
            parsed = parse_orderbook(ob_payload)
            if parsed["mid"] is None:
                continue
            if not (0.30 <= parsed["mid"] <= 0.70):
                continue
            ob_rows.append({
                "ts_utc": ts, "cycle_idx": cycle_idx,
                "prefix": prefix, "ticker": ticker,
                "yes_bid": parsed["yes_bid"], "yes_ask": parsed["yes_ask"],
                "spread": parsed["spread"], "mid": parsed["mid"],
                "yes_depth_at_bid": parsed["yes_depth_at_bid"],
                "no_depth_at_bid": parsed["no_depth_at_bid"],
                "yes_depth_total": parsed["yes_depth_total"],
                "no_depth_total": parsed["no_depth_total"],
                "close_time": m.get("close_time", ""),
            })

            # Pull trades for this ticker
            try:
                trades = list(client.paginate(
                    "/markets/trades", item_key="trades", limit=100,
                    ticker=ticker, max_pages=2,
                ))
            except Exception:
                trades = []
            for t in trades:
                # Kalshi /markets/trades post-March-2026 uses dollar-string
                # fields (yes_price_dollars, no_price_dollars, count_fp).
                # Fall back to legacy int fields for forward compatibility.
                yp = t.get("yes_price_dollars")
                if yp is not None:
                    try:
                        yes_price_cents = int(round(float(yp) * 100))
                    except (TypeError, ValueError):
                        yes_price_cents = None
                else:
                    yes_price_cents = t.get("yes_price")
                np_ = t.get("no_price_dollars")
                if np_ is not None:
                    try:
                        no_price_cents = int(round(float(np_) * 100))
                    except (TypeError, ValueError):
                        no_price_cents = None
                else:
                    no_price_cents = t.get("no_price")
                cf = t.get("count_fp")
                if cf is not None:
                    try:
                        count_val = int(round(float(cf)))
                    except (TypeError, ValueError):
                        count_val = None
                else:
                    count_val = t.get("count")
                tr_rows.append({
                    "snapshot_ts_utc": ts, "cycle_idx": cycle_idx,
                    "prefix": prefix, "ticker": ticker,
                    "trade_id": t.get("trade_id"),
                    "yes_price": yes_price_cents,
                    "no_price": no_price_cents,
                    "count": count_val,
                    "taker_side": t.get("taker_side"),
                    "taker_book_side": t.get("taker_book_side"),
                    "taker_outcome_side": t.get("taker_outcome_side"),
                    "created_time": t.get("created_time"),
                })

    if ob_rows:
        df_ob = pd.DataFrame(ob_rows)
        if orderbook_path.exists():
            existing = pd.read_parquet(orderbook_path)
            df_ob = pd.concat([existing, df_ob], ignore_index=True)
        df_ob.to_parquet(orderbook_path, index=False)
    if tr_rows:
        df_tr = pd.DataFrame(tr_rows)
        if trades_path.exists():
            existing = pd.read_parquet(trades_path)
            # Dedup on trade_id
            df_tr = pd.concat([existing, df_tr], ignore_index=True)
            df_tr = df_tr.drop_duplicates(subset=["ticker", "trade_id"], keep="first")
        df_tr.to_parquet(trades_path, index=False)
    print(f"  cycle {cycle_idx} appended {len(ob_rows)} orderbook rows, "
          f"{len(tr_rows)} trade rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=16)
    parser.add_argument("--interval-min", type=int, default=30)
    parser.add_argument("--out-dir", type=str, default="data/v10a")
    args = parser.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    orderbook_path = out_dir / "itf_orderbook_log.parquet"
    trades_path = out_dir / "itf_trades_log.parquet"

    settings = load_settings()
    with KalshiClient(settings) as client:
        for i in range(args.cycles):
            t0 = time.time()
            print(f"[{datetime.now(UTC).isoformat()}] cycle {i + 1}/{args.cycles}")
            try:
                run_cycle(client, i + 1, orderbook_path, trades_path)
            except Exception as exc:
                print(f"  [ERROR] cycle failed: {exc}", file=sys.stderr)
            elapsed = time.time() - t0
            if i + 1 < args.cycles:
                sleep_s = max(60, args.interval_min * 60 - int(elapsed))
                print(f"  sleeping {sleep_s}s before next cycle")
                time.sleep(sleep_s)
    print(f"\nDone. {args.cycles} cycles completed.")
    print(f"  orderbook log: {orderbook_path}")
    print(f"  trades log: {trades_path}")


if __name__ == "__main__":
    main()
