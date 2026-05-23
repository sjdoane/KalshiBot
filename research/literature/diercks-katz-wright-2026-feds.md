# Diercks, Katz, Wright (Feb 2026): "Kalshi and the Rise of Macro Markets"

**Authors:** Anthony Diercks (Federal Reserve Board), Jared Katz
(Northwestern Kellogg), Jonathan H. Wright (Johns Hopkins / NBER)
**Reference:** FEDS Working Paper 2026-010, February 12 2026
**DOI:** 10.17016/FEDS.2026.010
**Venue:** Federal Reserve Finance and Economics Discussion Series
(working paper - "preliminary, circulated for discussion")
**Retrieved:** 2026-05-23

**Why this matters for Project Kalshi.** This is the first Fed
working paper using Kalshi data. It's NOT directly about weather
or maker-taker economics (the focus is on macro release accuracy:
CPI, NFP, FOMC). But it provides important context: the macro
markets are tightly priced by professionals, which **reinforces
our decision to focus on weather instead of macro.**

## TL;DR

1. Kalshi macro markets (CPI, NFP, FOMC, GDP, unemployment) are as
   accurate as Bloomberg consensus and FRBNY's Survey of Market
   Expectations.
2. For some releases (headline CPI), Kalshi statistically beats
   Bloomberg consensus.
3. **Kalshi's mode-on-day-before-FOMC has a perfect forecast record**
   for fed funds rate decisions through the 2025 sample (a
   statistically significant improvement over fed funds futures).
4. **Implication for Project Kalshi:** macro markets are NOT a
   tradable edge for retail. They're already priced efficiently by
   professional macro funds and prop desks. EC-1 weather focus is
   correct.
5. The paper's main contribution is methodological: showing how to
   extract full risk-neutral probability distributions from Kalshi
   for macro variables that previously had no options-based
   distributional measure.

## What the paper does

- **Validates Kalshi as a macro forecasting tool.** Compares
  Kalshi-implied probabilities for CPI/NFP/FOMC/GDP to:
  - Fed Funds futures (for FOMC decisions)
  - FRBNY Survey of Market Expectations (for fed funds path)
  - Bloomberg consensus (for CPI, unemployment)
- **Documents intraday dynamics.** Example: July 2025 FOMC rate-cut
  probability rose to 25% after Waller/Bowman remarks, fell after
  stronger-than-expected June employment.
- **Decomposes the full distribution.** Mean, variance, skewness of
  fed funds rate distribution responds to news in ways previously
  not measurable.
- **Promises a public data release** at EconFutures.com (subject to
  approval) with downloadable time series + GitHub code.

## Kalshi macro market list (Table 1)

| Series | First contract | Frequency | Theme |
|---|---|---|---|
| CPI MoM | June 2021 | Monthly | Inflation |
| CPI YoY | November 2022 | Monthly | Inflation |
| CPI for Year | 2022 | Annual | Inflation |
| Core CPI MoM | June 2022 | Monthly | Inflation |
| Core CPI YoY | December 2022 | Monthly | Inflation |
| Core CPI for Year | 2025 | Annual | Inflation |
| Unemployment Rate | July 2021 | Monthly | Labor |
| Payroll Release | March 2023 | Monthly | Labor |
| GDP Growth | Q2 2021 | Quarterly | Growth |
| GDP Growth | 2025 | Annual | Growth |
| Probability of US Recession | 2022 | Annual | Growth |
| Federal Funds Rate Decision | May 2023 | FOMC | Policy |
| Federal Funds Rate Target Rate | December 2021 | FOMC | Policy |

These are Kalshi's macro markets. Note **NONE of them are weather.**

## Headline findings

| Comparison | Kalshi outcome |
|---|---|
| 150-day-out federal funds rate forecast vs FRBNY SME | Similar MAE |
| Day-before-FOMC fed funds rate vs fed funds futures | **Kalshi statistically beats futures** (perfect forecast record on Kalshi median/mode) |
| Headline CPI forecast vs Bloomberg consensus | Kalshi statistically beats |
| Core CPI forecast vs Bloomberg consensus | Statistically similar |
| Unemployment vs Bloomberg consensus | Statistically similar |
| Macro distribution variance after CPI release | Falls most after zero-surprise (general resolution of uncertainty) |
| Macro distribution skewness after FOMC press conference | Becomes more negative (upside uncertainty resolves) |

