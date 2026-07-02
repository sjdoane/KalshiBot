# v26 PLAN CRITIC: adversarial review of the window-aggregate proposal

**Date:** 2026-07-02. Role: kill the idea before data if it deserves killing.
Inputs: 00-proposal.md, scout-data-sources.md, v25 06-FINAL-VERDICT.md and
02-methodology-lock.md, v24 00-HANDOFF-PROMPT.md. Family #26.

## VERDICT: PROCEED-WITH-AMENDMENTS

Not a clean proceed. The proposal as written registers two hypotheses of very
unequal quality and hides its best claim inside its weakest one. H-A (TSA) as
drafted is mostly a weekend-traffic forecast wearing an arithmetic costume, and
its universe count is contradicted by the scout. H-B (rain) as drafted mixes a
capture-phantom-shaped mid-window climatology claim with a genuinely novel
post-crossing determination claim that deserves its own registration and its
own gates. The amendments below restructure the hypothesis set before lock.
If amendment A1 resolves against the proposal (KXTSAW really has only ~10-19
settled weeks), H-A dies at the 0b feasibility rule and this becomes a
one-underlying family, which is still worth running for H-B2.

## 1. The market-matches-arithmetic prior (attack surface 1)

The honest structural question: why would ANY participant, however thin the
book, fail to price a number that is literally on a public webpage? The
project has confirmed the capture phantom seven-plus ways on exactly this
shape. Points against the proposal:

- The signal inputs (TSA page, CLI month-to-date) are the single easiest
  public data in the entire project history. No GRIB decoding, no Wayback
  reconstruction needed to trade it live. The marginal bettor CAN do this
  arithmetic in their head.
- 1.35M contracts on KXTSAW and 2M+ on KXRAINNYCM are not dead markets. Real
  volume attracts at least one participant who reads the settlement source.

Points for a nonzero prior, honestly weighed:

- The MLB post-determination null was measured on Kalshi's MOST liquid series
  at an INSTANT determination (a game ends, everyone knows within seconds).
  Here determination is gradual and undramatic: nobody gets a push alert when
  the July 14 CLI puts the month-to-date over 5.00 inches. The mechanism that
  killed MLB (MMs racing an unambiguous public event) is weaker where the
  event is a line item in a text product read by almost nobody.
- The thin-ladder microstructure is genuinely different: monthly rain ladders
  in 9 of 10 cities have existed for ~7 months with 0.3-1.4M contracts spread
  over an entire ladder and month; resting quotes can be hours-to-days stale.

Ruling: a 10-12 percent prior for the FAMILY is too high as drafted because
most of the drafted fire surface (unrestricted H-A, mid-window H-B) is
forecast-vs-market territory where the prior should be 3-5 percent. Re-mark:
family prior ~8-10 percent with the probability mass concentrated on the
post-crossing sub-claim (A4), which is the only component whose escape story
survives contact with the capture-phantom record.

Pre-data distinguisher (must go in the lock as an outcome-blind 0b input):
the difference between "MLB null transfers" and "thin ladders lag" is
MEASURABLE without touching outcomes. For each underlying, compute from
trades/quotes data only: (a) time from the publication event (TSA ~9am ET
post-day, CLI issuance timestamp) to the first subsequent print in each
near-money market; (b) fraction of weekly/monthly volume printed within 1
hour of publication vs spread across the day; (c) count of distinct price
levels per market-day. If near-money markets systematically reprice within
minutes of publication, expect the market-matches-arithmetic NULL and say so
in the lock before data. These are prices and timestamps, never settlement.

## 2. H-A and the TSA weekend gap (attack surface 2)

The scout's verified publication schedule breaks the proposal's own framing.
"By late week, 4-6 of 7 days are published facts" is FALSE during trading:
Fri, Sat, Sun all land Monday ~9am ET. The maximum observable pinned
component while the market trades is 4/7 (Mon-Thu, visible from Friday 9am),
and the unobserved remainder is exactly the high-traffic, high-variance,
holiday-sensitive weekend. Before Friday 9am it is 3/7 or less.

