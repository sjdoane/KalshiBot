"""
V10-A Revival Probe: Count unique release events per Economics series.

For each series in the Kim et al. mapping, paginate ALL settled markets,
extract close_time dates, and count unique release dates (each date = one
release event regardless of how many strike contracts existed).

Also verifies trade data accessibility via /markets/trades?ticker=...
(the correct query-param endpoint, NOT /markets/{ticker}/trades which 404s).

READ-ONLY. No portfolio endpoints.
"""

import base64
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# --- Auth config (same as probe_settled_sample.py pattern) ---
KEY_ID = "83df1ad0-b442-4740-9bf6-f02f2102d807"
PEM_PATH = r"C:\Users\SamJD\AppData\Local\KalshiBot\kalshi_prod_write.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
API_PREFIX = "/trade-api/v2"


def load_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_request(private_key, key_id: str, method: str, path: str) -> dict:
    ts_ms = str(int(time.time() * 1000))
    msg = ts_ms + method.upper() + path
    sig = private_key.sign(msg.encode(), padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.b64encode(sig).decode()
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "KALSHI-ACCESS-SIGNATURE": sig_b64,
        "Content-Type": "application/json",
    }


def api_get(client: httpx.Client, private_key, endpoint: str, params: dict | None = None, retries: int = 5) -> tuple:
    path = API_PREFIX + endpoint
    url = BASE_URL + endpoint
    for attempt in range(retries):
        headers = sign_request(private_key, KEY_ID, "GET", path)
        try:
            r = client.get(url, headers=headers, params=params, timeout=30.0)
        except Exception as e:
            print(f"    Network error attempt {attempt+1}: {e}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429:
            wait = 2 ** attempt * 3
            print(f"    429 rate limit, retrying in {wait:.0f}s ...")
            time.sleep(wait)
            continue
        return r
    return None


def paginate_settled_markets(client: httpx.Client, private_key, series_ticker: str) -> list[dict]:
    """Paginate ALL settled markets for a series. Returns list of market dicts."""
    all_markets = []
    cursor = None
    page = 0

    while True:
        page += 1
        params = {
            "series_ticker": series_ticker,
            "status": "settled",
            "limit": 1000,
        }
        if cursor:
            params["cursor"] = cursor

        r = api_get(client, private_key, "/markets", params=params)
        if r is None or r.status_code != 200:
            sc = r.status_code if r is not None else "None"
            print(f"    ERROR page {page}: HTTP {sc}")
            break

        data = r.json()
        markets = data.get("markets", []) or []
        all_markets.extend(markets)

        cursor = data.get("cursor")
        if not cursor or not markets:
            break

        # Courteous rate-limit pause
        time.sleep(0.3)

    return all_markets


def parse_close_date(close_time) -> str | None:
    """Extract YYYY-MM-DD from close_time (ISO string or epoch int)."""
    if close_time is None:
        return None
    if isinstance(close_time, str):
        try:
            dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None
    # Numeric epoch (seconds or ms)
    try:
        ts = int(close_time)
        # Detect milliseconds vs seconds
        if ts > 1e12:
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def analyze_series(client: httpx.Client, private_key, series_ticker: str) -> dict:
    """Paginate settled markets for series, compute event count stats."""
    print(f"\n  Fetching {series_ticker} settled markets ...")
    markets = paginate_settled_markets(client, private_key, series_ticker)

    if not markets:
        print(f"    -> 0 settled markets found")
        return {
            "series": series_ticker,
            "n_settled": 0,
            "n_unique_events": 0,
            "oldest_date": None,
            "newest_date": None,
            "sample_tickers": [],
        }

    # Collect close dates
    dates = []
    for m in markets:
        d = parse_close_date(m.get("close_time"))
        if d:
            dates.append(d)

    unique_dates = sorted(set(dates))
    n_unique = len(unique_dates)
    oldest = unique_dates[0] if unique_dates else None
    newest = unique_dates[-1] if unique_dates else None

    # Sample tickers for trade verification step
    sample_tickers = [m.get("ticker", "") for m in markets[:5] if m.get("ticker")]

    print(f"    -> {len(markets)} settled markets, {n_unique} unique release dates")
    if oldest:
        print(f"    -> Oldest: {oldest}, Newest: {newest}")

    return {
        "series": series_ticker,
        "n_settled": len(markets),
        "n_unique_events": n_unique,
        "oldest_date": oldest,
        "newest_date": newest,
        "sample_tickers": sample_tickers,
        "unique_dates": unique_dates,
    }


def verify_trades(client: httpx.Client, private_key, ticker: str) -> dict:
    """Verify trade data is accessible via /markets/trades?ticker= (query param form)."""
    r = api_get(client, private_key, "/markets/trades", params={"ticker": ticker, "limit": 100})
    if r is None:
        return {"ok": False, "n_trades": 0, "error": "network error"}
    if r.status_code != 200:
        return {"ok": False, "n_trades": 0, "error": f"HTTP {r.status_code}: {r.text[:200]}"}

    trades = r.json().get("trades", []) or []
    return {"ok": True, "n_trades": len(trades), "error": None}


def main():
    print("=" * 70)
    print("V10-A Revival Probe: Economics Series Release Event Count")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)

    # Series to probe (Kim mapping + alternates)
    # Grouped by Kim target:
    #   Kim KXCPI     -> KXCPI
    #   Kim KXFEDFUNDS -> KXFEDDECISION (pref) or KXEFFR
    #   Kim KXNFP     -> KXUSNFP (pref) or KXPAYROLLS
    #   Kim KXUNRATE  -> KXECONSTATU3 (pref) or KXU3
    SERIES_TO_PROBE = [
        "KXCPI",
        "KXFEDDECISION",
        "KXEFFR",
        "KXUSNFP",
        "KXPAYROLLS",
        "KXECONSTATU3",
        "KXU3",
    ]

    results = {}

    with httpx.Client(timeout=30.0) as client:
        for series in SERIES_TO_PROBE:
            result = analyze_series(client, private_key, series)
            results[series] = result
            time.sleep(1.0)  # rate-limit courtesy between series

        # --- Kim mapping: pick best-equivalent per Kim ticker ---
        # Prefer higher event count between alternates
        kim_cpi_result = results.get("KXCPI", {})
        kim_fed_result = max(
            results.get("KXFEDDECISION", {}),
            results.get("KXEFFR", {}),
            key=lambda x: x.get("n_unique_events", 0) if x else 0,
        )
        kim_nfp_result = max(
            results.get("KXUSNFP", {}),
            results.get("KXPAYROLLS", {}),
            key=lambda x: x.get("n_unique_events", 0) if x else 0,
        )
        kim_unrate_result = max(
            results.get("KXECONSTATU3", {}),
            results.get("KXU3", {}),
            key=lambda x: x.get("n_unique_events", 0) if x else 0,
        )

        kim_mapping = {
            "KXCPI (Kim KXCPI)": kim_cpi_result,
            "KXFEDDECISION/KXEFFR (Kim KXFEDFUNDS)": kim_fed_result,
            "KXUSNFP/KXPAYROLLS (Kim KXNFP)": kim_nfp_result,
            "KXECONSTATU3/KXU3 (Kim KXUNRATE)": kim_unrate_result,
        }

        total_unique_events = sum(
            v.get("n_unique_events", 0) for v in kim_mapping.values() if v
        )

        # --- Trade verification on best series ---
        # Find series with most events
        best_series_result = max(
            results.values(),
            key=lambda x: x.get("n_unique_events", 0) if x else 0,
        )
        best_series = best_series_result.get("series", "")
        trade_verify = {"ok": False, "n_trades": 0, "error": "no series"}

        if best_series and best_series_result.get("sample_tickers"):
            # Pick a ticker from the middle of the sample (likely ATM)
            tickers = best_series_result["sample_tickers"]
            test_ticker = tickers[len(tickers) // 2]
            print(f"\n  Verifying trade data: {best_series} -> {test_ticker}")
            trade_verify = verify_trades(client, private_key, test_ticker)
            print(f"    Trade verify: ok={trade_verify['ok']} n_trades={trade_verify['n_trades']}")
            if trade_verify.get("error"):
                print(f"    Error: {trade_verify['error']}")

    # --- Print summary table ---
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"\nAll probed series:")
    print(f"{'Series':<22} {'n_settled':>10} {'n_events':>10} {'oldest':>12} {'newest':>12}")
    print("-" * 70)
    for s in SERIES_TO_PROBE:
        r = results.get(s, {})
        print(
            f"{s:<22} {r.get('n_settled', 0):>10} {r.get('n_unique_events', 0):>10} "
            f"{r.get('oldest_date', 'N/A'):>12} {r.get('newest_date', 'N/A'):>12}"
        )

    print(f"\nKim mapping (4 series, best-equivalent chosen):")
    print(f"{'Kim target':<42} {'n_events':>10} {'oldest':>12}")
    print("-" * 70)
    for label, r in kim_mapping.items():
        if r:
            print(
                f"{label:<42} {r.get('n_unique_events', 0):>10} "
                f"{r.get('oldest_date', 'N/A'):>12}"
            )
        else:
            print(f"{label:<42} {'0':>10} {'N/A':>12}")

    print("-" * 70)
    print(f"TOTAL unique release events (4 Kim series): {total_unique_events}")
    print()

    # --- Verdict ---
    if total_unique_events >= 60:
        verdict = "PASS"
        verdict_note = "V10-A REVIVES. Sufficient sample for Granger analysis."
    elif total_unique_events >= 40:
        verdict = "MARGINAL"
        verdict_note = "V10-A MARGINAL. Conditional revive recommended."
    else:
        verdict = "FAIL"
        verdict_note = "V10-A CONFIRM-KILL on sample size."

    print(f"VERDICT: {verdict}")
    print(f"NOTE: {verdict_note}")
    print()
    print(f"Trade verification ({best_series}): ok={trade_verify['ok']} n_trades={trade_verify['n_trades']}")

    # Return structured data for report writing
    return {
        "results": results,
        "kim_mapping": {k: {"series": v.get("series"), "n_unique_events": v.get("n_unique_events", 0), "oldest_date": v.get("oldest_date")} for k, v in kim_mapping.items()},
        "total_unique_events": total_unique_events,
        "verdict": verdict,
        "verdict_note": verdict_note,
        "best_series": best_series,
        "trade_verify": trade_verify,
    }


if __name__ == "__main__":
    data = main()
    sys.exit(0)
