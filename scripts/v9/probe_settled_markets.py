"""
v9 Agent A1: settled markets probe.
Key finding: KXNBAWINS returns 5 "settled" (not "closed") markets.
Also investigating: prospective v1-eligible market details,
and the-odds-api signup tier.
"""
import json, time, base64, os
from datetime import datetime, timezone
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
            time.sleep(5)
            continue
        return r, lat
    return r, lat

V1_BAND = (0.70, 0.95)
OPUS_CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)  # conservative cutoff for foreknowledge

def get_mid(m):
    yes_bid = float(m.get("yes_bid_dollars") or 0)
    yes_ask = float(m.get("yes_ask_dollars") or 0)
    no_bid = float(m.get("no_bid_dollars") or 0)
    if yes_bid > 0 and yes_ask > 0:
        return (yes_bid + yes_ask) / 2.0
    if yes_bid > 0 and no_bid > 0:
        return (yes_bid + (1.0 - no_bid)) / 2.0
    return float(m.get("last_price_dollars") or 0)

# Main sports series from W2 + AIA scope
SPORTS_SERIES = [
    "KXNBAWINS", "KXMLBWINS-NYY", "KXMLBWINS-LAD", "KXMLBWINS-BOS",
    "KXMLBWINS-ATL", "KXMLBWINS-HOU", "KXMLBWINS-CHC", "KXMLBWINS-MIN",
    "KXMLBWINS-PHI", "KXMLBWINS-SEA", "KXMLBWINS-SD", "KXMLBWINS-TB",
    "KXMLBWINS-KC", "KXMLBWINS-STL", "KXMLBWINS-MIL", "KXMLBWINS-WSH",
    "KXMLBWINS-SF", "KXMLBWINS-DET", "KXMLBWINS-CLE", "KXMLBWINS-CWS",
    "KXMLBWINS-LAA", "KXMLBWINS-CIN", "KXMLBWINS-BAL", "KXMLBWINS-TEX",
    "KXMLBWINS-NYM", "KXMLBWINS-AZ",
    "KXNCAAFPLAYOFF", "KXNFLGAME", "KXNHLWINS", "KXUCLROUND",
    "KXATPGRANDSLAM", "KXBOXING", "KXUFCFIGHT", "KXNBAPLAYOFF",
    "KXPGAUSO", "KXNHLPLAYOFF",
]

