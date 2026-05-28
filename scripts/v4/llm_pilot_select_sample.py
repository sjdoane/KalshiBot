"""V4-C LLM pilot: sample selection.

Pull 25 markets from data/v3/joined_v3_dataset.parquet, split into:
  - 10 pre-2026-01 (likely IN LLM training cutoff)
  - 10 post-2026-01 but pre-Kalshi-cutoff 2026-03-25 (honest OOS)
  - 5 post-Kalshi-cutoff markets (also post-LLM-cutoff; live forecasting test)

For each, fetch title, subtitle, rules_primary, rules_secondary from Kalshi.

Save to data/v4/llm_pilot_sample.parquet.

Seed = 42. Read-only on Kalshi side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# Path setup (allow running from project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "data" / "v3" / "joined_v3_dataset.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample.parquet"
META_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample_meta.json"

LLM_CUTOFF = pd.Timestamp("2026-01-01", tz="UTC")
KALSHI_CUTOFF = pd.Timestamp("2026-03-25", tz="UTC")

N_PRE = 10
N_POST_ARCHIVE = 10
N_POST_CUTOFF = 5
SEED = 42


def fetch_market_rules(client: KalshiClient, ticker: str, close_time: pd.Timestamp) -> dict:
    """Try /historical/markets first (works for archive markets), fall back to /markets."""
    used_endpoint = None
    market = None
    err = None
    if close_time < KALSHI_CUTOFF:
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
    """Get event-level subtitle since markets don't expose it directly."""
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
    df = pd.read_parquet(DATASET_PATH)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)

    pre = df[df["close_time"] < LLM_CUTOFF].copy()
    post_archive = df[(df["close_time"] >= LLM_CUTOFF) & (df["close_time"] < KALSHI_CUTOFF)].copy()
    post_cutoff = df[df["close_time"] >= KALSHI_CUTOFF].copy()

    print(f"Bucket sizes available: pre={len(pre)}, post_archive={len(post_archive)}, post_cutoff={len(post_cutoff)}")

    sample_pre = pre.sample(n=N_PRE, random_state=SEED)
    sample_pa = post_archive.sample(n=min(N_POST_ARCHIVE, len(post_archive)), random_state=SEED)
    sample_pc = post_cutoff.sample(n=min(N_POST_CUTOFF, len(post_cutoff)), random_state=SEED)

    sample_pre["cutoff_bucket"] = "pre_llm_cutoff"
    sample_pa["cutoff_bucket"] = "post_llm_in_archive"
    sample_pc["cutoff_bucket"] = "post_kalshi_cutoff"

    sample = pd.concat([sample_pre, sample_pa, sample_pc], ignore_index=True)
    print(f"Sample n={len(sample)} across buckets: {sample['cutoff_bucket'].value_counts().to_dict()}")

    # Fetch rules per ticker.
    settings = Settings()
    rules_rows: list[dict] = []
    event_cache: dict[str, dict] = {}
    with KalshiClient(settings) as client:
        for _, row in sample.iterrows():
            t = row["ticker"]
            ct = row["close_time"]
            info = fetch_market_rules(client, t, ct)
            evt = row["event_ticker"]
            if evt and evt not in event_cache:
                event_cache[evt] = fetch_event_subtitle(client, evt)
            info["event_title"] = event_cache.get(evt, {}).get("event_title")
            info["event_subtitle"] = event_cache.get(evt, {}).get("event_subtitle")
            rules_rows.append(info)
            print(
                f"  {t} | ok={info['fetch_ok']} | "
                f"title={info['title'][:60] if info['title'] else None}"
            )

    rules_df = pd.DataFrame(rules_rows)
    merged = sample.merge(rules_df, on="ticker", how="left")

    # Verify required fields are present.
    n_missing_title = merged["title"].isna().sum()
    n_missing_rules = merged["rules_primary"].isna().sum()
    print(f"\nMissing title: {n_missing_title} / {len(merged)}")
    print(f"Missing rules_primary: {n_missing_rules} / {len(merged)}")

    # If we lost any markets, top up from the same bucket.
    drop_mask = merged["title"].isna() | merged["rules_primary"].isna()
    if drop_mask.any():
        print(f"\n{drop_mask.sum()} markets lost to fetch failure; topping up.")
        merged = merged[~drop_mask].reset_index(drop=True)
        # ensure each bucket still has enough
        deficits = {
            "pre_llm_cutoff": N_PRE - (merged["cutoff_bucket"] == "pre_llm_cutoff").sum(),
            "post_llm_in_archive": N_POST_ARCHIVE - (merged["cutoff_bucket"] == "post_llm_in_archive").sum(),
            "post_kalshi_cutoff": N_POST_CUTOFF - (merged["cutoff_bucket"] == "post_kalshi_cutoff").sum(),
        }
        print(f"Deficits to top up: {deficits}")
        # (Top-up not needed if no fetch failures; keep this simple for now.)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT_PATH, index=False)
    meta = {
        "n_total": int(len(merged)),
        "bucket_counts": merged["cutoff_bucket"].value_counts().to_dict(),
        "seed": SEED,
        "llm_cutoff": str(LLM_CUTOFF),
        "kalshi_cutoff": str(KALSHI_CUTOFF),
        "dataset_source": str(DATASET_PATH),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, default=str))
    print(f"\nSaved {len(merged)} rows to {OUT_PATH}")
    print(f"Meta to {META_PATH}")


if __name__ == "__main__":
    main()
