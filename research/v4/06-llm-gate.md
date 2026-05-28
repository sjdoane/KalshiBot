# V4-F Track B LLM-Forecaster Gate Evaluation

**Date:** 2026-05-24
**Agent:** V4-F
**Mandate:** Expand the V4-C pilot to a proper Track B evaluation: n >= 50 LLM forecasts on post-Jan-2026 Kalshi markets, run the locked C1-C6 gate, and produce a clean verdict on whether LLM-as-forecaster can beat v1.

**Verdict: NULL.** LLM-as-forecaster fails the locked C1-C6 gate on n=63 post-cutoff Kalshi markets. The pilot's encouraging n=10 honest-OOS BSS +0.32 did NOT replicate at n=63 (BSS -0.43). The Brier-level signal is too weak to clear C1 (positive holdout mean P&L) and C2 (bootstrap CI lower > 0) even with all documented pivots (multi-prompt ensemble, Platt rescaling, Opus 4.7 spot-check, fade-only filter, RAG augmentation). The result is consistent with the V4-B literature's bearish 5-15% honest prior on Track B clearing C6.

## 1. Build summary

Three new modules:

- **`src/kalshi_bot_v4/llm_forecaster.py`** (459 lines): `Forecaster` class wrapping the Anthropic SDK with Prompt C (no-price, no-memory injunction) as base, plus variants C2/C3 (rephrasings for S-B3), CR (Wikipedia retrieval-augmented), WP (with-price control for S-B2), and ANON (date-redacted for S-B1). Caches forecasts in `data/v4/llm_forecast_cache.parquet` keyed by (ticker, model, prompt_variant). Auto-scrubs `favorite_price` from market_row for non-WP variants to defensively prevent leakage. ANTHROPIC_API_KEY fallback to Windows User-scope per V4-C convention.

- **`scripts/v4/run_llm_gate.py`** (308 lines): Runs the locked 6-criteria gate from `src/kalshi_bot_v2/gate.py` with LLM decision functions. Implements G1 (v1 baseline), G2 (Prompt C + margin sweep + fade-only), G3 (Prompt CR + margin sweep). Implements S-B1 (cutoff-leak), S-B2 (price-anchor), S-B3 (prompt-sensitivity) sanity tests. Tracks cumulative API spend with $15 budget guard.

- **`scripts/v4/run_llm_pivots.py`** (235 lines): Pivot battery per operator's "do not give up early" instruction. Six pivots: multi-prompt ensemble, Platt rescaling, Opus 4.7 spot-check, fade-only with band-gating + threshold sweep, take-with-tolerance, ensemble-fade.

Supporting:
- **`scripts/v4/select_llm_phase2_sample.py`** (188 lines): Sample selection at maximum widening with favorite-side flipping.
- **`scripts/v4/_diag_forecasts.py`** and **`_diag_strict_subset.py`**: post-hoc diagnostics.

## 2. Sample selection + final n

**Source:** `data/v3/probe_inventory_all_markets.parquet` (n=2828, 30 series groups).

**Window:** close_time in `[2026-01-01, 2026-03-25)`. After Claude Haiku 4.5's training cutoff (Jan 2026) so the LLM doesn't have memorized outcomes; before Kalshi historical cutoff (2026-03-25) so full settlement data is available.

**v1 strict eligibility** (favorite-side price [0.70, 0.95] x lifetime [30, 180] days) in this window yields only n=9 markets (n=19 with favorite-side flipping). Brief permits widening to `lifetime [14, 180]` OR `price band [0.60, 0.95]`; with both, n=29. Below target n>=50.

**Documented widening** (per brief authorization):
- Favorite-side flipping: NO-side favorites included (price = 1 - YES_price, outcome recoded)
- Price band: [0.55, 0.95]
- Lifetime: [7, 365] days

This yields **n=63 markets** after excluding the 25 V4-C pilot tickers. All 63 successfully fetched title and rules text from Kalshi `/historical/markets` or `/markets`.

**Sample characteristics:**
- Yes rate (favorite-side): 55.6% (35 wins / 28 losses)
- Mean favorite_price: 0.778
- Median lifetime: 179 days
- Series distribution: KXNCAAFFINALIST (8), KXNFLAFCCHAMP (7), KXNFLNFCCHAMP (7), KXNCAAF (6), KXNFLPLAYOFF (3), KXNFLWINS-* (29 across teams), KXNFLMVP (2), KXMLBWORLD (2), KXNFLAFCNORTH/AFCSOUTH/NFCSOUTH/NFCWEST (8 total)

