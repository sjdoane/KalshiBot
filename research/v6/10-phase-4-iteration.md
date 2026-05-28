# v6 Phase 4: Iteration on Findings

**Date:** 2026-05-25
**Status:** Phase 3 critic exhausted retrospective salvages. Phase 4 documents non-retrospective options and confirms NULL closure.

## What Phase 4 considered

Per operator standing instruction "do not give up before all angles attacked," Phase 4 explicitly evaluated all in-session iteration options for the K1 NULL.

The Phase 3 critic ran five retrospective salvages BEFORE writing the verdict:

| Salvage | Approach | Result |
|---|---|---|
| Conditional F1 fresh-mid | `cvd_30_when_fresh` on full T-30 orth | +0.00160 (FAIL +0.005) |
| F4 T-15 midband subset | drift-defined-only, midband | +0.01162 (n=40) but bootstrap CI [-0.005, +0.030] (FAIL sample-guard) |
| Multivariate LGBM joint | mid + 8 features, LGBM-vs-LGBM | +0.00971 point estimate, bootstrap CI [-0.035, +0.059] (FAIL CI) |
| Combined-band univariate | F1 on full band [0.05, 0.95] T-30 | +0.00061 (FAIL +0.005) |
| Regime-restricted F1 | post-Aug-2025 T-30 midband | -0.00130 (NEGATIVE, regime-flatter exposed) |

Every retrospective angle the critic was able to test in-session FAILED. The remaining recommended salvages are:

- **S1**: prospective F1 fresh-mid collection (60-90 days, cost 0, prior 25%). Forward-only.
- **S2**: Kalshi-internal microstructure expansion via /markets snapshots (1-2 weeks build, cost <$1, prior 15%). Forward-only.

Neither S1 nor S2 can be evaluated within this session. They are FUTURE-PROSPECTIVE candidates.

## What Phase 4 did NOT attempt (and why)

The critic's Test 10 listed four "NOT recommended" salvages with reasons. Phase 4 honors those:

- **Different horizons (T-45, T-60)**: v5-C tested T-1h null. T-45/T-60 interpolate between v5 null and v6 null with no fresh mechanism. Re-running them would be a third bite per methodology Section 7 of v1's original lock.
- **LightGBM nonlinear with different hyperparams**: critic ran fair LGBM-vs-LGBM joint; bootstrap CI straddles zero. Sweeping hyperparams to try to lift it would be post-hoc tuning forbidden by methodology Section 7.
- **Contract-day fixed effects**: critic's regime-restricted Test 9.5.1 showed F1 lift goes NEGATIVE under regime control. Day-effect tests would amplify, not solve, the regime-shift issue.
- **Percentile-rank decision rule**: K1 killed before any decision rule; cannot rescue via decision rule when no feature has Brier signal.

## What Phase 4 commits to

1. **Honor K1 NULL.** The Phase 2 verdict reproduces exactly, regime control STRENGTHENS the NULL, every in-session salvage failed. v6 closes as a K1 NULL alongside v5-C.

2. **Document salvages S1 and S2** in the FINAL-VERDICT.md as future-work items. The operator can elect to wire S1 as a side-output of v1's existing logging (zero capital risk, zero infrastructure build) for 60-90 day prospective evaluation. S2 requires 1-2 weeks of build effort.

3. **Preserve v6 artifacts** as reference. The `data/v6/v6_master.parquet` (3688 rows, 14 features) is the cleanest retrospective Kalshi-internal microstructure dataset assembled. The build / orthogonality / critic scripts are reusable.

4. **Update CLAUDE.md, project_kalshi.md, MEMORY.md** to reflect Round 12 (v6 NULL).

5. **Do not extend the v6 budget** for further retrospective work. Net spend has been ~$2 to $3 LLM (well under cap), $0 external. The diminishing marginal value of additional retrospective testing in v6 is below the cost of triggering false-positive bias.

## Key diagnostics flagged for future rounds

The critic surfaced three things that future v7+ work must internalize:

### D1: Regime shift in midband KXBTCD YES rate (Finding 9.5.1)

KXBTCD-1h midband [0.55, 0.80] yes_rate dropped from 0.85 to 0.95 (Dec-2024 through Oct-2025) to 0.42 to 0.62 (Nov-2025 through Mar-2026). Any future train/test split that crosses Nov-2025 will have a distribution shift between train and test that flatters in-sample lifts. Future builds should regime-control via:
- Restrict train to most-recent N months (rolling window).
- Add a regime-indicator feature.
- Block by month or quarter when bootstrap-resampling.

### D2: Funding-delta cache-edge artifact (Finding 8.1)

929 of 3688 rows (25%) had `funding_rate_delta_4h_at_t` numerically equal to `funding_rate_level_at_t` due to `asof_lookup` returning 0.0 at the Deribit cache start boundary. Did not flip v6's verdict because funding-delta has no signal, but future builds using Deribit interest_1h must patch `asof_lookup` to return NaN at cache boundaries.

### D3: Brier baseline interpretation (Finding 7.1)

Methodology Section 3.1 baseline `logit on (mid)` returned Brier 0.27971 on midband T-30, but identity predictor (predict = mid) had Brier 0.21667. Logit on (mid) under-performs identity by +0.063 because train YES rate 0.858 makes the logit predict ~0.86 for almost every test row regardless of mid input. Future builds may want to specify the baseline as identity (predict = mid) instead of logit on mid, especially when train/test class balance differs.

## Verdict

**v6 NULL is final. STAND.** No retrospective salvage in this session. S1 and S2 documented as prospective candidates for the operator's discretion. v5-C extends to sub-hour and to Kalshi-internal microstructure at our scale within free-tier data.

The honest answer to the operator's mission "find an alternative ML model trained on large outside datasets, possibly trading at a higher frequency" is: at our budget, free-tier external data does not produce a positive-edge signal beyond the Kalshi mid on KXBTCD at T-30 or T-15. Kalshi-internal microstructure shows hints of marginal signal in narrow regimes (F1 fresh-mid n=45 lift +0.0096) but does not survive operationalization or regime control. The signal-extraction frontier closes for Bitcoin-direction Kalshi markets at sub-hour horizons.

What this leaves open for future rounds:
- S1 prospective F1 fresh-mid collection (forward-only, low cost).
- S2 Kalshi-internal microstructure expansion via /markets snapshots (forward-only, mid cost).
- Cross-asset Kalshi internal microstructure on non-crypto series (e.g., KXNFLGAME at T-N minute resolution, when v1's existing data path exposes /historical/trades for those tickers).
- the-odds-api paid tier ($30/mo) for sports line-movement time-series.
- News/sentiment alignment as a Phase 2 build (was Phase 1 deprioritized due to operationalization complexity).

v1 continues running on $32 unchanged with v4-H denylist and v5-A SHIP-shadow-mode pending operator wire.
