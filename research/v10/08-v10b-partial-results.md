# V10-B Phase 2 Partial Results (n=20 of 185 resolved)

**Date:** 2026-05-27
**Author:** v10 orchestrator
**Status:** PARTIAL DATA. Final verdict pending more resolutions (target n >= 80).
**Total forecasts:** 185 (5 smoke + 180 main batch)
**Resolved at this snapshot:** 20 (16 MLB props + 4 esports; all same-day or next-day MLB games)
**Open:** 165 (mostly tennis at 14-day horizon, esports 3-14 days)

---

## Headline early-resolution finding

Brier delta is NEGATIVE at n=20:

| Metric | Value |
|---|---|
| Brier_market (orderbook mid) | 0.23109 |
| Brier_v10 (67/33 ensemble, Platt) | 0.25940 |
| Brier_delta | -0.02831 |
| 95% bootstrap CI | [-0.06524, +0.00791] |
| Verdict at n=20 | DESCRIPTIVE (below n=80 minimum); directional NULL trend |

Bootstrap CI includes zero at the upper end. Formally cannot reject NULL at n=20, but the directional evidence is consistent across every subset checked.

## Subset analysis

| Subset | n | Brier_market | Brier_v10 | Delta | Note |
|---|---|---|---|---|---|
| 2-vendor agreement | 5 | 0.248 | 0.346 | -0.098 | WORST; multi-vendor consensus most wrong |
| 1-vendor only | 11 | 0.234 | 0.236 | -0.002 | Near parity |
| 0-vendor (defaulted 0.5) | 4 | 0.203 | 0.216 | -0.013 | Slight noise penalty |
| Days to close > 3 | 4 | 0.184 | 0.228 | -0.044 | Higher delta; small n |
| Signal >= 10c (strong) | 6 | 0.256 | 0.321 | -0.065 | Strong signals MOST wrong |
| Signal 5-10c | 11 | 0.216 | 0.232 | -0.015 | Medium signal slight loss |
| Signal < 5c | 3 | 0.235 | 0.239 | -0.004 | Near parity |
| Mid 0.30 to 0.45 | 13 | 0.210 | 0.238 | -0.027 | LLM bearish, market better |
| Mid 0.45 to 0.55 (coin flip) | 6 | 0.253 | 0.265 | -0.012 | Least bad |

## Why this is consistent with Prediction Arena (arXiv 2604.07355)

Prediction Arena ran 6 frontier LLMs each at $10,000 live capital on Kalshi for 57 days. All 6 lost between -16% and -30.8%. The mechanism: LLMs on Kalshi produce noisy estimates that markets correctly fade. V10-B's n=20 result replays the pattern with cheap-tier vendors.

Standalone LLM Brier (no market blend) on this sample: 0.36. This is WORSE than random (0.25 baseline for p=0.5). The LLM is actively anti-informative on these markets.

## Why early kill is NOT yet warranted

1. **n=20 < 80 verdict floor.** CI includes zero (barely). Not statistically significant at the pre-registered level.

2. **Sample is dominated by short-horizon MLB props (16 of 20).** Per TimeSeek arXiv 2604.04220 (April 2026), LLMs are LEAST competitive on "strong-consensus markets near resolution." Same-day MLB game props are exactly that regime.

3. **The TimeSeek "early lifecycle on high-uncertainty" sweet spot is still unrepresented**: tennis matches (n=64; resolve over 1-15 days; T-7 to T-14 days when forecast) and the remaining esports markets (n=20+; mid-horizon multi-game series). Those resolutions arrive over the next 5-15 days.

4. **No SHIP gate has fired in any direction.** The methodology pre-registered Brier_delta >= 0.010 with CI > 0 as SHIP. We're at -0.028. Even an order-of-magnitude swing toward positive across the remaining n=145 would not clear the gate.

## Interesting auxiliary finding: the LLM as a fade signal

Computed Brier_market vs an INVERTED ensemble: `p_fade = 0.67 * market_mid + 0.33 * (1 - p_llm_ensemble)`. The fade-LLM ensemble gets to PARITY with the market: delta = -0.00065. The LLM appears to have a small anti-signal (worth ~2-3pp of Brier).

This is NOT a v10-B salvage; using it would violate B3 "no post-hoc weight tuning." But it could be a research hypothesis for a future round: **v11 (or v10-C) = fade the LLM signal on uncertain Kalshi props.** The mechanism would need to be examined: why does the LLM systematically err against the market on these markets? Possibilities:
- LLM over-confidence in extreme directions (Halawi anti-hedging in reverse for the cheap-tier vendors)
- Recency bias in news retrieval (LLM reads recent reports that have already moved the market)
- Insufficient retrieval depth (Tavily returned 0 snippets on many tennis/esports niche markets)

The fade hypothesis would require its own pre-registered methodology, prospective forecasting, and Phase 3 critic.

## Vendor performance

| Vendor | Forecasts where present | Working |
|---|---|---|
| Haiku 4.5 | ~50% of markets | YES (after max_tokens fix) |
| Groq Llama 3.3 70B | ~80% of markets | YES (with rate limiter) |
| Gemini 2.5 Flash | ~5% of markets | LIMITED (daily cap + 503s) |
| DeepSeek V4 Flash | 0% | UNAVAILABLE ($0 balance) |

The "multi-vendor diversity" was effectively Haiku + Groq for most forecasts. Without DeepSeek and with Gemini largely unavailable, the diversity dimension was weaker than designed. This is a methodology degradation acknowledged at Phase 1.5.

## Next steps

1. **Continue polling** Kalshi every 6-12 hours for new resolutions. Save updated `data/v10/v10b_resolutions.parquet`.
2. **Final analysis when n >= 80** resolved markets accumulate (estimated 5-15 days).
3. **Phase 3 adversarial critic** after final analysis. Critic will:
   - Reproduce Brier numbers to 5 decimal places
   - Verify no v7-B-style phantom (orderbook mid was real at forecast time? confirmed)
   - Re-run with vendor coverage stratification
   - Audit the fade-LLM hypothesis honestly
4. **Final V10-B verdict** in `research/v10/FINAL-VERDICT.md`.

## Spend

| Bucket | Spent |
|---|---|
| LLM (Anthropic Haiku judge + supervisor + sub-agents) | $0.28 main + $0.0063 smoke = $0.29 |
| External (Tavily, Gemini, DeepSeek, Groq) | $0 (all free tier or unavailable) |
| Kalshi orderbook fetches | $0 |
| Capital | $0 |

Well under the $3 V10-B budget cap from B3.

## Failure modes to log if final NULL fires

If at n >= 80 the verdict is still NULL or PARTIAL-WITH-LOCO-FRAGILITY:

- **F12 (NEW)**: Cheap-tier multi-LLM ensemble on Kalshi short-horizon sports props produces anti-informative aggregate output. Prediction Arena pattern (all 6 frontier models lost on Kalshi) replicates at the retail-budget tier.

This would extend the cumulative failure-mode taxonomy (F1-F11) for any future LLM-on-Kalshi attempt.

## Anti-em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout.
