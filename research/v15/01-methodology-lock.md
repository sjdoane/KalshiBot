# v15 (Round 20) Methodology Lock

**Date:** 2026-05-28. **Author:** parallel-context orchestrator
(distinct session from v14 live deployment). **Round:** 20.
**Status:** PRE-DATA lock. No data pulled until this doc is committed.

## Scope and angle

Two-thread tennis-specific investigation, branching off Round 15c
(v10a) Track 2C and 2D findings. **Different edge from v14** (which
is MLB-night sportsbook-leads-Kalshi taker on Politics/MLB).

### Thread A: WTA day-of-week effect

Round 15c Track 2D (research/v10a/16-time-of-day-analysis.md)
surfaced an unexpected day-of-week tail on KXWTAMATCH: Friday
event-mean +0.0395 (CI [+0.0089, +0.0680]) vs overall +0.0264 (CI
[+0.0166, +0.0371]). That is a +1.31pp lift on Friday over the
prefix overall. The Round 15c verdict was "not actionable on its
own"; v15 Thread A tests it rigorously.

**Hypothesis (one-sided):** WTA tennis matches resolved on Friday
have higher per-event maker net P&L (v1 regime: BUY YES as maker
at yes_price >= 0.70) than non-Friday WTA matches.

**Mechanism candidate:** WTA tournament cadence puts the round of
16 on Friday and higher rounds on weekends. Round-of-16 matches
exhibit larger seeding gaps between favorites and longshots than
later rounds, so the favorite-longshot bias may be more
extractable on Friday cards. Confound: this could equally be a
volume/liquidity effect (Friday is the most-traded WTA day for
non-tennis-specific retail flow reasons).

### Thread B: ITF intraday spread / time-to-close dynamics

Round 15c Track 2C concluded ITF tennis is a SHADOW-CANDIDATE
(mean spread 3.8c men, 5.8c women on synthetic-fill set;
borderline +0.9c to +1.9c net after Kalshi fees per fill). The
weakest part of that verdict was the single 6-8 hour observation
window. v15 Thread B uses the existing 17-snapshot dataset to ask:

**Hypothesis (one-sided):** ITF orderbook spreads widen
materially as time-to-close shrinks (specifically: in the 30
minutes before market close where MM withdrawal is plausible).

If true, a maker placement strategy targeting the pre-close window
captures wider spreads and higher per-fill EV than placement at
arbitrary times of day.

## Gates (pre-registered, no post-data tuning)

All gates are evaluated PER THREAD independently.

### Thread A gates

| Gate | Condition | Source of truth |
|---|---|---|
| A-G1 | n_Friday events >= 100 (Becker post-Oct-2024 KXWTAMATCH at v1 regime) | Becker query |
| A-G2 | Friday event-mean > non-Friday event-mean (point estimate) | event-level aggregation |
| A-G3 | Cluster bootstrap CI on Friday-minus-non-Friday DIFFERENCE excludes zero (lower > 0) at 95% level | 2000 cluster bootstrap, by event_ticker |
| A-G4 | Pattern persists across train (Nov 2024 to Aug 2025) AND OOS (Sep 2025 to Nov 2025) windows: A-G3 holds within each window | chronological split |
| A-G5 | Stratifying by inferred tournament round (Round of 16 vs Round of 8+) does NOT eliminate the Friday effect (i.e., the lift survives the round confounder) | Round inferred from match position in event_ticker if possible; otherwise documented as a limitation |

### Verdict tree (Thread A)

- All 5 pass: SHIP-CANDIDATE recommendation for a v1 scanner refinement (add Friday-WTA emphasis or per-DOW position-size lift).
- 4 of 5 pass: SHADOW-CANDIDATE; document for operator follow-up.
- 3 of 5 pass: MARGINAL; honest report, no recommendation.
- Less than 3 pass: NULL.

### Thread B gates

| Gate | Condition | Source of truth |
|---|---|---|
| B-G1 | n_orderbook_snapshots >= 1000 across ITF prefixes in 17-snapshot dataset | data/v10a/itf_orderbook_log.parquet |
| B-G2 | Linear regression of spread on time-to-close (in minutes) has negative slope (spread widens as close approaches) | OLS |
| B-G3 | Spread in last-30-min window > median spread overall by at least 2 cents | percentile comparison |
| B-G4 | Cluster bootstrap CI on (last-30-min mean spread minus overall mean spread) excludes zero with positive lower bound | 1000 bootstrap by ticker |

### Verdict tree (Thread B)

