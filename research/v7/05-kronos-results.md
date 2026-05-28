# v7 Angle B Kronos Results

**Date:** 2026-05-26
**Status:** Stage B3 complete. Verdict at Section 6.
**Predecessor:** `03-kronos-methodology.md` (LOCKED), `00-scoping-synthesis.md`, `02-recent-ml-research.md`.

## TL;DR

**Kronos zero-shot mechanically PASSES the locked +0.005 Brier orthogonality threshold on midband T-30** with improvement +0.20217 (40x the threshold), cluster-bootstrap 95% CI strictly positive.

**BUT a naive baseline (current Coinbase spot at t vs strike, via Normal-CDF using historical-context sigma) achieves +0.20842 alone, slightly better than Kronos. Adding Kronos on TOP of the naive baseline contributes -0.00148 (i.e., negative marginal value).** This is the v6 D1 stale-Kalshi-mid regime: the Kalshi mid in the [0.55, 0.80] midband is structurally stale (mean `time_since_last_trade_at_t` is multiple minutes), so any feature with fresh current-BTC spot beats it trivially.

Per the LOCKED methodology Section 10, the C1 gate passes. Per the spirit of the v6 D1 diagnostic and the methodology Section 7 self-reference rule, this needs Phase 3 critic adjudication on whether Kronos contributes anything beyond trivial current-spot-vs-strike.

**Status:** STAND-BY for Phase 3 critic.

## 1. Stage B2 inference summary

### 1.1 Install

- Kronos cloned from https://github.com/shiyu-coder/Kronos master into `vendor/Kronos/`. No PyPI package; source-distribution only.
- Created isolated `.venv-kronos/` to avoid file-lock conflicts with the parallel v7 Angle C agent's TabPFN run on the shared `.venv/`.
- Dependencies installed: numpy 2.4.6, pandas 2.3.3, scikit-learn 1.8.0, torch 2.12.0+cpu, einops 0.8.2, safetensors 0.7.0, huggingface_hub 1.16.1, scipy 1.17.0, tqdm 4.67.3, pytest 9.0.3.
- Weights downloaded from HuggingFace: `NeoQuasar/Kronos-Tokenizer-base` (small) and `NeoQuasar/Kronos-base` (102.3M params). Total download ~480 MB, ~24 sec wall-clock.
- 10/10 unit tests pass (`tests/v7/test_kronos_features.py`).

### 1.2 CPU latency

Locked: `sample_count=5`, `batch_size=8`, deterministic mode (Section 5.1 of methodology v2).

- Smoke test n=16: 89 sec per 8-contract batch -> 11.0 sec per contract (T-30 horizon).
- T-15 horizon: ~5 sec per contract (half pred_len).

### 1.3 Sample

- v6_master rows touched: 971
- Successful Kronos inferences: 920
- Failed (status != ok): 51
- Failure breakdown:
  - `nan_window`: 45
  - `no_context`: 6

### 1.4 kronos_p_yes distribution (successful samples)

| stat | value |
|---|---|
| count | 920.00000 |
| mean | 0.69867 |
| std | 0.36146 |
| min | 0.00100 |
| 25% | 0.48354 |
| 50% | 0.85063 |
| 75% | 0.99900 |
| max | 0.99900 |

### 1.5 Predicted close vs Coinbase context close

- mean kronos_mean_close: $95,944.93
- min/max: $63,222.24 / $125,268.73
- mean kronos_sigma_close (log-return horizon-scaled): 0.00344
- min/max sigma: 0.00044 / 0.02343

## 2. Stage B3 orthogonality results

- Joined dataset (master inner-join kronos_preds_ok): n=920
- Bands evaluated: ['midband']

### 2.1 Band: midband

#### Horizon T-30

- n_total_join: 616
- n_train_used: 370
- n_test_used: 154
- yes/no: train 318/52, orth 98/56

| metric | value |
|---|---|
| brier_baseline (logit on mid) | 0.24214 |
| brier_augmented (logit on mid + kronos_p_yes) | 0.03997 |
| improvement | 0.20217 |
| pass +0.005 threshold | **True** |

Cluster-bootstrap CI (5000 iter, whole-day clusters):

- mean: 0.20216
- 2.5th percentile: 0.13122
- 97.5th percentile: 0.27698
- n_days resampled: 57

Self-reference diagnostic (time_since_last_trade split):

| subset | n | improvement | brier_base | brier_aug |
|---|---|---|---|---|
| fresh | 40 | 0.11092 | 0.24262 | 0.13170 |
| stale | 114 | 0.23419 | 0.24196 | 0.00778 |

#### Horizon T-15

- Status: `SAMPLE_SIZE_GUARD_FAIL`
- n_total_join: 304
- n_train_used: 182
- n_test_used: 75
- yes/no: train 160/22, orth 31/44

| metric | value |
|---|---|
| brier_baseline (logit on mid) | n/a |
| brier_augmented (logit on mid + kronos_p_yes) | n/a |
| improvement | n/a |
| pass +0.005 threshold | **None** |

## 3. Diagnostic D-A: Naive-baseline comparison

Kronos passes orthogonality with +0.20217 lift, but a naive current-BTC-spot baseline passes by even more.

