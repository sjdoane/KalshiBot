"""V5-C2 conditional gate runner.

Only runs if 1+ features survived orthogonality probe. Builds a fresh
LogReg(outcome ~ favorite_price + survivors) using the v2 locked C1-C6
gate from src/kalshi_bot_v2/gate.py.

Trade rule: should_trade = predicted_prob > favorite_price + 0.02 (per V5-C2 brief).

Output: data/v5/crypto_gate_results.json

Run: uv run python -m scripts.v5.run_v5c_gate
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot_v2.gate import evaluate  # noqa: E402
from kalshi_bot_v5.crypto_features import make_trainer  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "v5"
DATASET_PATH = DATA_DIR / "v5c_orthogonality_data.parquet"
REPORT_PATH = DATA_DIR / "v5c_orthogonality_report.json"
GATE_PATH = DATA_DIR / "crypto_gate_results.json"


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def main() -> int:
    if not REPORT_PATH.exists():
        log("ERROR: orthogonality report missing; run orthogonality probe first")
        return 1
    with open(REPORT_PATH) as f:
        report = json.load(f)
    retained = report.get("features_retained", [])
    log(f"Orthogonality features_retained = {retained}")
    if not retained:
        log("0 features survived orthogonality; declaring null. No gate run.")
        with open(GATE_PATH, "w") as f:
            json.dump(
                {
                    "verdict": "NULL_AT_ORTHOGONALITY",
                    "note": (
                        "0 features survived V5-C2 orthogonality probe; "
                        "no model trained; locked C1-C6 gate not executed. "
                        "Per kill-early principle."
                    ),
                    "retained_features": [],
                },
                f,
                indent=2,
            )
        log(f"Wrote {GATE_PATH}")
        return 0

    df = pd.read_parquet(DATASET_PATH)
    df = df.dropna(subset=["favorite_price", "outcome", "close_time", *retained])
    df = df.sort_values("close_time").reset_index(drop=True)
    log(f"Gate input n={len(df)} after dropping NaN features")

    trainer = make_trainer(retained)
    # Initial decision_fn for the headline holdout pass: train on chronological 70%
    split = int(len(df) * 0.7)
    initial_train = df.iloc[:split]
    headline_decision_fn = trainer(initial_train)

    result = evaluate(
        df,
        headline_decision_fn,
        trainer=trainer,
        price_col="favorite_price",
        outcome_col="outcome",
        time_col="close_time",
        note=f"V5-C2 crypto narrow gate; features={retained}",
    )

    log(f"Gate passes: {result.passes}")
    log(f"Holdout n_eligible: {result.holdout_eligible_n}")
    log(f"Holdout mean P&L: {result.holdout_mean:.4f}")
    log(f"Holdout 95% CI: [{result.holdout_ci_lower:.4f}, {result.holdout_ci_upper:.4f}]")
    log(f"Holdout hit_rate: {result.holdout_hit_rate:.4f}")
    log(f"v1 baseline holdout mean: {result.v1_holdout_mean:.4f}")
    log(f"Criteria: {result.criteria}")

    payload = {
        "verdict": "PASS" if result.passes else "FAIL",
        "retained_features": retained,
        "gate_result": asdict(result),
    }
    with open(GATE_PATH, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"Wrote {GATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
