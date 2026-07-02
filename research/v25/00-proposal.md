# v25 Idea 1 PROPOSAL: AAA retail-gas ladder taker driven by wholesale pass-through

**Date:** 2026-07-02. Status: PROPOSAL (pre-lock, pre-critic). No outcome data pulled or
inspected. Author: autonomous session under the v24 handoff charter.

## One-line idea

Trade Kalshi's AAA retail gasoline ladders (KXAAAGASW weekly, KXAAAGASM monthly) as a
TAKER when a walk-forward wholesale-to-retail pass-through model diverges from the market
price, netting every result against the worst-case taker fee.

## The mechanism, and why it is genuinely new for this project

Settlement: "average regular gas prices for the United States strictly greater than $X on
date D according to AAA" (verified from live rules_primary). The settlement variable is
the AAA national average retail price, which is:

1. **Administered and non-tradeable.** There is no derivatives market on AAA retail gas.
   No options surface, no sharp sportsbook line, no exchange feed to copy into the ask.
   Every prior capture-phantom confirmation (crypto spot, sports books, NWP consensus,
   SPX/VIX options) involved a sharp external reference the MM could mechanically mirror.
   Here the "sharp reference" does not exist; pricing the tail requires actually modeling
   retail dynamics.
2. **Extremely smooth.** The national average is a volume-weighted mean over ~100k
   stations that reprice on staggered schedules. Daily moves are typically well under
   1 cent; even violent wholesale shocks pass through over days-to-weeks.
3. **Mechanically lagged to wholesale.** Retail follows wholesale (RBOB / spot gasoline)
   with a distributed lag of roughly 1-4 weeks and asymmetric speed (the rockets-and-
   feathers literature: retail rises faster than it falls). Wholesale is observable daily
   for free (FRED carries EIA daily spot gasoline series). This gives a genuinely
   EXTERNAL predictor of the settlement variable, which is what the operator's charter
   asks for: a market where an outside variable is a strong predictor of settlement.

Differs from every dead idea on all four axes: TARGET (an administered retail price
level, not a game/asset outcome), REGIME (multi-day to multi-week horizons on thin
Economics ladders), FEATURES (wholesale futures/spot lead + pass-through asymmetry),
ROLE (taker on model-vs-market divergence where the model input is a different market's
price, not a recalibration of Kalshi's own price and not a from-scratch forecast of a
liquid financial asset).

## Honest prior: ~12%

Tempering facts, stated plainly:
- The capture phantom has killed 7 straight public-info taker ideas. Wholesale prices
  are public; anyone CAN run this regression. The escape argument is about attention and
  the absence of a copyable reference, not about secrecy.
- 2024-era volumes (median ~24k-47k contracts per settled market) show these ladders had
  real attention during the inflation/election cycle; an MM that survived that era may
  price pass-through fine.
- The v24 index-vol NULL showed Kalshi prices S&P vol efficiently; if the same MM firm
  quotes gas, sophistication may transfer.
Supporting facts:
- This is the first idea in 25 rounds where the settlement variable is not itself a
  traded/sharp-referenced quantity, and the first with a mechanical distributed-lag
  driver.
- Current live ladders show 1c spreads at the money with hundreds of contracts of depth
  (KXAAAGASM-26JUL31-3.70: bid 145 @ 0.50 / ask 64 @ 0.51, volume 367 in 2 days), so
  capacity exists for the ~$200 bankroll if an edge exists.
- ~110 post-Oct-2024 settlement clusters (82 weekly + 19 monthly from the historical
  drain, plus ~10 more from the live-endpoint recency window), enough for an honest
  event-cluster CI.

## Why it escapes the named failure modes (one line each)

- **Capture phantom:** settlement variable has no tradeable sharp reference to copy; the
  claim being tested is precisely whether the MM does the modeling work anyway.
- **F11 / schema phantom:** taker mechanism, simulated fills only at REAL historical
  trade prints (time-stamped executed prices) with a spread haircut; live-read staging
  before any capital regardless of backtest outcome.
