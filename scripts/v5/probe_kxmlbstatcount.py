"""V5-B1: probe Kalshi player-prop series (KXMLBSTATCOUNT and analogs).

Pulls full settled markets from /markets for each prop series prefix,
saves to data/v5/kxmlbstatcount_inventory.parquet, and emits a summary
JSON. Polite throttle.

This is the player-prop inventory for the v5 Track B feasibility study.
The cutoff for /historical/markets is 2026-03-25; all of these series
opened after that cutoff, so /historical returns zero rows. We pull
via /markets?status=settled instead, which returns the full
operationally-settled set ("live but past-close" archive).

Run: uv run python -m scripts.v5.probe_kxmlbstatcount
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERIES_LIST = [
    "KXMLBSTATCOUNT",
    "KXMLBHIT",
    "KXMLBHR",
    "KXMLBHRR",
    "KXMLBKS",
]


def fetch_series_full(client: KalshiClient, series: str, max_pages: int = 200) -> list[dict]:
    """Page through /markets?status=settled for a series_ticker."""
    out: list[dict] = []
    cursor: str | None = None
    page = 0
    while True:
        params: dict[str, object] = {
            "series_ticker": series,
            "limit": 1000,
            "status": "settled",
        }
        if cursor:
            params["cursor"] = cursor
        resp = client._request("GET", "/markets", params=params)
        if not isinstance(resp, dict):
            break
        ms = resp.get("markets", [])
        cursor = resp.get("cursor")
        out.extend(ms)
        page += 1
        if not cursor or len(ms) == 0:
            break
        time.sleep(0.15)
        if page >= max_pages:
            print(f"  [{series}] hit max_pages={max_pages}")
            break
    return out


def main() -> None:
    settings = Settings()
    all_rows: list[dict] = []
    summary: dict[str, dict] = {}

    with KalshiClient(settings) as client:
        cut = client._request("GET", "/historical/cutoff")
        print(f"Historical cutoff: {cut}")
        summary["_cutoff"] = cut
        for series in SERIES_LIST:
            print(f"--- Fetching {series} ---")
            start = time.time()
            ms = fetch_series_full(client, series)
            wall = time.time() - start
            print(f"  n={len(ms)} wall={wall:.1f}s")
            for m in ms:
                m["_series_prefix"] = series
            all_rows.extend(ms)
            summary[series] = {
                "n_total_settled": len(ms),
                "wall_seconds": wall,
            }

    df = pd.DataFrame(all_rows)
    if not df.empty:
        out_path = OUT_DIR / "kxmlbstatcount_inventory.parquet"
        df.to_parquet(out_path)
        print(f"\nWrote {out_path}  shape={df.shape}")

        # Series-level summary
        for series in SERIES_LIST:
            sdf = df[df["_series_prefix"] == series]
            if sdf.empty:
                continue
            result_counts = sdf["result"].value_counts().to_dict()
            n_binary = int(sdf["result"].isin(["yes", "no"]).sum())
            n_scalar = int(sdf["result"].isin(["scalar"]).sum())
            px = pd.to_numeric(sdf["last_price_dollars"], errors="coerce")
            ct = pd.to_datetime(sdf["close_time"], format="mixed", errors="coerce", utc=True)
            ot = pd.to_datetime(sdf["open_time"], format="mixed", errors="coerce", utc=True)
            life_h = (ct - ot).dt.total_seconds() / 3600
            summary[series].update({
                "result_counts": {str(k): int(v) for k, v in result_counts.items()},
                "n_binary_resolved": n_binary,
                "n_scalar": n_scalar,
                "yes_rate_binary": float((sdf["result"] == "yes").sum() / max(n_binary, 1)),
                "mean_lifetime_hours": float(life_h.mean()) if life_h.notna().any() else None,
                "median_lifetime_hours": float(life_h.median()) if life_h.notna().any() else None,
                "p10_lifetime_hours": float(life_h.quantile(0.10)) if life_h.notna().any() else None,
                "p90_lifetime_hours": float(life_h.quantile(0.90)) if life_h.notna().any() else None,
                "mean_last_price": float(px.mean()) if px.notna().any() else None,
                "median_last_price": float(px.median()) if px.notna().any() else None,
                "q25_last_price": float(px.quantile(0.25)) if px.notna().any() else None,
                "q75_last_price": float(px.quantile(0.75)) if px.notna().any() else None,
                "n_in_70_95_band": int(((px >= 0.70) & (px <= 0.95)).sum()),
                "n_in_30_70_band": int(((px >= 0.30) & (px <= 0.70)).sum()),
                "n_distinct_events": int(sdf["event_ticker"].nunique()) if "event_ticker" in sdf.columns else None,
                "n_distinct_participants": int(sdf["primary_participant_key"].nunique()) if "primary_participant_key" in sdf.columns else None,
                "close_time_min": str(ct.min()),
                "close_time_max": str(ct.max()),
            })

    out_summary = OUT_DIR / "kxmlbstatcount_inventory_summary.json"
    out_summary.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Wrote {out_summary}")


if __name__ == "__main__":
    main()
