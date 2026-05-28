"""Phase 2 Step 2: Granger F-test on sportsbook -> Kalshi lead-lag.

Inputs:
- data/v11/granger_sample_events.parquet (433 events: 170 MLB + 162 NBA + 101 NFL)
- data/v11/odds_pulls/*.json (527 the-odds-api historical snapshots)
- prediction-market-analysis/data/kalshi/trades/*.parquet (Kalshi trade tape)

Outputs:
- data/v11/joint_dataset.parquet (per-event joint data)
- research/v11/05-phase2-granger-results.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from team_maps import map_event_to_team_names, parse_event_date


BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis" / "data" / "kalshi"
TRADES_GLOB = str(BECKER / "trades" / "*.parquet").replace("\\", "/")
DATA = BASE / "data" / "v11"
PULLS = DATA / "odds_pulls"
RESEARCH = BASE / "research" / "v11"

WINDOWS = {
    "T-6h": pd.Timedelta(hours=6),
    "T-3h": pd.Timedelta(hours=3),
    "T-1h": pd.Timedelta(hours=1),
}
COMMENCE_OFFSET = pd.Timedelta(hours=3, minutes=30)


def parse_snapshot_filename(p: Path) -> tuple[str, pd.Timestamp]:
    """KXMLBGAME__20250712T1000.json -> (KXMLBGAME, Timestamp UTC)."""
    stem = p.stem
    sport, ts = stem.split("__")
    return sport, pd.Timestamp(ts).tz_localize("UTC")


def load_pulls() -> pd.DataFrame:
    """Load all saved odds-api pulls into a long-form DataFrame.

    One row per (snapshot_time, sport, game, bookmaker, outcome).
    """
    rows: list[dict] = []
    for p in sorted(PULLS.glob("*.json")):
        sport, snap_t = parse_snapshot_filename(p)
        body = json.loads(p.read_text())
        for g in body.get("data", []):
            commence = pd.Timestamp(g["commence_time"])
            for bk in g.get("bookmakers", []):
                bk_key = bk.get("key")
                for mk in bk.get("markets", []):
                    if mk.get("key") != "h2h":
                        continue
                    outcomes = mk.get("outcomes", [])
                    if len(outcomes) != 2:
                        continue
                    for o in outcomes:
                        rows.append(
                            {
                                "sport_prefix": sport,
                                "snapshot_time": snap_t,
                                "commence_time": commence,
                                "home_team": g.get("home_team"),
                                "away_team": g.get("away_team"),
                                "bookmaker": bk_key,
                                "team": o.get("name"),
                                "decimal_odds": o.get("price"),
                            }
                        )
    df = pd.DataFrame(rows)
    return df


def implied_from_decimal(odds: float) -> float:
    return 1.0 / odds if odds and odds > 0 else float("nan")


def normalize_two_way_implied(p1: float, p2: float) -> tuple[float, float]:
    s = p1 + p2
    if s <= 0:
        return float("nan"), float("nan")
    return p1 / s, p2 / s


def compute_per_event_implied(odds: pd.DataFrame) -> pd.DataFrame:
    """Collapse bookmaker-level rows to per-(snapshot, game) median
    implied probability, normalized to remove overround.

    Pre-normalize per (game, bookmaker), then take median across
    bookmakers per game.
    """
    odds = odds.copy()
    odds["implied"] = odds["decimal_odds"].apply(implied_from_decimal)
    rows_out: list[dict] = []
    grp = odds.groupby(
        ["sport_prefix", "snapshot_time", "commence_time", "home_team", "away_team"]
    )
    for (sport, snap_t, commence, home, away), g in grp:
        per_book = g.groupby("bookmaker")
        home_imps, away_imps = [], []
        for _, gb in per_book:
            home_row = gb[gb["team"] == home]
            away_row = gb[gb["team"] == away]
            if home_row.empty or away_row.empty:
                continue
            p_h = home_row["implied"].iloc[0]
            p_a = away_row["implied"].iloc[0]
            if not (p_h > 0 and p_a > 0):
                continue
            p_h_n, p_a_n = normalize_two_way_implied(p_h, p_a)
            home_imps.append(p_h_n)
            away_imps.append(p_a_n)
        if not home_imps:
            continue
        rows_out.append(
            {
                "sport_prefix": sport,
                "snapshot_time": snap_t,
                "commence_time": commence,
                "home_team": home,
                "away_team": away,
                "home_implied_median": float(np.median(home_imps)),
                "away_implied_median": float(np.median(away_imps)),
                "n_bookmakers": len(home_imps),
            }
        )
    return pd.DataFrame(rows_out)


def match_events_to_odds(
    sample: pd.DataFrame, odds_per_event: pd.DataFrame
) -> pd.DataFrame:
    """Match Becker events to the-odds-api games by (date, teams).

    Returns rows with per-event (T-6h, T-3h, T-1h) sportsbook implied
    probabilities for the home team.
    """
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
    if sample.empty:
        return sample
    sample[["team1", "team2"]] = pd.DataFrame(
        sample["teams_parsed"].tolist(), index=sample.index
    )

    odds_per_event = odds_per_event.copy()
    odds_per_event["commence_date"] = (
        pd.to_datetime(odds_per_event["commence_time"], utc=True).dt.date.astype(str)
    )

    rows_out: list[dict] = []
    for r in sample.itertuples(index=False):
        # KILLER-1 fix: evening games (most NBA, late MLB, NFL primetime)
        # have commence UTC on the NEXT calendar day after the Kalshi local
        # ticker date. Accept event_date AND event_date+1 as match candidates.
        from datetime import datetime as _dt, timedelta as _td
        try:
            d0 = _dt.strptime(r.event_date, "%Y-%m-%d")
            d1 = (d0 + _td(days=1)).strftime("%Y-%m-%d")
        except Exception:
            d1 = r.event_date
        cand = odds_per_event[
            (odds_per_event["sport_prefix"] == r.sport_prefix)
            & (odds_per_event["commence_date"].isin([r.event_date, d1]))
        ].copy()
        if cand.empty:
            continue
        team_set = {r.team1, r.team2}
        cand_match = cand[
            cand.apply(
                lambda c: {c["home_team"], c["away_team"]} == team_set,
                axis=1,
            )
        ].copy()
        if cand_match.empty:
            continue

        commence_estimate = r.close_time - COMMENCE_OFFSET
        per_window: dict[str, float] = {}
        per_window_actual: dict[str, pd.Timestamp] = {}
        cand_match_reset = cand_match.reset_index(drop=True)
        for w_label, delta in WINDOWS.items():
            target = commence_estimate - delta
            target_h = target.floor("h")
            row = cand_match_reset[cand_match_reset["snapshot_time"] == target_h]
            if row.empty:
                ts_diff = (cand_match_reset["snapshot_time"] - target_h).abs()
                row = cand_match_reset.iloc[[int(ts_diff.values.argmin())]]
                actual = row["snapshot_time"].iloc[0]
                if abs((actual - target_h).total_seconds()) > 3600:
                    per_window[w_label] = float("nan")
                    per_window_actual[w_label] = pd.NaT
                    continue
            row_data = row.iloc[0]
            # Home team of the-odds-api game maps to one of team1/team2.
            # Use team1 = "home_team" by convention if team1 matches.
            if row_data["home_team"] == r.team1:
                p = row_data["home_implied_median"]
            elif row_data["home_team"] == r.team2:
                p = 1.0 - row_data["home_implied_median"]
            else:
                p = float("nan")
            per_window[w_label] = p
            per_window_actual[w_label] = row_data["snapshot_time"]

        if all(np.isnan(v) for v in per_window.values()):
            continue
        rows_out.append(
            {
                "ticker": r.ticker,
                "event_ticker": r.event_ticker,
                "sport_prefix": r.sport_prefix,
                "close_time": r.close_time,
                "team1": r.team1,
                "team2": r.team2,
                "p_sportsbook_team1_T-6h": per_window.get("T-6h"),
                "p_sportsbook_team1_T-3h": per_window.get("T-3h"),
                "p_sportsbook_team1_T-1h": per_window.get("T-1h"),
                "snap_actual_T-6h": per_window_actual.get("T-6h"),
                "snap_actual_T-3h": per_window_actual.get("T-3h"),
                "snap_actual_T-1h": per_window_actual.get("T-1h"),
            }
        )
    return pd.DataFrame(rows_out)


def compute_kalshi_vwaps(
    con: duckdb.DuckDBPyConnection, joined: pd.DataFrame
) -> pd.DataFrame:
    """For each event, compute Kalshi trade-print VWAP in 1-hour windows
    centered on T-6h, T-3h, T-1h relative to commence_estimate.

    Uses the YES-side ticker (the joined dataframe is YES-only by Becker
    convention; YES = Kalshi-listed team1; need to derive carefully).
    """
    joined = joined.copy()
    joined["close_time"] = pd.to_datetime(joined["close_time"], utc=True)
    joined["commence_estimate"] = joined["close_time"] - COMMENCE_OFFSET

    rows: list[dict] = []
    for r in joined.itertuples(index=False):
        ts_target = {
            "T-6h": r.commence_estimate - pd.Timedelta(hours=6),
            "T-3h": r.commence_estimate - pd.Timedelta(hours=3),
            "T-1h": r.commence_estimate - pd.Timedelta(hours=1),
        }
        per_window_vwap: dict[str, float] = {}
        for w_label, target in ts_target.items():
            lo = target - pd.Timedelta(minutes=30)
            hi = target + pd.Timedelta(minutes=30)
            lo_utc = lo.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S+00:00")
            hi_utc = hi.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S+00:00")
            sql = f"""
            SELECT SUM(yes_price * count) / NULLIF(SUM(count), 0) AS vwap
            FROM '{TRADES_GLOB}'
            WHERE ticker = '{r.ticker}'
              AND created_time >= TIMESTAMPTZ '{lo_utc}'
              AND created_time <  TIMESTAMPTZ '{hi_utc}'
            """
            df = con.execute(sql).df()
            v = df["vwap"].iloc[0] if not df.empty else None
            per_window_vwap[w_label] = (
                float(v) / 100.0 if v is not None and not pd.isna(v) else float("nan")
            )
        rows.append(
            {
                "ticker": r.ticker,
                "kalshi_vwap_T-6h": per_window_vwap["T-6h"],
                "kalshi_vwap_T-3h": per_window_vwap["T-3h"],
                "kalshi_vwap_T-1h": per_window_vwap["T-1h"],
            }
        )
    return pd.DataFrame(rows)


def assign_team1_yes_side(joined: pd.DataFrame) -> pd.DataFrame:
    """The Becker YES-side ticker convention: the suffix team after the
    final dash is the YES winner. The event_ticker has team1+team2 in
    concatenated order.

    We need to determine whether team1 is the YES winner (Kalshi VWAP
    represents team1's implied probability) or team2 (then Kalshi VWAP
    represents team2's; need to flip).
    """
    df = joined.copy()
    # Suffix team is the last token after the last dash
    df["yes_side_abbr"] = df["ticker"].str.rsplit("-", n=1).str[1]
    # team1 = first abbreviation, team2 = second. The yes_side_abbr
    # tells us which of (team1, team2) is the YES side.
    # We need to know: does abbr "TOR" map to team1 or team2?
    # Without re-parsing, we approximate by string match on
    # team1.split()[-1] vs team2.split()[-1] vs yes_side_abbr.
    # Cleaner: re-derive from event_ticker which abbr came first.
    from team_maps import split_team_abbrs

    def is_team1_yes(row: pd.Series) -> bool:
        ev = row["event_ticker"]
        sport = row["sport_prefix"]
        prefix = f"{sport}-"
        rest = ev[len(prefix):]
        teams_str = rest[7:]
        split = split_team_abbrs(teams_str, sport)
        if split is None:
            return None
        return split[0] == row["yes_side_abbr"]

    df["team1_is_yes"] = df.apply(is_team1_yes, axis=1)
    return df


def granger_f_test(
    delta_kalshi_post: np.ndarray,
    delta_kalshi_pre: np.ndarray,
    delta_sportsbook: np.ndarray,
) -> dict:
    """Compute Granger F-test for the gamma=0 restriction in the
    unrestricted model delta_kalshi_post = alpha + beta * delta_kalshi_pre +
    gamma * delta_sportsbook + eps.

    Returns dict with F, df1, df2, p_value, gamma, gamma_se, n.
    """
    mask = (
        ~np.isnan(delta_kalshi_post)
        & ~np.isnan(delta_kalshi_pre)
        & ~np.isnan(delta_sportsbook)
    )
    y = delta_kalshi_post[mask]
    x1 = delta_kalshi_pre[mask]
    x2 = delta_sportsbook[mask]
    n = len(y)
    if n < 10:
        return {
            "F": float("nan"),
            "df1": 1,
            "df2": max(0, n - 3),
            "p_value": float("nan"),
            "gamma": float("nan"),
            "gamma_se": float("nan"),
            "n": n,
            "note": "insufficient n",
        }
    # Restricted: y ~ 1 + x1
    X_r = np.column_stack([np.ones(n), x1])
    beta_r, _, _, _ = np.linalg.lstsq(X_r, y, rcond=None)
    resid_r = y - X_r @ beta_r
    ss_r = float(np.sum(resid_r**2))

    # Unrestricted: y ~ 1 + x1 + x2
    X_u = np.column_stack([np.ones(n), x1, x2])
    beta_u, _, _, _ = np.linalg.lstsq(X_u, y, rcond=None)
    resid_u = y - X_u @ beta_u
    ss_u = float(np.sum(resid_u**2))

    df1 = 1
    df2 = n - 3
    if ss_u <= 0 or df2 <= 0:
        return {
            "F": float("nan"),
            "df1": df1,
            "df2": df2,
            "p_value": float("nan"),
            "gamma": float(beta_u[2]) if len(beta_u) > 2 else float("nan"),
            "gamma_se": float("nan"),
            "n": n,
            "note": "degenerate fit",
        }
    F = ((ss_r - ss_u) / df1) / (ss_u / df2)
    p = 1.0 - stats.f.cdf(F, df1, df2)
    # Standard error of gamma (the third coefficient)
    XtX_inv = np.linalg.inv(X_u.T @ X_u)
    sigma2 = ss_u / df2
    gamma_se = float(np.sqrt(sigma2 * XtX_inv[2, 2]))
    return {
        "F": float(F),
        "df1": df1,
        "df2": df2,
        "p_value": float(p),
        "gamma": float(beta_u[2]),
        "gamma_se": gamma_se,
        "n": n,
        "note": "ok",
    }


def main() -> int:
    print("Phase 2 Step 2: Granger F-test")
    print("--- Loading odds-api pulls...")
    odds_raw = load_pulls()
    print(f"  Odds rows (per bookmaker-outcome): {len(odds_raw)}")
    print(
        f"  Per-sport rows: "
        f"{dict(odds_raw.groupby('sport_prefix').size().astype(int))}"
    )

    print("--- Collapsing to per-event implied probability...")
    odds_per_event = compute_per_event_implied(odds_raw)
    print(f"  Per-event rows: {len(odds_per_event)}")

    print("--- Loading sample events...")
    sample = pd.read_parquet(DATA / "granger_sample_events.parquet")
    print(f"  Sample events: {len(sample)}")

    print("--- Matching events to sportsbook odds (team-name parser)...")
    matched = match_events_to_odds(sample, odds_per_event)
    print(f"  Matched events: {len(matched)}")
    if len(matched) == 0:
        print("FATAL: no events matched")
        return 1

    print("--- Computing Kalshi VWAPs at T-6h, T-3h, T-1h...")
    con = duckdb.connect()
    vwap_df = compute_kalshi_vwaps(con, matched)
    joined = matched.merge(vwap_df, on="ticker", how="left")
    print(f"  Joined rows: {len(joined)}")

    print("--- Aligning YES-side teams...")
    joined = assign_team1_yes_side(joined)

    # If team1 is NOT YES, flip the sportsbook prob to be on YES side
    def yes_side_prob(row: pd.Series, col: str) -> float:
        p = row[col]
        if pd.isna(p):
            return float("nan")
        return p if row["team1_is_yes"] else 1.0 - p

    for w in ["T-6h", "T-3h", "T-1h"]:
        joined[f"p_sportsbook_yes_{w}"] = joined.apply(
            lambda r: yes_side_prob(r, f"p_sportsbook_team1_{w}"), axis=1
        )

    # Compute deltas
    joined["delta_sportsbook_pre"] = (
        joined["p_sportsbook_yes_T-3h"] - joined["p_sportsbook_yes_T-6h"]
    )
    joined["delta_kalshi_pre"] = (
        joined["kalshi_vwap_T-3h"] - joined["kalshi_vwap_T-6h"]
    )
    joined["delta_kalshi_post"] = (
        joined["kalshi_vwap_T-1h"] - joined["kalshi_vwap_T-3h"]
    )

    joined.to_parquet(DATA / "joint_dataset.parquet", index=False)

    print("--- Running Granger F-test per sport...")
    results: dict[str, dict] = {}
    pooled_mask = (
        ~joined["delta_sportsbook_pre"].isna()
        & ~joined["delta_kalshi_pre"].isna()
        & ~joined["delta_kalshi_post"].isna()
    )
    print(f"  Joint coverage (rows with all 3 deltas): {int(pooled_mask.sum())}")

    for sport in joined["sport_prefix"].unique():
        sub = joined[joined["sport_prefix"] == sport]
        r = granger_f_test(
            sub["delta_kalshi_post"].to_numpy(),
            sub["delta_kalshi_pre"].to_numpy(),
            sub["delta_sportsbook_pre"].to_numpy(),
        )
        results[sport] = r
        print(
            f"  {sport}: n={r['n']}, F={r['F']:.4f}, p={r['p_value']:.6f}, "
            f"gamma={r['gamma']:.4f} (se={r['gamma_se']:.4f})"
        )

    # Pooled (descriptive)
    r_pool = granger_f_test(
        joined["delta_kalshi_post"].to_numpy(),
        joined["delta_kalshi_pre"].to_numpy(),
        joined["delta_sportsbook_pre"].to_numpy(),
    )
    results["POOLED"] = r_pool
    print(
        f"  POOLED: n={r_pool['n']}, F={r_pool['F']:.4f}, p={r_pool['p_value']:.6f}, "
        f"gamma={r_pool['gamma']:.4f} (se={r_pool['gamma_se']:.4f})"
    )

    # Save results JSON
    (DATA / "granger_results.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    # Write markdown report
    print("--- Writing markdown report...")
    write_report(joined, results)
    return 0


def write_report(joined: pd.DataFrame, results: dict[str, dict]) -> None:
    bonferroni_alpha = 0.05 / 3
    md = [
        "# v11 Phase 2 Step 2: Granger Lead-Lag Test Results",
        "",
        "**Round:** 16 (v11) Track 1 Granger-first.",
        "**Date:** 2026-05-27. **Script:** scripts/v11/phase2_step2_granger.py",
        "**Lock:** v3 amendment (research/v11/04-lock-v3-granger-amendment.md)",
        "",
        "## Hypothesis (locked verbatim per v3 amendment)",
        "",
        "H0: sportsbook movement in T-6h to T-3h does NOT predict Kalshi "
        "trade-print movement in T-3h to T-1h, given Kalshi's own T-6h to T-3h "
        "movement.",
        "",
        "Granger F-test on the gamma=0 restriction in:",
        "  delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + epsilon",
        "",
        "## Sample coverage",
        "",
        f"- Total joined events: {len(joined)}",
        f"- Events with all 3 deltas non-null: "
        f"{int((~joined[['delta_sportsbook_pre', 'delta_kalshi_pre', 'delta_kalshi_post']].isna().any(axis=1)).sum())}",
        "- Per-sport joined: "
        f"{dict(joined.groupby('sport_prefix').size().astype(int))}",
        "",
        "## Per-sport Granger F-test",
        "",
        "Bonferroni-corrected alpha: 0.05 / 3 = 0.01667",
        "",
        "| Sport | n | F | p_value | gamma | gamma_se | passes (p<=0.01667) | positive direction |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for sport in ["KXMLBGAME", "KXNBAGAME", "KXNFLGAME"]:
        if sport not in results:
            continue
        r = results[sport]
        passes = (
            r["p_value"] <= bonferroni_alpha
            if not np.isnan(r["p_value"])
            else False
        )
        positive = r["gamma"] > 0 if not np.isnan(r["gamma"]) else False
        md.append(
            f"| {sport} | {r['n']} | "
            f"{r['F']:.4f} | {r['p_value']:.6f} | {r['gamma']:.4f} | "
            f"{r['gamma_se']:.4f} | {passes} | {positive} |"
        )
    md.extend(
        [
            "",
            "## Pooled (descriptive, not gated)",
            "",
            f"- n={results['POOLED']['n']}, "
            f"F={results['POOLED']['F']:.4f}, "
            f"p={results['POOLED']['p_value']:.6f}, "
            f"gamma={results['POOLED']['gamma']:.4f} "
            f"(se={results['POOLED']['gamma_se']:.4f})",
            "",
            "## G_GRANGER verdict",
            "",
        ]
    )
    passes_per_sport = []
    for sport in ["KXMLBGAME", "KXNBAGAME", "KXNFLGAME"]:
        if sport not in results:
            continue
        r = results[sport]
        passes = (
            (r["p_value"] <= bonferroni_alpha) and (r["gamma"] > 0)
            if not np.isnan(r["p_value"]) and not np.isnan(r["gamma"])
            else False
        )
        passes_per_sport.append((sport, passes))
    n_pass = sum(1 for _, p in passes_per_sport if p)
    if n_pass == 3:
        verdict = "GRANGER-CONFIRMED"
    elif n_pass == 2:
        verdict = "GRANGER-PARTIAL (2 of 3)"
    else:
        verdict = "NULL"
    md.append(f"Sports passing G_GRANGER (p<=0.01667 AND gamma>0): {n_pass} of 3")
    for sport, p in passes_per_sport:
        md.append(f"- {sport}: {'PASS' if p else 'FAIL'}")
    md.extend(
        [
            "",
            f"**Verdict: {verdict}**",
            "",
            "## Recommendation",
            "",
        ]
    )
    if verdict == "GRANGER-CONFIRMED":
        md.append(
            "All 3 sports confirm sportsbook leads Kalshi. Recommend v12 follow-up "
            "to design a strategy P&L test with execution-model that does not "
            "depend on Becker MARKETS snapshots (e.g., live-probe haircut "
            "calibration). v11 Track 1 closes GRANGER-CONFIRMED, no capital."
        )
    elif verdict.startswith("GRANGER-PARTIAL"):
        md.append(
            "2 of 3 sports confirm sportsbook leads Kalshi. Recommend v12 follow-up "
            "scoped to the passing sports only. Single-sport failure may reflect "
            "low n, league-specific market microstructure, or true absence of "
            "lead-lag in that sport. v11 Track 1 closes GRANGER-PARTIAL."
        )
    else:
        md.append(
            "0 or 1 sports pass G_GRANGER. Sportsbook does NOT systematically "
            "lead Kalshi on game-resolution markets in the post-Oct-2024 cohort. "
            "v11 Track 1 closes NULL. No further strategy P&L test warranted."
        )
    md.append("")
    md.append("---")
    md.append("")
    md.append(
        "*Anti-em-dash and anti-en-dash verification: written without U+2014 or "
        "U+2013 throughout.*"
    )
    (RESEARCH / "05-phase2-granger-results.md").write_text(
        "\n".join(md), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
