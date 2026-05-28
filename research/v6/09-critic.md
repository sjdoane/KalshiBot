# v6 Phase 3 Adversarial Critic

**Date:** 2026-05-25
**Author:** Agent v6-Critic (independent adversarial pass over v6 K1 NULL verdict)
**Status:** Read-only review. No modifications to Phase 2 source, dataset, or methodology.
**Predecessor reads:** `phase-1.5-methodology.md`, `06-orthogonality.md`, `07-model-results.md`, `08-gate-results.md`, `data/v6/v6_master.parquet`, `v6_orthogonality_results.json`, `v6_run_manifest.json`, `v6_build_log.json`, `scripts/v6/build_v6_master.py`, `scripts/v6/run_v6_orthogonality.py`, `src/kalshi_bot_v6/v6_features.py`, `tests/v6/test_v6_features.py`, `research/v5/07-critic.md` (style precedent).

---

## Executive summary

**Verdict on K1 NULL: STAND.** The Phase 2 verdict reproduces to 5 decimal places, no feature lift survives a cluster-bootstrap CI lower bound above zero, every attempted salvage either fails +0.005 or fails the Section 3.4 sample-size guard. The single outlier (F1 fresh-mid lift +0.00958 on n=45) has a 80% probability of exceeding +0.005 per per-row bootstrap, but does not pass the methodology contract and collapses to +0.00160 when operationalized as a conditional feature on full orth. Two methodology concerns are logged (train-orth regime shift, funding-delta cache-edge artifact) but neither flips the verdict. Top 2 salvages recommended: F1 fresh-mid conditional re-test via prospective collection, then close. Otherwise close v6 as a clean K1 NULL alongside v5-C.

---

## Test 1: K1 verdict reproduction

**Method.** Independently loaded `data/v6/v6_master.parquet`. Applied Section 4 filters (chronological 60/25/15 split with 24h purge buffer; midband [0.55, 0.80]). Fit logistic baseline on `kalshi_mid_at_t` and augmented on `(mid, kalshi_cvd_30)`. Same `C=10.0`, `random_state=42`, like-for-like NaN-drop subset.

**Result.**
- `n_train=430`, `n_test=168` (matches report exactly).
- `brier_base=0.27971`, `brier_aug=0.27756`, `improvement=+0.00214`.
- Matches `v6_orthogonality_results.json` `kalshi_cvd_30` lift to 5 decimals.

**Finding 1.1: Minor (verification).** The K1 number reproduces exactly. The orthogonality screen code is faithful to the methodology contract; no off-by-one or shuffle bug.

---

## Test 2: Sample-size adequacy

**Method.** Compared v6 midband T-30 train n=430 / orth n=168 to v5-C2 midband n=250. Tested F1 (kalshi_cvd_30) on combined train+orth n=598 with sweep over chronological train_frac in {0.50, 0.55, 0.60, 0.65, 0.70}.

**Result.**
- v5-C2 narrow [0.70, 0.95] midband had n=200 with 4 NOs (vs v6 midband 430 train with 61 NOs); v6's NO-mix is better.
- v5-C2 midband held best Brier improvement +0.0001 across 7 features. v6's best is +0.00214 (kalshi_cvd_30), 21x bigger in magnitude but still below threshold.
- Combined 60/40 split sweep on n=598: F1 lifts are {+0.00097, +0.00279, +0.00246, +0.00108, +0.00227}. Consistently positive, range 0.001 to 0.003, none clear +0.005.
- Train YES rate 0.858 vs orth YES rate 0.566 (regime shift, see Test 9.5).

**Finding 2.1: Important.** F1 has a small, consistent, positive lift across all reasonable split fractions but never clears +0.005. v5-C2 at n=250 produced a clean null with 21x smaller magnitude; v6's lift is bigger but below threshold. Sample size is adequate to detect a +0.005 effect per Section 4.2; the null is real, not n-driven.

---

## Test 3: F1 fresh-mid sliver bootstrap

**Method.** Per-row bootstrap (B=5000) of the n=45 fresh-mid (`time_since_last_trade_at_t < 5 min`) subset of T-30 orth holdout. Conditional feature `cvd_30_when_fresh = cvd_30 if tslt<5 else 0` tested on full T-30 midband orth.

**Result.**
- Fresh-mid (n=45): mean lift +0.00960, 95% CI [+0.00025, +0.02175].
- P(lift > 0) = 98.0%, P(lift > 0.005) = 80.0%.
- Conditional feature `cvd_30_when_fresh` on full orth n=168: lift +0.00160 (below threshold).
- Cluster-bootstrap (whole-day) on full F1 lift, n_dates=64, B=5000: mean +0.00220, 95% CI [-0.00035, +0.00546]. P(lift > 0.005) = 4.5%.

