# v27 METHODOLOGY CRITIC: stress test of the draft lock (02-methodology-lock.md)

**Date:** 2026-07-02. Role: break the lock before it commits. Inputs read:
v27/02-methodology-lock.md (draft), v27/01-plan-critic.md (A1-A12),
v27/00-proposal.md, v27/scout-flight-data.md, v25/02-methodology-lock.md
(carried machinery). Standard: the EIA release-calendar, interpolation-phantom,
and restatement-leak catches of prior rounds.

## VERDICT: LOCK-OK-WITH-EDITS

The core two-part construction (H1 reconstructible baseline, D1 registered
look-ahead bound with family-death gates) is sound and the pre-lock kill
switches were run outcome-blind. But the draft contains: one bucket design that
contradicts the publication mechanics it models (the n_unpub 0-1 state is
unreachable at any legal fire), one saturation mechanism that reproduces the
exact certainty-fire shape that killed v26, one silently-degraded model input
covering the majority of the sample's holiday weeks, a D1 multiplier whose
"upper bound" label is wrong in sign under rebooking, a shadow protocol that
deviates from A3 in four places and is arithmetically near-unpassable as
written, and a K2 pass measured under definitions that do not match either the
lock or the plan critic. All are fixable pre-commit. Fifteen binding edits
below; the lock is invalid until all are folded in.

## 1. The frozen daily model: holiday factor and median-of-6

**1a. The holiday factor is silently 1 for most of the sample (real defect).**
The factor for day d needs the SAME holiday one year earlier from VINTAGE
values, and the vintage window starts Nov 2024. Therefore every holiday from
the universe start (Dec 2024) through roughly Oct 2025 has no prior-year
vintage counterpart: Christmas/New Year 2024-25, MLK, Presidents Day, Memorial
Day, Juneteenth, July 4, Labor Day 2025 all get factor 1 by the lock's own
"if unavailable, factor 1" clause. That is roughly 11 of 19 months, and
holiday weeks are exactly where fires are expected to concentrate (proposal
kill risk 3).

Direction: three channels, none benign.
- Fires inside those weeks price off a pred that misses the holiday deviation
  entirely: spurious fires in both directions, mostly a false-null noise
  injection for H1.
- Those weeks' large signed errors enter the shared walk-forward weekly error
  distribution and are then applied to NORMAL weeks: if holiday misses are
  systematically signed (they are: holiday-window volumes deviate in a
  consistent direction per holiday), the empirical quantiles shift and the
  model manufactures divergence everywhere else. That is a mechanical
  false-positive vector.
- D1 runs the identical pipeline, and D1 failure = FAMILY DEATH. Wasting D1's
  20-fire/8-cluster power budget on a preventable model defect in precisely
  D1's target weeks biases the family toward false death.

EDIT E1. Also underspecified: "the ratio observed at the SAME holiday one year
earlier" never defines ratio of WHAT to WHAT (actual over the same model's
baseline pred? actual over trailing same-weekday median?). That is post-hoc
wiggle; freeze the exact formula (EDIT E2).

**1b. Median-of-6 disruption contamination (minor, own it).** Median of 6 =
mean of the 3rd and 4th order statistics; a single abnormal same-weekday value
barely moves it. The real exposure is the December cluster: three consecutive
abnormal Sundays (Dec 21, Dec 28, Jan 4 pattern) put 2-3 outliers in one
6-value window and bias January baselines in the holidays' direction, with
those errors then entering the buckets. Direction: sign of the disruption,
decaying over 6 weeks; predominantly false-null noise. No structural fix
needed beyond E1's exclusion of factor-1 holiday weeks from the error build;
state the December-cluster caveat in the lock's honesty note (EDIT E3).

## 2. The weekly error distribution: bucket design vs publication mechanics

**2a. The n_unpub 0-1 bucket is unreachable; 2-3 is really {3} (design
defect).** Publication is Mon-Fri, one-business-day lag: Thursday's value
posts Friday ~9am, Friday's value posts MONDAY. Markets close Sun 23:59 ET
(or 22:59 EST; see section 9). So at any legal fire time the minimum
unpublished count is 3 (Fri, Sat, Sun), reached from Friday's publication
until close. Reachable states are n_unpub in {3, 4, 5, 6, 7} only. The
{0-1} bucket can never contain an observation or a fire, and {2-3} collapses
to n_unpub=3. The frozen partition {0-1, 2-3, 4-7} was written without
checking the mechanics it models. This also answers the Monday-morning-pocket
question: no fire can ever use a Monday publication, no pocket exists,
CONFIRMED; but the bucket set must be re-partitioned to the reachable states
BEFORE lock, e.g. {3}, {4-5}, {6-7} (EDIT E4). Holiday-slip weeks
automatically land in higher buckets because bucket assignment at fire time
must use PROVEN publications (A7), which is consistent; state it.

