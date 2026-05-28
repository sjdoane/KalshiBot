"""
v10 Market Universe Scout v2 - rate-limit aware
Uses /events endpoint to get category breakdown and specific market samples.
Avoids per-series hammering that caused 429s.
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

def api_get(client, private_key, endpoint, params=None, retry=3):
    path = "/trade-api/v2" + endpoint
    for attempt in range(retry):
        headers = sign_request(private_key, KEY_ID, "GET", path)
        t0 = time.time()
        r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=30.0)
        latency_ms = int((time.time() - t0) * 1000)
        if r.status_code == 429:
            wait = 2 ** attempt * 1.5
            print(f"    429 on {endpoint}, waiting {wait:.1f}s...")
            time.sleep(wait)
            continue
        return r, latency_ms
    return r, latency_ms

NOW = datetime.now(timezone.utc)
TWO_WEEKS = NOW + timedelta(days=14)
THIRTY_DAYS = NOW + timedelta(days=30)

def main():
    print("=" * 70)
    print("v10 Market Universe Scout v2")
    print(f"Run time: {NOW.isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=30.0) as client:

        # -------------------------------------------------------
        # PROBE 0: Exchange status
        # -------------------------------------------------------
        r, lat = api_get(client, private_key, "/exchange/status")
        print(f"[PROBE 0] Exchange status: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            print(f"  exchange_active: {r.json().get('exchange_active')}")

        time.sleep(1.0)

        # -------------------------------------------------------
        # PROBE 1: /events with pagination to get ALL categories
        # -------------------------------------------------------
        print("\n[PROBE 1] Enumerating open events by category...")
        all_events = []
        cursor = None
        page = 0
        while True:
            params = {"status": "open", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            r, lat = api_get(client, private_key, "/events", params=params)
            print(f"  Page {page}: {r.status_code} ({lat}ms)")
            if r.status_code != 200:
                break
            data = r.json()
            ev = data.get("events", [])
            all_events.extend(ev)
            print(f"    Got {len(ev)} events (total so far: {len(all_events)})")
            cursor = data.get("cursor")
            if not cursor or len(ev) < 200:
                break
            page += 1
            time.sleep(1.0)

        print(f"\nTotal open events: {len(all_events)}")

        # Category breakdown
        cat_events = defaultdict(list)
        for e in all_events:
            cat = e.get("category", "unknown")
            cat_events[cat].append(e)

        print("\nCategory breakdown:")
        for cat, evs in sorted(cat_events.items(), key=lambda x: -len(x[1])):
            print(f"  {cat}: {len(evs)} events")

        results["events_by_category"] = {cat: len(evs) for cat, evs in cat_events.items()}

        time.sleep(1.0)

        # -------------------------------------------------------
        # PROBE 2: For each category, sample markets and compute stats
        # -------------------------------------------------------
        category_data = {}

        for cat, evs in sorted(cat_events.items(), key=lambda x: -len(x[1])):
            print(f"\n--- Category: {cat} ({len(evs)} events) ---")
            # Sample up to 5 events and fetch their markets
            sample_events = evs[:8]
            cat_markets = []
            event_series = []

            for e in sample_events:
                event_ticker = e.get("event_ticker", "")
                series_ticker = e.get("series_ticker", "")
                if series_ticker and series_ticker not in event_series:
                    event_series.append(series_ticker)

                # Fetch markets for this event
                r, lat = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker,
                    "status": "open",
                    "limit": 50,
                })
                if r.status_code == 200:
                    ms = r.json().get("markets", [])
                    cat_markets.extend(ms)
                    if ms:
                        yb = ms[0].get("yes_bid", 0) or 0
                        ya = ms[0].get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = ms[0].get("close_time", "")[:10] if ms[0].get("close_time") else "?"
                        vol = ms[0].get("volume", 0) or 0
                        print(f"  Event {event_ticker}: {len(ms)} mkts, sample mid={mid} spread={spread}c close={close} vol={vol}")
                    else:
                        print(f"  Event {event_ticker}: 0 open markets")
                time.sleep(0.8)

            # Analyze
            total_mkt = len(cat_markets)
            close_2wk = 0
            close_30d = 0
            mids = []
            spreads = []
            uncertain = 0  # 0.20-0.80
            confident = 0  # 0.70-0.95
            extreme = 0

            for m in cat_markets:
                ct_str = m.get("close_time") or m.get("expiration_time")
                if ct_str:
                    try:
                        ct = datetime.fromisoformat(ct_str.replace("Z", "+00:00"))
                        if ct.tzinfo is None:
                            ct = ct.replace(tzinfo=timezone.utc)
                        if ct <= TWO_WEEKS:
                            close_2wk += 1
                        if ct <= THIRTY_DAYS:
                            close_30d += 1
                    except Exception:
                        pass
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                if yb and ya:
                    mid = (yb + ya) / 200.0
                    spread = ya - yb
                    mids.append(mid)
                    spreads.append(spread)
                    if 0.20 <= mid <= 0.80:
                        uncertain += 1
                    if 0.70 <= mid <= 0.95:
                        confident += 1
                    if mid > 0.95 or mid < 0.05:
                        extreme += 1

            quoted = len(mids)
            avg_spread = round(sum(spreads) / len(spreads), 1) if spreads else None
            sample_mids = [round(m, 3) for m in mids[:8]]

            category_data[cat] = {
                "event_count": len(evs),
                "sampled_events": len(sample_events),
                "sampled_markets": total_mkt,
                "closing_2wks": close_2wk,
                "closing_30d": close_30d,
                "quoted": quoted,
                "uncertain_0.20_0.80": uncertain,
                "confident_0.70_0.95": confident,
                "extreme": extreme,
                "avg_spread_cents": avg_spread,
                "sample_mids": sample_mids,
                "sample_series": event_series[:5],
            }

            print(f"  Sampled {total_mkt} markets ({quoted} quoted)")
            print(f"  Uncertain (0.20-0.80): {uncertain}, Confident (0.70-0.95): {confident}")
            print(f"  Avg spread: {avg_spread}c | Sample mids: {sample_mids}")
            print(f"  Sample series tickers: {event_series[:5]}")

        results["category_data"] = category_data

        time.sleep(1.0)

        # -------------------------------------------------------
        # PROBE 3: /series for unique series count per category
        # -------------------------------------------------------
        print("\n[PROBE 3] Series count per category (/series)...")
        # Already got this from first probe: 10398 series total
        # Confirmed categories: Entertainment:2401, Sports:2025, Politics:1937,
        # Elections:1356, Economics:536, Financials:459, Mentions:359,
        # Climate:274, SciTech:246, Crypto:232, World:142, Companies:142,
        # Health:96, Social:52, Commodities:48, Transportation:39, Exotics:10, Education:1
        results["series_count"] = {
            "Entertainment": 2401, "Sports": 2025, "Politics": 1937,
            "Elections": 1356, "Economics": 536, "Financials": 459,
            "Mentions": 359, "Climate and Weather": 274,
            "Science and Technology": 246, "Crypto": 232,
            "World": 142, "Companies": 142, "Health": 96,
            "Social": 52, "Commodities": 48, "Transportation": 39,
            "Exotics": 10, "Education": 1,
        }

        time.sleep(1.0)

        # -------------------------------------------------------
        # PROBE 4: Specific deep-dives on key categories
        # -------------------------------------------------------
        print("\n[PROBE 4] Deep dives on specific promising series...")

        # CPI markets
        print("\n  CPI markets:")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXCPI", "status": "open", "limit": 20
        })
        print(f"  KXCPI status=open: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} open markets")
            for m in ms[:5]:
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                spread = (ya - yb) if (yb and ya) else None
                close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                vol = m.get("volume", 0) or 0
                subtitle = m.get("subtitle", "")[:60]
                print(f"    {m.get('ticker','')} | mid={mid} spread={spread}c | close={close} vol={vol} | {subtitle}")

        time.sleep(1.5)

        # FOMC
        print("\n  FOMC markets:")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXFOMC", "status": "open", "limit": 20
        })
        print(f"  KXFOMC: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} open markets")
            for m in ms[:5]:
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                spread = (ya - yb) if (yb and ya) else None
                close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                vol = m.get("volume", 0) or 0
                subtitle = m.get("subtitle", "")[:60]
                print(f"    {m.get('ticker','')} | mid={mid} spread={spread}c | close={close} vol={vol} | {subtitle}")

        time.sleep(1.5)

        # MLB game resolution
        print("\n  KXMLBGAME markets:")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXMLBGAME", "status": "open", "limit": 30
        })
        print(f"  KXMLBGAME: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} open markets")
            for m in ms[:8]:
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                spread = (ya - yb) if (yb and ya) else None
                close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                vol = m.get("volume", 0) or 0
                subtitle = m.get("subtitle", "")[:60]
                print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {subtitle}")

        time.sleep(1.5)

        # BTCD - crypto daily
        print("\n  KXBTCD markets:")
        r, lat = api_get(client, private_key, "/markets", params={
            "series_ticker": "KXBTCD", "status": "open", "limit": 20
        })
        print(f"  KXBTCD: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  {len(ms)} open markets")
            for m in ms[:5]:
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                spread = (ya - yb) if (yb and ya) else None
                close = m.get("close_time", "")[:16] if m.get("close_time") else "?"
                vol = m.get("volume", 0) or 0
                subtitle = m.get("subtitle", "")[:60]
                print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {subtitle}")

        time.sleep(1.5)

        # Elections
        print("\n  Elections sample:")
        r, lat = api_get(client, private_key, "/events", params={
            "status": "open", "limit": 10
        })
        # Use stored events from cat_events
        if "Elections" in cat_events:
            for e in cat_events["Elections"][:5]:
                event_ticker = e.get("event_ticker", "")
                r2, lat2 = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker, "status": "open", "limit": 10
                })
                if r2.status_code == 200:
                    ms2 = r2.json().get("markets", [])
                    for m in ms2[:2]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                        vol = m.get("volume", 0) or 0
                        title = m.get("title", "")[:60]
                        print(f"    {event_ticker}: mid={mid} spread={spread}c close={close} vol={vol} | {title}")
                time.sleep(1.0)

        # World Cup 2026 - try different tickers
        print("\n  World Cup 2026 search:")
        for wc_ticker in ["KXWCFINAL", "KXWCMATCH", "KXWCRESULT", "KXWCUSA"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": wc_ticker, "status": "open", "limit": 5
            })
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"  {wc_ticker}: {len(ms)} open markets (status={r.status_code})")
            time.sleep(0.8)

        # Entertainment
        print("\n  Entertainment sample:")
        if "Entertainment" in cat_events:
            for e in cat_events["Entertainment"][:5]:
                event_ticker = e.get("event_ticker", "")
                r2, lat2 = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker, "status": "open", "limit": 10
                })
                if r2.status_code == 200:
                    ms2 = r2.json().get("markets", [])
                    for m in ms2[:2]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                        vol = m.get("volume", 0) or 0
                        title = m.get("title", "")[:70]
                        print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {title}")
                time.sleep(1.0)

        # Science and Technology
        print("\n  Science and Technology sample:")
        if "Science and Technology" in cat_events:
            for e in cat_events["Science and Technology"][:5]:
                event_ticker = e.get("event_ticker", "")
                r2, lat2 = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker, "status": "open", "limit": 10
                })
                if r2.status_code == 200:
                    ms2 = r2.json().get("markets", [])
                    for m in ms2[:2]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                        vol = m.get("volume", 0) or 0
                        title = m.get("title", "")[:70]
                        print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {title}")
                time.sleep(1.0)

        # World events
        print("\n  World events sample:")
        if "World" in cat_events:
            for e in cat_events["World"][:5]:
                event_ticker = e.get("event_ticker", "")
                r2, lat2 = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker, "status": "open", "limit": 10
                })
                if r2.status_code == 200:
                    ms2 = r2.json().get("markets", [])
                    for m in ms2[:2]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                        vol = m.get("volume", 0) or 0
                        title = m.get("title", "")[:70]
                        print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {title}")
                time.sleep(1.0)

        # -------------------------------------------------------
        # PROBE 5: Check specific "exotics" and notable categories
        # -------------------------------------------------------
        print("\n[PROBE 5] Exotics and notable categories...")
        if "Exotics" in cat_events:
            for e in cat_events["Exotics"][:10]:
                event_ticker = e.get("event_ticker", "")
                title = e.get("title", "")
                print(f"  Exotic event: {event_ticker} | {title}")
                r2, lat2 = api_get(client, private_key, "/markets", params={
                    "event_ticker": event_ticker, "status": "open", "limit": 10
                })
                if r2.status_code == 200:
                    ms2 = r2.json().get("markets", [])
                    for m in ms2[:3]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                        spread = (ya - yb) if (yb and ya) else None
                        close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                        vol = m.get("volume", 0) or 0
                        mtitle = m.get("title", "")[:70]
                        print(f"    mid={mid} spread={spread}c close={close} vol={vol} | {mtitle}")
                time.sleep(1.0)

        # -------------------------------------------------------
        # Save results
        # -------------------------------------------------------
        out_path = Path("data/v10/universe_v2.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {out_path}")

        print("\n" + "=" * 70)
        print("FULL CATEGORY DATA DUMP")
        print("=" * 70)
        for cat, d in category_data.items():
            print(f"\n{cat} (events={d['event_count']}):")
            print(f"  Sampled {d['sampled_markets']} markets ({d['quoted']} quoted)")
            print(f"  Uncertain: {d['uncertain_0.20_0.80']} | Confident: {d['confident_0.70_0.95']}")
            print(f"  Avg spread: {d['avg_spread_cents']}c | Mids: {d['sample_mids']}")
            print(f"  Close 2wk: {d['closing_2wks']} | Close 30d: {d['closing_30d']}")
            print(f"  Sample series: {d['sample_series']}")

if __name__ == "__main__":
    main()