Consequence: unrestricted H-A is not arithmetic. It is a day-of-week plus
trend plus holiday forecast of weekend TSA traffic, compared against a market
that can build the identical forecast from the identical public history. That
is the capture-phantom shape with a thinner costume than v25 wore (v25 at
least had a pass-through regression frontier story). The "nothing to go
degenerate" defense is true but irrelevant: v9/v25 died from the market
already having the same information, not only from model degeneracy.

Required restriction (A2): H-A fires ONLY where the pinned component nearly
decides the bracket. Concretely: fire only if partial_sum plus a frozen
walk-forward worst-case remainder envelope (empirical min/max or 1st/99th
percentile of same-day-of-week remainder sums, level-scaled, no holiday weeks
in the envelope's support without a holiday flag) puts the weekly average on
ONE side of the strike. That converts H-A into a certainty-zone claim, which
is honest, and which lands it in the same fee arithmetic as section 6 (the
fires will print at 0.85-0.97, not at 0.50). The unrestricted distributional
version may run as a REPORTED, NON-BINDING stratum only.

Bracket-scale sanity check the lock must include: weekly-average strikes sit
~50k apart; a 3-day unobserved remainder has an empirical spread of roughly
plus-minus 20-40k on the weekly average. So the deterministic zone exists
(strikes 2+ brackets from the money) but the near-money strike is genuinely
open until Monday. Fires will therefore be extreme-price fires. If the
outcome-blind print histogram shows no prints below the 0.95 breakeven in
that zone, H-A is infeasible and the 0b rule must drop it.

## 3. The KXTSAW universe contradiction (blocking, must resolve pre-lock)

The proposal claims 48 settled weekly events May 2025 - Apr 2026 via the
historical endpoint plus ~9 live. The scout states the 10 settled weeks
26APR26 through 26JUN28 are "the full series history" and reproduced all 10.
Both cannot be right. Possibilities: the 48 are an older ticker family the
scout did not check; the scout's "full history" refers only to the live
settled endpoint; or the proposal's count is wrong. This is load-bearing:
~57 clusters vs ~10-19 clusters is the difference between a runnable H-A and
a structurally underpowered one (10 clusters gives a ~25pp CI half-width at
generic sigma; even certainty-zone sigma ~0.10 gives ~6pp).

Rules for the lock (A1): enumerate the exact settled event list pre-lock;
extend the settlement-reproduction audit from 10/10 to EVERY settled event
in the binding set (booleans and rates only, E12a firewall); any unexplained
reproduction failure = kill H-A. If the reconciled cluster ceiling is below
the power floor, H-A is dropped at the locking commit per the 0b feasibility
rule and the ledger records it.

## 4. TSA revisions (attack surface 3)

The scout's 2023 finding (183/194 dates restated, up to +6.1 percent) proves
the live page is not an as-of series. Two separate exposures:

- Settlement labels: NOT exposed. Settlement truth is the Kalshi result
  field; Kalshi settled with then-current numbers. No audit needed there
  beyond reproduction.
- Signal inputs: FULLY exposed. A backtest that reads today's page as the
  partial sum visible in week W of 2025 may be trading on restated numbers
  nobody could see. Revisions were predominantly UPWARD; an upward-restated
  partial sum biases the signal toward YES on above-K strikes, and the bias
  correlates with the outcome (higher true traffic). This is a classic
  leak-shaped contamination, not noise.

And the reproduction audit does NOT clear it: 10/10 settled-bracket
reproduction only proves no revision CROSSED a bracket boundary after
settlement. Sub-bracket revisions (the typical +0.1 to +0.5 percent) are
invisible to that test while still poisoning the as-of signal. The lock must
say this explicitly.

Required audit (A3): Wayback as-of verification across the FULL binding
window, minimum one snapshot per calendar month May 2025 - Jun 2026, diffing
every daily value that any fire's partial sum would consume. Any day whose
value differs between the within-window snapshot and the series used by the
signal = zero-staleness NO-FIRE for every fire consuming it. If more than a
pre-set fraction of weeks (suggest 10 percent) are contaminated or
un-auditable (no snapshot), H-A restricts to the auditable subset or dies.
Preferred stronger form: build the TSA as-of series FROM snapshots where
coverage allows, with the live page only for the verified-stable 2026 tail.

## 5. Rain: fat tails, zero bound, and the post-crossing split (attack 4)

Mid-window pinning is weak and the proposal half-admits it. Monthly precip
is zero-bounded and storm-driven; in convective cities (HOU, MIA, AUS, DAL)
a single event can add 3-5 inches, so a dry first half excludes almost
nothing on the YES side of low strikes. The honest mid-window content of H-B
is "market climatology vs my climatology," which is precisely the
general-miscalibration claim that gate 3's control exists to catch, and
precisely where the capture phantom lives. Meanwhile the West Coast dry
season is degenerate in the opposite direction: KXRAINLAX in July is decided
on day 1 by climatology everyone shares; there is nothing to trade net of
fees.

The genuinely novel component is the crossing: strikes are "strictly greater
than X inches," precipitation is physically non-decreasing, so the moment the
published month-to-date exceeds K, YES is settled fact with weeks of trading
possibly remaining. This is a GRADUAL, UNDRAMATIC determination on a THIN
ladder: the exact configuration the MLB null did NOT test (instant, liquid,
salient). What MLB DOES transfer: (a) determination itself confers no edge
if anyone is watching, so the entire question is empirical staleness of thin
books; (b) the edge, if any, lives in the ask AFTER the fact, so the taker
print + haircut mechanism is the right F11-aware instrument.

Two caveats the lock must own:

- "Irreversible" is a claim about the atmosphere, not the record. NWS issues
  corrected CLIs; a corrected daily value could un-cross a strike. The scout
  has NOT verified whether ACIS ingests late corrections (open item 5). The
  crossing must be defined on archived as-issued CLI products, and the audit
  must measure, across all 10 stations and all universe months, how often a
  correction ever moved a month-to-date backward across any traded strike.
  With win sizes of +1 to +6c and a loss size of ~-97c, a correction
  probability of even 1-2 percent destroys the trade; see section 6.
- The mirror side has no symmetric fact: NO is never determined early (a dry
  month stays undetermined until the final CLI). Post-crossing is a YES-only,
  buy-only stratum and must be registered as such, not discovered as such.

Amendment A4: split H-B. H-B1 = the distributional claim (partial + remainder
climatology vs market), restricted to the final N days of the month where the
frozen climatological remainder envelope actually pins (N fixed pre-lock from
climatology alone, per station-month, outcome-blind). H-B2 = post-crossing:
buy YES when the as-of published month-to-date strictly exceeds K, price
below the breakeven band of section 6. H-B2 is the strongest claim in the
family and must not share a verdict cell with H-B1.

## 6. Fee and spread arithmetic at the extremes (attack 6)

Worst-case taker fee ceil(7 P (1-P)) cents; binding run adds a 3c haircut.
For a post-crossing (or H-A certainty-zone) YES buy at print p:

| print p | exec p+3c | fee | net if YES |
|---|---|---|---|
| 0.85 | 0.88 | 1c | +11c |
| 0.90 | 0.93 | 1c | +6c |
| 0.93 | 0.96 | 1c | +3c |
| 0.95 | 0.98 | 1c | +1c |
| 0.96 | 0.99 | 1c | 0c |

Binding-run breakeven: print <= 0.95, strictly profitable only at <= 0.95.
Reported +1c run breakeven: print <= 0.97. The v25 H2 lesson transfers
exactly: the certainty zone is nearly infeasible unless the book is leaving
asks at 0.95 or lower AFTER a public determination. That is a 5c+ posted
free lunch; the claim is not absurd on books this thin, but it is exactly
what the outcome-blind 0b projection must count before lock: number of
prints at p <= 0.95 in post-crossing windows (crossing computed from weather
data only, no Kalshi result field touched), per month-cluster.

Loss asymmetry, pre-committed: a fire at exec 0.96 that loses (correction,
settlement mismatch, mapping error) costs -97c and erases ~32 wins at +3c.
Therefore H-B2's viability is dominated by the correction/mismatch rate, not
by the mean stale-ask depth. The lock must state: if the section 5 correction
audit finds ANY un-crossing event in the universe, the P=1 assumption is
replaced by P=1-eps with eps from the audit, and the breakeven band tightens
accordingly; if eps cannot be bounded below 0.5 percent, H-B2 dies pre-data.

## 7. Power arithmetic (attack 5)

Using the v25 half-width formula 1.96 sigma_c / sqrt(n_c):

- H-A: ceiling 57 ISO-week clusters IF the proposal's count survives A1,
  plausibly ~10-19 if the scout is right. Fired clusters will be fewer (only
  near-boundary weeks fire). At generic sigma_c 0.40: n_c=30 gives ~14pp,
  hopeless for a certainty-zone edge of 1-6c. At certainty-zone sigma_c
  ~0.10-0.15 (near-uniform small wins, rare large loss): n_c=25 gives
  ~4-6pp. Still cannot validate a true +3c mean. Honest ceiling statement
  required in the lock: H-A can only pass if fires are numerous, cheap
  (prints 0.85-0.93), and near-uniformly winning; the lock must pre-commit
  UNDERPOWERED-NULL wording otherwise.
- H-B: the proposal's own conservative clustering (calendar month across ALL
  cities) is correct and must be binding; 10 cities in one month share
  synoptic weather and, worse, share the same climatology-vs-market
  mechanism, which is the actual correlated exposure. That yields ~26 NYC-era
  months + ~7 multi-city months = ~30-33 month clusters ceiling, NOT 85.
  At sigma_c 0.05 (plausible for H-B2 if corrections are ~0): n_c=20 gives
  ~2.2pp half-width: a true +3-6c mean edge IS detectable. This is the only
  cell in the family where the power arithmetic honestly closes. H-B1 at
  generic sigma has the same hopeless arithmetic as H-A.
