# v6 Novelty Audit Against v5 Track C

**Date:** 2026-05-25
**Agent:** v6 Agent D
**Inputs read:** `research/v5/{00-master-plan, 03-crypto-inventory, 06-crypto-model, 07-critic}.md` (Test 4); `src/kalshi_bot_v5/crypto_features.py`; `scripts/v5/{build_v5c_orthogonality_dataset, run_v5c_orthogonality_probe, run_v5c_pivot_midband_probe, run_v5c_pivot_widerband_probe}.py`; `data/v5/v5c_{orthogonality_report, orthogonality_full_sample_report, pivot_midband_report, pivot_widerband_report}.json`.

## 1. Features tested in v5 Track C

All v5-C features were sampled AS-OF `open_time`, which for KXBTCD 1h-cadence markets equals `close_time minus 1 hour`. **The only horizon ever tested in v5-C was T-1h.** Three price bands probed at +0.005 Brier-improvement threshold. Narrow band collapsed to in-sample bootstrap (train had 1 NO); widerband train had 0 NOs (single-class drop for all 7); midband holdout with train=7 NOs / test=20 NOs is the only clean comparison.

| # | Feature | Formula | Horizon | Brier improve (narrow insample, n=200) | Brier improve (widerband insample, n=300) | Brier improve (midband holdout, n=250) | Pass +0.005 | Band tested |
|---|---|---|---|---:|---:|---:|---|---|
| F1 | f1_realized_vol_1h | stdev log-returns Coinbase 1m candles [open_time-1h, open_time] | T-1h | +8e-11 | drop-single-class | +2e-8 | FAIL | all 3 |
| F2 | f2_vwap_dev_1h | VWAP(1h Coinbase) / spot, minus 1 | T-1h | +2e-7 | drop | -2e-8 | FAIL | all 3 |
| F3 | f3_spot_futures_basis | (Deribit BTC-PERP / Coinbase spot) minus 1 | T-1h | +4e-12 | drop | +4e-9 | FAIL | all 3 |
| F4 | f4_funding_rate_1h | Deribit `interest_1h` LEVEL (latest within 8h lookback), NOT delta | T-1h | +1e-14 | drop | -3e-11 | FAIL | all 3 |
| F6 | f6_active_addr_delta | Coin Metrics BTC `AdrActCnt` 24h daily delta | T-1h daily | +1e-4 | drop | -7e-4 | FAIL | all 3 |
| F7 | f7_dxy_24h_change | Yahoo `DX-Y.NYB` daily pct change | T-1h daily | -3e-11 | drop | +6e-6 | FAIL | all 3 |
| F8 | f8_hashrate_24h_change | blockchain.info daily hash-rate pct change | T-1h daily | +2e-5 | **+0.0015** (best in v5-C) | -1e-3 | FAIL | all 3 |

V5-C1 also proposed but v5-C2 deliberately did NOT sample: F5 (orderbook imbalance, no historical AS-OF for Coinbase L2), F9 (gas), F10 (mempool fee), F11 (mempool size), F12 (S&P), F13 (BTC dominance), F14 (VIX). F5 was V5-C1's joint highest-prior candidate alongside F4.

Best result across all 7 features and 3 bands: f8_hashrate at +0.0015 in-sample on widerband; 3.3x below threshold and not multiple-comparison robust.

## 2. Per-v6-feature audit

**v6.1 Binance L5 + L20 orderbook imbalance (T-30 / T-15 / T-5)**
- v5-C TESTED DIRECTLY: **no**. Was V5-C1's F5 candidate but excluded for lack of historical AS-OF.
- v6 horizon different: yes, sub-hour vs T-1h.
- Conceptual overlap: weak with f2_vwap_dev_1h; resting depth vs executed volume.
- **Novelty: NEW.**

**v6.2 CVD (5 / 15 / 30 min)**
- v5-C TESTED DIRECTLY: **no**.
- v6 horizon different: yes, 5 to 30 min vs 1h.
- Conceptual overlap: **moderate with f2_vwap_dev_1h**. Both summarize signed trade flow over potentially overlapping windows. CVD is integrated signed volume; VWAP-dev is a price-weighted residual.
- **Novelty: NEW HORIZON ONLY + refined statistic.** Residualize against f2-equivalent.

**v6.3 Deribit 25-delta risk reversal (T-30 / T-15 / T-5)**
- v5-C TESTED DIRECTLY: **no**.
- v6 horizon different: yes.
- Conceptual overlap: weak with f3_spot_futures_basis. Both encode derivative term structure but measure different objects (IV asymmetry vs price gap; distribution moment vs level).
- **Novelty: NEW.** Options layer was never sampled in v5-C.

