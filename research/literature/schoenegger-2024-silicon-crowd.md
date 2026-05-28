# Schoenegger, Tuminauskaite, Park, Bastos, Tetlock (2024): "Wisdom of the Silicon Crowd: LLM Ensemble Prediction Capabilities Rival Human Crowd Accuracy"

**Citation.** Schoenegger, Philipp; Tuminauskaite, Indre; Park, Peter S.; Bastos, Rafael Valdece Sousa; Tetlock, Philip E. (Nov 8 2024). Science Advances 10, eadp1528. arXiv:2402.19379 (preprint Feb 2024, v5 Nov 2024). Schoenegger affiliation includes University of St Andrews + LSE; Park is MIT; Tetlock is Penn / Forecasting Research Institute.

**Why it matters for Project Kalshi.** This is the canonical "LLM ensemble matches human crowd" headline. The cleanest empirical demonstration that you do NOT need a frontier-only LLM to reach human-crowd-level forecasting: a 12-LLM ensemble spanning cheap (Mistral 7B, Qwen 7B) to expensive (GPT-4 with Bing, Claude 2) models, in median ensemble, matches a tournament of 925 human forecasters. The result is positive for v4 but the equivalence bounds are wide (Cohen's d=0.5 ≈ ±0.081 Brier window) and only 31 questions are evaluated.

## TL;DR for future Claude

1. **LLM 12-model ensemble median Brier 0.20 (SD 0.12); 925-human crowd median Brier 0.19 (SD 0.19) on 31 binary Metaculus questions (Oct 2023 - Jan 2024).** Difference statistically not significant (t(60)=0.19, p=0.85).

2. **Equivalence bounds wide.** Cohen's d=0.5 corresponds to ±0.081 Brier window. "Bounds of 0.08 in Brier scores are quite wide." So "indistinguishable" means "not different by more than ~50% effect size," a weak claim.

3. **Best individual LLM: GPT-4, Brier 0.15 (SD 0.11).** Worst: Coral / Cohere Command, Brier 0.38 (SD 0.40). The ensemble's accuracy is BELOW the best individual model. Ensembling cuts noise but doesn't add accuracy beyond the best base model.

4. **Documented LLM-specific biases.** (a) Round-number clustering: 38 predictions at exactly 50%, zero at 49% or 51%. (b) Acquiescence (YES) bias: mean prediction 57.4% vs 45% actual YES rate. (c) Topic refusal: Qwen-7B-Chat refused to answer "controversial" questions. (d) Overconfidence and poor calibration.

5. **Study 2 (LLM update on human forecast).** When LLMs see the median human forecast, GPT-4 and Claude 2 improve their accuracy by 17-28% relative to no-information baseline. But "simple aggregation" (averaging human + machine) outperformed the LLM's reasoned update. Even when LLMs update on human signal, they update INFERIORLY to a naive average.

## Sample and methodology

**12 LLMs tested:**
- High-end: GPT-4, GPT-4 with Bing, Claude 2, PaLM 2 (Chat-Bison@002), Bard (PaLM 2)
- Mid: GPT-3.5-Turbo-Instruct, Llama-2-70B, Solar-0-70B, Falcon-180B
- Low: Mistral-7B-Instruct, Qwen-7B-Chat
- Other: Coral / Cohere Command

**Study design.**
- 31 binary forecasting questions from Metaculus tournament (Oct 2023 - Jan 2024).
- 925 human forecasters provided at least one prediction (median ~50 forecasts per question).
- Each LLM queried 3 times per question, within 48 hours of question opening.
- 1,007 individual machine forecasts collected total.
- Ensemble = simple median across the 12 LLMs.

**Questions span topics:** Conflict (Middle East), interest rates, literary prizes, English electoral politics, Indian air quality, cryptocurrency, consumer technology, space travel. No US sports questions in this sample.

## Headline numbers to pin

### Aggregate Brier (median across 31 questions)

| Forecaster | Median Brier | SD |
|---|---|---|
| LLM 12-model ensemble | 0.20 | 0.12 |
| Human crowd (925 forecasters) | 0.19 | 0.19 |
| 50% no-info baseline | 0.25 | - |

### Statistical tests

| Test | Statistic | p-value | Interpretation |
|---|---|---|---|
| H2: LLM ensemble ≠ human crowd | t(60) = 0.19 | 0.850 | Fail to reject null of equal accuracy |
| Equivalence (Cohen's d=0.5) lower bound | t = 2.16 | 0.017 | Within bound (significant) |
| Equivalence upper bound | t = -1.78 | 0.040 | Within bound (significant) |

"Provides evidence that the LLM crowd is as accurate as the human crowd within these bounds. However, bounds of 0.08 in Brier scores are quite wide."

### Individual LLM ranges

| LLM | Median Brier | SD |
|---|---|---|
| GPT-4 (best) | 0.15 | 0.11 |
| GPT-4 with Bing | similar to GPT-4 | - |
| Claude 2 | mid | - |
| Llama 2 70B | mid | - |
| Coral / Cohere Command (worst) | 0.38 | 0.40 |
| Mistral 7B, Qwen 7B | near random (~0.25) | - |

The ensemble Brier 0.20 is WORSE than GPT-4 alone (0.15). Ensembling didn't help here; it diluted the best model.

### Per-topic Brier (informational, small n per cell)

| Topic | Mean Brier | N |
|---|---|---|
| Law | 0.100 | 3 |
| Literature | 0.120 | 1 |
| Economics | 0.143 | 4 |
| Conflict | 0.171 | 7 |
| Technology | 0.173 | 3 |
| Politics | 0.237 | 9 |
| Climate | 0.303 | 3 |
| Education | 0.360 | 1 |

LLMs strongest on deterministic-leaning topics (law, literature, economics); weakest on volatile topics (politics, climate). **No sports questions in this sample.**

### Calibration index (CI)

| LLM | CI |
|---|---|
| Falcon-180B | 0.027 (best) |
| LLM aggregate | 0.041 |
| Coral / Cohere Command | 0.212 (worst) |

Lower CI = better calibrated. Most models have substantial overconfidence.

## Pin quotes

> "Our LLM crowd outperforms a simple no-information benchmark and is not statistically different from the human crowd." (Abstract)

> "Across all questions and all models, a total of 38 predictions were entered for 50%, but no predictions were given for 49% or 51%." (Round-number bias)

> "Most models showing overconfidence, i.e., they assign higher probabilities to outcomes than is warranted by the empirical facts." (Calibration failure mode)

> "However, bounds of 0.08 in Brier scores are quite wide." (Self-acknowledged limitation of equivalence claim)

> "Underperform simple aggregations" (LLMs underperform naive human+machine averaging even after updating on human signal)

> "Alibaba Cloud's Qwen-7B-Chat was substantially more likely to refuse forecasting on potentially controversial questions like conflict." (Topic refusal bias)

## What is NOT in the paper

- **No US sports questions.** The topic distribution skews political/conflict/technology/economics. Project Kalshi v4 inherits no sports-specific evidence from this paper.
- **No Claude 3.x, GPT-4o, or later models.** The 12 LLMs are 2023-vintage. Newer models likely improve absolute Brier (per ForecastBench 2026 update showing o3 0.135, GPT-4.5 0.101).
- **No fine-tuning or retrieval system.** Each LLM queried plain (GPT-4 with Bing is the only retrieval-equipped model in the lineup). The Halawi 2024 system architecture is not represented.
- **No cost analysis.** Each query is treated as free / equal-cost.
- **n=31 is small.** Power to detect Brier differences smaller than 0.08 is limited.

## Implications for Project Kalshi v4

1. **Ensembling 12 LLMs matches human crowd, BUT the ensemble Brier (0.20) is WORSE than the best individual LLM (GPT-4 at 0.15).** Ensembling helps the median LLM more than it helps a top LLM. For v4 with Haiku 4.5 as the only viable model, the relevant comparison is "single Haiku query" vs "3 Haiku queries with different prompts averaged" rather than "12 LLMs ensembled."

2. **Round-number clustering is severe (38 predictions at 50%, zero at 49%/51%).** Translated to Project Kalshi: if Haiku 4.5 has the same bias, the LLM will produce a small set of distinct probability values, making it hard to express fine-grained edges over the Kalshi price. Mitigation: ask for "a probability to two decimal places" and average multiple queries.

3. **Acquiescence bias (LLM mean 57.4% YES vs 45% actual) is ~12pp.** This is the same direction as Schoenegger 2024's no-sports sample; the bias may or may not generalize to sports. If it generalizes, Haiku 4.5 will OVER-estimate v1's favorites and recommend the same trades v1 already takes. If anti-correlated with v1's existing edge, it adds noise; if correlated, it doesn't add information.

4. **The "LLM matches human crowd" finding does NOT mean "LLM beats Kalshi market price."** The 925-forecaster Metaculus crowd is a strong baseline but not a prediction-market price baseline. Schoenegger's experiment did NOT measure LLM vs market price. v4 master plan's C6 is the latter, and the literature (Karger 2024 ForecastBench, AIA Forecaster MarketLiquid) shows LLMs lag market price on liquid markets.

5. **Falcon-180B has the best calibration (CI 0.027)** but is no longer available (Technology Innovation Institute discontinued public API access in 2024). For v4, Claude Haiku 4.5 likely has CI in the middle of Schoenegger's spread (~0.05-0.10), needing Platt scaling correction.

6. **Topic refusal (Qwen 7B refusing conflict questions) is a flag for Haiku 4.5 on sports betting questions.** Anthropic's RLHF may shape Haiku 4.5 to be more conservative or refuse on certain sports-betting framings. v4 should test this empirically in V4-C pilot.

## Verdict on v4 Track B viability

Schoenegger 2024 provides the MOST OPTIMISTIC reading of LLM forecasting in the 4-paper set: an ensemble matches a 925-human crowd on broad topics. But:

- The equivalence bounds are wide (±0.081 Brier).
- The ensemble Brier (0.20) is worse than the best individual LLM (0.15).
- 31 questions is a thin sample; statistical power is limited.
- No sports questions; v4's primary domain is unrepresented.
- The "human crowd" is a Metaculus tournament, NOT a prediction-market price; v4 must beat the latter.

For v4 to clear C6, an LLM forecaster must beat the Kalshi PRICE (not a human crowd average) by enough to clear the +14.47pp threshold. Schoenegger 2024 does NOT measure LLM vs market price; the closest measurement (AIA Forecaster MarketLiquid Brier 0.126 vs market 0.111, LLM lags by 0.015) is bearish.

**Schoenegger 2024 raises the prior on "LLM forecaster is operable at all on prediction-market questions" but does NOT raise the prior on "LLM beats Kalshi price by +14.47pp on long-horizon sports favorites."** The latter remains low (5-15% per synthesis at `research/v4/02-llm-forecasting-lit.md`).
