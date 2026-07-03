# v28 VERDICT CRITIC: adversarial dissection of the D' PASS

**Date:** 2026-07-03. Role: kill the first gate-pass in 28 hypothesis families, or
size it honestly. Reviewed: 02-methodology-lock.md (locked at e0fc76f, which also
contains rt_backtest.py byte-identical to the working tree), 01-plan-critic.md,
03-methodology-critic.md, data/v28/backtest_results.json + backtest_results_ha.json.
Independent reproduction run directly against the banked data with the project venv;
every number below is my own recomputation. The 18-fire set, funnel counts
(399,332 / 142,036 / 32,980 / 2,385 / 18), binding CI (+6.78pp, [+2.55, +10.0]),
LOCO (girls_like_girls, 12 fires, lo +2.11pp), and month-block (lo +1.50pp)
all reproduce exactly. No arithmetic error found. The kill, where it lands, is
methodological, not computational.

## VERDICT: PASS-DOWNGRADED

From "PASS (FEASIBILITY-NOT-SAFETY)" to **FEASIBILITY-CENSUS PASS: deterministic at
lock time, unbankable, bust hazard unbounded, edge headline struck**. Routing to the
stage-1 $0 live read and (conditionally) the one v27-A3 shadow on H-A LIVE stands,
because it is pre-paid and free. What does NOT stand: any reading of this as the
project's first out-of-sample P&L validation, and the +6.8pp figure as an edge
estimate. Grounds follow; V2, V3, V5, V6 are load-bearing.

## THE 18 FIRES, DISSECTED

Columns: side, print price, print size (contracts), row state (s/N), realized
arrivals A_act, strike K, deciding bound, slack = distance past the decided
threshold in display points, settlement read, net P&L per contract at binding
frictions, taker side of the print.

| # | ticker | movie | side | p | size | s/N | A_act | K | bound | slack | read | pnl | taker |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | KXRT-MEL-5 | melania | yes | .950 | 1000 | 11/18 | 12 | 5 | low 6.67 | 0.67 | 10 | +.01 | no |
| 2 | KXRT-MEL-5 | melania | yes | .940 | 20 | 11/18 | 12 | 5 | low 6.67 | 0.67 | 10 | +.02 | no |
| 3 | KXRT-ANI-17 | animal_farm | yes | .940 | 1 | 23/43 | 7 | 17 | low 20.00 | 2.00 | 24 | +.02 | no |
| 4 | KXRT-INT-40 | in_the_grey | yes | .930 | 27 | 47/34 | 5 | 40 | low 41.03 | 0.03 | 46 | +.03 | no |
| 5 | KXRT-INT-55 | in_the_grey | no | .090 | 13 | 47/34 | 5 | 55 | high 53.85 | 0.15 | 46 | +.05 | yes |
| 6 | KXRT-INT-40 | in_the_grey | yes | .950 | 23 | 46/35 | 4 | 40 | low 41.03 | 0.03 | 46 | +.01 | no |
| 7 | KXRT-POW-65 | power_ballad | yes | .930 | 5 | 87/105 | 32 | 65 | low 66.42 | 0.42 | 86 | +.03 | no |
| 8 | KXRT-DIS-93 | disclosure_day | no | .070 | 100 | 82/220 | 88 | 93 | high 87.34 | 4.66 | 80 | +.03 | no |
| 9 | KXRT-DEA-90 | death_of_robin_hood | no | .050 | 5 | 77/53 | 47 | 90 | high 88.00 | 1.00 | 70 | +.01 | yes |
| 10 | KXRT-GIR-70 | girls_like_girls | yes | .920 | 10 | 87/31 | 6 | 70 | low 72.97 | 1.97 | 89 | +.04 | no |
| 11 | KXRT-GIR-65 | girls_like_girls | yes | .870 | 82 | 87/31 | 6 | 65 | low 72.97 | 6.97 | 89 | +.09 | no |
| 12 | KXRT-GIR-60 | girls_like_girls | yes | .950 | 77 | 87/31 | 6 | 60 | low 72.97 | 11.97 | 89 | +.01 | no |
| 13 | KXRT-GIR-95 | girls_like_girls | no | .060 | 25 | 87/31 | 6 | 95 | high 89.19 | 4.81 | 89 | +.02 | no |
| 14 | KXRT-GIR-92 | girls_like_girls | no | .050 | 11 | 87/31 | 6 | 92 | high 89.19 | 1.81 | 89 | +.01 | yes |
| 15 | KXRT-TOY-45 | toy_story_5 | yes | .760 | 3 | 93/211 | 32 | 45 | low 80.66 | 34.66 | 94 | +.19 | no |
| 16 | KXRT-GIR-50 | girls_like_girls | yes | .420 | 1 | 87/31 | 6 | 50 | low 72.97 | 21.97 | 89 | +.53 | no |
| 17 | KXRT-DEA-75 | death_of_robin_hood | no | .150 | 20 | 69/95 | 5 | 75 | high 71.00 | 3.00 | 70 | +.11 | yes |
| 18 | KXRT-JAC-45 | jackass_best_and_last | yes | .950 | 16 | 87/60 | 13 | 45 | low 71.23 | 25.23 | 88 | +.01 | no |

