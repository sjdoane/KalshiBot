# Project Kalshi v7: Recent ML Research Scoping (2024 to 2026)

**Date:** 2026-05-25
**Author:** Claude (v7 scoping subagent)
**Scope:** Survey 2024 to 2026 ML literature for approaches untried in v2 to v6 that have a real chance of producing Kalshi signal.

## Executive summary

Six rounds of NULL leave a narrow remaining surface. The three highest-prior v7 angles, in priority order, are (1) **agentic LLM forecasting with tool use plus Kalshi-mid anchoring**, replicating the AIA Forecaster plus market-ensemble recipe that closed the v4 Track B gap; (2) **Kronos zero-shot OHLCV foundation model on KXBTCD as a pre-trained second opinion**, the only 2025 release pre-trained on tokenized crypto K-lines at 12B record scale, untouched in v5-C / v6; (3) **TabPFN v2 swap on v6's master dataset** to test whether the v5-B / v6 "model anchors on price" failure mode is LightGBM-specific. Medium-prior fourth and fifth: limit-order-book transformers (LiT / TLOB) on Kalshi's own websocket book if Kalshi exposes Level-2 firehose, and Polymarket as a longer-horizon feature now that the 30-day CLOB ceiling may have softened. Foundation-model evidence remains negative for direct price forecasting (Chronos and TimesFM both underperform CatBoost / LightGBM on financial returns), so v7 should NOT bet on out-of-the-box TSFM. The single biggest finding from this survey: AIA + market ensemble at 67% market weight beats either alone on hard markets at Brier 0.106, the canonical reference point for what an agentic LLM can plausibly add to v1.

## 1. Agentic LLM forecasting (extending v4)

v4-B used Claude Haiku 4.5 with no tools, no retrieval, no Kalshi price; the literature predicts this is the worst possible configuration. The 2025-2026 frontier has moved decisively to agentic-retrieval + market-ensemble.

**AIA Forecaster (Anthropic Insights, Nov 2025, arXiv 2511.07678).** Matches superforecasters on ForecastBench FB-7-21 (Brier 0.1125 vs SF 0.1110) but LAGS market consensus by 0.015 Brier on hard liquid markets (MarketLiquid: AIA 0.126 vs market 0.111). AIA + market ensemble beats either alone (0.092 / 0.106 on hard, 67% market weight). **Tag: NEW-ANGLE-HIGH-PRIOR.** Already extracted in v4 lit; the ENSEMBLE recipe is what v7 should test, not bare LLM.

**ForecastBench leaderboard 2026 (Karger et al., updated).** GPT-4.5 0.101 Brier, superforecasters 0.081 (parity projected Nov 2026 +- 12 months). xAI Grok 4.20 and CassiAI ensemble_2_crowdadj tied top at 67.9% Brier Index vs SF 70.6%. **Tag: NEW-ANGLE-HIGH-PRIOR** for the *recipe* (multi-model ensemble, market-anchored extremization). Source: https://www.forecastbench.org/leaderboards/

**Prophet Arena live (Jan to Mar 2026, arXiv 2510.17638).** 57-day live trading evaluation of six frontier LLMs as autonomous Polymarket agents. Top model (Grok-4-20-checkpoint) settlement win rate 30.9%; "frontier proprietary LLMs achieved Brier scores competitive with the Market Baseline." Translation: even at frontier, LLMs barely match market price and trading returns are marginal at best. **Tag: NEW-ANGLE-HIGH-PRIOR** for METHODOLOGY (live evaluation harness), MEDIUM-PRIOR for expected edge magnitude.

**PolyBench (Cheng / Liu / Long, arXiv 2604.14199, Apr 2026).** 36,165 LLM predictions across 38,666 Polymarket markets, Feb 6 to 12 2026. Only 2 of 7 models positive CWR: MiMo-V2-Flash +17.6%, Gemini-3-Flash +6.2%; other five LOST money. **The 5-of-7-lose result is the v4-Track-B failure mode generalized:** most LLMs ship with overconfident sentiment that order-book execution punishes. **Tag: NEW-ANGLE-MEDIUM-PRIOR** because the winners exist but model selection is load-bearing and unstable across rebenchmarks.

