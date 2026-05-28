"""V4-G Phase 4 sample selection (corrected WINDOW_START).

Phase 3 critic flagged that V4-F's `WINDOW_START = pd.Timestamp("2026-01-01")`
assumed Claude Haiku 4.5's training cutoff was Jan 2026. Anthropic's published
training data cutoff for `claude-haiku-4-5-20251001` is JULY 2025 (with a
"reliable knowledge cutoff" of Feb 2025) per
https://platform.claude.com/docs/en/about-claude/models/overview.

To be safely past the training cutoff we use WINDOW_START = 2025-08-01 (one
month buffer past the documented Jul 2025 cutoff). This yields ~238 strict
v1-eligible markets in the probe inventory after excluding V4-C pilot and
V4-F Phase 2 tickers (vs V4-F's n=19 strict).

This sample is STRICT v1-eligible (favorite-side [0.70, 0.95] x lifetime
[30, 180]), so the v1-baseline test is finally a fair comparison: v1 is
operating within the band where its measured +12.47pp edge applies.

Output:
- data/v4/llm_phase4_sample.parquet
- data/v4/llm_phase4_sample_meta.json

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
PHASE2_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase2_sample.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_sample.parquet"
META_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_sample_meta.json"

# Verified Anthropic Haiku 4.5 training data cutoff: Jul 2025.
# Source: https://platform.claude.com/docs/en/about-claude/models/overview
# Use Aug 1 buffer; markets closing after this point are safely beyond training.
WINDOW_START = pd.Timestamp("2025-08-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-03-25", tz="UTC")

# STRICT v1 eligibility (matching the band where v1's +12.47pp edge applies).
PRICE_MIN = 0.70
PRICE_MAX = 0.95
LIFETIME_MIN_DAYS = 30
LIFETIME_MAX_DAYS = 180

# No chronological cap. V4-G2 rerun: capping at 200 chronologically
# excluded the late-Dec/early-Jan close dates where the catastrophic
# losses concentrate, biasing v1's measured performance upward. Use
# the full eligible pool (n approx 238).
SAMPLE_CAP = None


def fetch_market_rules(client: KalshiClient, ticker: str, close_time: pd.Timestamp) -> dict:
    """Fetch market metadata via /historical/markets with fallback to /markets."""
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
            "ticker": ticker, "fetch_ok": False, "fetch_error": err,
            "endpoint": None, "title": None, "rules_primary": None,
            "rules_secondary": None, "yes_sub_title": None,
            "no_sub_title": None, "event_ticker": None,
            "result": None, "status": None,
        }
    return {
        "ticker": ticker, "fetch_ok": True, "fetch_error": None,
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
    try:
        r = client.get(f"/events/{event_ticker}")
        ev = r.get("event", {})
        return {"event_title": ev.get("title"), "event_subtitle": ev.get("sub_title")}
    except KalshiHTTPError:
        return {"event_title": None, "event_subtitle": None}


def main() -> None:
    df = pd.read_parquet(INVENTORY_PATH)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)

    post = df[(df["close_time"] >= WINDOW_START) & (df["close_time"] < WINDOW_END)].copy()
    print(f"Total in window [{WINDOW_START.date()}, {WINDOW_END.date()}): {len(post)}")

    post["p_yes_t35"] = post["vwap_t35_narrow"].fillna(post["vwap_t35_wide"])
    post = post[post["p_yes_t35"].notna()].copy()
    post["favorite_side"] = post["p_yes_t35"].apply(lambda x: "yes" if x >= 0.5 else "no")
    post["favorite_price"] = post["p_yes_t35"].apply(lambda x: max(x, 1.0 - x))
    post["outcome_favorite"] = post.apply(
        lambda r: int(r["outcome"]) if r["favorite_side"] == "yes" else int(1 - r["outcome"]),
        axis=1,
    )
    print(f"With T-35d VWAP price: {len(post)}")

    elig_mask = (
        (post["favorite_price"] >= PRICE_MIN)
        & (post["favorite_price"] <= PRICE_MAX)
        & (post["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (post["lifetime_days"] <= LIFETIME_MAX_DAYS)
    )
    elig = post[elig_mask].copy()
    print(
        f"Strict v1-eligible (favorite-side [{PRICE_MIN},{PRICE_MAX}] x "
        f"lifetime [{LIFETIME_MIN_DAYS},{LIFETIME_MAX_DAYS}]): {len(elig)}"
    )

    elig = elig[elig["outcome_favorite"].isin([0, 1])].copy()
    print(f"After finalized filter: {len(elig)}")

    # Exclude V4-C pilot AND V4-F Phase 2 tickers
    excl_set: set[str] = set()
    if PILOT_PATH.exists():
        pl = pd.read_parquet(PILOT_PATH)
        excl_set |= set(pl["ticker"].tolist())
        print(f"Pilot exclusion list: {len(pl)} tickers")
    if PHASE2_PATH.exists():
        p2 = pd.read_parquet(PHASE2_PATH)
        excl_set |= set(p2["ticker"].tolist())
        print(f"Phase 2 exclusion list: {len(p2)} tickers")

    before = len(elig)
    elig = elig[~elig["ticker"].isin(excl_set)].copy()
    print(f"After exclusion ({len(excl_set)} unique tickers): {len(elig)} (removed {before - len(elig)})")

    # Chronological cap disabled (None) for V4-G2 rerun. The previous
    # V4-G capped at 200 which excluded late-Dec/early-Jan closes where
    # v1's catastrophic losses concentrate (KXNFLWINS late-regular-season
    # losers per research/v4/09-v1-stress-test.md Section 2.).
    elig = elig.sort_values("close_time").reset_index(drop=True)
    if SAMPLE_CAP is not None and len(elig) > SAMPLE_CAP:
        print(f"Capping {len(elig)} to first {SAMPLE_CAP} chronologically.")
        elig = elig.head(SAMPLE_CAP).copy()

    print("\nSeries distribution in final sample:")
    for series, count in elig.groupby("series_ticker").size().sort_values(ascending=False).items():
        print(f"  {series:30s} {count:3d}")
    print()

    # Fetch market metadata
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
            if i % 25 == 0 or i == len(elig) or not ok:
                title = (info["title"] or "")[:60]
                print(f"  [{i:3d}/{len(elig)}] {t:35s} ok={ok} title='{title}'")

    rules_df = pd.DataFrame(rules_rows)
    merged = elig.reset_index(drop=True).merge(rules_df, on="ticker", how="left", suffixes=("", "_meta"))

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
        "cutoff_source": "https://platform.claude.com/docs/en/about-claude/models/overview",
        "cutoff_anthropic_published": "Jul 2025 (training data) / Feb 2025 (reliable knowledge)",
        "cutoff_used_with_buffer": str(WINDOW_START),
        "favorite_price_band": [PRICE_MIN, PRICE_MAX],
        "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
        "eligibility_note": (
            "STRICT v1 band: matches the regime where v1's measured +12.47pp edge applies "
            "(per CLAUDE.md Round 7 / research/time-scale-analysis.md). This is the leak-free "
            "fair comparison V4-F was prevented from running by the wrong cutoff assumption."
        ),
        "favorite_side_flipping": (
            "Markets where YES side traded < 0.50 at T-35d are treated as NO-side favorites. "
            "Forecaster predicts favorite-side P(WIN); outcome is recoded accordingly."
        ),
        "exclusions": {
            "pilot_count": int(len(pd.read_parquet(PILOT_PATH))) if PILOT_PATH.exists() else 0,
            "phase2_count": int(len(pd.read_parquet(PHASE2_PATH))) if PHASE2_PATH.exists() else 0,
        },
        "yes_rate_favorite_side": float(merged["outcome_favorite"].mean()),
        "mean_favorite_price": float(merged["favorite_price"].mean()),
        "median_lifetime_days": float(merged["lifetime_days"].median()),
        "series_breakdown": {
            str(k): int(v) for k, v in
            merged.groupby("series_ticker").size().sort_values(ascending=False).to_dict().items()
        },
        "source_inventory": str(INVENTORY_PATH),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, default=str))
    print(f"\nSaved {len(merged)} rows to {OUT_PATH}")
    print(f"Meta to {META_PATH}")


if __name__ == "__main__":
    main()
