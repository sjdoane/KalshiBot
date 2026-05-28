# v7 Angle C: TabPFN v2 Diagnostic Methodology

**Date:** 2026-05-25
**Author:** Claude (v7 Angle C build agent)
**Status:** LOCKED before pulling any data or running any model. Thresholds and split design are pre-registered.
**Inputs:** `research/v7/00-scoping-synthesis.md`, `research/v7/02-recent-ml-research.md`, `research/v6/phase-1.5-methodology.md`, `research/v6/06-orthogonality.md`, `research/v6/FINAL-VERDICT.md`, `research/v5/05-statcast-model.md`, `research/v5/07-critic.md`.

## 1. Thesis (re-stated)

The v7 Angle C question is binary: **is the v5-B / v6 "model anchors on price" failure mode LightGBM-specific, or is it model-class-robust?** Six rounds of NULL across Project Kalshi used either logistic regression (v5-B, v3, v4 Track A) or LightGBM (v5-C, v6 Phase 2 M2 candidate) for the model class. TabPFN v2 is a transformer-based foundation model pre-trained on 130 million synthetic tabular datasets (PriorLabs, Nature January 2025); its inductive bias is fundamentally different from gradient boosting and from logistic regression. If TabPFN ALSO produces null orthogonality lift on the same data, v6's K1 NULL and v5-B's gate failure are robust to model class. If TabPFN extracts +0.005 Brier lift over Kalshi mid where LightGBM did not, the "no signal" verdict was model-specific and v7 has a candidate path.

## 2. Models compared

Two classifiers, fit on identical train and orthogonality-test splits per dataset:

- **TabPFN v2** (`tabpfn.TabPFNClassifier`, package `tabpfn==8.0.3`, PyPI). Run with default hyperparameters (no per-dataset tuning). Device set to `auto` (CPU on this machine; torch 2.12.0+cpu). Random seed 42 for any non-deterministic step.
- **LightGBM** (`lightgbm.LGBMClassifier`, version 4.6+). Hyperparameters fixed to v6's locked M2 spec: `max_depth=4, num_leaves=15, learning_rate=0.05, n_estimators=200, objective="binary", random_state=42, verbose=-1`. Early stopping on a 10% chronological val slice of train, patience 20, eval metric binary_logloss. This is the EXACT M2 configuration v6 was prepared to run had Phase 2 not killed at K1.

Both models receive the same input matrix `(mid, features)` for each comparison.

## 3. Datasets

### 3.1 Dataset A: v6 master at midband, T-30

- Source: `data/v6/v6_master.parquet` (3,688 rows total, 24 columns, date range 2024-12-12 to 2026-03-24).
- Filter to T-30 rows only: `horizon_min == 30`.
- Filter to midband: `0.55 <= kalshi_mid_at_t <= 0.80`.
- Per v6 orthogonality report (`research/v6/06-orthogonality.md`), midband T-30 yields **n=971 contracts**, with chronological 60/25/15 split = **n_train=430, n_orth_holdout=168, n_final_holdout=145**.
- Feature column set (matching v6 Section 2): the 8 candidate features evaluated in v6 orthogonality (`kalshi_cvd_30, kalshi_trade_count_30, coinbase_realized_vol_30, coinbase_vwap_dev_30, time_since_last_trade_at_t, funding_rate_delta_4h_at_t, dvol_delta_1h_at_t, basis_delta_1h_at_t`) plus T-15 variants where available, for a max of 13 to 14 feature columns. The methodology used in C2 will deterministically select the feature column set matching v6 Section 2 (T-30 plus universal features), with NaN rows dropped from the training set.
- Baseline raw feature (always present): `kalshi_mid_at_t`.
- Outcome: `outcome_yes` (binary).
- Cluster id for bootstrap: `t.dt.date` (UTC day of horizon timestamp), matching v6 Section 4.4.

### 3.2 Dataset B: v5-B Statcast prop, subsampled to 10k

