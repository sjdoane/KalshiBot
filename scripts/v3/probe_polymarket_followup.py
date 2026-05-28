"""Follow-up probes:
- Can prices-history return data older than 30d using startTs alone?
- Does data-api/trades support filtering by market (token id or condition id)?
- What does the orderbook live look like for a more liquid sports event?
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
    token_id = "52854035362787091895017612076763457120573181014952605669517525908999466984865"  # NYY 2026 WS
    condition_id = "0x3df7be753c8b6ebbddf31d6d63535c4b31c836cb25b1a73085508a271bc103db"  # NYY 2026 WS market

    out: dict = {"probed_at_unix": int(time.time()), "token_id": token_id, "condition_id": condition_id}

    with httpx.Client(timeout=30.0, headers=UA) as client:
        # 1. Try requesting wider window
        now = int(time.time())
        for label, days_back in [("90d", 90), ("180d", 180), ("365d", 365)]:
            start_ts = now - days_back * 86400
            r = client.get(
                "https://clob.polymarket.com/prices-history",
                params={"market": token_id, "startTs": start_ts, "endTs": now, "fidelity": 60},
            )
            body = r.json() if r.status_code == 200 else None
            history = body.get("history", []) if isinstance(body, dict) else []
            out[f"history_back_{label}"] = {
                "status": r.status_code,
                "n_points": len(history),
                "first_t": history[0]["t"] if history else None,
                "first_p": history[0]["p"] if history else None,
                "last_t": history[-1]["t"] if history else None,
                "last_p": history[-1]["p"] if history else None,
                "span_days": round((history[-1]["t"] - history[0]["t"]) / 86400, 2) if len(history) > 1 else None,
                "first_iso": time.strftime("%Y-%m-%d", time.gmtime(history[0]["t"])) if history else None,
            }
            time.sleep(0.3)

        # 2. data-api/trades with takerOnly, polymerket trade filter (try by user, asset, condition)
        for kw, params in [
            ("filter_market", {"market": condition_id, "limit": 5}),
            ("filter_user", {"user": "0xcbea30b026b3b0f6a73c96abac24a0a74b9c7777", "limit": 5}),
            ("filter_asset", {"asset": token_id, "limit": 5}),
            ("no_filter", {"limit": 5}),
        ]:
            r = client.get("https://data-api.polymarket.com/trades", params=params)
            body = r.json() if r.status_code == 200 else r.text[:300]
            out[f"trades_{kw}"] = {
                "status": r.status_code,
                "n": len(body) if isinstance(body, list) else None,
                "first_market_title": body[0].get("title") if isinstance(body, list) and body else None,
                "first_condition_id": body[0].get("conditionId") if isinstance(body, list) and body else None,
            }
            time.sleep(0.3)

        # 3. Order book on a more-active token: the YES side of NYY WS
        r = client.get("https://clob.polymarket.com/book", params={"token_id": token_id})
        book = r.json() if r.status_code == 200 else None
        if isinstance(book, dict):
            bids = sorted(book.get("bids", []), key=lambda b: float(b["price"]), reverse=True)
            asks = sorted(book.get("asks", []), key=lambda a: float(a["price"]))
            out["orderbook_top5"] = {
                "top5_bids": bids[:5],
                "top5_asks": asks[:5],
                "n_total_bids": len(bids),
                "n_total_asks": len(asks),
                "last_trade_price": book.get("last_trade_price"),
                "tick_size": book.get("tick_size"),
            }

    p = DATA_DIR / "feature_probe_polymarket_followup.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {p}")


if __name__ == "__main__":
    probe()
