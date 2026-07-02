# v27 METHODOLOGY LOCK: TSA weekly nowcast taker (H1) + perfect-info bound (D1)

**Status: v1 draft, all plan-critic amendments A1-A12 (01-plan-critic.md) folded in.
LOCKED at the git commit including the completed section 0. No settlement-conditioned
P&L before that commit. The v25 lock's execution/fee/verdict machinery carries over
verbatim wherever referenced. Family ~#27; registered: H1 (binding) and D1
(non-binding bound with pre-committed routing); nothing else; no expansion.**

Date: 2026-07-02. Honest prior: H1 ~8-10 percent; P(D1 justifies shadow) ~25-30
percent. TIMELINE ACKNOWLEDGMENT (A12): if D1 routes to shadow, a fundable verdict
needs the week-26 evaluation at the earliest, ~6-9 months total; the operator is
being told this in the session report; no capital before that gate regardless.

## 1. Universe

KXTSAW settled events, close_time [2024-12-01, 2026-06-30]: 87 events, 1,750 markets,
55,735 deduped prints (banked). Strike normalization: floor_strike > 1000 is a raw
count, else millions (units changed mid-series). Settlement truth: Kalshi result.

## 2. As-of discipline

- TSA daily inputs: the VINTAGE series (data/v27/tsa_vintages.json first_value,
  892 days), which K1 proved is the settlement basis (82/82 events reproduce; later
  archive restatements never touch settlement). Today's-page values are used for
  NOTHING.
- SNAPSHOT-PROVEN EVALUABILITY (A7): a print is evaluable ONLY if every required
  published day (Mon-Fri publication rule, noon-ET visibility) has vintage
  first_seen at or before the print time. No posting-schedule inference. Measured
  outcome-blind: 41.3 percent of in-band prints qualify (above the pre-set 40
  percent kill line; the un-provable 58.7 percent are untested territory, stated in
  the verdict).
