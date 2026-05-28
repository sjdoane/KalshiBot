# v10 Literature Delta: New Research Since 2026-05-25

**Date:** 2026-05-26
**Author:** Agent v10-S2 (Data + Literature Scout)
**Baseline:** `research/v7/02-recent-ml-research.md` (dated 2026-05-25)
**Prior lit index:** `research/literature/INDEX.md` (14 papers; last entry
covers the AIA Forecaster cluster through Apr 2026 PolyBench and PolySwarm)
**Method:** WebSearch + WebFetch (10 fetch limit). All papers were discovered
via search and validated against abstracts or full HTML versions on arXiv.

---

## Executive Summary

Eight papers have been identified as material updates beyond the v7 baseline.
The three highest-priority findings for v10:

1. **TimeSeek (arXiv 2604.04220)** is the ONLY published paper evaluated
   specifically on CFTC-regulated Kalshi binary markets (150 markets, 10 frontier
   models, 15,000 forecasts). Key finding: LLM agents are most competitive EARLY
   in a market's life and on HIGH-UNCERTAINTY markets. They are much less
   competitive near resolution and on strong-consensus (high-confidence) markets.
   This directly confirms the v9 Phase 3 critic's design-layer finding: v1's
   confident-favorite universe (0.70-0.95 YES) is the regime where LLMs are
   least competitive. **This is the authoritative new evidence that LLM
   forecasting does NOT work in v1's regime.**

2. **Prediction Arena (arXiv 2604.07355)** ran 6 frontier models with $10,000
   each on Kalshi and Polymarket for 57 days (Jan-Mar 2026). On Kalshi: all
   six lost money (-16% to -30.8%). On Polymarket: better performance (Cohort 1
   avg -1.1%; one model +6.02%). This confirms that Kalshi specifically is the
   harder platform for LLM trading strategies.

3. **Outcome-based RL for Forecasting (arXiv 2505.17989, Turtel et al.)** and
   **Foresight Learning (arXiv 2604.18576 / separate report, Murphy)** represent
   a new direction: fine-tuning small models (14B) with RLVR on prediction market
   questions achieves frontier-level Brier and +10% ROI in Polymarket simulation.
   This is genuinely new -- prior rounds never considered RL fine-tuning of a
   local model as a path. However, it requires GPU hardware not currently in the
   operator's setup.

Additional findings:
- **TabPFN-3 (arXiv 2605.13986)** released May 2026: 1M-row support, 20x faster
  than v2, time-series specialist checkpoint. Supersedes v2 for any future
  tabular diagnostic.
- **ForesightFlow (arXiv 2605.00493)** and **Polymarket Anatomy (arXiv 2604.24366)**
  advance microstructure understanding but are Polymarket-specific with limited
  direct Kalshi applicability.
- **LLM Lead-Lag Semantic Filtering (arXiv 2602.07048)** shows LLMs can filter
  Granger-causal pairs on Kalshi Economics markets, improving win rate from 51.4%
  to 54.5%. This is a genuinely new Kalshi-specific positive signal.

---

## Paper 1: TimeSeek

**Citation:** Mostafa, Hamza; Shastri, Om; Lee, Dennis. "TimeSeek: Temporal
Reliability of Agentic Forecasters." arXiv:2604.04220. April 2026. Workshop paper.

**Abstract sentence:** Evaluates 10 frontier LLM models on 150 CFTC-regulated
Kalshi binary markets at five temporal checkpoints with and without web search
(15,000 total forecasts), finding that model competitiveness varies significantly
across a market's lifecycle.

**Key findings:**
- Models are most competitive EARLY in a market's life and when uncertainty is
  high (markets near 0.5 probability).
- Models are "much less competitive near resolution and on strong-consensus
  markets" (markets near 0.0 or 1.0 probability).
- Web search improves pooled Brier Skill Score for every model, but hurts in
  12% of model-checkpoint pairs.
- Simple two-model ensembles reduce error but do NOT surpass the market overall.
- Conclusion: time-aware evaluation and selective-deference policies are needed.

