"""V5-B2 Statcast feature engineering.

This module builds the joined dataset for Kalshi player-prop ML.

Pipeline:
1. `load_kalshi_prop_markets(...)` reads the V5-B1 inventory parquet,
   filters to the four player-prop series (KXMLBHIT, KXMLBHR,
   KXMLBHRR, KXMLBKS) and to binary resolved outcomes (drops the
   small `result == scalar` slice).
2. `extract_player_and_date(...)` parses the Kalshi ticker / market row
   into (player_name, game_date) and maps player_name to MLBAM id via
   pybaseball's chadwick_register (one-shot in-memory lookup).
3. `compute_statcast_features_as_of(...)` aggregates per-player
   Statcast metrics over [as_of - window_days, as_of) with the strict
   `game_date < as_of` AS-OF rule (no same-day leak).
4. `build_dataset(...)` joins markets with features and writes the
   cached parquet.

Leak discipline:
- Statcast queries always use `game_date < market_game_date`. Strict
  less-than excludes the game-of-the-market from the player history.
- The chadwick_register is a static lookup table, not date-indexed,
  so name -> id mapping is leak-free.
- The dataset is sorted chronologically by `game_date` ASC; downstream
  CV (gate.py) just slices contiguously.

Locked thresholds:
- WINDOW_DAYS_LONG = 30 (per brief)
- WINDOW_DAYS_SHORT = 7 (per brief)
- WINDOW_DAYS_FORM = 14 (orthogonality light probe used this)

This module is research-mode only. v1 live trading is untouched.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


def _safe_float(value: Any) -> float:  # noqa: ANN401
    """Coerce a pandas/numpy scalar (possibly pd.NA) to float, with NaN
    for null. Required because pandas extension Float64 .mean() returns
    pd.NA when all entries are NA, which `float()` cannot coerce.
    """
    try:
        if value is None:
            return float("nan")
        if pd.isna(value):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")

# Locked feature windows.
WINDOW_DAYS_LONG: int = 30
WINDOW_DAYS_SHORT: int = 7
WINDOW_DAYS_FORM: int = 14

# Locked target series (per V5-B1 scope amendment).
PROP_SERIES: tuple[str, ...] = ("KXMLBHIT", "KXMLBHR", "KXMLBHRR", "KXMLBKS")

# Path constants.
INVENTORY_PATH = Path("data/v5/kxmlbstatcount_inventory_enriched.parquet")
STATCAST_PATH = Path("data/v5/statcast_2026_season_to_date.parquet")
OUTPUT_PATH = Path("data/v5/prop_dataset.parquet")


def _normalize_name(s: str) -> str:
    """Strip diacritics and lowercase for matching across encodings."""
    if not isinstance(s, str):
        return ""
    decomp = unicodedata.normalize("NFKD", s)
    ascii_only = "".join(c for c in decomp if not unicodedata.combining(c))
    return ascii_only.lower().replace(".", "").replace(",", "").strip()


def load_kalshi_prop_markets(
    series_tickers: list[str] | tuple[str, ...] = PROP_SERIES,
    *,
    eligible_only: bool = True,
    inventory_path: Path = INVENTORY_PATH,
) -> pd.DataFrame:
    """Load resolved player-prop markets from the V5-B1 inventory cache.

    Args:
        series_tickers: series prefixes to retain. Default: PROP_SERIES
            (KXMLBHIT, KXMLBHR, KXMLBHRR, KXMLBKS).
        eligible_only: if True, drop markets whose `result` is not in
            {yes, no} (the small scalar-settlement slice n=3,158).
        inventory_path: parquet path. Defaults to V5-B1's cached file.

    Returns:
        DataFrame with one row per market. Adds parsed columns:
        - `game_date_parsed`: pandas Timestamp (date only)
        - `outcome`: int 0/1 (1 = yes)
        - `favorite_price`: float in [0, 1] from `last_price_dollars`
        - `series`: alias of `_series_prefix`
        - `player`: as-is (raw Kalshi player name)
        Sorted by `game_date_parsed` ASC.
    """
    df = pd.read_parquet(inventory_path)
    series_set = set(series_tickers)
    df = df[df["_series_prefix"].isin(series_set)].copy()
    if eligible_only:
        df = df[df["result"].isin(["yes", "no"])].copy()
    # Parse types.
    df["game_date_parsed"] = pd.to_datetime(
        df["game_date"], format="%Y-%b-%d", errors="coerce",
    )
    df["outcome"] = (df["result"] == "yes").astype(int)
    df["favorite_price"] = pd.to_numeric(df["last_price_dollars"], errors="coerce")
    df["series"] = df["_series_prefix"]
    # Drop NaN game_date or price.
    n_before = len(df)
    df = df.dropna(subset=["game_date_parsed", "favorite_price"]).copy()
    n_after = len(df)
    if n_before != n_after:
        log.info("dropped_na_rows", before=n_before, after=n_after)
    # Sort.
    df = df.sort_values("game_date_parsed").reset_index(drop=True)
    log.info("loaded_kalshi_prop_markets", n=len(df),
             series=sorted(df["series"].unique().tolist()))
    return df


def extract_player_and_date(market_row: pd.Series | dict) -> tuple[str, pd.Timestamp]:
    """Parse a single market row into (player_name, game_date).

    The Kalshi `player` and `game_date_parsed` columns are already
    populated by V5-B1's inventory build, so this is a thin accessor.
    Kept as a separate function to match the brief's API and to make
    the leak boundary explicit.

    Args:
        market_row: Series or dict with `player` and `game_date_parsed`
            keys.

    Returns:
        (player_name, game_date_timestamp).
    """
    if hasattr(market_row, "get"):
        player = market_row.get("player")
        gd = market_row.get("game_date_parsed")
    else:
        player = market_row["player"]
        gd = market_row["game_date_parsed"]
    if not isinstance(player, str):
        player = "" if player is None else str(player)
    if not isinstance(gd, pd.Timestamp):
        gd = pd.to_datetime(gd)
    return player, gd


def build_player_id_lookup(
    player_names: list[str],
    *,
    chadwick_register_df: pd.DataFrame | None = None,
) -> dict[str, int]:
    """Map a list of raw Kalshi player names to MLBAM IDs.

    Uses pybaseball's chadwick_register lookup table (in-memory; ~0.03s
    load on the second-and-later call). For matching we strip
    diacritics and lowercase, so `Jose Ramirez` matches whichever
    encoding Kalshi serialized.

    Returns:
        Dict from raw_player_name -> mlbam_int. Names that fail to
        match are omitted from the dict (caller drops those rows).
    """
    if chadwick_register_df is None:
        import pybaseball as pyb

        pyb.cache.enable()
        chadwick_register_df = pyb.chadwick_register()
    reg = chadwick_register_df.copy()
    # Build normalized full name column.
    reg["_norm_first"] = reg["name_first"].astype(str).apply(_normalize_name)
    reg["_norm_last"] = reg["name_last"].astype(str).apply(_normalize_name)
    reg["_norm_full"] = reg["_norm_first"] + " " + reg["_norm_last"]
    # Restrict to plausibly active MLB players (played in or after 2020)
    # to reduce ambiguous matches; the prop universe is 2026 players.
    reg = reg[reg["mlb_played_last"].fillna(0) >= 2020].copy()

    out: dict[str, int] = {}
    unmatched: list[str] = []
    for raw_name in set(player_names):
        if not isinstance(raw_name, str) or raw_name == "":
            continue
        norm = _normalize_name(raw_name)
        # Strip common Jr./III/II/Sr. suffixes for matching.
        norm_no_suffix = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", norm).strip()
        norm_no_suffix = re.sub(r"\s+", " ", norm_no_suffix).strip()
        # Try exact full-name match first.
        cand = reg[reg["_norm_full"] == norm_no_suffix]
        if len(cand) == 0:
            cand = reg[reg["_norm_full"] == norm]
        if len(cand) == 0:
            unmatched.append(raw_name)
            continue
        if len(cand) > 1:
            # Multiple matches: prefer the one with the latest
            # `mlb_played_last`. This handles e.g. "Luis Garcia" who
            # has had multiple MLB careers.
            cand = cand.sort_values("mlb_played_last", ascending=False)
        mlbam = cand.iloc[0]["key_mlbam"]
        if pd.isna(mlbam):
            unmatched.append(raw_name)
            continue
        out[raw_name] = int(mlbam)
    log.info("player_id_lookup", matched=len(out),
             unmatched=len(unmatched), unmatched_sample=unmatched[:10])
    return out


def load_statcast(statcast_path: Path = STATCAST_PATH) -> pd.DataFrame:
    """Load the V5-B1 cached 2026 Statcast pitch-by-pitch.

    Returns:
        DataFrame with `game_date` parsed to Timestamp, plus the
        original 118 Statcast columns.
    """
    sc = pd.read_parquet(statcast_path)
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    return sc


def _aggregate_batter_window(
    sc_window: pd.DataFrame,
    *,
    prefix: str,
) -> dict[str, float]:
    """Aggregate batter Statcast features over a window.

    Args:
        sc_window: Statcast rows where `batter == player_id` and
            `game_date < as_of`.
        prefix: string prefix for the returned dict keys, e.g. "bat30".

    Returns:
        Dict of feature_name -> float (or NaN).
    """
    out: dict[str, float] = {}
    n_pitches = len(sc_window)
    out[f"{prefix}_n_pitches"] = float(n_pitches)
    if n_pitches == 0:
        for k in (
            "_n_pa", "_xba", "_xwoba", "_exit_velo_mean", "_launch_angle_mean",
            "_k_rate", "_bb_rate", "_hard_hit_rate", "_hits_per_pa",
        ):
            out[f"{prefix}{k}"] = float("nan")
        return out
    # n_pa = unique (game_pk, at_bat_number) ending in a PA-terminating event.
    pa_terminal = sc_window["events"].notna()
    n_pa = pa_terminal.sum()
    out[f"{prefix}_n_pa"] = float(n_pa)

    # Quality of contact: filter to batted balls.
    bb = sc_window[sc_window["events"].isin([
        "single", "double", "triple", "home_run", "field_out",
        "force_out", "grounded_into_double_play", "double_play",
        "sac_fly", "sac_bunt", "field_error", "fielders_choice",
        "fielders_choice_out", "sac_fly_double_play",
    ])]
    if len(bb) > 0:
        out[f"{prefix}_xba"] = _safe_float(bb["estimated_ba_using_speedangle"].mean(skipna=True))
        out[f"{prefix}_xwoba"] = _safe_float(bb["estimated_woba_using_speedangle"].mean(skipna=True))
        out[f"{prefix}_exit_velo_mean"] = _safe_float(bb["launch_speed"].mean(skipna=True))
        out[f"{prefix}_launch_angle_mean"] = _safe_float(bb["launch_angle"].mean(skipna=True))
        # Hard-hit: launch_speed >= 95 mph.
        hard_hit = (bb["launch_speed"] >= 95).sum()
        out[f"{prefix}_hard_hit_rate"] = _safe_float(hard_hit / len(bb)) if len(bb) > 0 else float("nan")
    else:
        for k in (
            "_xba", "_xwoba", "_exit_velo_mean", "_launch_angle_mean",
            "_hard_hit_rate",
        ):
            out[f"{prefix}{k}"] = float("nan")

    # Plate discipline (K rate, BB rate, hits/PA).
    if n_pa > 0:
        k_events = sc_window["events"].isin(["strikeout", "strikeout_double_play"]).sum()
        bb_events = sc_window["events"].isin(["walk", "intent_walk"]).sum()
        hit_events = sc_window["events"].isin(["single", "double", "triple", "home_run"]).sum()
        out[f"{prefix}_k_rate"] = _safe_float(k_events / n_pa)
        out[f"{prefix}_bb_rate"] = _safe_float(bb_events / n_pa)
        out[f"{prefix}_hits_per_pa"] = _safe_float(hit_events / n_pa)
    else:
        out[f"{prefix}_k_rate"] = float("nan")
        out[f"{prefix}_bb_rate"] = float("nan")
        out[f"{prefix}_hits_per_pa"] = float("nan")
    return out


def _aggregate_pitcher_window(
    sc_window: pd.DataFrame,
    *,
    prefix: str,
) -> dict[str, float]:
    """Aggregate pitcher Statcast features over a window.

    Args:
        sc_window: Statcast rows where `pitcher == player_id` and
            `game_date < as_of`.
        prefix: e.g. "pit30".

    Returns:
        Dict of feature_name -> float.
    """
    out: dict[str, float] = {}
    n_pitches = len(sc_window)
    out[f"{prefix}_n_pitches"] = float(n_pitches)
    if n_pitches == 0:
        for k in (
            "_n_pa", "_k_rate", "_bb_rate", "_hits_allowed_per_pa",
            "_xwoba_allowed", "_release_speed_mean", "_n_games",
        ):
            out[f"{prefix}{k}"] = float("nan")
        return out
    n_pa = sc_window["events"].notna().sum()
    out[f"{prefix}_n_pa"] = float(n_pa)
    out[f"{prefix}_n_games"] = float(sc_window["game_pk"].nunique())
    out[f"{prefix}_release_speed_mean"] = _safe_float(sc_window["release_speed"].mean(skipna=True))
    if n_pa > 0:
        k_events = sc_window["events"].isin(["strikeout", "strikeout_double_play"]).sum()
        bb_events = sc_window["events"].isin(["walk", "intent_walk"]).sum()
        hit_events = sc_window["events"].isin(["single", "double", "triple", "home_run"]).sum()
        out[f"{prefix}_k_rate"] = _safe_float(k_events / n_pa)
        out[f"{prefix}_bb_rate"] = _safe_float(bb_events / n_pa)
        out[f"{prefix}_hits_allowed_per_pa"] = _safe_float(hit_events / n_pa)
    else:
        for k in ("_k_rate", "_bb_rate", "_hits_allowed_per_pa"):
            out[f"{prefix}{k}"] = float("nan")
    # xwOBA-against (batted balls only).
    bb = sc_window[sc_window["events"].isin([
        "single", "double", "triple", "home_run", "field_out",
        "force_out", "grounded_into_double_play", "double_play",
        "sac_fly",
    ])]
    if len(bb) > 0:
        out[f"{prefix}_xwoba_allowed"] = _safe_float(bb["estimated_woba_using_speedangle"].mean(skipna=True))
    else:
        out[f"{prefix}_xwoba_allowed"] = float("nan")
    return out


def compute_statcast_features_as_of(
    player_id: int,
    as_of_date: pd.Timestamp | str,
    *,
    statcast_batter_grouped: dict | None = None,
    statcast_pitcher_grouped: dict | None = None,
    is_pitcher: bool = False,
    window_days_long: int = WINDOW_DAYS_LONG,
    window_days_short: int = WINDOW_DAYS_SHORT,
    window_days_form: int = WINDOW_DAYS_FORM,
) -> dict[str, float]:
    """Aggregate per-player Statcast metrics over windows preceding
    `as_of_date`.

    AS-OF discipline: only rows with `game_date < as_of_date` are
    included. Strict less-than excludes same-day games (no leak).

    Args:
        player_id: MLBAM id.
        as_of_date: market game date (Timestamp or date string).
        statcast_batter_grouped: pre-grouped dict[player_id, DataFrame]
            of Statcast rows where batter == player_id. Pass once per
            build; the function will look up player_id in O(1).
        statcast_pitcher_grouped: same but indexed by pitcher.
        is_pitcher: if True, compute pitcher-side features instead of
            batter-side features. For KXMLBKS markets the player is the
            starting pitcher; for HIT/HR/HRR the player is the batter.
        window_days_long: default 30
        window_days_short: default 7
        window_days_form: default 14

    Returns:
        Dict of feature_name -> float (or NaN). Always returns a fixed
        schema regardless of data availability. NaN means the player
        had no qualifying Statcast rows in that window (rookie call-up,
        injury return, etc.).
    """
    as_of = pd.to_datetime(as_of_date)
    out: dict[str, float] = {}
    # Resolve player history.
    if is_pitcher:
        if statcast_pitcher_grouped is None:
            raise ValueError("is_pitcher=True requires statcast_pitcher_grouped")
        history = statcast_pitcher_grouped.get(player_id, pd.DataFrame())
        agg_fn = _aggregate_pitcher_window
        prefix_base = "pit"
    else:
        if statcast_batter_grouped is None:
            raise ValueError("is_pitcher=False requires statcast_batter_grouped")
        history = statcast_batter_grouped.get(player_id, pd.DataFrame())
        agg_fn = _aggregate_batter_window
        prefix_base = "bat"

    # Restrict to strict-less-than as_of (no same-day leak).
    if len(history) == 0 or "game_date" not in history.columns:
        # Empty fallback DataFrame with the columns the aggregators
        # require so downstream indexing doesn't KeyError.
        history_prior = pd.DataFrame({
            "game_date": pd.Series([], dtype="datetime64[ns]"),
            "events": pd.Series([], dtype="object"),
            "launch_speed": pd.Series([], dtype="float64"),
            "launch_angle": pd.Series([], dtype="float64"),
            "estimated_ba_using_speedangle": pd.Series([], dtype="float64"),
            "estimated_woba_using_speedangle": pd.Series([], dtype="float64"),
            "release_speed": pd.Series([], dtype="float64"),
            "game_pk": pd.Series([], dtype="int64"),
        })
    else:
        history_prior = history[history["game_date"] < as_of]

    # Long window.
    cutoff_long = as_of - pd.Timedelta(days=window_days_long)
    win_long = history_prior[history_prior["game_date"] >= cutoff_long]
    out.update(agg_fn(win_long, prefix=f"{prefix_base}{window_days_long}"))

    # Short window.
    cutoff_short = as_of - pd.Timedelta(days=window_days_short)
    win_short = history_prior[history_prior["game_date"] >= cutoff_short]
    out.update(agg_fn(win_short, prefix=f"{prefix_base}{window_days_short}"))

    # Form window (14d for batter only; for pitcher we keep symmetry).
    cutoff_form = as_of - pd.Timedelta(days=window_days_form)
    win_form = history_prior[history_prior["game_date"] >= cutoff_form]
    out.update(agg_fn(win_form, prefix=f"{prefix_base}{window_days_form}"))

    # Season-to-date (anchor / context).
    out.update(agg_fn(history_prior, prefix=f"{prefix_base}std"))

    # Differential: long-window vs season-to-date (recent form indicator).
    # Only meaningful for batters with the xba metric.
    if not is_pitcher:
        xba_long = out.get(f"{prefix_base}{window_days_long}_xba", float("nan"))
        xba_std = out.get(f"{prefix_base}std_xba", float("nan"))
        if not (np.isnan(xba_long) or np.isnan(xba_std)):
            out[f"{prefix_base}_xba_diff_long_vs_std"] = float(xba_long - xba_std)
        else:
            out[f"{prefix_base}_xba_diff_long_vs_std"] = float("nan")
    else:
        # Pitcher: K-rate differential (recent vs season).
        k_long = out.get(f"{prefix_base}{window_days_long}_k_rate", float("nan"))
        k_std = out.get(f"{prefix_base}std_k_rate", float("nan"))
        if not (np.isnan(k_long) or np.isnan(k_std)):
            out[f"{prefix_base}_k_rate_diff_long_vs_std"] = float(k_long - k_std)
        else:
            out[f"{prefix_base}_k_rate_diff_long_vs_std"] = float("nan")
    return out


def build_dataset(
    market_df: pd.DataFrame,
    statcast_df: pd.DataFrame,
    *,
    output_path: Path = OUTPUT_PATH,
    drop_unmatched: bool = True,
    write_parquet: bool = True,
) -> pd.DataFrame:
    """Join the Kalshi prop markets with per-player Statcast features.

    Args:
        market_df: output of `load_kalshi_prop_markets`.
        statcast_df: pitch-by-pitch Statcast DataFrame (from
            `load_statcast`).
        output_path: where to cache the joined parquet. Pass write_parquet=False
            to skip writing (useful for tests).
        drop_unmatched: if True, drop rows whose player_name failed
            to map to an MLBAM id; otherwise leave features as NaN.

    Returns:
        DataFrame with one row per market and feature columns added.
        Sorted by `game_date_parsed` ASC.
    """
    log.info("build_dataset_start", n_markets=len(market_df))
    # Build player_id lookup.
    player_names = market_df["player"].astype(str).unique().tolist()
    name_to_id = build_player_id_lookup(player_names)
    market_df = market_df.copy()
    market_df["mlbam_id"] = market_df["player"].map(name_to_id)
    n_unmatched = market_df["mlbam_id"].isna().sum()
    log.info("name_to_id_join", matched=int((~market_df["mlbam_id"].isna()).sum()),
             unmatched=int(n_unmatched))
    if drop_unmatched:
        market_df = market_df.dropna(subset=["mlbam_id"]).copy()
        market_df["mlbam_id"] = market_df["mlbam_id"].astype(int)

    # Tag pitcher vs batter prop.
    market_df["is_pitcher_prop"] = market_df["series"] == "KXMLBKS"

    # Pre-group Statcast for O(1) lookup per player_id.
    log.info("statcast_grouping_start", n_pitches=len(statcast_df))
    bat_groups = {
        int(pid): grp for pid, grp in statcast_df.groupby("batter", sort=False)
    }
    pit_groups = {
        int(pid): grp for pid, grp in statcast_df.groupby("pitcher", sort=False)
    }
    log.info("statcast_grouped",
             n_batters=len(bat_groups), n_pitchers=len(pit_groups))

    # Compute features per unique (player_id, game_date, is_pitcher_prop).
    # Many Kalshi markets share the same (player, game_date) pair across
    # threshold ladders; cache feature computations to avoid duplicate
    # work.
    feature_cache: dict[tuple[int, pd.Timestamp, bool], dict[str, float]] = {}
    feature_records: list[dict[str, float]] = []
    for i, row in enumerate(market_df.itertuples(index=False), 1):
        pid = int(row.mlbam_id)
        gd = row.game_date_parsed
        is_p = bool(row.is_pitcher_prop)
        cache_key = (pid, gd, is_p)
        if cache_key in feature_cache:
            feats = feature_cache[cache_key]
        else:
            feats = compute_statcast_features_as_of(
                pid, gd,
                statcast_batter_grouped=bat_groups,
                statcast_pitcher_grouped=pit_groups,
                is_pitcher=is_p,
            )
            feature_cache[cache_key] = feats
        feature_records.append(feats)
        if i % 20000 == 0:
            log.info("feature_extraction_progress", processed=i,
                     unique_keys_cached=len(feature_cache))
    feat_df = pd.DataFrame(feature_records, index=market_df.index)
    joined = pd.concat([market_df, feat_df], axis=1)

    # Sort chronologically for downstream CV.
    joined = joined.sort_values("game_date_parsed").reset_index(drop=True)

    # Add a normalized close_time column for gate.py compatibility.
    if "close_time_dt" in joined.columns:
        joined["close_time"] = joined["close_time_dt"]
    else:
        joined["close_time"] = pd.to_datetime(joined["close_time"], errors="coerce")

    log.info("build_dataset_done",
             n_rows=len(joined),
             unique_player_game_pairs=len(feature_cache))

    if write_parquet:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Drop columns that parquet may struggle with (mixed dtype).
        out_df = joined.copy()
        # Some columns from the inventory have object/mixed types -
        # convert to str for safety.
        for col in out_df.columns:
            if out_df[col].dtype == object and col not in ("player", "ticker",
                                                            "series", "_series_prefix",
                                                            "result", "title",
                                                            "yes_sub_title",
                                                            "primary_participant_key",
                                                            "no_sub_title",
                                                            "strike_type"):
                try:
                    out_df[col] = out_df[col].astype(str)
                except Exception:  # noqa: BLE001
                    out_df = out_df.drop(columns=[col])
        out_df.to_parquet(output_path, index=False)
        log.info("dataset_written", path=str(output_path))
    return joined


def get_feature_column_names() -> list[str]:
    """Return the canonical list of feature column names produced by
    `build_dataset`.

    These are the columns the orthogonality probe and model training
    will iterate over. We list batter-only AND pitcher-only sets; the
    join leaves NaN for the other set so downstream code filters per
    series.
    """
    batter_features: list[str] = []
    pitcher_features: list[str] = []
    for window_days in (WINDOW_DAYS_LONG, WINDOW_DAYS_SHORT, WINDOW_DAYS_FORM):
        for suffix in (
            "n_pitches", "n_pa", "xba", "xwoba", "exit_velo_mean",
            "launch_angle_mean", "k_rate", "bb_rate", "hard_hit_rate",
            "hits_per_pa",
        ):
            batter_features.append(f"bat{window_days}_{suffix}")
        for suffix in (
            "n_pitches", "n_pa", "k_rate", "bb_rate", "hits_allowed_per_pa",
            "xwoba_allowed", "release_speed_mean", "n_games",
        ):
            pitcher_features.append(f"pit{window_days}_{suffix}")
    # Season-to-date.
    for suffix in (
        "n_pitches", "n_pa", "xba", "xwoba", "exit_velo_mean",
        "launch_angle_mean", "k_rate", "bb_rate", "hard_hit_rate",
        "hits_per_pa",
    ):
        batter_features.append(f"batstd_{suffix}")
    for suffix in (
        "n_pitches", "n_pa", "k_rate", "bb_rate", "hits_allowed_per_pa",
        "xwoba_allowed", "release_speed_mean", "n_games",
    ):
        pitcher_features.append(f"pitstd_{suffix}")
    # Differentials.
    batter_features.append("bat_xba_diff_long_vs_std")
    pitcher_features.append("pit_k_rate_diff_long_vs_std")
    return batter_features + pitcher_features
