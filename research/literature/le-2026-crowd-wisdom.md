# Le (Feb 2026): "Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets"

**Author:** Nam Anh Le (National Economics University, Vietnam)
**arXiv:** 2602.19520v1, posted 2026-02-23
**Venue:** Preprint (arXiv stat.AP)
**Retrieved:** 2026-05-23

**Why this matters for Project Kalshi.** This is the **single most
load-bearing paper for interpreting our Phase 1.5 vs Phase 1.6 gate
results.** Le decomposes Kalshi calibration error into four components
that together explain 87.3% of variance, and finds **weather markets
flip from OVERCONFIDENT at short horizons to UNDERCONFIDENT at long
horizons.** Phase 1.5 (close window) and Phase 1.6 (open+1h to
open+13h) sit on opposite sides of this transition.

## TL;DR for future Claude (the CRITICAL insight)

**Weather calibration is REGIME-DEPENDENT on Kalshi.** At short
horizons (close to resolution), prices are too extreme (overconfident
- isotonic should pull them toward 0.5). At long horizons (well
before resolution), prices are too compressed toward 0.5
(underconfident - isotonic should push them out toward the extremes).
Project Kalshi's Phase 1.5 measured the overconfident regime; Phase
1.6 measures the underconfident regime. **The two gates are testing
DIFFERENT calibration regimes, not the same regime with different
windows.** Expect different signal characters.

## The four components of calibration error (87.3% of variance)

| Component | Variance explained | Direction |
|---|---|---|
| Universal horizon effect (µ) | 30.2% | All domains: underconfident at long horizons (mean slope rises from 0.99 at <1h to 1.32 at >1mo) |
| Domain-by-horizon interactions (β) | **26.0%** (the dominant domain-specific component) | Each domain has its OWN calibration trajectory over time |
| Trade-size scale effect (γ) | 16.5% | Large trades (>100 contracts) on Kalshi politics are MORE compressed (Δ=0.53). Does NOT replicate on Polymarket - **Kalshi-specific microstructure** |
| Domain-specific structural biases (α) | 14.6% | Politics chronically overcompressed (+0.15 intercept); Weather and Entertainment OVERCONFIDENT (-0.09 intercept each) |

## The weather-specific finding (the load-bearing one)

> "Weather markets are **overconfident** at short horizons (slopes
> 0.69-0.97), with prices too extreme relative to base rates, before
> transitioning to **underconfidence** at longer horizons."

Calibration slope interpretation:
- **Slope > 1**: prices compressed toward 0.5 (underconfident).
  Isotonic recalibration would push predictions OUT toward extremes.
- **Slope < 1**: prices too extreme (overconfident). Isotonic
  recalibration would pull predictions IN toward 0.5.
- **Slope = 1**: well-calibrated.

For weather at short horizons: slope 0.69-0.97. This is the regime
**Phase 1.5 was measuring** (close window). Isotonic recovered a
"pull-toward-50%" mapping, which produced the 9pp shoulder edge we
saw.

For weather at long horizons: slope > 1 (transitions to
underconfidence per Le's text). **Phase 1.6 (open+1h to open+13h, ~14
hours before measurement starts) is in this regime.** Isotonic should
recover a "push-out-from-50%" mapping. The character of the edge
will differ from Phase 1.5.

## Dataset

| Platform | Trades | Markets | Cutoff |
|---|---|---|---|
| Kalshi | 64.7M (resolved: 98.6%) | 210,608 | 2025-12-31 |
| Polymarket | 227.6M | 116,000 resolved | 2025-12-31 |

**Per-domain breakdown on Kalshi:**

| Domain | Markets | Trades | Median per-market volume | YES base rate |
|---|---|---|---|---|
| Sports | 55,637 | 43.2M (66.7% of total) | 76 trades | 41.3% |
| Crypto | 76,181 | 6.5M | 35 | 40.7% |
| Politics | 6,609 | 4.9M | **127 (highest)** | 40.2% |
| Finance | 38,058 | 4.3M | 38 | 37.7% |
| **Weather** | **26,911** | **4.4M** | **74** | **24.0%** |
| Entertainment | 7,212 | 1.5M | 60 | 38.0% |
| Total | 210,608 | 64.7M | 47 | 38.1% |

**Notable: Weather has the LOWEST YES base rate (24%).** Most
weather contracts are out-of-the-money strikes that settle NO. This
explains why our Phase 1.5 dataset had outcome_rate of 28-29% and so
many mid prices near 0.01 (deep-OTM strikes).

## Domain-by-horizon trajectories

| Domain | Short horizon (<1h) | Medium (~day-week) | Long (>1mo) |
|---|---|---|---|
| Politics | 0.93 | ~1.5 | 1.83 (always underconfident) |
| Sports | 0.90-1.10 (well calibrated) | 0.90-1.10 | 1.74 (sharply underconfident) |
| **Weather** | **0.69-0.97 (overconfident)** | transition | **>1 (underconfident)** |

