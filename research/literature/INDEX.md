# Project Kalshi Literature Index

14 academic / community papers studied for Project Kalshi. Papers 1-7
were the EC-1 / v1 / v2 foundation; papers 8-10 were added by Agent V3-D
for the v3 design phase (Polymarket lead-lag, CV best practices, sports
prediction ceiling); papers 11-14 were added by Agent V4-B for the v4
design phase (LLM-as-forecaster literature). Each file is a thorough
extraction with data, methodology, findings, pin quotes, and explicit
"implications for Project Kalshi" sections.

Maintenance: when a new paper is added, copy the structure of an
existing file (any of the 7 below is fine), then append a TLDR to
this index and to the memory file
`project_kalshi_literature.md`.

## The four-fact summary

1. **Makers > Takers on Kalshi.** Whelan's equilibrium model
   predicts it; Burgi's data confirms (-9.64% vs -31.46%); Becker
   confirms (+1.12% vs -1.12% post-2024); Bartlett decomposes it
   into adverse-selection-loss + behavioral-surplus-gain.
2. **Weather has small bias.** Burgi ψ 0.031 (vs 0.034 cross-cat
   avg); Becker 2.57pp per-trade gross gap; Le finds it's
   overconfident at short horizons, underconfident at long.
3. **2024 sign flip.** Pre-October-2024 takers won; post-flip
   makers win. Only use post-flip data for modeling.
4. **Bias is shrinking.** Burgi ψ dropped from 0.048*** (2024) to
   0.021* (2025) as institutional MMs entered.

## Papers

| # | File | First author | Year | Venue | Status |
|---|---|---|---|---|---|
| 1 | [burgi-deng-whelan-2025.md](burgi-deng-whelan-2025.md) | Burgi/Deng/Whelan | Jan 2026 | UCD WP / CEPR DP20631 | Peer-reviewable academic |
| 2 | [becker-2026-microstructure.md](becker-2026-microstructure.md) | Becker | Early 2026 | jbecker.dev | Personal research, 72M trades |
| 3 | [le-2026-crowd-wisdom.md](le-2026-crowd-wisdom.md) | Le | Feb 2026 | arXiv 2602.19520 | Preprint, uses Becker's data |
| 4 | [bartlett-ohara-2026-adverse-selection.md](bartlett-ohara-2026-adverse-selection.md) | Bartlett / O'Hara | Apr 2026 | SSRN / Stanford Law | Working paper, partial extraction |
| 5 | [whelan-2026-betfair.md](whelan-2026-betfair.md) | Whelan | Jan 2026 | CEPR DP20633 | Theoretical foundation (Betfair) |
| 6 | [diercks-katz-wright-2026-feds.md](diercks-katz-wright-2026-feds.md) | Diercks/Katz/Wright | Feb 2026 | Fed FEDS 2026-010 | Fed working paper, macro focus |
| 7 | [zerve-calibshi-2026.md](zerve-calibshi-2026.md) | "umbreonseele" (pseudonym) | Mar 2026 | Zerve Gallery | Community notebook, NOT peer-reviewed |
| 8 | [ng-peng-tao-zhou-2026-price-discovery.md](ng-peng-tao-zhou-2026-price-discovery.md) | Ng/Peng/Tao/Zhou | Apr 2026 | SSRN 5331995 | Working paper (PDF gated; extracted from abstract + seminar + secondary) |
| 9 | [lopez-de-prado-2018-cv.md](lopez-de-prado-2018-cv.md) | Lopez de Prado | 2018 | Wiley AFML Ch 7 + JPM 2014 | Foundational book + companion paper |
| 10 | [sports-prediction-ceiling-2022-2024.md](sports-prediction-ceiling-2022-2024.md) | Li/Kuo/Burkhard/538 et al. | 2022-2025 | Combined (PMC, blog, Medium, 538) | Cross-source synthesis on ceiling |
| 11 | [halawi-2024-human-level-forecasting.md](halawi-2024-human-level-forecasting.md) | Halawi/Chen/Hashimoto/Steinhardt | Feb 2024 | arXiv 2402.18563 / NeurIPS 2024 spotlight | Canonical LLM-as-forecaster paper |
| 12 | [karger-2024-forecastbench.md](karger-2024-forecastbench.md) | Karger/Bastani/Yueh-Han/Jacobs/Halawi/Zhang/Tetlock | Sep 2024 | arXiv 2409.19839 | Dynamic LLM forecasting benchmark |
| 13 | [schoenegger-2024-silicon-crowd.md](schoenegger-2024-silicon-crowd.md) | Schoenegger/Tuminauskaite/Park/Bastos/Tetlock | Nov 2024 | Science Advances 10, eadp1528 | 12-LLM ensemble matches human crowd |
| 14 | [aia-2025-forecaster-and-followups.md](aia-2025-forecaster-and-followups.md) | AIA Team + Lu + Singh + Yang/Wu + Azam/Roucher + FutureSearch | 2025-2026 | arXiv 2511.07678 + 2507.04562 + 2511.18394 + 2510.17638 + HF blog + evals.futuresearch.ai | Frontier LLM forecasting cluster |

