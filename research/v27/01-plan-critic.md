# v27 PLAN CRITIC: adversarial review of the TSA weekly nowcast taker proposal

**Date:** 2026-07-02. Role: kill the family if it deserves killing. Inputs read:
v27/00-proposal.md, v27/scout-flight-data.md, v26/04-FINAL-VERDICT.md,
v25/02-methodology-lock.md, v24/00-HANDOFF-PROMPT.md. Context: ~26 dead families,
capture phantom on every public-info forecast idea, v26 killed pre-lock on
(a) certainty fires nonexistent in the executable band and (b) today's TSA page is
not the as-of series.

## VERDICT: PROCEED-WITH-AMENDMENTS

This is a better-constructed proposal than v26 and it genuinely differs on the two
axes that killed v26: continuous divergence instead of arithmetic certainty (so
fires can exist inside the executable band), and a vintage reconstruction instead
of today's page (so the as-of problem is at least addressed rather than ignored).
The D1 two-part construction is clever and MOSTLY honest, but as written it
contains one real backdoor (an unspecified shadow that a lucky D1 can open
indefinitely), one unreconciled factual conflict with v26's own audit (revision
magnitudes), one quietly contaminated feature (BTS scheduled counts in disruption
weeks), and a deployment timeline the proposal understates by roughly an order of
magnitude. None of these is intrinsic to the idea; all are lockable. Hence
amendments, not kill. The amendments below are BINDING: the methodology lock must
incorporate every A-numbered item or the lock is invalid.

The single most likely outcome remains: H1 nulls (market-matches-frontier), D1
shows something in 3-6 disruption clusters, LOCO flags concentration, and the
family dies at the D1 concentration gate. That is a fine, cheap, honest outcome.
Budget accordingly.

## 1. The D1 construction: honest in principle, backdoor in practice

The idea of a registered, capital-firewalled, deliberately look-ahead upper bound
whose PRE-COMMITTED rule either kills the family or justifies a live shadow is
legitimate. It answers a question no reconstructible backtest can: is there any
information in weekend flight outcomes that the ladder failed to price? If even
PERFECT weekend flight knowledge cannot beat the ladder net of frictions, the
disruption channel is dead and no feed, paid or free, can save it. That is a
clean kill switch and it is the strongest part of the proposal.

But the proposal's shadow clause is a backdoor as written:

- ">= 8-week live shadow" has a floor and NO CEILING, no pass gate, no fail gate,
  no cluster floor, and no statement of what happens after. An open-ended shadow
  that continues until it looks good is shadow-shopping, which is optional
  stopping, which manufactures the false positive this project exists to avoid.
- 8 weeks is 8 clusters at best. With the v25 sigma_c ~ 0.40, the 95 percent CI
  half-width at n_c = 8 is 1.96 * 0.40 / sqrt(8) ~ 28pp. An 8-week shadow can
  validate only a ~28pp mean edge, which does not exist. The 8-week number is
  cosmetic; it cannot adjudicate anything. See section 5 for the honest timeline.
- "EVEN IF H1 nulls" plus no LOCO requirement on D1 means one Southwest-meltdown
  cluster can single-handedly open the shadow. D1's fires will concentrate in a
  handful of disruption weeks by construction; without a concentration gate D1 is
  a lottery ticket on one week's tail.
- D1's decision rule says "clustered CI lower bound > 0 with mean >= 8pp" but does
  not say NET of what, at what cluster floor, with what fitting discipline. A
  look-ahead diagnostic with look-ahead FITTING (coefficients estimated on the
  substituted actuals) is not an upper bound on the channel, it is an upper bound
  on overfitting.

**A1 (D1 estimator, binding).** D1 uses the IDENTICAL v25-template execution
simulation as H1: taker prints, +3c binding haircut (see A9), worst-case quadratic
fee, one position per market per ET day, same fire window, same cluster key. The
8pp threshold in D1's decision rule is defined NET of haircut and fee. D1's model
coefficients are fit walk-forward on H1-permissible information only; the
look-ahead substitution happens at INFERENCE input time only (actual flown and
cancelled counts replace the scheduled counts as feature VALUES). No coefficient,
scaler, or error distribution may be estimated on the substituted actuals.

