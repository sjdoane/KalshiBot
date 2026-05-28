# Phase 2 Code Review: Milestone 1 (Parser, Gate, Splits, Scripts)

**Date:** 2026-05-23
**Reviewer:** Code-Reviewer sub-agent (cold walk-in)
**Scope:** Engineering review of the Phase 2 implementation BEFORE any
data is pulled. Methodology lock at [phase-2-methodology.md](phase-2-methodology.md)
is treated as fixed; code must faithfully implement it.
**Verification:** `uv run pytest -q tests/test_politics.py tests/test_slope.py tests/test_bootstrap.py tests/test_gate_phase2.py tests/test_train_test_split.py`
returns 76 passed in 1.77s; no em-dashes found via Grep across src,
scripts/phase_2, and tests.

## Executive summary

The code is **substantially correct and ready for data pull after one
BLOCKING fix and three IMPORTANT fixes**. Locked constants in
`gate_phase2.py` exactly match Section 7 thresholds (C1a=1.2, C1b=1.0,
C2=0.0204, C3=13, C4=3, slippage=0.015, bootstrap=5000/0.95). The
lifetime-straddle filter, price-conditional one-sided-flow rule, isotonic
fit-on-train, and small-trade VWAP gate path are all correctly
implemented. One methodology-required diagnostic (Section 6.1 step 3 / 6.5
per-MARKET slope distribution) is implemented in `slope.py` but never
called from the gate; this is the only methodology-fidelity miss with
operational consequence. The other findings are precision and silent-
drop concerns that could mask real failures in the results report.

## Methodology fidelity

### MISSED: per-market slope distribution diagnostic not called

`src/kalshi_bot/analysis/slope.py:91-124` defines `per_market_slopes`
with the correct `min_trades_per_group=50` default (Section 6.1 step 3:
"for markets with > 50 trades in window"). `slope_distribution_summary`
at lines 127-146 emits the median/q25/q75 dict shape Section 6.5 requires.
**Neither helper is invoked anywhere in `gate_phase2.evaluate`** (verified
via Grep: only test_slope.py and slope.py itself reference these names).
Section 6.5 is explicit: this is a separate diagnostic the gate must
report ("Used by C1 lower-quartile clause" wording is misleading - C1b
uses the per-PARTITION quartile via `np.quantile(slopes, 0.25)` at
`gate_phase2.py:337`, which the code does correctly. The per-MARKET
distribution is the ADDITIONAL diagnostic.).

Severity: IMPORTANT. The per-market diagnostic is what reveals whether
C1 passes because a few high-slope markets pull the partition median up
vs because the regime is broadly present. Without it, a passing gate
verdict cannot be defended against Section 7.1's small-trade-slope-
collapse risk.

### Methodology-text claim "expect 16-18 walk-forward splits"

`phase-2-methodology.md` Section 5.1 states the corpus + step parameters
will yield 16-18 splits. With the literal parameters
(`WALK_FORWARD_TRAIN_DAYS=180`, `WALK_FORWARD_TEST_DAYS=30`,
`WALK_FORWARD_PURGE_DAYS=14`, `WALK_FORWARD_STEP_DAYS=30`,
`FIRST_TRAIN_START=2024-10-01`, `LAST_TEST_END=2026-04-30` at
`src/kalshi_bot/analysis/gate_phase2.py:48-53`) the loop in
`make_walk_forward_splits` produces 12 splits (`(577 - 224) / 30 + 1`).
This is a methodology-text discrepancy, not a code bug; the code matches
the locked parameters. C3 threshold (13/17) implicitly assumes 17 splits;
with only 12 splits, C3 = 13 is unreachable.

Severity: BLOCKING for the C3 criterion (which can never pass if 12
splits is correct). The fix is either (a) shorten step or widen window
in the methodology (out of scope here) or (b) re-derive C3 threshold for
N=12 (`P(>=K of 12 | H0) = sum_{k=K}^{12} C(12,k) * 0.5^12 <= 0.05`
gives K=10). This must be resolved BEFORE data pull, because either
the methodology drift needs to be documented and authorized or the
threshold needs to be recomputed.

