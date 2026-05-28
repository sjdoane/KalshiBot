# V10-A Methodology Lock v2 (Becker Data Source)

**Date:** 2026-05-27
**Author:** V10-A orchestrator (this session)
**Predecessor:** `research/v10/A2-methodology-lock.md` (v1; killed at live API data layer)
**Status:** SPECULATIVE LOCK pending Becker inventory result (Phase 1 Agent v10A-1 output). If Phase 1 reports total Kim-mapped release months post 2024-10-01 less than 40, V10-A confirm-kills on sample size and v2 is shelved. If 40 to 59, MARGINAL with reduced gate. If at least 60, Phase 2 proceeds.

---

## Bottom-line decision logic (read first)

| Inventory result (post 2024-10-01 release months across Kim 4-series) | Action |
|---|---|
| n_events >= 60 | Phase 2 with full Bonferroni at alpha = 0.05 / 12 = 0.0042 |
| 40 <= n_events < 60 | Phase 2 with directional priors only (no Bonferroni; report raw + Holm corrected, treat as exploratory) |
| 20 <= n_events < 40 | KILL on sample size; document the kill with correct rationale |
| n_events < 20 | KILL on sample size; close round |

This decision is the only post-data gate adjustment permitted. All other gates are locked below.

---

## 1. Replication target

### Source paper

Kim, Sumin; Kim, Minjae; Kwon, Jihoon; Kim, Yoon; Kagan, Nicole; Lee, Joo Won; Levy, Oscar; Lopez-Lira, Alejandro; Lee, Yongjae; Choi, Chanyeol. "LLM as a Risk Manager: LLM Semantic Filtering for Lead-Lag Trading in Prediction Markets." arXiv:2602.07048v2. February 2026.

### Headline claim

Two stage hybrid: Granger causality on Kalshi Economics market probability time series identifies statistical lead-lag pairs; LLM filters economically implausible directions; result is 51.4% to 54.5% win rate (+3.1pp absolute), average loss magnitude $649 to $347 (-46%).

### Kim ticker -> Becker prefix mapping (confirmed via Becker categories.py)

| Kim ticker | Becker event_ticker prefix(es) | Note |
|---|---|---|
| KXCPI | CPI, CPIYOY, CPICORE, CPICOREYOY, ACPI | All CPI variant releases, monthly |
| KXNFP | PAYROLLS | Kalshi's nonfarm payrolls series prefix |
| KXUNRATE | U3 | Kalshi's unemployment rate series |
| KXFEDFUNDS | FEDDECISION, FED, RATECUT, RATECUTCOUNT, TERMINALRATE | Fed-related decision and rate cut markets |

The current Kalshi production API uses different (longer) tickers (KXFEDDECISION, KXUSNFP, KXECONSTATU3, KXU3); the historical Becker dataset captures the older shorter prefixes that existed through November 2025.

---

## 2. Data sources (locked)

### Primary historical data: Becker dataset

**Path:** `prediction-market-analysis/data/kalshi/{markets,trades}/*.parquet`
**Schema:** documented in `prediction-market-analysis/docs/SCHEMAS.md`
**Source:** `https://s3.jbecker.dev/data.tar.zst` (36 GB compressed snapshot Feb 5 2026)
**Coverage:** Kalshi trades through November 2025 (72.1 million rows)
**Why this source replaces live API:** Live Kalshi API only returns recently settled markets (KXCPI is post April 2026 rebrand, n_events <= 2; per v10A-1 revival probe). The Becker snapshot retains the older CPI / PAYROLLS / U3 / FEDDECISION ticker history that the live API has discarded.

### Time window (locked)

**Train + OOS combined:** 2024-10-01 (post sign flip per CLAUDE.md load-bearing fact 3) through 2025-11-01 (Becker snapshot end minus 1 month for finalization).
**OOS split point:** 2025-07-01 (rough 60/40 train/OOS split; CPI/PAYROLLS produce ~12 train events and ~5 OOS events per series; FOMC produces fewer).
**Why post Oct 2024 only:** Becker 2026 documents a maker-taker sign flip in October 2024 invalidating pre-flip patterns for current MM behavior. Including pre-flip data risks fitting a regime that no longer exists.

**Reserved alternative (only if main n_events < 40):** Extend the window back to 2022-10-01 explicitly acknowledging that pre-flip regime data is being mixed in. Document the regime control variable. This is the "REVIVE-PRE-FLIP-ONLY" branch of the verdict tree above.

### FRED API for macro ground truth

