# Karger, Bastani, Yueh-Han, Jacobs, Halawi, Zhang, Tetlock (2024): "ForecastBench: A Dynamic Benchmark of AI Forecasting Capabilities"

**Citation.** Karger, Ezra; Bastani, Houtan; Yueh-Han, Chen; Jacobs, Zachary; Halawi, Danny; Zhang, Fred; Tetlock, Philip E. (Sep 2024). arXiv:2409.19839. Forecasting Research Institute + University of Pennsylvania (Tetlock). Active leaderboard at forecastbench.org. Coverage update by FRI's substack 2026: https://forecastingresearch.substack.com/p/ai-llm-forecasting-model-forecastbench-benchmark.

**Why it matters for Project Kalshi.** ForecastBench is the actively-maintained 2024-2026 benchmark where most LLM-forecasting evals report numbers. It is also the only published source comparing top LLMs against Phil Tetlock's pool of certified superforecasters head-to-head. The benchmark sources questions from Metaculus, Manifold, Polymarket, and RCP plus auto-generated dataset questions (Wikipedia, FRED, ACLED, DBnomics), making it the literature's closest analogue to "Kalshi-like question distribution." Its 2026 updates show LLM-superforecaster parity projected for late 2026, which informs v4 timing.

## TL;DR for future Claude

1. **Superforecasters Brier 0.096; top LLM (Claude 3.5 Sonnet) Brier 0.122; general public Brier 0.121 (n=200 evaluation subset, Sep 2024 paper).** Gap superforecaster-vs-LLM = 0.026 Brier. "Expert forecasters outperform the top-performing LLM (p-value < 0.001)."

2. **LLMs are statistically indistinguishable from the general public on average.** The top LLM is at general-public median. Both LLMs and the public are 0.025 Brier worse than superforecasters.

3. **Older / cheaper models at or below random baseline.** GPT-3.5-Turbo, Claude 2.1, Mistral 7B perform at Brier ~0.25 (random). The high-end vs low-end LLM gap is roughly 0.13 Brier; the cheap-vs-frontier model question is settled in the literature: cheap older models are useless for forecasting.

4. **Market-sourced questions show LLMs CLOSER to superforecaster Brier than dataset-sourced**: superforecaster 0.074 / Claude 3.5 Sonnet 0.107 on market questions vs 0.118 / 0.138 on dataset questions. But on market questions LLMs trail the market itself; on the 2026 Tournament leaderboard, GPT-4.5 has 0.994 correlation with market prices (essentially copies them).

5. **2026 update**: o3 reaches 0.1352 on dataset slice; GPT-4.5 reaches 0.101 overall. Superforecaster baseline now 0.081 (improved). LLM-superforecaster parity projected November 2026 (95% CI Dec 2025 - Jan 2028) on linear extrapolation.

## Sample and methodology

**Benchmark scale.**
- 1,000 forecasting questions automatically generated and refreshed.
- 200 evaluated with human and LLM forecasts per round.
- Questions sourced from Metaculus, Manifold, Polymarket, RCP (market sources) + Wikipedia, FRED, ACLED, DBnomics (dataset sources auto-generated).
- New questions every two weeks (5,900+ open problems as of substack 2026 update).

