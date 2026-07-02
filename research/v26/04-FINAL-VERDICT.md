# v26 FINAL-VERDICT: window-aggregate certainty takers = KILLED AT PRE-LOCK AUDITS

**Date:** 2026-07-02. Hypothesis family ~#26. The lock was NEVER committed; NO
settlement-conditioned P&L was computed at any point. Every number below is
outcome-blind (published-series arithmetic + print prices + Kalshi audit booleans),
per the pre-committed section 0 kill rules of the draft lock. Capital: $0, FLAT.

## Three independent kills

1. **H-A (TSA arithmetic-bound certainty) power floor unreachable.** Outcome-blind
   projection: 15 in-band fires across 11 weekly events vs the 30/12 floor. When the
   published Mon-Thu days plus widened weekend extremes decide a KXTSAW strike, the
   ladder has already left the executable band (prints sit above 0.955 or below
   0.045). Market-matches-arithmetic at the projection stage.
2. **H-A as-of integrity violated (draft-lock 0a2 kill rule).** Wayback spot audit,
   12 snapshots May 2025 - Jun 2026, 120 sampled values: 5 revisions above 0.5
   percent, worst +2.9 percent (2025-06-07), all upward. Today's TSA page is NOT the
   as-of series even in the market window. Corroborated by settlement reproduction:
   2,306/2,309 settled brackets reproduce from today's data and the 3 failures are
   knife-edge cases (0.008-0.31 percent) consistent with post-settlement upward
   restatements. (The methodology critic independently flagged the 2023 restatement
   era leaking into the bound lookback as a blocking edit; moot after the kills, on
   record in 03-methodology-critic.md.)
3. **H-B2 (rain post-crossing) power floor unreachable AND the certainty premise is
   unsound.** (a) 17 post-crossing prints at or below 0.955 across 8 month clusters
   vs the 30/10 floor: once the archived CLI month-to-date crosses the strike, the
   ladder snaps to 0.96+; there is nothing to take on prints. (b) The IEM AFOS
   reconstruction (7,268 CLI products, 10 stations) found DOWNWARD month-to-date
   revisions concentrated exactly at heavy-rain moments: CLIDFW 2026-01-24 2.30 ->
   0.83 within an hour; CLIMDW 2026-06-22 6.44 -> 4.75 same day; CLISEA 8.37 -> 7.37;
   CLILAX 1.20 -> 0.83; plus one real settlement-source divergence month (CLINYC
   2025-02: final CLI 2.59 vs climate-database 2.60). A "certainty" buyer on an
   erroneous issuance takes the full -0.95 loss; with +1c to +6c per winning fire,
   the observed revision incidence cannot be bounded safely below the breakeven
   hazard on the tiny fire base. The 0a3 kill rule fires.

## What this adds to the wall

The v24 MLB null showed instant determination is captured instantly on liquid
sports. v26 shows GRADUAL determination on thin aggregate ladders is also captured,
at least everywhere a print exists: decided outcomes do not print inside the
executable band often enough to test, let alone trade. Combined with v25 (gas
point-read within taker frictions of an honest benchmark), the efficiency wall now
spans instant and gradual determination, forecasts and arithmetic, liquid and thin.

## The one channel prints cannot see, and the $0 deliverable

Print-based history cannot observe RESTING ASKS that never trade. A determined
outcome could in principle sit liftable at 0.90 for days with zero prints (nobody
watching). This is exactly the live-only frontier the v24 strategic pivot named. A
read-only live monitor (scripts/v26/live_certainty_monitor.py, logging determined
rain crossings and TSA bound-determinations against live top-of-book, every 30
minutes, self-expiring 2026-08-03) is deployed as the honest $0 continuation; its
log adjudicates in 2-4 weeks whether unprinted liftable certainty asks exist at all.

## Ledger

Families screened: ~26. Hypotheses this round reaching data: ZERO (both killed at
the outcome-blind feasibility/integrity audits; H-B1 was never registered). Strata
added post-data: zero. Third bites: zero. Data assets banked for any future lock:
as-of CLI issuance series (10 stations, corrections ordered), TSA daily history with
revision hazard documented, ACIS 30-150yr climatology, 206,842 deduped prints across
2,323 settled aggregate markets.

*Em-dash audit: clean (verified after write).*
