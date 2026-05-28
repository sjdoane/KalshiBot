"""Phase 2c: strategy P&L simulation on MLB-night v13 centered data.

Per v13 lock Section 6. Reads:
- data/v13/joint_dataset_v13_centered.parquet (centered VWAP from Phase 2a)
- data/v13/spread_probe_summary.json (haircut_p75 from Phase 2b)
- Becker MARKETS for ticker -> realized outcome

Pre-registers thresholds from the MLB-night delta distribution BEFORE
P&L peek (per v13 lock anti-pattern ban (f)).

Writes:
- data/v13/strategy_pnl_results.json
- research/v13/02-phase2c-strategy-pnl.md
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

from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract


DATA_V13 = BASE / "data" / "v13"
RESEARCH = BASE / "research" / "v13"
MARKETS_DIR = BASE / "prediction-market-analysis" / "data" / "kalshi" / "markets"


def fetch_outcomes(tickers: list[str]) -> dict[str, str]:
    """Get realized outcome ('yes' or 'no') from Becker MARKETS via pandas."""
    print(f"  Fetching outcomes for {len(tickers)} tickers (pandas scan)...", flush=True)
    if not tickers:
        return {}
    tickers_set = set(tickers)
    outcomes: dict[str, str] = {}
    import glob
    for fp in sorted(glob.glob(str(MARKETS_DIR / "*.parquet"))):
        df = pd.read_parquet(fp, columns=["ticker", "result"])
        sub = df[df["ticker"].isin(tickers_set)]
        for r in sub.itertuples(index=False):
            outcomes[r.ticker] = r.result
        if len(outcomes) >= len(tickers_set):
            break
    return outcomes


def block_bootstrap_pnl_ci(
    pnl_per_event: pd.Series,
    days: pd.Series,
    n_boot: int = 10_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Day-block bootstrap on per-event net P&L."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"pnl": pnl_per_event.values, "day": days.values}).dropna()
    if len(df) < 5:
        return float("nan"), float("nan"), float("nan")
    unique_days = df["day"].unique()
    by_day = {d: df[df["day"] == d]["pnl"].values for d in unique_days}
    n_days = len(unique_days)
    means: list[float] = []
    for _ in range(n_boot):
        sampled = rng.choice(unique_days, size=n_days, replace=True)
        parts = [by_day[d] for d in sampled]
        boot = np.concatenate(parts)
        if len(boot) < 5:
            continue
        means.append(float(boot.mean()))
    if not means:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(means)
    return float(arr.mean()), float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def row_bootstrap_pnl_ci(
    pnl_per_event: pd.Series, n_boot: int = 10_000, seed: int = 42
) -> tuple[float, float, float]:
    """Per-event row bootstrap."""
    rng = np.random.default_rng(seed)
    arr = pnl_per_event.dropna().to_numpy()
    if len(arr) < 5:
        return float("nan"), float("nan"), float("nan")
    means: list[float] = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(float(sample.mean()))
    means_arr = np.array(means)
    return float(means_arr.mean()), float(np.percentile(means_arr, 2.5)), float(np.percentile(means_arr, 97.5))


def main() -> int:
    print("v13 Phase 2c: strategy P&L simulation", flush=True)

    df = pd.read_parquet(DATA_V13 / "joint_dataset_v13_centered.parquet")
    print(f"  Joint dataset rows: {len(df)}", flush=True)

    # MLB-night subset
    mlb_night = df[
        (df["sport_prefix"] == "KXMLBGAME")
        & (df["close_utc_hour"].isin(list(range(0, 9)) + [23]))
    ].copy()
    needed = [
        "p_sb_yes_T-6h_off+0.0h", "p_sb_yes_T-3h_off+0.0h",
        "vwap_T-6h_off+0.0h", "vwap_T-3h_off+0.0h", "vwap_T-1h_off+0.0h",
    ]
    mlb_night = mlb_night.dropna(subset=needed).copy()
    n_mlb_night = len(mlb_night)
    print(f"  MLB-night with all 3 deltas: n={n_mlb_night}", flush=True)

    # Deltas (center offset 3.5h)
    mlb_night["delta_sportsbook_pre"] = (
        mlb_night["p_sb_yes_T-3h_off+0.0h"] - mlb_night["p_sb_yes_T-6h_off+0.0h"]
    )
    mlb_night["delta_kalshi_pre"] = (
        mlb_night["vwap_T-3h_off+0.0h"] - mlb_night["vwap_T-6h_off+0.0h"]
    )

    # Pre-register thresholds from delta distribution (NO P&L peek)
    X_threshold = float(np.percentile(np.abs(mlb_night["delta_sportsbook_pre"]), 75))
    Y_threshold = float(np.percentile(np.abs(mlb_night["delta_kalshi_pre"]), 25))
    print(f"  X_threshold (75th pct |delta_sportsbook_pre|): {X_threshold:.4f}", flush=True)
    print(f"  Y_threshold (25th pct |delta_kalshi_pre|): {Y_threshold:.4f}", flush=True)

    # Read haircut from Phase 2b
    try:
        spread_summary = json.loads((DATA_V13 / "spread_probe_summary.json").read_text())
        if "haircut_p75" in spread_summary:
            haircut = float(spread_summary["haircut_p75"])
        else:
            haircut = float(spread_summary.get("haircut_p75_default", 0.02))
        print(f"  Using haircut: {haircut:.4f} (from Phase 2b)", flush=True)
    except Exception as e:
        print(f"  WARNING: cannot read Phase 2b summary ({e}); using conservative 0.02 default", flush=True)
        haircut = 0.02

    # Trigger rule
    fires = mlb_night[
        (mlb_night["delta_sportsbook_pre"].abs() >= X_threshold)
        & (mlb_night["delta_kalshi_pre"].abs() < Y_threshold)
    ].copy()
    n_fires = len(fires)
    print(f"  n_fires: {n_fires}", flush=True)

    # G2 gate is binding regardless of n_fires count below. The descriptive
    # analysis proceeds even when n_fires is small, but the verdict
    # interpretation is documented per the lock.
    g2_pass = n_fires >= 20
    if n_fires < 2:
        print("  n_fires < 2; cannot compute any descriptive P&L", flush=True)
        result = {
            "n_mlb_night": n_mlb_night, "X_threshold": X_threshold, "Y_threshold": Y_threshold,
            "haircut": haircut, "n_fires": n_fires,
            "g2_n_fires_ge_20": g2_pass,
            "abandon": "n_fires < 2",
        }
        (DATA_V13 / "strategy_pnl_results.json").write_text(json.dumps(result, indent=2, default=str))
        return 0

    # Side: YES if sportsbook moved UP, NO if DOWN
    fires["side"] = np.where(fires["delta_sportsbook_pre"] > 0, "yes", "no")
    # Execution price = Kalshi trade-print mid at T-3h + haircut
    fires["execution_price_yes"] = fires["vwap_T-3h_off+0.0h"] + haircut
    # For NO side: execution price is (1 - yes mid - haircut) = no-side ask proxy
    fires["execution_price"] = np.where(
        fires["side"] == "yes",
        fires["execution_price_yes"],
        1.0 - fires["vwap_T-3h_off+0.0h"] + haircut,
    )

    # Fetch outcomes
    outcomes = fetch_outcomes(fires["ticker"].tolist())
    fires["resolution"] = fires["ticker"].map(outcomes)
    print(f"  Resolution mapping coverage: {fires['resolution'].notna().sum()} of {n_fires}", flush=True)

    # Determine if our side won
    def side_wins(row):
        if pd.isna(row["resolution"]):
            return float("nan")
        if row["side"] == "yes":
            return 1.0 if row["resolution"] == "yes" else 0.0
        else:
            return 1.0 if row["resolution"] == "no" else 0.0

    fires["realized_outcome"] = fires.apply(side_wins, axis=1)
    fires = fires.dropna(subset=["realized_outcome"]).copy()

    # Compute fees + net P&L
    fires["fee"] = fires["execution_price"].apply(
        lambda p: kalshi_taker_fee_per_contract(price=p, contracts=1)
    )
    fires["gross_pnl"] = fires["realized_outcome"] - fires["execution_price"]
    fires["net_pnl"] = fires["gross_pnl"] - fires["fee"]

    print(f"  Final n with resolutions: {len(fires)}", flush=True)
    print(f"  Mean execution price: {fires['execution_price'].mean():.4f}", flush=True)
    print(f"  Mean fee: {fires['fee'].mean():.4f}", flush=True)
    print(f"  Mean gross P&L: {fires['gross_pnl'].mean():.4f}", flush=True)
    print(f"  Mean net P&L: {fires['net_pnl'].mean():.4f}", flush=True)
    win_rate = float((fires["net_pnl"] > 0).mean())
    print(f"  Win rate: {win_rate:.3f}", flush=True)

    # Bootstrap CI (only meaningful if n is big enough)
    if len(fires) >= 5:
        row_mean, row_lo, row_hi = row_bootstrap_pnl_ci(fires["net_pnl"])
        print(f"  Row bootstrap 95% CI: [{row_lo:.4f}, {row_hi:.4f}], mean={row_mean:.4f}", flush=True)
        fires["close_day"] = pd.to_datetime(fires["close_time"], utc=True).dt.floor("D")
        day_mean, day_lo, day_hi = block_bootstrap_pnl_ci(fires["net_pnl"], fires["close_day"])
        print(f"  Day-block bootstrap 95% CI: [{day_lo:.4f}, {day_hi:.4f}], mean={day_mean:.4f}", flush=True)
    else:
        print(f"  Bootstrap skipped (n={len(fires)} < 5); reporting raw stats only", flush=True)
        row_mean = row_lo = row_hi = day_mean = day_lo = day_hi = float("nan")
        fires["close_day"] = pd.to_datetime(fires["close_time"], utc=True).dt.floor("D")

    # Side breakdown
    yes_fires = fires[fires["side"] == "yes"]
    no_fires = fires[fires["side"] == "no"]
    print(f"  YES side: n={len(yes_fires)}, mean_net={yes_fires['net_pnl'].mean():.4f}", flush=True)
    print(f"  NO side: n={len(no_fires)}, mean_net={no_fires['net_pnl'].mean():.4f}", flush=True)

    # Save full per-fire records
    fires.to_parquet(DATA_V13 / "strategy_fires.parquet", index=False)

    # Money-deployment gate evaluation (G2-G6)
    gate = {
        "G2_n_fires_ge_20": n_fires >= 20,
        "G3_mean_net_pnl_gt_0_AND_CI_lower_gt_0": (
            fires["net_pnl"].mean() > 0 and row_lo > 0
        ),
        "G4_day_block_CI_lower_gt_0": day_lo > 0,
        "G5_haircut_p75_le_003": haircut <= 0.03,
        "G6_win_rate_gt_05": win_rate > 0.5,
    }
    print(f"\n=== Money-deployment gates G2-G6 ===", flush=True)
    for k, v in gate.items():
        print(f"  {k}: {v}", flush=True)
    all_pass = all(gate.values())
    print(f"  All G2-G6 pass: {all_pass}", flush=True)

    result = {
        "n_mlb_night": n_mlb_night, "X_threshold": X_threshold, "Y_threshold": Y_threshold,
        "haircut": haircut, "n_fires": n_fires, "n_with_resolution": len(fires),
        "mean_execution_price": float(fires["execution_price"].mean()),
        "mean_fee": float(fires["fee"].mean()),
        "mean_gross_pnl": float(fires["gross_pnl"].mean()),
        "mean_net_pnl": float(fires["net_pnl"].mean()),
        "win_rate": win_rate,
        "row_bootstrap": {"mean": row_mean, "ci_lower_95": row_lo, "ci_upper_95": row_hi},
        "day_block_bootstrap": {"mean": day_mean, "ci_lower_95": day_lo, "ci_upper_95": day_hi},
        "yes_side": {"n": len(yes_fires), "mean_net_pnl": float(yes_fires["net_pnl"].mean()) if len(yes_fires) else float("nan")},
        "no_side": {"n": len(no_fires), "mean_net_pnl": float(no_fires["net_pnl"].mean()) if len(no_fires) else float("nan")},
        "gate_g2_g6": gate,
        "all_gates_pass": all_pass,
    }
    (DATA_V13 / "strategy_pnl_results.json").write_text(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
