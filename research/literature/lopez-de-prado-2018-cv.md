# Lopez de Prado (2018): "Advances in Financial Machine Learning" Ch 7 + Bailey & Lopez de Prado (2014) Deflated Sharpe

**Citation.** Lopez de Prado, Marcos. *Advances in Financial Machine Learning*. Wiley, 2018. Chapter 7 ("Cross-Validation in Finance"). Companion: Bailey, David H. and Lopez de Prado, Marcos (2014), "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality," *Journal of Portfolio Management* 40(5), SSRN 2460551.

**Why it matters for Project Kalshi.** This is the methodological foundation the v2 critic invoked (Section 3 of `research/v2/06-critic.md`) when it diagnosed v2's "5-fold CV in-sample contamination." Specifically: the v2 gate applied a single model trained on the chronological train portion to all 5 walk-forward fold tests; folds 1-3 were 100%, 100%, 83% INSIDE the training data. Purged k-fold with embargo would have prevented this. Bailey/Lopez de Prado 2014 also gives the multiple-testing correction framework that v3 needs because v2 explored 6+ hyperparameter combinations on holdout (Section 8 of v2 critic).

## TL;DR for future Claude

1. **Purged k-fold removes training observations whose label-formation horizon overlaps test labels.** This is bidirectional: rows from before AND after the test fold that depend on test-period information get removed from training.

2. **Embargo adds a one-sided buffer AFTER each test fold.** Lopez de Prado's stated default is ~1% of the dataset; the precise size should be H (the longest-horizon feature lookback or label-formation period). For v3 with H = T-35d feature sampling and outcome at close_time, the natural embargo is 35 days minimum.

3. **Walk-forward CV in Chapter 12 is acknowledged-limited.** "Walk-forward backtesting methods only test a single scenario, easily overfit." Purged k-fold CV is the recommended alternative. Combinatorial Purged CV (CPCV) is the further generalization that gives a distribution of OOS estimates.

4. **Minimum sample for nested CV.** Bailey/Lopez de Prado 2014: "T > 252 observations" is the bare minimum for backtests to be informative; "T > 1,260" (~5 years daily) is recommended for robust estimates. v3's likely n=30-100 markets is FAR below this threshold. The deflation penalty at this n is severe.

5. **Deflated Sharpe Ratio formula.** DSR = (1 - γ/2) × SR - z_{1-α} × √(V[SR]). The expected maximum SR across N independent trials grows like √(ln(N)/T), so for each unit of N you should mentally discount the headline SR by that amount. For v3, if we test 6 hyperparameter combinations on holdout, the inflation factor is √(ln(6)/T); with T = 30 rows, that's √(1.79/30) ≈ 0.245 standard deviations of SR which is a meaningful chunk.

6. **Bonferroni and FDR are the practical corrections.** Bonferroni divides α by N (number of trials). For v3 evaluating C1-C6 across 6 hyperparameter combinations, the effective per-criterion α drops from 0.05 to 0.05/36 = 0.0014, which corresponds to a much wider CI than the 95% we report. Benjamini-Hochberg FDR is less conservative when tests are correlated (as our hyperparameter sweep is) and is the recommended alternative for backtest-discovery settings.

## Chapter 7 mechanics (per the book and secondary sources)

### Purging

For each test fold T_k, identify the set of training labels whose label-formation period overlaps T_k. Remove those labels from the training set. The condition is:

> "If a test set label Y_j depends on information Φ_j, training set labels that depend on Φ_j should be removed."

In v3 terms: if the test fold's earliest label is at time t_start and the latest is at t_end, and labels are formed over a horizon H_label (e.g. 30-180d for v1-domain markets), then any training row with close_time in [t_start - H_label, t_end] must be purged.

### Embargo

After each test fold ends at t_end, exclude observations in [t_end, t_end + E] from the training set. The embargo size E protects against:

