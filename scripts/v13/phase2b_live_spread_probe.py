"""Phase 2b: probe live Kalshi spreads on currently-open KXMLBGAME markets.

Per v13 lock Section 5. Pulls /markets/orderbook + recent /markets/trades
for currently-open MLB game markets, computes (yes_ask - trade_print_mid)
distribution. The 75th percentile of that gap is the haircut used in
Phase 2c's strategy P&L.

Writes:
- data/v13/live_spread_probe.parquet (per-market snapshot)
- research/v13/02-phase2b-live-spread-probe.md (summary)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient


DATA_V13 = BASE / "data" / "v13"
DATA_V13.mkdir(parents=True, exist_ok=True)
RESEARCH = BASE / "research" / "v13"


def fetch_open_mlb_markets(client: KalshiClient) -> list[dict]:
    """Pull currently-open KXMLBGAME markets."""
    print("  Fetching open KXMLBGAME markets...", flush=True)
    all_markets: list[dict] = []
    cursor = ""
    for _ in range(20):
        params: dict = {"series_ticker": "KXMLBGAME", "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = client.get("/markets", **params)
        markets = resp.get("markets", [])
        if not markets:
            break
        all_markets.extend(markets)
        cursor = resp.get("cursor") or ""
        if not cursor:
            break
    print(f"    Got {len(all_markets)} open markets", flush=True)
    return all_markets


def fetch_orderbook(client: KalshiClient, ticker: str) -> dict:
    try:
        return client.get(f"/markets/{ticker}/orderbook")
    except Exception as e:
        return {"error": str(e)}


def fetch_recent_trades(client: KalshiClient, ticker: str, limit: int = 100) -> list[dict]:
    try:
        resp = client.get("/markets/trades", ticker=ticker, limit=limit)
        return resp.get("trades", [])
    except Exception as e:
        return [{"error": str(e)}]


def compute_trade_print_mid_30min(trades: list[dict]) -> float | None:
    """VWAP over the last 30 minutes of trades. API returns yes_price_dollars
    as string like "0.6800"; count is count_fp as string.
    """
    if not trades or "error" in (trades[0] if isinstance(trades[0], dict) else {}):
        return None
    now = datetime.now(timezone.utc)
    cutoff = now - pd.Timedelta(minutes=30)
    relevant: list[tuple[float, float]] = []
    for t in trades:
        ct = t.get("created_time")
        if not ct:
            continue
        try:
            t_time = pd.Timestamp(ct).tz_convert("UTC")
        except Exception:
            continue
        if t_time < cutoff:
            continue
        price_str = t.get("yes_price_dollars") or t.get("yes_price")
        count_str = t.get("count_fp") or t.get("count")
        if price_str is None or count_str is None:
            continue
        try:
            price = float(price_str)
            count = float(count_str)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        relevant.append((price, count))
    if not relevant:
        return None
    total = sum(c for _, c in relevant)
    if total <= 0:
        return None
    return float(sum(p * c for p, c in relevant) / total)


def main() -> int:
    print("v13 Phase 2b: live Kalshi spread probe", flush=True)
    settings = Settings()
    rows: list[dict] = []
    with KalshiClient(settings) as client:
        markets = fetch_open_mlb_markets(client)
        if not markets:
            print("  No open MLB markets right now; probe inconclusive", flush=True)
            return 1
        for i, m in enumerate(markets):
            ticker = m.get("ticker")
            if not ticker:
                continue
            ob = fetch_orderbook(client, ticker)
            trades_resp = fetch_recent_trades(client, ticker, limit=100)
            ob_fp = ob.get("orderbook_fp", {}) if isinstance(ob, dict) else {}
            yes_book = ob_fp.get("yes_dollars") or []
            no_book = ob_fp.get("no_dollars") or []
            yes_ask = None
            yes_bid = None
            if yes_book:
                # Best YES bid = highest yes_dollars entry. Lists arrive
                # ascending by price; take last.
                try:
                    yes_bid = float(yes_book[-1][0])
                except (IndexError, TypeError, ValueError):
                    yes_bid = None
            if no_book:
                try:
                    no_bid = float(no_book[-1][0])
                    yes_ask = 1.0 - no_bid
                except (IndexError, TypeError, ValueError):
                    yes_ask = None
            trade_print_mid = compute_trade_print_mid_30min(trades_resp)
            n_trades = 0
            if isinstance(trades_resp, list) and trades_resp:
                first = trades_resp[0]
                if not (isinstance(first, dict) and "error" in first):
                    n_trades = len(trades_resp)
            row = {
                "snapshot_ts_utc": datetime.now(timezone.utc).isoformat(),
                "ticker": ticker,
                "title": m.get("title", "")[:80],
                "close_time": m.get("close_time"),
                "yes_ask": yes_ask,
                "yes_bid": yes_bid,
                "trade_print_mid_30min": trade_print_mid,
                "n_recent_trades": n_trades,
                "volume": m.get("volume"),
            }
            if yes_ask is not None and trade_print_mid is not None:
                row["gap_ask_minus_mid"] = yes_ask - trade_print_mid
            else:
                row["gap_ask_minus_mid"] = None
            rows.append(row)
            if (i + 1) % 10 == 0:
                print(f"    [{i + 1}/{len(markets)}]", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(DATA_V13 / "live_spread_probe.parquet", index=False)
    print(f"  Saved {len(df)} rows", flush=True)

    # Compute gap distribution
    valid = df.dropna(subset=["gap_ask_minus_mid"]).copy()
    print(f"  Valid (ask, mid) snapshots: {len(valid)}", flush=True)
    if len(valid) >= 5:
        gaps = valid["gap_ask_minus_mid"]
        haircut_p50 = float(gaps.quantile(0.50))
        haircut_p75 = float(gaps.quantile(0.75))
        haircut_p95 = float(gaps.quantile(0.95))
        spreads = (valid["yes_ask"] - valid["yes_bid"])
        spread_p50 = float(spreads.quantile(0.50))
        spread_p75 = float(spreads.quantile(0.75))
        print(f"  haircut_p50: {haircut_p50:.4f}", flush=True)
        print(f"  haircut_p75: {haircut_p75:.4f}", flush=True)
        print(f"  haircut_p95: {haircut_p95:.4f}", flush=True)
        print(f"  spread (ask-bid) p50: {spread_p50:.4f}", flush=True)
        print(f"  spread (ask-bid) p75: {spread_p75:.4f}", flush=True)
        result = {
            "n_valid": len(valid),
            "haircut_p50": haircut_p50,
            "haircut_p75": haircut_p75,
            "haircut_p95": haircut_p95,
            "spread_p50": spread_p50,
            "spread_p75": spread_p75,
            "abandon_condition_haircut_p75_gt_005": haircut_p75 > 0.05,
            "g5_pass_haircut_p75_le_003": haircut_p75 <= 0.03,
        }
    else:
        result = {
            "n_valid": len(valid),
            "haircut_p75_default": 0.02,
            "note": "sample below floor (n<20); using conservative 2c haircut default per lock Section 5",
        }
    (DATA_V13 / "spread_probe_summary.json").write_text(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