Weather is the only domain that FLIPS sign in the calibration error.
Politics is always underconfident. Sports is well-behaved until very
long horizons.

## Trade-size scale effect (Kalshi-specific microstructure)

Le finds **large trades (>100 contracts) in Kalshi politics are
MORE compressed** than small trades (Δ = 0.53, 95% CI [0.29, 0.75]).
Interpretation: confident partisans on opposite sides of political
markets cancel each other out with large bets, pulling prices toward
0.5.

**This does NOT replicate on Polymarket** (Δ = 0.11, CI [-0.15,
0.39]). Le attributes this to Kalshi-specific microstructure -
plausibly the maker/taker incentive structure or the trader
demographics.

**For Project Kalshi:** the Δ effect is documented in POLITICS, not
weather. Le explicitly says sports shows no such effect (Δ = 0.07,
CI [-0.07, 0.26]). Whether weather has a trade-size effect is not
reported. Worth checking empirically.

## Mechanism: why politics is chronically compressed

Le's hypothesis (Section 7 implication): "opposing large bets from
confident partisans cancel each other out, pulling prices toward 0.5
rather than toward truth." This is consistent with the broader
intellectual frame: aggregation works well when traders have diffuse
priors, fails when there are coalitions with strong opposing beliefs.

## Methodology

- **Calibration metric:** logistic recalibration. Slope > 1 =
  underconfident, < 1 = overconfident.
- **Inferential framework:** Bayesian hierarchical model with HMC /
  NUTS sampler. 96.3% posterior predictive coverage.
- **Cross-platform validation:** patterns that replicate Kalshi →
  Polymarket are structural; those that don't (Δ politics effect)
  are platform-specific.
- **Time bins:** "within 1 hour" through "beyond one month" horizons.

## Implications for Project Kalshi (specific and actionable)

1. **Phase 1.5 and Phase 1.6 are NOT measuring the same thing.** 1.5
   sampled the overconfident regime (close window); 1.6 samples the
   underconfident regime (open window). The 9pp shoulder edge in 1.5
   reflected isotonic pulling extreme prices toward 0.5. Phase 1.6's
   isotonic will be doing the OPPOSITE - pushing compressed prices
   out toward extremes.

2. **If Phase 1.6 fails on the same criteria, it might still be
   because of regime mix.** A walk-forward split that mixes early
   weather markets with later weather markets will average over a
   transitioning calibration regime. The OOS ECE ratio might be
   lower than ideal even with real signal, just because the "right
   calibration" varies across markets.

3. **Weather has the lowest YES base rate (24%).** Our dataset
   should reflect this; outcome_rate of 28-29% in our Phase 1.5
   dataset is consistent. The asymmetry means shoulder strikes are
   not symmetric around 0.5 - the actual modal mid-prices cluster
   well below 0.5 for most strikes.

4. **Trade-size scale effect not documented for weather.** The Le
   finding is politics-specific. Project Kalshi can proceed without
   conditioning on trade size, but should empirically verify there
   is no trade-size dependence in the EC-1 signal.

5. **The universal horizon effect (slope 1.32 at >1mo) means the
   underconfidence regime gets STRONGER as horizon lengthens.** If
   Phase 1.6 shows weak signal at 14h, signal may be larger at
   24h+. Phase 2 strategy design could vary trading horizon.

6. **Polymarket comparison is structurally informative.** If we ever
   add cross-platform reference data (per the Project Kalshi action
   items), Polymarket's politics calibration is similar to Kalshi's,
   but the trade-size dependence differs - useful for sanity-
   checking any model.

## Pin quotes

> "Calibration is a structured, multidimensional phenomenon. On
> Kalshi, calibration decomposes into four components ... that
> together explain 87.3% of calibration variance." (abstract)

> "The dominant pattern is persistent underconfidence in political
> markets, where prices are chronically compressed toward 50%."

> "Weather markets are overconfident at short horizons (slopes
> 0.69-0.97), with prices too extreme relative to base rates,
> before transitioning to underconfidence at longer horizons."

> "Crowds are not universally wise or foolish; their forecast
> quality depends systematically on the epistemic structure of what
> they are predicting."

> "Consumers of prediction market prices who treat them as
> face-value probabilities will systematically misinterpret them,
> and the direction of misinterpretation depends on what is being
> predicted, when and by whom."

## Cross-references in the paper

- Le explicitly uses Becker 2026's dataset ("the pre-collected
  dataset of Becker [6]"). So Le and Becker are working on the same
  underlying trades.
- Le cites Page & Clemen (2013) for the standard favorite-longshot
  result.
- Le cites Tetlock & Gardner on superforecasters as a benchmark.

## Limitations

- Polymarket timestamps have ~3-hour noise (Polygon block-derived).
  Short-horizon time bins on Polymarket are unreliable.
- No analysis of how calibration changes within a single market
  intraday - only across-market patterns.
- Finance domain excluded from Polymarket comparison (thin coverage).
- Weather and Entertainment have negligible Polymarket presence.
- Bayesian model assumes additive component structure; non-additive
  interactions not tested.
