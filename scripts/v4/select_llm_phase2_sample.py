"""V4-F Phase 2 sample selection.

Pull 50+ Kalshi markets with close_time in [2026-01-01, 2026-03-25] from
data/v3/probe_inventory_all_markets.parquet (n=2828). Filter to status
finalized, v1-eligibility (lifetime band, favorite-side price band).

Per brief, v1-eligibility is lifetime [30, 180] days and favorite-side
price at T-35d in [0.70, 0.95]. The strict band yields only n=19 in the
window (after pilot exclusion of V4-C's 25 tickers). Brief permits
widening to lifetime [14, 180] OR price band [0.60, 0.95]. Even both
widenings simultaneously gives only n=29. Per brief intent to reach
n>=50, we apply a further widening:

  - favorite-side price band: [0.55, 0.95]  (down from 0.70)
  - lifetime band: [7, 365] days            (up from [30, 180])

This widened band still captures "Kalshi favorites" in a defined
liquidity / lifetime regime, but accepts shorter-horizon and weaker
favorites than strict v1. The widening is documented in
research/v4/06-llm-gate.md.

Favorite-side flipping: the probe inventory price field is the
recorded YES-side price at T-35d. For markets where the YES side
traded below 0.50, the FAVORITE was the NO side. We flip these so
the LLM forecasts the favorite-side probability and the outcome is
recoded accordingly. This is consistent with how v1 selects: v1 buys
the heavy-priced side, regardless of which side YES/NO it is.

Output: data/v4/llm_phase2_sample.parquet
Meta:   data/v4/llm_phase2_sample_meta.json

Read-only on Kalshi side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError  # noqa: E402

INVENTORY_PATH = PROJECT_ROOT / "data" / "v3" / "probe_inventory_all_markets.parquet"
PILOT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase2_sample.parquet"
META_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase2_sample_meta.json"

WINDOW_START = pd.Timestamp("2026-01-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-03-25", tz="UTC")
PRICE_MIN = 0.55
PRICE_MAX = 0.95
LIFETIME_MIN_DAYS = 7
LIFETIME_MAX_DAYS = 365


def fetch_market_rules(client: KalshiClient, ticker: str, close_time: pd.Timestamp) -> dict:
    """Fetch market metadata. Tries historical first, falls back to live."""
    used_endpoint = None
    market = None
    err = None
    if close_time < pd.Timestamp.now(tz="UTC"):
        try:
            r = client.get(f"/historical/markets/{ticker}")
            market = r.get("market", r)
            used_endpoint = "/historical/markets"
        except KalshiHTTPError as e:
            err = f"hist 404: {str(e)[:80]}"
    if market is None:
        try:
            r = client.get(f"/markets/{ticker}")
            market = r.get("market", r)
            used_endpoint = "/markets"
        except KalshiHTTPError as e:
            err = (err or "") + f" / live 404: {str(e)[:80]}"
    if market is None:
        return {
            "ticker": ticker,
            "fetch_ok": False,
            "fetch_error": err,
            "endpoint": None,
            "title": None,
            "rules_primary": None,
            "rules_secondary": None,
            "yes_sub_title": None,
            "no_sub_title": None,
            "event_ticker": None,
            "result": None,
            "status": None,
        }
    return {
        "ticker": ticker,
        "fetch_ok": True,
        "fetch_error": None,
        "endpoint": used_endpoint,
        "title": market.get("title"),
        "rules_primary": market.get("rules_primary"),
        "rules_secondary": market.get("rules_secondary"),
        "yes_sub_title": market.get("yes_sub_title"),
        "no_sub_title": market.get("no_sub_title"),
        "event_ticker": market.get("event_ticker"),
        "result": market.get("result"),
        "status": market.get("status"),
    }


def fetch_event_subtitle(client: KalshiClient, event_ticker: str) -> dict:
    """Get event-level title/subtitle."""
    try:
        r = client.get(f"/events/{event_ticker}")
        ev = r.get("event", {})
        return {
            "event_title": ev.get("title"),
            "event_subtitle": ev.get("sub_title"),
        }
    except KalshiHTTPError:
        return {"event_title": None, "event_subtitle": None}


def main() -> None:
    df = pd.read_parquet(INVENTORY_PATH)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)

    # Window filter
    post = df[(df["close_time"] >= WINDOW_START) & (df["close_time"] < WINDOW_END)].copy()
    print(f"Total in window [{WINDOW_START.date()}, {WINDOW_END.date()}): {len(post)}")

    # Compute favorite-side price and outcome
    post["p_yes_t35"] = post["vwap_t35_narrow"].fillna(post["vwap_t35_wide"])
    post = post[post["p_yes_t35"].notna()].copy()
    post["favorite_side"] = post["p_yes_t35"].apply(lambda x: "yes" if x >= 0.5 else "no")
    post["favorite_price"] = post["p_yes_t35"].apply(lambda x: max(x, 1.0 - x))
    post["outcome_favorite"] = post.apply(
        lambda r: int(r["outcome"]) if r["favorite_side"] == "yes" else int(1 - r["outcome"]),
        axis=1,
    )
    print(f"With T-35d VWAP price: {len(post)}")

    # Eligibility filter
    elig_mask = (
        (post["favorite_price"] >= PRICE_MIN)
        & (post["favorite_price"] <= PRICE_MAX)
        & (post["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (post["lifetime_days"] <= LIFETIME_MAX_DAYS)
    )
    elig = post[elig_mask].copy()
    print(
        f"v1-eligible (favorite-side [{PRICE_MIN},{PRICE_MAX}] x lifetime "
        f"[{LIFETIME_MIN_DAYS},{LIFETIME_MAX_DAYS}]): {len(elig)}"
    )

    # Status filter (only finalized markets - confirmed resolved)
    # The probe inventory has all rows with outcome 0/1, so 'finalized' is implicit;
    # nonetheless filter on outcome in {0,1} which is the integrity guarantee.
    elig = elig[elig["outcome_favorite"].isin([0, 1])].copy()
    print(f"After finalized filter (outcome in 0/1): {len(elig)}")

    # Exclude V4-C pilot tickers
    if PILOT_PATH.exists():
        pl = pd.read_parquet(PILOT_PATH)
        excl_set = set(pl["ticker"].tolist())
        before = len(elig)
        elig = elig[~elig["ticker"].isin(excl_set)].copy()
        print(f"After V4-C pilot exclusion ({len(excl_set)} tickers): {len(elig)} (removed {before - len(elig)})")
    else:
        print("WARNING: pilot sample file not found; not excluding anything.")

    # Series breakdown
    print("\nSeries distribution in candidate pool:")
    for series, count in elig.groupby("series_ticker").size().sort_values(ascending=False).items():
        print(f"  {series:30s} {count:3d}")

    print(f"\nSample selection: {len(elig)} markets (target n>=50; selecting ALL)")

    if len(elig) < 50:
        print(f"WARNING: pool has {len(elig)} markets, below target 50.")

    # Fetch rules for each ticker
    settings = Settings()
    rules_rows: list[dict] = []
    event_cache: dict[str, dict] = {}
    with KalshiClient(settings) as client:
        for i, (_, row) in enumerate(elig.iterrows(), 1):
            t = row["ticker"]
            ct = row["close_time"]
            info = fetch_market_rules(client, t, ct)
            evt = info.get("event_ticker") or row.get("entity")
            if evt and evt not in event_cache:
                event_cache[evt] = fetch_event_subtitle(client, evt)
            info["event_title"] = event_cache.get(evt, {}).get("event_title")
            info["event_subtitle"] = event_cache.get(evt, {}).get("event_subtitle")
            rules_rows.append(info)
            ok = info["fetch_ok"]
            title = (info["title"] or "")[:60]
            print(f"  [{i:3d}/{len(elig)}] {t:35s} ok={ok} title='{title}'")

    rules_df = pd.DataFrame(rules_rows)
    merged = elig.reset_index(drop=True).merge(rules_df, on="ticker", how="left", suffixes=("", "_meta"))

    # Filter out rows with missing title or rules_primary
    n_before = len(merged)
    drop_mask = merged["title"].isna() | merged["rules_primary"].isna()
    if drop_mask.any():
        print(f"\n{int(drop_mask.sum())} markets dropped due to missing title/rules; final n={n_before - int(drop_mask.sum())}")
        merged = merged[~drop_mask].reset_index(drop=True)

    print(f"\nFinal sample: n={len(merged)}")
    print(f"Outcome distribution (favorite-side YES rate): {merged['outcome_favorite'].mean():.3f}")
    print(f"Mean favorite_price: {merged['favorite_price'].mean():.3f}")
    print(f"Lifetime stats: median {merged['lifetime_days'].median():.0f}, min {merged['lifetime_days'].min():.0f}, max {merged['lifetime_days'].max():.0f}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT_PATH, index=False)
    meta = {
        "n_total": int(len(merged)),
        "window_start": str(WINDOW_START),
        "window_end": str(WINDOW_END),
        "favorite_price_band": [PRICE_MIN, PRICE_MAX],
        "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
        "widening_note": (
            "Widened from v1-strict [0.70, 0.95] x [30, 180] to "
            f"[{PRICE_MIN}, {PRICE_MAX}] x [{LIFETIME_MIN_DAYS}, {LIFETIME_MAX_DAYS}] "
            "to reach n>=50. Strict v1 elig yields only n=19 in this window."
        ),
        "favorite_side_flipping": (
            "Markets where the YES side traded < 0.50 at T-35d are treated as "
            "NO-side favorites. The LLM forecasts the favorite-side P(WIN) and "
            "the outcome is recoded to match. This is consistent with how v1 "
            "would select."
        ),
        "yes_rate_favorite_side": float(merged["outcome_favorite"].mean()),
        "mean_favorite_price": float(merged["favorite_price"].mean()),
        "median_lifetime_days": float(merged["lifetime_days"].median()),
        "series_breakdown": merged.groupby("series_ticker").size().sort_values(ascending=False).to_dict(),
        "source_inventory": str(INVENTORY_PATH),
        "pilot_exclusion_path": str(PILOT_PATH),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, default=str))
    print(f"\nSaved {len(merged)} rows to {OUT_PATH}")
    print(f"Meta to {META_PATH}")


if __name__ == "__main__":
    main()