**Finding 3.1: Important.** The fresh-mid sliver has a real, statistically significant positive lift, but it collapses when projected back to the full orth via a clean conditional feature. The Section 3.5 diagnostic correctly flagged this as regime-specific. Even an honest +0.01 Brier improvement on the < 1 fresh-mid candidate / day rate would generate < 5 high-conviction trades / year.

**Finding 3.2: Minor.** The methodology Critic Important Finding 2 worried about lift concentrating in STALE-mid; reality concentrated in FRESH-mid. This is the opposite of the predicted failure mode and confirms the diagnostic is correctly catching real distributional structure.

---

## Test 4: F4 sample-selection re-audit

**Method.** Re-ran F4 (`kalshi_price_drift_15`) at T-15 like-for-like on drift-defined widerband subset (matches report). Additionally tested at T-15 MIDBAND drift-defined (not in report).

**Result.**
- T-15 widerband drift-defined: train n=267 / test n=64, lift +0.00272 (matches report).
- T-15 MIDBAND drift-defined: train n=147 / test n=40, lift +0.01162. Per-row bootstrap CI [-0.005, +0.030], P(lift > 0.005) = 76%.
- T-15 midband drift-defined sample sizes: train_yes=126 / train_no=21 / orth_yes=24 / orth_no=16. **All four counts fail the Section 3.4 guard (50/50/30/30 minimums).**

**Finding 4.1: Important.** The Phase 2 report did NOT test F4 at T-15 midband because the midband Section 3.4 sample-size guard fails. The apparent +0.01162 lift on T-15 midband drift-defined exceeds threshold but is computed on n=40 test rows with n=16 NOs, well below the guard floor. The bootstrap CI straddles zero. Phase 2's decision to use widerband at T-15 is correct.

**Finding 4.2: Minor.** F4 at T-30 is 100% NaN across the entire master parquet because the K1b NaN guard requires both a trade before window_start AND a trade inside window; with median lifetime ~1 hr KXBTCD contracts the window predates open in essentially every case. Structural, not a bug.

---

## Test 5: Multivariate joint orthogonality

**Method.** Fit linear logistic and LightGBM on (mid, F1, F2, F4, F5, F6, F7, F8, F9) on T-30 midband train, evaluated on orth. Tested combined-band [0.05, 0.95] variant.

**Result.**
- Linear joint (T-30 midband, 8 features + mid): brier_base=0.28748 vs brier_aug=0.32473. Lift = -0.03724 (worse than baseline).
- Sweep over C in {0.01, 0.1, 1.0, 10.0}: all lifts negative.
- LightGBM mid-only baseline: brier=0.20927.
- LightGBM joint (mid + 8): brier=0.19956. Fair LGBM-vs-LGBM lift = +0.00971. Cluster-bootstrap (n_dates=64): mean +0.00895, 95% CI [-0.03515, +0.05907].
- Full-band [0.05, 0.95] LGBM: lift = -0.03916 (overfit).
- Identity predictor (predict = mid): brier=0.21667. LGBM mid-only beats identity by 0.007, meaning the LGBM is mostly absorbing miscalibration of the band-restricted mid distribution, not learning new signal.

**Finding 5.1: Important.** Univariate orthogonality is the methodology contract and joint linear orthogonality fails worse than univariate. Fair LGBM-vs-LGBM lift of +0.00971 is above threshold in point estimate but cluster-bootstrap 2.5th is -0.035 and 97.5th is +0.059. No significant joint signal beyond chance.

**Finding 5.2: Minor.** Methodology specifies univariate orthogonality (Section 3.1); joint test was appropriately not run in Phase 2.

---

## Test 6: Spread-realism check on K3

**Method.** Probed `v6_master.parquet` and `kxbtcd_sample_trades.parquet` for `yes_bid_dollars` / `yes_ask_dollars` columns.

**Result.** Neither file contains bid/ask columns. The build script does not pull a /markets snapshot at horizon time, only /historical/trades. The +2c spread assumption in Section 6 would have used a static approximation in any K3 evaluation.

**Finding 6.1: Minor.** Moot because K1 killed before K3. If Phase 4 attempts a salvage that reaches the model-fitting step, the build script must be extended to fetch /markets snapshot at horizon time to verify the 2c spread approximation. Currently v6 has no empirical spread observation.

---

## Test 7: Stale-mid Brier baseline check

**Method.** Computed three baseline candidates on midband T-30 orth: (A) logit on mid only, (B) constant train mean, (C) identity (predict = mid).

