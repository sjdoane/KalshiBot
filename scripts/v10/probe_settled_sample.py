"""
v10 Scout: Sample settled markets to understand mid distribution by category.
Also probes specific orderbook snapshots for live markets to understand spread.
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
import httpx
import base64
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

def api_get(client, private_key, endpoint, params=None, retry=4):
    path = "/trade-api/v2" + endpoint
    for attempt in range(retry):
        headers = sign_request(private_key, KEY_ID, "GET", path)
        t0 = time.time()
        r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=30.0)
        latency_ms = int((time.time() - t0) * 1000)
        if r.status_code == 429:
            wait = 2 ** attempt * 2.5
            print(f"    429, retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue
        return r, latency_ms
    return r, latency_ms

NOW = datetime.now(timezone.utc)

def probe_series_settled(client, private_key, ticker, label, limit=50):
    """Get recently settled markets to understand mid/volume distribution."""
    r, lat = api_get(client, private_key, "/markets", params={
        "series_ticker": ticker,
        "status": "settled",
        "limit": limit,
    })
    print(f"\n  {ticker} (settled) -> {r.status_code} ({lat}ms)")
    if r.status_code != 200:
        return None

    ms = r.json().get("markets", [])
    if not ms:
        print(f"    0 settled markets found")
        return None

    print(f"    {len(ms)} settled markets")
    mids = []
    vols = []
    last_prices = []

    for m in ms:
        yb = m.get("yes_bid", 0) or 0
        ya = m.get("yes_ask", 0) or 0
        last_p = m.get("last_price") or 0
        vol = m.get("volume", 0) or 0
        if yb and ya:
            mid = (yb + ya) / 200.0
            mids.append(mid)
        elif last_p:
            last_prices.append(last_p / 100.0)
        vols.append(vol)

    uncertain = sum(1 for m in mids if 0.20 <= m <= 0.80)
    confident = sum(1 for m in mids if 0.70 <= m <= 0.95)
    avg_vol = round(sum(vols)/len(vols)) if vols else 0
    total_vol = sum(vols)

    # Sample output
    for m in ms[:4]:
        last_p = m.get("last_price") or 0
        vol = m.get("volume", 0) or 0
        close = (m.get("close_time","") or "")[:10]
        result_v = m.get("result", "")
        subtitle = (m.get("subtitle","") or "")[:50]
        print(f"    last_price={last_p}c close={close} vol={vol} result={result_v} | {subtitle}")

    print(f"    Avg vol={avg_vol} total_vol={total_vol} quoted={len(mids)} uncertain={uncertain} confident={confident}")
    return {
        "ticker": ticker, "label": label, "settled_count": len(ms),
        "avg_vol": avg_vol, "total_vol": total_vol,
        "uncertain": uncertain, "confident": confident,
    }

def probe_orderbook(client, private_key, market_ticker):
    """Check orderbook for a specific open market."""
    r, lat = api_get(client, private_key, f"/markets/{market_ticker}/orderbook")
    print(f"\n  Orderbook {market_ticker}: {r.status_code} ({lat}ms)")
    if r.status_code == 200:
        ob = r.json().get("orderbook", {})
        yes_bids = ob.get("yes", [])
        no_bids = ob.get("no", [])
        print(f"    YES side: {len(yes_bids)} levels | NO side: {len(no_bids)} levels")
        if yes_bids:
            print(f"    Top YES bids: {yes_bids[:3]}")
        if no_bids:
            print(f"    Top NO bids: {no_bids[:3]}")
        return ob
    return None

def main():
    print("=" * 70)
    print("v10 Settled Markets + Orderbook Probe")
    print(f"Run time: {NOW.isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=30.0) as client:

        # -------------------------------------------------------
        # PROBE A: Settled markets by category to understand volume/mid
        # -------------------------------------------------------
        print("\n[PROBE A] Settled market samples by series")
        settled_series = [
            ("KXCPI", "CPI"),
            ("KXFOMC", "FOMC"),
            ("KXNFP", "Nonfarm Payrolls"),
            ("KXBTCD", "BTC Daily"),
            ("KXETHD", "ETH Daily"),
            ("KXHIGHNY", "Weather High NY"),
            ("KXHIGHCHI", "Weather High Chicago"),
            ("KXMLBGAME", "MLB Game"),
            ("KXMLBWINS", "MLB Team Wins"),
            ("KXNBAWINS", "NBA Team Wins"),
            ("KXBOXING", "Boxing"),
            ("KXUFCFIGHT", "UFC Fight"),
            ("KXATPGRANDSLAM", "ATP Grand Slam"),
            ("KXPRES2028", "2028 Presidential"),
            ("KXPGA", "PGA Golf"),
            ("KXSPX", "S&P 500"),
            ("KXGOLD", "Gold"),
        ]

        settled_results = {}
        for ticker, label in settled_series:
            res = probe_series_settled(client, private_key, ticker, label)
            if res:
                settled_results[ticker] = res
            time.sleep(1.8)

        results["settled"] = settled_results

        # -------------------------------------------------------
        # PROBE B: Check orderbooks for key open markets
        # We know KXBTCD and KXHIGHNY have open markets
        # -------------------------------------------------------
        print("\n[PROBE B] Orderbook snapshots for live markets")

        # Get first KXBTCD open market ticker
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXBTCD", "status": "open", "limit": 5
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            if ms:
                btcd_ticker = ms[len(ms)//2].get("ticker", "")  # middle strike
                print(f"  Checking KXBTCD middle strike: {btcd_ticker}")
                ob = probe_orderbook(client, private_key, btcd_ticker)
                results["btcd_ob"] = ob
            time.sleep(1.5)

        # Get first KXHIGHNY open market
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXHIGHNY", "status": "open", "limit": 5
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            if ms:
                hny_ticker = ms[2].get("ticker", "") if len(ms) > 2 else ms[0].get("ticker","")
                print(f"  Checking KXHIGHNY: {hny_ticker}")
                ob = probe_orderbook(client, private_key, hny_ticker)
                results["hny_ob"] = ob
            time.sleep(1.5)

        # Get first KXMLBGAME open market
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXMLBGAME", "status": "open", "limit": 5
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            if ms:
                mlb_ticker = ms[0].get("ticker", "")
                print(f"  Checking KXMLBGAME: {mlb_ticker}")
                ob = probe_orderbook(client, private_key, mlb_ticker)
                results["mlbgame_ob"] = ob
            time.sleep(1.5)

        # Get first KXCPI open market
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXCPI", "status": "open", "limit": 10
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            if ms:
                # Find the "current" CPI at-the-money strike
                cpi_ticker = ms[len(ms)//2].get("ticker", "")
                print(f"  Checking KXCPI mid-strike: {cpi_ticker}")
                ob = probe_orderbook(client, private_key, cpi_ticker)
                results["cpi_ob"] = ob
            time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE C: Check recent trades for volume confirmation
        # -------------------------------------------------------
        print("\n[PROBE C] Recent trades for key series")
        trade_series = [
            ("KXBTCD", "BTC Daily"),
            ("KXCPI", "CPI"),
            ("KXHIGHNY", "Weather NY"),
            ("KXMLBGAME", "MLB Game"),
        ]
        for ticker, label in trade_series:
            r, lat = api_get(client, private_key, f"/series/{ticker}/trades", params={"limit": 10})
            print(f"\n  {ticker} trades: {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                trades = r.json().get("trades", [])
                print(f"    {len(trades)} recent trades")
                for t in trades[:4]:
                    count = t.get("count", 0)
                    price = t.get("yes_price", 0) or 0
                    ts = t.get("created_time", "")[:16]
                    taker_side = t.get("taker_side", "")
                    print(f"    count={count} price={price}c ts={ts} taker={taker_side}")
            time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE D: Historical trades on a settled KXCPI to confirm mid dist
        # -------------------------------------------------------
        print("\n[PROBE D] Historical settled market detail - CPI")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXCPI", "status": "settled", "limit": 5
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            for m in ms[:3]:
                mk_ticker = m.get("ticker", "")
                last_p = m.get("last_price") or 0
                vol = m.get("volume", 0) or 0
                result_v = m.get("result", "")
                open_interest = m.get("open_interest", 0) or 0
                close = (m.get("close_time","") or "")[:10]
                subtitle = (m.get("subtitle","") or "")[:50]
                print(f"\n  {mk_ticker}: last_price={last_p}c vol={vol} result={result_v} close={close}")
                print(f"    subtitle: {subtitle}")
                # Get trades for this specific settled market
                r2, lat2 = api_get(client, private_key, f"/markets/{mk_ticker}/trades", params={"limit": 5})
                if r2.status_code == 200:
                    trades2 = r2.json().get("trades", [])
                    print(f"    Trades: {len(trades2)} found")
                    for t in trades2[:3]:
                        print(f"      price={t.get('yes_price')}c count={t.get('count')} side={t.get('taker_side')}")
                time.sleep(1.5)

        # -------------------------------------------------------
        # Save
        # -------------------------------------------------------
        out_path = Path("data/v10/settled_probe.json")
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nSaved to {out_path}")

if __name__ == "__main__":
    main()