- BTS schedule term (A8, frozen treatment): sched(d) from the monthly file is
  contaminated by intra-week schedule changes (pre-cancellations 1-3 days out),
  material exactly in disruption weeks. Chosen treatment: H1 uses sched(d) lagged
  s.t. only the SIGN-NEUTRAL component enters: sched_ratio(d) = sched(d) / median of
  the trailing 6 same-weekday sched values, CAPPED to [0.9, 1.1] (frozen), which
  bounds the contamination's reach to 10 percent and is applied identically in every
  week. A standalone H1 pass is explicitly labeled unbankable-without-live-read in
  the verdict (the critic's constraint), routing to stage-1 $0 read like any
  fragile class.
- Holiday factor: fixed federal-holiday calendar; factor for day d in a holiday
  window (day of and +/- 1 day) = the ratio observed at the SAME holiday one year
  earlier (vintage values; if unavailable, factor 1). Frozen.

## 3. Models (frozen)

- Daily prediction: pred(d) = median(last 6 same-weekday vintage values, as-of) *
  clamp(sched_ratio(d), 0.9, 1.1) * hol(d).
- CONTROL: identical with sched_ratio forced to 1 (pure seasonal + holiday).
- D1 (A1): identical pipeline and coefficients; ONLY the inference inputs for
  unpublished days are replaced: pred_D1(d) = pred(d) * (flown(d) / sched(d)) where
  flown = sched - cancelled from BTS actuals (deliberate look-ahead, upper bound,
  beta = 1 frozen). D1 is computed in a separate pass AFTER the H1/control runs are
  complete and written to disk (A4 ordering firewall); no coefficient re-estimation.
- Weekly probability: avg_hat = (sum of published proven days + sum of pred over
  the rest) / 7; P(avg > K) via the empirical distribution of this pipeline's
  weekly-average errors, walk-forward over prior settled weeks (vintage-scored),
  bucketed by number of unpublished days n_unpub in {0-1, 2-3, 4-7}; minimum 15
  error observations in bucket else NO FIRE; sqrt-n_unpub normalization NOT applied
  (weekly errors are not horizon-scaled; frozen as stated).
- NO FIRE if the required vintage inputs are missing (zero-staleness; no fills).

## 4. Execution, fees, fires (v25 machinery + A9/A11)

- Taker prints only; one position per market per ET day (first qualifying print);
  BINDING +3c haircut; REPORTED side-matched +1c; worst-case quadratic fee; band
  p_print in [0.05, 0.95]; both sides.
- Disrupted-week sensitivity (A9): non-binding rerun with 5c haircut on fires in
  weeks whose max daily cancellations (BTS) exceed 1,000.
- Threshold (A11): candidates 0.08 and 0.12 only; 0b computes projected fire counts
  and mean model-conditional net edge at both; rule: 0.08 stands if its projected
  conditional edge >= 8pp, else 0.12. Recorded in 0c before the locking commit.

## 5. Gates

- H1 (A10): floor 40 fires AND 30 fired ISO-week clusters (else UNDERPOWERED-NULL);
  binding CI lower > 0; CONTROL (identical rules, no-schedule model) must NOT clear
  its own floor-plus-CI (else NULL, general-seasonality claim); LOCO; month-block
  guard. Verdict lattice, null wording, no-third-bite per v25 sections 8-10.
- D1 (A2): floor 20 fires AND 8 fired clusters; CI lower > 0 at the NET 8pp mean
  level (mean net P&L >= 0.08 AND CI lower > 0); LOCO survives; month-block guard
  survives. ANY failure = FAMILY DEATH (no shadow, no rescue). D1 passing while H1
  nulls = shadow route ONLY.
- H1 PASS routing (A5): stage-1 $0 live read, then the SAME shadow protocol below
  (its "unbankable without live read" label per A8); never direct to pilot.

## 6. Shadow protocol (A3, pre-committed in full; ONE shadow ever)

If routed: a read-only engine polls TSA page, FlightAware /live/cancelled +
/yesterday, FAA nasstatus, and Kalshi KXTSAW quotes every 30 minutes, self-archiving
all inputs (the as-of record the free historical world lacks), computing the H1
model PLUS a live disruption term (the D1 channel with real as-of data), and logging
hypothetical taker fills at the live ask with the binding haircut convention.
- Week-13 checkpoint (early-kill only): if shadow clustered mean < -5pp with >= 8
  fired clusters, STOP, family dead. No pass action at week 13.
- Week-26 BINDING evaluation: requires >= 20 fired weekly clusters AND cluster CI
  lower bound > 0 net of worst-case fee at REAL logged asks. Pass -> pilot proposal
  to the operator (their explicit approval required; fixed $-risk, contract cap,
  weekly drawdown breaker per charter). Fail -> family dead.
- Week-39 HARD STOP regardless of state. No extensions, no restarts, no second
  shadow. Shadow results are evaluated against these numbers and nothing else.

## 0. Pre-lock record (kill switches run 2026-07-02, outcome-blind)

- K1 (A6) settlement reconciliation: 82/82 fully-vintaged events reproduce settled
  brackets from FIRST-published values; 5 events lack full vintages (excluded from
  the binding set, listed in 0c). The v26-observed "revisions" are archive-page
  restatements occurring AFTER settlement; they never touch this design. KILL
  SWITCH PASSES.
- K2 (A7) evaluability: 41.3 percent (13,192 of 31,931 in-band prints)
  snapshot-proven. Above the 40 percent line. Fires restricted to proven states.
- K3 (A9) print liveness: 87/87 weeks have in-band prints (median 258/week; Fri-Sun
  median 109/week). No print-death.
- 0b fire projection + threshold decision (run 2026-07-02 under the E-edited spec,
  outcome-blind): H1 at 0.08 -> 491 fires / 57 event clusters, mean model-conditional
  net edge 23.5pp, sub-5pp-edge fire fraction 8 percent; at 0.12 -> 392 / 57, 28.2pp.
  A11 DECISION: BINDING THRESHOLD 0.08 (recorded in data/v27/audit_0b_decision.json).
  E13 closure demonstrated: max all-in cost 0.990 < 1.00. E7 recomputed per CLUSTER
  under lock definitions: 57/77 eligible events (74.0 percent) have at least one
  evaluable fire-candidate, above the 60 percent restriction line; the binding set is
  the evaluable-fire set, and the 20 uncovered events are named untested territory.
  D1 projections: beta 0.3 -> 489 / 57; 0.5 -> 490 / 57; 1.0 -> 507 / 57 (floors
  20/8 reachable at every beta).
- 0c ledger (exhaustive; nothing else was computed pre-lock): K1/K2/K3 outputs
  (prelock_kills.py, printed rates and counts only); the 0b numbers above; the BTS
  schedule-includes-cancelled verification (2025-07-01: sched 19,092 with 1,175
  cancelled flags vs Tuesday median 18,378); the universe/print counts in the
  proposal; vintage coverage (892 days, revisions: 6 intra-window, none over 0.5
  percent); v26-banked artifacts reused as documented.

## AMENDMENTS v2 (methodology-critic E1-E15, all binding; full text in
## 03-methodology-critic.md)

- E1/E2: holiday windows without a prior-year factor = NO FIRE (never silent 1.0);
  such days also contribute no error rows; the factor formula is frozen as
  prior-year same-offset vintage value over its own 6-week same-weekday baseline.
- E4/E5: error buckets re-partitioned to n_unpub {3}, {4-5}, {6-7} (a legal fire
  never sees fewer than 3 unpublished days); warmup and exclusions leave ~57-65
  eligible clusters and 0b confirms the floors against that count.
- E6: SUPPORT RULE: if the required error lies outside the bucket's observed error
  support, NO FIRE (interpolation only, no extrapolated tails; the peso-problem
  guard).
- E7: evaluability recomputed per cluster under lock definitions: 74.0 percent
  (above the 60 percent line); binding set = evaluable fires only.
- E8: corrected premise, verified: BTS scheduled rows INCLUDE pre-cancelled flights,
  so schedule-term look-ahead is ~nil; the [0.9, 1.1] clamp is retained as a
  proxy-error bound; a no-clamp sensitivity runs ONLY if H1 does not NULL (it can
  never rescue a null).
- E9/E10: D1 beta grid frozen {0.3, 0.5, 1.0}; FAMILY-DEATH requires ALL THREE to
  fail the A2 gates; D1 reuses each mode's own walk-forward error distribution.
- E11: stated plainly: the D1 gate requires a ~18-28pp mean at realistic cluster
  counts (monster-signal-only, by design); the shadow prior is re-marked to 10-15
  percent.
- E12: shadow protocol restored to A3 verbatim: week-13 checkpoint kills only if
  the shadow cluster-CI UPPER bound < 0 at >= 8 fired clusters; week-26 binding
  evaluation at >= 12 fired weekly clusters with CI lower > 0 AND LOCO surviving;
  if under 12 clusters at week 26, ONE extension to week 39, then the same binding
  evaluation, then stop regardless; fired cluster = a week with >= 1 logged
  hypothetical fill at the REAL logged ask (the ask convention governs live; the
  +3c haircut is backtest-only); the live threshold is the locked 0.08, immutable.
- E13: band-edge closure demonstrated in 0b; sub-5pp-edge fire fraction reported.
- E14: cluster key = the settlement EVENT (one event = one Mon-Sun ET week).
- E15/residuals: close-time uniformity and the 5 no-vintage events' disruption
  profile are reported in the verdict doc; A12 timeline table lives in the session
  report to the operator with their acknowledgment required before any pilot.

*Em-dash audit: clean (verified after write).*
