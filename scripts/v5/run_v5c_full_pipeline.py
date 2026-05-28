"""Full V5-C2 pipeline: orthogonality probe + conditional gate + summary.

Run AFTER build_v5c_orthogonality_dataset has completed. Calls:
1. run_v5c_orthogonality_probe.main()
2. If features retained: run_v5c_gate.main()
3. Prints summary

Run: uv run python -m scripts.v5.run_v5c_full_pipeline
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "v5"))

# Import as modules. Module names use the file basename.
from scripts.v5 import run_v5c_orthogonality_probe, run_v5c_gate

DATA_DIR = REPO_ROOT / "data" / "v5"
REPORT_PATH = DATA_DIR / "v5c_orthogonality_report.json"
GATE_PATH = DATA_DIR / "crypto_gate_results.json"


def main() -> int:
    print("=" * 80)
    print("V5-C2 PIPELINE STEP 1: Orthogonality probe")
    print("=" * 80)
    rc = run_v5c_orthogonality_probe.main()
    if rc != 0:
        return rc

    with open(REPORT_PATH) as f:
        report = json.load(f)
    retained = report.get("features_retained", [])
    verdict = report.get("verdict")

    print()
    print("=" * 80)
    print("V5-C2 PIPELINE STEP 2: Conditional gate")
    print("=" * 80)
    print(f"Orthogonality verdict: {verdict}")
    print(f"Features retained: {retained}")

    rc = run_v5c_gate.main()
    if rc != 0:
        return rc

    print()
    print("=" * 80)
    print("V5-C2 PIPELINE SUMMARY")
    print("=" * 80)
    with open(GATE_PATH) as f:
        gate = json.load(f)
    print(f"Gate verdict: {gate.get('verdict')}")
    if gate.get('gate_result'):
        gr = gate['gate_result']
        print(f"  holdout_n: {gr.get('holdout_eligible_n')}")
        print(f"  holdout_mean: {gr.get('holdout_mean'):.4f}")
        print(f"  holdout_ci_lower: {gr.get('holdout_ci_lower'):.4f}")
        print(f"  v1_baseline: {gr.get('v1_holdout_mean'):.4f}")
        print(f"  criteria: {gr.get('criteria')}")
    print()
    print(f"Tracking error abs_mean_pct: {report['tracking_error'].get('abs_mean_err_pct')}")
    print(f"  p95: {report['tracking_error'].get('p95_abs_err_pct')}")
    print(f"  p99: {report['tracking_error'].get('p99_abs_err_pct')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
