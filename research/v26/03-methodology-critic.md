# v26 METHODOLOGY CRITIC: stress review of the draft lock

**Date:** 2026-07-02. Role: stress the lock AS WRITTEN before commit: false-positive
vectors, false-null vectors, ambiguity permitting post-hoc wiggle, implementation
traps, amendment fidelity. Inputs: 02-methodology-lock.md (target), 01-plan-critic.md
(A1-A10), scout-data-sources.md, 00-proposal.md, v25/02-methodology-lock.md (carried
machinery). Standard: the v25 round's critic caught the EIA weekly-release calendar
and interpolation phantoms; this review hunts at that level.

## VERDICT: LOCK-OK-WITH-EDITS

Four blocking defects (E1-E4) and fourteen required edits (E5-E18). No REDESIGN: the
two-hypothesis structure, the certainty restriction, the clustering, and the fee/band
machinery are sound. Every defect found is a bounded edit to text or audit scope, but
E1 and E2 are genuine leak vectors of exactly the class this project has died from,
and the lock must not commit without them.

## 1. Killer-class findings (blocking)

### K1 -> E1: the H-A trailing-730-day bound input reaches into the 2023-2024 TSA
### restatement regime, and the 0a2 audit window does not cover it

The universe starts at close_time 2025-05-01, so the trailing 730-day same-day-of-week
extreme window for early fires reaches back to roughly 2023-05-01. The scout proved
that window is poisoned: 183 of 194 overlapping 2023 dates on today's page are
post-restatement, predominantly UPWARD, worst case +6.1 percent (1/16/2023 +129k), and
the restatement landed between Jul 2023 and May 2024. 0a2 samples only May 2025 - Jun
2026, so it structurally cannot see this. Consequence: a YES fire's ADVERSE bound uses
the historical MIN; if that min day was restated upward, the as-of-invisible restated
value narrows the adverse bound and fires trades no live trader could have certified.
Min/max statistics are maximally sensitive to exactly the extreme days that took the
largest restatements. This is a false-positive vector aimed at the precise mechanism
of the fire rule.

