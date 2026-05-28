"""Round 15c Track 2E: Tavily news lead-lag probe (exploratory).

Hypothesis: news mentions of teams/players in the 2-6 hours before
close on KXMLBGAME or KXNFLGAME markets correlate with subsequent
Kalshi price moves. If a strong correlation exists, news could feed a
fade or follow signal.

This script is a FEASIBILITY probe, not a tradeable signal.

Method (exploratory, n=20):
1. Pull currently-open KXMLBGAME markets closing in the next 24 hours.
2. For each market, extract the two team names from the title.
3. Tavily search for news about that matchup within the last 12 hours.
4. Snapshot the current Kalshi YES bid mid.
5. Save (timestamp, ticker, team_a, team_b, kalshi_mid, n_news_hits,
   sample_headlines) to data/v10a/news_probe_snapshot.json.

A follow-up cycle could re-pull each ticker's Kalshi mid hours later
and compute the post-snapshot price move per news bucket. We do NOT
do that follow-up here; this is a feasibility check.

NOTE: Tavily free tier is 1000 searches/month. We cap at 30 calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
load_dotenv(REPO / ".env")

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient

TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
OUT_JSON = REPO / "data" / "v10a" / "news_probe_snapshot.json"
MAX_TAVILY_CALLS = 30


def tavily_search(query: str, max_results: int = 5) -> dict:
    """Hit Tavily search API. Returns parsed JSON. Raises on error."""
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    r = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "days": 1,  # within last day
        },
        timeout=20.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Tavily {r.status_code}: {r.text[:200]}")
    return r.json()


def parse_orderbook_mid(payload: dict) -> float | None:
    ob = payload.get("orderbook_fp", {}) or {}
    yes_levels = ob.get("yes_dollars", []) or []
    no_levels = ob.get("no_dollars", []) or []
    if not yes_levels or not no_levels:
        return None
    yes_bid = max(float(p) for p, _ in yes_levels)
    no_bid = max(float(p) for p, _ in no_levels)
    yes_ask = 1.0 - no_bid
    return (yes_bid + yes_ask) / 2.0


def extract_teams_from_title(title: str) -> tuple[str | None, str | None]:
    """Title like 'Will the Kansas City win the game against Detroit?'
    or 'Will MLB result Yankees win over Red Sox?'. Returns (a, b) or
    (None, None). Best-effort parsing."""
    # Common patterns
    m = re.search(r"(?:Will|will)\s+(?:the\s+)?([A-Z][\w\s]+?)\s+(?:win|beat|defeat)\s+(?:the\s+)?([A-Z][\w\s]+?)(?:\?|$)", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"([A-Z][\w\s]+?)\s+vs\.?\s+([A-Z][\w\s]+?)(?:\?|$)", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def main():
    if not TAVILY_KEY:
        print("ERROR: TAVILY_API_KEY not set in .env", file=sys.stderr)
        return 1

    settings = load_settings()
    tavily_calls = 0
    snapshots = []
    now = datetime.now(UTC)
    cutoff = now + timedelta(hours=168)  # next 7 days

    with KalshiClient(settings) as client:
        # Pull KXMLBGAME open markets closing in next 24h
        markets = list(client.paginate(
            "/markets", item_key="markets", limit=200,
            status="open", series_ticker="KXMLBGAME", max_pages=5,
        ))
        print(f"Found {len(markets)} open KXMLBGAME markets")

        # Filter to ones closing in next 24h, mid in [0.30, 0.95]
        candidates = []
        for m in markets:
            ct = m.get("close_time")
            if not ct:
                continue
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt <= now or dt > cutoff:
                continue
            candidates.append(m)
        print(f"  closing in next 24h: {len(candidates)}")

        for m in candidates[:20]:
            if tavily_calls >= MAX_TAVILY_CALLS:
                print("Reached MAX_TAVILY_CALLS; stopping")
                break
            ticker = m.get("ticker", "")
            title = m.get("title", "") or m.get("subtitle", "")
            yes_sub = m.get("yes_sub_title", "")
            team_a, team_b = extract_teams_from_title(title or yes_sub)

            try:
                ob = client.get(f"/markets/{ticker}/orderbook")
                mid = parse_orderbook_mid(ob)
            except Exception:
                mid = None

            news_hits = 0
            headlines = []
            if team_a and team_b:
                q = f'"{team_a}" "{team_b}" MLB injury lineup news'
                try:
                    res = tavily_search(q, max_results=5)
                    tavily_calls += 1
                    hits = res.get("results", []) or []
                    news_hits = len(hits)
                    headlines = [h.get("title", "")[:120] for h in hits[:3]]
                except Exception as exc:
                    print(f"  tavily fail on {ticker}: {exc}", file=sys.stderr)
            time.sleep(0.5)  # rate-limit politeness

            snap = {
                "snapshot_ts_utc": now.isoformat(),
                "ticker": ticker,
                "title": title,
                "team_a": team_a, "team_b": team_b,
                "yes_mid": mid,
                "close_time": m.get("close_time"),
                "n_news_hits_last_day": news_hits,
                "sample_headlines": headlines,
            }
            snapshots.append(snap)
            print(
                f"  {ticker}: mid={mid}, teams=({team_a}, {team_b}), "
                f"news={news_hits}"
            )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "snapshot_ts_utc": now.isoformat(),
        "tavily_calls_used": tavily_calls,
        "n_snapshots": len(snapshots),
        "snapshots": snapshots,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved {len(snapshots)} snapshots to {OUT_JSON}")
    print(f"Tavily calls used: {tavily_calls}")


if __name__ == "__main__":
    sys.exit(main() or 0)
