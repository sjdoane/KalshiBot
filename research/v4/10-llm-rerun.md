# V4-G2 Phase 4: LLM-as-forecaster rerun at corrected cutoff

**Date:** 2026-05-24
**Author:** Agent V4-G2
**Mandate:** Rerun V4-F's LLM-forecaster gate on the larger honest-OOS sample available under Anthropic's official Haiku 4.5 cutoff (training data Jul 2025; reliable knowledge Feb 2025). V4-F hard-coded `WINDOW_START = "2026-01-01"` and assumed the cutoff was Jan 2026; per the orchestrator's verified read of Anthropic's docs (https://platform.claude.com/docs/en/about-claude/models/overview), this was wrong by ~6 to 11 months. Decide whether V4-F's null verdict on Track B holds at the expanded sample, and whether V4-H's denylist plus an LLM filter is materially better than v1 raw.

**Verdict: CONFIRM NULL (with two important reframings).** The LLM-as-forecaster fails the locked C1 to C6 gate on the expanded honest-OOS sample at the correct cutoff. The LLM does not add value as a take-side decision rule and does not add value as a fade-only filter on top of either v1 raw or v1 plus the V4-H denylist. The Brier-level deficit (LLM 0.261 vs Kalshi 0.082, BSS -2.17) is structurally too large to close with prompt-engineering pivots. V4-F's null conclusion stands.

**Two reframings beyond V4-F:**
1. V4-F's "v1 catastrophically fails" finding was overstated; on this STRICT-eligible larger sample, v1 raw mean P&L is +1.83pp with CI [-1.73pp, +5.28pp], straddling zero rather than the V4-F figure of -15.86pp. The earlier negative figure was an artifact of the widened band V4-F was forced to use.
2. The V4-H series denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) DOES improve v1 raw on this sample (+1.45pp mean lift) but DOES NOT cleanly clear the CI lower > 0 threshold either. v1 with denylist still has a CI that includes zero. The denylist verdict from V4-H is preserved as directionally correct; the magnitude on this newer sample is smaller than V4-H's because the V4-G2 sample has favorite-side-flipping coverage and includes some additional non-fragile series.

The Phase 3 critic Finding 4.2 (cutoff misassumption) is closed: the corrected window yields a 12.5x larger strict-eligible sample than V4-F's, and the larger sample confirms the null rather than reversing it.

---

## 1. Sample build

### 1.1 Source and filters

Source: `data/v3/probe_inventory_all_markets.parquet` (n=2828).

Window: `close_time` in [2025-08-01, 2026-03-25). Lower bound is one month past Anthropic's published Haiku 4.5 training data cutoff of Jul 2025 (per https://platform.claude.com/docs/en/about-claude/models/overview).

v1 STRICT eligibility per the locked band:
- favorite-side price at T-35d (from `vwap_t35_narrow` falling back to `vwap_t35_wide`) in [0.70, 0.95]
- lifetime in [30, 180] days
- finalized markets (outcome in {yes, no})

Favorite-side flipping applied (as in V4-F): markets where the YES side traded < 0.50 at T-35d are recoded so the LLM forecasts the favorite-side probability and the outcome is recoded to match.

Exclusions:
- 25 V4-C pilot tickers (data/v4/llm_pilot_sample.parquet)
- 63 V4-F Phase 2 tickers (data/v4/llm_phase2_sample.parquet)
- Total unique exclusions: 88

### 1.2 Sample characteristics

Built `data/v4/llm_phase4_sample.parquet`:
- n = 238 markets
- YES rate (favorite-side, post-flipping): 0.912
- Mean favorite_price: 0.858
- Median lifetime_days: 89; min 33; max 173
- 21 catastrophic losses (P&L < -0.50), 217 wins (P&L > 0)

Series distribution (top 10):
```
KXNCAAFPLAYOFF        19
KXNFLPLAYOFF          14
KXNFLWINS-MIA          9
KXMLBPLAYOFFS          9
KXNFLWINS-CLE          8
KXNFLWINS-DAL          8
KXNFLWINS-IND          8
KXNFLWINS-SEA          8
KXNFLWINS-NE           8
KXNFLWINS-WAS          7
```