def main():
    private_key = load_key(PEM_PATH)
    settled_results = {}

    with httpx.Client(timeout=20.0) as client:
        print("=" * 70)
        print("PROBE 1: Settled markets per series (post-Opus-cutoff = 2026-01+)")
        print("=" * 70)

        for series in SPORTS_SERIES:
            if series in DENYLIST:
                continue
            # Try status=settled with close_time_min
            params = {
                "limit": 200, "status": "settled",
                "series_ticker": series,
                "close_time_min": "2026-01-15T00:00:00Z",
                "close_time_max": "2026-05-26T23:59:59Z",
            }
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                time.sleep(0.3)
                continue
            data = r.json()
            markets = data.get("markets", [])
            n_total = len(markets)
            n_v1 = 0
            mids = []
            close_ts = []
            for m in markets:
                mid = get_mid(m)
                mids.append(mid)
                close_ts.append(m.get("close_time", "")[:10])
                # Only count as v1-eligible if mid was in band AT SOME POINT
                # We use the stored mid (snapshot at time of data pull)
                if V1_BAND[0] <= mid <= V1_BAND[1]:
                    n_v1 += 1
            if n_total > 0:
                settled_results[series] = {
                    "n_total": n_total, "n_v1": n_v1,
                    "mean_mid": round(sum(mids)/len(mids),3) if mids else 0,
                    "close_dates": sorted(set(close_ts))[:5],
                }
                print(f"  {series:35s}  n={n_total:3d}  v1={n_v1:3d}  mean_mid={sum(mids)/len(mids):.3f}  close:{sorted(set(close_ts))[:2]}")
            time.sleep(0.2)

        # Also try with no date filter
        print("\n" + "=" * 70)
        print("PROBE 2: Settled markets - ANY date (to find historical range)")
        print("=" * 70)
        check_series = ["KXNBAWINS", "KXMLBWINS-NYY", "KXNCAAFPLAYOFF", "KXNFLGAME", "KXUFCFIGHT"]
        for series in check_series:
            params = {"limit": 10, "status": "settled", "series_ticker": series}
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                print(f"  {series}: {r.status_code}")
                time.sleep(0.3)
                continue
            data = r.json()
            markets = data.get("markets", [])
            if markets:
                close_ts = sorted([m.get("close_time","")[:10] for m in markets])
                results = [m.get("result","?") for m in markets[:3]]
                mids = [round(get_mid(m),3) for m in markets[:5]]
                print(f"  {series}: n={len(markets)} settled, dates: {close_ts[:3]}, results: {results[:3]}, mids: {mids}")
                # Show a full settled market for orderbook investigation
                if markets:
                    sample = markets[0]
                    ticker = sample.get("ticker","")
                    print(f"    Sample ticker: {ticker}")
                    print(f"    yes_bid={sample.get('yes_bid_dollars')}, yes_ask={sample.get('yes_ask_dollars')}, last={sample.get('last_price_dollars')}")
                    # Try orderbook
                    r2, lat2 = api_get(client, private_key, f"/markets/{ticker}/orderbook")
                    print(f"    Orderbook for settled market: HTTP {r2.status_code}")
                    if r2.status_code == 200:
                        ob = r2.json()
                        yes_side = ob.get("orderbook_fp", {}).get("yes_dollars", [])
                        no_side = ob.get("orderbook_fp", {}).get("no_dollars", [])
                        print(f"    yes_side levels: {len(yes_side)}, no_side levels: {len(no_side)}")
                        if yes_side:
                            print(f"    Best yes bid (settled): {yes_side[:2]}")
                        if no_side:
                            print(f"    Best no bid (settled): {no_side[:2]}")
            else:
                print(f"  {series}: 0 settled markets")
            time.sleep(0.3)

        print("\n" + "=" * 70)
        print("PROBE 3: Prospective v1-eligible markets - closing 2026-05-27 to 2026-06-30")
        print("(detailed breakdown)")
        print("=" * 70)
        # sports series from probe 4 - sample the prospective markets
        prospective_sports_series = [
            "KXNHLNORRIS", "KXNHLADAMS", "KXNHLHART", "KXNHLVEZINA",
            "KXWCGAME", "KXUFCFIGHT", "KXPGAUSO", "KXNBAPLAYOFF",
            "KXMLBWINS-NYY", "KXMLBWINS-LAD",
        ]
        total_prospective_v1 = 0
        prospective_detail = {}
        for series in prospective_sports_series:
            params = {
                "limit": 50, "status": "open",
                "series_ticker": series,
                "min_close_ts": int(datetime(2026, 5, 27, tzinfo=timezone.utc).timestamp()),
                "max_close_ts": int(datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp()),
            }
            r, lat = api_get(client, private_key, "/markets", params)
            if r.status_code != 200:
                time.sleep(0.3)
                continue
            data = r.json()
            markets = data.get("markets", [])
            n_v1 = sum(1 for m in markets if V1_BAND[0] <= get_mid(m) <= V1_BAND[1])
            total_prospective_v1 += n_v1
            if n_v1 > 0:
                prospective_detail[series] = {"n_total": len(markets), "n_v1": n_v1}
                v1_mkt = [m for m in markets if V1_BAND[0] <= get_mid(m) <= V1_BAND[1]]
                close_ts = [m.get("close_time","")[:10] for m in v1_mkt[:3]]
                mids = [round(get_mid(m),3) for m in v1_mkt[:3]]
                print(f"  {series}: n_open={len(markets)}, n_v1={n_v1}, close_dates: {close_ts}, mids: {mids}")
            time.sleep(0.2)
        print(f"\n  Total prospective v1-eligible in sample series: {total_prospective_v1}")

        print("\n" + "=" * 70)
        print("PROBE 4: SUMMARY of all settled sports markets in post-cutoff OOS window")
        print("=" * 70)
        total_n = sum(v["n_total"] for v in settled_results.values())
        total_v1 = sum(v["n_v1"] for v in settled_results.values())
        print(f"  Total settled sports markets (2026-01-15 to 2026-05-26): {total_n}")
        print(f"  v1-eligible (mid in [0.70, 0.95]): {total_v1}")
        print("\n  Per-series breakdown (non-zero only):")
        for s, v in sorted(settled_results.items(), key=lambda x: -x[1]["n_v1"]):
            print(f"    {s:35s}  n={v['n_total']:3d}  v1={v['n_v1']:3d}  mean_mid={v['mean_mid']:.3f}")

    out_path = r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v9\settled_probe.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "run_time": datetime.now(timezone.utc).isoformat(),
            "settled_results": settled_results,
            "totals": {"n_settled": total_n, "n_v1_eligible": total_v1}
        }, f, indent=2)
    print(f"\nSaved to {out_path}")

if __name__ == "__main__":
    main()
