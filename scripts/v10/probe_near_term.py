"""
v10 Market Universe Scout - near-term focused probe.
Targets series we know have open markets from probe v1.
Also probes /markets endpoint directly with category filter.
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
            wait = 2 ** attempt * 2.0
            print(f"    429, waiting {wait:.0f}s...")
            time.sleep(wait)
            continue
        return r, latency_ms
    return r, latency_ms

NOW = datetime.now(timezone.utc)
TWO_WEEKS = NOW + timedelta(days=14)

def probe_series(client, private_key, ticker, label=None, limit=100):
    """Probe a single series and return market summary."""
    label = label or ticker
    r, lat = api_get(client, private_key, "/markets", params={
        "series_ticker": ticker,
        "status": "open",
        "limit": limit,
    })
    print(f"\n  {ticker} -> {r.status_code} ({lat}ms)")
    if r.status_code != 200:
        return None

    ms = r.json().get("markets", [])
    if not ms:
        print(f"    0 open markets")
        return None

    print(f"    {len(ms)} open markets")
    total = len(ms)
    close_2wk = 0
    mids = []
    spreads = []
    uncertain = 0
    confident = 0
    vols = []

    for m in ms:
        ct_str = m.get("close_time") or m.get("expiration_time")
        if ct_str:
            try:
                ct = datetime.fromisoformat(ct_str.replace("Z", "+00:00"))
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                if ct <= TWO_WEEKS:
                    close_2wk += 1
            except Exception:
                pass
        yb = m.get("yes_bid", 0) or 0
        ya = m.get("yes_ask", 0) or 0
        vol = m.get("volume", 0) or 0
        vols.append(vol)
        if yb and ya:
            mid = (yb + ya) / 200.0
            spread = ya - yb
            mids.append(mid)
            spreads.append(spread)
            if 0.20 <= mid <= 0.80:
                uncertain += 1
            if 0.70 <= mid <= 0.95:
                confident += 1

    avg_spread = round(sum(spreads)/len(spreads), 1) if spreads else None
    avg_vol = round(sum(vols)/len(vols)) if vols else 0
    quoted = len(mids)
    sample_mids = [round(m, 3) for m in mids[:6]]
    sample_spreads = spreads[:6]

    # Print first 5 markets
    for m in ms[:5]:
        yb = m.get("yes_bid", 0) or 0
        ya = m.get("yes_ask", 0) or 0
        mid = round((yb + ya)/200.0, 3) if (yb and ya) else None
        spread = (ya - yb) if (yb and ya) else None
        close = m.get("close_time", "")[:16] if m.get("close_time") else "?"
        vol = m.get("volume", 0) or 0
        subtitle = (m.get("subtitle","") or "")[:50]
        print(f"    {m.get('ticker','')[:45]} | mid={mid} sp={spread}c | close={close[:10]} vol={vol} | {subtitle}")

    result = {
        "ticker": ticker,
        "label": label,
        "total_open": total,
        "closing_2wk": close_2wk,
        "quoted": quoted,
        "uncertain": uncertain,
        "confident": confident,
        "avg_spread": avg_spread,
        "avg_vol": avg_vol,
        "sample_mids": sample_mids,
    }
    print(f"    Summary: {total} open, {close_2wk} close in 2wk, {quoted} quoted, uncertain={uncertain}, confident={confident}, avg_spread={avg_spread}c, avg_vol={avg_vol}")
    return result


def main():
    print("=" * 70)
    print("v10 Near-Term Market Universe Probe")
    print(f"Run time: {NOW.isoformat()}")
    print("=" * 70)

    private_key = load_key(PEM_PATH)
    results = {}

    with httpx.Client(timeout=30.0) as client:

        # -------------------------------------------------------
        # First try /markets endpoint with limit to get ALL open
        # -------------------------------------------------------
        print("\n[PROBE A] /markets?status=open (direct, up to 200)")
        r, lat = api_get(client, private_key, "/markets", params={
            "status": "open",
            "limit": 200,
        })
        print(f"  -> {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms = r.json().get("markets", [])
            print(f"  Got {len(ms)} markets")
            # Tally by series prefix
            series_counts = defaultdict(int)
            series_mids = defaultdict(list)
            series_spreads = defaultdict(list)
            for m in ms:
                st = m.get("series_ticker", "unknown")
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                vol = m.get("volume", 0) or 0
                series_counts[st] += 1
                if yb and ya:
                    series_mids[st].append((yb+ya)/200.0)
                    series_spreads[st].append(ya-yb)

            print("\n  Series breakdown (top 40 by count):")
            for st, cnt in sorted(series_counts.items(), key=lambda x: -x[1])[:40]:
                mids_list = series_mids[st]
                avg_mid = round(sum(mids_list)/len(mids_list), 3) if mids_list else None
                sp_list = series_spreads[st]
                avg_sp = round(sum(sp_list)/len(sp_list), 1) if sp_list else None
                print(f"    {st}: {cnt} mkts, avg_mid={avg_mid}, avg_spread={avg_sp}c")

            results["all_open_series"] = {
                st: {"count": cnt, "quoted": len(series_mids[st]),
                     "avg_mid": round(sum(series_mids[st])/len(series_mids[st]), 3) if series_mids[st] else None,
                     "avg_spread": round(sum(series_spreads[st])/len(series_spreads[st]), 1) if series_spreads[st] else None}
                for st, cnt in sorted(series_counts.items(), key=lambda x: -x[1])
            }

        time.sleep(2.0)

        # -------------------------------------------------------
        # PROBE B: Known near-term series from probe v1 (those that returned 200)
        # -------------------------------------------------------
        print("\n[PROBE B] Known near-term series with open markets")

        near_term_series = [
            # Sports game resolution
            ("KXMLBGAME", "MLB Game Resolution"),
            ("KXATPGRANDSLAM", "ATP Grand Slam"),
            ("KXWTA", "WTA Tennis"),
            # Crypto
            ("KXBTCD", "BTC Daily"),
            ("KXETHD", "ETH Daily"),
            ("KXETHWK", "ETH Weekly"),
            ("KXSOLWK", "SOL Weekly"),
            ("KXBTCMAX", "BTC Monthly Max"),
            # Macro
            ("KXCPI", "CPI Release"),
            ("KXPCE", "PCE Release"),
            ("KXJOLTS", "JOLTS Release"),
            ("KXPPI", "PPI Release"),
            ("KXNONFARM", "Nonfarm Payrolls"),
            ("KXFEDRATE", "Fed Rate"),
            # Weather (known from EC-1)
            ("KXHIGHNY", "Weather High NY"),
            ("KXHIGHCHI", "Weather High Chicago"),
            ("KXHIGHHOU", "Weather High Houston"),
            ("KXHIGHPHX", "Weather High Phoenix"),
            ("KXHIGHPHI", "Weather High Philadelphia"),
            ("KXHIGHDET", "Weather High Detroit"),
            ("KXHIGHBOS", "Weather High Boston"),
            ("KXLOW", "Weather Low"),
            ("KXSNOW", "Snow"),
            # Sports season
            ("KXPGA", "PGA Golf"),
            ("KXNBAWINS", "NBA Team Wins"),
            ("KXMLBWINS", "MLB Team Wins"),
            # Index / financial
            ("KXNDX", "Nasdaq"),
            ("KXOIL", "Oil"),
            ("KXSILVER", "Silver"),
            ("KXMSFT", "Microsoft"),
            ("KXAI", "AI Markets"),
            ("KXTECH", "Tech Markets"),
            # Politics / elections near-term
            ("KXPRES2028", "2028 Presidential"),
            ("KXHOUSE2026", "2026 House Elections"),
            ("KXGOV2026", "2026 Governor Elections"),
            # Other
            ("KXSPOTIFY", "Spotify"),
            ("KXNETFLIX", "Netflix"),
            ("KXRUSSIA", "Russia"),
            ("KXCEASEF", "Ceasefire"),
        ]

        probe_results = {}
        for ticker, label in near_term_series:
            res = probe_series(client, private_key, ticker, label)
            if res:
                probe_results[ticker] = res
            time.sleep(1.5)

        results["near_term"] = probe_results

        # -------------------------------------------------------
        # PROBE C: Specific samples to check mid distribution
        # for promising categories
        # -------------------------------------------------------
        print("\n[PROBE C] Mid distribution checks on key categories")

        # Check what Sports series are actually active
        print("\n  Active sports series check:")
        sports_near = [
            "KXMLBGAME", "KXNBAFINALS", "KXNBAPLAYOFF", "KXMLBWORLD",
            "KXWC2026MATCH", "KXUCL2026", "KXEUROCUP2026",
            "KXBOXINGMATCH", "KXUFCMATCH", "KXUFC",
            "KXF12026RACE", "KXNASCARGAME",
        ]
        for st in sports_near:
            r, lat = api_get(client, private_key, "/markets", params={
                "series_ticker": st, "status": "open", "limit": 5
            })
            print(f"  {st}: {r.status_code}", end="")
            if r.status_code == 200:
                ms2 = r.json().get("markets", [])
                if ms2:
                    yb = ms2[0].get("yes_bid", 0) or 0
                    ya = ms2[0].get("yes_ask", 0) or 0
                    mid = round((yb+ya)/200.0, 3) if (yb and ya) else None
                    print(f" -> {len(ms2)} mkts, sample mid={mid}")
                else:
                    print(f" -> 0 mkts")
            else:
                print()
            time.sleep(1.2)

        # -------------------------------------------------------
        # PROBE D: Check the Kalshi "series" categories list
        # to see what active categories exist for near-term (not futures)
        # -------------------------------------------------------
        print("\n[PROBE D] Checking /markets directly for cross-category discovery")
        # Query markets without series filter to see what's active
        r, lat = api_get(client, private_key, "/markets", params={
            "status": "open",
            "limit": 200,
            "min_close_ts": int(NOW.timestamp()),
            "max_close_ts": int((NOW + timedelta(days=30)).timestamp()),
        })
        print(f"  /markets closing in 30d: {r.status_code} ({lat}ms)")
        if r.status_code == 200:
            ms3 = r.json().get("markets", [])
            print(f"  {len(ms3)} markets closing within 30 days")
            series_30d = defaultdict(list)
            for m in ms3:
                st = m.get("series_ticker", "unknown")
                yb = m.get("yes_bid", 0) or 0
                ya = m.get("yes_ask", 0) or 0
                vol = m.get("volume", 0) or 0
                mid = (yb+ya)/200.0 if (yb and ya) else None
                spread = (ya-yb) if (yb and ya) else None
                series_30d[st].append({
                    "mid": round(mid, 3) if mid else None,
                    "spread": spread,
                    "vol": vol,
                    "close": (m.get("close_time","") or "")[:10],
                })
            print(f"\n  Series with markets closing in 30 days ({len(series_30d)} unique series):")
            for st, mkts in sorted(series_30d.items(), key=lambda x: -len(x[1])):
                mids_here = [m["mid"] for m in mkts if m["mid"] is not None]
                avg_m = round(sum(mids_here)/len(mids_here), 3) if mids_here else None
                sps = [m["spread"] for m in mkts if m["spread"] is not None]
                avg_sp = round(sum(sps)/len(sps), 1) if sps else None
                vols = [m["vol"] for m in mkts]
                avg_v = round(sum(vols)/len(vols)) if vols else 0
                uncertain_c = sum(1 for m in mids_here if 0.20 <= m <= 0.80)
                confident_c = sum(1 for m in mids_here if 0.70 <= m <= 0.95)
                print(f"    {st}: {len(mkts)} mkts | avg_mid={avg_m} avg_sp={avg_sp}c avg_vol={avg_v} | uncertain={uncertain_c} confident={confident_c}")
            results["series_30d"] = {
                st: {
                    "count": len(mkts),
                    "avg_mid": round(sum([m["mid"] for m in mkts if m["mid"] is not None]) /
                                max(1, sum(1 for m in mkts if m["mid"] is not None)), 3)
                    if any(m["mid"] is not None for m in mkts) else None,
                }
                for st, mkts in series_30d.items()
            }

        # -------------------------------------------------------
        # Save
        # -------------------------------------------------------
        out_path = Path("data/v10/near_term_probe.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nSaved to {out_path}")

if __name__ == "__main__":
    main()