**v6.4 Funding rate DELTA (1h or 4h change)**
- v5-C TESTED DIRECTLY: **partial: the LEVEL was tested, NOT the delta**. v5-C's f4 reads `interest_1h` as a level at T-1h.
- v6 horizon different: yes, sub-hour, AND first-difference transformation.
- Conceptual overlap: **same data stream (Deribit BTC-PERP funding history)**, different transformation. Delta carries trajectory the level does not; two markets at same level / different deltas have different posteriors.
- **Novelty: NEW HORIZON ONLY + new transformation.** Methodology must residualize delta against level if both enter.

**v6.5 Sub-hour horizons (T-30 / T-15 / T-5)**
- v5-C TESTED DIRECTLY: **no**. v5-C only sampled T-1h. v5 critic Test 4a explicitly flagged T-15 / T-5 as untested; V5-C2 Section 6.3 documents the skip and kill-early rationale.
- **Novelty: NEW.** Exactly the pivot v5 critic flagged. Caveat: critic's skip rationale was that at T-5 the Kalshi mid is near-deterministic; v6 must justify sub-hour edge against that.

**v6.6 Kalshi own orderbook (spread, depth)**
- v5-C TESTED DIRECTLY: **no**. v5-C used only `last_price_dollars`. v5 critic Test 2c flagged this as the data-layer gap on Track B.
- **Novelty: NEW.** Forward-recording only.

## 3. Red flags

- **CVD vs funding level**: partial overlap. CVD = realized aggressive-trade direction; funding = perp-vs-spot premium. Co-move (sustained CVD-positive raises funding) but lead/lag and layer differ. Predicted rho(CVD_1h, funding_level) positive but under 0.5; rho(CVD_5min, funding_level) near 0.
- **OB imbalance vs VWAP dev**: different book layers (standing depth vs executed trades). Diverge under iceberg or thin offers. Keep both.
- **Options skew vs spot-futures basis**: different objects (IV asymmetry shape vs price-gap level). Co-move in stress but not identical. Residualize if both entered.
- **Funding delta vs funding level**: same stream, different statistic. Delta is informative when level is at its mean. NOT a re-test; residualize.

## 4. Adversarial reading

Greediest extension: all crypto microstructure features at any horizon are already priced into the Kalshi mid because professional MMs (Wintermute, Jump, GSR, Jane Street, IMC per V5-C2 Section 8) run identical models on paid BRTI feeds with sub-millisecond infrastructure. Retail at $32 with free-tier data has no edge anywhere on the microstructure spectrum.

Defensible from v5 evidence? **Partially.** v5-C evidence supports the narrower claim: at T-1h with 7 free-tier hourly-resolution features, 0 clear +0.005 across three bands. v5-C did NOT test sub-hour, options-derived, or L2 imbalance.

Where greedy HOLDS: at narrow [0.70, 0.95] yes_rate 0.98, Brier headroom is bounded above at roughly +0.001 even with a perfect feature. v6 sub-hour at narrow hits the same ceiling. Midband is the only regime with sufficient NO-density.

Where greedy FAILS: V5-C1 pre-registered F5 (OB imbalance) as one of two highest-prior candidates and v5-C2 could not test it. Options layer never touched. Sub-hour was an explicit kill-early skip, not a tested-and-failed claim.

Assessment: greedy reading is NOT defensible categorically but IS a high prior on v6's modal outcome (the v6 plan itself sets P(CONFIRMED_NULL) = 70%). Kill-early test: if ANY of OB imbalance, sub-hour CVD, or options skew clears +0.005 Brier on midband at T-15, greedy falls. If all fail at midband T-15, v5-C extends to v6 and the microstructure frontier closes.

## 5. Verdict

**v6 feature set is genuinely new and orthogonal to v5-C's tested universe.** Five v6 features (orderbook imbalance, CVD, options skew, sub-hour horizons, Kalshi own book) have no v5-C counterpart along the dimensions that matter (data source, transformation, horizon). The sixth (funding rate delta) shares funding-rate data with v5-C's f4 but is a distinct transformation at a distinct horizon; retain it and residualize against the level.

v6 is NOT a re-test in disguise. Drop nothing as redundant. Two Phase 1.5 methodology asks: (a) compute the v6 pairwise feature correlation matrix before locking the orthogonality probe; (b) when funding level and funding delta are both in scope, enter level first and require delta to clear orthogonality net of the level. v6 should otherwise proceed.