**2b. Warmup interacts with the power floor and is currently uncounted.**
One error per (week, bucket-state) is the only coherent reading (within a
state no inputs change), but the lock does not say it, and it does not say
whether TRAINING error observations require snapshot-proven availability like
fires do. The two readings differ enormously: without proof-for-training,
all reachable buckets hit 15 errors around week 16-20 of the 82-event binding
set (5 of 87 events are excluded by K1); with proof-for-training at the 41.3
percent evaluability rate, warmup stretches to roughly week 35+. Eligible fire
clusters are therefore somewhere between ~47 and ~65, not 82/87, and the
40-fire/30-cluster floor needs a 46-64 percent fire rate among eligible weeks
(v25 fired 57 percent). This is decidable pre-data and 0b must decide it:
report the eligible-cluster count after warmup under the chosen convention,
and run the A10 floor projection against THAT count (EDIT E5). Recommended
convention: training errors use first_value with schedule-implied state
assignment (the value is identical whenever seen; only fires need proof);
own the one caveat that publication-slip weeks may be bucket-misassigned in
training.

**2c. Saturation and out-of-support extrapolation: v26's death shape returns
(false-positive vector, the sharpest in the draft).** With minimum 15
empirical errors and P_model read off the empirical distribution, any
avg_hat - K beyond the observed error support yields P_model exactly 0 or 1.
A 15-observation distribution has no tails, so outer-strike markets will
routinely see P_model = 1 vs market 0.88-0.92: divergence 0.08-0.12, inside
the [0.05, 0.95] band, fires BUY YES at up to 0.95 exec. These are
certainty-by-extrapolation fires: the model collects premium on tail risk it
cannot see (weather meltdown, security incident), and 60-80 backtest weeks may
simply not contain the tail. That is a peso-problem false positive and it is
the same band-edge certainty regime v26 was killed for. EDIT E6: NO FIRE
whenever |avg_hat - K| exceeds the largest |error| in the trade's bucket
(P_model must be an interpolation, never an extrapolation), and specify the
interpolation rule (linear between order statistics, as v25 section 3 does;
the draft never says).

## 3. K2's 41.3 percent vs the 40 line: the pass does not yet count

Three definition mismatches, each independently able to flip a 1.3-point
margin:

- **Unit mismatch vs the pre-set line.** The plan critic's kill trigger
  (section 7 item ii) was "under ~40 percent of CLUSTERS"; A7's restriction
  rule is "fewer than 60 percent of lifetime clusters have at least one fully
  evaluable fire-day". K2 reports 41.3 percent of in-band PRINTS. Print-level
  and cluster-level evaluability are different quantities (a few dense proven
  weeks can carry the print rate while many clusters have zero evaluable
  states). The lock never runs the A7 60-percent cluster rule at all. That is
  a watering-down of A7, not an implementation detail.
- **Band mismatch.** The kill script's in-band definition (0.15-0.85) is not
  the lock's fire band (0.05-0.95). Evaluability is a time property, but band
  membership correlates with time-of-week (edge prints cluster late-week where
  the anchor set is larger and snapshot density differs), so the ratio need
  not survive the band change.
- **"Noon-ET visibility" smells like schedule inference.** A7: "a value is
  available only when a snapshot proves it", "NO posting-schedule inference".
  If the K2 script credited a day's value from noon ET when the proving
  snapshot's first_seen is later that day, the 41.3 is inflated by exactly the
  inference A7 bans. If noon-ET is merely a conservative extra condition ON
  TOP of first_seen <= print time, it is fine; the lock does not say which.

Which governs: the lock's band and A7's cluster rule govern; the kill script
must be reconciled to them, not vice versa. EDIT E7: recompute K2 under
(i) strict first_seen <= print time with no noon crediting, (ii) the lock's
0.05-0.95 band, and (iii) BOTH units: percent of in-band prints AND percent of
clusters with >= 1 fully evaluable fire-day; apply the pre-set lines (40
percent kill line on the critic's cluster quantity, A7's 60 percent
restriction rule); record all numbers in 0c. A pass by 1.3 points under
mismatched definitions is not a pass.

