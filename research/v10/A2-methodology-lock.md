# V10-A Phase 1.5 Methodology Lock

**Date:** 2026-05-26
**Author:** Agent v10-A1
**Status:** LOCKED (pre-data-pull). See Section 10 for KILL verdict.
**Scope:** Kim et al. arXiv 2602.07048 replication on Kalshi Economics markets (V10-A)

**NOTICE:** The Phase 1 data probe (`A1-data-probe.md`) returned a KILLER verdict. This methodology lock is written as if the data were available, to make the methodology critic's job concrete and to document what was attempted. Section 10 records the pre-backtest kill. No backtest will be executed.

---

## 1. Replication Target

### Source

Kim, Sumin; Kim, Minjae; Kwon, Jihoon; Kim, Yoon; Kagan, Nicole; Lee, Joo Won; Levy, Oscar; Lopez-Lira, Alejandro; Lee, Yongjae; Choi, Chanyeol. "LLM as a Risk Manager: LLM Semantic Filtering for Lead-Lag Trading in Prediction Markets." arXiv:2602.07048v2. February 2026.

The paper is NOT directly WebFetched in this session (LLM budget constraint; the v10-S2 summary in `02b-literature-delta.md` Paper 4, lines 200-280, is the primary source). The replication methodology is reconstructed from the Paper 4 summary plus economic reasoning about the methodology. Deviations from the paper's exact methodology are noted where forced by data constraints.

### Summary of Kim et al. methodology (inferred from 02b-literature-delta.md lines 200-280)

A two-stage approach:

1. **Stage 1 (Granger causality):** Kalshi Economics market probability time series are constructed from historical trade data for KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE. For each directed pair (X leads Y), a Granger causality F-test is run at multiple lags. Statistically significant pairs are retained for Stage 2.

2. **Stage 2 (LLM semantic filter):** An LLM evaluates whether "plausible economic transmission mechanisms" support each proposed causal direction. Pairs that are Granger-significant but LLM-implausible are filtered out. The taker strategy follows the surviving pairs: when market X moves, take a position in market Y in the predicted direction.

Reported result: win rate 51.4% to 54.5% (+3.1pp absolute); average loss magnitude $649 to $347 (-46%).

**Known deviations from paper if forced:**

- Paper series KXFEDFUNDS, KXNFP, KXUNRATE do not exist in the current Kalshi API. We would use KXECONSTATU3 (unemployment), KXUSNFP (payrolls), KXFEDDECISION or KXEFFR (fed funds rate). This is a deviation in series naming but not in economic content.
- Paper likely used pre-2026 historical data (submitted February 2026); our window starts October 2024. Window is shorter.
- Paper's lag specification is not published in the literature summary; we default to lags 1, 3, 5 days and report all results.
- Paper may have used intraday probability time series; we use last-trade print at daily close horizon per available data.

---

## 2. Data Sources Locked

### Kalshi historical trade data

