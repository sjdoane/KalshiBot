# Code Review: Phase 2 Milestone 2 (Sports Pivot + Phase 3 Scaffolding)

**Reviewer:** Code-review sub-agent (walked in cold)
**Date:** 2026-05-23
**Scope:** Sports x Long-Horizon analysis modules and Phase 3 paper
trading scaffolding produced during the autonomous run after the
Politics x H mechanical fail.
**Test state observed:** `uv run pytest -q` returned 219 passed in 7.08s
(autonomous run reported 214; the delta is presumably the additional
test_polymarket.py tests counted into the same suite).

## Executive summary

The autonomous run executed faithfully against the locked sports
methodology and produced category-agnostic Phase 3 scaffolding that
matches the design doc. The five locked sports criteria are encoded
correctly with the methodology-critic revisions applied
(`PASS_C2_GROSS_EDGE = 0.0223`, `MIN_TEST_SIZE = 30`,
`MIN_LIFETIME_DAYS = 30`, `MIN_LEAGUE_SAMPLE = 50`, C3 demoted to
bootstrap-based gate with N_leagues >= 3 floor). The pooled bootstrap
gate is wired in and the leagues fallback was removed cleanly.

However the Phase 3 entry point has a hard import bug that will crash
on startup. The fix is one line. The order_manager P&L math is
correct but its inline comment contradicts the code. Several silent-
failure paths exist around the live API surface, all in the
"untested-with-prod-API" perimeter. Test coverage for `paper_trade`
top-level orchestration is empty. None of the deviations require
methodology re-lock; they are engineering polish issues to fix before
any paper trading begins.

Severity tallies: 1 BLOCKING (import bug), 6 IMPORTANT, 5 NICE-TO-HAVE.

## Methodology fidelity issues

All locked sports criteria match the post-critic methodology where
verified.

1. **`gate_sports.py:88` C2 constant.** `PASS_C2_GROSS_EDGE = 0.0223`.
   Matches `sports-longhorizon-methodology.md` Section 7 C2 (revised
   per critic finding 7 from 0.0446 down to 1x Becker sports). The
   docstring at lines 9-10 of the same file is STALE: it still says
   ">= 4.46pp (2x Becker sports 2.23pp)". STATUS: code correct, doc
   stale. Severity: IMPORTANT (misleading future-reader).
2. **`gate_sports.py:70` `MIN_TEST_SIZE = 30`**. Matches methodology
   5.1 BLOCKING fix 2. Pre-committed and exercised in `_split_metrics`
   skip rule at line 184. Diagnostic counted in
   `n_splits_skipped_sample_size`.
3. **`gate_sports.py:98` `MIN_LEAGUE_SAMPLE = 50`**. Matches
   methodology 5.2 (critic finding 6, reduced from 100). Eligible
   leagues computed at `run_leagues` line 326. C4 also requires
   `n_leagues_evaluated >= PASS_C4_MIN_LEAGUES_POSITIVE = 3` per the
   criteria dict line 453-455 ("no 2-of-2 fallback"). Matches.