Concentration: 16 distinct markets, 9 movie clusters, but girls_like_girls carries
6 of 18 fires and months are 2026-02 (2), 2026-05 (4), 2026-06 (12): the month-block
"guard" runs on 3 month-clusters, two thirds of the sample in one month. Slug and
read sanity: every fire's settlement read sits inside its fire-time bound widened by
the margin; no vintage or slug mismatch found on the 9 fire movies.

## V1. CIRCULARITY: WHAT THE PASS DOES AND DOES NOT ESTABLISH (confirmed)

On any event that survives the 0-S validity rule, a D' fire cannot lose unless the
read escapes [low - 1, high + 1], and 0-S verified coverage 34/34 with worst excess
0.00 BEFORE the lock. Therefore all 18 fires winning is not evidence; it is the 0-S
result restated. The binding CI is a cluster-bootstrap on FIRE SIZES (1 - cost -
fee), i.e. on how far below 0.955 the 18 prints happened to sit. The gate, in plain
words, reduces to: "at least 15 prints at <= 0.955 existed on realized-arrival-decided
states across >= 8 movies." That is a real, falsifiable feasibility census (v26 died
on exactly this shape, and 99.25 percent of decided prints here are indeed priced
past breakeven), and it is the ONLY thing the pass establishes. It establishes
nothing about win probability, bust hazard, live decidability, or fillability.

## V2. THE PASS WAS DETERMINISTIC AT LOCK TIME

The lock commit already contains, in section 0: the 18-fire / 9-cluster census (0-B)
and the 34/34 coverage result (0-S). Given those two numbers, the "post-lock
settlement-conditioned run" had zero remaining degrees of freedom: every fire's win
was implied, so the binding CI, LOCO, and month-block could not have failed in any
world consistent with section 0. This is disclosed and permitted by the lock's own
design (pre-paid audits), but the headline "a registered component passed its locked
gates for the first time in 28 families" must not be read as lock-then-discover.
It was lock-and-simultaneously-know. The a-priori suspicion that motivated this
review is therefore CORRECT in direction: the pass is exactly as strong as the
pre-lock census, no stronger.

## V3. THE 0-S REFINEMENT WAS LOAD-BEARING AND SEQUENTIALLY ADOPTED (downgrading)

Recomputed under each historical form of the 0-S rule, holding everything else
locked:

| 0-S form | margin | fires | clusters | verdict |
|---|---|---|---|---|
| Draft naive (all events), p95 raise | 6.0 | 5 | 3 | UNDERPOWERED-NULL |
| Validity rule + naive diff, p95 raise | 2.0 | 11 | 6 | UNDERPOWERED-NULL |
| As locked (validity + bound coverage) | 1.0 | 18 | 9 | PASS |

Both pre-lock refinements (the validity rule AND the coverage reformulation) are
individually necessary for the pass; each was adopted after an adverse intermediate
result (5 naive violations, on SHE/HOW/WUT/REM/STR). On the merits the refined form
is the CORRECT test for a bound that already carries realized arrivals (the naive
|diff| conflates archive staleness, which A_act absorbs, with read divergence, which
the margin absorbs; the valid-read naive p95 of 2.0 is driven by SCA's 2.3-day-stale
row, a staleness artifact). So this is honest audit repair rather than fabrication,
BUT the fact remains: the pass does not survive any earlier version of its own
audit, and the refinement direction was chosen with the violations in view. At
family #28, that is precisely the survivorship channel. Downgrade, not refute.

## V4. THE N_final CONVENTION CONFLICT: THE ALTERNATE READING FLIPS THE VERDICT

The lock adopts D' by reference to 03-methodology-critic.md Part 1.2 ("full text...
all binding"), whose N_final convention reads: first proven row at-or-after close
within 72h, "ELSE THE LAST PROVEN ROW BEFORE CLOSE", else excluded. The
implementation (read_state, rt_backtest.py line 77) drops the fallback and the 72h
clause entirely, excluding 9 events. Rerun WITH the referenced fallback: **100
fires, 17 clusters, 33 LOSSES, mean -7.0pp, CI [-16.2, +6.5]: the gate FAILS.**
The losses are all A_act = 0 fires on stale-archive events (SHE, WUT, HOW) busting
at -0.05 to -0.99.

