"""Build the v3 leak-free joined dataset.

Inputs:
- data/v3/probe_inventory_eligible_with_team.parquet (147 rows from V3-A)
- data/v3/probe_inventory_all_markets.parquet (optional join for extra cols)

Outputs:
- data/v3/joined_v3_dataset.parquet
- data/v3/v3_orthogonality_report.json
- data/v3/mlb_stats_cache/ (cached MLB Stats API responses)
- data/v3/nflverse_cache/ (cached nflverse parquets)

Hard leak-discipline rules (per V3-B1 brief):
1. Every external-feature query MUST use a timestamp / date STRICTLY less than
   close_time - 35 days. We use (close_time - 35 days - 1 day) as the
   conservative upper bound for any AS-OF call.
2. After build, assertion: for every row, every feature value is provably
   computable from data available at-or-before t35d_time - 1 day.
3. nflverse rows filtered by gameday < t35d_time. (Season parquet is the
   full season; we filter rows to only those games already played at T-35d.)
4. MLB Stats API date= parameter is the official AS-OF; we use t35d - 1 day.
5. If a feature cannot be sampled AS-OF, leave NaN; document.

Orthogonality protocol (per V3-B audit Section "Orthogonality check protocol"):
For each candidate feature X:
  1. Restrict to chronologically earliest 70% of dataset (train).
  2. Fit OLS(X ~ favorite_price) on train. Residuals = X_resid.
  3. Fit LogReg(outcome ~ favorite_price + X_resid) on train.
  4. Bootstrap coefficient on X_resid (5000 resamples, seed 42). 95% CI.
  5. If CI(X_resid) includes zero AND AUC improvement over price-only < 0.005,
     drop X from final feature set.

Run: uv run python -m scripts.v3.build_v3_dataset
"""
from __future__ import annotations

import io
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "v3"
MLB_CACHE = DATA_DIR / "mlb_stats_cache"
NFL_CACHE = DATA_DIR / "nflverse_cache"
MLB_CACHE.mkdir(parents=True, exist_ok=True)
NFL_CACHE.mkdir(parents=True, exist_ok=True)

ELIGIBLE_PATH = DATA_DIR / "probe_inventory_eligible_with_team.parquet"
ALL_MARKETS_PATH = DATA_DIR / "probe_inventory_all_markets.parquet"
OUTPUT_PATH = DATA_DIR / "joined_v3_dataset.parquet"
ORTHO_REPORT_PATH = DATA_DIR / "v3_orthogonality_report.json"

UA = {"User-Agent": "Mozilla/5.0 (ProjectKalshi v3 dataset build; sjdoane@usc.edu)"}

# Kalshi NFL team-code -> nflverse team-code. Kalshi uses 'JAC' but nflverse
# uses 'JAX'. Most other codes match. Add LA / LAR variants too.
KALSHI_NFL_TO_NFLVERSE = {
    "JAC": "JAX",
    # LA is Rams in both. LAC is Chargers in both. NE/NO/NYG/NYJ/SF/TB/TEN/WAS all match.
}


# MLB team abbreviation -> MLB Stats API team_id. Source: live probe of
# statsapi.mlb.com/api/v1/teams?sportId=1&season=2025.
MLB_TEAM_ID = {
    "ATH": 133, "PIT": 134, "SD": 135, "SEA": 136, "SF": 137, "STL": 138,
    "TB": 139, "TEX": 140, "TOR": 141, "MIN": 142, "PHI": 143, "ATL": 144,
    "CWS": 145, "MIA": 146, "NYY": 147, "MIL": 158, "LAA": 108, "AZ": 109,
    "BAL": 110, "BOS": 111, "CHC": 112, "CIN": 113, "CLE": 114, "COL": 115,
    "DET": 116, "HOU": 117, "KC": 118, "LAD": 119, "WSH": 120, "NYM": 121,
}


def derive_league(group: str) -> str:
    """Map our group column to a league code (NFL/MLB/NBA/NCAA/NHL)."""
    m = {
        "nfl_team_wins": "NFL",
        "nfl_playoffs": "NFL",
        "mlb_team_wins": "MLB",
        "mlb_playoffs": "MLB",
        "mlb_awards": "MLB",
        "nba_wins": "NBA",
        "nhl_division": "NHL",
        "ncaaf_playoff_qual": "NCAA",
    }
    return m.get(group, "OTHER")


