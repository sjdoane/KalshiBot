"""Phase 2a: re-run v12 Granger with v11 centered +/- 30min VWAP.

Per v13 lock Section 2: replace v12's hour-bucket forward-anchored VWAP
with v11's centered +/- 30min via direct DuckDB query.

Performance approach: pre-load all trades for matched tickers ONCE
(single SQL query), then per-event +/- 30min filtering in pandas. Avoids
both v11's 7000+ DuckDB roundtrips and v12's biased hour-bucketing.

Inputs:
- data/v11/granger_sample_events.parquet
- data/v11/odds_pulls/*.json (527 + 122 NFL extended from v12)

Outputs:
- data/v13/joint_dataset_v13_centered.parquet
- data/v13/v13_per_stratum_results.json
- research/v13/02-phase2a-centered-rerun.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime as _dt, timedelta as _td
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).parent.parent / "v11"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v12"))
from team_maps import map_event_to_team_names, parse_event_date, split_team_abbrs
from phase2b_v12_analysis import (
    BASE, DATA_V11, RESEARCH as RESEARCH_V12, PULLS,
    SPORT_OFFSETS, OFFSET_DELTAS, ALPHA_TOPLEVEL, ALPHA_NFL_WITHIN,
    BOOTSTRAP_N, SEED,
    CLASSIC_WINDOWS, EXPANDED_WINDOWS,
    load_all_pulls, per_event_implied, build_sportsbook_index,
    sportsbook_implied_team1, yes_flip, match_sample,
    classify_stratum, granger_f, block_bootstrap_gamma_ci,
)


DATA_V13 = BASE / "data" / "v13"
RESEARCH = BASE / "research" / "v13"
DATA_V13.mkdir(parents=True, exist_ok=True)
RESEARCH.mkdir(parents=True, exist_ok=True)
TRADES_GLOB = str(BASE / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet").replace("\\", "/")


def preload_trades_for_tickers(
    con: duckdb.DuckDBPyConnection, tickers: list[str]
) -> pd.DataFrame:
    """Pull all trades for the matched tickers into a single DataFrame."""
    print(f"  Pre-loading trades for {len(tickers)} tickers (single SQL)...", flush=True)
    tickers_sql = "', '".join(tickers)
    sql = f"""
    SELECT ticker, created_time, yes_price, count
    FROM '{TRADES_GLOB}'
    WHERE ticker IN ('{tickers_sql}')
    """
    df = con.execute(sql).df()
    df["created_time"] = pd.to_datetime(df["created_time"], utc=True)
    print(f"    Loaded {len(df):,} trade rows", flush=True)
    return df


def build_ticker_index(trades: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group trades by ticker, sorted by created_time, for fast +/- 30min slicing."""
    print(f"  Indexing trades by ticker...", flush=True)
    idx: dict[str, pd.DataFrame] = {}
    for ticker, g in trades.groupby("ticker"):
        g_sorted = g.sort_values("created_time").reset_index(drop=True)
        idx[ticker] = g_sorted
    return idx


def centered_30min_vwap(
    ticker_trades: pd.DataFrame, target: pd.Timestamp
) -> float:
    """v11-equivalent centered +/- 30min VWAP."""
    if ticker_trades.empty:
        return float("nan")
    lo = target - pd.Timedelta(minutes=30)
    hi = target + pd.Timedelta(minutes=30)
    mask = (ticker_trades["created_time"] >= lo) & (ticker_trades["created_time"] < hi)
    sub = ticker_trades[mask]
    if sub.empty:
        return float("nan")
    total_count = sub["count"].sum()
    if total_count <= 0:
        return float("nan")
    vwap_cents = (sub["yes_price"] * sub["count"]).sum() / total_count
    return float(vwap_cents) / 100.0


def assign_team1_yes(ticker: str, event_ticker: str, sport: str) -> bool:
    prefix = f"{sport}-"
    rest = event_ticker[len(prefix):]
    teams_str = rest[7:]
    split = split_team_abbrs(teams_str, sport)
    if split is None:
        return False
    yes_suffix = ticker.rsplit("-", 1)[1]
    return split[0] == yes_suffix


