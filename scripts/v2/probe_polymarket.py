"""Probe Polymarket's public Gamma API for market data.

Confirms:
- Endpoints are public, no auth
- Response shape
- Search capability for matching against Kalshi tickers

Writes raw samples to data/v2/polymarket_samples.json.
No order placement. No wallet setup. Read-only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "v2"
DATA_DIR.mkdir(parents=True, exist_ok=True)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"


def get(url: str, params: dict | None = None) -> Any:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(url, params=params or {})
        r.raise_for_status()
        return r.json()


def probe_gamma_markets() -> list[dict]:
    """Fetch a sample of active markets from Gamma."""
    print(f"GET {GAMMA_BASE}/markets")
    data = get(f"{GAMMA_BASE}/markets", params={"limit": 5, "active": "true"})
    if isinstance(data, list):
        markets = data
    else:
        markets = data.get("data", [])
    print(f"  -> got {len(markets)} markets")
    if markets:
        sample = markets[0]
        keys = sorted(sample.keys())
        print(f"  -> field keys ({len(keys)}): {keys[:15]} ...")
    return markets


def probe_gamma_events() -> list[dict]:
    """Fetch events (groups of related markets) from Gamma."""
    print(f"GET {GAMMA_BASE}/events")
    data = get(f"{GAMMA_BASE}/events", params={"limit": 5, "active": "true"})
    if isinstance(data, list):
        events = data
    else:
        events = data.get("data", [])
    print(f"  -> got {len(events)} events")
    return events


def probe_search(query: str) -> dict:
    """Search the Polymarket Gamma API for markets matching a free-text query."""
    print(f"GET {GAMMA_BASE}/public-search  q={query!r}")
    try:
        data = get(f"{GAMMA_BASE}/public-search", params={"q": query, "limit_per_type": 5})
        events = data.get("events", []) if isinstance(data, dict) else []
        print(f"  -> {len(events)} events matched")
        return data
    except httpx.HTTPStatusError as e:
        print(f"  -> HTTP {e.response.status_code}: {e.response.text[:200]}")
        return {"error": str(e), "status": e.response.status_code}


def probe_clob_price(token_id: str) -> dict:
    """Try fetching a price from the CLOB."""
    print(f"GET {CLOB_BASE}/price  token_id={token_id}")
    try:
        return get(f"{CLOB_BASE}/price", params={"token_id": token_id, "side": "BUY"})
    except httpx.HTTPStatusError as e:
        return {"error": str(e), "status": e.response.status_code}


def main() -> int:
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}

    # 1. Markets list
    try:
        markets = probe_gamma_markets()
        out["gamma_markets_sample"] = markets[:2]
        out["gamma_markets_count_returned"] = len(markets)
    except Exception as e:
        print(f"markets probe failed: {e}")
        out["gamma_markets_error"] = str(e)
        markets = []

    # 2. Events list
    try:
        events = probe_gamma_events()
        out["gamma_events_sample"] = events[:2]
    except Exception as e:
        print(f"events probe failed: {e}")
        out["gamma_events_error"] = str(e)

    # 3. Search probes for 5 Kalshi-derived queries
    queries = [
        ("NFL Detroit Lions 8 wins 2027", "KXNFLWINS-27DET-8"),
        ("Yankees AL East 2025 division", "KXMLBALEAST-25-NYY"),
        ("Bundesliga 2025 Bayern Munich champion", "KXBUNDESLIGA-25-BM"),
        ("Boxing Tyson Fury Anthony Joshua April 2026", "KXBOXING-26APR11TFURAMAK-TFUR"),
        ("Ballon d'Or 2025 Yamal", "KXBALLONDOR-25-LYAM"),
    ]
    search_results = []
    for query, kalshi_ticker in queries:
        print(f"\n--- matching probe for Kalshi {kalshi_ticker} ---")
        res = probe_search(query)
        events = res.get("events", []) if isinstance(res, dict) else []
        candidates = [
            {
                "slug": e.get("slug"),
                "title": e.get("title"),
                "active": e.get("active"),
                "endDate": e.get("endDate"),
            }
            for e in events[:5]
        ]
        search_results.append(
            {"kalshi_ticker": kalshi_ticker, "query": query, "n_results": len(events), "top": candidates}
        )
    out["search_probes"] = search_results

    # 4. Try price fetch from CLOB using a token id from the first market
    if markets:
        sample = markets[0]
        try:
            tokens = sample.get("clobTokenIds")
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            if tokens:
                price = probe_clob_price(tokens[0])
                out["clob_price_sample"] = {"token_id": tokens[0], "response": price}
        except Exception as e:
            print(f"clob price probe failed: {e}")
            out["clob_price_error"] = str(e)

    out_path = DATA_DIR / "polymarket_samples.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