Recommended: surface this in operator decision before unlock.

## Silent failures

### Insufficient assertion coverage on per-split skip

`src/kalshi_bot/analysis/gate_phase2.py:178-179`: `_split_metrics` returns
`None` if `len(train) < MIN_TRAIN_SIZE or len(test) < MIN_TEST_SIZE`. The
caller in `run_walk_forward` (lines 262-268) silently drops the split
without logging or counting. If most splits skip, `walk_forward` is short
and C3 fails by virtue of having too few splits, but the report does not
say WHY. Reader sees "5 of 12 splits net > 0" with no flag that 7 splits
were skipped for sample-size.

Severity: IMPORTANT (silent failure that masquerades as a real verdict).
Fix: emit a structlog warning at `gate_phase2.py:267` when `_split_metrics`
returns None, with `split.label`, `len(train)`, `len(test)`, and the
minimums. Surface the skipped-split count in `Phase2GateResult` and the
report.

### Section 8 anti-leakage assertions not implemented

Methodology Section 8 says "scripts/phase_2/run_gate.py emits these as
assertions; failures block the run." All 10 checklist items. Grep on
`scripts/phase_2/run_gate.py` shows NO assert statements anywhere; the
file is purely structlog logging and report rendering. The split logic
in `apply_split_phase2` enforces items 1-3 implicitly via masking, but
items 4 (VWAP windows use only trades <= resolution - 28d), 5 (settle
from Kalshi only), 6 (no feature uses data >= resolution_time), 7
(calibrators fit only on train), 8 (per-market slope only on own
partition), 9 (election tagging uses pre-resolution metadata), 10
(bootstrap on test only) are not actively asserted at run-time.

Severity: IMPORTANT. The methodology explicitly mandates assertions
block the run. The fact that 8 of 10 are TRUE by construction does not
discharge the obligation - the checklist exists to catch regressions.
Fix: add a `_assert_no_leakage(df, splits, results)` helper before
`evaluate` returns; emit a structlog event for each check passing.

### Empty `all_net_small` not flagged in criteria

`src/kalshi_bot/analysis/gate_phase2.py:346-348`: if pooled net_small
array is empty, `pooled_median_net_edge_small` and `pooled_mean_net_edge_small`
remain NaN, so C5 evaluates False (the `not np.isnan(...)` guards on
lines 421-422). Gate fails. Verdict report shows "n/a" for both metrics
under the formatter `_fmt_pct` at `run_gate.py:36-39`. This is correct
behavior, just worth noting that the cause (no eligible markets passed
the filters in any split) is invisible in the report.

Severity: NICE-TO-HAVE. Add a top-line note like "all walk-forward
splits had zero eligible markets after Section 4 filters" when that
condition holds.

### `taker_side` missing or malformed coerces to NaN one-sided flow

`scripts/phase_2/build_dataset.py:93-99`: when `taker_side` column is
absent, `one_sided = float("nan")`. The dataset filter at line 141-148
does NOT require `one_sided_flow_pct` to be non-NaN. NaN flows then
propagate to `_eligibility_mask` at `gate_phase2.py:158`: `one_sided_flow
> ONE_SIDED_FLOW_MAX` is False on NaN, so the conditional clause
(`in_narrow & (flow > 0.65)`) becomes False, so `flow_ok` is True. **NaN
flow markets in the narrow band are KEPT, contrary to the conservative
intent of the filter.**

Severity: IMPORTANT. A real Kalshi trade row should always have
taker_side, but if some don't, missing-data markets will silently slip
through the adverse-selection filter. Fix: in `build_dataset.py` at line
148 add `& df["one_sided_flow_pct"].notna()` to the keep mask, OR add
a defensive `np.nan_to_num(one_sided_flow, nan=1.0)` in
`_eligibility_mask` so missing flow is treated as MAXIMALLY one-sided
(exclude in narrow band).

## P&L and math correctness

### Fee math: round-trip vs single-side at YES=0.30