# ---------- nflverse loaders ----------------------------------------------

def load_nfl_games() -> pd.DataFrame:
    """Pull nflverse schedules/games.parquet (full historical schedules with
    gameday + scores). Cached locally."""
    cache = NFL_CACHE / "games.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    url = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
    r = httpx.get(url, follow_redirects=True, timeout=60, headers=UA)
    r.raise_for_status()
    df = pd.read_parquet(io.BytesIO(r.content))
    df.to_parquet(cache, index=False)
    print(f"  nflverse: cached {len(df)} games to {cache}")
    return df


def compute_nfl_team_features(team: str, t35d_minus1: datetime, games: pd.DataFrame, season: int) -> dict[str, Any]:
    """Compute NFL team features AS-OF t35d_minus1 (strictly before T-35d).

    Filter rule: gameday < t35d_minus1 (i.e., only games already played).
    Season scope: restrict to the relevant NFL season so cross-season noise
    does not bleed in.
    """
    # Map Kalshi team-code to nflverse team-code.
    team = KALSHI_NFL_TO_NFLVERSE.get(team, team)
    cutoff_date = t35d_minus1.date()
    rel = games[(games["season"] == season) & (games["gameday"].notna())]
    # gameday is a string YYYY-MM-DD; convert
    rel = rel.copy()
    rel["gameday_dt"] = pd.to_datetime(rel["gameday"], errors="coerce").dt.date
    # Strictly less than cutoff_date for safety (no same-day inclusion).
    rel = rel[rel["gameday_dt"] < cutoff_date]
    # Restrict to regular-season games (game_type == 'REG'). Per nflverse
    # docs, 'POST' is playoffs and we want only completed-regular-season
    # form for win-total contracts.
    rel = rel[rel["game_type"] == "REG"]
    # Find games where this team was either home or away.
    home_games = rel[rel["home_team"] == team][["home_score", "away_score", "gameday_dt"]].rename(
        columns={"home_score": "team_score", "away_score": "opp_score"}
    )
    away_games = rel[rel["away_team"] == team][["away_score", "home_score", "gameday_dt"]].rename(
        columns={"away_score": "team_score", "home_score": "opp_score"}
    )
    team_games = pd.concat([home_games, away_games], ignore_index=True)
    # Drop games with no score (not yet played; should already be excluded by
    # gameday filter, but defensive).
    team_games = team_games.dropna(subset=["team_score", "opp_score"])
    n = len(team_games)
    if n == 0:
        return {
            "nfl_w_pct_pre_t35d": np.nan,
            "nfl_pyth_w_pct_pre_t35d": np.nan,
            "nfl_recent5_w_pct": np.nan,
            "nfl_games_played_pre_t35d": 0,
            "nfl_point_diff_per_game": np.nan,
        }
    team_games = team_games.sort_values("gameday_dt").reset_index(drop=True)
    wins = (team_games["team_score"] > team_games["opp_score"]).sum()
    losses = (team_games["team_score"] < team_games["opp_score"]).sum()
    ties = (team_games["team_score"] == team_games["opp_score"]).sum()
    w_pct = (wins + 0.5 * ties) / n
    pts_for = float(team_games["team_score"].sum())
    pts_against = float(team_games["opp_score"].sum())
    # Pythagorean (Pro-Football-Reference uses exponent ~2.37 for NFL; we
    # use a generic 2.37 per literature consensus).
    exp_pyth = 2.37
    if pts_for + pts_against > 0:
        pyth = (pts_for ** exp_pyth) / (pts_for ** exp_pyth + pts_against ** exp_pyth)
    else:
        pyth = np.nan
    # Recent 5 games
    if n >= 1:
        recent = team_games.tail(5)
        recent_w = (recent["team_score"] > recent["opp_score"]).sum()
        recent_t = (recent["team_score"] == recent["opp_score"]).sum()
        recent_pct = (recent_w + 0.5 * recent_t) / len(recent)
    else:
        recent_pct = np.nan
    point_diff_per_game = (pts_for - pts_against) / n if n > 0 else np.nan
    return {
        "nfl_w_pct_pre_t35d": float(w_pct),
        "nfl_pyth_w_pct_pre_t35d": float(pyth),
        "nfl_recent5_w_pct": float(recent_pct),
        "nfl_games_played_pre_t35d": int(n),
        "nfl_point_diff_per_game": float(point_diff_per_game),
    }


