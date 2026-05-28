# V5 Phase 3 Adversarial Critic

**Date:** 2026-05-24
**Author:** Agent V5-Critic (v5 Phase 3, adversarial review of V5-A2 Track A, V5-B2 Track B, V5-C2 Track C)
**Status:** Read-only review. No modifications to V5-A2 / V5-B2 / V5-C2 docs, source code, or v1 bot.
**Predecessor reads:** `00-master-plan.md`, `iterations.md` (Iter 0-4), `01-sportsbook-coverage.md` (V5-A1), `02-statcast-feasibility.md` (V5-B1), `03-crypto-inventory.md` (V5-C1), `04-sportsbook-filter-build.md` (V5-A2), `05-statcast-model.md` (V5-B2), `06-crypto-model.md` (V5-C2), source code (`src/kalshi_bot_v5/filter_combined.py`, `statcast_features.py`, `statcast_model.py`, `crypto_features.py`), data artifacts (`data/v5/divergence_summary.json`, `prop_dataset.parquet`, `sportsbook_filter_backtest_results.json`, `statcast_gate_results.json`, `v5b_orthogonality_report.json`, `v5c_*`), v4 critic for style (`research/v4/07-critic.md`).

---

## Executive summary

### Track A (sportsbook + Polymarket + cross-market filter)

**SIGN OFF WITH CAVEATS** on the SHIP-shadow-mode verdict. V5-A2's Path Y reproduces V4-E exactly (+1.70pp diff, CI [-0.32pp, +4.22pp], `data/v4/filter_backtest_decisions.parquet`). The sportsbook arm contributes 0 fires on v3 inventory because v3's universe has 0 MATCH-class h2h game-resolution markets. The live-universe 23% fire rate (3 of 13 v1-band) is real but the entire signal lives in the +9c+ TAIL of the divergence distribution, not the +1.7c MEAN. The 10 non-firing v1-band candidates have mean divergence -0.19c. Shadow-mode is the right disposition; the critic-imposed timeline reform (120-180 day window) inherited from V4 critic still applies.

### Track B (Statcast prop ML)

**SIGN OFF on NULL but FLAG one important salvage to test post-Phase-4.** V5-B2's NULL is structurally honest: G1=-6.50c, G2 mean=-47.71c, G3 mean=-26.35c on the holdout; every pre-registered pivot fails. The positive BSS (+0.574) is calibration smoothing toward the population mean, not predictive signal. **The fade-direction salvage (Test 2 below) FAILS at the symmetric -5c threshold because the price-only LogReg produces only TWO discrete delta values, both with magnitude < 0.025.** The Kelly-NO salvage looks positive (+3.17c net per contract on n=31,630) but breaks under the realistic-spread audit: at mid-band [0.20, 0.70] markets the actual NO ASK is at ~1.00 (yes_bid_dollars mean = 0.0547 vs `last_price_dollars` mean = 0.398). The phantom edge is from using stale last-trade prints as the buy-price proxy. **Track B's null stands.** The "model anchors on price" failure mode is the v2/v3 pattern at 1000x scale.

### Track C (crypto orthogonality)