- Floors: keep the v25 pattern. H-A and H-B1: 40 fires / 30 clusters or
  UNDERPOWERED-NULL. H-B2: the H2-style floor 30 fires / 8 month-clusters,
  with the explicit note that 8 clusters gives ~3.5pp half-width at sigma
  0.05 and a pass therefore requires a mean of ~4c+, i.e. persistent prints
  at <= 0.92 post-crossing.
- 0b outcome-blind fire projection is MANDATORY per hypothesis before the
  locking commit; any hypothesis whose projection cannot reach its floor is
  dropped at lock, recorded in the ledger.

## 8. Multiple testing and the ledger (attack 7)

Family #26 after ~25 dead families. The restructure creates up to three
binding hypotheses (H-A1 restricted, H-B1 restricted, H-B2). The ledger must
state, pre-lock: the exact registered count after the 0b feasibility drops;
that the v25 NO-side seed is NOT tested in v26 and remains a seed (it must
not silently become a v26 stratum via the rain NO side or any other door);
that any pass is labeled "survivor of screen #26" and routes through the
staged $0 path; zero post-data strata; no third bite. Splitting H-B is
honest ONLY because the split is pre-data and mechanism-motivated; say so in
the lock, and accept that three registered bites at family #26 raises the
false-positive budget: a single marginal pass in ONE of three cells is weak
evidence by construction and must be worded that way.

