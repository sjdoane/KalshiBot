# V10-A Methodology Lock v2: Adversarial Critique

**Date:** 2026-05-27
**Author:** Phase 1.5 adversarial methodology critic (V10-A v2 pass)
**Target document:** `research/v10a/A2-methodology-lock-v2.md`
**Predecessor critic:** `research/v10/05-phase1.5-critic.md` (v1 lock critic)
**Budget consumed:** approximately $0.40 LLM (reads, 2 WebSearch calls, no generation-heavy work)
**Pre-reads completed:** A2-methodology-lock-v2 (v2), A2-methodology-lock (v1), 03-methodology-meta (F1-F10), 05-phase1.5-critic (predecessor), 06-v10a-revival-probe (n=7 result), diercks-katz-wright (bearish counterpoint), 02b-literature-delta paper 4 (Kim), CLAUDE.md.

---

## Executive summary

The v2 lock is a substantial improvement over v1: it correctly diagnoses the Variant-A endpoint bug, switches to the Becker historical dataset which has multi-year coverage, and tightens the fee-aware breakeven analysis to 51.75% (sharper than v1's 52.6%). However, three killer-class findings remain. The most damaging is a load-bearing data-schema gap that re-creates the v7-B phantom failure mode in a new costume: the Becker TRADES table contains no orderbook bid or ask at trade time, so "BUY YES at the orderbook ask" cannot be priced from this dataset. The v2 lock claims F4 is refuted on the signal step but never audits whether the execution step is constructible at all. It is not.

The second killer is sample size insufficiency that compounds with the LOCO requirement. With 4 series at roughly 12 events per series in the train split, each LOCO subset has at most 9 events, and a Granger F-test at lag 5 needs at least 11 observations to even compute the null distribution. The gate G3 is structurally infeasible per row, not just statistically underpowered.

The third killer is that the operator-stated breakeven of 51.75% is correct only for at-the-money trades at price 0.50; at off-ATM prices the fee-aware breakeven shifts materially, and Section 6's signal definition (fire when delta_X >= 5pp) does NOT constrain Y's execution price to 0.50. The strategy can fire signals at any Y price between roughly 0.30 and 0.70, and gate G1 (CI excludes 0.5175) is calibrated to the wrong number.

Six additional IMPORTANT-tier findings cover the LLM-filter rubber-stamp risk, the $1 vs $50 notional inconsistency, the anchoring audit's logical inversion, the multiple-strike-per-event independence violation, the pre-flip-only fallback that violates a load-bearing CLAUDE.md fact, and Diercks-implied frequency mismatch.

**Recommendation: KILL.** The combination of the three killer findings (Becker schema lacks ask, LOCO-Granger structurally infeasible, breakeven calibrated to wrong price) means the v2 lock cannot be revised into a fireable methodology. Repair attempts would require either a different dataset (which the live API revival probe already excluded) or a fundamentally different strategy specification (no longer a Kim replication).

---

## Section A: Killer findings

### KILLER-1: Becker trades schema has no orderbook ask at trade time; F4 phantom risk recurs

**Claim being critiqued (v2 Section 3 "Phantom prevention notes" and Section 6 "Signal definition"):**

> "(b) The execution baseline at trade time is the live orderbook ask (per project rules), but that decision is made AFTER the Granger filter identifies a candidate pair, not as part of the Granger computation."
>
> "BUY YES on Y's at-the-money strike at the current orderbook ask"

**The issue:**

The Becker TRADES schema in `prediction-market-analysis/docs/SCHEMAS.md` (verified, lines 32 to 47) contains these columns only:

```
trade_id, ticker, count, yes_price, no_price, taker_side, created_time, _fetched_at
```

There is no `yes_ask`, no `yes_bid`, no orderbook depth snapshot at trade time. The orderbook data only appears in the MARKETS schema (one snapshot per `_fetched_at` per ticker), which is a snapshot table with one row per market per fetch occasion, NOT a time series of orderbook state aligned to trade timestamps.

Concretely: when the v2 strategy in Section 6 fires "BUY YES on Y's at-the-money strike at the current orderbook ask" on day t in the OOS window, there is no field in the Becker dataset that records what the YES ask was on day t. The only data available for day t is whatever trades happened on day t (with their executed prices). The strategy is therefore forced to fall back to one of:

(a) Use the daily VWAP as a proxy for the execution price. This is identical in spirit to v7-B's use of `kalshi_mid_at_t` from stale trade-print, which CLAUDE.md documents as the v7-B CONFIRMED PHANTOM failure mode (8 of 8 live bets lost, mean -$0.20).

(b) Use the next-trade-print after the signal time as the execution price. This introduces look-ahead bias AND still does not capture the actual ask the strategy would have paid.

(c) Use the MARKETS snapshot from the nearest `_fetched_at` timestamp to the signal time. The Becker MARKETS snapshots are not at uniform 15-minute or hourly intervals; the _fetched_at field reflects when the Becker collector ran, which is irregular. Even if it were regular, this is exactly the v8-A failure mode: the orderbook ask the strategy would have paid is the LIVE ask at signal-fire time, not a historical snapshot from minutes or hours earlier.

The v2 lock's Section 3(b) acknowledges the orderbook ask is the project rule, but then assumes it is available in the dataset without verifying the schema. This is the same conceptual error as v7-B: assuming the "true mid" is available when only the trade-print is recorded.

The v2 lock's argument in Section 3(a) (cross-market signal vs within-market signal) is correct for the SIGNAL side but irrelevant for the EXECUTION side. The phantom risk in v7-B was on the EXECUTION baseline, not on the signal feature. The same failure mode applies here.

**Suggested fix or required revision:**

Required revision before any Phase 2 work:

(1) Document explicitly which Becker field will be used as the execution price proxy and acknowledge that no field captures the live orderbook ask at signal time.

(2) Run a verification probe against the live Kalshi API today: pull the orderbook ask for any currently-open KXCPI market and pull a recent trade for the same market. Compare the executed yes_price to the ask at the same moment. If the gap is more than 2c on a meaningful fraction of trades, the daily VWAP is a phantom baseline.

(3) Acknowledge that without the live ask in the dataset, all OOS P&L numbers are computed against a baseline that no live taker would actually pay, and that PHANTOM-RISK is the most likely verdict regardless of how many other gates clear.

This finding alone elevates the prior on V10-A PHANTOM to roughly 60 to 80 percent. Given v7-B's confirmed live failure (1 PHANTOM in the cumulative ledger already), the project cannot afford a second confirmed phantom that follows the exact same data-baseline pattern.

**Tag: KILLER.**

---

### KILLER-2: LOCO at sample size n = 9 cannot run Granger F-test at lag 5

**Claim being critiqued (v2 Section 7, gate G3 and Section 8 F10):**

> "G3 (LOCO robust): Both G1 and G2 hold under leave-one-series-out (4 LOCO subsets). All 4 subsets clear."
> "F10 (LOCO fragility): G3 requires all 4 LOCO subsets to clear. Hard requirement."

**The issue:**

The v2 lock's bottom-line decision logic accepts n_events_post_flip >= 60 as PASS. Distributed across 4 series, that is 15 events per series on average. The train/OOS split point is 2025-07-01, dividing roughly 60/40, so the training window has approximately 9 events per series and the OOS window has approximately 6 events per series.

Granger causality at lag L = 5 requires the regression of Y_t on 5 lags of Y plus 5 lags of X plus a constant, which needs at minimum 5 + 5 + 1 = 11 observations to even compute the OLS coefficients. With 9 training observations per series, the lag-5 regression is structurally infeasible (more parameters than observations); the system is underdetermined.

When you run LOCO (leave one of 4 series out), each subset has 3 series. But the Granger F-test is bivariate (X leads Y, ordered pair); LOCO does not change the pair-level regression's observation count. LOCO changes which PAIRS are evaluated, not how many TIME POINTS each pair has.

So the structural problem is at the pair level, not the LOCO level: every single Granger regression at lag 5 requires 11+ training events on the pair's time series. If the time series for series Y has 9 daily observations in the training window (because there are 9 monthly release events and we are aggregating per release date), the lag-5 Granger F-test cannot run.

If instead the time series is daily VWAP over the full October-2024-to-July-2025 trading-day window (roughly 190 trading days), then n is sufficient for lag 5. But then the Granger regression is on DAILY observations, most of which are not release-event days. The series will have heavy serial correlation (forward-fill across no-trade days per v2 Section 3), and the F-test's asymptotic distribution assumes IID errors, which is violated. The lag selection in Granger is also typically based on information criteria, not on a fixed grid; pre-registering {1, 3, 5} ignores the typical AIC/BIC step.

Either way, the gate is infeasible:
- If observations are release events (n = 9 per series), lag-5 Granger fails to compute.
- If observations are daily VWAP (n = 190 per series), the serial correlation invalidates the F-test's null distribution, and the daily-vs-monthly mismatch between Y's release-event resolution and X's daily VWAP movement creates a different inference problem entirely.

This is a F2-class infeasibility within the regression itself, separate from the F2 sample-size concern for gate firability.

**Suggested fix or required revision:**

The v2 lock must specify:

(1) What the unit of observation actually is for Granger (release-event or daily VWAP). If release-event, lag set must reduce to {1} or {1, 2} maximum at n = 9, and the F-test interpretation must acknowledge near-saturation.

(2) If daily VWAP, the serial-correlation-corrected variant of the test must be used (e.g., Newey-West HAC variance), and the implications for the bootstrap CI on the trading strategy must be reworked.

(3) The bootstrap CI implementation must accommodate serial correlation in the residuals. Standard percentile bootstrap on time-series data is biased toward narrow CIs.

Given that v2's gates G1 and G2 require bootstrap CI exclusion of breakeven, the bootstrap procedure has to be a stationary or block bootstrap, not a row-shuffle bootstrap. v2 Section 6 does not specify which.

**Tag: KILLER.**

---

### KILLER-3: Breakeven 51.75% is wrong at off-ATM execution prices; gate G1 calibrated to wrong number

**Claim being critiqued (v2 Section 6 "Fee-aware breakeven"):**

> "EV = 0 when p = 51.75 / 100 = **0.5175** -> breakeven win rate is approximately **51.75%**."
> "Pre-registered confidence interval gate (G1): The bootstrap 95% CI on win rate in the OOS test split must strictly exclude the 51.75% breakeven, not merely exclude 50%."

**The issue:**

The 51.75% breakeven is derived for a $50 notional at price 0.50 (100 contracts). At that price the fee is ceil(0.07 * 100 * 0.50 * 0.50) = ceil(1.75) = $1.75. EV = p * 48.25 - (1 - p) * 51.75 = 0 yields p = 51.75 percent.

But Section 6 "Signal definition" fires the trade based on delta_X (X's 5pp move), not on Y's price. Y could be at any price between 0.05 and 0.95 when the signal fires. The breakeven shifts as follows for 100 contracts:

| Y exec price | gross win per contract | gross loss per contract | fee per contract | fee total ($) | breakeven win rate |
|---|---|---|---|---|---|
| 0.30 | 0.70 | 0.30 | ceil(0.07 * 0.30 * 0.70) = 0.02 | 2.00 | (0.30 + 2.00 / 100) / 1.00 = 0.320 |
| 0.40 | 0.60 | 0.40 | ceil(0.07 * 0.40 * 0.60) = 0.02 | 2.00 | 0.420 |
| 0.50 | 0.50 | 0.50 | ceil(0.07 * 0.50 * 0.50) = 0.02 | 1.75 | 0.5175 |
| 0.60 | 0.40 | 0.60 | ceil(0.07 * 0.60 * 0.40) = 0.02 | 2.00 | 0.620 |
| 0.70 | 0.30 | 0.70 | ceil(0.07 * 0.70 * 0.30) = 0.02 | 2.00 | 0.720 |

(The fee column uses Kalshi's verified formula `fee_per_contract = ceil(0.07 * price * (1 - price) * 100) / 100`, rounded UP at the contract level per Kalshi's documented per-contract ceiling.)

The breakeven win rate at price 0.30 is roughly 0.32, at price 0.70 is roughly 0.72. Kim et al.'s claim of 54.5% post-filter win rate is BELOW breakeven at any execution price above 0.55 and is COMFORTABLY above breakeven at any price below 0.45. The directional asymmetry matters: Kim's 54.5% is a population statistic averaged across whatever prices their trades happened to fire at; our backtest's per-trade breakeven depends on each trade's actual execution price.

The v2 lock's gate G1 uses a single number (0.5175) for the CI exclusion threshold. This is wrong unless we constrain Y's execution price to a narrow band around 0.50. The v2 lock's ATM strike selection (Section 3) only picks the strike whose opening probability is closest to 0.50; it does NOT constrain the price at execution time, which could be far from 0.50 by the time the signal fires.

A more subtle issue: the fee formula uses the EXECUTION price, but the strategy's "BUY YES at the orderbook ask" means the ask is the relevant price, which is above the mid by half the spread. For wide-spread markets (typical of Kalshi macro at less-liquid strikes), this widens the breakeven further.

**Suggested fix or required revision:**

The v2 lock must either:

(a) Recompute the breakeven per trade based on the actual execution price, and gate G1 must compare the realized win rate to the trade-level breakeven (average over trades). This is harder to bootstrap and the CI interpretation changes.

(b) Constrain the strategy to fire only when Y's ask is in a tight band around 0.50 (e.g., 0.45 to 0.55), losing many signals but making the 0.5175 breakeven defensible. This is a material strategy revision and will further reduce n.

(c) Pre-register a per-trade-EV gate (mean net P&L per trade > 0 with CI excluding zero) and abandon the win-rate gate entirely. G2 already does this; G1 becomes redundant. But G2's CI on dollar-per-trade P&L is much wider than the win-rate CI at small n.

Without one of these revisions, gate G1 is calibrated to the wrong number and a CI exclusion of 0.5175 does not actually exclude breakeven in the strategy's true regime.

**Tag: KILLER.**

---

## Section B: Important findings

### IMPORTANT-1: Sample size compounding with multiple-strikes-per-event independence violation (Section 6 Mitigation)

**Claim being critiqued (v2 Section 6 Mitigation):**

> "If n_events >= 60 in the inventory result, we expand the trade rule to fire on more strikes per event (multiple strikes per event_ticker, not just ATM). This multiplies n by 3 to 8 (number of strikes per macro release event). If 60 events generate 200 to 400 individual strike-level trades, the binomial CI tightens enough to potentially clear breakeven."

**The issue:**

Multiple strikes on the same release event are not independent. A CPI release with actual MoM 0.4% will settle YES on all strikes at or below 0.4 and NO on all strikes above 0.4. The strike-level outcomes are perfectly correlated within event: if the ATM strike loses, several other adjacent strikes also lose; if it wins, the others win conditionally on the realized outcome value.

The effective sample size for inference is the EVENT count, not the strike-trade count. Standard binomial CI assumes IID Bernoulli outcomes; clustered outcomes inflate Type-I error rates.

If we treat events as clusters and use a cluster-bootstrap, the effective n for CI computation is the event count (roughly 60 PASS, 40 to 59 MARGINAL). At n_events = 60 and win rate 54.5%, the cluster-bootstrap CI half-width is approximately 1.96 * sqrt(0.55 * 0.45 / 60) = 0.126, giving a CI of roughly [41.9%, 67.1%]. This easily includes both 50% and 51.75% breakeven, so even at the PASS threshold the gate G1 is not clearable.

To clear the CI half-width of 1.4% (the v2 lock's own analysis at n > 4000), we would need 4000 INDEPENDENT events, not 4000 strike-level trades clustered into 60 events.

The Mitigation in Section 6 is therefore a statistical illusion. Multiplying n by 3-8 via additional strikes per event does NOT tighten the CI proportionally; it tightens it by sqrt of the design effect at most, which for highly correlated clustered outcomes is roughly 1 (no tightening at all).

**Suggested fix or required revision:**

Drop the "expand to multiple strikes per event" mitigation entirely. It does not work statistically. Either:

(a) Acknowledge n_events = 60 cannot clear G1 at Kim's claimed 54.5% win rate, and KILL on F2 power.

(b) Reduce the gate stringency: accept a "directional pilot" verdict (point estimate above breakeven with CI including breakeven, descriptive only). v2's Section 0 verdict tree already has this MARGINAL path for n < 60; it should apply at n = 60 as well unless the gate accepts directional-only.

(c) Wait for more events to accumulate (the v1-original "REVIVE-PRE-FLIP-ONLY" workaround is killed by load-bearing fact 3; see IMPORTANT-6).

**Tag: IMPORTANT.**

---

### IMPORTANT-2: LLM filter is likely a rubber stamp on macroeconomic textbook relationships

**Claim being critiqued (v2 Section 5 prompt template and the implicit assumption that LLM filtering reduces the pair set):**

The v2 prompt asks Gemini Flash:

> "Is it economically plausible that changes in {X_label} causally influence {Y_label} with a {L}-day lead? Answer YES or NO on the first line."

**The issue:**

Gemini 2.5 Flash's parametric knowledge includes mainstream macroeconomic theory. For the 4 Kim-mapped series (CPI, NFP, unemployment, fed funds), textbook macro predicts plausible causal relationships in MOST directions:

- CPI -> Fed Funds (inflation drives policy)
- Fed Funds -> CPI (policy transmits to inflation with lag)
- NFP -> Fed Funds (labor market drives policy)
- Fed Funds -> NFP (rates affect hiring)
- Unemployment -> Fed Funds (labor slack drives policy)
- Fed Funds -> Unemployment (rates affect job market)
- CPI -> Unemployment (Phillips curve relationship)
- Unemployment -> CPI (Phillips curve relationship)
- NFP -> Unemployment (definitionally related, both labor)
- Unemployment -> NFP (definitionally related)
- NFP -> CPI (labor costs feed prices)
- CPI -> NFP (real wages affect hiring)

That's 12 of 12 ordered pairs where mainstream macro theory predicts SOME plausible mechanism. The LLM is very likely to answer YES on most or all pairs.

If Gemini says YES on 10 to 12 of 12 pairs, the filter does not filter. It is a rubber stamp. The downstream "win rate post-filter" computation reduces to "win rate of all Granger-significant pairs," which is just the Granger result without LLM contribution. Kim's claimed +3.1pp improvement from filtering disappears because no filtering occurred.

The v2 anchoring audit gate (G5) is designed to detect the OPPOSITE failure (filter correlates with past P&L because of leakage), but does not detect the rubber-stamp failure (filter says YES to everything).

**Suggested fix or required revision:**

Add a "filter discrimination" pre-test before running G5:

- Smoke-test the LLM filter on a labeled set of 6 to 8 pairs (3 plausible, 3 to 5 implausible reversed-direction or cross-asset-class controls).
- Pass condition: at least 60 to 70 percent of the implausible controls return NO.
- If the filter says YES to everything, V10-A NULLs immediately. The Kim mechanism cannot operate.

The implausible controls could include things like "Does today's bond auction yield cause yesterday's CPI release?" (temporal reversal), or absurd cross-asset claims. If the LLM correctly rejects these, the filter has discrimination power. If it accepts them, V10-A is dead.

Alternatively, the prompt could explicitly require the LLM to identify a specific TRANSMISSION MECHANISM (named institutional channel, not just plausibility), and a separate evaluator scores the mechanism's specificity. This is closer to what Kim's "semantic risk manager" framing implies.

**Tag: IMPORTANT.**

---

### IMPORTANT-3: $1 notional in Section 6 contradicts $50 notional in fee calc

**Claim being critiqued (v2 Section 6, two places):**

> "Position sizing: $1 notional per trade. No Kelly, no leverage. Consistent with v6 / v9 backtest conventions."
>
> "For an at-the-money $0.50 trade with quantity = 100 contracts ($50 notional)... fee = ceil(0.07 * 100 * 0.50 * 0.50) = ceil(1.75) = $1.75"

**The issue:**

These two paragraphs contradict each other. $1 notional at $0.50 per contract is 2 contracts, not 100. At 2 contracts the fee is `ceil(0.07 * 2 * 0.50 * 0.50) = ceil(0.035) = $0.04` (Kalshi rounds the per-contract fee UP at each contract, so this is roughly $0.02 per contract or $0.04 for 2 contracts). The fee-to-notional ratio at $1 is 4 percent, not 3.5 percent, and the breakeven win rate becomes p * 0.96 = (1 - p) * 1.04, yielding p = 1.04 / 2.00 = 52.0 percent (close to but not equal to 51.75 percent).

A subtler problem: Kalshi's fee rounding is per-CONTRACT (each contract's fee is ceiling-rounded to the next penny), not per-TRADE total. At very small trade sizes (1 to 5 contracts), the ceiling rounding dominates. A 1-contract trade at 0.50 pays `ceil(0.07 * 1 * 0.50 * 0.50) = ceil(0.0175) = $0.02` in fees, which is 4 percent of the $0.50 contract. Breakeven win rate at 1-contract size is 0.52 / 1.00 = 52.0 percent.

So the v2 lock's 51.75 percent breakeven applies only at trade sizes of 100 contracts or more where the ceiling rounding is amortized. At $1-notional (2 contracts), breakeven is closer to 52 percent.

Combined with KILLER-3 (off-ATM execution prices), the actual breakeven for the v2 strategy's realized trade distribution is unknown until the strategy is run and trade-level execution prices are recorded.

**Suggested fix or required revision:**

Pick one notional size and use it consistently. If the strategy is $1 per trade, the breakeven is 52.0 percent. If the strategy is $50 per trade ($16 of capital at any time given 32-deployed cap, which is half), the breakeven is 51.75 percent at ATM only. Re-derive G1 using the consistent notional.

For the actual paper-trade, recommend $50 notional per trade (100 contracts) to minimize fee impact, but acknowledge this means 1 to 2 trades at a time given the $32 deployed cap, and only on the at-the-money strike. If the strategy fires multiple signals simultaneously, the $32 cap limits parallel positions.

**Tag: IMPORTANT.**

---

### IMPORTANT-4: Anchoring audit gate G5 is logically inverted

**Claim being critiqued (v2 Section 5 Critical Anchor Audit and Section 7 G5):**

> "Compute Pearson correlation between (a) the LLM's binary YES/NO and (b) the sign of the historical mean P&L of executing that pair in the training window. If r > 0.50, the LLM is anchoring on past performance (a leakage failure). If r is near zero, the LLM is genuinely judging plausibility."

**The issue:**

The prompt template in v2 Section 5 explicitly does NOT include historical P&L data. The LLM does not see "this pair has been profitable historically." The LLM sees:
- X_label, X_fred value
- Y_label, Y_fred value
- Lag L
- Granger F and p

So the LLM at runtime has no access to historical P&L. The correlation between filter YES/NO and historical P&L sign can be high for at least two reasons:

(a) Leakage: the LLM is anchoring on past P&L data (cannot happen here since it is not in prompt).
(b) Coincidence: the LLM is a competent economist, and good economic theory tends to identify mechanisms that work in practice. Pairs the LLM rates plausible may also be pairs with positive historical mean P&L, not because of leakage but because the underlying economic mechanism is real and produced realized profits.

A high r in case (b) is NOT evidence of leakage; it is evidence that the LLM's filter is doing what we hired it to do (rate genuinely plausible pairs higher).

Gate G5 as written cannot distinguish (a) from (b). If it fires PHANTOM-RISK on high r, it may incorrectly kill a legitimate edge. If it does not fire on low r, it does not detect actual leakage either (because leakage would only happen if the prompt accidentally included P&L data, which it does not).

**Suggested fix or required revision:**

Refine or discard G5.

(a) DISCARD option: drop G5 entirely; the prompt structurally prevents the leakage that G5 tries to detect. Replace with a prompt-content audit (verify the prompt contains no P&L data) before launch.

(b) REFINE option: replace G5 with a "filter discrimination" gate (per IMPORTANT-2): the filter must correctly reject implausible controls at least 60 to 70 percent of the time. This tests whether the filter is functioning, not whether it leaks.

The current G5 conflates "filter is competent" with "filter has leaked," and a PHANTOM-RISK verdict on this gate would be a false positive.

**Tag: IMPORTANT.**

---

### IMPORTANT-5: Diercks 2026 implies daily VWAP frequency is wrong

**Claim being critiqued (v2 Section 11):**

> "However, if Susquehanna makes both X and Y markets, they likely arb the lead-lag relationship within seconds. Retail at 15 min cadence is at the wrong frequency to catch this."
> "The remaining Kim signal must be in DAILY rather than INTRADAY lead-lag, which is what daily VWAP captures."
> "Realistic prior: even if Kim's claim is real at the trade level, the daily VWAP version may be too coarse to detect signal."

**The issue:**

The v2 lock acknowledges this concern then proceeds anyway. Section 11 says "operator authorized the attempt anyway; we proceed." But the concern is more specific than v2 frames it.

Diercks/Katz/Wright 2026 (lit #6) documents that Kalshi's day-before-FOMC median has a perfect forecast record for fed funds decisions. This implies the price discovery in macro markets occurs on the day BEFORE the release, in continuous response to incoming data, NOT in cross-market spillover. Susquehanna is making both X and Y markets and arbitrages cross-market price differences in seconds-to-minutes.

The window in which retail could exploit a lead-lag is therefore:
- Sub-second to seconds: Susquehanna closes it
- Seconds to minutes: high-frequency arb closes it
- Minutes to hours: institutional macro funds close it
- Hours to days: Kalshi mid converges to Bloomberg consensus (Diercks confirms)
- Days: no lead-lag remains because both markets have already incorporated all available macro information

The daily VWAP cadence the v2 lock uses sits in the "days" bucket where Diercks says markets are tightly priced. Whatever lead-lag exists is captured at a frequency the daily VWAP smooths out. Kim's reported 54.5 percent win rate would need to operate at a frequency the daily VWAP preserves, which contradicts Diercks's finding for the same series.

This is not a fatal flaw in the methodology design (Diercks does not contradict Kim's specific design as v2 Section 11 notes), but the realistic prior on V10-A is dragged DOWN by this finding to something like 5 to 10 percent at the daily-VWAP frequency. The methodology is conducting a low-prior experiment.

**Suggested fix or required revision:**

Either:

(a) Acknowledge in v2's bottom-line that the realistic prior is approximately 5 to 10 percent (one in 10 to 20 chance of clearing G1 even if Kim's reported signal is real) due to frequency mismatch. The operator should know this before spending $8 LLM cap.

(b) Redesign to intraday cadence (15-minute or 1-hour VWAP). This requires intraday trade timestamps from Becker (verify availability) and may push sample size up. However, it introduces serial correlation problems (IMPORTANT-1 / KILLER-2 expansion).

(c) Pre-register a much weaker gate (G1' = CI excludes 50% only, not 51.75%) and treat this as a directional pilot, accepting that NULL at low power is uninformative.

**Tag: IMPORTANT.**

---

### IMPORTANT-6: Pre-flip-only fallback violates CLAUDE.md load-bearing fact 3

**Claim being critiqued (v2 Section 2, Time window):**

> "Reserved alternative (only if main n_events < 40): Extend the window back to 2022-10-01 explicitly acknowledging that pre-flip regime data is being mixed in. Document the regime control variable. This is the 'REVIVE-PRE-FLIP-ONLY' branch of the verdict tree above."

**The issue:**

CLAUDE.md load-bearing fact 3 (referenced verbatim in v2 Section 2 itself):

> "The 2024 sign flip (Becker): pre-October-2024 takers won, makers now win. Use only post-flip data for modeling."

The pre-flip-only branch directly contradicts this. The justification "document the regime control variable" is insufficient: load-bearing fact 3 is not a soft preference; it is a methodology rule established across 14 rounds of project history. Allowing pre-flip data to enter via a fallback branch risks falsifying any positive result via the v9 F8 failure mode (gate-regime mismatch with the wrong sign).

In practical terms: Kim et al. likely used pre-flip data (their paper submitted February 2026 with multi-year history). Their results may be regime-specific to the pre-flip MM behavior. Replicating their win rate on a pre-flip-only data window risks the same regime mismatch v9 hit: the result is real in the historical regime and zero in the live regime.

**Suggested fix or required revision:**

Remove the REVIVE-PRE-FLIP-ONLY branch entirely. The verdict tree should be:

- n_events >= 60: PASS gate (subject to other critiques)
- 40 to 59: MARGINAL with reduced gate
- < 40: KILL

No pre-flip extension. If the post-flip data are insufficient, V10-A NULLs and we wait for more events to accumulate organically.

The Becker dataset's coverage through November 2025 means post-flip n_events is bounded by what has accumulated through that date. If the inventory result is below 40, V10-A is dead until more events accumulate (months to years of waiting).

**Tag: IMPORTANT.**

---

## Section B (continued): Minor findings

### MINOR-1: Stationarity differencing may flip the Granger interpretation

v2 Section 4 specifies first-differencing for non-stationary series. For Kalshi probability time series (bounded in [0, 1]), the differenced series is the day-over-day probability change. Granger causality on differenced series tests whether X's probability CHANGES predict Y's probability CHANGES, which is conceptually different from "X leads Y in level." For interpretation of the trading signal, this matters: a Granger-significant relationship in differences may not translate to the level-based signal rule (delta_X >= 5pp in 1 to 5 days). Document explicitly that the test and the signal are on the same time-domain transformation.

**Tag: MINOR.**

---

### MINOR-2: Holm-Bonferroni step-down at 12 hypotheses is approximately Bonferroni

v2's verdict tree uses Holm-Bonferroni at the MARGINAL threshold (40 to 59 events). At 12 hypotheses, the most stringent Holm threshold is alpha / 12, same as Bonferroni; only the lower-ranked hypotheses get progressively less stringent. This is correct but document expectation: if only 1 or 2 pairs reach significance, the Holm correction's stringency at the first threshold is identical to Bonferroni, so the "reduced gate" framing in the verdict tree may not be as forgiving as it sounds.

**Tag: MINOR.**

---

### MINOR-3: Spend cap accounting in Section 12 missing pre-flight cost

Section 12 lists Phase 1 inventory at $0 LLM. The methodology critic pass (this document) is listed at $1. The phase 1 inventory likely cost $0 (the v10A-1 revival probe was a duckdb scan). However, the data extraction from the Becker S3 tarball is not budgeted; if extraction or duckdb queries fail and require iteration with assistance, that cost is unbudgeted. The $7 stop trigger has only $1 buffer above the projected $5.50 spend. For a methodology this complex, more buffer is prudent.

**Tag: MINOR.**

---

## Section C: Overall recommendation

**KILL.**

The combination of three KILLER findings cannot be fixed without fundamentally changing the methodology:

1. **The Becker trades schema has no orderbook ask at trade time** (KILLER-1). This is a data-layer infeasibility identical in structure to v7-B's confirmed phantom. No methodology revision can repair this; the dataset itself does not contain the field. Options to fix all fall outside V10-A scope: (a) prospective collection of live orderbook over many months (not a session-final verdict, equivalent to the rejected v8-A pattern); (b) different dataset that includes orderbook (Becker is the best available historical Kalshi dataset; no alternative).

2. **LOCO at sample size 9 cannot run Granger lag 5** (KILLER-2). Either the unit of analysis changes to daily VWAP (introducing serial correlation problems, ambiguous F-test distribution, and the daily-frequency-vs-monthly-event tension), or the lag set drops to {1} only (degrading the Kim replication into a different methodology). Neither is the locked v2 methodology.

3. **Breakeven 51.75% is calibrated to wrong execution price** (KILLER-3). Gate G1's threshold is a single number applied to a strategy that fires across a wide price range. The fix requires either constraining the trade rule to a tight price band (reducing n further) or re-specifying the gate as a per-trade-EV computation (which collapses into G2 and makes G1 redundant). Either way, the v2 lock as written is uncalibrated.

The compounding effect: each killer alone might be repairable with substantial revision, but the joint repair requires changing the dataset (no replacement exists), changing the unit of analysis (no longer Kim replication), and changing the gate (no longer the calibrated breakeven). The result of all three repairs together is not a "Kim replication on Kalshi macro." It is a different angle entirely.

Given the cumulative project state through Round 14 (8 NULLs, 1 PHANTOM, 2 pending PARTIAL shadow modes) and the operator-stated kill-early preference, the v2 lock should not proceed to Phase 2. The Kim et al. paper's mechanism may be real, but at the current Becker dataset and post-flip window, V10-A cannot extract a defensible verdict from it.

**Recommended action:**

(1) V10-A closes KILL at methodology lock, before any LLM filter calls are made. Total LLM spend for V10-A approximately $2 (the literature scout in 01-lit-delta.md plus this critic, both already spent), well under the $8 cap.

(2) Document the kill rationale: data-layer phantom risk replays v7-B pattern; sample size structurally infeasible for LOCO + Granger; breakeven gate uncalibrated for off-ATM execution prices.

(3) Redirect remaining v10 effort to V10-B (already authorized per `research/v10/05-phase1.5-critic.md` Section C as REVISE-AND-PROCEED) or to one of the alternative angles in `research/v10/03-methodology-meta.md` Section 3 (Proposal 1 sportsbook line movement, Proposal 2 game-resolution sports microstructure).

(4) Add to CLAUDE.md a new methodology rule, derived from this critique: BEFORE registering a backtest gate, verify that the execution-price field exists in the dataset schema and is captured at the strategy's signal-fire timestamp. The dataset-schema audit is the new pre-flight check, distinct from the existing methodology-critique pass.

**Tag: KILL.**

---

## Anti-em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout. All separations use double hyphens, commas, semicolons, or "to" / "vs" as appropriate per CLAUDE.md and user memory file `feedback_no_em_dashes.md`.