**Endpoint:** `https://api.stlouisfed.org/fred/series/observations`
**Key:** `FRED_API_KEY` in .env (operator added 2026-05-26)
**Series fetched:** FEDFUNDS, CPIAUCSL, PAYEMS, UNRATE (monthly observations).
**Use:** Economic context in the LLM filter prompt. NOT a predictive feature.

### LLM semantic filter

**Preferred model (free tier):** Gemini 2.5 Flash via `GEMINI_API_KEY` (1500 req/day; sufficient for at most 12 pair filter calls per run).
**Fallback:** DeepSeek V4 Flash via `DEEPSEEK_API_KEY` (5M signup tokens).
**Second fallback:** Groq Llama 3.1 70B via `GROQ_API_KEY`.
**Reserved for orchestrator and final critic only:** Anthropic models. (ANTHROPIC_API_KEY is NOT in .env; Claude Code runtime injects it for orchestrator use; standalone scripts cannot call Anthropic without explicit key.)
**Forbidden:** Including Kalshi prices in the LLM filter prompt. The filter judges economic plausibility only.

---

## 3. Probability time series construction

### Granularity

Daily VWAP per (event_ticker, day). One observation per event_ticker per day. The event_ticker (e.g. CPI-2025-04) groups multiple strikes belonging to the same release; we extract the probability of the at-the-money strike per day.

### At-the-money strike selection

For each event_ticker on each day, pick the strike whose realized outcome distance from the opening yes_price is minimum among same-event strikes (i.e. the strike whose probability of resolving YES is closest to 0.5 on the day it was first traded). Lock this choice once per event_ticker; do not re-select per day.

### Gap handling

If no trades occur for a given (event_ticker, day) cell, mark the cell as a forward-fill from prior day. If the gap is greater than 5 consecutive trading days, exclude the event from the Granger regression window. Do not impute or interpolate.

### Phantom prevention notes (F4)

The probability time series is the FEATURE that predicts the FOLLOWER series' probability. There is no within-market prediction vs stale mid comparison. The v7-B phantom mode does not apply here because:

(a) X's daily VWAP is the unit of analysis for the regression on Y's daily VWAP; the comparison is cross-market.
(b) The execution baseline at trade time is the live orderbook ask (per project rules), but that decision is made AFTER the Granger filter identifies a candidate pair, not as part of the Granger computation.
(c) Becker's historical data captures actual realized trades; the VWAP is a real price, not a synthetic estimate.

The phantom risk for V10-A is at the EXECUTION step, not at the SIGNAL step. The signal is a Granger F-test on historical VWAPs; the execution is a taker order at the current orderbook ask at the time the signal fires in OOS.

### Execution price source (revised)

For Becker-backed historical backtest, the execution price for Y at signal-fire time is the **next-trade yes_price after signal time** at the chosen strike. This is NOT the orderbook ask (orderbook history is unavailable in Becker). Instead, we use the actual realized trade fill price within a small window (up to 1 trading day) after signal. If no trade occurs in that window, the signal is shelved as "unexecutable" and counted in n but with NaN P&L (excluded from win-rate computation).

This is methodologically defensible because:
- Macro markets had non-trivial trade volume per Becker (KXCPI / PAYROLLS / U3 each have hundreds of thousands of trades through Nov 2025)
- Next-trade fill price approximates what a taker would have paid (the trade actually occurred at that price)
- This is DIFFERENT from the v7-B phantom because we are not using a STALE PRICE as the baseline; we are using the FIRST POST-SIGNAL trade as the realized fill price

Caveat: if MMs see our signal-direction trade and adjust quote, the price we trade at may differ from the historical post-signal trade. This is the residual adverse selection risk. Phase 3 critic must verify this approach.

---

## 4. Granger causality protocol

### Test specification (locked)

For each ordered pair (X, Y) with X != Y across the 4 Kim-mapped series:

```
Y_t = c + sum_{k=1}^{L} alpha_k Y_{t-k} + sum_{k=1}^{L} beta_k X_{t-k} + epsilon_t
```

Null: beta_1 = ... = beta_L = 0. F-test, OLS residuals.