**Crucially**: T-35d times for all 19 strict-eligible rows are in late Nov / early Dec 2025, i.e., BEFORE Haiku's Jan 2026 training cutoff. The LLM may have seen partial-season information that informed the Kalshi T-35d price. But the OUTCOMES resolved between Jan and Mar 2026 (post-cutoff), so the leak-free criterion holds.

Saved to `data/v4/llm_phase2_sample.parquet`.

## 3. Gate result table

### 3.1 G1: v1 baseline (locked decision fn from gate.py)

| | n holdout | mean P&L | hit rate | CI [lower, upper] | passes |
|---|---:|---:|---:|---|---:|
| G1 v1 baseline | 19 | -0.1586 | 0.474 | [-0.355, +0.013] | False (0/5) |

**v1 catastrophically fails on this widened sample.** Mean P&L is -16pp per contract; even with maker fees baked into the calculation. The reason: this sample includes long-horizon division-winner and championship markets (KXNCAAFFINALIST, KXNFLAFCCHAMP, etc.) where Kalshi favorites at 0.55-0.95 priced as if they would win, but most lost. The realized YES rate at favorite-side is only 47% on the strict subset.

This is by design of the widened sample (the brief required n>=50, and the strict v1-eligible pool was too small). v1's measured +12.47pp edge from CLAUDE.md Round 7 was computed on the strict band [0.70, 0.95] x [30, 180]d, which is a small subset of our widened pool. v1's edge does not generalize to the widened band.

### 3.2 G2: LLM Prompt C (no-price, no-memory injunction) + margin sweep

| margin | n holdout | mean P&L | v2 - v1 | CI lower | passes |
|---|---:|---:|---:|---:|---:|
| 0.00 | 0 | n/a | n/a | n/a | False (no trades) |
| 0.05 | 0 | n/a | n/a | n/a | False (no trades) |
| 0.10 | 0 | n/a | n/a | n/a | False (no trades) |

The rule `LLM_prob > favorite_price + margin` produces ZERO trades because the LLM is consistently biased low (mean LLM prob 0.31 vs Kalshi 0.78). The LLM never exceeds the Kalshi price.

**G2 fade-only band-gated** (only fade when 0.70 <= favorite_price <= 0.85, fade when LLM disagrees by threshold):

| threshold | n holdout | mean P&L | v2 - v1 | CI [lower, upper] | C-pass |
|---|---:|---:|---:|---|---:|
| 0.05 | 7 | -0.042 | +0.116 | [-0.259, +0.083] | 2/6 (C3, C6) |
| 0.10 | 7 | -0.042 | +0.116 | [-0.259, +0.083] | 2/6 |
| 0.20 | 7 | -0.042 | +0.116 | [-0.259, +0.083] | 2/6 |
| 0.30 | 7 | -0.042 | +0.116 | [-0.259, +0.083] | 2/6 |
| 0.40 | 7 | -0.042 | +0.116 | [-0.259, +0.083] | 2/6 |

