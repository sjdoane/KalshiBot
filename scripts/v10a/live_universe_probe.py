"""V10-A round 15b: live universe probe for candidate maker-edge prefixes.

Queries the live Kalshi API for currently-open markets across all 6
candidate cells (Media, Tennis WTA/ATP, Crypto BTCD/BTC/ETHD, Other) and
reports:

- n_open_markets per prefix
- mean_spread (yes_ask - yes_bid)
- mean_depth (sum of orderbook levels)
- median time-to-close in days

Confirms whether the Becker-historical edges are tradeable in the live
universe TODAY (the Becker data is 6 months old; new categories may have
been launched or retired).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")

KEY_ID = os.environ["KALSHI_API_KEY_ID"]
PEM_PATH = Path(os.environ["KALSHI_PRIVATE_KEY_PATH"])
BASE = "https://external-api.kalshi.com/trade-api/v2"

# Load private key once
with open(PEM_PATH, "rb") as fh:
    PRIVATE_KEY = serialization.load_pem_private_key(fh.read(), password=None)


def sign(timestamp_ms: str, method: str, path: str) -> str:
    """Kalshi RSA-PSS signing per https://trading-api.readme.io/."""
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = PRIVATE_KEY.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def headers(method: str, path: str) -> dict:
    ts = str(int(time.time() * 1000))
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": sign(ts, method, path),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


def get(path: str, params: dict | None = None) -> dict:
    full_path = "/trade-api/v2" + path
    url = "https://external-api.kalshi.com" + full_path
    r = httpx.get(url, headers=headers("GET", full_path), params=params or {}, timeout=30.0)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return r.json()


