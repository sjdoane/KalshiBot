# v26 METHODOLOGY LOCK: window-aggregate certainty takers (TSA weekly, rain post-crossing)

**Status: v1 draft incorporating ALL plan-critic amendments A1-A10
(research/v26/01-plan-critic.md). Becomes LOCKED at the git commit that includes the
completed section 0 audits and ledger. No settlement-conditioned P&L before that
commit. The v25 lock's E-edit machinery (research/v25/02-methodology-lock.md) carries
over wherever referenced; every constant here is frozen at this document.**

Date: 2026-07-02. Hypothesis family ~#26. Registered hypotheses: exactly TWO, H-A and
H-B2 below (final count fixed here per A10; may only DECREASE via the pre-committed 0
rules, never increase). Mid-window rain climatology divergence (the plan critic's
H-B1) is explicitly NOT REGISTERED: its shape is general-miscalibration vs a
climatology, and the critic's power arithmetic shows it cannot validate a plausible
edge size at reachable cluster counts; registering it would be null theater (the v25
E7 lesson). The v25 NO-side seed remains untested and untouched (A10).

## Honest prior and escape claim

Family prior ~8-10 percent (critic re-mark), with the mass on H-B2. Escape form: both
hypotheses fire ONLY where the outcome is decided or near-decided by ALREADY-PUBLISHED
arithmetic, so there is no forecast for the market to out-model (the capture phantom
needs a forecast to phantom). The tested question is purely microstructural: do thin
aggregate ladders leave the DECIDED side purchasable below breakeven after the
deciding fact publishes? The MLB post-determination null closed this for
instant-determination liquid sports; GRADUAL, unsalient determination on thin
Economics/Climate ladders is the one configuration it did not test.

## 1. Universe and hypotheses