**A2 (D1 gates, binding).** D1's pre-committed rule in the lock must read: PASS
requires (i) >= 20 fires AND >= 8 fired clusters (else UNDERPOWERED-D1, family
DIES: if the deliberately generous test cannot reach even this floor, the channel
has no testable surface); (ii) clustered bootstrap 95 percent CI lower bound > 0
on net P&L; (iii) mean net >= 8pp; (iv) LOCO: dropping the single best cluster
must NOT flip the CI to include zero (else D1 = SINGLE-CLUSTER, family DIES, no
shadow); (v) the month-block regime guard from v25 section 7. All five or no
shadow. D1 outcomes other than PASS route to family death. There is no D1
MARGINAL.

**A3 (shadow spec in the LOCK, binding).** The lock must contain the complete
shadow protocol BEFORE any data is pulled: (i) shadow starts only after D1 PASS
and only once the self-archived as-of feed (FlightAware /live/cancelled +
/yesterday + nasstatus polling) has been running and archiving; (ii) FIXED
evaluation design: one interim look at week 13 permitted ONLY as an early KILL
(CI upper bound < the net hurdle), one binding evaluation at week 26, and a hard
stop at week 39 if fired-cluster count at week 26 was below floor (single
pre-committed extension, never more); (iii) shadow PASS = clustered CI lower
bound > 0 net of REALIZED spread and fee, >= 12 fired clusters, LOCO-robust;
(iv) shadow PASS routes to the charter's tiny-pilot stage, shadow FAIL = family
dead, no second shadow ever; (v) the feature set, thresholds, and feed spec are
frozen at shadow start; any change = new family number. Item (ii) exists because
"at least 8 weeks" invites running until lucky; the lock must make continuation
mechanical, not discretionary.

**A4 (D1-to-H1 firewall, binding).** No component fitted, tuned, or selected using
D1's substituted inputs or D1's results may be shared with H1. Concretely: H1's
results are computed and written to the verdict doc BEFORE D1 is run, and the lock
states this ordering. Kill risk 4 in the proposal names this; the lock must
operationalize it as an ordering constraint, not a wish.

## 2. H1's information content: near-certain null, kept anyway as D1's floor

Attack: TSA volumes are ferociously seasonal. Same-weekday ratios are stable
within ~2-4 percent, and the published Mon-Thu partials already anchor the week's
LEVEL shock (holiday demand and macro drift show up Mon-Thu too). The settlement
is the 7-day mean, so weekend-day forecast error e moves the settlement by ~3e/7.
A 2-4 percent weekend residual is ~1-1.7 percent on the weekly average. What do
BTS scheduled-flight counts add on top? Schedules are themselves near-perfectly
seasonal; their week-over-week information increment after conditioning on
seasonality plus the Mon-Thu partials is plausibly well under 1 percent of
volume, except in schedule-shock weeks. For an 8pp PROBABILITY divergence to be
generated by the schedule term, the term must move the settlement distribution
materially relative to strike spacing; in a normal week it will not. So H1 vs its
own control will fire rarely outside disruption weeks, and in disruption weeks
the schedule term is contaminated (section 4). H1 is v25's shape: a public model
racing a ladder that plausibly already sits at this frontier, and the honest
prior of 8-10 percent is if anything generous.

Would I cut H1? NO, for three reasons. (i) D1 without H1 is uninterpretable: D1's
delta over the H1/control machinery IS the measured value of weekend flight
information; without the reconstructible baseline you cannot say whether D1's
edge came from flight data or from the partials-plus-seasonality frame. (ii) H1
is nearly free: same pipeline, same audits, one extra model run. (iii) An H1 null
with a D1 pass is exactly the evidence pattern that justifies paying for the
as-of feed; an H1 null alone justifies nothing. H1 earns its place as the honest
baseline, not as a live candidate.

**A5 (H1 expectation set honestly, binding).** The lock's prior section must state
that H1 is expected to fire thinly outside disruption weeks and that an H1
UNDERPOWERED-NULL or empty-fire-set outcome is anticipated and does NOT by itself
kill the family (D1 adjudicates). Conversely an H1 PASS routes only to the same
D1-then-shadow path, never directly further: the schedule term's disruption-week
contamination (section 4) makes a standalone H1 pass unbankable by construction.

## 3. Vintage completeness: the availability proof is currently an assertion

Two problems, one of them a direct factual conflict with v26.

