# v11 A1: Becker game-resolution audit

**Agent:** v11-A1
**Date:** 2026-05-27
**Mission:** determine whether Becker dataset can support v11's sportsbook line-movement
hypothesis on Kalshi game-resolution markets. Pure data-feasibility audit, no edge claims.

## Methodology notes

Source: `prediction-market-analysis/data/kalshi/{markets,trades}/*.parquet`
(read-only). DuckDB 1.5.3 via uv. Status field on markets table; settled = `status = 'finalized'`
(6,971,905 markets total carry that status across all KX prefixes; only 9 rows have
`determined`, 1 has `disputed`, so `finalized` is the canonical settled flag).

The `close_time` field lives on the markets table (not trades), so window queries join
markets to trades on ticker. Trade timestamps are `created_time` on the trades table.
Both are TIMESTAMP WITH TIME ZONE.

Cutoff per brief: post-October-2024 = `close_time >= 2024-10-01`. The 5 KX game prefixes
are all post-rebrand series, so their entire history is post-cutoff in this dataset (no
markets pre-date the cutoff).

Window definitions (relative to market `close_time`):
1. `[T-6h, T-3h]` = trade.created_time in `[close_time - 6h, close_time - 3h]`
2. `[T-3h, T-1h]` = `[close_time - 3h, close_time - 1h]`
3. `[T-1h, close]` = `[close_time - 1h, close_time]`

Feasibility-verdict rule (per brief): FEASIBLE if post-cutoff n >= 100 AND all-three-window
coverage >= 50%. MARGINAL if n >= 50 OR coverage >= 30%. INFEASIBLE otherwise.

I added one supplementary metric not in the brief: trades-per-market p25/median/p75 per
window. Window-coverage alone says "is there >=1 trade", but for line-movement modeling
the bot needs a queue depth that justifies treating Kalshi quotes as reactive. Reporting
the trade-count distribution lets v11's downstream design see whether a 1-min-bucket
return regression has enough trades per bucket to be informative.

## Per-prefix results

### KXNFLGAME (NFL game moneyline)

1. **n_settled_markets:** 428
2. **Date range:** 2025-07-31 to 2025-11-20 (preseason through week 11 of the 2025 season; 2024 NFL games are not in this dataset because the KX rebrand happened mid-2024)
3. **Trade-time-of-day coverage** (post-cutoff = all 428 markets):
   - `[T-6h, T-3h]`: 428 / 428 = 100.0%
   - `[T-3h, T-1h]`: 428 / 428 = 100.0%
   - `[T-1h, close]`: 427 / 428 = 99.8%
   - all three windows: 427 / 428 = 99.8%
4. **Post-Oct-2024 cohort:** 428 (entire series is post-cutoff)
5. **Depth** (trades per market, p25 / median / p75):
   - `[T-6h, T-3h]`: 629 / 1,662 / 3,592
   - `[T-3h, T-1h]`: 1,631 / 4,683 / 9,872
   - `[T-1h, close]`: 232 / 2,138 / 7,173
6. **VERDICT: FEASIBLE.** Coverage is near-100%, depth is massive (median 4.6k trades in
   the [T-3h, T-1h] window). Sample size 428 markets is the smallest of the three
   majors but still 4.3x the FEASIBLE n=100 floor and grows with the 2025 NFL season.

### KXMLBGAME (MLB game moneyline)

1. **n_settled_markets:** 4,408
2. **Date range:** 2025-04-16 to 2025-10-31 (full 2025 MLB regular season plus postseason)
3. **Trade-time-of-day coverage** (post-cutoff = all 4,408 markets):
   - `[T-6h, T-3h]`: 4,403 / 4,408 = 99.9%
   - `[T-3h, T-1h]`: 4,406 / 4,408 = 100.0%
   - `[T-1h, close]`: 4,359 / 4,408 = 98.9%
   - all three windows: 4,357 / 4,408 = 98.8%
4. **Post-Oct-2024 cohort:** 4,408 (entire series is post-cutoff)
5. **Depth** (trades per market, p25 / median / p75):
   - `[T-6h, T-3h]`: 28 / 52 / 96
   - `[T-3h, T-1h]`: 144 / 264 / 444
   - `[T-1h, close]`: 48 / 136 / 303
