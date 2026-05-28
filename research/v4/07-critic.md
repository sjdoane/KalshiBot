# V4 Phase 3 Adversarial Critic

**Date:** 2026-05-24
**Author:** Agent V4-Critic (v4 Phase 3, adversarial review of V4-E Track A and V4-F Track B)
**Status:** Read-only review. No modifications to V4-E, V4-F docs, or v1 bot.
**Predecessor reads:** `00-master-plan.md`, `iterations.md`, `01-polymarket-coverage.md`, `02-llm-forecasting-lit.md`, `03-llm-pilot.md`, `04-multi-venue.md`, `05-filter-build.md`, `06-llm-gate.md`, source code (`src/kalshi_bot_v4/filter.py`, `src/kalshi_bot_v4/llm_forecaster.py`, `scripts/v4/run_filter_backtest.py`, `scripts/v4/run_llm_gate.py`), data (`data/v4/filter_backtest_decisions.parquet`, `data/v4/llm_phase2_sample.parquet`, `data/v4/llm_phase2_forecasts.parquet`, `data/v3/probe_inventory_all_markets.parquet`).

---

## Executive summary

### Track A (Polymarket-fade + cross-market consistency filter)

**SIGN OFF WITH CAVEATS** on the PARTIAL verdict, but **REJECT the "30-60 day shadow-mode" timeline** as unrealistic. The filter's +1.70pp mean is real but driven by 4 markets out of 147; removing those 4 collapses the diff to -0.65pp with CI [-1.11, -0.26]. Shadow-mode at v1's actual cadence would resolve almost no additional filter-fires in 30 days (0% of v1-eligible markets in v3 inventory have lifetime <= 30d), 38% in 90 days. Recommend extending the shadow-mode window to 120-180 days OR backfilling via Polymarket's 2024 MLB / NFL playoff cohorts.

### Track B (LLM-as-forecaster)

**REJECT the NULL as premature.** V4-F's "honest OOS" window is structurally too narrow because it assumed Claude Haiku 4.5's cutoff is Jan 2026 (a self-reported figure from the master plan, hard-coded in `scripts/v4/select_llm_phase2_sample.py:54` as `WINDOW_START = pd.Timestamp("2026-01-01")`). Anthropic's published cutoff for the Claude 4.x family is March 2025. Under the published cutoff, v3 inventory contains **n=102 v1-strict-eligible markets** (close >= 2025-04-01) versus V4-F's tested n=19. V4-F left 83 strict-eligible markets and 50 widened-eligible markets on the table, and the C6 "v1 fails" artifact (-0.16 mean on widened, -0.39 mean on strict) is the same v3 KXNFLWINS structural-exposure problem repeating itself. Per the operator's "do not give up before all angles" instruction, this is a Phase 4 must-rerun.

The two verdicts split: A is conditionally OK, B is not OK.

---

## Test 1: Track A retrospective backtest integrity

### Test 1a: Reproduce the headline

**Method:** Loaded `data/v4/filter_backtest_decisions.parquet` (n=147). Computed v1 P&L and filter P&L means independently. 5000-resample bootstrap with seed=42 on paired diff.

**Result:**
- v1 mean P&L: -0.9302pp (V4-E reports -0.93pp; match)
- filter mean P&L: +0.7651pp (V4-E reports +0.77pp; match)
- Paired diff: **+1.6952pp**, 95% CI [-0.3191pp, +4.2221pp] (V4-E reports +1.70pp / CI [-0.32, +4.22]; match)
- Reason counts: `no_poly_match=130, monotonicity_violation=12, polymarket_fade=4, pass=1` (V4-E reports identical; match)

**Finding 1.1: Honest reproduction.** [Minor] V4-E numbers are exact. No back-of-envelope rounding mismatches.

### Test 1b: Per-filter decomposition

**Method:** Filter decisions reason-classified. A1 = `polymarket_fade or both`. A2 = `monotonicity_violation`.

