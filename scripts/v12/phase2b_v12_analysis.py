"""Phase 2b: v12 Granger analysis with all pre-registered fixes.

Per v12 lock Section 7 binding gates:
- 4 strata: MLB-day, MLB-night, NBA, NFL (with OR-of-2 sub-test NFL-A and NFL-B)
- Sport-specific commence offsets with +/- 0.5h robustness range
- Block-bootstrap 95% CI on gamma at block_size = 1 calendar day
- Top-level Bonferroni alpha = 0.05/4 = 0.0125
- Within-NFL Bonferroni alpha = 0.05/8 = 0.00625

Performance: pre-aggregates Kalshi VWAPs once via DuckDB single-query;
pre-indexes sportsbook odds by (sport, commence_date, frozenset of teams).
Avoids the 7000+ DuckDB-roundtrip pattern that hung the original v0.
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

# Force unbuffered output so progress prints reach the operator log
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).parent.parent / "v11"))
from team_maps import map_event_to_team_names, parse_event_date, split_team_abbrs


BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis" / "data" / "kalshi"
TRADES_GLOB = str(BECKER / "trades" / "*.parquet").replace("\\", "/")
DATA_V11 = BASE / "data" / "v11"
DATA_V12 = BASE / "data" / "v12"
PULLS = DATA_V11 / "odds_pulls"
RESEARCH = BASE / "research" / "v12"

CLASSIC_WINDOWS = {"T-6h": 6, "T-3h": 3, "T-1h": 1}
EXPANDED_WINDOWS = {"T-24h": 24, "T-18h": 18, "T-12h": 12}

SPORT_OFFSETS = {"KXMLBGAME": 3.5, "KXNBAGAME": 2.5, "KXNFLGAME": 3.5}
OFFSET_DELTAS = [-0.5, 0.0, 0.5]

ALPHA_TOPLEVEL = 0.05 / 4
ALPHA_NFL_WITHIN = 0.05 / 8

BOOTSTRAP_N = 10_000
SEED = 42


def parse_snapshot_filename(p: Path) -> tuple[str, pd.Timestamp]:
    stem = p.stem
    sport, ts = stem.split("__")
    return sport, pd.Timestamp(ts).tz_localize("UTC")


def load_all_pulls() -> pd.DataFrame:
    print("  Loading all odds pulls...", flush=True)
    rows: list[dict] = []
    for p in sorted(PULLS.glob("*.json")):
        sport, snap_t = parse_snapshot_filename(p)
        body = json.loads(p.read_text())
        for g in body.get("data", []):
            commence = pd.Timestamp(g["commence_time"])
            for bk in g.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk.get("key") != "h2h":
                        continue
                    outs = mk.get("outcomes", [])
                    if len(outs) != 2:
                        continue
                    for o in outs:
                        rows.append(
                            {
                                "sport_prefix": sport,
                                "snapshot_time": snap_t,
                                "commence_time": commence,
                                "home_team": g.get("home_team"),
                                "away_team": g.get("away_team"),
                                "bookmaker": bk.get("key"),
                                "team": o.get("name"),
                                "decimal_odds": o.get("price"),
                            }
                        )
    return pd.DataFrame(rows)


def per_event_implied(odds: pd.DataFrame) -> pd.DataFrame:
    print("  Collapsing to per-event implied probabilities...", flush=True)
    odds = odds.copy()
    odds["implied"] = 1.0 / odds["decimal_odds"].clip(lower=1e-9)
    grp = odds.groupby(
        ["sport_prefix", "snapshot_time", "commence_time", "home_team", "away_team"]
    )
    rows: list[dict] = []
    for (sport, snap_t, commence, home, away), g in grp:
        per_book = g.groupby("bookmaker")
        home_imps: list[float] = []
        for _, gb in per_book:
            hr = gb[gb["team"] == home]
            ar = gb[gb["team"] == away]
            if hr.empty or ar.empty:
                continue
            p_h = float(hr["implied"].iloc[0])
            p_a = float(ar["implied"].iloc[0])
            s = p_h + p_a
            if s <= 0:
                continue
            home_imps.append(p_h / s)
        if not home_imps:
            continue
        rows.append(
            {
                "sport_prefix": sport,
                "snapshot_time": snap_t,
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "home_implied_median": float(np.median(home_imps)),
                "n_bookmakers": len(home_imps),
            }
        )
    return pd.DataFrame(rows)


def build_sportsbook_index(odds_per_event: pd.DataFrame) -> dict:
    """Index (sport, commence_date, frozenset_teams) -> list[(snap_time, home, p_home)].

    O(1) lookup for matching events.
    """
    print("  Indexing sportsbook odds...", flush=True)
    odds_per_event = odds_per_event.copy()
    odds_per_event["commence_date"] = (
        pd.to_datetime(odds_per_event["commence_time"], utc=True).dt.date.astype(str)
    )
    idx: dict = {}
    for r in odds_per_event.itertuples(index=False):
        key = (r.sport_prefix, r.commence_date, frozenset({r.home_team, r.away_team}))
        idx.setdefault(key, []).append(
            (pd.Timestamp(r.snapshot_time), r.home_team, float(r.home_implied_median))
        )
    return idx


def precompute_kalshi_hourly_vwap(
    con: duckdb.DuckDBPyConnection, tickers: list[str]
) -> dict:
    """Single SQL query that returns (ticker, hour_floor_utc) -> VWAP_yes (in dollars).

    Hour-floor means trades grouped by floor(created_time, hour) so a target
    hour T maps to all trades in [T, T+1h).
    """
    print(
        f"  Pre-aggregating Kalshi VWAPs across {len(tickers)} tickers (1 SQL query)...",
        flush=True,
    )
    if not tickers:
        return {}
    tickers_sql = "', '".join(tickers)
    sql = f"""
    SELECT ticker, date_trunc('hour', created_time AT TIME ZONE 'UTC') AS hour_utc,
           SUM(yes_price * count) / NULLIF(SUM(count), 0) AS vwap
    FROM '{TRADES_GLOB}'
    WHERE ticker IN ('{tickers_sql}')
    GROUP BY ticker, hour_utc
    """
    df = con.execute(sql).df()
    print(f"    Got {len(df)} (ticker, hour) VWAP cells", flush=True)
    out: dict = {}
    for r in df.itertuples(index=False):
        out[(r.ticker, pd.Timestamp(r.hour_utc).tz_localize("UTC"))] = (
            float(r.vwap) / 100.0
        )
    return out


def kalshi_window_vwap(
    vwap_index: dict,
    ticker: str,
    target: pd.Timestamp,
) -> float:
    """Single-bucket VWAP lookup at floor(target, hour).

    Matches v11 phase2_step2_granger.py's behavior: trades in
    [floor(target), floor(target)+1h) which is approximately +/- 30min
    of the typical target time. If the operator wants a wider window,
    pre-aggregate at finer granularity instead of averaging buckets.
    """
    target_h = target.floor("h")
    v = vwap_index.get((ticker, target_h))
    return float(v) if v is not None and not pd.isna(v) else float("nan")


def sportsbook_implied_team1(
    sb_index: dict,
    sport: str,
    team1: str,
    team2: str,
    target_h: pd.Timestamp,
    event_date: str,
    tolerance_seconds: int = 3600,
) -> float:
    """Return team1's implied probability at the closest snapshot to
    target_h. Determines team1 vs team2 by checking the matching snapshot's
    home_team field directly (matches v11 per-snapshot logic).
    """
    try:
        d0 = _dt.strptime(event_date, "%Y-%m-%d")
        candidates = [
            event_date,
            (d0 + _td(days=1)).strftime("%Y-%m-%d"),
            (d0 - _td(days=1)).strftime("%Y-%m-%d"),
        ]
    except Exception:
        candidates = [event_date]
    team_set = frozenset({team1, team2})
    best: tuple[int, float, str] | None = None
    for cd in candidates:
        key = (sport, cd, team_set)
        if key not in sb_index:
            continue
        for snap_t, home, p_home in sb_index[key]:
            diff = abs((snap_t - target_h).total_seconds())
            if diff > tolerance_seconds:
                continue
            if best is None or diff < best[0]:
                best = (diff, p_home, home)
    if best is None:
        return float("nan")
    _, p_home, home_team_actual = best
    if home_team_actual == team1:
        return p_home
    if home_team_actual == team2:
        return 1.0 - p_home
    return float("nan")


def yes_flip(p: float, team1_is_yes: bool) -> float:
    if pd.isna(p):
        return float("nan")
    return p if team1_is_yes else 1.0 - p


def assign_team1_yes(ticker: str, event_ticker: str, sport: str) -> bool:
    prefix = f"{sport}-"
    rest = event_ticker[len(prefix):]
    teams_str = rest[7:]
    split = split_team_abbrs(teams_str, sport)
    if split is None:
        return False
    yes_suffix = ticker.rsplit("-", 1)[1]
    return split[0] == yes_suffix


def match_sample(sample: pd.DataFrame) -> pd.DataFrame:
    sample = sample.copy()
    sample["close_time"] = pd.to_datetime(sample["close_time"], utc=True)
    sample["event_date"] = sample["event_ticker"].apply(
        lambda et: parse_event_date(et, et.split("-")[0])
    )
    sample["teams_parsed"] = sample.apply(
        lambda r: map_event_to_team_names(r["event_ticker"], r["sport_prefix"]),
        axis=1,
    )
    sample = sample[sample["teams_parsed"].notna()].copy()
    sample[["team1", "team2"]] = pd.DataFrame(
        sample["teams_parsed"].tolist(), index=sample.index
    )
    sample["team1_is_yes"] = sample.apply(
        lambda r: assign_team1_yes(r["ticker"], r["event_ticker"], r["sport_prefix"]),
        axis=1,
    )
    return sample


def build_v12_dataset(
    sample: pd.DataFrame, sb_index: dict, vwap_index: dict
) -> pd.DataFrame:
    print("  Building v12 joint dataset...", flush=True)
    rows: list[dict] = []
    n = len(sample)
    for i, r in enumerate(sample.itertuples(index=False)):
        if (i + 1) % 50 == 0:
            print(f"    [{i + 1}/{n}]", flush=True)
        sport = r.sport_prefix
        offset_h = SPORT_OFFSETS[sport]
        ev_date = r.event_date

        row_out: dict = {
            "ticker": r.ticker,
            "event_ticker": r.event_ticker,
            "sport_prefix": sport,
            "close_time": r.close_time,
            "team1_is_yes": r.team1_is_yes,
            "close_utc_hour": r.close_time.hour,
        }
        for od in OFFSET_DELTAS:
            eff_offset = pd.Timedelta(hours=offset_h + od)
            commence_est = r.close_time - eff_offset
            for w_label, w_h in CLASSIC_WINDOWS.items():
                target = commence_est - pd.Timedelta(hours=w_h)
                p_team1 = sportsbook_implied_team1(
                    sb_index, sport, r.team1, r.team2, target.floor("h"), ev_date,
                )
                row_out[f"p_sb_yes_{w_label}_off{od:+.1f}h"] = yes_flip(
                    p_team1, r.team1_is_yes
                )
                row_out[f"vwap_{w_label}_off{od:+.1f}h"] = kalshi_window_vwap(
                    vwap_index, r.ticker, target
                )
            if sport == "KXNFLGAME":
                for w_label, w_h in EXPANDED_WINDOWS.items():
                    target = commence_est - pd.Timedelta(hours=w_h)
                    p_team1 = sportsbook_implied_team1(
                        sb_index, sport, r.team1, r.team2, target.floor("h"),
                        ev_date, tolerance_seconds=3600 * 2,
                    )
                    row_out[f"p_sb_yes_{w_label}_off{od:+.1f}h"] = yes_flip(
                        p_team1, r.team1_is_yes
                    )
                    row_out[f"vwap_{w_label}_off{od:+.1f}h"] = kalshi_window_vwap(
                        vwap_index, r.ticker, target
                    )
        rows.append(row_out)
    return pd.DataFrame(rows)


def granger_f(y: np.ndarray, x_pre: np.ndarray, x_sb: np.ndarray) -> dict:
    mask = ~np.isnan(y) & ~np.isnan(x_pre) & ~np.isnan(x_sb)
    y, x1, x2 = y[mask], x_pre[mask], x_sb[mask]
    n = len(y)
    if n < 10:
        return {"F": float("nan"), "p": float("nan"), "gamma": float("nan"), "gamma_se": float("nan"), "n": n}
    X_r = np.column_stack([np.ones(n), x1])
    beta_r, *_ = np.linalg.lstsq(X_r, y, rcond=None)
    ss_r = float(np.sum((y - X_r @ beta_r) ** 2))
    X_u = np.column_stack([np.ones(n), x1, x2])
    beta_u, *_ = np.linalg.lstsq(X_u, y, rcond=None)
    ss_u = float(np.sum((y - X_u @ beta_u) ** 2))
    df1, df2 = 1, n - 3
    if ss_u <= 0 or df2 <= 0:
        return {"F": float("nan"), "p": float("nan"), "gamma": float("nan"), "gamma_se": float("nan"), "n": n}
    F = ((ss_r - ss_u) / df1) / (ss_u / df2)
    p = 1.0 - stats.f.cdf(F, df1, df2)
    XtX_inv = np.linalg.inv(X_u.T @ X_u)
    gamma_se = float(np.sqrt((ss_u / df2) * XtX_inv[2, 2]))
    return {"F": float(F), "p": float(p), "gamma": float(beta_u[2]), "gamma_se": gamma_se, "n": n}


def block_bootstrap_gamma_ci(
    df: pd.DataFrame, post_col: str, pre_col: str, sb_col: str
) -> tuple[float, float, float]:
    rng = np.random.default_rng(SEED)
    df = df.dropna(subset=[post_col, pre_col, sb_col]).copy()
    df["day"] = pd.to_datetime(df["close_time"], utc=True).dt.floor("D")
    days = df["day"].unique()
    if len(days) < 5:
        return float("nan"), float("nan"), float("nan")
    by_day = {d: df[df["day"] == d] for d in days}
    n_days = len(days)
    gammas: list[float] = []
    for _ in range(BOOTSTRAP_N):
        sampled = rng.choice(days, size=n_days, replace=True)
        parts = [by_day[d] for d in sampled]
        boot = pd.concat(parts, ignore_index=True)
        y = boot[post_col].to_numpy()
        x1 = boot[pre_col].to_numpy()
        x2 = boot[sb_col].to_numpy()
        if len(y) < 10:
            continue
        X_u = np.column_stack([np.ones(len(y)), x1, x2])
        try:
            beta_u, *_ = np.linalg.lstsq(X_u, y, rcond=None)
            gammas.append(float(beta_u[2]))
        except Exception:
            continue
    if not gammas:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(gammas)
    return float(np.mean(arr)), float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def classify_stratum(df: pd.DataFrame, name: str) -> pd.DataFrame:
    if name == "MLB-day":
        return df[(df["sport_prefix"] == "KXMLBGAME") & df["close_utc_hour"].between(17, 22, inclusive="both")]
    elif name == "MLB-night":
        return df[(df["sport_prefix"] == "KXMLBGAME") & (df["close_utc_hour"].isin(list(range(0, 9)) + [23]))]
    elif name == "NBA":
        return df[df["sport_prefix"] == "KXNBAGAME"]
    elif name == "NFL":
        return df[df["sport_prefix"] == "KXNFLGAME"]
    return df.iloc[0:0]


def run_stratum_granger(df: pd.DataFrame, stratum: str, use_nfl_b: bool = False) -> dict:
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


def evaluate_gate(sr: dict, name: str, n: int) -> dict:
    alpha = ALPHA_NFL_WITHIN if name == "NFL" else ALPHA_TOPLEVEL
    has_n = n >= 50
    pass_offsets = []
    for od in OFFSET_DELTAS:
        r = sr.get(f"offset{od:+.1f}h", {})
        if "p" in r and not pd.isna(r["p"]):
            passes = r["p"] <= alpha and r["gamma"] > 0
        else:
            passes = False
        pass_offsets.append({"offset": od, "passes": passes, "p": r.get("p"), "gamma": r.get("gamma")})
    offset_robust = all(po["passes"] for po in pass_offsets)
    bb = sr.get("block_bootstrap_center", {})
    ci_lo = bb.get("ci_lower_95")
    bb_pass = (ci_lo is not None) and (not pd.isna(ci_lo)) and (ci_lo > 0)
    center = sr.get("offset+0.0h", {})
    overall = (
        has_n
        and (center.get("p", float("nan")) <= alpha)
        and (center.get("gamma", float("nan")) > 0)
        and offset_robust
        and bb_pass
    )
    return {
        "stratum": name, "n": n, "alpha_used": alpha, "has_n_floor": has_n,
        "center": center, "offset_robust": offset_robust, "per_offset": pass_offsets,
        "block_bootstrap": bb, "block_bootstrap_pass": bb_pass, "overall_pass": overall,
    }


def main() -> int:
    print("v12 Phase 2b: Granger analysis (refined)", flush=True)
    print("--- Step 1: load sample + odds...", flush=True)
    sample = pd.read_parquet(DATA_V11 / "granger_sample_events.parquet")
    print(f"  Sample events: {len(sample)}", flush=True)
    odds = load_all_pulls()
    print(f"  Raw odds rows: {len(odds)}", flush=True)
    odds_per_event = per_event_implied(odds)
    print(f"  Per-event rows: {len(odds_per_event)}", flush=True)
    sb_index = build_sportsbook_index(odds_per_event)
    print(f"  Indexed sportsbook keys: {len(sb_index)}", flush=True)

    print("--- Step 2: pre-aggregate Kalshi VWAPs...", flush=True)
    sample = match_sample(sample)
    print(f"  Matched sample after team_maps parse: {len(sample)}", flush=True)
    con = duckdb.connect()
    tickers = sample["ticker"].unique().tolist()
    vwap_index = precompute_kalshi_hourly_vwap(con, tickers)

    print("--- Step 3: build joint dataset...", flush=True)
    df = build_v12_dataset(sample, sb_index, vwap_index)
    DATA_V12.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA_V12 / "joint_dataset_v12.parquet", index=False)
    print(f"  Joint dataset rows: {len(df)}", flush=True)

    print("--- Step 4: per-stratum Granger + bootstrap...", flush=True)
    results: dict = {}
    for stratum_name in ["MLB-day", "MLB-night", "NBA", "NFL"]:
        st = classify_stratum(df, stratum_name)
        n_with = st.dropna(
            subset=[
                "p_sb_yes_T-6h_off+0.0h", "p_sb_yes_T-3h_off+0.0h",
                "vwap_T-6h_off+0.0h", "vwap_T-3h_off+0.0h", "vwap_T-1h_off+0.0h",
            ]
        )
        n = len(n_with)
        print(f"  Stratum {stratum_name}: n={n}", flush=True)
        if stratum_name == "NFL":
            ra = run_stratum_granger(st, "NFL", use_nfl_b=False)
            rb = run_stratum_granger(st, "NFL", use_nfl_b=True)
            ga = evaluate_gate(ra, "NFL", n)
            gb = evaluate_gate(rb, "NFL", n)
            results["NFL-A"] = {"raw_results": ra, "gate": ga}
            results["NFL-B"] = {"raw_results": rb, "gate": gb}
            results["NFL-combined"] = {
                "passes": ga["overall_pass"] or gb["overall_pass"],
                "via": "A" if ga["overall_pass"] else ("B" if gb["overall_pass"] else "neither"),
            }
            print(f"    NFL-A center: F={ra.get('offset+0.0h', {}).get('F', float('nan')):.4f}, p={ra.get('offset+0.0h', {}).get('p', float('nan')):.6f}, gamma={ra.get('offset+0.0h', {}).get('gamma', float('nan')):.4f}", flush=True)
            print(f"    NFL-B center: F={rb.get('offset+0.0h', {}).get('F', float('nan')):.4f}, p={rb.get('offset+0.0h', {}).get('p', float('nan')):.6f}, gamma={rb.get('offset+0.0h', {}).get('gamma', float('nan')):.4f}", flush=True)
            print(f"    NFL passes via: {results['NFL-combined']['via']}", flush=True)
        else:
            r = run_stratum_granger(st, stratum_name)
            g = evaluate_gate(r, stratum_name, n)
            results[stratum_name] = {"raw_results": r, "gate": g}
            c = r.get("offset+0.0h", {})
            bb = r.get("block_bootstrap_center", {})
            print(
                f"    center: F={c.get('F', float('nan')):.4f}, p={c.get('p', float('nan')):.6f}, "
                f"gamma={c.get('gamma', float('nan')):.4f}, bb_ci_lower={bb.get('ci_lower_95', float('nan')):.4f}",
                flush=True,
            )
            print(
                f"    offset_robust: {g['offset_robust']}, bb_pass: {g['block_bootstrap_pass']}, overall_pass: {g['overall_pass']}",
                flush=True,
            )

    n_pass = sum(1 for s in ["MLB-day", "MLB-night", "NBA"] if results.get(s, {}).get("gate", {}).get("overall_pass", False))
    if results.get("NFL-combined", {}).get("passes", False):
        n_pass += 1
    vm = {4: "GRANGER-CONFIRMED-v12", 3: "GRANGER-PARTIAL-v12-3of4", 2: "GRANGER-PARTIAL-v12-2of4", 1: "NULL-v12", 0: "NULL-v12"}
    verdict = vm[n_pass]
    print(f"\n=== v12 VERDICT: {verdict} ({n_pass} of 4 strata pass) ===", flush=True)
    results["VERDICT"] = {"label": verdict, "n_passing": n_pass}
    (DATA_V12 / "v12_per_stratum_results.json").write_text(json.dumps(results, indent=2, default=str))

    write_report(results, verdict, n_pass)
    return 0


def write_report(results: dict, verdict: str, n_pass: int) -> None:
    md = [
        "# v12 Phase 2b: Granger Lead-Lag Test, Refined Methodology",
        "",
        "**Round:** 17 (v12). **Date:** 2026-05-27. **Script:** scripts/v12/phase2b_v12_analysis.py.",
        "**Lock:** research/v12/01-methodology-lock.md.",
        "",
        "## Per-stratum results (center offset, +/- 0.5h checks, block-bootstrap CI)",
        "",
        f"Top-level Bonferroni alpha = 0.05/4 = {ALPHA_TOPLEVEL:.5f}. NFL within-stratum alpha = 0.05/8 = {ALPHA_NFL_WITHIN:.5f}.",
        "",
        "| Stratum | n | F (center) | p (center) | gamma (center) | gamma_se | bb_ci_lower | bb_ci_upper | offset_robust | bb_pass | OVERALL |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in ["MLB-day", "MLB-night", "NBA"]:
        r = results.get(s, {})
        g = r.get("gate", {})
        c = r.get("raw_results", {}).get("offset+0.0h", {})
        bb = r.get("raw_results", {}).get("block_bootstrap_center", {})
        md.append(
            f"| {s} | {g.get('n', 0)} | {c.get('F', float('nan')):.4f} | {c.get('p', float('nan')):.6f} | "
            f"{c.get('gamma', float('nan')):.4f} | {c.get('gamma_se', float('nan')):.4f} | "
            f"{bb.get('ci_lower_95', float('nan')):.4f} | {bb.get('ci_upper_95', float('nan')):.4f} | "
            f"{g.get('offset_robust')} | {g.get('block_bootstrap_pass')} | {g.get('overall_pass')} |"
        )
    for s in ["NFL-A", "NFL-B"]:
        r = results.get(s, {})
        g = r.get("gate", {})
        c = r.get("raw_results", {}).get("offset+0.0h", {})
        bb = r.get("raw_results", {}).get("block_bootstrap_center", {})
        md.append(
            f"| {s} | {g.get('n', 0)} | {c.get('F', float('nan')):.4f} | {c.get('p', float('nan')):.6f} | "
            f"{c.get('gamma', float('nan')):.4f} | {c.get('gamma_se', float('nan')):.4f} | "
            f"{bb.get('ci_lower_95', float('nan')):.4f} | {bb.get('ci_upper_95', float('nan')):.4f} | "
            f"{g.get('offset_robust')} | {g.get('block_bootstrap_pass')} | {g.get('overall_pass')} |"
        )
    nc = results.get("NFL-combined", {})
    md.append(f"| NFL combined | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | {nc.get('passes', False)} (via {nc.get('via', 'neither')}) |")
    md.extend(["", "## Offset robustness detail", ""])
    for s in ["MLB-day", "MLB-night", "NBA", "NFL-A", "NFL-B"]:
        r = results.get(s, {})
        g = r.get("gate", {})
        md.append(f"**{s}** (alpha {g.get('alpha_used', float('nan')):.5f}):")
        for po in g.get("per_offset", []):
            md.append(
                f"- offset {po['offset']:+.1f}h: p={po.get('p', float('nan')):.6f}, "
                f"gamma={po.get('gamma', float('nan')):.4f}, passes={po['passes']}"
            )
        md.append("")
    md.extend([
        "## v12 verdict",
        "",
        f"Strata passing all 5 binding gates: {n_pass} of 4",
        "",
        f"**Verdict: {verdict}**",
        "",
        "---",
        "",
        "*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013.*",
    ])
    (RESEARCH / "02-phase2b-v12-results.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