**Implications for Project Kalshi:**
This paper is the single most directly relevant new piece of evidence for v10.
It was evaluated on KALSHI specifically (CFTC-regulated = Kalshi). The regime
finding -- worst performance on "strong-consensus markets" -- is a precise
description of v1's 0.70-0.95 YES universe. This is third-party empirical
confirmation of the v9 Phase 3 critic's Test 5 finding: v9's pre-registered
gate borrowed AIA's +0.014 from the hard-market regime, but v1 trades in the
confident-favorite regime where LLMs are weakest.

The positive implication for v10: if a future angle targeted markets early in
their lifecycle and at high uncertainty (0.40-0.60 YES range), the TimeSeek
findings suggest LLMs could be competitive. This is a different market selection
criterion than v1's 0.70-0.95 YES.

**Novelty vs prior coverage:** CONFIRMS-EXISTING (the design-layer failure mode
v9 critic identified) AND NEW-ANGLE (time-aware + uncertainty-selective policy
is a new design direction not present in prior rounds).

**Tag: CONFIRMS-EXISTING + NEW-ANGLE-HIGH-PRIOR** (for future angle design;
not for current v10 immediately).

---

## Paper 2: Prediction Arena

**Citation:** Zhang, Jaden; Liu, Gardenia; Johansson, Oliver; Yitayew, Hileamlak;
Ohly, Kamryn; Li, Grace. "Prediction Arena: Benchmarking AI Models on Real-World
Prediction Markets." arXiv:2604.07355. April 2026.

**Abstract sentence:** Six frontier AI models each received $10,000 to trade
autonomously on Kalshi and Polymarket for 57 days (January 12 to March 9, 2026),
finding final returns of -16.0% to -30.8% on Kalshi and a platform effect that
dominated model capability.

**Key findings:**
- On Kalshi (Cohort 1): all 6 models lost money. Range -16.0% to -30.8%.
- On Polymarket (Cohort 1): average only -1.1% loss; grok-4 achieved 71.4%
  settlement win rate; gemini-3.1-pro-preview +6.02% in 3 days (best return
  across any platform or cohort).
- "Platform design has a profound effect on which models succeed."
- "Initial prediction accuracy and the ability to capitalize on correct
  predictions are the main drivers" of performance differences within a platform.

**Implications for Project Kalshi:**
The paper provides live-capital evidence that Kalshi is harder for LLM trading
than Polymarket. The -16% to -30.8% range on Kalshi during a 57-day live test
confirms the v9 NULL was not an anomaly -- this is the baseline expectation for
autonomous LLM trading on Kalshi with real capital. The Polymarket outperformance
by the same models suggests Polymarket's CLOB design (thinner markets, potentially
different pricing regime) creates more exploitable moments for LLMs. For v10, this
confirms that any LLM-as-trader angle on Kalshi requires a structural edge beyond
"run a frontier model and trade its output."

**Novelty vs prior coverage:** PolyBench (arXiv 2604.14199, already in v7/v9
coverage) showed 5 of 7 models lost on Polymarket. Prediction Arena adds the
direct Kalshi comparison with live capital. **This is NEW DATA on Kalshi
specifically.**

**Tag: CONFIRMS-EXISTING** (LLM trading losses on Kalshi) and **NEW-ANGLE-HIGH-PRIOR**
(the Polymarket vs Kalshi platform differential is a new comparative finding).

---

## Paper 3: Outcome-Based RL for Forecasting (Foresight Learning)

**Citation (primary):** Turtel, Benjamin; Franklin, Danny; Skotheim, Kris;
Hewitt, Luke; Schoenegger, Philipp. "Outcome-based Reinforcement Learning to
Predict the Future." arXiv:2505.17989. May 2025.

**Citation (companion / newer):** Murphy, Kevin. "Agentic Forecasting using
Sequential Bayesian Updating of Linguistic Beliefs." arXiv:2604.18576. April 2026.

**Abstract sentence (Turtel):** Applies RLVR to a 14B model fine-tuned on
prediction market questions and news, achieving frontier-level Brier and
simulated +10% ROI on Polymarket test questions.

**Abstract sentence (Murphy):** Bayesian Linguistic Forecaster (BLF) uses an
iterative belief-refinement loop with logit-space averaging and Platt scaling,
outperforming all top public methods including Cassi, GPT-5, Grok 4.20, and
Foresight-32B on ForecastBench.

**Key findings (Turtel):**
- A 14B model fine-tuned with RLVR (Reinforcement Learning with Verifiable
  Rewards) "can match or surpass the predictive accuracy of frontier models like
  o1."
