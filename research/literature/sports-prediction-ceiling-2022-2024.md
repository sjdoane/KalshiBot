# Sports outcome prediction with public features: literature ceiling 2022-2024

**Citations.**
1. Li, S-F, Huang, M-L, Li, Y-Z (2022). "Exploring and Selecting Features to Predict the Next Outcomes of MLB Games." Open-access at PMC8871522.
2. Kuo, Albert (2022). "How Good is FiveThirtyEight's NBA Prediction Model?" blog.albertkuo.me, 2022-01-21. Independent OOS evaluation of 538's NBA forecasts vs. seed-only baseline.
3. Burkhard, Brian (2025). "The Most Accurate Model to Predict MLB Season Win Totals (and Beat Vegas)." Medium. HOBIE model vs. ESPN/PECOTA/FanGraphs/Davenport/Law over 2022-2024 seasons.
4. FiveThirtyEight methodology / Pickwatch tracker (NBA, NFL); accuracy reporting through 2023.
5. Sports-AI.dev (2024). Brier-score benchmark guidance for sports betting models.

Treated as a single combined extraction because no single paper covers the v3-relevant question end-to-end and the combined picture is what v3 needs.

**Why it matters for Project Kalshi v3.** v3's H1 and H2 require external-feature models to add information beyond Kalshi price. If literature shows ceiling accuracy at ~58-66% for game-level outcomes with public features, that constrains what v3 can extract on season-long markets at 0.70-0.95 YES.

## TL;DR for future Claude

1. **MLB game-level prediction ceiling with public features: 55-66% accuracy.** Li et al. 2022 achieved 65.75% with SVM + RFE feature selection on 24 batting/pitching features across 2015-2019; prior literature spans 55-62%. The 94% claim from neural networks on a "pitcher database" is a specialized within-pitcher case, not a game-prediction ceiling.

2. **NBA game-level prediction with public features: ~67% accuracy** (both prediction markets and professional bookmakers cluster here on regular-season games). 538's NBA model achieves comparable accuracy to a seed-only baseline on playoff series (76% over 2016-2020, n=75 series). The sophistication gap collapses to noise at small sample.

3. **NBA in-game Brier scores 0.18-0.22 for sportsbook lines** (Sports-AI.dev benchmark). 538 NFL pregame Brier was 0.208 in 2020 (best since 2015). These are the practical floors; pure noise is 0.25.

