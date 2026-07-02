# v28 PROPOSAL: Rotten Tomatoes score ladders (review-accumulation takers)

**Date:** 2026-07-02. Family ~#28. Pre-lock, pre-critic. No settlement-conditioned
analysis run. Chosen under operator full-authority as the best-odds continuation:
the largest per-cluster volume of any family yet tested, genuinely independent
clusters, weekly-recurring new events (deployable shadow math), a free unblocked
live feed, and a settlement variable that is a pure review-count average, so the
v26/v27 bound-and-channel machinery applies on a market 100x more liquid.

## Verified universe (today)

43 settled movie-events, Jan-Jun 2026 closes, 671 markets, 412,004 deduped prints,
15.25M contracts lifetime volume; open ladder shows 1c spreads on 15k-35k volume
markets. Settlement: the displayed Tomatometer at close-date 10:00 AM ET
(quadratic x1 fee). Every event maps to an RT slug; Wayback vintage paths
reconstructible at 1-3 day granularity (bursty; scout doc); live RT pages are NOT
bot-blocked (the live engine is free).

## Registered structure (to be locked)

- **H-A (bound certainty):** the Tomatometer is fresh/count. At a snapshot-proven
  state (score s, count N) with A_max = walk-forward empirical max review arrivals
  for the remaining window (estimated cross-movie from EARLIER-settled movies),
  the final score is bounded in [s*N/(N+A_max), (s*N+A_max)/(N+A_max)] (display
  rounding handled explicitly). Strike outside the bound = decided side; fire when
  priced <= 0.955 with the standard breakeven table. The v26 counter-precedent
  (rain ladders snapped to 0.96+) is the known risk; the outcome-blind 0b fire
  projection adjudicates for $0 before the lock binds.
- **H-B (convergence divergence):** P(final > K) from the empirical distribution
  of score changes conditioned on (days-to-close, N bucket), built cross-movie
  walk-forward; taker fires on divergence >= 0.08; v25/v27 execution machinery
  (binding +3c, worst-case fee, one position per market per ET day, evaluability =
  snapshot-proven states only).
- **D (arrival-channel bound, v27-pattern, non-binding router):** substitute the
  ACTUAL realized review-arrival count (look-ahead) while keeping the current
  fresh-rate for the unknown mix: prices the ceiling of the
  arrival-modeling channel. Pre-committed: if D clears its gates while H-B nulls,
  a live shadow (live RT polling, which the backtest cannot have: fresh intraday
  states) is justified; if D fails everywhere, the arrival channel is dead and
  only H-A/H-B's own verdicts stand.
- CONTROL for H-B: same machinery with the state frozen at the movie's FIRST
  proven post-release state (no updating): catches "any anchored model wins"
  artifacts.

## Known biases to own in the lock

- Backtest staleness (1-3 day snapshot granularity) makes H-B strictly WORSE than
  a live engine holding fresh states: a false-null direction, stated; the live
  shadow is the upgrade path, not a backtest patch.
- Display rounding at integer strikes (the MOR boundary flicker): settlement truth
  is the Kalshi result field ONLY; bound arithmetic uses a 1-point safety margin.
- Slug churn on open events; the 1 closed-unsettled anomaly (KXRT-SEND) excluded.
- Multiple testing at family ~28: three registered components, closed set, the
  ledger counts them.

## Honest prior

Family ~10-12 percent: highest of the recent families on structure (retail
entertainment crowd, no sharp reference, huge volume, mechanical component), but
the same wall evidence stands against it, and the v26 precedent says decided
outcomes may be quoted efficiently even here. The 0b projection and the D bound
will kill cheaply if so.

*Em-dash audit: clean (verified after write).*