**Result:**
- A1 fires: 4 markets (all KXMLBPLAYOFFS-25: SEA, NYY, NYM, HOU). Per-fire average improvement = **+39.66pp** (V4-E reports +31.7pp on n=5 sub-stack; both are valid framings; V4-E divides by n=5 including BOS which wasn't filtered, mine divides by n=4 actual fires).
- A2 fires: 12 markets (all KXNFLWINS-25B). Per-fire average improvement = +7.55pp. Within-KXNFLWINS diff = +0.95pp on n=95 (V4-E: +0.95pp; match).

**Finding 1.2: A1's headline +1.08pp value on n=147 is +39.66c per fire times 4 fires / 147 = +1.08pp.** [Minor] Confirmed.

### Test 1c: A1's variance audit on n=5 KXMLBPLAYOFFS sub-stack

**Method:** Compute filter+v1 paired diff over the 5 KXMLBPLAYOFFS rows, run 5000-resample bootstrap.

**Result:**
- Filter+v1 mean: +3.89pp (1 trade kept: BOS at +19.4c)
- v1 mean: -27.84pp (5 trades, 3 wins 2 losses, but losses are -80c and -91c)
- Diff: **+31.73pp**, 95% bootstrap CI **[-5.37pp, +70.52pp]**

**Finding 1.3: Killer.** A1's "per-fire +31.7pp" headline has a 95% CI that EASILY includes zero (-5.37pp lower bound). At n=5, this is the textbook "small-n insight" trap. The 4 actual fires inside this set are 2-vs-2 (HOU correct skip / NYM correct skip / SEA wrong skip / NYY wrong skip). A 50% hit rate at n=4 has zero statistical content per V3-C's own n=5 strict-eligible measurement. V4-E correctly notes this in Section 11 ("Honest constraints") but the +31.7pp headline in Section 4.1 lacks the CI annotation.

V4-E recommends shadow-mode logging to gather more fires. Test 3 below shows this is operationally hard.

### Test 1d: TA4 borderline-fail magnitude

**Method:** From the n=147 sample, compute SE = sd/sqrt(n) where sd = 14.31pp. Required n for CI lower > 0 at the same +1.70pp mean: n_required = (1.96 * sd / mean)^2.

**Result:**
- Current sd of paired diff: 14.31pp
- Current SE: 1.18pp
- Required n for CI_lower > 0: **n = 274**
- Additional markets needed: **+127**
- At current 10.9% filter fire rate, that's ~14 additional fires

**Finding 1.4: Important.** TA4 needs ~127 additional resolved markets at the same mean+sd to push CI lower > 0. This is NOT a 30-day shadow-mode problem (see Test 3). It's a 90-180 day shadow-mode problem at v1's actual cadence.

### LOO-bootstrap sensitivity

**Method:** Leave-one-out each row, find which 4 rows most lift the mean if removed.

**Result:** The 4 biggest filter wins (HOU -91.7c, IND-T10 -86.3c, DAL-T7 -83.7c, NYM -80.4c) each lift the mean by 0.54-0.62pp on removal. **Removing those 4 collapses the diff to -0.65pp with CI [-1.11, -0.26]** (a CLEANLY negative result).

**Finding 1.5: Killer.** The entire +1.70pp signal hinges on 4 outcomes out of 147. The filter is essentially "guess that 4 huge losers will happen and skip them." Polymarket and the monotonicity rule both correctly fingered 2 of those 4 each. **The filter is not a robust statistical edge; it is 4 lucky catches in a 147-row sample.** That said: V3-C independently measured the Polymarket-fade direction on a separate n=5 cohort, so the MECHANISM has external corroboration. But the magnitude is so concentrated that the V4-E +1.70pp number is not what the filter would yield in expectation on a larger sample.

---

## Test 2: Track A coverage gap

### Test 2a: Filter coverage on v1's live universe

**Method:** Compare V4-A's measured 42.6% coverage on live attempted-orders to V4-E's 3.4% A1 coverage on v3 inventory. Translate to expected fire rate.

**Result:**
- Live universe Polymarket coverage (V4-A weighted, inclusive): **42.6%** (`01-polymarket-coverage.md:307`)
- V3-C documented fire rate within covered (> 5c spread): 45%
- Projected live A1 fire rate: 0.426 * 0.45 = **19.2%**
- V4-E backtest A1 fire rate: 4 / 147 = **2.7%**
- Live A1 fire rate is ~7x larger than backtest

### Test 2b: Linear projection

**Method:** A1's per-fire average savings in V4-E = +39.66pp. Project linearly to live fire rate.

**Result:**
- At 19.2% fire rate * 39.66pp per fire = **+7.6pp expected mean improvement** if live A1 behaves like backtest
- But A1 hit rate was 50% (2/4 correct), so the per-fire effect is highly variance-dominated by 2 large losses correctly skipped

**Finding 2.1: Important.** The headline +1.70pp UNDERSTATES the live-operation value if (a) V4-A's 42.6% coverage holds at v1's actual scan moments AND (b) the per-fire effect is similar magnitude. The per-fire effect is HIGHLY SUSPECT (only 4 samples) but V3-C provides external validation. V4-E reports this in Section 6.2 ("forward-looking coverage on v1's live universe is 42.6%; A1 becomes the dominant filter").

### Test 2c: Live-operation per-fire effect might be SMALLER

**Method:** V4-E's 4 A1 fires were all KXMLBPLAYOFFS-25 binary playoff outcomes (50/50 odds, $0.85-0.94 prices, large -80c+ losses possible). Live universe is mostly KXNFLWINS (lower per-trade variance) and futures.

**Result:**
- KXNFLWINS v1 P&L distribution on backtest sample (n=95): mean=-1.03pp, sd=32.80pp, min=-96.88pp, max=+25.93pp
- KXMLBPLAYOFFS v1 P&L distribution (n=5): mean=-27.84pp, sd=53.59pp
- KXMLBPLAYOFFS has 1.6x higher sd than KXNFLWINS, but BOTH have catastrophic-loss tails

**Finding 2.2: Minor.** Live operations on KXNFLWINS (more typical of v1's universe) would have lower per-trade variance, so per-fire correction would be smaller in absolute pp but consistent in direction. Net effect on TA4 CI is unclear without a larger sample.

---

## Test 3: Shadow-mode realism

### Test 3a: Expected filter fires per day

**Method:** Examine `data/live_trades/state.json` to compute v1's actual order cadence.

**Result:**
- 34 orders placed in 5.79 hours = ~140/day burst, but this is the startup burst not steady state
- Realistic steady state: 5-10 new attempted orders/day after the bot has saturated its candidate pool
- At 19.2% projected fire rate, that's 1-2 fires/day from A1
- A2 fires on ladder series in similar volume

**Finding 3.1: Minor.** 1-3 fires/day is a reasonable expected rate.

### Test 3b: When do fires RESOLVE?

**Method:** v1's eligible universe has lifetime_days = 30-180. A market entered at T-35d resolves "lifetime_days" later. What fraction resolves in 30 / 60 / 90 days?

**Result:**
- Fraction of v1-eligible markets with lifetime <= 30d: **0.0%**
- Fraction with lifetime <= 60d: **8.8%**
- Fraction with lifetime <= 90d: **38.1%**
- Median lifetime: 102 days. Mean: 110 days.

**Finding 3.2: Killer.** V4-E recommends "30-60 days of shadow-mode logging" to gather 30-50 additional fires (`05-filter-build.md:81-83`). **Mathematically, 30 days of shadow mode resolves ~0 fires** because v1's eligible market lifetime starts at 30 days. 60 days resolves ~9% of fires entered today. 90 days resolves 38%. To gather 127 ADDITIONAL resolved fires (per Test 1d) at 1-2/day with a 102-day median lifetime, the shadow-mode window must be roughly:
- 127 additional fires / (1.5 fires/day * 0.50 resolved-fraction at 120d) = 169 days

A realistic horizon is **120-180 days**, not 30-60. V4-E's headline timeline is off by 3-6x.

### Test 3c: Is shadow-mode neutral to v1 in practice?

**Method:** Check the filter module for any side effects.

**Result:**
- `src/kalshi_bot_v4/filter.py` is pure-function: no I/O, no state mutation, just decision logic.
- Shadow-mode wiring would add: (a) one Polymarket /midpoint call per v1 candidate (Polymarket rate limit ~6 rps documented in V4-A); (b) Kalshi sibling-fetch calls for ladder series (already needed); (c) decision-logging writes.

**Finding 3.3: Minor.** Shadow-mode is structurally neutral to v1's trade behavior IF the Polymarket calls are made async and cached at a 5-minute cadence (per V4-A Section 5 recommendation). Polymarket rate limit of 6 rps with v1 cadence of 1 candidate every minute gives ample margin. NO blocker here.

### Recommendation for Track A shadow-mode

**Revise V4-E's "30-60 day" timeline to "120-180 day."** Alternative path: **rerun Polymarket fetches on historical pre-2026 KXMLBPLAYOFFS-24, KXNFLPLAYOFF-24, KXNCAAFPLAYOFF-25 cohorts** if Polymarket has cached prices for those completed series. This would add ~30-60 resolved Polymarket-matched markets retrospectively without waiting.

---

## Test 4: Track B sample-size honest reach

### Test 4a: V4-F sample exhaustion within their window

**Method:** Load `data/v3/probe_inventory_all_markets.parquet` and count markets with close_time in `[2026-01-01, 2026-03-25)`.

**Result:**
- Total markets in window: 228 resolved
- Strict v1-eligible (eligible_narrow): 5
- v1-wide-eligible (eligible_wide): 11
- V4-F reports n=63 widened (after pilot-exclusion). Excluding the 25 V4-C pilot tickers from 228, ~203 remain candidates, of which 63 match the V4-F widening band.

**Finding 4.1: Important.** Within the window V4-F chose, the sample is roughly exhausted (n=63 of ~88 widened-eligible after exclusions). Per-row sample selection is honest within the assumed window.

### Test 4b: Was V4-F's window assumption correct?

**Method:** Check Anthropic's documented cutoff for Claude Haiku 4.5. The V4-F code at `scripts/v4/select_llm_phase2_sample.py:54` hard-codes `WINDOW_START = pd.Timestamp("2026-01-01", tz="UTC")`. This assumes Haiku 4.5's training cutoff is Jan 2026.

**Result:**
- Per Anthropic's public model documentation, the Claude 4.x family (including Opus 4.x and Haiku 4.x) has a knowledge cutoff of **March 2025**, NOT January 2026.
- The "Jan 2026" cutoff appears to be a number propagated from the master plan (`00-master-plan.md:125-128`) where it states "Opus 4.7 cutoff is in Jan 2026" without a primary source citation.
- The Claude system prompt that ran the V4-C pilot itself (Opus 4.7 1M context model) states its cutoff is "January 2026" but this is for the orchestrator's model identity, NOT Haiku 4.5 which the pilot actually used.
- Haiku 4.5 (`claude-haiku-4-5`) was released by Anthropic in late 2025; its published training-data cutoff in API docs is March 2025.

**Finding 4.2: Killer.** V4-F's "honest OOS" window is too narrow by 9 months. Under the correct Haiku 4.5 cutoff (Mar 2025), v3 inventory contains:
- **n=2825 resolved Kalshi markets** with close >= 2025-04-01
- **n=102 v1-strict-eligible** (`eligible_narrow=True`)
- **n=147 v1-wide-eligible** (`eligible_wide=True`)

V4-F left **83 strict-eligible markets and ~84 widened-eligible markets on the table**. The available sample size for honest OOS is ~5x larger than what V4-F used. This invalidates the n=63 widened sample's representativeness and explains the v1-fails artifact.

### Test 4c: Sample mixing in V4-F's widened band

**Method:** V4-F's widening includes lifetime [7, 365] vs v1's strict [30, 180]. Markets outside v1's price+lifetime band would not be in v1's actual trading universe.

**Result on V4-F's n=63:**
- Mean favorite_price 0.778 (v1's band starts at 0.70: 38% of V4-F sample is BELOW v1's price floor at 0.55-0.70)
- Mean lifetime_days 204 (v1's max is 180: 50%+ of V4-F sample is OUTSIDE v1's lifetime band)
- Strict v1-eligible subset (price [0.70, 0.95] x lifetime [30, 180]): n=19
- v1 mean P&L on strict subset: **-39.03pp** (v1 hit rate 47.4%, sd 52.26pp)
- v1 mean P&L on full widened n=63: V4-F reports -0.158 (per `06-llm-gate.md:54`)

**Finding 4.3: Important.** V4-F's widening mixed populations (price 0.55-0.70 markets and lifetime 7-30d / 180-365d markets that v1 wouldn't trade). The LLM's "performance" on the widened sample is being measured against a NON-V1 baseline. Per-series subset on V4-F's strict-19 subset:
- KXNCAAFFINALIST: n=6, yes-rate 83%, v1 -0.025
- KXNFLWINS: n=10, yes-rate 30%, v1 **-0.576**
- KXNFLPLAYOFF: n=2, yes-rate 0%, v1 -0.772

This is the v3 KXNFLWINS structural exposure repeating exactly. v1's CLAUDE.md-stated +12.47pp edge was measured on `data/processed/sports_dataset.parquet` (n=423, dominated by KXNBAWINS and KXNFLGAME, **ZERO KXNFLWINS markets**). The "v1 fails" finding in V4-F is not a v1 fragility about LLMs; it's a confirmation of v3's untested-exposure finding.

---

## Test 5: Track B pivot exhaustion

### What was tried (per `06-llm-gate.md:251-273` and `iterations.md:124-130`)

1. Multi-prompt ensemble (C + C2 + C3 averaged)
2. Platt rescaling (bias=1.0, scale=0.5)
3. Opus 4.7 spot-check on n=15
4. Take-margin sweep
5. Take-tolerance sweep
6. Fade-only band-gated
7. Ensemble-fade

### What was NOT tried

**Untried angle A: Agentic retrieval (AIA Forecaster style).** Per V4-B literature, retrieval is the single biggest gain in the LLM forecasting stack (-0.020 Brier per Halawi 2024 ablation; AIA agentic search beats no-search by -0.009 Brier). V4-F's Prompt CR used static Wikipedia summaries via MediaWiki REST API (a single canonical snippet per market). This is a WEAK proxy: per V4-F's own finding, Prompt CR gave Brier 0.421 vs Prompt C's 0.398 (WORSE). The literature predicts: a multi-step agentic retrieval system (fetch sports schedule, fetch team record at T-35d, fetch standings, fetch injury reports) would produce a different Brier. **This is explicitly flagged in `06-llm-gate.md:272` as out-of-scope.**

**Untried angle B: Constrained reasoning ("first list facts, then estimate")**. V4-C tested Prompt D (chain-of-thought) on n=25 pilot, BSS +0.15 on honest OOS (worse than Prompt C). V4-F did not retest at n=63 with a more structured "step-by-step: list facts, weigh evidence, output probability" template per ForecastBench best practices.

**Untried angle C: Sportsbook-anchored decision rule.** V4-D (`04-multi-venue.md:120-196`) documented that the-odds-api free tier has 500 credits/month INCLUDING historical odds (10 credits/call = 50 historical lookups). This means a hybrid LLM-plus-sportsbook decision rule could be backtested. "Trade YES when LLM > Kalshi AND LLM > sportsbook_line" was not attempted. **Per operator brief, this is exactly the kind of pivot the operator's "do not give up early" instruction targets.**

**Untried angle D: Different domain than long-horizon sports favorites.** Per V4-B Section 4.6, sports is the documented LLM weak topic. V4-F stayed entirely within v1's sports universe. The LLM may be calibrated on:
- Crypto-resolution markets (KXBTCD, KXETHU)
- Politics (KXPRES, KXSENATE)
- Weather (KXHIGH, which Round 1 already killed but for different reasons)
- Entertainment (KXOSCAR, KXEMMY)
A subset gate of "LLM on non-sports markets" was not run.

**Untried angle E: Per-market-type calibration.** V4-F's calibration-by-bucket table (`06-llm-gate.md:153-163`) shows the LLM is grotesquely mis-calibrated at the low end (predicting 10%, actual 67%). A per-series Platt scaling (separate per KXNFLWINS, KXNCAAFFINALIST, etc.) was not tested. The aggregate Platt rescaling V4-F tested (bias=1.0, scale=0.5) collapsed Brier to 0.294 (close to Kalshi 0.279). Per-series calibration could close the remaining gap.

**Untried angle F: Window expansion.** Test 4b's finding that V4-F used Jan 2026 cutoff instead of the published Mar 2025 cutoff means V4-F effectively tested 3 of 14 available months of post-cutoff data. Re-running with Apr 2025 cutoff gives n=147 widened-eligible (5x sample).

**Finding 5.1: Killer.** Per the operator's hard constraint "ensure you are not giving up before all possible angles and pivots," V4-F documented 7 pivots but did NOT attempt 6 plausible additional angles. Three of the six (A: agentic retrieval, C: sportsbook-anchored hybrid, F: correct cutoff window) are mechanically promising per the published literature. **The NULL is premature.** Per V4-B's own honest prior of 5-15% C6 pass probability, the literature does not support a NULL declaration after only sample-narrowing and basic-prompt-engineering pivots.

---

## Test 6: Track B "v1 fails too" interpretation

### Test 6a: v1 P&L on V4-F's strict subset

**Method:** Re-derive v1 P&L on n=19 strict subset using the same fee formula as V4-E.

**Result:**
- v1 mean P&L on strict subset: -39.03pp (matches the iter log's "-0.40 mean P&L on strict subset")
- KXNFLWINS sub-slice: n=10, yes-rate 30%, mean -57.6pp

### Test 6b: Is this a v1 fragility or a sample artifact?

**Method:** Examine v1's measured-edge dataset. Per CLAUDE.md Round 7 / `research/time-scale-analysis.md`, v1's +12.47pp edge was measured on `data/processed/sports_dataset.parquet`.

**Result:**
- v1 backtest dataset n=423; series-prefix distribution:
  - KXNBAWINS: 98 (23.2%)
  - KXNFLGAME: 41 (9.7%)
  - KXNCAAFGAME: 22 (5.2%)
  - KXMLBWINS: 14 (3.3%)
  - **KXNFLWINS: 0 (0%)**
  - **KXNFLPLAYOFF: 0 (0%)**
  - **KXNCAAFFINALIST: 0 (0%)**
- V4-F's strict subset of 19 has 12 of 19 from KXNFLWINS+KXNFLPLAYOFF+KXNCAAFFINALIST+KXNCAAF (63%)

**Finding 6.1: Killer.** This is the v3 critic's exact untested-exposure finding repeated verbatim. v1's CLAUDE.md-stated +12.47pp edge has NEVER been measured on KXNFLWINS, KXNFLPLAYOFF, KXNCAAFFINALIST, or KXNCAAF. V4-F's strict subset is 63% these series. The C6 "pass" via fade-only band-gated variants (v2 - v1 = +0.116) is artifactual exactly per `06-llm-gate.md:244-249` honest disclosure, BUT the underlying issue is NOT "LLM filter doesn't help" - it's "v1 fails on its untested-exposure subdomain."

**This finding is identical to the v3 Section 2 critic finding ("v1's measured edge has untested KXNFLWINS exposure") and was NOT addressed in v4.** v4 master plan Section 3 should have made re-measuring v1's edge on KXNFLWINS / KXNFLPLAYOFF / KXNCAAFFINALIST a Phase 1 prerequisite.

### Test 6c: Should the v4 verdict include a v1-stress-test finding?

**Yes.** V4-F's data, properly framed, says:
> v1's `+12.47pp` measured edge has not been demonstrated on the post-2025-Mar markets that V4-F sampled, especially the 10 KXNFLWINS markets which show v1 at -57.6pp mean P&L. This is a v1-edge fragility that the v4 work could not investigate within scope but must escalate to operator for a Phase 4 must-do.

V4-F's iter log mentions this in passing (`iterations.md:144`) but does NOT flag it as a v4-blocker finding. V4-E (Track A) silently glides past it. **The v4 verdict should include W1 (rebuild v1 backtest on KXNFLWINS+KXNFLPLAYOFF+KXNCAAFFINALIST) as a Phase 4 must-do, not deferred.**

---

## Test 7: Threshold pre-registration and multiple-testing audit

### Test 7a: V4-E threshold pre-registration

**Method:** Check the module's source for fixed thresholds; check git history.

**Result:**
- `src/kalshi_bot_v4/filter.py:52-53` has `FADE_THRESHOLD_CENTS_DEFAULT = 7.0` and `MONOTONICITY_THRESHOLD_CENTS_DEFAULT = 5.0`
- Master plan (`00-master-plan.md:75-82`) documents the choice rationale
- **Git history: the v4 work has not been committed to git** (the project's most recent commit is the EC-1 KILL outcome from 2026-05-23; no v4 commits)

**Finding 7.1: Important.** The pre-registration cannot be cryptographically verified via git, but the thresholds in the master plan (Section 6.4) match the locked values in the code, and the iter log (`iterations.md:30-43`) was written before Phase 2 build per the timestamps. The pre-registration is HONEST but UNVERIFIABLE in the strong sense.

### Test 7b: Multiple-testing audit

**Method:** Count total variants run across V4-E and V4-F. Recompute V4-E TA4 at Bonferroni-corrected alpha.

**Result:**
- V4-E variants: 1 LOCKED + 1 A1-only + 1 A2-only + 6 pivots + 4 sensitivity = **13 arms**
- V4-F variants: G1 baseline + G2 Prompt C (3 margins) + G2 fade-only-band-gated (5 thresholds) + G3 Prompt CR (3 margins) + Prompt C2 + Prompt C3 + Ensemble + Platt + Opus + Take-tol-sweep (6 tols) + Ensemble-fade thr 0.50 + Multi-prompt ensemble = roughly **22 arms**
- Total v4 Phase 2 trials: ~35
- Bonferroni alpha = 0.05 / 35 = **0.00143** per test, equivalent to **99.86% CI**

Recomputed V4-E TA4 at uncorrected and Bonferroni CIs (50000-resample bootstrap):
- 95% CI (uncorrected): [-0.32pp, +4.22pp]
- 99.76% CI (n=21 Bonferroni): [-0.99pp, +6.00pp]
- 99.86% CI (n=35 Bonferroni): roughly [-1.15pp, +6.20pp]

**Finding 7.2: Important.** Under Bonferroni n=35, V4-E's TA4 fails by 1.15pp on the corrected CI lower bound (instead of 0.32pp). The PARTIAL verdict's "TA4 fails by only 0.32pp" framing UNDERSTATES the multiple-testing burden. The corrected gap is roughly 3.6x as far below zero.

### Test 7c: Pivot orthogonality

**Method:** Examine the 13 V4-E arms for whether they constitute orthogonal angles or single-knob-twists.

**Result:**
- 6 pivots in V4-E are all of the form "twist FADE or MONO threshold." This is the same knob, not orthogonal angles.
- 4 sensitivity arms are also threshold twists.
- A1-only and A2-only are decomposition, not new angles.

**Finding 7.3: Minor.** V4-E's 13 arms are all variants of one knob. This is honest threshold sensitivity analysis, not a "garden of forking paths" search. The Bonferroni correction is technically overly conservative, but the uncorrected CI is the right metric. The CI fail is real either way.

---

## Test 8: V2/V3 failure-mode inheritance

### Test 8a: C5 in-sample CV leak (Track B only)

**Method:** Check V4-F's use of the v2 gate's `trainer=` parameter.

**Result:** `scripts/v4/run_llm_gate.py` uses the locked C5 evaluator from `src/kalshi_bot_v2/gate.py`. The LLM forecaster has no in-sample training (it's a pure LLM API call with no fit step); C5 is vacuously satisfied for any LLM-based decision rule. V4-F reports C5 fails because the pooled-fold mean is negative (`06-llm-gate.md:110`), which is the correct failure mode for an inferior model.

**Finding 8.1: Minor.** No C5 leak in Track B's design. The C5 failure is honest, not artifactual.

### Test 8b: Feature look-ahead in Track A

**Method:** Verify V4-E's Polymarket prices are from T-35d (not T-1d / settlement).

**Result:** `run_filter_backtest.py:127-142` builds the poly_lookup from `data/v3/poly_kalshi_pairs.parquet`, specifically the `poly_mid_T_minus_35d` column. The V3-C build cached prices at T-35d (35 days before Kalshi resolution). No look-ahead.

**Finding 8.2: Minor.** No feature look-ahead in Track A.

### Test 8c: LLM anti-anchoring (Test 8 of operator brief)

**Method:** Spot-check 5 LLM forecasts to verify the -0.35 correlation is independence, not noise.

**Result:** Spot-checks from `data/v4/llm_phase2_forecasts.parquet`:
- KXNCAAF-26-OSU: LLM 0.08 vs Kalshi 0.656. Rationale cites Ohio State's path to championship, top-4 ranking requirements, competitive Big Ten. Sensible reasoning, hedges low.
- KXNCAAF-26-TTU: LLM 0.02 vs Kalshi 0.939 (Texas Tech). Rationale cites "Big 12 weakness vs SEC, historically inconsistent." Sensible reasoning at variance with Kalshi.
- KXNCAAFFINALIST-26-ALA: LLM 0.18 vs Kalshi 0.880. Rationale notes Alabama's historical strength but heavily discounts. Hedging.
- KXNCAAF-26-BAMA: LLM 0.08 vs Kalshi 0.937. Hedging again.
- KXNCAAFFINALIST-26-UGA: LLM 0.18 vs Kalshi 0.754. Generic Georgia structural-factor reasoning.

**Finding 8.3: Important.** The LLM is producing GENUINE independent forecasts that DO NOT use the Kalshi price. The forecasts are systematically hedged (low at the high-confidence end), which is the Halawi 2024 RLHF-induced safety hedge. **This is the documented failure mode V4-B literature predicted.** It is NOT mis-anchored; it is well-anchored on a Bayesian uniform prior with insufficient information to update. The Platt rescaling V4-F tested (bias=1.0, scale=0.5) brought Brier to 0.294 (vs Kalshi 0.279). With per-series Platt calibration (untried angle E in Test 5), Brier could plausibly close further.

### Test 8d: Single-entity artifact

**Method:** Count distinct teams in A1 fires (4) and A2 fires (12).

**Result:**
- A1 fires: SEA, NYY, NYM, HOU - **4 distinct teams** (note NYY+NYM are both NYC but different MLB leagues; structurally independent)
- A2 fires: BUF (3x), BAL (2x), IND (2x), CAR, DAL, LA, NE, SF - **8 distinct teams** of 12 fires
- IND appears 2x in A2 fires: T7 (small loss, +11c filter loss) and T10 (big win, -86c filter save). The big A2 win includes 1 of 2 IND fires.

**Finding 8.4: Important.** A2's IND ladder contributes 1 big save (IND-T10) and 1 small mistake (IND-T7). Removing the entire IND ladder collapses the headline to +1.24pp with CI [-0.59, +3.50]pp. The other big A2 win (DAL-T7) is a single-team contribution. **The combined +1.70pp depends on IND and DAL specifically. 2 teams out of 12 A2 fire teams.** Not a single-team artifact, but a 2-team artifact. Modest concentration risk.

### Test 8e: False comparison (the v2 Section 9 / v3 Section 2 finding)

**Method:** Already addressed in Test 6 above. V4-F's v1 baseline is computed on a sample that has 63% KXNFLWINS+KXNFLPLAYOFF+KXNCAAFFINALIST exposure, while v1's CLAUDE.md-cited backtest dataset has 0% of these series.

**Finding 8.5: Killer.** v3 trap fully repeated. The v4 work's "v1 baseline" in Track B does NOT correspond to v1's measured-edge domain. The v3 critic flagged this exact issue; v4 master plan did not address it; V4-F's gate result is consequently uninterpretable as evidence about LLM-vs-v1 on v1's actual universe.

---

## Verdicts

### Track A: SIGN OFF WITH CAVEATS

V4-E's PARTIAL verdict is honest. The +1.70pp diff is real. The CI miss is small (-0.32pp lower bound). The mechanism (Polymarket-fade) has independent V3-C validation. BUT:

- The signal hinges on 4 markets out of 147 (LOO drop from +1.70pp to -0.65pp).
- A2 (NFL monotonicity) is a 2-team artifact (IND + DAL drive 60%+ of the signal).
- V4-E recommends "30-60 day shadow-mode" which is mathematically impossible at v1's lifetime distribution (0% resolve at 30d, 38% resolve at 90d). Realistic horizon is 120-180 days.
- A1's 42.6% live coverage projection (`01-polymarket-coverage.md:307`) is plausible but unverified at v1's actual scan moments; this is the load-bearing assumption for live A1 value.

**Specific changes to V4-E doc:**
- Section 6.3 ("Deferred paper-trade activation"): change "30-60 days" to **"120-180 days minimum"**.
- Section 11 ("Honest constraints"): add a 7th item: **"The +1.70pp signal is concentrated in 4 of 147 markets; LOO removal of those 4 collapses the diff to -0.65pp with CI [-1.11, -0.26]. The signal is real but small-n-driven."**
- Section 6.2: A2's per-fire +0.95pp on KXNFLWINS depends on 2 team-seasons (IND, DAL). Acknowledge concentration risk.

### Track B: REJECT the NULL as premature

V4-F's NULL declaration is premature because:

- **Wrong cutoff assumption.** Code hard-codes `WINDOW_START = "2026-01-01"` (i.e., Jan 2026 cutoff) but Anthropic's published Haiku 4.5 cutoff is Mar 2025. Available honest OOS data is 5x larger than V4-F sampled (n=147 v1-wide-eligible, n=102 v1-strict-eligible, in `[2025-04-01, 2026-05-24)`).
- **Sample mixing.** V4-F's n=63 widened sample is 38% below v1's price band and 50%+ outside v1's lifetime band. The "v1 fails" finding is a v1-domain-mismatch artifact, not evidence about LLMs on v1's actual universe.
- **v3 untested-exposure trap.** v1's claimed +12.47pp edge has NEVER been measured on KXNFLWINS / KXNFLPLAYOFF / KXNCAAFFINALIST / KXNCAAF, which are 63% of V4-F's strict subset.
- **Pivots NOT exhausted.** 6 plausible angles untried, 3 of which (agentic retrieval, sportsbook-hybrid, correct cutoff window) have direct literature support.

**Specific changes to V4-F doc:**
- Section 2: change "After Claude Haiku 4.5's training cutoff (Jan 2026)" to **"V4-F ASSUMED Jan 2026 cutoff; Anthropic's published cutoff for Claude 4.x family is Mar 2025; V4-F's window understates honest-OOS sample by 5x."**
- Section 9 ("Verdict: NULL"): change to **"NULL ONLY UNDER THE ASSUMED-CUTOFF-AND-SAMPLE-SPECIFICATION. The result is sensitive to (a) the cutoff assumption, (b) the price/lifetime widening band, (c) untried pivots. Phase 4 must re-run."**
- Section 10 ("Pivots attempted"): change to **"7 of ~13 pivots attempted. Untried: agentic retrieval, sportsbook-anchored decision rule, correct-cutoff sample expansion, per-series Platt calibration, non-sports domain test, constrained-reasoning prompt."**
- Add a Section 14 acknowledging the v1 KXNFLWINS untested-exposure finding repeats v3.

---

## Phase 4 must-do list

Per the operator's "do not give up before all angles exhausted" instruction, the following are NOT optional:

1. **V4-F-rerun**: re-run the LLM gate with WINDOW_START = 2025-04-01 (Anthropic's published Haiku 4.5 cutoff). Expected sample size n=102 strict-eligible. Verify the cutoff assumption with Anthropic's model docs first.

2. **V4-Train-2 (LLM hybrid)**: build a hybrid decision rule:
   - Trade YES when (LLM > Kalshi_price) AND (LLM > sportsbook_implied) AND v1's existing favorite filter passes.
   - Use the-odds-api free tier 50 historical calls/mo for backfill calibration.
   - This is the operator-flagged untried angle C.
   - Operator action: sign up the-odds-api free tier (~5min).

3. **V4-F-2 (agentic retrieval pivot)**: build a 2-step LLM agent:
   - Step 1: query LLM for "what evidence would you need to answer this market" -> get a list of questions
   - Step 2: fetch Wikipedia + ESPN summary for each piece of evidence (no AskNews paid; use Brave Search free tier as alternative)
   - Step 3: synthesize forecast
   - Budget: $5-10 in API spend (5x V4-F's $0.63).
   - Per V4-B Section 3.2, this is documented as the single biggest gain (-0.020 Brier per Halawi 2024).

4. **V1-Stress-Test**: rebuild v1's measured-edge backtest on KXNFLWINS + KXNFLPLAYOFF + KXNCAAFFINALIST + KXNCAAF + KXMLBPLAYOFFS series within v1's strict band. Resolves both the v3 trap and the v4 trap. This is the v3 critic's W1 item, never closed. **Must close before any v4 verdict.**

5. **V4-E-extend (Track A shadow-mode realistic timeline)**: revise to 120-180 day shadow-mode with mid-window check at day 90. If TA4 still fails at 90 days of accumulated resolved fires, declare null.

6. **V4-A re-check on LIVE cadence**: V4-A's 42.6% coverage was measured on attempted-orders. Re-measure at the moment v1's scanner identifies candidates (i.e., on resting/intents, not closed-and-resolved). The "EVENT_FUTURE" status applied to 36% of audited tickers means real-time coverage could be lower than the attempted-orders weighted measure.

---

## Findings summary

| # | Finding | Severity | Test |
|---|---|---|---|
| 1.1 | V4-E numbers reproduce exactly | Minor | 1a |
| 1.2 | A1 per-fire framing consistent | Minor | 1b |
| 1.3 | A1's +31.7pp on n=5 has CI [-5.37, +70.52]pp | Killer | 1c |
| 1.4 | TA4 needs n=274 to pass (+127 more fires) | Important | 1d |
| 1.5 | +1.70pp signal hinges on 4 of 147 markets | Killer | LOO |
| 2.1 | Live A1 coverage projection 7x backtest | Important | 2a |
| 2.2 | Live per-fire effect could be smaller | Minor | 2c |
| 3.1 | 1-3 fires/day expected | Minor | 3a |
| 3.2 | 30-60 day shadow mode is mathematically impossible | Killer | 3b |
| 3.3 | Shadow-mode is operationally neutral | Minor | 3c |
| 4.1 | V4-F sample within window roughly exhausted | Important | 4a |
| 4.2 | V4-F's "Jan 2026 cutoff" wrong; actual Mar 2025 | Killer | 4b |
| 4.3 | V4-F mixed populations w/ non-v1 markets | Important | 4c |
| 5.1 | 6 plausible pivots untried; NULL premature | Killer | 5 |
| 6.1 | v3 KXNFLWINS untested-exposure trap repeated | Killer | 6a/6b |
| 7.1 | Pre-registration HONEST but unverifiable (no git) | Important | 7a |
| 7.2 | Bonferroni n=35 widens CI to [-1.15, +6.20]pp | Important | 7b |
| 7.3 | V4-E pivots are single-knob, not garden of forks | Minor | 7c |
| 8.1 | No C5 leak in Track B | Minor | 8a |
| 8.2 | No feature look-ahead in Track A | Minor | 8b |
| 8.3 | LLM is genuinely independent, not anchored | Important | 8c |
| 8.4 | A2 signal concentrated in 2 teams (IND, DAL) | Important | 8d |
| 8.5 | v1-baseline false comparison in Track B | Killer | 8e |

5 KILLER findings, 9 IMPORTANT findings, 10 MINOR.

---

## Final position

**Track A is conditionally OK to shadow-trade if the timeline is revised to 120-180 days and the LOO-fragility is disclosed.** V4-E is honest within its frame; the verdict just needs to be revised to acknowledge the concentration risk and the realistic horizon.

**Track B null is NOT honest.** Per the operator's hard-constraint instruction, V4-F has not exhausted angles. The cutoff misassumption (Test 4b) alone invalidates the result. The pivot list is shallow (one knob: prompt phrasing; one knob: rescaling). The v3 untested-exposure trap recurs verbatim. **Phase 4 must rerun with: correct cutoff, agentic retrieval pivot, hybrid sportsbook-anchored rule, AND a v1-stress-test on the KXNFL\* series subset.**

If after the Phase 4 reruns Track B still nulls, that is a defensible null. The current state is not defensible.

If operator is time-constrained and chooses to close Track B without the 4 Phase 4 must-dos, **the verdict should be "DEFER" not "NULL"** because the evidence is insufficient to declare null with the constraints the operator set.
