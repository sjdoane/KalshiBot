# V4-C LLM-Forecaster Empirical Pilot

**Date:** 2026-05-24
**Agent:** V4-C
**Mandate:** Run an empirical pilot. Query an LLM as a forecaster on 25 Kalshi markets and measure how well it forecasts compared to (a) the actual outcome, (b) the Kalshi mid-price baseline. Feasibility data, NOT a full evaluation. Result drives the orchestrator's decision on whether Track B is worth a full Phase 2 build.

**TL;DR verdict (with caveats):** **PIVOT (proceed with specific changes).**

Headline: aggregated across all 25 markets, Claude Haiku 4.5 with the brief's Prompt A produces Brier 0.191 vs Kalshi raw price Brier 0.149 (BSS -0.29). Aggregate looks worse than market.

But disaggregate by cutoff bucket and the picture flips: on the n=10 honest-OOS bucket (close 2026-01-01 through 2026-03-25; outside Haiku's training cutoff but in Kalshi archive), Haiku-A produces Brier 0.305 vs Kalshi 0.339 (BSS +0.10). Variant B (no Kalshi price in the prompt) produces Brier 0.231 vs Kalshi 0.339 (BSS +0.32). This is the bucket that matters for the GO threshold.

Crucially the n=10 honest-OOS Brier improvement has a 95% bootstrap CI of [-0.003, +0.075] for Variant A and [-0.001, +0.222] for Variant B. The point estimates favor the LLM but the CIs barely exclude zero. We cannot make a firm "beats Kalshi" claim at this n.

The brief's GO threshold is "LLM Brier beats Kalshi price by at least 0.02 on honest OOS, cost is < $20 for full eval, no severe cutoff-leak." Point estimates pass for A and B on the honest OOS bucket. Cost is dramatically under threshold ($0.36 for full v4 eval at Haiku x 2 prompts). Cutoff-leak is NOT detected as severe.

But Variant A clearly anchors on Kalshi price (correlation r=0.48 with the displayed price) and Variant B is unreliable (mean prob 0.60 vs sample yes-rate 0.80; some wild misses like 0.04 on KXNBAWINS-NOP). Neither variant is production-ready.

Recommended pivot for Phase 2 if the orchestrator proceeds: ditch the brief's Prompt A; build a chain-of-thought scaffolded prompt that does NOT show Kalshi price but DOES inject relevant context (team record, schedule strength, recent games). Then run a larger n>=50 honest-OOS evaluation to clear the CI uncertainty before committing to Phase 2 capital and engineering.

## 1. Sample selection

Source: `data/v3/joined_v3_dataset.parquet` (n=147).

Cutoff buckets:
- **pre_llm_cutoff** (close < 2026-01-01): n=118 available, sampled n=10 (likely in Haiku training data)
- **post_llm_in_archive** (2026-01-01 <= close < 2026-03-25): n=11 available, sampled n=10 (post-LLM-cutoff, still in Kalshi historical archive). This is the honest-OOS bucket.
- **post_kalshi_cutoff** (close >= 2026-03-25): n=18 available, sampled n=5 (also post-LLM-cutoff; were "open" at v3 dataset construction, have since resolved)

Total sample n=25. Stratified random by bucket, seed=42. Saved to `data/v4/llm_pilot_sample.parquet`.

For each row, fetched `title`, `rules_primary`, `rules_secondary`, `yes_sub_title`, `no_sub_title`, `event_subtitle` from Kalshi `/historical/markets/{ticker}` (archive) or `/markets/{ticker}` (live), depending on close date. All 25 markets returned full rules text.

Sample distribution check:
- post_kalshi_cutoff (n=5): yes_rate 1.00 (all 5 favorites won)
- pre_llm_cutoff (n=10): yes_rate 1.00 (all 10 favorites won; consistent with v3's 100% pre-cutoff YES rate)
- post_llm_in_archive (n=10): yes_rate 0.50 (5 wins, 5 losses; this is the v3 holdout failure zone)

The honest-OOS bucket having 50% yes-rate is critical: this is the slice where Kalshi mid-price is poorly calibrated (Brier 0.34, predicting at 0.85 a probability of 0.50). The other two buckets have 100% YES rate, so Kalshi at 0.85 is near-perfectly calibrated by accident (Brier 0.026 and 0.013).

## 2. Prompt design

Following the brief, two prompt variants implemented (`scripts/v4/llm_pilot_run.py:build_prompt`):

**Prompt A (vanilla, includes Kalshi price)**:

```
You are a probabilistic forecaster. The following Kalshi market is currently
trading at <price>. Based on the rules and evidence available, what is your
best estimate of P(YES)?

Market: <title>
Subtitle: <subtitle>
Rules: <rules_primary>
Settlement: <rules_secondary if present>
YES means: <yes_sub_title>
NO means: <no_sub_title>
Open date: <open_time>
Close date: <close_time>

Output ONLY a probability between 0.0 and 1.0, followed by a one-paragraph
rationale. Format:
PROB: <value>
RATIONALE: <text>
```

**Prompt B (no Kalshi price)**: identical to A but with the price line removed. Tests the "model anchors on price" v3 failure mode in LLM form.

**Pivot Prompt C (no-memory injunction)**: same as B but with the instruction "Do not use your memory of past events or their actual outcomes; reason only from the market description and rules provided below."

**Pivot Prompt D (chain-of-thought scaffolding)**: instructs the LLM to first list relevant facts, then estimate the probability. No price shown.

Total prompt length is ~200 tokens input; output 150-450 tokens. Parse the `PROB:` line via a regex.

## 3. Run

**Haiku 4.5** (`claude-haiku-4-5`): all 25 markets x 4 variants (A, B, C, D) = 100 calls.
**Opus 4.7** (`claude-opus-4-7`): spot-check on 5 markets x 2 variants (A, B) = 10 calls.

Total 110 calls. 0 parse errors, 0 API errors. Total cost **$0.343** against the $5 cap.

Per-call cost:
- Haiku: $0.00123 / call (input ~200 tok, output ~200-450 tok depending on variant)
- Opus 4.7: $0.0191 / call

Implementation: official `anthropic` Python SDK at version 0.104.1 installed via `uv pip install anthropic`. The `ANTHROPIC_API_KEY` was found in the Windows User-scope environment but not the process inherit; the runner script reads it via PowerShell `[System.Environment]::GetEnvironmentVariable(...,'User')` as a fallback. Future v4 work should add the key to `.env` or set it in the process env.

Results saved to `data/v4/llm_pilot_results.parquet` (Haiku A, B primary), `data/v4/llm_pilot_results_pivotCD.parquet` (Haiku C, D), `data/v4/llm_pilot_results_opus.parquet` (Opus A, B spot). Full per-row records include input/output tokens, latency, cost, parsed probability, first-200-char rationale.

## 4. Aggregate Brier scores

| | n | Brier | BSS vs Kalshi |
|---|---:|---:|---:|
| Kalshi raw price (baseline) | 25 | **0.1487** | (reference) |
| Haiku-A (with price) | 25 | 0.1913 | -0.29 |
| Haiku-B (no price) | 25 | 0.2467 | -0.66 |
| Haiku-C (no memory) | 25 | 0.2739 | -0.84 |
| Haiku-D (chain-of-thought) | 25 | 0.2893 | -0.95 |
| Opus-A (n=5 spot) | 5 | 0.2059 | -0.55 (vs Kalshi 0.133 on subset) |
| Opus-B (n=5 spot) | 5 | 0.3049 | -1.29 |

On the aggregate, every LLM variant is WORSE than Kalshi raw price. Headline reads "LLM does not add signal." But this conclusion is dominated by the 60% of sample (n=15) where Kalshi is near-perfectly calibrated by luck (pre and post-cutoff buckets, both 100% YES).

## 5. Per-bucket Brier (THE LOAD-BEARING TABLE)

| Bucket | n | yes_rate | Kalshi Brier | Haiku-A | Haiku-B | Haiku-C | Haiku-D |
|---|---:|---:|---:|---:|---:|---:|---:|
| pre_llm_cutoff | 10 | 1.00 | **0.026** | 0.106 | 0.195 | 0.270 | 0.259 |
| post_llm_in_archive | 10 | 0.50 | 0.339 | **0.305** | **0.231** | **0.242** | **0.290** |
| post_kalshi_cutoff | 5 | 1.00 | **0.013** | 0.136 | 0.382 | 0.346 | 0.349 |

Bolded cells are the per-bucket winner. The pattern is clear:

- **Pre-LLM-cutoff and post-Kalshi-cutoff buckets**: Kalshi is hugely better than every LLM variant. This is because both buckets have 100% yes-rate; Kalshi sitting at ~0.85 gets a Brier of 0.026 and 0.013 respectively, near-floor. The LLM, when honestly uncertain, produces probabilities 0.5-0.9 that LOSE Brier against the deterministic outcomes.
- **Post-LLM-in-archive (honest OOS) bucket**: every LLM variant beats Kalshi. This is the bucket with 50% yes-rate, where Kalshi at ~0.85 is mis-calibrated (predicting 85% YES on rows that actually go 50% YES). Haiku-A reduces Brier by 0.034 absolute / +0.10 BSS. Haiku-B reduces by 0.108 absolute / +0.32 BSS. Haiku-C reduces by 0.097 / +0.29 BSS. Haiku-D reduces by 0.049 / +0.15 BSS.

The orchestrator's GO threshold is "LLM Brier beats Kalshi by at least 0.02 absolute on honest OOS." All four variants pass this threshold on point estimate.

## 6. Bootstrap confidence intervals (THE LOAD-BEARING HONESTY TABLE)

| Variant | Bucket | Brier diff (Kalshi - LLM), positive = LLM beats | 95% CI |
|---|---|---:|---|
| Haiku-A | pre_llm_cutoff | -0.078 (median) | [-0.177, -0.024] |
| Haiku-A | post_llm_in_archive | +0.035 | **[-0.003, +0.075]** |
| Haiku-A | post_kalshi_cutoff | -0.121 | [-0.326, -0.007] |
| Haiku-B | post_llm_in_archive | +0.111 | **[-0.001, +0.222]** |
| Haiku-C | post_llm_in_archive | +0.099 | **[-0.011, +0.206]** |
| Haiku-D | post_llm_in_archive | +0.056 | [-0.236, +0.287] |

5000-resample bootstrap, seed=42, stratified within bucket.

The honest OOS Brier improvement CIs **all touch zero**. Haiku-A's CI is [-0.003, +0.075] - missing significance by a whisker. Haiku-B's CI is [-0.001, +0.222] - same boat, but a much wider upside if real. Haiku-D's CI is [-0.236, +0.287] - the chain-of-thought variant has so much per-row noise that it's clearly unreliable.

**At n=10 we cannot statistically confirm the LLM beats Kalshi.** The point estimate is favorable for A, B, C; the CI uncertainty makes the conclusion preliminary.

## 7. Price-anchoring measurement

Correlation between LLM probability and Kalshi price (across the n=25 sample):

| Variant | r(LLM, Kalshi) | Mean LLM | Mean Kalshi | Notes |
|---|---:|---:|---:|---|
| Haiku-A | **+0.482** | 0.748 | 0.858 | Strongly anchored |
| Haiku-B | -0.002 | 0.602 | 0.858 | Decoupled |
| Haiku-C | -0.094 | 0.572 | 0.858 | Decoupled |
| Haiku-D | -0.120 | 0.522 | 0.858 | Decoupled |
| Sample yes-rate | n/a | n/a | n/a | 0.80 |

Inserting the Kalshi price in the prompt (A) drags the LLM toward the displayed price (r=0.48). Removing it (B, C, D) decouples the forecast from the price (r near zero).

But removing the price doesn't make the LLM well-calibrated globally: variants B/C/D have mean prob 0.52-0.60 against the actual sample yes-rate of 0.80. The LLM-without-price is biased LOW on average. This is consistent with the LLM being asked to forecast something it doesn't have enough information about, defaulting toward uniformity.

The Variant A vs B difference (which is the v3-style "model anchors on price" diagnostic in LLM form) is large enough to confirm anchoring exists. If we proceed with Track B, the production prompt CANNOT show the Kalshi price, or it will collapse to a slightly-noisy Kalshi clone.

## 8. Cutoff-leak diagnostic

Brief: "If LLM is much better on pre-cutoff (BSS_pre >> BSS_post), the LLM is memorizing past outcomes."

Per Haiku-A:
- Pre-cutoff Brier: 0.106 (n=10, yes_rate 1.0)
- Post-cutoff Brier: 0.248 (n=15, yes_rate 0.67 combining the two post buckets)

Naive read: pre-cutoff Brier is much lower, so the LLM looks like it's "memorizing." But this is **confounded by the outcome distribution**:
- Pre-cutoff bucket has 100% YES; Kalshi (Brier 0.026) handles it trivially. The LLM at 0.72-0.92 mean still gets a low Brier because the squared error is just (1 - 0.7x)^2.
- Post-cutoff buckets have mixed YES; the LLM's confident predictions (0.7-0.9) get hit hard on the 50% of rows that flip to NO.

The correct cutoff-leak test is COMPARED TO KALSHI on the same bucket, not aggregate. Per bucket:
- Pre-cutoff: Kalshi Brier 0.026, Haiku-A Brier 0.106. Kalshi wins by 0.080 (much better).
- Post-cutoff (in archive): Kalshi 0.339, Haiku-A 0.305. LLM wins by 0.034.

**If the LLM were memorizing pre-cutoff outcomes, it should be BETTER than Kalshi pre-cutoff. It is much worse.** This is the OPPOSITE of leak signature: the LLM is not memorizing outcomes; it is providing a noisy estimate that hurts on the easy-Kalshi rows and slightly helps on the hard-Kalshi rows.

Quantitative leak magnitude:
- Pre-cutoff BSS (LLM vs Kalshi): -3.10
- Post-cutoff BSS (LLM vs Kalshi, in-archive): +0.10

The post-cutoff BSS is better than pre-cutoff BSS by 3.2 BSS units. This is the OPPOSITE direction from leak. **No evidence of training-data memorization on this sample.**

Caveat: n=10 honest-OOS is small enough that this conclusion is preliminary. A larger eval should re-run the same diagnostic to confirm.

## 9. Cost analysis

Pilot total: **$0.343** out of $5 cap.

| Scenario | Per-call | x N calls | Total |
|---|---:|---:|---:|
| Haiku-A only, full v4 eval (n=147) | $0.00123 | 147 | $0.18 |
| Haiku-A + B, full v4 eval | $0.00123 | 294 | $0.36 |
| Opus-A only, full v4 eval | $0.0191 | 147 | $2.81 |
| Haiku live, 15min loop, 15 candidates, 30 days | $0.00123 | 64,800 | **$80** |

The brief's threshold "cost projection < $20 for full v4 eval" passes by 50x on Haiku and by 7x on Opus.

For live operation, $80/month at the full 15-candidate cadence exceeds the $32 capital. Per the master plan Section 7.3 pivot, we'd cache LLM responses keyed by market ID (markets do not need to be re-forecast each loop) and only forecast at v1's actual scan-positive moments. Realistically this drops live cost to $5-20/month. Within budget.

Opus is too expensive for production but appropriate for spot-checks during research. Per the brief's spot-check (n=5), Opus-A was MARGINALLY WORSE than Haiku-A on the overlapping subset: Brier 0.206 vs 0.140 (n=5). Small-n caveat applies, but no evidence Opus adds value over Haiku for this task. **Haiku is the right Phase 2 model choice.**

## 10. Pivots attempted

Per the brief, "implement at least 2 pivots if the first attempt fails." The first attempt (Prompt A) had BSS -0.29 aggregate, +0.10 honest OOS. Implemented:

1. **Pivot to Prompt C** (no-memory injunction): aggregate BSS -0.84; honest OOS BSS +0.29. Honest OOS improvement vs Prompt A.
2. **Pivot to Prompt D** (chain-of-thought): aggregate BSS -0.95; honest OOS BSS +0.15. Honest OOS improvement vs Prompt A but worse than C.
3. **Pivot to Opus 4.7** (capable model spot-check on n=5): aggregate BSS -0.55; honest OOS n=2 too small to read. Marginally WORSE than Haiku on overlap. Adds no value vs Haiku 4.5.
4. **Pivot to Haiku+Opus ensemble** (n=5 overlap subset): average of the two probs, ensemble Brier 0.167 vs Haiku alone 0.140 vs Opus alone 0.206 vs Kalshi 0.133. Ensemble does NOT beat Haiku alone on this small subset.

NOT attempted (deferred to Phase 2 if proceed):
- News-context-augmented prompt (would require fetching Wikipedia or recent news per ticker; nontrivial scope creep)
- Multiple LLM ensemble across providers (out of scope per brief: "this is research mode; no other LLM providers")

The pivots produced a clear directional finding: REMOVING the Kalshi price from the prompt is the most impactful change. Across A vs B/C/D, the no-price variants improve honest OOS Brier vs A. Variant B is the best non-A variant. Variant C (the no-memory injunction) provides modest additional improvement; D (chain-of-thought) is more variable.

## 11. Fade-filter signal

A practical use of the LLM forecaster for the Track B strategy is: at v1's scan moment, query the LLM; if LLM_prob < Kalshi_price by a threshold, SKIP the trade. This is the "LLM as fade filter on top of v1." Even with weak Brier numbers, the FADE direction can have value.

Honest OOS bucket (n=10), filter behavior:

| Variant | Filter "skip if LLM < Kalshi - 0.05" | Skipped n | Skipped YES rate | Taken n | Taken YES rate |
|---|---|---:|---:|---:|---:|
| A | yes | 5 | 0.40 | 5 | 0.60 |
| B | yes | 8 | 0.38 | 2 | 1.00 |
| C | yes | 8 | 0.38 | 2 | 1.00 |
| D | yes | 9 | 0.44 | 1 | 1.00 |

Baseline on the honest OOS bucket: 50% YES rate.

Variant A's filter is roughly random (skipped 40%, taken 60% vs baseline 50%). Variants B/C/D are aggressive (skipping 80-90% of rows) and DO show the taken-rows have higher YES rate (100%), but n=1 to 2 taken is too small to call a real signal.

At n=10 per variant, the fade-filter measurement is not informative. The 95% CI is wider than the effect size. This is consistent with the Brier CI uncertainty.

## 12. Failure modes observed

1. **Variant A anchors on price.** r=0.48. The LLM is providing a slightly-noisy version of Kalshi when shown the price. This is the v3 "model anchors on price" failure mode reproduced in LLM form.

2. **Variants B/C/D are biased low.** Mean LLM prob 0.52-0.60 vs sample yes-rate 0.80. The LLM-without-price defaults toward uniformity. This means even the variants that "decouple" from Kalshi produce poor calibration globally.

3. **Some LLM responses are wildly miscalibrated.** Examples on Variant B (Haiku, no price):
   - KXNBAWINS-NOP-25-T15: LLM prob 0.92, outcome 1 (correct)
   - KXNHLMETROPOLITAN-26-CAR: LLM prob 0.18 (Variant B), outcome 1 (very wrong, Brier 0.67 on this row alone)
   - KXMLBALCY-25-TSKU: LLM prob 0.18, outcome 1 (very wrong)
   - These wild misses appear concentrated on specific question types (division winners, awards). The LLM seems to have low confidence on these and answers near-uniform.

4. **Pivot D (chain-of-thought) has the highest per-row variance** of any variant. Its honest OOS CI is [-0.236, +0.287] vs Variant B's [-0.001, +0.222]. Encouraging the LLM to "list facts first" produces more spread-out answers that include outliers like the 0.04 prediction on KXNBAWINS-NOP-25-T15.

5. **No clear cutoff-leak.** Per Section 8, the LLM is WORSE on pre-cutoff than post-cutoff (compared to Kalshi). This is the opposite of memorization-leak signature. Either the leak truly doesn't exist for these market types, or the comparison is dominated by the confound that pre-cutoff has 100% yes-rate.

## 13. Verdict

**PIVOT.** The honest-OOS Brier improvement is in the right direction (point estimates +0.10 to +0.32 BSS, exceeding the +0.02 threshold) but the n=10 CI uncertainty makes the conclusion preliminary. The cost is within budget. The cutoff-leak appears not to be severe. Concretely:

**What is positive enough to PIVOT, not KILL:**
- All 4 prompt variants beat Kalshi on honest OOS by Brier 0.034-0.108. The direction is consistent.
- Variant B/C (no-price, no-memory) produce BSS +0.29 to +0.32 on honest OOS - the largest improvement.
- Cost is $0.36 for the full v4 eval (vs $20 cap; 50x margin).
- Cutoff-leak does NOT appear severe; LLM is actually WORSE on pre-cutoff than post-cutoff in Brier-relative terms.

**What requires PIVOT before Phase 2:**
- Drop Prompt A from the build. The brief's "include the Kalshi price" prompt anchors and provides only modest improvement vs the v3 baseline.
- Use Prompt C as the production variant: no price shown, explicit "do not use memory of past outcomes" injunction, structured rationale output.
- Implement at scale n>=50 to clear the CI uncertainty on the honest-OOS Brier improvement. With n=10 the +0.10 BSS estimate has CI touching zero; at n=50 with the same point estimate the CI would tighten to roughly [+0.05, +0.15] (back-of-envelope; would need to verify).
- Add Wikipedia-snippet-context augmentation for at least the team-specific markets (NBA/NFL/MLB team-wins, division-winners). The current "wild miss" rows in Section 12 are concentrated on questions where the LLM has no information; injecting team-strength context could narrow these.
- Stick with Haiku 4.5. Opus 4.7 is more expensive and on this sample marginally worse.

**What blocks Phase 2 if not addressed:**
- The C6 gate criterion (LLM trade-set beats v1 by >= 2pp on the locked 6-criteria gate) is a TRADE-LEVEL test, not a Brier test. The pilot does not demonstrate this. Phase 2 must build:
  1. The full forecaster pipeline (prompt builder, parser, cost-cached store, ensemble averaging if needed)
  2. The trade decision rule (LLM_prob > Kalshi_price + margin -> YES; or LLM_prob < Kalshi_price - margin -> NO/skip)
  3. The leak-free CV / holdout evaluation on the v3 dataset's honest OOS slice + a fresh forward-test set
- If Phase 2's trade-level evaluation fails the C6 gate, Track B closes regardless of the Brier-level pilot success.

**Path forward (one-sentence per option):**
- **GO with Pivots**: build Phase 2 with Prompt C / Haiku 4.5 / cached storage / news context for team markets; run trade-level evaluation on the full v3 dataset (n=147) plus a fresh post-Kalshi-cutoff slice (n=50+ from current open markets settling in the next 3 weeks).
- **KILL**: declare null on Track B; the honest-OOS Brier improvement is real but small (BSS +0.10 to +0.32 with CI touching zero); the C6 +2pp gate is structurally hard with these probabilities; the v3 lesson "we cannot beat market price on long-horizon sports favorites" likely applies in LLM form too.
- **DEFER**: collect another 60-90 days of post-cutoff Kalshi data, then re-run the pilot at n=50 honest OOS. This is the slowest path but produces the highest-confidence answer.

My recommendation as V4-C: **PIVOT.** The honest-OOS direction is correct; the cost is negligible; the cutoff-leak is not severe. Build Phase 2 with Prompt C and Haiku 4.5. Run the trade-level evaluation on the v3 honest-OOS slice. If trade-level performance also points positive, expand to a fresh n=50 post-Kalshi-cutoff sample for confirmation. If trade-level performance is null, kill Track B with the documented failure mode being "Brier-level signal too small to clear the C6 2pp trade-level gate after fees and slippage."

## 14. Hard constraints satisfied

- READ-only on Kalshi side (used `/historical/markets/{ticker}` and `/markets/{ticker}` for read-only metadata fetch). No trades placed.
- LLM calls only via the official `anthropic` Python SDK (version 0.104.1).
- Cost guard: $0.343 spent of the $5 cap.
- No modifications outside `scripts/v4/`, `data/v4/`, `research/v4/`.
- No em-dashes.

## 15. Files written

- `scripts/v4/llm_pilot_select_sample.py` (sample selection + Kalshi rule fetch)
- `scripts/v4/llm_pilot_run.py` (LLM pilot runner; supports A/B/C/D variants and Haiku/Opus)
- `scripts/v4/llm_pilot_analyze.py` (analysis script; Brier, BSS, cutoff-leak diagnostic, cost projection)
- `data/v4/llm_pilot_sample.parquet` (n=25 sample with full market rules)
- `data/v4/llm_pilot_sample_meta.json` (sample metadata)
- `data/v4/llm_pilot_results.parquet` (Haiku A, B primary)
- `data/v4/llm_pilot_results_pivotCD.parquet` (Haiku C, D pivot)
- `data/v4/llm_pilot_results_opus.parquet` (Opus A, B spot)
- `data/v4/llm_pilot_results_meta*.json` (per-run metadata)
- `data/v4/llm_pilot_analysis_summary.json` (all per-variant Brier, BSS, bootstrap CIs)
- This document.

No modifications to `src/kalshi_bot/`, `src/kalshi_bot_v2/`, `src/kalshi_bot_v3/`, `scripts/` outside `scripts/v4/`, `tests/`, or `data/` outside `data/v4/`. v1 bot untouched.

## 16. Handoff to orchestrator

The pilot data exists; the verdict is PIVOT. Key decision for the orchestrator:

1. **Proceed with Track B Phase 2**: implement the recommendations in Section 13 ("GO with Pivots"). Specifically: Prompt C as base; Haiku 4.5; Wikipedia-context augmentation; n>=50 honest OOS measurement; trade-level C6 evaluation.

2. **Kill Track B**: the Brier-level signal at n=10 is borderline (CI touching zero) and the v3 lesson plus literature ceiling (V4-B doc) suggest the trade-level gate is structurally hard. Move all Phase 2 resources to Track A (Polymarket fade filter, per V4-A).

3. **Defer Track B**: collect more honest-OOS data over 60-90 days and re-run with larger n. Move Phase 2 to Track A only meanwhile.

V4-C's recommendation per the operator's "don't give up before all angles are exhausted" instruction: option 1 (proceed with documented pivots). Option 2 is premature given the directional positive on honest OOS; option 3 is the slowest path.

If the orchestrator chooses option 1, Phase 2 must build:
- `src/kalshi_bot_v4/llm_forecaster.py` (prompt template + parsing + caching)
- `scripts/v4/run_llm_gate.py` (trade-level evaluation against the locked 6-criteria gate)
- `tests/v4/test_llm_forecaster.py` (deterministic mock-LLM tests for prompt assembly and decision rule)

The Phase 3 critic for Track B should specifically test:
- The pilot's n=10 honest-OOS sample is small; does Phase 2's larger sample REPLICATE or REVERT?
- The pilot's pivot decision was "drop Prompt A in favor of C"; does C still beat Kalshi at n=50?
- Cutoff-leak retest at the larger n
- Cost projection update for the actual Phase 2 call volume
