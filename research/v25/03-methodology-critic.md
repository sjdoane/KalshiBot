# v25 METHODOLOGY CRITIC: stress test of the draft lock (02-methodology-lock.md)

**Date:** 2026-07-02. Role: methodology critic under the v24 charter, reviewing the
DRAFT v2 lock before commit and before any data pull. Scope: false-positive vectors,
false-null vectors, post-hoc wiggle room, implementation traps, and amendment fidelity
vs 01-plan-critic.md A1-A7. Not re-litigating idea worth (plan critic verdict stands).

**VERDICT UP FRONT: LOCK-OK-WITH-EDITS. No fatal flaw requiring redesign. Fifteen
required edits (E1-E15 below), of which four are load-bearing: E3 (wholesale lag is a
live look-ahead vector as drafted), E4 (the A6-mandated fallback spec is missing),
E6/E7 (H2 as locked is partially null theater: its model gate exceeds the error CDF's
resolution and part of its price band is unexecutable by arithmetic), and E8 (the 0.08
threshold contradicts the lock's own power arithmetic, a false-null generator A5
explicitly warned against). The lock is invalid for commit until all fifteen are in.**

---

## 1. Amendment fidelity audit (A1-A7)

| Amendment | Status | Detail |
|---|---|---|
| A1 prior ~10% + frontier-form escape restated in lock | **MISSING** | The lock nowhere states the prior or the corrected escape argument. Edit E14. |
| A2.1 backward-fill only, never interpolation | **AMBIGUOUS** | Section 2 says "Backward-fill is used ONLY inside model FITTING" and in the same sentence "no synthetic values are created; missing days simply drop out." These contradict. If gap days drop out of the fit, no fill of any kind exists and the sentence should say so. Edit E2. |
| A2.2 zero-staleness firing | **WATERED DOWN at the margin** | The 09:00 ET keying boundary creates a window (roughly 03:00-09:00 ET, AAA publishes ~3-5am ET) in which a trade is keyed to the D-1 print even though the D print exists. Fires in that window run on an input up to one day staler than what the market sees. That is the stale-spot mechanism, capped at one day: during the 2026 ramp a one-day-stale R overstates remaining pass-through and manufactures divergence. A false-POSITIVE vector. Edit E1. |
| A2.3 settlement truth Kalshi-only | HONORED | Sections 1 and 2. |
| A2.4 settlement-key audit >= 20 markets, kill on ambiguity | HONORED | Section 0a, with a 95% operationalization. One tightening needed: any mismatch must be investigated for the decimal-precision cause (below) before the key is accepted; unexplained mismatch = ambiguity = KILL. |
| A2.5 3-to-4 decimal display change handled in parser and audit | **MISSING** | Not mentioned anywhere in the lock. A near-tie strike at 3.800 vs a 3.8001 print is a settlement flip. Edit E13. |
| A3 wholesale lag: ALFRED-verify, else conservative 3-business-day primary | **VIOLATED** | The lock's primary is d-3 CALENDAR days = 2 business days, justified by a single-day empirical check on 2026-07-02. A3 said: if unverifiable, primary at 3 BUSINESS days, shorter lag as sensitivity. The lock inverts this. If real-world publication ever ran slower than the one observed day (holidays, EIA delays), the backtest hands the model wholesale data the real-time trader did not have: a genuine look-ahead false-positive vector on exactly the regressor the whole hypothesis runs on. Edit E3. |
| A4 dual-bound execution, bind on lower bound, attrition | MOSTLY HONORED | Binding +3c all-fires run and side-matched reported run are correct. Two dilutions: (a) A4 specified the haircut as the measured median spread PER SERIES/BAND; the lock hardcodes a flat 3c. Monthly spreads were scouted at 1-5c, so 3c may flatter the monthly leg. (b) A4's ">50% attrition = the capacity story is weaker and the verdict must say so" language was dropped. Edit E15. |
| A5 power arithmetic + 30-cluster floor + threshold derived so a pass is reachable | **HALF HONORED** | Arithmetic and floor: honored (0b, gate 1, honest-ceiling statement present and correctly worded). Threshold: NOT honored. See section 4 below. Edit E8. |
| A6 one binding stat, frozen spec PLUS ONE NAMED FALLBACK, daily exploratory, ledger | **PARTIALLY VIOLATED** | Binding stat: honored. Daily series: honored (stricter than asked, fine). Hypothesis ledger: partially (section 10 gestures; require it in the verdict doc). The pre-registered named fallback spec is ABSENT from section 3. A6 was explicit: "one pre-registered simpler fallback spec (named in the lock, not chosen later)." Without it, a degenerate fit on real data invites exactly the post-data spec search A6 exists to prevent. Edit E4. |
| A7 month-block FRAGILE-PASS + shock in/out diagnostic | HONORED | Sections 7a/7b with pre-committed language. One gap: 7b has no routing consequence at all; see E9. |