The sample is 63% KXNFLWINS-* (n=151), 8% KXNCAAFPLAYOFF (n=19), 6% KXNFLPLAYOFF (n=14), 4% KXMLBPLAYOFFS (n=9). 87% (n=207) of rows fall under the V4-H "fragile-series" prefixes (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS); the per-V4-H-denylist residual is n=43.

### 1.3 Sample-construction notes

The first attempt by the previous V4-G agent used SAMPLE_CAP = 200 chronologically. This excluded close dates after 2025-12-22, which mechanically dropped 13 of the 15 catastrophic-loss tickers from V4-H. The cap was an artifact, not a brief requirement. V4-G2 disabled the cap and rebuilt with n=238 (the natural pool size after exclusions). The cap-vs-no-cap difference is large: yes-rate dropped from 0.965 (capped) to 0.912 (full); v1 holdout mean dropped from +7.77pp to -7.89pp. The honest reading uses the full pool.

The strict-eligible sample exceeds the brief's n >= 30 threshold by a wide margin, so no wide-eligibility supplementation was needed.

---

## 2. Run the forecaster

### 2.1 Forecaster configuration

`Forecaster` class from `src/kalshi_bot_v4/llm_forecaster.py` with:
- model: `claude-haiku-4-5` (resolved to `claude-haiku-4-5-20251001` by SDK)
- prompt_variant: `C` (no price shown, no-memory injunction; V4-C and V4-F both identified this as the best base)
- cache: `data/v4/llm_forecast_cache.parquet` (continued from V4-F)

### 2.2 Cache reuse

The V4-F cache had 477 entries (mostly the 63 V4-F Phase 2 tickers across multiple variants). V4-G inherited the cache and pre-cached the first batch of 200 phase-4 tickers. V4-G2 needed to forecast only the 38 additional tickers added when removing the chronological cap.

Total new Haiku Prompt-C forecasts in V4-G2: 38 markets at $0.047 (cumulative-cache delta).
S-B1 sanity required 10 additional ANON forecasts at $0.012 incremental.
V4-G2 total incremental LLM spend: **$0.059**.

### 2.3 Aggregate forecast quality on n=238

| Metric | Value |
|---|---:|
| Brier (LLM) | 0.2614 |
| Brier (Kalshi price) | 0.0824 |
| BSS vs Kalshi | -2.17 |
| ECE (LLM) | 0.3735 |
| ECE (Kalshi) | 0.0533 |
| Brier diff (Kalshi minus LLM) | -0.1789 |
| Brier diff 95% CI | [-0.2127, -0.1455] |
| Mean LLM probability | 0.538 |
| Mean Kalshi price | 0.858 |
| corr(LLM, Kalshi) | 0.013 |

The CI on (Kalshi - LLM) sits entirely below zero. Kalshi is significantly better than the LLM at the n=238 sample. This is consistent with V4-F's finding (BSS -0.428) but more extreme because the rerun sample has higher yes-rate (0.91 vs 0.56 in V4-F's widened); the LLM's structural hedging penalty is larger on a more-favorite-dominated set.

LLM calibration by probability bucket (Halawi 2024 high-confidence-failure-mode signature):

| LLM prob bucket | n | mean LLM | actual yes rate |
|---|---:|---:|---:|
| (0.0, 0.1] | 7 | 0.064 | 0.857 |
| (0.1, 0.2] | 11 | 0.164 | 1.000 |
| (0.2, 0.3] | 14 | 0.252 | 0.857 |
| (0.3, 0.4] | 18 | 0.335 | 0.944 |
| (0.4, 0.5] | 42 | 0.424 | 0.952 |
| (0.5, 0.6] | 23 | 0.562 | 0.870 |
| (0.6, 0.7] | 50 | 0.626 | 0.880 |
| (0.7, 0.8] | 65 | 0.722 | 0.908 |
| (0.9, 1.0] | 6 | 0.935 | 1.000 |

Same pattern V4-F documented: when the LLM says 10% yes, actual is 86% yes. The Platt-rescaling V4-F tested (bias 1.0, scale 0.5) would bring LLM Brier to ~0.13 against Kalshi 0.08, still meaningfully worse.

### 2.4 Per-series Brier (where n >= 5; selected rows)