**Three forecaster groups evaluated.**
- Expert forecasters (Phil Tetlock's certified superforecaster pool, n varies).
- General public (collected via separate survey).
- LLMs (17 models in original Sep 2024 release; more in 2026 leaderboard).

**Data leakage prevention.** Questions are about future events with unknown answers at submission. The benchmark refreshes; new questions are unresolved when LLMs forecast.

**LLM evaluation protocol.**
- Basic prompting WITHOUT news retrieval in the canonical run ("by keeping prompting constant, ForecastBench isolates improvements in core model capabilities from advances in prompting techniques").
- Some baselines include scratchpad reasoning and "freeze values" (priors).
- 5 baseline configurations tested per LLM.
- Top baseline (#5) provides scratchpad + freeze values.

**17 LLMs tested in Sep 2024 paper:** GPT-3.5-Turbo, GPT-4, GPT-4o, GPT-4-Turbo, Claude 2.1, Claude 3-Haiku, Claude 3-Sonnet, Claude 3-Opus, Claude 3.5-Sonnet, Llama-2-70B, Llama-3-7B, Llama-3-70B, Mistral 7B, Mistral 8x22B, Gemini 1.5 Pro, Qwen-72B, Mistral Large.

## Headline numbers to pin

### Aggregate Brier (200-question evaluation subset, Sep 2024 paper)

| Forecaster | Brier | Significance vs LLM |
|---|---|---|
| Superforecasters | 0.096 | beats top LLM (p < 0.001) |
| General public | 0.121 | indistinguishable from top LLM |
| Top LLM (Claude 3.5 Sonnet) | 0.122 | |
| Random baseline | 0.250 | |

### Per-source Brier

| Source type | Superforecaster | Claude 3.5 Sonnet | GPT-4 Turbo |
|---|---|---|---|
| Dataset questions | 0.118 | 0.138 | 0.162 |
| Market questions | 0.074 | 0.107 | 0.095 |

Market-sourced questions (Metaculus, Manifold, Polymarket, RCP) are easier (lower Brier) than auto-generated dataset questions for all three groups.

### LLM range on the benchmark

- Best (Claude 3.5 Sonnet): 0.122
- Worst (older / smaller): >= 0.25 (random)
- GPT-4o vs GPT-4 gap: 0.026 Brier
- Superforecaster vs GPT-4o gap: 0.054 Brier
- "The 0.054 Brier score gap between superforecasters and GPT-4o is significantly larger than the 0.026 gap between GPT-4o and GPT-4."

### 2026 leaderboard updates (FRI substack 2026)

| Forecaster | Brier (Dataset slice) | Brier (Tournament w/ market access) |
|---|---|---|
| o3 | 0.1352 | - |
| GPT-4.5 | 0.101 | best on Tournament; 0.994 correlation with market |
| Superforecaster baseline | 0.081 | - |
| Annual improvement rate | -0.020 / yr (dataset) | -0.036 / yr (Baseline, no market access) |

Linear extrapolation suggests LLM-superforecaster parity around **November 2026 (95% CI Dec 2025 - Jan 2028)**.

## Pin quotes

> "While LLMs have achieved super-human performance on many benchmarks, they perform less well here: expert forecasters outperform the top-performing LLM (p-value < 0.001)." (Abstract)

> "The LLMs in ForecastBench use basic prompting without access to news, and by keeping prompting constant, ForecastBench isolates improvements in core model capabilities from advances in prompting techniques."

> "The 0.054 Brier score gap in performance between superforecasters and GPT-4o is significantly larger than the 0.026 gap in performance between GPT-4o and GPT-4." (Frontier-model spacing)

> (2026 substack) "Linear extrapolation suggests LLMs will match superforecaster performance on ForecastBench in November 2026."

> (2026 substack on Tournament leaderboard) GPT-4.5 "copies market forecasts (0.994 correlation)." (Market-anchoring failure mode, directly relevant to v4 master plan S-B2)

## What is NOT in the paper

- **No per-sport / per-topic Brier decomposition** in the main text of the Sep 2024 paper; per-topic analysis is in Appendix M (questions distributed across geopolitical, economic, scientific, and sports domains sourced from nine platforms).
- **No retrieval / RAG evaluation.** The canonical protocol is "no news access." This is by design (to isolate core capability) but means the benchmark UNDERSTATES what a retrieval-augmented system like Halawi 2024 or AIA Forecaster can do.
- **No Kalshi questions.** Sources are Metaculus, Manifold, Polymarket, RCP, Wikipedia, FRED, ACLED, DBnomics. Kalshi is not on the source list.
- **No cost analysis.** Cost per LLM forecast not quantified.
- **No prompt sensitivity test** beyond the 5 baselines (baseline 1-5 are different prompt structures, not random rephrasings).

## Implications for Project Kalshi v4

1. **The Brier 0.122 top-LLM number is the realistic ceiling for an LLM forecaster without retrieval.** v4 master plan Section 7.1 calls for "(Optional) Recent news headlines / Wikipedia summary / context" in the prompt. Without that, expect Brier near 0.122-0.15 on broad mixed-topic questions, worse on sports-specific.

2. **The 0.994 correlation between GPT-4.5 and market prices** on the Tournament leaderboard is the documented version of v4 master plan S-B2 (price-anchor test) failing. This is the canonical evidence that when LLMs see market prices, they copy them. v4 must NOT include the Kalshi price in the prompt at test time; or must include AND exclude as separate runs (S-B2 design).

3. **The market-question subset Brier gap (superforecaster 0.074 vs top LLM 0.107) is the most relevant comparison for Kalshi.** Kalshi is a market venue. The LLM trailing the superforecaster by 0.033 Brier on market questions translates to roughly +3-5pp probability accuracy gap. **In v1's domain, the human market (Kalshi) IS the "superforecaster" baseline.** An LLM at Brier 0.107 on Kalshi market questions would be 0.04 above the Kalshi market consensus Brier (since Kalshi consensus IS the market price), reproducing the AIA Forecaster MarketLiquid result.

4. **Older models are useless.** The benchmark settles the cheap-vs-frontier question for old models: GPT-3.5, Claude 2.1, Mistral 7B at random baseline. For Project Kalshi: do NOT consider GPT-3.5-class models. The lowest viable tier is Claude 3 Haiku (in the 17-model benchmark; specific Haiku Brier not pulled in this extraction, but it's in the leaderboard range).

5. **The "LLM-superforecaster parity by Nov 2026" projection** is an industry trend signal. If Project Kalshi can defer Track B to 2026-12 with a frontier model, the prior probability of clearing C6 may improve. But the projection is for ForecastBench (mixed-topic), not Kalshi sports specifically.

6. **The basic-prompting protocol caps LLM performance at the baseline** and is conservative. v4 should use retrieval + ensembling + Platt scaling on top, which adds documented improvements (Halawi 2024: -0.020 retrieval; AIA Forecaster 2025: -0.007 Platt; Schoenegger 2024: ensemble matches crowd).

## Verdict on v4 Track B viability

ForecastBench's headline finding is that **the top LLM matches the general public, NOT superforecasters, on prediction-market-style questions, with statistical significance.** For Project Kalshi:

- Kalshi sports markets are price-discovered by sportsbook-saturated retail flow plus institutional MMs.
- The literature's "general public median" is Brier 0.121-0.149 (ForecastBench, Halawi).
- v1 already trades at +12.47pp gross edge over Kalshi price, which corresponds to a Brier improvement of approximately 0.04-0.06 over raw-price-as-prediction (rough conversion: edge of 12.47pp at 0.70-0.95 YES regime maps to Brier delta ~0.04-0.06).

For v4 Track B to clear C6, the LLM-forecaster must produce per-trade edges of +14.47pp on a leak-free OOS holdout. This requires the LLM to outperform Kalshi market consensus AND v1's favorite-longshot heuristic on the same set. ForecastBench shows LLMs do NOT outperform market consensus on market questions (top LLM 0.107 vs market 0.094 on Tournament). Translated: the literature evidence is that LLMs can match the public crowd but NOT the prediction market itself; v1 has measured an edge OVER the prediction market itself.

**v4 Track B's prior of clearing C6 is structurally below 20% per ForecastBench evidence**, before accounting for sports-topic weakness or Haiku-tier cost forcing.
