# Project Kalshi v4 Master Plan

**Date:** 2026-05-24
**Status:** Research phase, multi-agent autonomous execution
**Author:** Claude (orchestrator)
**Operator authorization:** Rethink the strategy after v3 null. Pursue two tracks in parallel: Track A (Polymarket-live-fade-filter) and Track B (LLM-as-forecaster). Explicit instruction: "ensure you are not giving up before you attack all possible angles and make all possible pivots and improvements to the model that could help based on research and good principles. Explore both first options thoroughly."

## 1. Why v4

v2 and v3 closed as null findings on the "external feature predicts outcome better than market" thesis at our scale. v3 specifically established three hard constraints for future ML work:

1. Free-public-feature sports prediction has a +1-3pp gross-edge ceiling. Outcome prediction with public sportsbook-overlapping features is a dead path.
2. Sample size at n=30-147 is structurally below AFML T=252 minimum; any "passing" gate at this n has high prior on false positive.
3. Polymarket lacks free historical price data beyond 30 days, so any "Polymarket as training feature" thesis is blocked at the data-availability layer for historical CV.

v4 explicitly avoids those failure modes by NOT competing on sports-outcome-prediction with sportsbooks and NOT requiring historical Polymarket data.

Two angles we measured to be promising but didn't exploit in v3:

- **Polymarket signal direction is real and consistent** on long-horizon sports markets (v3 V3-C: Brier 0.192 vs Kalshi 0.264 on n=5 strict-eligible; every >5c spread had Kalshi over Polymarket). The signal works as a LIVE FILTER even though it fails as historical TRAINING.
- **LLM forecasting** is a fundamentally different paradigm that doesn't compete with sportsbooks on traditional features. Recent literature (Halawi et al. 2024, Karger et al. 2024, Schoenegger 2024) documents LLM forecasting performance approaching aggregated crowd accuracy on prediction-market-style questions.

## 2. Thesis

The v4 candidate edges:

- **Track A (Polymarket-fade-filter)**: when v1 considers placing a YES order on a Kalshi market that ALSO exists on Polymarket Global, fetch Polymarket's current mid; if Polymarket implies a lower probability than Kalshi by more than X cents, skip the trade. The expected effect is to PRUNE v1's worst-calibrated entries (those v1 over-prices relative to Polymarket's better-calibrated estimate). Counterfactual measurement requires retrospective evaluation on the live attempted-orders log + forward-test going forward.

- **Track B (LLM-as-forecaster)**: for each v1-eligible Kalshi market candidate, construct a prompt with the market's full description, settlement rules, and (optionally) relevant news. Query an LLM for a probability estimate. Trade Kalshi YES when LLM_prob > Kalshi_price by a meaningful margin (after fees and slippage). Evaluate against the locked gate with leak-free CV.

Both tracks operate AT or AROUND v1's live universe, not on a chronological 30/70 holdout of a contrived dataset. v3's holdout-construction problem (NFL late-season concentration) does not apply because the evaluation is forward-looking on real v1 candidates OR on a properly-anonymized historical Kalshi set.

## 3. Hypotheses

- **H-A (Track A)**: Polymarket-as-live-fade-filter improves v1's realized P&L per trade by at least +1pp without reducing volume by more than 50%. (Smaller-than-C6 threshold reflects defensive overlay nature; the goal is improvement-over-v1, not a brand-new strategy.)

- **H-B (Track B)**: an LLM-as-forecaster with structured prompt + news context produces probability estimates that, on a leak-free OOS holdout, yield trades that beat v1 by >= 2pp on the same C6 criterion as locked in v2/v3 gate.

## 4. What would falsify each hypothesis

**H-A falsified if:**
- Polymarket-Kalshi event matching has < 30% coverage of v1's actual filled-orders universe. (We can match what Polymarket lists, but most of v1's live universe might be in series Polymarket doesn't carry, e.g., KXBOXING, KXUFCFIGHT, KXCS2.)
- The filter rule's retrospective application (using V3-C's existing matched pairs) shows zero or negative improvement over v1's bare strategy.
- The filter's true positive rate (correctly skipping Kalshi favorites that resolve NO) is below random-chance baseline.

**H-B falsified if:**
- LLM forecasts are systematically anchored on the Kalshi price itself (because the prompt includes it), with no value-add. This is the v3 "model anchors on price" failure mode in LLM form.
- LLM forecasts have a knowledge-cutoff leak: the LLM correctly forecasts events that resolved BEFORE its training cutoff but produces noise for events after. This is the time-equivalent of the v3 "in-sample CV leak."
- On a clean post-cutoff holdout, LLM Brier score does not beat the raw Kalshi price baseline.
- Operator API costs exceed value at $32-capital scale (we need to estimate this empirically).

