# v7 Scoping Synthesis

**Date:** 2026-05-25
**Inputs:** `research/v7/01-data-sources-scoping.md`, `research/v7/02-recent-ml-research.md`.
**Status:** Pre-Phase-1 candidate angle list for operator approval.

## TL;DR

Six rounds of NULL leave a narrow surface. After scoping 2025-2026 ML literature and US-accessible data sources, three v7 candidate angles emerge plus one operations-first alternative. The single biggest negative finding: foundation TS models (Chronos-2, TimesFM) are KNOWN-NULL for financial price forecasting per arXiv 2511.18578; only **Kronos** (the one 2025 model pre-trained on 12B crypto K-lines) survives as a candidate. The single biggest positive finding: **AIA Forecaster + market ensemble at 67% market weight** beats either alone at Brier 0.092 on hard markets (arXiv 2511.07678), suggesting v4-B's BSS -2.17 was the worst possible configuration. The single biggest data-acquisition win: **Hyperliquid /info is free and US-accessible** ($1B+ daily BTC-PERP volume), unblocking v6's Binance-451 problem for forward-recording.

## What Phase 1 scoping changes about the v6/v7 landscape

### Data side (Agent 1)

- **Hyperliquid /info**: live probed 200 OK on `l2Book`, `candleSnapshot`, `fundingHistory` from CA IP. Free, $1B+ daily volume. L2 is current-state only so historical L2 still requires forward-recording, but **historical funding + candles are deep**. Substitutes for Binance.com 451-block at zero cost.
- **the-odds-api 20K Starter at $30/month**: unlocks v6's deferred sports-line-movement angle with historical odds across US sportsbooks back to 2020. One month buy and drain, total $30 of $30-$60 budget.
- **dYdX v4 indexer (free)**: historical trades / candles / funding free; current-state L2 only.
- **Coinglass Hobbyist $29**: SKIP per agent 1 reclassification. The "tick-level L2" advertised at Hobbyist actually starts at Standard ($299).
- **GDELT 2.0**: free, but timed out from CA on 3 retries. Retry from a production VPS if needed for news angle.

OUT OF BUDGET (confirmed): Tardis $350+, CoinAPI $79+, Amberdata enterprise, Velo $129+, NewsAPI Business $449, X Basic $200.

### ML side (Agent 2)

- **AIA Forecaster (Anthropic Insights, Nov 2025)**: matches superforecasters on FB-7-21 (Brier 0.1125 vs SF 0.1110); LAGS market consensus by 0.015 Brier on hard liquid markets; ensemble at 67% market weight beats either alone at Brier 0.092 / 0.106 on hard subset.
- **Kronos (Tsinghua, AAAI / arXiv 2508.02739)**: only 2025 foundation model pre-trained on 12B crypto K-lines, Apache 2.0 weights. Zero-shot +93% RankIC over prior TSFM. Never tested in v5-C or v6.
- **TabPFN v2 (Prior Labs, Nature Jan 2025)**: 130M synthetic tabular datasets pre-training, transformer in-context learning. Free, runs locally. v6's master parquet is squarely in TabPFN's sweet spot.
- **Chronos-2 / TimesFM**: KNOWN-NULL for direct financial price forecasting per "Re(Visiting) TSFM in Finance" arXiv 2511.18578. Do NOT bet on these.
- **PolyBench Apr 2026**: 5 of 7 LLMs LOST money live on Polymarket; only MiMo-V2-Flash +17.6% and Gemini-3-Flash +6.2% positive. Even at 2026 frontier, LLM forecasting on prediction markets is unreliable.
- **Prophet Arena live Jan-Mar 2026**: top model Grok-4 only 30.9% settlement win rate.
- Cumulative ML agent prior of v7 producing NEW monetizable signal: **15 to 30%**. CLEAN documented NULL strengthening cumulative state: >85%.

## v7 candidate angles

### Angle A: Agentic LLM forecaster + Kalshi-mid ensemble

The cutting-edge LLM forecasting recipe. Closes v4 Track B's "did we try hard enough?" question.