- Source: `data/v5/prop_dataset.parquet` (144,873 rows, 132 columns; binary `outcome` column with class ratio 27.5% YES, 72.5% NO).
- Stratified random subsample to **n=10,000** with `random_state=42`, preserving the `outcome` class ratio. TabPFN v2's in-context regime has a ~10k row practical limit per the PriorLabs documentation. The subsample is drawn ONCE and frozen for both TabPFN and LightGBM fits.
- After subsample, apply chronological order (sort by `game_date_parsed`), then chronological 60/25/15 split = **n_train=6000, n_orth_holdout=2500, n_final_holdout=1500** for analysis. For the v5-B side-by-side, we run the orthogonality protocol on the 2500-row holdout slice only (the final holdout is reserved per v6 protocol; on this diagnostic we do NOT need to gate, we only need the orthogonality lift comparison and the model-class-Brier-delta comparison, so the 25% slice is sufficient).
- Feature column set: the 8 orthogonality-surviving features per v5-B Section 2.2: `bat30_n_pitches, bat30_n_pa, bat7_n_pitches, bat7_n_pa, bat14_n_pitches, bat14_n_pa, batstd_n_pitches, batstd_n_pa`. Plus the baseline `favorite_price` (always included).
- Outcome: `outcome` (binary, 0/1).
- Cluster id for bootstrap: `game_date_parsed.dt.date`, matching v5-B's by-date cluster definition.
- NaN handling: rows with NaN in any selected feature are dropped before fit, same as v5-B Section 1.3 leak discipline.

### 3.3 What is NOT in scope

- T-15 horizon analysis on the v6 dataset is NOT in scope; v6 found T-15 widerband-only and the midband n=325 is too thin for a cluster-bootstrap comparison. Only T-30 midband is reported per the prior-registered single comparison.
- The v6 final holdout (last 15%, n=145) is NOT touched in this diagnostic. Orthogonality-holdout (next 25% after train, n=168) is the comparison slice, matching v6 Section 3.
- The v5-B final holdout slice (1500 rows in the chronological 15%) is NOT touched. Orthogonality holdout (2500 rows) is the comparison slice.

## 4. Split design (LOCKED)

For each dataset:

- Sort chronologically by the dataset's natural close/game_date column. NO RANDOM SHUFFLE.
- 60/25/15 chronological split into train / orthogonality holdout / final holdout. Final holdout reserved.
- Purge buffer: 24 hours between train end and orthogonality start, and between orthogonality and final holdout. v6 protocol Section 4.3.

Train: model fit on this slice.
Orthogonality holdout: Brier reported on this slice. All comparisons happen here.
Final holdout: untouched.

## 5. Orthogonality comparison (LOCKED)

For each model M in {TabPFN, LightGBM} and each dataset D in {v6 midband T-30, v5-B 10k subsample}:

1. **Baseline Brier**: fit a univariate logistic regression on `(mid)` only on D's train. Predict on D's orthogonality holdout. Compute Brier baseline.
2. **Model probability as augmenting feature**: fit M on D's train using `(mid, features)`. Predict on D's orthogonality holdout to get `M_prob`. Then fit a logistic regression on D's orthogonality holdout using `(mid, M_prob)` as inputs... NO WAIT, that double-uses the holdout. Re-spec:
3. **Brier on (mid, features)**: fit M on D's train using `(mid, features)`. Predict on D's orthogonality holdout. Compute Brier. This is the direct comparison of the model's joint use of mid plus features.

The orthogonality lift for model M is `Brier_baseline_logit_on_mid - Brier_M_on_(mid, features)`. Locked v6 threshold: **+0.005 absolute** for the model to be a "pass" against Kalshi mid.

For the side-by-side comparison: `Delta_Brier_M(TabPFN - LightGBM) = Brier_LightGBM - Brier_TabPFN`. Positive means TabPFN beats LightGBM. Locked threshold: **+0.003 absolute** Brier delta for TabPFN to be declared a genuinely-better model class on this data.

## 6. Pre-registered pass criteria (LOCKED)

These are binding. ALL of the following are pre-registered before any data pull or fit:

### PASS conditions (any one triggers PASS)

