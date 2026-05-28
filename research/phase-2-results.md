# Phase 2 Results: Politics x H Maker-Quote OOS Gate

**Date generated:** 2026-05-23T08:51:43Z
**Methodology:** [phase-2-methodology.md](phase-2-methodology.md)
**Proposal:** [phase-2-proposal.md](phase-2-proposal.md)
**Critic reports:** [plan](critic-plan-phase-2.md), [methodology](critic-methodology-phase-2.md), [code-review-1](code-review-phase-2-milestone-1.md)
**Window:** small-trade VWAP in [resolution - 42d, resolution - 28d] (Option A widening invoked)
**Verdict:** **GATE FAILS** (methodology-strategy incompatibility, not strategy-mechanism failure)

## Headline

All 12 walk-forward splits were SKIPPED because n_test = 0 markets per
split after applying the lifetime-straddle filter (methodology-critic
IMPORTANT fix, Section 5.1). The strategy did not get a fair test of its
core hypothesis (Le's compression slope on long-horizon politics
markets). The gate fails by mechanic incompatibility, not by criteria.

## Pass criteria

| Criterion | Required | Observed | Result |
|---|---|---|---|
| C1a median per-partition slope (small-trade) | >= 1.2 | n/a (0 splits ran) | FAIL |
| C1b q25 per-partition slope (small-trade) | >= 1.0 | n/a (0 splits ran) | FAIL |
| C2 median pooled gross edge (small, eligible) | >= 2.04pp | n/a (0 splits ran) | FAIL |
| C3 walk-forward splits with median net > 0 | >= 10 | 0 of 0 (skipped 12 of 12) | FAIL |
| C4 event windows with median net > 0 | >= 3 of 4 | 0 of 0 (no events tested) | FAIL |
| C5 pooled median AND mean net edge (small) | both > 0pp | median=n/a mean=n/a | FAIL |

## Diagnosis: why all splits skipped

The Phase 2 dataset has 243 binary politics markets in [2024-10-01,
2026-04-30] with sufficient lifetime trades and in-window trades. Their
lifetime distribution: p25=49 days, **p50=79 days**, p75=195 days. Most
politics markets are long-horizon by design.

The methodology-critic IMPORTANT fix (Section 5.1 lifetime-straddle
filter) requires test markets to have `market_open_time > train_end + 14d`,
which equals `> test_start`. Combined with `close_time in [test_start,
test_end]`, this requires market lifetime < test_window length (30
days). Only ~5% of politics markets satisfy lifetime < 30 days.

The funnel:

| Walk-forward split | n_train (straddle) | n_test (straddle) | n_test (resolution-only) |
|---|---|---|---|
| wf_01_2024-10-01_to_2025-05-13 | 66 | 0 | 10 |
| wf_02_2024-10-31_to_2025-06-12 | 72 | 0 | 3 |
| wf_03_2024-11-30_to_2025-07-12 | 81 | 0 | 12 |
| wf_04_2024-12-30_to_2025-08-11 | 87 | 0 | 7 |
| wf_05_2025-01-29_to_2025-09-10 | 100 | 0 | 6 |
| wf_06_2025-02-28_to_2025-10-10 | 103 | 0 | 13 |
| wf_07_2025-03-30_to_2025-11-09 | 113 | 0 | 9 |
| wf_08_2025-04-29_to_2025-12-09 | 127 | 0 | 5 |
| wf_09_2025-05-29_to_2026-01-08 | 135 | 0 | 81 |
| wf_10_2025-06-28_to_2026-02-07 | 137 | 0 | 4 |
| wf_11_2025-07-28_to_2026-03-09 | 217 | 0 | 8 |
| wf_12_2025-08-27_to_2026-04-08 | 222 | 0 | 13 |

Even with the straddle filter REMOVED (rightmost column, hypothetical),
only one split (wf_09 with 81 markets, election cycle) approaches
MIN_TEST_SIZE = 50. The remaining 11 splits have 3-13 test markets each.
After Section 4 strategy filters (mid-band, one-sided-flow), eligible
counts would drop to single digits per split.

## Dataset summary

