"""
v10 Market Universe Scout - Agent v10-S1
READ-ONLY probe of Kalshi market categories.
No /portfolio/* calls. No orders. Pure discovery.
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

def api_get(client, private_key, endpoint, params=None):
    path = "/trade-api/v2" + endpoint
    headers = sign_request(private_key, KEY_ID, "GET", path)
    t0 = time.time()
    r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=20.0)
    latency_ms = int((time.time() - t0) * 1000)
    return r, latency_ms

NOW = datetime.now(timezone.utc)
TWO_WEEKS = NOW + timedelta(days=14)

def classify_mid(mid):
    if mid is None:
        return "unknown"
    if 0.20 <= mid <= 0.80:
        return "uncertain"
    elif 0.70 <= mid <= 0.95:
        return "v1-confident"
    elif mid > 0.95 or mid < 0.05:
        return "extreme"
    else:
        return "other"

def analyze_markets(markets):
    """Summarize a list of market dicts."""
    total = len(markets)
    if total == 0:
        return {}

    closing_soon = 0
    mid_uncertain = 0  # 0.20-0.80
    mid_confident = 0  # 0.70-0.95 (v1 band)
    mid_extreme = 0
    mids = []
    spreads = []

    for m in markets:
        # Close time
        close_time_str = m.get("close_time") or m.get("expiration_time")
        if close_time_str:
            try:
                if close_time_str.endswith("Z"):
                    close_time_str = close_time_str[:-1] + "+00:00"
                ct = datetime.fromisoformat(close_time_str)
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                if ct <= TWO_WEEKS:
                    closing_soon += 1
            except Exception:
                pass

        # Mid price
        yes_bid = m.get("yes_bid") or 0
        yes_ask = m.get("yes_ask") or 0

        if yes_bid and yes_ask:
            mid = (yes_bid + yes_ask) / 200.0  # cents -> 0-1
            spread = (yes_ask - yes_bid)  # cents
            mids.append(mid)
            spreads.append(spread)

            if 0.20 <= mid <= 0.80:
                mid_uncertain += 1
            if 0.70 <= mid <= 0.95:
                mid_confident += 1
            if mid > 0.95 or mid < 0.05:
                mid_extreme += 1
        elif yes_bid or yes_ask:
            # one side
            val = (yes_bid or yes_ask) / 100.0
            mids.append(val)

    avg_spread = sum(spreads) / len(spreads) if spreads else None
    quoted = len(spreads)

    return {
        "total": total,
        "closing_within_2wks": closing_soon,
        "quoted_markets": quoted,
        "mid_uncertain_count": mid_uncertain,
        "mid_confident_count": mid_confident,
        "mid_extreme_count": mid_extreme,
        "avg_spread_cents": round(avg_spread, 1) if avg_spread else None,
        "pct_uncertain": round(100 * mid_uncertain / quoted, 1) if quoted else 0,
        "pct_confident": round(100 * mid_confident / quoted, 1) if quoted else 0,
    }

def probe_series_category(client, private_key, category_slug, label, series_tickers=None):
    """Probe a category by fetching open markets for known series tickers."""
    print(f"\n--- Probing: {label} ---")

    all_markets = []
    series_found = []

    if series_tickers:
        for ticker in series_tickers:
            # Fetch open markets for this series
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 100,
            })
            print(f"  /markets?series_ticker={ticker}&status=open -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                data = r.json()
                markets = data.get("markets", [])
                if markets:
                    series_found.append((ticker, len(markets)))
                    all_markets.extend(markets)
                    # Small sample of mids
                    sample_mids = []
                    for m in markets[:5]:
                        yb = m.get("yes_bid", 0) or 0
                        ya = m.get("yes_ask", 0) or 0
                        if yb and ya:
                            sample_mids.append(round((yb + ya) / 200.0, 3))
                    if sample_mids:
                        print(f"    {len(markets)} open markets, sample mids: {sample_mids}")
                    else:
                        print(f"    {len(markets)} open markets (no quotes)")
            time.sleep(0.15)  # rate-limit courtesy

    analysis = analyze_markets(all_markets)
    analysis["series_found"] = series_found
    analysis["label"] = label
    return analysis


def probe_events_category(client, private_key, event_category, label, limit=200):
    """Probe a category via /events?category= endpoint."""
    print(f"\n--- Probing events: {label} ({event_category}) ---")

    r, lat = api_get(client, private_key, "/events", params={
        "status": "open",
        "limit": limit,
    })
    print(f"  /events?status=open&limit={limit} -> {r.status_code} ({lat}ms)")

    if r.status_code != 200:
        return {"label": label, "total": 0, "error": r.status_code}

    data = r.json()
    events = data.get("events", [])
    print(f"  Total open events returned: {len(events)}")

    # Show category breakdown
    cat_counts = defaultdict(int)
    for e in events:
        cat = e.get("category", "unknown")
        cat_counts[cat] += 1

    print("  Category breakdown of returned events:")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt}")

    return {"label": label, "events_total": len(events), "category_breakdown": dict(cat_counts)}


def main():
    print("=" * 70)
    print("v10 Market Universe Scout (Agent v10-S1)")
    print(f"Run time: {NOW.isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=20.0) as client:

        # -------------------------------------------------------
        # PROBE 0: Exchange status
        # -------------------------------------------------------
        print("\n[PROBE 0] Exchange status...")
        r, lat = api_get(client, private_key, "/exchange/status")
        print(f"  Status: {r.status_code}, latency: {lat}ms")
        if r.status_code == 200:
            print(f"  exchange_active: {r.json().get('exchange_active')}")

        # -------------------------------------------------------
        # PROBE 1: Full open markets enumeration via /events
        # -------------------------------------------------------
        results["events"] = probe_events_category(client, private_key, "all", "ALL_OPEN_EVENTS")
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 2: Politics
        # -------------------------------------------------------
        politics_tickers = [
            "KXPRES2028", "KXSENATE2026", "KXHOUSE2026", "KXGOV2026",
            "KXIMPEACH", "KXSPEAKER", "KXSENATE", "KXHOUSEGAIN",
            "KXPRESIDENT", "KXELECTION2026", "KXPOLITICS",
        ]
        results["politics"] = probe_series_category(
            client, private_key, "politics", "POLITICS", politics_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 3: Macro / Economics
        # -------------------------------------------------------
        macro_tickers = [
            "KXFEDFUNDS", "KXCPI", "KXNFP", "KXFOMC",
            "KXGDPGROWTH", "KXUNRATE", "KXRECESSION",
            "KXCPIYOY", "KXCORECPI", "KXNONFARM", "KXGDP",
            "KXUNEMPLOYMENT", "KXFEDRATE", "KXINFLATION",
        ]
        results["macro"] = probe_series_category(
            client, private_key, "macro", "MACRO_ECON", macro_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 4: Crypto
        # -------------------------------------------------------
        crypto_tickers = [
            "KXBTCD", "KXETHD", "KXBTCMAX", "KXETHMAX",
            "KXBTC", "KXETH", "KXSOL", "KXBTCW", "KXETHW",
            "KXBTCM", "KXETHM", "KXSOLM", "KXBTCH",
            "KXBTCWK", "KXETHWK", "KXSOLWK",
        ]
        results["crypto"] = probe_series_category(
            client, private_key, "crypto", "CRYPTO", crypto_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 5: Weather
        # -------------------------------------------------------
        weather_tickers = [
            "KXHIGH", "KXLOW", "KXSNOW", "KXRAIN",
            "KXHURRICANE", "KXHIGHNY", "KXHIGHLA", "KXHIGHCHI",
            "KXHIGHHOU", "KXHIGHPHI", "KXHIGHPHX",
            "KXTORNADO", "KXFROST", "KXHIGHDET", "KXHIGHBOS",
        ]
        results["weather"] = probe_series_category(
            client, private_key, "weather", "WEATHER", weather_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 6: Entertainment
        # -------------------------------------------------------
        entertainment_tickers = [
            "KXOSCARS", "KXEMMYS", "KXGRAMMYS", "KXBOXOFFICE",
            "KXSTREAMING", "KXGOLDENGLOBES", "KXSPOTIFY",
            "KXNETFLIX", "KXDISNEY", "KXMOVIE", "KXMUSIC",
            "KXTV", "KXAWARDS",
        ]
        results["entertainment"] = probe_series_category(
            client, private_key, "entertainment", "ENTERTAINMENT", entertainment_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 7: Tech / Business
        # -------------------------------------------------------
        tech_tickers = [
            "KXTSLA", "KXAAPL", "KXIPO", "KXMERGER",
            "KXLAYOFF", "KXEARNINGS", "KXNVDA", "KXMETA",
            "KXGOOGL", "KXMSFT", "KXAI", "KXTECH",
            "KXCEO", "KXFED500", "KXSP500", "KXNAS",
        ]
        results["tech"] = probe_series_category(
            client, private_key, "tech", "TECH_BUSINESS", tech_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 8: Geopolitics / World Events
        # -------------------------------------------------------
        geo_tickers = [
            "KXUKRAINE", "KXISRAEL", "KXCHINA", "KXNATO",
            "KXSANCTIONS", "KXGAZA", "KXRUSSIA", "KXTAIWAN",
            "KXIRAN", "KXWAR", "KXCEASEF", "KXPEACE",
        ]
        results["geopolitics"] = probe_series_category(
            client, private_key, "geopolitics", "GEOPOLITICS", geo_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 9: Sports props / game resolution
        # -------------------------------------------------------
        sports_game_tickers = [
            "KXNFLGAME", "KXMLBGAME", "KXNBAGAME",
            "KXBOXING", "KXUFCFIGHT", "KXNHLGAME",
            "KXSOCCER", "KXWCSQUAD", "KXWC2026",
            "KXTENNIS", "KXATPGRANDSLAM", "KXWTA",
        ]
        results["sports_game"] = probe_series_category(
            client, private_key, "sports_game", "SPORTS_GAME_RESOLUTION", sports_game_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 10: Recurring / high-frequency markets
        # -------------------------------------------------------
        highfreq_tickers = [
            "KXBTCH", "KXBTCD", "KXBTCWK", "KXBTCM",
            "KXETHH", "KXETHD", "KXETHWK", "KXETHM",
            "KXSOLH", "KXSOLD", "KXSOLWK",
            "KXSPXH", "KXSPXD", "KXNDX",
            "KXOIL", "KXGOLD", "KXSILVER",
        ]
        results["highfreq"] = probe_series_category(
            client, private_key, "highfreq", "HIGH_FREQ_RECURRING", highfreq_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 11: FOMC / macro release event markets
        # -------------------------------------------------------
        macro_event_tickers = [
            "KXFOMC", "KXCPI", "KXNFP", "KXPCE",
            "KXUNRATE", "KXGDP", "KXJOLTS", "KXPPI",
            "KXISM", "KXRETAIL", "KXHOUSING",
        ]
        results["macro_events"] = probe_series_category(
            client, private_key, "macro_events", "MACRO_RELEASE_EVENTS", macro_event_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 12: World Cup / Sports seasons (novel series)
        # -------------------------------------------------------
        novel_sports_tickers = [
            "KXWC2026", "KXWCSQUAD", "KXWCGROUP", "KXWCWINNER",
            "KXEURO2026", "KXCL2026", "KXNBA2026",
            "KXMLBWINS", "KXNBAWINS", "KXNHLCENTRAL",
            "KXF12026", "KXNASCAR", "KXPGA",
        ]
        results["sports_season"] = probe_series_category(
            client, private_key, "sports_season", "SPORTS_SEASON_LONG", novel_sports_tickers
        )
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 13: Miscellaneous discovery - check /series endpoint
        # -------------------------------------------------------
        print("\n--- Probing /series endpoint for category discovery ---")
        r, lat = api_get(client, private_key, "/series", params={"limit": 200})
        print(f"  /series?limit=200 -> {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            series_data = r.json()
            all_series = series_data.get("series", [])
            print(f"  Total series returned: {len(all_series)}")
            # Show categories present
            cat_counts2 = defaultdict(int)
            series_tickers_found = []
            for s in all_series:
                cat = s.get("category", "unknown")
                cat_counts2[cat] += 1
                series_tickers_found.append(s.get("ticker", ""))
            print("  Category breakdown of series:")
            for cat, cnt in sorted(cat_counts2.items(), key=lambda x: -x[1]):
                print(f"    {cat}: {cnt}")
            results["series_discovery"] = {
                "total_series": len(all_series),
                "category_breakdown": dict(cat_counts2),
                "sample_tickers": series_tickers_found[:50],
            }
        time.sleep(0.3)

        # -------------------------------------------------------
        # PROBE 14: Deep-dive on most promising novel: FOMC specific
        # -------------------------------------------------------
        print("\n--- Deep dive: FOMC / CPI event markets ---")
        for ticker in ["KXFOMC", "KXCPI", "KXNFP", "KXPCE", "KXFEDFUNDS"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 20,
            })
            print(f"  /markets?series_ticker={ticker}&status=open -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"    {len(ms)} open markets")
                for m in ms[:3]:
                    yb = m.get("yes_bid", 0) or 0
                    ya = m.get("yes_ask", 0) or 0
                    mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                    close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                    vol = m.get("volume", 0) or 0
                    print(f"    ticker={m.get('ticker','')} mid={mid} close={close} vol={vol}")
            time.sleep(0.2)

        # -------------------------------------------------------
        # PROBE 15: World Cup 2026 specific (FIFA 2026)
        # -------------------------------------------------------
        print("\n--- Deep dive: World Cup 2026 ---")
        for ticker in ["KXWC2026", "KXWCGROUP", "KXWCSQUAD", "KXWCWINNER", "KXFIFAHOSTCITY", "KXWCGOAL"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 20,
            })
            print(f"  /markets?series_ticker={ticker} -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"    {len(ms)} open markets")
                for m in ms[:3]:
                    yb = m.get("yes_bid", 0) or 0
                    ya = m.get("yes_ask", 0) or 0
                    mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                    close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                    vol = m.get("volume", 0) or 0
                    subtitle = m.get("subtitle", "")[:60]
                    print(f"    mid={mid} close={close} vol={vol} | {subtitle}")
            time.sleep(0.2)

        # -------------------------------------------------------
        # PROBE 16: KXBTCD hourly vs KXBTCMAX monthly
        # -------------------------------------------------------
        print("\n--- Deep dive: Crypto by horizon ---")
        for ticker in ["KXBTCD", "KXBTCMAX", "KXBTCWK", "KXBTCM", "KXETHD", "KXETHMAX"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 10,
            })
            print(f"  /markets?series_ticker={ticker} -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"    {len(ms)} open markets")
                for m in ms[:2]:
                    yb = m.get("yes_bid", 0) or 0
                    ya = m.get("yes_ask", 0) or 0
                    mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                    spread = (ya - yb) if (yb and ya) else None
                    close = m.get("close_time", "")[:16] if m.get("close_time") else "?"
                    print(f"    mid={mid} spread={spread}c close={close}")
            time.sleep(0.2)

        # -------------------------------------------------------
        # PROBE 17: KXHIGH weather markets (EC-1 territory)
        # -------------------------------------------------------
        print("\n--- Deep dive: Weather KXHIGH ---")
        for ticker in ["KXHIGHNY", "KXHIGHLA", "KXHIGHCHI", "KXHIGHHOU", "KXHIGHPHX", "KXHIGHBOS"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 10,
            })
            print(f"  /markets?series_ticker={ticker} -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"    {len(ms)} open markets")
                for m in ms[:2]:
                    yb = m.get("yes_bid", 0) or 0
                    ya = m.get("yes_ask", 0) or 0
                    mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                    spread = (ya - yb) if (yb and ya) else None
                    close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                    print(f"    mid={mid} spread={spread}c close={close}")
            time.sleep(0.2)

        # -------------------------------------------------------
        # PROBE 18: SPX / indices / financial markets
        # -------------------------------------------------------
        print("\n--- Deep dive: Index/Financial ---")
        for ticker in ["KXSPX", "KXNAS", "KXNDX", "KXOIL", "KXGOLD", "KXSP500", "KXDOW"]:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": ticker,
                "status": "open",
                "limit": 10,
            })
            print(f"  /markets?series_ticker={ticker} -> {r.status_code} ({lat}ms)")
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                print(f"    {len(ms)} open markets")
                for m in ms[:2]:
                    yb = m.get("yes_bid", 0) or 0
                    ya = m.get("yes_ask", 0) or 0
                    mid = round((yb + ya) / 200.0, 3) if (yb and ya) else None
                    close = m.get("close_time", "")[:10] if m.get("close_time") else "?"
                    vol = m.get("volume", 0) or 0
                    print(f"    mid={mid} close={close} vol={vol}")
            time.sleep(0.2)

        # -------------------------------------------------------
        # Save raw results
        # -------------------------------------------------------
        out_path = Path("data/v10/market_universe_probe.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {out_path}")

        # -------------------------------------------------------
        # Print summary
        # -------------------------------------------------------
        print("\n" + "=" * 70)
        print("SUMMARY BY CATEGORY")
        print("=" * 70)
        for key, res in results.items():
            if key in ("events", "series_discovery"):
                continue
            label = res.get("label", key)
            total = res.get("total", 0)
            close2wk = res.get("closing_within_2wks", 0)
            quoted = res.get("quoted_markets", 0)
            unc = res.get("mid_uncertain_count", 0)
            conf = res.get("mid_confident_count", 0)
            spread = res.get("avg_spread_cents", None)
            series = res.get("series_found", [])
            print(f"\n{label}:")
            print(f"  Open markets total: {total}")
            print(f"  Closing within 2 weeks: {close2wk}")
            print(f"  Quoted (bid+ask): {quoted}")
            print(f"  Mid 0.20-0.80 (uncertain): {unc}")
            print(f"  Mid 0.70-0.95 (v1-confident): {conf}")
            print(f"  Avg spread: {spread}c")
            print(f"  Series with open markets: {series}")

if __name__ == "__main__":
    main()
