# v25 METHODOLOGY LOCK: AAA retail-gas ladder taker (wholesale pass-through)

**Status: v3, all plan-critic amendments (01-plan-critic.md A1-A7) and all methodology-
critic edits (03-methodology-critic.md E1-E15) incorporated. This document is LOCKED at
the git commit that includes the completed section 0 audits and ledger. No settlement-
conditioned P&L is computed before that commit. Every decision constant is frozen here;
thresholds derive from fee arithmetic, never from price-vs-outcome inspection.**

Date: 2026-07-02. Hypothesis ledger: hypothesis FAMILY #25 of the project (11+ NULLs,
1 phantom, 7 live capture-phantom confirmations). Registered hypotheses this round: H1
and (conditional on the 0b feasibility rule) H2. No expansion after data.

## Honest prior and escape claim (E14, restoring A1)

Prior: ~10 percent, at the plan critic's re-marked level, on the kill line but above it.
The escape claim, in its corrected frontier form: prior capture-phantom kills were cases
where the retail model sat strictly BELOW the public frontier (naive NWP vs the NBM
consensus the MM also had; naive lognormal vs the options/VIX surface). For AAA retail
gas the public frontier IS a textbook distributed-lag pass-through regression on public
wholesale data, and this project can implement that frontier in full. The test therefore
asks something genuinely new for this venue: does the Kalshi ladder sit AT the public
frontier for a non-tradeable administered series, or below it? A NULL is evidence the
ladder is at the frontier (of THIS spec; see E11 wording rule); a PASS is evidence it is
not. Design-level contamination is owned in section 7's honesty note.

## 0. Pre-lock audits and ledger (kill switches; filled before the locking commit)

### 0a. Settlement-key audit (A2, E12a, E13)

Question: does a market closing 03:59Z on UTC date D settle on the AAA print of date D
(published ~3-5am ET on D) or of D-1? Method: for every settled market where the
reconstructed AAA values of D-1 and D straddle the strike, compare the Kalshi result to
each candidate key; cross-check the no-straddle consistency rate for both keys.
FIREWALL (E12a): the audit script outputs ONLY per-market booleans (consistent under
key D / key D-1) and aggregate rates; no prices, no trade joins, no P&L-like quantity.
Decimal rule (E13): the parser preserves full AAA display precision (3 decimals through
2025, 4 from 2026); any audit mismatch is first re-checked under both precisions; ONE
mismatch fully explained by display precision may pass; any UNEXPLAINED mismatch =
ambiguity = KILL before data.

RESULT (2026-07-02): KEY = D, DECISIVE, NO AMBIGUITY. 698 settled markets testable
(both AAA(D-1) and AAA(D) present): key D consistency 698/698 = 100.0 percent; key D-1
663/698 = 95.0 percent. All 35 straddle (decisive) markets agree with key D, 0 of 35
with D-1. Near-tie precision flags: 23 (all consistent under key D at full precision;
no mismatch to explain). The kill switch PASSES; settlement = the AAA print of the UTC
close date D. This also independently validates the Wayback reconstruction (698
markets consistent at 100 percent).

### 0b. Power, fire-rate, and threshold decision (A5, E8)

Cluster-CI arithmetic: with n_c fired clusters and per-fire net-P&L cluster SD sigma_c
~ 0.40, the 95 percent CI half-width is ~1.96*0.40/sqrt(n_c): n_c=30 -> ~14pp; 60 ->
~10pp; 90 -> ~8pp. HONEST CEILING: this screen can only validate a LARGE (roughly
8-14pp mean net) edge; a true 3-6pp edge is undetectable here and will correctly come
out UNDERPOWERED or NULL; accepted tradeoff at this bankroll.

OUTCOME-BLIND inputs permitted for this audit: trade print counts, price-band
histograms per cluster, and the model-vs-print divergence distribution (P_model needs
only AAA + FRED; prints are execution metadata; Kalshi results are never touched).

