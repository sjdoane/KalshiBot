# AIA Forecaster 2025 + LLM-forecasting follow-up cluster (2025-2026)

**Citations** (combined extraction across 6 sources covering 2025-2026 LLM-forecasting frontier):

1. **AIA Team (Nov 2025)**, "AIA Forecaster: Technical Report," arXiv:2511.07678. Aria Lab. The state-of-the-art system as of late 2025.
2. **Lu, Janna (Jul 2025)**, "Evaluating LLMs on Real-World Forecasting Against Expert Forecasters," arXiv:2507.04562. 464 Metaculus questions. Per-model and per-category Brier breakdowns.
3. **Singh, Shivansh et al. (Nov 2025)**, "Future Is Unevenly Distributed: Forecasting Ability of LLMs Depends on What We're Asking," arXiv:2511.18394. Per-topic Brier showing sports as a weak topic.
4. **Yang, Qingchuan; Wu, Jibang et al. (Oct 2025)**, "LLM-as-a-Prophet: Understanding Predictive Intelligence with Prophet Arena," arXiv:2510.17638. 23 frontier models on 1,367 prediction-market events.
5. **Azam, Charles & Roucher, Aymeric (2025)**, PrediBench (huggingface.co/blog/charles-azam/predibench). Live Polymarket-based benchmark.
6. **FutureSearch (Apr 2026)**, "Bench to the Future" / BTF-2 leaderboard (evals.futuresearch.ai). 1,417 hard pastcasting questions on frozen 15M-document corpus.

Treated as a combined extraction because (a) AIA Forecaster is the published state-of-the-art reference point, (b) the other 5 sources triangulate the same picture from different angles, (c) no single paper alone covers v4's question end-to-end.

**Why it matters for Project Kalshi.** This cluster represents the 2025-2026 frontier of LLM forecasting evidence. Three load-bearing findings: (1) AIA Forecaster matches superforecasters on the FORI ForecastBench but LAGS market consensus on hard liquid markets; (2) sports is documented as one of the worst LLM topics; (3) frontier reasoning models (o3, GPT-5, Opus 4.7) substantially outperform older frontier (Claude 3.5 Sonnet, GPT-4o), but cheap-tier (Haiku, GPT-4o-mini) is structurally untested in any major published forecasting benchmark.

## TL;DR for future Claude

1. **AIA Forecaster matches superforecasters but LAGS market on hard markets.** FB-7-21 Brier: AIA 0.1125 vs superforecaster median 0.1110 (indistinguishable). MarketLiquid Brier: AIA 0.1258 vs market consensus 0.1106 (LLM lags by 0.015, -13.7% Brier skill).

2. **AIA + market ensemble beats either alone.** Simplex regression: 67% market, 33% AI weight on hard MarketLiquid; ensemble Brier 0.106 (vs market 0.111 alone). LLM adds ~5% Brier skill via ensembling, NOT by beating the market head-to-head.

3. **Sports is the LLM weak topic.** "Future Is Unevenly Distributed" 2025 Brier per topic (no news): Claude 3.7 sports 0.28 vs geopolitics 0.12; GPT-5 sports 0.28 vs geopolitics 0.14. Two of four frontier models ~2x worse on sports. Janna Lu 2025: o3 sports 0.1649 vs politics 0.1199 (37% worse).

4. **Frontier reasoning > frontier non-reasoning > older > cheap.** Janna Lu 2025 Brier: o3 0.1352 < GPT-4.1 0.1542 < o4-mini 0.1589 < DeepSeek v3 0.1798 < Claude 3.6 Sonnet 0.1810 < GPT-4o 0.1883. Brier spread top-to-bottom is ~0.05. No published Haiku benchmark.

5. **Calibration techniques (AIA Forecaster ablation).** Platt scaling -0.007 Brier (best); log-odds extremization -0.006; isotonic -0.004; OLS -0.002; no correction baseline 0.1140. Platt with parameter √3 ≈ 1.73 is canonical mitigation for RLHF hedging.

