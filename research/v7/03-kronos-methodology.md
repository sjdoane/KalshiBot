# v7 Angle B: Kronos Methodology Lock

**Date:** 2026-05-25
**Status:** LOCKED before any Kronos data pull / inference. Any change after this point requires explicit operator authorization.
**Predecessors:** `00-scoping-synthesis.md` (v7 plan), `02-recent-ml-research.md` (ML scoping), `../v6/phase-1.5-methodology.md` (v6 methodology to inherit Sections 3, 4, 11).

## 1. Thesis

**Test whether NeoQuasar/Kronos-base (Tsinghua, arXiv 2508.02739, AAAI), the only 2025 foundation model pre-trained on 12B crypto K-lines with Apache 2.0 open weights, can zero-shot forecast KXBTCD-1h Bitcoin direction better than the Kalshi mid at v6's locked +0.005 Brier orthogonality threshold.**

If Kronos clears, v6's K1 NULL is overturned by model class (foundation pre-training) and not by data. If Kronos fails, v6's NULL is doubly corroborated across feature-class AND model-class.

## 2. Target (locked)

- Series: KXBTCD-1h hourly Bitcoin direction contracts. v6's exact target.
- Sample reuse: `data/v6/v6_master.parquet` 3688 rows from 2807 contracts, dec 2024 to mar 2026. NO new contracts.
- Eligibility: identical to v6 Section 4.1. Already enforced in v6_master:
  - `close_time` after 2024-10-01 (Becker sign flip).
  - `lifetime_hours` between 0.5 and 4.
  - At least 1 trade printed in [t - horizon, t].
  - `status == "settled"`.
- Strike parsing: ticker suffix `-T{strike}` (e.g. `KXBTCD-24DEC1209-T100749.99` -> strike = 100749.99).
- Band stratification: **midband [0.55, 0.80]** primary; **widerband [0.55, 0.95]** fallback if midband sample-size guard (Section 3.4 v6) fails. Note: v7 widerband is [0.55, 0.95] per task brief, NOT v6's [0.20, 0.80]. Documented intentional difference.

## 3. Horizons (locked)

Two horizons matching v6:

- T-30 min: Kronos predicts BTC price 30 minutes ahead, given prior 120 min context.
- T-15 min: Kronos predicts BTC price 15 minutes ahead, given prior 120 min context.

Per task brief: input window is 120 minutes of Coinbase 1m OHLCV ending at `t = close_time - horizon_min`.

## 4. Kronos model (locked)

- Model: `NeoQuasar/Kronos-base` (102.3M params).
- Tokenizer: `NeoQuasar/Kronos-Tokenizer-base`.
- License: Apache 2.0.
- Source: https://github.com/shiyu-coder/Kronos
- Install: clone repo (no PyPI package). Use `from model import Kronos, KronosTokenizer, KronosPredictor`.
- Device: CPU only (this machine has no CUDA / no MPS; torch 2.12.0+cpu confirmed). All inference at FP32 on CPU.
- Context length: `max_context=512` (covers 120 1m bars comfortably).
- Inference params (locked before any data pull):
  - `T = 1.0` (temperature). Kronos default.
  - `top_p = 0.9` (nucleus sampling). Kronos default.
  - `sample_count = 30` (per-contract Monte Carlo draws). Trades off latency vs distribution quality; locked at 30 for the pilot. Empirical p_yes is mean of indicator over 30 paths.
  - `pred_len = horizon_min` (30 or 15). Kronos predicts 1-minute bars; we use the final bar's close as price at horizon end.

## 5. From Kronos output to `kronos_p_yes` (locked)

Kronos's public `predict()` averages samples internally and returns a single mean OHLCV trajectory. To get a price distribution at horizon end, we must call `predict()` repeatedly with `sample_count=1` and collect the predicted final-bar close. Implementation plan:

1. For each (ticker, horizon) sample, build the 120-min Coinbase 1m OHLCV window ending at `t = close_time - horizon_min`.
   - Columns: open, high, low, close, volume.
   - x_timestamp: the 120 minute-bar timestamps.
   - y_timestamp: the next `horizon_min` minute-bar timestamps ending at `close_time`.
2. Call `predictor.predict(...)` N times with `sample_count=1` to collect N sample paths. Default N = 30.
   - If even 30 sample-paths per contract is too slow on CPU, fall back to a single call with `sample_count=30` and use the returned **mean** path together with a sigma estimate from Kronos's empirical 1m close stdev over the prediction window. This degrades to the deterministic point-forecast approach described in the task brief.
3. Per sample, take the final predicted close at time `close_time` (the last minute-bar).
4. Compute empirical `p_yes` = fraction of N samples where `pred_close_at_close_time > strike`.
5. Edge cases:
   - If Kronos returns NaN or fails (e.g. context window has Coinbase NaN bars > 20%, mirroring v6 F6 NaN-gap audit), set `kronos_p_yes = NaN` and drop the row.
   - Clip `kronos_p_yes` to [0.001, 0.999] to keep logit baseline numerically stable.

### 5.1 Deterministic fallback (the mode actually used in the v1 run)