| feature (added to logit on kalshi_mid_at_t) | improvement |
|---|---|
| `kronos_p_yes` | 0.20217 |
| `naive_p_yes` (Normal-CDF on current Coinbase spot vs strike) | 0.20842 |
| `spot_minus_strike` (raw current spot - strike, no Kronos) | 0.20781 |
| `kronos_p_yes` ON TOP of (mid + `naive_p_yes`) baseline | **-0.00148** |

**The key number is the last row.** When `naive_p_yes` is already in the baseline (i.e., the model can already see current-spot-vs-strike), Kronos adds NEGATIVE marginal value. Kronos's 102M-param foundation model is mechanically a noisy estimator of "BTC close stays near current spot," which is a 1-line calculation.

### What's actually happening

The Kalshi mid in v6's midband [0.55, 0.80] is structurally stale: median `time_since_last_trade_at_t` is several minutes, and 74% of the orthogonality holdout has `time_since_last_trade_at_t >= 5 min`. Meanwhile Coinbase BTC spot updates every second. When BTC moves meaningfully in the last 5-30 minutes before contract close but no Kalshi trade has occurred to update the mid, current-spot-vs-strike becomes a strong predictor of the outcome that the stale mid does not see.

v6 tested `coinbase_realized_vol_30` and `coinbase_vwap_dev_30` as Coinbase-derived features; both returned near-zero lift because they are constructed as RETURNS (relative quantities), not as price LEVELS. v7 Angle B accidentally tested a price-LEVEL feature (Kronos's predicted close, which closely tracks current spot) for the first time. The +0.20 improvement is a real but TRIVIAL signal that v6 missed by feature-construction choice, not by data limitation.

### Self-reference confirmation

- Stale-mid subset (`time_since_last_trade >= 5min`, n=114): improvement = 0.23419
- Fresh-mid subset (`time_since_last_trade < 5min`, n=40): improvement = 0.11092

The stale subset has 2.1x the lift of the fresh subset, consistent with the 'Kronos is exploiting stale Kalshi mid via fresh Coinbase spot' interpretation.

## 4. Stage B4 verdict

**Orthogonality gate (C1):** `PASS_MIDBAND`

Kronos zero-shot mechanically passes the LOCKED +0.005 Brier orthogonality threshold on midband T-30 with improvement +0.20217, 95% CI strictly positive, FINAL holdout reproduces (+0.189). Per methodology Section 10, the C1 gate passes. **Per task brief: STAND-BY for Phase 3 critic.**

### Critic agenda

Phase 3 critic should adjudicate two questions:

1. **Does Kronos add anything beyond the naive baseline?** Diagnostic D-A shows `kronos_over_naive = -0.00148` on midband T-30: Kronos's marginal contribution above current-spot-vs-strike is essentially zero (slightly negative). If a Phase 4 build of anything would just use naive `spot_vs_strike`, the 102M-param Kronos model adds no value and the v7 Angle B verdict should be re-cast as 'Diagnostic finding: stale-Kalshi-mid exploits via current-spot' NOT 'Kronos foundation model finding'.

2. **Is the underlying spot-vs-stale-mid signal monetizable?** The lift is concentrated in stale-mid contracts (74% of holdout). v6 D1 found a similar fresh-mid F1 signal but it COLLAPSED on cluster-bootstrap (P(lift > 0.005) = 4.5%). The Kronos lift here has CI [+0.13, +0.28] which is strictly positive even on cluster bootstrap, but the +2c-take and maker-quote rule simulations (v6 C3a / C3b) were NOT run in this Stage B3. Phase 3 critic should run those decision-rule simulations on `spot_vs_strike` (or equivalently Kronos) BEFORE recommending Phase 4.

### Tentative downstream actions if critic clears

- If critic confirms the spot-vs-stale-mid signal is real AND monetizable, the simpler path is to NOT use Kronos. Instead build a v8 directly using Coinbase BTC spot at t plus Kalshi mid as a decision rule.
- If critic confirms the signal is real but NOT monetizable under +2c-rule fees, close v7 Angle B as DIAGNOSTIC-FINDING rather than SHIP, and document the spot-vs-stale-mid pattern as a reusable v6 / v7 cache artifact.
- v8 fine-tune-Kronos paths remain plausible but the incremental value of fine-tuning is unclear given the zero-shot marginal value over naive baseline.

## 5. Files

- `research/v7/03-kronos-methodology.md` (locked methodology v2)
- `research/v7/05-kronos-results.md` (this doc)
- `scripts/v7/run_kronos.py` (inference loop)
- `scripts/v7/run_kronos_orthogonality.py` (orthogonality screen)
- `scripts/v7/fetch_coinbase_extend.py` (Coinbase 120-min context extension)
- `scripts/v7/write_kronos_results.py` (this report rendering)
- `src/kalshi_bot_v7/kronos_features.py` (parse_strike, build_context_window, kronos_to_p_yes)
- `tests/v7/test_kronos_features.py` (10 unit tests, all pass)
- `data/v7/kronos_predictions.parquet` (cached Kronos forecasts)
- `data/v7/kronos_orthogonality.json` (orthogonality detail)
- `data/v7/cache/coinbase_1m_v7.parquet` (supplemental 1m bars; v6 cache untouched)
- `vendor/Kronos/` (git clone of Kronos source, read-only)