- All 4 pass: SHADOW-CANDIDATE for "place ITF maker quotes only in last-30-min window" rule. Forward probe required to validate live.
- 3 of 4 pass: weak signal; document.
- Less than 3 pass: NULL on this refinement (ITF mean-spread remains the headline; no time-of-day refinement).

## Self-critique (anti-confounder checklist)

Acting as my own critic before pulling data. If any of these
collapses an apparent positive, the verdict moves toward NULL.

**Thread A:**

1. **Tournament round confound.** Friday is canonically round of 16.
   If higher-seed-vs-lower-seed matches have a higher Becker maker
   edge regardless of day, the Friday lift is a round artifact.
   **Mitigation:** A-G5 stratifies by inferred round. If Becker
   data doesn't reveal round, document as a limitation and DO NOT
   ship without further work.
2. **Volume / liquidity confound.** Friday is the most-traded WTA
   day for non-tennis-specific reasons (week-end retail flow,
   sportsbook prop tie-ins). Higher volume could mean tighter
   spreads which counterintuitively REDUCES the maker edge.
   Round 15c's overall WTA prefix Friday lift was +1.31pp despite
   any liquidity effect. **Mitigation:** none in this round;
   note as a known limitation; a forward live probe is the real
   test.
3. **Multiple-comparisons risk.** Round 15c looked at 7 days of
   the week per prefix; Friday was one of 7. With 7 prefixes x 7
   days = 49 cells, finding ONE cell with CI excluding zero at
   95% is approximately the expected base rate. **Mitigation:**
   A-G3 + A-G4 require both train and OOS windows to pass
   independently; multiple-comparison risk is essentially squared.
4. **Sample mix shift.** WTA Friday n=162 vs WTA total n=1136
   means Friday is 14% of the events. If the calendar of which
   tournaments run which weeks differs across days of week, the
   "Friday effect" could be a tournament-quality effect in
   disguise. **Mitigation:** A-G4 chronological split would
   absorb most calendar regime shifts.

**Thread B:**

1. **Selection: which markets have orderbook snapshots near close?**
   ITF markets close at the match start time. If our 30-min
   probe cycle hits some markets near close and others far from
   close, the "last 30 min" comparison may be made on a different
   ticker mix than the overall comparison. **Mitigation:** B-G4
   clusters by ticker, removing per-ticker means before testing
   the difference.
2. **Spread definition.** If `yes_ask` is interpolated to 1.00
   when the no-side book is empty, all our "wide spread" cells
   may be empty-book artifacts. **Mitigation:** filter to rows
   where both yes_levels and no_levels are non-empty (we built
   this into the original parser).
3. **17 snapshots is structurally low n.** 17 cycles per ticker
   gives only 17 measurements per market over 8 hours. The slope
   estimate per ticker is low-power. **Mitigation:** cluster
   bootstrap reduces the per-ticker variance influence; the
   cross-ticker spread distribution is the test, not the
   per-ticker slope.

## What I will NOT do (no third bite)

If the pre-registered gates fail, the verdict is honest NULL
or MARGINAL. No post-hoc threshold tuning. No "but this one
sub-cell passed" rationalizing. The 5-phase pattern applies.

## Phase plan

- Phase 1: this lock (DONE on commit)
- Phase 1.5: methodology critic (deferred; using self-critique
  above instead of an LLM critic agent due to budget; if
  Thread A verdict is SHADOW-CANDIDATE or better, an explicit
  LLM critic Phase 3 pass becomes mandatory before any v1
  scanner change is recommended)
- Phase 2: pull data; run analyses; record numbers
- Phase 3: adversarial critic (LLM agent IF needed per Phase 1.5
  conditional)
- Phase 4: salvage attempts on failed gates (zero allowed for
  Thread A; one allowed for Thread B since it is exploratory)
- Phase 5: final verdict + verdict-conditional next-step plan

## Spend budget

- LLM: < $1 (this orchestrator session; no agent spawns unless
  Phase 1.5 conditional triggers)
- External APIs: $0 (Becker is local, ITF dataset is local)
- Capital: $0 (no live capital actions; v1 and v14 untouched)

## Coordination with live bots (v1 + v14)

- I will NOT touch any code paths that v1 or v14 use at runtime.
- I will NOT recommend any v1 scanner change in this round
  without an explicit Phase 3 critic and operator approval.
- If a SHIP-CANDIDATE emerges, the recommendation is "operator
  evaluates adding to v1 scanner config" not "I edit v1".

## Anti em-dash audit

Verified after writing.
