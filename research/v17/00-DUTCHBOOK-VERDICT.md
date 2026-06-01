# Angle B: Kalshi Dutch-Book / No-Arb Scan. VERDICT: NULL

**Date:** 2026-06-01. **Type:** read-only empirical scan (no capital, no orders).
**Code:** `src/kalshi_bot/analysis/dutchbook.py` (pure core, 8 tests),
`scripts/v17/dutchbook_scan.py` (live scan). Data: `data/v17/dutchbook_scan.json`.

## Question

Does any Kalshi mutually-exclusive event group offer a risk-free lock: buy YES
on every outcome when the asks sum below 1 (underround), or buy NO on every
outcome (overround, profit = (N-1) - sum(no_ask)), net of the per-leg taker fee?

## Pre-registered gate (locked before the run)

A candidate is a mutually-exclusive, all-active event whose underround OR
overround net margin is > +$0.01 per basket AND minimum top-of-book depth is
>= 1 contract on every needed leg. Underround additionally requires manual
exhaustiveness verification (the listed outcomes must cover every possibility);
overround is robust to a missing outcome (an unlisted winner just makes all N
NOs pay). KILL/NULL if no robust candidate survives.

## Result (6,304 open events scanned)

- mutually-exclusive, all-active, >= 2 legs: **2,791**
- with a fully-quoted (computable) basket: 2,791
- **Overround (buy-all-NO, the robust direction): 0 locks.**
- Underround with cost >= 0.90 (plausibly exhaustive): **1**
- Underround low-coverage phantoms (cost far below 1): **24**

## Why this is NULL, not an edge

1. **Overround shows zero.** This is the direction that does NOT depend on the
   group being exhaustive, so it is the only one that could be a clean lock.
   Market makers keep the bid side from summing above 1 everywhere. Nothing.

2. **The big underround "arbs" are non-exhaustiveness phantoms.** Their basket
   cost is far below 1 (0.037 to 0.57), meaning the listed outcomes cover only a
   small fraction of the probability. Example KXLAPRIMARY-04D26 (LA-04 Democratic
   nominee): two listed candidates at asks 0.017 + 0.020 = 0.037. The real
   nominee is almost certainly someone unlisted, so buying both is a 3.7%
   longshot bet, not a lock. The headline "+1789% annualized" is an artifact of
   dividing a longshot stake into a guaranteed-looking payout that is not
   guaranteed at all.

3. **The one cost-near-1 case is a tail-risk bet, not an arb.** KXSENATERIR-26
   (Rhode Island Republican Senate nominee, 2 candidates): asks 0.911 + 0.056 =
   0.967, net 1.3c after fees. The sub-1 sum is the market pricing a small
   "neither candidate becomes the nominee" tail (a third filer, a withdrawal,
   no nominee). Mutual-exclusivity is real but exhaustiveness is not guaranteed;
   that residual is compensation for the tail, which is exactly why it persists.
   Even if it were genuinely exhaustive, it is ~3% annualized, capital-locked
   for ~5 months, and fragile across a 2-leg simultaneous fill. Not worth $1.

## Structural reason the edge does not exist

For any genuinely exhaustive group, market makers arb the ask sum to ~1 (and the
bid sum to ~1), so no overround or underround survives. What is left below 1 is
either non-exhaustiveness (the scan cannot programmatically guarantee a group
lists every outcome) or an unpriced "none of the above" tail. Neither is
risk-free. The retail-executable, capital-locked, N-leg nature makes even a real
1-3% lock not worth pursuing at the $100 cap.

## Recommendation

KILL this angle. The scan is retained (`scripts/v17/dutchbook_scan.py`) and can
be re-run anytime in seconds if the operator wants to spot-check for a genuine
mispricing during unusual market events, but it should not be expected to
produce capturable edge. No methodology critic / capital deployment is warranted
because the gate produced no robust candidate.

## Reusable artifact

`kalshi_bot.analysis.dutchbook` (parse_market_quote, analyze_group,
annualized_return) is a clean, tested primitive for any future Kalshi
cross-market consistency work.

---

*Em-dash and en-dash audit: verified clean after write.*