**PolySwarm (Barot / Borkhatariya, arXiv 2604.03888, Apr 2026).** 50 LLM personas with KL / JS divergence cross-market detection + quarter-Kelly sizing + CEX-implied-probability latency arbitrage. Paper reports Brier and log-loss only, NO actual P&L. **Tag: NEW-ANGLE-LOW-PRIOR**: 50-agent fan-out is expensive (cost ~50x v4-B at $1.03 cumulative), no proven monetization, and v6-K1 already showed latency arbitrage at sub-hour horizons is dead on KXBTCD.

**LiveTradeBench (arXiv 2511.03628, Nov 2025) + When Agents Trade / AMA (arXiv 2510.11695, Oct 2025).** 50-day live eval of 21 LLMs across US stocks + Polymarket; 4-agent x 5-LLM comparison live. Joint findings: "state-of-the-art models in LMArena do not exhibit state-of-the-art trading performance" and "agent frameworks display markedly distinct behavioral patterns... whereas model backbones contribute less to outcome variation." Architecture > model choice; select on trading benchmark not general intelligence. **Tag: NEW-ANGLE-MEDIUM-PRIOR.**

**Multi-agent frameworks (LangGraph / CrewAI / AutoGen).** Comparisons are blog-tier; no documented edge over single-agent for forecasting. **Tag: LITERATURE THIN, NEW-ANGLE-LOW-PRIOR.**

## 2. Foundation models for time series

**Chronos-2 (Amazon, Oct 2025, arXiv 2510.15821, Apache 2.0).** 120M-param encoder, zero-shot multivariate + covariates, 300 forecasts/sec on A10G, weights free. SOTA on fev-bench / GIFT-Eval / Chronos Benchmark II. https://huggingface.co/amazon/chronos-2 **BUT financial-domain papers report it UNDERPERFORMS CatBoost / LightGBM on daily excess returns; fine-tuning yields "limited improvements"** (arXiv 2511.18578, "Re(Visiting) TSFM in Finance"). **Tag: KNOWN-NULL** for direct price forecasting; **NEW-ANGLE-LOW-PRIOR** as a feature-extractor input to a downstream model.

**TimesFM (Google, 2024, ~200M params).** Same domain-finance story per the financial-TSFM revisit paper. **Tag: KNOWN-NULL** for direct prediction.

**Kronos (Shi et al., Tsinghua, AAAI / arXiv 2508.02739, Aug 2025).** Decoder-only foundation model pre-trained on 12B K-lines across 45 exchanges including crypto. Two-stage tokenizer for OHLCV. Zero-shot: +93% RankIC over leading TSFM, +87% over best non-pre-trained baseline, -9% MAE volatility, +22% generative fidelity on synthetic K-lines. Weights on HF (NeoQuasar/Kronos-base). Live BTC/USDT 24h demo. https://github.com/shiyu-coder/Kronos **Tag: NEW-ANGLE-HIGH-PRIOR** for KXBTCD specifically. Kronos is the ONLY 2025 foundation model with crypto K-line pretraining + open weights + financial-task SOTA. v5-C and v6 NEVER tested a pre-trained second opinion; both used classical features.

**Moirai-2 / Moirai-MoE (Salesforce, 2025).** SOTA on 39 datasets, any-variate attention. Same domain-finance caveat: documented test-train overlap inflation 47 to 184% in TSFM evals (arXiv 2510.13654). **Tag: NEW-ANGLE-LOW-PRIOR** absent direct financial validation.

**Lag-Llama (ServiceNow, 2023, 10M params).** CPU-friendly. Outdated vs Chronos-2 / Kronos. **Tag: KNOWN-NULL** by dominance.

**PatchTST / iTransformer / TSMixer.** Architecture variants, not foundation models. Tested in financial benchmarks; do not dominate gradient boosters at our sample size. **Tag: NEW-ANGLE-LOW-PRIOR.**

## 3. Tabular foundation models

**TabPFN v2 (Prior Labs, Nature Jan 2025).** Foundation model pre-trained on 130M synthetic tabular datasets. Beats 4-hour-tuned ensemble in 2.8 seconds on n <= 10k, p <= 500, c <= 10. https://github.com/PriorLabs/TabPFN. Free, local. **Tag: NEW-ANGLE-HIGH-PRIOR.** v6's master dataset is 3688 rows x 14 features at midband n=971; squarely in TabPFN's sweet spot. TabPFN's different inductive bias (transformer in-context learning on synthetic priors) is the cheapest way to test whether v5-B / v6's "mid absorbs everything" verdict is a LightGBM artifact. ~4-hour build to swap LGBM for TabPFN on v6's existing parquet. If TabPFN ALSO shows lift < +0.005, the "no signal" verdict gets a second-model corroboration; if TabPFN shows >+0.005, v7 has a genuine model-class lift.