Bottom line: the lock's claim "all plan-critic amendments folded in" is false as drafted.
A1 and A2.5 are missing, A3 is inverted, A5's threshold clause and A6's fallback clause
are dropped. These are restorations, not new design, so LOCK-OK-WITH-EDITS rather than
REDESIGN.

## 2. The "every fire is OOS by construction" claim (section 7)

The claim is SOUND AS FAR AS IT GOES: walk-forward fits with strictly-prior data plus
constants frozen pre-P&L do make each fire out-of-sample in the estimation sense. But
it does not address the contamination that actually exists, and the lock should say so
plainly rather than imply the binding set is contamination-free:

- The IDEA was selected in July 2026 by a researcher who knows AAA ran $2.83 to $4.07
  in H1 2026. Choosing a rockets-and-feathers pass-through model AFTER observing a
  historic pass-through episode is design-level selection on the realized path. No
  within-sample split can remove this: constants like the 180-day median window, the
  horizon buckets, the 120-obs minimum, and the [0.03, 0.97] band were all written by
  someone who has seen 2026. Both halves of any chronological split are equally
  contaminated by that knowledge.
- The 0.08 threshold specifically is CLEAN of outcome tuning (it is derived from fee
  plus haircut arithmetic that would be identical in any regime), and I verified the
  derivation. The contamination risk is at the design level, not the constant level.

**Firm recommendation: KEEP the pooled binding set. A chronological binding split is
REJECTED on arithmetic:** the lock's own 0b table gives a ~14pp CI half-width at 30
fired clusters, which is already at the detectability ceiling; a binding half-split
leaves ~15 clusters per half and ~20pp half-widths, which can detect no edge size
anyone believes in. You would convert a weak test into no test while curing nothing
(the contamination is in the design choices, which a split does not touch). The honest
compensations, all required:
1. E8 (threshold-power coherence, so the pooled test is at least a real test).
2. E9 (shock-window routing teeth: a pass that dies when Feb-Jun 2026 is excluded is
   labeled and routed like FRAGILE-PASS, never to capital).
3. A one-paragraph honesty note in section 7 stating the design-level selection
   explicitly and that the staged forward read/shadow (section 9) is the only true OOS
   in this program; the backtest alone can never route to capital. Section 9 already
   implies this; section 7 should own it.

## 3. Model spec traps (section 3)

(a) **Calendar mismatch, weekends, and W alignment: UNDERSPECIFIED.** AAA is 7-day,
FRED wholesale is business-day. The lock never says what W(s) is on a weekend/holiday
(carry last lagged business-day value? drop the day?), whether m(s)'s 180-day median
uses only days where both R and W exist, whether that median requires a minimum pair
count, or what a "valid daily observation" for the 120-obs gate is (the regression row
needs R at s-1, s, s+1 for dR(s), dR(s+1), plus as-of W for g(s); a single Wayback gap
kills up to three rows). Two implementations of this section produce different fire
sets. That is post-hoc wiggle by underspecification. Edit E2.