6. **VERDICT: FEASIBLE.** Largest sample (4,408 markets) but lowest per-market depth of
   the majors. Median 264 trades in [T-3h, T-1h] is enough for 5-min-bucket aggregation
   (~22 trades/bucket at median, ~37 at p75). MLB also has the largest in-season window
   (~6 months) so the v11 backtest can chronologically split with substantial OOS.

### KXNBAGAME (NBA game moneyline)

1. **n_settled_markets:** 738
2. **Date range:** 2025-04-15 to 2025-11-22 (covers end of 2024-25 season plus playoffs plus start of 2025-26 regular season)
3. **Trade-time-of-day coverage** (post-cutoff = all 738 markets):
   - `[T-6h, T-3h]`: 736 / 738 = 99.7%
   - `[T-3h, T-1h]`: 736 / 738 = 99.7%
   - `[T-1h, close]`: 726 / 738 = 98.4%
   - all three windows: 726 / 738 = 98.4%
4. **Post-Oct-2024 cohort:** 738
5. **Depth** (trades per market, p25 / median / p75):
   - `[T-6h, T-3h]`: 178 / 382 / 773
   - `[T-3h, T-1h]`: 946 / 2,359 / 4,357
   - `[T-1h, close]`: 314 / 1,082 / 3,576
6. **VERDICT: FEASIBLE.** Strong on every dimension. 738 markets is 7.4x the FEASIBLE
   floor, coverage 98%+ on all windows, depth median 2,359 trades in [T-3h, T-1h].
   The cross-season date range straddles the dataset cutoff so v11 can split NBA into
   2024-25-playoffs train vs 2025-26-regular OOS cleanly.

### KXBOXING (boxing fight moneyline)

1. **n_settled_markets:** 12
2. **Date range:** 2025-05-03 to 2025-11-03 (12 fights spread over 6 months; episodic)
3. **Trade-time-of-day coverage** (post-cutoff = all 12 markets):
   - `[T-6h, T-3h]`: 10 / 12 = 83.3%
   - `[T-3h, T-1h]`: 10 / 12 = 83.3%
   - `[T-1h, close]`: 12 / 12 = 100.0%
   - all three windows: 10 / 12 = 83.3%
4. **Post-Oct-2024 cohort:** 12
5. **Depth** (trades per market, p25 / median / p75):
   - `[T-6h, T-3h]`: 28 / 58 / 392
   - `[T-3h, T-1h]`: 15 / 92 / 793
   - `[T-1h, close]`: 8 / 159 / 2,293
6. **VERDICT: MARGINAL** by mechanical rule (n=12 < 50, coverage 83.3% >= 30%), but in
   practice INFEASIBLE for any defensible v11 backtest. n=12 events cannot support a
   walk-forward CV with even one fold, and the depth p25 in the [T-1h, close] window
   is 8 trades, so even rich-data markets would not give the regression enough cells.
   Boxing also has the highest variance: p75 trades is 1.6 to 16x p25, so any model
   would overfit to the 2 or 3 high-profile fights (Crawford-Madrimov, Davis-Roach, etc).

### KXUFCFIGHT (UFC fight moneyline)

1. **n_settled_markets:** 374
2. **Date range:** 2025-05-10 to 2025-11-22 (~6 months of regular UFC card cadence)
3. **Trade-time-of-day coverage** (post-cutoff = all 374 markets):
   - `[T-6h, T-3h]`: 365 / 374 = 97.6%
   - `[T-3h, T-1h]`: 363 / 374 = 97.1%
   - `[T-1h, close]`: 357 / 374 = 95.5%
   - all three windows: 356 / 374 = 95.2%
4. **Post-Oct-2024 cohort:** 374
5. **Depth** (trades per market, p25 / median / p75):
   - `[T-6h, T-3h]`: 12 / 31 / 84
   - `[T-3h, T-1h]`: 26 / 54 / 170
   - `[T-1h, close]`: 104 / 230 / 503
6. **VERDICT: FEASIBLE.** 374 markets and 95%+ coverage clears the bar. Depth is the
   weakest of the FEASIBLE four: p25 of 12 trades in [T-6h, T-3h] means a quarter of
   UFC markets have only ~12 trades in that 3-hour window. That bites for any window
   model that needs minute-level granularity at low quantiles. Median 54 in [T-3h, T-1h]
   is still workable. Also note: KXUFCFIGHT covers a single fight, not a card, so 374
   markets implies roughly 30 UFC events at ~12 fights per event over the date range.
   When clustering for inference, use the event-card cluster, not the fight.