def build_joint_dataset(
    sample: pd.DataFrame,
    sb_index: dict,
    ticker_trades_index: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    print("  Building v13 joint dataset (centered VWAP)...", flush=True)
    rows: list[dict] = []
    n = len(sample)
    for i, r in enumerate(sample.itertuples(index=False)):
        if (i + 1) % 50 == 0:
            print(f"    [{i + 1}/{n}]", flush=True)
        sport = r.sport_prefix
        offset_h = SPORT_OFFSETS[sport]
        ev_date = r.event_date
        tt = ticker_trades_index.get(r.ticker, pd.DataFrame(columns=["created_time", "yes_price", "count"]))

        row_out: dict = {
            "ticker": r.ticker,
            "event_ticker": r.event_ticker,
            "sport_prefix": sport,
            "close_time": r.close_time,
            "team1_is_yes": r.team1_is_yes,
            "close_utc_hour": r.close_time.hour,
        }
        for od in OFFSET_DELTAS:
            eff = pd.Timedelta(hours=offset_h + od)
            commence_est = r.close_time - eff
            for w_label, w_h in CLASSIC_WINDOWS.items():
                target = commence_est - pd.Timedelta(hours=w_h)
                p_team1 = sportsbook_implied_team1(
                    sb_index, sport, r.team1, r.team2, target.floor("h"), ev_date,
                )
                row_out[f"p_sb_yes_{w_label}_off{od:+.1f}h"] = yes_flip(p_team1, r.team1_is_yes)
                row_out[f"vwap_{w_label}_off{od:+.1f}h"] = centered_30min_vwap(tt, target)
            if sport == "KXNFLGAME":
                for w_label, w_h in EXPANDED_WINDOWS.items():
                    target = commence_est - pd.Timedelta(hours=w_h)
                    p_team1 = sportsbook_implied_team1(
                        sb_index, sport, r.team1, r.team2, target.floor("h"), ev_date, tolerance_seconds=3600 * 2,
                    )
                    row_out[f"p_sb_yes_{w_label}_off{od:+.1f}h"] = yes_flip(p_team1, r.team1_is_yes)
                    row_out[f"vwap_{w_label}_off{od:+.1f}h"] = centered_30min_vwap(tt, target)
        rows.append(row_out)
    return pd.DataFrame(rows)


def run_stratum_granger_v13(df: pd.DataFrame, stratum: str, use_nfl_b: bool = False) -> dict:
    if stratum == "NFL" and use_nfl_b:
        wins_keys = list(EXPANDED_WINDOWS.keys())
    else:
        wins_keys = list(CLASSIC_WINDOWS.keys())
    out: dict = {}
    for od in OFFSET_DELTAS:
        sb6 = f"p_sb_yes_{wins_keys[0]}_off{od:+.1f}h"
        sb3 = f"p_sb_yes_{wins_keys[1]}_off{od:+.1f}h"
        v6 = f"vwap_{wins_keys[0]}_off{od:+.1f}h"
        v3 = f"vwap_{wins_keys[1]}_off{od:+.1f}h"
        v1 = f"vwap_{wins_keys[2]}_off{od:+.1f}h"
        if sb6 not in df.columns:
            return {"error": "columns missing"}
        d = df.copy()
        d[f"delta_sb_{od:+.1f}"] = d[sb3] - d[sb6]
        d[f"delta_k_pre_{od:+.1f}"] = d[v3] - d[v6]
        d[f"delta_k_post_{od:+.1f}"] = d[v1] - d[v3]
        result = granger_f(
            d[f"delta_k_post_{od:+.1f}"].to_numpy(),
            d[f"delta_k_pre_{od:+.1f}"].to_numpy(),
            d[f"delta_sb_{od:+.1f}"].to_numpy(),
        )
        out[f"offset{od:+.1f}h"] = result
        if od == 0.0:
            mg, lo, hi = block_bootstrap_gamma_ci(
                d, f"delta_k_post_{od:+.1f}", f"delta_k_pre_{od:+.1f}", f"delta_sb_{od:+.1f}"
            )
            out["block_bootstrap_center"] = {"gamma_mean": mg, "ci_lower_95": lo, "ci_upper_95": hi}
    return out


def evaluate_gate_v13(sr: dict, name: str, n: int) -> dict:
    """v13 gate: center Bonferroni AND adjacent uncorrected 0.05.

    Two-level offset robustness per v13 lock Section 4(d):
    - Level 1 (hard): center passes Bonferroni 0.0125 (or NFL 0.00625)
    - Level 2 (soft): both adjacent offsets pass uncorrected 0.05
    """
    alpha_center = ALPHA_NFL_WITHIN if name == "NFL" else ALPHA_TOPLEVEL
    alpha_adjacent = 0.05  # uncorrected for the level-2 check
    has_n = n >= 50

    center = sr.get("offset+0.0h", {})
    level1_pass = (
        not pd.isna(center.get("p", float("nan")))
        and center.get("p", float("nan")) <= alpha_center
        and center.get("gamma", float("nan")) > 0
    )

    adjacent_passes: list[bool] = []
    for od in [-0.5, 0.5]:
        r = sr.get(f"offset{od:+.1f}h", {})
        passes = (
            not pd.isna(r.get("p", float("nan")))
            and r.get("p", float("nan")) <= alpha_adjacent
            and r.get("gamma", float("nan")) > 0
        )
        adjacent_passes.append(passes)
    level2_pass = all(adjacent_passes)

    bb = sr.get("block_bootstrap_center", {})
    ci_lo = bb.get("ci_lower_95")
    bb_pass = (ci_lo is not None) and (not pd.isna(ci_lo)) and (ci_lo > 0)

    overall = has_n and level1_pass and level2_pass and bb_pass
    return {
        "stratum": name, "n": n, "alpha_center": alpha_center,
        "has_n_floor": has_n, "level1_pass": level1_pass,
        "level2_pass": level2_pass, "adjacent_passes": adjacent_passes,
        "block_bootstrap_pass": bb_pass, "block_bootstrap": bb,
        "center": center, "overall_pass": overall,
    }


def main() -> int:
    print("v13 Phase 2a: Granger re-run with v11 centered VWAP", flush=True)
    sample = pd.read_parquet(DATA_V11 / "granger_sample_events.parquet")
    print(f"  Sample events: {len(sample)}", flush=True)

    odds = load_all_pulls()
    print(f"  Raw odds rows: {len(odds)}", flush=True)
    odds_per_event = per_event_implied(odds)
    print(f"  Per-event rows: {len(odds_per_event)}", flush=True)
    sb_index = build_sportsbook_index(odds_per_event)
    print(f"  Indexed sportsbook keys: {len(sb_index)}", flush=True)

    sample = match_sample(sample)
    print(f"  Matched after parse: {len(sample)}", flush=True)

    con = duckdb.connect()
    tickers = sample["ticker"].unique().tolist()
    trades = preload_trades_for_tickers(con, tickers)
    ticker_trades_index = build_ticker_index(trades)

    df = build_joint_dataset(sample, sb_index, ticker_trades_index)
    df.to_parquet(DATA_V13 / "joint_dataset_v13_centered.parquet", index=False)
    print(f"  Joint dataset rows: {len(df)}", flush=True)

    print("--- Per-stratum Granger + v13 gate...", flush=True)
    results: dict = {}
    for stratum in ["MLB-day", "MLB-night", "NBA", "NFL"]:
        st = classify_stratum(df, stratum)
        n_with = st.dropna(
            subset=[
                "p_sb_yes_T-6h_off+0.0h", "p_sb_yes_T-3h_off+0.0h",
                "vwap_T-6h_off+0.0h", "vwap_T-3h_off+0.0h", "vwap_T-1h_off+0.0h",
            ]
        )
        n = len(n_with)
        print(f"  Stratum {stratum}: n={n}", flush=True)
        if stratum == "NFL":
            ra = run_stratum_granger_v13(st, "NFL", use_nfl_b=False)
            rb = run_stratum_granger_v13(st, "NFL", use_nfl_b=True)
            ga = evaluate_gate_v13(ra, "NFL", n)
            gb = evaluate_gate_v13(rb, "NFL", n)
            results["NFL-A"] = {"raw_results": ra, "gate": ga}
            results["NFL-B"] = {"raw_results": rb, "gate": gb}
            results["NFL-combined"] = {
                "passes": ga["overall_pass"] or gb["overall_pass"],
                "via": "A" if ga["overall_pass"] else ("B" if gb["overall_pass"] else "neither"),
            }
            print(f"    NFL-A center: F={ra.get('offset+0.0h', {}).get('F', float('nan')):.4f}, p={ra.get('offset+0.0h', {}).get('p', float('nan')):.6f}, gamma={ra.get('offset+0.0h', {}).get('gamma', float('nan')):.4f}", flush=True)
            print(f"    NFL-B center: F={rb.get('offset+0.0h', {}).get('F', float('nan')):.4f}, p={rb.get('offset+0.0h', {}).get('p', float('nan')):.6f}, gamma={rb.get('offset+0.0h', {}).get('gamma', float('nan')):.4f}", flush=True)
        else:
            r = run_stratum_granger_v13(st, stratum)
            g = evaluate_gate_v13(r, stratum, n)
            results[stratum] = {"raw_results": r, "gate": g}
            c = r.get("offset+0.0h", {})
            bb = r.get("block_bootstrap_center", {})
            adj_minus = r.get("offset-0.5h", {})
            adj_plus = r.get("offset+0.5h", {})
            print(
                f"    -0.5h: F={adj_minus.get('F', float('nan')):.4f}, p={adj_minus.get('p', float('nan')):.6f}, gamma={adj_minus.get('gamma', float('nan')):.4f}",
                flush=True,
            )
            print(
                f"    center: F={c.get('F', float('nan')):.4f}, p={c.get('p', float('nan')):.6f}, gamma={c.get('gamma', float('nan')):.4f}, bb_ci_lower={bb.get('ci_lower_95', float('nan')):.4f}",
                flush=True,
            )
            print(
                f"    +0.5h: F={adj_plus.get('F', float('nan')):.4f}, p={adj_plus.get('p', float('nan')):.6f}, gamma={adj_plus.get('gamma', float('nan')):.4f}",
                flush=True,
            )
            print(f"    L1: {g['level1_pass']}, L2: {g['level2_pass']}, bb: {g['block_bootstrap_pass']}, overall: {g['overall_pass']}", flush=True)

    n_pass = sum(1 for s in ["MLB-day", "MLB-night", "NBA"] if results.get(s, {}).get("gate", {}).get("overall_pass", False))
    if results.get("NFL-combined", {}).get("passes", False):
        n_pass += 1
    print(f"\n=== v13 GRANGER GATE: {n_pass} of 4 strata pass ===", flush=True)
    results["GRANGER_VERDICT"] = {"n_passing": n_pass}
    (DATA_V13 / "v13_per_stratum_results.json").write_text(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
