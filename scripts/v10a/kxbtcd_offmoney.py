"""Round 15c Track 2B: KXBTCD off-money strike analysis.

Hypothesis: the at-the-money KXBTCD strike has 1c MM-saturated spreads,
but off-money strikes (especially the deep OTM tail above current spot)
may have wider spreads, less MM competition, and larger retail
mispricing (lottery-ticket buying behavior).

Approach:
1. Pull Becker KXBTCD post-Oct-2024 trades.
2. Recover the strike from the ticker pattern KXBTCD-YYMMMDDHH-T<strike>.
3. For each trade, find the BTC spot price at trade time. Approximate
   spot using the implied YES probability of the at-the-money strike
   in the same KXBTCD event: at ATM, P(YES) approx 0.5 maps to
   spot ~ strike. More robust: use the median yes_price across all
   strikes weighted by closeness to 0.5 to back out implied spot.
4. Compute distance_pct = (strike - spot) / spot.
5. Bucket: deep OTM (>+5%), OTM (+1% to +5%), ATM (-1% to +1%),
   ITM (-5% to -1%), deep ITM (<-5%).
6. For each bucket, compute maker-side net excess return at yes_price
   >= 0.10 (loosen the v1 0.70 gate; lottery-ticket buying happens at
   low yes_price tails).
7. Event-level cluster bootstrap CI by event_ticker.

Output: research/v10a/15-kxbtcd-offmoney.{md,json}
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"
OUT_JSON = REPO / "research" / "v10a" / "15-kxbtcd-offmoney.json"
OUT_MD = REPO / "research" / "v10a" / "15-kxbtcd-offmoney.md"


def pull_kxbtcd_trades(con: duckdb.DuckDBPyConnection) -> "pd.DataFrame":
    """Pull all KXBTCD trades post Nov 2024 with maker side + ticker
    parsed (strike extracted). Returns DataFrame.
    """
    sql = f"""
    SELECT
        m.ticker AS ticker,
        m.event_ticker AS event_ticker,
        m.result AS result,
        TRY_CAST(REGEXP_EXTRACT(m.ticker, 'T([0-9.]+)$', 1) AS DOUBLE) AS strike,
        t.yes_price / 100.0 AS yes_px,
        t.no_price / 100.0 AS no_px,
        t.taker_side AS taker_side,
        t.created_time AS created_time,
        CASE WHEN m.result = 'yes' THEN 1.0 - t.yes_price/100.0
             ELSE -t.yes_price/100.0 END AS gross_yes_pl_maker,
        CASE WHEN m.result = 'no' THEN 1.0 - t.no_price/100.0
             ELSE -t.no_price/100.0 END AS gross_no_pl_maker,
        0.25 * CEIL(0.07 * (t.yes_price/100.0) * (1.0 - t.yes_price/100.0) * 100.0) / 100.0 AS fee_yes,
        0.25 * CEIL(0.07 * (t.no_price/100.0) * (1.0 - t.no_price/100.0) * 100.0) / 100.0 AS fee_no
    FROM '{TRADES.as_posix()}' t
    INNER JOIN '{MARKETS.as_posix()}' m ON t.ticker = m.ticker
    WHERE m.ticker LIKE 'KXBTCD-%'
      AND m.status = 'finalized'
      AND m.result IN ('yes', 'no')
      AND t.created_time >= '2024-11-01'
      AND t.created_time < '2025-11-25'
    """
    df = con.execute(sql).df()
    # Maker-side net P&L. If taker_side='no', maker is YES side -> uses yes_pl;
    # if taker_side='yes', maker is NO side -> uses no_pl.
    df["maker_net_pl"] = np.where(
        df["taker_side"] == "no",
        df["gross_yes_pl_maker"] - df["fee_yes"],
        df["gross_no_pl_maker"] - df["fee_no"],
    )
    df["maker_yes_px"] = np.where(df["taker_side"] == "no", df["yes_px"], df["no_px"])
    return df


def infer_spot_per_event(df) -> dict[str, float]:
    """For each event_ticker, infer the BTC spot price as the strike
    where median yes_price across event trades is closest to 0.50.

    This is a coarse proxy. A more accurate version would use the
    actual BTC spot at trade time (which Becker doesn't have), so we
    approximate by the strike whose midprice is most ATM.
    """
    import pandas as pd
    out: dict[str, float] = {}
    for event, sub in df.groupby("event_ticker"):
        per_strike = sub.groupby("strike")["yes_px"].median().reset_index()
        per_strike = per_strike.dropna(subset=["strike", "yes_px"])
        if len(per_strike) == 0:
            continue
        # Find strike whose median yes_px is closest to 0.5
        per_strike["dist"] = (per_strike["yes_px"] - 0.5).abs()
        atm_row = per_strike.loc[per_strike["dist"].idxmin()]
        out[event] = float(atm_row["strike"])
    return out


def bucket_distance(distance_pct: float) -> str:
    if distance_pct < -0.05:
        return "deep_ITM_below_-5pct"
    if distance_pct < -0.01:
        return "ITM_-5_to_-1pct"
    if distance_pct < 0.01:
        return "ATM_-1_to_+1pct"
    if distance_pct < 0.05:
        return "OTM_+1_to_+5pct"
    return "deep_OTM_above_+5pct"


def cluster_bootstrap(per_event: np.ndarray, n_boot: int = 1000,
                      seed: int = 42) -> dict:
    if len(per_event) == 0:
        return {"n": 0}
    if len(per_event) < 2:
        return {"n": 1, "event_mean": float(per_event[0])}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(per_event, size=len(per_event), replace=True).mean()
             for _ in range(n_boot)]
    return {
        "n": int(len(per_event)),
        "event_mean": float(per_event.mean()),
        "ci_lo": float(np.percentile(boots, 2.5)),
        "ci_hi": float(np.percentile(boots, 97.5)),
    }


def main():
    con = duckdb.connect()
    print("Pulling KXBTCD trades + markets...")
    df = pull_kxbtcd_trades(con)
    print(f"  {len(df)} trades on {df['event_ticker'].nunique()} events; "
          f"{df['ticker'].nunique()} unique tickers")

    # Drop trades without parseable strike or extreme prices
    df = df.dropna(subset=["strike", "yes_px"])
    df = df[(df["yes_px"] >= 0.01) & (df["yes_px"] <= 0.99)]
    print(f"  after price/strike filter: {len(df)} trades")

    spot_map = infer_spot_per_event(df)
    print(f"  inferred spot for {len(spot_map)} events")

    df["inferred_spot"] = df["event_ticker"].map(spot_map)
    df = df.dropna(subset=["inferred_spot"])
    df["distance_pct"] = (df["strike"] - df["inferred_spot"]) / df["inferred_spot"]
    df["bucket"] = df["distance_pct"].apply(bucket_distance)

    # Analyze: for each bucket x maker-yes-px range, event-level CI
    buckets = ["deep_ITM_below_-5pct", "ITM_-5_to_-1pct", "ATM_-1_to_+1pct",
               "OTM_+1_to_+5pct", "deep_OTM_above_+5pct"]
    # Loosen the price gate: lottery-ticket buying happens at 0.05 to 0.30 yes-px
    price_ranges = [
        ("yes_px_0.05_to_0.30", 0.05, 0.30),  # lottery YES buy
        ("yes_px_0.30_to_0.50", 0.30, 0.50),
        ("yes_px_0.50_to_0.70", 0.50, 0.70),
        ("yes_px_0.70_to_0.95", 0.70, 0.95),  # v1 regime
        ("yes_px_any", 0.01, 0.99),
    ]

    results: dict = {}
    for bucket in buckets:
        results[bucket] = {}
        sub_b = df[df["bucket"] == bucket]
        for label, lo, hi in price_ranges:
            sub_p = sub_b[(sub_b["maker_yes_px"] >= lo)
                          & (sub_b["maker_yes_px"] < hi)]
            n_tr = len(sub_p)
            if n_tr == 0:
                results[bucket][label] = {"n_trades": 0}
                continue
            per_event = sub_p.groupby("event_ticker")["maker_net_pl"].mean().to_numpy()
            stats = cluster_bootstrap(per_event)
            stats["n_trades"] = int(n_tr)
            results[bucket][label] = stats

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # MD summary
    lines = ["# Round 15c Track 2B: KXBTCD off-money strike analysis",
             "",
             "Method: parse strike from KXBTCD ticker (T<strike>$ suffix).",
             "Infer event-level spot by finding the strike whose median",
             "yes_price is closest to 0.50 (ATM proxy). Bucket each",
             "trade by (strike - spot) / spot. For each (bucket, price",
             "range), compute maker-side event-level cluster bootstrap",
             "CI on net P&L after Kalshi maker fees.",
             "",
             "Maker side: if taker_side='no' the maker is YES side at",
             "yes_price; if taker_side='yes' the maker is NO side at",
             "no_price. Net P&L computed accordingly.",
             "",
             "Window: Becker 2024-11-01 to 2025-11-25.",
             "",
             "## Per-bucket per-price-range results",
             ""]
    for bucket in buckets:
        lines.append(f"### {bucket}")
        lines.append("")
        lines.append("| Price range | n_trades | n_events | event_mean | CI lower | CI upper |")
        lines.append("|---|---|---|---|---|---|")
        for label, _lo, _hi in price_ranges:
            s = results[bucket].get(label, {})
            n = s.get("n", 0)
            if n == 0:
                lines.append(f"| {label} | {s.get('n_trades', 0)} | 0 | -- | -- | -- |")
                continue
            lines.append(
                f"| {label} | {s.get('n_trades', 0)} | {n} | "
                f"{s.get('event_mean', 0):+.4f} | "
                f"{s.get('ci_lo', 0):+.4f} | {s.get('ci_hi', 0):+.4f} |"
            )
        lines.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved to {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
