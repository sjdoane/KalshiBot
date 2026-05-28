"""V10-B resolution poller.

Polls Kalshi /markets/{ticker} for each forecast ticker; records
the settled status and outcome. Run repeatedly until enough resolutions
accumulate for Brier delta computation (n >= 50 ideal, n >= 80 for SHIP gate).

Usage:
    python scripts/v10/poll_v10b_resolutions.py
        # Reads data/v10/v10b_forecasts.parquet
        # Polls each open ticker
        # Writes data/v10/v10b_resolutions.parquet

Idempotent: re-running updates the resolutions parquet with any new
settled markets. Already-settled rows are not re-fetched.

READ-ONLY against Kalshi API. No /portfolio/orders.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

import pandas as pd
import requests

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
FORECASTS_PATH = PROJECT_ROOT / "data" / "v10" / "v10b_forecasts.parquet"
RESOLUTIONS_PATH = PROJECT_ROOT / "data" / "v10" / "v10b_resolutions.parquet"


def _auth_headers(method: str, path: str) -> dict[str, str]:
    try:
        from kalshi_bot.data.auth import build_headers, load_private_key
        key_id = os.environ.get("KALSHI_API_KEY_ID", "")
        pem_path_str = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if not key_id or not pem_path_str:
            return {}
        return build_headers(load_private_key(Path(pem_path_str)), key_id, method, path)
    except Exception:
        return {}


def fetch_market_state(ticker: str) -> dict:
    """Fetch current state of a market. Returns dict with status, result, fields."""
    path = f"/trade-api/v2/markets/{ticker}"
    headers = _auth_headers("GET", path)
    url = KALSHI_BASE + f"/markets/{ticker}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return {"ticker": ticker, "status": "not_found", "error": "404"}
        resp.raise_for_status()
        data = resp.json().get("market", {})
        return {
            "ticker": ticker,
            "status": data.get("status", "unknown"),
            "result": data.get("result", ""),
            "close_time": data.get("close_time", ""),
            "settled_time": data.get("settled_time", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
    except requests.RequestException as exc:
        return {"ticker": ticker, "status": "error", "error": str(exc)[:100]}


def map_result_to_outcome(result: str) -> int | None:
    """Map Kalshi result field to YES=1 or NO=0. Returns None if not yet resolved."""
    r = (result or "").lower().strip()
    if r == "yes":
        return 1
    if r == "no":
        return 0
    # Other values: "settled", "" (open), etc.
    return None


def main() -> None:
    if not FORECASTS_PATH.exists():
        print(f"ERROR: forecasts parquet not found at {FORECASTS_PATH}")
        sys.exit(1)

    df_forecasts = pd.read_parquet(FORECASTS_PATH)
    print(f"Forecasts to poll: {len(df_forecasts)}")
    tickers = df_forecasts["ticker"].unique().tolist()
    print(f"Unique tickers: {len(tickers)}")

    # Load existing resolutions (idempotent)
    if RESOLUTIONS_PATH.exists():
        df_existing = pd.read_parquet(RESOLUTIONS_PATH)
        already_settled = set(df_existing[df_existing["outcome"].notna()]["ticker"].tolist())
        print(f"Already-settled tickers (skip): {len(already_settled)}")
    else:
        df_existing = pd.DataFrame()
        already_settled = set()

    rows: list[dict] = []
    n_settled = 0
    n_open = 0
    n_error = 0

    for i, ticker in enumerate(tickers, 1):
        if ticker in already_settled:
            continue

        state = fetch_market_state(ticker)
        outcome = map_result_to_outcome(state.get("result", ""))
        state["outcome"] = outcome

        if outcome is not None:
            n_settled += 1
        elif state.get("status") == "error":
            n_error += 1
        else:
            n_open += 1

        rows.append(state)

        # Rate limit
        time.sleep(0.10)

        if i % 25 == 0:
            print(f"  Polled {i}/{len(tickers)}: settled={n_settled} open={n_open} err={n_error}", flush=True)

    df_new = pd.DataFrame(rows)
    # Merge with existing (existing wins for already-settled rows)
    if not df_existing.empty:
        already_keys = set(df_existing["ticker"])
        df_new_only = df_new[~df_new["ticker"].isin(already_keys)]
        df_combined = pd.concat([df_existing, df_new_only], ignore_index=True)
        # Also update any previously-open rows that are now settled
        for _, row in df_new.iterrows():
            if row.get("outcome") is not None and row["ticker"] in already_keys:
                df_combined.loc[df_combined["ticker"] == row["ticker"], "outcome"] = row["outcome"]
                df_combined.loc[df_combined["ticker"] == row["ticker"], "status"] = row["status"]
                df_combined.loc[df_combined["ticker"] == row["ticker"], "result"] = row["result"]
                df_combined.loc[df_combined["ticker"] == row["ticker"], "settled_time"] = row.get("settled_time", "")
    else:
        df_combined = df_new

    df_combined.to_parquet(RESOLUTIONS_PATH, index=False)
    print()
    print(f"Resolution poll complete.")
    print(f"  New rows polled: {len(rows)}")
    print(f"  Newly settled: {n_settled}")
    print(f"  Still open: {n_open}")
    print(f"  Errors: {n_error}")

    # Summary across all tickers in combined parquet
    total_settled = (df_combined["outcome"].notna()).sum() if "outcome" in df_combined.columns else 0
    print(f"  Total settled across all polls: {total_settled} / {len(df_combined)}")
    print(f"Written to: {RESOLUTIONS_PATH}")


if __name__ == "__main__":
    main()