`src/kalshi_bot/analysis/metrics.py:163-167` defines
`kalshi_maker_fee_per_contract` as `ceil(1.75 * P * (1-P))` cents,
algebraically identical to Section 6.4's `ceil(0.0175 * 100 * P * (1-P))`.
At P=0.30: ceil(1.75 * 0.21) = ceil(0.3675) = 1 cent = $0.01. Then
`kalshi_round_trip_maker_fees` at lines 205-208 returns `2 * 0.01 = $0.02`.
The test at `tests/test_gate_phase2.py:114-125` confirms net edge =
0.20 (gross) - 0.02 (RT fee) - 0.015 (slippage) = 0.165. MATCHES the
methodology.

The methodology Section 6.4 wording "Round-trip maker fee" with the
"doubled for round-trip" qualifier is what is implemented. The
reviewer's brief flags that for "buy-to-hold-to-settle" the round-trip
is arguably wrong (only the entry fee is paid; the settlement is a
zero-fee Kalshi process). The locked methodology says round-trip, so
the code is faithful to the lock. Out-of-scope finding per the brief
constraints; flagging only.

Severity: PASS for fidelity. Out-of-scope methodology comment noted.

### `per_trade_gross_edge` symmetric abs

`src/kalshi_bot/analysis/metrics.py:108-128`: `per_trade_gross_edge`
returns `np.abs(model - market)`. Section 6.3 calls for
`|recalibrated_prob - mid_price_at_T_small|`. MATCHES.

### Slippage applied per-trade as flat 1.5pp

`src/kalshi_bot/analysis/gate_phase2.py:65, 163-172`: SLIPPAGE_ALLOWANCE
= 0.015, subtracted from gross-minus-fees inside `_per_trade_net_edge`.
Section 6.4: "1.5pp slippage allowance for residential retail latency".
MATCHES.

### `_per_trade_net_edge` uses small-trade `market` for fee computation

`src/kalshi_bot/analysis/gate_phase2.py:212`: `_per_trade_net_edge(
cal_small[eligible], raw_small[eligible])`. Fee is computed on `market`
which is `raw_small`. Section 6.4: "computed on mid_price_at_T_small".
MATCHES.

### All-trade diagnostic uses `raw_all` for fees

`src/kalshi_bot/analysis/gate_phase2.py:226`: `_per_trade_net_edge(
cal_all[eligible_all], raw_all[eligible_all])` uses `raw_all` for fees.
The methodology only specifies the SMALL-TRADE case for fee normalization;
the all-trade diagnostic naturally uses its own price for fees. This is
consistent. No issue.

## Leakage paths

### `apply_split_phase2` test boundary uses `>=` not `>`

`src/kalshi_bot/analysis/train_test_split.py:179-183`:

```python
test_mask = (
    (df[close_col] >= split.test_start)
    & (df[close_col] <= split.test_end)
    & (df[open_col] > split.train_end + purge)
)
```

Methodology Section 8: "Every market in test set has resolution_time
AFTER train_end + purge (14 days)." Code uses `>= test_start`, where
`test_start = train_end + purge` (by construction in
`make_walk_forward_splits`). So a market with `close_time == train_end
+ purge` is in test, which is "at or after" not strictly "after". For
to-the-second timestamps this is vanishingly unlikely, but the strict
reading of Section 8 is violated.

Severity: NICE-TO-HAVE (precision). Fix: change `close_col >= test_start`
to `close_col > test_start` in `apply_split_phase2`.

### Train mask correctly uses strict `<`

`src/kalshi_bot/analysis/train_test_split.py:178`:
`train_mask = df[close_col] < split.train_end`. Section 8 item 3:
"Every market in train set has resolution_time BEFORE train_end."
STRICTLY before. MATCHES.

### `leave_one_event_window_out` boolean inversion

`src/kalshi_bot/analysis/train_test_split.py:215-217`:

```python
test_mask = (df[close_col] >= window_start) & (df[close_col] <= window_end)
test = df[test_mask].copy()
train = df[~test_mask].copy()
```

Test = in window, train = NOT in window. The methodology Section 5.2:
"hold out all markets resolving in each window and train on the rest".
MATCHES. Test covered at `tests/test_train_test_split.py:226-242`.

