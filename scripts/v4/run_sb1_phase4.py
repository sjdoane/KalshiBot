"""V4-G2 S-B1 cutoff-leak sanity check on Phase 4 sample.

V4-F's S-B1 used the V4-C pilot's PRE-cutoff sample (those markets
closed before V4-F's incorrect Jan 2026 assumption). V4-G2's window
is [2025-08-01, 2026-03-25), so all sample rows are post the actual
Haiku 4.5 training cutoff (Jul 2025). The honest S-B1 here measures:

  Among the rerun-sample rows, does the LLM forecast DIFFER materially
  when given full ticker + dates vs when given an anonymized version
  (year only, no ticker)? Big diff => the LLM is using cues from
  ticker/dates (potential memorization).

Sample: random n=10 from the V4-G2 phase4 sample (deterministic seed).

Output: appended to data/v4/llm_phase4_gate_results.json under "SB1_phase4".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kalshi_bot_v4.llm_forecaster import Forecaster, HAIKU_MODEL  # noqa: E402

SAMPLE_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_sample.parquet"
RESULTS_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_gate_results.json"
N_TEST = 10


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


def main() -> None:
    df = pd.read_parquet(SAMPLE_PATH)
    df = df.dropna(subset=["title", "rules_primary"]).copy()
    df["outcome"] = df["outcome_favorite"].astype(int)

    sub = df.sample(n=min(N_TEST, len(df)), random_state=42).copy()
    print(f"S-B1 sample n={len(sub)} (out of phase4 n={len(df)})")
    print(f"Sample yes_rate (favorite-side): {sub['outcome'].mean():.3f}")
    print(f"Sample close_time range: {sub['close_time'].min()} to {sub['close_time'].max()}")
    print()

    forecaster_full = Forecaster(model=HAIKU_MODEL, prompt_variant="C", enable_cache=True)
    forecaster_anon = Forecaster(model=HAIKU_MODEL, prompt_variant="ANON", enable_cache=True)

    records = []
    for _, row in sub.iterrows():
        rd = row.to_dict()
        # Strip favorite_price (defensive)
        rd.pop("favorite_price", None)
        r_full = forecaster_full.forecast(rd)
        r_anon = forecaster_anon.forecast(rd)
        records.append({
            "ticker": row["ticker"],
            "series": row["series_ticker"],
            "outcome": int(row["outcome"]),
            "favorite_price": float(row["favorite_price"]),
            "prob_full": r_full.prob_yes,
            "prob_anon": r_anon.prob_yes,
            "diff_full_minus_anon": r_full.prob_yes - r_anon.prob_yes,
            "abs_diff": abs(r_full.prob_yes - r_anon.prob_yes),
        })
        print(f"  {row['ticker']:35s}  full={r_full.prob_yes:.3f}  anon={r_anon.prob_yes:.3f}  diff={r_full.prob_yes - r_anon.prob_yes:+.3f}")

    rec_df = pd.DataFrame(records)
    probs_full = rec_df["prob_full"].to_numpy()
    probs_anon = rec_df["prob_anon"].to_numpy()
    outcomes = rec_df["outcome"].to_numpy()

    summary = {
        "n": int(len(rec_df)),
        "mean_abs_diff": float(rec_df["abs_diff"].mean()),
        "mean_signed_diff_full_minus_anon": float(rec_df["diff_full_minus_anon"].mean()),
        "brier_full": brier(probs_full, outcomes),
        "brier_anon": brier(probs_anon, outcomes),
        "yes_rate_subsample": float(outcomes.mean()),
        "interpretation": (
            "If mean_abs_diff is small (<0.10) and brier_full ~ brier_anon, then "
            "the LLM is not exploiting ticker/date hints for outcome memorization. "
            "A large positive (brier_anon - brier_full) on a post-cutoff sample "
            "(yes rate ~0.90 in our case) would indicate the LLM may be using "
            "cues that recover the outcome better than blind anonymized reasoning."
        ),
        "records": rec_df.to_dict(orient="records"),
        "window_start": "2025-08-01 (Aug 2025; one month past Anthropic Haiku 4.5 Jul 2025 training cutoff)",
        "sample_path": str(SAMPLE_PATH),
        "agent": "V4-G2",
    }
    print()
    print(f"mean_abs_diff: {summary['mean_abs_diff']:.4f}")
    print(f"brier_full: {summary['brier_full']:.4f}  brier_anon: {summary['brier_anon']:.4f}")
    print(f"brier_anon - brier_full: {summary['brier_anon'] - summary['brier_full']:+.4f}")
    print(f"yes_rate: {summary['yes_rate_subsample']:.3f}")

    # Append to results
    if RESULTS_PATH.exists():
        existing = json.loads(RESULTS_PATH.read_text())
    else:
        existing = {}
    existing["SB1_phase4"] = summary
    RESULTS_PATH.write_text(json.dumps(existing, indent=2, default=str))
    print(f"\nResults appended to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