**The conflict.** v26's final verdict records: 12 snapshots, 120 sampled values,
5 revisions ABOVE 0.5 percent, worst +2.9 percent (2025-06-07), all upward. The
v27 proposal asserts: 527-day reconstruction, 6 revisions, NONE over 0.5 percent.
Both cannot describe the same quantity. The likely reconciliation is that v26
measured first-published vs TODAY'S page (long-horizon restatements included)
while v27 measures snapshot-to-snapshot within the market window. If so, both can
be true and v27's number is the relevant one for firing, BUT the quantity that
matters for P&L is a THIRD one neither has isolated: first-published value vs the
value THE MARKET SETTLED ON (the page state at settlement time, roughly the
following Monday-Tuesday). A +2.9 percent revision of a published anchor day
landing between fire time and settlement is larger than the entire weekend
seasonal residual and flows straight into P&L as unmodeled noise, or worse, bias
(v26 found all revisions upward).

**A6 (revision reconciliation, binding, pre-lock kill switch).** Before the lock
commits, a written vintage audit artifact (currently NONE exists in research/v27;
the 527-day claim lives only inside the proposal) must report, per revised value:
first-published, value at settlement time, value today. The lock's 0a must
compute the distribution of (settlement-time minus first-published) for all
partial-week days used as anchors, and reconcile the v26 numbers explicitly. Kill
rule: if more than 2 percent of anchor-day values move by more than 0.5 percent
between first publication and settlement, OR if the movement is systematically
signed (binomial p < 0.05 on sign), the family dies pre-lock unless the fire
threshold is raised to absorb it under a written arithmetic argument.

**The availability gap.** A fire on day X needs every anchor day's value proven
published AT OR BEFORE the fire timestamp. The TSA-page Wayback density is 112
snapshot-days over the 427-day scout window (and ~450 snapshots over 527 days per
the proposal). Most fire timestamps will NOT have a same-day, pre-fire snapshot.
Inferring availability from the "TSA posts by ~9am ET Mon-Fri" schedule is an
ASSUMPTION, and it fails exactly where fires concentrate: federal-holiday weeks,
when TSA posting is known to slip and when Monday is a holiday. v26 died partly
on assuming today's page was the series; v27 must not die on assuming the
posting schedule was the series.

**A7 (evaluability coverage, binding, outcome-blind in 0b).** 0b computes, per
(ISO week, fire-day) state: is every required anchor value's first_seen timestamp
in the vintage <= the fire timestamp, with NO schedule-based inference (a value is
available only when a snapshot proves it). Report the evaluable fraction overall
and separately for holiday weeks. Pre-committed rule: if fewer than 60 percent of
lifetime clusters have at least one fully evaluable fire-day, the binding
universe is RESTRICTED to evaluable states and the power floors (A10) are
re-checked against the restricted count; if the restricted count cannot reach the
floors, H1 is UNDERPOWERED at birth and the lock must say so before data.
Unevaluable state = NO FIRE, never a fill (v25 E2 discipline carries over).

## 4. BTS scheduled counts: mildly look-ahead exactly where it matters

The monthly BTS on-time file is an as-flown record. Its "scheduled" rows for day
d reflect the schedule as reported by carriers around d, not the schedule as
knowable on the prior Wednesday. In a normal week the difference is noise (well
under 1 percent). In a disruption week it is MATERIAL and FAVORABLE: mass
pre-cancellations are pulled from or flagged in the schedule 1-3 days ahead, so
the file's scheduled-and-cancelled structure partially encodes the disruption
that a Wednesday observer could not yet see. Fires concentrate in disruption
weeks. So H1's schedule term is quietly contaminated precisely in its fire set,
in the direction that flatters H1. There is no free ex-ante schedule archive to
fix this historically.

**A8 (schedule term treatment, binding).** The lock adopts ALL of: (i) H1's
schedule feature is the MONTHLY-AGGREGATE-DERIVED day-of-week scheduled count
profile, not the per-day count, in any week containing a federal holiday or where
the realized cancellation rate later exceeded a pre-set percentile (computed
outcome-blind from BTS only, never from Kalshi data); OR ALTERNATIVELY (ii) the
per-day count is kept everywhere but the lock states in the honesty section that
H1 carries a pro-H1 contamination in disruption weeks, an H1 pass therefore
cannot route past the D1-shadow path (already A5), and a named non-binding
sensitivity re-runs H1 with schedule features REMOVED in flagged weeks and
reports the delta. The lock must pick (i) or (ii) explicitly, before data. Either
is honest; silence is not.

