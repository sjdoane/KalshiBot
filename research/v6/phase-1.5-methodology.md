# v6 Phase 1.5 Methodology Lock

**Date:** 2026-05-25
**Status:** LOCKED before Phase 2 data pull. Any changes after this point require explicit operator authorization and a new methodology critic pass.
**Predecessors:** `00-master-plan.md`, `01-microstructure-literature.md`, `02-data-feasibility.md`, `03-kalshi-crypto-profile.md`, `04-v5c-novelty-audit.md`, `05-phase-1-synthesis.md`.

## 1. Pivoted v6 thesis (re-stated)

After Phase 1, the v6 hypothesis is: **Kalshi internal taker-flow imbalance (CVD) and recent trade momentum at T-30 / T-15 minute horizons on KXBTCD hourly contracts carry information beyond what is already in the Kalshi mid-price.** Supplementary features: Coinbase realized vol at T-30 (re-test of v5-C feature at new horizon), Deribit funding-rate delta (genuinely new transformation), DVOL term-structure delta (untested in v5-C), spot-futures basis delta (vs v5-C's level).

If these features pass orthogonality, fit a calibrated model on midband [0.55, 0.80] contracts and evaluate via cluster-bootstrap on a held-out chronological slice. Apply the +2c-rule and a maker-bid quote rule for the decision layer.

## 2. Feature universe (LOCKED)

Nine candidate features at two primary horizons (T-30 min and T-15 min before settlement). All features sampled AS-OF the horizon timestamp using only data observable AT THAT TIME.

| ID | Feature | Definition (AS-OF time `t`) | Data source | Horizon variants |
|---|---|---|---|---|
| F1 | kalshi_cvd | sum over trades in `[t - N min, t]` of (count_fp * sign(taker_outcome_side)), sign = +1 if `yes` (taker bought YES, bullish), -1 if `no` (taker bought NO, bearish). VERIFIED EMPIRICALLY against `data/v6/kxbtcd_sample_trades.parquet` (n=9446): `taker_outcome_side='yes'` <=> `taker_book_side='bid'`, `taker_outcome_side='no'` <=> `taker_book_side='ask'`. | Kalshi `/historical/trades` | N = 15, 30 |
| F2 | kalshi_trade_count | number of trades in `[t - N min, t]` | Kalshi `/historical/trades` | N = 15, 30 |
| F3 | kalshi_time_since_last_trade | minutes between `t` and most recent trade `<= t` | Kalshi `/historical/trades` | single value at `t` |
| F4 | kalshi_price_drift | last_traded_price at `t` minus last_traded_price at `t - N min` | Kalshi `/historical/trades` | N = 15, 30 |
| F5 | funding_rate_delta | Deribit BTC-PERPETUAL `interest_1h(t)` minus `interest_1h(t - 4h)` | Deribit `get_funding_rate_history` | single value at `t` |
| F6 | coinbase_realized_vol | stdev of 1m log returns over `[t - 30 min, t]` | Coinbase `/products/BTC-USD/candles?granularity=60` | N = 15, 30 (window length) |
| F7 | coinbase_vwap_dev | VWAP over `[t - 30 min, t]` / spot at `t` minus 1 | Coinbase `/products/BTC-USD/candles?granularity=60` | N = 15, 30 |
| F8 | dvol_delta | Deribit BTC DVOL at `t` minus DVOL at `t - 1h` | Deribit `/public/get_volatility_index_data` | single value at `t` |
| F9 | basis_delta | (Deribit BTC-PERP / Coinbase spot at `t`) minus (Deribit BTC-PERP / Coinbase spot at `t - 1h`) | Deribit + Coinbase | single value at `t` |

**Baseline raw feature** (always in the model, NOT subject to orthogonality drop): `kalshi_mid_at_t` = last_traded_price at `t` (Kalshi's own implied probability).

**Feature count**: 9 features times (1 or 2 horizon variants) = ~14 distinct feature columns plus the baseline mid.

## 3. Orthogonality protocol (LOCKED, v5 protocol with one amendment per Agent D)

Same orthogonality protocol used in v5-C, with one critical amendment for funding-rate-delta:

### 3.1 Standard orthogonality test

For each candidate feature `f`:
1. Fit a univariate logistic regression on `kalshi_mid_at_t` only. Compute Brier on the orthogonality holdout (most-recent-15% of contracts, chronological).
2. Fit a logistic regression on `(kalshi_mid_at_t, f)`. Compute Brier on the same holdout.
3. Improvement = `Brier_baseline - Brier_with_f`.
4. Pass criterion: `Improvement >= +0.005`.

### 3.2 Funding-delta amendment

Per Agent D's recommendation: funding-rate-DELTA shares the data stream with v5-C's funding-rate-LEVEL. To prevent funding-delta from being a sneaky restatement of funding-level:

- Fit baseline as `(kalshi_mid_at_t, funding_rate_level_at_t)` (with funding LEVEL included in baseline).
- Test funding-delta as `(kalshi_mid_at_t, funding_rate_level_at_t, funding_rate_delta_at_t)`.
- Improvement is delta-net-of-level Brier improvement.

### 3.3 Correlation pre-screen

Before orthogonality, compute pairwise correlation matrix across all 14 feature columns. If any pair has `|rho| >= 0.85`, drop the lower-priority one (priority: F1 > F2 > F4 > F6 > F7 > F5 > F8 > F9 > F3). Document the drop and reasoning in `06-orthogonality.md`.

### 3.5 Self-reference diagnostic (per Methodology Critic Important Finding 2)

F1 (kalshi_cvd) is correlated with kalshi_mid by construction: the trades used to compute CVD also moved the mid. The orthogonality lift on F1 may concentrate in the 80% of contracts where mid is stale-by-construction (median 0 trades in T-15, 1 in T-30 per Agent C).

Diagnostic to run before reporting F1 as orthogonality-passed:
- Split orthogonality holdout by `time_since_last_trade_at_t < 5 min` vs `>= 5 min`.
- Compute F1 orthogonality lift separately on each subset.
- If lift is concentrated (e.g., > 80% of the absolute lift) in the stale-mid subset, F1 is contract-state-conditioned, not generic alpha. Document but do not auto-drop; the model uses it conditionally on the regime.

### 3.4 Sample-size guards

For orthogonality to be valid, both YES and NO outcomes must be present in train AND test slices.

- Required: train YES >= 50 AND train NO >= 50; test YES >= 30 AND test NO >= 30.
- If midband holdout fails this, FALL BACK to widerband [0.55, 0.95] for orthogonality only.
- If widerband also fails, KILL v6 at Phase 1.5 (NULL); the band has insufficient NO mix to even probe.

## 4. Sample construction (LOCKED)

### 4.1 Eligibility filter

A KXBTCD contract is v6-eligible if ALL of:
- `close_time` after 2024-10-01 (post-Becker sign flip).
- `lifetime_hours` between 0.5 and 4 (excludes pre-launch multi-day events).
- At least 1 trade printed in `[t - 30 min, t]` for AT LEAST the T-30 horizon (otherwise v6 cannot fire on it). This restricts the sample to contracts where a maker COULD have observed and reacted to the feature.
- `status == "settled"` (so outcome is known).

For T-15 horizon: must have at least 1 trade in `[t - 15 min, t]`. Per Agent C, this is a much stricter filter (median 0 trades), so T-15 sample will be roughly 20% of T-30 sample.

### 4.2 Band stratification

Per v5-C2's finding that midband is the only band with sufficient NO-mix:

- **Midband [0.55, 0.80]** (primary): mid at `t` falls in [0.55, 0.80]. Estimated n at T-30 ~10k to 30k post-eligibility.
- **Widerband [0.20, 0.80]** (fallback for orthogonality only).

Narrow [0.70, 0.95] is EXCLUDED because v5-C2 found train YES rate 0.98 leaves Brier headroom under +0.001 even with perfect features.

Per Methodology Critic Minor Finding 7: at the low-n end of midband (~10k contracts post-eligibility), the 25% orthogonality holdout = ~2,500 contracts across ~100 daily clusters. Cluster-bootstrap precision is O(1/sqrt(100)), comparable to v5-B's 43-cluster regime. Manageable but not tight. CI widths will be reported alongside point estimates.

### 4.3 Train / orthogonality / holdout split

Chronological, NO RANDOM SHUFFLE.

- Train: first 60% by `close_time`.
- Orthogonality holdout: next 25%.
- Final holdout (untouched until end of Phase 2): last 15%.

Purge buffer: 24 hours between train end and orthogonality start; 24 hours between orthogonality and final holdout. Standard time-series purge per Lopez de Prado 2018.

### 4.4 Cluster definition for bootstrap

Within each split, group contracts by `close_time.date()` (UTC). Cluster-bootstrap resamples WHOLE DAYS, not individual contracts. This prevents serial correlation across adjacent hourly contracts from inflating effective sample size.

## 5. Model architecture (LOCKED)

Two model classes tested in parallel; better one selected by orthogonality-holdout BSS (NOT by final holdout, which is reserved).

- **M1**: Logistic regression on `(kalshi_mid_at_t, survived_features)` with L2 regularization. C tuned by 5-fold time-series CV on train only.
- **M2**: LightGBM (max_depth=4, num_leaves=15, learning_rate=0.05, num_iterations <= 200, early stopping on a held-out 10% of train). Same feature inputs.

**No feature interactions added by hand.** LightGBM finds them; logistic is a deliberately-linear baseline.

**Calibration:** if model output's Brier is good but ECE is high, apply isotonic regression on a 10% calibration slice of train (not test).

## 6. Decision rule and execution simulation (LOCKED)

Per Methodology Critic Important Finding 4: both taker and maker rules are now BINDING. The operator's v1 mission is maker-side; the taker-side gate is the execution-realistic stress test. v6 SHIPS only if both extract positive P&L; PARTIAL if one passes; NULL if neither.

### 6.1 Binding rule A: +2c-take rule (taker side, execution-realistic)

For each holdout contract at horizon `t`:
- Compute `model_prob`.
- Compute `kalshi_mid_at_t` from last_traded_price.
- Approximate `kalshi_yes_ask = mid + 0.01`, `kalshi_yes_bid = mid - 0.01` (median spread 2c per Agent C).
- Decision:
  - **BUY YES** if `model_prob >= kalshi_yes_ask + 0.02` AND `0.20 <= kalshi_yes_ask <= 0.85`.
  - **BUY NO** if `(1 - model_prob) >= kalshi_no_ask + 0.02` AND `0.20 <= kalshi_no_ask <= 0.85`. Note `kalshi_no_ask = 1 - kalshi_yes_bid` so `kalshi_no_ask = 1 - mid + 0.01`.
  - **NO TRADE** otherwise.
- Per-contract P&L assuming fill at the ask (taker):
  - BUY YES: `(outcome == 1) ? 1 - kalshi_yes_ask : -kalshi_yes_ask`, minus TAKER fee `ceil(0.07 * C * P * (1-P))`.
  - BUY NO: mirror.

### 6.2 Binding rule B: maker-quote rule (operator deployment intent)

The v1 strategy is maker-side. Rule B evaluates v6 as if it were deployed in v1's quoting pattern.

For each holdout contract at horizon `t`:
- BUY YES if `model_prob - mid >= 0.04` AND `0.30 <= mid <= 0.85`. Quote at `mid - 0.01` (better than current bid by 1c, top-of-book).
- BUY NO if `(1 - model_prob) - (1 - mid) >= 0.04` AND `0.30 <= (1 - mid) <= 0.85`. Quote at `(1 - mid) - 0.01`.
- Fill modeling: assume effective fill rate of 15% per contract that has >= 1 trade in T-30 (Agent C's 38% upper bound halved for queue position; this is a documented approximation).
- Per-fired-contract expected P&L: `fill_rate * conditional_P&L`, where conditional_P&L uses the quote price (mid - 0.01 for YES) and MAKER fee `ceil(0.0175 * C * P * (1-P))`.

### 6.3 Approximations documented

The decision-rule simulation makes three approximations that must be flagged in the verdict:

1. `kalshi_yes_ask` is approximated as `mid + 0.01` based on Agent C's live snapshot median spread. Sensitivity: re-run with spread 3c and 4c (Agent C p90).
2. Filling at the ask assumes a taker trade with no slippage beyond 1c. Reasonable per Agent C's 1k to 7k contract depth.
3. The `kalshi_yes_bid` is approximated as `mid - 0.01`. Maker-quote rule sensitivity uses this directly.

These are documented approximations, not phantom edges. The v5-B failure mode (`last_price_dollars` reading as ~$0.01 post-settlement) is structurally impossible here because we use the IN-CONTRACT last-trade price at sample time, not the post-settlement snapshot.

## 7. Pass criteria (LOCKED, binding)

Five binding criteria. ALL must pass for v6 to ship.

### C1: Orthogonality survival

At least 1 feature must pass orthogonality (+0.005 Brier improvement) on midband holdout.

- IF C1 fails: **KILL at Phase 1.5**. Write NULL verdict immediately, do NOT build the model.
- This is the cheapest kill point and where v6's modal NULL is expected.

### C2: Brier skill score on FINAL holdout

After model fit on train and selected by orthogonality-holdout BSS, evaluate on FINAL holdout (last 15%, untouched).

- Required: `BSS_final >= +0.01` on midband.
- BSS = 1 - (Brier_model / Brier_baseline), where baseline is the constant-prob model fit on train mean.

### C3a: Cluster-bootstrap CI on +2c-take rule P&L

Bootstrap-resample WHOLE-DAY clusters from final holdout 5000 times. Compute mean per-contract P&L for the rule A (+2c-take) firing decisions in each resample.

- Required: 2.5th percentile of bootstrap distribution > 0 cents per contract.
- Reported with point estimate, 2.5th, 97.5th.

### C3b: Cluster-bootstrap CI on maker-quote rule P&L

Same cluster-bootstrap on rule B (maker-quote), with the 15% effective fill rate.

- Required: 2.5th percentile of bootstrap distribution > 0 cents per fired contract.
- This is the operator-deployment-intent test.

### C4: Model output magnitude span

On final holdout: distribution of `|model_prob - kalshi_mid|`.

- Required: at least 5% of holdout observations have `|model_prob - kalshi_mid| >= 0.03`. (3c separation between model and mid, so the +2c rule can fire.)
- This catches the v5-B "shrinkage to 0.5" failure mode where the model never moves enough from mid to trigger.

### C4b: Minimum fire-count floor (per Methodology Critic Important Finding 3)

To prevent tail-luck bootstrap pass on a tiny fire count:

- Required: rule A fires at least 200 times on final holdout midband (or 1% of holdout n, whichever is lower).
- Required: rule B fires at least 200 times on final holdout midband (or 1% of holdout n, whichever is lower).
- If either rule fails C4b, that rule's C3 is reported as INSUFFICIENT-N rather than PASS, regardless of bootstrap CI.

### C5: Realistic-spread sensitivity audit

Re-run the +2c-take rule P&L at spread = 3c and spread = 4c (Agent C p90 spread).

- Required: at spread 3c, bootstrap CI lower bound > -1 cent per contract (small allowance for worse-than-typical spread).
- At spread 4c, mean P&L still positive (no requirement on CI).
- If C5 fails, the gate verdict is PARTIAL not PASS. NULL if it's well below 0.

## 8. Kill criteria (LOCKED)

- **K1**: C1 fails (0 features pass orthogonality) at midband AND widerband. **NULL at Phase 1.5.**
  - K1 sub-clause (per Methodology Critic Minor Finding 10): a widerband-only pass that does not have a Section 4.2 tail-asymmetry trace is also K1-NULL. The widerband often picks up extreme-tail asymmetry (yes_rate near 0.98) and is not a generic alpha; do not promote a widerband-only pass without a documented mechanism.
- **K1b** (per Methodology Critic Important Finding 5): F4 (kalshi_price_drift) orthogonality lift comes predominantly from contracts where drift = 0 by construction (no second trade in window). F4 then encodes contract-state, not signal. Drop F4 from the model; do NOT count as a surviving orthogonality pass.
- **K2**: C2 fails (BSS < +0.01 on final holdout). **NULL at Phase 2.**
- **K3a**: C2 passes but BOTH C3a and C3b fail. **NULL** (v5-B pattern recurrence; signal exists but neither rule extracts).
- **K3b**: C2 passes, one of {C3a, C3b} passes, the other fails. **PARTIAL** with rule-specific verdict.
- **K4**: Phase 3 critic identifies a new failure mode (e.g., phantom-edge analog, leakage, biased sample). Salvage in Phase 4 only if the critic explicitly recommends; otherwise **NULL**.
- **K5**: Spread sensitivity (C5) shows the +2c-take rule P&L is critically dependent on spread = 2c assumption (e.g., flips to -2c per contract at spread 3c). **NULL** with execution-cost note.
- **K6** (per Methodology Critic Important Finding 3): rule fire count fails C4b on BOTH rules. **NULL** as "model signal too narrow to deploy at any frequency."

## 9. What we will NOT do (per v5 lessons)

- **NO** use of `last_price_dollars` as a bid or ask proxy. Use only Kalshi's last-traded-price AT SAMPLE TIME, with explicit +/- 1c spread approximation. The v5-B Killer Finding 2c is the canonical warning.
- **NO** pre-Oct-2024 contracts in any train, orthogonality, or holdout sample. Becker sign flip.
- **NO** narrow band [0.70, 0.95] in primary analysis. YES rate 0.98 leaves no Brier headroom.
- **NO** simple holdout. Cluster-bootstrap by whole-day clusters, with chronological 60/25/15 split and 24h purge buffers.
- **NO** post-hoc threshold tuning. Decision rules and thresholds are locked at +2c-rule, 0.20-0.85 range, model_prob - mid > 0.02 boundary.
- **NO** training on out-of-band contracts to predict midband (no cross-band transfer). Midband-only train for midband evaluation.
- **NO** retesting v5-C's tested feature universe at T-1h. v6 horizons are T-30 and T-15 only.
- **NO** funding-rate level as a feature unless it co-enters with delta (delta is what's tested).
- **NO** retraining within the orthogonality holdout. Per v5-B Killer Finding 4.4: pipeline must refit per fold and never share state across train/test boundaries.

## 10. Data acquisition plan (LOCKED for Phase 2)

Acquired data, in order:

1. **Kalshi `/historical/trades`** for all eligible KXBTCD contracts (post-Oct-2024, lifetime 0.5 to 4h). Estimated 8k to 30k contracts per Agent C. Use `kalshi_client.py` with respectful rate limiting (10 reqs/sec).
2. **Coinbase 1m candles** AS-OF the union of all contract close_times. Endpoint `/products/BTC-USD/candles?granularity=60`. Free, no auth.
3. **Deribit funding (`interest_1h`)** for BTC-PERPETUAL across the date range. Endpoint `/public/get_funding_rate_history`. Free.
4. **Deribit DVOL** hourly across the date range. `/public/get_volatility_index_data?currency=BTC&resolution=3600`. Free.
5. **Deribit BTC-PERP price** at hourly resolution (for basis_delta). `/public/get_tradingview_chart_data?instrument_name=BTC-PERPETUAL&resolution=60`. Free.

Total spend: $0. Authorized $30-60 reserve held for unforeseen needs (e.g., Coinglass Hobbyist if Phase 2 finds positive signal worth augmenting with paid sources).

Cache layout: `data/v6/cache/{source}_{date_range}.parquet`. Single canonical merge in `data/v6/v6_master.parquet`.

## 11. Engineering hygiene (LOCKED)

- All Phase 2 code in `src/kalshi_bot_v6/` and `scripts/v6/`. Unit tests in `tests/v6/`.
- No mutation of v1 or v5 source.
- No touching `.env`, `data/live_trades/`, `data/paper_trades/`.
- All file writes preceded or followed by an em-dash check (`grep -P '[\x{2014}\x{2013}]'`).
- Each engineering milestone gets a code-review agent pass (per project rule).
- Random seed: 42 for any non-deterministic step. Document seed in result JSON.

### 11.1 Entry tests (must pass before any trainer runs)

Per Methodology Critic Killer Finding 1: pin sign conventions to verified data probes, not verbal descriptions.

- **CVD direction test**: assert that F1 implementation, when given a trade with `taker_outcome_side='yes'`, returns sign = +1 (and `taker_outcome_side='no'` returns -1). Use `data/v6/kxbtcd_sample_trades.parquet` (n=9446) as ground truth.
- **F4 cross-contract leak test**: kalshi_price_drift must return NaN when `time_since_last_trade > N min` OR when `t - N` falls before contract `open_time`. Unit test against synthetic data with two contracts of differing tickers.
- **F6 NaN-gap audit**: Coinbase 1m candle reads must flag `nan_pct_in_window` alongside realized_vol output. If `nan_pct > 20%` for a sample, drop that sample.
- **F5 epoch-jump note** (per Methodology Critic Minor Finding 6): Deribit `interest_1h` is rolling-1h, NOT per-epoch funding payment, so the 4h delta is smooth. No epoch-jump guard needed.

## 12. Reproducibility manifest

Phase 2 build script writes to `data/v6/v6_run_manifest.json`:

```json
{
  "run_timestamp": "...",
  "git_commit": "...",
  "data_sources": {
    "kalshi_trades": {"n_contracts": ..., "n_trades": ..., "date_range": [...]},
    "coinbase_candles": {"n_minutes": ..., "date_range": [...]},
    "deribit_funding": {"n_obs": ..., "date_range": [...]},
    "deribit_dvol": {"n_obs": ...},
    "deribit_perp": {"n_obs": ...}
  },
  "split": {"train_close_max": "...", "orth_holdout_close_max": "...", "final_holdout_close_max": "..."},
  "midband_definition": [0.55, 0.80],
  "features": {"correlation_drops": [...], "orthogonality_pass": [...], "orthogonality_fail": [...]},
  "model": {"class": "LogReg" | "LGBM", "params": {...}, "BSS_orth_holdout": ..., "BSS_final_holdout": ...},
  "gate": {"C1": ..., "C2": ..., "C3": ..., "C4": ..., "C5": ...},
  "verdict": "SHIP" | "PARTIAL" | "NULL",
  "kill_reason_if_null": "K1" | "K2" | "K3" | ...
}
```

## 13. Critic readiness

Before Phase 2 begins, run methodology critic agent with full read-only access to:
- This doc
- Phase 1 docs (01 through 05)
- The v5 Phase 3 critic at `research/v5/07-critic.md`

Critic's job: stress-test sections 2, 3, 4, 6, 7, 8 of this doc. Identify any missing kill condition, any leak in the CV split, any phantom-edge risk, any tested-but-mislabeled feature.

If critic finds material flaws, this doc gets ONE revision pass before final lock.

## 14. Decision log

- **2026-05-25 (v1)**: methodology v1 written by orchestrator. Next: methodology critic agent.
- **2026-05-25 (v2)**: methodology critic returned 1 Killer + 4 Important + 5 Minor findings. Revisions applied:
  - Killer Finding 1: F1 CVD sign convention re-anchored to `taker_outcome_side` empirical ground truth (n=9446 verification).
  - Important Finding 2: Section 3.5 self-reference diagnostic added.
  - Important Finding 3: C4b minimum fire-count floor added; K6 kill condition added.
  - Important Finding 4: Section 6 restructured. BOTH rule A (+2c-take) and rule B (maker-quote) are BINDING. Either passing = PARTIAL; both passing = SHIP; neither = NULL.
  - Important Finding 5: K1b kill condition added (F4 contract-state artifact); Section 11.1 unit test for cross-contract drift NaN guard.
  - Minor Findings 6 through 10: notes added inline (F5 rolling-not-epoch, Section 4.2 cluster count, Section 11.1 Coinbase NaN audit, K1 widerband-only labeling).
  - DVOL stale-print risk note (Minor Finding 9) is structurally absent and added to Section 6.3 inline.
- Next: Phase 2 build can begin once code-reviewer confirms entry-test scaffold matches Section 11.1.