4. **`gate_sports.py:60` test_window = 60d, step = 60d**. Matches
   methodology 5.1 (delta from Phase 2's 30d).
5. **`gate_sports.py:284-288` train mask uses `market_close_time <
   train_end`**. This corresponds to anti-leakage checklist item 2
   ("Every market in train set has resolution_time BEFORE train_end").
   Lifetime-straddle filter correctly NOT applied. Matches Section 5.1
   delta.
6. **`gate_sports.py:449-452` C3 = bootstrap CI lower bound > 0**.
   Matches Section 7 C3 BLOCKING fix 1. The diagnostic per-split count
   (`n_splits_net_positive_small`) is retained but not in the criteria
   dict.
7. **`build_dataset.py:34` `MIN_LIFETIME_DAYS = 30`** matches Section
   2.2 long-horizon filter (revised from 60 to 30 per critic finding
   8).
8. **`build_dataset.py:31` `MIN_TRADES_IN_WINDOW = 20`** matches
   Section 4 per-market minimum.
9. **Resolution-time-purge sensitivity check is NOT implemented**
   in `gate_sports.py`. Methodology Section 5.1 IMPORTANT finding 4
   marks it as a sensitivity check (NOT gate). The autonomous run
   shipped without it. Severity: IMPORTANT (the methodology says
   "in addition to the locked split, also report results under the
   stricter constraint"; the report cannot honestly distinguish
   leakage-driven pass from real signal without it).
10. **Single-name vs broad-based segment-report NOT implemented**
    in `gate_sports.py` or `run_gate.py`. Methodology Section 7
    IMPORTANT finding 5 ("Tag each market by parent-event sibling-
    count; report C3-equivalent separately per segment"). The dataset
    builder computes `is_binary_market` but no segment tag, no
    per-segment metric. Severity: IMPORTANT.
11. **Within-cluster shuffle bootstrap diagnostic NOT implemented**.
    Methodology Section 12 marks this as NICE-TO-HAVE 9. Acceptable
    to skip; flag for follow-up.

## Silent failure paths

1. **`paper_trade.py:44` import will crash at startup.** The script
   imports `from kalshi_bot.alerts.discord import send as send_discord`
   but the module only exports `post` (`alerts/discord.py:31`). First
   invocation of `python -m scripts.paper_trade` will raise
   `ImportError`. There is no test exercising this import path because
   no `tests/test_paper_trade.py` exists. Severity: BLOCKING. Fix:
   change to `from kalshi_bot.alerts.discord import post as
   send_discord` (one line).
2. **`market_scanner.py:113` `series_category=config.category`**
   parameter name is unverified against Kalshi `/markets` endpoint.
   The `/series` endpoint uses `category=` (see
   `discover_series.py:21`); `/markets` may use `series_category` OR
   `category` OR neither. If wrong, the call returns all open markets
   regardless of category and the bot quotes any open market that
   passes the mid-band filter. Severity: IMPORTANT. Fix: smoke-test
   against demo env before paper trading.
3. **`paper_trade.py:67-90` `one_loop` swallows scan failures
   silently.** If `scan()` raises, the exception propagates up to the
   `while True` loop's `except Exception`, but a partial scan that
   returns empty produces `no_candidates_this_loop` and continues. If
   Kalshi changes the schema and `parse_snapshot` rejects every row,
   the bot will log "no candidates" indefinitely with no alert.
   Severity: IMPORTANT. Fix: emit Discord warning when N consecutive
   empty scans exceed a threshold (e.g., 4).
4. **`paper_trade.py:194` empty calibrator dataset will produce a
   degenerate isotonic fit.** `IsotonicCalibrator().fit(df["..."])`
   on an empty `df` will raise or produce an all-NaN model. No
   pre-check on `len(df)`. Severity: IMPORTANT.
5. **`market_scanner.py:86-89` lifetime parse failure silently
   skips the market** (`continue` on `TypeError, ValueError`). If
   Kalshi changes the time format, the bot just sees fewer
   candidates without warning. Severity: NICE-TO-HAVE (add a counter
   logged at scan end).
6. **`order_manager.py:88-95` corrupted state.json raises and
   prevents PaperOrderManager init.** This IS the correct behavior
   (fail loudly per CLAUDE.md), but there is no recovery path: the
   bot will refuse to start until the file is manually deleted /
   repaired. Document this in the runbook. Severity: NICE-TO-HAVE.
7. **`sports/fetch_trades.py:135` no validation that
   `/historical/cutoff` returned `trades_created_ts`.** If the
   endpoint shape changes, raises `KeyError` instead of a helpful
   message. Severity: NICE-TO-HAVE.

## P&L math correctness

P&L math in `order_manager.settle_at_resolution` (lines 217-251) is
correct. Verified against tests `test_settle_at_resolution_yes_wins`
and `test_settle_at_resolution_yes_loses`:

- YES side, outcome 1 (YES wins): `payoff = 1.0 - filled_price`. Net
  per contract = `payoff - 2 * maker_fee`. At filled_price=0.30,
  contracts=10: 10 * (0.70 - 0.02) = 6.80. Matches test expectation.
- YES side, outcome 0 (YES loses): `payoff = 0 - filled_price`. At
  filled_price=0.30, contracts=10: 10 * (-0.30 - 0.02) = -3.20.
- NO side, outcome 0 (NO wins, YES loses): code computes
  `payoff = 1.0 - (1.0 - filled_price) = filled_price`. Matches
  spec ("payoff = filled_price").
- NO side, outcome 1 (NO loses): payoff = `0 - (1.0 - filled_price)`
  = `filled_price - 1.0`. Negative, sane.

**Inline comment contradicts code at `order_manager.py:234-236`.**
Comment says "Subtract maker fee (single-side; settlement is fee-
free but we conservatively account for it..." but the next line
applies `2.0 * kalshi_maker_fee_per_contract(...)` (round-trip).
The CODE matches the methodology lock (round-trip per
sports-longhorizon-methodology Section 1), so this is intentional
conservatism. The comment should be corrected to either justify the
round-trip choice or be removed. Severity: NICE-TO-HAVE (comment
misleads only future maintainers).

**Worth flagging for operator:** For a buy-and-hold-to-settle
strategy, the realistic fee is single-side, not round-trip. The
methodology lock chose round-trip for conservative backtest
accounting. Once paper trading runs, the gap between modeled net
edge (round-trip fee) and realized net edge (single-side fee) will
be roughly `kalshi_maker_fee_per_contract(price)` per contract,
i.e., 1-2 cents per $1 of notional. Realized P&L should
SYSTEMATICALLY beat the modeled net edge by this amount. Document
this as an expected discrepancy in the paper-trading runbook.

**Expected-net-edge math in `pricing.py:71-93`** verified via
`test_expected_net_edge_yes_side`, `test_expected_net_edge_no_side`,
`test_expected_net_edge_negative_when_no_edge`. Correct.

**`pricing.decide` target-price cap** (`pricing.py:124, 130`)
implements "cap target to avoid paying more than recalibrated value
minus fee + slippage buffer". The cap uses `round_trip_maker_fee` at
the target_price itself, which creates a soft circular dependency
(target depends on fee which depends on target), but maker fees are
slow functions of price so the iterate converges in one pass. Sane.

## Concurrency and persistence

1. **`order_manager.py:82` PaperOrderManager is not thread-safe.**
   The docstring explicitly warns "Operator should run only ONE
   paper-trade process at a time." The runbook
   (`phase-3-runbook.md`) does not echo this warning. Severity:
   IMPORTANT. Fix: add a clear "DO NOT run multiple paper_trade
   processes against the same state.json" line in the runbook
   "Starting paper trading" section.
2. **`order_manager.py:110-124` `_save()` is atomic but `_load()`
   on next call may race a concurrent write** even by the same
   process if a settlement and a place-order happen close in time.
   The current loop is sequential, so this is theoretical. NICE-TO-
   HAVE: add `fcntl`-style file locking for defense-in-depth.
3. **`drawdown.py:101-108` history list grows unbounded.** Every
   call to `update()` appends. For a 15-minute cadence over 14 days,
   that's ~1344 records, fine. For a long live deployment, periodic
   truncation or rotation should be considered. Severity: NICE-TO-
   HAVE.
4. **`paper_trade.py:215-225` `while True` loop has no graceful
   shutdown handler.** Ctrl-C will interrupt mid-loop, potentially
   between `place_paper_order` and the subsequent reconcile. Each
   `place_paper_order` saves immediately (`_save()` at line 156), so
   state is consistent at the order level. Acceptable for paper
   mode. For live mode this needs a SIGINT handler. Severity:
   NICE-TO-HAVE.

## Test coverage gaps

1. **`paper_trade.py` has zero tests.** No `tests/test_paper_trade.py`
   exists. The import bug from Silent Failure 1 would have been
   caught by any smoke test, including a one-line
   `from scripts.paper_trade import one_loop`. Severity: IMPORTANT.
   Fix: add at minimum an import smoke test and a `one_loop` test
   with mocked client + calibrator + state path.
2. **`order_manager.reconcile_fills` is tested for the
   happy-path YES and NO single-trade cases**
   (`test_reconcile_fills_yes_side`, `test_reconcile_fills_no_side`)
   but not for the edge cases:
   - Multiple trades in the same batch; first matches, second is
     ignored (`break` at line 200).
   - Trade list with mixed `yes_price` and `yes_price_dollars`
     formats simultaneously.
   - Filled order persists across `PaperOrderManager` reinstantiation
     (state.json round-trip with `OrderStatus.PAPER_FILLED`).
   Severity: NICE-TO-HAVE.
3. **`gate_sports.py` test coverage for the bootstrap C3 path.**
   `test_c3_uses_pooled_bootstrap_gate` confirms the criteria-dict
   KEY exists but does not test the gate logic across the boundary
   (e.g., a dataset where pooled mean > 0 but CI lower bound just
   touches 0; or pooled mean = 0). The bootstrap is exercised only
   indirectly through `test_evaluate_passes_with_strong_signal`.
   Severity: NICE-TO-HAVE.
4. **`market_scanner.scan` not tested.** Only
   `parse_snapshot` and `filter_candidates` are tested. The
   `scan()` function (which calls Kalshi paginate) has no integration
   test. The `max_pages=5` cap and the `series_category` param are
   both unverified. Severity: IMPORTANT for pre-paper-trading
   confidence.
5. **`drawdown.py` test coverage for monotone state transitions**
   (warn -> halve -> pause -> halt without recovery) is missing. The
   existing tests reset bankroll between each threshold check. The
   `action_changed` audit logic at lines 99-100 needs a multi-step
   test. Severity: NICE-TO-HAVE.
6. **`gate_sports.py` LOCO test (`test_evaluate_leagues_get_evaluated`)
   only asserts `n_leagues_evaluated >= 1`** (line 131). Methodology
   requires N >= 3 for C4 to even be considered. The test does not
   verify that the gate correctly fails with N=2. The
   `test_c4_fails_when_less_than_three_leagues` does test this; OK.

## Phase 3 design vs implementation deltas

`phase-3-design.md` specifies five new modules (`discovery.py`,
`pricing.py`, `order_manager.py`, `drawdown.py`, `runtime.py`) and
one entry point (`scripts/paper_trade.py`). Implementation:

1. **`discovery.py` renamed to `market_scanner.py`.** Functionally
   the same role per the design doc, but the doc lists two
   functions: `list_open_politics_markets(client)` and
   `apply_phase2_filters(df)`. The implementation has `scan(client,
   config)` and `filter_candidates(markets, config)`. The split is
   sane and the design clearly says "category-agnostic ...
   reparameterized rather than rewritten". Acceptable rename.
2. **`runtime.py` was NOT created.** The design has runtime.run() as
   "Main loop entry point". Implementation puts the main loop
   directly in `scripts/paper_trade.py` `main()` at lines 166-227.
   Functionally equivalent; cleaner to inline given the small
   scope. Acceptable.
3. **State file format** is JSON (matches design "SQLite DB or JSON
   file"). Atomic writes via tempfile + rename
   (`order_manager.py:121-124`). Matches design.
4. **PAPER mode simulated-fill rule** matches design ("if any taker
   trade in the market matches or crosses our paper-bid price within
   the order's lifetime, mark as filled at our bid price"). See
   `order_manager.reconcile_fills` lines 197-202.
5. **Drawdown thresholds.** Design says 10/15/25 percent for
   DAILY/WEEKLY/TOTAL. Implementation in `drawdown.py:57-60` uses
   5/10/15/25 (warn at 5%, halve at 10%, pause at 15%, halt at 25%).
   These match `config.py` (DAILY_DD_HALT_PCT=0.10, WEEKLY=0.15,
   TOTAL=0.25) with an added 5% warn. The reframing from
   daily/weekly/total to a single drawdown-from-HWM is a
   simplification (the design tracks drawdown windows; the
   implementation only tracks HWM). Acceptable simplification for
   paper trading but a follow-up should reconcile this with the
   methodology if live deployment is approved. Severity: IMPORTANT.
6. **Discord alerts.** Design lists "Start of session, Each fill,
   End of session, Drawdown threshold breaches". Implementation has
   start (`paper_trade.py:211`), fill (line 113), drawdown halt
   (line 86), placement (line 158). Missing: end of session. For an
   infinite-loop script this is conceptually fine, but the SIGINT
   handler gap (see Concurrency 4) means there's no graceful
   close-and-alert sequence. Severity: NICE-TO-HAVE.

## Recommended fixes

### BLOCKING (must fix before any paper trading)

1. **Fix `paper_trade.py:44` import**: change `from
   kalshi_bot.alerts.discord import send as send_discord` to `from
   kalshi_bot.alerts.discord import post as send_discord`. Add a
   smoke test that imports the module to prevent regressions.

### IMPORTANT (should fix before paper trading begins)

2. **Update `gate_sports.py` docstring lines 9-10** to reflect the
   actual C2 = 2.23pp threshold (currently still says 4.46pp).
3. **Implement the resolution-time-purge sensitivity check** in
   `gate_sports.py` and `run_gate.py` per methodology Section 5.1
   IMPORTANT finding 4. Without it, a leakage-driven pass cannot be
   distinguished from a real signal.
4. **Implement single-name vs broad-based segment-report** per
   methodology Section 7 IMPORTANT finding 5. Tag markets via
   `count_contracts_per_event(df) >= 5`; report pooled mean net
   edge per segment in `sports-results.md`.
5. **Verify `market_scanner.py:113` `series_category` parameter
   name** against Kalshi's `/markets` endpoint on demo env. If wrong,
   the bot quotes all categories.
6. **Add tests for `scripts/paper_trade.py`**: at minimum an import
   smoke test + a `one_loop` test with mocked dependencies.
7. **Document round-trip vs single-side fee gap** in the
   `phase-3-runbook.md` so the operator knows realized paper P&L
   will systematically beat the modeled net edge by the maker fee.
8. **Add "DO NOT run multiple paper_trade processes" warning** to
   the runbook "Starting paper trading" section.
9. **Reconcile `drawdown.py` HWM-based thresholds with the
   methodology's daily/weekly/total framing** if live deployment is
   approved.

### NICE-TO-HAVE

10. **Fix `order_manager.py:234-236` comment** to match the code
    (round-trip is intentional per methodology).
11. **Add SIGINT handler** in `paper_trade.py` main loop for clean
    shutdown.
12. **Bound `drawdown.py` history list** with periodic truncation.
13. **Add scan-failure-counter Discord warning** when N consecutive
    empty scans exceed a threshold (defends against silent API
    schema drift).
14. **Add per-segment, multi-trade-format, and round-trip-persistence
    tests** to `test_order_manager.py`.

## Closing assessment

The autonomous run made the correct methodology pivot, applied every
critic finding pre-data, and built scaffolding that adheres to the
locked plan with one BLOCKING import bug. The methodology fidelity is
high. The code is clean and the tests are sound where present. The
main risk is the gap between paper-trading scaffolding and the
methodology's sensitivity-check requirements; without
resolution-time-purge and segment reporting, a gate PASS cannot be
fully defended as non-leakage-driven. Both are mechanical additions
that should land before any paper-trading session begins.

No deviations require strategy re-lock. All issues are engineering
polish or methodology completeness items that fit cleanly into a
pre-paper-trading checklist.
