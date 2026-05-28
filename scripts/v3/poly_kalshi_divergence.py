"""Phase 1 / Agent V3-C: Polymarket vs Kalshi divergence analysis.

For a sample of v1-eligible-style Kalshi markets, attempt to:
  (a) match to a Polymarket event/contract,
  (b) fetch Polymarket YES mid-price at the Kalshi T-35d timestamp,
  (c) fetch Polymarket YES mid-price at T-21d, T-7d, T-1d for
      convergence-vs-divergence assessment,
  (d) compare Kalshi VWAP at the same timestamps,
  (e) confirm settlement alignment (Kalshi outcome vs Polymarket
      resolved YES/NO).

Outputs:
  - data/v3/poly_match_summary.parquet  (updated)
  - data/v3/poly_kalshi_pairs.parquet   (per-pair divergence table)
  - data/v3/poly_kalshi_divergence_meta.json
  - data/v3/poly_kalshi_priceseries.parquet  (long-format mids per timestamp)

READ-ONLY public Polymarket Gamma + CLOB endpoints. No auth. No trading.
Polite (0.8 s between request groups).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

# Kalshi client (read-only). Imported below after sys.path insert.

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_V2 = REPO_ROOT / "data" / "v2"
DATA_V3 = REPO_ROOT / "data" / "v3"
DATA_V3.mkdir(parents=True, exist_ok=True)
SPORTS_MARKETS = REPO_ROOT / "data" / "sports" / "markets"
SPORTS_TRADES = REPO_ROOT / "data" / "sports" / "trades"
V3_TRADES_CACHE = DATA_V3 / "kalshi_trades_extra"
V3_TRADES_CACHE.mkdir(parents=True, exist_ok=True)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

POLITE_SLEEP_S = 0.6

MLB_TEAM_NAMES: dict[str, dict[str, str]] = {
    "ARI": {"full": "Arizona Diamondbacks", "slug": "arizona-diamondbacks"},
    "ATL": {"full": "Atlanta Braves", "slug": "atlanta-braves"},
    "BAL": {"full": "Baltimore Orioles", "slug": "baltimore-orioles"},
    "BOS": {"full": "Boston Red Sox", "slug": "boston-red-sox"},
    "CHC": {"full": "Chicago Cubs", "slug": "chicago-cubs"},
    "CWS": {"full": "Chicago White Sox", "slug": "chicago-white-sox"},
    "CIN": {"full": "Cincinnati Reds", "slug": "cincinnati-reds"},
    "CLE": {"full": "Cleveland Guardians", "slug": "cleveland-guardians"},
    "COL": {"full": "Colorado Rockies", "slug": "colorado-rockies"},
    "DET": {"full": "Detroit Tigers", "slug": "detroit-tigers"},
    "HOU": {"full": "Houston Astros", "slug": "houston-astros"},
    "KC":  {"full": "Kansas City Royals", "slug": "kansas-city-royals"},
    "LAA": {"full": "Los Angeles Angels", "slug": "los-angeles-angels"},
    "LAD": {"full": "Los Angeles Dodgers", "slug": "los-angeles-dodgers"},
    "MIA": {"full": "Miami Marlins", "slug": "miami-marlins"},
    "MIL": {"full": "Milwaukee Brewers", "slug": "milwaukee-brewers"},
    "MIN": {"full": "Minnesota Twins", "slug": "minnesota-twins"},
    "NYM": {"full": "New York Mets", "slug": "new-york-mets"},
    "NYY": {"full": "New York Yankees", "slug": "new-york-yankees"},
    "OAK": {"full": "Oakland Athletics", "slug": "oakland-athletics"},
    "PHI": {"full": "Philadelphia Phillies", "slug": "philadelphia-phillies"},
    "PIT": {"full": "Pittsburgh Pirates", "slug": "pittsburgh-pirates"},
    "SD":  {"full": "San Diego Padres", "slug": "san-diego-padres"},
    "SEA": {"full": "Seattle Mariners", "slug": "seattle-mariners"},
    "SF":  {"full": "San Francisco Giants", "slug": "san-francisco-giants"},
    "STL": {"full": "St. Louis Cardinals", "slug": "st-louis-cardinals"},
    "TB":  {"full": "Tampa Bay Rays", "slug": "tampa-bay-rays"},
    "TEX": {"full": "Texas Rangers", "slug": "texas-rangers"},
    "TOR": {"full": "Toronto Blue Jays", "slug": "toronto-blue-jays"},
    "WSH": {"full": "Washington Nationals", "slug": "washington-nationals"},
}

DIVISION_EVENT_SLUGS = {
    "KXMLBALEAST": "al-east-division-winner",
    "KXMLBALCENT": "al-central-division-winner",
    "KXMLBALWEST": "al-west-division-winner",
    "KXMLBNLEAST": "nl-east-division-winner",
    "KXMLBNLCENT": "nl-central-division-winner",
    "KXMLBNLWEST": "nl-west-division-winner",
}
PLAYOFFS_EVENT_SLUG = "mlb-which-teams-make-the-playoffs"


def http_get(url: str, params: dict | None = None, retries: int = 2) -> dict | list | None:
    last_err = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(url, params=params or {})
                if r.status_code == 200:
                    return r.json()
                if r.status_code >= 500 and attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                return {"_http_error": r.status_code, "_body": r.text[:300]}
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            return {"_error": last_err}
    return None


def load_kalshi_universe() -> pd.DataFrame:
    df = pd.read_parquet(DATA_V2 / "joined_mlb_longhorizon_dataset.parquet")
    # attach title + rules
    titles, rules = [], []
    for _, row in df.iterrows():
        path = SPORTS_MARKETS / f"{row['series_ticker']}.parquet"
        if path.exists():
            cache = pd.read_parquet(path)
            hit = cache[cache["ticker"] == row["ticker"]]
            if len(hit):
                r0 = hit.iloc[0]
                titles.append(r0.get("title"))
                rules.append(r0.get("rules_primary"))
                continue
        titles.append(None)
        rules.append(None)
    df = df.copy()
    df["kalshi_title"] = titles
    df["kalshi_rules_primary"] = rules
    return df


def pick_20_for_probe(df: pd.DataFrame) -> pd.DataFrame:
    """Sample: all 11 strict-eligible + 9 marginal close-to-eligible markets."""
    elig = df[df["is_eligible"]].copy()
    marginal = df[(~df["is_eligible"]) & (df["favorite_price"] >= 0.45)].copy()
    marginal_sample = (
        marginal.sort_values(["series_ticker", "favorite_price"], ascending=[True, False])
        .groupby("series_ticker")
        .head(2)
    )
    needed = 20 - len(elig)
    marginal_sample = marginal_sample.head(needed)
    return pd.concat([elig, marginal_sample], ignore_index=True)


def parse_year(row: pd.Series) -> int:
    m = re.search(r"-(\d{2})-", row["ticker"])
    if m:
        return 2000 + int(m.group(1))
    return pd.Timestamp(row["market_close_time"]).year


def map_to_polymarket_market(row: pd.Series) -> dict:
    """Map a Kalshi market to its Polymarket counterpart, if any.

    Returns dict with keys:
      polymarket_event_slug, polymarket_market_slug, polymarket_question,
      yes_token_id, no_token_id, match_confidence, match_rationale,
      polymarket_outcome ("Yes"/"No"/None), umaResolutionStatus
    """
    out: dict = {
        "polymarket_event_slug": None,
        "polymarket_market_slug": None,
        "polymarket_question": None,
        "yes_token_id": None,
        "no_token_id": None,
        "match_confidence": "none",
        "match_rationale": "",
        "polymarket_outcome": None,
        "polymarket_umaResolutionStatus": None,
    }
    kind = row.get("market_kind")
    series = row["series_ticker"]
    team_abbrev = row.get("favorite_team_abbrev")
    year = parse_year(row)
    team = MLB_TEAM_NAMES.get(team_abbrev, {})
    team_slug = team.get("slug")
    team_full = team.get("full")

    # Division markets: deterministic event slug, then per-team market slug.
    if kind == "division":
        event_slug = DIVISION_EVENT_SLUGS.get(series)
        if not event_slug:
            out["match_rationale"] = f"unknown series {series}"
            return out
        ev = http_get(f"{GAMMA}/events/slug/{event_slug}")
        time.sleep(POLITE_SLEEP_S)
        if not isinstance(ev, dict) or ev.get("_http_error"):
            out["match_rationale"] = f"event slug not found: {event_slug}"
            return out
        # endDate sanity
        ev_year = pd.Timestamp(ev.get("endDate")).year if ev.get("endDate") else year
        if abs(ev_year - year) > 0:
            out["match_rationale"] = f"event year {ev_year} != kalshi year {year}"
            return out
        # Look for matching market
        for m in ev.get("markets", []):
            slug = (m.get("slug") or "").lower()
            if not team_slug:
                continue
            if team_slug in slug and "another" not in slug and "other" not in slug:
                cti = m.get("clobTokenIds")
                if isinstance(cti, str):
                    cti = json.loads(cti)
                out.update({
                    "polymarket_event_slug": event_slug,
                    "polymarket_market_slug": m.get("slug"),
                    "polymarket_question": m.get("question"),
                    "yes_token_id": cti[0] if cti else None,
                    "no_token_id": cti[1] if cti and len(cti) > 1 else None,
                    "match_confidence": "confident",
                    "match_rationale": "deterministic slug match (event year + team)",
                    "polymarket_outcome": (m.get("outcomePrices") or m.get("outcomes")),
                    "polymarket_umaResolutionStatus": m.get("umaResolutionStatus"),
                })
                return out
        out["match_rationale"] = f"event found, team slug not in markets: team_slug={team_slug}"
        return out

    # Playoffs: deterministic slug "will-the-{team-slug}-make-the-{year}-mlb-playoffs"
    if kind == "playoffs":
        # event_slug = mlb-which-teams-make-the-playoffs (without year)
        ev = http_get(f"{GAMMA}/events/slug/{PLAYOFFS_EVENT_SLUG}")
        time.sleep(POLITE_SLEEP_S)
        if not isinstance(ev, dict) or ev.get("_http_error"):
            out["match_rationale"] = "playoffs event not found"
            return out
        ev_year = pd.Timestamp(ev.get("endDate")).year if ev.get("endDate") else year
        if abs(ev_year - year) > 0:
            out["match_rationale"] = f"event year {ev_year} != kalshi year {year}"
            return out
        for m in ev.get("markets", []):
            slug = (m.get("slug") or "").lower()
            if team_slug and team_slug in slug and "make-the" in slug:
                cti = m.get("clobTokenIds")
                if isinstance(cti, str):
                    cti = json.loads(cti)
                out.update({
                    "polymarket_event_slug": PLAYOFFS_EVENT_SLUG,
                    "polymarket_market_slug": m.get("slug"),
                    "polymarket_question": m.get("question"),
                    "yes_token_id": cti[0] if cti else None,
                    "no_token_id": cti[1] if cti and len(cti) > 1 else None,
                    "match_confidence": "confident",
                    "match_rationale": "deterministic playoffs slug match",
                    "polymarket_outcome": (m.get("outcomePrices") or m.get("outcomes")),
                    "polymarket_umaResolutionStatus": m.get("umaResolutionStatus"),
                })
                return out
        out["match_rationale"] = f"playoffs event found, team {team_slug} not in markets"
        return out

    # Season-win totals (KXMLBWINS): probe for 2025-specific win-totals event
    if kind == "wins":
        # Try common slug variants
        candidates = [
            f"mlb-{year}-regular-season-win-totals",
            f"{year}-mlb-regular-season-win-totals",
            f"mlb-{year}-win-totals",
        ]
        for s in candidates:
            ev = http_get(f"{GAMMA}/events/slug/{s}")
            time.sleep(POLITE_SLEEP_S)
            if isinstance(ev, dict) and not ev.get("_http_error"):
                for m in ev.get("markets", []):
                    slug = (m.get("slug") or "").lower()
                    if team_slug and team_slug in slug:
                        cti = m.get("clobTokenIds")
                        if isinstance(cti, str):
                            cti = json.loads(cti)
                        out.update({
                            "polymarket_event_slug": s,
                            "polymarket_market_slug": m.get("slug"),
                            "polymarket_question": m.get("question"),
                            "yes_token_id": cti[0] if cti else None,
                            "no_token_id": cti[1] if cti and len(cti) > 1 else None,
                            "match_confidence": "confident",
                            "match_rationale": "wins event found via slug guess",
                            "polymarket_outcome": (m.get("outcomePrices") or m.get("outcomes")),
                            "polymarket_umaResolutionStatus": m.get("umaResolutionStatus"),
                        })
                        return out
        out["match_rationale"] = (
            f"no MLB {year} win-totals event found on Polymarket (event slug candidates 404 or "
            f"team slug missing). Kalshi's KXMLBWINS-X-{year-2000}-TN markets have no per-team "
            f"Polymarket counterpart at this season."
        )
        return out

    out["match_rationale"] = f"unknown market_kind {kind}"
    return out


def fetch_price_window(token_id: str, target_unix: int, half_window_s: int = 86400) -> list[dict]:
    """Fetch CLOB hourly price history within +/- half_window_s of target."""
    start = target_unix - half_window_s
    end = target_unix + half_window_s
    # API caps the window length. Hourly fidelity works for windows up to ~7d.
    if (end - start) > 86400 * 7:
        end = start + 86400 * 7
    res = http_get(f"{CLOB}/prices-history", params={
        "market": token_id, "startTs": start, "endTs": end, "fidelity": 60
    })
    time.sleep(POLITE_SLEEP_S)
    if not isinstance(res, dict):
        return []
    return res.get("history", []) or []


def avg_mid(history: list[dict], target_unix: int, max_offset_s: int = 86400 * 2) -> float | None:
    """Average prices within +/- max_offset_s of target. Returns None if none in range."""
    if not history:
        return None
    pts = [pt["p"] for pt in history if abs(int(pt["t"]) - target_unix) <= max_offset_s]
    if not pts:
        return None
    return float(np.mean(pts))


_KALSHI_CLIENT_SINGLETON = None


def _get_kalshi_client():
    """Lazily build a READ-scope Kalshi client. Returns None if config missing."""
    global _KALSHI_CLIENT_SINGLETON
    if _KALSHI_CLIENT_SINGLETON is not None:
        return _KALSHI_CLIENT_SINGLETON
    try:
        from kalshi_bot.config import Settings  # noqa
        from kalshi_bot.data.kalshi_client import KalshiClient  # noqa
        s = Settings()
        if not s.KALSHI_API_KEY_ID or not s.KALSHI_PRIVATE_KEY_PATH:
            return None
        _KALSHI_CLIENT_SINGLETON = KalshiClient(s)
        return _KALSHI_CLIENT_SINGLETON
    except Exception as e:
        print(f"  (kalshi client init failed: {e})")
        return None


def fetch_kalshi_trades_window(ticker: str, target_unix: int, half_window_s: int = 86400 * 3) -> pd.DataFrame:
    """Fetch Kalshi trades for a ticker within +/- half_window_s of target,
    caching the result to data/v3/kalshi_trades_extra/{ticker}_{target}.parquet."""
    cache_path = V3_TRADES_CACHE / f"{ticker}__t{target_unix}__hw{half_window_s}.parquet"
    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception:
            pass
    c = _get_kalshi_client()
    if c is None:
        return pd.DataFrame()
    start = target_unix - half_window_s
    end = target_unix + half_window_s
    try:
        trades = list(c.paginate(
            "/historical/trades",
            item_key="trades",
            limit=1000,
            ticker=ticker,
            min_ts=start,
            max_ts=end,
        ))
    except Exception as e:
        print(f"  (kalshi fetch err for {ticker}: {e})")
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    if len(df) > 0:
        df.to_parquet(cache_path, index=False)
    return df


def load_kalshi_vwap_at(row: pd.Series, target_unix: int, half_window_s: int = 86400) -> float | None:
    """Compute VWAP-of-mid (or trade-price mean) for Kalshi within +/- half_window_s.

    Strategy: prefer the v1 cache (covers T-35d window); for windows outside
    the cache, fall back to authenticated /historical/trades and cache to
    data/v3/kalshi_trades_extra/.
    """
    ticker = row["ticker"]
    series = row["series_ticker"]
    # v1 cache first
    td = pd.DataFrame()
    trade_path = SPORTS_TRADES / f"{series}.parquet"
    if trade_path.exists():
        try:
            td = pd.read_parquet(trade_path)
            td = td[td["ticker"] == ticker].copy()
        except Exception:
            td = pd.DataFrame()
    # If empty or doesn't cover this window, fetch fresh
    needs_fetch = False
    if len(td) == 0:
        needs_fetch = True
    else:
        ts = pd.to_datetime(td["created_time"], utc=True).astype("datetime64[ns, UTC]")
        ux = ts.astype("int64") // 1_000_000_000
        in_win = ((ux >= target_unix - half_window_s) & (ux <= target_unix + half_window_s)).sum()
        if in_win == 0:
            needs_fetch = True
    if needs_fetch:
        extra = fetch_kalshi_trades_window(ticker, target_unix, half_window_s=max(half_window_s, 86400 * 3))
        if len(extra) > 0:
            if len(td) > 0:
                td = pd.concat([td, extra], ignore_index=True).drop_duplicates(subset=["trade_id"])
            else:
                td = extra
    if len(td) == 0:
        return None
    # Normalize created_time to unix int. Cast to ns precision first so the
    # /1e9 conversion is correct regardless of source dtype (us or ns).
    if "created_time" in td.columns:
        ts = pd.to_datetime(td["created_time"], utc=True).astype("datetime64[ns, UTC]")
        td["created_unix"] = ts.astype("int64") // 1_000_000_000
    elif "ts" in td.columns:
        td["created_unix"] = td["ts"].astype("int64")
    else:
        return None
    mask = (td["created_unix"] >= target_unix - half_window_s) & (td["created_unix"] <= target_unix + half_window_s)
    sub = td[mask]
    if len(sub) == 0:
        return None
    # Prefer yes_price column; fall back to trade price.
    price_col = None
    for c in ("yes_price_dollars", "yes_price", "price", "trade_price"):
        if c in sub.columns:
            price_col = c
            break
    if not price_col:
        return None
    p = pd.to_numeric(sub[price_col], errors="coerce")
    # Some columns may be in cents
    p_mean = p.mean()
    if pd.notna(p_mean) and p_mean > 1.5:
        p = p / 100.0
    size_col = None
    for c in ("count_fp", "count", "size", "volume"):
        if c in sub.columns:
            size_col = c
            break
    if size_col:
        w = pd.to_numeric(sub[size_col], errors="coerce").fillna(1.0)
        if w.sum() > 0:
            return float((p * w).sum() / w.sum())
    return float(p.mean())


def settled_outcome_polymarket(market_obj: dict) -> int | None:
    """Map Polymarket market resolution to 1/0/None."""
    op = market_obj.get("outcomePrices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except Exception:
            op = None
    if isinstance(op, list) and len(op) >= 1:
        try:
            yes_p = float(op[0])
            if yes_p >= 0.95:
                return 1
            if yes_p <= 0.05:
                return 0
        except Exception:
            pass
    # Sometimes the resolved outcome is in 'umaResolutionStatus' / 'resolved'
    return None


def main() -> int:
    df = load_kalshi_universe()
    sample = pick_20_for_probe(df)
    print(f"Sample size: {len(sample)} ({sample['is_eligible'].sum()} strict-eligible).")

    pairs: list[dict] = []
    series_long: list[dict] = []

    for i, (_, row) in enumerate(sample.iterrows()):
        ticker = row["ticker"]
        close_unix = int(pd.Timestamp(row["market_close_time"]).timestamp())
        t35 = close_unix - 35 * 86400
        t21 = close_unix - 21 * 86400
        t7 = close_unix - 7 * 86400
        t1 = close_unix - 1 * 86400
        print(f"\n[{i+1}/{len(sample)}] {ticker}  close_unix={close_unix}  market_kind={row['market_kind']}")
        match = map_to_polymarket_market(row)
        print(f"  match: {match['match_confidence']}  ({match['match_rationale']})")
        if match["polymarket_market_slug"]:
            print(f"    -> {match['polymarket_market_slug']}")
        rec = {
            "ticker": ticker,
            "series_ticker": row["series_ticker"],
            "market_kind": row["market_kind"],
            "favorite_team_abbrev": row.get("favorite_team_abbrev"),
            "favorite_price": float(row["favorite_price"]),
            "lifetime_days": float(row["lifetime_days"]),
            "is_eligible": bool(row.get("is_eligible", False)),
            "kalshi_outcome": int(row["outcome"]),
            "market_close_time": str(row["market_close_time"]),
            **match,
        }

        # Fetch Polymarket prices at the four target timestamps
        for label, target in [("T_minus_35d", t35), ("T_minus_21d", t21),
                               ("T_minus_7d", t7), ("T_minus_1d", t1)]:
            poly_mid = None
            kalshi_mid = None
            if match["yes_token_id"]:
                hist = fetch_price_window(match["yes_token_id"], target, half_window_s=86400 * 3)
                poly_mid = avg_mid(hist, target, max_offset_s=86400 * 2)
            kalshi_mid = load_kalshi_vwap_at(row, target, half_window_s=86400 * 2)
            rec[f"poly_mid_{label}"] = poly_mid
            rec[f"kalshi_mid_{label}"] = kalshi_mid
            if poly_mid is not None and kalshi_mid is not None:
                rec[f"divergence_{label}"] = kalshi_mid - poly_mid
            else:
                rec[f"divergence_{label}"] = None
            series_long.append({
                "ticker": ticker,
                "timestamp_label": label,
                "target_unix": target,
                "poly_mid": poly_mid,
                "kalshi_mid": kalshi_mid,
            })

        # Pull Polymarket settled outcome via the market object
        if match["polymarket_market_slug"] and match["polymarket_event_slug"]:
            # We previously fetched the event; refetch the market with full detail
            ev = http_get(f"{GAMMA}/events/slug/{match['polymarket_event_slug']}")
            time.sleep(POLITE_SLEEP_S)
            mk = None
            if isinstance(ev, dict):
                for m in ev.get("markets", []):
                    if m.get("slug") == match["polymarket_market_slug"]:
                        mk = m
                        break
            if mk:
                rec["polymarket_resolved_yes"] = settled_outcome_polymarket(mk)
                rec["polymarket_outcomePrices"] = json.dumps(mk.get("outcomePrices"))
                rec["polymarket_umaResolutionStatus"] = mk.get("umaResolutionStatus")
            else:
                rec["polymarket_resolved_yes"] = None
        else:
            rec["polymarket_resolved_yes"] = None

        pairs.append(rec)

    out_df = pd.DataFrame(pairs)
    out_df.to_parquet(DATA_V3 / "poly_kalshi_pairs.parquet", index=False)
    pd.DataFrame(series_long).to_parquet(DATA_V3 / "poly_kalshi_priceseries.parquet", index=False)

    # Summary stats
    n_total = len(out_df)
    n_confident = (out_df["match_confidence"] == "confident").sum()
    n_with_t35_poly = out_df["poly_mid_T_minus_35d"].notna().sum()
    print(f"\n=== SUMMARY ===")
    print(f"Total sampled: {n_total}")
    print(f"Confident matches: {n_confident}/{n_total} = {n_confident/n_total:.0%}")
    print(f"Polymarket price at T-35d available: {n_with_t35_poly}/{n_total} = {n_with_t35_poly/n_total:.0%}")

    # Divergence stats on pairs that have both prices at T-35d
    div = out_df[out_df["divergence_T_minus_35d"].notna()].copy()
    if len(div):
        d = div["divergence_T_minus_35d"]
        abs_d = d.abs()
        print(f"\nDivergence at T-35d (Kalshi YES - Polymarket YES), n={len(d)}:")
        print(f"  mean:   {d.mean():+.4f}")
        print(f"  median: {d.median():+.4f}")
        print(f"  p25:    {d.quantile(0.25):+.4f}")
        print(f"  p75:    {d.quantile(0.75):+.4f}")
        print(f"  |div| > 0.02: {(abs_d > 0.02).sum()}/{len(d)} = {(abs_d > 0.02).mean():.0%}")
        print(f"  |div| > 0.05: {(abs_d > 0.05).sum()}/{len(d)} = {(abs_d > 0.05).mean():.0%}")
        print(f"  |div| > 0.15: {(abs_d > 0.15).sum()}/{len(d)} = {(abs_d > 0.15).mean():.0%}")

        print("\nMean spread at each timestamp (Kalshi - Polymarket):")
        for lab in ("T_minus_35d", "T_minus_21d", "T_minus_7d", "T_minus_1d"):
            sub = out_df[f"divergence_{lab}"].dropna()
            if len(sub):
                print(f"  {lab}: mean={sub.mean():+.4f}  mean|.|={sub.abs().mean():.4f}  n={len(sub)}")

        # Settlement audit
        print("\nSettlement audit:")
        sa = out_df[(out_df["polymarket_resolved_yes"].notna()) & out_df["kalshi_outcome"].notna()]
        if len(sa):
            agree = (sa["polymarket_resolved_yes"] == sa["kalshi_outcome"]).sum()
            print(f"  resolved on both: n={len(sa)}, agreement: {agree}/{len(sa)} = {agree/len(sa):.0%}")
            disagreements = sa[sa["polymarket_resolved_yes"] != sa["kalshi_outcome"]]
            for _, r in disagreements.iterrows():
                print(f"    DISAGREE: {r['ticker']}  kalshi={r['kalshi_outcome']}  poly={r['polymarket_resolved_yes']}")

    meta = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_total": int(n_total),
        "n_confident_matches": int(n_confident),
        "n_with_t35_poly_price": int(n_with_t35_poly),
        "summary": {
            "match_rate": float(n_confident) / n_total,
            "poly_price_at_t35_rate": float(n_with_t35_poly) / n_total,
        },
    }
    (DATA_V3 / "poly_kalshi_divergence_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\nWrote {DATA_V3 / 'poly_kalshi_pairs.parquet'}")
    print(f"Wrote {DATA_V3 / 'poly_kalshi_priceseries.parquet'}")
    print(f"Wrote {DATA_V3 / 'poly_kalshi_divergence_meta.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
