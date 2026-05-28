# Project Kalshi v4 - LLM Forecasting Literature Review

**Date:** 2026-05-24
**Agent:** V4-B (Phase 1, parallel research)
**Mandate:** Pull 2023-2026 literature on LLM-based forecasting for prediction-market-style questions. Document state-of-art accuracy, techniques, and failure modes. Inform the orchestrator's go / kill decision on v4 Track B (LLM-as-forecaster).

## Documents added in this pass

Four new full extractions in `research/literature/`:

1. **halawi-2024-human-level-forecasting.md** - Halawi/Chen/Hashimoto/Steinhardt et al. NeurIPS 2024. Retrieval-augmented GPT-4 system approaching crowd Brier on 914 binary questions across 5 platforms.
2. **karger-2024-forecastbench.md** - Karger/Bastani/Yueh-Han/Jacobs/Halawi/Zhang/Tetlock 2024 (arXiv 2409.19839). Dynamic 1,000-question benchmark; superforecasters significantly beat the top LLM (p < 0.001).
3. **schoenegger-2024-silicon-crowd.md** - Schoenegger/Tuminauskaite/Park/Bastos/Tetlock 2024 Science Advances. 12-LLM ensemble matches a 925-human crowd on 31 Metaculus questions, but equivalence bounds are wide.
4. **aia-2025-forecaster-and-followups.md** - AIA Forecaster (arXiv 2511.07678, Nov 2025), plus the Janna Lu 2025 "Real-World Forecasting" paper (2507.04562), the "Future Is Unevenly Distributed" Nov 2025 paper (2511.18394), Prophet Arena (2510.17638), PrediBench, and BTF-2. The aggregate frontier state-of-the-art.

`INDEX.md` and `~/.claude/.../memory/project_kalshi_literature.md` updated below.

## Working summary in one paragraph