- **H-A (TSA arithmetic-bound certainty, both sides):** KXTSAW markets, settled
  events with close_time in [2025-05-01, 2026-06-30] (48 historical + recent live
  events; the 0a audit reproduces EVERY settled event's bracket, A1). Fire rule: at
  as-of time t with published day-values P_pub (subset of the Mon-Sun week), compute
  the week-average BOUNDS implied by the published days plus the EMPIRICAL EXTREME
  bounds for the unpublished days: for each unpublished day d, its historical
  min/max share-adjusted value over the trailing 730 days of as-of TSA data
  (same-day-of-week), widened by 15 percent both ways (frozen constant). If even the
  ADVERSE extreme keeps the average strictly above K, YES is arithmetic-bound
  certain; mirror for NO. Fire only then. This is A2's restriction: no distributional
  weekend forecast, only bound arithmetic.
- **H-B2 (rain post-crossing, YES only):** KXRAIN{NYC,CHI,SEA,HOU,MIA,AUS,DEN,LAX,
  DAL,SFO}M markets (STPM excluded: zero settled markets), settled events closing
  [2024-03-01, 2026-06-30]. Fire rule: the AS-OF ARCHIVED CLI month-to-date
  precipitation (from the IEM AFOS reconstruction, section 2) is STRICTLY GREATER
  than the strike PLUS a 0.02 inch safety margin (frozen; guards reporting-precision
  wobble). Then YES is a published fact (strike_type is strictly-greater). No NO-side
  mirror is possible (precipitation cannot decrease; a not-yet-crossed market is
  never NO-certain before month end, and month-end NO-certainty windows are hours,
  not weeks).

## 2. As-of data discipline (A3, A6, A7)

- TSA: value for day d becomes visible at 12:00 ET (9am publication + 3h margin) on
  the first Mon-Fri day strictly after d (Fri/Sat/Sun values all visible Monday
  12:00 ET). Model bounds use ONLY values visible at fire time. Source series:
  data/v26/tsa_daily.json (today's page) PLUS the 0a2 Wayback as-of audit: if ANY
  sampled in-window date shows a revision vs today's page above 0.5 percent, H-A is
  KILLED at the audit (the arithmetic-bound rule cannot tolerate a leaky input,
  A3). Holiday non-publication days push visibility to the next publication day by
  construction (visibility = next Mon-Fri day's noon; a holiday gap simply means
  fewer published days in the bound, never a leak).
- Rain: the as-of month-to-date is the value in the LATEST ARCHIVED CLI product
  (IEM AFOS) with issuance timestamp <= fire time minus 30 minutes; days with no
  archived CLI contribute no update (the partial sum stays at the last archived
  value: conservative, can only DELAY a crossing detection, never advance it). ACIS
  values are used ONLY for settlement reproduction (0a) and the correction audit
  (0a3), never for firing.
- Settlement truth: the Kalshi `result` field ONLY.
- Trade timestamps, ET keying, and the one-position-per-market-per-ET-day rule carry
  over from v25 E15b.

## 3. Execution, fee, bands (A5)

Carried from the v25 lock verbatim: BINDING run = print price worsened by a flat 3c
haircut; REPORTED run = side-matched prints at +1c; worst-case taker fee
ceil(7 * p_exec * (1 - p_exec)) cents on every fill; p_exec > 1 impossible by band
construction; first qualifying print per market per ET day; 1 contract.

BREAKEVEN CLOSURE TABLE (A5, frozen): a certainty fire at yes-print p costs
p + 0.03 + fee(p + 0.03). Net-if-right: p = 0.90 -> +0.06; 0.92 -> +0.04; 0.94 ->
+0.02; 0.95 -> +0.01; 0.955 -> +0.005; above 0.955 the trade cannot profit at the
binding haircut. FIRE BAND (both hypotheses): yes-print in [0.03, 0.955] for YES
fires (H-A NO fires mirror: yes-print in [0.045, 0.97], NO cost = 1 - p + 0.03).
Prints in (0.955, 0.985] on a fire-eligible market are counted UNEXECUTABLE and
reported, never scored (v25 E7 convention).

## 4. Statistics, clustering, guards (A8)

- Binding statistic: cluster-bootstrap (10,000 resamples, seed 25) 95 percent CI of
  mean net P&L per contract, binding run.
- Clusters: H-A = ISO week (UTC) of close_time. H-B2 = CALENDAR MONTH (UTC) of
  close_time ACROSS ALL CITIES (the conservative choice per A8; ~26 NYC-era months
  of which ~7 are 10-city months).
- Guards carried from v25: LOCO (drop best cluster), month-block sensitivity for
  H-A (calendar-month clusters), chrono halves reported. The v25 shock-window guard
  is replaced by: exclude the single highest-volume calendar month (reported;
  binding only through the LOCO gate).
- CONTROL GATE IS VACUOUS BY DESIGN and is hereby replaced (both hypotheses embed
  the partial-window fact in the fire condition; a no-partial-info control cannot
  fire): instead the verdict MUST report the A9 microstructure diagnostic:
  publication-to-print latency (time from the deciding publication to each fired
  print) and its relation to per-fire P&L, as a REPORTED, non-binding honesty check
  that fires are genuinely post-publication (any fire whose print PRECEDES the
  deciding publication indicates an as-of bug and invalidates the run).

## 5. Gates and verdict lattice

H-A PASS requires ALL: (1) >= 30 fires across >= 12 distinct fired ISO-week
clusters (else UNDERPOWERED-NULL, sub-floor quantity named); (2) binding CI lower
bound > 0; (3) LOCO survives (else MARGINAL); (4) month-block guard clean (else
FRAGILE-PASS). H-B2 PASS: same with >= 30 fires across >= 10 distinct month
clusters. Routing, no-third-bite, null wording ("a null of THIS frozen rule set"),
and the ledger duties carry over from v25 sections 9-10 verbatim. Any PASS routes to
the staged path (stage 1 $0 live read first), never to capital.

## 0. Pre-lock audits and ledger (kill switches; filled before the locking commit)

### 0a. Settlement reproduction (A1)

TSA: for EVERY settled KXTSAW event in the universe, the Mon-Sun mean of
data/v26/tsa_daily.json values must reproduce the settled bracket (result field).
Rain: for every settled city-month, the ACIS monthly sum (T=0) must reproduce the
settled bracket. Any unexplained mismatch = KILL (that hypothesis).
RESULT: [PENDING]

### 0a2. TSA as-of integrity (A3)

Wayback snapshots of tsa.gov/travel/passenger-volumes at >= 12 spot dates spanning
May 2025 - Jun 2026: sampled same-dates must match today's page within 0.5 percent.
Any in-window revision above that = H-A KILLED.
RESULT: [PENDING]

### 0a3. CLI correction rate (A6)

From the IEM AFOS reconstruction: count corrected reissuances and DOWNWARD
month-to-date revisions across all archived station-months; compare last-of-month
CLI month-to-date vs ACIS final for >= 3 stations. If the downward-revision rate
implies a post-crossing reversal probability that cannot be bounded below 0.5
percent, H-B2 is DROPPED (the -0.95 tail at 0.5 percent eats the +2-6c edge).
RESULT: [PENDING]

### 0b. Outcome-blind fire projection and power (A8)

Using only published-series arithmetic + prints (never results): projected fire and
fired-cluster counts per hypothesis at the frozen bands. If a hypothesis cannot
reach its floor, it is DROPPED at the locking commit (ledger records the reduced
count). The A9 latency distribution is also computed here outcome-blind.
RESULT: [PENDING]

### 0c. Pre-lock computation ledger

[PENDING: exhaustive list per the v25 E12b convention: 0a/0a2/0a3 rates, 0b
projections, and the universe/volume/rules probes recorded in 00-proposal.md and
scout-data-sources.md. Nothing else.]

*Em-dash audit: clean (verified after write).*