THRESHOLD DECISION RULE (E8, pre-committed): compute the projected fire counts and mean
model-conditional net edge (P_model-implied edge minus haircut minus fee) at candidate
thresholds 0.08 and 0.12. If the projected mean conditional net edge at 0.08 is >= 8pp,
the binding threshold is 0.08; otherwise it is 0.12. These are the ONLY two permitted
values; the decision is recorded in 0c before the locking commit.

H2 FEASIBILITY RULE (E7, pre-committed): if the print histograms show the repaired H2
band cannot plausibly reach H2's power floor (30 fires / 8 clusters), H2 is DROPPED at
the locking commit and the ledger records ONE registered hypothesis.

RESULT (2026-07-02): the PRIMARY spec is degenerate under the E4 stability clamp on
299 of 503 evaluable trade dates (59 percent > 20 percent), so per the pre-committed
E4 rule the FALLBACK spec (symmetric ECM, no rho) is the OPERATIVE model for the
entire backtest, labeled as such throughout. Outcome-blind fire projection under the
fallback: threshold 0.08 -> 2,927 fires across 52 fired ISO-week clusters, mean
model-conditional net edge 25.9pp; threshold 0.12 -> 2,171 fires across 51 clusters,
33.0pp. |divergence| quantiles among fires (10/25/50/75/90/95):
0.09 / 0.12 / 0.22 / 0.45 / 0.67 / 0.78. E8 DECISION: mean conditional edge at 0.08 =
25.9pp >= 8pp, so the BINDING THRESHOLD IS 0.08 (recorded in
data/v25/audit_0b_decision.json). Power floor (40 fires / 30 clusters) is comfortably
reachable: kill switch PASSES. H2 feasibility upper bound: 34,199 yes-band + 69,485
no-band prints across 91 clusters >= floor 30/8: H2 IS KEPT (two registered
hypotheses). HONESTY NOTE, pre-committed interpretation constraint: the very large
median divergence (22pp) means EITHER the market is grossly miscalibrated OR the
fallback model is overconfident at extremes; gate 2 (settlement CI) plus gate 3 (the
control) adjudicate; no post-hoc reinterpretation of the fire set is permitted.

### 0c. PRE-LOCK COMPUTATION LEDGER (E12b; exhaustive)

Every number computed before the locking commit is listed here; anything computed
pre-lock and not listed invalidates the lock.
1. 0a rates, straddle counts, near-tie flags (above), plus the per-market booleans in
   the audit output (booleans and rates only, per the E12a firewall).
2. 0b (primary spec, superseded): 454 fires / 6 clusters at 0.08; funnel with 299/503
   degenerate days; divergence quantiles 0.09/0.117/0.174/0.289/0.399/0.467.
3. 0b (fallback spec, operative): the numbers in 0b RESULT above, and the funnel
   (712,728 deduped prints; 649,517 in-band; 79,375 ambiguity-window; 86,042
   zero-staleness excluded; 93,632 no-path; 7,203 insufficient errors; 345,490
   dedup-suppressed; 958 no-strike; 2,927 fired).
4. In-sample pass-through fit quality (context only, no decision depends on it):
   PRIMARY spec on its non-degenerate days: h=7 R^2 0.190 corr 0.733 (n=30); h=14
   R^2 -0.699 corr 0.664 (n=29). FALLBACK spec (operative): h=7 R^2 -0.023 corr
   -0.022 (n=231); h=14 R^2 -0.033 corr -0.065 (n=216). Stated plainly: the operative
   fallback's point forecast shows NO in-sample edge over a random walk at these
   horizons; the empirical-error machinery may still price tails differently from the
   market, which is exactly what gates 2-3 test, and a NULL here will be worded per
   the E11 rule as a null of THIS frozen spec.
5. Pre-lock schema/coverage reads documented in the proposal: market counts and
   close-date ranges per series, cluster counts, live-ladder quotes/volumes, and the
   June-2026 settlement bracket incidentally observed during the schema probe (AAA
   between 3.80 and 3.90 on 2026-06-30, a single already-public value).