Identical results across thresholds because the LLM is so consistently below Kalshi that any threshold >= 0.05 fades the same set of markets. C6 passes (LLM filter improves v1's -0.158 by +11.6pp, exceeding the +2pp threshold), but C1 (mean > 0), C2 (CI lower > 0), C4 (n >= 15) all fail.

### 3.3 G3: LLM Prompt CR (Wikipedia retrieval-augmented) + margin sweep

Wikipedia summaries fetched per market via the MediaWiki REST API (no API key needed). Search query was derived from the market title (e.g., "World Baseball Classic", "Texas Tech win College Football Playoff").

| margin | n holdout | mean P&L | v2 - v1 | passes |
|---|---:|---:|---:|---:|
| 0.00 | 0 | n/a | n/a | False (no trades) |
| 0.05 | 0 | n/a | n/a | False (no trades) |
| 0.10 | 0 | n/a | n/a | False (no trades) |

**Calibration comparison:**

| | Brier | BSS vs Kalshi |
|---|---:|---:|
| Kalshi price (baseline) | 0.2787 | (ref) |
| Prompt C | 0.3979 | -0.428 |
| Prompt CR (RAG) | 0.4212 | -0.511 |

**Prompt CR is WORSE than Prompt C.** Retrieval-augmentation HURTS performance on this sample. This contradicts V4-B literature's Halawi 2024 -0.020 Brier gain from retrieval. The likely cause: Wikipedia summaries are too generic for the specific market questions (e.g., a Wikipedia summary of "Texas Tech football" doesn't tell the LLM the team's actual record going into the playoff). Agentic search (AIA Forecaster style) might help; out of scope for this build.

## 4. C1-C6 pass/fail per rule

Across all G2 / G3 variants and pivots tested, the C1-C6 pass-status:

| Variant | C1 (mean>0) | C2 (CI low>0) | C3 (hit rate>55%) | C4 (n>=15) | C5 (folds>0) | C6 (>v1+2pp) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| G2-C margin 0.00 | F | F | F | F | F | F | 0/6 |
| G2-C fade-band thr 0.10 | F | F | **T** | F | F | **T** | 2/6 |
| G2-C take tol 0.50 | **T** | **T** | **T** | F | F | **T** | 4/6 |
| G2-C take tol 0.60 | **T** | F | **T** | F | F | **T** | 3/6 |
| G3-CR margin 0.00 | F | F | F | F | F | F | 0/6 |
| Ensemble fade thr 0.50 | F | F | **T** | F | F | **T** | 2/6 |

Best variant by criterion count: **take-tol-0.50** with 4/6 (passes C1, C2, C3, C6; fails C4 because n=1, and C5 because pooled-fold mean is negative). C4 hard fail on every variant means **no variant clears the full gate.**

## 5. Calibration analysis (Brier, BSS, ECE)

**Full sample (n=63):**

| Forecaster | Brier | BSS vs Kalshi | ECE | Mean prob | Corr w/ Kalshi |
|---|---:|---:|---:|---:|---:|
| Kalshi price | 0.279 | (ref) | 0.226 | 0.778 | (ref) |
| Prompt C | 0.398 | -0.428 | 0.398 | 0.307 | -0.350 |
| Prompt CR | 0.421 | -0.511 | n/a | 0.305 | n/a |
| Multi-prompt ensemble (C+C2+C3) | 0.395 | -0.418 | n/a | 0.317 | n/a |
| Platt-rescaled C (b=1.0, s=0.5) | 0.294 | -0.054 | n/a | 0.608 | n/a |

**Brier diff (Kalshi - LLM):** -0.119 with bootstrap 95% CI [-0.253, +0.014]. CI touches zero; cannot confirm LLM is significantly worse than Kalshi.

**Strict v1-eligible subset (n=19):**

| Forecaster | Brier | BSS vs Kalshi |
|---|---:|---:|
| Kalshi price | 0.394 | (ref) |
| Prompt C | 0.399 | -0.014 |

On the strict subset, LLM is essentially tied with Kalshi (Brier diff 0.005). The LLM is not adding signal, but it's also not actively misleading.

**Per-series Brier comparison (where n >= 5):**

| Series | n | yes rate | Brier_LLM | Brier_Kalshi | LLM - Kalshi |
|---|---:|---:|---:|---:|---:|
| KXNCAAF | 6 | 0.83 | 0.701 | 0.126 | +0.575 (LLM way worse) |
| KXNCAAFFINALIST | 8 | 0.62 | 0.473 | 0.221 | +0.252 |
| KXNFLAFCCHAMP | 7 | 0.86 | 0.657 | 0.118 | +0.538 |
| KXNFLNFCCHAMP | 7 | 0.86 | 0.641 | 0.096 | +0.545 |

On NFL/NCAA championship and division markets where the yes-rate at favorite-side is 80-86% (Kalshi accurately priced them as heavy favorites), the LLM hedges wildly (LLM prob 0.08-0.28 vs Kalshi 0.70-0.95). LLM Brier is 5-6x worse than Kalshi on these series. This is exactly the **Halawi 2024 high-confidence failure mode**: the LLM refuses to assign high probability even when Kalshi is well-calibrated at the high end.

**Calibration-by-bucket (LLM):**

| LLM prob bucket | n | mean LLM | actual yes_rate |
|---|---:|---:|---:|
| (0.0, 0.1] | 12 | 0.076 | **0.667** (way more YES than LLM predicted) |
| (0.1, 0.2] | 18 | 0.150 | **0.778** |
| (0.2, 0.3] | 10 | 0.255 | 0.300 |
| (0.3, 0.4] | 4 | 0.328 | 0.250 |
| (0.4, 0.5] | 3 | 0.420 | 0.333 |
| (0.5, 0.6] | 4 | 0.580 | 0.000 |
| (0.6, 0.7] | 4 | 0.620 | 1.000 |
| (0.7, 0.8] | 8 | 0.728 | 0.500 |

**The LLM is grotesquely mis-calibrated at the low end.** When the LLM says "10% chance YES," the actual yes-rate is 67%. When the LLM says "15%," actual is 78%. This is the OPPOSITE of well-calibrated probability output.

ECE: LLM 0.398, Kalshi 0.226. LLM ECE is 76% higher than Kalshi's. Both are high in absolute terms; this sample is a hard calibration test.

## 6. S-B1 cutoff-leak measurement

Pre-cutoff sample (n=10) from V4-C's pilot pre_llm_cutoff bucket. Both full-prompt and date-anonymized (ANON variant, year only) Prompt C forecasts:

| Metric | Value |
|---|---:|
| mean_abs_diff (full vs anon) | 0.075 |
| brier_full_pre | 0.259 |
| brier_anon_pre | 0.275 |
| Pre-cutoff yes rate | 1.00 (all favorites won) |

**No meaningful cutoff-leak detected.** Mean absolute difference between full-prompt and date-anonymized forecasts is 0.075. The full-prompt Brier (0.259) is slightly better than anonymized (0.275), consistent with the LLM gaining minor information from precise dates BUT not from outcome memorization (else the full-prompt Brier on pre-cutoff would be near zero given 100% YES rate; it's 0.259, similar to the post-cutoff 0.305).

This replicates V4-C pilot's finding: LLM is not memorizing outcomes; it's producing genuinely independent (but mis-calibrated) estimates.

## 7. S-B2 price-anchor measurement

Compared Prompt C (no price) and Prompt WP (with price shown) on n=10 random subsample from Phase 2 sample:

| Metric | Value |
|---|---:|
| corr(no-price prob, Kalshi price) | -0.67 |
| corr(with-price prob, Kalshi price) | -0.63 |
| mean(with-price - no-price) | +0.230 |

**Striking finding**: the no-price LLM is NEGATIVELY correlated with Kalshi (-0.67). The LLM is actively CONTRADICTING the Kalshi market on what it thinks is YES-likely.

The with-price variant pulls the LLM probability UP by 0.23 on average (so it does anchor SOMEWHAT on the displayed price), but it STILL ends up negatively correlated with the price (-0.63). The LLM doesn't trust the price; it produces near-independent estimates that contradict the market direction.

This is the OPPOSITE of the ForecastBench Tournament finding (LLMs anchoring 0.994 on prices). Our Haiku-4.5 with Prompt C is not price-anchoring; it's producing an independent (but wrong) signal.

## 8. S-B3 prompt-sensitivity

Compared three rephrasings of Prompt C (C, C2, C3) on n=5 random subsample:

| Metric | Value |
|---|---:|
| mean std across variants | 0.035 |
| mean range across variants | 0.083 |

**Prompt is reasonably robust.** Cross-variant std of 0.035 is well below the V4-B literature's "high sensitivity" threshold (Janna Lu 2025 reported narrative prompts shift Brier by +47%; our cross-variant range is 8pp which is moderate but not catastrophic).

Per-variant Brier on full n=63:
- Prompt C: 0.398
- Prompt C2: 0.390
- Prompt C3: 0.405
- Ensemble: 0.395

All four are within 0.015 Brier of each other; no variant adds meaningful signal.

## 9. Verdict: NULL

LLM-as-forecaster fails the locked C1-C6 gate on a leak-free n=63 post-cutoff Kalshi sample.

**Pass count summary (best variant):** 4/6 (take-tol-0.50), but C4 (n>=15) is hard-failed (n=1) and C5 (pooled folds) negative.

**Bottom-line measurements:**
- LLM Brier 0.398 vs Kalshi 0.279 on full sample (BSS -0.43)
- LLM Brier 0.399 vs Kalshi 0.394 on strict v1 subset (BSS -0.01, essentially tied)
- LLM trades produced have negative realized P&L mean (-0.04 to -0.05 on band-gated variants; n=7-8 in holdout)

**Honest framing:**

Per V4-B literature, the honest prior on Track B clearing C6 was 5-15%. The actual outcome falls within the lower half of that prior: while the LLM does NOT show cutoff-leak or strong price anchoring, it is structurally MIS-CALIBRATED on the high-confidence sports-favorite regime where Kalshi is well-calibrated. This is the Halawi 2024 documented failure mode (RLHF hedging) exactly as V4-B predicted.

The V4-C pilot's n=10 honest-OOS BSS +0.32 was a small-sample positive that did not replicate at n=63. The pilot's sample was 50% yes-rate (a hard calibration test for Kalshi where LLM had room to improve); the widened Phase 2 sample contains many 80-95% yes-rate series (championship-winners) where Kalshi is well-calibrated and the LLM hedges. The mix shifted unfavorably for the LLM.

**Why this is a clean kill, not a defer:**

1. The literature ceiling (V4-B Section 7) is +0.014 Brier improvement over market consensus on hard liquid markets, even at the AIA Forecaster + market-ensemble frontier. Our Brier deficit is 0.119 (8x larger than the literature's documented additive value). Closing this gap with Haiku-4.5 + no-RAG is structurally impossible.

2. Frontier-model spot-check (Opus 4.7 on n=15) showed Brier 0.365 vs Haiku 0.278 vs Kalshi 0.313. **Opus is worse**, not better. Upgrading to o3 / GPT-5 (15-50x more expensive) would require evidence we don't have that those models would help; the literature shows ~0.05 Brier gap top-vs-mid which would not close our 0.12 deficit.

3. Retrieval augmentation (Prompt CR) made it WORSE. The naive Wikipedia approach failed; agentic search (AIA-style) is out of scope and would not change the fundamental issue of LLMs hedging on high-confidence sports favorites.

4. Sample size (n=63) is not the bottleneck; the per-series Brier on KXNFLAFCCHAMP (n=7, LLM Brier 0.66) is hopelessly bad regardless of sample size.

**Note on the C6 "pass" artifact:**

Several fade-only variants technically PASS C6 (v2 beats v1 by >= 2pp). This is because v1 catastrophically fails on the widened sample (mean P&L -0.16), and the LLM filter removes some of v1's worst trades. Per the brief's "any criterion meaningfully cleared is a publishable positive finding," we note this carefully:

The C6 pass is **not a sign that the LLM is adding value**; it's a sign that v1's eligibility is too broad for the widened sample. On the strict v1-eligible subset (n=19), v1 also fails (mean P&L -0.40), and the LLM filter does NOT rescue it (kept-3 trades have mean -0.46; LLM picks the WRONG markets to keep). So the C6 "pass" is artifactual and would not generalize to v1's live universe where v1's measured +12.47pp edge holds.

## 10. Pivots attempted (chronological)

Per operator's "do not give up early" instruction, six pivots were exhausted before declaring null:

1. **Multi-prompt ensemble** (average of Prompts C, C2, C3): Brier 0.395 (no gain over C alone at 0.398).

2. **Platt rescaling** (best params bias=1.0, scale=0.5): Brier 0.294. Brings LLM close to Kalshi (0.279) but still worse. Demonstrates the LLM has SOME signal that becomes more useful after calibration, but not enough to beat Kalshi.

3. **Opus 4.7 spot-check** on n=15 markets: Opus Brier 0.365 vs Haiku 0.278 on same subset. **Opus is WORSE.** Cost $0.28. V4-C pilot finding replicated.

4. **Take-threshold sweep** (LLM_prob > Kalshi_price + margin for margin in {-0.20, -0.10, 0, 0.05, 0.10}): All margins produce 0 trades (LLM persistently below Kalshi).

5. **Take-tolerance sweep** (LLM_prob >= Kalshi_price - tolerance for tolerance in {0.10, 0.20, 0.30, 0.40, 0.50, 0.60}): Mostly 0-1 trades; best is tol=0.60 with n=5, mean +0.028, CI lower -0.32.

6. **Fade-only band-gated** (skip when LLM_prob < Kalshi - threshold for prices in [0.70, 0.85], threshold in {0.05, 0.10, 0.20, 0.30, 0.40}): 7 trades in holdout, mean -0.042, v2-v1 +0.116. Best by C6 criterion but fails C1/C2/C4.

7. **Ensemble-fade thr=0.50 band-gated** (use ensemble of C+C2+C3 instead of C alone): 8 trades, mean -0.010, v2-v1 +0.149. Marginal improvement over single-prompt fade.

NOT attempted:
- **Agentic search / AIA-style retrieval**: out of scope budget-wise (would require multi-step LLM calls per market; $20+ extra)
- **Stripping ticker name from prompt** (further anonymization): the S-B1 ANON variant already does this for the leak test; LLM forecasts were not improved
- **News API retrieval**: AskNews API is paid; Bing/Brave Search free tier would need additional integration; deemed unlikely to close 0.12 Brier gap

## 11. Cost analysis

Cumulative API spend (V4-F Phase 2): **$0.627** out of $15 budget.

| Stage | Tokens | Cost |
|---|---:|---:|
| Prompt C on 63 markets | ~30K in / ~14K out | $0.079 |
| Prompt CR on 63 markets | ~50K in / ~14K out | $0.084 |
| Prompt C2 on 63 markets | ~30K in / ~14K out | $0.080 |
| Prompt C3 on 63 markets | ~30K in / ~14K out | $0.080 |
| Prompt WP on 10 markets | ~5K in / ~2K out | $0.013 |
| Prompt ANON on 10 markets | ~3K in / ~2K out | $0.011 |
| Opus 4.7 on 15 markets | ~5K in / ~5K out | $0.278 |
| Buffer / re-runs | | $0.002 |
| Total Phase 2 | | **$0.627** |

Cumulative with V4-C pilot ($0.343): **$0.970** total v4 LLM spend. Well under the $15 master-plan budget cap.

## 12. Files written

- `src/kalshi_bot_v4/llm_forecaster.py` (LLM forecaster module)
- `scripts/v4/select_llm_phase2_sample.py` (sample selection)
- `scripts/v4/run_llm_gate.py` (gate runner)
- `scripts/v4/run_llm_pivots.py` (pivot battery)
- `scripts/v4/_diag_forecasts.py` (diagnostic)
- `scripts/v4/_diag_strict_subset.py` (strict-subset diagnostic)
- `data/v4/llm_phase2_sample.parquet` (n=63 sample with metadata)
- `data/v4/llm_phase2_sample_meta.json`
- `data/v4/llm_phase2_forecasts.parquet` (Prompt C forecasts on n=63)
- `data/v4/llm_forecast_cache.parquet` (all variant forecasts; cache)
- `data/v4/llm_gate_results.json` (G1, G2, G3, S-B1, S-B2, S-B3 results)
- `data/v4/llm_pivots_results.json` (pivot battery results)
- This document.

No modifications to `src/kalshi_bot/`, `src/kalshi_bot_v2/`, `src/kalshi_bot_v3/`, `scripts/` outside `scripts/v4/`, `tests/`, or `data/` outside `data/v4/`. v1 bot untouched.

## 13. Handoff to orchestrator

**Recommendation: close Track B as null.** Track A (V4-E filter) remains the live recommendation; shadow-mode deployment on the v1 production bot is the next step per the V4-E doc.

If the orchestrator wishes to iterate further on Track B despite this null:

- **Wait 60-90 days** for more post-cutoff Kalshi data to accumulate (sample size would grow from n=63 to perhaps n=200+), then re-run.
- **Switch to a frontier reasoning model** (o3, GPT-5) at 50x cost; literature suggests ~0.05 Brier improvement which would close half the gap.
- **Build a proper agentic retrieval system** (AIA-style); requires building a multi-step LLM agent with citation-required outputs; ~10x complexity over what we have now.
- **Accept lower acceptance bar**: drop C6's +2pp-over-v1 to "matches v1." Even this is not currently demonstrated.

None of these are cheap. The literature ceiling for the LLM-only approach is +0.014 Brier improvement over market consensus (V4-B AIA + market ensemble result), translating to ~+1.4pp probability edge. C6's threshold of +2pp over v1's measured edge (which itself is +12.47pp over the price) is ~+14.47pp. The LLM-only ceiling is structurally 10x below this. Even the strongest agentic / RAG / ensemble system in the published literature cannot clear C6 without the market itself in the ensemble.

Per the operator's kill-early principle, this is the right place to close.
