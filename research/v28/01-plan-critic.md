# v28 PLAN CRITIC: adversarial review of the RT score-ladder proposal

**Date:** 2026-07-02. Reviewed: 00-proposal.md, scout-rt-vintages.md, v27
05-FINAL-VERDICT + 02-methodology-lock, v26 04-FINAL-VERDICT. Two independent
API pulls run during this review (documented below). Family ~#28.

## VERDICT: PROCEED-WITH-AMENDMENTS (A1-A12, all binding)

The family earns its data pull ONLY under a restructured lock: H-A backtest
(raw-count bound, widened) + D* perfect-information bound (replaces the
proposed D) as the binding components, with H-B scoped OUT of the backtest
entirely (shadow-only). If the operator will not accept the H-B descoping
(A2), the verdict flips to KILL: a backtest H-B on 1-3 day stale snapshots is
a false-null machine that would burn the family's one shadow slot on a
contaminated verdict. The cheap kill path (A8's 0b projection + D*) costs ~$0
and adjudicates before any settlement-conditioned P&L, which is exactly what
justifies proceeding at a 5-8 percent honest prior (the proposal's 10-12 is
generous; see F10).

## Facts I verified independently (2 API calls, 2026-07-02)

GET /trade-api/v2/markets?series_ticker=KXRT&limit=1000 returns 520 markets,
400 finalized, and exactly 22 finalized events (MIC through SUPE, closes
2026-04-27 to 2026-06-29) plus the SEND closed-unsettled anomaly. Per-market
fields verified on KXRT-JAC-87 and across the settled set:

- `rules_secondary` (verbatim, load-bearing): "The Tomatometer score must be
  above the strike value to resolve as YES (for example, a score of 75 would
  resolve 'Above 75' as No.) The market will be determined the Monday after
  wide release at 10:00 AM ET." Strict-greater confirmed. NO settlement
  source or read-method is specified anywhere in the rules.
- `expiration_value` exposes Kalshi's actual settled SCORE per event (JAC=88,
  MOR=66, SCA=24, ...). The settled score is directly available; band
  inference from yes/no results is only a cross-check. MOR settled 66 while
  BOTH bracketing Wayback snapshots read 65: the settlement read can differ
  by 1 point from every archive state.
- Trading windows are TINY: open-to-close per event is 2.5 to 10.9 days,
  median ~3.8, mode ~2.7 (open Thursday-ish, close Monday 10:00 ET). The
  entire tradable life sits inside the wide-release review flood.
- `can_close_early: true` on every market; `settlement_ts` ~3h after close
  (Kalshi's read happens at an unspecified time at or after 10:00 ET).
- Sibling-series probe (KXRTAUD, KXPOPCORN, KXRTA, KXROTTEN): none exist.

## Load-bearing findings

### F1. The proposal's universe does not reconcile with the API (BLOCKING)

Proposal: "43 settled movie-events, Jan-Jun 2026 closes, 671 markets,
412,004 deduped prints." API today: 22 finalized events + 1 closed-unsettled,
400 settled markets of 520 total, settled closes Apr 27 to Jun 29 ONLY.
Nearly half the claimed universe does not exist under KXRT, and no sibling RT
series was found. Every power number in the proposal is built on the wrong
base. Until the 43/671/412k figures are reproduced from the API or corrected,
nothing downstream is trustworthy. The scout (23 finalized including its own
count) agrees with the API, not the proposal.

### F2. The trading window collapses the backtest design

Markets open around wide-release day and close the following Monday. With
Wayback density 0.3-1.4 snaps/day (bursty; small titles 3+ days dark), most
events will have roughly 1-5 snapshot-proven states INSIDE the window; thin
titles may have 0-2. Consequences: the H-B conditioning "(days-to-close, N
bucket)" degenerates to days-to-close in {0..3}; a 15-observation minimum per
error bucket is unreachable at 22 events; A_max's "remaining window" is 0-3
days, not a long accumulation arc. The proposal was written as if these were
multi-week markets. They are weekend markets.

### F3. Backtest H-B is structurally doomed: we are the stale side (DECISIVE)

The RT page is free, unblocked, and pollable every minute (scout section 5).
Any competent participant on a 15M-contract series polls it live. Our
backtest holds states 1-3 days old across a 3-day market whose score moves
1-3 points per day near close (PRE 86->87, SCA 27->24) and far more at
embargo-lift bursts. A model-vs-market divergence >= 0.08 computed from a
stale state is, first-order, evidence that the SCORE ALREADY MOVED and the
market saw it. This is the v24 stale-spot shape inverted: the backtest
measures "does the live market beat a day-old snapshot" (yes, trivially) and
returns a false null about the deployable live strategy. There is no
freshness-window salvage: snapshot density cannot support even a 6-hour
window, and 6 hours is still stale during arrival bursts. DECISION: only the
live shadow can test H-B. Scope the backtest to H-A + D* (A2, A3).

### F4. The proposed D bound is uninformative here; replace it with D*

