# Project Kalshi v6: Final Verdict

**Date:** 2026-05-25
**Author:** Claude (orchestrator)
**Authorization:** Operator instruction 2026-05-25: research alternative ML models trained on large outside datasets, possibly trading at higher frequency than v1's 15-min loop. Operator listed 5 candidate angles; orchestrator-recommended angle 3 (crypto microstructure at sub-hour horizons) selected. Operator approved one-time $30 to $60 external-data spend.
**Status:** v6 complete. **CONFIRMED NULL at Phase 2 Stage 2B (K1 kill condition).**

## Verdict in one paragraph

v6 closed cleanly as **K1 NULL**: zero candidate features cleared the locked +0.005 Brier improvement orthogonality threshold on midband [0.55, 0.80] holdout at either T-30 or T-15 horizon. Best lift was kalshi_cvd_30 at +0.00214 (less than half the threshold). The Phase 3 adversarial critic reproduced the K1 verdict to 5 decimal places, ran five retrospective salvages (conditional F1 fresh-mid, F4 T-15 midband subset, multivariate LGBM joint, combined-band univariate, regime-restricted F1) and all FAILED. One critic unprompted finding (D1, train/orth regime shift) showed the F1 lift was FLATTERED by a Kalshi market regime change in late-2025; regime-controlled F1 lift goes negative (-0.00130). K1 NULL is STRONGER under regime control. Two prospective salvages (S1 F1 fresh-mid forward collection over 60-90 days, S2 /markets snapshot recording for 1-2 weeks) are documented as forward-work candidates but cannot be tested in this session.

v6 is the SECOND crypto microstructure null in Project Kalshi history (after v5-C). The cumulative evidence: free-tier external data plus Kalshi-internal taker-flow at T-1h (v5-C) AND T-30/T-15 (v6) does not produce signal beyond the Kalshi mid for KXBTCD-1h Bitcoin direction contracts. v1 continues running unchanged on $32.

## The five numbers that matter

| Number | Value | Meaning |
|---|---|---|
| Best Brier improvement across 14 feature-horizon combinations | **+0.00214** (kalshi_cvd_30 on midband) | 2.3x below the +0.005 threshold; no feature clears |
| Midband sample size at T-30 / T-15 | **n=971** / **n=325** | Smaller than initial estimate (10k to 30k) due to midband stratification; per Section 3.4 above 50/50/30/30 sample-size guard |
| Phase 3 critic salvages attempted in-session | **5 of 5 failed** | Conditional features, multivariate, combined-band, F4 subset, regime-restricted |
| Train vs orth YES rate (regime shift) | **0.858 vs 0.566** | Late-2025 distribution shift in midband KXBTCD; F1 lift flattered by this; regime-controlled lift is -0.00130 |
| Total LLM API spend in v6 | **~$2 to $3 of $25 cap** | Well under budget; 9 agents at modest token counts |

Supplementary context:
- v6 master dataset: 3688 rows from 2807 contracts across 2024-12 to 2026-03; cleanest retrospective Kalshi-internal microstructure dataset assembled.
- Date range starts 2024-12 not 2024-10 due to hourly KXBTCD series launch date.
- Funding-delta artifact: 25% of rows contaminated with cache-edge artifact (D2). Did not change verdict.
- The orthogonality baseline (logit on mid) is +0.063 worse than identity (predict = mid) at midband because train YES rate 0.858 makes logit predict ~0.86 nearly constantly (D3).
- F1 fresh-mid sliver (time_since_last_trade < 5 min, n=45) had per-row bootstrap CI [+0.00025, +0.02175], P(lift > 0.005) = 80% on per-row resample, but conditional feature on full orth collapses to +0.00160 and cluster-bootstrap full-F1 CI [-0.00035, +0.00546] (P > 0.005 = 4.5%).

## What v6 produced

### Negative findings (the verdict)

1. **Kalshi internal CVD at T-30 / T-15 does not beat raw mid.** Best lift +0.00214 (kalshi_cvd_30 midband), below threshold. v6's strongest signal is too small to extract through fees / decision rules.