**E1 (blocking):** extend 0a2 coverage to the FULL bound-input span (earliest possible
fire date minus 730 days, i.e. from 2023-05-01), diffing EVERY overlapping date in
each snapshot against the signal series (the scout's diff method already does this),
not merely the snapshot's own date. Accepted alternatives, chosen pre-lock and
recorded in 0c: (a) truncate the H-A universe start so that no bound input predates
the verified-stable regime; (b) build the 2023-2024 portion of the bound-input series
FROM Wayback as-of values. One of the three, no fourth option.

### K2 -> E2: the A7 KXTSAW close-time vs Monday-publication exclusion was dropped

Plan-critic section 9 item 2, bound in by A7 ("verbatim"), requires excluding any
trading window at or after the Monday full-publication moment as post-FULL-
determination. The lock contains no such clause, and its fire rule quietly permits it:
"published day-values P_pub (subset of the Mon-Sun week)" includes the improper
subset. If KXTSAW markets trade Monday after 12:00 ET (per-market close_time never
enumerated), the bound rule degenerates to 7/7 published days = exact arithmetic on a
fully-determined market. That is an unregistered MLB-null-shaped sub-case that
inflates fire counts and contaminates the gradual-determination claim the family
exists to test.

**E2 (blocking):** enumerate per-market close_time in 0a. H-A fires require AT LEAST
ONE unpublished day at fire time. Any print at or after the full-week visibility
instant (Monday 12:00 ET after the week ends) is excluded from firing and counted in
a separately REPORTED, never-scored post-determination stratum.

### K3 -> E3: 0a3's eps estimator is undefined; a kill switch computable a dozen ways

"If the downward-revision rate implies a post-crossing reversal probability that
cannot be bounded below 0.5 percent" names no numerator, no denominator, no
confidence treatment, and no link to the 0.02 margin; and ">= 3 stations" waters down
A6's all-ten-stations requirement. As written, the audit can be run several defensible
ways, some passing, some killing: that is post-hoc wiggle on a kill switch.

**E3 (blocking), frozen estimator:**
- Numerator: events where a published month-to-date value DECREASES BY MORE THAN 0.02
  inch at any later issuance in the same station-month, measured on the SAME product
  stream used for firing (all archived CLI issuances including corrections and AM/PM
  versions).
- Denominator: station-day issuance steps across all archived station-months
  (~10 stations x ~28 months x ~30 days gives roughly 8,000+, enough for the
  zero-event case).
- eps_day = 95 percent Clopper-Pearson upper bound of that rate (rule-of-three at
  zero events).
- Per-fire reversal exposure = eps_day x mean remaining issuance-days after crossing
  among 0b's projected fires.
- H-B2 is dropped if the per-fire bound is >= 0.5 percent.
- The ACIS-vs-final-CLI/CLM cross-check runs on ALL TEN stations (A6 as written), not
  three.
Note the coherence this buys: reversals of 0.01-0.02 inch are absorbed by the margin
and correctly do NOT count; only margin-exceeding reversals are priced, which is what
eps must mean.

### K4 -> E4: the H-A bound formula is not computable one way

"Historical min/max share-adjusted value" defines neither "share-adjusted" nor the
rescaling to the current week. Min/max of what: raw counts, day-of-week share of the
week total, level-scaled ratio? Scaled to the current week by which denominator? A2
said "level-scaled"; the lock says "share-adjusted"; neither is a formula. Every
choice changes the fire set, which is the definition of post-hoc wiggle.

**E4 (blocking):** freeze the exact formula. A suggested one-way form: for unpublished
day d, bound_d = extreme over trailing 730 as-of days u (same weekday as d) of
value(u) / mean7(u), where mean7(u) = trailing 7-day mean ending at u, multiplied by
the current week's published-days mean; widen min by x0.85, max by x1.15. Whichever
variant is frozen, every window, denominator, and edge case (fewer than 7 published
current-week days is the ONLY case, since fires need >= 1 published day: state the
minimum published-day count too) must be written as arithmetic.

## 2. Required edits (high)

### E5: revision tolerance vs bound margin are inconsistent at the edge

0a2 tolerates sub-0.5-percent revisions, so the backtest's "published" values may sit
up to 0.5 percent from what was visible. A fire whose adverse bound clears K by less
than that tolerated drift is not certain as-of. Edit: H-A fires require the adverse
bound to clear K by at least 0.005 x K (about 13k on a 2.6M-average strike, cheap
against ~50k strike spacing). Mirror on the NO side. This makes the fire rule and the
audit tolerance a coherent pair.

### E6: the certainty framing hides a real fat tail; own it in wording

The widened 730-day extreme is an EMPIRICAL bound, not arithmetic. A ground-stop,
9/11-scale, or weather-shutdown day in the unpublished remainder breaks any
historical-min x 0.85 floor: a YES bought at 0.95 settles NO for about -97c, erasing
~30 modal wins. The 2025-2026 sample cannot contain such a day, so the backtest CI
structurally cannot price this tail; it is H-B2's eps with no audit to bound it.
Edit: (a) rename the claim "empirical-bound certainty" throughout (true arithmetic
certainty exists only at 7/7 published, which E2 excludes); (b) pre-commit verdict
wording: any H-A pass states that the measured mean excludes an unpriced disruption
tail, with the tolerance arithmetic made explicit (at +3c modal win, breakeven
disruption incidence is roughly 1 per 3,000 unpublished-day exposures); the staged
live path and position caps are the control for this tail, never the CI.

### E7: define "the deciding publication" one way; the H-A bound is not monotone

Note first the trap: a published day can come in BELOW its widened min, so publishing
can UN-clear a previously cleared bound. Latency and the invalidation check therefore
need a definition robust to re-crossings. Edit, frozen: H-A deciding publication for
a fire at print time t = the earliest publication instant u <= t such that the bound
rule holds at u and at every publication instant in (u, t]. H-B2 deciding issuance =
the earliest archived CLI issuance u <= t - 30 min with month-to-date > K + 0.02 such
that every later issuance up to t also satisfies it. Latency = t - u, computed in 0b
outcome-blind. A fire with t < u is impossible by construction; if observed it is an
implementation defect: the run is invalid, the bug is fixed, the FROZEN rules are
re-run once, and the incident is recorded in the ledger (bug-repair rerun, not a
second bite).

### E8: pre-commit a symmetric print-sanity quarantine

A post-crossing print at 0.10 inside the [0.03, 0.955] band is a +0.86 net-if-right
observation, ~30x the modal win; a single such fire can carry its cluster and the CI.
It is far more likely to be a bad print, strike-parse error, or station-mapping error
than a genuine 90c posted free lunch. Nothing in the lock guards this. Edit, frozen
and SYMMETRIC: quarantine before scoring (a) every certainty fire with net-if-right
> 0.50 (i.e. YES prints below 0.50; NO mirror equivalently), and (b) EVERY losing
certainty fire (settles against the determined side). Frozen verification protocol:
re-parse the strike from raw market JSON; re-verify series-to-station mapping;
re-read the crossing/bound from raw source text (archived CLI or TSA values); re-pull
the print from the raw trade record. Verified-genuine fires are scored AS-IS (a real
loss stays a loss; a real cheap print stays a win); verified data-error fires are
excluded AND counted as defects; more than 2 defects invalidates the run per E7's
repair rule. Identical protocol both directions, so it can neither fabricate a pass
nor rescue a null. All quarantine dispositions are listed in the verdict doc.

### E9: H-A floor deviates from the plan critic silently; honest-ceiling text missing

Critic section 7 set H-A at 40 fires / 30 clusters and REQUIRED an honest-ceiling
statement; the lock ships 30 / 12 with neither justification nor the statement. At 12
clusters the half-width is ~5.7pp at sigma_c 0.10: a +1-6c edge passes only if losses
are essentially absent, which is arguably CORRECT behavior for a certainty claim, but
the lock must say so, not silently lower the bar. Edit: add the pre-committed
rationale (certainty-zone sigma argument) plus the critic's required sentence: H-A
can pass only if fires are numerous, cheap, and near-uniformly winning; any other
texture is UNDERPOWERED-NULL with the sub-floor quantity named. Alternatively restore
40/30. Either is acceptable; silence is not.

### E10: holiday handling waters down A7 item 9.1

The lock's "visibility = next Mon-Fri noon by construction ... never a leak" assumes
the publication schedule holds in exactly the weeks TSA warns it may not ("holiday
weeks though may be slightly delayed"). Edit: (a) restore 9.1: in weeks containing a
federal holiday, a fire may consume a day-value only if a Wayback or live-capture
snapshot confirms the value was posted by the assumed visibility instant; otherwise
zero-staleness NO-FIRE for that week; (b) state that holiday days REMAIN in the
trailing extreme window (they only widen the bound: conservative) and that
federal-holiday weeks are flagged from the fixed calendar as a reported stratum.

### E11: noon visibility and the 30-minute AFOS margin are asserted, not verified

The TSA page claims "by 9 a.m."; the scout verified presence once, at ~15:00 ET. Noon
(9am + 3h) is plausible but unverified, and no latency diagnostic can detect late
posting because posting timestamps do not exist. Edit: either verify by-noon posting
on >= 5 sampled days (intraday Wayback captures, or live checks during the pre-lock
window) and record in 0c, or move binding visibility to 15:00 ET (the verified bound;
costs only intra-day fire timing). Same class: the 30-minute IEM AFOS ingest margin
is an assumption; sample >= 10 current-day CLI products, compare product issuance
stamp vs first-retrievable time, widen the margin if any sample exceeds 30 minutes,
record in 0c.

### E12: A9 shipped at one-third strength

A9 specified three outcome-blind diagnostics (publication-to-first-print latency,
post-publication volume share, distinct price levels per market-day) PLUS a
pre-committed interpretation ("fast systematic repricing = the expected
market-matches-arithmetic NULL"). The lock carries latency only and no interpretation
sentence. Edit: restore all three diagnostics and the interpretation sentence
verbatim into 0b, computed per underlying.

### E13: rain decimal and trace semantics dropped (critic 9.5, bound by A7)

The lock never states T = 0.00 for CLI month-to-date parsing nor exact-decimal
comparison. Edit: all precipitation arithmetic in INTEGER HUNDREDTHS of an inch
(string parse, never floats); T parses to 0; fire comparison is MTD_hundredths >
K_hundredths + 2; strikes taken from the market's floor_strike decimal exactly (a
strike of "4" is 400 hundredths; no tolerance); a total exactly equal to the strike
settles NO and the 0a reproduction must agree. Under these semantics the 0.02 margin
is coherent: a late correction of 0.01 or 0.02 cannot flip a fire; only
margin-exceeding corrections can, and those are exactly what E3's eps prices.

### E14: refire inflation and concentration texture

One position per market per ET day (v25 E15b, carried) lets a single crossed market
refire daily for weeks: 30 fires can be 2-3 markets. All same-market fires share a
close_time cluster, so the CI is honest and the cluster floor is the real guard, but
the fire floor is cosmetically inflatable and a pass could be one city in one wet
season. A hard two-city floor is REJECTED here: ~19 of the months are NYC-only by
construction, so that floor would manufacture nulls. Edit: (a) report distinct fired
MARKETS per hypothesis and add a floor of >= 12 distinct markets for H-B2 (>= 10 for
H-A); (b) pre-commit a CONCENTRATED-PASS label, routed exactly like FRAGILE-PASS
(stage-1 $0 read only), when more than 80 percent of H-B2 fires come from a single
city.

### E15: the volume-month guard has no teeth

v25's shock-window guard ROUTED (SHOCK-WINDOW PASS = stage-1-only). Its named
replacement is "reported; binding only through the LOCO gate", which is strictly
weaker than the machinery the lock claims to carry. Edit: if excluding the single
highest-volume calendar month flips the binding CI to include zero, the verdict class
is FRAGILE-PASS, same routing as the month-block guard.

### E16: restate the audit firewall; close the "unexplained mismatch" wiggle

0a and 0a3 necessarily touch settlement results; the lock does not restate the E12a
firewall A1 required (booleans and rates only, no prices, no trade joins, no
P&L-like quantity). And "any UNEXPLAINED mismatch = KILL" leaves "explained"
open-ended, which is where wiggle lives. Edit: restate the firewall for every section
0 audit; enumerate the ONLY permitted explanation classes in advance (v25 E13
pattern): (a) display precision / rounding of expiration_value; (b) a documented
corrected CLI that ACIS did not ingest, in which case reproduction switches to the
final CLI/CLM value for that month, recorded in 0c. Anything else = KILL.

### E17: the contested universe count is asserted as fact

"48 historical + recent live events" restates the proposal's side of the exact
contradiction A1 flagged as blocking (scout: 10 settled weeks = "the full series
history"). Edit: phrase the count as PENDING the 0a enumeration; the lock must not
carry a number its own audit exists to establish. Also add the A3-mandated sentence,
currently missing: settled-bracket reproduction CANNOT detect sub-bracket revisions;
only 0a2 addresses the signal path.

### E18: frozen knobs without provenance

730 days, 15 percent widening, and 0.02 inch were frozen by a researcher who has seen
recent TSA and rain data; they have no stated a-priori derivation and will read as
tuned in any post-mortem. Edit: one sentence of a-priori rationale per constant in
the lock, plus an outcome-blind 0b sensitivity: fire and cluster counts at the
neighbor grid (widening 10/15/25 percent; lookback 365/730 days; margin
0.01/0.02/0.05 inch), REPORTED only; binding constants never reselected from it.

## 3. Checked and clean (no edit required)

- **A5 breakeven table:** every row recomputed under fee = ceil(7 x p_exec x
  (1 - p_exec)) cents at p_exec = p + 0.03; all five rows verified; band top 0.955
  nets +0.005; the NO mirror [0.045, 0.97] closes identically; no fire can cost >= 1.
  (Optional one-liner to complete A5: "a band-edge loss erases ~32 band-edge wins".)
- **Control-gate replacement (concept):** dropping gate 3 is honestly justified; a
  no-partial-info control cannot fire when the fire condition IS the partial-window
  fact, and a vacuous gate is worse than a named replacement. With E7 and E12 the
  replacement is adequate.
- **H-B1 non-registration:** justified, mechanism stated, consistent with A4's split
  logic and A10's decrease-only rule. Registering it would have been null theater.
- **Clustering (A8):** calendar month across ALL cities for H-B2, ISO week for H-A,
  both keyed on close_time; all refires of one market share a cluster; conservative
  and correct.
- **H-B2 YES-only registration:** correctly pre-declared; month-end NO-certainty
  correctly excluded; no NO-side seed leakage (A10 honored on the v25 seed).
- **Fee model:** matches series metadata (quadratic x1 both families).
- **H-B2 floor reachability (stress point 5):** ~26 candidate month clusters against
  a floor of 10 is tight but plausible; the 0b drop rule already adjudicates it
  outcome-blind, which is the correct place; no edit beyond E14's texture guards.
- **A10 ledger text:** hypothesis count fixed at two, decrease-only; survivor-of-
  screen-#26 wording carried via v25 sections 9-10 (renumber "#25" to "#26" when
  transcribing).

## Answers to the specific stress points, compact

1. H-A bound rule: NOT leak-free as written (K1: 730d window reaches the 2023
   restatement; E5: tolerance/margin incoherence); tail loss real and unpriced (E6);
   15 percent / 730d are knobs needing provenance and outcome-blind sensitivity
   (E18); formula itself underdefined (K4).
2. H-B2 margin: coherent ONLY once integer-hundredths semantics are restored (E13);
   whole-inch strikes are safe under margin +0.02 against corrections <= 0.02.
3. Control replacement: justified; deciding publication now defined one way for both
   hypotheses including the non-monotone H-A bound (E7); print-precedes-publication
   check becomes a well-defined implementation invariant with a bug-repair rule.
4. Bands: pre-commit the symmetric quarantine (E8); without it one bad cheap print
   can fabricate a pass and one bad losing print can be silently eaten.
5. Cluster/power: floor reachable per 0b; add distinct-market floors and the
   CONCENTRATED-PASS label instead of a null-manufacturing two-city floor (E14).
6. Amendment fidelity: A1 (E17), A3 (E1, E17), A5 (clean), A6 (K3/E3), A7 (E2, E10,
   E11, E13), A8 (clean, add histograms to 0b per E18's grid), A9 (E12), A10 (clean).
7. Carried machinery: E8-analog tunables handled by E18; shock-window replacement
   needs teeth (E15); E12a firewall restated (E16); v25 E15b refire interaction
   handled (E14).
8. Other fabricate/manufacture vectors: post-determination Monday leak-in (K2), the
   quarantine gap (E8), the eps wiggle (K3), the "unexplained mismatch" wiggle (E16).

*Em-dash audit: clean (verified after write).*
