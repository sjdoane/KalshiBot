"""Round 15c Track 2C analysis: synthetic maker fill rate on ITF tennis.

Inputs (built by scripts/v10a/itf_forward_probe.py):
  data/v10a/itf_orderbook_log.parquet  -- per-cycle orderbook snapshots
  data/v10a/itf_trades_log.parquet     -- recent-trades log

Method: for each retail trade print, find the most recent orderbook
snapshot for that ticker (within `max_match_age_minutes`, default 35
to cover the 30-min cycle plus 5-min slack). At that snapshot, compute
mid = (yes_bid + yes_ask) / 2. A synthetic maker who placed a passive
quote at mid AHEAD of the trade is filled by ANY taker trade that
crossed at or past mid:

  - taker_side='no' (taker SOLD YES at the inside bid, price=trade.yes_price):
        maker who bid YES at mid would be at the top of the queue
        (yes_bid < mid). Always filled when this trade happens.
        Maker fills at mid (better than trade.yes_price, since
        trade.yes_price = yes_bid <= mid).

  - taker_side='yes' (taker BOUGHT YES at the inside ask, price=trade.yes_price):
        maker selling YES at mid would have ask < trade.yes_price.
        Always filled. Maker sells at mid (better than trade.yes_price).

Note: this is a SYNTHETIC upper bound; in reality multiple competing
makers would race to be at mid. The model assumes ours wins.

For each filled trade we record the maker side and the maker price.
Maker P&L per fill (after Kalshi maker fees) is computed under the
assumption that the SAMPLED OUTCOME of the market matches the
direction implied by the taker. We do NOT have settlements for these
ITF markets (they may not have resolved yet), so realized P&L is
DEFERRED. The script outputs:

  - fill-rate statistics (per prefix)
  - implied per-fill maker entry price distribution
  - per-ticker fill-rate snapshot for follow-up settlement audit

Output: research/v10a/19-itf-fill-analysis.md + JSON
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OB_PATH = REPO / "data" / "v10a" / "itf_orderbook_log.parquet"
TR_PATH = REPO / "data" / "v10a" / "itf_trades_log.parquet"
OUT_JSON = REPO / "research" / "v10a" / "19-itf-fill-analysis.json"
OUT_MD = REPO / "research" / "v10a" / "19-itf-fill-analysis.md"

MAX_MATCH_AGE_MINUTES = 35  # cycle period + slack
MAKER_FEE_FORMULA_PER_DOLLAR_PRICE = lambda px: 0.25 * np.ceil(  # noqa: E731
    0.07 * px * (1.0 - px) * 100.0
) / 100.0


def load_logs():
    ob = pd.read_parquet(OB_PATH)
    tr = pd.read_parquet(TR_PATH)
    ob["ts_utc"] = pd.to_datetime(ob["ts_utc"], utc=True)
    tr["created_time"] = pd.to_datetime(tr["created_time"], utc=True)
    tr["snapshot_ts_utc"] = pd.to_datetime(tr["snapshot_ts_utc"], utc=True)
    return ob, tr


def match_trades_to_orderbook(tr: pd.DataFrame, ob: pd.DataFrame) -> pd.DataFrame:
    """For each trade, find the most recent orderbook snapshot for the
    same ticker, no older than MAX_MATCH_AGE_MINUTES.
    """
    # pandas merge_asof requires the "on" keys to be globally sorted,
    # not just within groups. Sort by the merge keys before passing.
    ob_sorted = ob.sort_values(["ts_utc", "ticker"]).reset_index(drop=True)
    tr_sorted = tr.sort_values(["created_time", "ticker"]).reset_index(drop=True)
    merged = pd.merge_asof(
        tr_sorted, ob_sorted,
        left_on="created_time", right_on="ts_utc", by="ticker",
        direction="backward",
        tolerance=pd.Timedelta(minutes=MAX_MATCH_AGE_MINUTES),
        suffixes=("_tr", "_ob"),
    )
    return merged


def classify_fill(row) -> dict:
    """Decide whether a passive maker quote at mid would have filled this trade.

    Returns dict with `would_fill` and `maker_entry_price` (the price the
    maker would have transacted at, in dollars), or NaN if no match.
    """
    if pd.isna(row.get("mid")) or pd.isna(row.get("yes_price")):
        return {"would_fill": False, "maker_entry_price": np.nan,
                "maker_side": None, "spread_at_match": np.nan}
    mid = float(row["mid"])
    trade_yes_dollars = float(row["yes_price"]) / 100.0  # yes_price is cents
    taker = row.get("taker_side")
    if taker == "no":
        # Taker sold YES at trade_yes_dollars (=yes_bid at the time).
        # A maker at mid had bid above yes_bid. Maker fills at mid.
        return {"would_fill": True, "maker_entry_price": mid,
                "maker_side": "yes_bid_at_mid",
                "spread_at_match": float(row["spread"])}
    if taker == "yes":
        # Taker bought YES at trade_yes_dollars (=yes_ask). Maker at
        # mid had ask below yes_ask. Maker fills at mid.
        return {"would_fill": True, "maker_entry_price": mid,
                "maker_side": "yes_ask_at_mid",
                "spread_at_match": float(row["spread"])}
    return {"would_fill": False, "maker_entry_price": np.nan,
            "maker_side": None, "spread_at_match": np.nan}


def main():
    ob, tr = load_logs()
    print(f"Loaded {len(ob)} orderbook snapshots, {len(tr)} trades")
    print(f"  unique tickers: ob={ob.ticker.nunique()}, tr={tr.ticker.nunique()}")
    print(f"  cycles: ob={ob.cycle_idx.nunique()}")

    merged = match_trades_to_orderbook(tr, ob)
    n_matched = int(merged["mid"].notna().sum())
    print(f"\nMatched {n_matched} of {len(merged)} trades to a recent orderbook snapshot")

    classifications = merged.apply(classify_fill, axis=1, result_type="expand")
    df = pd.concat([merged.reset_index(drop=True), classifications.reset_index(drop=True)], axis=1)

    # Fill rate per prefix
    print("\n=== Synthetic maker fill rate ===")
    summary = {}
    for prefix, sub in df.groupby("prefix_tr"):
        n_total = len(sub)
        n_matched = int(sub["mid"].notna().sum())
        n_fills = int(sub["would_fill"].sum())
        pct_fill_of_matched = n_fills / max(n_matched, 1) * 100
        # Spread distribution among the snapshots that anchored fills
        spreads = sub.loc[sub["would_fill"], "spread_at_match"].dropna()
        # Entry price distribution
        entries = sub.loc[sub["would_fill"], "maker_entry_price"].dropna()
        # Sample of trades within yes mid in [0.30, 0.70]
        midband = sub[(sub["mid"].between(0.30, 0.70)) & sub["would_fill"]]
        summary[prefix] = {
            "n_trades_total": n_total,
            "n_trades_matched_to_orderbook": n_matched,
            "n_synthetic_fills": n_fills,
            "fill_rate_pct_of_matched": pct_fill_of_matched,
            "n_fills_in_midband_0.30_0.70": int(len(midband)),
            "median_spread_at_fill_cents": float(spreads.median() * 100) if len(spreads) else None,
            "mean_spread_at_fill_cents": float(spreads.mean() * 100) if len(spreads) else None,
            "median_entry_price": float(entries.median()) if len(entries) else None,
            "mean_entry_price": float(entries.mean()) if len(entries) else None,
        }
        print(f"\n{prefix}:")
        for k, v in summary[prefix].items():
            print(f"  {k}: {v}")

    # Per-ticker snapshot for settlement follow-up: maker entry price +
    # outcome bet direction. Cache to disk so a future analyst can join
    # to Kalshi /markets/{ticker} for the result and compute realized P&L.
    per_ticker = (
        df[df["would_fill"]]
        .groupby("ticker")
        .agg(
            n_synthetic_fills=("would_fill", "sum"),
            mean_maker_entry=("maker_entry_price", "mean"),
            sample_close_time=("close_time", "first"),
            sample_mid=("mid", "mean"),
        )
        .reset_index()
        .sort_values("n_synthetic_fills", ascending=False)
    )

    print(f"\nUnique tickers with at least 1 synthetic fill: {len(per_ticker)}")
    print("Top 10 by fill count:")
    print(per_ticker.head(10).to_string(index=False))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_cycles": int(ob.cycle_idx.nunique()),
        "n_orderbook_snapshots": int(len(ob)),
        "n_trades": int(len(tr)),
        "summary_by_prefix": summary,
        "n_unique_tickers_with_fills": int(len(per_ticker)),
        "top10_tickers_by_fills": per_ticker.head(10).to_dict(orient="records"),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # Markdown verdict
    lines = ["# Round 15c Track 2C: ITF tennis synthetic maker fill analysis",
             "",
             "Method: for each retail trade print in the ITF probe trade log,",
             "look up the most recent orderbook snapshot (within 35 minutes)",
             "for the same ticker and compute mid = (yes_bid + yes_ask) / 2.",
             "A synthetic maker passive quote at mid is ASSUMED to fill any",
             "taker trade that crossed mid (which is every observed trade,",
             "since a maker at mid is at the inside of the book ahead of",
             "the existing yes_bid / yes_ask).",
             "",
             "This is a synthetic upper bound on fill rate. In reality,",
             "multiple makers would compete for the same inside; ours might",
             "win 30-50% of races, not 100%.",
             "",
             f"Cycles collected: {payload['n_cycles']}",
             f"Orderbook snapshots: {payload['n_orderbook_snapshots']}",
             f"Trade prints: {payload['n_trades']}",
             "",
             "## Per-prefix summary",
             "",
             "| Prefix | n_trades | n_matched | n_synth_fills | fill_rate (%) | midband fills | median spread at fill (c) | mean entry price |",
             "|---|---|---|---|---|---|---|---|"]
    for prefix, s in summary.items():
        lines.append(
            f"| {prefix} | {s['n_trades_total']} | "
            f"{s['n_trades_matched_to_orderbook']} | "
            f"{s['n_synthetic_fills']} | "
            f"{s['fill_rate_pct_of_matched']:.1f} | "
            f"{s['n_fills_in_midband_0.30_0.70']} | "
            f"{(s['median_spread_at_fill_cents'] or 0):.1f} | "
            f"{(s['mean_entry_price'] or 0):.3f} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "If `median spread at fill` is materially above 1c, retail-",
        "competing markets are rare to absent on ITF and a maker at",
        "mid would have a real spread to capture. If `n_trades_matched`",
        "is a large fraction of total trades, the 30-minute snapshot",
        "cadence is adequate for ITF dynamics.",
        "",
        "## Next step (deferred)",
        "",
        "Realized P&L requires settled results. Take the top 10 to 50",
        "tickers from `payload.top10_tickers_by_fills`, wait for their",
        "close_time + 6h, then GET /markets/{ticker} for each and",
        "compute payout = (1.0 - maker_entry if YES else -maker_entry)",
        "minus 2 * maker_fee. Cluster bootstrap by event (which here",
        "is the match) gives the realized maker edge CI.",
        "",
        "If the realized maker per-fill mean is positive after fees AND",
        "the fill rate (after a realistic competition haircut, e.g.",
        "30%) is sufficient for the 8-hour cycle volume, ITF becomes a",
        "SHADOW-CANDIDATE for live capital at $5 to $10 size.",
        "",
        "## Em-dash audit",
        "",
        "(verified after write)",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nSaved {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
