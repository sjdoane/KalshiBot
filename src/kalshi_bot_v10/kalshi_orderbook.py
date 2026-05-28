"""Kalshi orderbook mid snapshot for V10-B.

Per B2 Section (F4 phantom prevention): the orderbook mid is fetched at
forecast time from /markets/{ticker}/orderbook. Using live bid/ask avoids
the v7-B stale-trade-print phantom.

Auth pattern copied from src/kalshi_bot/data/kalshi_client.py (read-only).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
_TIMEOUT = 20  # seconds


def _build_auth_headers(method: str, path: str) -> dict[str, str]:
    """Build Kalshi RSA-PSS auth headers for one request.

    Imports from the existing kalshi_bot auth module to avoid duplication.
    Falls back to no-auth if the module is unavailable (smoke test dry-run).
    """
    try:
        import sys
        project_root = Path(__file__).resolve().parents[3]
        if str(project_root / "src") not in sys.path:
            sys.path.insert(0, str(project_root / "src"))

        from kalshi_bot.data.auth import build_headers, load_private_key

        key_id = os.environ.get("KALSHI_API_KEY_ID", "")
        pem_path_str = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if not key_id or not pem_path_str:
            return {}
        pem_path = Path(pem_path_str)
        private_key = load_private_key(pem_path)
        return build_headers(private_key, key_id, method, path)
    except Exception:
        return {}


def _get_orderbook_raw(ticker: str) -> dict[str, Any]:
    """Fetch raw orderbook from Kalshi API."""
    path = f"/trade-api/v2/markets/{ticker}/orderbook"
    headers = _build_auth_headers("GET", path)
    url = _KALSHI_BASE + f"/markets/{ticker}/orderbook"
    resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_orderbook_mid(ticker: str) -> dict[str, Any]:
    """Fetch live orderbook mid for a Kalshi market ticker.

    Returns dict:
        ticker:           str
        yes_bid:          float or None
        yes_ask:          float or None
        mid:              float or None
        ts:               datetime (UTC, fetch time)
        is_parity_derived: bool (True if yes_ask derived from 1 - best_no_bid)
        error:            str or None

    If both yes_bid and yes_ask are present: mid = (yes_bid + yes_ask) / 2.
    If yes_ask absent: derive from 1.0 - max(no_dollars prices); is_parity_derived = True.
    If orderbook is empty (no bids on either side): mid = None; log as empty book.
    """
    ts = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "ticker": ticker,
        "yes_bid": None,
        "yes_ask": None,
        "mid": None,
        "ts": ts,
        "is_parity_derived": False,
        "error": None,
    }

    try:
        raw = _get_orderbook_raw(ticker)
    except requests.HTTPError as exc:
        result["error"] = f"HTTP {exc.response.status_code}: {exc}"
        return result
    except requests.RequestException as exc:
        result["error"] = f"Request error: {exc}"
        return result

    # Actual response shape: {"orderbook_fp": {"yes_dollars": [[price_str, qty_str], ...], "no_dollars": [...]}}
    # Each entry is [price_in_dollars_str, quantity_str], sorted ascending so MAX is the last entry
    ob = raw.get("orderbook_fp", raw.get("orderbook", raw))
    yes_side = ob.get("yes_dollars", ob.get("yes", [])) or []
    no_side = ob.get("no_dollars", ob.get("no", [])) or []

    def _best_price(side: list) -> float | None:
        if not side:
            return None
        try:
            return max(float(entry[0]) for entry in side if entry and len(entry) >= 1)
        except (ValueError, TypeError, IndexError):
            return None

    # Best yes bid: highest price on yes_dollars side
    yes_bid = _best_price(yes_side)
    if yes_bid is not None and yes_bid <= 0:
        yes_bid = None

    # Best yes ask: derived via parity from highest no_dollars bid
    yes_ask: float | None = None
    is_parity_derived = False
    best_no = _best_price(no_side)
    if best_no is not None and best_no > 0:
        yes_ask = 1.0 - best_no
        is_parity_derived = True

    if yes_bid is None and yes_ask is None:
        result["error"] = "empty_orderbook"
        return result

    # Compute mid
    if yes_bid is not None and yes_ask is not None:
        mid = (yes_bid + yes_ask) / 2.0
    elif yes_bid is not None:
        mid = yes_bid
    else:
        mid = yes_ask  # type: ignore[assignment]

    result.update({
        "yes_bid": round(yes_bid, 4) if yes_bid is not None else None,
        "yes_ask": round(yes_ask, 4) if yes_ask is not None else None,
        "mid": round(mid, 4),
        "is_parity_derived": is_parity_derived,
    })
    return result