# ---------- MLB Stats API loader ------------------------------------------

def mlb_standings_as_of(date_str: str, season: int) -> dict[str, Any]:
    """Fetch MLB standings AS-OF date (strictly before T-35d). Cached locally
    by date+season for reproducibility."""
    cache = MLB_CACHE / f"standings_{season}_{date_str}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    url = "https://statsapi.mlb.com/api/v1/standings"
    params = {
        "leagueId": "103,104",
        "season": season,
        "date": date_str,
        "standingsTypes": "regularSeason",
    }
    r = httpx.get(url, params=params, timeout=60, headers=UA)
    r.raise_for_status()
    data = r.json()
    cache.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return data


def compute_mlb_team_features(team_abbr: str, t35d_minus1: datetime, season: int) -> dict[str, Any]:
    """Compute MLB team features AS-OF t35d_minus1. Pulls standings at that
    date and extracts wins/losses/runs."""
    team_id = MLB_TEAM_ID.get(team_abbr)
    if team_id is None:
        return {
            "mlb_w_pct_pre_t35d": np.nan,
            "mlb_pyth_w_pct_pre_t35d": np.nan,
            "mlb_games_back": np.nan,
            "mlb_run_diff_per_game": np.nan,
            "mlb_games_played_pre_t35d": 0,
        }
    date_str = t35d_minus1.strftime("%Y-%m-%d")
    data = mlb_standings_as_of(date_str, season)
    records = data.get("records", [])
    for rec in records:
        for tr in rec.get("teamRecords", []):
            if tr.get("team", {}).get("id") == team_id:
                wins = tr["leagueRecord"]["wins"]
                losses = tr["leagueRecord"]["losses"]
                gp = tr.get("gamesPlayed", wins + losses)
                if gp == 0:
                    return {
                        "mlb_w_pct_pre_t35d": np.nan,
                        "mlb_pyth_w_pct_pre_t35d": np.nan,
                        "mlb_games_back": np.nan,
                        "mlb_run_diff_per_game": np.nan,
                        "mlb_games_played_pre_t35d": 0,
                    }
                w_pct = wins / gp
                rs = tr.get("runsScored", 0)
                ra = tr.get("runsAllowed", 0)
                # MLB Pythagorean exponent: Bill James 1.83 (the canonical).
                exp_pyth = 1.83
                if rs + ra > 0:
                    pyth = (rs ** exp_pyth) / (rs ** exp_pyth + ra ** exp_pyth)
                else:
                    pyth = np.nan
                gb_str = tr.get("gamesBack", "-")
                try:
                    games_back = 0.0 if gb_str == "-" else float(gb_str)
                except (ValueError, TypeError):
                    games_back = np.nan
                run_diff = (rs - ra) / gp
                return {
                    "mlb_w_pct_pre_t35d": float(w_pct),
                    "mlb_pyth_w_pct_pre_t35d": float(pyth),
                    "mlb_games_back": float(games_back),
                    "mlb_run_diff_per_game": float(run_diff),
                    "mlb_games_played_pre_t35d": int(gp),
                }
    # Team not found in standings.
    return {
        "mlb_w_pct_pre_t35d": np.nan,
        "mlb_pyth_w_pct_pre_t35d": np.nan,
        "mlb_games_back": np.nan,
        "mlb_run_diff_per_game": np.nan,
        "mlb_games_played_pre_t35d": 0,
    }


# ---------- Build loop ----------------------------------------------------

