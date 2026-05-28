"""V10-B Phase 1 data probe: uncertain-mid market inventory.

Probes Kalshi /markets for open markets closing 2026-05-27 through 2026-06-30.
Applies V10-B filters:
- Series prefix NOT in v1 denylist or crypto denylist
- Orderbook mid in [0.30, 0.70] (uncertain regime)
- Groups by series prefix

READ-ONLY. No /portfolio/* calls. No writes to .env or production data.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient

# Denylists from CLAUDE.md / v4-H / v10 spec
V1_DENYLIST = {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"}
CRYPTO_DENYLIST = {"KXBTCD", "KXETHD", "KXBTC15M", "KXETH15M"}
FULL_DENYLIST = V1_DENYLIST | CRYPTO_DENYLIST

# Target series for V10-B (from 04-phase0-synthesis.md)
TARGET_SERIES = {
    "KXMLBTOTAL", "KXMLBF5", "KXMLBRFI", "KXMLBKS", "KXMLBHIT",
    "KXMLBSPREAD", "KXMLBHR", "KXMLBHRR",
    "KXNBASPREAD", "KXNBATOTAL", "KXNBAOVERTIME", "KXNBAGAME",
    "KXNHLGAME",
    "KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY", "KXVALORANTGAME",
    "KXITFWMATCH", "KXATPCHALLENGERMATCH",
    "KXCONMEBOLLIBGAME", "KXCONMEBOLSUDGAME",
}

# Date range for close_time
PROBE_START = datetime(2026, 5, 27, tzinfo=timezone.utc)
PROBE_END = datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
MIN_CLOSE_TS = int(PROBE_START.timestamp())
MAX_CLOSE_TS = int(PROBE_END.timestamp())
NOW = datetime.now(timezone.utc)


def get_mid(orderbook: dict) -> float | None:
    """Compute YES mid from orderbook response.

    Tries yes_bid + yes_ask directly; falls back to parity (1 - no_bid).
    """
    bids = orderbook.get("yes", [])
    asks_no = orderbook.get("no", [])

    yes_bid = None
    yes_ask = None

    if bids:
        # bids sorted by price descending; best bid is first
        yes_bid = max((b.get("price", 0) for b in bids), default=None)
        if yes_bid is not None:
            yes_bid = yes_bid / 100.0  # convert cents to dollars

    if asks_no:
        # no_bid best bid (cents) -> yes_ask = 1 - no_bid_best / 100
        no_bid_best = max((a.get("price", 0) for a in asks_no), default=None)
        if no_bid_best is not None:
            yes_ask = 1.0 - (no_bid_best / 100.0)

    if yes_bid is not None and yes_ask is not None:
        mid = (yes_bid + yes_ask) / 2.0
        return mid
    elif yes_bid is not None:
        return yes_bid
    elif yes_ask is not None:
        return yes_ask
    return None


def main() -> None:
    settings = Settings()
    client = KalshiClient(settings)

    # Track results by series
    all_markets: list[dict] = []
    uncertain_markets: list[dict] = []
    series_counts: dict[str, int] = defaultdict(int)
    series_uncertain: dict[str, int] = defaultdict(int)
    series_errors: dict[str, int] = defaultdict(int)

    target_series_with_data: set[str] = set()

    print(f"Probe start: {NOW.isoformat()}")
    print(f"Close range: {PROBE_START.date()} to {PROBE_END.date()}")
    print(f"Uncertain band: mid in [0.30, 0.70]")
    print(f"Scanning {len(TARGET_SERIES)} target series plus broad open market scan...")
    print()

    # First: scan target series specifically
    for series_prefix in sorted(TARGET_SERIES):
        if series_prefix in FULL_DENYLIST:
            continue
        try:
            resp = client.get(
                "/markets",
                params={
                    "series_ticker": series_prefix,
                    "status": "open",
                    "limit": 200,
                }
            )
            markets = resp.get("markets", [])
            time.sleep(0.5)  # rate limit courtesy
        except Exception as e:
            print(f"  ERROR fetching {series_prefix}: {e}")
            continue

        for mkt in markets:
            close_ts = mkt.get("close_time")
            if close_ts:
                # close_time may be ISO string or timestamp
                if isinstance(close_ts, str):
                    try:
                        close_dt = datetime.fromisoformat(
                            close_ts.replace("Z", "+00:00")
                        )
                        close_ts_int = int(close_dt.timestamp())
                    except Exception:
                        continue
                else:
                    close_ts_int = int(close_ts)
                    close_dt = datetime.fromtimestamp(close_ts_int, tz=timezone.utc)
            else:
                continue

            if not (MIN_CLOSE_TS <= close_ts_int <= MAX_CLOSE_TS):
                continue

            ticker = mkt.get("ticker", "")
            prefix = mkt.get("series_ticker", series_prefix)
            series_counts[prefix] += 1

            # Compute days to close
            days_to_close = (close_dt - NOW).days

            all_markets.append({
                "ticker": ticker,
                "series": prefix,
                "close_dt": close_dt.isoformat(),
                "days_to_close": days_to_close,
            })

    # Now probe orderbooks for all collected markets
    print(f"Found {len(all_markets)} open markets in target series closing in range.")
    print(f"Probing orderbooks for uncertain-mid filter...")
    print()

    orderbook_errors = 0
    orderbook_ok = 0
    empty_books = 0

    for i, mkt in enumerate(all_markets):
        ticker = mkt["ticker"]
        prefix = mkt["series"]

        try:
            ob_resp = client.get(f"/markets/{ticker}/orderbook")
            time.sleep(0.4)
        except Exception as e:
            series_errors[prefix] += 1
            orderbook_errors += 1
            continue

        orderbook = ob_resp.get("orderbook", ob_resp)
        mid = get_mid(orderbook)

        if mid is None:
            empty_books += 1
            series_errors[prefix] += 1
            continue

        orderbook_ok += 1
        mkt["mid"] = round(mid, 4)

        if 0.30 <= mid <= 0.70:
            series_uncertain[prefix] += 1
            target_series_with_data.add(prefix)
            uncertain_markets.append(mkt)

        if (i + 1) % 20 == 0:
            print(f"  Probed {i+1}/{len(all_markets)} markets, "
                  f"{len(uncertain_markets)} uncertain so far...")

    print()
    print("=" * 60)
    print("RESULTS: Market Inventory by Series")
    print("=" * 60)
    print(f"{'Series':<36} {'Total Open':>10} {'Uncertain [.30-.70]':>20}")
    print("-" * 70)

    total_open = 0
    total_uncertain = 0
    for s in sorted(series_counts.keys()):
        n_open = series_counts[s]
        n_unc = series_uncertain.get(s, 0)
        total_open += n_open
        total_uncertain += n_unc
        flag = " <-- TARGET" if n_unc > 0 else ""
        print(f"{s:<36} {n_open:>10} {n_unc:>20}{flag}")

    print("-" * 70)
    print(f"{'TOTAL':<36} {total_open:>10} {total_uncertain:>20}")
    print()

    # Short-horizon breakdown (1-30 days)
    short_horizon = [m for m in uncertain_markets if 1 <= m.get("days_to_close", 999) <= 30]
    medium_horizon = [m for m in uncertain_markets if 31 <= m.get("days_to_close", 999) <= 60]

    print(f"Short horizon (1-30 days):  n = {len(short_horizon)}")
    print(f"Medium horizon (31-60 days): n = {len(medium_horizon)}")
    print(f"All uncertain in range:      n = {total_uncertain}")
    print()
    print(f"Orderbook probe stats: ok={orderbook_ok}, empty={empty_books}, error={orderbook_errors}")
    print()

    # Power analysis note
    n = total_uncertain
    import math
    se = 0.39 / math.sqrt(max(n, 1))  # AIA-implied sigma_delta
    mdd = 2.802 * se  # 80% power, one-sided z_alpha+z_beta = 1.96+0.842
    print(f"Power analysis at n={n}:")
    print(f"  AIA-implied sigma_delta = 0.39")
    print(f"  SE(Brier_delta) = {se:.4f}")
    print(f"  Min detectable delta (80% power) = {mdd:.4f}")
    print(f"  Gate threshold = 0.005")
    print(f"  Required n for 80% power at gate=0.005: {int((2.802*0.39/0.005)**2)}")
    print(f"  Status: {'SUFFICIENT (n>=80)' if n >= 80 else 'BELOW THRESHOLD (n<80)'}")
    print()

    # Sample of uncertain markets
    if uncertain_markets:
        print("Sample uncertain markets (first 10):")
        for m in uncertain_markets[:10]:
            print(f"  {m['ticker']:<50} mid={m.get('mid','?'):.3f}  close={m['close_dt'][:10]}  days={m.get('days_to_close','?')}")


if __name__ == "__main__":
    main()