## Volume / depth

- Kalshi macro markets are "supported by market makers such as
  Susquehanna."
- "Maximum exposure per market currently reaches $7 million" -
  enough for institutional macro funds.
- Macro markets are explicitly compared to options markets in
  liquidity; Fed-funds-rate distributional markets fill a niche
  that options don't.

This is the **opposite end of the depth spectrum from EC-1
weather.** Macro markets attract pro/institutional flow; weather
attracts retail + some pro market makers.

## What this paper says about market efficiency

The paper does NOT find favorite-longshot bias or systematic
mispricing in macro markets (that's not its focus). The implicit
finding is: macro markets are tightly priced by sophisticated
participants. There's no obvious retail-overpricing-the-longshot
edge in macro.

This is consistent with Burgi 2026's per-category finding that
Finance/Economics had the smallest favorite-longshot bias (ψ
0.032/0.034 vs 0.034 average, but with constants of -1.431 /
-0.978 vs -1.736 - i.e., milder distortion).

## Implications for Project Kalshi

1. **Confirms macro is not a retail edge.** Fed-funds-rate
   forecasting on Kalshi already matches FRBNY SME. The Fed
   itself is studying Kalshi as a measurement instrument. EC-1's
   choice of weather over macro is correct.

2. **Susquehanna actively makes macro markets.** Per this paper.
   If Susquehanna also makes weather markets (which Burgi and
   Becker both suggest), then Project Kalshi will compete with a
   professional MM in the same product family. Plan accordingly.

3. **The Fed paper notes Burgi/Deng/Whelan 2025 as concurrent
   work** ("examine the full range of Kalshi markets and find them
   to be valuable forecasters"). Diercks et al sit beside Burgi,
   Becker, and Le in the small cluster of academic work on Kalshi.

4. **Distribution-based metrics matter.** Diercks shows that the
   FULL distribution of Kalshi prices (across strikes for a given
   release) is useful. For Project Kalshi this suggests Phase 2
   strategy design could consider the cross-strike structure
   within an event, not just per-strike calibration.

5. **The CFTC's blessing of Kalshi as "the same category as the
   Chicago Mercantile Exchange"** is significant. This is a Fed
   working paper relying on Kalshi data; the Fed's institutional
   credibility partially rubs off on Kalshi's status as a
   trustworthy venue. Reduces (slightly) the regulatory tail risk
   I had factored into the legal analysis.

## What the paper does NOT cover

- No analysis of weather markets, sports markets, or non-macro
  Kalshi categories.
- No maker/taker decomposition.
- No favorite-longshot analysis.
- No trading strategy proposals.
- No discussion of small-account economics or retail viability.

## Pin quotes

> "Kalshi markets provide a high-frequency, continuously updated,
> distributionally rich benchmark that is valuable to both
> researchers and policymakers."

> "We find the Kalshi median and mode have a perfect forecast
> record on the day before the FOMC meeting, which represents a
> statistically significant improvement over the fed funds futures
> forecast."

> "For headline CPI, we find Kalshi provides a statistically
> significant improvement over the Bloomberg consensus forecast."

> "Burgi, Deng and Whelan (2025) examine the full range of Kalshi
> markets and find them to be valuable forecasters for nearly all
> events, many of which are unrelated to economic variables. We
> complement these contributions by focusing on extensively
> validating Kalshi as a forecasting tool."

## Limitations the Fed authors flag

- Working paper status; not peer-reviewed.
- Sample period 2022-2025; macro markets evolve as Kalshi grows.
- Comparison to FRBNY SME and Bloomberg consensus may not be the
  toughest benchmark for some series.
- Fed funds rate distribution dynamics are studied; other macro
  variables get less distributional analysis.
- They explicitly do NOT focus on micro-microstructure (maker/
  taker, spreads, depth).