**XGBoost / CatBoost / LightGBM.** Baselines, used in v5-B and v6. No new insight to extract.

**TabLLM / TabTransformer.** Engineering-tier, not benchmarked above gradient boosters at low n. **Tag: NEW-ANGLE-LOW-PRIOR.**

**AutoML (AutoGluon, H2O.ai).** Meta-learning ensembles. AutoGluon ships with Chronos-2 integration. **Tag: NEW-ANGLE-LOW-PRIOR**: useful as a one-shot baseline but doesn't change the fundamental signal question.

## 4. Graph / orderbook ML

**LiT, Limit Order Book Transformer (Frontiers in AI, 2025).** Structured patches + transformer self-attention on Binance Level-2 top-20 bid/ask. Outperforms classical ML and prior LOB deep baselines; robust under distributional shift via fine-tuning. **Tag: NEW-ANGLE-MEDIUM-PRIOR** for Kalshi IF Kalshi exposes Level-2 depth. Per v6 Phase 1, Kalshi websocket DOES expose orderbook_snapshot + orderbook_delta, so the input is available; the question is whether KXBTCD-1h has enough book depth for LOB-style features (per v6 Section 3.4, depth is 1k-7k contracts at top-of-book, mostly thin).

**TLOB, Transformer with Dual Attention (arXiv 2502.15757, Feb 2025).** Tested on FI-2010, NASDAQ, Bitcoin. Same v6 caveat applies: cryptoesque depth profile is the test case. **Tag: NEW-ANGLE-MEDIUM-PRIOR.**

**Attention-Based Multi-Asset OFI (Yang et al., ACM AI in Finance 6th Conf, 2025).** Cross-asset attention on OFI; gains "pronounced in the <3 min regime." **Tag: NEW-ANGLE-MEDIUM-PRIOR** but v6 already tested OFI-adjacent features and got null at T-30 / T-15.

**Hawkes-process OFI (Anantha 2024) and RL market making (Marin/Vera 2022, MDPI Risks 2025, arXiv 2509.12456 SAC).** Elegant modeling of the dying signal v6 already killed; recent RL operates on continuous LOBs with millisecond cadence vs Kalshi's sparse arrivals. **Tag: NEW-ANGLE-LOW-PRIOR.**

## 5. Multimodal prediction

**FinGPT dissemination-aware (arXiv 2412.10823, Dec 2024).** +8% accuracy via news-clustering on stocks. Kalshi-mid pre-prices news; v4-B failure mode applies. **Tag: NEW-ANGLE-LOW-PRIOR.** FinBERT+LSTM and CLIP-style multimodal: literature thin or dominated. **Tag: KNOWN-NULL / LOW-PRIOR.**

## 6. Cross-platform arbitrage / second-opinion

**Polymarket CLOB price-history (2026 update).** Per pm.wiki and Polymarket docs, Gamma API returns historical snapshots, CLOB `/prices-history` provides per-token detailed price history; Data API + subgraph cover bulk historical trades. **Tag: NEW-ANGLE-MEDIUM-PRIOR.** v3 killed Polymarket-as-feature at the 30-day-detail ceiling; the 2026 endpoints may have softened this. Single phone call to verify history depth on KXBTCD-comparable markets is cheap.

**Polymarket-Dome, FinFeedAPI, Prediction Hunt, Arbitix, OddsPapi.** Aggregators consolidated; replacements paid or fragmented. Manifold REST public + Metaculus research-gated: play-money calibration without informational dominance on Kalshi sports. MARKETPULSE-style indices literature thin. **Tag: NEW-ANGLE-LOW-PRIOR across.**

## 7. RL and bandit approaches for market making

**Contextual bandits / Thompson sampling for sports betting.** NeurIPS 2025 work on contextual TS via missing data; high-dim sparse linear contextual bandits (arXiv 2211.05964). **Tag: NEW-ANGLE-MEDIUM-PRIOR** for v1's filter-vs-trade decision policy, NOT for forecasting. v5-A's combined filter is a deterministic threshold; a Thompson-sampling overlay could exploit the LOO-fragile +1.70pp signal more efficiently than fixed thresholds.

