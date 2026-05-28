"""
v9 Agent A1: data layer + universe probe script.
Probes Kalshi API for sports market inventory, orderbook endpoints,
and computes OOS window statistics.
READ-ONLY: never touches /portfolio/orders.
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx

# ---------------------------------------------------------------------------
# Inline auth (mirrors src/kalshi_bot/data/auth.py) to avoid import issues
# ---------------------------------------------------------------------------
import base64
import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KEY_ID = "83df1ad0-b442-4740-9bf6-f02f2102d807"
PEM_PATH = r"C:\Users\SamJD\AppData\Local\KalshiBot\kalshi_prod_write.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

def load_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def sign_request(private_key, key_id, method, path):
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

def api_get(client, private_key, endpoint, params=None):
    path = "/trade-api/v2" + endpoint
    headers = sign_request(private_key, KEY_ID, "GET", path)
    t0 = time.time()
    r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=20.0)
    latency_ms = int((time.time() - t0) * 1000)
    return r, latency_ms

# Denylist per market_scanner.py
DENYLIST = {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"}

# v1 filter criteria
MIN_LIFETIME_DAYS = 0  # we want all resolved sports, filter later
MID_BAND = [(0.20, 0.45), (0.55, 0.80)]
V1_PRICE_BAND = (0.70, 0.95)  # v1 strategy-specific band

def is_v1_eligible(mid):
    return V1_PRICE_BAND[0] <= mid <= V1_PRICE_BAND[1]

def main():
    print("=" * 70)
    print("v9 Agent A1: Kalshi Universe Probe")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=20.0) as client:

        # ------------------------------------------------------------------
        # PROBE 1: Exchange status (connectivity check)
        # ------------------------------------------------------------------
        print("\n[PROBE 1] Exchange status...")
        r, lat = api_get(client, private_key, "/exchange/status")
        print(f"  Status: {r.status_code}, latency: {lat}ms")
        if r.status_code == 200:
            data = r.json()
            print(f"  exchange_active: {data.get('exchange_active')}")
            print(f"  trading_active: {data.get('trading_active')}")

        # ------------------------------------------------------------------
        # PROBE 2: Discover sports series
        # ------------------------------------------------------------------
        print("\n[PROBE 2] Sports series discovery...")
        all_series = []
        cursor = None
        page = 0
        while True:
            params = {"limit": 200, "category": "Sports"}
            if cursor:
                params["cursor"] = cursor
            r, lat = api_get(client, private_key, "/series", params)
            if r.status_code != 200:
                print(f"  ERROR: {r.status_code} {r.text[:200]}")
                break
            data = r.json()
            series_batch = data.get("series", [])
            all_series.extend(series_batch)
            cursor = data.get("cursor")
            page += 1
            print(f"  Page {page}: {len(series_batch)} series (total: {len(all_series)})")
            if not cursor or not series_batch:
                break
            if page >= 20:
                break
            time.sleep(0.2)

        print(f"\n  Total sports series found: {len(all_series)}")
        series_tickers = []
        for s in all_series:
            t = s.get("ticker") or s.get("series_ticker", "")
            if t:
                series_tickers.append(t)

        # Print first 30 series tickers
        print("  First 30 series tickers:")
        for t in series_tickers[:30]:
            print(f"    {t}")

        # Post-denylist series
        residual_series = [t for t in series_tickers if t not in DENYLIST]
        print(f"\n  Post-denylist residual series: {len(residual_series)}")
        results["total_series"] = len(series_tickers)
        results["residual_series"] = len(residual_series)
        results["series_tickers"] = series_tickers

        # ------------------------------------------------------------------
        # PROBE 3: Open markets in residual sports series
        # ------------------------------------------------------------------
        print("\n[PROBE 3] Open markets scan (residual series)...")
        now_utc = datetime.now(timezone.utc)
        open_markets = []

        # Scan up to 50 series to stay within time budget
        scan_series = residual_series[:50]
        for i, series_t in enumerate(scan_series):
            params = {"limit": 100, "status": "open", "series_ticker": series_t}
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  WARN [{series_t}]: {r.status_code}")
                time.sleep(0.5)
                continue
            data = r.json()
            markets = data.get("markets", [])
            for m in markets:
                m["_series"] = series_t
            open_markets.extend(markets)
            time.sleep(0.1)

        print(f"\n  Total open markets found (across {len(scan_series)} series): {len(open_markets)}")

        # ------------------------------------------------------------------
        # PROBE 4: Closed markets 2026-02-01 to 2026-05-26 (OOS window)
        # ------------------------------------------------------------------
        print("\n[PROBE 4] Closed markets - OOS window 2026-02-01 to 2026-05-26...")
        oos_start = "2026-02-01T00:00:00Z"
        oos_end   = "2026-05-26T23:59:59Z"
        closed_markets = []
        cursor = None
        page = 0
        while True:
            params = {
                "limit": 1000,
                "status": "closed",
                "close_time_min": oos_start,
                "close_time_max": oos_end,
                "category": "Sports"
            }
            if cursor:
                params["cursor"] = cursor
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  ERROR closed markets: {r.status_code} {r.text[:300]}")
                break
            data = r.json()
            batch = data.get("markets", [])
            closed_markets.extend(batch)
            cursor = data.get("cursor")
            page += 1
            print(f"  Page {page}: {len(batch)} markets (total: {len(closed_markets)}), lat: {lat}ms")
            if not cursor or not batch:
                break
            if page >= 20:
                print("  (hit page cap at 20)")
                break
            time.sleep(0.3)

        print(f"\n  Total closed sports markets in OOS window: {len(closed_markets)}")

        # Classify by series prefix
        from collections import defaultdict
        series_counts = defaultdict(int)
        series_v1_eligible = defaultdict(int)
        for m in closed_markets:
            st = m.get("series_ticker", "")
            if not st:
                ticker = m.get("ticker", "")
                st = ticker.split("-")[0] if ticker else "UNKNOWN"
            if st in DENYLIST:
                continue
            series_counts[st] += 1
            # Check if v1-eligible (price band)
            yes_bid = m.get("yes_bid_dollars") or 0
            yes_ask = m.get("yes_ask_dollars") or 0
            last_p = m.get("last_price_dollars") or 0
            if yes_bid and yes_ask:
                mid = (float(yes_bid) + float(yes_ask)) / 2.0
            elif last_p:
                mid = float(last_p)
            else:
                mid = 0
            if is_v1_eligible(mid):
                series_v1_eligible[st] += 1

        print("\n  Closed OOS markets by series (post-denylist):")
        total_oos = sum(series_counts.values())
        total_v1_elig = sum(series_v1_eligible.values())
        for s, n in sorted(series_counts.items(), key=lambda x: -x[1])[:30]:
            v1e = series_v1_eligible.get(s, 0)
            print(f"    {s:30s}  n={n:4d}  v1-eligible={v1e}")
        print(f"\n  TOTAL (post-denylist, closed OOS): n={total_oos}, v1-eligible={total_v1_elig}")
        results["closed_oos_total"] = total_oos
        results["closed_oos_v1_eligible"] = total_v1_elig
        results["series_counts"] = dict(series_counts)

        # ------------------------------------------------------------------
        # PROBE 5: Upcoming closing markets (v9 prospective window)
        # ------------------------------------------------------------------
        print("\n[PROBE 5] Currently open markets closing 2026-05-27 to 2026-06-30...")
        prospective_end = "2026-06-30T23:59:59Z"
        prospective_start_str = "2026-05-27T00:00:00Z"
        prospective_markets = []
        cursor = None
        page = 0
        while True:
            params = {
                "limit": 1000,
                "status": "open",
                "min_close_ts": int(datetime(2026, 5, 27, tzinfo=timezone.utc).timestamp()),
                "max_close_ts": int(datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp()),
            }
            if cursor:
                params["cursor"] = cursor
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  ERROR prospective: {r.status_code} {r.text[:300]}")
                break
            data = r.json()
            batch = data.get("markets", [])
            prospective_markets.extend(batch)
            cursor = data.get("cursor")
            page += 1
            print(f"  Page {page}: {len(batch)} markets (total: {len(prospective_markets)}), lat: {lat}ms")
            if not cursor or not batch:
                break
            if page >= 20:
                print("  (hit page cap)")
                break
            time.sleep(0.3)

        # Filter to sports + post-denylist
        sports_prospective = []
        for m in prospective_markets:
            cat = m.get("category", "").lower()
            event_cat = m.get("event_category", "").lower()
            series_t = m.get("series_ticker", "")
            ticker = m.get("ticker", "")
            prefix = series_t if series_t else (ticker.split("-")[0] if ticker else "")
            # keep only if series is in sports series list or if category is Sports
            if prefix in DENYLIST:
                continue
            if prefix in series_tickers or "sport" in cat or "sport" in event_cat:
                sports_prospective.append(m)

        print(f"\n  Sports markets open, closing 2026-05-27 to 2026-06-30 (post-denylist): {len(sports_prospective)}")

        # v1-eligible prospective
        v1_prospective = []
        for m in sports_prospective:
            yes_bid = float(m.get("yes_bid_dollars") or 0)
            yes_ask = float(m.get("yes_ask_dollars") or 0)
            if yes_bid and yes_ask:
                mid = (yes_bid + yes_ask) / 2.0
                if is_v1_eligible(mid):
                    v1_prospective.append(m)

        print(f"  v1-eligible (price band 0.70-0.95): {len(v1_prospective)}")

        # Sample a few
        print("\n  Sample prospective v1-eligible markets:")
        for m in v1_prospective[:10]:
            yes_bid = float(m.get("yes_bid_dollars") or 0)
            yes_ask = float(m.get("yes_ask_dollars") or 0)
            mid = (yes_bid + yes_ask) / 2.0 if yes_bid and yes_ask else 0
            close_time = m.get("close_time", "")
            print(f"    {m.get('ticker','')[:45]:45s}  mid={mid:.3f}  close={close_time[:10]}")

        results["prospective_sports_total"] = len(sports_prospective)
        results["prospective_v1_eligible"] = len(v1_prospective)

        # ------------------------------------------------------------------
        # PROBE 6: Orderbook endpoint test (v7-B phantom prevention)
        # ------------------------------------------------------------------
        print("\n[PROBE 6] Orderbook endpoint test (v7-B phantom prevention)...")

        # Find a currently-open sports market with a bid
        test_ticker = None
        for m in open_markets[:200]:
            yes_bid = float(m.get("yes_bid_dollars") or 0)
            yes_ask = float(m.get("yes_ask_dollars") or 0)
            if yes_bid > 0 and yes_ask > 0:
                test_ticker = m.get("ticker")
                break

        if not test_ticker:
            # try first prospective
            for m in sports_prospective[:50]:
                yes_bid = float(m.get("yes_bid_dollars") or 0)
                yes_ask = float(m.get("yes_ask_dollars") or 0)
                if yes_bid > 0 and yes_ask > 0:
                    test_ticker = m.get("ticker")
                    break

        if test_ticker:
            print(f"  Test ticker: {test_ticker}")

            # 6a: Current market snapshot
            r, lat = api_get(client, private_key, f"/markets/{test_ticker}")
            print(f"\n  /markets/{{ticker}} snapshot: HTTP {r.status_code}, {lat}ms")
            if r.status_code == 200:
                mkt = r.json().get("market", {})
                yes_bid = mkt.get("yes_bid_dollars")
                yes_ask = mkt.get("yes_ask_dollars")
                last_p = mkt.get("last_price_dollars")
                no_bid = mkt.get("no_bid_dollars")
                print(f"    yes_bid={yes_bid}, yes_ask={yes_ask}, last_price={last_p}, no_bid={no_bid}")
                if yes_bid and yes_ask:
                    live_mid = (float(yes_bid) + float(yes_ask)) / 2.0
                elif no_bid:
                    yes_ask_derived = round(1.0 - float(no_bid), 4)
                    live_mid = (float(yes_bid or 0) + yes_ask_derived) / 2.0
                    print(f"    yes_ask derived from parity (1-no_bid): {yes_ask_derived}")
                print(f"    LIVE ORDERBOOK MID = {live_mid:.4f}")
                print(f"    Sample payload keys: {list(mkt.keys())[:15]}")

            # 6b: Orderbook endpoint
            r, lat = api_get(client, private_key, f"/markets/{test_ticker}/orderbook")
            print(f"\n  /markets/{{ticker}}/orderbook: HTTP {r.status_code}, {lat}ms")
            if r.status_code == 200:
                ob = r.json().get("orderbook", r.json())
                print(f"    Keys: {list(ob.keys() if isinstance(ob, dict) else {})}")
                print(f"    Sample: {str(ob)[:400]}")
            else:
                print(f"    Response: {r.text[:300]}")

            # 6c: Historical orderbook with ts param
            r, lat = api_get(client, private_key, f"/markets/{test_ticker}/orderbook",
                             params={"ts": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())})
            print(f"\n  /markets/{{ticker}}/orderbook?ts=...: HTTP {r.status_code}, {lat}ms")
            if r.status_code != 200:
                print(f"    Response: {r.text[:300]}")
            else:
                print(f"    UNEXPECTED 200 - historical orderbook MAY be available!")
                print(f"    Sample: {str(r.json())[:400]}")

            # 6d: Trades endpoint (for reference, NOT baseline)
            r, lat = api_get(client, private_key, "/markets/trades",
                             params={"ticker": test_ticker, "limit": 3})
            print(f"\n  /markets/trades?ticker=...: HTTP {r.status_code}, {lat}ms")
            if r.status_code == 200:
                trades = r.json().get("trades", [])
                print(f"    n_trades returned: {len(trades)}")
                if trades:
                    t0 = trades[0]
                    print(f"    Sample trade: yes_price={t0.get('yes_price_dollars')}, created={t0.get('created_time')[:20] if t0.get('created_time') else 'N/A'}")
                    print(f"    NOTE: This is a TRADE PRINT, NOT orderbook mid. Do not use as v9 baseline.")
        else:
            print("  WARNING: no suitable test ticker found for orderbook probe.")

        results["test_ticker"] = test_ticker

        # ------------------------------------------------------------------
        # PROBE 7: Historical closed market - check if orderbook data exists
        # ------------------------------------------------------------------
        print("\n[PROBE 7] Historical closed market orderbook feasibility...")
        # Pick a recently resolved market from closed OOS
        closed_test = None
        for m in closed_markets[:200]:
            st = m.get("series_ticker", "")
            if st not in DENYLIST:
                yes_bid = m.get("yes_bid_dollars") or 0
                if float(yes_bid) > 0:
                    closed_test = m.get("ticker")
                    break

        if not closed_test:
            # Just pick any
            if closed_markets:
                closed_test = closed_markets[0].get("ticker")

        if closed_test:
            print(f"  Testing closed ticker: {closed_test}")
            r, lat = api_get(client, private_key, f"/markets/{closed_test}/orderbook")
            print(f"  /markets/{{closed_ticker}}/orderbook: HTTP {r.status_code}, {lat}ms")
            if r.status_code == 200:
                print(f"  UNEXPECTED 200 for closed market! Sample: {str(r.json())[:400]}")
            else:
                print(f"  Response: {r.text[:300]}")
                print(f"  CONFIRMED: orderbook endpoint does NOT serve historical data for closed markets.")

            # Check the closed market snapshot
            r, lat = api_get(client, private_key, f"/markets/{closed_test}")
            print(f"\n  /markets/{{closed_ticker}}: HTTP {r.status_code}, {lat}ms")
            if r.status_code == 200:
                mkt = r.json().get("market", {})
                print(f"    status={mkt.get('status')}")
                print(f"    yes_bid={mkt.get('yes_bid_dollars')}, yes_ask={mkt.get('yes_ask_dollars')}")
                print(f"    last_price={mkt.get('last_price_dollars')}")
                print(f"    result={mkt.get('result')}")
                print(f"    NOTE: post-settlement bid/ask fields are unreliable (v5-B Killer 2c).")

        # ------------------------------------------------------------------
        # PROBE 8: the-odds-api reachability (key in .env)
        # ------------------------------------------------------------------
        print("\n[PROBE 8] the-odds-api probe...")
        ODDS_KEY = "3579114de6d301100083d64cb934927a"
        t0 = time.time()
        r2 = client.get(
            "https://api.the-odds-api.com/v4/sports",
            params={"apiKey": ODDS_KEY},
            timeout=15.0
        )
        lat2 = int((time.time() - t0) * 1000)
        print(f"  /v4/sports: HTTP {r2.status_code}, {lat2}ms")
        if r2.status_code == 200:
            sports = r2.json()
            print(f"  Sports count: {len(sports)}")
            keys_of_interest = ["americanfootball_nfl", "baseball_mlb", "basketball_nba",
                                "americanfootball_ncaaf", "basketball_ncaab", "soccer_usa_mls", "mma_mixed_martial_arts"]
            print("  Sports of interest (v9 scope):")
            found = {s["key"]: s for s in sports if isinstance(s, dict)}
            for k in keys_of_interest:
                if k in found:
                    s = found[k]
                    print(f"    {k}: has_outrights={s.get('has_outrights')}, active={s.get('active')}")
                else:
                    print(f"    {k}: NOT FOUND")
            # remaining credits
            remaining = r2.headers.get("x-requests-remaining", "N/A")
            used = r2.headers.get("x-requests-used", "N/A")
            print(f"  Credits remaining: {remaining}, used: {used}")
        else:
            print(f"  Response: {r2.text[:300]}")

        # ------------------------------------------------------------------
        # PROBE 9: ESPN site.api
        # ------------------------------------------------------------------
        print("\n[PROBE 9] ESPN site.api probe...")
        espn_endpoints = [
            ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard", "MLB scoreboard"),
            ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", "NFL scoreboard"),
            ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", "NBA scoreboard"),
            ("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard", "NCAAB scoreboard"),
            ("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard", "NCAAF scoreboard"),
            ("https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard", "MLS scoreboard"),
        ]
        for url, label in espn_endpoints:
            t0 = time.time()
            r3 = client.get(url, timeout=10.0)
            lat3 = int((time.time() - t0) * 1000)
            print(f"  {label}: HTTP {r3.status_code}, {lat3}ms")
            if r3.status_code != 200:
                print(f"    {r3.text[:100]}")
            time.sleep(0.2)

        # ------------------------------------------------------------------
        # PROBE 10: GDELT retry
        # ------------------------------------------------------------------
        print("\n[PROBE 10] GDELT retry probe...")
        try:
            t0 = time.time()
            r4 = client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": "NBA basketball", "mode": "artlist", "maxrecords": "1", "format": "json"},
                timeout=12.0
            )
            lat4 = int((time.time() - t0) * 1000)
            print(f"  GDELT doc API: HTTP {r4.status_code}, {lat4}ms")
            if r4.status_code == 200:
                print(f"  GDELT RESPONSIVE! Sample: {r4.text[:200]}")
            else:
                print(f"  GDELT response: {r4.text[:200]}")
        except Exception as e:
            print(f"  GDELT TIMEOUT/ERROR: {e}")

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