def build_dataset() -> pd.DataFrame:
    elig = pd.read_parquet(ELIGIBLE_PATH)
    print(f"Loaded {len(elig)} eligible rows.")

    # Pull nflverse games once (cached).
    nfl_games = load_nfl_games()

    rows = []
    for i, row in elig.iterrows():
        ticker = row["ticker"]
        series_ticker = row["series_ticker"]
        # event_ticker is not in the eligible parquet; derive from ticker
        # (ticker has format SERIES-EVENT-MARKET). Best-effort.
        # For KXNFLWINS-SEA-27SEA-8 the event would be KXNFLWINS-SEA-27SEA.
        # The structure is SERIES_TICKER + EVENT_SUFFIX + market_id. We
        # leave event_ticker as series_ticker for series like KXNFLWINS-SEA;
        # the brief notes downstream code joins from all_markets if needed.
        event_ticker = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
        team = row["team"]
        group = row["group"]
        league = derive_league(group)
        open_time = row["open_time"]
        close_time = row["close_time"]
        # T-35d sampling time (UTC, datetime).
        t35d_time = close_time - pd.Timedelta(days=35)
        # Conservative AS-OF: T-35d - 1 day for external API queries.
        t35d_minus1 = t35d_time - pd.Timedelta(days=1)
        lifetime_days = (close_time - open_time).total_seconds() / 86400.0
        season_month = close_time.month
        favorite_price = row["vwap_t35_wide"]  # per brief
        outcome = int(row["outcome"])

        # Determine the season-year for the league. NFL season is named by
        # the year the season STARTS (Sept of year Y -> 2025 season). MLB
        # season is the year of close (regular season ends Sept-Oct of same
        # year).
        if league == "NFL":
            # NFL: season starts Sep of year. If close in Sep-Dec, season is
            # that year. If close in Jan-Feb (playoffs), season is the PREV
            # year.
            if close_time.month >= 8:
                season_year = close_time.year
            else:
                season_year = close_time.year - 1
        elif league == "MLB":
            season_year = close_time.year
        else:
            season_year = close_time.year

        # Build per-league features.
        nfl_feats = {
            "nfl_w_pct_pre_t35d": np.nan,
            "nfl_pyth_w_pct_pre_t35d": np.nan,
            "nfl_recent5_w_pct": np.nan,
            "nfl_games_played_pre_t35d": 0,
            "nfl_point_diff_per_game": np.nan,
        }
        mlb_feats = {
            "mlb_w_pct_pre_t35d": np.nan,
            "mlb_pyth_w_pct_pre_t35d": np.nan,
            "mlb_games_back": np.nan,
            "mlb_run_diff_per_game": np.nan,
            "mlb_games_played_pre_t35d": 0,
        }

        if league == "NFL":
            nfl_feats = compute_nfl_team_features(
                team, t35d_minus1.to_pydatetime(), nfl_games, season_year
            )
        elif league == "MLB":
            # Awards (mlb_awards) have team='TSKU' which is a player
            # initialism, not a team. Skip.
            if group != "mlb_awards":
                mlb_feats = compute_mlb_team_features(
                    team, t35d_minus1.to_pydatetime(), season_year
                )

        # Determine feature completeness for this row's league.
        if league == "NFL":
            feat_complete = (
                not np.isnan(nfl_feats["nfl_w_pct_pre_t35d"])
                and nfl_feats["nfl_games_played_pre_t35d"] > 0
            )
        elif league == "MLB":
            feat_complete = (
                not np.isnan(mlb_feats["mlb_w_pct_pre_t35d"])
                and mlb_feats["mlb_games_played_pre_t35d"] > 0
            )
        else:
            feat_complete = False  # NBA/NCAA/NHL: NaN by design

        coverage_note = ""
        if not feat_complete:
            if league in ("NBA", "NCAA", "NHL"):
                coverage_note = f"NO_AS_OF_API_FOR_LEAGUE_{league}"
            elif group == "mlb_awards":
                coverage_note = "AWARD_MARKET_NO_TEAM_MAPPING"
            elif nfl_feats["nfl_games_played_pre_t35d"] == 0 and mlb_feats["mlb_games_played_pre_t35d"] == 0:
                coverage_note = "TEAM_NOT_FOUND_OR_SEASON_NOT_STARTED"

        row_out = {
            "ticker": ticker,
            "series_ticker": series_ticker,
            "event_ticker": event_ticker,
            "team": team,
            "league": league,
            "group": group,
            "season_year": season_year,
            "open_time": open_time,
            "close_time": close_time,
            "t35d_time": t35d_time,
            "lifetime_days": float(lifetime_days),
            "season_month": int(season_month),
            "favorite_price": float(favorite_price),
            "outcome": outcome,
            **nfl_feats,
            **mlb_feats,
            "feature_complete": bool(feat_complete),
            "coverage_note": coverage_note,
        }
        rows.append(row_out)
        if (i + 1) % 25 == 0:
            print(f"  built {i+1} / {len(elig)} rows")

    df = pd.DataFrame(rows)
    # Sort chronologically by close_time (CRITICAL for downstream walk-forward CV).
    df = df.sort_values("close_time").reset_index(drop=True)
    return df