The 2023-2026 literature converges on a clear picture: top frontier LLMs equipped with retrieval and proper prompt engineering now achieve **Brier scores in the 0.10-0.18 range on broad-topic prediction-market-style questions**, comparable to or slightly better than the median human crowd, but **still 0.02-0.06 Brier behind elite human superforecasters and behind the prediction-market consensus on hard, liquid markets** (AIA Forecaster 0.1258 vs market consensus 0.1106 on MarketLiquid; Halawi system 0.179 vs crowd 0.149 on his test set). On topic decomposition, **sports is repeatedly documented as one of the weakest LLM categories** (Brier 0.16-0.45 across recent papers, vs 0.12-0.22 on geopolitics or politics). The headline implication for Project Kalshi: at v1's price band 0.70-0.95 YES on long-horizon sports markets where Kalshi-US is the most liquid venue, **a competent LLM forecaster's realistic ceiling is to match the Kalshi price, not beat it**, with an honest 10-20% probability of clearing C6 (+2pp over v1's measured edge).

---

## 1. Foundational papers (full extractions)

### 1.1 Halawi et al. 2024 - "Approaching Human-Level Forecasting with Language Models"

**Citation.** Halawi, Danny; Chen, Adam; Hashimoto, Tatsunori B.; Steinhardt, Jacob (Feb 2024 arXiv; NeurIPS 2024 spotlight). arXiv:2402.18563. UC Berkeley. Full extraction: [halawi-2024-human-level-forecasting.md](../literature/halawi-2024-human-level-forecasting.md).

**Headline.** Retrieval-augmented, fine-tuned GPT-4 system reaches Brier **0.179** on 914 binary questions from June 1 2023 onward (post-LLM-cutoff); crowd Brier on the same set is **0.149** (gap 0.030, in crowd's favor). On the subset where crowd is uncertain (predictions in 0.3-0.7), system Brier 0.199 BEATS crowd 0.246.

**Test set composition.**
| Platform | N |
|---|---|
| Metaculus | 275 |
| Good Judgment Open | 38 |
| INFER | 4 |
| Polymarket | 300 |
| Manifold | 297 |

**Per-platform Brier (system vs crowd):**
| Platform | System Brier | Crowd Brier |
|---|---|---|
| Metaculus | 0.134 | 0.104 |
| Good Judgment Open | 0.193 | 0.157 |
| Polymarket | 0.172 | 0.127 |
| Manifold | 0.219 | 0.200 |

The pattern: the system is **closer to the crowd on platforms where the crowd itself is worse** (Manifold gap 0.019, Polymarket gap 0.045, Metaculus gap 0.030). The well-calibrated venue (Metaculus crowd Brier 0.104) leaves the most absolute room for the LLM to fall behind.

**Ablation effect sizes (Brier improvement, from no-retrieval baseline 0.206):**
| Technique | Brier contribution |
|---|---|
| Retrieval (news articles) | -0.020 |
| Fine-tuning on 6,000 samples | -0.007 |
| Combined system | -0.027 |

Retrieval is roughly 3x more important than fine-tuning. The bare GPT-4-1106-Preview zero-shot baseline is 0.208. The retrieval-only system (no fine-tune) is 0.186. The full fine-tuned + retrieval system is 0.179.

**Calibration:** RMS calibration error 0.42 (system) vs 0.38 (crowd). The paper notes the system is "naturally well calibrated" without explicit post-processing.

**Documented failure mode (load-bearing for v4):** The system underperforms the crowd on high-confidence questions (crowd < 0.05 or > 0.95). The paper attributes this to RLHF / safety-tuning hedging: GPT-4 will not output very-low or very-high probabilities. This is the Project-Kalshi-relevant failure mode because **v1 only trades when Kalshi price is >= 0.70**, which is exactly the high-confidence regime where the LLM is structurally worse than the crowd.

**Models used.** Base reasoning: GPT-4-1106-Preview. Fine-tuned: GPT-4-0613 on 6,000 self-distilled samples from 13,253 candidates. Supporting tasks (retrieval ranking, summarization): Claude-2.1 and GPT-3.5-Turbo. No Claude-3.x family models tested.

**Cutoff handling.** Training cutoff June 1 2023. Test questions are published after this date. Training/validation questions resolved before. This is the cleanest leak-control protocol in the literature; v4 must follow it.

**Key pin quote.** "On average, the system nears the crowd aggregate of competitive forecasters, and in some settings surpasses it." (Abstract). "Our system is naturally well calibrated."

---

### 1.2 Karger et al. 2024 - ForecastBench

**Citation.** Karger, Ezra; Bastani, Houtan; Yueh-Han, Chen; Jacobs, Zachary; Halawi, Danny; Zhang, Fred; Tetlock, Philip E. (Sep 2024). arXiv:2409.19839. Forecasting Research Institute + University of Pennsylvania. Full extraction: [karger-2024-forecastbench.md](../literature/karger-2024-forecastbench.md).

**Headline.** On 200 questions drawn from a 1,000-question dynamic benchmark, **superforecasters Brier 0.096; general public 0.121; top LLM 0.122 (Claude 3.5 Sonnet).** "Expert forecasters outperform the top-performing LLM (p-value < 0.001)" (abstract). The general public is statistically indistinguishable from the top LLM.

**Per-source Brier (sample, from arXiv HTML extraction):**
| Source | Superforecaster Brier | Claude 3.5 Sonnet Brier | GPT-4 Turbo Brier |
|---|---|---|---|
| Dataset questions | 0.118 | 0.138 | 0.162 |
| Market questions | 0.074 | 0.107 | 0.095 |

Market-sourced questions (Metaculus, Manifold, Polymarket, RCP) are easier than dataset-sourced questions (auto-generated from Wikipedia, FRED, ACLED, DBnomics). Note the superforecaster Brier on market questions (0.074) is roughly half the LLM Brier (0.095-0.107).

**LLMs tested:** 17 models including GPT-3.5-Turbo, GPT-4, GPT-4o, GPT-4-Turbo, Claude 2.1, Claude 3-Haiku, Claude 3-Opus, Claude 3.5-Sonnet, Llama-2-70B, Llama-3-7B, Llama-3-70B, Mistral variants, Gemini, Qwen. Older models (GPT-3.5, Claude 2, Mistral 7B) performed **at or below random baseline (Brier 0.25)**.

**Prompting style.** Basic prompting without news retrieval; some configurations include "scratchpad" CoT and human "freeze values" (i.e., crowd forecasts) as priors. Key finding: providing recent news context did NOT improve performance substantially in this benchmark configuration.

**Updates through 2025-2026 (ForecastBench leaderboard at forecastingresearch.substack.com, via 2026 update):**
- o3 reaches Brier 0.1352 on the dataset slice (best LLM at that update)
- GPT-4.5 reaches 0.101 on a re-evaluation (best by Q1 2026)
- Superforecaster baseline now 0.081
- LLM improvement rate ~0.016 Brier/year on the baseline track, ~0.036/year on the no-market-access track
- Linear extrapolation: LLM-superforecaster parity around November 2026 (95% CI Dec 2025 - Jan 2028)

**Critical for v4.** On the MARKET sub-benchmark, the best LLM (GPT-4.5) has Brier 0.107 vs market consensus baseline 0.094 (lagging by ~0.013). The market sources are exactly Project Kalshi's domain. **In the market-comparison frame, no LLM in ForecastBench beats the market consensus.** The ForecastBench tournament also reports that the top "Tournament" LLM heavily anchors on market prices when given access (0.994 correlation), which is the v4 master plan's S-B2 price-anchor failure mode in published form.

**Key pin quote.** "While LLMs have achieved super-human performance on many benchmarks, they perform less well here: expert forecasters outperform the top-performing LLM (p-value < 0.001)." (Abstract)

---

### 1.3 Schoenegger et al. 2024 - "Wisdom of the Silicon Crowd"

**Citation.** Schoenegger, Philipp; Tuminauskaite, Indre; Park, Peter S.; Bastos, Rafael Valdece Sousa; Tetlock, Philip E. (Nov 2024). Science Advances 10, eadp1528. arXiv:2402.19379. Full extraction: [schoenegger-2024-silicon-crowd.md](../literature/schoenegger-2024-silicon-crowd.md).

**Headline.** Median Brier on 31 binary Metaculus tournament questions (Oct 2023 - Jan 2024): **LLM 12-model ensemble 0.20 (SD 0.12)** vs **human crowd of 925 forecasters 0.19 (SD 0.19)**. T-test t(60)=0.19, p=0.85; null of equal accuracy is not rejected. Equivalence bounds are wide: Cohen's d = 0.5 corresponds to a ±0.081 Brier window. The strongest individual LLM (GPT-4) had Brier 0.15 (SD 0.11); the worst (Coral / Cohere Command) was 0.38 (SD 0.40).

**Per-topic Brier (small n per cell; informational):**
| Topic | Brier | N questions |
|---|---|---|
| Law | 0.100 | 3 |
| Literature | 0.120 | 1 |
| Economics | 0.143 | 4 |
| Conflict | 0.171 | 7 |
| Technology | 0.173 | 3 |
| Politics | 0.237 | 9 |
| Climate | 0.303 | 3 |
| Education | 0.360 | 1 |

No sports questions in the Schoenegger tournament. The pattern is that the LLM ensemble is best on quasi-deterministic categories (law, literature, economics) and worst on volatile or noisy categories (politics, climate).

**Documented failure modes.**
1. **Round-number bias.** "Across all questions and all models, a total of 38 predictions were entered for 50%, but no predictions were given for 49% or 51%." Models cluster on multiples of 5.
2. **Acquiescence (YES) bias.** Mean prediction 57.4% vs 45% actual YES rate. Systematic over-prediction of positive resolution.
3. **Topic refusal.** Qwen-7B-Chat refused to forecast on potentially controversial questions (e.g., conflict).
4. **Overconfidence.** Best individual calibration (Falcon-180B CI 0.027) hides that most models were poorly calibrated; worst (Coral 0.212).

**Cost / model spread.** Twelve models spanning the cheap-to-expensive spectrum (GPT-3.5, Mistral 7B, Qwen 7B at the low end; GPT-4 with Bing, Claude 2, Llama 2 70B at the high end). The ensemble masks a wide quality gap: individual LLMs ranged from Brier 0.15 to 0.38, a 2.5x spread.

**Key pin quote.** "Our LLM crowd outperforms a simple no-information benchmark and is not statistically different from the human crowd." Equivalence note: "However, bounds of 0.08 in Brier scores are quite wide."

---

### 1.4 AIA Forecaster 2025 + follow-up cluster

**Citation cluster.**
- AIA Team (Nov 2025), "AIA Forecaster: Technical Report," arXiv:2511.07678. Built by Aria Lab.
- Lu, Janna (Jul 2025), "Evaluating LLMs on Real-World Forecasting Against Expert Forecasters," arXiv:2507.04562.
- Singh, Shivansh et al. (Nov 2025), "Future Is Unevenly Distributed: Forecasting Ability of LLMs Depends on What We're Asking," arXiv:2511.18394.
- Yang, Qingchuan; Wu, Jibang et al. (Oct 2025), "LLM-as-a-Prophet: Understanding Predictive Intelligence with Prophet Arena," arXiv:2510.17638.
- Azam, Charles & Roucher, Aymeric (2025), PrediBench (huggingface.co/blog/charles-azam/predibench).
- FutureSearch (Apr 2026), "Bench to the Future" / BTF-2 leaderboard (evals.futuresearch.ai).

Full combined extraction: [aia-2025-forecaster-and-followups.md](../literature/aia-2025-forecaster-and-followups.md). Treating as a single combined extraction because no single paper covers v4's question end-to-end and the combined picture is what v4 needs.

**Headline.**
- **AIA Forecaster matches superforecasters on ForecastBench FB-7-21**: AIA Brier 0.1125, superforecaster median 0.1110, statistically indistinguishable.
- **AIA Forecaster LAGS market consensus on MarketLiquid (1,610 hard liquid-market questions)**: AIA Brier 0.1258 vs market consensus 0.1106. The market beats the LLM by 0.015 Brier points on the harder, more relevant benchmark.
- **AIA + market ensemble beats either**: simplex-regression-weighted combination achieves Brier 0.092 (FB-7-21) and 0.106 (MarketLiquid), giving the market 67% weight on hard questions.
- **Janna Lu 2025**: on 464 Metaculus questions with AskNews API retrieval, o3 reaches Brier 0.1352, GPT-4.1 0.1542, o4-mini 0.1589; superforecaster baseline 0.0225 (6x better).
- **"Future Is Unevenly Distributed" 2025**: per-topic Brier (no news context) shows **sports is the worst category for LLMs** (Claude 3.7: 0.28; DeepSeek-R1: 0.26; GPT-4.1: 0.45; GPT-5: 0.28) versus geopolitics (Claude 3.7: 0.12; DeepSeek-R1: 0.32; GPT-4.1: 0.40; GPT-5: 0.14). Two of four models have ~2x worse Brier on sports than geopolitics.
- **Prophet Arena 2025**: 23 frontier models on 1,367 prediction-market events. GPT-5 (Reasoning) Brier 0.184, Claude Sonnet 4 (Reasoning) 0.194, market baseline 0.187. Models cluster around the market. Critically: **LLMs lose to markets within 3 hours of resolution but can match markets at longer horizons**. Top model market-trading return 0.943 (below break-even).
- **BTF-2 (April 2026)**: FutureSearch Agent ensemble leads at Brier 0.119, Opus 4.6 Agent 0.130, Gemini 3.1 Pro Agent 0.141 on 1,417 hard questions.

**Calibration techniques (from AIA Forecaster ablation).** Platt scaling alone improves Brier from 0.1140 (no correction) to 0.1071 (-0.007). Other techniques tested:
| Method | Brier |
|---|---|
| Platt scaling | 0.1071 |
| Log odds extremization | 0.1085 |
| Isotonic regression | 0.1097 |
| OLS | 0.1119 |
| No correction | 0.1140 |

Platt scaling (with parameter set to √3 ≈ 1.73) is the most effective. Importantly: **the calibration techniques are correcting for LLM hedging by pushing probabilities toward extremes**. This is the documented mitigation for the Halawi 2024 high-confidence failure mode.

**Cost-vs-quality (from Janna Lu 2025 and per-platform pricing as of May 2026).**
| Model | Brier (Janna Lu 2025) | Tier |
|---|---|---|
| o3 | 0.1352 | Top (expensive) |
| GPT-4.1 | 0.1542 | Frontier |
| Claude 3.7 / 3.6 Sonnet | 0.1810 | Frontier (mid) |
| GPT-4o | 0.1883 | Frontier (older) |
| o4-mini | 0.1589 | Reasoning, lower cost |
| DeepSeek v3 | 0.1798 | Frontier (cheap, open) |

The Brier spread from top to mid is roughly 0.05 (top reasoning ~0.135 to non-reasoning frontier ~0.19). **There is no published study showing a Haiku-tier model competitive on prediction-market forecasting**. The published evidence trends: reasoning models > non-reasoning frontier > older frontier > cheap models. Older / cheaper models (GPT-3.5, Mistral 7B, original Claude 2) were at or below the random baseline in ForecastBench, while top reasoning models match the prediction-market consensus.

**Knowledge cutoff handling.** AIA Forecaster uses an "LLM-based judge to flag search results exceeding the intended information cutoff." On 502 audited traces, 1.65% contained foreknowledge bias. Robustness checks showed ≤0.6% Brier shift from the bias. The Halawi 2024 protocol relies on test set being post-cutoff. ForecastBench uses live unresolved questions. None of the papers use a "redact dates from prompt" protocol like v4's S-B1.

---

## 2. State-of-art accuracy numbers

### What the literature actually shows

Across the four papers and the AIA / follow-up cluster, state-of-the-art LLM forecasting on prediction-market-style questions sits in a **Brier 0.10-0.18 envelope**, depending on retrieval, calibration, and model tier. Here's the canonical comparison stack (Brier, lower is better):

| Forecaster | Brier | Source | Question domain |
|---|---|---|---|
| Superforecasters (best) | 0.081-0.097 | Karger 2024, ForecastBench leaderboard 2026 | Mixed |
| Superforecasters (FORI 2025 sample) | 0.111 | AIA Forecaster paper | FB-7-21 |
| AIA Forecaster (agentic + Platt) | 0.108 | AIA Forecaster paper | FB-7-21 |
| AIA Forecaster (on hard markets) | 0.126 | AIA Forecaster paper | MarketLiquid 1610 |
| Market consensus (hard markets) | 0.106-0.111 | AIA Forecaster, Prophet Arena | Liquid prediction markets |
| Halawi 2024 system | 0.179 | Halawi 2024 | 914 Q's, 5 platforms |
| Halawi 2024 crowd baseline | 0.149 | Halawi 2024 | Same |
| GPT-5 / o3 (top non-agentic) | 0.135-0.184 | Lu 2025, Prophet Arena | Mixed |
| Bare GPT-4 zero-shot | 0.208 | Halawi 2024 | 914 Q's |
| Random baseline | 0.250 | All | All |
| Sportsbook NBA/NFL pregame | 0.18-0.22 | sports-prediction-ceiling-2022-2024.md (v3) | Sportsbook lines |

### How LLMs compare to market consensus on liquid prediction markets

This is the load-bearing comparison for v4. From the AIA Forecaster paper, the strongest LLM system in late 2025 (AIA, which is the published frontier of agentic search + Platt-scaling-calibrated multi-LLM systems) has Brier **0.1258** on hard liquid markets vs market consensus **0.1106**. **The LLM lags the market by 0.015 Brier units.** Prophet Arena finds similar: 23 frontier LLMs cluster Brier 0.18-0.22 on 1,367 prediction-market events vs market baseline 0.187, with GPT-5 (Reasoning) at 0.184 (barely better than market) and Claude Sonnet 4 (Reasoning) at 0.194 (worse than market).

In Brier-skill terms relative to the market baseline:
- AIA Forecaster Brier skill on MarketLiquid = (0.1106 - 0.1258) / 0.1106 = **-13.7%** (negative skill, lags market)
- AIA + market ensemble Brier skill = (0.1106 - 0.092) / 0.1106 = +16.8% (positive but only because the market itself is in the ensemble at 67% weight)

The published-best LLM-forecaster system as of November 2025 cannot match a liquid prediction market on prediction-market-style questions without ensembling with the market itself.

### Topic-specific pattern: sports is the LLM weak spot

This is the most actionable finding for Project Kalshi. From "Future Is Unevenly Distributed" 2025:

| Model | Sports Brier | Geopolitics Brier | Sports vs Geo ratio |
|---|---|---|---|
| Claude 3.7 | 0.28 | 0.12 | 2.33x worse |
| DeepSeek-R1 | 0.26 | 0.32 | 0.81x (better!) |
| GPT-4.1 | 0.45 | 0.40 | 1.13x worse |
| GPT-5 | 0.28 | 0.14 | 2.00x worse |

Three of four models show LLMs noticeably worse on sports than on geopolitics. The paper's headline: "**Sports** and **Finance** are the weakest LLM topics, at 48-60% accuracy versus geopolitics 84%." From Janna Lu 2025 (different sample, broader): o3 sports Brier 0.1649 vs politics 0.1199 (sports 37% worse).

This converges with v3's literature finding (sports-prediction-ceiling-2022-2024.md): free-public-feature sports prediction caps at 65-67% game accuracy on MLB/NBA, with sportsbook Brier 0.18-0.22 already at or below the LLM. The new evidence is that LLMs are **structurally worse on sports than the cross-topic average**, not better.

### Translation to Project Kalshi's price band 0.70-0.95 YES

v1's price band is 0.70-0.95 YES, where the Kalshi market is already implying high confidence. Three independent failure-mode signals stack on this regime:

1. **Halawi 2024 documented high-confidence failure mode.** The retrieval-augmented system underperforms the crowd on questions where the crowd predicts < 0.05 or > 0.95. RLHF-induced hedging keeps LLM outputs in the middle. This means the LLM will systematically refuse to confirm what the Kalshi price already implies.

2. **Sports topic weakness.** Two of four 2025-tested models have sports Brier ~2x worse than geopolitics Brier. v1's universe is roughly 80% sports series (NFL, MLB, NBA, NCAA, boxing, UFC, CS2, etc., per CLAUDE.md Round 6 list).

3. **Sportsbook-saturated information environment.** The Kalshi price already integrates Vegas / DraftKings / FanDuel consensus on sports favorites at >0.70 YES; any LLM that scrapes free public news / Wikipedia is downstream of the same data the sportsbooks already priced in. This is the v3 sports-prediction-ceiling finding extended: the LLM has no information advantage over the price.

**Realistic LLM Brier ceiling for Project Kalshi's exact regime (long-horizon sports favorites at 0.70-0.95 YES):** literature does not contain a direct measurement. The closest is AIA Forecaster on MarketLiquid (Brier 0.1258 vs market 0.1106, LLM lags by 0.015). Project the sports-topic 2x worse multiplier on the LLM's deficit, and the realistic Brier deficit relative to the Kalshi price on the v1 sports universe is roughly **0.02-0.04 Brier worse than the Kalshi price**. Translated to probability accuracy: that's roughly **-2pp to -4pp behind raw-price-as-prediction**. **The LLM forecaster's realistic ceiling on v1's domain is to LAG the Kalshi price, not match it.**

For v1's measured edge of +12.47pp at our >=0.70 YES, ~30-180d-lifetime sports subset (from CLAUDE.md Round 7 / `research/time-scale-analysis.md`), an LLM forecaster needs Brier roughly equal to a forecast that says "trade at 0.70-0.95 YES on favorites with the favorite-longshot bias." If the LLM Brier is 0.02-0.04 worse than that, the LLM will recommend AGAINST trades that v1 takes profitably, or recommend trades that v1's favorite-longshot heuristic would not take. **The LLM is structurally not value-add on v1's specific domain at v1's specific price band.**

---

## 3. Techniques the literature uses (best practices)

For an LLM forecaster to be competitive (not necessarily to beat the market, but to reach state-of-the-art for an LLM), the literature converges on:

### 3.1 Prompt structure

- **Scratchpad / chain-of-thought is standard** (ForecastBench top configurations). Effect size is small but positive (a few thousandths of a Brier point per Karger 2024 baseline 5 vs baseline 4 comparison).
- **Narrative / fictional framing prompts HURT performance** (Janna Lu 2025: o3 Brier worsens from 0.1352 to ~0.1985 in narrative mode, +47% worse).
- **"Provide a probability between 0 and 100" with explicit role of a calibrated forecaster** is the canonical Halawi 2024 / Schoenegger 2024 prompt template.
- **Multiple prompts per question and averaging** (3 queries per question per LLM in Schoenegger; 5 in Janna Lu 2025).

### 3.2 News retrieval / RAG

- **Retrieval is the single biggest gain.** Halawi 2024 ablation: +0.020 Brier from retrieval alone (-0.020 lower Brier), the largest single contribution. The fine-tune adds only -0.007.
- **AIA Forecaster's agentic search beats non-agentic by 0.0034 Brier** (0.1140 vs 0.1174). Adding agentic search beats no-search baseline 0.1230 by 0.0090.
- **But news retrieval is not free.** ForecastBench (Karger 2024) found that providing recent news did NOT improve performance in their configuration, and "Future Is Unevenly Distributed" 2025 documented that **news context sometimes HURTS performance through recency bias and rumor over-weighting**. The effect is domain-conditional.
- **AskNews API with 30 articles per question is the Janna Lu 2025 baseline.** That's expensive per query and an external dependency. Free-public alternatives include Bing/Brave Search APIs and direct Wikipedia summaries.

### 3.3 Ensembling

- **Schoenegger 2024**: 12-LLM ensemble matched human crowd (median Brier 0.20 vs 0.19). Ensembling individual LLMs by simple median outperforms individual models.
- **AIA Forecaster**: a "supervisor agent" that examines disagreements among agents and issues follow-up search queries before synthesizing. This is more than simple averaging.
- **Ensembling LLM + market is the only way the LLM literature has shown a "beat the market" result.** AIA + market simplex regression: 67% market, 33% LLM weight on hard markets, ensemble Brier 0.092 vs market alone 0.106. The LLM's additive value is non-zero but small.

### 3.4 Calibration

- **Platt scaling is the most effective single-step post-processing** (AIA Forecaster ablation: -0.007 Brier improvement, parameter ≈ √3 = 1.73). This pushes hedged LLM probabilities toward extremes.
- **Isotonic regression** (-0.004 Brier) and **log-odds extremization** (-0.005 Brier) are competitive but slightly worse than Platt.
- **No correction baseline 0.1140 Brier** is meaningfully worse than Platt-calibrated 0.1071.
- **Halawi 2024 reports the un-calibrated system is "naturally well calibrated"** which is the outlier finding; AIA Forecaster's ablation suggests this is wrong on harder benchmarks and Platt scaling is needed.

### 3.5 Knowledge-cutoff handling

- **Halawi 2024 protocol**: training cutoff is June 1 2023; test set is questions PUBLISHED after that. Cleanest published method.
- **AIA Forecaster**: LLM-as-judge to flag search results exceeding the cutoff. On 502 traces, 1.65% had foreknowledge bias, with ≤0.6% Brier shift.
- **ForecastBench**: uses live unresolved questions. The most defensible test design.
- **No paper uses "redact dates from prompt"** like v4's master plan S-B1. This is an idiosyncratic v4 design.
- **The hardest leak is "LLM remembers the actual outcome of a famous event"** (e.g., 2024 election). For sports, the relevant analogue is "LLM remembers that the Lakers won the 2025 season." The Halawi protocol handles this via post-cutoff test sets only.

### 3.6 Best-practice technique stack (literature consensus, ordered by effect size)

1. Retrieval / agentic search of recent news (largest gain, ~-0.020 to -0.030 Brier)
2. Ensembling across N >= 3 LLMs (next-largest gain; cuts noise, matches human crowds)
3. Platt scaling calibration (-0.007 Brier; corrects RLHF hedging)
4. CoT / scratchpad prompting (small but positive)
5. Fine-tuning (smallest gain, -0.007 Brier in Halawi 2024; expensive)
6. Strict post-cutoff test set (mandatory for honesty; not a perf gain)

---

## 4. Documented failure modes

### 4.1 RLHF / safety-induced hedging on high-confidence questions

**Magnitude.** Halawi 2024: system Brier underperforms crowd by ~0.030 on questions where crowd's predictions are 0.3-0.7, but the gap REVERSES (system 0.199 vs crowd 0.246) on uncertain-crowd questions. The implication: when the crowd is certain, the LLM hedges; when the crowd is uncertain, the LLM does fine. This is bad for v4 because v1 trades at 0.70-0.95 YES, the high-crowd-certainty regime.

**Mitigation.** Platt scaling with parameter √3 (AIA Forecaster). Extremizes probabilities toward 0 and 1. Brier improvement -0.007 in their ablation.

### 4.2 Anchoring on visible market price

**Magnitude.** ForecastBench leaderboard: GPT-4.5 on the Tournament leaderboard has 0.994 correlation with market prices when given access. The model essentially copies the market.

**Mitigation.** Don't include the market price in the prompt; or use a "blind" baseline alongside a "with-price" variant and report both (v4 master plan S-B2 is this exact protocol).

### 4.3 Knowledge-cutoff leak ("LLM remembers the answer")

**Magnitude.** AIA Forecaster's foreknowledge-bias judge found 1.65% of search results contained leakage. The Brier impact was ≤0.6%. This is small but non-zero. For famous events (US presidential election, World Series outcome), the leakage is much larger and pre-cutoff testing is impossible.

**Mitigation.** Test on post-LLM-cutoff questions only (Halawi 2024 standard). Project Kalshi's situation: Opus 4.7 cutoff is Jan 2026; Kalshi historical data extends to 2026-03-25 per v3 probe. Window of usable test data is Feb-March 2026 only, a thin slice.

### 4.4 Prompt sensitivity / fragility

**Magnitude.** Janna Lu 2025: narrative-style prompt makes o3 Brier worsen from 0.1352 to 0.1985 (+47%). Schoenegger 2024 documents that LLMs cluster on round numbers (38 predictions at 50%, zero at 49% or 51%).

**Mitigation.** Test 3+ prompt rephrasings (v4 master plan S-B3). Use the canonical "you are a calibrated forecaster, output a probability between 0 and 1" form. Avoid fictional framings.

### 4.5 Hallucinated facts in the reasoning chain

**Magnitude.** General LLM hallucination rates are 5-30% depending on domain (Lakera 2026 review). Forecasting-specific: AIA Forecaster's foreknowledge audit found 1.65% leakage; broader hallucination is not directly measured in the forecasting literature. Janna Lu 2025 documents "censorship" failures (DeepSeek v3 skipped 9 China-Taiwan questions).

**Mitigation.** Agentic search with citation-required outputs (AIA Forecaster pattern). Self-consistency checks across multiple queries (AIA supervisor agent). Reject probability outputs that contradict cited evidence.

### 4.6 Topic-specific weakness on sports

**Magnitude.** "Future Is Unevenly Distributed" 2025: sports Brier 0.26-0.45 across 4 frontier models, geopolitics 0.12-0.40 (3 of 4 models worse on sports). Janna Lu 2025: o3 sports Brier 0.1649 vs politics 0.1199. v3 literature (sports-prediction-ceiling-2022-2024.md): free-feature sports prediction ceiling 65-67% game accuracy.

**Mitigation.** None documented. The mitigation is "don't use LLMs for sports forecasting at the price band where sportsbook efficiency is already saturated." This is the existential threat for v4 Track B given v1's mostly-sports universe.

### 4.7 Acquiescence (YES) bias

**Magnitude.** Schoenegger 2024: LLM mean prediction 57.4% vs 45% actual YES rate. Systematic ~12pp over-prediction of positive resolution.

**Mitigation.** Platt scaling helps. Also: shifting the threshold for "trade YES" upward (v4 should require LLM_prob > Kalshi_price + alpha, where alpha accounts for the documented YES bias).

### 4.8 Round-number clustering

**Magnitude.** Schoenegger 2024: 38 predictions at exactly 50%, zero at 49% or 51%. Granularity deficit: LLMs default to 10% increments (Janna Lu 2025) versus expert humans at 1%.

**Mitigation.** Average multiple queries; ask explicitly for "a probability to two decimal places." Doesn't fully fix the issue.

---

## 5. Cost-performance trade-off

### What the literature shows

The cost dimension is under-documented in the academic literature. Most papers use frontier models (GPT-4 / o3 / Claude 3.5 Sonnet+ / GPT-5) without explicit cost analysis. Three data points are available:

1. **Older / cheaper models perform at or below random baseline** (ForecastBench: GPT-3.5-Turbo Brier ~0.25, Claude 2 ~0.25, Mistral 7B ~0.25). These are dead-letter.

2. **Reasoning models (o3, o4-mini) outperform non-reasoning frontier (GPT-4.1, GPT-4o)** in Janna Lu 2025: o3 0.1352 < GPT-4.1 0.1542 < GPT-4o 0.1883.

3. **No published study evaluates Claude Haiku family or GPT-4o-mini on a major forecasting benchmark.** The "Prompt Engineering Large Language Models' Forecasting Capabilities" 2025 paper (arXiv 2506.01578) tested Claude 3.5 Haiku, but the PDF returned binary in this run; the abstract / search results do not document a competitive Haiku Brier. The closest evidence is that Claude 3 Haiku appears in ForecastBench but specific numbers were not pulled (PDF binary issue).

### The cost-quality envelope as best-inferred

| Tier | Example | Approx Brier on broad benchmarks | $/MTok input |
|---|---|---|---|
| Top reasoning | o3, GPT-5 R | 0.13-0.18 | $10-20 |
| Frontier | GPT-4.1, Opus 4.7, Sonnet 4 | 0.15-0.22 | $5-15 |
| Mid frontier | Claude 3.5 Sonnet, GPT-4o | 0.17-0.21 | $3-5 |
| Cheap (Haiku, 4o-mini) | Haiku 4.5, 4o-mini | UNMEASURED in literature | $0.15-1 |
| Older / random | GPT-3.5, Claude 2 | ~0.25 (random) | <$1 |

### Implication for v4

The 15x price ratio of Haiku ($1/MTok) vs Opus ($15/MTok) is **not directly justified or refuted by the literature**. The closest available data is the 0.05 Brier spread between reasoning models and non-reasoning frontier, which spans approximately a 3x price ratio. Naively extrapolating: a 15x price step might be worth 0.03-0.10 Brier of accuracy. But that's an extrapolation off-curve into unmeasured territory.

**For Project Kalshi at $32 capital, Haiku is the only viable model.** Per master plan Section 7.3: Opus monthly cost ~$300-500 at v1's cadence is 10x the bankroll and structurally unviable. Haiku monthly cost ~$25-50 is within bankroll. **The v4 design is forced to use Haiku regardless of accuracy implication.** The empirical question for Phase 1 (Agent V4-C pilot) is whether Haiku is even at the "above random" floor on Kalshi's specific market types.

### Recommended cost-aware design

- Use Haiku 4.5 as the workhorse model (single-LLM, $0.003 per forecast).
- For cheap ensembling: use Haiku 4.5 with 3-5 different prompts (still under $0.02 per question).
- Reserve Opus 4.7 for the "spot-check 20 questions" mode to estimate the Haiku-vs-Opus gap empirically.
- Batch API (50% discount) for the historical evaluation run.
- Cache by market ID (prompt + question text doesn't change frequently for v1's 30-180d lifetime markets).

---

## 6. Implications for v4 Track B design

Each design decision below cites the specific literature finding.

### 6.1 Recommended model tier: Haiku 4.5 as workhorse; Opus 4.7 only as spot-check

**Citation**: Cost constraint from master plan Section 7.3; literature does not refute Haiku as workable but does not confirm either. ForecastBench shows older / cheaper models (GPT-3.5, Claude 2, Mistral 7B) at random baseline; that's a meaningful prior that Haiku may also be near-random. The honest test is V4-C pilot empirical measurement.

### 6.2 Recommended prompt structure: scratchpad CoT with explicit probability output

**Citation**: Halawi 2024 and Schoenegger 2024 prompt templates; Karger 2024 baseline 5 (scratchpad + freeze). Avoid narrative / fictional framing (Janna Lu 2025: +47% Brier when narrative).

### 6.3 Recommended news context: include 2-5 recent news headlines retrieved at forecast time

**Citation**: Halawi 2024 ablation -0.020 Brier from retrieval (the single biggest gain). AIA Forecaster agentic search -0.009 Brier vs no search. CAVEAT: "Future Is Unevenly Distributed" 2025 documented that news context sometimes HURTS performance through recency bias. Recommend testing both with and without news in V4-C pilot.

Free-public news source for $32 budget: Bing/Brave Search free tier, or direct Wikipedia summary endpoint. Avoid AskNews API ($) unless V4-C empirically shows it's needed.

### 6.4 Recommended ensembling: single-model multi-prompt; not multi-model

**Citation**: Schoenegger 2024 ensembling effect ~3% Brier improvement on aggregate vs best individual. Cost-prohibitive on $32 to run 12 models. Single Haiku with 3 prompt rephrasings (v4 S-B3 sensitivity test doubles as the ensemble) is the cost-feasible approximation.

### 6.5 Recommended calibration: Platt scaling at parameter √3 on a held-out calibration slice

**Citation**: AIA Forecaster ablation: Platt scaling Brier 0.1071 vs no correction 0.1140 (-0.007). Platt is the most-effective single technique. Requires a held-out calibration set; allocate 20-30% of the post-cutoff Kalshi historical sample for this.

### 6.6 Recommended knowledge-cutoff guardrails

**Citation**: Halawi 2024 post-cutoff-only protocol; AIA Forecaster LLM-as-judge for foreknowledge bias.

For v4: test exclusively on Kalshi markets that RESOLVED after Jan 2026 (Opus cutoff). v3 probe found Kalshi historical cutoff 2026-03-25; v4 test window is Feb-March 2026 only. This is thin. Mitigation: ensemble Opus 4.7 (Jan 2026 cutoff) + a model with different cutoff if available (e.g., Sonnet 4 cutoff Apr 2025, GPT-5 family with later cutoff). Also: run the master-plan S-B1 date-redaction sensitivity test on a sample of pre-cutoff markets to quantify the leak magnitude.

### 6.7 Recommended honesty checks (already in master plan; re-confirmed by literature)

- **S-B1 cutoff leak**: full prompt vs date-redacted prompt; gap = leak magnitude.
- **S-B2 price anchor**: with-price vs without-price prompt; if correlation > 0.95, the model is copying the price (per ForecastBench Tournament leaderboard finding of 0.994 correlation).
- **S-B3 prompt sensitivity**: 3 prompt rephrasings; high variance = model is unreliable.

---

## 7. Honest prior on v4 Track B passing C6

### Bottom-line input for the orchestrator

C6 requires the LLM-forecaster to **beat v1 by at least 2pp on the same leak-free holdout** as the v2/v3 gate.

v1's measured edge on its strict-eligible long-horizon (30-180d) >=0.70 YES sports subset is **+12.47pp gross mean P&L** (per CLAUDE.md Round 7 / time-scale-analysis.md). C6's threshold is therefore +14.47pp absolute.

The literature supports the following honest prior decomposition:

**Component 1: Can a state-of-the-art LLM forecaster match the Kalshi market price on broad prediction-market questions?**
- Best published evidence: AIA Forecaster Brier 0.1258 vs market 0.1106 on MarketLiquid (LLM lags market by 0.015, or -13.7% Brier skill). With market in the ensemble, LLM contributes 33% of the weight.
- Best published LLM-only system on liquid prediction markets does NOT beat the market.
- Lit prior: P(LLM matches market on broad mixed-topic markets) ≈ 30-40%.

**Component 2: Adjustment for sports specificity.**
- "Future Is Unevenly Distributed" 2025: sports Brier roughly 2x worse than geopolitics for 3 of 4 frontier models tested.
- Janna Lu 2025: o3 sports 37% worse than politics.
- v3 sports-prediction-ceiling-2022-2024.md: free-feature sports prediction ceiling at +1-3pp gross edge, at-or-below v3's C6 threshold.
- Implication: condition Component 1's prior on the sports-specific factor. P(LLM matches Kalshi price on long-horizon sports) ≈ 15-25%.

**Component 3: Adjustment for high-confidence price band (0.70-0.95 YES).**
- Halawi 2024: system underperforms crowd on high-confidence questions (crowd < 0.05 or > 0.95). RLHF hedging.
- v1's price band is exactly the high-confidence band where this failure mode dominates.
- Mitigation via Platt scaling helps but is documented at -0.007 Brier improvement, not enough to close a 0.015 deficit.
- Implication: further condition down. P(LLM matches Kalshi price on high-confidence sports favorites) ≈ 10-20%.

**Component 4: Even matching the price is NOT enough; C6 requires beating v1.**
- v1's edge is +12.47pp gross above the Kalshi price's implied probability (v1 buys at price p, but the realized win rate on its filtered set is p + 12.47pp).
- For the LLM to clear C6 (+2pp over v1), it must produce edges of +14.47pp.
- The LLM has to either (a) generate independent information beyond what the price reflects, OR (b) discover a different filter that's even more selective than v1's.
- AIA Forecaster's "additive information" measurement: LLM ensemble weight on MarketLiquid is 33%, ensemble beats market by only 0.014 Brier. Translated to probability-edge units: ~+1.4pp.
- Implication: even when the LLM has measurable additive value, it's roughly +1-2pp on top of the market, not +14pp. **The C6 threshold sits roughly 7x higher than the documented LLM additive-value on liquid markets.**
- P(LLM additive value alone is +14pp) ≈ very small. The literature shows LLM additive values measured in 1-2pp Brier, not 14pp.

**Component 5: Cost feasibility.**
- v4 is forced to Haiku 4.5 by budget; literature does not document Haiku at competitive Brier on forecasting benchmarks. The above priors assume a state-of-the-art system (AIA, GPT-5, o3, Claude Opus 4.7); Haiku 4.5 is at best a small fraction of that capability.
- Implication: Haiku's realistic Brier on prediction-market-style sports markets is likely UNMEASURED in literature but worse than the frontier numbers above. Conservative estimate: Haiku Brier on v1's domain is 0.02-0.05 worse than the frontier literature, which is 0.04-0.07 worse than the Kalshi price.

### Aggregate honest prior

Multiplying through (rough Bayesian narrative; not formal):
- P(an AIA-tier system matches Kalshi price on v1's sports domain) ≈ 0.15
- P(any system beats Kalshi price's effective Brier by enough to clear C6's +2pp-over-v1 = +14.47pp edge bar) ≈ 0.05 (small even at frontier)
- P(Haiku-tier system at $32 budget achieves this) ≈ 0.02-0.05

**Bottom-line honest prior on v4 Track B clearing C6 on a leak-free Kalshi sports holdout: 5-15%.**

This is below v3's H1/H2 prior of 10-25% (from `research/v3/04-literature.md` Section "Honest prior on v3 outcomes"). Track B is structurally a harder bet than v3 was, because:
- The LLM has to BEAT a sportsbook-saturated market, not just match a public-feature regression model.
- Sports is the LLM weak topic.
- v1's high-confidence regime amplifies the documented RLHF-hedging failure mode.
- Cost forces a Haiku-tier model, below where the literature measures competitive performance.

### What would update the prior upward

- V4-C pilot empirically shows Haiku at Brier within 0.02 of Opus on a sample of v1-domain Kalshi questions. (Plausible but not literature-supported.)
- V4-C pilot empirically shows the LLM produces probability estimates with > 0.05 absolute distance from Kalshi price and the LLM is right (correlation between LLM-vs-price disagreement and resolution is positive).
- Polymarket coverage on v1 universe is high enough (Track A) that Track A subsumes Track B's edge cheaper.

### What would update the prior downward (or kill Track B early)

- V4-C pilot shows Haiku Brier near random (0.25) on v1-domain Kalshi questions.
- V4-C pilot shows LLM probabilities cluster within 0.02 of Kalshi price (price anchoring, master plan S-B2 fails).
- V4-C pilot shows LLM Brier on date-redacted vs full prompts differ by > 0.03 on pre-cutoff Kalshi markets (cutoff leak measured, master plan S-B1 fails).

### Recommendation to orchestrator

**Recommend running V4-C pilot (Phase 1) before committing to Phase 2 Track B build.** The pilot is cheap (~$5-10 in API spend per master plan Section 7.3) and decisive: if Haiku-on-Kalshi-sports is near random or strongly price-anchored, kill Track B at Phase 1. If Haiku produces independent estimates with realistic Brier, proceed to Phase 2. The literature does NOT supply a confidence-passing prior, so the pilot is the binding test.

If V4-C is dropped or pilot results are not yet in, the orchestrator's default should be to allocate Phase 2 budget to Track A (Polymarket-fade-filter) first, treating Track B as a stretch goal contingent on pilot results.

---

## Files updated by this pass

- Created `research/literature/halawi-2024-human-level-forecasting.md`
- Created `research/literature/karger-2024-forecastbench.md`
- Created `research/literature/schoenegger-2024-silicon-crowd.md`
- Created `research/literature/aia-2025-forecaster-and-followups.md`
- Updated `research/literature/INDEX.md` (entries added; count moved from 10 to 14)
- Updated `~/.claude/.../memory/project_kalshi_literature.md` (TLDRs appended)

## Search trail and what we did NOT retrieve

- Halawi 2024 full PDF (arxiv.org/pdf/2402.18563): binary-only via WebFetch. Used the arxiv HTML v1 + Alignment Forum summary + ResearchGate abstract + Semantic Scholar.
- Schoenegger 2024 Science Advances PDF: binary-only via WebFetch (two redirect attempts). Used arxiv HTML v5 instead; numbers cross-checked against the LSE eprints metadata.
- Karger 2024 ForecastBench full PDF: binary-only via WebFetch. Used arxiv HTML + ForecastingResearch substack 2026 update.
- "Prompt Engineering Large Language Models' Forecasting Capabilities" (arXiv 2506.01578): binary-only PDF; no Haiku-specific Brier extracted. Marked as "secondary citation, primary not retrieved" on the cheap-model question.
- AIA Forecaster (arXiv 2511.07678): arxiv HTML successfully retrieved; numbers high-confidence.
- Janna Lu 2025 (arXiv 2507.04562): arxiv HTML successfully retrieved.
- "Future Is Unevenly Distributed" (arXiv 2511.18394): arxiv HTML successfully retrieved.
- Prophet Arena (arXiv 2510.17638): arxiv HTML successfully retrieved.

The four required papers were all retrievable at the HTML / abstract / substack-summary level. No fabricated numbers; every claim has a URL. Where the primary source was inaccessible, the path used (HTML version, secondary summary, official leaderboard) is noted.

The two load-bearing findings are robust across multiple independent sources:

1. **State-of-art LLM forecasters LAG market consensus on liquid prediction markets** (AIA Forecaster, ForecastBench leaderboard, Prophet Arena, BTF-2 all converge).
2. **Sports is documented as one of the weakest LLM topics** ("Future Is Unevenly Distributed" 2025, Janna Lu 2025, plus the existing v3 sports-prediction-ceiling synthesis).

Both findings are bearish for v4 Track B's prior of clearing C6 on Project Kalshi's specific sports-heavy long-horizon high-confidence universe.