Adjudication: the fallback convention is itself unsound. With N_final = a pre-close
row, A_act = 0 asserts "zero arrivals until the read" on events whose archives end
3-5 days early; that is not a perfect-arrival bound, it is a wrong-arrival bound,
and it contradicts D's own premise (the 03 text's "overcounting post-close arrivals
only widens the bound (conservative)" has no mirror: undercounting narrows it,
anti-conservatively). The implementation's exclusion also matches the lock body's
0-S validity language. So I rule the implemented reading the methodologically
correct one and do NOT refute on this ground. But two consequences are binding:
(i) the verdict doc must state the textual conflict and that the alternate reading
of the locked spec fails the gate; (ii) the 33-bust profile is the honest exhibit of
what a wrong bound costs (mean bust ~ -0.45, tail -0.99), which is the hazard class
the shadow must bound before any capital. Also note the 72h clause is unimplemented
in the passing direction too: KXRT-STO's read row is 80.8h post-close and under the
referenced spec would have used the pre-close fallback.

## V5. FIRE QUALITY: THE HEADLINE IS TWO OFF-MARKET LOTS DEEP (downgrading)

- **Fire 16 (GIR-50, +0.53) is an off-market one-lot print**: 1 contract at 0.42
  while the same market's other prints that ET day are at 0.99 (day range 0.42-0.99,
  3 prints, 8 contracts). **Fire 15 (TOY-45, +0.19) is a 3.4-lot print at 0.76**
  with within-the-hour neighbors at 0.90-0.99 (day volume 9 contracts). These two
  prints carry **59 percent of the total P&L** of the pass. Ex-fluke: mean +3.1pp,
  CI [+2.1, +4.1], 16 fires / 8 clusters, sitting EXACTLY at the cluster floor.
- **16 of 18 fire prints have the taker on the OPPOSITE side** (e.g. a 1000-lot
  SELL into the bid at 0.95 on MEL-5, with the surrounding book printing 0.96+,
  i.e. above the band). A taker strategy on the fire side had no print-priced
  liquidity to lift at those moments; the +3c haircut assumption is doing all the
  work. The locked "reported side-matched +1c" sensitivity, missing from
  backtest_results.json (computed only for H-A), computes to **2 fires / 2 clusters**
  (DIS-93, GIR-95): the execution-credible evidence base is two prints.
- **6 of 18 fires decide by less than 1.0 display point of slack**, including both
  INT-40 fires at 0.03 points (one review's rounding moves them). 12 of 18 net
  1-3 cents per contract at binding frictions.
- E5 margin restoration (the lock's implementation uses symmetric 1.0, weaker on
  the YES side than the E5 amendment's rounding-width-plus-read-margin; 0-R was
  never runnable on the banked display-only schema, so unpinned worst-case applies):
  rerun at yes > K+2.0 / no < K-0.5 gives 24 fires / 9 clusters, 0 losses, CI lo
  +2.4pp. The pass is robust to the E5 deviation (the NO side loosens as the YES
  side tightens); symmetric tightening to 1.5 / 2.0 gives 14/7 and 11/6, both
  under-floor, so the margin sensitivity is real but the locked asymmetric form
  survives. Documented, not verdict-changing.

## V6. LIVE REPLICABILITY: ZERO OF 18 FIRES ARE LIVE-CERTIFIABLE (the shadow's real question)

For each fire I computed A_thr, the largest arrival count at which the fire stays
decided, against the certifiers a real-time engine could run:

- **Registered H-A cap (2.0 x max prior ratio): decides 0 of 18.** Caps exceed
  A_thr by 8x to 50x everywhere (e.g. ANI: cap 208 vs threshold 12.6; GIR: cap 150
  vs 7-36; TOY: cap 660 vs 215). MEL has 1 prior (no fire possible).
- Own-movie realized arrival rate, extrapolated 1x (not a bound, just a point
  estimate): decides 6 of 18. At 2x own rate: 2 of 18 (POW, TOY).

So every one of the 18 fires needed arrival knowledge unavailable to any real-time
certifier under the registered rule; the pass transfers to live H-A only if fresh
states polled near the read shrink d and the cap enough, which no backtest quantity
here demonstrates. The routing's own rationale ("estimator-width diagnosis") is
CONFIRMED as a diagnosis: A_cap is 10-50x realized arrivals. But the shadow prior
must be stated as: no evidence yet that the live bound EVER decides inside the
executable band; the stage-1 $0 read exists to answer exactly that before the
shadow burns the family's one slot.

## V7. THE 9 EXCLUDED EVENTS ARE NOT THIN MOVIES (selection characterized)

BIL, HOW, MER, MIC, REM, SCR, SHE, STR, WUT: excluded solely because the Wayback
archive lacks a post-close row (gaps 0.1 to 4.7 days). By volume they include the
LARGEST events in the universe (MIC 2.2M contracts, SCR 965k, WUT 836k, MER 516k);
32,980 evaluable prints left the funnel with them. The exclusion is archive-driven,
not liquidity-driven, and it is the superset of the 5 naive-0-S violators, so the
events most capable of producing busts are exactly the events removed (V3/V4). For
the live engine this is irrelevant (it polls its own states); for the BACKTEST
claim, "all fires positive" is conditional on archive completeness and must be
worded as such.

## V8. ROUTING FIDELITY (verified, two nits)

- dprime verdict string "PASS (FEASIBILITY-NOT-SAFETY; $0 live read first, always)"
  matches the locked E10/PASS wording. Routing string "shadow testing H-A LIVE (D'
  bound passed; estimator-width diagnosis)" matches the locked lattice branch
  "D' pass + H-A null = shadow testing H-A LIVE".