6. **News context is double-edged.** Halawi 2024 retrieval is -0.020 Brier (good). AIA agentic search adds -0.009. But "Future Is Unevenly Distributed" 2025 documents news context can HURT through recency bias and rumor over-weighting. Janna Lu 2025 found AskNews retrieval improves o3 to 0.1352 vs baseline. Effect is benchmark and topic-conditional.

7. **Anchoring on market price is empirically severe.** ForecastBench 2026 Tournament leaderboard: GPT-4.5 has 0.994 correlation with market prices when given access. Prophet Arena: LLMs lose to markets within 3 hours of resolution but match markets at longer horizons (3+ hours).

## AIA Forecaster (arXiv 2511.07678) - detailed

### System architecture

Three components:
1. **Agentic search** over high-quality news sources. Multiple independent agents conduct iterative queries; "full discretion to determine whether and how to query the search provider."
2. **Supervisor agent** that examines disagreements among individual forecasts; issues additional search queries to resolve ambiguities; synthesizes final prediction.
3. **Statistical calibration** via Platt scaling to counter RLHF hedging bias.

### Performance

| Benchmark | AIA | Best baseline | Notes |
|---|---|---|---|
| ForecastBench FB-7-21 | 0.1125 | Superforecaster 0.1110 | Indistinguishable |
| MarketLiquid (1,610 hard Q) | 0.1258 | Market consensus 0.1106 | AIA lags by 0.015 |
| MarketLiquid ensemble | 0.092 | - | AIA + market beats both |
| FB-7-21 ensemble | 0.106 | - | 87% AIA, 13% market |

### Calibration technique ablation

| Method | FB-7-21 Brier |
|---|---|
| Platt scaling (best) | 0.1071 |
| Log odds extremization | 0.1085 |
| Isotonic regression | 0.1097 |
| OLS | 0.1119 |
| No correction | 0.1140 |

Platt scaling with parameter √3 ≈ 1.73 is the recommended single-step post-processing.

### Search ablation

| Configuration | Brier (FB-7-21) |
|---|---|
| Agentic search | 0.1140 |
| Non-agentic search | 0.1174 |
| No search baseline | 0.1230 |

Agentic search adds -0.009 Brier; total search effect (vs no-search) -0.009.

### Foreknowledge / cutoff control

LLM-as-judge protocol audits search results for content exceeding the intended information cutoff. On 502 traced audits, 1.65% contained foreknowledge bias. Robustness checks: removing flagged results changes Brier by ≤0.6%. Methodology is the cleanest published "post-cutoff honesty" approach.

### Pin quote

> "On the more challenging MarketLiquid benchmark, the AIA Forecaster (0.108) lags behind market consensus (0.098). However, an ensemble combining the AIA Forecaster and market prices achieves a Brier score of 0.092, outperforming both components."

