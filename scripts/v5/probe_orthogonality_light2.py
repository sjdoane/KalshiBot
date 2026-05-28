"""V5-B1: orthogonality light pass v2.

Resample with a better design:
- 10 random KXMLBHIT 2+ markets (floor 1.5) - more balanced YES/NO
- For each, compute T-1 day Statcast: BA last 14 games, recent xwOBA, recent PA count
- Eyeball whether Statcast features predict OUTCOME independent of price

Run: uv run python -m scripts.v5.probe_orthogonality_light2
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

    props = pd.read_parquet(DATA_DIR / "kxmlbstatcount_inventory_enriched.parquet")
    # KXMLBHIT 2+ floor (more YES/NO balance)
    hit2 = props[(props["_series_prefix"] == "KXMLBHIT") & (props["floor_strike"] == 1.5) & (props["result"].isin(["yes", "no"]))].copy()
    print(f"KXMLBHIT 2+ binary resolved: n={len(hit2)}")
    print(f"  YES rate: {(hit2['result'] == 'yes').mean():.3f}")

    # Take a balanced sample
    yes_n = (hit2["result"] == "yes").sum()
    no_n = (hit2["result"] == "no").sum()
    take = 25
    yes_sample = hit2[hit2["result"] == "yes"].sample(min(take // 2, yes_n), random_state=42)
    no_sample = hit2[hit2["result"] == "no"].sample(min(take // 2, no_n), random_state=42)
    # Also draw a "varied price" sample - markets in the 0.20-0.80 mid-band
    px = pd.to_numeric(hit2["last_price_dollars"], errors="coerce")
    midband = hit2[(px >= 0.20) & (px <= 0.80)]
    print(f"Mid-band (0.20-0.80) n={len(midband)}, YES rate={(midband['result']=='yes').mean():.3f}")
    midband_sample = midband.sample(min(30, len(midband)), random_state=42)

    sample = pd.concat([yes_sample, no_sample, midband_sample]).drop_duplicates(subset="ticker").reset_index(drop=True)
    print(f"Combined sample n={len(sample)}: result={sample['result'].value_counts().to_dict()}")

    # Statcast
    sc = pd.read_parquet(DATA_DIR / "statcast_2026_season_to_date.parquet")
    sc["game_date_str"] = sc["game_date"].astype(str)

    HIT_EVENTS = {"single", "double", "triple", "home_run"}
    sc_pa_end = sc[sc["events"].notna()].copy()
    sc_pa_end["is_hit"] = sc_pa_end["events"].isin(HIT_EVENTS)
    sc_pa_end["is_pa"] = 1

    per_b_day = sc_pa_end.groupby(["batter", "game_date_str"]).agg(
        pa=("is_pa", "sum"),
        hits=("is_hit", "sum"),
        xwoba_sum=("estimated_woba_using_speedangle", "sum"),
        xwoba_n=("estimated_woba_using_speedangle", "count"),
    ).reset_index()
    per_b_day = per_b_day.sort_values(["batter", "game_date_str"]).reset_index(drop=True)

    print("\nLoading chadwick_register...")
    start = time.time()
    lookup = pyb.chadwick_register()
    print(f"  loaded in {time.time()-start:.1f}s")
    lookup["name_first_lower"] = lookup["name_first"].astype(str).str.lower().str.strip()
    lookup["name_last_lower"] = lookup["name_last"].astype(str).str.lower().str.strip()
    lookup_active = lookup[lookup["key_mlbam"].notna() & (lookup["mlb_played_last"] >= 2024)].copy()

    def kalshi_to_mlbam(name):
        if pd.isna(name):
            return None
        s = str(name).strip()
        s = s.replace(" Jr.", "").replace(" Sr.", "").replace(" III", "").replace(" II", "")
        parts = s.split()
        if len(parts) < 2:
            return None
        first = parts[0].lower()
        last = " ".join(parts[1:]).lower()
        m = lookup_active[(lookup_active["name_first_lower"] == first) & (lookup_active["name_last_lower"] == last)]
        if len(m) == 1:
            return int(m["key_mlbam"].iloc[0])
        if len(m) > 1:
            m = m.sort_values("mlb_played_last", ascending=False)
            return int(m["key_mlbam"].iloc[0])
        return None

    rows = []
    for _, market in sample.iterrows():
        kalshi_player = market["player"]
        game_date = market["game_date"]
        result = market["result"]
        last_px = float(market["last_price_dollars"])
        ticker = market["ticker"]

        try:
            mon_map = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05",
                       "JUN": "06", "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10",
                       "NOV": "11", "DEC": "12"}
            parts = game_date.split("-")
            iso_date = f"{parts[0]}-{mon_map[parts[1]]}-{parts[2]}"
        except Exception:
            iso_date = None

        mlbam = kalshi_to_mlbam(kalshi_player)

        feature_ba14g = None
        feature_pa_count = None
        feature_xwoba = None
        if iso_date and mlbam:
            matched = per_b_day[(per_b_day["batter"] == mlbam) & (per_b_day["game_date_str"] < iso_date)]
            if len(matched) > 0:
                last14 = matched.tail(14)
                feature_ba14g = float(last14["hits"].sum() / max(last14["pa"].sum(), 1))
                feature_pa_count = int(last14["pa"].sum())
                if last14["xwoba_n"].sum() > 0:
                    feature_xwoba = float(last14["xwoba_sum"].sum() / last14["xwoba_n"].sum())

        rows.append({
            "ticker": ticker,
            "kalshi_player": kalshi_player,
            "mlbam": mlbam,
            "game_date": iso_date,
            "kalshi_last_price": last_px,
            "result": result,
            "ba14g": feature_ba14g,
            "pa14g": feature_pa_count,
            "xwoba14g": feature_xwoba,
            "outcome_y": 1 if result == "yes" else 0,
        })

    out = pd.DataFrame(rows)
    out_path = DATA_DIR / "orthogonality_light_sample_v2.parquet"
    out.to_parquet(out_path)
    print(out.to_string())
    print(f"\nWrote {out_path}")

    # Eyeball the BA14g feature
    clean = out.dropna(subset=["ba14g"])
    print(f"\nFeature coverage: {len(clean)}/{len(out)} markets")
    if len(clean) > 5:
        print(f"BA14g | YES (n={(clean['outcome_y']==1).sum()}): mean={clean[clean['outcome_y']==1]['ba14g'].mean():.3f}")
        print(f"BA14g | NO  (n={(clean['outcome_y']==0).sum()}): mean={clean[clean['outcome_y']==0]['ba14g'].mean():.3f}")
        try:
            from scipy.stats import spearmanr
            if clean["ba14g"].std() > 0:
                r_ba_y, p_ba_y = spearmanr(clean["ba14g"], clean["outcome_y"])
                r_ba_p, p_ba_p = spearmanr(clean["ba14g"], clean["kalshi_last_price"])
                print(f"Spearman r(BA14g, outcome) = {r_ba_y:.3f} (p={p_ba_y:.3f})")
                print(f"Spearman r(BA14g, price)   = {r_ba_p:.3f} (p={p_ba_p:.3f})")
                r_p_y, p_p_y = spearmanr(clean["kalshi_last_price"], clean["outcome_y"])
                print(f"Spearman r(price,  outcome) = {r_p_y:.3f} (p={p_p_y:.3f})")
        except Exception as e:
            print(f"scipy err: {e}")

        # The orthogonality test: regress outcome on price + BA14g
        # Does BA14g add lift beyond price?
        try:
            from sklearn.linear_model import LogisticRegression
            X1 = clean[["kalshi_last_price"]].values
            X2 = clean[["kalshi_last_price", "ba14g"]].values
            y = clean["outcome_y"].values
            if y.std() > 0:
                lr1 = LogisticRegression().fit(X1, y)
                lr2 = LogisticRegression().fit(X2, y)
                from sklearn.metrics import brier_score_loss
                # Use in-sample predict_proba just for the eyeball
                p1 = lr1.predict_proba(X1)[:, 1]
                p2 = lr2.predict_proba(X2)[:, 1]
                b1 = brier_score_loss(y, p1)
                b2 = brier_score_loss(y, p2)
                print(f"\nIn-sample Brier (eyeball only):")
                print(f"  price-only model: {b1:.4f}")
                print(f"  price + BA14g:    {b2:.4f}")
                print(f"  delta: {b2-b1:+.4f}")
                print(f"  Coefficients price+BA14g: {lr2.coef_[0]}")
        except Exception as e:
            print(f"sklearn err: {e}")


if __name__ == "__main__":
    main()
