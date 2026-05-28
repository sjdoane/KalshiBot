# Round 15c: Cancel-on-drift wiring summary

**Date:** 2026-05-27 (overnight extension)
**Author:** Round 15c orchestrator
**Status:** WIRED, default OFF, 10 wiring tests + 11 monitor tests pass (151 total)

## What this change does

Adds an opt-in adverse-selection safety net to v1's live loop. When the
operator passes `--cancel-on-drift`, every loop iteration the bot now:

1. Builds a `RestingOrderView` for each ticker in `state.resting`.
2. Pulls `/markets/{ticker}/orderbook` for each unique ticker and computes
   the YES mid in cents.
3. Calls `evaluate_resting_orders` from the existing
   `kalshi_bot.risk.adverse_selection_monitor` module to get a list of
   `CancelRecommendation`s.
4. For each recommendation, sends `DELETE /portfolio/orders/{order_id}` and
   moves the local LiveOrder from `state.resting` to `state.closed` with
   status `LIVE_CANCELLED`.
5. Logs each cancellation with `adverse_selection_cancel` and posts a
   single Discord summary message for the loop.

The default behavior is UNCHANGED: without the `--cancel-on-drift` flag,
the bot's firing and reconcile loop is exactly the same as before Round
15c. v1 on $32 will not see any new cancel behavior unless the operator
restarts with the new flag.

## Mechanism rationale

Live observation 2026-05-27 (`scripts/v10a/analyze_v1_live.py`) found a
mean post-fill mid drift of -4.93pp across 15 still-open v1 fills, with
9 of 15 drifting AGAINST the maker bid. This is the classic
favorite-maker adverse-selection failure mode: the market moves before
the maker quote can be cancelled, and the maker fills near the worst
price.

Cancel-on-drift is the cheapest defensive response. It does not change
v1's fire criteria (which prefixes / prices the bot is willing to take);
it only retracts a resting bid AFTER the live mid has visibly drifted
past a configurable threshold.

The CLI flags expose the three knobs in the existing
`AdverseSelectionConfig`:

- `--cancel-on-drift` (bool, default off): master switch
- `--drift-threshold-cents N` (default 3): cents of adverse drift that
  triggers a cancel
- `--drift-min-age-minutes N` (default 15): minimum order age before
  drift cancellation activates (avoids cancelling on transient bounces)

## Where the wiring lives

| Layer | File | Function / symbol |
|---|---|---|
| Pure logic | `src/kalshi_bot/risk/adverse_selection_monitor.py` | `evaluate_resting_orders`, `AdverseSelectionConfig`, `RestingOrderView`, `CancelRecommendation` (BUILT in Round 15b) |
| Live actuation | `src/kalshi_bot/strategy/live_order_manager.py` | `LiveOrderManager.reconcile_adverse_selection`, `_fetch_orderbook_mid_cents` (NEW Round 15c) |
| CLI surface | `scripts/paper_trade_favorite.py` | `--cancel-on-drift`, `--drift-threshold-cents`, `--drift-min-age-minutes`; plumbed via `one_loop_favorite_live(adverse_selection_cfg=...)` (NEW Round 15c) |
| Tests | `tests/test_adverse_selection_wiring.py` | 10 new tests covering wiring; existing `tests/test_adverse_selection_monitor.py` covers pure logic (11 tests) |

`LiveOrderManager.reconcile_adverse_selection` is called inside
`one_loop_favorite_live` right after `cancel_stale_resting`. The call is
guarded by `if adverse_selection_cfg is not None` so it does nothing
when the flag is off.

The orderbook parser uses the same `orderbook_fp.yes_dollars` /
`orderbook_fp.no_dollars` shape that `scripts/v10a/live_spread_probe.py`
already validated against the live Kalshi API. A one-sided book (no
NO levels, or no YES levels) returns `None` and the ticker is skipped;
no false-positive cancellations on illiquid books.

## Test coverage (Round 15c additions)

`tests/test_adverse_selection_wiring.py`:

1. `test_no_op_when_no_resting_orders`: empty state, zero API calls.
2. `test_cancel_fires_on_adverse_drift`: 5c drift past 3c threshold, cancel fires.
3. `test_no_cancel_when_drift_within_threshold`: 2c drift below 3c, no cancel.
4. `test_no_cancel_for_young_order`: 5-minute-old order with 10c drift, no cancel.
5. `test_multiple_orders_processed_independently`: three orders, only the drifted one is cancelled.
6. `test_orderbook_fetch_failure_does_not_crash`: first GET raises, second succeeds, loop continues.
7. `test_orderbook_with_one_sided_book_skipped`: one-sided book returns None mid, no cancel.
8. `test_cancel_api_failure_leaves_order_resting`: DELETE failure, order stays resting.
9. `test_custom_threshold_applied`: wider threshold suppresses cancel.
10. `test_state_persists_cancellation`: cancel saved to disk, reload sees closed state.

Full suite per the brief: `tests/test_market_scanner.py
tests/test_adverse_selection_monitor.py tests/test_adverse_selection_wiring.py
tests/test_favorite_maker.py tests/test_order_manager.py
tests/test_live_order_manager.py tests/test_kill_triggers.py
tests/test_drawdown.py tests/test_kalshi_client.py tests/test_auth.py`
collects **151 tests, 151 pass** (Round 15b baseline 141 pass; added 10
wiring tests).

## Operator restart command

The operator restarts v1 manually. The minimal command that turns the
new safety net on while preserving the existing Round 15b allowlist and
denylist is:

```
.venv-kronos\Scripts\python.exe -m scripts.paper_trade_favorite \
  --mode live --yes-i-authorize --cadence 900 \
  --allowlist --expanded-denylist --min-minutes-to-close 60 \
  --cancel-on-drift --drift-threshold-cents 3 --drift-min-age-minutes 15
```

The `--allowlist`, `--expanded-denylist`, and `--min-minutes-to-close 60`
flags continue Round 15b's protective scoping. The three new flags add
cancel-on-drift on top, without changing firing behavior.

If the operator wants to test the new flag in isolation first (without
also turning on the allowlist), the minimal new-flag-only addition is
`--cancel-on-drift`.

## What is NOT changed

- v1's firing logic (which markets it bids on, at what price). The
  scanner and pricing modules are not touched in Round 15c.
- The PaperOrderManager (paper mode). Cancel-on-drift only operates on
  real Kalshi orders.
- State schemas. `LiveOrder`, `LiveState`, and the on-disk JSON layout
  are byte-identical to Round 15b.
- The `evaluate_resting_orders` function itself (already shipped and
  tested in Round 15b).
- The W1 / EXPANDED denylist / PERSIST allowlist constants.
- The kill triggers, drawdown thresholds, and preflight checks.

## What additional analysis was wired

`scripts/v10a/analyze_v1_live.py` gained a "PER-FILL REALIZED P&L" block
that runs once any of v1's fills settle. It reports per-fill P&L,
total realized, mean per-fill, and a per-prefix breakdown tagged with
PERSIST / DENYLIST / OTHER. Until at least one fill settles, the block
prints a "no settled fills yet" line and continues to the existing
adverse-selection mid-drift check.

## Em-dash audit

```
src/kalshi_bot/strategy/live_order_manager.py: em=0, en=0
scripts/paper_trade_favorite.py: em=0, en=0
tests/test_adverse_selection_wiring.py: em=0, en=0
scripts/v10a/analyze_v1_live.py: em=0, en=0
research/v10a/18-cancel-on-drift-wiring.md: em=0, en=0
```