2. **Coinbase realized vol + VWAP deviation re-tested at sub-hour horizons remains null.** v5-C tested both at T-1h and got null. v6 tests at T-30 / T-15 with finer resolution. Both still null (<1e-5 lift). Confirms v5-C extends.

3. **Deribit funding-rate DELTA does not predict KXBTCD direction at sub-hour horizons.** Genuinely new feature (vs v5-C tested level). Still null. Cluster-edge artifact found and documented (D2).

4. **Deribit DVOL delta (volatility index changes) does not predict KXBTCD direction.** Untested in v5-C. Now tested and null.

5. **Spot-futures basis DELTA does not predict KXBTCD direction.** Adjacent to v5-C's basis LEVEL. Both null.

6. **Multivariate joint signal absent.** LightGBM with all 8 external features plus mid had cluster-bootstrap CI [-0.035, +0.059]. Indistinguishable from chance.

7. **F1 (kalshi_cvd_30) has signal direction-correct in the fresh-mid (n=45) sub-regime but not operationalizable.** Conditional feature collapses on full orth. The signal is real (P(lift > 0) = 98% on per-row bootstrap) but too narrow.

### Reusable artifacts

1. **`data/v6/v6_master.parquet`** (3688 rows, 14 features) -- cleanest retrospective Kalshi-internal microstructure dataset assembled. Future rounds can rerun any analysis without re-collecting Kalshi `/historical/trades`, Coinbase 1m candles, Deribit funding, DVOL, or BTC-PERPETUAL data.

2. **`src/kalshi_bot_v6/v6_features.py`** -- production-grade feature implementations with K1b NaN guard, CVD direction verified empirically against `kxbtcd_sample_trades.parquet` (n=9446).

3. **`scripts/v6/build_v6_master.py`, `run_v6_orthogonality.py`** -- reusable Phase 2 build pattern.

4. **`tests/v6/test_v6_features.py`** -- entry tests including the methodology critic Killer-1 verification (CVD direction unit test).

5. **The Phase 1 docs** -- `02-data-feasibility.md` is the definitive free-tier data inventory for crypto microstructure on Kalshi (Binance.com US 451, tardis $350+/mo, Coinglass $29/mo as cheapest paid). `03-kalshi-crypto-profile.md` is the definitive KXBTCD spread profile (median 2c, depth 1k to 7k, median 0 trades in T-5). Any future crypto angle on Kalshi starts here.

6. **The Phase 3 critic at `09-critic.md`** -- documents the regime-shift mechanism (D1), funding-delta cache-edge artifact (D2), and the logit-vs-identity baseline interpretation (D3). All three carry forward to v7+.

## Why the operator should accept this as a complete answer

1. **The methodology was locked before any data pull.** Section 7 criteria are honored as written.
2. **The methodology critic caught one Killer (CVD sign inverted) before Phase 2 fired.** The fix was empirically verified against ground truth.
3. **The Phase 3 critic reproduced the K1 verdict to 5 decimal places.** Independent reproduction.
4. **Five in-session salvages were attempted.** All failed. Per Phase 4 section, the remaining S1 and S2 are FORWARD-PROSPECTIVE and not testable in-session.
5. **Regime control STRENGTHENS the NULL.** F1's apparent +0.00214 lift is flattered by a train-orth regime shift; regime-controlled lift is -0.00130.
6. **The total spend was ~$2 to $3 of $25 cap.** Diminishing marginal value of additional retrospective testing is below the cost of bias from continued probing.

This is a v5-C-style clean NULL at the right kill point. The orthogonality screen did exactly what it was designed to do.

## What v6 changes about the live bot

**Nothing immediate.** v6 produced no signal worth deploying. v1 continues running on $32 with v4-H denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) and v5-A Track A SHIP-shadow-mode candidate-for-wiring still pending operator decision.

**Operator-OPTIONAL future work:**

- **S1**: prospective F1 fresh-mid logging via v1's existing infrastructure. Zero capital risk, zero infrastructure build. v1's scanner records candidates with time_since_last_trade and recent-trade history; add a v6_features call to compute kalshi_cvd_30 and log alongside v1's existing decision log. After 60-90 days of accumulated fresh-mid samples (estimate 30 to 60 new observations on KXBTCD-1h), re-run the v6 orthogonality test on the augmented sample. Decision tree:
  - If F1 fresh-mid lift narrows toward +0.005 but does not clear, close v6 cleanly. Prior 75% null.
  - If it clears with robust cluster-bootstrap CI, build a v7 conditional model. Prior 25% positive.
  
