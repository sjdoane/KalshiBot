# v28 METHODOLOGY LOCK: RT score ladders, bound-certainty taker (H-A only)

**Status: v1 draft. Plan-critic amendments A1-A12 (01-plan-critic.md) folded, with ONE
documented deviation the methodology critic must adjudicate (section D below). LOCKED
at the git commit including completed section 0. No settlement-conditioned P&L before
that commit. v27/v25 machinery carries over verbatim wherever referenced. Family ~#28.**

Date: 2026-07-02. Honest family prior: 5-8 percent (critic re-mark); proceed because
the kill is nearly free and every gate is pre-paid.

## Registered hypothesis: H-A ONLY

- **H-A (bound certainty):** at a snapshot-proven state (liked L, notLiked M, N=L+M,
  unrounded ratio r=L/N from the scorecard JSON, NEVER the rounded display), with
  d days to the settlement read, the final displayed score is bounded by
  low = 100*L/(N+A_cap) and high = 100*(L+A_cap)/(N+A_cap), where
  A_cap = ceil(2.0 * max over prior-settled movies of (arrivals over their final d
  days / their N at that point) * N_current), requiring >= 12 prior settled movies
  else NO FIRE (critic A: relative-scale cap, x2.0 frozen). Decided YES if
  low > K + 1.0; decided NO if high < K - 1.0 (the 1.0-point margin absorbs the
  proven settlement-read-vs-archive divergence, e.g. the MOR case; strictly-greater
  semantics confirmed via rules_secondary). Fire the decided side at prints with
  cost <= 0.955 feasibility band (breakeven table as in v26/v27; binding +3c
  haircut, reported side-matched +1c, worst-case quadratic fee, one position per
  market per ET day, first qualifying print).
- **H-B (convergence model): NOT REGISTERED for the backtest**, per plan-critic A2
  accepted in full: the RT page is freely pollable per minute, the market is fresh,
  and our archive states are 1-3 days stale, so a backtest H-B is a false-null
  machine. H-B may exist ONLY inside a shadow opened by H-A's own lattice
  (PASS/MARGINAL/FRAGILE -> stage-1 $0 live read -> the v27 A3-verbatim shadow
  protocol with its week-13/26/39 gates, one shadow ever).

## D deviation (for the methodology critic to adjudicate)

