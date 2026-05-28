# v11 Track 2 Wiring Report

**Round 16. Phase 2 Track 2.**
**Status:** SHIPPED. 2026-05-27.

## What we built

A post-hoc join script that produces the v11 prompt-specified
cross-table from the existing v5 filter shadow log and v1 order state.

Per the operator decision in research/v11/00-phase1-synthesis.md
(Q2 = "Add join script"), no v1 production code was modified. The
existing shadow-mode + live-filter overlay in `src/kalshi_bot/strategy/shadow_filter.py`
(activated by the operator on 2026-05-24 via SHADOW_MODE_ENABLED=true
AND LIVE_FILTER_ENABLED=true in `scripts/run_live_bot.ps1`) continues
unchanged. This script reads its accumulated output.

## Deliverables

| File | Purpose |
|---|---|
| `src/kalshi_bot_v11/__init__.py` | Package marker for v11 code |
| `src/kalshi_bot_v11/filter_v1_join.py` | Pure-function join logic (testable) |
| `scripts/v11/join_filter_vs_v1.py` | Operator entry point |
| `tests/v11/__init__.py` | Test-package marker |
| `tests/v11/test_join_filter_vs_v1.py` | 15 unit tests (7 required + 8 extras) |
| `data/live_trades/shadow/shadow_filter_decisions.jsonl` | Generated output (412 rows on first run) |

## Verdict gate (per methodology lock v2 Section 9.7)

| Criterion | Status |
|---|---|
| a) Script runs cleanly on current `v5_filter_shadow_log.jsonl` | PASS (412 rows generated) |
| b) Output schema validates against Section 9.4 spec | PASS |
| c) All 7+ unit tests pass | PASS (15 tests pass) |
| d) Existing tests still pass (no regression) | PASS (489 importable tests pass; the 8 test files with missing-dep import errors in the kronos venv predate v11 and are not regressions) |

**Verdict: SHIPPED.**

## First-run cross-table observations

Real data from 412 shadow-log rows after running the join script:

| shadow_filter_decision | v1_decision | Count |
|---|---|---|
| False | not_placed | 10 |
| True | not_placed | 314 |
| True | placed_and_cancelled | 59 |
| True | placed_and_filled | 15 |
| True | placed_and_resting | 14 |

Interpretation note (descriptive, NOT a Track 2 ship criterion):

- Filter said don't-trade in only 10 of 412 rows (2.4%). The active
  overlay rarely fires on the post-W1-denylist universe; this is
  consistent with V5-A1's 40.7% coverage finding (filter has signal
  on a subset of v1's universe, fires the SKIP rule on a fraction
  of that subset).
- Of the 402 rows where filter said trade, v1 fired and got filled in
  15 cases (3.7%). Most filter-pass candidates do not become v1 fills,
  consistent with v1's downstream filtering (eligibility, min net edge,
  max concurrent slots).
- 59 placed-and-cancelled vs 15 placed-and-filled: cancellation rate
  79.7% on the placed subset, consistent with v1's run_live_bot.ps1
  cycle-restart behavior (orders that do not fill within the loop's
  resting window are cancelled and re-placed on the next cycle).

These descriptive observations do not yet support any inference about
filter accuracy. The 120-180 day evaluation per Round 11 v5 closure
recommendation should re-run this join periodically and analyze the
joint distribution against v1 realized P&L by ticker.

## Operator notes

- The join script is idempotent: each run overwrites
  `data/live_trades/shadow/shadow_filter_decisions.jsonl` with a fresh
  build from the current logs.
- The script is a one-shot CLI; v11 did not wire a cron or supervisor.
  If the operator wants regular cross-table refreshes (e.g., nightly),
  add a scheduled task that invokes
  `uv run python -m scripts.v11.join_filter_vs_v1`.
- The output JSONL can be consumed by future analysis without
  re-reading state.json directly. This isolates downstream evaluation
  scripts from v1's state schema.

## What this does NOT do

- Does not modify v1 production code (per operator decision Q2 = "Add
  join script").
- Does not add new logging on the live path. The existing
  v5_filter_shadow_log.jsonl is the data source.
- Does not analyze the cross-table for filter accuracy or P&L
  attribution. That is a downstream analysis, deferred to the 120-180
  day evaluation window.
- Does not change the live filter behavior (LIVE_FILTER_ENABLED=true
  remains active per scripts/run_live_bot.ps1).

## Anti-em-dash and anti-en-dash verification

This report and all code files were post-write greped for U+2014 and
U+2013 with no matches.
