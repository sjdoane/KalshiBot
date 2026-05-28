"""V5-B1: light orthogonality probe.

For a sample of resolved KXMLBHIT markets, compute one or two Statcast
features as-of T-1d (player's rolling form before the game) and
eyeball-correlate with the actual outcome.

This is the informal Phase 1 feasibility check (Section 4 of the
deliverable). The rigorous orthogonality protocol per v3-B audit runs
in Phase 2.

Run: uv run python -m scripts.v5.probe_orthogonality_light
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "v5"


def main() -> None:
    import pybaseball as pyb
    pyb.cache.enable()

    # Load Kalshi prop inventory (enriched)
    props = pd.read_parquet(DATA_DIR / "kxmlbstatcount_inventory_enriched.parquet")
    # Focus on KXMLBHIT, 1+ floor (most balanced YES/NO)
    hit = props[(props["_series_prefix"] == "KXMLBHIT") & (props["floor_strike"] == 0.5) & (props["result"].isin(["yes", "no"]))].copy()
    print(f"KXMLBHIT 1+ binary resolved: n={len(hit)}")

    # Sample 20 markets (10 yes + 10 no balanced)
    yes_sample = hit[hit["result"] == "yes"].sample(min(10, (hit["result"] == "yes").sum()), random_state=42)
    no_sample = hit[hit["result"] == "no"].sample(min(10, (hit["result"] == "no").sum()), random_state=42)
    sample = pd.concat([yes_sample, no_sample]).reset_index(drop=True)
    print(f"Sample n={len(sample)}: {sample['result'].value_counts().to_dict()}")

    # Load 2026 statcast pulled earlier
    sc = pd.read_parquet(DATA_DIR / "statcast_2026_season_to_date.parquet")
    sc["game_date_str"] = sc["game_date"].astype(str)
    print(f"Statcast 2026: n_rows={len(sc)}, dates {sc['game_date_str'].min()} -> {sc['game_date_str'].max()}")

    # IMPORTANT: pybaseball's 'player_name' column is the PITCHER, not the batter.
    # Batter is referenced by MLBAM ID in the 'batter' column. To map Kalshi
    # player names ('First Last') to MLBAM IDs we use pybaseball.playerid_lookup.

    # Build the per-batter per-day aggregate using batter ID (no name needed yet)
    HIT_EVENTS = {"single", "double", "triple", "home_run"}
    sc_pa_end = sc[sc["events"].notna()].copy()
    sc_pa_end["is_hit"] = sc_pa_end["events"].isin(HIT_EVENTS)
    sc_pa_end["is_pa"] = 1
    per_b_day = sc_pa_end.groupby(["batter", "game_date_str"]).agg(
        pa=("is_pa", "sum"),
        hits=("is_hit", "sum"),
    ).reset_index()

    # Now look up Kalshi player names -> MLBAM IDs. Cache the lookup table once.
    print("\nLoading playerid_lookup table (one-shot)...")
    start = time.time()
    lookup = pyb.chadwick_register()
    print(f"  loaded in {time.time()-start:.1f}s, n_rows={len(lookup)}")
    # The lookup has 'name_first', 'name_last', 'key_mlbam' columns
    lookup["name_first_lower"] = lookup["name_first"].astype(str).str.lower().str.strip()
    lookup["name_last_lower"] = lookup["name_last"].astype(str).str.lower().str.strip()
    lookup_active = lookup[lookup["key_mlbam"].notna() & (lookup["mlb_played_last"] >= 2024)].copy()
    print(f"  active 2024+ players: n={len(lookup_active)}")

    def kalshi_to_mlbam(name: str) -> int | None:
        """Best-effort lookup: split 'First Last' Kalshi name, search Chadwick."""
        if pd.isna(name):
            return None
        s = str(name).strip()
        # Handle suffix "Jr." / "Sr."
        s_clean = s.replace(" Jr.", "").replace(" Sr.", "").replace(" Jr", "").replace(" Sr", "").replace(" III", "").replace(" II", "")
        parts = s_clean.split()
        if len(parts) < 2:
            return None
        first = parts[0].lower()
        last = " ".join(parts[1:]).lower()  # handle "De La Cruz" etc
        m = lookup_active[(lookup_active["name_first_lower"] == first) & (lookup_active["name_last_lower"] == last)]
        if len(m) == 1:
            return int(m["key_mlbam"].iloc[0])
        if len(m) > 1:
            # multiple matches; take the most recent
            m = m.sort_values("mlb_played_last", ascending=False)
            return int(m["key_mlbam"].iloc[0])
        return None

    # Per-batter aggregate already keyed on MLBAM (batter col)
    per_b_day = per_b_day.sort_values(["batter", "game_date_str"]).reset_index(drop=True)

    print("\n=== Per-market feature lookups ===")
    rows = []
    for _, market in sample.iterrows():
        kalshi_player = market["player"]
        game_date = market["game_date"]
        result = market["result"]
        last_px = float(market["last_price_dollars"])
        ticker = market["ticker"]

        # Convert "2026-APR-29" -> "2026-04-29"
        try:
            mon_map = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05",
                       "JUN": "06", "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10",
                       "NOV": "11", "DEC": "12"}
            parts = game_date.split("-")
            iso_date = f"{parts[0]}-{mon_map[parts[1]]}-{parts[2]}"
        except Exception:
            iso_date = None

        mlbam = kalshi_to_mlbam(kalshi_player)

        feature_ba14 = None
        feature_pa_count = None
        if iso_date and mlbam:
            cutoff = iso_date  # AS-OF: strictly games BEFORE this game's date
            matched = per_b_day[(per_b_day["batter"] == mlbam) & (per_b_day["game_date_str"] < cutoff)]
            if len(matched) > 0:
                last14 = matched.tail(14)  # last 14 GAMES (not days); close enough for light check
                feature_ba14 = float(last14["hits"].sum() / max(last14["pa"].sum(), 1))
                feature_pa_count = int(last14["pa"].sum())

        rows.append({
            "ticker": ticker,
            "kalshi_player": kalshi_player,
            "mlbam": mlbam,
            "game_date": iso_date,
            "kalshi_last_price": last_px,
            "result": result,
            "feature_ba_last_14games": feature_ba14,
            "feature_pa_last_14games": feature_pa_count,
            "outcome_y": 1 if result == "yes" else 0,
        })

    out = pd.DataFrame(rows)
    print(out.to_string())

    # Eyeball-correlate
    out_clean = out.dropna(subset=["feature_ba_last_14games"])
    print(f"\nFeature extraction coverage: {len(out_clean)}/{len(out)} markets had >=1 prior PA")
    if len(out_clean) > 0:
        yes_ba = out_clean[out_clean["outcome_y"] == 1]["feature_ba_last_14games"].mean()
        no_ba = out_clean[out_clean["outcome_y"] == 0]["feature_ba_last_14games"].mean()
        print(f"Mean BA14games | result=YES: {yes_ba:.3f}")
        print(f"Mean BA14games | result=NO:  {no_ba:.3f}")
        try:
            from scipy.stats import spearmanr, pointbiserialr
            if out_clean["feature_ba_last_14games"].std() > 0:
                r_outcome, p_outcome = spearmanr(out_clean["feature_ba_last_14games"], out_clean["outcome_y"])
                r_price, p_price = spearmanr(out_clean["feature_ba_last_14games"], out_clean["kalshi_last_price"])
                print(f"Spearman r(BA14, outcome) = {r_outcome:.3f}, p={p_outcome:.3f}")
                print(f"Spearman r(BA14, price)   = {r_price:.3f}, p={p_price:.3f}")
        except Exception as e:
            print(f"(scipy stats unavailable: {e})")
        print(f"\nKalshi price calibration:")
        print(f"  YES mean price = {out[out['outcome_y']==1]['kalshi_last_price'].mean():.3f}")
        print(f"  NO  mean price = {out[out['outcome_y']==0]['kalshi_last_price'].mean():.3f}")

    out_path = DATA_DIR / "orthogonality_light_sample.parquet"
    out.to_parquet(out_path)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
