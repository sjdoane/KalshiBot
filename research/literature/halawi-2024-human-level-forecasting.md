# Halawi, Chen, Hashimoto, Steinhardt (2024): "Approaching Human-Level Forecasting with Language Models"

**Citation.** Halawi, Danny; Chen, Adam; Hashimoto, Tatsunori B.; Steinhardt, Jacob (Feb 2024). arXiv:2402.18563. NeurIPS 2024 spotlight. UC Berkeley. Published proceedings: https://proceedings.neurips.cc/paper_files/paper/2024/file/5a5acfd0876c940d81619c1dc60e7748-Paper-Conference.pdf. Code referenced in paper but not pulled in this extraction.

**Why it matters for Project Kalshi.** This is THE canonical citation for LLM-as-forecaster. It is the source the v4 master plan references when it says "Halawi et al. 2024 documents LLM forecasting approaching aggregated crowd accuracy." The paper's headline number (system Brier 0.179 vs crowd 0.149 on 914 binary questions across 5 platforms) is the upper-bound the v4 Track B has to evaluate against. Per-platform breakdowns include Polymarket and Manifold, which are the closest platform analogues to Kalshi available in the literature.

## TL;DR for future Claude

1. **System Brier 0.179 on 914 binary questions from 5 platforms** (Metaculus, Good Judgment Open, INFER, Polymarket, Manifold), test set published after June 1 2023 (post-LLM-cutoff). Human crowd Brier 0.149 on same set. Gap 0.030 in crowd's favor.

2. **The system BEATS the crowd on UNCERTAIN-crowd questions** (crowd predictions in 0.3-0.7): system Brier 0.199 vs crowd 0.246. But it LAGS the crowd on confident-crowd questions (< 0.05 or > 0.95). This is the load-bearing failure mode for v4 because v1 trades at 0.70-0.95 YES (the confident regime).

3. **Retrieval is the biggest gain.** Ablation: retrieval -0.020 Brier, fine-tuning -0.007 Brier, combined system -0.027 from zero-shot baseline 0.206. Retrieval > fine-tuning by 3x.

4. **Per-platform Brier shows the LLM closes more of the gap on noisier platforms.** Metaculus crowd 0.104 / system 0.134 (gap 0.030); Manifold crowd 0.200 / system 0.219 (gap 0.019). Polymarket crowd 0.127 / system 0.172 (gap 0.045). On the better-calibrated platforms (Metaculus, Polymarket), the LLM has more room to fall behind in absolute terms.

5. **RLHF / safety-induced hedging is the central failure mode** at high crowd confidence. The paper attributes this to "the model rarely outputs low probabilities" due to safety training. This means a Project Kalshi v4 forecaster, applied at the 0.70-0.95 price band, will structurally hedge inward and fail to confirm the price's directional confidence.

## Sample and methodology

**Test set.** 914 binary questions published after June 1 2023:
| Platform | N | Notes |
|---|---|---|
| Metaculus | 275 | Well-calibrated competitive platform |
| Good Judgment Open | 38 | Superforecaster-adjacent |
| INFER | 4 | Small subset |
| Polymarket | 300 | Real-money crypto market |
| Manifold | 297 | Play-money community market |
| **Total** | **914** | |

**Training set.** 13,253 candidate samples; 6,000 used for the fine-tune. All resolved before the June 1 2023 cutoff.

**Models.**
- Base reasoning: GPT-4-1106-Preview (knowledge cutoff April 2023).
- Fine-tuned: GPT-4-0613 fine-tuned via the OpenAI API on 6,000 samples.
- Auxiliary tasks (article retrieval ranking, summarization): Claude-2.1 and GPT-3.5-Turbo.
- No Claude-3.x or later models. The paper predates Claude 3 Opus by approximately one month.

**Retrieval pipeline.**
1. Query reformulation: convert the forecasting question into 6 search queries.
2. Article retrieval: 6 sources via Bing News Search and Wikipedia.
3. Relevancy ranking and filtering: GPT-3.5-Turbo and Claude-2.1 score relevance.
4. Summarization: extract key facts and recency-weighted summaries.
5. Top-k articles fed into the forecast prompt.

**Forecast prompt.** Structure: "Pose the question + description + resolution criteria + key dates + top-k summaries." Then ask the model to reason and output a probability.

**Aggregation.** When the system was queried with multiple article summarizations or hyperparameter settings, the final prediction averages across.

## Headline numbers to pin

| Metric | Value |
|---|---|
| Test set N | 914 binary questions |
| Test date floor | June 1 2023 (post LLM cutoff) |
| Full system Brier (test) | 0.179 (±0.003) |
| Human crowd Brier (test) | 0.149 (±0.003) |
| Gap | 0.030 in crowd's favor |
| GPT-4-1106 zero-shot Brier | 0.208 |
| GPT-4 no-retrieval no-finetune Brier | 0.206 |
| GPT-4 retrieval, no fine-tune | 0.186 |
| Retrieval contribution | -0.020 Brier |
| Fine-tune contribution | -0.007 Brier |
| Combined system improvement | -0.027 Brier vs baseline |
| Random baseline | 0.250 |

### Per-platform Brier

| Platform | System Brier | Crowd Brier | Gap |
|---|---|---|---|
| Metaculus | 0.134 | 0.104 | 0.030 |
| Good Judgment Open | 0.193 | 0.157 | 0.036 |
| Polymarket | 0.172 | 0.127 | 0.045 |
| Manifold | 0.219 | 0.200 | 0.019 |

### Brier on subset where crowd is uncertain (predictions in 0.3-0.7)

| Forecaster | Brier on uncertain subset |
|---|---|
| System | 0.199 |
| Crowd | 0.246 |