**Result.**
- A logit on mid: brier=0.27971 (matches report).
- B constant 0.8581 (train mean): brier=0.33136.
- C identity: brier=0.21667.

**Finding 7.1: Important.** The fitted logit baseline (0.27971) is WORSE than identity (0.21667) by +0.063, because logit trained on YES-rate-0.858 train data predicts ~0.86 for almost every test row regardless of mid. Section 3.1 specifies logit baseline (honest, allows coefficient testing). **A +0.002 improvement over logit baseline still trails identity by +0.061.** Under-threshold features that "almost pass" are still dominated by predict-equals-mid.

---

## Test 8: Feature engineering integrity audit

**Method.** Picked sample row 100 (T-15 contract, low band) and a random T-30 midband row (idx 20 of midband subset). Manually recomputed Coinbase realized_vol, vwap_dev, funding_level, and funding_delta from cached endpoint data.

**Result.**
- T-30 midband row, ticker=KXBTCD-24DEC2315-T92249.99, t=2024-12-23 19:30 UTC.
- Manual coinbase realized_vol = 0.000897 vs stored 0.000897 (exact match).
- Manual vwap_dev = -0.003417 vs stored -0.003417 (exact match).
- Funding level = 1.54e-6 vs stored 1.54e-6 (exact match).
- Funding delta_4h = 1.54e-6 (manual) vs stored 1.54e-6 (match), BUT manual level_4h returned 0.0 from the asof_lookup edge (no funding data > 4h before t at start of cache).

**Finding 8.1: Important.** Feature values match manually. However, on 929 of 3688 rows (25.2%) the stored `funding_rate_delta_4h_at_t` is numerically equal to `funding_rate_level_at_t`. This is `asof_lookup` returning `0.0` at cache boundary plus the ~20% of Deribit funding rows that have `interest_1h == 0` scattered throughout (real low-funding regimes that propagate the artifact). In midband T-30 train: 90 of 430; orth: 37 of 168. Both contaminated.

**Finding 8.2: Important.** Despite contamination, funding-delta lift was 8.7e-11. The artifact did not change K1 verdict because funding-delta has no signal anyway. A future salvage testing funding-delta on different sample period must patch `asof_lookup` to return NaN at cache boundaries.

---

## Test 9: Date range integrity

**Method.** Traced eligibility filter on `crypto_full_KXBTCD.parquet` to verify why date range starts 2024-12-12.

**Result.**
- Total KXBTCD: 592,571 rows. Post-Oct-2024: 588,200.
- After `lifetime_hours in [0.5, 4]` filter: 566,178 rows; date range 2024-12-12 to 2026-03-24.
- Pre-Dec-2024 eligible: 0. Hourly KXBTCD contracts launched as a series around Dec 12, 2024; earlier contracts have lifetime > 4h.
- Coinbase cache start: 2024-12-12 12:55 UTC. Aligned with first eligible contract.

**Finding 9.1: Minor.** No silent data drop. The Oct-Dec 2024 gap is structurally explained by the lifetime filter and is the correct behavior. Methodology Section 4.1 says "post-Oct-2024" but the actual sample starts Dec-2024; this is consistent with eligibility, not a bug.

---

## Test 9.5: Train/orth regime shift (unprompted finding)

**Method.** Tabulated monthly YES rate within midband T-30. Tabulated within-stratum YES rate using the `_stratum` column from `build_v6_master.py`.

**Result.**
- Monthly midband T-30 YES rate: ~0.85-0.95 in Dec-2024 through Oct-2025, then drops to 0.55, 0.62, 0.42, 0.84, 0.62 across Nov-2025 / Dec-2025 / Jan-2026 / Feb-2026 / Mar-2026.
- The `mid` stratum (settlement-time last_price_dollars in [0.55, 0.80]) had YES rate 0.95 through Oct-2025 then dropped to ~0.55 in Nov-2025 and ~0.39 in Jan-2026.
- Result: chronological 60% train cuts off at 2025-11-18, with train YES rate 0.858 and orth YES rate 0.566 (a 0.29 absolute shift between train and orth distributions).

**Finding 9.5.1: Important.** Real Kalshi market regime change: midband-by-settlement contracts in late-2025 to early-2026 started settling NO ~50% of the time vs ~5% earlier. Orth holdout is drawn from a different distribution than train. To check direction: re-ran F1 on Aug-2025-onwards midband T-30 (n=370): lift = -0.00130 (NEGATIVE, vs full +0.00214). The original F1 lift was FLATTERED by regime shift. K1 NULL stands and is stronger under regime control.