(b) **Overlapping-horizon error CDF: real but survivable, must be acknowledged.**
Walk-forward h-day errors at h in 15-35 overlap massively; 40 collected errors are
maybe 2-4 independent observations. Consequences: the min-40 gate is not the power
guarantee it appears to be, and the CDF tails are dominated by whichever single regime
episode the window covers (a calm-2025-fitted tail meets the 2026 trend and is too
tight, i.e. overconfident P_model, more extreme fires). Note the failure direction is
mixed: overconfident fires that LOSE are caught by the binding CI (false-null drag);
overconfident fires that WIN because the 2026 trend continued are the false-positive
path, and that path is exactly what E9's shock-window routing exists to catch. Also
unstated: whether errors pooled within a bucket are variance-heterogeneous (a 15-day
and a 35-day error in one CDF makes the CDF too tight for h=35 trades and too wide for
h=15). Edit E5: state h > 35 = NO FIRE (currently silent on monthly trades listed
further out than 35 days!), normalize pooled errors by sqrt(h) within bucket (pre-lock
spec choice, allowed now, never later), state the overlap caveat, and add a non-binding
sensitivity using errors subsampled at h-day spacing.

(c) **Rolling 180-day median m(s) lags structural breaks: ACCEPTED, but constrain the
interpretation.** During the 2026 refinery-era margin shift the median is slow by
construction; the model will be systematically wrong in level until the window rolls
through. This mostly biases toward FALSE NULL (model fights the market and loses) and
is part of what the frozen spec IS: the test is of THIS textbook-frontier model. The
required edit is interpretive, folded into E11: a NULL verdict must be worded as "this
frozen pass-through spec does not beat the market net of costs," never "the market
prices pass-through efficiently." Also: m(s) must be built only from as-of-available
(publication-lagged) W and zero-staleness R days; the current "as of s" wording does
not say the median input respects the d-lag rule. That is a small look-ahead hole.
Fold into E2.

(d) **W frozen at last value vs futures curve: FAIR both ways, state it.** The control
is not made unfair in either direction: the control uses zero wholesale information,
so freezing W affects only the treatment model, and freezing (vs importing a futures
curve) HANDICAPS the treatment, which is conservative for false positives. The cost is
interpretive: the market can see RBOB futures and the model cannot, so a null is again
a null OF THIS SPEC. Fold the sentence into E11's null wording. No design change.

(e) **Iteration stability: REAL TRAP, currently unguarded.** OLS is free to fit
theta_up or theta_dn with the wrong sign or rho large; iterating the fitted
AR(1)-plus-ECM 35 steps can then explode (spectral radius of the companion system > 1)
or oscillate, producing absurd point forecasts, P_model pinned at 0 or 1, and deep
fake divergences. In a trend those garbage fires can even WIN (false-positive fuel);
in chop they mechanically lose (false-null drag). Either way they are not the
hypothesis. Edit E4: (i) NO FIRE on any trade date where the fitted companion matrix
has spectral radius >= 1 OR the 35-day point forecast implies a cumulative move larger
than 3x the largest 35-day move in the fitting window (both pre-stated constants);
(ii) name the A6 fallback spec now: dR(s+1) = a + theta * g(s) (symmetric ECM, no rho),
run ONLY if the primary is degenerate by rule (i) on more than 20% of trade dates, and
always reported AS the fallback.

## 4. Execution and fee arithmetic (section 4/5), and the threshold-power contradiction

**Band-edge check, H1: the feared impossible-trade false-null generator does NOT
exist, but only because of the threshold, and the lock should show it.** BUY YES
requires P_model >= p_print + 0.08 and P_model <= 1, so p_print <= 0.92 and
p_exec <= 0.95; worst-case fee there is 1c; maximum all-in cost 0.96 < 1.00. Mirror
for NO. So no H1 fire can cost >= 1.00 and the p_exec > 1 pathology is unreachable.
No exclusion rule is needed for H1; the [0.03, 0.97] band plus the threshold already
closes it. Edit E15: add this two-line arithmetic to section 5 so nobody "discovers"
an exclusion rule after the results are in.