- **S2**: v6 Microstructure Expansion build (1-2 weeks engineering, < $1 API spend). Add /markets snapshot recording at horizon-time, expand Kalshi-internal feature set (cvd at N=5/10, trade_size_skew, quote_imbalance from snapshots, orderbook_depth_change). Forward-record for 60-90 days, then orthogonality re-screen.

The operator may also elect to:
- Defer all crypto-microstructure work indefinitely and pivot v7 to a different category (sports line-movement time-series with paid the-odds-api $30/mo, or news/sentiment alignment).
- Close the v6 frontier entirely and treat the v6 NULL as the final word on Kalshi crypto microstructure at retail scale.

## What we have NOT yet tried (future v7 candidates, if operator wants)

Per operator standing "do not give up" instruction:

1. **Sports line-movement time-series prediction** (Phase 1 deferred): the-odds-api paid tier $30/mo unlocks historical odds, enabling a backtest of sportsbook movement leading Kalshi over 1 to 6 hour windows on game-resolution markets.

2. **News-sentiment alignment** (Phase 1 deferred): expensive APIs (X $200/mo) and alignment complexity; medium prior of operationalization.

3. **Kalshi-internal microstructure on non-crypto series**: KXNFLGAME, KXMLBGAME, KXWCGAME, KXBOXING, KXUFCFIGHT all have /historical/trades exposure. Single-event sports markets have very different microstructure profiles (longer lifetime, news-driven trade clusters) than KXBTCD-1h hourly contracts. v6's null on KXBTCD does NOT automatically extend to game-resolution markets.

4. **Agentic-retrieval LLM forecaster** (v4 Phase 4 deferred): per v4-B literature, agentic retrieval is the documented single biggest gain in LLM forecasting. v4-G2's null was on bare retrieval; full agentic with Wikipedia + sportsbook + news might clear. Cost: $5 to $10 LLM spend; build effort 4 to 6h.

5. **Cross-market consistency at scale** (v5 Phase 4 deferred): v4-D found 6/6 NFL win-total monotonicity violations correctly predicted. v4-E A2 arm +0.95pp per fire on NFL was small-sample. Could extend to KXNBAWINS, KXNHL, KXMLBALEAST ladders.

6. **Real-execution spread measurement on Kalshi**: v6 used the Agent C 2c spread approximation. Future builds with /markets-snapshot recording could measure actual spread at horizon time.

## Time budget accounting

| Phase | Wall-clock | LLM tokens (estimated) |
|---|---|---|
| Phase 1, 4 parallel agents | ~30 min | ~500k |
| Phase 1.5 methodology v1 | ~5 min | direct orch |
| Methodology critic | ~7 min | ~130k |
| Methodology v2 patches | ~5 min | direct orch |
| Phase 2 build (background) | ~30 min | ~280k |
| Phase 3 critic (background) | ~13 min | ~160k |
| Phase 4 + Phase 5 docs | ~5 min | direct orch |
| **Total** | **~95 min** | **~1.1M tokens** |

Estimated LLM spend: $2 to $3 of $25 cap. External data: $0 of $30-$60 authorized.

## v2/v3/v4/v5/v6 cumulative failure-mode comparison

