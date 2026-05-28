"""V4-D: probe alternative prediction-market venues for Track A second-opinion fallback.

Tests:
  1. ManifoldMarkets API live + coverage on a sample of v1's resting orders
  2. PredictIt public marketdata feed
  3. the-odds-api free tier (key-less probe to confirm endpoint shape)
  4. Polymarket US (apidocs.polymarketexchange.com) status check

Read-only, public, no auth. Polite throttle between calls.

Output: data/v4/multi_venue_probe.json
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"
DATA_V4.mkdir(parents=True, exist_ok=True)
OUTPUT = DATA_V4 / "multi_venue_probe.json"

# Sample of v1's currently-resting tickers, drawn from state.json at probe time.
# Each row: (kalshi_ticker, free_text_query_for_external_venue, league_hint)
V1_SAMPLE = [
    (
        "KXWCSQUAD-26ESP-BIGL",
        "2026 World Cup Spain squad Lamine",
        "Soccer-WC",
    ),
    (
        "KXSTARTINGQBWEEK1-W1-26SEP15-LV-KCOU",
        "Raiders starting QB week 1 2026 NFL Kenny Pickett",
        "NFL",
    ),
    (
        "KXWCGAME-26JUN23ENGGHA-ENG",
        "England Ghana 2026 World Cup group stage",
        "Soccer-WC",
    ),
    (
        "KXUFCFIGHT-26JUL11MCGHOL-HOL",
        "Holloway UFC July 2026",
        "UFC-MMA",
    ),
    (
        "KXWNBAWINS-26PHX-20",
        "Phoenix Mercury 2026 WNBA win total 20",
        "WNBA",
    ),
]


def fetch_json(client: httpx.Client, url: str, params: dict | None = None) -> Any:
    """Single polite GET. Returns parsed JSON on 200, dict with error otherwise."""
    try:
        r = client.get(url, params=params, timeout=15.0)
        return {
            "status_code": r.status_code,
            "ok": r.status_code == 200,
            "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500],
        }
    except Exception as exc:
        return {"status_code": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def probe_manifold(client: httpx.Client) -> dict:
    """Section 1: ManifoldMarkets API probe + coverage on v1 sample."""
    results: dict = {"venue": "ManifoldMarkets", "base_url": "https://api.manifold.markets/v0"}

    # 1a. health check
    health = fetch_json(client, "https://api.manifold.markets/v0/markets", params={"limit": 5})
    results["health"] = {
        "ok": health["ok"],
        "status_code": health["status_code"],
        "first_market_keys": list(health["body"][0].keys()) if health["ok"] and health["body"] else None,
    }
    time.sleep(0.5)

    # 1b. coverage probe on v1 sample
    matches: list = []
    for kalshi_ticker, query, league in V1_SAMPLE:
        time.sleep(0.7)  # polite
        r = fetch_json(
            client,
            "https://api.manifold.markets/v0/search-markets",
            params={"term": query, "limit": 5},
        )
        if not r["ok"]:
            matches.append({
                "kalshi_ticker": kalshi_ticker,
                "query": query,
                "league": league,
                "search_ok": False,
                "error": r.get("error") or r.get("status_code"),
                "candidates": [],
            })
            continue
        body = r["body"]
        cands = []
        for m in body if isinstance(body, list) else []:
            cands.append({
                "id": m.get("id"),
                "question": m.get("question"),
                "slug": m.get("slug"),
                "isResolved": m.get("isResolved"),
                "mechanism": m.get("mechanism"),
                "outcomeType": m.get("outcomeType"),
                "volume": m.get("volume"),
                "volume24Hours": m.get("volume24Hours"),
                "totalLiquidity": m.get("totalLiquidity"),
                "probability": m.get("probability"),
                "closeTime": m.get("closeTime"),
                "uniqueBettorCount": m.get("uniqueBettorCount"),
                "token": m.get("token"),  # mana vs cash
            })
        matches.append({
            "kalshi_ticker": kalshi_ticker,
            "query": query,
            "league": league,
            "search_ok": True,
            "n_returned": len(cands),
            "candidates": cands,
        })
    results["coverage_probe"] = matches

    # 1c. sample currently-open binary sports markets to see volume distribution
    time.sleep(0.7)
    open_sports = fetch_json(
        client,
        "https://api.manifold.markets/v0/search-markets",
        params={
            "term": "NBA",
            "filter": "open",
            "sort": "liquidity",
            "limit": 10,
            "topicSlug": "sports-default",
        },
    )
    if open_sports["ok"]:
        body = open_sports["body"]
        results["open_sports_top10_liquidity"] = [
            {
                "question": m.get("question"),
                "slug": m.get("slug"),
                "volume": m.get("volume"),
                "totalLiquidity": m.get("totalLiquidity"),
                "uniqueBettorCount": m.get("uniqueBettorCount"),
                "token": m.get("token"),
                "probability": m.get("probability"),
            }
            for m in (body if isinstance(body, list) else [])
        ]
    else:
        results["open_sports_top10_liquidity"] = {
            "error": open_sports.get("error") or open_sports.get("status_code")
        }

    return results


def probe_predictit(client: httpx.Client) -> dict:
    """Section 2: PredictIt public marketdata feed probe."""
    results: dict = {"venue": "PredictIt", "base_url": "https://www.predictit.org/api/marketdata"}
    time.sleep(0.7)

    all_md = fetch_json(client, "https://www.predictit.org/api/marketdata/all/")
    if not all_md["ok"]:
        results["error"] = all_md.get("error") or all_md.get("status_code")
        return results
    body = all_md["body"]
    if isinstance(body, dict) and "markets" in body:
        markets = body["markets"]
    else:
        markets = []
    results["n_markets"] = len(markets)

    # Categorize topics. PredictIt is heavily political.
    topic_keywords: dict[str, list[str]] = {
        "politics": ["president", "senate", "house", "congress", "election", "primary", "governor", "speaker"],
        "sports": ["nfl", "nba", "mlb", "nhl", "world cup", "playoff", "champion", "super bowl", "stanley"],
        "economy": ["fed", "rate", "gdp", "unemployment", "recession", "inflation"],
    }
    topic_counts: dict[str, int] = {k: 0 for k in topic_keywords}
    topic_counts["other"] = 0
    sample_per_topic: dict[str, list[str]] = {k: [] for k in topic_keywords}
    sample_per_topic["other"] = []
    for m in markets:
        name = (m.get("name") or "").lower()
        matched = False
        for topic, kws in topic_keywords.items():
            if any(kw in name for kw in kws):
                topic_counts[topic] += 1
                if len(sample_per_topic[topic]) < 5:
                    sample_per_topic[topic].append(m.get("name"))
                matched = True
                break
        if not matched:
            topic_counts["other"] += 1
            if len(sample_per_topic["other"]) < 5:
                sample_per_topic["other"].append(m.get("name"))
    results["topic_breakdown"] = topic_counts
    results["sample_per_topic"] = sample_per_topic

    # Confirm sports coverage near zero
    if markets:
        sample_market = markets[0]
        results["sample_market_schema"] = {
            "keys": list(sample_market.keys()),
            "contract_keys": list(sample_market.get("contracts", [{}])[0].keys()) if sample_market.get("contracts") else None,
        }
    return results


def probe_the_odds_api(client: httpx.Client) -> dict:
    """Section 3: the-odds-api free tier probe (no key)."""
    results: dict = {"venue": "the-odds-api", "base_url": "https://api.the-odds-api.com/v4"}

    # 3a. /sports endpoint requires key. Probe without one to confirm 401.
    time.sleep(0.7)
    no_key = fetch_json(client, "https://api.the-odds-api.com/v4/sports")
    results["no_key_call"] = {
        "status_code": no_key["status_code"],
        "ok": no_key["ok"],
        "body_preview": str(no_key.get("body"))[:300],
    }

    # 3b. fetch the public sports list (some endpoints work without key)
    # Note: as of 2025+ the API requires apiKey on every endpoint.

    # 3c. doc page check
    time.sleep(0.7)
    doc = fetch_json(client, "https://the-odds-api.com/liveapi/guides/v4/")
    if isinstance(doc.get("body"), str):
        results["doc_reachable"] = {"status_code": doc["status_code"], "preview": doc["body"][:300]}
    else:
        results["doc_reachable"] = {"status_code": doc["status_code"]}

    return results


def probe_polymarket_us(client: httpx.Client) -> dict:
    """Section 4: Polymarket US (apidocs.polymarketexchange.com) status."""
    results: dict = {"venue": "Polymarket US (QCEX)", "base_url": "https://apidocs.polymarketexchange.com"}

    time.sleep(0.7)
    # Public landing pages
    landing = fetch_json(client, "https://www.polymarketexchange.com/")
    results["landing_reachable"] = {"status_code": landing["status_code"], "ok": landing["ok"]}

    time.sleep(0.7)
    api_docs = fetch_json(client, "https://apidocs.polymarketexchange.com/")
    results["api_docs_reachable"] = {"status_code": api_docs["status_code"], "ok": api_docs["ok"]}

    # Try the introduction page
    time.sleep(0.7)
    intro = fetch_json(client, "https://apidocs.polymarketexchange.com/api-reference/introduction")
    results["intro_reachable"] = {"status_code": intro["status_code"]}

    return results


def main() -> None:
    out: dict = {}
    with httpx.Client(headers={"User-Agent": "kalshi-bot-v4-research/1.0 (read-only research probe)"}) as client:
        print("Probing ManifoldMarkets...")
        out["manifold"] = probe_manifold(client)
        time.sleep(1.0)

        print("Probing PredictIt...")
        out["predictit"] = probe_predictit(client)
        time.sleep(1.0)

        print("Probing the-odds-api...")
        out["the_odds_api"] = probe_the_odds_api(client)
        time.sleep(1.0)

        print("Probing Polymarket US...")
        out["polymarket_us"] = probe_polymarket_us(client)

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote probe results to {OUTPUT}")


if __name__ == "__main__":
    main()