## 4. The sched_ratio clamp and A8: the premise is likely wrong in sign

The scout's file (section 3) is the BTS on-time performance record: rows are
carrier-reported SCHEDULED flights with a Cancelled flag. Flights cancelled
1-3 days ahead in a meltdown are overwhelmingly reported as rows with
Cancelled=1, not removed from the file; removal happens for long-horizon
schedule changes (month+ out), which a Wednesday observer knows anyway. So
sched(d) very likely INCLUDES pre-cancelled flights and the contamination A8
feared (the disruption leaking into the scheduled count) is approximately
zero. The clamp is then not bounding what the lock says it bounds.

What the clamp IS legitimately bounding: the monthly file is compiled 4-5
weeks after the fact, so sched(d) is a PROXY for the ex-ante CRS schedule (the
lock treats it as knowable in advance; the specific file is not). Keep the
clamp under that justification. Second real cost: [0.9, 1.1] truncates
genuine holiday schedule swings, exactly where the schedule term was supposed
to carry information, pushing H1 toward its own control (gate 3 then nulls
H1). That is a false-null direction and acceptable under A5's expectations,
but it must be owned, not hidden inside a wrong contamination story.

Also a process point: A8 offered exactly two options, (i) monthly-profile
feature in flagged weeks or (ii) per-day count + owned contamination + a
NAMED removal sensitivity. The draft invented a third treatment (the clamp)
and adopted only half of (ii) (the unbankable label, without the removal
sensitivity). Either is arguably honest, but the amendment said pick (i) or
(ii); silence on the delta is not compliance.

EDIT E8: (a) 0b verifies empirically, outcome-blind, whether pre-cancelled
flights appear as rows: in the max-cancellation weeks, compare day-over-day
sched(d) row counts vs Cancelled=1 counts (a meltdown showing stable rows +
spiking Cancelled=1 confirms inclusion). (b) Rewrite the A8 paragraph: the
clamp bounds the monthly-file-as-ex-ante-schedule proxy error, not
pre-cancellation leakage; report the raw (pre-clamp) sched_ratio distribution
in flagged vs normal weeks. (c) Add A8(ii)'s named non-binding sensitivity:
H1 rerun with the schedule term removed in flagged weeks, delta reported.
(d) Keep the unbankable-without-live-read label (already present).

## 5. D1 beta=1 is not an upper bound (direction error in the headline claim)

TSA screenings do not fall 1:1 with cancellations: cancelled passengers
rebook same-day or next-day onto higher-load flights, and cancelled CONNECTING
legs reduce screenings by zero (connections do not re-screen). A weekend with
15 percent cancellations plausibly loses ~5 percent of screenings; beta=1
overstates the drop by 2-3x. pred_D1 then undershoots in meltdown weeks, D1
buys NO on strikes the true average clears, and PERFECT information is
converted into losses by a miscalibrated transfer coefficient. Since any D1
gate failure = FAMILY DEATH, beta=1 as the sole registered coefficient is a
false-family-death machine: the channel could be alive and D1 still dies on
the overshoot.

"Upper bound" is only true in the information sense, not the P&L sense; the
lock's claim is the P&L sense. Two compliant fixes exist; pick one now:

EDIT E9 (preferred): pre-register a FROZEN beta grid {0.3, 0.5, 1.0}, no
other values ever; D1 PASSES if any registered beta clears all five A2 gates;
family death requires all three to fail. This is a 3-way multiple comparison
on a diagnostic whose pass opens only a $0 shadow with its own binding gates,
and it is asymmetric in the right direction (protects against false death,
cannot route to capital). Alternative (weaker): keep beta=1 and reword the
registered claim to "the beta=1 proportional-passthrough channel", accepting
that a D1 death does not kill the rebooking-aware channel; this reopens the
family-death semantics and is worse. Either way, record the choice pre-data.

Related, must be stated: A1 bans estimating any error distribution on the
substituted actuals, so D1 necessarily reuses H1's weekly error distribution,
which is too wide for a perfect-info pred. D1's P_model is therefore
underconfident by construction: fewer D1 fires, floor risk on the 20/8 gate,
again in the false-death direction. Own this in the lock text (EDIT E10);
it is a conservatism, but an uncounted one sitting on a family-death gate.

## 6. D1 gate arithmetic: coherent but the lock must say what it implies