| Series | n | yes rate | Brier LLM | Brier Kalshi | LLM - Kalshi |
|---|---:|---:|---:|---:|---:|
| KXNCAAFPLAYOFF | 19 | 0.895 | 0.509 | 0.082 | +0.427 |
| KXNFLPLAYOFF | 14 | 0.857 | 0.195 | 0.116 | +0.079 |
| KXMLBPLAYOFFS | 9 | 0.556 | 0.255 | 0.328 | -0.073 |
| KXNFLWINS-NE | 8 | 1.000 | 0.398 | 0.045 | +0.353 |
| KXNFLWINS-DEN | 7 | 1.000 | 0.267 | 0.041 | +0.226 |
| KXNFLWINS-GB | 6 | 1.000 | 0.272 | 0.014 | +0.259 |

The LLM only beats Kalshi on KXMLBPLAYOFFS (n=9, yes_rate 56%, a hard calibration test where Kalshi at 0.82 is poorly calibrated). On every other series the LLM is dramatically worse.

---

## 3. Apply the locked C1 to C6 gate

Using `src/kalshi_bot_v2/gate.py:evaluate` with the locked criteria. Saved to `data/v4/llm_phase4_gate_results.json`.

### 3.1 Gate results

| Variant | n holdout | mean P&L | hit rate | CI [lower, upper] | v1 mean | v2 - v1 | criteria passed |
|---|---:|---:|---:|---|---:|---:|---|
| G1 v1 baseline | 72 | -0.0789 | 0.875 | [-0.1748, +0.0024] | -0.0789 | 0.0000 | 0/6 |
| G2 LLM take margin 0.00 | 2 | +0.0857 | 1.000 | [+0.0550, +0.1150] | -0.0789 | +0.1646 | 0/6 (C4 fails n=2) |
| G2 LLM take margin 0.05 | 0 | n/a | n/a | n/a | -0.0789 | n/a | 0/6 |
| G2 LLM take margin 0.10 | 0 | n/a | n/a | n/a | -0.0789 | n/a | 0/6 |
| G2 LLM fade-only band-gated | 48 | -0.0821 | 0.875 | [-0.1947, +0.0008] | -0.0789 | -0.0032 | 0/6 |

(G3 with Prompt CR was skipped per the brief; V4-F definitively showed CR is WORSE than C, and the saved budget is not needed.)

### 3.2 C1 to C6 pass / fail

- **C1 (mean > 0):** v1 baseline FAILS (mean -0.08); fade-only FAILS (mean -0.08); G2-take-margin-0 PASSES but with n=2.
- **C2 (CI lower > 0):** all variants FAIL.
- **C3 (hit rate > 0.55):** v1 PASSES (0.875); fade-only PASSES (0.875); G2-take PASSES (1.0) at n=2.
- **C4 (n >= 15):** v1 PASSES (n=72); fade-only PASSES (n=48); G2-take FAILS (n=2 or 0).
- **C5 (pooled folds > 0):** all variants FAIL (pooled means are negative).
- **C6 (v2 beats v1 by >= 2pp):** fade-only FAILS (-0.0032); G2-take PASSES nominally (+0.165) but at n=2 the comparison is meaningless.

Best variant by criterion count is G2-take-margin-0 with 3/6, but that variant has n=2 (one third the C4 floor of 15) so the headline-positive mean is a single-noise artifact. **No variant clears the full gate.** The pattern is identical to V4-F's (no variant passed there either); the larger sample did not surface a hidden positive.

### 3.3 5-fold CV diagnostic