### Isotonic fit ONLY on train

`src/kalshi_bot/analysis/gate_phase2.py:182-184, 192-193`: `cal =
IsotonicCalibrator().fit(train["mid_price_at_T_small"], train["outcome"])`,
then `cal.predict(raw_small)` and `cal.predict(raw_all)` on test arrays.
MATCHES Section 8 item 7.

### Slope fit uses ONLY test partition

`src/kalshi_bot/analysis/gate_phase2.py:201`: `_intercept, slope =
fit_logistic_slope(raw_small, y.astype(int))` where `raw_small` and `y`
both come from the test slice (lines 186-188). MATCHES Section 6.1.

### Election tag uses pre-resolution metadata only

`src/kalshi_bot/data/politics.py:96-104`: tagger checks ticker,
event_ticker, series_ticker, title, subtitle, yes_sub_title, category -
all visible at market_open_time. MATCHES Section 8 item 9.

### Bootstrap pooled on test-partition arrays only

`src/kalshi_bot/analysis/gate_phase2.py:340-355`: `all_net_small` is
concatenated from `r.per_trade_net_edges_small` for each Phase2SplitResult,
each of which was computed in `_split_metrics` from the TEST DataFrame.
No train data enters the bootstrap. MATCHES Section 8 item 10.

## Deviations from plan

### Per-market slope distribution diagnostic missing (covered above under "Methodology fidelity")

Section 6.1 step 3 and Section 6.5 require per-market slope median/q25/q75.
`per_market_slopes` exists but is not called from
`gate_phase2.evaluate` or `run_gate.py`. The report sections (`Pass
criteria`, `Pooled bootstrap`, `Election composition`, `Walk-forward
splits`, `Leave-one-event-window-out`) at `run_gate.py:59-180` do not
include a per-market slope distribution section.

Severity: IMPORTANT.

### C5 all-trade-vs-small-trade comparison not explicitly asserted

Methodology Section 7 C5: "If C5 passes on all-trade VWAP but FAILS on
small-trade VWAP, the strategy is NOT retail-tradable and the gate
FAILS." Current implementation at `gate_phase2.py:420-425` only includes
small-trade C5 in `res.criteria`; the all-trade pooled medians/means at
`res.pooled_median_net_edge_all` and `res.pooled_mean_net_edge_all` are
reported but not compared.

Operationally: if small-trade C5 fails, the gate fails regardless of
all-trade. So the methodology's failure-mode IS caught (gate FAILS).
The deviation is reporting clarity: the diagnostic comparison is not
called out in `criteria`. The `run_gate.py:103-117` cross-check section
states the rule in prose. Acceptable but worth strengthening.

Severity: NICE-TO-HAVE. Fix: add a synthetic criterion
`"C5_small_trade_not_inferior_to_all_trade"` that asserts NOT (all-trade
passes AND small-trade fails). If small-trade fails C5 the gate fails
anyway; this diagnostic surfaces WHY (retail-untradable vs no edge at
all).

### Skipped-split count not surfaced

Covered above under "Silent failures": when `_split_metrics` returns
None for sample-size reasons, the report's "n_splits_net_positive_small
of len(walk_forward)" hides the skip count.

Severity: IMPORTANT.

## Other issues

### Style consistency

The Phase 2 modules follow the same conventions as Phase 1 (structlog,
pathlib, parquet round-trips, dataclass-with-defaults result structs).
Type hints are present throughout. `from __future__ import annotations`
is consistently applied.

### Test coverage gaps

- No test verifies `_split_metrics` returns None when train/test below
  the sample-size minimums (the silent-skip path).
  Recommend: add a test that constructs a tiny DataFrame and asserts the
  None return + (after the fix above) the structlog warning.
- No test verifies that NaN `one_sided_flow_pct` does NOT slip through
  the narrow-band filter (the silent NaN-as-pass issue documented above).
- No test verifies the "C5 passes on all-trade but fails on small-trade"
  branch produces gate FAIL. The two C5 paths are currently independent.