System BEATS crowd by 0.047 on uncertain-crowd questions; LAGS crowd on certain-crowd questions.

### Calibration

| Metric | System | Crowd |
|---|---|---|
| RMS calibration error | 0.42 | 0.38 |

The paper notes "naturally well calibrated" without explicit post-processing. The follow-up AIA Forecaster paper (arXiv 2511.07678) refutes this on harder benchmarks and shows Platt scaling adds -0.007 Brier improvement, suggesting Halawi 2024's calibration claim is benchmark-specific.

## Pin quotes

> "On average, the system nears the crowd aggregate of competitive forecasters, and in some settings surpasses it. Our work suggests that using LMs to forecast the future could provide accurate predictions at scale and help to inform institutional decision making." (Abstract)

> "When the crowd's predictions are between .3 and .7, the system's Brier score is .199 compared to the crowd's .246." (System beats crowd on uncertain questions)

> "The system underperforms the crowd on questions where they are highly certain, likely because it rarely outputs low probabilities. This stems from the model's tendency to hedge predictions due to its safety training." (Failure mode on high-confidence questions; load-bearing for Project Kalshi)

> "Our system is naturally well calibrated." (Calibration claim; refuted by later AIA paper)

## What is NOT in the paper

- **No Claude-3 family or GPT-5 / o3 family evaluation.** The base model is GPT-4-1106-Preview, the strongest model available at submission.
- **No sports-specific accuracy decomposition.** The platforms (Metaculus, GJOpen, INFER, Polymarket, Manifold) are mixed-topic. The paper does not break Brier out by topic (sports vs geopolitics vs economics).
- **No cost analysis.** The paper does not quantify $/forecast or the cost of operating the system. The OpenAI fine-tune adds significant one-time cost ($10s to $100s for the 6,000-sample fine-tune in 2024 pricing); per-forecast cost is dominated by the news-retrieval API + Claude-2.1 / GPT-3.5 summarization + GPT-4 reasoning, plausibly $0.10-$0.50 per forecast.
- **No cheap-model comparison.** Claude-2.1 and GPT-3.5-Turbo are used only for auxiliary tasks (retrieval ranking, summarization), not as forecaster models. The paper does not test cheap-model-as-forecaster.
- **No prompt-sensitivity / robustness analysis.** Single canonical prompt template; no documentation of how rephrasing affects accuracy.
- **No date-redaction or knowledge-cutoff sensitivity analysis** of the type proposed in v4 master plan S-B1. The paper relies entirely on "test set is post-cutoff" as the leak control.
- **No price-anchoring analysis.** The paper does not include Kalshi or Polymarket prices in the LLM prompts at forecast time (the prompts contain question text only, not market consensus); but it also does not test what happens when prices are included.

## Implications for Project Kalshi v4

1. **The +0.030 Brier gap (system vs crowd) on Halawi's broad test set translates to a noisy ceiling for v4.** v1's market is Kalshi (mostly sports), not Halawi's broad benchmark. The closest analogue in Halawi is the Polymarket subset (n=300), where the gap is 0.045 not 0.030. Project that onto sports-heavy Kalshi: expected LLM Brier deficit relative to Kalshi price is likely 0.04-0.06.

2. **The high-confidence failure mode is directly applicable.** v1's price band 0.70-0.95 YES is the exact regime where Halawi documents the system LAGS the crowd. The Platt-scaling mitigation discussed in AIA Forecaster 2025 helps but is documented at only -0.007 Brier; not enough to close the deficit on high-confidence questions.

3. **The retrieval pipeline is non-trivial.** Halawi uses Bing News + Wikipedia + summarization + ranking. For v4's $32 budget with Haiku 4.5 as the workhorse, a free-tier alternative (Brave Search free API, direct Wikipedia summary) is the only viable option. Effect size likely smaller than Halawi's -0.020 Brier (which was Bing-quality + GPT-4-summarized).

4. **The fine-tune effect is small (-0.007 Brier) and not worth Haiku 4.5's customization cost.** v4 should focus on retrieval + calibration + ensembling rather than fine-tuning.

5. **The post-cutoff test set protocol is the cleanest available.** v4 must mirror it: test ONLY on Kalshi markets that resolved after Opus 4.7 cutoff (Jan 2026), per master plan Section 7.2. The Kalshi historical cutoff (2026-03-25) gives a thin 2-month window, but the protocol is non-negotiable for honesty.

6. **Halawi 2024 is the upper bound, not the lower bound.** A retail $32-budget Haiku-only forecaster will not match Halawi's pipeline. Treat Halawi's 0.179 system Brier as the published frontier with a frontier model (GPT-4); a realistic Haiku-only system on Kalshi sports will be worse, plausibly Brier 0.20-0.25.

## Verdict on v4 Track B viability

This paper establishes that **the best-published LLM forecaster as of Feb 2024 underperforms the human crowd by 0.030 Brier on broad mixed-topic prediction-market questions.** For Project Kalshi specifically:
- v1's domain is high-confidence sports (where Halawi's system documented FAILURE mode dominates).
- v1's budget forces Haiku-only operation (where the literature has NO direct measurement).
- v1's edge is +12.47pp over Kalshi price; C6 requires beating v1 by +2pp = +14.47pp total edge above price.

Halawi's documented additive value (system vs underlying GPT-4 baseline) is roughly +0.030 Brier improvement on a broad benchmark, which translates to approximately +1-3pp probability accuracy. **This is structurally an order of magnitude below the C6 threshold.** Track B's prior of clearing C6 on v1's domain is low (5-15% from synthesis in `research/v4/02-llm-forecasting-lit.md` Section 7).