6. AAA reconstruction coverage: 566 as-of dates 2024-08-31..2026-07-01 (87 exact gap
   fills in the repair pass; 14 residual misses are genuine no-snapshot days incl.
   the late-Feb-2026 cluster, handled by zero-staleness NO-FIRE, never filled).
Nothing else was computed pre-lock.

## 1. Exact target and universe

- Series: KXAAAGASW (weekly) and KXAAAGASM (monthly) ONLY. KXAAAGASD fully out of
  scope; no rescue from it for any floor (gate 1 and H2 alike).
- Markets: all strikes, settlement events with close_time in [2024-10-01, 2026-06-30],
  result in {yes, no}. Sources: /historical/markets drain + live settled endpoint.
- Executions: real historical trade prints (created_time, yes_price_dollars, count_fp,
  taker_side).
- Settlement truth: the Kalshi `result` field ONLY.

## 2. As-of data discipline (A2/A3; E1, E2, E3, E13, E15a)

- Retail R(t): Wayback-reconstructed AAA daily series keyed on the page's own "Price as
  of" date, full display precision preserved (E13). A trade at ET timestamp t expects
  the AAA value of date(t, ET) if t >= 09:00 ET, else date(t, ET) - 1 day.
- ZERO-STALENESS FIRING: if the AAA series lacks a value exactly at the expected date,
  the trade CANNOT fire. No filling, no interpolation, anywhere (E2): a gap day simply
  contributes no regression row and no fire.
- PUBLICATION-AMBIGUITY WINDOW (E1): trades with ET time-of-day in [03:00, 09:00) are
  excluded from FIRING entirely (the D print may already exist while our keying still
  points at D-1; firing on a possibly one-day-stale input is the v24 stale-spot
  mechanism in miniature). Model inputs and keying are unchanged.