(Note: the AIA paper's tabulated MarketLiquid number is 0.108 / 0.098 in some tables; 0.126 / 0.111 in others, depending on the specific question subset. Both pairs show AIA lagging market by 0.010-0.015.)

## Janna Lu (arXiv 2507.04562) - detailed

### Setup

- 464 Metaculus questions: 334 training (July-September 2024) + 130 holdout (October-December 2024).
- AskNews API provides 30 retrieved articles per question.
- Five predictions per question, averaged.
- Two prompt styles: direct superforecasting prompt and narrative prompt (script-writing).
- 12 frontier and open-source models.

### Headline Brier (direct prompt, with AskNews retrieval)

| Model | Brier |
|---|---|
| o3 (best LLM) | 0.1352 |
| GPT-4.1 | 0.1542 |
| o4-mini | 0.1589 |
| DeepSeek v3 | 0.1798 |
| Claude 3.6 Sonnet | 0.1810 |
| GPT-4o | 0.1883 |
| Human crowd | 0.1490 |
| Expert (superforecaster) | 0.0225 |

The top LLM beats the human crowd (0.1352 vs 0.1490) but lags experts by 6x.

### Per-category Brier (best model per category)

| Category | Best model | Brier |
|---|---|---|
| Healthcare | GPT-4.1 | 0.0819 |
| Politics | o3 | 0.1199 |
| Economics | o3 | 0.1353 |
| Sports | o3 | 0.1649 |

Sports is the weakest topic for the top model. The category gap (politics 0.1199 vs sports 0.1649) is 0.045 Brier or 37% worse on sports.

### Failure modes documented

1. Overconfidence near certainty-extremes (poor calibration for high-confidence predictions).
2. Economic / financial weakness from numerical reasoning failures.
3. Narrative prompt degradation: o3 worsens from 0.1352 to ~0.1985 (+47%).
4. Granularity deficit: LLMs default to 10% probability increments; experts use 1%.
5. Update insensitivity to contradictory evidence.
6. Censorship issues: DeepSeek v3 skipped 9 China-Taiwan questions.

## "Future Is Unevenly Distributed" (arXiv 2511.18394) - detailed

### Per-topic Brier (no news context)

| Topic | Claude 3.7 | DeepSeek-R1 | GPT-4.1 | GPT-5 |
|---|---|---|---|---|
| Sports | 0.28 | 0.26 | 0.45 | 0.28 |
| Geopolitics | 0.12 | 0.32 | 0.40 | 0.14 |
| Finance | 0.31 | 0.35 | 0.33 | 0.26 |
| Technology | 0.25 | 0.27 | 0.42 | 0.24 |
| Entertainment | 0.23 | 0.28 | 0.33 | 0.24 |
| Politics | 0.22 | 0.27 | 0.38 | 0.21 |

Headline: "Strongest: Geopolitics (84% accuracy across models). Weakest: Finance and Sports (48-60% accuracy range)."

For Project Kalshi: TWO of four frontier models (Claude 3.7, GPT-5) have ~2x worse Brier on sports than geopolitics. The other two (DeepSeek-R1, GPT-4.1) are flatter across topics but still weak overall.

### News-context finding

"Adding news context sometimes hurts performance through mechanisms like 'recency bias' and 'rumour overweighting,' indicating domain-dependent brittleness rather than consistent improvement."

This contradicts the Halawi 2024 finding (retrieval is the biggest gain, -0.020 Brier). The reconciliation is that benchmark and topic matter: on broad mixed-topic post-cutoff benchmarks (Halawi), retrieval helps; on topic-stratified benchmarks ("Future Is Unevenly Distributed"), retrieval helps less and hurts in some topics.

## LLM-as-a-Prophet / Prophet Arena (arXiv 2510.17638)

### Setup

- 1,367 resolved events from 72,136 total prediction markets.
- Domains: politics, economics, sports, entertainment, science.
- Evaluation: Brier + calibration error (ECE) + market return.

### Brier scores

| Model | Brier |
|---|---|
| GPT-5 (Reasoning) | 0.184 |
| Claude Sonnet 4 (Reasoning) | 0.194 |
| Market baseline | 0.187 |

Range across 23 models: 0.18 - 0.22. Models cluster around the market.

### Calibration

ECE: strong models ≤ 0.05; weaker 0.06-0.20. "All the selected LLMs demonstrate better calibration than the market baseline." GPT-5 excels in the extreme probability bins (0-0.1 and 0.9-1.0).

### Temporal pattern (load-bearing for v4)

"Markets incorporate breaking information more rapidly than LLMs, quickly surpassing LLMs in short-term accuracy" as resolution approaches. LLMs match or beat markets at long horizons but lose advantage within 3 hours of resolution.

For Project Kalshi: v1 trades at T-35d (long horizon). The Prophet Arena finding is mildly positive for v4: at long horizons, LLMs can compete with markets. But the "compete" is "Brier near market" not "Brier substantially better than market," consistent with the AIA Forecaster MarketLiquid finding.

### Market return

Top model (GPT-5R) achieves average market-trading return of 0.943, BELOW break-even (1.0). Even when LLMs match market Brier, they do NOT generate trading profits. "Forecasts with worse Brier scores can achieve higher market returns" - Brier accuracy and trading P&L are decoupled.

For Project Kalshi: even if v4 Track B produces LLM forecasts at market-baseline Brier, the published evidence is that this does NOT translate to positive trading returns. The trading-P&L step requires additional signal (market mis-pricing direction) not directly captured by Brier.

## PrediBench + BTF-2 (live leaderboards)

### PrediBench

- Tests Polymarket top-10 trending events (1-week volume).
- Excludes crypto (high volatility).
- Markets ending within 2 months.
- Models tested via smolagents framework with web_search and visit_webpage tools.
- Headline: "Most recent/powerful models are becoming profitable. Half the models beat the market baseline." Grok-4 +6% returns.
- No published Brier numbers for individual models in the blog (live leaderboard at predibench.com).
- Practical pipeline: web search + structured output (rationale, estimated_probability, bet, confidence).
- Caveat: "this pipeline, in its current state, would certainly not be viable under real investment conditions" (no bid-ask spread modeling).

### BTF-2 (April 2026)

- 1,417 pastcasting questions, frozen 15M-document corpus.
- FutureSearch Agent ensemble: Brier 0.119 (leading).
- Opus 4.6 Agent: 0.130.
- Gemini 3.1 Pro Agent: 0.141.
- "Ensemble significantly more accurate than any single frontier agent."

## Synthesis numbers to pin (across the cluster)

### State-of-the-art Brier on different benchmarks

| System | Benchmark | Brier |
|---|---|---|
| AIA Forecaster | FB-7-21 (mixed) | 0.108-0.113 |
| AIA Forecaster | MarketLiquid (hard) | 0.126 |
| Market consensus | MarketLiquid | 0.111 |
| Superforecaster | FB-7-21 | 0.111 |
| FutureSearch Agent | BTF-2 (hard pastcast) | 0.119 |
| o3 (best non-agentic) | Janna Lu 2025 broad | 0.135 |
| GPT-5 Reasoning | Prophet Arena (prediction markets) | 0.184 |
| GPT-4.5 | ForecastBench 2026 | 0.101 |

### Cost vs accuracy spread (no published Haiku / 4o-mini Brier)

| Tier | Approx Brier | Models | $/MTok input |
|---|---|---|---|
| Top reasoning | 0.13-0.18 | o3, GPT-5R, AIA agentic | ~$10-20 |
| Frontier | 0.15-0.22 | GPT-4.1, Opus 4.x, Sonnet 4 | ~$5-15 |
| Mid frontier | 0.17-0.21 | Claude 3.5 Sonnet, GPT-4o | ~$3-5 |
| Cheap | UNMEASURED | Haiku 4.5, GPT-4o-mini | ~$0.15-1 |
| Older | ~0.25 (random) | GPT-3.5, Claude 2, Mistral 7B | <$1 |

### Topic-specific LLM weakness on sports

Triangulated finding across:
- "Future Is Unevenly Distributed" 2025: 3 of 4 frontier models worse on sports than geopolitics.
- Janna Lu 2025: o3 sports 37% worse than politics.
- v3 sports-prediction-ceiling-2022-2024.md: free-feature sports prediction ceiling is +1-3pp gross edge.

**This is the load-bearing bearish signal for v4 Track B's prior on Project Kalshi's mostly-sports universe.**

## Pin quotes

> (AIA Forecaster) "On FORECASTBENCH ... the system achieves results that are statistically indistinguishable from human superforecasters."

> (AIA Forecaster) "On the more challenging MarketLiquid benchmark, the AIA Forecaster (0.108) lags behind market consensus (0.098). However, an ensemble combining the AIA Forecaster and market prices achieves a Brier score of 0.092."

> (Janna Lu 2025) "Frontier models surpass crowd performance but still significantly underperform a group of experts."

> ("Future Is Unevenly Distributed") "Forecasting ability is highly variable as it depends on what, and how, we ask. Strongest: Geopolitics. Weakest: Finance and Sports."

> (Prophet Arena) "Markets incorporate breaking information more rapidly than LLMs, quickly surpassing LLMs in short-term accuracy."

> (Prophet Arena) "Forecasts with worse Brier scores can achieve higher market returns" (Brier-vs-P&L decoupling)

## What is NOT in the cluster

- **No Haiku 4.5 or GPT-4o-mini benchmark Brier.** "Prompt Engineering LLMs' Forecasting Capabilities" 2025 (arXiv 2506.01578) tests Claude 3.5 Haiku but full extraction blocked by binary PDF; abstract / search results do not report a Haiku Brier number competitive with frontier.
- **No Kalshi-specific evaluation.** All benchmarks use Metaculus, Polymarket, Manifold, RCP, or auto-generated dataset questions. Kalshi is not on the source list.
- **No long-horizon sports market specifically tested.** Prophet Arena includes sports in its 5 domains but specific per-domain Brier not pulled (PDF format issue).
- **No retail-budget cost analysis.** AIA Forecaster does not disclose model versions or per-query cost. PrediBench mentions $1/market budget but does not analyze API costs.

## Implications for Project Kalshi v4

1. **The best published LLM-forecaster (AIA, Nov 2025) lags market consensus on hard liquid markets by 0.015 Brier.** This is the literature-bounded honest expectation for v4 Track B on Kalshi sports: LAG the price, not beat it.

2. **Sports is documented as one of the worst LLM topics.** v1's universe is sports-heavy. Track B inherits a structural disadvantage.

3. **The "ensemble with market" pattern is the only documented path to a positive Brier-skill result.** AIA + market beats market by 0.014 Brier. Translated to Project Kalshi: a forecaster that combines Kalshi-price + LLM-output may have measurable additive value (~1-2pp probability accuracy), but this is FAR below the C6 threshold (+14.47pp). The LLM ensembling case for v4 must clear C6 standalone, not via "combine with the very price you're trying to beat."

4. **Reasoning models substantially outperform non-reasoning frontier and older models.** Per Janna Lu 2025: o3 0.135 vs GPT-4o 0.188 (0.05 Brier gap). Reasoning capability matters. Haiku 4.5 ships with extended reasoning; the empirical question is whether Haiku 4.5's reasoning is strong enough for forecasting. NOT MEASURED in any published benchmark.

5. **Platt scaling is the canonical post-processing.** AIA ablation: -0.007 Brier improvement. v4 should adopt Platt with parameter √3.

6. **Long-horizon LLM advantage over markets (Prophet Arena)** is positive for v4. v1 trades at T-35d. At this horizon, LLMs can compete with markets. But the competition is at parity, not at +14.47pp advantage.

7. **Market-trading return decoupled from Brier (Prophet Arena top model market return 0.943, below break-even).** Even matching market Brier does NOT generate trading profits. v4's C6 is a P&L test, not a Brier test. The literature evidence is that even at market-baseline Brier, LLM trading returns are negative.

## Verdict on v4 Track B viability

This cluster represents the strongest empirical case AGAINST v4 Track B clearing C6:

- AIA Forecaster (the published frontier) lags market consensus on hard liquid markets.
- Sports specifically is the LLM weak topic.
- LLM trading returns are below break-even even at market-matching Brier.
- No published evidence that cheap-tier models (Haiku 4.5) are competitive on forecasting.

The only positive signal in the cluster is the "long-horizon LLM advantage" from Prophet Arena, which aligns with v1's T-35d operation. But even this is "match market Brier" not "beat market by 14pp."

**Prior of v4 Track B clearing C6 from this cluster's evidence: 5-15%.** Same as the synthesis in `research/v4/02-llm-forecasting-lit.md` Section 7.

The decisive test is the V4-C pilot: if Haiku 4.5 produces independent estimates (not price-anchored, not random) on a sample of v1-domain Kalshi sports markets, the prior can update upward. Until then, the literature evidence is bearish.