## 5. Hard constraints (inherited from operator brief, locked)

1. v1 bot untouched. No changes to `src/kalshi_bot/`, `scripts/` (except `scripts/v4/`), `tests/` (except `tests/v4/`), `data/` outside `data/v4/`, `.env`, `data/live_trades/`.
2. No real Kalshi orders. READ-scope client only. v4 is paper/backtest only.
3. No Polymarket WRITE endpoints. READ public APIs only (gamma-api, clob, data-api).
4. Locked 6-criteria gate from `src/kalshi_bot_v2/gate.py` is binding for Track B. For Track A, the metric is "improvement over v1 on the same set of trades" (so the v1 baseline is bare v1, the v4 measurement is v1+filter).
5. No skipping or redefining gate criteria. v2/v3 discipline holds.
6. No claim of signal without leak-free OOS validation.
7. No em-dashes.
8. Continuous documentation in research/v4/. Iter log appended each phase.

## 6. Track A: Polymarket-as-live-fade-filter

### 6.1 Mechanism

When v1's scanner identifies a candidate market at T-35d, before placing the order, check:

1. Does this Kalshi market have a Polymarket Global counterpart? (event matching)
2. If yes, fetch Polymarket's current YES mid via clob.polymarket.com.
3. Compute the divergence: `kalshi_price - poly_mid`.
4. If `kalshi_price - poly_mid > FADE_THRESHOLD_CENTS`, SKIP this trade (Polymarket says Kalshi is over-pricing).
5. Otherwise, allow v1's normal trade logic to proceed.

`FADE_THRESHOLD_CENTS` is the critical hyperparameter. v3 V3-C measured:
- Mean Kalshi minus Polymarket = +9.21c at T-35d
- 45% of pairs > 5c spread
- 36% of pairs > 15c spread

A FADE_THRESHOLD of 5c is aggressive (skips ~45% of overlapping trades); 15c is conservative (skips ~36%). The right value must be picked OOS with leak-free discipline.

### 6.2 Coverage problem

v3 V3-C measured 65% match rate on 20 sampled MLB long-horizon markets (good for the subset tested), BUT 0% match rate on KXMLBWINS (Polymarket doesn't list 2025 MLB season-win totals). And v3's Phase 3 critic showed v1's actual live attempted-orders span 19 series-prefixes including KXBOXING, KXUFCFIGHT, KXWCGAME, KXCS2 - many of which Polymarket may not carry at all.

Track A is bottlenecked by HOW MANY of v1's actual live universe markets have a Polymarket counterpart. This must be measured BEFORE building the filter.

### 6.3 Pivot if coverage is low

If only 20-30% of v1's live universe has Polymarket counterparts, Track A becomes a "partial filter" that activates only on covered markets. This is still useful (improvement on the covered subset), but the headline value drops.

Further pivots if Polymarket coverage is too low:

- **Multi-venue second opinion**: PredictIt (US-legal political, low sports), ManifoldMarkets (community-driven, free API, lots of markets), Sportsbook closing lines (via the-odds-api free tier if operator signs up).
- **Implied-from-related-markets second opinion**: even if no direct Polymarket counterpart exists, related Polymarket markets (e.g., "Will Team X win the conference?" when v1 is looking at "Will Team X win 10+ regular-season games?") give CORRELATED signal. Use the related-market Polymarket prob plus a transition probability to construct an implied second-opinion.
- **Polymarket-implied signal from team-level conditional probabilities**: build a "team strength index" from Polymarket's championship futures, derived implied per-team win-totals.

### 6.4 Gate for Track A

Since Track A is a defensive overlay on v1 (not a new strategy), C6 (beats v1 by >= 2pp) is not the right gate. Instead:

- **TA1**: filter coverage >= 30% of v1's live attempted-orders universe (otherwise the filter rarely fires, value is small).
- **TA2**: on the covered subset, filter improves v1's realized mean P&L by at least +1pp.
- **TA3**: filter reduces v1's covered-subset trade count by no more than 50% (otherwise the filter is so aggressive it kills v1's volume).
- **TA4**: TA2 holds with bootstrap 95% CI lower > 0 on the realized improvement.
- **TA5**: per-series sanity check: filter's improvement on at least 2 distinct series-prefixes (not concentrated to one league/season).

## 7. Track B: LLM-as-forecaster

### 7.1 Mechanism

For each candidate Kalshi market, construct a prompt that includes:

- The market's `rules_primary` and `rules_secondary` text (settlement criteria)
- The market's `title` and `subtitle`
- Current Kalshi mid-price (for reference; the LLM is told this is the market's implied probability)
- (Optional) Recent news headlines / Wikipedia summary / context

Query the LLM for: "Given this market and the available evidence, what is your best estimate of P(YES)?"

Parse the response. Trade Kalshi YES when LLM_prob > Kalshi_price by a chosen margin (after fees).

### 7.2 Knowledge-cutoff leak

THIS IS THE LOAD-BEARING FAILURE MODE. The LLM's training cutoff is in Jan 2026. Any Kalshi market that RESOLVED BEFORE Jan 2026 may be in the LLM's training data. If we evaluate the forecaster on pre-cutoff markets, the LLM "knows" the answer and produces a leak-equivalent of v3's CV leak.

The honest test is on POST-CUTOFF Kalshi markets. Kalshi's `/historical/cutoff` returned 2026-03-25 in v3. The window of usable test markets is 2026-01 onward (LLM cutoff) through 2026-03 (Kalshi historical cutoff). That's a thin sample.

Pivots if the post-cutoff sample is too thin:

- Use multiple LLMs with different training cutoffs and ensemble (Claude Opus 4.7 cutoff Jan 2026, GPT-5 cutoff if available, Gemini cutoff if available).
- Construct prompts that explicitly tell the LLM "do not use any information you may know about the actual outcome of this event; only reason from the description"
- Test the leak quantitatively: ask the LLM for probabilities on a sample of pre-cutoff markets, then again with the resolution date REDACTED from the prompt. Compare. The gap is the cutoff-leak magnitude.

### 7.3 Cost concern

Anthropic API at our scale: Claude Opus 4.7 input is approximately $15/MTok, output approximately $75/MTok. A typical forecast prompt is ~1k input tokens, ~500 output tokens. Per forecast: ~$0.05. For a 147-row dataset evaluation: ~$7.50. For ongoing live operation at v1's cadence (15min loop, ~15 candidates, 100% Polymarket coverage hypothetical): ~$300-500/mo. THIS EXCEEDS $32 CAPITAL.

Pivots if cost is prohibitive:

- Use cheaper model (Haiku 4.5: $1/MTok input, $5/MTok output - 15x cheaper). Per forecast: ~$0.003. Per month live: ~$25-50. Within budget.
- Cache LLM responses keyed by market ID (the LLM doesn't need to re-forecast unchanged markets).
- Only forecast markets where v1's filter says "consider" (reduces volume).
- Batch API for the historical evaluation (50% discount, async).

### 7.4 Gate for Track B

Apply the locked 6-criteria gate from `src/kalshi_bot_v2/gate.py`:

- C1-C4: standard
- C5: leak-free per-fold retraining (the LLM is the "trainer" in spirit; per-fold means running the LLM forecaster on each fold's test slice without exposing future information)
- C6: LLM-forecaster trade-set beats v1 baseline by >= 2pp on the same holdout

Additional Track-B-specific sanity checks:

- **S-B1 (cutoff leak test)**: run the forecaster on a sample of pre-cutoff markets with two versions of the prompt: (a) full prompt, (b) prompt with all dates redacted to year-only. If the forecasts are very different, the LLM is using date-based memory. Magnitude of difference is the cutoff-leak measurement.
- **S-B2 (price-anchor test)**: run the forecaster WITHOUT the Kalshi price in the prompt. If the resulting probabilities cluster tightly around the price values, the LLM was anchoring; if they're independent estimates, the LLM is adding signal.
- **S-B3 (prompt-sensitivity test)**: rephrase the prompt three different ways and compare forecasts. High variance means the LLM is unreliable; low variance means the prompt is robust.

## 8. Phase structure (parallel where possible)

### Phase 1: parallel research (target 3-4h agent-clock)

Four agents in parallel:

- **Agent V4-A: Polymarket coverage on v1's full universe.** Pull v1's full live universe (all series-prefixes from `data/live_trades/state.json` + the Round 6/7 attempted markets + the v1 backtest dataset's 17 series). For each series-prefix, attempt to match to Polymarket Global via gamma-api.polymarket.com. Quantify match rate per series; build a master table. Output: `research/v4/01-polymarket-coverage.md`, `data/v4/poly_coverage_table.parquet`.

- **Agent V4-B: LLM-forecasting literature review.** Pull recent (2023-2026) papers on LLM forecasting: Halawi et al. 2024 "Approaching Human-Level Forecasting with LM"; Karger et al. 2024 "Forecasting Future World Events with Neural Networks"; Schoenegger 2024 on LLM prediction-market performance; FutureSearch / Phil Tetlock's recent work. Document: what does the literature say is the realistic LLM forecasting accuracy on prediction-market-style questions? Output: `research/v4/02-llm-forecasting-lit.md`.

- **Agent V4-C: LLM-forecaster empirical pilot.** Pick 20-30 Kalshi markets (split: 10 pre-LLM-cutoff for cutoff-leak measurement, 10 post-LLM-cutoff for honest OOS). For each, construct a structured forecast prompt and query Claude Haiku 4.5 (cheap) and Claude Opus 4.7 (capable). Record probability estimates. Compare to Kalshi mid and actual outcome. Compute Brier scores. This is FEASIBILITY DATA, not the full evaluation. Output: `research/v4/03-llm-pilot.md`, `data/v4/llm_pilot_results.parquet`.

- **Agent V4-D: Multi-venue alternative-signal scan.** If Polymarket coverage is low, what other venues could serve as a second opinion? PredictIt (US-legal political), ManifoldMarkets (free API), the-odds-api free tier (sportsbook lines). For each: API status, coverage of v1's universe, cost. Output: `research/v4/04-multi-venue.md`.

### Phase 2: build (depends on Phase 1)

Based on Phase 1 findings, build:

- **Track A module**: `src/kalshi_bot_v4/poly_filter.py` + `scripts/v4/run_poly_filter_backtest.py` + retrospective backtest doc.
- **Track B module**: `src/kalshi_bot_v4/llm_forecaster.py` + `scripts/v4/run_llm_gate.py` + holdout evaluation doc.

Track A and Track B can be built in parallel by separate agents.

### Phase 3: adversarial critic

Style-matched critic for both tracks. Specifically tests:
- Track A: coverage realism, filter rule overfitting, retrospective backtest leak
- Track B: cutoff-leak, price-anchoring, prompt sensitivity, cost realism

### Phase 4: iterate

Per operator: "ensure you are not giving up before you attack all possible angles." If a track's first design fails the critic, iterate the design (different prompt, different model, different filter threshold, different venue) BEFORE declaring null. Document each iteration in iterations.md.

### Phase 5: final verdict

`research/v4/FINAL-VERDICT.md`. For each track: PASS, NULL, or PARTIAL with what was learned.

## 9. Data and infrastructure

Already available from v2/v3:
- READ-scope Kalshi client + `.env`
- `data/v3/probe_inventory_all_markets.parquet` (n=2828 historical markets, 100 series)
- Polymarket public-search code at `scripts/v3/poly_kalshi_divergence.py`
- v2 gate code at `src/kalshi_bot_v2/gate.py`
- Live attempted-orders log at `data/live_trades/state.json` (34 orders, 19 series)

New infrastructure for v4:
- Anthropic API key: assume the user's environment has it OR confirm with operator. Cost guard: total LLM spend < $20 for the v4 research run (estimated ~$15 budget at Haiku, with Opus for spot-checks).

## 10. Operator authorizations needed

Same as v3 (no new operator action required for the research run itself):
- Free public APIs OK
- READ-scope Kalshi OK
- Anthropic API: clarify-if-needed but assume v4 can use it for research

Operator must NOT need to approve before each LLM call. Budget is constrained by Track B Section 7.3 pivots.

Operator-confirmation required BEFORE:
- Any live trade
- Modifying `.env` or v1 config
- Spending money on paid data tiers (NO paid data planned in v4 research run)

## 11. Failure-mode handling

Per operator's explicit instruction: "ensure you are not giving up before you attack all possible angles and make all possible pivots and improvements."

Specific pivots already enumerated for each track (Sections 6.3 and 7.2/7.3). Each iteration logged. Only declare null after exhausting documented pivots, AND with a critic pass confirming the null is honest.

## 12. Time budget

Approximately 8-10 agent-hours.

- Phase 1 parallel: 3-4h
- Phase 2 build: 3-4h (Track A + Track B independent)
- Phase 3 critic: 1-1.5h
- Phase 4 iterate: 1-2h
- Phase 5 verdict: 0.5-1h

Total ~9-12h. If we approach the upper limit and one track is clearly bottoming out, decide whether to keep iterating that track or accept a partial verdict.

## 13. Decision log

Orchestrator appends decisions here as the run progresses.

- 2026-05-24 (Iter 0): v4 master plan written. Phase 1 four-agent fan-out queued. v1 bot untouched.
- 2026-05-24 (Iter 1): Phase 1 returned. v1-universe Polymarket coverage 42.6% (partial-filter band). LLM pilot at n=10 shows honest-OOS Brier skill +0.29 to +0.32 with CI touching zero. Surprise V4-D finding: internal Kalshi cross-market consistency violations (NFL win-total monotonicity, 6 of 6 resolved cases right). New Track A2 added. Phase 2 splits into V4-E (Track A1 + A2 unified filter build) and V4-F (Track B LLM-forecaster expanded sample). Detail in `iterations.md` Iter 1.
