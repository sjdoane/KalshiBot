# v4 Iteration Log

Continuous trail of orchestrator decisions, pivots, and gate runs. Append-only. Most recent at the bottom.

## Iter 0 (2026-05-24, master plan)

`research/v4/00-master-plan.md` written. Two tracks (A: Polymarket-fade-filter, B: LLM-as-forecaster) selected by operator after v3 null. Operator instruction: "ensure you are not giving up before you attack all possible angles and make all possible pivots and improvements." Phase 1 four-agent fan-out queued (V4-A coverage, V4-B literature, V4-C LLM pilot, V4-D multi-venue fallback).

## Iter 1 (2026-05-24, Phase 1 synthesis)

Phase 1 returned four research docs:
- `01-polymarket-coverage.md` (V4-A)
- `02-llm-forecasting-lit.md` (V4-B)
- `03-llm-pilot.md` (V4-C)
- `04-multi-venue.md` (V4-D)

### Findings summary

1. **Polymarket-fade-filter (Track A) coverage is partial-but-real.** 42.6% inclusive coverage of v1's live attempted-orders universe (29.4% strict MATCH-only; 57.3% on v1's currently-acked tickers). Sits in the master plan's 30-50% partial-filter band. Live mids work where matches exist; some markets have empty orderbooks or thin depth. Polymarket Global is the relevant feed (not Polymarket US which is too small). PROCEED Track A as partial filter.

2. **LLM-as-forecaster (Track B) shows positive signal but literature prior is low.** Honest-OOS pilot at n=10 shows Brier skill score +0.29 to +0.32 for prompts without the Kalshi price visible; price-included Prompt A confirmed anchoring (r=+0.48 with Kalshi price); no cutoff-leak detected. Variant C (no-memory injunction) and Variant D (chain-of-thought) both work. Haiku 4.5 is as good as Opus 4.7 on this task, and 15x cheaper. Cost projection $0.36 for full v4 eval, well under budget. Literature prior says 5-15% chance of clearing C6 because (a) sports is LLM's documented weak topic, (b) AIA Forecaster 2025 LAGS market consensus by 0.015 on liquid markets, (c) C6 needs +14.47pp gross which is 7x larger than literature's documented LLM additive value. PROCEED Track B at expanded n>=50 to confirm pilot signal.

3. **Internal Kalshi cross-market consistency is a surprise high-promise finding.** V4-D's exploration of v4 master plan Section 5 (fallback path) found that 20.7% of NFL win-total threshold ladders violate monotonicity at T-35d. Of 6 resolved violations on KXNFLWINS, "short the over-priced high-threshold" was right 6 of 6 times. Small n but directionally clean. NBAWINS essentially monotone (1.5% violation rate); MLBWINS too sparse. This is a NEW track A-prime that doesn't depend on Polymarket at all. PROCEED as Track A2 alongside the Polymarket filter.

4. **the-odds-api free tier is more usable than v2/v3 assumed.** 500 credits/mo INCLUDES historical odds at 10 credits/call. 50 historical calls available free per month. Operator has not signed up; 5-min email-only registration. Documented as candidate-secondary-signal but defers to operator action.

### Decision: PROCEED with three sub-tracks in Phase 2

Track A1: Polymarket-fade-filter on the 42.6% covered subset of v1's universe. Builds on V3-C's measured signal direction.

Track A2: Internal Kalshi cross-market consistency check (NFL win-total monotonicity, extend to other ladders). Independent of external venues. Most-interesting V4-D finding.

Track B: LLM-as-forecaster at expanded sample (n>=50 post-cutoff Kalshi markets). Use Prompt C (no price, no-memory injunction) per V4-C pilot. Use Haiku 4.5 per V4-B literature + cost.

