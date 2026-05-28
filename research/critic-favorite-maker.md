# Adversarial Critic: Strategy B (Deep-Favorite YES-Maker)

**Date:** 2026-05-23
**Reviewer:** Adversarial-critic context
**Subject:** [favorite-maker-results.md](favorite-maker-results.md) gate report and [favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py) strategy code
**Mandate:** Stress-test before any live capital commits

## Executive summary

**Verdict: LIVE WITH CAVEATS (paper trade first, do NOT skip).** The gate passes its locked five criteria, but the headline +5.13pp test mean is anchored on a 33-trade window where every trade won (test YES rate 100%, not the claimed 97%). The strategy is structurally fragile: break-even YES rate is around 96-97% because the median eligible price is 0.924, so one failed market wipes 15 winning trades. The Bürgi / Becker literature supports a real positive edge of roughly +1 to +3pp net, NOT the 5pp gate headline. The strategy is plausibly profitable but the gate report systematically overstates the magnitude and understates the variance.

## 1. Threshold selection multiple-testing analysis

The Round 4 gate ([favorite-maker-results.md](favorite-maker-results.md) "Threshold-selection honesty check") discloses 7 thresholds (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85) were scanned on train, with 0.70 selected for the test gate. Reported 95% bootstrap CI on test: [+2.60pp, +7.99pp].

**Bonferroni correction.** Family-wise alpha = 0.05 across 7 thresholds gives per-test alpha = 0.05/7 = 0.00714, i.e. 99.29% CI per test. Re-running the bootstrap (10,000 resamples, seed 42, my run on the actual test partition):

- 95% CI: [+2.60pp, +7.98pp] (matches gate report)
- 99% CI: [+1.91pp, +8.81pp]
- 99.29% CI (Bonferroni): [+1.79pp, +8.95pp]
- 99.9% CI: [+1.24pp, +10.06pp]

**Result: even at Bonferroni-corrected 99.29%, the CI excludes zero.** C2 survives the correction at the explicit 7-test family.

**Caveat 1.** The TRUE hyperparameter family across Rounds 1-4 is much larger than 7. The binary-tier (single_name vs. 10-contract cap, see [round-3-methodology-revision.md](round-3-methodology-revision.md)), trading-window ([-42d, -28d] vs others), volume filter, price filter, all were tuned during methodology revisions. A 30-fold Bonferroni pushes per-test alpha to 0.00167 (99.83% CI ~ [+1.41pp, +9.49pp]). Still excludes zero, but the test mean is contaminated (Section 5).

**Caveat 2.** The gate report's "nearby thresholds also positive on test" claim was computed by ALSO scanning thresholds on test. That is circularity. Thresholds 0.65, 0.75, 0.80 produce positive test means BECAUSE the test partition had near-100% YES rate across the range. The robustness claim provides no incremental evidence.

## 2. Sample size and drawdown projections

Test SD = 7.78pp is computed from a sample where every trade won. This SD is artificially compressed. **Full-corpus SD on eligible markets (n=79) is 17.88pp**, which is the proper input for drawdown projections.

I ran 10,000 simulated 100-trade campaigns under five YES-rate scenarios, prices drawn from the actual eligible-price distribution, outcomes drawn from the assumed rate, P&L computed via the strategy's actual fee + slippage formula.

| Assumed YES rate | Mean P&L per trade | P50 max DD | P95 max DD | P99 max DD |
|---|---|---|---|---|
| 0.97 (gate empirical) | +2.09pp | 140c | 322c | 446c |
| 0.95 | +0.13pp | 221c | 521c | 674c |
| 0.93 | -1.90pp | 339c | 742c | 950c |
| 0.90 | -4.88pp | 578c | 1064c | 1300c |
| 0.85 (Bürgi-conservative) | -9.95pp | 1036c | 1636c | 1931c |

**At $1 per trade with $25 bankroll, P95 max drawdown over 100 trades is ~$3.22 (13% of bankroll) at 97% YES rate, jumping to ~$7.42 (30% of bankroll) at 93%.** The 25% drawdown circuit breaker in `config.py` would TRIP under conservative scenarios.

**Tail asymmetry is the real risk.** A 95c YES that resolves NO costs ~98c. A 90c YES that resolves YES earns only ~6.5c after fees and slippage. **Break-even YES rate is ~96.5%, derived from: at median price 0.924, E[P&L] = p(1-0.924-0.035) - (1-p)(0.924+0.035) = 0 when p ~ 0.96.** That is uncomfortably close to the measured 97%.

## 3. Mechanism sanity check vs Bürgi / Becker

Strategy code ([favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py) line 65-71) claims "Round 4 backtest measured 97% YES rate at >=70c sports markets; we conservatively use 0.97 here."

