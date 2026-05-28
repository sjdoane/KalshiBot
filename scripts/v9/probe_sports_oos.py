"""
v9 Agent A1: targeted sports OOS probe.
Focuses on v1-residual sports series: KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF,
KXNFLGAME, etc. Probes closed markets 2026-02-01 to 2026-05-26 by
series_ticker to get accurate v1-eligible counts.
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import httpx

KEY_ID = "83df1ad0-b442-4740-9bf6-f02f2102d807"
PEM_PATH = r"C:\Users\SamJD\AppData\Local\KalshiBot\kalshi_prod_write.pem"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DENYLIST = {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"}

# W2 residual series (n>=2 per W2 table) plus important expansions for v9
# v9 targets T-35d to T-7d horizon on same sports as v1's residual
V9_CANDIDATE_SERIES = [
    # Core W2 residual (n>=2 in W2 data, clean or fragile)
    "KXNBAWINS",
    "KXMLBWINS",
    "KXNCAAFPLAYOFF",
    "KXNFLGAME",
    # Specific team-KXMLBWINS (Kalshi uses team-specific sub-series)
    "KXMLBWINS-NYY", "KXMLBWINS-LAD", "KXMLBWINS-BOS", "KXMLBWINS-ATL",
    "KXMLBWINS-HOU", "KXMLBWINS-CHC", "KXMLBWINS-MIN", "KXMLBWINS-PHI",
    "KXMLBWINS-SEA", "KXMLBWINS-SD", "KXMLBWINS-TB", "KXMLBWINS-KC",
    "KXMLBWINS-STL", "KXMLBWINS-MIL", "KXMLBWINS-WSH", "KXMLBWINS-SF",
    "KXMLBWINS-DET", "KXMLBWINS-CLE", "KXMLBWINS-CWS", "KXMLBWINS-LAA",
    "KXMLBWINS-CIN", "KXMLBWINS-BAL", "KXMLBWINS-TEX", "KXMLBWINS-NYM",
    "KXMLBWINS-AZ",
    # NHL (v9 addition - same structure as KXMLBWINS, high ticket count)
    "KXNHLWINS",
    # Soccer / international
    "KXWCGAME", "KXUCLROUND", "KXUCLADVANCE",
    # Tennis / fights
    "KXATPGRANDSLAM", "KXBOXING", "KXUFCFIGHT",
    # v1-only series from W2
    "KXNFLGAME", "KXATPGRANDSLAM", "KXBALLONDOR", "KXBOXING",
    "KXLEADERNBAAST", "KXMLBALCY", "KXMLBSTATCOUNT",
    "KXNCAAFGAME", "KXNFLTRADE", "KXNHLCENTRAL", "KXNHLMETROPOLITAN",
    "KXSTARTCLEBROWNS", "KXSWIFTATTEND", "KXWNBAROTY",
    # PGA (from v9 prospective sample)
    "KXPGAUSO",
    # NBA specific
    "KXNBAPLAYOFF",
]

# Deduplicate
V9_CANDIDATE_SERIES = list(dict.fromkeys(V9_CANDIDATE_SERIES))

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
    }

def api_get(client, private_key, endpoint, params=None):
    path = "/trade-api/v2" + endpoint
    headers = sign_request(private_key, KEY_ID, "GET", path)
    t0 = time.time()
    r = client.get(BASE_URL + endpoint, headers=headers, params=params, timeout=20.0)
    latency_ms = int((time.time() - t0) * 1000)
    return r, latency_ms

V1_BAND = (0.70, 0.95)
AIA_BAND_LOWER = (0.20, 0.45)
AIA_BAND_UPPER = (0.55, 0.80)

def get_mid(m):
    yes_bid = float(m.get("yes_bid_dollars") or 0)
    yes_ask = float(m.get("yes_ask_dollars") or 0)
    no_bid = float(m.get("no_bid_dollars") or 0)
    last_p = float(m.get("last_price_dollars") or 0)
    if yes_bid > 0 and yes_ask > 0:
        return (yes_bid + yes_ask) / 2.0
    if yes_bid > 0 and no_bid > 0:
        yes_ask_derived = 1.0 - no_bid
        return (yes_bid + yes_ask_derived) / 2.0
    return last_p  # fallback (not ideal but available)

def main():
    private_key = load_key(PEM_PATH)
    oos_start = "2026-02-01T00:00:00Z"
    oos_end   = "2026-05-26T23:59:59Z"

    series_data = {}  # series -> {n_total, n_v1, mids_at_snapshot}

    with httpx.Client(timeout=20.0) as client:
        for series in V9_CANDIDATE_SERIES:
            if series in DENYLIST:
                continue
            markets = []
            cursor = None
            page = 0
            while True:
                params = {
                    "limit": 200,
                    "status": "closed",
                    "close_time_min": oos_start,
                    "close_time_max": oos_end,
                    "series_ticker": series,
                }
                if cursor:
                    params["cursor"] = cursor
                r, lat = api_get(client, private_key, "/markets", params)
                if r.status_code == 429:
                    print(f"  [429] {series}, backing off 5s...")
                    time.sleep(5)
                    continue
                if r.status_code != 200:
                    print(f"  [{r.status_code}] {series}: {r.text[:100]}")
                    break
                data = r.json()
                batch = data.get("markets", [])
                markets.extend(batch)
                cursor = data.get("cursor")
                page += 1
                if not cursor or not batch:
                    break
                if page >= 5:
                    break
                time.sleep(0.15)

            # Also try: the Kalshi series_ticker field may differ from the series name
            # Some team-level series may be under a root KXMLBWINS series
            n_total = len(markets)
            n_v1 = 0
            n_aia = 0
            mids = []
            close_times = []
            for m in markets:
                mid = get_mid(m)
                mids.append(mid)
                ct = m.get("close_time", "")
                close_times.append(ct)
                if V1_BAND[0] <= mid <= V1_BAND[1]:
                    n_v1 += 1
                if AIA_BAND_LOWER[0] <= mid <= AIA_BAND_LOWER[1] or AIA_BAND_UPPER[0] <= mid <= AIA_BAND_UPPER[1]:
                    n_aia += 1

            if n_total > 0:
                series_data[series] = {
                    "n_total": n_total,
                    "n_v1_eligible": n_v1,
                    "n_aia_band": n_aia,
                    "mean_mid": sum(mids)/len(mids) if mids else 0,
                    "sample_close_times": sorted(close_times)[:3],
                }
                print(f"  {series:35s}  n={n_total:4d}  v1={n_v1:3d}  aia={n_aia:3d}")
            else:
                print(f"  {series:35s}  n=   0")
            time.sleep(0.2)

    print("\n\nSUMMARY TABLE:")
    total_n = sum(v["n_total"] for v in series_data.values())
    total_v1 = sum(v["n_v1_eligible"] for v in series_data.values())
    total_aia = sum(v["n_aia_band"] for v in series_data.values())
    for s, v in sorted(series_data.items(), key=lambda x: -x[1]["n_v1_eligible"]):
        print(f"  {s:35s}  n_total={v['n_total']:4d}  n_v1={v['n_v1_eligible']:3d}  n_aia={v['n_aia_band']:3d}  mean_mid={v['mean_mid']:.3f}")
    print(f"\n  TOTAL across all scanned series:  n_total={total_n}  n_v1={total_v1}  n_aia={total_aia}")

    # Save
    import json
    out = {
        "run_time": datetime.now(timezone.utc).isoformat(),
        "oos_window": f"{oos_start} to {oos_end}",
        "series_data": series_data,
        "totals": {"n_total": total_n, "n_v1_eligible": total_v1, "n_aia_band": total_aia}
    }
    with open(r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v9\sports_oos_probe.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved to data/v9/sports_oos_probe.json")

if __name__ == "__main__":
    import os
    os.makedirs(r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v9", exist_ok=True)
    main()