At the floor n_c = 8 with the v25 sigma_c ~ 0.40: CI half-width ~27.7pp, so
"CI lower > 0" binds at mean ~28pp, and the nominal 8pp mean gate is inert at
the floor. At the realistic disruption-cluster counts (10-18 per the plan
critic), the binding requirement is mean net ~18-25pp. So D1 passes only on a
monster perfect-info signal. Reading A2's intent ("if the deliberately
generous test cannot reach even this floor, the channel has no testable
surface"), this is INTENDED, not accidental: a deliberately generous test
should have to shine. Not a redesign item. But two consequences must be
stated in the lock (EDIT E11): (a) the effective D1 bar is ~2-3.5x the
nominal 8pp at plausible cluster counts (reproduce the half-width arithmetic
in the D1 gate section); (b) the header's "P(D1 justifies shadow) ~25-30
percent" was set before this arithmetic was explicit and should be re-marked
(honest re-mark: ~10-15 percent). A prior that ignores its own gate
arithmetic is the quiet kind of wiggle.

## 7. Shadow protocol: four deviations from A3, and the week-26 numbers are
near-unpassable as drafted

- **Week-26 floor: 20 fired clusters vs A3's 12.** Fired clusters accrue at
  most 1 per week; 20 of 26 weeks = 77 percent weekly fire rate. v25's broad
  pattern was 57 percent (52 of 91), giving ~15 clusters at week 26; the
  disruption-concentrated scenario gives ~6. Under BOTH scenarios the drafted
  gate fails mechanically regardless of edge. And at n_c = 20 the CI
  requirement binds at mean ~17.5pp net at real asks. As drafted the shadow
  is a machine that kills the family at week 26 with near-certainty; that is
  not a gate, it is a delayed kill dressed as one.
- **The A3 extension was dropped.** A3(ii) pre-committed: binding eval at 26;
  if the CLUSTER FLOOR is unmet at 26, a single extension to a week-39 hard
  stop. The draft made 26 binding unconditionally and repurposed 39 as dead
  text (if 26 always adjudicates, 39 can never bind). This deviation is in
  the false-death direction and was not argued for anywhere.
- **Week-13 early-kill weakened.** A3(ii): early kill if CI UPPER bound <
  the net hurdle (cannot possibly be good). Draft: kill only if clustered
  mean < -5pp with >= 8 fired clusters, a much harder trigger. This wastes up
  to 13 more weeks on doomed families, against the kill-early rule, and it is
  a silent renumbering of a pre-committed criterion.
- **Week-26 LOCO missing.** A3(iii) required the shadow pass to be
  LOCO-robust. The draft's week-26 sentence has no LOCO. That is the single
  loosening in the pro-pass direction, and it matters most exactly here
  (shadow clusters will concentrate in disruptions).

Plus three wiggle points the draft leaves open: what counts as a fired
cluster in shadow (define: an ISO week containing >= 1 logged hypothetical
fill); the ask convention (the draft logs fills at live ask PLUS the binding
haircut, but evaluates week 26 "at REAL logged asks": with a real ask there
is nothing for the +3c to proxy, so log BOTH conventions and pre-commit that
the week-26 binding number uses real ask + worst-case fee, no synthetic
haircut); and the live threshold (nothing pins the shadow's divergence
threshold to 0b's recorded choice; A3(v) requires the frozen-spec doc at
shadow start, name the freeze artifact and that it commits before the first
logged fill).

EDIT E12: restore A3's numbers and structure verbatim (12-cluster floor at
week 26; single pre-committed extension to 39 iff the floor is unmet at 26;
week-13 early-kill on CI-upper < hurdle; LOCO at the binding eval), and add
the three definitions above. If the operator prefers 20 clusters over 12, that
is a choice to make EXPLICITLY with the 77-percent-fire-rate arithmetic in
front of them, not a drafting default.

## 8. Execution and band-edge closure: PASS (verify and state)