A1 and A2 are filter-style overlays on v1 (both reduce v1's trade entries on suspected over-pricing); they can share evaluation infrastructure. Track B is a different paradigm (LLM produces a probability, model trades when LLM disagrees with Kalshi); separate build.

### Phase 2 plan

Two parallel agents:
- **Agent V4-E (Track A1 + A2 build)**: build a unified filter module (`src/kalshi_bot_v4/filter.py`) that combines Polymarket-fade and cross-market-consistency. Retrospective backtest on v1's eligible markets where data is recoverable. Evaluate against TA1-TA5 criteria from master plan.
- **Agent V4-F (Track B build)**: build LLM-forecaster module (`src/kalshi_bot_v4/llm_forecaster.py`) at expanded sample size. Apply the locked C1-C6 gate from `src/kalshi_bot_v2/gate.py`. Use Prompt C from V4-C pilot.

Pivots already documented for each track in master plan Sections 6.3 and 7.2-7.3. Critic phase comes after both builds complete.

## Iter 2 (2026-05-24, V4-E filter build returned)

`research/v4/05-filter-build.md` written. Headline verdict: **PARTIAL pass.** 4 of 5 TA1-TA5 criteria pass at the LOCKED thresholds (fade=7c, mono=5c). TA4 fails by 0.32pp on the 95% bootstrap CI lower bound. The filter shows a real, directionally consistent improvement of +1.70pp mean P&L on n=147 eligible markets, but per-trade variance at this sample size prevents a clean CI exclusion of zero.

### Threshold variants tested (all pre-registered, none used to tune)

| Variant | fade(c) | mono(c) | Diff mean | CI lower | TA pass count |
|---|---:|---:|---:|---:|---|
| LOCKED (headline) | 7 | 5 | +1.70pp | -0.32pp | 4 / 5 |
| Pivot 1 | 5 | 5 | +1.70pp | -0.32pp | 4 / 5 |
| Pivot 2 | 10 | 5 | +1.70pp | -0.32pp | 4 / 5 |
| Pivot 3 | 7 | 3 | +1.62pp | -0.41pp | 4 / 5 |
| Pivot 4 | 7 | 8 | +1.24pp | -0.50pp | 4 / 5 |
| Pivot 5 | 5 | 3 | +1.62pp | -0.41pp | 4 / 5 |
| Pivot 6 | 10 | 8 | +1.24pp | -0.50pp | 4 / 5 |
| Sens A2-12c | 7 | 12 | +1.33pp | -0.42pp | 4 / 5 |
| Sens A2-15c | 7 | 15 | +0.92pp | -0.36pp | 2 / 5 |
| Sens A2-20c | 7 | 20 | +1.00pp | -0.24pp | 3 / 5 |
| Sens A2-25c | 7 | 25 | +1.00pp | -0.24pp | 3 / 5 |
| A1-only | 7 | (off) | +1.08pp | -0.16pp | 2 / 5 (TA1 fails on inventory) |
| A2-only | (off) | 5 | +0.62pp | -0.72pp | 2 / 5 (TA2 fails) |

**No variant clears TA4.** AND-logic (skip when BOTH fire) is mathematically zero on this dataset because A1 and A2 fire on disjoint subsets (KXMLBPLAYOFFS-25 vs KXNFLWINS-25B).

### Per-filter contribution

- **A1 (Polymarket-fade)** fires on 4 of 5 KXMLBPLAYOFFS-25 markets, saves -158c net (2 correct skips of NYM and HOU which resolved NO at -80c each, 2 incorrect skips of SEA and NYY which resolved YES at +10c and +3c). Per-trade improvement on the 5-market sub-stack: **+31.7pp**.

- **A2 (cross-market consistency)** fires on 12 of 95 KXNFLWINS markets, saves -91c net (2 large correct skips of DAL T7 and IND T10, 10 small incorrect skips of legitimate winners). Per-trade improvement on KXNFLWINS: **+0.95pp**, but hit rate only 16.7% (the +0.95 is driven by the asymmetric magnitudes of the 2 large losses).

### Honest finding

Per the master plan's kill-early principle and the operator's "no post-hoc threshold tuning" constraint, the filter does NOT pass the full TA1-TA5 gate. Per the operator's "do not give up early" instruction, all 6 pre-registered pivots + 4 sensitivity arms were tested; no variant cleared TA4. **Declared PARTIAL finding honestly.**

### Recommended next step

**Deferred paper-trade activation via shadow-mode logging.** Wire the filter into v1 to LOG its decisions on every candidate, do NOT alter v1's actual trades. After 30-60 days of additional resolved filter-fires (target n+30 to n+50 extra), re-run the TA1-TA5 evaluation. If TA4 cleanly passes on the expanded sample, activate the filter. If not, document as null and revisit in v5.

Track A2's NFL signal is the weakest piece (small-n, outlier-dependent). Track A1's Polymarket-fade is the strongest signal mechanism (mechanistically grounded by V3-C, large per-trade effect) but coverage is bottlenecked by 3.4% Polymarket pairing on this v3 inventory; V4-A predicts 42.6% on the LIVE universe, so shadow-mode is the right way to confirm.

Operator-action items NOT taken in this build:
- Sign up for the-odds-api free tier (V4-D recommendation): deferred to a future Track A3 build if needed.
- Extend Track A2 to NHL/NBA/MLB division-winner ladders: current inventory too sparse to justify.
- Live Polymarket fetch wiring: not in scope for retrospective backtest.

## Iter 3 (2026-05-24, V4-F Track B build returned)

`research/v4/06-llm-gate.md` written. Headline verdict: **NULL.** LLM-as-forecaster fails the locked C1-C6 gate on n=63 post-cutoff Kalshi markets. Most criteria do not pass; the apparent C6 pass on band-gated fade variants is artifactual because v1 itself FAILS on the widened sample (-0.158 mean P&L on holdout n=19).

### Sample expansion

Strict v1-eligibility (price [0.70, 0.95] x lifetime [30, 180] days) in the [2026-01-01, 2026-03-25) window yields only n=9-19 markets. Documented widening per brief:
- Favorite-side flipping: treat NO-side favorites as eligible (price = 1 - YES_price)
- Price band: [0.55, 0.95]
- Lifetime: [7, 365] days

Result: n=63 markets after V4-C pilot exclusion. Yes-rate 55.6%, mean favorite_price 0.778. All 63 fetched successfully.

### Gate outcome (Prompt C base, Haiku 4.5)

| Gate | n holdout | mean P&L | v2-v1 | CI lower | C1-C6 pass count |
|---|---:|---:|---:|---:|---:|
| G1 v1 baseline | 19 | -0.1586 | (ref) | -0.355 | 0/5 (v1 fails!) |
| G2 Prompt C, margin 0.00 | 0 | n/a | n/a | n/a | 0/6 (no trades) |
| G2 Prompt C, fade-only band-gated thr=0.10 | 7 | -0.0423 | +0.116 | -0.259 | 2/6 (C3, C6) |
| G3 Prompt CR (Wikipedia RAG), margin 0.00 | 0 | n/a | n/a | n/a | 0/6 (no trades) |

LLM probability mean = 0.31 vs Kalshi 0.78 (LLM persistently biased LOW). Correlation between LLM and Kalshi prob: -0.35 (LLM contradicts the market). Brier LLM 0.398 vs Kalshi 0.279 (BSS -0.43).

On the strict v1-eligible subset (n=19), Brier LLM 0.399 vs Kalshi 0.394 (BSS -0.01). Essentially tied; LLM does not add signal.

### Sanity test outcomes

- **S-B1 cutoff-leak**: brier_full_pre 0.259, brier_anon_pre 0.275; mean_abs_diff 0.075. NO meaningful cutoff-leak. The LLM is not memorizing past outcomes.
- **S-B2 price-anchor**: corr(no-price, price) = -0.67, corr(with-price, price) = -0.63. LLM does NOT anchor on price; if anything it actively CONTRADICTS the price. WP minus NP diff = +0.23 (showing price pulls LLM up by 0.23 on average but still net low).
- **S-B3 prompt-sensitivity**: mean_std_across_variants = 0.035, mean_range 0.083. Prompt is REASONABLY ROBUST.

### Pivots attempted

1. **Multi-prompt ensemble (C + C2 + C3 averaged)**: Brier 0.395 (essentially same as C alone). No gain.
2. **Platt rescaling (bias=1.0, scale=0.5)**: Brier 0.294 (close to Kalshi 0.279 but still worse). Cannot beat Kalshi even with optimal calibration.
3. **Opus 4.7 on n=15 subsample**: Brier 0.365 (WORSE than Haiku 0.278 on same subset). V4-C pilot finding replicated.
4. **Threshold sweep on take-margin**: All margins produce 0 trades (LLM biased too low).
5. **Tolerance sweep on take-when-LLM-disagrees-less-than-X**: tol=0.60 produces 5 trades, mean +0.028, but CI lower -0.32. C4 fails (n=5 < 15).
6. **Fade-only band-gated (0.70 <= price <= 0.85)**: 7 trades in holdout, mean -0.042. C6 passes (v2-v1 = +0.116) but C1, C2, C4 all fail.
7. **Ensemble-fade thr=0.50 band-gated**: 8 trades, mean -0.010, v2-v1 +0.149. C6 passes; C1, C2, C4 fail.

### Honest failure modes documented

1. **LLM is structurally LOW-biased relative to Kalshi price** on long-horizon sports favorites. Mean LLM prob 0.31 vs Kalshi 0.78. This is the V4-B literature documented "RLHF hedging on high-confidence questions" failure mode.

2. **Prompt CR (Wikipedia retrieval) makes Brier WORSE**, not better (0.421 vs 0.398). Contradicts V4-B literature's Halawi 2024 -0.020 Brier gain from retrieval; the Wikipedia summaries we fetched were too generic for the specific market questions. Agentic search (AIA Forecaster style) might help; out of scope.

3. **Opus 4.7 not better than Haiku 4.5** on this task. V4-C pilot finding replicated at larger n.

4. **No cutoff-leak detected**. The LLM is not benefiting from memorized outcomes; it's just bad at this task at this confidence level.

5. **No price-anchoring detected** (in fact NEGATIVE correlation). The LLM is producing INDEPENDENT but MIS-CALIBRATED probability estimates.

6. **The "v2 beats v1 by 2pp" criterion (C6) passes only artifactually** because v1 fails on the widened sample (-0.158 mean). On the strict v1 subset, v1 also fails (-0.40 mean P&L), and LLM filter does not rescue it because the LLM picks the WRONG markets to keep.

### Verdict: NULL

LLM-as-forecaster fails the locked C1-C6 gate on the leak-free post-cutoff sample. The Brier-level signal is too weak to clear C1 (positive mean P&L) and C2 (CI lower > 0). Sample size constraints (n=63 widened, n=19 strict) prevent passing C4 on any selective filter variant.

Cumulative API spend: $0.63 (well under $15 budget). V4 total LLM spend including V4-C pilot: ~$0.97.

Per operator's kill-early principle and the V4-B literature's 5-15% honest prior on Track B clearing C6, this is a clean kill consistent with the literature ceiling. The pilot's positive directional signal at n=10 (BSS +0.32 on honest-OOS) did NOT replicate at n=63: BSS -0.43 here. The signal was sample-specific; with the wider sample including division-winner / championship-winner markets where the LLM has no information, the Brier degrades sharply.

### Recommendation

Close Track B as null. Future Track B work would require:
- Agentic retrieval (AIA Forecaster style), not bare Wikipedia summaries
- A larger post-cutoff sample (n>=100), which requires waiting for more Kalshi historical data to accumulate past the LLM cutoff
- Possibly a frontier reasoning model (o3, GPT-5) at 50x cost; literature suggests this is the only tier showing competitive performance
- Acceptance that even with all of the above, the literature ceiling is +0.014 Brier improvement over market consensus on hard markets (per V4-B AIA + market ensemble result), which is ~1.4pp probability edge, far short of C6's +14.47pp required.

Track A (filter) remains the live recommendation per V4-E. Track B null is consistent with the v3 lesson that "we cannot beat market price on long-horizon sports favorites" extends to the LLM-as-forecaster paradigm.

## Iter 4 (2026-05-24, Phase 3 critic + Phase 4 plan)

`research/v4/07-critic.md` returned. 5 KILLER, 9 IMPORTANT, 10 MINOR findings.

### Verdicts amended

- **Track A**: SIGN OFF WITH CAVEATS. +1.70pp diff reproduces but LOO removal of 4 outlier wins collapses it to -0.65pp. Shadow-mode 30-60 days mathematically impossible (0% of v1-eligible markets resolve in 30 days, 38% in 90 days; realistic horizon is 120-180 days).
- **Track B**: REJECT the NULL as premature. V4-F hardcoded `WINDOW_START = "2026-01-01"` assuming Haiku 4.5 cutoff is Jan 2026; critic asserts Anthropic's published cutoff is earlier; sample is 5x undersized.

### Three Killer findings drive Phase 4

1. V4-F cutoff window may be wrong (Killer 4.2). Sample-size impact is 5x.
2. V3 KXNFLWINS untested-exposure trap repeated in v4 (Killer 6.1 / 8.5). v1's claimed +12.47pp has never been measured on KXNFLWINS+series which were 63% of V4-F's strict subset.
3. 6 plausible pivots untried (Killer 5.1). Most-recommended: correct cutoff window rerun, agentic retrieval, sportsbook hybrid.

### Phase 4 plan (parallel agents)

- **V4-G (cutoff verification + V4-F rerun)**: verify Haiku 4.5's actual cutoff via Anthropic docs; if different from V4-F's assumption, rerun the LLM gate with correct WINDOW_START. Likely sample n=102 strict-eligible vs V4-F's n=19.
- **V4-H (v1 stress-test)**: rebuild v1's measured-edge backtest on KXNFLWINS + KXNFLPLAYOFF + KXNCAAFFINALIST + KXNCAAF + KXMLBPLAYOFFS series within v1's strict band. Closes the v3 W1 item never closed. Also resolves the v4 Track B false-comparison interpretation.
- **V4-I (orchestrator-direct)**: amend V4-E doc per critic recommendations - revise shadow-mode timeline to 120-180 days, add LOO-fragility disclosure, note 2-team A2 concentration risk.

Optional additional pivots if budget allows after V4-G:
- V4-J: agentic retrieval pivot for Track B (per V4-B literature, single biggest gain in LLM forecasting stack)
- V4-K: sportsbook-anchored hybrid (requires operator the-odds-api signup)

Phase 4 must complete before FINAL-VERDICT.md can be written honestly.

## Iter 5 (2026-05-24, V4-H stress test result)

V4-H delivered `research/v4/09-v1-stress-test.md`. Closes v3 W1 and v4 critic Finding 6.1 / 8.5.

### Headline numbers

- KXNFLWINS n=95: mean -1.03pp, CI [-7.71pp, +5.08pp] (includes zero).
- KXNFLPLAYOFF n=9: mean -10.18pp, CI [-38.41pp, +11.85pp] (includes zero).
- KXMLBPLAYOFFS n=5: mean -27.84pp, CI [-68.98pp, +12.56pp] (includes zero).
- KXNCAAFFINALIST and KXNCAAF have ZERO v1-eligible markets (untradable by v1's price filter; T-35d VWAP never reaches 0.70).
- AGGREGATE (new 109 + original 39) = 148 markets, mean +1.06pp, CI [-4.06pp, +5.84pp] (includes zero).

### Verdict

v1 FRAGILE on the three measurable target series. The original +12.47pp on n=39 was a domain-restricted artifact (100% YES rate is itself a survivorship signature). On the full v1-tradable universe, v1's measured edge is NOT measurably positive.

### Operator action recommended

v1 PARTIAL: add a series-prefix denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) to the v1 scanner before any v4 verdict. Re-derive v1's edge on the denylisted-remaining universe before continuing live trading at scale.

### Cross-cutting implication

V4-F's "v1 baseline fails" finding is now interpretable as INTRINSIC, not artifactual. The LLM-vs-v1 comparison on these series is between two failing strategies, not "LLM vs strong v1." The Track B null conclusion stands; the additional conclusion is that v1 itself needs scope reduction.

Phase 4 V4-H complete. Awaiting V4-G (cutoff rerun) and V4-I (V4-E amendments) before final verdict.

## Iter 6 (2026-05-24, V4-G2 cutoff rerun + V4-I amendments)

V4-G2 returned at `research/v4/10-llm-rerun.md`. V4-I amendments applied to `research/v4/05-filter-build.md`. Phase 4 complete.

### Verified Anthropic cutoffs

Direct verification via `platform.claude.com/docs/en/about-claude/models/overview`:
- Claude Haiku 4.5 (`claude-haiku-4-5-20251001`): reliable knowledge cutoff Feb 2025, training data cutoff Jul 2025.
- Claude Opus 4.7: knowledge cutoff Jan 2026, training cutoff Jan 2026.

V4-F's hardcoded `WINDOW_START = 2026-01-01` assumed cutoff was Jan 2026; the actual Haiku 4.5 training cutoff is Jul 2025. V4-F undersampled by ~6 months of post-cutoff data.

### V4-G2 result

Rebuilt sample with `WINDOW_START = 2025-08-01` (one month after Haiku 4.5 training cutoff for safety). New strict sample n=238 (12.5x V4-F's n=19). Critical sample-construction correction: removed an over-aggressive `SAMPLE_CAP = 200` that the previous V4-G stalled-agent had left in the selector, which chronologically excluded 13 of 15 catastrophic-loss tickers.

Gate result on n=238:
- G1 v1 baseline: holdout mean -7.89pp, CI [-17.48pp, +0.24pp]; 0/6 criteria pass.
- G2 LLM take rule (`llm_prob > kalshi_price`): n=2 trades (LLM rarely says YES > Kalshi); C4 fails 7.5x.
- G2 fade-only band-gated: n=48, mean -8.21pp, v2 - v1 = -0.32pp; 0/6 criteria pass.
- LLM Brier 0.261 vs Kalshi 0.082, BSS -2.17 (LLM is much WORSE than Kalshi calibration).
- Three-way analysis: v1 raw +1.83pp [-1.73, +5.28]; v1 + V4-H denylist +3.28pp [-4.68, +9.77]; v1 + denylist + LLM-fade +3.30pp [-3.36, +7.59]. Denylist helps; LLM adds essentially nothing on top.

S-B1 leak sanity rerun: full-prompt advantage on pre-cutoff exists but reflects legitimate team-knowledge priors (Brier full 0.166, anon 0.237, mean abs diff 0.123). Even with the team-knowledge bonus, LLM Brier 0.166 is 2x Kalshi 0.081 on the pre-cutoff sample.

V4 cumulative LLM spend: $1.03 of $25 cap.

### Verdict: CONFIRM NULL for Track B

The Phase 3 critic's Killer Finding 4.2 (wrong cutoff window) is closed. The rerun at the correct cutoff DOES NOT change the Track B null verdict. The LLM-as-forecaster genuinely fails the locked C1-C6 gate at n=238 with proper leak discipline. Consistent with V4-B literature ceiling (5-15% prior, validated).

### V4-E doc amendments (V4-I)

Applied per Phase 3 critic's specific recommendations:
- Section 6.3 "shadow-mode 30-60 days" -> "120-180 days minimum" (Section 11A added with the math)
- Section 11 added items 7 and 8: LOO collapse to -0.65pp on removal of 4 outliers; A2 concentration in 2 teams (IND, DAL)

### Track A status post-Phase-4

PARTIAL stands but with disclosed concentration risk. Shadow-mode shipping is still the right move but with realistic 120-180 day timeline, not 30-60.

### Overall v4 verdict after Phase 4

- Track A (filter): PARTIAL with 120-180 day shadow-mode timeline. Real signal direction, small n.
- Track B (LLM): NULL CONFIRMED at correct cutoff window. v4-B literature ceiling validated.
- v1: FRAGILE on KXNFLWINS / KXNFLPLAYOFF / KXMLBPLAYOFFS (V4-H). Operator-action item: add series denylist before any further scaling.

Phase 5 final verdict can now be written honestly.
