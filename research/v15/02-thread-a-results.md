# v15 Thread A Results: WTA Friday day-of-week effect

**Date:** 2026-05-28. **Round:** 20. **Status:** NULL.
**Methodology lock:** research/v15/01-methodology-lock.md.

## TL;DR

The +1.31pp Friday lift surfaced in Round 15c
(research/v10a/16-time-of-day-analysis.md) does NOT survive rigorous
testing as a Friday-vs-non-Friday DIFFERENCE with cluster bootstrap.

| Window | n_Friday | n_nonFriday | Friday mean | non-Friday mean | Diff | Diff CI |
|---|---|---|---|---|---|---|
| Full (post-Oct-2024) | 130 | 1006 | +3.12% | +2.58% | +0.54pp | [-2.65, +3.38] |
| Train (Nov2024-Aug2025) | 74 | 605 | +2.27% | +2.80% | -0.54pp | [-4.87, +3.43] |
| OOS (Sep2025-Nov2025) | 56 | 402 | +4.25% | +2.30% | +1.95pp | [-2.76, +6.10] |

The train window even has a NEGATIVE point estimate (-0.54pp). The
apparent OOS lift (+1.95pp) is within the bootstrap noise.

## Pre-registered gate verdict

| Gate | Result | Detail |
|---|---|---|
| A-G1 (n_Friday >= 100) | PASS | n_Friday = 130 |
| A-G2 (Friday > non-Friday point estimate, full window) | PASS | +0.54pp |
| A-G3 (CI excludes zero, full window) | FAIL | [-2.65, +3.38] includes zero |
| A-G4-train (CI excludes zero, train) | FAIL | [-4.87, +3.43] includes zero |
| A-G4-oos (CI excludes zero, OOS) | FAIL | [-2.76, +6.10] includes zero |
| A-G5 (round confound stratification) | INCONCLUSIVE | Becker schema lacks tournament round metadata |

**2 of 5 pass = NULL** per the pre-registered verdict tree.

## Why the Round 15c finding evaporated

Round 15c's per-DOW table looked at Friday's own CI (mean +3.95%,
CI [+0.89%, +6.80%]) and noted it excludes zero. But that test
asks "is the Friday cell positive?", which it was. The properly-
specified question is "is Friday's cell HIGHER than the non-Friday
baseline?". Once tested as a difference with appropriate cluster
bootstrap, the lift evaporates.

This is exactly the multiple-comparison risk flagged in the
methodology lock self-critique. With 7 days x 7 prefixes = 49
day-of-week cells, finding ONE cell with a positive 95% CI is
within the false-positive base rate.

## Limitations and what was NOT tested

1. **A-G5 INCONCLUSIVE.** Becker's market metadata does not expose
   the tournament round (round of 16 vs quarterfinal etc.); only
   the match identity and resolution. A round-stratified test
   would require parsing tournament context from match titles or
   external scraping, neither in scope here.
2. **Friday assignment by majority of event trades.** An event
   is tagged Friday if 50%+ of its trades fell on Friday ET. WTA
   matches are short (often under 3 hours) so events typically
   trade on a single day. Edge cases (rain-delayed matches
   spanning days) are absorbed into whichever day held the
   majority.
3. **Cluster bootstrap is by event, not by tournament.** A
   tournament-block bootstrap would be more conservative if
   matches within a tournament share unobserved seeding or
   weather characteristics. The event-level cluster bootstrap is
   the project's standard per CLAUDE.md fact-3.

## What this kills

The Round 15c "WTA Friday Bonus" SHADOW-CANDIDATE hint is now NULL.
No change to v1's scanner or position-sizing logic on day-of-week
grounds is supported by this evidence.

## What survives

Nothing positive on day-of-week from this thread. The 5 PERSIST
prefixes from Round 15b remain the ONLY Becker-validated edge cells.

## Spend

This thread: <$0.10 LLM (no agents spawned), $0 external,
$0 capital. Total v15 spend running.

## Anti em-dash audit

Verified after writing.