- Wholesale: W := DGASNYH, full stop (E15a); DGASUSGULF and DCOILWTICO appear only in
  named non-binding sensitivities. Publication-visibility rule (E3, SUPERSEDING the
  draft's flat d-5 lag after direct verification on 2026-07-02): EIA petroleum daily
  spot prices are released in WEEKLY batches on Wednesdays covering data through the
  prior Monday (eia.gov spot page: Release Date 7/1/2026, Next Release 7/8/2026; and
  on Thursday 2026-07-02 the freshest DGASNYH observation was Monday 2026-06-29,
  exactly the 7/1 release's coverage). A trade on ET date d therefore sees only
  observations with series date <= W - 2 where W is the last Wednesday <= d - 1 (the
  one-day margin covers the FRED mirror delay). This is stricter than any flat lag on
  the days a flat rule would leak (a flat d-5 grants Thursday/Friday values 3-4 days
  before their actual release on some weekdays). The flat d-3 rule is the NON-BINDING
  optimistic sensitivity.
- Weekend/holiday W (E2): carry the last lag-visible business-day value.
- Valid regression observation (E2): row s requires R at s-1, s, s+1 (zero-staleness
  keyed values; no fills) and lag-visible W at s. m(s) = rolling 180-day median of
  (R(u) - W_asof(u)) over days u where BOTH exist under the same as-of rules, minimum
  90 valid pairs in the window, else NO FIRE (E2).
- Model horizon: trade timestamp to the settlement-morning AAA print of UTC close date
  D (trading ends 11:59pm ET on D-1; settlement is the D print).

## 3. Model (frozen spec; A6, E4, E5)

Primary spec (asymmetric error-correction pass-through):

- Weq(s) = W_asof(s) + m(s); g(s) = Weq(s) - R(s).
- OLS, expanding window, all valid rows strictly before the trade date, minimum 120
  rows else NO FIRE:
    dR(s+1) = a + theta_up * max(g(s), 0) + theta_dn * min(g(s), 0) + rho * dR(s) + eps
- Point forecast: iterate daily to the settlement morning; W and m frozen at their
  as-of values. The iteration's dR seed requires R at t0 - 1 exactly (zero-staleness;
  missing = NO FIRE, never an implicit zero fill).
- STABILITY CLAMP (E4): NO FIRE on any trade date where the fitted system's companion
  spectral radius >= 1 OR the 35-day point forecast implies a cumulative move larger
  than 3x the largest 35-day move in the fitting window.
- NAMED FALLBACK SPEC (E4, run only by rule, never by choice): dR(s+1) = a + theta *
  g(s) (symmetric ECM, no rho). Used ONLY if the primary is degenerate under the clamp
  on more than 20 percent of trade dates; all its output is labeled FALLBACK.
- P_model(R(D) > K): point forecast + empirical h-day error distribution, built
  walk-forward on the fitting window only; horizon buckets h in {1-3, 4-7, 8-14,
  15-35}; h > 35 days = NO FIRE (E5); within-bucket errors normalized by sqrt(h) and
  rescaled to the trade's h (E5, frozen now); linear interpolation between order
  statistics; minimum 40 error observations in the bucket else NO FIRE. CAVEAT owned
  (E5): overlapping horizons make 40 errors far fewer than 40 independent draws; the
  min-40 gate is a resolution floor, not a power guarantee. Non-binding sensitivity:
  errors subsampled at h-day spacing.
- CONTROL: identical machinery with a = theta_up = theta_dn = rho = 0 and its own
  error distribution.

## 4. Execution simulation (A4; E15)

- At most ONE simulated position per market per ET calendar date (first qualifying
  print), 1 contract, taker only (E15b).
- Direction: BUY YES if P_model - p_print >= threshold; BUY NO if p_print - P_model >=
  threshold (threshold set by 0b's recorded decision).
- BINDING RUN: every fire at print worsened by a flat 3c haircut. Non-binding
  sensitivity: 5c haircut on the monthly leg (scouted monthly spreads 1-5c) (E15e).
- REPORTED RUN (upper bound): side-matched prints only, +1c.
- Fee: worst-case taker quadratic ceil(7 * p_exec * (1 - p_exec)) cents, every fill.
  p_exec > 1 is definitionally unexecutable and must never appear in any run (E15c).
- P&L: settlement indicator minus p_exec minus fee. Settlement from Kalshi result only.
- Attrition: report fire-to-print attrition; if the side-matched run loses more than 50
  percent of binding-run fires, the capacity story is weaker and the verdict MUST say
  so (E15d).

## 5. Fire thresholds (locked; E8, E15c)

- Divergence threshold: 0.08 or 0.12 per 0b's pre-committed rule; no other value.
- Price band: p_print in [0.03, 0.97] for H1.
- Band-edge closure (E15c): BUY YES needs P_model >= p_print + 0.08 and P_model <= 1,
  so p_print <= 0.92 and p_exec <= 0.95; worst-case fee 1c; max all-in cost 0.96 <
  1.00. Mirror for NO. No H1 fire can be impossible or cost >= 1; no exclusion rule
  exists to be discovered later.
- Minimum-history gates per sections 2-3.

## 6. Strata (closed set; E6, E7)

- H1 (PRIMARY): pooled fires, both series, both directions, horizons 1-35d, band
  [0.03, 0.97], binding run.
- H2 (SECONDARY, kept only if 0b's feasibility rule passes): YES band [0.90, 0.955]
  when BOTH P_model and P_control >= 0.995; NO mirror [0.045, 0.10] when both <=
  0.005; requires >= 200 error observations in the trade's bucket (E6); prints outside
  the feasibility band are counted UNEXECUTABLE, never scored (E7); inherits regime
  guard 7a and the E11 lattice; no band widening ever.
- REPORTED, NON-BINDING: weekly vs monthly, horizon buckets, direction, moneyness
  thirds, threshold sensitivity (the unchosen of 0.08/0.12), d-3 wholesale-lag
  sensitivity, DGASUSGULF/DCOILWTICO regressor sensitivities, 5c monthly haircut,
  subsampled-error sensitivity, chrono halves.
- No stratum added after data.

## 7. Evaluation window, clustering, regime guards (E9)

- Binding set: ALL fires with close_time in [2025-01-01, 2026-06-30]. Fires are OOS in
  the estimation sense by construction (walk-forward fits, frozen constants).
  HONESTY NOTE (E9c), owned plainly: the estimation argument does NOT remove
  design-level contamination. This idea and these constants were chosen in July 2026
  by a researcher who watched AAA run $2.83 to $4.07 in H1 2026; picking a
  pass-through model after a historic pass-through episode is selection on the
  realized path, and no within-sample split cures it (a chronological binding split
  was considered and REJECTED: ~15 clusters per half gives ~20pp CI half-widths,
  converting a weak test into no test while curing nothing). The compensations are the
  E8 threshold-power coherence, the shock-window routing below, and the fact that the
  ONLY true out-of-sample evidence in this program is the staged forward read/shadow
  of section 9; the backtest alone can never route to capital.
- Cluster key: ISO-8601 week of close_time evaluated in UTC (E9a).
- Binding statistic: cluster bootstrap (10,000 resamples) 95 percent CI of mean net
  P&L per contract (cluster_bootstrap_mean_ci).
- Regime guards: (a) month-block bootstrap (clusters = calendar month, UTC): weekly CI
  clears but month-block does not -> FRAGILE-PASS; (b) SHOCK-WINDOW guard (E9b): if
  gate 2 clears but excluding close_times in [2026-02-15, 2026-06-30] flips the CI to
  include zero, verdict class = SHOCK-WINDOW PASS, routed exactly like FRAGILE-PASS.

## 8. Gates (E10)

H1 PASS requires ALL of:
1. Power floor: >= 40 fires AND >= 30 distinct fired clusters in the binding set.
   Failing EITHER floor = UNDERPOWERED-NULL, the sub-floor quantity named (E11).
2. Binding-run cluster-bootstrap 95 percent CI lower bound > 0.
3. Control check: the control strategy under identical rules does not itself clear
   gate 2 WITH gate 1's power floor also met (E10). A zero-fire or sub-floor control
   satisfies this gate vacuously; control stats are reported regardless. If a
   floor-meeting control clears gate 2, H1 = NULL (general-miscalibration is a
   different claim for a future lock; document, never upgrade).
4. Concentration: leave-one-cluster-out; dropping the best cluster flipping the CI to
   include zero = MARGINAL.
5. Regime guards 7a/7b clean (else FRAGILE-PASS / SHOCK-WINDOW PASS).

H2 gate (if kept): >= 30 fires AND >= 8 clusters; binding-run CI lower bound > 0;
LOCO; guards 7a/7b. No rescue by band widening or from KXAAAGASD.

## 9. Verdict lattice, routing, kill rule (E11)

- PASS -> stage 1 read-only live divergence check ($0) -> stage 2 forward shadow ->
  stage 3 tiny pilot (fixed $-risk, hard contract cap from the ~$200 bankroll, weekly
  drawdown breaker) -> stage 4 scale ONLY on explicit operator approval.
- FRAGILE-PASS / SHOCK-WINDOW PASS / MARGINAL -> stage 1 $0 live read ONLY; any
  continuation beyond it requires a NEW lock. Counted as NON-passes in the ledger.
- NULL / UNDERPOWERED-NULL -> FINAL-VERDICT doc, memory update, commit, pivot (next
  queued: the Tier 1 window-aggregate family, fresh lock).
- Empty binding fire set = the market-matches-model NULL, named as such.
- NULL WORDING RULE: every null is a null of THIS frozen spec (which also cannot see
  RBOB futures curve information the market can see); it is never worded as "the
  market prices pass-through efficiently."
- No re-runs with tuned thresholds, no third bite, no post-data strata.

## 10. Honesty accounting

At ~25 hypothesis families, a single marginal pass is weak evidence BY CONSTRUCTION;
any pass is labeled "survivor of screen #25" and the staged path exists to catch the
survivorship fluke. The verdict doc must restate the ledger: families screened,
hypotheses this round (per 0b's H2 decision), and zero strata added post-data.

*Em-dash audit: clean (verified after write).*