- **C1**: TabPFN Brier improvement over Kalshi mid on midband T-30 holdout >= **+0.005 absolute** (v6's locked threshold). The v6 K1 NULL is overturned by model class.
- **C2**: TabPFN Brier delta over LightGBM on midband T-30 holdout >= **+0.003 absolute** (LightGBM-beats-LightGBM threshold). Identifies LightGBM as the bottleneck.
- **C3**: Either C1 or C2 holds on the v5-B 10k subsample at the same thresholds.

### FAIL conditions (both must hold for clean NULL)

- All four (TabPFN-vs-mid on v6, TabPFN-vs-mid on v5-B, TabPFN-vs-LGBM on v6, TabPFN-vs-LGBM on v5-B) fail their respective thresholds.

### PARTIAL conditions (any one triggers PARTIAL)

- C1 or C2 passes on EXACTLY ONE of the two datasets. (Model-class robustness on one but not the other.)

## 7. Cluster-bootstrap CI on Brier delta

For the headline TabPFN-minus-LightGBM Brier delta, compute a cluster-bootstrap CI per v6 Section 4.4:

- Whole-day cluster id from `t.dt.date` (v6) or `game_date_parsed.dt.date` (v5-B).
- Resample whole-day clusters with replacement, 5000 iterations, seed 42.
- For each resample, recompute the Brier of TabPFN on the resampled holdout (using the already-fit predictions, no refit) MINUS the Brier of LightGBM on the resampled holdout.
- Report point estimate, 2.5th percentile, 97.5th percentile.
- If CI excludes 0, the model-class difference is statistically distinguishable from chance.

## 8. Self-reference diagnostic (per v6 Section 3.5)

If TabPFN shows ANY positive lift over Kalshi mid on the v6 midband T-30 holdout (regardless of whether it clears +0.005), replicate v6's stale-mid vs fresh-mid split (`time_since_last_trade_at_t < 5 min` vs `>= 5 min`). Compute lift separately on each subset. Document where the lift concentrates.

## 9. What we will NOT do

- **NO** TabPFN hyperparameter tuning. Default settings.
- **NO** ensembling. TabPFN alone vs LightGBM alone.
- **NO** isotonic recalibration. The Brier numbers are raw model output.
- **NO** retesting after seeing the result with different feature subsets. The 8 v6 features and 8 v5-B survivors are the locked input.
- **NO** rerunning the subsample with a different seed if the first one looks unfavorable. Seed 42, single draw, no peek-and-resample.
- **NO** post-hoc threshold tuning. +0.005 (v6) and +0.003 (LGBM-delta) are locked.
- **NO** use of `last_price_dollars` anywhere (v5-B Killer 2c).
- **NO** modification of v5 or v6 source, data files, or v1 source.
- **NO** in-sample reporting. Brier numbers come from the orthogonality holdout only.
- **NO** train-time access to the final holdout slice.

## 10. Reproducibility

All TabPFN and LightGBM predictions cached to `data/v7/`:
- `tabpfn_v6_predictions.parquet`: per-row `(ticker, t, outcome_yes, kalshi_mid_at_t, tabpfn_prob, lgbm_prob, split)` for the v6 midband T-30 sample.
- `tabpfn_v5b_predictions.parquet`: per-row `(ticker, game_date_parsed, outcome, favorite_price, tabpfn_prob, lgbm_prob, split)` for the v5-B 10k subsample.
- `tabpfn_orthogonality.json`: all Brier values, deltas, bootstrap CIs, pass/fail per criterion, install metadata (TabPFN version, torch version, CUDA flag).

Each run script writes a deterministic manifest with random seed, package versions, file hashes of input parquets.

## 11. Budget (LOCKED)

- External: **$0** (TabPFN free, weights downloaded once from HuggingFace).
- LLM: **< $2** of the $24 remaining cap.
- Compute: CPU only. TabPFN's published timing is 2.8 seconds on n=10k on a single CPU; the v6 n=430 train fit should be sub-second, the v5-B 6k train fit should be at most 10 seconds.

## 12. Decision log

- 2026-05-25 (v1): methodology written by v7 Angle C orchestrator. Single revision pass: clarified that the holdout used is the 25% orthogonality slice, not the final 15%, and pre-registered both C1 (TabPFN vs mid at +0.005) and C2 (TabPFN vs LightGBM at +0.003) as separate pass conditions.
- Next: install verification, run Stage C2 build.