**Boundary EV at the threshold: the lock's claim checks out but proves the wrong
thing.** At the fire boundary: 0.08 - 0.03 haircut - fee (1-2c) = +3 to +4pp expected
net IF the model is exactly right. Meanwhile the lock's OWN 0b arithmetic says the
test can only validate an 8-14pp realized mean. A5 said, verbatim in intent: set the
threshold so the model-conditional expected net per fire is >= 8-10pp, because firing
on 3pp-margin divergences at this n guarantees an uninformative straddle. The 0.08
threshold restores exactly the failure A5 amended away: boundary fires with 3pp
conditional edge dilute the mean toward undetectability. This is the design's largest
remaining FALSE-NULL generator. Edit E8, resolving the honest tension (raising the
threshold cuts n_c and could trip the power floor): 0b must additionally compute,
OUTCOME-BLIND (P_model needs only AAA + FRED; print prices are already permitted
pre-lock; results are never touched), the distribution of |P_model - p_print| over
prints and the implied fire counts and mean model-conditional net edge at thresholds
0.08 and 0.12. Pre-commit the decision rule NOW: if the projected mean conditional
net edge at 0.08 is >= 8pp (i.e. typical fires sit far above the boundary), 0.08
stands; otherwise the binding threshold is 0.12. Those are the only two permitted
values; the choice is made before the locking commit and recorded in the E12 ledger.
This is within A5's own kill-switch procedure ("pre-lock fire-rate estimate from
divergence geometry, not outcome data") and closes the last tuning door.

**Fee formula trap:** ceil(7 * p_exec * (1 - p_exec)) goes NEGATIVE for p_exec > 1,
which H2 as drafted can produce (0.985 + 0.03 = 1.015). Unreachable for H1 (above);
eliminated for H2 by E7. State in section 4 that p_exec > 1 is definitionally
unexecutable and must never appear in any run.

## 5. H2: partially fake as locked

Two independent defects:

1. **Arithmetic infeasibility of the upper sub-band.** With the 3c haircut and 1c fee,
   any YES print above ~0.955 has all-in cost >= 0.995 = the model floor itself, so
   EV <= 0 even when the model is exactly right; prints above 0.97 cost > 1.00, a
   trade that cannot exist. The lock's "hard to clear by construction; that is
   accepted" is not honesty, it is null theater for that sub-band: losses there are
   manufactured by the simulator, not by the hypothesis. Mirror on the NO side below
   0.045.
2. **The model gate exceeds the instrument's resolution.** P_model >= 0.995 under an
   empirical CDF with the locked minimum of 40 bucket errors is only achievable when
   the strike lies OUTSIDE the entire observed error range (granularity 1/40 = 2.5pp).
   H2 firing would be driven by the sample max of an autocorrelated error set, i.e.
   noise.

**Edit E6 + E7 (keep H2 only in this repaired form, else drop it):**
- Band restricted by the feasibility condition p_print + 0.03 + fee <= 0.99: YES band
  becomes [0.90, 0.955], NO mirror [0.045, 0.10]. Prints outside the band are counted
  and reported as UNEXECUTABLE, never scored as P&L.
- H2 requires >= 200 error observations in the trade's horizon bucket (else H2
  NO FIRE). If that starves H2, that is the honest outcome.
- H2 inherits regime guard 7a and the E11 verdict lattice like H1.
- DECISION RULE, pre-committed: if 0b's print histograms show the repaired band cannot
  plausibly reach H2's floor (30 fires / 8 clusters), H2 is DROPPED at the locking
  commit and the ledger records one registered hypothesis, not two. A hypothesis that
  cannot pass by construction must not be carried for ledger padding.