Pre-registered lag set L in {1, 3, 5, 7, 14} trading days. (Update vs original draft: the original used {1, 3, 5} but smoke test 2026-05-27 revealed Gemini Flash judges short macro transmission lags as economically implausible. Kim et al. reportedly tested holding horizons {1, 3, 5, 7, 10, 14, 21}; we mirror the lower half of Kim's range here. Pre-registered before any backtest pull.) All five lags run; the final reported signal per pair is the lag with the lowest p-value.

### Multiple testing correction

Per the verdict tree in Section 0:

- If n_events >= 60: Bonferroni at alpha = 0.05 / (12 ordered pairs x 5 lags) = 0.05 / 60 = 0.000833.
- If 40 <= n_events < 60: Holm-Bonferroni step-down on the same 60 hypotheses, alpha = 0.05.
- If n_events < 40: no multiple-test correction reported; the test is exploratory only and the V10-A kill is fired before LLM filter even runs.

### Pre-test: stationarity

ADF test on each series' VWAP. If p > 0.05 for raw series, take first differences. Apply Granger on the differenced series in that case. Document which series required differencing.

### Implementation

`statsmodels.tsa.stattools.grangercausalitytests` Python. Standalone script in `scripts/v10a/run_granger.py`. Uses Becker venv (not .venv-kronos).

---

## 5. LLM semantic filter protocol

### Inputs and prompt template (locked)

For each pair surviving Granger significance:

```
You are an economic reasoning assistant. Evaluate whether the following
proposed statistical relationship is economically plausible.

Proposed lead-lag relationship:
  Leader: {X_label} (current FRED value: {X_fred})
  Follower: {Y_label} (current FRED value: {Y_fred})
  Lag: {L} trading days
  Statistical evidence: Granger F = {F:.2f}, p = {p:.4f}

Question: Is it economically plausible that changes in {X_label} causally
influence {Y_label} with a {L}-day lead? Answer YES or NO on the first line,
then provide 1 to 2 sentences of economic reasoning. Do not reference
prediction market prices, Kalshi, Polymarket, betting odds, or any market
sentiment data in your response.
```

### Anti-anchoring constraints

- No Kalshi prices in prompt (forbids the LLM from validating a trade because the market is moving).
- No Tavily / web search retrieval in the filter step (different from v10-B which uses retrieval; here the LLM has FRED ground truth and basic series labels only).
- The LLM's training cutoff varies by vendor; Gemini 2.5 Flash cutoff is approximately late 2025. We accept that the LLM has seen pre-event data; the test is whether the LLM CHOOSES to filter, not whether it has parametric knowledge of outcomes. The filter is a binary YES/NO on plausibility, not a prediction.

### Failure mode for the filter

If the LLM responds with anything other than YES/NO on the first line, retry once with a clarification prompt. If second response is still malformed, the pair is excluded from the strategy (treated as filter NO).

### Critical Anchor Audit (post hoc)

After running the filter on all pairs:

Compute Pearson correlation between (a) the LLM's binary YES/NO and (b) the sign of the historical mean P&L of executing that pair in the training window. If r > 0.50, the LLM is anchoring on past performance (a leakage failure). If r is near zero, the LLM is genuinely judging plausibility.

This is a process check: if anchoring is detected, the analysis cannot proceed and we close the round with the anchoring failure documented. No salvage.

---

## 6. Trading strategy specification

### Signal definition

On day t, for each Granger and LLM filter passing pair (X, Y) at chosen lag L:

- Compute X's daily VWAP change in window [t - L, t]: delta_X = X_t - X_{t - L}
- If delta_X >= 0.05 (5 percentage points up): BUY YES on Y's at-the-money strike at the current orderbook ask
- If delta_X <= -0.05 (5 percentage points down): BUY NO on Y's at-the-money strike at the current orderbook ask
- If abs(delta_X) < 0.05: no trade

### Position sizing

$1 notional per trade. No Kelly, no leverage. Consistent with v6 / v9 backtest conventions.

### Fee model (load bearing)

Kalshi fees for binary markets follow a fee schedule that depends on price band. Per Kalshi public documentation:

- Standard markets: `fee = ceil(0.07 * contracts * price_yes * (1 - price_yes))`
- This is bell-shaped: max fee at price 0.50 ($0.0175 per contract on a $0.50 contract), much smaller near price 0 or 1.

For an at-the-money $0.50 trade with quantity = 100 contracts ($50 notional):

```
fee = ceil(0.07 * 100 * 0.50 * 0.50) = ceil(1.75) = $1.75
```

That is **3.5%** of the $50 trade notional ($1.75 / $50). On a winning $0.50 ATM trade, gross win = $0.50 per contract = $50; fee = $1.75; net = $48.25. On a losing trade, the contract goes to $0; loss = $50; fee = $1.75; net = -$51.75 (you pay the fee on the losing side too).

### Fee-aware breakeven (sharper than v1 lock)

Let p = win probability, f = fee per trade (in dollars), C = $50 trade notional, w = gross win on success = $50.

EV = p * (w - f) - (1 - p) * (C + f)
   = p * (50 - 1.75) - (1 - p) * (50 + 1.75)
   = p * 48.25 - (1 - p) * 51.75
   = p * (48.25 + 51.75) - 51.75
   = 100 p - 51.75

EV = 0 when p = 51.75 / 100 = **0.5175** -> breakeven win rate is approximately **51.75%**.

Kim et al. report 54.5% win rate (post LLM filter) and 51.4% pre filter. The pre filter rate is BELOW breakeven; the post filter rate is +2.75pp above breakeven. This is a much tighter margin than commonly cited.

**Pre-registered confidence interval gate (G1):** The bootstrap 95% CI on win rate in the OOS test split must strictly exclude the 51.75% breakeven, not merely exclude 50%.

At Kim's reported 54.5%:
- For CI half-width 1.4% (would exclude 51.75%) we need n at least about 1400 trades (binomial standard error analysis: sqrt(0.55 * 0.45 / 1400) * 1.96 = 0.026; so CI half-width 2.6% at n=1400; to get half-width 1.4% need n > 4000).

This implies: with our likely OOS n in the range of 5 to 30 trades (one signal per release event, ~16 events in OOS window, perhaps 0.5x to 1x trade per event after filter), Kim's reported 2.75pp net margin is NOT detectable. The CI on a 54.5% win rate at n=20 is approximately [33%, 73%], easily including breakeven.

This is the methodological CONFIRMED CONCERN: even if Kim's edge is REAL at large n, our OOS sample size will not be able to detect it with sufficient precision to clear gate G1.

**Mitigation:** If n_events >= 60 in the inventory result, we expand the trade rule to fire on more strikes per event (multiple strikes per event_ticker, not just ATM). This multiplies n by 3 to 8 (number of strikes per macro release event). If 60 events generate 200 to 400 individual strike-level trades, the binomial CI tightens enough to potentially clear breakeven. This is a pre-registered alternative.

### Walk-forward CV with purge

Purge buffer = max Granger lag = 5 trading days.
Embargo = 1 release event per series (do not let a training event's resolution leak into the OOS window's signal computation).

---

## 7. Gates (pre-registered, locked)

| Gate | Description | Threshold |
|---|---|---|
| G1 (primary, fee aware) | Bootstrap 95% CI of OOS win rate strictly excludes 0.5175 breakeven | CI lower bound > 0.5175 |
| G2 (mean P&L) | Bootstrap 95% CI of OOS mean net P&L per trade strictly excludes zero | CI lower bound > 0 dollars per trade |
| G3 (LOCO robust) | Both G1 and G2 hold under leave-one-series-out (4 LOCO subsets) | All 4 subsets clear |
| G4 (sample floor) | OOS trade count after Granger + LLM filter and ATM-strike rule | n_OOS_trades >= 30 |
| G5 (anchoring) | Pearson r between LLM filter decision and historical mean P&L sign | abs(r) < 0.50 |
| G6 (no third bite) | No post hoc rule adjustment after observing OOS results | Documented in this lock |

**Verdict tree:**
- PASS: G1 + G2 + G3 + G4 + G5 all clear.
- PARTIAL: G2 + G4 + G5 clear, G1 marginal (CI excludes zero but includes breakeven), G3 mixed.
- NULL: G1 fails OR G2 fails OR G4 fails.
- PHANTOM-RISK: G5 fails (LLM is anchoring on historical performance; the filter has leaked).

---

## 8. Failure modes addressed (F1 to F10)

**F1 (data access):** REFUTED for V10-A v2. Becker dataset provides historical trades through Nov 2025. Live API regression that killed v1 A2 lock no longer applies.

**F2 (sample size):** OPEN. Verdict depends on inventory result. n_events floor at 40 is hard. If less, kill.

**F3 (domain coverage):** Macro is a single domain (Finance / Economic Indicators). No domain mismatch comparable to v3 (sports overlap zero). Diercks 2026 confirms macro markets are tightly priced by institutions, so this is a "macro vs macro" comparison.

**F4 (phantom from stale price proxy):** REFUTED for the SIGNAL step. Cross-market lead-lag uses X's VWAP to predict Y's VWAP; no stale-mid comparison. The EXECUTION step (taker order at orderbook ask) is at live data and not present in backtest (since this is paper trade simulation). For the backtest itself, the OOS P&L is computed at the realized resolution outcome of Y at close_time, which is ground truth.

**F5 (methodological leak):** Walk-forward CV with 5-day purge buffer and per-event embargo enforced. ATM strike selection done once per event_ticker at open time, frozen for all subsequent days.

**F6 (single feature artifact):** Granger F-test summarizes the full lag block; no single feature dominates. LLM filter could in principle anchor on one variable, which gate G5 detects.

**F7 (LLM topic weakness):** Macro is NOT the documented LLM weak topic; sports is. The LLM here judges economic plausibility (not outcome prediction); F7 is structurally inapplicable.

**F8 (gate regime mismatch):** Gate G1 derived from Kalshi fee structure on macro markets directly, NOT borrowed from a different benchmark. Regime matched.

**F9 (seasonality):** Macro releases are year round at monthly cadence. No seasonal coverage collapse.

**F10 (LOCO fragility):** G3 requires all 4 LOCO subsets to clear. Hard requirement.

---

## 9. What we will NOT do (anti third-bite)

- No post hoc lag selection. Lags {1, 3, 5, 7, 14} are pre-registered (revised once on 2026-05-27 from {1, 3, 5} based on Gemini smoke test feedback that short-lag macro transmission is judged economically implausible; pre-data revision, not post-hoc).
- No post hoc strike selection beyond ATM and the "expand to multiple strikes" pre-registered alternative in Section 6.
- No post hoc filter prompt revision. The prompt template is locked.
- No silently dropping events that look like outliers.
- No live capital deployment regardless of result. Paper trade only.
- No changing the train/OOS split point after observing data.

If gates fail, V10-A NULL or PARTIAL. Operator authorizes any pivot.

---

## 10. Pre flight smoke tests

Before Phase 2 starts, all of these must pass:

1. Becker dataset extracted and queryable (markets and trades parquets exist).
2. v10A-1 inventory reports n_events_post_flip >= 40 (else KILL).
3. FRED API call returns valid data for FEDFUNDS, CPIAUCSL, PAYEMS, UNRATE.
4. Gemini API key works and the filter prompt returns parseable YES/NO on a known-good pair.
5. statsmodels Granger test runs on a synthetic AR(1) series and detects causality at the correct lag.

If any smoke test fails, do not start Phase 2. Document the failure in `research/v10a/00-smoke-test-report.md`.

---

## 11. Bearish prior from Diercks 2026

Diercks, Katz, Wright FEDS 2026-010 documents Kalshi macro markets as efficient against Bloomberg consensus and FRBNY SME. Susquehanna actively makes these markets. This is a STRONG bearish prior for retail edge.

**Impact on V10-A v2:**
- Diercks does NOT contradict Kim's claim (Kim is cross market lead lag within Kalshi, not Kalshi vs fundamentals).
- However, if Susquehanna makes both X and Y markets, they likely arb the lead-lag relationship within seconds. Retail at 15 min cadence is at the wrong frequency to catch this.
- The remaining Kim signal must be in DAILY rather than INTRADAY lead-lag, which is what daily VWAP captures.
- Realistic prior: even if Kim's claim is real at the trade level, the daily VWAP version may be too coarse to detect signal. We may NULL because we are at the wrong sampling frequency relative to the actual mechanism.

This is a known limitation. Operator authorized the attempt anyway; we proceed.

---

## 12. Spend cap

Total V10-A LLM spend cap: $8 (per orchestrator brief).

Estimated:
- Phase 1 inventory (this step): $0 (no LLM, just duckdb)
- Phase 1 lit scout (v10A-2 agent): ~$1
- Methodology critic agent: ~$1
- Phase 2 LLM filter (12 pair calls on Gemini Flash free tier): $0
- Phase 2 LLM filter on Haiku fallback (if needed): ~$0.50
- Phase 3 critic agent: ~$2
- Final verdict orchestrator pass: ~$1

Total estimated: $5.50; under the $8 cap with $2.50 buffer.

Stop trigger: at $7 accumulated spend, halt and report.

---

## 13. What this lock does NOT cover (deferred)

- Polymarket cross venue lead-lag (different angle; v10A-3 pivot menu)
- Hawkes process alternatives to Granger (different methodology; not pre-registered)
- Sentiment-driven trade flow (different methodology; not pre-registered)
- Live trading. Not in scope.

If V10-A NULLs and the operator wants to pivot to one of the above, that is a separate round.

---

*Anti em-dash verification: this document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout. All separations use double hyphens or commas.*