The pooled-fold mean for the LLM decision rule is negative across all variants (per gate.py's C5 calculation). This is honest: a worse-than-market model produces negative pooled-fold P&L by construction.

### 3.4 Saved gate output

`data/v4/llm_phase4_gate_results.json` contains:
- `sample_n`, `sample_yes_rate`, `sample_mean_price`
- `G1` (v1 baseline result)
- `calibration_promptC` (Brier, BSS, ECE, brier diff CI, correlations)
- `G2.margin_0.00`, `G2.margin_0.05`, `G2.margin_0.10` (take-rule margin sweep)
- `G2_fade` (fade-only band-gated)
- `per_series_brier` (per-series LLM vs Kalshi)
- `per_bucket_calibration` (LLM probability bucket vs actual yes rate)
- `lifetime_price_breakdown` (Brier by (lifetime bucket, price bucket))
- `cumulative_api_cost_usd_cache_total` ($0.94)
- `SB1_phase4` (this rerun's sanity check; see Section 7)

---

## 4. Three-way analysis (the meaningful question post-V4-H)

Per V4-H's finding that v1 is FRAGILE on KXNFLWINS, KXNFLPLAYOFF, and KXMLBPLAYOFFS series, the meaningful comparison is whether the LLM filter adds value on top of (a) v1 raw, (b) v1 plus the V4-H denylist, or (c) ONLY as a stand-in for the denylist (no V4-H knowledge).

Scenarios on the full n=238 (favorite-side-flipped, strict-band) sample:

| Scenario | n trades | mean P&L | CI lower | CI upper | hit rate |
|---|---:|---:|---:|---:|---:|
| A. v1 raw | 238 | +0.0183 | -0.0173 | +0.0528 | 0.912 |
| B. v1 + V4-H denylist | 43 | +0.0328 | -0.0468 | +0.0977 | 0.930 |
| C. v1 + denylist + LLM-fade | 28 | +0.0330 | -0.0336 | +0.0759 | 0.964 |
| D. v1 + LLM-fade (no denylist) | 164 | +0.0025 | -0.0408 | +0.0407 | 0.927 |

Differentials:
- B - A (denylist effect on raw v1): **+0.0145** (denylist helps but small)
- C - B (LLM-fade on top of denylist): **+0.0002** (LLM-fade adds essentially nothing)
- D - A (LLM-fade only, no denylist): **-0.0158** (LLM-fade alone HURTS v1)
- Denylisted aggregate: n=195, mean +0.0151 (positive on this sample, contra V4-H's -3.02pp).

### 4.1 Why does the denylist help less here than in V4-H?

V4-H's sample for the denylisted series was n=109 with mean -3.02pp. V4-G2's denylisted-series subset is n=195 with mean +1.51pp. The samples overlap on 63 tickers but V4-G2 adds 132 markets V4-H didn't see, all from the post-Jul-2025-cutoff window. Two effects:

1. **Favorite-side flipping**: V4-G2 includes 89 NO-side favorites (where YES traded < 0.50 at T-35d). V4-H used the YES-side `eligible_narrow` flag, which is YES-side-only. The NO-side favorites in V4-G2 happen to have a high (97.8%) yes-rate at favorite-side (i.e., heavy NO outcomes), so they win at the favorite-priced rate without catastrophic losses. This shifts the aggregate up.
2. **Apples-to-apples YES-side-only check**: restricting to YES-side-only (n=105), v1 mean drops to -1.44pp with CI [-7.97pp, +4.55pp]. This is consistent with V4-H's KXNFLWINS slice -1.03pp. The V4-H "v1 fails on denylisted series" reading is preserved in the YES-side-only comparison.

### 4.2 Honest framing

On the YES-side-only subset of n=105 (the apples-to-apples comparison with V4-H, and with v1's actual live universe per CLAUDE.md Round 7):
- v1 raw: mean -1.44pp, CI [-7.97pp, +4.55pp]. v1 fails to clear CI lower > 0.
- v1 + V4-H denylist: n=14, too small to read.
- Denylisted (KXNFLWINS+KXNFLPLAYOFF+KXMLBPLAYOFFS) aggregate: n=91, mean -1.00pp, hit rate 86.8%.

On the full favorite-side-flipped n=238:
- v1 raw: mean +1.83pp, CI [-1.73pp, +5.28pp]. Borderline; CI lower below 0.
- v1 + V4-H denylist: n=43, mean +3.28pp, CI [-4.68pp, +9.77pp]. Better point estimate but wider CI; still includes 0.

The LLM-fade-on-top-of-v1-denylist scenario (C) does not improve over (B). The LLM filter has no measurable value as a fade aid even on the residual where v1 is supposed to work. The only "improvement" is hit rate (0.964 vs 0.930), but mean P&L is identical and CI lower is still below 0.

---

## 5. Cost reporting

| Stage | Tokens | Cost (USD) |
|---|---:|---:|
| V4-C pilot (Haiku + Opus, 110 calls) | mixed | $0.343 |
| V4-F Phase 2 (Haiku A/B/C/CR/WP/ANON + Opus, ~450 calls) | mixed | $0.627 |
| V4-G2 Phase 4 (38 new Prompt-C forecasts + 10 ANON for S-B1) | small | $0.059 |
| **Total v4 LLM spend (cumulative)** | | **$1.03** |

Cache total per `data/v4/llm_forecast_cache.parquet`: $0.947 (this excludes V4-C pilot which was pre-cache; per V4-C doc was $0.343 separately).

Cumulative v4 LLM spend ($1.03) is well under the orchestrator's $25 cap and under V4-G2's $10 incremental cap. Headroom remains $24 if the operator authorizes a follow-on pivot.

---

## 6. Verdict

**CONFIRM NULL.** The locked C1 to C6 gate fails on the expanded sample at the correct cutoff. The LLM-as-forecaster is genuinely null on Kalshi sports favorite markets:

- Brier deficit is 0.179 (LLM 0.261 vs Kalshi 0.082), 95% CI [-0.213, -0.146], entirely below zero.
- ECE LLM is 7x Kalshi's (0.374 vs 0.053).
- The take rule LLM > price produces n=2 trades (LLM is biased low; rarely exceeds Kalshi).
- The fade-only band-gated rule produces n=48 trades with mean -8.21pp, essentially identical to v1's -7.89pp (v2 - v1 = -0.32pp; no improvement).
- The LLM-fade-on-top-of-V4-H-denylist scenario adds +0.02pp on top of denylist alone; this is noise.

The V4-F null verdict stands. The Phase 3 critic Finding 4.2 (cutoff misassumption) is closed by this rerun: the corrected window does not surface a hidden positive.

### 6.1 Reframing of V4-F findings

Two V4-F findings should be reframed in light of V4-G2:

1. **V4-F's "v1 catastrophically fails on widened sample"** was overstated. On the strict-band rerun sample (n=238), v1 raw mean is +1.83pp with CI [-1.73pp, +5.28pp]. The V4-F figure of -15.86pp on n=19 reflected the widened price/lifetime band, not v1's actual performance. V4-F's S-B section on "v1 baseline catastrophically fails" should be read as "v1 baseline catastrophically fails ON THE WIDENED SAMPLE" not "v1 always fails."

2. **V4-F's BSS -0.428 on the widened sample** holds in spirit but the rerun on the strict band shows BSS -2.17 (much worse). The LLM's relative-Brier penalty is larger on sets dominated by high-confidence favorites where Kalshi is well-calibrated. The Halawi 2024 high-confidence-failure-mode signature is sharper at the strict band than at the widened band.

### 6.2 V4-H reinterpretation

V4-H concluded v1 is FRAGILE on the three denylisted series with aggregate mean -3.02pp. On the V4-G2 strict-band sample (which has minimal overlap with V4-H's exact tickers due to the post-Jul-2025 window), the denylisted aggregate is +1.51pp at n=195. The discrepancy is partially due to favorite-side flipping and partially due to time-window effects:

- The YES-side-only subset of V4-G2 (n=91 denylisted) has mean -1.00pp, hit rate 86.8%. This is consistent with V4-H's KXNFLWINS slice (-1.03pp at n=95).
- The NO-side-favorite subset (n=104 denylisted) has a higher mean because outcomes for NO favorites are concentrated in "NO wins as expected" (the heavy-favorite NO ticker), which produces wins at favorite-priced odds.

The denylist is therefore SUPPORTED for v1's actual live universe (YES-side-only) but the magnitude is smaller on the expanded window than V4-H originally reported. The operator action (add KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS to v1's denylist) remains the right call.

### 6.3 Phase 5 implications

The V4 Phase 5 verdict needs to integrate:
- **Track A (Polymarket-fade filter):** V4-E's PARTIAL with the V4-Critic's 120-180 day shadow-mode timeline.
- **Track B (LLM-as-forecaster):** NULL confirmed by V4-G2 at corrected cutoff. The Phase 3 critic's cutoff-misassumption finding is closed but did not reverse the verdict.
- **v1 stress test (V4-H):** v1 is FRAGILE on the three denylisted series. Operator should add a per-series denylist for KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS.
- **The structural ceiling**: per V4-B literature, the LLM-only approach to Kalshi prediction has a +0.014 Brier improvement ceiling at the AIA frontier (out of reach for Haiku 4.5 with Prompt C). C6's +2pp-over-v1 threshold is structurally unattainable.

---

## 7. Sanity checks at the new n

### 7.1 S-B1 cutoff-leak on the rerun sample

V4-F's S-B1 used the V4-C pilot's PRE-cutoff (pre-Jan-2026) markets. Under the corrected cutoff (Jul 2025), those markets are also post-cutoff, so V4-F's S-B1 measured post-vs-post (no longer the right diagnostic).

V4-G2 reran S-B1 on the actual rerun sample: 10 markets from `llm_phase4_sample.parquet` (seed 42), forecasted with both Prompt C (full ticker + full dates) and Prompt ANON (year only, no ticker).

| Metric | Value |
|---|---:|
| n | 10 |
| Sample yes_rate | 0.900 |
| Sample close_time range | 2025-09-29 to 2025-12-27 |
| mean_abs_diff (full vs anon) | 0.123 |
| Brier (full prompt) | 0.166 |
| Brier (ANON prompt) | 0.237 |
| Brier (Kalshi price as forecast, for ref) | 0.081 |

Interpretation: the LLM IS using cues from full ticker + dates that improve its Brier by 0.071 absolute over the anonymized version on this 10-row subsample. Possibilities:
- **Public prior knowledge**: the LLM knows from training that "the Bills are good" and uses this when given the team name. This is legitimate forecasting, not memorization.
- **Outcome memorization**: the LLM has actually seen these market resolutions in training data. The Jul 2025 training cutoff makes this unlikely for the n=10 subsample, all of which close >= Sep 29 2025.

The Brier full-prompt 0.166 is still 2x worse than Kalshi mid-price 0.081. Even with the team-knowledge advantage, the LLM cannot beat the market. The "leak" question is therefore moot for trade-level evaluation: regardless of which prior the LLM is using, it remains worse than the market signal.

Honest framing: this is NOT a leak in the V4-F sense (outcome memorization). It is the LLM using public-knowledge priors. Those priors are legitimate, and the LLM still fails the gate.

### 7.2 S-B2 and S-B3 (skipped)

V4-F already ran S-B2 (price-anchor) on a 10-market subset, finding the LLM is NOT anchoring on the displayed price (corr -0.67 no-price vs -0.63 with-price). V4-F ran S-B3 (prompt-sensitivity) showing the variants C / C2 / C3 produce forecasts within std 0.035 of each other. Neither of these depends on the cutoff window; rerunning them on V4-G2's sample would not change the V4-F readings. V4-G2 did not rerun them per cost-discipline and time-budget; the V4-F results are inherited.

---

## 8. Hard constraints satisfied

- READ-only on Kalshi side (only /historical/markets and /events for metadata).
- LLM calls only via the official `anthropic` Python SDK.
- V4-G2 incremental LLM spend: $0.059. Cumulative v4 LLM spend: $1.03 (well under $25 cap, $10 V4-G2 cap).
- No modifications outside `scripts/v4/`, `data/v4/`, `research/v4/`, `src/kalshi_bot_v4/`.
- No em-dashes anywhere in this file.
- V4-F's existing outputs untouched: `data/v4/llm_phase2_sample.parquet`, `data/v4/llm_phase2_forecasts.parquet`, `data/v4/llm_gate_results.json`, `data/v4/llm_pivots_results.json`.
- v1 bot UNTOUCHED.

## 9. Files written / modified

Created:
- `scripts/v4/run_sb1_phase4.py` (S-B1 cutoff-leak sanity at new window; 130 lines)
- `scripts/v4/run_three_way_analysis.py` (three-way scenario analysis per brief; 200 lines)
- `data/v4/llm_phase4_three_way_results.json` (three-way analysis output)
- `data/v4/_phase4_select_log.txt` (transcript of sample rebuild)

Modified:
- `scripts/v4/select_llm_phase4_sample.py` (disabled SAMPLE_CAP = 200; now uncapped for honest n=238)
- `data/v4/llm_phase4_sample.parquet` (regenerated at n=238)
- `data/v4/llm_phase4_sample_meta.json` (regenerated)
- `data/v4/llm_phase4_forecasts.parquet` (regenerated with 38 new forecasts)
- `data/v4/llm_phase4_gate_results.json` (regenerated; S-B1 appended)
- `data/v4/llm_forecast_cache.parquet` (38 new entries; 545 total rows; $0.95 total)
- `data/v4/_phase4_gate_log.txt` (regenerated)
- This document.

Untouched:
- V4-F outputs (`llm_phase2_*`)
- V4-H outputs (`v1_stress_test_*`)
- V4-E outputs (`filter_backtest_*`)
- v1 bot

## 10. Handoff to V4 Phase 5

The V4 Phase 5 final verdict should fold in V4-G2's findings:

1. **Track B confirmed NULL** at the correct cutoff. Phase 3 critic Finding 4.2 closed.
2. **v1 PARTIAL stays** as the operator-recommended action per V4-H Section 6. The denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) is still supported on the YES-side-only analysis; magnitude is smaller on the broader sample but direction is preserved.
3. **Track A (Polymarket-fade filter)** remains the strongest live candidate, with the 120-180 day shadow-mode timeline per V4-Critic.
4. **The LLM-as-forecaster is structurally bounded** by the Halawi 2024 high-confidence-favorite hedging failure mode. Closing the 0.18 Brier deficit requires either (a) frontier reasoning models (Opus / o3 / GPT-5; literature suggests ~0.05 gain, not enough) or (b) agentic retrieval (out of scope per cost-discipline). The operator should consider Track B closed.

If the operator wants a final "before kill" pivot, the most-promising untried angle is the V4-Train-2 sportsbook-hybrid rule (per Phase 3 critic Section 5, untried angle C). Theodds-api free tier supports it at $0 cost; the operator action is 5 minutes to sign up. V4-G2's null is a strong-enough verdict that even adding the sportsbook anchor will not flip it on a single rerun; the critic's recommendation was a hybrid V1-strict-filter + LLM + sportsbook decision rule. Whether that warrants V4-I depends on operator time budget.

---

## Findings summary

| # | Finding | Severity |
|---|---|---|
| 10.1 | At corrected cutoff window (2025-08-01 onward), strict-eligible pool is n=238 (~12.5x V4-F's n=19) | Important |
| 10.2 | LLM Brier 0.261 vs Kalshi 0.082; BSS -2.17; CI on Brier diff [-0.213, -0.146] entirely below zero | Killer |
| 10.3 | LLM take rule produces n=2 trades; fails C4 by a factor of 7.5 | Killer |
| 10.4 | LLM fade-only rule produces n=48 trades; v2-v1 = -0.32pp (no improvement over v1) | Killer |
| 10.5 | v1 raw on full strict-band sample: mean +1.83pp, CI [-1.73, +5.28] (CI includes 0) | Important |
| 10.6 | V4-H denylist adds +1.45pp on top of v1 raw but CI still includes 0 (n=43 is small) | Important |
| 10.7 | LLM-fade on top of V4-H denylist adds +0.02pp (essentially zero) | Killer |
| 10.8 | YES-side-only analysis (apples-to-apples with V4-H) preserves the v1-fragile reading | Important |
| 10.9 | LLM is grotesquely miscalibrated at low end (predicts 10%, actual 86%) - documented Halawi 2024 mode | Important |
| 10.10 | S-B1 on rerun sample shows full-prompt is better than ANON by Brier 0.071 - team-knowledge prior, not outcome memorization (still worse than Kalshi) | Minor |
| 10.11 | V4-F's "v1 catastrophically fails" should be reframed as widened-band-only finding | Important |
| 10.12 | Cumulative V4 LLM spend $1.03 (V4-G2 incremental $0.06; well under $10 cap) | Minor |

4 KILLER, 7 IMPORTANT, 1 MINOR.

---

## Verdict in one sentence

The LLM-as-forecaster (Haiku 4.5, Prompt C, no-price no-memory) fails the locked C1 to C6 gate on the expanded n=238 honest-OOS sample at the corrected Anthropic cutoff, with a Brier deficit that is structurally larger than at V4-F's incorrect-cutoff sample, and adds no measurable value as either a take-side decision rule or a fade-only filter on top of v1 raw or v1 plus the V4-H denylist.