## 9. As-of traps to write into the lock verbatim (attack 8)

1. TSA availability: value for day t enters at publication day 09:00 ET plus
   a buffer (suggest 09:30 ET binding); Fri/Sat/Sun values enter Monday.
   Holiday weeks: the page itself warns of delays; where a Wayback snapshot
   exists, verify the value was actually up before any fire consumes it;
   where no snapshot exists in a holiday week, zero-staleness NO-FIRE for
   that week.
2. KXTSAW close time vs Monday publication: verify per-market close_time. If
   any market trades at or after Monday ~09:00 ET, that window is
   post-full-determination; exclude it from H-A firing entirely (v25 E1
   ambiguity-window pattern). Do not let a TSA post-determination sub-case
   leak in unregistered.
3. CLI availability: use the per-product IEM AFOS issuance timestamp as the
   availability time of each month-to-date value (the v25 EIA release
   calendar win, applied here). Never an assumed hour. The CLI's own
   coverage statement defines which local calendar day is complete; local
   midnight vs ET conversion per station, no shortcuts for LAX/SFO/SEA.
4. Partial sums for firing come from archived as-issued CLI products, not
   ACIS. ACIS is for climatology (remainder distributions) only, unless the
   open scout item (correction ingestion) is resolved with an explicit
   ACIS-vs-archived-CLI diff across the universe.