- rows after all locked filters: 243
- unique series: 239 (almost 1 market per series)
- date_min: 2024-11-05 (post-flip; pre-flip leakage filter worked)
- date_max: 2026-04-29
- outcome_rate: 0.317
- federal_election_rate: 0.506 (meets >= 30% diversity)
- median trades in window: 89 (well above the 20 threshold after Option A)
- median small-trade window count: 31
- mid_small_p50: 0.150 (most markets are deep-OTM longshots)
- pct in mid-band [0.20, 0.45]: 0.132
- pct in mid-band [0.55, 0.80]: 0.177
- total Section-4-eligible: 69 (28% of corpus)

## Root cause analysis

The strategy thesis (Le's chronically-compressed regime, slope = 1.83 at
>1mo horizon) requires LONG-HORIZON markets to test. The methodology
splits (180d train / 30d test / 14d purge with straddle filter) require
SHORT-LIFETIME markets to fit inside test partitions. **These two
requirements are mutually exclusive.**

The methodology critic flagged this risk as IMPORTANT-not-BLOCKING,
acknowledging that the straddle filter "loses sample" but is "the only
honest decorrelation in the long-horizon regime." The critic did not
predict the magnitude of the sample loss for politics specifically.

Secondary issue: even WITHOUT the straddle filter, the politics dataset
(243 markets across 18 months) is too thin to support 30-day test
windows. Median ~13 markets per 30-day window, below MIN_TEST_SIZE=50.

## What the dataset tells us (informational, no gate-equivalent power)

I ran the gate metrics on a hypothetical SINGLE-PARTITION pool (all 243
markets as "test", trained on itself, isotonic fitted on the same data).
This is overfit by construction; it should NOT be interpreted as edge
evidence. Reporting only to characterize the data shape:

- Per-partition logistic slope on small-trade VWAP, pooled: TBD (will
  run separately as a diagnostic, NOT for criteria)

## Decision

Per the methodology lock-in (no third bite, no post-data criterion
tuning), Politics x H ends here. The strategy did not get a fair
empirical test; it failed by methodology-strategy incompatibility.

**The methodology-strategy incompatibility means the Phase 2 verdict is
not a fair test of the mechanism (Le's compression slope).** The
mechanism may still be real. The combination of:

1. Limited binary-only politics markets in our 19-month corpus (~243)
2. Long-horizon mean lifetime (~79 days)
3. Strict lifetime-straddle filter applied to a 30-day test window
4. MIN_TEST_SIZE=50 threshold

cannot validate any long-horizon politics maker-quote strategy.

## Path forward (operator-asleep autonomous decision)

Per the operator's 2026-05-23 evening "full authority" grant and the
"validate the model and sector" mandate, the autonomous-run pivot is:

**Pivot to Sports x Long-Horizon with a methodology DESIGN revision
(not criterion revision) to accommodate long-horizon market lifetimes.**

Rationale:
- Sports has 9x the volume of politics on Kalshi (Becker: 43.2M vs 4.9M
  trades).
- Sports long-horizon slope per Le is 1.74 (comparable to politics 1.83).
- The mechanism (calibration-driven order-flow accommodation) is the
  same.
- The methodology design change (likely: larger test windows OR
  resolution-time-only split) addresses the discovered incompatibility,
  not the strategy thesis. It is a DESIGN fix, not a CRITERION fix.

This is documented in the autonomous-execution log
([phase-2-autonomous-log.md](phase-2-autonomous-log.md)) as a deliberate
decision made under the operator's authorization. The operator may
overrule on wake-up.

## What stays valid

- Engineering scaffolding (parser, fetcher, dataset builder, gate
  evaluator) is mostly category-agnostic and will be re-parameterized
  for Sports.
- The plan-critic findings (1-9), methodology-critic findings, and
  code-review milestone 1 findings all remain operative for any new
  strategy.
- The locked literature (key-findings, paper extractions) and the
  4-fact summary still apply.
- Phase 1.5/1.6 reusable code (auth, client, calibration, metrics)
  unchanged.

## What does NOT carry forward

- The 243-row politics dataset is too thin for any gate that respects
  the lifetime-straddle filter; it is preserved at
  `data/processed/politics_phase2_dataset.parquet` for reference but
  not used in Phase 2 sports.
- The 12-split walk-forward configuration was tuned for the politics
  corpus. Sports may want different parameters (TBD in sports
  methodology lock).