**Source:** Kalshi production API `/markets/{ticker}/trades` or `/series/{ticker}/trades`
**Key:** READ-scope key in `.env` (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH)
**Series:** KXCPI, KXECONSTATU3, KXUSNFP, KXPAYROLLS (mapping to Kim's KXCPI, KXUNRATE, KXNFP, KXFEDFUNDS respectively)
**Time period:** 2024-10-01 onward ONLY (per CLAUDE.md four load-bearing facts: the 2024 sign flip). Pre-October-2024 data is excluded.
**Unit:** Trade-print yes_price per market per timestamp. Use last trade price before each hourly interval close as the probability estimate. If no trade in a 24h window, interpolate linearly from the prior known price. Mark interpolated observations as such; do not count them as independent Granger observations.

**Status as of 2026-05-26:** DATA UNAVAILABLE. `/markets/{ticker}/trades` returns HTTP 404 for all settled markets. See `A1-data-probe.md` Section 1.

### FRED API for macro ground truth

**Source:** `https://api.stlouisfed.org/fred/series/observations`
**Key:** FRED_API_KEY (NOT in .env as of 2026-05-26; requires operator to add)
**Series:**
- FEDFUNDS (effective federal funds rate, monthly)
- CPIAUCSL (CPI all urban consumers, monthly, seasonally adjusted)
- PAYEMS (total nonfarm payrolls, monthly)
- UNRATE (civilian unemployment rate, monthly)

**Use:** Ground-truth values for the FRED macro series corresponding to each Kalshi Economics market. Used in the LLM filter prompt as economic context, not as a predictive feature.

### LLM API for semantic filter

**Model:** Haiku 4.5 (currently available via ANTHROPIC_API_KEY in Claude Code session). If GEMINI_API_KEY or DEEPSEEK_API_KEY become available (per operator action list in `04-phase0-synthesis.md`), use Gemini 2.5 Flash as first preference (cheaper, free tier).
**Role:** Semantic filter only. The LLM is NOT predicting outcomes. It is evaluating whether a proposed causal direction has a plausible economic transmission mechanism.

---

## 3. Granger Causality Protocol

### Time series construction

For each of the 4 target series, construct a daily probability time series:
- **Value:** last trade yes_price (in cents) / 100, representing the probability that a given strike settles YES
- **Granularity:** one observation per calendar day during the lifetime of the most liquid strike (the at-the-money strike, defined as the strike where the opening yes_price is closest to 0.50)
- **Aggregation:** if multiple trades occur in a day, use the volume-weighted average price (VWAP) for that day
- **Gaps:** if no trade occurs for > 5 consecutive calendar days, mark the period as a gap and exclude from the Granger regression window
- **v7-B phantom prevention:** The probability time series is the FEATURE (it predicts Y), not the baseline for comparison. There is no phantom risk here because we are not comparing our model's forecast to a stale mid. We are computing whether X's probability series Granger-causes Y's probability series. The unit of analysis is cross-market lead-lag, not within-market prediction vs. stale mid.

### Lag specification

Pre-registered lags: {1, 3, 5} trading days. All three lags are run and reported. The final trading signal uses the lag with the lowest Granger F-test p-value among statistically significant results.

**Rationale:** Kim et al. do not publish their lag specification in the literature summary. Monthly macro releases are 20-25 trading days apart. Cross-market spillover from CPI to FOMC expectations likely occurs within 1-5 days. Lags beyond 5 days are unlikely to yield stable Granger results given the 19-event sample per series.

### Statistical test

**Test:** Bivariate Granger causality F-test using OLS regression:
```
Y_t = c + sum_{k=1}^{L} alpha_k * Y_{t-k} + sum_{k=1}^{L} beta_k * X_{t-k} + epsilon_t
```
F-test on H0: beta_1 = beta_2 = ... = beta_L = 0.

**Significance threshold:** alpha = 0.05 raw. Bonferroni-corrected threshold for 12 directed pairs: alpha_corrected = 0.05 / 12 = 0.0042. Report both raw and Bonferroni p-values. A pair is "statistically significant" only if it passes Bonferroni.

**Implementation:** `statsmodels.tsa.stattools.grangercausalitytests` (Python, statsmodels library). Stationarity check: ADF test on each series before Granger; if non-stationary, take first differences.

**Directed pairs to test:** All 12 directed pairs from 4 series:
- KXCPI leads KXECONSTATU3
- KXCPI leads KXUSNFP
- KXCPI leads KXFEDDECISION
- KXECONSTATU3 leads KXCPI
- KXECONSTATU3 leads KXUSNFP
- KXECONSTATU3 leads KXFEDDECISION
- KXUSNFP leads KXCPI
- KXUSNFP leads KXECONSTATU3
- KXUSNFP leads KXFEDDECISION
- KXFEDDECISION leads KXCPI
- KXFEDDECISION leads KXECONSTATU3
- KXFEDDECISION leads KXUSNFP

---

## 4. LLM Semantic Filter Protocol

### Inputs to the LLM filter

For each Granger-significant pair (post Bonferroni correction):

1. **Pair description:** "Market X (description) Granger-causes Market Y (description) at lag L days, Granger F-stat = {F}, p-value = {p}"
2. **Economic context (FRED ground truth):** "Current {X description}: {FRED value}. Current {Y description}: {FRED value}. Trend over last 3 months: {up/down/flat}."
3. **The filter question:** "Is the proposed causal direction (X leads Y, lag L) economically plausible? Respond YES or NO, then provide a 1-2 sentence economic reasoning."

**Critical constraint: NO Kalshi prices in the filter prompt.** The LLM must reason from macroeconomic fundamentals, not from market prices. Including Kalshi mid prices in the prompt risks market-anchoring (the LLM validates the trade because the market is moving, not because the economics are sound). This is the anti-market-anchoring rule derived from the v9 lesson.

### Pre-registered prompt template

```
You are an economic reasoning assistant. Evaluate whether the following 
proposed statistical relationship is economically plausible.

Proposed lead-lag relationship:
  Leader: {X_description} (current FRED value: {X_fred_value})
  Follower: {Y_description} (current FRED value: {Y_fred_value})
  Lag: {L} trading days
  Statistical evidence: Granger F-stat = {F_stat:.2f}, p-value = {p_value:.4f}

Question: Is it economically plausible that changes in {X_description} 
causally influence {Y_description} with a {L}-day lead?

Respond with YES or NO on the first line, then provide 1-2 sentences 
of economic reasoning. Do not reference prediction market prices or 
betting odds in your response.
```

### Model selection

- **First preference:** Gemini 2.5 Flash (GEMINI_API_KEY) -- free tier, 1,500 req/day
- **Second preference:** Haiku 4.5 (ANTHROPIC_API_KEY) -- $0.80/$4.00 per MTok; ~$0.02 for 12-pair filter
- **Third preference:** DeepSeek V4 Flash (DEEPSEEK_API_KEY) -- free tier signup
- **Opus 4.7 reserved for orchestrator and final critic only**

### Filter decision rule

A Granger-significant pair passes the LLM filter if and only if the LLM responds "YES" to the plausibility question. A "NO" response removes the pair from the trading strategy. No intermediate scoring; binary filter only. This matches the Kim et al. design described as "filtering out economically implausible directions."

Pre-registered: any Granger-significant pair NOT passing the LLM filter is removed. The LLM filter cannot ADD pairs that failed Granger significance.

---

## 5. Trading Strategy Specification

### Signal definition

On the day of release event E for series Y, if series X issued a significant probability move at lag L trading days ago (move defined as > 5 percentage point change in X's at-the-money probability in a 24h window), and the pair (X leads Y) passed both Granger significance and LLM filter, then:
- If X moved UP: buy YES on Y's at-the-money strike (expect Y to move up)
- If X moved DOWN: buy NO on Y's at-the-money strike (expect Y to move down)

### Position sizing

Pre-registered: **$1 per trade** for backtest simulation (1 cent minimum contract = $0.01 actual; the $1 represents the notional position for P&L calculation). No Kelly, no leverage, no scaling. This is consistent with v6/v9 backtest conventions.

### Fee model

Kalshi fees for Economics markets (taker): approximately 2-7% per trade depending on price band. For a YES contract at $0.50 (at-the-money): fee is approximately $0.05 per $1 contract (5% of gross).

### Fee-aware win rate analysis

Kim et al. report win rate 51.4% to 54.5% (+3.1pp absolute), average loss magnitude $649 to $347. The paper does NOT publish net-of-fee P&L explicitly.

**Pre-registered breakeven calculation:**

Expected P&L per trade = win_rate * (1 - fee_winner) - (1 - win_rate) * (1 + fee_loser)

At a YES taker price of 0.50 (at-the-money):
- Win: collect $0.95 on a $0.50 bet = +$0.45 after fee
- Lose: lose $0.50 = -$0.50

Breakeven win rate: P&L = 0 requires win_rate * 0.45 = (1 - win_rate) * 0.50

win_rate_breakeven = 0.50 / (0.45 + 0.50) = 0.50 / 0.95 = **52.6%**

Kim et al.'s reported 54.5% win rate (post-LLM-filter) BARELY exceeds the 52.6% breakeven threshold at an at-the-money price of 0.50. The margin is 54.5% - 52.6% = +1.9pp net-of-fee. Given that:
(a) The paper does not publish confidence intervals on the win rate
(b) The paper's sample period and 54.5% are both unverified
(c) Kalshi fee rates vary by price band (lower fees near 0 or 1, higher near 0.5)
(d) Macro markets are efficiently priced (Diercks 2026)

The fee-aware pre-registered gate must explicitly require the bootstrap CI on win rate to exclude the breakeven threshold (52.6%), not merely exclude 50%. A 54.5% win rate at the sample sizes available in our OOS window (n ~16 post-Feb-2026) has a 95% CI of approximately +/- 24 percentage points (Wilson interval, n=16). This CI easily includes 50% and 52.6%; the gate is effectively unfirable at n=16.

This is a SECOND confirming kill signal on the methodology, independent of the data access kill.

---

## 6. Pre-Registered Gate Criteria

**Primary gate:**

G1: Mean P&L per trade, net of Kalshi taker fees, on OOS test split (post-2026-02-01), bootstrap 95% CI (10,000 resamples) strictly excludes zero AND strictly excludes the breakeven threshold (0.526 win rate equivalent, which is +0.00pp EV at the assumed fee model).

**Secondary gate:**

G2: Win rate in OOS test split, bootstrap 95% CI, strictly exceeds 0.526 (the fee-adjusted breakeven). This is a MORE STRINGENT gate than the Kim paper's stated 54.5%, because 54.5% is barely above breakeven for our at-the-money price assumption.

**Robustness gate:**

G3: Gate G1 holds under leave-one-series-out (LOCO). Remove each of 4 series in turn, recompute G1 on the remaining 3 series. All 4 LOCO subsets must independently pass G1.

**Sample size floor:**

G4: n >= 40 qualifying OOS trades. Below this floor, no verdict is issued; the analysis is marked INSUFFICIENT SAMPLE. At monthly frequency with 4 series and a 4-month OOS window, the expected OOS n is approximately 16 release events. This gate will mechanically FAIL at our current data access level.

**Time-series CV requirement:**

G5: Walk-forward CV with purge buffer = max Granger lag (5 trading days). Embargo boundary at each monthly event. No shuffle of time-series data.

---

## 7. Failure Modes Addressed

Per the F1-F10 taxonomy in `03-methodology-meta.md`:

**F1 (data access):** Kalshi historical trades for Economics series were expected to be accessible via `/markets/{ticker}/trades`. As of 2026-05-26, the endpoint returns HTTP 404 for ALL settled markets platform-wide. The data probe confirms F1 is a HARD KILL. The methodology is designed around the assumption that F1 is satisfied; it is not.

**F2 (sample size):** Monthly release frequency limits n to approximately 19 events per series in the post-Oct-2024 window, below the ~50 needed for reliable Granger tests. The OOS window post-Feb-2026 yields approximately 16 events total. G4 (n >= 40 floor) will not be reachable at monthly frequency. This is a SECOND CONFIRMING KILL, independent of F1.

**F4 (phantom prevention):** The cross-market lead-lag design does NOT replicate the v7-B phantom. The probability time series of X is used to predict the probability time series of Y. This is a cross-market feature-target relationship, not a within-market prediction vs. stale mid. The v7-B phantom occurred because `naive_p_yes` outperformed the stale trade-print mid but not the live orderbook ASK. In V10-A, there is no comparison to a stale mid; we are computing whether X's probability Granger-causes Y's probability. Phantom risk is absent from this design.

**F5 (temporal leakage):** Walk-forward CV with 5-day purge buffer (= max Granger lag) and monthly event embargo, per G5 above. No shuffle.

**F7 (LLM topic weakness):** Macro economics is NOT the weakest LLM domain (sports is weakest per Janna Lu 2025 analysis cited in 04-phase0-synthesis.md). However, Diercks 2026 documents that macro markets are efficiently priced by institutions (Susquehanna). The LLM filter is constrained to semantic plausibility assessment, not outcome prediction, which reduces F7 risk (the LLM does not need to be better than the market at macro; it only needs to evaluate whether a transmission mechanism is economically coherent).

**F8 (gate-regime mismatch):** Kim et al.'s reported lift (+3.1pp win rate) was measured on Kalshi Economics markets (specifically the four series in question). Gate G2 (win rate > 0.526 post-fee breakeven) is regime-matched: it is derived from the Kalshi fee structure on Economics taker trades, not borrowed from a different benchmark or different price regime. This correctly avoids the v9 failure mode (AIA +0.014 was on uncertain markets; v1 is in confident-favorite regime).

**F9 (seasonality):** Economics markets release year-round. CPI, NFP, and unemployment are monthly. FOMC meets 8 times per year. No seasonal concentration risk comparable to v9's sports universe (which had zero settled markets in winter/spring 2026).

**F10 (LOCO fragility):** Gate G3 requires all 4 LOCO subsets to pass independently. With 4 series and n ~16 total OOS events, each LOCO subset has n ~12. This is far below the statistical floor for robust inference. LOCO is formally pre-registered but practically unfirable at the available sample size.

---

## 8. What We Will NOT Do

- No post-hoc gate adjustment. If G1/G2/G3/G4 fail, the strategy ends. No "this criterion almost passed" rationalization per CLAUDE.md methodology discipline.
- No re-purposing the LLM filter to predict outcomes. The LLM answers one binary plausibility question per pair and is not used for any other prediction task.
- No live capital deployment. The backtest is paper-trade simulation only. Any live deployment requires a separate operator authorization decision and the full five-gate pass.
- No third bite if gate fails. Per CLAUDE.md Section "Methodology discipline": if a strategy fails its gate, the strategy ends. Operator must authorize any pivot.
- No Granger tests on markets outside the pre-registered four series. Adding markets post-hoc is p-hacking.
- No tuning the Granger lag after observing results. Lags {1, 3, 5} are pre-registered. If a different lag had better results, it is not the tested hypothesis.
- No excluding inconvenient release events after observing their outcomes.

---

## 9. Smoke Test Plan

If the data probe were to return accessible data (or if operator obtains the Kim et al. dataset directly), the following smoke tests gate Phase 2 entry:

**Smoke Test 1: Kalshi trade data fetch**
- Goal: Confirm that `/markets/{ticker}/trades` returns > 0 trades for at least one Economics series
- Pass condition: At least one settled KXCPI/KXECONSTATU3/KXUSNFP market returns n > 5 trades with non-zero yes_price values
- Current status: FAILING. See `A1-data-probe.md`.

**Smoke Test 2: FRED data fetch**
- Goal: Confirm FRED API returns monthly FEDFUNDS/CPIAUCSL/PAYEMS/UNRATE series
- Pass condition: HTTP 200, at least 24 months of observations returned for each series
- Prerequisite: FRED_API_KEY must be added to `.env` (currently absent)
- Implementation:
```python
import requests
r = requests.get(
    'https://api.stlouisfed.org/fred/series/observations',
    params={'series_id': 'CPIAUCSL', 'api_key': FRED_API_KEY,
            'file_type': 'json', 'observation_start': '2024-01-01'}
)
assert r.status_code == 200
obs = r.json()['observations']
assert len(obs) >= 12
print(f'FRED OK: {len(obs)} observations for CPIAUCSL')
```

**Smoke Test 3: Haiku LLM filter call**
- Goal: Confirm the semantic filter prompt returns a parseable YES/NO response
- Pass condition: API call to Haiku 4.5 with the pre-registered prompt template returns "YES" or "NO" on the first line
- Implementation: Call with a known-plausible pair (CPI leads Fed funds) and verify "YES"; call with a known-implausible direction (Fed funds leads CPI backwards) and verify "NO" is at least plausible.

**Smoke Test 4: One Granger pair hand-coded**
- Goal: Confirm the statsmodels Granger implementation runs on synthetic data before touching live series
- Pass condition: `statsmodels.tsa.stattools.grangercausalitytests` runs without error on 20 synthetic data points, returns p-values and F-stats in expected format
- Implementation: Generate AR(1) synthetic series with known causality, verify the test detects it at correct lag

---

## 10. Pre-Backtest Kill Verdict

**Based on the Phase 1 data probe (`A1-data-probe.md`), V10-A is KILLED before any backtest data is pulled.**

The kill is fired by two independent mechanisms, either of which would suffice:

**Kill 1 (data layer):** Kalshi historical trades are unavailable. The API endpoint `/markets/{ticker}/trades` returns HTTP 404 for all settled markets platform-wide. Without a historical trade feed, the probability time series cannot be constructed, and Granger causality cannot be computed.

**Kill 2 (sample size):** Even if trade data were available, the available post-Oct-2024 OOS window contains approximately 16 release events. Gate G4 requires n >= 40 OOS trades, and Gate G3 requires LOCO robustness. Both are structurally unachievable at monthly release frequency with the current data window. This is a SECOND confirming kill independent of the data access issue.

**What this kill means for v10:**

V10-A as currently specified (direct Kim et al. replication on current Kalshi API) is NOT feasible. The evidence base for V10-A (the Kim paper's positive results) remains valid in principle, but is inoperable given:
1. The Kalshi API no longer exposes historical trade data for settled markets
2. The series the paper used (KXFEDFUNDS, KXNFP, KXUNRATE) do not exist in the current API
3. The current Economics series have zero historical trading volume in the API

**Possible futures for the V10-A hypothesis:**

The lead-lag hypothesis itself is not killed by this probe; it is the data infrastructure that is killed. Three paths could revive it:

1. **Direct dataset request to Kim et al.:** Email the authors requesting their Kalshi Economics trade dataset. Free, but uncertain timeline and not under our control.

2. **Prospective data collection:** Build a forward-recorder for Economics series (same infrastructure pattern as v8-A) targeting KXCPI, KXUSNFP, KXECONSTATU3, KXFEDDECISION. Collect 12-18 months of release events (approximately 48-72 events at monthly frequency) before running Granger tests. Timeline: 1-1.5 years. Beyond v10 scope.

3. **Alternative platform:** The Polymarket lead-lag paper (Ng/Peng/Tao/Zhou 2026, lit index) covers cross-venue lead-lag on Polymarket Economics markets. Polymarket has a CLOB with more accessible historical data. However, this is no longer V10-A (Kalshi replication) and introduces different fee/liquidity dynamics.

**Immediate action for operator:** V10-A closes NULL at data layer. Redirect v10 effort to V10-B (multi-LLM regime-matched ensemble on uncertain Kalshi sports props) per the Phase 0 synthesis recommendation. V10-B uses a different market universe (sports props in 0.30-0.70 band) that does not require historical trade reconstruction and can operate prospectively on the current API.

---

## Appendix: Diercks 2026 Bearish Context for V10-A

Diercks, Katz, Wright 2026 (FEDS Working Paper 2026-010) documents that Kalshi macro markets are as accurate as Bloomberg consensus, and for headline CPI, Kalshi statistically BEATS Bloomberg consensus. Susquehanna actively makes these markets. This finding implies:

1. The macro markets are efficiently priced by sophisticated institutional participants.
2. There is limited room for retail edge from first-principles macro prediction.
3. The Kim et al. lead-lag result is NOT about beating the market on macro forecasts; it is about identifying when one market updates faster than another. This is an arbitrage-style efficiency argument (one market leads another in incorporating the same information), not a fundamental-forecasting argument.

Diercks 2026 does NOT contradict the Kim et al. design, as the literature delta (02b, lines 237-239) notes: "The lead-lag relationship between two Kalshi markets does not require either market to be individually mispriced relative to fundamentals." However, Diercks 2026 does increase the prior that any detectable lead-lag in macro markets is small and may not survive Kalshi's fee structure. The fee-aware analysis in Section 5 above confirms this concern: the margin between Kim's reported 54.5% win rate and the 52.6% breakeven is razor-thin (+1.9pp), and our methodology critic should flag this as a fragile result.