5. Trace and tie handling: T=0.00 frozen (scout-verified); "strictly greater
   than X" evaluated on exact decimal inches, no float tolerance; a monthly
   total exactly equal to the strike settles NO and the signal must agree.
6. Station map frozen to the scout's table minus KXRAINSTPM (dropped, ~28y
   depth and zero settled markets); no Stapleton splice for KDEN; KDEN's
   31y depth named as a caveat in any KDEN-heavy result.
7. TSA remainder envelope (H-A1) and rain remainder climatology (H-B1) built
   walk-forward only; holiday weeks flagged from a fixed federal-holiday
   calendar, never fitted post-data.

## 10. Amendments (numbered, binding for the lock)

- **A1 (blocking):** Reconcile the KXTSAW universe contradiction (proposal
  48+9 events vs scout 10 full-history). Enumerate every settled event
  pre-lock; extend settlement reproduction to all of them (booleans/rates
  only). Unexplained failure = kill H-A. Cluster ceiling below floor = drop
  H-A at the 0b feasibility rule.
- **A2:** Restrict H-A to arithmetic-bound fires (partial + frozen worst-case
  remainder envelope decides the bracket). The unrestricted weekend-forecast
  variant is REPORTED, NON-BINDING only.
- **A3:** TSA as-of integrity audit via Wayback across May 2025 - Jun 2026
  (monthly minimum); contaminated or un-auditable days = NO-FIRE; more than
  10 percent of weeks contaminated = restrict or kill H-A. State explicitly
  that settled-bracket reproduction cannot detect sub-bracket revisions.
- **A4:** Split H-B pre-lock: H-B1 = late-window distributional claim,
  restricted to a pre-computed climatological pinning window per
  station-month; H-B2 = post-crossing YES-only stratum, own floors, own
  verdict cell. No shared pass.
- **A5:** Write the section 6 breakeven table into the lock (E15c pattern):
  binding-run fires require print <= 0.95; certainty-zone ceiling is +1 to
  +6c per contract; loss asymmetry ~32:1 at the band edge; band closure
  proven pre-lock so no exclusion rule is discovered later.
- **A6:** Correction audit before lock: archived as-issued CLI dailies vs
  final CLI/CLM across all 10 stations x all universe months; any
  strike-un-crossing correction = quantify eps and tighten the H-B2
  breakeven; eps not boundable below 0.5 percent = drop H-B2. Resolve the
  ACIS correction-ingestion open item or demote ACIS to climatology-only.
- **A7:** As-of rules of section 9 verbatim in the lock: TSA 09:30 ET
  binding availability with holiday NO-FIRE; per-product IEM AFOS issuance
  timestamps for CLI; KXTSAW close-time vs Monday-publication exclusion;
  archived-CLI-only partial sums.
- **A8:** Binding clustering: calendar month across ALL rain cities (~30-33
  ceiling), ISO week for TSA. Mandatory outcome-blind 0b fire projection per
  hypothesis (print histograms in the pre-defined fire zones, crossing
  computed from weather/TSA data only); any hypothesis below floor is
  dropped at lock.
- **A9:** Microstructure distinguisher in 0b, outcome-blind: publication-to-
  first-print latency, post-publication volume share, distinct price levels
  per market-day, for each underlying. Pre-commit the interpretation: fast
  systematic repricing = the expected market-matches-arithmetic NULL.
- **A10:** Ledger text: family #26; final registered hypothesis count fixed
  at lock after 0b drops; v25 NO-side seed explicitly NOT tested here; any
  pass = survivor of screen #26, staged $0 routing; no post-data strata; no
  third bite. Re-mark the family prior to ~8-10 percent, mass on H-B2.

## 11. What would make me eat this critique

If the 0b outcome-blind projection shows a real population of post-crossing
prints at 0.85-0.93 across 15+ month clusters with near-zero correction
incidence, the post-crossing claim is exactly the kind of boring, capacity-
bound, mechanically-explained edge a $200 bankroll can actually eat, and the
MLB-null transfer argument fails on the stated microstructure difference.
That projection costs $0 and no outcome data. Run it before believing
anything I said in section 1.

*Em-dash audit: clean (verified after write).*