- `tests/test_gate_phase2.py:128-139`
  (`test_evaluate_passes_with_strong_compressed_regime`) only asserts
  C1a and C2 pass; it does not assert the overall `res.passes` is True
  for the strong-signal case. Hard to do cleanly because the synthetic
  data has random outcomes; but a parametrized seed sweep with majority-
  pass assertion would harden this.

### Test naming and class-balance test

`tests/test_slope.py:86-94`: `test_fit_logistic_slope_requires_class_balance`
correctly verifies all-zeros and all-ones inputs raise ValueError. The
gate's `_split_metrics` catches this ValueError and sets `slope = NaN`
(lines 200-203). Path is correct end-to-end.

### Hardcoded path constants

Constants like `OUTPUT_DIR = Path("data/phase2")` (discover script line
30), `MARKETS_DIR = Path("data/phase2/markets")` (fetch trades line 39),
`OUT_PATH = PROCESSED_DIR / "politics_phase2_dataset.parquet"`
(build_dataset line 47) are relative to the cwd, not the project root.
A script run from elsewhere would write to the wrong location. Phase 1.5
has the same pattern; consistency is OK but a `Path(__file__).parents[2]
/ "data" / "phase2"` would be more robust. NICE-TO-HAVE.

### Secrets handling

`scripts/phase_2/discover_politics_series.py:46-49`,
`scripts/phase_2/fetch_politics_markets.py:140-144`,
`scripts/phase_2/fetch_politics_trades.py:180-185` all use
`load_settings()` and `KalshiClient(settings)`. No hardcoded keys, no
PEM contents in code. Outputs are under `data/phase2/`. CORRECT.

### Em-dashes

Grep across `src/kalshi_bot`, `scripts/phase_2`, and `tests` returns no
matches for U+2014 or U+2013. CORRECT.

## Recommended fixes before data pull

**BLOCKING (must fix before data pull):**

1. **Reconcile C3 threshold with actual walk-forward split count.**
   `gate_phase2.py:48-53` parameters produce 12 splits, not 17. C3 = 13
   of 12 is unreachable. Either the methodology constants need updating
   (out of scope; requires operator authorization) or the C3 threshold
   needs recomputation for N=12 (binomial null with alpha=0.05 gives
   `>= 10 of 12`). DO NOT proceed without resolving.

**IMPORTANT (fix before data pull or accept documented bias):**

2. **Wire per-market slope distribution diagnostic into the report.**
   Add a `per_market_slope_summary` field to `Phase2GateResult`, populated
   by calling `per_market_slopes(test, price_col="mid_price_at_T_small",
   outcome_col="outcome", group_col="series_ticker",
   min_trades_per_group=50)` then `slope_distribution_summary(...)` in
   `_split_metrics`. Add a corresponding section to the report.

3. **Emit a structlog warning when `_split_metrics` returns None**, and
   surface `n_splits_skipped` in `Phase2GateResult` + the report.
   Without this, a low-sample failure looks identical to a real edge
   failure.

4. **Defensive coverage for NaN `one_sided_flow_pct`.** Either filter
   NaN rows out at `build_dataset.py:148` or treat NaN as "maximally
   one-sided" in `gate_phase2._eligibility_mask`. Current behavior
   silently bypasses the adverse-selection filter on missing-data
   markets.

5. **Implement Section 8 anti-leakage assertions in `run_gate.py`.**
   Add `_assert_no_leakage` that walks the 10 checklist items and emits
   a structlog event per item; raise on any violation. Currently NONE of
   the 10 are actively asserted at run time.

**NICE-TO-HAVE (track separately):**

6. Tighten `apply_split_phase2` test mask from `close_col >= test_start`
   to `close_col > test_start` for strict Section 8 compliance.

7. Add an explicit "C5 all-trade-vs-small-trade comparison" criterion
   (synthetic FAIL when all passes and small fails). The current
   behavior is correct end-to-end; this would just make the report read
   the right WHY.

8. Add tests for (a) `_split_metrics` returns None on undersized splits,
   (b) NaN one_sided_flow rejection, (c) overall `res.passes` True
   under strong-signal synthetic data.