**Deep RL for Avellaneda-Stoikov (Marin/Vera 2022 plus 2024-2025 SAC extensions).** Same Kalshi depth issue as Section 4. **Tag: NEW-ANGLE-LOW-PRIOR.**

## 8. Self-supervised pretraining on Kalshi data

Kalshi has tens-of-millions of trades historically (Becker 72M through Nov 2025). Pretraining a small transformer on Kalshi's full trade history then fine-tuning per series is conceptually clean. **Literature is thin specifically on prediction-market pretraining**: most 2025 self-supervised work targets stock LOBs (Kronos, LiT, TLOB) or generic time series (Chronos, Moirai). **No published paper attempts this on prediction markets at our identifiable scale.** **Tag: NEW-ANGLE-MEDIUM-PRIOR** as research originality, **NEW-ANGLE-LOW-PRIOR** as expected edge: if a 12B-K-line foundation model (Kronos) shows zero-shot SOTA on crypto and TSFM still underperform CatBoost on financial returns, an in-house pretrain on a smaller corpus is unlikely to beat Kronos on KXBTCD or beat LGBM elsewhere.

## Recommended top-3 v7 angle list

### Angle A: Agentic LLM + Kalshi-mid ensemble (HIGHEST PRIOR)

**Technical approach:** Replicate the AIA Forecaster recipe at retail scale. Claude Opus 4.7 (1M context, $5 in / $25 out per MTok) plus web search plus news plus sportsbook second-opinion tool, output a calibrated YES probability, then ENSEMBLE with Kalshi mid at 67% market weight per AIA's MarketLiquid finding. Run on v1's denylisted-residual sports universe at T-35d to T-7d. Pre-register a Brier improvement threshold of +0.014 over Kalshi mid (matches AIA's market-ensemble lift on hard).

**Data requirements:** Free. Web search via Anthropic tool use; news via free RSS; sportsbook via the-odds-api free 500 credits/mo (v5-A budget); Kalshi mid via existing /historical/trades infra.

**Expected agent-clock cost:** 6 to 10 hours build (prompts + tool wiring + ensemble + orthogonality screen); $20 to $40 LLM spend at 200 to 400 forecasts at Opus 4.7 rates with reasoning.

**Prior of finding signal:** 25 to 35%. The 2025 literature (AIA, ForecastBench, Prophet Arena) all show LLMs at parity or slight lift over market on liquid markets when paired with retrieval + ensemble. v4-B's BSS -2.17 was the worst possible configuration; the lift from adding agentic retrieval + market ensemble per Halawi -0.020 plus AIA-style ensemble +0.014 closes most of the gap. Sports remains the weakest LLM topic (Janna Lu 2025: o3 sports 0.165 vs politics 0.120), so the prior is hedged.

**What it unlocks:** First demonstrated retail LLM edge on Kalshi sports if it passes; if it fails, closes the agentic-retrieval-was-the-salvage hypothesis cleanly.

### Angle B: Kronos zero-shot OHLCV on KXBTCD (HIGHEST ORIGINALITY)

**Technical approach:** Download NeoQuasar/Kronos-base from HF (free), run zero-shot 1-hour-ahead BTC/USDT direction forecasts at T-30 and T-15 relative to each KXBTCD-1h close, then orthogonality screen against Kalshi mid at v6's locked midband + +0.005 Brier threshold. Test both raw Kronos directional prediction and a Kronos-derived volatility forecast as a Kalshi-mid moderator.

**Data requirements:** Free. Coinbase 1-min OHLCV (already cached in v6's master parquet); KXBTCD mid AS-OF horizon (already in v6 master). Kronos weights free under Apache 2.0.

**Expected agent-clock cost:** 3 to 5 hours (model download, inference loop, parquet integration, orthogonality re-run); $0 external.

**Prior of finding signal:** 10 to 20%. v6 already showed v6_master features are absorbed by Kalshi mid at sub-hour horizons; Kronos's pre-trained inductive bias is the genuinely new variable. Kronos's published +93% RankIC over prior TSFM on price forecasting is the strongest 2025 signal for zero-shot crypto. If Kronos clears the v6 +0.005 threshold, v6's NULL is overturned by model class, not by data; if it doesn't, v6's NULL is doubly confirmed.

**What it unlocks:** First foundation-model second-opinion on Kalshi crypto; if it works, opens a clear path to fine-tuned Kronos on Kalshi-specific KXBTCD closes.

### Angle C: TabPFN v2 swap on v6 + v5-B datasets (CHEAPEST DIAGNOSTIC)

**Technical approach:** Swap LightGBM for TabPFN v2 on (a) v6's master parquet at midband n=971, T-30 horizon; (b) v5-B's Statcast n=146k subsampled to <=10k per TabPFN's row limit. Re-run the v6 / v5-B orthogonality screen unchanged. Pre-register: if TabPFN lift > LightGBM by >+0.003 Brier on either dataset, the v5-B / v6 "model anchors on price" verdict is partially LightGBM-specific.

**Data requirements:** Free. Both parquets already exist.

**Expected agent-clock cost:** 2 to 4 hours (TabPFN installation, sklearn-compatible swap, re-run); $0 external.

**Prior of finding signal:** 15 to 25%. TabPFN's transformer-in-context inductive bias is meaningfully different from gradient-boosting's tree-based bias. v5-B's positive Brier skill at n=146k (BSS +0.574) but unmonetizable margins suggest some signal exists but is in features LightGBM can't isolate; TabPFN's attention over rows + columns might extract it. If TabPFN ALSO shows tiny lift, v6 / v5-B NULLs are model-class robust; if it shows real lift, v7 has a path.

**What it unlocks:** Cheapest possible diagnostic on whether v5-B / v6 NULLs are LightGBM artifacts. Killer-experiment for the operator's "kill early > ship-then-fail" preference: 4 hours and $0 to materially update on two prior NULLs.

## Honest assessment

Three rounds of NULLs have established that free-public-feature ML at retail scale does not produce monetizable Kalshi edge on outcome prediction or microstructure. Angles A, B, C are the strongest remaining shots with pre-locked kill conditions. Prior of v7 producing NEW monetizable signal: 15 to 30%. Prior of CLEAN documented NULL strengthening cumulative state: >85%. Both serve the operator's kill-early standing rule. v5 Track A shadow-mode wiring and W2 v1 audit remain HIGHER EV than any v7 angle and should be done first.

Sources:
- [AIA Forecaster Technical Report](https://arxiv.org/html/2511.07678v1)
- [ForecastBench Leaderboards](https://www.forecastbench.org/leaderboards/)
- [LLM-as-a-Prophet / Prophet Arena](https://arxiv.org/abs/2510.17638)
- [PolyBench arXiv 2604.14199](https://arxiv.org/abs/2604.14199)
- [PolySwarm arXiv 2604.03888](https://arxiv.org/abs/2604.03888)
- [LiveTradeBench arXiv 2511.03628](https://arxiv.org/abs/2511.03628)
- [When Agents Trade / AMA arXiv 2510.11695](https://arxiv.org/abs/2510.11695)
- [Chronos-2 Hugging Face](https://huggingface.co/amazon/chronos-2)
- [Chronos-2 Paper](https://huggingface.co/papers/2510.15821)
- [Re(Visiting) TSFM in Finance arXiv 2511.18578](https://arxiv.org/html/2511.18578v1)
- [Kronos arXiv 2508.02739](https://arxiv.org/abs/2508.02739)
- [Kronos GitHub](https://github.com/shiyu-coder/Kronos)
- [TabPFN GitHub](https://github.com/PriorLabs/TabPFN)
- [TabPFN v2 Nature paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11711098/)
- [LiT Frontiers in AI 2025](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1616485/full)
- [TLOB arXiv 2502.15757](https://arxiv.org/abs/2502.15757)
- [Attention-Based Multi-Asset OFI ACM AI Finance 2025](https://dl.acm.org/doi/10.1145/3768292.3770430)
- [RL Market Making MDPI Risks 2025](https://www.mdpi.com/2227-9091/13/3/40)
- [FinGPT arXiv 2412.10823](https://arxiv.org/abs/2412.10823)
- [Polymarket Historical Timeseries Docs](https://docs.polymarket.com/developers/CLOB/timeseries)
- [Kalshi Orderbook Updates Docs](https://docs.kalshi.com/websockets/orderbook-updates)
- [Claude Opus 4.7 Anthropic](https://www.anthropic.com/claude/opus)