In v27, D1 substituted the channel INPUT (actual flight ops), which was
distinct from the settlement variable. Here they are the same object. Final
score = (f + a_f) / (N + A). Substituting actual arrivals A while modeling
the fresh mix a_f leaves the dominant uncertainty in place (the mix, not the
arrival count, drives the score), so D ~= H-B + epsilon: it cannot price the
channel ceiling. Substituting the actual mix too IS the final score. So the
only sharp bound is the limit case: D* = substitute the settled
`expiration_value` at every evaluable print, apply the fire rule at
worst-case frictions. D* prices the ceiling of EVERY modeling channel at once
(the v27 D1 pattern taken to its limit) and doubles as the v26
executable-band audit on real prints. Pre-committed routing: D* fails its
gates anywhere = FAMILY DEATH, no shadow; D* clears while H-A nulls = shadow
route for H-B only.

### F5. H-A bound arithmetic is fixable but currently underspecified

(a) Do not reconstruct the fresh count from the rounded displayed integer:
the scorecard JSON carries `likedCount` and `notLikedCount` directly (scout
section 3). Bound on raw counts: decided-YES for strike K requires
100 * f / (N + A_max) >= K + 1 + margin; decided-NO symmetric. Integrity
check per state: likedCount + notLikedCount == reviewCount, else the state is
discarded (this also kills the audience-score parse-confusion risk together
with A11).
(b) Rounding rule (half-up vs other) on the displayed integer is unverified,
and MOR proves the settlement read can differ by 1 from any archive state.
The 1-point frozen margin must therefore be applied against the UNROUNDED
ratio on BOTH deciding directions, on top of the strict-greater K+1.
(c) A_max as an empirical max over 10-20 prior movies is indefensible: max is
the worst estimator on a heavy-tailed count, cross-movie heterogeneity is
huge (in-window N ranges ~37 to ~235), and an underestimated A_max converts
"decided" into a -0.95 bust. Breakeven bust hazard at a 0.955 print with the
3c haircut and 1c fee is ~0.5 percent (F8); 22 events cannot bound a 0.5
percent hazard. Estimate on the RELATIVE scale r = arrivals/N per
remaining-days bucket, frozen as 2.0 x max observed r across ALL prior
settled movies, minimum 12 priors else NO FIRE.
(d) Honest consequence, stated now: for small titles (N ~= 37) the widened
bound is 25-35 points wide, so decided strikes are deep tails only, exactly
where v26 found ladders snapped to 0.96+. The 0b projection (A8) is the real
gate; run it before the lock binds.

### F6. Withdrawals and reclassifications are a live hazard to "decided"

RT recounts, purges, and fresh/rotten reclassifications can move f DOWN or N
down (the v26 CLI downward-revision lesson: a bound-decided side can
undecide). Decided-YES is attacked by fresh-review removal, decided-NO by
rotten-review removal. Mandatory pre-lock audit 0-W, from the vintage rows
themselves: across every within-window snapshot pair per movie, test
reviewCount, likedCount, and notLikedCount for decreases. Frozen rule: any
decrease observed in more than 2 percent of pairs, or any single decrease
greater than 2 reviews, adds a two-sided W_max slack (max observed decrease)
to the bound; decreases in more than 5 percent of pairs = H-A dead.

### F7. Settlement wrinkles (verified against the API)

- Settlement truth = `expiration_value`, cross-checked against per-market
  `result`. This upgrades the scout's band inference and RESOLVES the MOR
  ambiguity operationally (settled score 66 is now data, even though the
  archive cannot reproduce it); MOR stays in the settled set via
  expiration_value but is excluded from any snapshot-to-settlement
  calibration row (its near-close state is unknowable).
- Whose read: unspecified in rules; treat as "Kalshi staff read of the page
  at or after 10:00 ET." The MOR 1-point gap prices this risk; the F5b margin
  covers it. No further mitigation exists; do not pretend otherwise.
- "Monday after wide release" makes the close date conditional on release
  actually happening. SEND (closed 2026-02-02, never finalized) is the
  release-slip precedent: exclude it everywhere; live/shadow rule: NO FIRE on
  any event whose wide-release date is unconfirmed or moving; monitor
  close_time daily; can_close_early is true on every market.
- DUN is an inactive duplicate of DUNE: exclude.
- Strike semantics locked by rules_secondary: "above 42" = displayed 43+.

### F8. Friction arithmetic at the relevant moneyness

Kalshi fee = ceil(0.07 x P x (1-P)) per contract = 1c everywhere in the
0.62-0.955 band. At a 0.955 print with the binding +3c haircut: cost 0.985,
gross cap 1.5c, fee 1c, net 0.5c against 98.5c of risk. The binding
convention makes everything above roughly 0.92 unfirable BY CONSTRUCTION;
the lock must state this instead of discovering it post-hoc. Keep +3c
binding, REPORT the +1c side-matched sensitivity (the observed book shows 1c
spreads on 15k-35k volume), and pre-commit: a component that clears only at
1c routes to shadow (real logged asks), never to a backtest-alive
declaration.

### F9. Power on the REAL universe