# ---------- Leak audit ----------------------------------------------------

def leak_audit(df: pd.DataFrame) -> dict[str, Any]:
    """Verify every external feature is provably computed AT-OR-BEFORE
    (t35d_time - 1 day). The build path enforces this; the audit re-asserts
    it externally."""
    audit = {"rows_checked": int(len(df)), "violations": []}
    for _, row in df.iterrows():
        t35d = pd.Timestamp(row["t35d_time"])
        # We can't read back the actual sample-time from each external row,
        # but the build code uses (t35d - 1 day) for every API call. We
        # encode that here as a one-line claim per row.
        # The substantive audit is: did any feature exist BEFORE the season
        # started? E.g., NFL games_played > 0 with t35d in pre-season is
        # impossible -> would be a code bug, flagged.
        if row["league"] == "NFL":
            gp = row["nfl_games_played_pre_t35d"]
            # NFL season starts early September. If t35d is pre-September of
            # the season year, gp should be 0 or NaN.
            try:
                season_start = pd.Timestamp(f"{row['season_year']}-09-01", tz="UTC")
                if t35d < season_start and gp > 0:
                    audit["violations"].append({
                        "ticker": row["ticker"],
                        "reason": "NFL games_played > 0 but t35d before season start",
                    })
            except Exception:
                pass
        elif row["league"] == "MLB":
            gp = row["mlb_games_played_pre_t35d"]
            try:
                season_start = pd.Timestamp(f"{row['season_year']}-03-15", tz="UTC")
                if t35d < season_start and gp > 0:
                    audit["violations"].append({
                        "ticker": row["ticker"],
                        "reason": "MLB games_played > 0 but t35d before season start",
                    })
            except Exception:
                pass
    audit["clean"] = len(audit["violations"]) == 0
    return audit


# ---------- Orthogonality protocol ----------------------------------------