**Finding 9.5.2: Minor.** `stratify_sample` in `build_v6_master.py` uses settlement-time `last_price_dollars` to assign mid vs out, but master parquet uses AS-OF horizon-time `kalshi_mid_at_t`. Internally consistent for sampling, but the train-orth chronological cut interacts with the stratified sampler to produce the regime shift above. Phase 4 salvages should regime-balance or restrict train period.

---

## Test 10: Highest-prior Phase 4 salvages

I attempted four salvages internally during this critic pass. Results:

| Salvage | Tested approach | Result | Verdict |
|---|---|---|---|
| Conditional F1 fresh-mid | `cvd_30_when_fresh = cvd_30 if tslt<5 else 0` on full T-30 orth | lift +0.00160 (n=168) | FAIL |
| F4 T-15 midband subset | drift-defined train -> drift-defined test, midband only | lift +0.01162 (n=40) but bootstrap CI [-0.005, +0.030], sample-size guard fail | FAIL |
| Multivariate LGBM joint | (mid, 8 features) at T-30 midband | lift +0.00971 (LGBM vs LGBM), bootstrap CI [-0.035, +0.059] | FAIL |
| Combined-band univariate | F1 on full band [0.05, 0.95] T-30 | lift +0.00061 (n=371) | FAIL |
| Regime-restricted F1 | post-Aug-2025 T-30 midband | lift -0.00130 (n=91 orth) | FAIL (negative) |

**Priority recommendations for Phase 4 (max 2 salvages, both low-cost):**

**S1: F1 fresh-mid prospective collection (PRIOR 25%, COST 0).**
Fresh-mid (tslt < 5 min) subset has bootstrap CI [+0.00025, +0.02175], mean +0.00960. With n=45 the test is power-limited. Prospective collection of F1 + mid + tslt observations via v1 scaffold for 60-90 days (no live capital) yields ~30-60 new fresh-mid observations. Pushed to n=75-105 the lower CI bound would tighten meaningfully. If the lift narrows toward +0.005 but does not clear, close v6 cleanly; if it clears with robust bootstrap CI, build a conditional model. No refit needed; v6 build script re-runs with same code. Risk: still subject to regime shift; mitigate by chunking by month.

**S2: Microstructure expansion at T-30 KXBTCD-1h (PRIOR 15%, COST: 1-2 weeks build).**
v6's free-tier feature universe is broad but every external feature lift is ~0. Only F1 Kalshi-internal CVD shows detectable lift. Targeted retry: ONLY Kalshi-internal features at higher granularity (cvd at N=5, N=10, trade_size_skew, quote_imbalance from /markets snapshots, orderbook_depth_change). Requires prospective /markets snapshots (v6 used only /historical/trades). Risk: asymmetric; could find real micro-edge OR confirm null with stronger sample.

**NOT recommended:**
- Different horizons (T-45, T-60): v5-C already proved T-1h null; T-45 and T-60 interpolate between v5 null and v6 null with no fresh angle.
- LightGBM nonlinear: ran above, lift is bootstrap-indistinguishable from zero.
- Contract-day fixed effects: ran in regime-restricted Test 9.5; signal disappears, not appears.
- Percentile-rank decision rule: K1 killed before any decision rule was tested; need to pass orthogonality first.

**Phase 4 budget:** S1 has zero API spend (data already cached or generated by v1's running bot). S2 has < $1 API spend (Kalshi /markets snapshots are 10 req/sec, ~50k snapshots over a 60-day window).

---

## Verdict on K1 NULL: STAND

The Phase 2 K1 NULL reproduces exactly. No methodology bug. No phantom edge of the v5-B `last_price_dollars` variety (v6 correctly uses `yes_price_dollars` AS-OF horizon-time only, not post-settlement, verified in `kalshi_mid_at_t` source). The single observation worth flagging (F1 fresh-mid +0.00960 lift, n=45) is documented in Phase 2 report and operationalizes below threshold.

The regime shift biases the test in F1's favor; with regime control, F1 lift goes negative. K1 NULL is stronger under regime control. The funding-delta cache-edge artifact contaminates 25% of rows but has no signal, so does not change verdict.

**STAND-WITH-SALVAGES.** Two low-cost salvages in priority order: (1) prospective F1 fresh-mid collection on KXBTCD via v1's existing infrastructure for 60-90 days, (2) Kalshi-internal microstructure expansion via /markets snapshots. If both fail or operator declines, v6 closes cleanly as a K1 NULL alongside v5-C; v1 continues unchanged on $32 with W1 denylist. The v6 sample stays valuable as a clean reference for future microstructure work.