| Dimension | Value |
|---|---|
| Methodology | Claude Opus 4.7 with web search + news + sportsbook tool use, output calibrated YES prob, ensemble with Kalshi mid at 67% market weight per AIA Forecaster |
| Target | v1's denylisted-residual sports universe at T-35d to T-7d horizons (NFL, MLB, NBA, NCAA-FB, NCAA-BB, soccer, fights) |
| Pre-registered bar | +0.014 Brier improvement over Kalshi mid (matches AIA's market-ensemble lift on hard markets) |
| Data requirements | Free: web search via Anthropic tools, news via free RSS, sportsbook via the-odds-api free 500 credits/mo. Kalshi mid via existing infrastructure. |
| Agent-clock cost | 6 to 10 hours build (prompts + tool wiring + ensemble + orthogonality screen) |
| LLM API spend | $20 to $40 (200 to 400 forecasts at Opus 4.7 rates with reasoning) |
| Prior of finding signal | **25 to 35%** (highest of the three) |
| What it unlocks if positive | First demonstrated retail LLM edge on Kalshi sports. Could deploy as v1 filter overlay. |
| Cool/original factor | High - replicates AIA Forecaster recipe, fully agentic |

### Angle B: Kronos zero-shot foundation model on KXBTCD

The most originally-novel angle. Tests whether a crypto-specific foundation model can do what v5-C and v6's classical features could not.

| Dimension | Value |
|---|---|
| Methodology | Download NeoQuasar/Kronos-base from HF (Apache 2.0), run zero-shot 1h-ahead BTC/USDT direction forecasts at T-30 / T-15 relative to each KXBTCD close, orthogonality screen at v6's locked +0.005 Brier threshold |
| Target | KXBTCD-1h hourly Bitcoin direction contracts (v6's exact target) |
| Pre-registered bar | +0.005 Brier improvement over Kalshi mid (v6 protocol) |
| Data requirements | Free. Coinbase 1m OHLCV (already in v6 master parquet), KXBTCD mid (already in v6 master), Kronos weights free |
| Agent-clock cost | 3 to 5 hours (model download + inference loop + parquet integration + orthogonality re-run) |
| LLM API spend | $0 external |
| Prior of finding signal | **10 to 20%** |
| What it unlocks if positive | First foundation-model second-opinion on Kalshi crypto. Path to fine-tuned Kronos on KXBTCD-specific data. v6 NULL overturned by model class, not data. |
| Cool/original factor | Highest - only 2025 paper, only 12B-K-line pretrained model with open weights, untested anywhere in Project Kalshi |

### Angle C: TabPFN v2 diagnostic swap on v6 + v5-B

Cheapest possible diagnostic. Tests whether the "model anchors on price" failure mode is LightGBM-specific or model-class-robust.

| Dimension | Value |
|---|---|
| Methodology | Swap LightGBM for TabPFN v2 on (a) v6 master parquet at midband n=971, T-30 horizon, and (b) v5-B Statcast n=146k subsampled to <=10k per TabPFN row limit. Re-run orthogonality screen unchanged. |
| Target | v6 KXBTCD-1h + v5-B MLB props (both already null at LightGBM) |
| Pre-registered bar | TabPFN Brier lift > LightGBM by > +0.003 on either dataset, OR TabPFN clears +0.005 over Kalshi mid in absolute terms |
| Data requirements | Free. Both parquets already in repo. |
| Agent-clock cost | 2 to 4 hours (install + sklearn-compatible swap + re-run) |
| LLM API spend | $0 |
| Prior of finding signal | **15 to 25%** |
| What it unlocks if positive | Identifies LightGBM as the bottleneck. Path to TabPFN-based v6 / v5-B salvage runs. Resolves "is it data or model" question. |
| Cool/original factor | Medium - Nature Jan 2025 paper but applied to existing data, not new |

## Alternative path: operations first

Per ML agent's note "Track A shadow-mode wiring and W2 v1 audit remain higher EV than any v7 angle":

### Path Ops-1: W2 v1 audit (1-2h, $0)

Re-measure v1's measured edge on the denylisted-residual universe. Pending from v3. Resolves whether v1 actually has a measurable +X pp edge on the markets it currently trades, after removing the KXNFLWINS / KXNFLPLAYOFF / KXMLBPLAYOFFS series that v4-H stress-tested as -3.02pp aggregate.

### Path Ops-2: Track A shadow-mode wiring (4-6h, $0)

Wire v5's `evaluate_market_combined` as a logging-only call in v1's main loop. After 120-180 days of accumulated live decisions, evaluate the filter on resolved outcomes. Pending from v5.

## What I recommend (and why)

**My top recommendation: run B + C in parallel as v7 Phase 2** ($0 spend, 5 to 9 hours combined agent-clock).

Reasoning:
1. Both are $0 external. The $24 LLM headroom stays intact for a potential Angle A follow-up if either passes.
2. B (Kronos) is the operator's stated wish for "really cool and original" - it's the only 2025 crypto-specific foundation model with open weights.
3. C (TabPFN) is the cheapest possible diagnostic on whether v5-B / v6 NULLs were model-class-specific. If TabPFN ALSO shows null, it strengthens v6's verdict cleanly; if it shows lift, v7 has found a path.
4. Together they cover two orthogonal "did we try hard enough?" hypotheses (model class for tabular, foundation pre-training for time series).
5. If either passes, run Phase 3 critic; if both fail, write v7 NULL verdict and consider Angle A as v8.

**My second recommendation: Angle A as v7** ($20-40 spend, 6-10h).

Higher prior (25-35%) but burns most of the remaining LLM budget. Cool factor matches the operator's wish. Use this if the operator wants a high-conviction single swing.

**My third recommendation: Ops path first**.

Per the ML agent's higher-EV reasoning. Less "cool and original" but operationally meaningful. Could combine with v7-B + v7-C diagnostics.

## Open question for the operator

Which path?

1. **v7 = B + C in parallel** (zero spend, two shots, $24 LLM budget untouched for v8). Recommended.
2. **v7 = Angle A only** (highest prior, $20-40 spend, single biggest swing). Most "cool" via AIA recipe.
3. **v7 = Angle B only** (most original, $0). Tests foundation model on crypto.
4. **Ops path first** (W2 + Track A wiring), defer v7 research.
5. **Combination** (e.g., B + C + Track A wiring), or different priorities you have in mind.

I'll wait for green light before launching any Phase 1 v7 agents.

## Prior distribution after Phase 0 scoping

Combining the ML agent's per-angle priors with the data feasibility findings:

| Outcome | Subjective P |
|---|---|
| v7 finds monetizable signal (SHIP-clean or PARTIAL) | 25 to 35% (if Angle A); 10 to 25% (if B or C only); 30 to 40% (if B + C combined two-shot) |
| v7 NULL clean | 60 to 75% (depending on angle mix) |
| v7 NULL with diagnostic insight (e.g., TabPFN confirms model-class-robust null) | 10 to 20% sub-component of NULL |

The "find signal" tail is real but small. Project Kalshi has now produced 6 confirmed NULLs; v7 is a probabilistic but not desperate swing at "cool and original." The kill-early standing rule remains in force.