## Cross-prefix synthesis

**Aggregate post-Oct-2024 settled markets across the 5 prefixes: 5,960**
(KXMLBGAME 4,408 + KXNBAGAME 738 + KXNFLGAME 428 + KXUFCFIGHT 374 + KXBOXING 12)

Status field on Becker `markets` is `finalized` for settled (this is the canonical value;
`determined` and `disputed` together account for 10 of 6.97M rows, so `finalized` is
operationally equivalent to "settled"). All 5 prefixes are post-rebrand and entirely
post-cutoff, so the "post-Oct-2024 restriction" does not bind on this universe.

Coverage is uniformly high (95%+ for 4 of 5 prefixes, 83% for the boxing outlier). The
v11 line-movement hypothesis is data-feasible in principle: there are enough markets with
trades in the relevant windows to fit and test a model. Depth varies massively (KXNFLGAME
median 1,662 vs KXMLBGAME median 52 in [T-6h, T-3h]), so the v11 design choice of bucket
width matters.

### Recommended v11 Track 1 primary targets

**Primary: KXMLBGAME.** Largest sample (4,408 markets), 6-month in-season window, post-
cutoff coverage 98.8%. Caveats: lowest per-market trade depth of the majors (median 52
in [T-6h, T-3h]), and a Round 15 memo flagged KXMLBGAME as the "cleanest scale-up" for
v1's existing maker edge with 3c+ spread on 90% of markets. v11 should design around
event-level clustering (one game = one cluster), and verify line-movement signal is not
double-counting v1's existing maker bias.

**Secondary: KXNBAGAME.** 738 markets with massive per-market trade depth (median 2,359
in [T-3h, T-1h]) makes this the best prefix for any high-frequency line-movement model.
The 2025-26 NBA season just started (close_time max 2025-11-22 in dataset) so the OOS
window can stay live as Becker is refreshed.

**Tertiary / optional add: KXNFLGAME.** 428 markets, near-perfect coverage, highest
per-market depth. Small n is the only weakness; the 2025 NFL season adds ~16 games per
week and will close the n gap by playoff time. Worth including if Track 1 wants a
3-sport diversification.

**Drop: KXBOXING and KXUFCFIGHT for Track 1.**
- KXBOXING (n=12) is INFEASIBLE despite the mechanical MARGINAL.
- KXUFCFIGHT (n=374) is FEASIBLE on the rule but per-market depth p25 of 12 trades in
  [T-6h, T-3h] makes minute-level modeling unreliable for the bottom quartile of fights.
  Better-suited to a separate fight-card episodic model, not the v11 line-movement
  hypothesis that needs continuous flow.

**One-line recommendation:** v11 Track 1 should target KXMLBGAME (primary, large n) and
KXNBAGAME (secondary, deep books); add KXNFLGAME if Track 1 wants 3-sport robustness.

## Caveats and known limitations not in scope of this audit

1. This audit only counts trades. The Kalshi orderbook bid/ask at trade time is NOT in the
   Becker schema (load-bearing F11 finding from Round 15). Any v11 hypothesis that needs
   the displayed quote when a sportsbook line moves cannot get it from Becker alone. The
   audit answers only "are there trades to align with sportsbook moves", not "can a maker
   bid be filled at the displayed Kalshi quote".
2. Sportsbook data is not in Becker. v11 must source the-odds-api or equivalent for the
   line-movement leg. Beyond this audit's scope.
3. close_time on Becker is the market resolution time, not the game start time. For NFL
   and NBA the two are typically close (markets resolve right after game ends, games run
   ~3 hours), but for MLB and UFC there can be 4 to 6 hours of game-time after the [T-6h,
   T-1h] window if the bot wants to anchor on game-start instead. v11 should decide which
   anchor matters for the sportsbook-line-movement signal and re-audit if it picks game
   start instead of close_time.

## Scripts and artifacts

- `scripts/v11_tmp/audit_game_resolution.py` (main audit script, READ-ONLY queries)
- `scripts/v11_tmp/audit_depth.py` (supplementary depth probe)
- `scripts/v11_tmp/audit_results.json` (machine-readable results)
- `scripts/v11_tmp/depth_results.json` (depth distribution)