The threshold closes the band the same way v25 E15c did: BUY YES needs
P_model >= p_print + 0.08 with P_model <= 1, so p_print <= 0.92 and p_exec <=
0.95; all-in worst case 0.95 + 1c fee = 0.96 < 1.00. NO side mirrors. Fee at
ATM is 2c (ceil(7*0.25) = 2), so the minimum model-conditional net edge at
threshold 0.08 is 8 - 3 - 2 = +3pp ATM and 8 - 3 - 1 = +4pp at the edges:
thin but positive; no impossible-trade or negative-EV-by-construction pocket
exists in the binding run (v26's H2 defect is absent). The 5c disrupted
sensitivity bottoms out at 8 - 5 - 2 = +1pp, still positive, and is
non-binding anyway. EDIT E13: add this closure paragraph to section 4 of the
lock (the draft asserts the band but never demonstrates closure; v25 made it
explicit and it caught v26's pocket). Note the residual honest caveat: the
+3pp ATM minimum is thinner than v25's, so A11's projected-mean >= 8pp rule
is doing real work; 0b must also report the FRACTION of projected fires with
conditional edge below 5pp, not just the mean (a mean carried by a few fat
fires over a mass of +3pp fires is the shape that dies to spread widening).

## 9. Remaining traps (calendar, clustering, exclusions, fidelity)

- **Cluster key must be the EVENT's week, not the print's ISO-UTC week.**
  Sun 20:00-23:59 ET prints sit in the NEXT ISO week in UTC. If the cluster
  key is the fire timestamp's ISO week, fires settled by event week N land in
  clusters N and N+1: two "independent" clusters sharing one settlement
  outcome, which breaks the cluster bootstrap's independence assumption
  outright. EDIT E14: cluster = the settlement event (equivalently the
  event's Mon-Sun ET week); one cluster per event, all its fires inside it.
  v25's print-week key was safe there (daily AAA settlements); it is not safe
  here.
- **Per-market close_time audit (plan-critic section 6) is missing from the
  draft.** Mon 03:59Z = Sun 23:59 EDT but Sun 22:59 EST; and the no-fire-
  after-close premise underlying section 2a needs the verified per-market
  close, not an assumed one. Add to 0c: max close_time vs Monday publication
  window per market; any market closing after Monday ~9am ET publication
  excludes those hours from its fire window by rule (also required for the
  section 2 bucket claim).
- **The 5 no-vintage excluded events are a selection risk.** If vintages are
  missing BECAUSE the page or archive behaved badly in chaotic weeks, the
  exclusion removes disruption clusters, which flatters H1 (drops hard weeks)
  and starves D1 (drops its target clusters, false-death direction again).
  0c must list the 5 events' dates with holiday/disruption flags; if 2+ are
  disruption weeks, the verdict must own the selection explicitly.
- **Units heuristic vs plan critic.** Section 6 of the critic banned
  normalizing units "by heuristic, never from metadata"; the draft's
  floor_strike > 1000 rule is a heuristic. It happens to be VALIDATED by K1's
  82/82 settlement reproduction (wrong units cannot reproduce 82 of 82), which
  is honestly better than metadata. State that linkage in section 1, and add:
  any future market violating the heuristic = NO FIRE, never a guess.
- **A6 artifact.** K1's 82/82 first-published reproduction subsumes A6's kill
  rule (settlement = first-published means anchor revisions cannot touch
  P&L), a genuinely clean close. But A6 also demanded the written per-revision
  audit artifact (first-published / at-settlement / today); produce it in 0c
  even if it is three lines of zeros; the amendment said artifact, not
  argument.
- **A12 is watered down.** A12: reproduce the power table and the 7-to-30-
  month arithmetic VERBATIM in the lock, plus an explicit operator
  acknowledgment line (or linked decision doc) before any shadow starts. The
  draft has one summary sentence and "the operator is being told this in the
  session report". Fold the table into section 6 and add the acknowledgment
  mechanism as a named precondition of shadow start.
- **DST/timezone pins.** Noon-ET and 9am-ET rules must be computed
  ET-timezone-aware, not as fixed UTC offsets (13:00Z vs 14:00Z flips twice a
  year, and two clusters per year contain the transition); day-of-week keying
  on ET calendar days; cluster key per E14. One sentence in the lock.

All of the above is EDIT E15 (a-g as listed).

## Amendment fidelity summary

- A1 D1 estimator: MET (inference-input substitution only, no re-estimation).
- A2 D1 gates: MET textually; implied arithmetic must be stated (E11); beta
  registration defect sits underneath it (E9).
- A3 shadow: FOUR DEVIATIONS (week-26 floor 20 vs 12; extension dropped;
  week-13 criterion weakened; LOCO missing) + three open wiggle points (E12).
- A4 firewall: MET (ordering stated); write "verdict doc", not just disk.
- A5 H1 routing/expectation: substantively MET; add the explicit sentence
  that H1 UNDERPOWERED-NULL does not kill the family (D1 adjudicates).
- A6 revisions: substantively CLOSED by K1 (stronger result); artifact
  missing (E15e).
- A7 evaluability: PARTIAL; unit and band mismatches plus the noon rule
  ambiguity; the 60-percent cluster restriction rule was never run (E7).
- A8 schedule treatment: DEVIATION (unauthorized third option, half of (ii));
  premise likely wrong in sign (E8).
- A9 haircuts/print counts: PARTIAL; K3 covers liveness; the disrupted-vs-
  normal spread proxy split is not yet in 0b's required outputs; the 1,000-
  cancellation flag is an acceptable frozen criterion.
- A10 power floors: carried; 0b must project against the WARMUP-REDUCED
  eligible cluster count, not 87 (E5).
- A11 threshold: carried; closure now demonstrated (E13); add the sub-5pp
  fire-fraction report.
- A12 timeline: WATERED DOWN (E15f).

## Binding edit list

- E1: holiday windows lacking a prior-year vintage factor = NO FIRE in that
  window, and those weeks' errors are EXCLUDED from the weekly error buckets.
  No silent factor 1.
- E2: freeze the exact holiday-factor formula (numerator, denominator, which
  vintage values, same-weekday convention).
- E3: honesty note: December-cluster contamination of the median-of-6
  baseline (2-3 abnormal same-weekday values in one window), direction and
  6-week decay.
- E4: re-partition the n_unpub buckets to the reachable states {3}, {4-5},
  {6-7}; delete {0-1}; state that bucket assignment at fire time uses proven
  publications only.
- E5: define one error observation per (week, bucket-state); pick and state
  the training-availability convention; 0b reports the eligible-cluster count
  after warmup and runs the A10 projection against it.
- E6: NO FIRE when |avg_hat - K| exceeds the bucket's observed error support
  (interpolation only, never extrapolation); specify linear interpolation
  between order statistics.
- E7: recompute K2 under strict first_seen, the lock's 0.05-0.95 band, and
  both units (prints AND clusters); run A7's 60-percent cluster restriction
  rule; all in 0c. The kill lines govern the recomputed numbers.
- E8: sched(d) pre-cancellation inclusion check in 0b; re-justify the clamp
  as bounding the monthly-file proxy error; report raw sched_ratio
  distributions; add the A8(ii) schedule-term-removal sensitivity in flagged
  weeks.
- E9: register the frozen D1 beta grid {0.3, 0.5, 1.0}; D1 passes if any
  registered beta clears all A2 gates; family death requires all three to
  fail.
- E10: state that D1 reuses H1's error distribution by A1's own ban and is
  therefore underconfident by construction (uncounted conservatism on a
  family-death gate).
- E11: reproduce the CI half-width arithmetic inside the D1 gate section
  (effective bar ~18-28pp at plausible cluster counts) and re-mark the
  D1-justifies-shadow prior accordingly.
- E12: restore A3's shadow structure verbatim (12-cluster floor at 26,
  single extension to 39 iff floor unmet, week-13 CI-upper early-kill, LOCO
  at the binding eval); define fired-cluster-in-shadow; log both ask
  conventions and pre-commit the week-26 number to real ask + fee with no
  synthetic haircut; pin the live threshold to 0b's choice and name the
  shadow-start freeze artifact.
- E13: add the band-edge closure paragraph (p_exec <= 0.95, all-in <= 0.96,
  minimum conditional edge +3pp ATM); 0b additionally reports the fraction of
  projected fires with conditional edge under 5pp.
- E14: cluster key = settlement event (Mon-Sun ET week of the event), not
  the print's ISO-UTC week.
- E15: (a) per-market close_time audit in 0c; (b) list the 5 excluded events
  with disruption flags and own any selection; (c) units heuristic tied to
  K1's validation, unmatched market = NO FIRE; (d) A5 explicit sentence;
  (e) A6 artifact in 0c; (f) A12 table + operator acknowledgment line as a
  shadow precondition; (g) ET-timezone-aware publication/visibility rules and
  DST note.

## What survives untouched

K1's design and result (settlement = first-published, decisively shown), the
H1/control/LOCO/month-block gate stack, the A4 ordering firewall, the two-
candidate threshold rule, the zero-staleness no-fill discipline, and the
one-shadow-ever principle. The family remains worth running for the same
reason the plan critic said: the backtest is cheap and D1 can kill it this
month. The edits exist so that when it dies, it dies of a real null and not
of a bucket that could never fill, a beta that overshot, or a shadow gate no
true edge could pass.

*Em-dash audit: clean (verified after write).*