- H-A "NO-FIRES NULL" is consistent with the pre-lock 0-B kill: zero fires, so no
  settlement-conditioned H-A P&L ever ran, honoring the lock's "no H-A run will
  ever occur" in substance.
- The v27 A3 shadow protocol reference is intact in the lock (lines registering
  H-B as shadow-only and E11: week-13 kill on cluster-CI upper < 0 at >= 8 fired
  clusters, week-26 binding at >= 12 clusters, one week-39 extension, one shadow
  ever, H-B strictly a reported overlay).
- Nits: results.json omits the locked side-matched +1c reported sensitivity for D'
  (it is 2 fires / 2 clusters, V5); and the N_final textual conflict (V4) must be
  resolved in writing before the shadow spec is drafted.

## BINDING CONSEQUENCES

1. Verdict class: **PASS-DOWNGRADED to FEASIBILITY-CENSUS PASS.** Not refuted: the
   census is real (18 executable prints on decided states genuinely existed where
   v26 found zero), the locked-and-implemented rules reproduce exactly, and the
   two disclosed pre-lock refinements are methodologically defensible. Not
   confirmed as an edge: V1/V2 (the win record is circular and was known at lock),
   V3 (pass fails under every earlier form of its own audit), V5 (59 percent of
   the P&L is two sub-5-lot off-market prints; execution-credible base is 2
   fires), V6 (0 of 18 live-certifiable under the registered rule).
2. Routing stands: stage-1 $0 live read, then at most the one v27-A3 shadow on
   H-A LIVE. The $0 read is a GATE, not a formality: if live-polled fresh states
   never produce a bound-decided side inside the 0.955 band, the shadow does not
   open and the family dies without it.
3. The +6.8pp / CI [+2.5, +10.0] headline may not be quoted as an edge estimate
   anywhere. Quotable form: ex-fluke +3.1pp [+2.1, +4.1] print-size statistic,
   16 fires / 8 clusters, at the cluster floor.

## REQUIRED VERDICT WORDING (exact, evidence-supported)

"v28 D' PASSED its locked gates as implemented (18 fires / 9 clusters, all
positive, cluster CI [+2.5, +10.0]), and the verdict critic DOWNGRADES the pass to
a feasibility census: the all-win record was deterministically implied by the
pre-lock 0-S coverage result, so the gate certifies only that mid-priced executable
prints existed on realized-arrival-decided states, 99.25 percent of which were
already priced past breakeven. The mean is a print-size statistic, 59 percent
carried by two sub-5-lot off-market prints (ex-fluke +3.1pp, [+2.1, +4.1], exactly
at the 8-cluster floor); 16 of 18 prints traded with the taker on the opposite
side and the side-matched sensitivity holds 2 fires; zero of the 18 fires were
decidable at fire time by the registered live arrival cap, which exceeds the
deciding threshold 8x to 50x on every fire; and under the alternate (referenced)
N_final fallback reading of the locked D' spec the gate fails outright (100 fires,
33 busts, CI [-16.2, +6.5]), a reading rejected here as anti-conservative but
disclosed as verdict-flipping. Consequently this is NOT the project's first
validated edge; it is the first family whose executable-print census came back
nonempty. Unbankable without a live read. Routing per the locked lattice: stage-1
$0 live read of the H-A LIVE bound; the one v27-A3 shadow (weeks 13/26/39, one
shadow ever, H-B reported-overlay only) opens only if the $0 read shows the live
bound deciding inside the executable band at least once."

*Em-dash audit: clean (verified after write).*
