"""V5-A1 supplementary: extended divergence sampling across all cached
the-odds-api live responses and Kalshi open markets.

Uses the cached the-odds-api responses (no new credits) and pulls Kalshi
open markets for each MATCH-class series. Produces a broader sample for
the signal-direction conclusion in 01-sportsbook-coverage.md.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import timedelta
from pathlib import Path

import pandas as pd

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient

ROOT = Path(__file__).resolve().parents[2]
LIVE_CACHE = ROOT / "data" / "v5" / "odds_api_live_cache"
OUT_JSON = ROOT / "data" / "v5" / "extended_divergence_probe.json"


def implied_from_decimal(d: float) -> float:
    if d <= 0:
        return 0.0
    return 1.0 / d


def devig(ps: list[float]) -> list[float]:
    s = sum(ps)
    if s <= 0:
        return [0.0] * len(ps)
    return [p / s for p in ps]


def canonicalize(name: str) -> str:
    """Normalize a name for fuzzy matching: strip accents, lower, alnum only."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", n.lower())


def load_book(sport_key: str, markets: str = "h2h", regions: str = "us") -> list[dict]:
    f = LIVE_CACHE / f"{sport_key}_{markets}_{regions}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("events", [])


def parse_kalshi_fight_ticker(ticker: str):
    """Match KX{UFCFIGHT,BOXING}-YYMonDD<NAMES>-WINNER tickers.

    Strategy: split on '-', last token is the winner side, the long
    chunk encodes date + two fighter abbrevs. We just keep the winner
    side and let canonicalize() match on the sportsbook outcome name.
    """
    parts = ticker.split("-")
    if len(parts) < 2:
        return None
    return {"winner_token": parts[-1]}