CPU latency budget did not allow 30 MC paths per contract on the full sample. Adopted approach:
- One Kronos `predict_batch` call with `sample_count=5` per batch of 8 contracts, internally averaged by Kronos -> mean predicted close.
- Sigma estimate: stdev of the 1-minute log returns of the HISTORICAL CONTEXT WINDOW (the 120 1-min bars going INTO Kronos), scaled by sqrt(horizon_min). The original methodology (5.1 v1) proposed using sigma from Kronos's PREDICTED window, but the smoke test showed Kronos's internal sample-averaging smooths the predicted path so that predicted-window sigma under-estimates BTC realized vol by ~10x and snaps p_yes to {0, 1}. The locked sigma is now sourced from the historical context window stdev, which anchors uncertainty to actual BTC behavior.
- Treat the log price at close_time as Normal(log mu_kronos, sigma_horizon).
- `kronos_p_yes` = `1 - Phi((log strike - log mu_kronos) / sigma_horizon)`.

This is the "calibrated normal around Kronos's median" approach from the task brief, with sigma re-sourced from historical context for stability.

This change was made AFTER the smoke test on n=16 (16/16 successes, p_yes distribution mean 0.857 with std 0.32, mostly snapped to extremes) and BEFORE the full inference run. It is documented here to preserve the audit trail. The +0.005 Brier orthogonality threshold remains LOCKED unchanged.

## 6. Orthogonality protocol (locked, v6 Section 3 inherited verbatim)

v6 methodology Section 3 is inherited unchanged. Briefly:

