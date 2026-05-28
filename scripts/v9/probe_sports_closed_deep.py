"""
v9 Agent A1: Deep sports closed market probe.
The generic /markets?status=closed query returned 20k markets dominated
by esports and financial contracts. We need a series-specific pull
without the series_ticker filter failing silently.

Key insight from probe: KXNBAWINS, KXMLBWINS etc returned 0 closed
in OOS window. This suggests:
1. These markets closed BEFORE 2026-02-01 (NBA/MLB season ended Oct-Nov 2025)
2. OR the series_ticker parameter is case/prefix sensitive

Let me try: pulling the series list for those tickers to find
the correct close_time range.
"""
import json, sys, time, base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import httpx

KEY_ID = "83df1ad0-b442-4740-9bf6-f02f2102d807"
PEM_PATH = r"C:\Users\SamJD\AppData\Local\KalshiBot\kalshi_prod_write.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DENYLIST = {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"}

def load_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def sign_request(private_key, key_id, method, path):
    ts_ms = str(int(time.time() * 1000))
    msg = ts_ms + method.upper() + path
    sig = private_key.sign(msg.encode(), padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.b64encode(sig).decode()
    return {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts_ms, "KALSHI-ACCESS-SIGNATURE": sig_b64}

def api_get(client, private_key, endpoint, params=None):
    path = "/trade-api/v2" + endpoint
    headers = sign_request(private_key, KEY_ID, "GET", path)
    for attempt in range(3):
        t0 = time.time()
        r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=20.0)
        lat = int((time.time() - t0) * 1000)
        if r.status_code == 429:
            print(f"  [429] backing off...")
            time.sleep(5)
            continue
        return r, lat
    return r, lat