22 finalized events. The 12-prior floor for A_max leaves roughly 10-11
walk-forward-evaluable H-A clusters in-sample. Floors (A9): H-A 15 fires / 8
movie clusters, D* 30 fires / 12 clusters; below floor = UNDERPOWERED-NULL,
not NULL. If even D* (which fires broadly by construction: every winning side
priced inside the band) cannot reach its floor, the print universe itself is
dead and the family dies pre-lock for $0. Accrual of 1-3 movies/week means a
13-week shadow adds ~15-30 clusters, so shadow power is fine; backtest power
is marginal. Lean on 0b + D* + shadow, not a fat backtest lattice.

### F10. Who sets these prices

Three candidate edge channels: (i) latency: lost by construction in the
backtest, measurable only live; (ii) tail-bound certainty (H-A): the v26
precedent says decided outcomes get quoted at 0.96+ even on thin ladders,
and one RT-polling bot suffices to enforce that here; (iii) mid-curve crowd
miscalibration vs a review-arrival model: shadow-only per F3. A 15M-contract
series is more than enough to pay for one bot that polls a free page. The
retail-crowd argument is real but cuts only at (iii). Honest family prior:
5-8 percent. Proceed only because the kill is nearly free.

## AMENDMENTS (binding; the lock is invalid without them)

- **A1 (BLOCKING).** Reconcile the universe against the API before anything
  else: reproduce or retract 43 events / 671 markets / 412,004 prints. All
  power floors and the 0b projection run on API-verified counts (22 finalized
  events, 400 settled markets today).
- **A2.** H-B is REMOVED from the binding backtest. It exists only as the
  pre-committed live-shadow protocol (v27 E12 pattern: one shadow ever,
  week-13 early-kill on cluster-CI upper < 0, week-26 binding evaluation,
  week-39 hard stop, thresholds frozen NOW, real logged asks). The backtest
  registers H-A and D* only; the CONTROL frozen-first-state model moves to
  the shadow spec.
- **A3.** Replace D with D*: substitute settled `expiration_value` at every
  evaluable print, fire rule and worst-case frictions unchanged. Routing
  pre-committed: D* fails gates = FAMILY DEATH (no shadow, no rescue); D*
  passes + H-A nulls = shadow for H-B only; both pass = shadow still required
  before any capital (stage-1 $0 read, v27 A5 pattern).
- **A4.** H-A bound on raw counts (likedCount / notLikedCount), never the
  rounded display. Per-state integrity check likedCount + notLikedCount ==
  reviewCount else discard. Strict-greater semantics: decided-YES needs
  unrounded 100f/(N+A_max) >= K + 1 + 1.0 frozen margin; symmetric for
  decided-NO.
- **A5.** A_max on the relative scale r = arrivals/N, per remaining-days
  bucket, frozen at 2.0 x max observed r over all prior settled movies,
  minimum 12 prior movies else NO FIRE.
- **A6.** Pre-lock audit 0-W (withdrawals): monotonicity of reviewCount,
  likedCount, notLikedCount across all within-window snapshot pairs. Frozen
  thresholds: >2 percent of pairs with any decrease or any single decrease >2
  reviews = two-sided W_max slack added; >5 percent = H-A dead. Results in 0c
  before the locking commit.
- **A7.** Settlement truth = expiration_value verified against result. MOR in
  the settled set but excluded from calibration rows. SEND and DUN excluded
  everywhere. Live/shadow: NO FIRE while a release date is unconfirmed;
  monitor close_time daily.
- **A8.** 0b outcome-blind projection, run BEFORE the lock binds, kill
  numbers frozen: count executable-band prints (binding +3c, fee =
  ceil(0.07 P(1-P)), p in [0.05, 0.955]) on (i) H-A bound-decided strikes and
  (ii) the D* fire set; report at +1c as sensitivity. Below the A9 floors on
  the projection = KILL pre-lock at $0 (the v26 pattern, demanded here
  explicitly).
- **A9.** Floors: H-A 15 fires / 8 movie clusters; D* 30 fires / 12 clusters;
  below floor = UNDERPOWERED-NULL wording, v26/v27 lattice carried verbatim;
  cluster key = the movie event (one bound decides many strikes; all
  inference cluster-level).
- **A10.** Frictions: +3c binding, +1c reported, fee rounding ceil per
  contract in the breakeven table, and the lock states plainly that the
  executable H-A band is effectively prints <= ~0.92 under the binding
  convention.
- **A11.** Parse discipline: media-scorecard-json criticsScore with JSON-LD
  Tomatometer agreement required; disagreement or missing/blank score = no
  state, no fire. Slug re-verification with 3xx following at engine start.
  Start SavePageNow + scheduled self-pulls on all ACTIVE events NOW,
  regardless of verdict path (banks the as-of record any future shadow
  needs; the scout's blocker 2 mitigation, made mandatory).
- **A12.** Multiple testing: the registered set is exactly {H-A, D*,
  H-B-shadow}, closed; the ledger counts family #28 once; no post-data
  strata; no third bite.

*Em-dash audit: clean (verified after write).*