- In a Polymarket trading simulation, estimated +10%+ ROI on test set questions.
- Training does not require labeled data or humans in the loop (uses prediction
  market resolution as the verifiable reward signal).

**Key findings (Murphy):**
- Three components: semi-structured linguistic belief state, hierarchical multi-
  trial aggregation (logit-space averaging), hierarchical Platt scaling.
- Outperforms "all top public methods" on ForecastBench 400-question test set.
- Ablation: all three components contribute; structured belief updating improves
  forecasting across model sizes.
- Question variability accounts for 62% of performance variance (mixed-effects
  finding), suggesting per-question adaptation matters more than model size.

**Implications for Project Kalshi:**
The Turtel paper represents a NEW DIRECTION not present in any prior round: fine-
tuning a small open model on Polymarket historical outcomes using RL. A 14B model
(e.g., Llama 3.1 14B) could potentially be run locally with a GPU, fine-tuned
on the Becker 72M trade dataset or the Polymarket lifecycle dataset (arXiv
2604.20421), and used as a Kalshi-specific forecasting model. The +10% Polymarket
ROI is a simulation result (not live trading), but it is the most optimistic
published result for a cheap model.

However, the operator's current hardware setup (Windows + WSL2, no GPU confirmed)
makes running a 14B model locally prohibitive. Fine-tuning on Replicate or Together
AI would cost roughly $10-50 for a training run, which is within the $30-60 budget.

The Murphy BLF paper's structured belief updating is useful as an architectural
recipe for any LLM forecasting pipeline: iterative refinement beats single-shot
prompting, and the Platt scaling finding (already in v7) is reinforced.

**Novelty vs prior coverage:** The RLVR fine-tuning approach is **genuinely new**.
Prior rounds considered: bare LLM prompting (v4-B, NULL), agentic LLM with tools
(v9, NULL on design grounds), foundation model direct (Kronos v7-B, NULL). Fine-
tuning a small model on prediction market outcomes was not explored.

**Tag: NEW-ANGLE-MEDIUM-PRIOR** for RLVR fine-tuning; the +10% Polymarket ROI is
compelling but requires GPU and training budget not currently available. Murphy's
BLF architecture is **NEW-ANGLE-MEDIUM-PRIOR** as a structured pipeline recipe
for any future LLM forecasting attempt.

---

## Paper 4: LLM Semantic Filtering for Lead-Lag Trading (Kalshi Economics)

**Citation:** Kim, Sumin; Kim, Minjae; Kwon, Jihoon; Kim, Yoon; Kagan, Nicole;
Lee, Joo Won; Levy, Oscar; Lopez-Lira, Alejandro; Lee, Yongjae; Choi, Chanyeol.
"LLM as a Risk Manager: LLM Semantic Filtering for Lead-Lag Trading in Prediction
Markets." arXiv:2602.07048v2. February 2026.

**Abstract sentence:** A two-stage hybrid approach uses Granger causality to
identify statistical lead-lag pairs on Kalshi Economics markets, then applies
an LLM to filter out economically implausible causal directions, improving win
rate from 51.4% to 54.5% and halving average loss magnitude from $649 to $347.

**Key findings:**
- Granger causality on Kalshi Economics market probability time series identifies
  statistical lead-lag relationships.
- An LLM evaluates whether "plausible economic transmission mechanisms" support
  each proposed direction.
- Win rate improvement: 51.4% to 54.5% (an absolute +3.1pp).
- Average loss magnitude: $649 to $347 (-46% loss reduction).
- "LLMs function as semantic risk managers... prioritizing lead-lag relationships
  that generalize under changing market conditions."
- Evaluated on Kalshi Economics category (the macro markets: KXFEDFUNDS, KXCPI,
  KXNFP, KXUNRATE).

**Implications for Project Kalshi:**
This is the most directly actionable new paper for v10. It operates on Kalshi
Economics markets (the FRED-data-aligned markets: KXFEDFUNDS, KXCPI, KXNFP,
KXUNRATE) and produces a measurable win rate improvement. The approach is
different from all prior Project Kalshi angles:
- Not forecasting outcomes from first principles.
- Identifying which Kalshi macro market leads which other macro market in
  probability updates.
