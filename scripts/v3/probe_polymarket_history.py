"""Deeper probe of Polymarket price-history and order-book endpoints.

The first probe failed to extract a clobTokenId because body was truncated.
This probe goes directly via a known sports market token to test:
- Which interval values does /prices-history accept?
- Can we request an AS-OF timestamp window (startTs, endTs)?
- What's the history-depth ceiling?
- Is order book historical or live-only?
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "v3"

UA = {"User-Agent": "Mozilla/5.0 (Kalshi v3 research)"}


def probe() -> None:
    out: dict = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=30.0, headers=UA) as client:
        # Find a Polymarket NBA / NFL season-win-type market via gamma
        # Use the discovered "MLB World Series Champion 2026" event id 179312 directly
        r = client.get(
            "https://gamma-api.polymarket.com/events",
            params={"id": "179312"},
        )
        out["event_lookup_status"] = r.status_code
        ev_list = r.json()
        if isinstance(ev_list, list) and ev_list:
            event = ev_list[0]
        else:
            event = ev_list if isinstance(ev_list, dict) else {}
        markets = event.get("markets", [])
        out["event_title"] = event.get("title")
        out["n_markets_in_event"] = len(markets)
        # First market with clobTokenIds
        token_id = None
        market_meta = None
        for m in markets:
            ids = m.get("clobTokenIds")
            if isinstance(ids, str):
                try:
                    ids = json.loads(ids)
                except Exception:
                    ids = None
            if ids and len(ids) >= 1:
                token_id = ids[0]
                market_meta = {
                    "question": m.get("question"),
                    "endDate": m.get("endDate"),
                    "startDate": m.get("startDate"),
                    "tokens": ids,
                }
                break
        out["sample_token_market"] = market_meta
        out["sample_token_id"] = token_id

        if not token_id:
            out["fatal"] = "no clob token found in first event lookup"
            (DATA_DIR / "feature_probe_polymarket_history.json").write_text(
                json.dumps(out, indent=2, default=str), encoding="utf-8"
            )
            return

        # 1. Test each interval value documented in CLOB docs
        for interval in ["1m", "1h", "6h", "1d", "1w", "max"]:
            r = client.get(
                "https://clob.polymarket.com/prices-history",
                params={"market": token_id, "interval": interval, "fidelity": 60},
            )
            history = []
            try:
                body = r.json()
                history = body.get("history", []) if isinstance(body, dict) else []
            except Exception:
                pass
            entry: dict = {
                "status": r.status_code,
                "n_points": len(history),
                "first_point": history[0] if history else None,
                "last_point": history[-1] if history else None,
            }
            if history and isinstance(history[0], dict) and "t" in history[0]:
                t0 = history[0]["t"]
                t1 = history[-1]["t"]
                entry["span_days"] = round((t1 - t0) / 86400, 2)
                entry["start_iso"] = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t0))
                entry["end_iso"] = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t1))
            out[f"history_{interval}"] = entry
            time.sleep(0.3)

        # 2. Test AS-OF window query (T-35d sampling). Pick a recent past window.
        now = int(time.time())
        for offset_days, label in [(35, "T-35d"), (60, "T-60d"), (90, "T-90d")]:
            end_ts = now - offset_days * 86400
            start_ts = end_ts - 86400
            r = client.get(
                "https://clob.polymarket.com/prices-history",
                params={"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": 60},
            )
            body = r.json() if r.status_code == 200 else None
            history = body.get("history", []) if isinstance(body, dict) else []
            out[f"asof_window_{label}"] = {
                "status": r.status_code,
                "start_ts_query": start_ts,
                "end_ts_query": end_ts,
                "n_points": len(history),
                "first_point": history[0] if history else None,
                "last_point": history[-1] if history else None,
            }
            time.sleep(0.3)

        # 3. Order book (current)
        r = client.get(
            "https://clob.polymarket.com/book",
            params={"token_id": token_id},
        )
        book = r.json() if r.status_code == 200 else None
        if isinstance(book, dict):
            out["orderbook_current"] = {
                "status": r.status_code,
                "n_bids": len(book.get("bids", [])),
                "n_asks": len(book.get("asks", [])),
                "top_bid": book.get("bids", [])[0] if book.get("bids") else None,
                "top_ask": book.get("asks", [])[0] if book.get("asks") else None,
                "all_keys": list(book.keys()),
            }
        else:
            out["orderbook_current"] = {"status": r.status_code, "body": book}

        # 4. Midpoint and spread
        for path in ["midpoint", "spread", "price"]:
            r = client.get(
                f"https://clob.polymarket.com/{path}",
                params={"token_id": token_id, "side": "BUY"} if path == "price" else {"token_id": token_id},
            )
            out[f"endpoint_{path}"] = {
                "status": r.status_code,
                "body": r.json() if r.status_code == 200 else r.text[:200],
            }

        # 5. Historical trades via data API
        r = client.get(
            "https://data-api.polymarket.com/trades",
            params={"market": token_id, "limit": 5, "takerOnly": "false"},
        )
        out["data_api_trades"] = {
            "status": r.status_code,
            "body_sample": r.json() if r.status_code == 200 else r.text[:300],
        }

    p = DATA_DIR / "feature_probe_polymarket_history.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {p}")


if __name__ == "__main__":
    probe()