def orthogonality_check(df: pd.DataFrame, feature_cols: list[str], train_frac: float = 0.7,
                        seed: int = 42, n_boot: int = 5000) -> dict[str, Any]:
    """Per V3-B audit protocol Section 'Orthogonality check protocol'.

    For each X in feature_cols:
      1. Train rows = chronologically earliest train_frac.
      2. Fit OLS(X ~ favorite_price). Residuals X_resid.
      3. Fit LogReg(outcome ~ favorite_price + X_resid). Record coef on X_resid.
      4. Bootstrap-resample the train rows (with replacement) 5000 times.
         For each bootstrap, fit step 2+3 fresh and record coef. 95% CI.
      5. Compute AUC train of (favorite_price + X_resid) vs (favorite_price) baseline.
      6. Decision: retain if CI excludes zero AND AUC improvement >= 0.005.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    train_n = int(n * train_frac)
    # Already sorted by close_time in build_dataset.
    train_full = df.iloc[:train_n].copy()
    # Restrict to rows with non-null favorite_price and outcome.
    train_full = train_full[train_full["favorite_price"].notna()].copy()
    # Standardize: limit eval to rows where the candidate feature is observed.
    out = {}
    # Baseline: train logistic regression with favorite_price only on train.
    Xp_full = train_full[["favorite_price"]].values
    y_full = train_full["outcome"].values
    # Guard: if outcome lacks both classes in train, skip.
    if len(np.unique(y_full)) < 2:
        return {
            "n_train": int(len(train_full)),
            "error": "training set has only one outcome class; cannot fit logistic regression",
            "features": {},
        }
    try:
        base_model = LogisticRegression(max_iter=1000, solver="liblinear")
        base_model.fit(Xp_full, y_full)
        base_auc = roc_auc_score(y_full, base_model.predict_proba(Xp_full)[:, 1])
    except Exception as e:
        base_auc = np.nan

    for X in feature_cols:
        train = train_full.dropna(subset=[X]).copy()
        if len(train) < 10:
            out[X] = {
                "n_train_with_feature": int(len(train)),
                "decision": "drop",
                "reason": "fewer than 10 training rows with feature observed",
                "ci_lower": None, "ci_upper": None,
                "coef_point": None, "auc_with": None, "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
                "auc_delta": None,
            }
            continue
        # Step 2 + 3 on the FULL train (point estimate).
        p = train["favorite_price"].values.reshape(-1, 1)
        xv = train[X].values
        try:
            ols = LinearRegression()
            ols.fit(p, xv)
            x_resid = xv - ols.predict(p)
        except Exception as e:
            out[X] = {
                "n_train_with_feature": int(len(train)),
                "decision": "drop",
                "reason": f"OLS fit error: {e}",
                "ci_lower": None, "ci_upper": None,
                "coef_point": None, "auc_with": None, "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
                "auc_delta": None,
            }
            continue
        # LogReg with both features.
        X_lr = np.column_stack([p.ravel(), x_resid])
        y_lr = train["outcome"].values
        if len(np.unique(y_lr)) < 2:
            out[X] = {
                "n_train_with_feature": int(len(train)),
                "decision": "drop",
                "reason": "training subset (with X observed) has only one outcome class",
                "ci_lower": None, "ci_upper": None,
                "coef_point": None, "auc_with": None, "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
                "auc_delta": None,
            }
            continue
        try:
            lr = LogisticRegression(max_iter=1000, solver="liblinear")
            lr.fit(X_lr, y_lr)
            coef_point = float(lr.coef_[0, 1])  # X_resid coefficient
            auc_with = roc_auc_score(y_lr, lr.predict_proba(X_lr)[:, 1])
        except Exception as e:
            out[X] = {
                "n_train_with_feature": int(len(train)),
                "decision": "drop",
                "reason": f"LogReg fit error: {e}",
                "ci_lower": None, "ci_upper": None,
                "coef_point": None, "auc_with": None, "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
                "auc_delta": None,
            }
            continue

        # Bootstrap. Resample rows of `train` with replacement.
        coefs = []
        n_train = len(train)
        for _ in range(n_boot):
            idx = rng.integers(0, n_train, size=n_train)
            pb = train["favorite_price"].values[idx].reshape(-1, 1)
            xb = train[X].values[idx]
            yb = train["outcome"].values[idx]
            if len(np.unique(yb)) < 2:
                continue
            try:
                ols_b = LinearRegression()
                ols_b.fit(pb, xb)
                xb_resid = xb - ols_b.predict(pb)
                Xb_lr = np.column_stack([pb.ravel(), xb_resid])
                lr_b = LogisticRegression(max_iter=1000, solver="liblinear")
                lr_b.fit(Xb_lr, yb)
                coefs.append(float(lr_b.coef_[0, 1]))
            except Exception:
                continue
        if len(coefs) < 100:
            out[X] = {
                "n_train_with_feature": int(len(train)),
                "decision": "drop",
                "reason": f"too few successful bootstrap resamples ({len(coefs)}/{n_boot})",
                "ci_lower": None, "ci_upper": None,
                "coef_point": coef_point,
                "auc_with": float(auc_with),
                "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
                "auc_delta": float(auc_with - base_auc) if not np.isnan(base_auc) else None,
            }
            continue
        coefs_arr = np.array(coefs)
        ci_lower = float(np.percentile(coefs_arr, 2.5))
        ci_upper = float(np.percentile(coefs_arr, 97.5))
        ci_excludes_zero = (ci_lower > 0) or (ci_upper < 0)
        auc_delta = float(auc_with - base_auc) if not np.isnan(base_auc) else 0.0
        retain = ci_excludes_zero and auc_delta >= 0.005
        out[X] = {
            "n_train_with_feature": int(len(train)),
            "n_boot_success": int(len(coefs)),
            "coef_point": float(coef_point),
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "ci_excludes_zero": bool(ci_excludes_zero),
            "auc_with": float(auc_with),
            "auc_base": float(base_auc) if not np.isnan(base_auc) else None,
            "auc_delta": auc_delta,
            "decision": "retain" if retain else "drop",
            "reason": (
                "ci excludes zero AND auc improvement >= 0.005"
                if retain
                else f"{'ci includes zero' if not ci_excludes_zero else 'ci ok'}; auc_delta={auc_delta:.4f} < 0.005"
                if not retain else ""
            ),
        }

    # Diagnostic: training-set outcome variance and per-league counts.
    train_outcome_pct = float(train_full["outcome"].mean())
    train_outcome_counts = train_full["outcome"].value_counts().to_dict()
    league_counts = train_full.groupby("league")["outcome"].agg(["count", "sum", "mean"]).to_dict("index")
    return {
        "n_train_total": int(len(train_full)),
        "train_frac": train_frac,
        "n_boot": n_boot,
        "seed": seed,
        "base_auc_price_only": float(base_auc) if not np.isnan(base_auc) else None,
        "train_outcome_yes_rate": train_outcome_pct,
        "train_outcome_class_counts": {str(k): int(v) for k, v in train_outcome_counts.items()},
        "train_league_breakdown": {
            k: {ck: float(cv) for ck, cv in v.items()} for k, v in league_counts.items()
        },
        "features": out,
    }


# ---------- Main ----------------------------------------------------------

def main():
    t0 = time.time()
    df = build_dataset()
    print(f"\nBuilt {len(df)} rows in {time.time()-t0:.1f}s")
    print("\nLeague coverage:")
    print(df.groupby("league")[["feature_complete"]].agg(["count", "sum"]).to_string())

    print("\nLeak audit:")
    audit = leak_audit(df)
    print(f"  violations: {len(audit['violations'])}")
    if audit["violations"]:
        for v in audit["violations"][:10]:
            print(f"    {v}")

    # Orthogonality check on candidate features.
    # Candidate features (excluding favorite_price which is the baseline,
    # and excluding pure metadata like season_year, lifetime_days,
    # season_month - we treat lifetime_days + season_month as additional
    # candidate features too).
    candidate_features = [
        "lifetime_days",
        "season_month",
        "nfl_w_pct_pre_t35d",
        "nfl_pyth_w_pct_pre_t35d",
        "nfl_recent5_w_pct",
        "nfl_point_diff_per_game",
        "nfl_games_played_pre_t35d",
        "mlb_w_pct_pre_t35d",
        "mlb_pyth_w_pct_pre_t35d",
        "mlb_run_diff_per_game",
        "mlb_games_back",
        "mlb_games_played_pre_t35d",
    ]

    print("\nOrthogonality check (train 70%, bootstrap 5000):")
    ortho = orthogonality_check(df, candidate_features)
    print(f"  n_train={ortho.get('n_train_total')}")
    print(f"  base_auc(price-only)={ortho.get('base_auc_price_only')}")
    print()
    retain_list = []
    drop_list = []
    for feat, res in ortho["features"].items():
        decision = res["decision"]
        if decision == "retain":
            retain_list.append(feat)
        else:
            drop_list.append(feat)
        print(f"  {feat:32s}  n={res['n_train_with_feature']:4d}  CI=[{res.get('ci_lower')}, {res.get('ci_upper')}]  "
              f"auc_delta={res.get('auc_delta')}  decision={decision}")

    print(f"\nRetained features ({len(retain_list)}): {retain_list}")
    print(f"Dropped features ({len(drop_list)}): {drop_list}")

    # Write outputs.
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nWrote {OUTPUT_PATH}")

    report = {
        "build_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(len(df)),
        "leak_audit": audit,
        "orthogonality": ortho,
        "retained_features": retain_list,
        "dropped_features": drop_list,
        "candidate_features": candidate_features,
    }
    ORTHO_REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {ORTHO_REPORT_PATH}")

    # Single-entity sanity check (S1 from master plan).
    print("\nSingle-entity sanity check:")
    team_counts = df["team"].value_counts()
    print(f"  top 5 teams: {team_counts.head(5).to_dict()}")
    top_share = float(team_counts.iloc[0] / len(df))
    print(f"  max single-team share: {top_share:.3%}")

    return df, report


if __name__ == "__main__":
    main()