## 6. Clustering (section 7)

Checked the boundary mechanics: clustering is BY SETTLEMENT EVENT (each fire inherits
its event's close-week key), so "most of the trading happened the prior ISO week" is
irrelevant; fires are never split across clusters and no fire is orphaned. One weekly
event per ISO week; a monthly settling mid-week merges with that week's weekly event,
which is the CORRECT direction (their settlement prints are days apart on a smooth
series, hence strongly correlated). The scheme is strictly coarser than per-event
clustering, i.e. conservative. Adjacent-week serial correlation (a monthly settling
Friday vs the NEXT Monday's weekly, 3 days apart but different clusters) is real but
is exactly what the binding-adjacent month-block guard 7a exists for; per-event
clustering would be WORSE, not cleaner, and I recommend AGAINST changing the scheme.

One genuine ambiguity: the ISO week of "Monday 03:59Z" depends on the timezone used
to compute the week. Monday 03:59 UTC = Sunday 23:59 ET = two different ISO weeks.
**Edit E9a: pin the cluster key as the ISO-8601 week of close_time evaluated in UTC.**
Either convention is fine; an unpinned one is post-hoc wiggle.

**Edit E9b (routing teeth for 7b):** as drafted the shock diagnostic has no
consequence, so it will be argued about after results. Pre-commit: if the binding CI
clears gate 2 but excluding the 2026-02-15..2026-06-30 window flips the CI to include
zero, the verdict class is SHOCK-WINDOW PASS, routed identically to FRAGILE-PASS
($0 live read only, never capital, further progress requires a new lock).

## 7. Gate logic wording (section 8/9)

Residual ambiguities that permit post-results interpretation, each with the fix:

1. **Verdict lattice and routing are not enumerated.** MARGINAL (gate 4), FRAGILE-PASS
   (7a), SHOCK-WINDOW PASS (E9b), NULL, UNDERPOWERED-NULL, PASS all exist but section 9
   only routes "PASS" and "both NULL." What follows a MARGINAL $0 read? Unstated =
   negotiable later. **Edit E11:** enumerate: PASS -> stages 1-4; FRAGILE-PASS /
   SHOCK-WINDOW PASS / MARGINAL -> stage-1 $0 read ONLY, and any continuation beyond
   it requires a NEW lock; NULL / UNDERPOWERED -> pivot per section 9. For the ledger,
   MARGINAL and FRAGILE count as non-passes. Include the E11 null-wording rule: a NULL
   is a null of THIS frozen spec, never a market-efficiency claim.
2. **Power floor met for fires but not clusters (or vice versa):** gate 1's AND already
   covers both; add one clarifying clause: failing EITHER floor = UNDERPOWERED-NULL,
   and the sub-floor quantity is named in the verdict.
3. **Control with zero or trivially few fires (gate 3).** As written, a control with
   6 lucky fires and a degenerate all-win CI "clears gate 2" and mechanically NULLs
   H1: a false-null trap via garbage inference. And a zero-fire control trivially
   passes gate 3, which is correct but should be said. **Edit E10:** the control
   "clears gate 2" ONLY if the control fire set ALSO meets gate 1's power floor AND
   its cluster CI lower bound > 0. A zero-fire or sub-floor control satisfies gate 3
   vacuously; control stats are reported in the verdict regardless.
4. **Binding run has fires but reported run has none:** the binding run governs all
   gates; an empty reported (side-matched) run is reported as 100% attrition with
   A4's capacity-story language (E15). An empty BINDING set is the market-matches-
   model NULL of section 10, named as such. Add one sentence.

## 8. Pre-lock contamination ledger (section 0)

Two gaps:

1. **The settlement-key audit touches more results than advertised.** The straddle
   comparison touches ~20-30 markets' result fields, but the "no-straddle consistency
   rate" clause touches EVERY settled market's result. The information content is
   near-nil (both keys agree there by construction), but the firewall must be
   procedural, not trust-based. **Edit E12a:** the audit script outputs ONLY
   per-market booleans (consistent under key A / key B) and aggregate rates; it never
   computes or displays any price, any trade join, or any P&L-like quantity; the raw
   result-field pull is quarantined to that script. Any audit mismatch is investigated
   for the decimal-precision cause (E13) before the key is accepted; an unexplained
   mismatch = ambiguity = KILL, per 0a.
2. **No exhaustive pre-lock computation ledger exists.** Section 0 promises results
   will be "filled in" but never promises completeness. **Edit E12b:** add a section 0c
   PRE-LOCK COMPUTATION LEDGER listing EVERY number computed before the locking
   commit: 0a consistency rates and straddle count; 0b print counts and band
   histograms per cluster; the E8 outcome-blind divergence distribution and projected
   fire counts at 0.08/0.12 with the recorded threshold decision; the in-sample
   pass-through R^2 at 1-2 week horizons (plan critic Attack 8 item 5 said this
   SHOULD be reported at lock time from AAA+FRED only; the lock silently dropped it,
   either compute it and ledger it or state its deliberate omission); and nothing
   else. Anything computed pre-lock and not on the ledger invalidates the lock.

Could the audit leak edge-tuning information? Assessed: the audit reveals settlement
keying plus, implicitly, how near-tie markets resolved. The design's thresholds are
fee-derived and its model never sees Kalshi outcomes, so the only exploitable leak
would be a strike-boundary/rounding pattern (e.g. AAA 4-decimal prints beating strikes
by hairs), which could inspire a boundary-sniping stratum. The closed strata set (no
stratum added after data) already forbids acting on that within v25; E12a plus the
booleans-only output reduces the residual to acceptable. Adequately firewalled WITH
E12a/E12b; not without them.

## 9. Additional traps found (not in the assigned list)

- **W is never defined as a single series.** Section 2 lists DGASNYH, DGASUSGULF,
  DCOILWTICO; section 3 uses W(s) singular. Post-hoc series choice is a wiggle door,
  and NY Harbor specifically sat at the center of the 2026 refinery story. **Edit
  E15a: W := DGASNYH, full stop; DGASUSGULF and DCOILWTICO appear only as named
  non-binding sensitivities.**
- **"One position per market per calendar date": timezone unpinned.** Pin to ET
  (matches the AAA publication day). Edit E15b.
- **Trades with horizon > 35 days are unhandled** (monthly markets list further out
  than the last error bucket). NO FIRE, stated. Folded into E5.
- **95% audit threshold granularity:** at n=20 straddle markets one mismatch = exactly
  95%. State whether 95.0% passes (recommend: one E13-explained mismatch may pass;
  one UNEXPLAINED mismatch = KILL regardless of the rate). Folded into E12a/E13.
- **Gate 1's "no rescue from KXAAAGASD"** is good; add the same sentence to H2's gate
  for symmetry (H2 rescue via band widening is now also foreclosed by E7's
  pre-committed band).

## 10. REQUIRED EDITS, consolidated (the lock is commit-ready when all are in)

- **E1 (section 2):** exclude fires with trade timestamps in [03:00, 09:00) ET (AAA
  publication ambiguity window). Model inputs and keying unchanged; firing only.
  Closes the one-day-stale firing vector.
- **E2 (sections 2-3):** remove the contradictory backward-fill sentence ("no filling
  anywhere; a gap day contributes no dR row"); define a valid regression observation
  (R present at s-1, s, s+1 under zero-staleness keying; W under the lag rule);
  define weekend/holiday W as carry of last lagged business-day value; m(s) median
  uses only as-of-available (lagged) W paired with zero-staleness R days, minimum 90
  pairs in the 180-day window else NO FIRE.
- **E3 (section 2):** wholesale lag primary = d-5 calendar (>= 3 business days) per
  A3 unless ALFRED-verified before the locking commit; d-3 becomes the non-binding
  sensitivity. (Restores A3; kills the look-ahead vector.)
- **E4 (section 3):** stability clamp (spectral radius >= 1 OR 35-day forecast > 3x
  max historical 35-day move = NO FIRE) and the A6-mandated named fallback spec
  (symmetric ECM, no rho; run only on >20% degeneracy; always labeled fallback).
- **E5 (section 3):** h > 35 days = NO FIRE; within-bucket errors normalized by
  sqrt(h) (pre-lock choice, frozen now); overlap caveat stated (min-40 is not 40
  independent); non-binding subsampled-error sensitivity added.
- **E6 (sections 3/6):** H2 requires >= 200 error observations in bucket (0.995 is
  unresolvable at n=40).
- **E7 (section 6):** H2 band restricted to feasibility: YES [0.90, 0.955], NO
  [0.045, 0.10]; outside-band prints counted as UNEXECUTABLE, never P&L; H2 inherits
  guard 7a; pre-committed drop rule if 0b shows the repaired band cannot reach H2's
  floor, with the ledger then recording one hypothesis.
- **E8 (sections 0b/5):** 0b additionally computes the outcome-blind divergence
  distribution and projected mean model-conditional net edge at thresholds 0.08 and
  0.12; pre-committed rule: mean conditional edge < 8pp at 0.08 => binding threshold
  is 0.12; only these two values exist; decision recorded in the E12 ledger before
  the locking commit.
- **E9 (section 7):** (a) cluster key = ISO-8601 week of close_time in UTC, stated;
  (b) SHOCK-WINDOW PASS class with FRAGILE-PASS routing when excluding
  2026-02-15..2026-06-30 flips gate 2; (c) one-paragraph honesty note owning the
  design-level 2026-knowledge contamination and naming the staged forward read as the
  only true OOS. Chronological binding split: considered and REJECTED (power
  arithmetic above); the chrono-half diagnostic stays non-binding.
- **E10 (section 8):** control clears gate 2 only if it also meets gate 1's floor;
  zero/sub-floor control = vacuous satisfaction of gate 3, stated; control stats
  always reported.
- **E11 (sections 8-9):** enumerate the full verdict lattice with routes (PASS ->
  stages; FRAGILE / SHOCK-WINDOW / MARGINAL -> $0 read only, new lock to proceed;
  NULL / UNDERPOWERED -> pivot); empty binding set = market-matches-model NULL; NULL
  wording constrained to "this frozen spec," never market efficiency.
- **E12 (section 0):** (a) audit firewall: booleans and aggregate rates only, no
  prices, no joins, no P&L-like quantities; unexplained mismatch = KILL; (b) section
  0c exhaustive pre-lock computation ledger (0a rates, 0b histograms, E8 divergence
  numbers and threshold decision, in-sample pass-through R^2 or its stated omission);
  anything pre-lock and unledgered invalidates the lock.
- **E13 (sections 0a/2):** 3-to-4 decimal AAA display change handled in the parser;
  near-tie strikes re-checked in the audit under both precisions (restores A2.5).
- **E14 (header/section 1):** restate the honest prior ~10% and the frontier-form
  escape claim (restores A1).
- **E15 (sections 2/4/5):** (a) W := DGASNYH, secondaries non-binding sensitivities
  only; (b) one-position-per-market-per-day pinned to ET calendar date; (c) add the
  two-line band-edge closure arithmetic (H1 p_exec <= 0.95, no impossible trades,
  p_exec > 1 definitionally unexecutable); (d) restore A4's >50%-attrition verdict
  language; (e) monthly-leg 5c-haircut non-binding sensitivity noted next to the flat
  3c binding haircut.

*Em-dash and en-dash audit: to be verified after write (Select-String U+2014/U+2013).*