def iter_open_markets_with_prefix(prefix: str, limit_total: int = 5000):
    """Paginate /markets?status=open and yield those whose event_ticker starts with prefix."""
    cursor = None
    fetched = 0
    while True:
        params = {"status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = get("/markets", params=params)
        markets = data.get("markets", [])
        if not markets:
            break
        for m in markets:
            et = (m.get("event_ticker") or "").upper()
            if et.startswith(prefix):
                yield m
        fetched += len(markets)
        cursor = data.get("cursor")
        if not cursor or fetched >= limit_total:
            break


CANDIDATES = [
    # Media maker midprice candidates (from agent's category-level analysis)
    ("KXTSAW", [0.40, 0.60], "Media: TSA passenger counts"),
    ("KXVANCEMENTION", [0.40, 0.60], "Media: Vance mentions"),
    ("KXAPRPOTUS", [0.40, 0.60], "Media: POTUS approval"),
    ("KX538APPROVE", [0.40, 0.60], "Media: 538 approval polls"),
    ("KXEARNINGSMENTION", [0.40, 0.60], "Media: Earnings mentions"),
    ("KXSNFMENTION", [0.40, 0.60], "Media: SNF mentions"),
    ("KXSNLMENTION", [0.40, 0.60], "Media: SNL mentions"),
    ("KXHEADLINE", [0.40, 0.60], "Media: Headlines"),
    # Tennis (orchestrator prefix-level finding)
    ("KXWTAMATCH", [0.30, 0.70], "Sports: WTA tennis"),
    ("KXATPMATCH", [0.30, 0.70], "Sports: ATP tennis"),
    # Crypto (orchestrator finding)
    ("KXBTCD", [0.30, 0.70], "Crypto: Bitcoin daily"),
    ("KXBTC", [0.30, 0.70], "Crypto: Bitcoin range"),
    ("KXETHD", [0.30, 0.70], "Crypto: Ethereum daily"),
    # Other diversified (agent finding)
    ("KXELONTWEETS", [0.60, 0.80], "Other: Elon tweets"),
    ("KXWHVISIT", [0.60, 0.80], "Other: White House visits"),
    # Sanity check: v1's regime
    ("KXNFLGAME", [0.30, 0.70], "Sanity: NFL games (v1 trades nearby)"),
    ("KXMLBGAME", [0.30, 0.70], "Sanity: MLB games"),
]


def summarize_markets(markets: list[dict], px_lo: float, px_hi: float) -> dict:
    """Return market depth + spread summary for markets with mid in band."""
    in_band = []
    for m in markets:
        yes_bid = m.get("yes_bid")
        yes_ask = m.get("yes_ask")
        if yes_bid is None or yes_ask is None:
            continue
        # yes_bid and yes_ask are in CENTS (per Kalshi v2 API)
        bid_d = yes_bid / 100.0
        ask_d = yes_ask / 100.0
        mid = (bid_d + ask_d) / 2.0
        if px_lo <= mid <= px_hi:
            spread = ask_d - bid_d
            in_band.append({
                "ticker": m.get("ticker"),
                "event_ticker": m.get("event_ticker"),
                "yes_bid": bid_d,
                "yes_ask": ask_d,
                "mid": mid,
                "spread": spread,
                "volume": m.get("volume", 0),
                "close_time": m.get("close_time"),
                "liquidity": m.get("liquidity", 0),
            })
    if not in_band:
        return {"n_in_band": 0, "n_total_open": len(markets)}
    spreads = [m["spread"] for m in in_band]
    mids = [m["mid"] for m in in_band]
    vols = [m["volume"] for m in in_band]
    liq = [m["liquidity"] for m in in_band]
    # time to close
    now = datetime.now(timezone.utc)
    days_to_close = []
    for m in in_band:
        ct = m.get("close_time")
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                days_to_close.append((dt - now).total_seconds() / 86400.0)
            except Exception:
                pass
    return {
        "n_total_open": len(markets),
        "n_in_band": len(in_band),
        "mean_spread_cents": sum(spreads) / len(spreads) * 100,
        "median_spread_cents": sorted(spreads)[len(spreads) // 2] * 100,
        "mean_mid": sum(mids) / len(mids),
        "mean_volume": sum(vols) / len(vols),
        "mean_liquidity_cents": sum(liq) / len(liq),
        "n_zero_spread": sum(1 for s in spreads if s == 0),
        "median_days_to_close": sorted(days_to_close)[len(days_to_close) // 2] if days_to_close else None,
        "min_days_to_close": min(days_to_close) if days_to_close else None,
        "max_days_to_close": max(days_to_close) if days_to_close else None,
        "sample_tickers": [m["ticker"] for m in in_band[:5]],
    }


def main() -> None:
    print(f"Live universe probe @ {datetime.now(timezone.utc).isoformat()}")
    print("=" * 100)
    print(f"{'prefix':22} {'band':>14}  {'open':>5} {'inBand':>7} {'spread_c':>8} {'mid':>5} {'volMean':>8} {'daysToClose':>12}  description")
    print("-" * 130)
    summary = {}
    for prefix, (lo, hi), desc in CANDIDATES:
        try:
            markets = list(iter_open_markets_with_prefix(prefix, limit_total=10000))
        except Exception as e:
            print(f"{prefix:22}  ERROR: {e}")
            continue
        stats = summarize_markets(markets, lo, hi)
        summary[prefix] = {"px_band": [lo, hi], "stats": stats, "description": desc}
        band_str = f"[{lo:.2f},{hi:.2f}]"
        n_total = stats.get("n_total_open", 0)
        n_in = stats.get("n_in_band", 0)
        if n_in == 0:
            print(f"{prefix:22} {band_str:>14}  {n_total:>5} {n_in:>7}                                          {desc}")
        else:
            ms = stats.get("median_spread_cents", 0)
            mid = stats.get("mean_mid", 0)
            vol = stats.get("mean_volume", 0)
            mdc = stats.get("median_days_to_close")
            mdc_str = f"{mdc:.1f}" if mdc is not None else "n/a"
            print(f"{prefix:22} {band_str:>14}  {n_total:>5} {n_in:>7} {ms:>8.1f} {mid:>5.3f} {vol:>8.0f} {mdc_str:>12}  {desc}")

    out = REPO / "research" / "v10a" / "09-live-universe-probe.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nFull JSON saved to {out}")

    # Overall assessment
    n_tradeable = sum(1 for k, v in summary.items() if v["stats"].get("n_in_band", 0) >= 5)
    print(f"\n{n_tradeable} of {len(CANDIDATES)} prefixes have >= 5 open markets in the target band TODAY")


if __name__ == "__main__":
    main()