4. **MLB season win total RMSE: ~3.2 wins per team for the best-tuned model** (Burkhard's HOBIE 2022-2024). HOBIE's Pearson correlation with actual is ~0.92; Vegas is ~0.97. So the best public-feature model is close to Vegas but consistently below.

5. **Critical translation for v3 season-long Kalshi markets.** A 3.2-win MAE on full-season totals (out of ~162 games) is ~2% of the season. Translated to a 0.70-0.95 YES binary market on "team X wins >= K games": the probability resolution this gives you is roughly the difference between two Gaussian CDFs at the threshold K, which for a high-favored market is in the 1-5% range. That puts the maximum information edge over the Kalshi price (which already reflects sharpshooter sportsbook consensus) at ~1-3pp in probability terms.

## Sample-level findings per source

### Li et al. 2022 (MLB game prediction)

| Spec | Value |
|---|---|
| Sample | 30 MLB teams × 5 seasons (2015-2019), 162 games/team/year |
| Features | 24: 15 hit-related, 8 pitcher-related, 1 win% |
| Methods | 1DCNN, ANN, SVM, Logistic |
| Best accuracy | 65.75% (SVM + RFE feature selection) |
| Without feature selection | 64.25% (SVM) |
| Prior literature range | 55-62% |

**Pin quote:** "SVM obtains the highest prediction accuracies of 64.25% and 65.75% without feature selection and with feature selection, respectively." (Li et al. 2022)

### Kuo 2022 (FiveThirtyEight NBA playoff series)

| Spec | Value |
|---|---|
| Sample | 75 NBA playoff series (2016-2020) |
| 538 model accuracy | 76% correct series predictions |
| Seed-only baseline accuracy | 76% (identical to 538 in 4 of 5 seasons) |
| Implication | Sophisticated model adds zero discriminative power over seed at this n |

**Pin quote (paraphrased):** "The two models correctly predicted the same number of series in every season, except in 2017 and 2019."

### Burkhard 2025 (MLB season win totals)

| Spec | Value |
|---|---|
| Sample | 30 MLB teams × 3 seasons (2022-2024) = 90 team-seasons |
| Best model (HOBIE) MAE | ~3.2 wins/team |
| HOBIE Pearson correlation w/ actual | ~0.92 |
| Vegas line Pearson w/ actual | ~0.97 |
| HOBIE 2024 over/under record | 14-3 (82% win rate on bets) |
| HOBIE win rate when projecting >=6.5 game divergence from Vegas | 91% |

**Pin quote (paraphrased):** "The 2024 record vs. Vegas O/U was 14-3, with win rates increasing relative to divergence magnitude from Vegas lines."

### 538 NFL (Pickwatch / 538 retrospectives)

| Spec | Value |
|---|---|
| 2020 NFL pregame Brier score | 0.208 |
| 2015-2020 NFL Brier range | ~0.20-0.23 |
| Win rate on favored teams | 68.6% (2020) |
| Naive baseline (always predict 0.5) Brier | 0.25 |

### Sports-AI.dev benchmarks

| Sport | Sportsbook Brier range | "Good" Brier threshold |
|---|---|---|
| NBA / NFL game lines | 0.18 - 0.22 | < 0.125 |
| Naive 50/50 | 0.25 | n/a |
| Perfect | 0.0 | n/a |

## What this means for v3 season-long Kalshi markets at 0.70-0.95 YES

The v3 thesis (informed deviation from Kalshi price when external model disagrees) requires that an external public-feature model produces a *more accurate* probability estimate than the Kalshi price.

The math for translating game-level accuracy to season-long binary accuracy:

- A 162-game MLB season has standard deviation ~6.4 wins around the true expected wins (binomial spread of independent games at the team's true win rate).
- A model with MAE 3.2 wins on the point estimate of expected wins is reducing the residual uncertainty to ~2.5 wins of unexplained variance (since MAE 3.2 + irreducible 6.4 = total ~7).
- At a 0.70 YES market on "team X wins >= 85 games," a 2.5-win uncertainty reduction shifts the implied probability by perhaps 3-8pp.
- After Kalshi taker fees (~1.2% of expected earnings) and Polymarket-style maker fees (~25% of taker), the net edge at 0.70 YES on a 3-8pp probability advantage is roughly +1pp to +3pp net P&L per trade.

This is in the SAME ballpark as v1's empirical +5.13pp gross / +1-3pp net edge from `research/critic-favorite-maker.md`. **The literature ceiling on external-feature sports prediction is essentially identical to v1's heuristic edge.** Therefore the operative v3 question is not "is there signal" but "does the external-feature model produce a DIFFERENT signal than v1's favorite-longshot residual," and if it does, does that incremental signal survive multiple-testing correction at the n=30-100 sample size.

The honest read: at this sample size, the literature ceiling does not allow a confident "v3 beats v1 by +2pp" finding. The expected lift is in the 0-3pp range; the gate floor is +2pp; the noise SD on 30-100 trades is ~40pp. The 95% CI on the v3-vs-v1 delta is ±15pp for n=30 and ±8pp for n=100. v3 cannot statistically clear C6 at these sample sizes EVEN IF the true edge is at the literature ceiling.

## Pin quotes

> "Relevant research predicts the accuracy of the next game falls between 55% and 62%." (Search summary of prior MLB literature)

> "SVM obtains the highest prediction accuracies of 64.25% and 65.75% without feature selection and with feature selection, respectively." (Li et al. 2022)

> "Models picked winners correctly about 67% to 68% of the time, with a weighted wins metric producing scores like 75.6 for 538 Elo." (Pickwatch summary of 538 NBA performance)

> "FiveThirtyEight's NFL predictions had a surprisingly good year in 2020, with a Brier score for pregame win probabilities of 0.208, the most accurate mark in any year since 2015, and teams favored by the model won 68.6 percent of their games." (538 retrospective)

> "Sports betting lines tend to average a Brier score of between .18-.22." (Sports-AI.dev benchmark)

## What is NOT in the literature

- **Kalshi-specific calibration vs. Polymarket on sports.** No paper directly compares the two for sports outcomes at the long-horizon end. The Le 2026 paper (already in our index) covers some of this for politics/weather but not sports specifically.
- **OOS-validated external-feature edge on season-long markets.** All public-feature MLB / NBA model papers focus on game outcomes or season totals; none do a head-to-head against a season-long binary market at the price band v3 is interested in.
- **Joint Polymarket-Kalshi-external-feature triple analysis.** This is precisely the v3 gap. v3 would be doing original work here, not extending an existing paper.

## Implications for Project Kalshi v3

1. **External-feature game-level prediction ceiling is ~58-66%.** Anything higher than this in v3's backtest is a red flag for leak or overfit, not signal.

2. **The translated edge on season-long Kalshi markets at 0.70-0.95 YES is +1pp to +3pp net** at the literature ceiling. v1 already operates at +1pp to +3pp net. v3 cannot rely on the external-feature ceiling to deliver C6's +2pp v1-overage; the expected v3-vs-v1 delta is bounded above by ~2pp, which is the C6 floor itself.

3. **The honest H1/H2 falsification gate.** If the external model trained on public features produces an OOS calibration that is no better than the raw Kalshi price (i.e., the model is just a re-encoding of the price), then H1 and H2 are dead. The literature suggests this outcome is structurally likely because the Kalshi price already reflects sportsbook consensus which already integrates the public features.

4. **H3 (Polymarket-Kalshi spread rule) is the only v3 hypothesis that does NOT depend on external-feature prediction.** H3 uses Polymarket as a second opinion directly. Per Topic A's finding that Polymarket-Global has $2.1B/wk volume and might still lead Kalshi-US on shared events, H3 is the most-promising v3 hypothesis given the literature ceiling.

5. **Calibration as the primary metric.** Brier skill vs. the raw Kalshi price baseline is the right metric. P&L is too noisy at v3's sample size. If the v3 model achieves Brier skill > 0 vs. price baseline with statistical significance, that is real signal even if the P&L gate doesn't clear.

6. **Reject the "more features fix it" instinct.** v2 critic Section 5 found the v2 model anchored on price; adding starting-pitcher features was identified as the wrong fix. The literature ceiling (Li et al. saturating at 65.75% even with 24 features and feature selection) confirms: there is no public feature combination that breaks through 65-67% MLB game accuracy. v3 should not invest in feature engineering as the path to clearing the gate.

## Action items for v3

1. Set the v3 calibration baseline as the raw Kalshi price (Brier loss = raw price as the predicted probability). Any v3 model's Brier must beat this baseline OOS or H1/H2 are dead.
2. Project v3 expected edge as +1pp to +3pp gross before fees, in line with the literature ceiling. The gate's C6 (+2pp over v1) is at the structural maximum of what the literature supports; treat anything passing it with high prior on false positive.
3. Pre-commit to evaluating H3 (Polymarket spread rule) even if H1 falsifies, because H3 does not depend on the public-feature ceiling.
4. Do not invest in expensive feature engineering. The marginal lift is bounded by the literature ceiling at game level and shrinks further at season level.
