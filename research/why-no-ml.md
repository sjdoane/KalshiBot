# Why Strategy B uses no machine learning

**Date:** 2026-05-23
**Question raised by operator:** "I figured it would be using some machine learning model trained on data or something. Evaluate the path and if this would be more effective than simply buying the likely bets."
**Decision:** Keep the current heuristic. No ML for now. Revisit only if we accumulate 100+ live fills with clear per-segment differences in observed YES rate.

## Summary of the answer

The current strategy is a single-threshold rule: buy YES at the bid on Kalshi sports markets where the bid is in [0.70, 0.95] and market lifetime is 30 to 180 days. No prediction model. We deliberately chose this over ML approaches and the choice was validated by the gate.

## Three reasons ML hurts at our scale

### 1. Sample size

The full Round 4 sports dataset has 423 markets; the eligible subset (price band, lifetime, volume filters) is 79. Even a small logistic regression with 5 features needs ~100-500 examples to not overfit. Gradient-boosted models need 1000+. We are 20x to 1000x short on data for any non-trivial model. The literature (Bürgi, Becker, Whelan, Bartlett, Le, Polymarket calibration studies, Zerve CalibShi) all use simple statistics on this kind of data, not machine learning, for the same reason.

### 2. Edge size vs model variance

The realistic forward-looking net edge in this strategy is +1 to +3pp per trade, per the Bürgi favorite-longshot bias and Becker maker-advantage estimates. A model's overfit variance at our sample size is comparable to or larger than this edge. Adding a model degrades the realized P&L distribution rather than improving it.

This is not theoretical. Round 3 of this project used isotonic-calibrated probabilities to compute trade decisions. Predicted gross edge: +6.79pp. Realized median P&L: +0.27pp with bootstrap CI [-19pp, +17pp]. The model was confident and the realized variance ate the predicted edge. Round 4 dropped the calibration entirely and the simpler rule passed all five gate criteria on a holdout split.

### 3. The edge comes from structural bias, not predictability

The published edge in event contracts is documented as a structural property of retail-trader-dominated markets: retail bettors overprice longshots and underprice favorites. The bias is not about predicting WHICH favorite wins; it is about NOT paying full price for ANY favorite. The published methods that exploit this are:

- Bürgi 2025: simple maker bids at price bands, no prediction model
- Becker 2026: average per-category maker advantage, no prediction model
- Whelan: equilibrium analysis, no prediction model
- Bartlett & O'Hara 2026: adverse-selection microstructure, no prediction model

A prediction model that tries to forecast WHICH team wins is competing with the legal-sports-betting industry, which has millions of trades, full team-stat feeds, and tens of millions of dollars of model development per year. Retail cannot win that game. The favorite-longshot bias is the residual edge AFTER all of that is priced in.

## What ML COULD theoretically add, evaluated honestly

| Angle | Verdict | Why |
|---|---|---|
| Predict which markets fill | Useful eventually | Requires ~100+ fills to train. We have zero right now. |
| Predict outcome probability per market | Not worth it | Competes with the entire sports-betting industry. Our edge comes from average mispricing, not single-event prediction. |
| Optimal bid price (69 vs 70 vs 71 cents) | Negligible gain | Tick size is $0.01; bid-stack dynamics are noisy at retail volume. |
| Time-to-settlement refinement | Useful as data accumulates | But just a per-segment cap, not a model. We already implemented this as a 180-day filter. |
| Position sizing (Kelly) | Math, not ML | Could implement once we have a defensible YES-rate estimate per segment. |
| Detect bias compression | Already done | The `KILL_ROLLING_30_MEAN_PP_MIN` trigger fires when our rolling-30 mean drops below 0.5pp. Same purpose, no model. |
| Per-league YES-rate calibration | Promising at 100+ fills | Reduces to a 5-row dict. Pure averaging, not ML. |

## When we should revisit

Three concrete preconditions, all required:

1. We have observed at least 100 settled live fills.
2. Per-league outcome rates differ from the global rate by more than 5 percentage points in either direction (i.e., the segments are actually distinct).
3. A revalidation gate (same five criteria as Round 4) passes after introducing the per-segment parameters.

If all three hold, we add a per-league YES-rate dict and recompute expected_net_edge per candidate using the league-specific rate. That is the maximum sophistication the data could justify at the scale we operate.

If we ever scale to >= $1000 bankroll and have >= 1000 historical fills, the same evaluation reopens with a higher ceiling on model complexity. For $32 and 80 historical markets, the answer the math gives us is: stay simple.

## What the operator said and what we are doing

Operator: "There's nothing wrong with simplicity."

That is the right call mechanically. The research literature on event contracts is unusually consistent that the documented edge is structural, not predictive. We keep the current heuristic and revisit after material live data accumulates.

The discipline we are maintaining: more data first, more sophistication only if the data supports it.

## Citations

- Project Round 1 isotonic-calibration KILL: research/phase-1.6-final.md
- Project Round 3 isotonic PROVISIONAL_PASS with C6 fail: research/sports-results.md
- Project Round 4 heuristic PASS: research/favorite-maker-results.md
- Bürgi/Deng/Whelan 2025 favorite-longshot bias: research/literature/burgi-deng-whelan-2025.md
- Becker 2026 maker advantage: research/literature/becker-2026-microstructure.md
- Bartlett & O'Hara 2026 adverse selection: research/literature/bartlett-ohara-2026-adverse-selection.md
- Le 2024 weather calibration: research/literature/le-2024-weather-calibration.md (if present in repo)
- Polymarket calibration / Zerve CalibShi: research/literature/INDEX.md