## One-paragraph TLDRs

### #1 Burgi, Deng, Whelan 2026 - the empirical foundation
First academic paper with transaction-level Kalshi data (313k
prices, 2021 - April 2025). Showed maker -9.64%, taker -31.46%
average returns (pre-2025 fees). Makers profitable on contracts
>= 50c (+2.6%, 33% SD). Weather has SMALLER favorite-longshot
bias than the cross-category average. Bias attributable to
Kahneman-Tversky probability over-weighting (β = 0.09) plus modest
disagreement.

### #2 Becker 2026 - the biggest sample
72.1M trades through November 2025. Per-category maker-taker gaps
in basis points; weather gap is 2.57pp per trade (mid-tier).
Documents the 2024 sign flip - pre-October-2024 takers won +2.0%,
makers now win +2.5%. Mechanism is order-flow accommodation, not
forecasting (Cohen's d = 0.02 between maker YES vs NO returns).

### #3 Le 2026 - calibration regime structure
Decomposes prediction market calibration into 4 components (87.3%
of variance). The load-bearing finding for Project Kalshi: weather
is OVERCONFIDENT at short horizons (prices too extreme), but
UNDERCONFIDENT at long horizons (prices compressed toward 0.5).
This explains why Phase 1.5 (close-window) showed 9pp edge while
Phase 1.6 (pre-resolution) showed only 1.5pp - opposite regimes.

### #4 Bartlett & O'Hara 2026 - adverse selection vs behavioral surplus
41.6M trades. VPIN-adapted adverse-selection metric. Single-name
markets have higher informed price impact but makers earn 2x more
per contract because traders systematically overbet YES on
NO-settling markets, generating a behavioral surplus that
cross-subsidizes adverse selection. KXHIGH per-day strikes are
single-name markets (higher both effects). Full PDF inaccessible
without SSRN auth; extraction is abstract-level.

### #5 Whelan 2026 - the theoretical foundation
The model Burgi 2026 adapted for Kalshi. Maker/Taker sort by
subjective belief into 5 actions. Predicts Maker > Taker returns
and nonlinearly worse Taker losses on longshots. Multiple
equilibria (thick vs thin). Empirical Betfair work on 200k+ soccer
matches confirms predictions pre-match; "Yogi Berra effect"
emerges late in-play (bettors overestimate late comebacks).

### #6 Diercks/Katz/Wright 2026 - Fed macro paper
Validates Kalshi macro markets (CPI, NFP, FOMC) as accurate as
Bloomberg consensus and FRBNY Survey of Market Expectations.
Kalshi beats fed funds futures for day-before-FOMC fed funds rate
mode forecast. Confirms macro is NOT a retail edge (institutions
make these markets efficiently). Doesn't analyze weather.

### #7 Zerve CalibShi 2026 - community origin of EC-1
Anonymous community notebook. Source of the "14.8x ECE improvement
on 8,494 KXHIGHNY markets via isotonic regression" claim that
originally motivated EC-1. CRITICAL: no in-sample-vs-OOS partition
disclosed. The 14.8x figure is almost certainly in-sample. Our
Phase 1.6 OOS gate (which Zerve never did) shows the true number
is 1.44x and below the tradable threshold after fees. **Do not
cite as evidence of edge in any future plan.**

### #8 Ng, Peng, Tao, Zhou 2026 - Polymarket vs Kalshi price discovery
The academic paper underlying the v3 thesis. Common contracts across
Polymarket, Kalshi, PredictIt, Robinhood during 2024 US election (Oct
23 - Nov 5 2024). Headline: **Polymarket leads Kalshi in price
discovery**, particularly when liquidity / activity high. Mechanism is
order-flow conditional: greater-directional-flow venue leads.
Arbitrage windows are seconds-to-minutes; transaction costs significantly
reduce profit. **Critical for v3:** sample is politics 2024 only, NOT
sports 2026. The 2026 sports volume asymmetry (Kalshi $2.7B/wk vs
Polymarket US $5M/wk) likely INVERTS the lead-lag direction for
US-tradeable sports markets. Polymarket Global (offshore) at $2.1B/wk
is the only Polymarket sports venue plausibly leading Kalshi.

### #9 Lopez de Prado 2018 - CV best practices + multiple testing
AFML Ch 7 (purged k-fold with embargo) + Bailey/Lopez de Prado 2014
Deflated Sharpe Ratio. **The methodological foundation against the
v2 CV-leak failure.** Purging removes training rows whose label horizon
overlaps test; embargo adds one-sided buffer (default 1% of dataset,
practical floor = max(H_label, max feature lookback) which is 90+ days
for v3). Multiple-testing correction: expected max Sharpe across N
trials inflates by √(ln(N)/T); apply Bonferroni α/N or BH-FDR.
**Minimum AFML sample is T >= 252;** v3's likely n=30-100 is structurally
below this. Treat v3 gate as kill-test, not discovery-test.

### #10 Sports prediction ceiling 2022-2025
Combined extraction across Li et al. 2022 (MLB game prediction ceiling
55-66% with public features, n=30 teams * 5 seasons, SVM+RFE at 65.75%),
Kuo 2022 (538 NBA model = seed-only baseline = 76% on n=75 playoff
series), Burkhard 2025 (MLB season-total best model HOBIE MAE 3.2 wins,
Pearson 0.92 vs Vegas 0.97), 538 NFL retrospectives (Brier 0.208 in 2020,
0.20-0.23 range 2015-2020), Sports-AI.dev benchmarks (sportsbook lines
Brier 0.18-0.22). **Translated to season-long Kalshi markets at 0.70-0.95
YES, the maximum public-feature edge is +1pp to +3pp gross.** This is AT
OR BELOW C6's +2pp v1-overage floor. A passing v3 gate at the realistic
sample size has a high prior on false positive.

### #11 Halawi et al. 2024 - canonical LLM-as-forecaster
The Halawi/Chen/Hashimoto/Steinhardt paper (UC Berkeley, NeurIPS 2024
spotlight). Retrieval-augmented + fine-tuned GPT-4 system achieves
**Brier 0.179 on 914 binary questions** across 5 platforms (Metaculus,
GJOpen, INFER, Polymarket, Manifold) published after June 1 2023 (post-
cutoff). Human crowd Brier 0.149 on same set (gap 0.030 in crowd's
favor). System BEATS crowd on uncertain questions (0.199 vs 0.246 on
crowd predictions 0.3-0.7) but LAGS on high-confidence questions due to
RLHF hedging. **This load-bearing failure mode applies directly to v4
because v1 trades at 0.70-0.95 YES (the high-confidence regime).**
Ablation: retrieval -0.020 Brier, fine-tune -0.007 Brier, combined
-0.027 from baseline 0.206. Per-platform: Metaculus crowd 0.104 /
system 0.134; Polymarket crowd 0.127 / system 0.172.

### #12 Karger et al. 2024 - ForecastBench
The Tetlock + FRI + Halawi benchmark (arXiv 2409.19839). 1,000-question
dynamic benchmark with 200-question evaluation rounds. **Superforecasters
Brier 0.096; top LLM (Claude 3.5 Sonnet) Brier 0.122; general public
0.121.** "Expert forecasters outperform the top-performing LLM (p < 0.001)."
Per-source: superforecaster vs Claude 3.5 Sonnet on market questions
(Metaculus / Manifold / Polymarket / RCP) 0.074 vs 0.107; on dataset
questions 0.118 vs 0.138. **Older / cheaper LLMs (GPT-3.5, Claude 2.1,
Mistral 7B) at random Brier 0.25.** 2026 update: o3 0.1352 on dataset;
GPT-4.5 0.101 overall (best LLM). LLM-superforecaster parity projected
Nov 2026 (95% CI Dec 2025 - Jan 2028). **GPT-4.5 0.994 correlation with
market prices on Tournament leaderboard** is the documented market-anchoring
failure mode (v4 master plan S-B2).

### #13 Schoenegger et al. 2024 - Wisdom of the Silicon Crowd
Science Advances Nov 2024 (arXiv 2402.19379). 12-LLM ensemble on 31
binary Metaculus questions vs 925-human crowd. **Ensemble median Brier
0.20 (SD 0.12) vs human crowd 0.19 (SD 0.19).** t(60)=0.19, p=0.85;
not statistically different. Equivalence bounds wide (Cohen's d=0.5 =
±0.081 Brier window). **Ensemble Brier (0.20) is WORSE than best individual
(GPT-4 at 0.15)**, ensembling cuts noise but doesn't beat the best base.
Documented biases: round-number clustering (38 predictions at 50%, zero
at 49% / 51%); acquiescence YES bias (mean 57.4% vs 45% actual); topic
refusal (Qwen 7B refused conflict questions); overconfidence. **No sports
questions** in this sample. Most-optimistic LLM-forecasting paper of the
v4 cluster, but does NOT measure LLM vs market price (only vs crowd
average).

### #14 AIA Forecaster 2025 + LLM-forecasting follow-up cluster
Combined extraction across AIA Forecaster (arXiv 2511.07678, Nov 2025),
Janna Lu 2025 (2507.04562), "Future Is Unevenly Distributed" 2025
(2511.18394), Prophet Arena 2025 (2510.17638), PrediBench, BTF-2.
**State-of-the-art LLM forecasting findings:** (a) AIA Forecaster
matches superforecasters on ForecastBench FB-7-21 (AIA 0.1125 vs SF
0.1110) but **LAGS market consensus 0.015 Brier on hard liquid markets**
(MarketLiquid: AIA 0.126, market 0.111). (b) AIA + market ensemble
beats either alone (Brier 0.092 FB-7-21, 0.106 MarketLiquid; 67% market
weight on hard). (c) **Sports is one of the weakest LLM topics**:
Claude 3.7 sports 0.28 vs geopolitics 0.12 (2.3x worse); GPT-5 sports
0.28 vs geopolitics 0.14 (2x worse); Janna Lu 2025 o3 sports 0.1649 vs
politics 0.1199 (37% worse). (d) Reasoning models substantially
outperform non-reasoning frontier (o3 0.135 vs GPT-4o 0.188, 0.05 spread).
(e) **No published Haiku 4.5 or GPT-4o-mini forecasting benchmark Brier.**
Cheap-tier untested. (f) Platt scaling (parameter √3) is canonical
calibration post-processing (-0.007 Brier vs no correction). (g) Long-
horizon LLM advantage over markets (3+ hour resolution window) per
Prophet Arena, mildly positive for v4's T-35d operation. (h) Even at
market-baseline Brier, LLM trading returns are below break-even (Prophet
Arena top model 0.943). **Aggregate verdict: prior of v4 Track B clearing
C6 on Project Kalshi's sports-heavy long-horizon high-confidence universe
is 5-15%** per cluster evidence.

## Convention for new entries

When you add a new paper:
1. Write the full extraction following the existing file structure
   at the same level of detail.
2. Add a row to the table above (preserve the alphabetical-by-
   importance ordering).
3. Add a one-paragraph TLDR in the order matching the table.
4. Update the count at the top of this file.
5. Append the same TLDR to
   `~/.claude/projects/.../memory/project_kalshi_literature.md`.
6. If the new paper adds a 5th-or-greater "must remember" fact,
   add it to the four-fact summary section at the top.
