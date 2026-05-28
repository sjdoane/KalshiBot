"""Write markdown reports for v6 Phase 2.

- research/v6/06-orthogonality.md
- research/v6/07-model-results.md
- research/v6/08-gate-results.md

Reads:
- data/v6/v6_orthogonality_results.json
- data/v6/v6_gate_results.json
- data/v6/v6_build_log.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "v6"
RESEARCH_DIR = REPO_ROOT / "research" / "v6"


def write_orthogonality(ortho: dict, build_log: dict) -> str:
    lines = []
    lines.append("# v6 Orthogonality Results (Phase 2 Stage 2B)")
    lines.append("")
    lines.append(
        "Per phase-1.5-methodology.md Section 3. Each candidate feature is "
        "tested for Brier improvement on a held-out 25% chronological slice "
        "above the baseline `kalshi_mid_at_t`. Pass criterion: Brier "
        "improvement >= 0.005.",
    )
    lines.append("")

    lines.append("## Build summary")
    lines.append("")
    lines.append(f"- Rows total: {build_log.get('rows_emitted')}")
    bc = build_log.get("band_counts", {}) or {}
    lines.append(f"- Midband (mid in [0.55, 0.80]): {bc.get('midband_total')}")
    lines.append(f"- Widerband (mid in [0.20, 0.80]): {bc.get('widerband_total')}")
    lines.append(f"- Midband yes_rate: {bc.get('midband_yes_rate')}")
    lines.append(f"- Date range: {build_log.get('date_range')}")
    lines.append("")

    lines.append("## Overall K1 verdict")
    lines.append("")
    lines.append(f"`{ortho.get('k1_verdict')}`")
    lines.append("")
    lines.append(f"- Midband passes (horizon, feature): `{ortho.get('midband_passes')}`")
    lines.append(f"- Widerband passes: `{ortho.get('widerband_passes')}`")
    lines.append("")

    lines.append("## Per-horizon detail")
    lines.append("")

    for h_key, hr in ortho.get("by_horizon", {}).items():
        lines.append(f"### Horizon T-{h_key} min")
        lines.append("")
        if not isinstance(hr, dict):
            lines.append(f"Status: {hr}")
            continue
        if "status" in hr:
            lines.append(f"Status: `{hr['status']}`")
            lines.append("")
            if "midband_size" in hr:
                lines.append(f"Midband sample sizes: `{hr['midband_size']}`")
            if "widerband_size" in hr:
                lines.append(f"Widerband sample sizes: `{hr['widerband_size']}`")
            lines.append("")
            continue
        band = hr.get("band_used", "unknown")
        lines.append(f"- Band used: **{band}**")
        lines.append(f"- n_train: {hr.get('n_train')}, n_orth_holdout: {hr.get('n_orth')}")
        n_drift = hr.get("n_drift_defined_train")
        if n_drift is not None:
            lines.append(f"- F4 drift defined in train (K1b guard): n={n_drift}")
        lines.append("")
        drops = hr.get("correlation_drops") or []
        lines.append("#### Correlation pre-screen drops (|rho| > 0.85)")
        lines.append("")
        if not drops:
            lines.append("None.")
        else:
            for d in drops:
                lines.append(f"- dropped `{d['dropped']}`, kept `{d['kept']}` (rho={d['rho']:.3f})")
        lines.append("")
        lines.append("#### Feature orthogonality test")
        lines.append("")
        lines.append("| feature | Brier base | Brier aug | improvement | n_test | pass +0.005 |")
        lines.append("|---|---|---|---|---|---|")
        for r in hr.get("per_feature", []):
            lines.append(
                f"| `{r['feature']}` | {r['brier_baseline']:.5f} | "
                f"{r['brier_augmented']:.5f} | {r['brier_improvement']:.5f} | "
                f"{r['n_test']} | {r['pass_005']} |",
            )
        lines.append("")
        lines.append(f"**n_passed: {hr.get('n_passed')}**")
        lines.append(f"Passed features: `{hr.get('passed_features')}`")
        lines.append("")

        if hr.get("f1_self_reference_diagnostic"):
            d = hr["f1_self_reference_diagnostic"]
            lines.append("#### F1 self-reference diagnostic (Section 3.5)")
            lines.append("")
            lines.append(
                "Holdout split by `time_since_last_trade < 5 min` "
                "(fresh) vs >= 5 min (stale). F1 lift on each subset:",
            )
            lines.append("")
            lines.append(f"- n_stale: {d.get('n_stale')}, n_fresh: {d.get('n_fresh')}")
            for k in ("stale", "fresh"):
                v = d.get(k, {})
                if isinstance(v, dict):
                    lines.append(f"  - {k}: n={v.get('n')}, lift={v.get('lift')}")
            lines.append("")

    return "\n".join(lines)


def write_model_results(gate: dict) -> str:
    lines = []
    lines.append("# v6 Model Results (Phase 2 Stage 2C)")
    lines.append("")
    verdict = gate.get("verdict")
    kill = gate.get("kill_reason_if_null")
    lines.append(f"**Verdict:** `{verdict}` (kill: `{kill}`)")
    lines.append("")
    if verdict == "NULL" and kill == "K1":
        lines.append("## NULL at Phase 2 Stage 2B")
        lines.append("")
        lines.append(
            "No features passed orthogonality on midband. Per methodology "
            "Section 7 / K1, the model is not trained. See "
            "`06-orthogonality.md` for the per-feature detail. v6 is closed "
            "as a clean K1 NULL.",
        )
        return "\n".join(lines)
    if verdict == "NULL" and kill is None:
        lines.append("Model not trained (insufficient data or other early stop).")
        return "\n".join(lines)

    model = gate.get("model") or {}
    split = gate.get("split") or {}
    feats = gate.get("features") or {}
    g = gate.get("gate") or {}

    lines.append("## Selected model")
    lines.append("")
    lines.append(f"- Class: `{model.get('class')}`")
    lines.append(f"- LogReg tuned C: `{model.get('logreg_C')}`")
    lines.append(f"- LogReg BSS orth: {model.get('logreg_bss_orth')}")
    lines.append(f"- LGBM BSS orth: {model.get('lgbm_bss_orth')}")
    lines.append(f"- Selected BSS orth: {model.get('selected_bss_orth')}")
    lines.append(f"- Final-holdout BSS (C2): {model.get('selected_bss_final')}")
    lines.append(f"- ECE on orth: {model.get('ece_orth')}")
    lines.append(f"- Isotonic-calibrated: {model.get('calibrated')}")
    lines.append("")
    lines.append("## Features")
    lines.append("")
    lines.append(f"- Surviving from orthogonality: `{feats.get('surviving')}`")
    lines.append(f"- Feature columns in model: `{feats.get('feature_cols')}`")
    lines.append("")
    lines.append("## Split")
    lines.append("")
    lines.append(f"- Train n (midband): {split.get('train_n')}")
    lines.append(f"- Orth holdout n: {split.get('orth_n')}")
    lines.append(f"- Final holdout n: {split.get('final_n')}")
    lines.append("")
    lines.append("## Decision rule fire counts on final holdout")
    lines.append("")
    boot_a = g.get("C3a") or {}
    boot_b = g.get("C3b") or {}
    lines.append(f"- Rule A (+2c-take) fires: {boot_a.get('n_fires')}")
    lines.append(f"- Rule B (maker-quote) fires: {boot_b.get('n_fires')}")
    lines.append(f"- C4b floor: {g.get('C4b_floor')}")
    lines.append(f"- C4 share of |prob - mid| >= 0.03: {g.get('C4_share')}")
    lines.append("")
    return "\n".join(lines)


def write_gate_results(gate: dict) -> str:
    lines = []
    lines.append("# v6 Gate Results (Phase 2 Stage 2D)")
    lines.append("")
    verdict = gate.get("verdict")
    kill = gate.get("kill_reason_if_null")
    lines.append(f"**Verdict:** `{verdict}`")
    lines.append("")
    if kill:
        lines.append(f"**Kill reason:** `{kill}`")
        lines.append("")

    if verdict == "NULL" and kill == "K1":
        lines.append("## Honest interpretation")
        lines.append("")
        lines.append(
            "v6 closes at Phase 2 Stage 2B (orthogonality). No feature in the "
            "T-30 / T-15 universe (Kalshi internal CVD, trade count, price drift, "
            "Coinbase realized vol / VWAP dev, Deribit funding-delta, DVOL delta, "
            "spot-futures basis delta) cleared the +0.005 Brier improvement "
            "threshold on the midband holdout. The expected modal outcome from "
            "Phase 1 synthesis (80% NULL prior) is realized. v5-C's null at T-1h "
            "extends to sub-hour horizons within the free-tier feature universe.",
        )
        lines.append("")
        lines.append("## Notable diagnostic findings")
        lines.append("")
        lines.append(
            "1. **F1 (kalshi_cvd) self-reference diagnostic**: On T-30 midband, "
            "F1 orthogonality lift was +0.00214 overall but +0.00958 on the "
            "fresh-mid subset (n=45) and -0.00058 on the stale-mid subset "
            "(n=123). Lift concentrates in the fresh subset, not the stale "
            "subset (the methodology Critic Important Finding 2 worried about "
            "the OPPOSITE pattern). Even on fresh-mid subset, sample size is "
            "too small and overall lift is below +0.005.",
        )
        lines.append("")
        lines.append(
            "2. **F4 (kalshi_price_drift) K1b artifact verified**: At T-30 "
            "midband, F4 was structurally undefined for 100% of train contracts "
            "(0 / 430 with second trade in window). At T-15 widerband, F4 "
            "showed an apparent +0.10 Brier improvement when baseline and "
            "augmented were fit on different sub-samples (drift-defined "
            "contracts have yes_rate 0.54 vs drift-undefined 0.31, a "
            "sample-selection effect, not a generic alpha). The fair "
            "like-for-like comparison (Section 3.1 protocol, baseline AND "
            "augmented on the SAME drift-defined rows) collapses F4's lift to "
            "+0.00272. Below the +0.005 threshold.",
        )
        lines.append("")
        lines.append(
            "3. **Coinbase external features (realized_vol, vwap_dev)**: "
            "Effectively zero contribution beyond Kalshi mid on midband "
            "(improvement < 1e-5). The Coinbase / BTC-USD signal is fully "
            "absorbed by the Kalshi mid at the T-30 / T-15 horizons studied.",
        )
        lines.append("")
        lines.append(
            "4. **Deribit funding-delta, DVOL-delta, basis-delta**: All show "
            "near-zero or negative Brier improvement. The hypothesis that "
            "perpetual funding-rate trajectory, IV-level changes, or "
            "spot-futures basis movement carries information beyond Kalshi "
            "mid at T-30/T-15 is rejected by the data.",
        )
        return "\n".join(lines)

    g = gate.get("gate") or {}
    model = gate.get("model") or {}

    lines.append("## Per-criterion verdict")
    lines.append("")
    lines.append(f"- C1 (orthogonality survival): `{g.get('C1_pass')}`")
    lines.append(f"- C2 (BSS_final >= +0.01): `{g.get('C2_pass')}`, value={model.get('selected_bss_final')}")
    boot_a = g.get("C3a") or {}
    boot_b = g.get("C3b") or {}
    lines.append(
        f"- C3a (rule A +2c-take, 2.5th percentile > 0c): pass={g.get('C3a_pass')}, "
        f"point={boot_a.get('mean_cents')}, CI=[{boot_a.get('ci_low')}, {boot_a.get('ci_high')}], fires={boot_a.get('n_fires')}",
    )
    lines.append(
        f"- C3b (rule B maker-quote, 2.5th percentile > 0c): pass={g.get('C3b_pass')}, "
        f"point={boot_b.get('mean_cents')}, CI=[{boot_b.get('ci_low')}, {boot_b.get('ci_high')}], fires={boot_b.get('n_fires')}",
    )
    lines.append(
        f"- C4 (>= 5% holdout with |prob - mid| >= 0.03): pass={g.get('C4_pass')}, share={g.get('C4_share')}",
    )
    lines.append(
        f"- C4b (rule A fires >= floor): pass={g.get('C4b_a_ok')}; rule B: pass={g.get('C4b_b_ok')}, floor={g.get('C4b_floor')}",
    )
    c5_3 = g.get("C5_3c") or {}
    c5_4 = g.get("C5_4c") or {}
    lines.append(
        f"- C5 (spread 3c CI lower > -1c AND spread 4c mean > 0c): pass={g.get('C5_pass')}",
    )
    lines.append(f"  - C5 spread 3c: point={c5_3.get('mean_cents')}, CI=[{c5_3.get('ci_low')}, {c5_3.get('ci_high')}]")
    lines.append(f"  - C5 spread 4c: point={c5_4.get('mean_cents')}, CI=[{c5_4.get('ci_low')}, {c5_4.get('ci_high')}]")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ortho_path = DATA_DIR / "v6_orthogonality_results.json"
    gate_path = DATA_DIR / "v6_gate_results.json"
    build_log_path = DATA_DIR / "v6_build_log.json"

    ortho = json.loads(ortho_path.read_text()) if ortho_path.exists() else {}
    gate = json.loads(gate_path.read_text()) if gate_path.exists() else {}
    build_log = json.loads(build_log_path.read_text()) if build_log_path.exists() else {}

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    (RESEARCH_DIR / "06-orthogonality.md").write_text(write_orthogonality(ortho, build_log))
    (RESEARCH_DIR / "07-model-results.md").write_text(write_model_results(gate))
    (RESEARCH_DIR / "08-gate-results.md").write_text(write_gate_results(gate))
    print("wrote 06-orthogonality.md, 07-model-results.md, 08-gate-results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