## 5. Power and deployment arithmetic: say the real timeline out loud

Using the v25 constants (sigma_c ~ 0.40, half-width 1.96 * 0.40 / sqrt(n_c)):

| Fired clusters | CI half-width | Detectable mean edge |
|---|---|---|
| 8 | ~28pp | fantasy |
| 15 | ~20pp | fantasy |
| 30 | ~14pp | large only |
| 60 | ~10pp | large only |
| 90 | ~8pp | the 8pp gate itself |

Lifetime universe: 87 clusters. If continuous divergence fires broadly (the v25
pattern was 52 of 91 clusters), a 30-cluster floor is reachable and H1 is
testable at the validate-only-a-large-edge ceiling, same honest ceiling v25
accepted. If fires concentrate in the 5-8 holiday/disruption weeks per year that
the proposal itself names as kill risk 3, the lifetime fired-cluster count is
roughly 10-18 and H1 is UNDERPOWERED before it starts.

**A9 (execution realism, binding).** The scouted ~3c median spread was not
conditioned on the fire regime: near-ATM strikes, Thu-Sun, in high-uncertainty
weeks, on a ladder doing 59,345 prints across 1,750 markets (~34 prints per
market LIFETIME). Spreads widen exactly when this strategy fires. 0b must report,
outcome-blind: per-week in-band print counts, and the spread proxy (or print
dispersion) separately for holiday/disruption weeks vs normal weeks. Binding
haircut: +3c in normal weeks, +5c in any week flagged by the A8 disruption
criterion. If per-week in-band prints show the fire window is print-dead in the
median week (as v26 found for its band), the market-matches-frontier null must be
declared cheaply at 0b, not discovered after modeling.

**A10 (power floors, binding).** H1 keeps the v25 floor: >= 40 fires AND >= 30
fired clusters, else UNDERPOWERED-NULL with the sub-floor quantity named. 0b must
project fire counts outcome-blind at candidate thresholds (A11) and, if the
projection cannot reach the floor, the lock records H1 as unpowered BEFORE data
and the family proceeds as a D1-only adjudication (A2 floors), or dies if the
operator declines that reduced scope.

**A11 (threshold vs hurdle, binding).** The all-in hurdle at ATM is ~5c: +3c
haircut (5c disrupted) plus the worst-case quadratic taker fee ceil(7 * p * (1-p))
= 2c for p in roughly [0.20, 0.80], which is where these fires live, unlike v26's
certainty fires at the fee-cheap extremes. An 8pp threshold therefore clears the
normal-week hurdle by only ~3pp before model error and revision noise (A6), and
clears the disrupted-week hurdle by ~1pp, i.e. not really. The lock adopts the
v25 E8 two-candidate rule with candidates 0.08 and 0.12 and the pre-committed
selection rule: projected mean model-conditional NET edge at 0.08 must be >= 8pp
NET or the binding threshold is 0.12. No other values, decided in 0b, recorded
before the locking commit.

**The deployment fact the operator needs stated plainly.** The shadow accrues at
MOST ~4.3 clusters per month, and only fire-weeks count. If fires are broad, 30
fired clusters take ~7 months and 60 take ~14 months. If fires concentrate in
disruption weeks (~1 per month), 30 fired clusters take ~2.5 YEARS. The honest
statement for the lock and the verdict doc: a fundable live verdict on this
family is 7 to 30 months away from shadow start, and the proposal's ">= 8-week"
phrasing describes the minimum runway, not a decision timeline. If a 7-30 month
path to first capital is unacceptable, the correct move is to kill NOW, at $0,
rather than after a year of shadow. The critic's read: the family is still worth
running BECAUSE the backtest phase is cheap and D1 can kill it this month; but
nobody should start the shadow without accepting the timeline in writing.

**A12 (timeline acknowledgment, binding).** The lock reproduces the table above
and the 7-to-30-month shadow arithmetic verbatim, and the shadow may not start
without an explicit operator acknowledgment line in the lock or a linked
operator decision doc.

## 6. Settlement key, units, and calendar traps (v26 carryovers)

