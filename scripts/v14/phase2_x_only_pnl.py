"""v14 Phase 2: strategy P&L with X-only trigger (no Y filter).

Per v14 lock Section 2. Same v12 MLB-night data, same haircut, same fee
model. Only the trigger rule changes: drop the Y filter.

Writes:
- data/v14/strategy_pnl_xonly.json
- data/v14/x_only_fires.parquet
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))
sys.path.insert(0, str(BASE / "scripts/v13"))

from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract
from phase2c_strategy_pnl import (
    DATA_V13, MARKETS_DIR, fetch_outcomes,
    row_bootstrap_pnl_ci, block_bootstrap_pnl_ci,
)

DATA_V14 = BASE / "data" / "v14"
DATA_V14.mkdir(parents=True, exist_ok=True)


def main() -> int:
    print("v14 Phase 2: strategy P&L (X-only trigger)", flush=True)
    df = pd.read_parquet(DATA_V13 / "joint_dataset_v13_centered.parquet")
    mlb_night = df[
        (df["sport_prefix"] == "KXMLBGAME")
        & (df["close_utc_hour"].isin(list(range(0, 9)) + [23]))
    ].copy()
    needed = [
        "p_sb_yes_T-6h_off+0.0h", "p_sb_yes_T-3h_off+0.0h",
        "vwap_T-6h_off+0.0h", "vwap_T-3h_off+0.0h", "vwap_T-1h_off+0.0h",
    ]
    mlb_night = mlb_night.dropna(subset=needed).copy()
    print(f"  MLB-night with all deltas: n={len(mlb_night)}", flush=True)

    mlb_night["delta_sportsbook_pre"] = (
        mlb_night["p_sb_yes_T-3h_off+0.0h"] - mlb_night["p_sb_yes_T-6h_off+0.0h"]
    )
    mlb_night["delta_kalshi_pre"] = (
        mlb_night["vwap_T-3h_off+0.0h"] - mlb_night["vwap_T-6h_off+0.0h"]
    )

    X_threshold = float(np.percentile(np.abs(mlb_night["delta_sportsbook_pre"]), 75))
    print(f"  X_threshold (75th pct |delta_sportsbook_pre|): {X_threshold:.4f}", flush=True)

    haircut = 0.0007  # from v13 Phase 2b

    # X-only trigger (NO Y filter)
    fires = mlb_night[mlb_night["delta_sportsbook_pre"].abs() >= X_threshold].copy()
    n_fires = len(fires)
    print(f"  n_fires (X-only): {n_fires}", flush=True)

    # Side: YES if sportsbook moved UP
    fires["side"] = np.where(fires["delta_sportsbook_pre"] > 0, "yes", "no")
    fires["execution_price_yes"] = fires["vwap_T-3h_off+0.0h"] + haircut
    fires["execution_price"] = np.where(
        fires["side"] == "yes",
        fires["execution_price_yes"],
        1.0 - fires["vwap_T-3h_off+0.0h"] + haircut,
    )

    outcomes = fetch_outcomes(fires["ticker"].tolist())
    fires["resolution"] = fires["ticker"].map(outcomes)

    def side_wins(row):
        if pd.isna(row["resolution"]):
            return float("nan")
        if row["side"] == "yes":
            return 1.0 if row["resolution"] == "yes" else 0.0
        else:
            return 1.0 if row["resolution"] == "no" else 0.0

    fires["realized_outcome"] = fires.apply(side_wins, axis=1)
    fires = fires.dropna(subset=["realized_outcome"]).copy()

    fires["fee"] = fires["execution_price"].apply(
        lambda p: kalshi_taker_fee_per_contract(price=p, contracts=1)
    )
    fires["gross_pnl"] = fires["realized_outcome"] - fires["execution_price"]
    fires["net_pnl"] = fires["gross_pnl"] - fires["fee"]

    print(f"  Final n with resolutions: {len(fires)}", flush=True)
    print(f"  YES fires: {(fires['side'] == 'yes').sum()}", flush=True)
    print(f"  NO fires: {(fires['side'] == 'no').sum()}", flush=True)
    print(f"  Mean execution price: {fires['execution_price'].mean():.4f}", flush=True)
    print(f"  Mean fee: {fires['fee'].mean():.4f}", flush=True)
    print(f"  Mean gross P&L: {fires['gross_pnl'].mean():.4f}", flush=True)
    print(f"  Mean net P&L: {fires['net_pnl'].mean():.4f}", flush=True)
    win_rate = float((fires["net_pnl"] > 0).mean())
    print(f"  Win rate: {win_rate:.3f}", flush=True)

    # YES vs NO side breakdown
    yes_fires = fires[fires["side"] == "yes"]
    no_fires = fires[fires["side"] == "no"]
    print(f"  YES side mean_net: {yes_fires['net_pnl'].mean():.4f} (n={len(yes_fires)})", flush=True)
    print(f"  NO side mean_net: {no_fires['net_pnl'].mean():.4f} (n={len(no_fires)})", flush=True)

    # Bootstrap CIs
    row_mean, row_lo, row_hi = row_bootstrap_pnl_ci(fires["net_pnl"])
    print(f"  Row bootstrap 95% CI: [{row_lo:.4f}, {row_hi:.4f}], mean={row_mean:.4f}", flush=True)
    fires["close_day"] = pd.to_datetime(fires["close_time"], utc=True).dt.floor("D")
    day_mean, day_lo, day_hi = block_bootstrap_pnl_ci(fires["net_pnl"], fires["close_day"])
    print(f"  Day-block bootstrap 95% CI: [{day_lo:.4f}, {day_hi:.4f}], mean={day_mean:.4f}", flush=True)

    fires.to_parquet(DATA_V14 / "x_only_fires.parquet", index=False)

    # Money-deployment gate evaluation
    g2 = n_fires >= 20
    g3 = fires["net_pnl"].mean() > 0 and row_lo > 0
    g4 = day_lo > 0
    g5 = haircut <= 0.03  # from v13 Phase 2b
    g6 = win_rate > 0.5
    print(f"\n=== Money-deployment gates G2-G6 ===", flush=True)
    print(f"  G2 (n_fires >= 20): {g2}", flush=True)
    print(f"  G3 (mean > 0 AND CI > 0): {g3}", flush=True)
    print(f"  G4 (day-block CI > 0): {g4}", flush=True)
    print(f"  G5 (haircut <= 0.03): {g5}", flush=True)
    print(f"  G6 (win rate > 0.5): {g6}", flush=True)
    all_pass = g2 and g3 and g4 and g5 and g6
    print(f"  All G2-G6 pass: {all_pass}", flush=True)

    result = {
        "n_mlb_night": int(len(mlb_night)),
        "X_threshold": X_threshold, "haircut": haircut,
        "n_fires": n_fires, "n_with_resolution": int(len(fires)),
        "yes_count": int(len(yes_fires)), "no_count": int(len(no_fires)),
        "mean_execution_price": float(fires["execution_price"].mean()),
        "mean_fee": float(fires["fee"].mean()),
        "mean_gross_pnl": float(fires["gross_pnl"].mean()),
        "mean_net_pnl": float(fires["net_pnl"].mean()),
        "win_rate": win_rate,
        "yes_side_mean_net": float(yes_fires["net_pnl"].mean()) if len(yes_fires) else float("nan"),
        "no_side_mean_net": float(no_fires["net_pnl"].mean()) if len(no_fires) else float("nan"),
        "row_bootstrap": {"mean": row_mean, "ci_lower_95": row_lo, "ci_upper_95": row_hi},
        "day_block_bootstrap": {"mean": day_mean, "ci_lower_95": day_lo, "ci_upper_95": day_hi},
        "gate_g2_g6": {"g2": g2, "g3": g3, "g4": g4, "g5": g5, "g6": g6},
        "all_gates_pass": all_pass,
    }
    (DATA_V14 / "strategy_pnl_xonly.json").write_text(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