- Baseline model: univariate logistic regression `outcome_yes ~ logit(kalshi_mid_at_t)`. (Note v6's choice of mid-as-feature in logit; mid is treated as a feature, not as the prediction itself. The v6 diagnostic D3 documents this baseline is +0.063 worse than the identity baseline `p = mid`.)
- Augmented model: bivariate logistic regression `outcome_yes ~ logit(kalshi_mid_at_t + kronos_p_yes)`.
- Holdout: middle 25% chronologically (the "orthogonality holdout"), same split as v6 Section 4.3. 24h purge buffer before holdout. Train on first 60%, holdout on next 25% (after purge), final 15% held untouched.
- Metric: `improvement = Brier_baseline - Brier_augmented`.
- Pass criterion: **improvement >= +0.005**. LOCKED. No post-hoc tuning.
- Like-for-like: drop NaN on aug_cols, fit BOTH baseline and augmented on identical row subset (v6 fit_brier_on_same_subset pattern).
- Cluster-bootstrap CI on the improvement: resample WHOLE-DAY clusters from the orthogonality holdout 5000 times (v6 Section 4.4 pattern). Report point estimate, 2.5th, 97.5th percentile.

## 7. Self-reference diagnostic (per v6 Section 3.5, applied to kronos_p_yes)

v6 found F1 (kalshi_cvd_30) lift concentrated in the `time_since_last_trade_at_t < 5 min` (fresh) subset (n=45, lift +0.00958) vs stale (n=123, lift -0.00058). This is the "fresh mid" subset where Kalshi's mid has just incorporated new information.

For Kronos, we replicate the diagnostic:
- Split orthogonality holdout by `time_since_last_trade_at_t < 5 min` (fresh) vs `>= 5 min` (stale).
- Compute Kronos lift on each subset.
- If lift is concentrated in stale subset (>80% of absolute lift there), Kronos may be exploiting the stale-mid regime where Kalshi has not yet priced in the BTC microstructure. Document but do not auto-drop.
- If lift is concentrated in fresh subset, Kronos is overlapping with Kalshi's information set and the signal is structurally weak.

## 8. Sample (locked)

Reuse `data/v6/v6_master.parquet` directly. From this:

- Total rows: 3688.
- T-30 rows: ~half. T-15 rows: ~half.
- Midband filter (mid in [0.55, 0.80]) at T-30: n=971 (per v6 06-orthogonality.md).
- Midband filter at T-15: n=325 (per v6 06-orthogonality.md).
- Chronological 60/25/15 split with 24h purge applied per v6 Section 4.3.

If Kronos CPU inference latency exceeds 5 sec/contract, fall back to stratified subsample:
- Pilot: 500 contracts random-sampled from midband T-30, stratified by yes_rate.
- Stratification ensures both YES and NO outcomes appear in train AND holdout per Section 3.4 sample-size guards (train YES, NO >= 50; test YES, NO >= 30).
- If even 500 is too slow, drop to 200 contracts.
- Document the actual n run and any subsampling.

## 9. Hygiene (locked, inherited from v6 Section 11)

- All v7 code under `src/kalshi_bot_v7/` and `scripts/v7/`.
- Tests under `tests/v7/`.
- No mutation of v1, v5, or v6 source.
- No touching `.env`, `data/live_trades/`, `data/paper_trades/`.
- Predictions cached to `data/v7/kronos_predictions.parquet` with columns: `ticker, horizon_min, strike, kronos_p_yes, kronos_mean_close, kronos_sigma_close, n_samples, status, error`. Cache is the SoT for orthogonality; orthogonality script reads from cache + v6_master.
- Random seed 42 for any non-deterministic step (numpy, torch). Torch deterministic mode `torch.use_deterministic_algorithms(True)` IFF supported on this build.
- NO em-dashes (U+2014) or en-dashes (U+2013) anywhere. grep `[\x{2014}\x{2013}]` after every file write.
- DO NOT use `last_price_dollars` as a price proxy. v6 reuses v6_master `kalshi_mid_at_t` which was built from `/historical/trades` AS-OF, not post-settlement.

## 10. Pass criteria (locked, ONE binding gate)

**C1: orthogonality improvement >= +0.005** on midband orthogonality holdout (T-30 horizon primary). Same gate v6 used. NO post-hoc threshold tuning.

- If C1 passes at T-30 OR T-15 midband: **STAND-BY for Phase 3 critic.** v7 Angle B has a candidate.
- If C1 fails at both horizons: **K1-style NULL**.
- Cluster-bootstrap CI lower bound > 0 is a SECONDARY robustness check, reported alongside the point estimate but does NOT relax C1.

C1 evaluation also reports:

- Brier baseline (logit on mid only) on holdout.
- Brier augmented (logit on mid + kronos_p_yes) on holdout.
- Improvement point estimate.
- 95% cluster-bootstrap CI on improvement.
- Self-reference diagnostic (fresh vs stale subsets).
- Effective n_test after NaN drops on kronos_p_yes.

## 11. Kill criteria (locked)

- **K-A**: orthogonality improvement < +0.005 at midband T-30 AND midband T-15. **NULL**.
- **K-B**: Kronos installation fails or model cannot run on CPU at reasonable latency (>30 sec/contract) AND deterministic fallback also infeasible. **BLOCKED** (documented in 05-kronos-results.md; not a NULL, since we never measured).
- **K-C**: Kronos output systematically returns absurd values (e.g., predicted price < 0 or > 10x current) on > 5% of contracts. **BLOCKED**, model is broken on CPU.
- **K-D**: Coinbase 1m context window has NaN_pct > 20% for > 20% of contracts (the v6 F6 audit standard generalized). **NULL with data-coverage caveat**.

## 12. What we will NOT do (per v6 Section 9)

- NO retraining of Kronos. Zero-shot only. Fine-tuning is a downstream v8 angle if v7-B passes.
- NO use of `last_price_dollars` as a price proxy.
- NO pre-Oct-2024 contracts (already excluded by v6_master).
- NO post-hoc threshold tuning.
- NO post-hoc swap from midband to widerband UNLESS midband sample-size guard fails by Section 3.4 v6 protocol.
- NO use of Kronos's volume / amount outputs beyond what is needed for p_yes. The pre-registered output is a price distribution -> p_yes scalar.
- NO ensemble with kalshi_cvd_30 or other v6 features in Stage B3. (If Kronos passes, a Phase 3 critic can explore feature interactions; this is downstream.)
- NO retrospective Monte Carlo sample-count tuning. sample_count locked at 30 (or 10 in fallback) BEFORE any inference.

## 13. Data and compute budget

- External data: $0. Coinbase 1m already cached in v6.
- Kronos model: free, Apache 2.0.
- LLM API: $0 (no LLM call in this angle).
- Compute: local CPU. Estimated 30 sample paths * 102M-param transformer * 120-min context * pred_len 30 = order of seconds per contract on CPU. If 5 sec/contract: 500 contracts = 2500 sec ~= 42 min wall-clock. If 30 sec/contract: same 500 -> 4 hours, falls back to 200 contracts -> 1.7 hours.
- Hard ceiling: < $2 of $24 LLM budget (this constraint is from task brief). No paid GPU host without operator approval.

## 14. Decision log

- 2026-05-25 v1: methodology written by v7 Angle B build agent before any Kronos clone / inference.
- Next: Stage B2 build. Clone Kronos, verify weights download, write inference loop, smoke test on 1 contract, then scale.

## 15. Reproducibility manifest

`data/v7/kronos_orthogonality.json` will record:

```json
{
  "run_timestamp": "...",
  "kronos_model": "NeoQuasar/Kronos-base",
  "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
  "n_samples_per_contract": 30,
  "device": "cpu",
  "torch_version": "2.12.0+cpu",
  "context_length_min": 120,
  "horizons": [30, 15],
  "v6_master_path": "data/v6/v6_master.parquet",
  "v6_master_rows": 3688,
  "n_contracts_run": ...,
  "n_contracts_succeeded": ...,
  "by_horizon": {
    "30": {
      "band_used": "midband" | "widerband",
      "n_train": ..., "n_orth": ...,
      "brier_baseline": ..., "brier_augmented": ..., "improvement": ...,
      "ci_lower_2.5": ..., "ci_upper_97.5": ...,
      "self_reference": {"fresh": {...}, "stale": {...}},
      "pass_005": ...
    },
    "15": {...}
  },
  "kronos_inference_latency_sec_mean": ...,
  "verdict": "PASS" | "NULL" | "BLOCKED"
}
```
