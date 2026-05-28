"""Tavily Search API wrapper with V10-B exclusion filter.

Per B3 Revision 2: every query has a mandatory exclusion suffix that strips
prediction market and sportsbook content from search results before they
are passed to the LLM forecasters. This prevents backdoor anchoring via
retrieved Kalshi/Polymarket/sportsbook price information.

Usage:
    from kalshi_bot_v10.tavily_search import search

    snippets = search("NYY vs KC tonight total runs latest news")
    # Returns list of dicts: [{title, url, snippet, date}, ...]
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_TIMEOUT = 30  # seconds

# B3 Revision 2: mandatory exclusion suffix applied to every query.
# Removes: prediction markets, sportsbooks, betting odds.
_EXCLUSION_SUFFIX = (
    " -site:kalshi.com -site:polymarket.com -site:predictit.org"
    " -site:manifold.markets -site:metaculus.com"
    " -betting -\"live odds\" -sportsbook"
    " -DraftKings -FanDuel -BetMGM -Caesars -Pinnacle -Bovada"
    " -\"prediction market\" -odds"
)


def search(
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Run a Tavily search with the V10-B exclusion filter.

    Args:
        query: Natural-language search query derived from market title.
        max_results: Maximum number of snippets to return (default 5).

    Returns:
        List of snippet dicts, each with keys:
            title (str), url (str), snippet (str), date (str or None).
        Returns empty list if TAVILY_API_KEY is absent or on any error.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []

    filtered_query = query + _EXCLUSION_SUFFIX

    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": filtered_query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        resp = requests.post(
            _TAVILY_ENDPOINT,
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []
    except json.JSONDecodeError:
        return []

    results = data.get("results", [])
    snippets: list[dict[str, Any]] = []
    for r in results:
        snippets.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", r.get("snippet", "")),
            "date": r.get("published_date", None),
        })
    return snippets
