# v15 Thread B Results: ITF spread vs time-to-close

**Date:** 2026-05-28. **Round:** 20. **Status:** NULL.
**Methodology lock:** research/v15/01-methodology-lock.md.

## TL;DR

ITF orderbook spreads do NOT widen near close. The OLS slope of
spread on minutes-to-close is POSITIVE (+0.0009 per minute), which
means spreads narrow slightly as close approaches. Opposite of the
pre-registered hypothesis.

The pre-close timing refinement is NULL on this evidence.

## Numbers

- Snapshots with positive TTC and defined spread: **2,451**
  (KXITFMATCH 1,321 + KXITFWMATCH 1,130)
- Unique tickers: 317
- Median spread overall (population): 21c (much higher than the
  1-2c we saw in the trade-matched subset of v10a Track 2C; the
  population includes thinly-traded markets that retail trades
  never hit)
- **OLS slope (spread on minutes_to_close): +0.000935 per minute**,
  r-squared 0.33
- Per-prefix slopes:
  - KXITFMATCH: +0.000965 (r2 0.31)
  - KXITFWMATCH: +0.000903 (r2 0.36)

Both prefixes show the same positive slope: spread narrows slightly
toward close. This is consistent with MMs tightening books as match
start time approaches, not withdrawing.

## Pre-registered gate verdict

| Gate | Result | Detail |
|---|---|---|
| B-G1 (n_snapshots >= 1000) | PASS | n = 2,451 |
| B-G2 (OLS slope negative) | FAIL | slope = +0.000935 |
| B-G3 (last-30-min median > overall by 2c+) | FAIL | last-30-min subset is EMPTY |
| B-G4 (bootstrap CI on diff, lower > 0) | FAIL | insufficient data |

**1 of 4 pass = NULL** per the pre-registered verdict tree.

## Why the 30-minute pre-close subset is empty

The probe ran every 30 minutes during a US afternoon / Eurasian
evening window. ITF matches close at match-start time which is
generally during European late-afternoon / Asian morning. By
chance, the probe cadence and the match calendar didn't overlap
within a 30-minute pre-close window for any single ticker.

This is a real limitation, not a refutation. To definitively test
B-G3 / B-G4 we'd need a probe that explicitly samples the 30 to
60 minutes before each market's close_time. That would require an
event-driven probe (look up each open ITF market's close_time and
schedule a snapshot 30 min before each). Outside v15 scope.

## What survives

- **The Round 15c Track 2C SHADOW-CANDIDATE remains intact.**
  Mean spread in the trade-matched subset is 3.8c men / 5.8c women.
  Maker economics at mean spread are marginally positive after
  fees (+0.9c / +1.9c per fill). The pre-close timing refinement is
  NULL, so the recommendation remains "any-time ITF maker" not
  "pre-close ITF maker".
- The population-wide median spread of 21c (vs trade-matched 2-3c)
  is **informative for sizing realistic fill rate**: the wide cells
  are where there is no flow, the tight cells are where the flow
  happens, and the actual maker EV is driven by the trade-matched
  distribution, not the population.

## What this means for live trading

- Do NOT add a pre-close timing rule to any ITF probe; the data
  doesn't support it.
- If the operator runs the small-capital ITF shadow probe (Round
  15c recommendation), keep the time-of-day strategy as "any-time
  in [40c, 60c] band" rather than "pre-close only".

## Spend

This thread: $0 LLM (script-only), $0 external, $0 capital. Total
v15 spend running.

## Anti em-dash audit

Verified after writing.