| Failure mode | v6 outcome |
|---|---|
| CV leak (v2 Section 3) | PREVENTED. Chronological 60/25/15 split with 24h purge, no shuffle. |
| Feature look-ahead (v2 Section 4) | PREVENTED. All features AS-OF horizon time using `/historical/trades` with `created_time <= t`. |
| Model anchors on price (v2 Section 5; v5-B at 1000x scale) | DETECTED. The 8 external features have lift < 1e-5, indicating the Kalshi mid absorbs all the external signal at our horizons. F1's tiny lift on fresh-mid is exactly the pattern v5-B exhibited. |
| Single-entity artifact (v2 Section 6) | NOT REPRODUCED. KXBTCD-1h has no per-entity concentration. |
| False C6 comparison (v2 Section 9; v3 trap) | n/a (no v1-comparison gate; v6 is a new domain). |
| Wrong-cutoff-window (v4 Killer 4.2) | n/a (no LLM). |
| Series-prefix coverage mismatch (v3 W1) | n/a (single-series KXBTCD-1h). |
| Stale-price phantom edge (v5 Killer 2c) | PREVENTED. v6 reconstructs `kalshi_mid_at_t` from /historical/trades AS-OF, never uses post-settlement `last_price_dollars`. Methodology Section 11.1 verified. |
| Sign convention inversion (v6 methodology critic Killer 1) | CAUGHT BEFORE PHASE 2. Methodology critic identified F1 sign convention was inverted in the methodology v1 doc; pinned to empirical ground truth via unit test against `kxbtcd_sample_trades.parquet`. |
| F4 sample-selection artifact (v6 methodology critic Important 5) | CAUGHT BY METHODOLOGY CRITIC + ENGINEERED-OUT IN PHASE 2. F4 had apparent +0.10 lift on un-screened comparison; like-for-like protocol collapsed to +0.00272. K1b explicit kill condition. |
| Train/orth regime shift (D1, v6 Phase 3 critic Finding 9.5.1) | CAUGHT BY PHASE 3 CRITIC. Documented as future-build requirement (regime-control or rolling-window train). |
| Funding-delta cache-edge artifact (D2, v6 Phase 3 critic Finding 8.1) | DETECTED. 25% of rows contaminated. Did not flip verdict because funding-delta has no signal. Documented as patch requirement for any future Deribit-funding builder. |

v6 introduced ZERO new uncaught failure modes. The methodology critic caught the CVD sign inversion before Phase 2. The Phase 3 critic caught the regime shift, the funding-delta artifact, and the baseline-vs-identity interpretation. The discipline of three critic passes (plan, methodology, Phase 3) has now caught uncaught failures in v3, v4, v5, AND v6.

## Closing the v6 project

Recommended actions:

1. **Mark v6 master plan complete.** This verdict + `09-critic.md` is the project's terminal state for v6.

2. **Keep v6 artifacts in the repo** as research-mode reference. Per Section 11.1, `tests/v6/test_v6_features.py` continues to pass; the build scripts remain runnable.

3. **Update CLAUDE.md and project memory** to reflect Round 12 (v6 K1 NULL).

4. **Operator decision on S1**: wire prospective F1 fresh-mid logging as a side-output of v1? Zero capital risk, modest engineering effort. 60-90 day evaluation. OPTIONAL.

5. **Operator decision on S2**: build microstructure expansion via /markets snapshot recording? 1-2 weeks engineering, < $1 API. OPTIONAL.

6. **Cumulative project state**: v1 is the only active trading strategy. v4 Track A filter + v5 Track A sportsbook arm is the only candidate for paper deployment (shadow-mode, still pending operator wire). All ML-prediction angles have been documented null across v2, v3, v4 Track B, v5 Track B, v5 Track C, and now v6. The cumulative evidence: free-public-feature ML at retail scale on Kalshi does NOT produce monetizable edge across outcome prediction (v2-v5) OR microstructure (v6).

## Closing note

Per the operator's instruction "ensure you are not giving up before all angles attacked," v6 followed the established five-phase protocol with three critic passes. The pivot from external Binance/Coinbase microstructure to Kalshi-internal CVD was made transparent in Phase 1 synthesis with explicit operator approval; the methodology lock + critic + revisions caught one Killer before any data pull; the Phase 2 build executed cleanly; the Phase 3 critic reproduced the verdict and exhausted retrospective salvages.

The bottom line for the operator's mission: at our scale, on Kalshi's KXBTCD-1h crypto markets, with free-tier data, sub-hour microstructure features do NOT carry information beyond the Kalshi mid that survives orthogonality, fee-aware decision rules, or regime control. The only viable future-retrospective direction is to test on non-crypto series (sports) or accept that retail-scale microstructure on Kalshi is dead. The only viable prospective direction is to forward-record for 60-90 days and re-evaluate.

v1 continues running on $32 unchanged.