- **Units change mid-series.** v26 found floor_strike flips between raw counts
  and millions within a series' history. The 0a settlement-key audit must
  normalize units per market from metadata, never by heuristic, and reproduce
  every settled result from the reconstructed weekly average with the v25 E12a
  firewall (booleans and rates only). Any unexplained mismatch = ambiguity =
  KILL before data.
- **Which Sunday.** The lock must define, per event, exactly which Mon-Sun window
  settles it, derived from Kalshi metadata, and the 0a audit must verify it the
  same way v25 0a adjudicated key D vs D-1 (straddle-decisive design).
- **Close time vs publication.** Do NOT assume Sun 23:59 ET or Mon 03:59Z. During
  EDT, Mon 03:59Z = Sun 23:59 ET; during EST it is Sun 22:59 ET. Pull close_time
  per market. Kill check: no market's close may sit AFTER the Monday ~9am ET
  publication window; if any does, the unpublished-weekend premise is false for
  that market's final hours and those hours are excluded from the fire window by
  rule. Also verify intra-week: Thursday's value posts Friday ~9am ET, so a
  Friday 08:00 ET fire has only Mon-Wed anchors; evaluability (A7) must be
  computed at fire-TIMESTAMP granularity, not fire-day.
- **Holiday publication delays.** Already covered by A7's no-inference rule, but
  the lock should name it: holiday-Monday weeks may lack the Monday publication
  entirely until Tuesday; any fire whose anchor set assumes it = NO FIRE.
- **2023 restatement era (v26 E1 carryover).** All seasonality and day-of-week
  factors must be estimated on vintage first-published values or pre-2025
  archives with the restatement documented, walk-forward, never on today's page.
  The proposal's kill risk 5 already owns this; the lock must operationalize it.
- **DST inside the week.** Two clusters per year contain a DST transition;
  day-of-week ratio estimation must key on ET calendar days (TSA's publication
  basis), and the cluster key stays ISO week UTC per v25 E9a. State it; do not
  improvise it in code.

## 7. What would change the verdict

KILL now if any of: (i) the A6 audit shows settlement-window revisions are
v26-magnitude (worst +2.9 percent) rather than proposal-magnitude (under 0.5
percent); (ii) A7 evaluability comes back under ~40 percent of clusters; (iii)
0b per-week in-band print counts show the Fri-Sun near-ATM band is print-dead in
the median week. Each is checkable outcome-blind, pre-lock or at 0b, for $0.
PROCEED without amendments was never on the table: the shadow backdoor (A3) alone
is disqualifying as written.

## Amendment index

- A1: D1 uses identical binding execution sim; net 8pp; walk-forward coefficients;
  look-ahead at inference inputs only.
- A2: D1 gates: 20 fires / 8 clusters floor, CI LB > 0, mean >= 8pp net, LOCO,
  regime guard; anything else = family death; no D1 MARGINAL.
- A3: full shadow protocol in the lock: gated start, week-13 early-kill only,
  week-26 binding eval, week-39 hard stop, pass/fail routing, frozen spec, one
  shadow ever.
- A4: D1-H1 firewall as an ordering constraint (H1 verdict written before D1 runs).
- A5: H1 expectation and routing: anticipated thin/null; a pass routes only into
  the D1-shadow path.
- A6: revision reconciliation vs v26 (+2.9 percent finding) on the
  first-published-vs-settlement-time quantity; written vintage audit artifact
  required; pre-lock kill switch.
- A7: evaluability coverage in 0b, snapshot-proven availability only, no
  posting-schedule inference; 60 percent restriction rule.
- A8: BTS schedule contamination treatment: pick (i) monthly-profile feature in
  flagged weeks or (ii) owned contamination + removal sensitivity.
- A9: per-week in-band print counts; +5c haircut in flagged weeks; cheap
  print-dead kill at 0b.
- A10: H1 power floor 40/30; sub-floor projection = D1-only scope or death,
  decided pre-data.
- A11: threshold rule: 0.08/0.12 two-candidate E8 clone; hurdle arithmetic (~5c
  normal, ~7c disrupted) stated in the lock.
- A12: the 7-to-30-month shadow timeline reproduced in the lock with explicit
  operator acknowledgment before any shadow starts.

*Em-dash audit: clean (verified after write).*
