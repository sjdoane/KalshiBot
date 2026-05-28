"""Polymarket cross-validation helpers.

Pulls resolved Polymarket markets via the public Gamma REST API
(`https://gamma-api.polymarket.com`) and converts to a schema that can
be cross-checked against Kalshi's compression-slope finding.

Per Le 2026 ([le-2026-crowd-wisdom.md](research/literature/le-2026-crowd-wisdom.md)
"Trade-size scale effect"), the Kalshi compression effect does NOT
replicate on Polymarket. If our maker-quote thesis depends on the
Kalshi-specific microstructure, Polymarket prices should show LOWER
or no compression on the same underlying events.

Polymarket is read-only here. No orders, no auth required for the
public endpoints used. This module is a Phase 4+ enhancement; not used
in Phase 2 / Phase 3 paths.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger(__name__)

POLYMARKET_BASE = "https://gamma-api.polymarket.com"


@dataclass
class PolymarketMarket:
    """Minimum fields for cross-validation against Kalshi."""

    id: str
    slug: str
    question: str
    end_date_iso: str
    closed: bool
    resolved_outcome: str | None  # "Yes", "No", or None if unresolved
    last_trade_price: float | None
    volume_total_usd: float


def fetch_resolved_markets(
    category: str | None = None,
    limit: int = 100,
) -> list[PolymarketMarket]:
    """Pull resolved Polymarket markets via the public Gamma REST API.

    Args:
        category: optional category filter (e.g., "Sports", "Politics").
        limit: pagination size per page.

    Returns:
        List of PolymarketMarket records.

    Network requests use a 30s timeout. No retries on transient failure
    in this minimal implementation; for production cross-validation
    pulls, wrap with tenacity.
    """
    params: dict[str, str | int | bool] = {
        "closed": True,
        "limit": limit,
        "order": "endDate",
        "ascending": False,
    }
    if category:
        params["category"] = category

    results: list[PolymarketMarket] = []
    with httpx.Client(timeout=30.0) as client:
        cursor = 0
        while True:
            params["offset"] = cursor
            resp = client.get(f"{POLYMARKET_BASE}/markets", params=params)
            if resp.status_code != 200:
                log.warning("polymarket_fetch_failed",
                            status=resp.status_code, body=resp.text[:200])
                break
            page = resp.json()
            if not isinstance(page, list) or not page:
                break
            for m in page:
                try:
                    results.append(PolymarketMarket(
                        id=str(m.get("id", "")),
                        slug=str(m.get("slug", "")),
                        question=str(m.get("question", "")),
                        end_date_iso=str(m.get("endDate", "")),
                        closed=bool(m.get("closed", False)),
                        resolved_outcome=m.get("outcome") or None,
                        last_trade_price=(
                            float(m["lastTradePrice"]) if m.get("lastTradePrice") else None
                        ),
                        volume_total_usd=float(m.get("volumeNum", 0) or 0),
                    ))
                except (TypeError, ValueError):
                    continue
            cursor += len(page)
            if cursor >= limit * 5:  # Cap pagination to avoid runaway
                break
    log.info("polymarket_fetch_done", n=len(results))
    return results


def match_kalshi_to_polymarket(
    kalshi_question: str,
    polymarket_markets: list[PolymarketMarket],
    *,
    min_word_overlap: int = 3,
) -> PolymarketMarket | None:
    """Naive question-text matcher. For each Kalshi market question,
    find the best-matching Polymarket question by word overlap.

    Returns the best match if overlap >= min_word_overlap, else None.

    This is intentionally simple. For Phase 4+ cross-validation work,
    consider embedding-based matching or manual curation of (Kalshi,
    Polymarket) pairs.
    """
    if not kalshi_question:
        return None
    kalshi_words = set(kalshi_question.lower().split())
    kalshi_words.discard("")
    best: tuple[int, PolymarketMarket] | None = None
    for pm in polymarket_markets:
        pm_words = set(pm.question.lower().split())
        overlap = len(kalshi_words & pm_words)
        if overlap >= min_word_overlap and (best is None or overlap > best[0]):
            best = (overlap, pm)
    return best[1] if best else None