The plan critic proposed D* = substitute the settled score (from expiration_value)
as a perfect-information router. DEVIATION: D* is NOT registered, because it is
degenerate-positive: with the settled score known, every fire wins by construction,
so D* reduces to "do mid-priced prints exist," which is trivially true on a 15M-
contract family; a trivially-passing bound cannot route to a shadow (that is the
v27-A-critics' shadow-shopping backdoor). The v27 D1 worked because perfect channel
inputs still left model error; here the channel input IS the settlement variable.
Consequence: if H-A dies, the family dies; there is no bound-based rescue. The
methodology critic is explicitly asked to confirm or refute this reasoning.

## Universe and settlement (plan-critic F1 resolved by direct count)

43 result-bearing events (17 close before 2026-04-01; range 2026-01-26..2026-06-29),
671 settled markets, 412,004 deduped prints (data/v28/markets_all.json, trades.jsonl;
the critic's 22-event count was an incomplete pull, documented here). ALL 671 markets
carry expiration_value (the settled score); settlement truth = the result field,
with expiration_value as the recorded settlement read. KXRT-SEND (closed, unsettled)
excluded; KXRT-DUN and KXRT-DUNE are distinct settled events on the same film and
both count (their correlation is handled by clustering only if... NO: they share the
underlying; they form ONE cluster, frozen here). Cluster unit: the MOVIE (merged for
DUN/DUNE), else the event.

## As-of discipline

- States: Wayback vintage rows (data/v28/rt_vintages.json), each row proven by its
  snapshot timestamp; a print may use only rows with ts <= print time (v27
  evaluability). No interpolation between rows; the newest proven row governs;
  A_cap absorbs arrivals since that row by construction (d measured from the ROW's
  timestamp, not the print's, which can only WIDEN the bound: frozen).
- Walk-forward: prior-movie arrival empirics use only movies settled before the
  print's movie closes.
- 0-W withdrawal audit (section 0) guards the monotonicity assumption.

## Gates (H-A)

Power floor: >= 15 fires AND >= 8 distinct movie clusters (critic A). Binding CI
lower > 0 (cluster bootstrap, 10k, seed 28). LOCO (drop best movie). Month-block
guard (calendar month of close). Verdict lattice, null wording, no-third-bite,
routing per v27 sections 5-6 verbatim (PASS class explicitly labeled
unbankable-without-live-read; stage-1 $0 read before any shadow).

## 0. Pre-lock audits (kill switches; filled before the locking commit)

- 0-U universe reconciliation: DONE above (43 events; SEND excluded; DUN/DUNE
  merged as one cluster).
- 0-W withdrawal/monotonicity audit: from vintage rows, the rate of
  consecutive-row review-count DECREASES exceeding 2 reviews; if more than 2
  percent of consecutive pairs, or any decided-bound reversal would have occurred
  historically (a decided side un-decided by a later row), H-A is KILLED.
- 0-S settlement-read audit: vintage row nearest each close vs expiration_value;
  distribution of |diff|; the 1.0-point margin must cover the observed p95, else
  the margin is raised to the observed p95 BEFORE the lock binds (never after).
- 0-B outcome-blind fire projection: fires and fired clusters at the frozen rules;
  floors (15/8) must be reachable, else KILL pre-lock at $0 (v26 pattern).
- 0-L ledger: exhaustive pre-lock computation list.

RESULTS: [PENDING the vintage crawl; filled before the locking commit.]

## AMENDMENTS v2 (methodology critic E1-E13 + D' adoption; full text in
## 03-methodology-critic.md; all binding)

- **D' ADOPTED (replacing the refused D*):** perfect-ARRIVAL bound: identical to
  H-A but with A_cap replaced by the REALIZED arrivals A_act = max(0, N_final -
  N_row) (look-ahead on arrival volume only; the fresh/rotten mix stays
  worst-cased, margins/frictions/evaluability identical). Non-trivial by
  construction (fires exist only where the realized-arrival bound decides and an
  executable print exists; busts remain possible via withdrawals and read
  divergence). Floors 15 fires / 8 movie clusters. Routing: D' fail = FAMILY
  DEATH, no shadow; D' pass + H-A null = shadow testing H-A LIVE (bound fires at
  live asks; H-B strictly a REPORTED overlay, never the binding shadow
  hypothesis: fixes the hypothesis-swap). H-A floor-failure alone never infers a
  shadow.
- **E3 (schema): the bound is reformulated on (displayed score s, reviewCount N)**
  since the banked vintage rows lack raw counts: the fresh count L lies in the
  rounding interval [ceil((s-0.5)*N/100), floor((s+0.5)*N/100)] (convention-
  agnostic band; 0-R pins the display convention empirically and may TIGHTEN,
  never widen, this interval); the bound low/high use the adverse end of the L
  interval per side.
- **E4d (leak fix): prior movies contribute arrival empirics only if settled at or
  before the PRINT timestamp** (not the movie's close).
- **E5 (margin split): decided requires clearing K by (rounding-interval width in
  display points) PLUS the 1.0-point settlement-read margin**, per side; 0-S may
  raise (never lower) the read margin to the observed p95.
- A_cap pinning: d measured from the fire ROW timestamp to the settlement read;
  prior contributions require >= 12 movies each having a proven row within
  [d - 2, d + 2] days-to-close; fire-time cap-exceedance audit reported.
- 0-E evaluability line: >= 30 percent of in-band prints must have a proven row,
  else restrict/kill pre-lock; 0-B reports the line.
- Universe corrections (0-U): DUN/DUNE are NOT settled (Dec 2026 closes; excluded
  from the binding set); the same-film settled pair is SEN/SEND handling per slug
  map (one movie cluster); KXRT-SCR expiration_value is a string ("Above 32"),
  parse-guarded; settled universe recount documented with the pull method.
- PASS wording: at-floor passes bound the bust hazard only at ~20 percent (rule
  of three), vs the ~5-7 percent breakeven hazard ceiling, so any PASS is
  labeled FEASIBILITY-NOT-SAFETY and routes to the $0 live read first, always.
- The five previously-undocumented deviations from the plan critic's amendments
  are hereby documented as superseded by this amendments block (A4 margin
  restored via E5; A6 W_max slack restored: 0-W thresholds widened to 3 reviews
  / 3 percent with the decided-bound-reversal check computed at the FIRE-TIME
  A_cap; A7/A11 carried rules restored by reference to v27; A10's effective
  <= 0.92 executable statement restored).

*Em-dash audit: clean (verified after write).*
