# Round 3 Methodology Revision (Sports x Long-Horizon, post-pivot)

**Author:** Round 3 autonomous-execution context (operator-asleep-2,
woke briefly to authorize pivot at ~22:00 then re-slept)
**Lock date:** 2026-05-24 ~03:00 (re-locked after diagnosis)
**Status:** Operator-authorized methodology pivot. Replaces the binary-
only locked filter with a tiered structural filter that allows multi-
strike events up to 10 sibling contracts per event. Maintains all
other Sports x Long-Horizon methodology constraints.

**Operator authorization (2026-05-24 wake-up message):** "I want you
to make the decision on something that is not END the project, do the
research, figure out how to pass the tests pivot as needed, review
changes, and continue implementing."

This document is the Round 3 delta on
[sports-longhorizon-methodology.md](sports-longhorizon-methodology.md).
The base methodology stands; this doc documents the single revision.

## What changed and why

### The change: relax binary-only filter to tiered structural filter

Previously: `is_binary_market` required exactly 1 contract per
`event_ticker`. This excluded ALL multi-strike events including
ordinary 2-team sports games (where each team has its own YES contract
under one shared event).

Round 3 revision: replace with `is_tradable_event_size` that allows up
to 10 contracts per event. Tag each market by structural tier:
- **single_name**: 1 contract per event (pure binary)
- **two_way**: 2 contracts per event (e.g., NFL game)
- **small_multi**: 3-10 contracts per event (small championships,
  small primary fields)
- **large_multi**: > 10 contracts per event (large brackets;
  EXCLUDED)

### Why: empirical funnel diagnosis (2026-05-23 ~22:00)

Per [sports-results.md](sports-results.md) "Diagnosis" section, the
Round 2 sports gate failed mechanically. Post-mortem diagnosis of the
sports market universe (858,273 settled markets in corpus + volume >=
50 = 572,758):

| Filter step | Markets | Multiplier |
|---|---|---|
| Total post-corpus + volume filters | 572,758 | 1.00 |
| Binary STRICT (1 contract per event) | 6,486 | 0.011 |
| Binary RELAXED (<= 10 contracts per event) | 259,960 | 0.454 |
| Relaxed + lifetime >= 30 days | 1,966 | (40x vs strict) |
| Relaxed + lifetime >= 14 days | 6,771 | |

The binary-strict filter eliminated 99% of sports markets. The Round
2 methodology critic's recommendation (relax + segment-report) was
correct in principle but I implemented strict-binary anyway and then
mechanically failed.

### Why up to 10 (not all)

Bartlett's adverse-selection concern is sharpest in "single-name"
markets. For events with 2-10 sibling contracts:
- Coherence: per-contract slope > 1 implies sum of truth probabilities
  > 1 (incoherent). Up to 10 contracts means slope discrepancies are
  bounded and small.
- Adverse selection: 2-10 sibling events are typically narrower
  competitions (NFL game = 2 teams; small primary = 3-5 candidates)
  where informed flow per contract is more dispersed than single-name.
- Sample preservation: 6,486 -> 259,960 = 40x sample boost.

For events with > 10 contracts (large NCAA brackets, many-candidate
primaries):
- Coherence: per-contract slope > 1 across 10+ contracts implies
  large incoherence.
- Most contracts are deep longshots (< 5c) where Bartlett's adverse
  selection bites hardest.
- Excluded as Tier 4 (large_multi).

## Other methodology changes (NONE)

All other constraints in [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
remain locked:
- 2024-10-01 to 2026-04-30 corpus window
- Min lifetime 30 days
- Trading window [resolution - 42d, resolution - 28d] (Option A)
- Mid-band price filter [0.20, 0.45] U [0.55, 0.80]
- Price-conditional one-sided-flow > 0.65 in [0.30, 0.70]
- Min 20 trades in window
- 6 walk-forward splits, 180d train / 60d test / 14d purge / 60d step
- MIN_TEST_SIZE = 30, MIN_TRAIN_SIZE = 200
- All five pass criteria (C1a, C1b, C2, C3, C4, C5)
- Resolution-time-purge sensitivity check
- Pooled bootstrap as primary C3

## Segment-reporting (added)

In addition to the aggregate gate verdict, the Round 3 gate reports
per-segment results:

- Tier 1 (single_name) aggregate stats
- Tier 2 (two_way) aggregate stats
- Tier 3 (small_multi) aggregate stats
- Per-league aggregate stats (already in v2)

If the aggregate gate passes but a specific tier shows negative net
edge, the operator can choose to deploy only the passing tier(s).

## Pre-commitment for window-widening

If after building the new dataset the median per-market trades in
window is < 20 (Section 3 Option A trigger), widen window to 21 days
[-49d, -28d] (one more week than Option A's 14d). Pre-committed.

## What this is NOT

- Not a change to ANY pass criterion threshold (C1a, C1b, C2, C3, C4, C5
  thresholds unchanged).
- Not a change to the corpus window.
- Not a change to the trading window definition.
- Not a relaxation of MIN_TEST_SIZE or MIN_LEAGUE_SAMPLE.
- Not a re-introduction of pre-flip data.

## Change log

- 2026-05-24 03:00: Initial draft. Round 3 methodology revision. Binary
  filter relaxed to <= 10 contracts per event. market_tier tag added.
  Segment-reporting added to gate output.
- Pending: methodology-critic review after the new gate runs.

## Citations

- Round 2 Sports x Long-Horizon mechanical fail diagnosis:
  [sports-results.md](sports-results.md) "Diagnosis" section
- Round 2 Sports methodology-critic recommendation (relax binary):
  [critic-methodology-sports.md](critic-methodology-sports.md) Section
  4.2 IMPORTANT finding 5
- Bartlett single-name adverse selection logic:
  [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
  TL;DR items 2 and 4
- Operator authorization for Round 3 pivot: chat transcript 2026-05-24
  "I want you to make the decision on something that is not END the
  project"