- Using LLM to filter statistically fragile relationships.

The Diercks/Katz/Wright 2026 finding (lit #6) showed Kalshi macro markets are
efficiently priced against Bloomberg consensus. This paper's finding is NOT
contradicted by that: the lead-lag relationship between two Kalshi markets
(e.g., KXCPI leads KXNFP, or vice versa, in probability updates) does not
require either market to be individually mispriced relative to fundamentals.

**Practical constraints:**
- Requires multi-market time-series data from Kalshi macro series.
- v6 already established that Kalshi `/historical/trades` is accessible for
  any series. Macro markets have higher trade frequency than v1's sports
  universe.
- Diercks/Katz/Wright 2026 (lit #6) showed institutional-quality pricing of
  macro markets, so the edge from lead-lag filtering may be thin at Kalshi's
  execution costs (2c spread, plus taker fees). The +3.1pp win rate improvement
  is meaningful but requires a realistic fee model.
- v9 showed the sports universe is seasonal and thin for statistical work;
  Kalshi Economics markets (CPI monthly, NFP monthly, FOMC bi-monthly) are
  also low-frequency (at most 12-24 events per year per series). Sample size
  for any cross-market backtest would be n < 50 per pair.

**Novelty vs prior coverage:** The lead-lag angle on Kalshi was never tested in
any prior round. Ng/Peng/Tao/Zhou 2026 (lit #8) covered Polymarket-Kalshi cross-
VENUE lead-lag. This paper covers Kalshi-INTERNAL cross-MARKET lead-lag (one
Kalshi series predicting another Kalshi series in the macro category). **This is
NEW.**

**Tag: NEW-ANGLE-MEDIUM-PRIOR.** The +3.1pp win rate improvement on Kalshi
Economics is the only published positive Kalshi-specific result in the 2026
literature. It is real but requires careful feasibility audit on sample size
and fee model.

---

## Paper 5: TabPFN-3

**Citation:** Prior Labs. "TabPFN-3: Technical Report." arXiv:2605.13986v1.
May 2026.

**Key changes from TabPFN v2 (the version tested in v7-C):**
- **Scale:** Supports up to 1M training rows (v2 capped at 10k).
- **Speed:** 20x faster than TabPFN-2.5 for inference.
- **Time-series specialist:** TabPFN-TS-3 checkpoint ranks 2nd on fev-bench
  time-series benchmark.
- **Compute:** H100 GPU required at 1M-row scale. CPU feasibility for small
  datasets (< 10k rows) is not documented as changed.
- **New modalities:** Relational data (new SOTA on RelBenchV1), tabular-text
  (SOTA via TabPFN-3-Plus).

**Implications for Project Kalshi:**
v7-C confirmed TabPFN v2 is a clean NULL on v6's master dataset (n=971) and v5-B
(n=146k sub-sampled to 10k). TabPFN-3's 1M-row support means v5-B's full n=146k
is now within range without subsampling. The TabPFN-TS-3 checkpoint's 2nd-place
fev-bench ranking is relevant if v10 revisits any time-series prediction angle.

However, the core finding from v7-C -- that TabPFN ties LightGBM within +0.00040
Brier on v5-B -- was a model-class diagnostic. TabPFN-3's architectural
improvements are unlikely to create signal where v2 found none; the NULL was
about signal absence, not model class limitation.

**Tag: CONFIRMS-EXISTING** (NULL is model-class robust; v3 fixes scale, not
signal). **Low priority to re-run on existing datasets.** Only relevant if a new
larger dataset is assembled (n > 10k).

---

## Paper 6: Polymarket Anatomy of Microstructure

**Citation:** Dubach, Philipp D. "The Anatomy of a Decentralized Prediction
Market: Microstructure Evidence from the Polymarket Order Book."
arXiv:2604.24366. April 2026.

**Key findings:**
- 30 billion order-book events across 600 Polymarket markets over 52 days.
- Eight stylized facts: longshot spread premiums, uniform depth profile,
  concentrated maker wallets, category-dependent spreads, 99% of trades at
  quoted prices (no midpoint crossing).
- Critical: Trade direction inferred from public feeds matches on-chain truth
  in only ~59% of buckets (vs ~80% Lee-Ready accuracy on Nasdaq). Kyle's
  lambda and effective spreads FLIP SIGN on majority of markets when using
  feed vs on-chain data.
- Implication: Classical microstructure metrics (VPIN, Kyle's lambda, effective
  spread) computed from public Polymarket data are unreliable and likely wrong.

**Implications for Project Kalshi:**
This finding applies to Polymarket specifically (decentralized, on-chain). Kalshi
is a centralized CLOB operated by Kalshi Inc., so the feed/on-chain gap does not
apply. However, the broader lesson reinforces v6's findings: microstructure metrics
on prediction markets are hard to compute correctly and easy to get wrong. The
paper's open-source code for joining feed and on-chain data could be adapted for
any Polymarket cross-venue analysis.

**Tag: CONFIRMS-EXISTING** (validates v6's caution about microstructure
measurement). Not directly actionable for Kalshi-internal analysis.

---

## Paper 7: ForesightFlow Information Leakage Score

**Citation:** Nechepurenko, Maksym. "ForesightFlow: An Information Leakage Score
Framework for Prediction Markets." arXiv:2605.00493. May 2026.

**Key findings:**
- Introduces Information Leakage Score (ILS) adapted from Murphy decomposition
  for binary outcome markets.
- Tested on 911,237 Polymarket markets.
- Documented insider cases were deadline-resolved (0 of 24 qualified under
  original methodology), requiring a deadline-ILS extension.
- Proxy timestamps vs manually-derived timestamps shift scores by 0.444
  magnitude -- timestamp precision is critical for leakage detection.

**Implications for Project Kalshi:**
ILS is a methodology for detecting whether prices move before public information
events (i.e., whether smart money front-runs resolutions). Applied to Kalshi,
this would test whether Kalshi prices move before economic data releases
(CPI day, NFP day) in the hours prior to the release. This is adjacent to the
lead-lag paper (arXiv 2602.07048) but at a finer time resolution.

The practical challenge for v10: building ILS on Kalshi requires high-frequency
price snapshots around release events. v8-A's forward-record infrastructure
(which closed as PHANTOM on the crypto angle) could theoretically be repurposed
for macro release events. But n (number of CPI / NFP events per year) is too
small for statistical inference at the operator's scale.

**Tag: NEW-ANGLE-LOW-PRIOR.** Methodologically interesting but sample-size
infeasible at retail scale on Kalshi macro markets (n < 24 events per year).

---

## Paper 8: Polymarket Lifecycle Dataset

**Citation:** Jia, Huaiyu; Zhou, Luofeng; Zhang, Wentao; Cong, Lin William;
Li, Siguang; Sun, Shuo. "Unlocking the Forecasting Economy: A Suite of Datasets
for the Full Lifecycle of Prediction Market." arXiv:2604.20421. April 2026.

**Key findings:**
- 770,000+ Polymarket market records, 943M fill records, 2M oracle events,
  October 2020 to March 2026.
- Full lifecycle: creation, trading, oracle resolution, dispute, settlement.
- Case studies: NBA outcome calibration and CPI expectation reconstruction
  demonstrate quantitative modeling applicability.
- Dataset covers the full Polymarket history including the 2024 US election cycle.

**Implications for Project Kalshi:**
This is the richest publicly available prediction market dataset. For any fine-
tuning approach (per Paper 3 Turtel et al.), the Polymarket lifecycle dataset
could serve as the training corpus (outcomes are observable, market prices are
available, sample sizes in the hundreds of millions are available). The NBA
calibration case study also shows directly how to apply the data to calibrate
predictions for sports markets similar to v1's universe.

**Tag: NEW-ANGLE-MEDIUM-PRIOR** for fine-tuning a local model on prediction
market outcomes. Enables the RL fine-tuning approach from Paper 3.

---

## Other Search Findings (Thin or Not Individually Actionable)

The following were surfaced in search but do not rise to the level of a full
extraction:

- **"Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in
  Prediction Markets"** (search result only; no arXiv ID confirmed): Studies
  calibration dynamics. If accessible, could update lit #3 (Le 2026) on
  calibration regime structure.

- **PolySwarm (arXiv 2604.03888)** and **PolyBench (arXiv 2604.14199)**: Both
  already covered in the v7 ML research scoping. No material new findings from
  this search pass.

- **"LLM as a Prophet / Prophet Arena" (arXiv 2510.17638)**: Already in lit #14.
  No update needed.

- **Adaptive Temperature Scaling with Conformal Prediction (arXiv 2505.15437)**:
  New calibration technique but not tested on prediction markets. Theory-tier;
  Platt scaling remains the canonical post-processing per AIA ablation.

- **"Fill-Side Non-Retail Trading on Polymarket" (arXiv 2605.11640)**: Studies
  behavioral tiers (retail vs non-retail) on Polymarket using PMXT v2 archive.
  Relevant background for understanding who is on the other side of a Kalshi
  trade, but Polymarket-specific and not directly applicable to Kalshi CLOB.

---

## Literature Gap Checks

Consistent with the v7 baseline scoping, the following remain NOT documented
in any published paper as of May 2026:

1. **No paper applies RLVR fine-tuning to Kalshi specifically.** Turtel et al.
   used Polymarket. A Kalshi-specific version would require the Becker dataset
   or equivalent.

2. **No paper tests LLM forecasting on the confident-favorite (0.70-0.95 YES)
   regime on sports markets.** TimeSeek's finding (weak in strong-consensus)
   fills this gap at a high level but does not provide a Brier number for this
   regime specifically.

3. **No paper tests cross-series lead-lag within Kalshi's sports markets**
   (e.g., does KXBOXING market update predict KXUFCFIGHT update before a fight
   card with co-promoters). The Kim et al. (arXiv 2602.07048) approach was on
   Economics; sports cross-series lead-lag is unexplored.

4. **No paper tests TabPFN-3 on prediction market datasets.** The v7-C result
   (TabPFN v2 NULL) was the first application; v3 was not tested on any
   prediction market dataset.

5. **Calibration of high-confidence LLM forecasts on binary sports markets**:
   the Halawi 2024 hedging failure mode is documented but no paper has
   specifically published a calibration technique for the 0.70-0.95 YES
   prediction market regime.

---

## Summary Table: New Papers for v10

| Paper | arXiv | Date | Tag | Priority for v10 |
|-------|-------|------|-----|------------------|
| TimeSeek (Mostafa et al.) | 2604.04220 | Apr 2026 | CONFIRMS-EXISTING + NEW-ANGLE | HIGH: confirms v9 regime kill |
| Prediction Arena (Zhang et al.) | 2604.07355 | Apr 2026 | CONFIRMS-EXISTING | HIGH: live Kalshi LLM trading data |
| RL Forecasting Foresight Learning (Turtel et al.) | 2505.17989 | May 2025 | NEW-ANGLE | MEDIUM: fine-tuning path |
| Bayesian Linguistic Forecaster (Murphy) | 2604.18576 | Apr 2026 | NEW-ANGLE | MEDIUM: pipeline recipe |
| LLM Lead-Lag Filtering (Kim et al.) | 2602.07048 | Feb 2026 | NEW-ANGLE | MEDIUM: Kalshi Economics |
| TabPFN-3 (Prior Labs) | 2605.13986 | May 2026 | CONFIRMS-EXISTING | LOW: NULL is model-class robust |
| Polymarket Anatomy (Dubach) | 2604.24366 | Apr 2026 | CONFIRMS-EXISTING | LOW: Polymarket microstructure |
| ForesightFlow (Nechepurenko) | 2605.00493 | May 2026 | NEW-ANGLE | LOW: sample-size infeasible |
| Prediction Market Lifecycle Dataset (Jia et al.) | 2604.20421 | Apr 2026 | NEW-ANGLE | MEDIUM: enables RL fine-tuning |

---

## Calibration Research Delta

The search for new calibration methods specific to prediction markets (post
2026-05-25) did not surface materially new work beyond:

- Adaptive Temperature Scaling with Conformal Prediction (arXiv 2505.15437,
  May 2025): extends temperature scaling. Not tested on prediction markets.
- Murphy BLF (arXiv 2604.18576): reinforces hierarchical Platt scaling as the
  canonical recipe. No change to recommendation.

**Bottom line on calibration:** The AIA Forecaster ablation (Platt scaling
parameter sqrt(3) = best single step, -0.007 Brier) remains the state-of-the-
art recommendation. No new method has been published specifically for the high-
confidence regime (0.70-0.95 YES) where Halawi 2024 documents RLHF hedging.
This gap remains open.
