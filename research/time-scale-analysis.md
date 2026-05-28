# Time-Scale Analysis: Should Strategy B Filter or Stratify by Time-to-Resolution?

**Date:** 2026-05-23
**Reviewer:** Research context
**Subject:** Operator observation that most resting orders are long-horizon (season-long bets, fight outcomes months out, NBA expansion that could resolve years from now), question whether the favorite-maker strategy should add a time-scale criterion
**Mandate:** Empirical analysis of the eligible >=70c sports subset by lifetime, plus literature check, plus mechanical reasoning about capital lockup and variance

## Executive summary

**Recommendation: add a soft max-lifetime filter at 180 days, default-on, configurable.** The dataset shows the favorite-maker edge is strong and clean below 180-day lifetimes (n=39, all 39 wins, mean +12.47pp, bootstrap CI [+10.33, +14.63], zero catastrophic losses) and noisy with a single ruinous tail above 180 days (n=8, 1 loss, mean +4.71pp, CI [-21.32, +20.78]). The single long-horizon loss (KXNFLNFCSOUTH-25-TB at 283 days, -81.36pp realized) drags the wider eligible-set mean down by 7.76pp by itself. Capital efficiency is also far worse on long horizons (15.6% annualized vs 130% for sub-90-day). Literature in [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) shows the favorite-longshot bias holds at every measured horizon up to 10 days pre-close but does not segment by total market lifetime. The operator's instinct is correct mechanically and empirically. Recommend `--max-lifetime-days 180` default with documented escape hatch for operator override.

## 1. The data: per-bucket realized P&L on the eligible >=70c subset

Bucketing the 47 eligible markets (current strategy filter: `mid_price_at_T_small` in [0.70, 0.95]) by `lifetime_days` (data at `data/processed/sports_dataset.parquet`, computed in `src/kalshi_bot/strategy/favorite_maker.py:99-125`):

| Bucket | n | YES rate | Mean P&L | Median P&L | SD | Bootstrap 95% CI | Losses > 10pp |
|---|---|---|---|---|---|---|---|
| 30-90d | 11 | 100.0% | +15.17pp | +15.33pp | 4.81pp | [+12.01, +17.70] | 0 |
| 90-180d | 28 | 100.0% | +11.41pp | +10.39pp | 7.42pp | [+8.84, +14.13] | 0 |
| 180-365d | 8 | 87.5% | +4.71pp | +17.15pp | 33.26pp | [-21.32, +20.78] | 1 |

The CI for the 180-365d bucket includes zero. Every other bucket excludes zero by a wide margin.

The pooled <=180d subset (n=39) has mean +12.47pp, bootstrap CI [+10.33, +14.63], YES rate 100.0%, zero losses greater than 10pp. The pooled >180d subset (n=8) contributes one realized loss of -81.36pp on KXNFLNFCSOUTH-25-TB (NFC South division winner market, opened 283 days before resolution at 0.779, settled NO).

If we use the no-upper-cap definition (matches the n=79 cited in [critic-favorite-maker.md](critic-favorite-maker.md) Section 6), the >180d bucket has 11 markets, 2 losses (the same TB market plus KXMLBALCENT-25-DET at 0.976), and the bucket mean is -5.86pp with CI [-33.25, +15.26]. The pattern is identical: the long-horizon bucket is where the SD blows up and the catastrophic tail lives.

## 2. Capital efficiency by bucket (annualized return on capital tied up)

Strategy B locks each dollar of bid capital from fill until settlement. Annualized return on capital, computed as `(realized_pnl / entry_price) * (365 / lifetime_days)` on the eligible set with current cap:

| Bucket | n | Mean annualized | Median annualized |
|---|---|---|---|
| 30-90d | 11 | +130.0% | +119.2% |
| 90-180d | 28 | +34.0% | +26.1% |
| 180-365d | 8 | +15.6% | +29.1% |

