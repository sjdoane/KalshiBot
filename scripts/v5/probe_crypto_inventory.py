"""V5-C1 Kalshi crypto market inventory probe.

Enumerates Kalshi's crypto series via /historical/markets and (where
present) /series. Computes sample-size, lifetime, price band, and result
distribution per series. Writes:

  data/v5/crypto_inventory.parquet         (per-market rows)
  data/v5/crypto_inventory_summary.parquet (per-series summary)
  data/v5/crypto_inventory_meta.json       (run metadata)

Run as: uv run python -m scripts.v5.probe_crypto_inventory

READ-only against Kalshi historical endpoints. Polite throttle ~5 req/s.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import (  # noqa: E402
    KalshiClient,
    KalshiHTTPError,
)

OUT_DIR = REPO_ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Candidate crypto series prefixes per V5-C1 brief plus a wider net of
# plausible names. Each probed via /historical/markets?series_ticker=...
CRYPTO_SERIES_CANDIDATES: list[str] = [
    # Bitcoin price prediction
    "KXBTC",
    "KXBTCD",       # BTC daily
    "KXBTCH",       # BTC hourly (analogue to KXETHH)
    "KXBTCW",       # BTC weekly
    "KXBTCM",       # BTC monthly
    "KXBTCEOY",     # BTC end of year
    "KXBTCMAX",     # BTC all-time high
    "KXBTCMIN",     # BTC all-time low
    "KXBTCRANGE",   # BTC range
    "KXBTCABOVE",   # BTC above threshold
    "KXBTCBELOW",   # BTC below threshold
    "KXBTCPRICE",
    "KXBTCRES",     # BTC reserve / strategic reserve
    "KXBTCETF",     # BTC ETF flows
    "KXBTCSUPPLY",  # BTC supply / issuance
    "KXBTCHALVING",
    "KXBTCDOMINANCE",
    # Ethereum price prediction
    "KXETH",
    "KXETHD",       # ETH daily
    "KXETHH",       # ETH hourly
    "KXETHW",       # ETH weekly
    "KXETHM",       # ETH monthly
    "KXETHEOY",
    "KXETHMAX",
    "KXETHRANGE",
    "KXETHABOVE",
    "KXETHBELOW",
    "KXETHPRICE",
    "KXETHSUPPLY",
    "KXETHMERGE",
    "KXETHGAS",     # gas-fee markets
    # Other major cryptos
    "KXSOL",
    "KXSOLD",
    "KXSOLH",
    "KXSOLM",
    "KXDOGE",
    "KXDOGED",
    "KXXRP",
    "KXXRPD",
    "KXADA",
    "KXLTC",
    "KXAVAX",
    "KXMATIC",
    "KXLINK",
    # On-chain milestones
    "KXBLOCKCHAIN",
    "KXMEMECOIN",
    "KXBTCBLOCK",
    "KXETHBLOCK",
    "KXSTABLECAP",   # stablecoin market cap
    "KXUSDC",
    "KXUSDT",
    # Exchanges / events
    "KXBINANCE",
    "KXCOINBASE",
    "KXMICROSTRAT",
    "KXMSTR",
    # Crypto regulation / events
    "KXCRYPTOREG",
    "KXSEC",
]


def _coerce_ts(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return pd.to_datetime(value, utc=True, errors="coerce")
    except (ValueError, TypeError):
        return None


def fetch_cutoff(client: KalshiClient) -> pd.Timestamp | None:
    try:
        resp = client.get("/historical/cutoff")
        for k, v in (resp or {}).items():
            if "settled" in k.lower() or "cutoff" in k.lower():
                ts = _coerce_ts(v)
                if ts is not None:
                    return ts
        # fallback: any timestamp
        for v in (resp or {}).values():
            ts = _coerce_ts(v)
            if ts is not None:
                return ts
    except Exception as e:  # noqa: BLE001
        print(f"  /historical/cutoff failed: {e}", flush=True)
    return None


def probe_series_endpoint(client: KalshiClient) -> list[dict[str, Any]]:
    """Try `/series?category=Crypto` (and a few capitalization variants).
    Returns a list of series dicts if successful, empty list otherwise.
    """
    out: list[dict[str, Any]] = []
    for cat in ("Crypto", "crypto", "Cryptocurrency", "Cryptocurrencies"):
        try:
            resp = client.get("/series", category=cat)
            if not resp:
                continue
            for k in ("series", "items", "data"):
                if k in resp and isinstance(resp[k], list):
                    out.extend(resp[k])
            if out:
                print(f"  /series?category={cat} -> {len(out)} entries",
                      flush=True)
                return out
        except KalshiHTTPError as e:
            print(f"  /series?category={cat} -> {e.status}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  /series?category={cat} -> {type(e).__name__}: {e}",
                  flush=True)
    return out


def fetch_markets_for_series(
    client: KalshiClient, series_ticker: str, max_pages: int = 50,
) -> list[dict[str, Any]]:
    """Drain /historical/markets?series_ticker=... up to max_pages."""
    rows: list[dict[str, Any]] = []
    try:
        for m in client.paginate(
            "/historical/markets",
            item_key="markets",
            limit=1000,
            max_pages=max_pages,
            series_ticker=series_ticker,
        ):
            rows.append(m)
    except KalshiHTTPError as e:
        if e.status in (404, 400):
            return []
        raise
    return rows


def summarize_series(
    series_ticker: str, markets: list[dict[str, Any]],
    cutoff_ts: pd.Timestamp | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not markets:
        return pd.DataFrame(), {
            "series_ticker": series_ticker,
            "n_total": 0,
            "n_finalized": 0,
            "n_settled": 0,
            "n_yes": 0,
            "n_no": 0,
            "n_v1_eligible_band": 0,
            "earliest_close": None,
            "latest_close": None,
            "mean_lifetime_hours": None,
            "median_lifetime_hours": None,
            "mean_last_price": None,
            "mean_volume": None,
            "yes_rate": None,
            "v1_eligible_yes_rate": None,
        }
    df = pd.DataFrame(markets)
    df["series_ticker"] = series_ticker
    df["open_time"] = pd.to_datetime(
        df.get("open_time"), utc=True, errors="coerce"
    )
    df["close_time"] = pd.to_datetime(
        df.get("close_time"), utc=True, errors="coerce"
    )
    df["lifetime_hours"] = (
        (df["close_time"] - df["open_time"]).dt.total_seconds() / 3600.0
    )
    if "last_price_dollars" in df.columns:
        df["last_price"] = pd.to_numeric(
            df["last_price_dollars"], errors="coerce"
        )
    elif "last_price" in df.columns:
        df["last_price"] = pd.to_numeric(df["last_price"], errors="coerce")
        # if it's cents (>1), convert
        if df["last_price"].dropna().gt(1.5).any():
            df["last_price"] = df["last_price"] / 100.0
    else:
        df["last_price"] = pd.NA
    # volume / liquidity
    if "volume_fp" in df.columns:
        df["volume"] = pd.to_numeric(df["volume_fp"], errors="coerce")
    elif "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    else:
        df["volume"] = pd.NA
    # result distribution
    n_total = int(len(df))
    n_finalized = int((df.get("status").astype(str) == "finalized").sum()
                      if "status" in df.columns else 0)
    n_settled = int((df.get("status").astype(str) == "settled").sum()
                    if "status" in df.columns else 0)
    if "result" in df.columns:
        n_yes = int((df["result"] == "yes").sum())
        n_no = int((df["result"] == "no").sum())
    else:
        n_yes = n_no = 0
    settled_results = df[df.get("result").isin(["yes", "no"])] \
        if "result" in df.columns else df.head(0)
    yes_rate = (
        float(settled_results["result"].eq("yes").mean())
        if not settled_results.empty else None
    )
    # v1-style eligibility band: last_price in [0.70, 0.95]
    v1_band = df[
        df["last_price"].between(0.70, 0.95, inclusive="both")
        & df.get("status", "").isin(["finalized", "settled"])
        & df.get("result", "").isin(["yes", "no"])
    ] if "result" in df.columns else df.head(0)
    n_v1 = int(len(v1_band))
    v1_yes_rate = (
        float((v1_band["result"] == "yes").mean()) if n_v1 > 0 else None
    )
    summary = {
        "series_ticker": series_ticker,
        "n_total": n_total,
        "n_finalized": n_finalized,
        "n_settled": n_settled,
        "n_yes": n_yes,
        "n_no": n_no,
        "n_v1_eligible_band": n_v1,
        "earliest_close": df["close_time"].min(),
        "latest_close": df["close_time"].max(),
        "mean_lifetime_hours": float(df["lifetime_hours"].mean())
            if df["lifetime_hours"].notna().any() else None,
        "median_lifetime_hours": float(df["lifetime_hours"].median())
            if df["lifetime_hours"].notna().any() else None,
        "mean_last_price": float(df["last_price"].mean())
            if df["last_price"].notna().any() else None,
        "mean_volume": float(df["volume"].mean())
            if df["volume"].notna().any() else None,
        "yes_rate": yes_rate,
        "v1_eligible_yes_rate": v1_yes_rate,
    }
    # pre/post cutoff counts
    if cutoff_ts is not None:
        summary["n_pre_cutoff"] = int(
            (df["close_time"] < cutoff_ts).sum()
        )
        summary["n_post_cutoff"] = int(
            (df["close_time"] >= cutoff_ts).sum()
        )
    return df, summary


def main() -> int:
    settings = Settings()
    started = pd.Timestamp.utcnow()
    print(f"Started at {started.isoformat()}", flush=True)

    with KalshiClient(settings) as client:
        # 1) Cutoff
        cutoff_ts = fetch_cutoff(client)
        print(f"Kalshi historical cutoff: {cutoff_ts}", flush=True)

        # 2) Try the /series endpoint
        print("\nProbing /series?category=Crypto ...", flush=True)
        series_listing = probe_series_endpoint(client)
        listed_tickers: list[str] = []
        for s in series_listing:
            t = (s.get("ticker") or s.get("series_ticker")
                 or s.get("name") or "")
            if isinstance(t, str) and t:
                listed_tickers.append(t)
        if listed_tickers:
            print(f"  /series enumerated {len(listed_tickers)} crypto series:",
                  flush=True)
            for t in listed_tickers[:50]:
                print(f"    {t}", flush=True)

        # Combine candidate list with /series results, dedupe
        full_candidates = list(dict.fromkeys(
            CRYPTO_SERIES_CANDIDATES + listed_tickers
        ))
        print(f"\nProbing {len(full_candidates)} candidate series ...",
              flush=True)

        # 3) Per-series probe
        all_rows: list[pd.DataFrame] = []
        summaries: list[dict[str, Any]] = []
        hit_count = 0
        for series_ticker in full_candidates:
            t0 = time.time()
            try:
                markets = fetch_markets_for_series(client, series_ticker)
            except KalshiHTTPError as e:
                print(f"  {series_ticker:32s} HTTP {e.status}", flush=True)
                summaries.append({
                    "series_ticker": series_ticker,
                    "n_total": 0,
                    "http_error": e.status,
                })
                continue
            df, summ = summarize_series(series_ticker, markets, cutoff_ts)
            elapsed = time.time() - t0
            if summ["n_total"] > 0:
                hit_count += 1
                print(
                    f"  {series_ticker:32s} n={summ['n_total']:5d} "
                    f"fin={summ['n_finalized']:5d} "
                    f"v1_band={summ['n_v1_eligible_band']:4d} "
                    f"yes_rate={summ['yes_rate']} "
                    f"life_med_h={summ['median_lifetime_hours']:.1f} "
                    f"({elapsed:.1f}s)",
                    flush=True,
                )
            else:
                print(f"  {series_ticker:32s} n=0  ({elapsed:.1f}s)",
                      flush=True)
            if not df.empty:
                all_rows.append(df)
            summaries.append(summ)
            time.sleep(0.15)  # polite throttle ~6 req/s

        # 4) Persist
        summary_df = pd.DataFrame(summaries)
        summary_p = OUT_DIR / "crypto_inventory_summary.parquet"
        summary_df.to_parquet(summary_p, index=False)
        print(f"\nSummary saved -> {summary_p}", flush=True)

        markets_df = pd.DataFrame()
        if all_rows:
            # Some columns may differ across series; align by union
            markets_df = pd.concat(all_rows, ignore_index=True, sort=False)
            # Persist only a stable subset of columns to avoid pyarrow
            # mixed-type errors
            keep_cols = [
                "ticker", "series_ticker", "event_ticker", "open_time",
                "close_time", "status", "result", "last_price",
                "last_price_dollars", "volume", "lifetime_hours",
                "settlement_value", "settlement_value_dollars",
                "rules_primary", "rules_secondary",
            ]
            keep_cols = [c for c in keep_cols if c in markets_df.columns]
            markets_persist = markets_df[keep_cols].copy()
            # Cast object/string columns explicitly
            for c in ("rules_primary", "rules_secondary", "result",
                      "status", "ticker", "series_ticker", "event_ticker"):
                if c in markets_persist.columns:
                    markets_persist[c] = markets_persist[c].astype(str)
            inv_p = OUT_DIR / "crypto_inventory.parquet"
            markets_persist.to_parquet(inv_p, index=False)
            print(f"Inventory saved -> {inv_p} (n={len(markets_persist)})",
                  flush=True)

        # 5) Aggregate stats
        print()
        print("=" * 72, flush=True)
        print("AGGREGATE", flush=True)
        print("=" * 72, flush=True)
        if not markets_df.empty:
            print(f"Total crypto markets across all series:    {len(markets_df)}",
                  flush=True)
            n_final = int((markets_df.get("status").astype(str) == "finalized").sum())
            print(f"Finalized:                                  {n_final}",
                  flush=True)
            v1_mask = (
                markets_df["last_price"].between(0.70, 0.95, inclusive="both")
                & markets_df.get("status", "").astype(str).isin(["finalized", "settled"])
                & markets_df.get("result", "").isin(["yes", "no"])
            )
            n_v1 = int(v1_mask.sum())
            print(f"v1-eligible-band (price 0.70-0.95):         {n_v1}",
                  flush=True)
            if n_v1 > 0:
                sub = markets_df[v1_mask]
                v1_yes_rate = float((sub["result"] == "yes").mean())
                print(f"  yes_rate in v1 band:                       {v1_yes_rate:.3f}",
                      flush=True)
            if cutoff_ts is not None:
                pre = int((markets_df["close_time"] < cutoff_ts).sum())
                post = int((markets_df["close_time"] >= cutoff_ts).sum())
                print(f"Pre-cutoff (close<{cutoff_ts.date()}):           {pre}",
                      flush=True)
                print(f"Post-cutoff:                                {post}",
                      flush=True)
            print(f"Series with non-zero hits:                  {hit_count}",
                  flush=True)
            # Group by close-year
            cyear = markets_df["close_time"].dt.year
            print("\nClose-year distribution:", flush=True)
            for y, c in cyear.value_counts().sort_index().items():
                print(f"  {y}: {c}", flush=True)
        else:
            print("No data fetched.", flush=True)

        meta = {
            "timestamp": started.isoformat(),
            "kalshi_cutoff": cutoff_ts.isoformat() if cutoff_ts is not None else None,
            "n_candidate_series": len(full_candidates),
            "n_listed_via_series_endpoint": len(listed_tickers),
            "n_series_with_data": hit_count,
            "n_total_markets": int(len(markets_df)),
            "candidate_list": full_candidates,
            "series_endpoint_results": listed_tickers,
        }
        (OUT_DIR / "crypto_inventory_meta.json").write_text(
            json.dumps(meta, indent=2, default=str), encoding="utf-8",
        )
        print(f"\nMeta saved -> {OUT_DIR / 'crypto_inventory_meta.json'}",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