def main():
    s = load_settings()
    client = KalshiClient(s)

    rows = []
    n_credits_new = 0
    # ===== UFC =====
    ufc_events = load_book("mma_mixed_martial_arts", "h2h", "us")
    # Build name index from sportsbook (canonical tokens of last name)
    book_index_ufc = {}
    for ev in ufc_events:
        commence = ev.get("commence_time", "")[:10]
        for nm in (ev.get("home_team", ""), ev.get("away_team", "")):
            # The 3-letter Kalshi token is rarely first 3 chars; often the
            # last name short form. Build by canonical full and surname.
            tokens = nm.split()
            surname = tokens[-1] if tokens else nm
            book_index_ufc.setdefault(canonicalize(surname)[:3], []).append((ev, nm))
            book_index_ufc.setdefault(canonicalize(surname), []).append((ev, nm))

    resp_ufc = client.get("/markets", series_ticker="KXUFCFIGHT", status="open", limit=200)
    for mk in resp_ufc.get("markets", []):
        ticker = mk.get("ticker", "")
        parsed = parse_kalshi_fight_ticker(ticker)
        if not parsed:
            continue
        winner = parsed["winner_token"]
        # Find sportsbook event where one fighter's surname matches winner.
        best = None
        for key in (canonicalize(winner), canonicalize(winner)[:3]):
            for ev, full_name in book_index_ufc.get(key, []):
                if canonicalize(full_name).startswith(canonicalize(winner)) or \
                   canonicalize(full_name).endswith(canonicalize(winner)):
                    best = (ev, full_name)
                    break
            if best:
                break
        if best is None:
            continue
        ev, full_name = best
        # Extract h2h prices
        all_ps = []
        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                names = [o.get("name", "") for o in outcomes]
                ps_raw = [implied_from_decimal(float(o.get("price", 0) or 0)) for o in outcomes]
                if not all(p > 0 for p in ps_raw):
                    continue
                ps_dv = devig(ps_raw)
                for nm, p in zip(names, ps_dv, strict=False):
                    if nm == full_name:
                        all_ps.append({"book": bm.get("key", ""), "p": p})
                        break
        if not all_ps:
            continue
        median_p = float(pd.Series([x["p"] for x in all_ps]).median())
        yb = mk.get("yes_bid_dollars")
        ya = mk.get("yes_ask_dollars")
        last = mk.get("last_price_dollars")
        if yb not in (None, "", 0) and ya not in (None, "", 0):
            kalshi_mid = (float(yb) + float(ya)) / 2.0
        elif last not in (None, "", 0):
            kalshi_mid = float(last)
        else:
            continue
        divergence = round((kalshi_mid - median_p) * 100, 2)
        rows.append({
            "series": "KXUFCFIGHT",
            "ticker": ticker,
            "matched_name": full_name,
            "kalshi_mid": round(kalshi_mid, 4),
            "sportsbook_median": round(median_p, 4),
            "n_books": len(all_ps),
            "divergence_cents": divergence,
            "is_favorite": median_p >= 0.55,
            "in_v1_band": 0.70 <= kalshi_mid <= 0.95,
        })

    # ===== Boxing =====
    box_events = load_book("boxing_boxing", "h2h", "us")
    book_index_box = {}
    for ev in box_events:
        for nm in (ev.get("home_team", ""), ev.get("away_team", "")):
            tokens = nm.split()
            surname = tokens[-1] if tokens else nm
            for k in (canonicalize(surname)[:3], canonicalize(surname)[:5], canonicalize(surname)):
                book_index_box.setdefault(k, []).append((ev, nm))

    resp_box = client.get("/markets", series_ticker="KXBOXING", status="open", limit=200)
    for mk in resp_box.get("markets", []):
        ticker = mk.get("ticker", "")
        parsed = parse_kalshi_fight_ticker(ticker)
        if not parsed:
            continue
        winner = parsed["winner_token"]
        best = None
        for key in (canonicalize(winner), canonicalize(winner)[:5], canonicalize(winner)[:3]):
            for ev, full_name in book_index_box.get(key, []):
                if canonicalize(full_name).startswith(canonicalize(winner)) or \
                   canonicalize(full_name).endswith(canonicalize(winner)) or \
                   canonicalize(winner) in canonicalize(full_name):
                    best = (ev, full_name)
                    break
            if best:
                break
        if best is None:
            continue
        ev, full_name = best
        all_ps = []
        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                names = [o.get("name", "") for o in outcomes]
                ps_raw = [implied_from_decimal(float(o.get("price", 0) or 0)) for o in outcomes]
                if not all(p > 0 for p in ps_raw):
                    continue
                ps_dv = devig(ps_raw)
                for nm, p in zip(names, ps_dv, strict=False):
                    if nm == full_name:
                        all_ps.append({"book": bm.get("key", ""), "p": p})
                        break
        if not all_ps:
            continue
        median_p = float(pd.Series([x["p"] for x in all_ps]).median())
        yb = mk.get("yes_bid_dollars")
        ya = mk.get("yes_ask_dollars")
        last = mk.get("last_price_dollars")
        if yb not in (None, "", 0) and ya not in (None, "", 0):
            kalshi_mid = (float(yb) + float(ya)) / 2.0
        elif last not in (None, "", 0):
            kalshi_mid = float(last)
        else:
            continue
        divergence = round((kalshi_mid - median_p) * 100, 2)
        rows.append({
            "series": "KXBOXING",
            "ticker": ticker,
            "matched_name": full_name,
            "kalshi_mid": round(kalshi_mid, 4),
            "sportsbook_median": round(median_p, 4),
            "n_books": len(all_ps),
            "divergence_cents": divergence,
            "is_favorite": median_p >= 0.55,
            "in_v1_band": 0.70 <= kalshi_mid <= 0.95,
        })

    df = pd.DataFrame(rows)
    print(f"Total UFC+Boxing favorite-style pairs: {len(df)}")
    print()
    if df.empty:
        OUT_JSON.write_text(json.dumps({"rows": []}, indent=2), encoding="utf-8")
        return
    print(df.to_string(index=False))
    fav = df[df["is_favorite"]]
    elig = df[df["in_v1_band"]]
    print()
    if not fav.empty:
        print(f"FAVORITE-side mean Kalshi-Sportsbook: {fav['divergence_cents'].mean():.2f} cents (n={len(fav)})")
        print(f"FAVORITE-side over rate: {(fav['divergence_cents']>0).sum()}/{len(fav)} = {(fav['divergence_cents']>0).mean()*100:.0f}%")
    if not elig.empty:
        print(f"v1-band mean Kalshi-Sportsbook: {elig['divergence_cents'].mean():.2f} cents (n={len(elig)})")
    OUT_JSON.write_text(json.dumps({
        "rows": rows,
        "summary": {
            "favorite_mean": float(fav["divergence_cents"].mean()) if not fav.empty else None,
            "favorite_n": int(len(fav)),
            "v1_band_mean": float(elig["divergence_cents"].mean()) if not elig.empty else None,
            "v1_band_n": int(len(elig)),
        },
    }, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