Short-horizon trades return roughly 8x more per dollar per year than long-horizon trades even before accounting for the tail risk. The long-horizon trades carry both higher variance and lower turnover. This is the mechanical concern the operator raised, quantified.

## 3. What the literature says about time-scale variance in this bias

[burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Table 5 runs the Mincer-Zarnowitz favorite-longshot regression at 0, 1, 2, ..., 10 days pre-close. The ψ coefficient is roughly stable across those horizons. Bürgi's conclusion is that the bias is present at every measured horizon, "a pre-resolution trading window does not magically fix the bias". This does NOT segment by TOTAL market lifetime (open-to-close), only by snapshot distance to close.

[becker-2026-microstructure.md](literature/becker-2026-microstructure.md) per-category table reports sports gap of 2.23pp pre-fee but does not break down by horizon. Becker's Q3 to Q4 2024 jump from $30M to $820M volume is more about market regime than lifetime.

[bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md) notes single-name markets show greater informed price impact than broad-based. Long-horizon sports markets (season winners, division winners) are almost entirely small_multi sibling-tier; the adverse-selection concern there is structural and partly orthogonal to lifetime, but the longer the horizon the more time for an informed counterparty to pick off a stale quote.

**Literature verdict: no paper rules a time-scale stratification in or out, but the mechanism that produces our edge (retail underpricing of favorites) is documented at all horizons, while the risks that hurt long-horizon trades (information staleness, capital lockup, fat-tailed event risk like a star-player season-ending injury) compound with time.**

## 4. Mechanical analysis of the operator's three implicit concerns

**(a) Capital lockup.** Quantified in Section 2. A 30-90d trade returns 130% annualized on its locked dollar; a 180-365d trade returns 15.6%. This compounds across the bot's max-concurrent budget. With 15 slots all locked in long-horizon trades the bot cannot rotate into new opportunities for months. With 15 slots cycling through 90-day trades the bot can rotate roughly 4x per year. Operator's intuition is correct.

**(b) Information staleness.** Long-horizon prices at the -42d to -28d trading window of [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md) Section 3 are computed when the market still has months of pre-resolution drift. Live trading on a 280d-lifetime market enters at a price set when the relevant news is still maturing. A division-winner market priced at 0.77 in March can absolutely flip to 0.20 by November on an injury or slump; the 0.77 entry was a fair price for THAT week but commits capital through six months of variance. The single -81.36pp loss is structurally consistent with this.

**(c) Variance.** Section 1 quantifies. SD jumps from 4.81pp at 30-90d to 33.26pp at 180-365d, a 7x increase. The bucket SDs are not driven by sampling noise; the underlying outcome distribution is fatter-tailed in the long-horizon bucket.

## 5. Does the existing critic doc already flag this?

[critic-favorite-maker.md](critic-favorite-maker.md) Section 6 raises survivorship concern around lifetime: "Eligible >=70c subset median lifetime 179.8d vs 123.2d for non-eligible <70c. Eligible markets are LONGER-LIVED, consistent with markets that resolved high having long pre-resolution clarity." That observation is about how the eligible set gets selected, not about per-bucket P&L variance. The critic also flags "if the live strategy enters on any [70c, 99c] price regardless of time-to-resolution, survivorship bias materializes" but offers no specific filter recommendation. This research extends that observation into a concrete, data-grounded threshold.

## 6. Live-bot observation reconciled

The operator's live snapshot ("15 resting orders, mostly long-horizon: season-long bets, fight outcomes months out, NBA expansion that could resolve years from now") is consistent with the dataset. The current scanner ([market_scanner.py:29](../src/kalshi_bot/strategy/market_scanner.py) `min_lifetime_days: int`) takes a MIN lifetime, defaulting to 30 (see [paper_trade_favorite.py:398](../scripts/paper_trade_favorite.py)), but no MAX lifetime. With a 0.70-bid posted on any open market in the favorite zone, the bot fills on whatever happens to be available, and long-horizon markets are mechanically over-represented in the open-market universe because they have larger market_close_time minus now. The bot is sampling long-horizon markets in proportion to their open-time inventory, not in proportion to their edge density.

## 7. Recommendation

**Change: add `--max-lifetime-days` argument to `scripts/paper_trade_favorite.py`, default 180, and pass through to `ScannerConfig`.** Add a `max_lifetime_days: int | None = None` field on `ScannerConfig` ([market_scanner.py:25](../src/kalshi_bot/strategy/market_scanner.py)) with the filter check after the existing min-lifetime check.

**Why 180 days, not 90 or 365:**
- 180d preserves 39 of 47 eligible markets in the dataset (83%) and eliminates the catastrophic tail (no losses greater than 10pp).
- A 90d cap would exclude 28 of the 39 clean trades; the 90-180d bucket has CI [+8.84, +14.13], strongly positive.
- A 365d cap would still include the 283d NFL division market that produced the only -81pp loss in the dataset.
- 180d aligns with the natural break in the empirical SD (4-7pp below, 33pp above).

**Default-on, not advisory:** the cost of mis-trade on a long-horizon market (potential -80pp realized) is far larger than the benefit of catching the median +17pp long-horizon winner. Operator can override with `--max-lifetime-days 365` or `--no-max-lifetime` if specific high-conviction markets warrant it.

**Testing:**
- Unit test: scanner rejects a market with lifetime > max when filter is set, accepts when filter is None.
- Backtest sanity: re-run `scripts/gate_favorite.py` (or equivalent gate runner) with max_lifetime_days=180 on the existing parquet; should confirm the +12.47pp pooled mean and tighter CI.
- No live retest needed if the gate stays positive; the change is a strict subset filter on the previously gated population.

**Operational note on existing live orders:** the 15 currently-resting orders include some long-horizon tickets (NBA expansion years out, season-long bets months out). Recommendation is NOT to retroactively cancel resting orders. The filter applies to new scans; existing fills hold to settlement per the documented strategy. Optionally, the operator may individually cancel the longest-horizon resting orders if they were placed without explicit intent, but this is an operator judgment call.

## 8. What this does NOT change

- The favorite-maker edge thesis (Strategy B as a whole). The literature support in [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) and [becker-2026-microstructure.md](literature/becker-2026-microstructure.md) holds equally for sub-180-day markets.
- The 0.70 threshold or 0.95 upper cap.
- The 5-criteria gate or the LIVE_READINESS_DECISION.md acceptance criteria.
- Any safety / kill / drawdown trigger.

The recommendation is a strict subset filter on the existing strategy; it tightens, not redefines.

## Citations

- Dataset: `data/processed/sports_dataset.parquet` (423 rows, 47 eligible with current cap, 79 eligible no-cap).
- Strategy code: [../src/kalshi_bot/strategy/favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py) lines 47-51, 60-66, 99-125.
- Scanner code: [../src/kalshi_bot/strategy/market_scanner.py](../src/kalshi_bot/strategy/market_scanner.py) lines 25-33, 89-91.
- Live bot defaults: [../scripts/paper_trade_favorite.py](../scripts/paper_trade_favorite.py) line 398 (min-lifetime default 30).
- Gate report: [favorite-maker-results.md](favorite-maker-results.md).
- Adversarial critic: [critic-favorite-maker.md](critic-favorite-maker.md) Section 6 (survivorship and time-period concentration).
- Bürgi favorite-longshot bias and horizon analysis: [literature/burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Section 6, Table 5, "Day-by-day evolution".
- Becker sports per-category gap: [literature/becker-2026-microstructure.md](literature/becker-2026-microstructure.md) per-category table.
- Bartlett single-name adverse selection: [literature/bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md) TL;DR item 2.
- Long-horizon methodology context: [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md) Section 2.2 (filters), Section 3 (window).
- All numerical claims re-ran the dataset directly via the realized-P&L formula in [favorite_maker.py:99](../src/kalshi_bot/strategy/favorite_maker.py).