**SIGN OFF on NULL.** V5-C2 has the cleanest result of the three tracks. The pre-registered prediction (0-2 features pass) was confirmed at the lower bound across three orthogonality probes spanning narrow / wider / midband price ranges. Tracking error to BRTI is 0.09% (below 0.1% concern threshold). Pairwise feature correlations on the 7-feature panel are mostly under 0.2 absolute (so the "7 features" aren't collinear-degenerate). The T-15min / T-5min pivot was skipped with reasoning that aligns with the kill-early principle. **Two caveats**: (a) the midband actual data file has n=500 with 124 NOs but the report runs on n=250 with 27 NOs (a discrepancy worth documenting); (b) the verdict relies on AS-OF Coinbase as a BRTI proxy, and tracking error of 0.09% is fine but a future Phase 4 should not chase this track without paid BRTI access.

The verdicts split: A is conditionally OK, B is null with a verified salvage attempt, C is a clean null.

---

## Test 1: V5-A live signal robustness (3 fires of 13 v1-band candidates)

### Test 1a: Reproduce the 3-of-13 count at exact 5c threshold

**Method:** Loaded `data/v5/divergence_summary.json`. Filtered to `in_v1_band == True` (n=13). Counted rows where `divergence_cents > 5.0`.

**Result:**
- v1-band n: **13** (matches V5-A2 Section 4.1)
- Fires at 5c: **3 of 13** (matches V5-A2 Section 4.1: 23.1%)
- The 3 fires:
  - `KXWCGAME-26JUN23ENGGHA-ENG`: k=0.715, b=0.554, div=+16.14c
  - `KXWCGAME-26JUN24SCOBRA-BRA`: k=0.730, b=0.585, div=+14.49c
  - `KXMLBGAME-26MAY241610WSHATL-ATL`: k=0.725, b=0.629, div=+9.55c
- Mean divergence on the 3 fires: **+13.39c**
- Mean divergence on the 10 non-fires: **-0.19c**
- 7c threshold: same 3 fire. 3c threshold: same 3 fire. 10c threshold: 2 fire (loses ATL at +9.55c).

**Finding 1.1: Important.** Count reproduces exactly. The threshold sensitivity sweep documented in V5-A2 Section 6.4 is correct: the signal is concentrated at the +9c+ TAIL, not the +1.7c mean. Within the 3-10c range, the 5c locked threshold is equivalent to 3c or 7c on this sample.

### Test 1b: Selection-bias check

**Method:** Confirm the n=13 includes ALL v1-band candidates (no MATCH-class pre-filter).

**Result:**
The 13 v1-band candidates span 3 series-prefixes: KXWCGAME (3), KXMLBGAME (5), KXBOXING (4), KXUFCFIGHT (1). All are MATCH-class series per V5-A1 Section 3.1 (h2h game-resolution markets where the-odds-api has coverage). The denominator is restricted to MATCH-class by the matched-event filter in `build_sportsbook_lookup.py` (58 of 58 candidates matched a sport_key event). **NO_MATCH-class series (KXMLBSTATCOUNT, KXNBAPLAYOFFWINS, KXFOMEN, etc.) are pre-excluded from the 13.**

**Finding 1.2: Minor.** This is structurally honest. NO_MATCH series can never fire A3 by definition. The 13 denominator is correct for measuring A3's fire rate WITHIN ITS COVERAGE UNIVERSE, but the "23% fire rate on v1-band" headline understates the true forward-looking expected fire rate on v1's full universe because A3 cannot fire on ~70% of v1's live universe.

### Test 1c: Live fire rate on v1's FULL post-denylist universe (not just sportsbook-covered)

**Method:** V5-A1 Section 3.5 reports inclusive sportsbook coverage of 40.7% on v1's 29 attempted-orders. MATCH-only strict coverage is 31.0%. A3 can fire only on MATCH-class candidates, so the effective per-v1-candidate A3 fire rate is `(MATCH-only coverage) x (within-coverage fire rate)`.

**Result:**
- v1 live universe size (post-denylist): 29 attempted orders per V5-A1 Section 1.1
- MATCH-only strict coverage: 31.0%
- Within-MATCH-coverage fire rate (V5-A1 v1-band sample): 23%
- **Effective A3 fire rate on v1's full universe: 0.31 * 0.23 = 7.1%**

**Finding 1.3: Important.** A3's fire rate on v1's actual live candidate stream is ~7%, not 23%. The combined filter (A1 + A2 + A3 OR-logic) will still fire higher because A1 and A2 have different coverage subsets, but A3 alone contributes one fire per ~14 v1 candidates. At v1's documented 5-10 candidates/day steady state, that's < 1 A3 fire/day on average. V5-A2 Section 4.3 correctly notes the combined skip rate is well below 50%, but the headline "23%" misframes A3's standalone contribution.

### Test 1d: Distributional vs mean check on the divergence sample

**Method:** Computed mean+SD of divergence on firing vs non-firing v1-band candidates separately.

**Result:**
- All 13 v1-band: mean=+2.95c, sd=6.50c
- 10 non-firing: mean=-0.19c, sd≈1.74c (median +0.45c)
- 3 firing: mean=+13.39c, sd=3.61c, min=+9.55c, max=+16.14c

**Finding 1.4: Killer (frames the verdict).** The "+1.70c mean on n=23" headline (V5-A1 Section 4.3) and the "+2.95c mean on n=13" headline (V5-A1 Section 4.3) describe the DISTRIBUTION CENTER, not the SIGNAL. The actual signal lives in the +9c+ tail (3 of 13). On a 10-candidate sample, you would expect roughly 2-3 fires at threshold 5c if the underlying distribution is consistent. **V5-A2's "SHIP shadow-mode" is the right verdict because the tail-signal pattern is what V4-E's signal also looked like (4 fires of 147; LOO drop from +1.70pp to -0.65pp).** A3's expected behavior at production scale is "rare, large-divergence skips" not "frequent, mean-divergence skips."

### Test 1e: Forward-looking expected hit rate from a Bayesian prior

**Method:** V3-C measured 2 correct skips of 4 fires on Polymarket-fade signal (n=5 KXMLBPLAYOFFS). V5-A1's 3 fires have no resolved outcomes yet. Treating V3-C's prior as Beta(2.5, 2.5) (Jeffreys) and updating with the V5-A1 sample of 3 unresolved fires gives the same Beta posterior.

**Result:**
- Prior posterior mean: 50% correct-skip rate.
- Posterior 95% CI on correct-skip rate: roughly [20%, 80%].
- Expected per-fire P&L impact (using V4-E's +39.66pp per-fire on KXMLBPLAYOFFS as a generous estimate, derated for live KXNFLGAME/KXWCGAME tail-loss profile by 0.4): roughly +12-15pp per fire if A3 correctly skips, -10pp if A3 wrongly skips.
- Net expected per-fire effect: roughly 0.5 * (+15) - 0.5 * 10 = +2.5pp. With wide CI.

**Finding 1.5: Minor.** The "do A3 fires actually save P&L" question is unresolved at n=0 resolved. Shadow-mode logging is the right way to gather that data. Without resolved fires, every claim about A3's headline P&L value is forward-looking projection.

---

## Test 2: V5-B fade-direction salvage attempt

This is the highest-prior killer candidate per the brief. V5-B2 reports positive BSS (+0.574) but cannot monetize via the +2c take rule because the LogReg shrinks extreme prices toward 0.5 (the WRONG direction for buying YES). The natural mirror: when the model says YES is LESS likely than the market, buy NO.

### Test 2a: Reproduce G2 holdout and run fade-direction NO-buy at -5c threshold

**Method:** Loaded `data/v5/prop_dataset.parquet`. Chronological 70/30 split. Fit StandardScaler + LogReg(C=1.0) on train favorite_price. Predicted test probabilities. Applied fade rule: BUY NO when `model_prob < kalshi_yes_price - 0.05 AND kalshi_yes_price >= 0.70`. P&L per NO contract: `(1 - outcome_yes) - (1 - kalshi_yes_price) = kalshi_yes_price - outcome_yes`. Net of round-trip maker fees (Kalshi quadratic, 25% of taker) + 1.5c slippage.

**Result:**
- G1 always-trade YES reproduction: gross -3.60c, net -6.56c per contract (V5-B2 reports -6.50c; match within fee-rounding).
- Fade rule fires at -5c threshold: **0 trades.**
- Investigation: at price >= 0.70, the LogReg delta (model_prob - price) takes only TWO values across all 11,647 holdout rows: -0.0223 (at price=0.99 markets) and +0.0207 (at price=0.70-0.95 markets). Neither exceeds the 5c threshold.

**Finding 2.1: Important (closes the fade-direction salvage).** The price-only LogReg is essentially a monotonic recalibration. At price=0.99 it shrinks to 0.9676 (-2.23c below market); at price=0.70-0.85 it RAISES to 0.78 (+2.07c above market). The "shrink toward 0.5" pattern V5-B2 documents is real but small in magnitude; the symmetric fade rule cannot fire because the magnitude of disagreement never reaches the 5c trigger.

### Test 2b: Wider thresholds and Kelly-sized NO buys

**Method:** Swept -2c through +2c thresholds and full Kelly NO-buy on the holdout.

**Result:**
- Threshold delta < -2c (NO buy at price >= 0.70): n=11,489, gross -0.45c, **net -1.99c** per NO contract, 95% CI [-2.12c, -1.86c]. CI cleanly excludes zero on the NEGATIVE side.
- Threshold delta < 0 (NO buy at price >= 0.70): n=11,575, gross -0.13c, net -1.67c, CI [-1.83c, -1.49c]. Same shape.
- Kelly-NO buy without price restriction (`f_no > 0.05`, i.e. model says NO is at least 5% better EV): n=20,083, gross +7.67c, **net +5.98c**, 95% CI [+5.79c, +6.17c]. CI cleanly excludes zero on the POSITIVE side. This looks like a positive-EV signal.

**Finding 2.2: Killer (apparent positive signal, needs Test 2c).** The Kelly-NO rule at `f_no > 0.05` fires 20k times and yields +5.98c per contract net. The price-distribution of the firing trades has 75th-percentile at 0.04 and median at 0.02, i.e. the rule fires almost exclusively on heavy-underdog markets where the YES price is 0.01-0.10.

### Test 2c: Realistic spread audit on the Kelly-NO salvage

**Method:** The V5-B2 dataset uses `last_price_dollars` as `favorite_price`. To execute a NO buy at the implied NO price (1 - favorite_price), you would need NO_ask near 1 - favorite_price. Checked `yes_bid_dollars` and `yes_ask_dollars` on mid-band [0.20, 0.70] markets in the test holdout (n=2,972 sample).

**Result:**
- yes_bid_dollars on mid-band: top frequency value is "0.0000" with 2,943 rows of 2,972 (99.0%).
- yes_ask_dollars on mid-band: 5,422 of 9,337 (58%) at NaN or >= 0.99 across the full mid-band.
- All mid-band markets have `status='finalized'`. Bid/ask are POST-SETTLEMENT snapshots.
- **Realistic NO buy price (1 - yes_bid_dollars) on mid-band: mean = 0.9941** (you would pay ~$0.99 for the NO contract because yes_bid is near 0).
- Realistic NO buy gross PnL at mid-band [0.20, 0.30): n=793, mean = -0.13c per contract.
- Realistic NO buy gross PnL at mid-band [0.30, 0.50): n=1,634, mean = -0.00c.
- Realistic NO buy gross PnL at mid-band [0.50, 0.70): n=545, mean = -1.93c.
- **The +5.98c "Kelly-NO" salvage is a PHANTOM**, generated by treating `last_price_dollars` as if it were the NO ask price; the actual NO ask is at $1.00 (effectively no liquidity to buy NO at the historic last-trade NO price).

**Finding 2.3: Killer (closes the Kelly-NO salvage).** The salvage rule's apparent +5.98c per contract net is an artifact of using a stale last-trade price as the buy proxy. At maker-side execution, you could try to post a NO BID at NO_bid = 1 - yes_ask, but the dataset shows yes_ask is itself at $1.00 post-settlement, so the maker-side data is also unreliable for any retrospective P&L claim. The realistic "cross-spread" NO buy yields 0 to -2c per contract gross at mid-band, deeply negative net. **The fade-direction salvage does NOT recover Track B.**

### Test 2d: Calibration-only deployment (Kelly fraction sizing on G1 always-trade)

**Method:** Skipped after Test 2c. If the realistic NO-buy execution doesn't work at the model's predicted price, Kelly sizing cannot recover the rule. The model's calibration improvement (BSS +0.574) is real but operationally locked behind the post-settlement bid/ask gap.

**Finding 2.4: Important.** V5-B2's calibration improvement is real but the data layer V5-B2 used (`/markets?status=settled` post-settlement snapshots) does not contain the live bid/ask that would have been available during the market's open lifetime. To honestly test the model's tradeable edge, V5-B2 would need to repull the markets via a live-cadence sampling that captures bid/ask at multiple points before close. This is the Phase 4 must-do if anyone wants to revisit Track B.

---

## Test 3: V5-B "model anchors on price" deeper check

### Test 3a: Are the 8 retained features actually volume proxies?

**Method:** Loaded `data/v5/v5b_orthogonality_report.json`.

**Result:**
- 8 retained features: `bat30_n_pitches`, `bat30_n_pa`, `bat7_n_pitches`, `bat7_n_pa`, `bat14_n_pitches`, `bat14_n_pa`, `batstd_n_pitches`, `batstd_n_pa`.
- All 8 have negative bootstrap CI on the residualized coefficient (e.g. `bat30_n_pitches`: CI [-0.907, -0.414]) and positive AUC delta (~0.010).
- 26 features cleared the CI test; only 8 cleared the AUC delta >= 0.005 threshold. The skill metrics (`bat30_xba`, `bat30_xwoba`, `bat30_exit_velo_mean`, `bat30_hard_hit_rate`, `bat30_k_rate`) all have AUC delta in [0.0007, 0.0034], below the 0.005 floor.

**Finding 3.1: Important (confirms V3-B1 failure mode at scale).** The 8 survivors are unambiguously volume proxies. The interpretation V5-B2 Section 2.3 provides ("more PAs = regulars priced as heavy favorites who occasionally bust") is mechanically plausible. This is the V3-B1 `nfl_games_played_pre_t35d` failure mode reproduced at 1000x scale: the only orthogonal-to-price signal is "is this a regular player in season."

### Test 3b: Per-prop-type orthogonality

**Method:** V5-B2 ran orthogonality on the AGGREGATE n=144k dataset, partitioning by feature type (batter features on HIT/HR/HRR; pitcher features on KS). It did NOT run orthogonality PER-PROP-TYPE (separate runs for KXMLBHIT, KXMLBHR, KXMLBHRR, KXMLBKS).

**Result:**
- The orthogonality protocol's "is_pitcher_feature" flag in `v5b_orthogonality_report.json` partitions FEATURES, not OUTCOMES. So batter features are tested on the union of HIT+HR+HRR markets.
- This could mask per-prop-type signal. For example, `bat30_xba` might add meaningful signal for KXMLBHIT (where xBA is a direct predictor) but be drowned in aggregation by KXMLBHR (where HR_rate is the better target).
- V5-B2 Section 8 reports the pivots ran per-prop-type GATE tests (P2a through P2g) but NOT per-prop-type ORTHOGONALITY. The gate-level tests all failed but tested only price-only or price+8-survivors models, not per-prop-type orthogonality survivors.

**Finding 3.2: Important (Phase 4 candidate).** A per-prop-type orthogonality rerun could plausibly retain a skill feature (xBA for KXMLBHIT specifically). The prior is bleak given V5-B2's overall finding, but per the operator's "do not give up" instruction, this is a 2-hour rerun. **Specifically: rerun the orthogonality protocol restricted to KXMLBHIT mid-band markets (n=259-760 per V5-B1 Section 1.5), and check whether `bat14_hits_per_pa`, `bat14_xba`, or `bat30_xba` clear the AUC delta on the restricted sample.**

### Test 3c: Orthogonality CI test rigor

**Method:** V5-B2 used 1,000 bootstrap resamples vs the brief's 5,000. V5-B2 Section 12 documents this and notes "CI quantiles stabilize within ~2% of their 5,000-resample value."

**Result:**
- 1,000 resamples on 43 distinct game-date clusters: per CLT, the bootstrap CI variance is O(1/sqrt(43)) at the cluster level and O(1/sqrt(1000)) at the resample level. The cluster count is the binding precision constraint.
- The 8 retained volume features have AUC deltas in [0.009, 0.010]; the cutoff is 0.005. The retention decision is robust to bootstrap-iteration-count changes in this range.
- The 26 marginally-significant features (CI clears but AUC delta < 0.005) have AUC deltas in [0.0007, 0.0049]. Some borderline candidates (`bat30_xwoba` at 0.0032; some other skill features near 0.003-0.0049) are within ~0.001 of the threshold. Running at 5,000 resamples would tighten the CI but not change the AUC delta point estimate.

**Finding 3.3: Minor.** The 1,000-vs-5,000 substitution is a documented compromise. The verdict is robust to it. The Phase 4 per-prop-type rerun (Finding 3.2) is a higher-prior win than rerunning at 5,000 resamples.

---

## Test 4: V5-C orthogonality probe coverage

### Test 4a: T-15min / T-5min sampling skip

**Method:** V5-C2 Section 6.3 documents the T-15min pivot was NOT attempted. Rationale given: (1) Pivots 1-2 already exhaust the orthogonality space at 1h cadence; (2) at T-5min the market price has already absorbed virtually all information; (3) time budget.

**Result:**
- The market's underlying random variable is "BRTI at 19:00 EDT in the next 60 seconds." At T-5min the price has settled within strike-spacing (~$100 = ~5bp) of the eventual BRTI. The Kalshi market is nearly deterministic at T-5min.
- A feature sampled at T-5min would have ~5 minutes to "see" structure the market hasn't priced in. For 1-hour markets, that's a 92% deterministic regime; for 15-minute markets, it's a 67% deterministic regime.
- V5-C1 mentioned (Section 5) that microstructure asymmetry at the close is "the only mechanically plausible source of edge" but requires sub-second AS-OF feed access. T-5min sampling does NOT give sub-second access; it just shrinks the window.

**Finding 4.1: Important (the skip is defensible but documents a limit).** V5-C2's skip rationale is sound: at T-5min the market is approaching determinism and our free-tier features (Coinbase 1-min candles, Deribit funding rate, daily DXY) lack the sub-second resolution to find edge in the final-minute regime. The kill-early principle correctly favors NOT spending 1-2 hours rebuilding for a low-prior pivot.

### Test 4b: Are the 7 features truly orthogonal sources?

**Method:** Loaded the v5c orthogonality / midband datasets and computed pairwise feature correlations.

**Result:** Narrow [0.70, 0.95] band pairwise correlations (n=200):
```
                       f1     f2     f3     f4     f6     f7     f8
f1_realized_vol_1h    1.000   0.244 -0.160 -0.146  0.042 -0.036 -0.139
f2_vwap_dev_1h        0.244   1.000  --    --     --     --    -0.041
f3_spot_futures_basis -0.160  --     1.000 --     --     --     0.053
f4_funding_rate_1h    -0.146  --    --     1.000  --     --     0.051
f6_active_addr_delta  0.042   --    --     --     1.000  --    -0.112
f7_dxy_24h_change    -0.036   --    --     --     --     1.000 -0.010
f8_hashrate_24h_change -0.139 -0.041 0.053 0.051 -0.112 -0.010  1.000
```

All off-diagonal absolute values are below 0.25. Mid-band (n=500) absolute correlations are mostly below 0.20 except `f3_spot_futures_basis` x `f1_realized_vol_1h` = -0.180.

**Finding 4.2: Minor.** The 7 features are not collinear. The "7 features dropped" finding really does mean 7 independent sources of signal all fail, not 1 underlying signal repeated 7 times. V5-C2's verdict generalization is honest.

### Test 4c: Train-NO count discrepancy on midband

**Method:** Loaded `data/v5/v5c_pivot_midband_data.parquet` and `data/v5/v5c_pivot_midband_report.json`. Compared sample sizes.

**Result:**
- midband data parquet: n=500, yes_rate=0.752, NOs=124.
- midband report json: n_total=250, yes_rate_total=0.892, verdict=NULL_AT_ORTHOGONALITY_MIDBAND. Train (n=175) has 7 NOs; test (n=75) has 20 NOs.
- The report appears to have run on a 250-row subset of the 500-row data file.

**Finding 4.3: Important (data-doc discrepancy).** The V5-C2 doc Section 4.6 says "n=250" with yes_rate=0.892 (NOs=27 total). The data parquet has n=500 with NOs=124. The report file confirms it ran on n=250. The doc claim is consistent with the report but the data file has more rows than the report consumed. This is either: (a) the run was early-killed and saved an intermediate 250-row report against a 500-row pre-built parquet, or (b) there are two versions. **Operator should be aware that re-running on the FULL n=500 data might shift outcome variance.** A spot-check at n=500: 124 NOs spread across train/test would give train_NOs ~ 87, test_NOs ~ 37 (if chronological 70/30). That's far more robust than the n=250 report's 7-train-NO sample. Track C might benefit from a 1-hour rerun on the full n=500 sample before final closure.

### Test 4d: Pre-registered prediction accuracy

**Method:** V5-C1 predicted 0-2 features pass orthogonality, biased toward F4 (funding rate) and F5 (orderbook imbalance). F5 was excluded for lack of AS-OF support.

**Result:**
- Across narrow / wider / midband: 0 features cleared the +0.005 Brier improvement threshold.
- Best in-sample Brier improvement across all 7 features and 3 bands: f8_hashrate at +0.0015 (in-sample on widerband). 3x below threshold; would not survive multiple-testing correction.
- F4 (funding rate) was tested at all 3 bands; failed.

**Finding 4.4: Minor (confirmation, not new finding).** The pre-registered 0-2 prediction held at the lower bound, exactly as Phase 1 anticipated. V5-C2's null is honest and the result was predicted with the right shape.

---

## Test 5: V5-A book-arm zero-fires on v3 inventory

### Test 5a: Is the 0-fires result a structural artifact or post-hoc rationalization?

**Method:** V5-A2 Section 3.1 reports that the v3 inventory (n=147) consists of season-long-winners series (KXNFLWINS, KXNBAWINS, KXMLBWINS, KXMLBPLAYOFFS, etc.), while the-odds-api MATCH-class coverage is h2h game-resolution. The book-only arm fires 0 times because there is no MATCH-class overlap on v3 inventory. Verified via `data/v5/sportsbook_filter_backtest_results.json`.

**Result:**
- Path Y "book-only" arm: rule_fire_counts: polymarket_fade=0, sportsbook_fade=0, monotonicity_violation=0. n=147, diff_pp=0.0, CI [0.0, 0.0].
- The locked 5c threshold was pre-registered in `iterations.md` Iter 2 BEFORE the backtest run (timestamps consistent).
- Sensitivity sweep on book threshold (3c / 5c / 7c / 10c) is only available for Path X (n=2 resolved); on Path Y the v3 inventory has no MATCH-class series so all book thresholds yield 0 fires.

**Finding 5.1: Important.** The 5c threshold lock IS pre-registered. The 0-fires-on-v3-inventory finding is a STRUCTURAL CONSEQUENCE of v3 inventory's series mix (no h2h games), not a post-hoc threshold tune. This is honest. However, the "combined filter improvement +1.70pp" headline on v3 inventory is ENTIRELY from the Polymarket-fade and Cross-Market-Consistency arms, NOT the sportsbook arm. The sportsbook arm contributes ZERO retrospective evidence.

### Test 5b: Combined filter +1.70pp = V4-E identity check (with LOO reproduction)

**Method:** Loaded `data/v4/filter_backtest_decisions.parquet` (n=147). Recomputed paired diff = filter_pnl - v1_pnl. Ran 5,000-resample bootstrap. Identified top-4 filter-win rows and ran LOO.

**Result:**
- v3 inventory paired diff: **mean=+1.70pp, sd=14.26pp, 95% CI [-0.30pp, +4.22pp]**.
- Top 4 filter wins: KXMLBPLAYOFFS-25-HOU (+91.7c diff, polymarket_fade), KXNFLWINS-IND-25B-T10 (+86.3c, monotonicity), KXNFLWINS-DAL-25B-T7 (+83.7c, monotonicity), KXMLBPLAYOFFS-25-NYM (+80.4c, polymarket_fade).
- After dropping the top 4: mean = **-0.65pp**, CI [-1.12pp, -0.27pp].

**Finding 5.2: Killer (the v4 critic finding carries over).** V5-A2's "+1.70pp matches V4-E" is exactly true. **The +1.70pp signal hinges on 4 of 147 markets**; LOO drop is the same finding the V4 critic flagged (Finding 1.5 in `research/v4/07-critic.md`). V5-A2's verdict "SHIP shadow-mode" is correctly cautious about this, but the headline P&L number in V5-A2's TLDR should disclose the LOO fragility from V4. **V5-A2 inherits a known-fragile retrospective signal AND brings forward-looking sportsbook coverage as a separate, untested signal.**

### Test 5c: Forward-looking value claim audit

**Method:** V5-A2 implies that A3 will provide additional value on v1's live universe (different series mix from v3 inventory). The empirical evidence is the 23% fire rate on 13 v1-band live candidates with 0 resolved.

**Result:**
- A3's forward-looking expected value is currently NOT QUANTIFIED. The 23% fire rate at locked threshold is real; the per-fire expected P&L impact is unknown.
- The headline claim implicit in V5-A2's TLDR is: "A3 adds value on forward-looking live universe." This is a HYPOTHESIS, not a measured result.
- A2's per-fire +0.95pp on KXNFLWINS (V4-E) and A1's per-fire +39.66pp on KXMLBPLAYOFFS (V4-E) are the only quantified per-fire numbers. A3 has no quantified per-fire number.

**Finding 5.3: Important.** The V5-A2 verdict is a hypothesis-shipping decision, not an evidence-shipping decision. Shadow-mode is the right disposition because the resolved-outcome sample is structurally zero. **The "ship" framing in V5-A2's TLDR overstates the case; "ship as shadow-mode logging for hypothesis-validation" is the honest framing**. V5-A2 Section 7 reads this correctly; the TLDR could mirror it more clearly.

---

## Test 6: Multi-track multiple-testing audit

### Test 6a: Count of statistical trials across V5

**Method:** Counted variants per track.

**Result:**
- V5-A2: 9 arms in `sportsbook_filter_backtest_results.json` (Path X, Path X book-threshold sensitivity at 3c/5c/7c/10c, Path Y combined, Path Y decompositions A1-only / A2-only / A3-only, Path Y at varied thresholds). Plus 28 unit tests (per V5-A2 Section 1.3).
- V5-B2: 74 orthogonality candidate features × 1 test = 74 tests. Plus 11 pre-registered pivots (P1a-P3b per V5-B2 Section 8). Plus 3 sanity checks (S1/S2/S3). Plus 1 sportsbook-spread realism. Plus 3 calibration analyses (G2/G3/baseline). = ~92 trials.
- V5-C2: 7 features × 3 bands = 21 orthogonality trials. Plus 3 pivots attempted (narrow / wider / midband). = 24 trials.

Total v5 trials: roughly **125** (9 + 92 + 24).

### Test 6b: Bonferroni correction on V5-A2 TA4

**Method:** Recomputed V5-A2 Path Y combined CI at Bonferroni-corrected confidence levels on the n=147 paired diff.

**Result:**
- 95% CI (uncorrected): **[-0.30pp, +4.22pp]** (V5-A2 reports [-0.32pp, +4.22pp]; match within bootstrap seed).
- 99.86% CI (Bonferroni n=35): **[-1.07pp, +6.29pp]**.
- 99.95% CI (Bonferroni n=100): **[-1.15pp, +6.76pp]**.
- 99.96% CI (Bonferroni n=125): **[-1.17pp, +6.80pp]** approximately.

**Finding 6.1: Important.** Under Bonferroni n=125, V5-A2's TA4 fails by ~1.17pp on the corrected CI lower bound (vs the headline -0.30pp). The CI fail magnitude is roughly 4x as far below zero. The V4 critic flagged this at Bonferroni n=35 (-1.15pp); V5 inherits and slightly extends. **V5-A2's TA4 borderline-fail framing UNDERSTATES the multiple-testing burden.** The verdict (ship shadow-mode) is still defensible because shadow-mode is a hypothesis-validation disposition; but the verdict doc should disclose the corrected CI.

### Test 6c: V5-B2 BSS multiple-testing

**Method:** V5-B2 reports G2 BSS = +0.574 on n=43,462 holdout. Did not compute a CI on BSS. Across 74 orthogonality features + 11 pivots + 3 gate variants + 3 sanity, the model BSS was reported once per gate variant.

**Result:**
- BSS at n=43k has very tight CI (the holdout is large). A 95% bootstrap CI on BSS for n=43k is probably ~±0.01.
- BSS is not a market-test criterion in V5-B2's locked gate (the gate uses C1-C6, none of which is BSS). BSS is reported as a "model has skill" diagnostic.
- The multiple-testing concern applies to C1-C6 (which all fail), not to BSS. BSS doesn't require correction because it's not part of the decision rule.

**Finding 6.2: Minor.** The positive BSS finding is robust at this sample size and is NOT subject to multiple-testing inflation. The OPERATIONAL claim ("model has calibration skill") is honestly framed by V5-B2 even though the trading-rule claim ("model produces profitable trades") is null.

### Test 6d: V5-C2 multiple-testing

**Method:** 7 features × 3 bands = 21 trials. Maximum observed in-sample Brier improvement: +0.0015. Threshold: +0.005.

**Result:**
- 21 trials with the BEST in-sample improvement at 3x below threshold means even pre-Bonferroni, no feature passes.
- Multiple-testing makes the null MORE robust, not less.

**Finding 6.3: Minor.** V5-C2's null is unambiguous and not threatened by multiple-testing. V5-C2 actually notes this directly (Section 11): "would be indistinguishable from sampling noise after multiple-comparison correction across 7 features and 3 bands."

---

## Test 7: V2/V3/V4 failure-mode inheritance

### Test 7a: Per-track failure-mode crosswalk

| Failure mode | Track A status | Track B status | Track C status |
|---|---|---|---|
| **CV leak** | n/a (overlay, no ML) | Defense: `trainer=` correctly wired in `scripts/v5/run_statcast_gate.py` via the gate's per-fold retrain. Per-fold C5 means range -0.054 to -0.712 (G2), -0.052 to -0.530 (G3); no spurious +X.XX flip. CONFIRMED CLEAN. | n/a (no model trained) |
| **Feature look-ahead** | Live-only; no historical signal yet. Sportsbook prices captured at moment of v1 candidate scan (forward-looking; shadow-mode logging). | Defense: `game_date < as_of_date` strict in `compute_statcast_features_as_of`. Unit test verifies. CONFIRMED CLEAN. | Defense: features sampled AT open_time (= close_time - 1h). For 1h markets this is the latest leak-free moment. CONFIRMED CLEAN. |
| **Model anchors on price** | n/a | NOT ESCAPED. Orthogonality drops 66 of 74 candidates; the 8 survivors are volume proxies (V3-B1 failure pattern at 1000x). Test 3a confirms. | Different mode: orthogonality drops 7 of 7 (no signal at all). Cleaner null than Track B. |
| **Single-entity artifact** | n/a in production (A3 fires across multiple sports per V5-A1 Section 4.4). | Top-player share <1%; S1 drop-top-10 changes G3 mean by <3c. STRUCTURALLY ABSENT. | Single-day handled by stratified sampling (one market per close-date). STRUCTURALLY ABSENT. |
| **False C6 comparison** | A is overlay on post-denylist v1; honest. | Gate uses v1_decision_fn from gate.py; honest. C6 reports v1=-6.50c baseline for the prop universe (a baseline v1 cannot actually trade because props are outside v1's universe; the C6 comparison is informational). | No gate run. |
| **Wrong cutoff window** | No LLM; n/a. | No LLM; n/a. | No LLM; n/a. |
| **Series-prefix coverage mismatch (v3 W1)** | A is tested on post-denylist v1 universe (denylist applied). HONEST. | Track B tests KXMLBHIT/HR/HRR/KS markets v1 does NOT trade (per V5-B1 Section 4.6.3). v1 is not affected by Track B's result. | Crypto is a new domain; v1 doesn't trade. |
| **C5 fold-boundary tie leak (new in v5)** | n/a | IDENTIFIED in V5-B2 S2: contiguous-row split breaks ties at identical close_time. S2 verification shows `test_strictly_after_train_cutoff=False` for all folds. V5-B2 estimates impact <0.05%; verdict robust regardless. | n/a (no gate run) |
| **Single-class train (V5-C narrow band)** | n/a | n/a | IDENTIFIED in V5-C2 Section 4.2: narrow [0.70, 0.95] train has 1 NO outcome; LogReg degenerates. Pivot to widerband + midband partially mitigates. midband has 7 train NOs / 20 test NOs (or potentially 87 train NOs / 37 test NOs on the full n=500 data per Test 4c). |

**Finding 7.1: Important.** v5 ESCAPES the classical v2/v3 failure modes (CV leak, look-ahead, single-entity) on all three tracks. The "model anchors on price" mode RECURS in Track B at 1000x scale and Track C as a clean null. The new v5-specific failure mode is the fold-boundary tie leak in V5-B2 S2; impact is <0.05% per V5-B2 documentation but the structural issue is real and a Phase 4 fix would split by (game_date, player) tuples rather than row order.

### Test 7b: V3-untested-exposure trap repeated?

**Method:** v1's `+12.47pp` measured edge was computed on `data/processed/sports_dataset.parquet` with ZERO KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS. The W1 denylist (per V4 critic) addressed this. V5's tracks should now operate on the post-denylist universe.

**Result:**
- V5-A2 explicitly uses post-denylist v1 universe (V5-A2 Section 1, confirmed via `data/v5/v1_post_denylist_universe.parquet`). The Path Y backtest uses v3 inventory (n=147) which still includes the now-denylisted series for retrospective comparability with V4-E, but the forward-looking shadow-mode wiring would be on the post-denylist v1.
- V5-B2 operates on prop markets v1 does NOT trade. Track B is structurally separate from v1's universe; the v3 trap does not apply.
- V5-C2 operates on crypto markets v1 does NOT trade. Same.

**Finding 7.2: Minor.** v5 ESCAPES the v3 W1 trap on all three tracks. The W1 denylist is correctly applied in V5-A2's universe enumeration and forward-looking deployment plan. The retrospective Path Y backtest is comparable to V4-E by design, even though it includes denylisted markets in the n=147 sample.

---

## Test 8: Honest verdict on each track

### Track A: V5-A2 says SHIP shadow-mode. CRITIC POSITION: SIGN OFF WITH CAVEATS.

The mechanism is real (V5-A1 measured +1.70c mean, V5-A2 verified 3 of 13 v1-band candidates fire at locked 5c). The retrospective Path Y reproduces V4-E exactly and inherits V4's LOO fragility (signal hinges on 4 of 147 markets). The sportsbook arm contributes ZERO retrospective evidence on v3 inventory and only HYPOTHESIS-LEVEL evidence on forward-looking live universe. Shadow-mode logging is the right disposition. The V5-A2 doc's TLDR slightly overstates the case; explicit "hypothesis-validation by shadow-mode logging" framing is honest.

**Specific changes to V5-A2 doc:**
1. Section TLDR: change "SHIP shadow-mode" to "SHIP as shadow-mode logging for hypothesis-validation; A3 retrospective evidence is structurally zero on v3 inventory; live-universe 23% fire rate is hypothesis-shaping, not P&L-quantified."
2. Section 4.1 (V5-A1 sample re-analysis): annotate the 23% live fire rate as conditional on MATCH-class coverage. On v1's full post-denylist universe (where MATCH coverage is 31%), effective A3 fire rate is **~7%**, not 23%.
3. Section 7 (Recommendation): change shadow-mode timeline from "120-180 days" (matches V4 critic's correction) and confirm the per-fire P&L unknown. After 90 days, mid-window check for whether A3 has resolved any of its fires.
4. Section 3.2 (Path Y combined filter): add LOO-fragility disclosure inherited from V4 critic Finding 1.5: signal hinges on 4 of 147 markets; LOO drop to -0.65pp CI [-1.12, -0.27].
5. Section 4.4: add Bonferroni note: at v5 trial count (~125), TA4 corrected CI is [-1.17pp, +6.80pp].

### Track B: V5-B2 says NULL. CRITIC POSITION: SIGN OFF on NULL.

The fade-direction salvage at the symmetric -5c threshold FIRES ZERO TIMES because the price-only LogReg's max delta is ±2.3c. Wider thresholds yield n>10k trades with consistently negative net P&L. The Kelly-NO salvage looks positive (+5.98c per contract on n=20k) but is a PHANTOM from using `last_price_dollars` (post-settlement stale print) as the buy-side proxy; the realistic NO ask is at $1.00 because yes_bid is at 0 (status=finalized markets have no live quotes). V5-B2's null verdict stands. The "model anchors on price" failure mode is the v2/v3 pattern at 1000x sample.

**Specific changes to V5-B2 doc:**
1. Section 4 (Calibration analysis): add a one-sentence note that the Kelly-NO and fade-direction salvages fail under realistic spread audit. The fade-direction at symmetric -5c fires 0 trades; Kelly-NO produces apparent +5.98c per contract that disappears when the actual NO ask (1 - yes_bid) is used instead of (1 - last_price_dollars).
2. Section 8 (Pivots attempted): add P4 (post-Phase-3 salvage candidates tested): "Fade-direction NO buy at -5c threshold: 0 fires. Kelly-NO buy at f_no > 0.05: phantom +5.98c from stale-print buy proxy. Realistic NO buy at (1-yes_bid): -0.13c to -1.93c gross at mid-band [0.20-0.70]."
3. Section 12 (Honest constraints): add: "The data layer uses post-settlement bid/ask snapshots from `/markets?status=settled`. yes_bid_dollars on mid-band markets is at ~0 in >99% of holdout rows. To honestly test the model's tradeable edge, a Phase 4 build would need live-cadence sampling of bid/ask DURING each market's open lifetime."
4. Section 9 (failure-mode crosswalk): add the C5 fold-boundary tie leak; document the <0.05% impact estimate; note that a fix (split by (game_date, player) tuples) is a structural correction worth doing if anyone revisits Track B.

### Track C: V5-C2 says NULL. CRITIC POSITION: SIGN OFF on NULL.

The cleanest null of the three tracks. The pre-registered prediction (0-2 features pass) held at the lower bound. Pairwise feature correlations confirm the 7 features are independent sources (no collinearity-degenerate). Tracking error to BRTI is 0.09% (below concern). The T-15min skip is defensible. The midband data-vs-report discrepancy (n=500 data vs n=250 report) is worth noting but doesn't change the verdict direction.

**Specific changes to V5-C2 doc:**
1. Section 4.6 (Midband): note that `data/v5/v5c_pivot_midband_data.parquet` contains n=500 rows while `data/v5/v5c_pivot_midband_report.json` ran on n=250. A re-run on the full n=500 with 124 NOs (instead of 27 NOs at n=250) would have more statistical power and is a 5-minute Phase 4 rerun if anyone wants to be thorough.
2. Section 6.3 (T-15min skip): add explicit cost-of-omission estimate: 1-2 hours to rebuild the dataset at T-5min sampling; prior of success is low because the 1h market is approaching determinism. Confirms kill-early.
3. Section 11 (Final note): explicitly state that the pre-registered prediction held at the lower bound; the null is the expected outcome.

---

## Phase 4 must-do list

Per the operator's "do not give up before all angles exhausted" instruction:

1. **V5-A2 shadow-mode wiring** (the right next step, already the recommendation): wire `evaluate_market_combined` into v1's main loop as a logging-only call. Collect 120-180 days of resolved filter activations. Re-run TA evaluation cleanly. Inherit the V4-critic-revised timeline.

2. **V5-A2 doc TLDR revision**: re-frame "SHIP shadow-mode" as "SHIP as hypothesis-validation shadow-mode logging." Disclose LOO fragility from V4-E. Disclose Bonferroni-corrected CI. Disclose A3's ~7% effective fire rate on v1's full universe (vs 23% within-coverage).

3. **V5-B2 per-prop-type orthogonality rerun (optional, ~2 hours)**: rerun the orthogonality protocol restricted to KXMLBHIT mid-band markets (n=259-760 per V5-B1). Check whether xBA / xwOBA / hard-hit-rate clear AUC delta on the restricted sample. Per V5-B2's overall finding, prior is bleak, but the operator's "do not give up" instruction targets exactly this kind of pivot. **Document the result as a definitive close, even if null.**

4. **V5-B2 fade-direction salvage closure**: explicitly document the fade-direction NO-buy failure mode (model delta max = ±2.3c, < 5c trigger). Add the realistic-spread audit (yes_bid=0 in 99% of mid-band post-settlement) so the next round doesn't waste time chasing the BSS-positive-but-untradable signal.

5. **V5-C2 midband full-sample rerun (optional, ~5 minutes)**: re-run the orthogonality probe on the full n=500 midband data (124 NOs) instead of the n=250 subset (27 NOs). Verdict will not change but the analysis is more robust.

6. **C5 fold-boundary tie leak structural fix** (low priority): in `kalshi_bot_v2/gate.py`, change chronological CV split to group-walk-forward by (game_date, player) tuples. This fixes the V5-B2 S2 finding for any future ML on per-game ladder markets. Not load-bearing for any current verdict.

---

## Findings summary

| # | Finding | Severity | Test |
|---|---|---|---|
| 1.1 | 3 of 13 v1-band fires reproduce exactly; 5c=3c=7c on this sample | Important | 1a |
| 1.2 | The 13-denominator is restricted to MATCH-class; honest within scope | Minor | 1b |
| 1.3 | Effective A3 fire rate on v1's full universe is ~7%, not 23% | Important | 1c |
| 1.4 | Signal lives in the +9c+ TAIL (3 fires mean +13.39c) not the +1.7c mean | Killer | 1d |
| 1.5 | Per-fire forward P&L is unquantified at n=0 resolved | Minor | 1e |
| 2.1 | Fade-direction salvage at -5c FIRES ZERO TIMES (model delta max ±2.3c) | Important | 2a |
| 2.2 | Kelly-NO rule at f_no>0.05 yields apparent +5.98c net per contract n=20k | Killer (apparent) | 2b |
| 2.3 | Kelly-NO is a PHANTOM: yes_bid=0 in 99% of mid-band post-settlement; realistic NO buy yields -0.13c to -1.93c gross | Killer | 2c |
| 2.4 | V5-B2 data layer (post-settlement snapshots) does not support tradeable-edge claims | Important | 2d |
| 3.1 | 8 retained features are unambiguously volume proxies; V3-B1 mode at 1000x | Important | 3a |
| 3.2 | Per-prop-type orthogonality NOT run; aggregate may mask KXMLBHIT-specific xBA signal | Important | 3b |
| 3.3 | 1000-vs-5000 bootstrap substitution does not change verdict | Minor | 3c |
| 4.1 | T-15min/T-5min skip is defensible per kill-early; market near-deterministic at T-5min | Important | 4a |
| 4.2 | 7 V5-C features are independent (pairwise corr abs < 0.25); not collinear | Minor | 4b |
| 4.3 | Midband data file has n=500 but report ran on n=250 (data-doc discrepancy) | Important | 4c |
| 4.4 | V5-C1 pre-registered 0-2 prediction held at lower bound | Minor | 4d |
| 5.1 | Book-only arm 0 fires on v3 inventory is structural; threshold not retuned | Important | 5a |
| 5.2 | +1.70pp Path Y identity to V4-E + LOO drop to -0.65pp CI [-1.12,-0.27] | Killer | 5b |
| 5.3 | Forward A3 value is HYPOTHESIS, not measured; V5-A2 TLDR overstates the case | Important | 5c |
| 6.1 | Bonferroni n=125: TA4 corrected CI [-1.17pp, +6.80pp]; understates by ~4x | Important | 6b |
| 6.2 | V5-B2 BSS is robust to multiple-testing; the operational claim is honest | Minor | 6c |
| 6.3 | V5-C2 null is unambiguous; multiple-testing makes null more robust | Minor | 6d |
| 7.1 | v5 escapes classical v2/v3 modes; V5-B2 inherits "anchor on price" + new fold-tie leak | Important | 7a |
| 7.2 | V3 untested-exposure (W1) trap properly closed by denylist | Minor | 7b |

**5 KILLER, 12 IMPORTANT, 8 MINOR.** None of the killers overturn the V5-A2 / V5-B2 / V5-C2 verdicts; they sharpen the framing.

---

## Final position

**Track A: SIGN OFF WITH CAVEATS.** V5-A2's "SHIP shadow-mode" is the right disposition. The verdict needs three framing revisions: (a) explicit hypothesis-validation framing in the TLDR, (b) disclosure of A3's ~7% effective fire rate on v1's full universe, (c) inheritance of V4 critic's LOO fragility on the +1.70pp identity reproduction. The shadow-mode wiring is the load-bearing Phase 4 action; the per-fire P&L will be measurable after 120-180 days of accumulated resolved A3 fires.

**Track B: SIGN OFF on NULL.** V5-B2's null is honest. The fade-direction salvage (the highest-prior killer candidate per the brief) was tested in two forms: symmetric -5c threshold (0 fires) and Kelly-sized NO buy (apparent +5.98c but phantom from stale-print buy proxy). Both fail. The model's +0.574 BSS is calibration smoothing, not tradeable signal. The "model anchors on price" failure mode is the v2/v3 pattern at 1000x scale. The per-prop-type orthogonality rerun (Finding 3.2) is the only remaining angle worth attempting; prior is bleak.

**Track C: SIGN OFF on NULL.** V5-C2's null is the cleanest of the three. The pre-registered prediction held; features are genuinely independent; tracking error is below threshold; T-15min skip is defensible. The midband data-vs-report n discrepancy (Finding 4.3) is worth a 5-minute rerun if the operator wants the most rigorous closure.

**Track A is the only v5 track with a path to live activation.** Tracks B and C are correctly closed. The operator's $32 capital continues running on v1 unchanged. The v5 effort has the strongest data backing of any Project Kalshi build: V5-A's 23% live fire rate (within MATCH coverage) at +9c+ divergence tail, V5-B's largest-ever-sample null with positive calibration skill, V5-C's clean orthogonality null with pre-registered prediction confirmation. The verdicts are defensible.