- Market-reaction lags (information from the test period that hasn't propagated yet)
- Features that lookback into the embargo window (any feature with lookback L < E would otherwise inherit test-period information)

Standard default: E ≈ 1% of total dataset duration. For v3 with multi-season MLB+NBA+NFL data (say 1095d total), 1% is ~11 days. But the real constraint is E ≥ max feature lookback. If we use 30-day rolling team performance, E ≥ 30 days.

### Walk-forward CV vs. purged k-fold

The book is clear: walk-forward is a *single* path through the data; it tests one ordering of train-then-test events. Easy to interpret, easy to overfit. Purged k-fold gives k separate train/test combinations and a more honest estimate of the OOS distribution. Combinatorial Purged CV (CPCV) chooses k of N test groups and produces (N choose k) backtest paths.

Critical for v3: the v2 gate's "5-fold pooled" was structurally a single-path measurement that REUSED the same trained model. To match the book's intent, the gate must retrain per fold (which v2's salvage fixed via the `trainer=` parameter).

## Multiple-testing corrections (Bailey/Lopez de Prado 2014)

### The problem

> "Analysts backtest millions (if not billions) of alternative strategies, and backtest optimizers search for combinations of parameters that maximize the simulated historical performance of a strategy, leading to backtest overfitting."

### The formula

DSR = (1 - γ/2) × SR - z_{1-α} × √(V[SR])

Where γ is a skewness adjustment, z_{1-α} is the normal critical value at the corrected significance level, and V[SR] is the variance of the Sharpe estimate (a function of T and the higher moments of returns).

The expected maximum SR across N independent trials grows approximately as:

> "For N trials, the expected maximum Sharpe ratio is increased by √(ln(N)/T)"

### Specific Project Kalshi v3 implications

If v3's training pipeline scans across:
- 2 hypotheses (H1, H2)
- 3 model families (logistic, GBM, ensemble)
- 4 threshold grids
- 3 feature subsets
- = 72 effective trials

Then √(ln(72)/T) with T = 100 holdout-eligible rows is √(4.28/100) = 0.207 SR-units of inflation. At an honest SR of ~0.3 (which is what a marginal-edge trading rule might score), the deflated SR is ~0.09, which is plainly not deployable. This matches the v2 finding that the apparent +6.74pp v2-vs-v1 delta was selection-on-holdout artifact.

The discipline implication: **specify the hyperparameter grid BEFORE the run, count N exactly, and report DSR not SR.** Or alternatively pre-register a SINGLE model spec and accept-or-kill on its single number.

## Pin quotes

> "If a test set label Y_j depends on information Φ_j, training set labels that depend on Φ_j should be removed." (AFML Ch 7)

> "For N trials, the expected maximum Sharpe ratio is increased by √(ln(N)/T)." (Bailey/Lopez de Prado 2014, secondary citation)

> "Selection bias combined with backtest overfitting misleads investors into allocating capital to strategies that will systematically lose money." (Bailey/Lopez de Prado 2014, secondary citation)

> "Small samples amplify the probability of false discovery; strategies tested over brief periods may appear profitable by chance alone." (Bailey/Lopez de Prado 2014, secondary citation)

> "Walk-forward backtesting methods only test a single scenario, easily overfit." (AFML Ch 12, secondary citation)

## What is NOT in the book / paper

- **Prediction market specific guidance.** Lopez de Prado's framework is portfolio-trading-strategy-centric. Binary outcomes (Kalshi markets) need adaptation: SR is undefined for binary classification per se, so we substitute realized P&L / SD per trade as the analog, or use Brier-skill / log-loss as the metric.
- **Small-sample (n < 100) prescriptive guidance.** The book assumes daily trading data with T >= 252. For v3's likely n=30-100 the framework SAYS DON'T but doesn't say "here's what to do instead."
- **Calibration-specific advice.** ECE and reliability-diagram methods are not in AFML; for that see Le 2026 and the broader prediction-markets literature.

## Implications for Project Kalshi v3

1. **The v3 gate MUST use per-fold retraining.** The v2 salvage already fixed this via `trainer=`. Verify it is wired correctly in the v3 evaluator before any gate run.

2. **Embargo size = max(H_label, max feature lookback).** For v1-domain markets H_label is the 30-180d lifetime; max feature lookback is whatever rolling-window feature is largest (typically 30-90d for team performance). E ≥ 90 days is the conservative floor.

3. **The grid of hyperparameters explored on holdout must be pre-registered AND counted.** Bonferroni at α=0.05/N or BH-FDR at q=0.10/N is mandatory before claiming a "passing" gate. The v2 critic Section 8 found this was not done.

4. **The realistic v3 sample size (n=30-100) is BELOW the AFML-recommended minimum.** This is a structural constraint, not a methodology choice. v3 should treat the gate as a kill-test (high false-positive aversion) rather than a discovery-test. The honest interpretation: if a model PASSES at n=30, the prior is heavily on false positive.

5. **Walk-forward should not be the sole evidence.** The v2 critic found that the v2 gate's "walk-forward fold means" were dominated by in-sample test windows. Either Combinatorial Purged CV (k of N test groups, multiple paths) or a single chronological 70/30 holdout with strict pre-registration is preferable for v3. Doing both is best practice; doing only purged k-fold with retraining is acceptable.

6. **Calibration is the more informative metric at small n than P&L.** For binary outcomes with n=30-100, P&L variance is dominated by per-trade noise (SD ~40pp for sports markets per v2 numbers); a 95% CI on the mean P&L will include zero up to n=200+. Calibration metrics (Brier skill, ECE, reliability slope) are more stable at small n. v3 should evaluate calibration alongside the P&L gate and treat calibration improvement (over the raw Kalshi price as baseline) as the more reliable signal.

## Action items for v3

1. Code-check the v3 gate's `trainer=` plumbing before any run. Match the v2 salvage spec at `src/kalshi_bot_v2/gate.py`.
2. Set embargo E = 90 days (covers max v1-domain feature lookback) in any purged k-fold.
3. Pre-register the v3 hyperparameter grid in `research/v3/05-dataset-build.md` BEFORE running B2. Count N trials. Apply Bonferroni at α=0.05/N at the headline-gate level.
4. Report calibration metrics (Brier skill vs raw Kalshi price baseline; ECE; reliability slope) alongside P&L metrics in B2's output. If calibration improvement is robust but P&L CI includes zero, the honest verdict is "right direction, wrong sample size" rather than pass-or-kill.
