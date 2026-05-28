"""V10-A round 15b Phase 2 maker backtest template.

Takes a (prefix, price band, side, horizon) cell from the Becker edge
discovery agent's recommendation and runs a full backtest with:

- Train (pre split-date) / OOS (post split-date) chronological split
- Bootstrap 95% CI on mean net P&L per trade
- LOCO by sub-prefix or event_ticker prefix subgroup
- Fee-aware breakeven check
- Sample size floor n >= 100 OOS trades

Run as:
    python phase2_maker_backtest.py --prefix KXEPLGAME --side maker --px-lo 0.30 --px-hi 0.70 --split-date 2025-05-01

Note: this is the IDEALIZED maker backtest on Becker historical TRADES,
which means every trade in the data represents a REAL fill. The "maker
side" here is the side that the taker filled into; we are simulating that
the maker (limit order) was already resting at that price and got filled.
For LIVE deployment, fill rate would be lower; this backtest assumes
100% fill rate on resting orders at the trade price. That is a known
optimistic assumption documented in the F11 (Dataset Schema Phantom)
failure mode entry.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"


def get_trades_for_cell(
    prefix: str,
    px_lo: float,
    px_hi: float,
    start_date: str,
    end_date: str,
) -> "pd.DataFrame":  # type: ignore
    """Return a dataframe of trades joined to outcomes for the given cell."""
    con = duckdb.connect()
    sql = f"""
    WITH resolved AS (
        SELECT
            ticker, event_ticker, result, close_time,
            regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix_raw,
            regexp_extract(event_ticker, '^([A-Z0-9]+-?[A-Z0-9]*)', 1) AS prefix_with_sub
        FROM '{MARKETS.as_posix()}'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    )
    SELECT
        t.ticker, t.yes_price, t.no_price, t.count, t.taker_side, t.created_time,
        m.event_ticker, m.result, m.close_time,
        m.prefix_raw, m.prefix_with_sub,
        -- Maker side price (opposite of taker)
        CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0 AS maker_px,
        -- Maker wins if taker loses (taker_side != result)
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END AS maker_won,
        -- Maker gross P&L (per contract, $ notional 1.0)
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END
            - (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0) AS maker_gross
    FROM '{TRADES.as_posix()}' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE m.prefix_raw = '{prefix}'
      AND t.created_time >= '{start_date}'
      AND t.created_time < '{end_date}'
      AND (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END) / 100.0 BETWEEN {px_lo} AND {px_hi}
    """
    df = con.execute(sql).df()
    return df


def maker_fee_per_contract(px: float) -> float:
    """Kalshi maker fee per contract at maker price px."""
    return 0.25 * math.ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0


def compute_summary(df, label: str) -> dict:
    if len(df) == 0:
        return {"label": label, "n": 0}
    fees = df["maker_px"].apply(maker_fee_per_contract)
    net = df["maker_gross"] - fees
    n = len(df)
    mean_net = float(net.mean())
    sd_net = float(net.std(ddof=1))
    ci_half = 1.96 * sd_net / math.sqrt(n) if n > 1 else float("nan")
    # bootstrap CI for robust comparison
    rng = np.random.default_rng(42)
    n_boot = 1000
    boot_means = []
    arr = net.to_numpy()
    for _ in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means.append(sample.mean())
    boot_lo = float(np.percentile(boot_means, 2.5))
    boot_hi = float(np.percentile(boot_means, 97.5))
    return {
        "label": label,
        "n": n,
        "mean_net": mean_net,
        "sd_net": sd_net,
        "ci_half_normal": ci_half,
        "boot_ci_lo": boot_lo,
        "boot_ci_hi": boot_hi,
        "mean_px": float(df["maker_px"].mean()),
        "win_rate": float(df["maker_won"].mean()),
        "fee_mean": float(fees.mean()),
        "gross_mean": float(df["maker_gross"].mean()),
    }


def loco_results(df, group_col: str) -> dict:
    """Leave one out (LOCO) by group_col; report worst-case CI lower."""
    groups = df[group_col].unique()
    if len(groups) < 2:
        return {"n_groups": len(groups), "loco_min_lower": None, "details": []}
    rng = np.random.default_rng(42)
    details = []
    for g in groups:
        subset = df[df[group_col] != g]
        if len(subset) < 50:
            continue
        fees = subset["maker_px"].apply(maker_fee_per_contract)
        net = subset["maker_gross"] - fees
        arr = net.to_numpy()
        boots = []
        for _ in range(500):
            s = rng.choice(arr, size=len(arr), replace=True)
            boots.append(s.mean())
        details.append({
            "excluded": g,
            "n_remaining": len(subset),
            "mean_net": float(net.mean()),
            "boot_ci_lo": float(np.percentile(boots, 2.5)),
            "boot_ci_hi": float(np.percentile(boots, 97.5)),
        })
    if not details:
        return {"n_groups": len(groups), "loco_min_lower": None, "details": []}
    min_lower = min(d["boot_ci_lo"] for d in details)
    return {"n_groups": len(groups), "loco_min_lower": min_lower, "details": details}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", required=True, help="event_ticker prefix, e.g. KXEPLGAME")
    p.add_argument("--side", default="maker", choices=["maker", "taker"], help="Which side to backtest (maker recommended)")
    p.add_argument("--px-lo", type=float, default=0.05, help="Maker price lower bound (inclusive)")
    p.add_argument("--px-hi", type=float, default=0.95, help="Maker price upper bound (inclusive)")
    p.add_argument("--start-date", default="2024-10-01", help="Earliest trade date (post-flip)")
    p.add_argument("--split-date", default="2025-05-01", help="Train/OOS split date")
    p.add_argument("--end-date", default="2025-12-31", help="Latest trade date")
    p.add_argument("--loco-col", default="prefix_with_sub", help="Column to group LOCO by")
    p.add_argument("--output-json", default=None, help="Where to save the result")
    args = p.parse_args()

    if args.side == "taker":
        raise SystemExit("Taker side not yet implemented; use maker (Becker headline is makers win)")

    print(f"Phase 2 maker backtest: prefix={args.prefix}, "
          f"px=[{args.px_lo}, {args.px_hi}], "
          f"split={args.split_date}")
    print("=" * 80)

    t0 = time.time()
    print(f"Pulling train trades ({args.start_date} to {args.split_date}) ...")
    train = get_trades_for_cell(args.prefix, args.px_lo, args.px_hi, args.start_date, args.split_date)
    print(f"  n_train = {len(train)}")

    print(f"Pulling OOS trades ({args.split_date} to {args.end_date}) ...")
    oos = get_trades_for_cell(args.prefix, args.px_lo, args.px_hi, args.split_date, args.end_date)
    print(f"  n_oos = {len(oos)}")
    print(f"Query time: {time.time()-t0:.1f}s")

    if len(oos) < 100:
        print(f"\nGATE FAIL: OOS n = {len(oos)} < 100 floor. Insufficient sample.")
        verdict = "NULL_INSUFFICIENT_SAMPLE"
    else:
        train_summary = compute_summary(train, "train")
        oos_summary = compute_summary(oos, "OOS")
        print("\nTrain summary:")
        for k, v in train_summary.items():
            print(f"  {k}: {v}")
        print("\nOOS summary:")
        for k, v in oos_summary.items():
            print(f"  {k}: {v}")

        # Gate checks
        print("\nGate checks (OOS):")
        gate_g1 = oos_summary["boot_ci_lo"] > 0
        print(f"  G1 (OOS bootstrap CI lower > 0): {'PASS' if gate_g1 else 'FAIL'} "
              f"(lower = {oos_summary['boot_ci_lo']:+.5f})")
        gate_g2 = oos_summary["mean_net"] > 0
        print(f"  G2 (OOS mean net > 0): {'PASS' if gate_g2 else 'FAIL'} "
              f"(mean = {oos_summary['mean_net']:+.5f})")
        gate_g3 = oos_summary["n"] >= 100
        print(f"  G3 (OOS n >= 100): {'PASS' if gate_g3 else 'FAIL'}")

        # LOCO
        print(f"\nLOCO by {args.loco_col} (OOS):")
        loco = loco_results(oos, args.loco_col)
        if loco["loco_min_lower"] is not None:
            gate_g4 = loco["loco_min_lower"] > 0
            print(f"  G4 (all LOCO subsets have boot CI lower > 0): {'PASS' if gate_g4 else 'FAIL'}")
            print(f"  Worst-case LOCO boot CI lower: {loco['loco_min_lower']:+.5f}")
            for d in sorted(loco["details"], key=lambda x: x["boot_ci_lo"])[:5]:
                print(f"    Exclude {d['excluded']:30}  n={d['n_remaining']:>6}  mean={d['mean_net']:+.5f}  CI=[{d['boot_ci_lo']:+.5f}, {d['boot_ci_hi']:+.5f}]")
        else:
            gate_g4 = None
            print("  G4: SKIP (insufficient groups)")

        if gate_g1 and gate_g2 and gate_g3 and (gate_g4 is None or gate_g4):
            verdict = "PASS"
        elif gate_g1 and gate_g2 and gate_g3:
            verdict = "PARTIAL_LOCO_FRAGILE"
        else:
            verdict = "NULL"

        print(f"\nVERDICT: {verdict}")

        result = {
            "prefix": args.prefix,
            "px_range": [args.px_lo, args.px_hi],
            "split_date": args.split_date,
            "side": args.side,
            "train": train_summary,
            "oos": oos_summary,
            "loco": loco,
            "verdict": verdict,
        }
        if args.output_json:
            Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\nResult JSON written to {args.output_json}")


if __name__ == "__main__":
    main()
