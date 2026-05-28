"""
v10 Scout: Use /markets/trades and /historical/trades to confirm volume
and mid distribution for key categories. This is the working approach
from v6 that proved the trade data is accessible.
Also does proper /markets pagination to see all open categories.
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
            print(f"    429, waiting {wait:.0f}s...")
            time.sleep(wait)
            continue
        return r, latency_ms
    return r, latency_ms

NOW = datetime.now(timezone.utc)

def main():
    print("=" * 70)
    print("v10 Trades/Volume Probe")
    print(f"Run time: {NOW.isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=30.0) as client:

        # -------------------------------------------------------
        # PROBE A: /markets/trades - recent trades across all markets
        # -------------------------------------------------------
        print("\n[PROBE A] /markets/trades?limit=200 (all recent trades)")
        r, lat = api_get(client, private_key, "/markets/trades", params={"limit": 200})
        print(f"  -> {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            trades = r.json().get("trades", [])
            print(f"  {len(trades)} trades")
            # Tally by series
            ticker_trades = defaultdict(list)
            for t in trades:
                tk = t.get("ticker", "")
                # Series is ticker up to second dash
                parts = tk.split("-")
                series = parts[0] if parts else tk
                ticker_trades[series].append(t)

            print("\n  Trade breakdown by series (top 30):")
            for s, ts in sorted(ticker_trades.items(), key=lambda x: -len(x[1]))[:30]:
                prices = [t.get("yes_price", 0) or 0 for t in ts]
                avg_p = round(sum(prices)/len(prices)/100.0, 3) if prices else None
                counts = [t.get("count", 0) or 0 for t in ts]
                total_c = sum(counts)
                print(f"    {s}: {len(ts)} trades, avg_mid={avg_p}, total_contracts={total_c}")
            results["recent_trades_by_series"] = {
                s: {"trade_count": len(ts),
                    "avg_price": round(sum([t.get("yes_price",0) or 0 for t in ts])/
                                 max(1,len(ts))/100.0, 3),
                    "total_contracts": sum([t.get("count",0) or 0 for t in ts])}
                for s, ts in sorted(ticker_trades.items(), key=lambda x: -len(x[1]))[:40]
            }
            # Show sample trades
            print("\n  Sample of last 10 trades:")
            for t in trades[:10]:
                tk = t.get("ticker", "")
                price = round((t.get("yes_price", 0) or 0) / 100.0, 2)
                count = t.get("count", 0) or 0
                side = t.get("taker_side", "")
                ts_v = (t.get("created_time", "") or "")[:16]
                print(f"    {tk[:50]} | price={price} count={count} side={side} | {ts_v}")

        time.sleep(2.0)

        # -------------------------------------------------------
        # PROBE B: /historical/trades for specific KXBTCD settled markets
        # -------------------------------------------------------
        print("\n[PROBE B] Historical trades for settled KXBTCD (T-2 hours window)")
        # From probe v1: KXBTCD-26MAY2617-T8xxxx settled 2026-05-26
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXBTCD", "status": "settled", "limit": 5
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  Got {len(ms)} settled KXBTCD markets")
            if ms:
                # Take a market that likely had trades (at-the-money type)
                for m in ms[2:5]:  # Skip extreme OTM
                    tk = m.get("ticker", "")
                    close_str = (m.get("close_time","") or "")
                    last_p = m.get("last_price") or 0
                    result_v = m.get("result","")
                    subtitle = (m.get("subtitle","") or "")[:40]
                    print(f"\n  Market: {tk} | result={result_v} last={last_p}c | {subtitle}")
                    if close_str:
                        try:
                            ct = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
                            window_start = ct - timedelta(hours=4)
                            window_end = ct + timedelta(hours=1)
                            r2, lat2 = api_get(client, private_key, "/markets/trades", params={
                                "ticker": tk,
                                "limit": 50,
                                "min_ts": int(window_start.timestamp()),
                                "max_ts": int(window_end.timestamp()),
                            })
                            print(f"  /markets/trades: {r2.status_code} ({lat2}ms)")
                            if r2.status_code == 200:
                                trades2 = r2.json().get("trades", [])
                                print(f"    {len(trades2)} trades in T-4h to T+1h window")
                                for t in trades2[:5]:
                                    price = round((t.get("yes_price",0) or 0)/100.0, 2)
                                    count = t.get("count",0) or 0
                                    side = t.get("taker_side","")
                                    ts_v = (t.get("created_time","") or "")[:19]
                                    print(f"      price={price} count={count} side={side} | {ts_v}")
                        except Exception as e:
                            print(f"  Error: {e}")
                    time.sleep(1.5)

        time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE C: Get CPI settled trades
        # -------------------------------------------------------
        print("\n[PROBE C] CPI April release - settled market trades")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXCPI", "status": "settled", "limit": 10
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} settled CPI markets")
            # Find the one that resolved YES (the actual outcome)
            for m in ms:
                result_v = m.get("result","")
                tk = m.get("ticker","")
                last_p = m.get("last_price") or 0
                vol = m.get("volume",0) or 0
                subtitle = (m.get("subtitle","") or "")[:50]
                close_str = (m.get("close_time","") or "")[:10]
                print(f"  {tk}: result={result_v} last={last_p}c vol={vol} close={close_str} | {subtitle}")

        time.sleep(1.5)

        # Try fetching CPI trades regardless of resolution
        print("\n  CPI - searching for trades in all settled markets:")
        if r.status_code == 200 and ms:
            for m in ms[:5]:
                tk = m.get("ticker","")
                close_str = m.get("close_time","") or ""
                if not close_str:
                    continue
                ct = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
                window_start = ct - timedelta(hours=72)  # 3 days before
                r2, lat2 = api_get(client, private_key, "/markets/trades", params={
                    "ticker": tk,
                    "limit": 20,
                    "min_ts": int(window_start.timestamp()),
                })
                print(f"  {tk} trades ({r2.status_code} {lat2}ms): {len(r2.json().get('trades',[])) if r2.status_code==200 else 'N/A'}")
                if r2.status_code == 200:
                    trades3 = r2.json().get("trades", [])
                    for t in trades3[:3]:
                        price = round((t.get("yes_price",0) or 0)/100.0, 2)
                        count = t.get("count",0) or 0
                        side = t.get("taker_side","")
                        ts_v = (t.get("created_time","") or "")[:16]
                        print(f"    price={price} count={count} side={side} | {ts_v}")
                time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE D: Check the KXBTCD today settled markets for volume
        # These JUST settled; should have trades from today
        # -------------------------------------------------------
        print("\n[PROBE D] KXBTCD from today (just settled)")
        today_str = NOW.strftime("%Y%m%d")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXBTCD",
            "status": "settled",
            "limit": 50,
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} settled KXBTCD")
            # Find markets that settled today
            today_mkts = []
            for m in ms:
                ct_str = m.get("close_time","") or ""
                if "2026-05-26" in ct_str:
                    today_mkts.append(m)
            print(f"  {len(today_mkts)} markets settled 2026-05-26")
            for m in today_mkts[:5]:
                tk = m.get("ticker","")
                result_v = m.get("result","")
                last_p = m.get("last_price") or 0
                vol = m.get("volume",0) or 0
                subtitle = (m.get("subtitle","") or "")[:50]
                print(f"  {tk}: result={result_v} last={last_p}c vol={vol} | {subtitle}")
            # Get trades for a today-settled market
            if today_mkts:
                tk = today_mkts[len(today_mkts)//2].get("ticker","")
                ct_str = today_mkts[len(today_mkts)//2].get("close_time","")
                ct = datetime.fromisoformat(ct_str.replace("Z","+00:00"))
                window_start = ct - timedelta(hours=2)
                r2, lat2 = api_get(client, private_key, "/markets/trades", params={
                    "ticker": tk, "limit": 50,
                    "min_ts": int(window_start.timestamp()),
                })
                print(f"\n  Trades for {tk}: {r2.status_code} ({lat2}ms)")
                if r2.status_code == 200:
                    trades4 = r2.json().get("trades", [])
                    print(f"  {len(trades4)} trades in T-2h window")
                    for t in trades4[:8]:
                        price = round((t.get("yes_price",0) or 0)/100.0, 2)
                        count = t.get("count",0) or 0
                        side = t.get("taker_side","")
                        ts_v = (t.get("created_time","") or "")[:16]
                        print(f"    price={price} count={count} side={side} | {ts_v}")

        time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE E: KXMLBGAME trades for today
        # -------------------------------------------------------
        print("\n[PROBE E] KXMLBGAME settled today")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXMLBGAME", "status": "settled", "limit": 50
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            today_mkts = [m for m in ms if "2026-05-26" in (m.get("close_time","") or "")]
            print(f"  {len(today_mkts)} KXMLBGAME settled today")
            for m in today_mkts[:5]:
                tk = m.get("ticker","")
                result_v = m.get("result","")
                last_p = m.get("last_price") or 0
                vol = m.get("volume",0) or 0
                subtitle = (m.get("subtitle","") or "")[:50]
                print(f"  {tk}: result={result_v} last={last_p}c vol={vol}")
            if today_mkts:
                tk = today_mkts[0].get("ticker","")
                r2, lat2 = api_get(client, private_key, "/markets/trades", params={
                    "ticker": tk, "limit": 50,
                    "min_ts": int((NOW - timedelta(hours=24)).timestamp()),
                })
                print(f"  Trades for {tk}: {r2.status_code} ({lat2}ms)")
                if r2.status_code == 200:
                    trades5 = r2.json().get("trades", [])
                    print(f"  {len(trades5)} trades")
                    for t in trades5[:5]:
                        price = round((t.get("yes_price",0) or 0)/100.0, 2)
                        count = t.get("count",0) or 0
                        side = t.get("taker_side","")
                        print(f"    price={price} count={count} side={side}")

        time.sleep(1.5)

        # -------------------------------------------------------
        # PROBE F: KXBOXING trades (fresh fight night data)
        # -------------------------------------------------------
        print("\n[PROBE F] KXBOXING recent trades (fight 2026-05-24)")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXBOXING", "status": "settled", "limit": 20
        })
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} settled KXBOXING markets")
            may24_mkts = [m for m in ms if "2026-05-24" in (m.get("close_time","") or "")]
            print(f"  {len(may24_mkts)} settled 2026-05-24")
            for m in may24_mkts[:4]:
                tk = m.get("ticker","")
                result_v = m.get("result","")
                last_p = m.get("last_price") or 0
                vol = m.get("volume",0) or 0
                subtitle = (m.get("subtitle","") or "")[:60]
                print(f"  {tk}: result={result_v} last={last_p}c vol={vol} | {subtitle}")
            if may24_mkts:
                tk = may24_mkts[0].get("ticker","")
                r2, lat2 = api_get(client, private_key, "/markets/trades", params={
                    "ticker": tk, "limit": 100,
                    "min_ts": int((NOW - timedelta(days=3)).timestamp()),
                })
                print(f"  Trades for {tk}: {r2.status_code} ({lat2}ms)")
                if r2.status_code == 200:
                    trades6 = r2.json().get("trades", [])
                    print(f"  {len(trades6)} trades in last 3 days")
                    for t in trades6[:8]:
                        price = round((t.get("yes_price",0) or 0)/100.0, 2)
                        count = t.get("count",0) or 0
                        side = t.get("taker_side","")
                        ts_v = (t.get("created_time","") or "")[:16]
                        print(f"    price={price} count={count} side={side} | {ts_v}")

        # -------------------------------------------------------
        # Save
        # -------------------------------------------------------
        out_path = Path("data/v10/trades_volume_probe.json")
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nSaved to {out_path}")

if __name__ == "__main__":
    main()