- **Adverse selection:** no resting orders anywhere in the design.
- **Stale-spot phantom (the v24 killer):** the as-of AAA level used at any simulated
  trade time is the value published that morning (Wayback-verified daily history, keyed
  on the page's own "Price as of" date); wholesale regressors enter with an explicit
  one-business-day publication lag.
- **Gate-regime mismatch:** no thresholds borrowed from literature; all thresholds from
  this project's own fee arithmetic.
- **Multiple testing:** strata pre-registered in the lock; no post-data expansion.

## Sketch of the locked test (details go in 01-methodology-lock.md)

- Universe: KXAAAGASW + KXAAAGASM trades, post-2024-10-01, tradeable band on price.
- Model: walk-forward distributed-lag regression of daily retail changes on lagged
  wholesale changes (FRED daily spot gasoline, publication-lagged), asymmetric up/down
  terms, fit only on data strictly before each trade date; P(settle > K) via the
  model-implied path + empirical residuals.
- CONTROL (the honesty detector, per the v24 method win): a random-walk model using the
  same as-of AAA level and residual vol but ZERO wholesale information. The pass-through
  model must beat BOTH the market AND the control OOS; a "pass" that the control also
  achieves is not an informational edge and gets flagged as the weaker claim.
- Execution proxy: take at the recorded trade price with a conservative spread haircut;
  net of the worst-case taker fee ceil(7 * P * (1-P)) cents per contract (the full 0.07
  quadratic; these are not index series, no reduced rate assumed).
- Binding statistic: OOS event-cluster (settlement-event) bootstrap CI of net P&L per
  contract. Pass = CI lower bound > 0 AND model beats control. Anything else = NULL.
- No third bite on NULL.

## Fee facts (from live series objects, scout-verified today)

- KXAAAGASW: fee_type quadratic, multiplier 1 (taker fee ceil(7*P*(1-P)) cents).
- KXAAAGASM: fee_type quadratic_with_maker_fees (taker side same quadratic; maker fee
  irrelevant, we never rest orders).
- Worst-case treatment: full 0.07 quadratic on every simulated fill, no reduced rate.

## Family context (universe scan, doc scout-universe-scan.md)

The full scan of 11,144 series found the gas family is Tier 2 (point-read of a slow
daily public series on the close date, NOT a time-average; KXAAAGASD daily also exists
and is noted as a non-binding exploratory extension). A Tier 1 family of TRUE window
aggregates (monthly rain sums across 11 cities, TSA weekly average, hurricane counts,
launch counts) exists with live markets and is QUEUED as the next candidate (v25 Idea 2)
if this idea nulls; it is not part of this lock.

## Data plan (all free, verified by scouts today)

- Kalshi: /historical/markets drained (271 + 362 markets cached); /historical/trades +
  /markets/trades for executions (2026-05-01 endpoint split respected).
- AAA daily national average: Wayback snapshots of gasprices.aaa.com, 547/640 days
  (85.5%) covered 2024-10-01..2026-07-02, gaps enumerated; smooth-series interpolation
  for gaps with a no-interpolation sensitivity run.
- Wholesale: FRED daily spot gasoline (fredgraph.csv, no key), WTI as secondary.

## What would kill it at the plan stage (invited critic attack surface)

1. Evidence the MM on these series already prices wholesale pass-through (e.g. if the
   ladder's implied drift already tracks RBOB moves; testable only after lock, but the
   critic should judge the prior).
2. The 93 missing Wayback days landing disproportionately in the volatile windows.
3. Fee + spread arithmetic at the relevant price bands eating the plausible edge size.
4. Cluster count too small once filtered to the tradeable band and divergence fires.
5. Any way the design peeks or self-selects (the critic should hunt for garden-of-
   forking-paths risk in the strata definitions).

*Em-dash audit: clean (verified after write).*