**Bürgi reference.** [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Section 6: makers buying contracts >= 50c earn +2.6% gross with 33% SD. Bürgi's data ended April 2025 (pre-maker-fees). Post-2025 maker fees on a 92c contract round-trip are approximately 2pp, so net Bürgi is ~+0.6%. The >=70c subpopulation should be HIGHER than the >=50c average, plausibly +1 to +2pp net after fees.

**Becker reference.** [becker-2026-microstructure.md](literature/becker-2026-microstructure.md) per-category table: sports per-trade maker advantage = +2.23pp pre-fee. The >=70c slice should be modestly higher.

**Gate measurement.** +5.05pp on full corpus (n=79), +5.13pp on test (n=33). Both are 2-3pp ABOVE what Bürgi + Becker would predict.

**Possible explanations:**

(a) **Institutional MMs have NOT yet competed it down on the >=70c sports niche** because Kalshi sports volume only became material in Q4 2024 ([becker-2026-microstructure.md](literature/becker-2026-microstructure.md) "The 2024 sign flip"). The bias may genuinely be larger than Bürgi's pre-2025 cross-section.

(b) **The 97% YES rate is sampled with significant uncertainty.** P(33/33 YES | true rate 97%) = 0.37 (not unusual), but P(>=77/79 YES | true rate 92%) = ~0.05. True population rate is plausibly 92-97% with wide uncertainty.

(c) **Survivorship.** Dataset filter (lifetime >=30d, >=5 trades in [-42d, -28d]). At T-28d a market trading >=70c YES typically already has the outcome near-certain (one team eliminated, championship clinched). Eligible-set price-conditional outcome rate is plausibly inflated relative to a less-clean live stream.

(d) **Outcome-attribution bug.** Checked the code path; not visible. Not the explanation.

**Most likely: combination of (a) and (b).** Realistic forward-looking expected net edge: **+1 to +3pp**, with headline +5pp being lucky.

## 4. Fill-rate concern (institutional MM competition)

**Largest unmodeled risk.** [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md) TL;DR item 2: "Single-name markets show greater informed price impact than broad-based markets." Sports >=70c is single-name-like.

**The backtest uses `mid_price_at_T_small` as fill assumption.** A live retail bot posting a $1 maker bid at the inside queues BEHIND institutional MM resting size. Jump and Susquehanna sit at the inside in NBA playoff favorite markets; a $1 retail order fills only when their displayed size gets exhausted, which is rare.

**This is untestable in historical trade data.** The backtest's `mid_price_at_T_small` is small-trade VWAP, NOT the bid for a maker order. The strategy ASSUMES the bot can sit at the bid and get filled. This is the load-bearing untested assumption.

**Estimate.** In NBA favorite markets at T-28d, spread is 1-2 ticks. Institutional MMs likely hold 60-80% of inside-book displayed depth (Bartlett qualitative; the % is critic's estimate). Retail fill at backtest price: **30-60% of attempts**. If effective price is 1c worse than backtest (queue-jumping cost), expected net edge drops from +1 to +3pp to +0 to +2pp.

## 5. 97% YES rate verification on held-out

**The single most important finding in this review.**

Strategy code line 67 hard-codes `empirical_yes_rate: float = 0.97` from the gate's full-corpus eligible YES rate. **I checked the held-out test partition specifically.**

- Full corpus eligible (n=79): YES rate = 0.9747
- Train partition (n=46): YES rate = 0.9565
- **Test partition (n=33): YES rate = 1.0000 (every trade won)**

At median price 0.924 with 100% YES rate, P&L per trade = (1 - 0.924 - 0.035) = +4.1pp, sample mean ~+5.1pp with price dispersion. The 5.13pp test result is mechanically consistent with 100% YES rate, NOT with the 97% rate.

**At true 97% YES rate, expected per-trade net is +2.1pp.** That is the defensible forward number. **Gate's 5.13pp overstates the long-run by ~2.5x.**

**Test partition structural concentration:**
- Date span: 2026-04-13 to 2026-04-28 (14 calendar days only)
- League: 31 NBA, 1 NFL, 1 MLB (94% NBA)
- This is NBA playoff time, when favorite/underdog gap is widest and outcomes are LEAST uncertain

**The test sample is structurally one playoff series, not 33 independent observations.** Many markets are sibling contracts on the same event (small_multi tier) or sequential games in the same playoff bracket. Effective independent sample size is closer to 5-10. Bootstrap CI under IID assumption is overstated.

## 6. Robustness concerns

**Time-period (quarterly breakdown, eligible >=70c full corpus):**

| Quarter | n | YES rate | Mean P&L |
|---|---|---|---|
| 2025 Q2 | 3 | 1.000 | +11.29pp |
| 2025 Q3 | 18 | 0.944 | +2.83pp |
| 2025 Q4 | 11 | 1.000 | +9.15pp |
| 2026 Q1 | 4 | 0.750 | -6.51pp |
| 2026 Q2 | 43 | 1.000 | +5.56pp |

**2026 Q1 showed warning signs.** 4 markets, 3 of 4 YES, mean -6.51pp. Consistent with Bürgi predicted ψ shrinkage over time ([burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Table 9). Small sample but bears watching. Q2 rebound to 100% YES is partly NBA-playoff concentration.

**Period concentration.** 43 of 79 eligible (54%) sit in 2026 Q2 alone. The "edge" is unevenly distributed in time.

**Survivorship.** Eligible >=70c subset median lifetime 179.8d vs 123.2d for non-eligible <70c. Eligible markets are LONGER-LIVED, consistent with markets that resolved high having long pre-resolution clarity. Live bot sees ALL markets that pass the filter so the stream IS conditioned identically, BUT ONLY IF it correctly applies the [-42d, -28d] window check before entering. If the live strategy enters on any [70c, 99c] price regardless of time-to-resolution, survivorship bias materializes.

## 7. Recommended pre-live conditions (specific gating steps)

Strategy is plausibly +EV but the gate's +5.13pp headline is misleading. Do NOT skip paper trading. Specific gating ladder:

**Step 1: Pre-paper-trade code audit (1 hour).**
- Change `expected_net_edge()` in `favorite_maker.py` line 65 to use `empirical_yes_rate=0.95`, NOT 0.97. The 97% is full-corpus and includes the lucky test window.
- Add an assertion in `is_eligible()` that the bot is operating in the [-42d, -28d] pre-resolution window. Without this check at live time, the strategy is undefined.
- Add a per-trade cap: skip markets at YES >= 0.95. The tail risk is asymmetric and data above 95c is too thin (5-10 obs) to estimate the NO rate there.

**Step 2: Paper trade 50 fills, ALL leagues (not just NBA).** Use existing `scripts/paper_trade_favorite.py`. Target: 50 ACTUAL maker fills (not attempted entries). Pass criteria:
- Realized YES rate >= 0.92 (95% binomial lower bound clears 0.85)
- Realized mean P&L >= 0 per filled trade
- Time-to-fill logged. If most fills take longer than intended hold window, fill assumption is wrong
- League diversity: >= 3 leagues represented

**Step 3: Fill-rate diagnostic.** Compute (paper-fills)/(paper-attempts). If below 30%, the strategy assumes more market access than it has and forward returns will be far below backtest. Gate live deployment on a fill rate >= 40%.

**Step 4: If steps 1-3 pass, deploy live at REDUCED size.** $0.50 per trade at $25 bankroll. Run 100 fills. Re-evaluate:
- Mean realized P&L >= +0.5pp (not the +5pp headline)
- Max drawdown <= 15% of bankroll
- YES rate on filled markets stays >= 92%

**Step 5: If step 4 passes, raise to $1 per trade.** Monitor weekly. Kill criteria (ANY triggers exit):
- 10-trade rolling mean turns negative for 2 consecutive weeks
- YES rate drops below 90% for a 20-trade window
- Drawdown exceeds 20% of bankroll
- Any single loss > round-trip fee on 15 winning trades

**Step 6: Honor the kill triggers.** Round 1 KXHIGH succeeded BECAUSE it killed cleanly. Round 2 mechanical fails preserved capital. This strategy has a real but small edge with asymmetric downside. Kill triggers above are calibrated to +1 to +3pp edge, not the headline +5pp.

## What I would specifically NOT do

1. **Do not deploy to $1/trade based on the gate report alone.** 100% YES on test is not the long-run rate.
2. **Do not trust test bootstrap CI as forward variance.** SD=7.78pp is compressed by zero losses; full-corpus SD=17.88pp.
3. **Do not skip paper trading.** Fill-rate against institutional MMs is the load-bearing untested assumption.
4. **Do not size on 97% YES rate.** Plan for 92-95%. At 90% the strategy is negative EV.
5. **Do not expand to additional thresholds or leagues without re-validating.** "Nearby thresholds also positive" was contaminated by the 100% YES test window.

## Citations

- Gate report: [favorite-maker-results.md](favorite-maker-results.md)
- Strategy code: [../src/kalshi_bot/strategy/favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py) lines 44, 65-71
- Gate code: [../src/kalshi_bot/analysis/gate_favorite.py](../src/kalshi_bot/analysis/gate_favorite.py)
- Round 3 revision: [round-3-methodology-revision.md](round-3-methodology-revision.md)
- Lessons: [lessons-learned.md](lessons-learned.md)
- Bürgi 2026: [literature/burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Section 6, Table 9, Section 3.4
- Becker 2026: [literature/becker-2026-microstructure.md](literature/becker-2026-microstructure.md) per-category table, "The 2024 sign flip"
- Bartlett & O'Hara 2026: [literature/bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md) TL;DR items 2 and 4
- Dataset: `data/processed/sports_dataset.parquet` (423 rows, 79 eligible >=70c)
- All numerical claims re-ran the dataset directly, not from the gate report.