def main():
    private_key = load_key(PEM_PATH)

    # Target sports series: pull ALL closed markets (no date filter) to see range
    test_series = [
        "KXNBAWINS", "KXMLBWINS-NYY", "KXMLBWINS-LAD", "KXNCAAFPLAYOFF",
        "KXNFLGAME", "KXUCLROUND", "KXNHLWINS", "KXMLBPLAYOFFS"
    ]

    with httpx.Client(timeout=20.0) as client:
        print("=" * 70)
        print("PROBE A: Closed markets for W2 series - ANY date range")
        print("=" * 70)
        for series in test_series:
            params = {"limit": 5, "status": "closed", "series_ticker": series}
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  {series}: HTTP {r.status_code}")
                continue
            data = r.json()
            markets = data.get("markets", [])
            if not markets:
                print(f"  {series}: 0 closed markets (series may be empty or inactive)")
            else:
                close_times = sorted([m.get("close_time","")[:10] for m in markets])
                print(f"  {series}: {len(markets)} markets (sample close dates: {close_times})")
            time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE B: Open markets for key W2 sports series")
        print("=" * 70)
        for series in test_series:
            params = {"limit": 10, "status": "open", "series_ticker": series}
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  {series}: HTTP {r.status_code}")
                continue
            data = r.json()
            markets = data.get("markets", [])
            if not markets:
                print(f"  {series}: 0 open markets")
            else:
                close_times = sorted([m.get("close_time","")[:10] for m in markets])
                yes_bids = [float(m.get("yes_bid_dollars") or 0) for m in markets if m.get("yes_bid_dollars")]
                yes_asks = [float(m.get("yes_ask_dollars") or 0) for m in markets if m.get("yes_ask_dollars")]
                mids = [(b + a)/2 for b, a in zip(yes_bids, yes_asks)]
                print(f"  {series}: {len(markets)} open markets, close dates: {close_times[:3]}, mids: {[round(m,3) for m in mids[:5]]}")
            time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE C: Check KXNBAWINS series metadata")
        print("=" * 70)
        r, lat = api_get(client, private_key, "/series/KXNBAWINS")
        print(f"  /series/KXNBAWINS: HTTP {r.status_code}, {lat}ms")
        if r.status_code == 200:
            s = r.json()
            print(f"  Sample: {json.dumps(s)[:500]}")
        time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE D: All closed markets any date (no date filter) for NBA")
        print("=" * 70)
        params = {"limit": 10, "status": "closed", "series_ticker": "KXNBAWINS"}
        r, lat = api_get(client, private_key, "/markets", params)
        print(f"  /markets?status=closed&series_ticker=KXNBAWINS: HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            markets = data.get("markets", [])
            print(f"  Count: {len(markets)}")
            for m in markets[:3]:
                print(f"    {m.get('ticker','')[:50]}: close={m.get('close_time','')[:10]}, status={m.get('status')}")

        print("\n" + "=" * 70)
        print("PROBE E: Settlement markets - status=settled for KXNBAWINS")
        print("=" * 70)
        for st in ["settled", "resolved", "finalized"]:
            params = {"limit": 5, "status": st, "series_ticker": "KXNBAWINS"}
            r, lat = api_get(client, private_key, "/markets", params)
            print(f"  status={st}: HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                markets = data.get("markets", [])
                print(f"    Count: {len(markets)}")
            time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE F: Recent settled basketball market - get orderbook snapshot")
        print("=" * 70)
        # Try to find any settled NBA market from our v3 data
        # W2 shows KXNBAWINS-BOS at specific ticker format
        test_tickers = [
            "KXNBAWINS-BOS-26-T50",  # guessed format
            "KXNBAWINS-MIA-26-T50",
        ]
        for ticker in test_tickers:
            r, lat = api_get(client, private_key, f"/markets/{ticker}")
            print(f"  /markets/{ticker}: HTTP {r.status_code}")
            if r.status_code == 200:
                mkt = r.json().get("market", {})
                print(f"    status={mkt.get('status')}, close_time={mkt.get('close_time','')[:10]}")
            time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE G: The-odds-api historical endpoint check")
        print("=" * 70)
        ODDS_KEY = "3579114de6d301100083d64cb934927a"
        # Check credit usage and historical endpoint
        r2 = client.get(
            "https://api.the-odds-api.com/v4/sports",
            params={"apiKey": ODDS_KEY}, timeout=10.0
        )
        print(f"  /v4/sports: HTTP {r2.status_code}")
        remaining = r2.headers.get("x-requests-remaining", "N/A")
        used = r2.headers.get("x-requests-used", "N/A")
        print(f"  Credits remaining: {remaining}, used: {used}")

        # Check what historical endpoint looks like
        r3 = client.get(
            "https://api.the-odds-api.com/v4/historical/sports",
            params={"apiKey": ODDS_KEY}, timeout=10.0
        )
        print(f"  /v4/historical/sports: HTTP {r3.status_code}")
        if r3.status_code == 200:
            sports = r3.json()
            print(f"  Historical sports count: {len(sports) if isinstance(sports, list) else 'N/A'}")
        else:
            print(f"  Response: {r3.text[:200]}")
        remaining = r3.headers.get("x-requests-remaining", "N/A")
        print(f"  Credits remaining after: {remaining}")

        # Check free-tier status - can we get historical odds?
        r4 = client.get(
            "https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl/odds",
            params={"apiKey": ODDS_KEY, "date": "2026-01-15T00:00:00Z", "regions": "us", "markets": "h2h"},
            timeout=15.0
        )
        print(f"  /v4/historical/.../odds?date=2026-01-15: HTTP {r4.status_code}")
        if r4.status_code == 200:
            data4 = r4.json()
            odds_data = data4.get("data", data4)
            print(f"  Historical odds available! n_events: {len(odds_data) if isinstance(odds_data, list) else 'N/A'}")
            if isinstance(odds_data, list) and odds_data:
                print(f"  Sample event: {odds_data[0].get('sport_key','N/A')}, {odds_data[0].get('commence_time','N/A')[:10]}")
        else:
            print(f"  Response: {r4.text[:300]}")
        remaining = r4.headers.get("x-requests-remaining", "N/A")
        used = r4.headers.get("x-requests-used", "N/A")
        print(f"  Credits remaining: {remaining}, used: {used}")

if __name__ == "__main__":
    main()
