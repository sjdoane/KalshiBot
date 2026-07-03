# v28 METHODOLOGY CRITIC: stress-test of the draft lock (02-methodology-lock.md)

**Date:** 2026-07-02. Reviewed: 02-methodology-lock.md (draft), 01-plan-critic.md
(A1-A12), 00-proposal.md, scout-rt-vintages.md, v27 02-methodology-lock.md (A3
shadow protocol + E-edits), v26 04-FINAL-VERDICT.md. Independent verification pass
run directly against the banked data (data/v28/markets_all.json, rt_slug_map.json,
rt_vintages.json, trades.jsonl); counts below are my own recomputation, not the
lock's assertions.

## VERDICT: LOCK-OK-WITH-EDITS (E1-E13 binding; E3, E4d, E5 are load-bearing)

The architecture (H-A bound-certainty taker, H-B descoped to shadow, kill-friendly
section 0) is sound and correctly shaped by the v26/v27 precedents. The draft is
NOT lockable as written: it contains one dataset-schema phantom in the F11 family
(E3), one genuine walk-forward leak (E4d), a silently weakened A4 margin (E5),
three factual errors in the universe paragraph (E1), and four undocumented
deviations from binding plan-critic amendments while claiming only one (E13).
All are fixable by edit; no redesign is required.

## PART 1: ADJUDICATION OF THE D DEVIATION

### 1.1 The refusal of D* as specified is CONFIRMED

The plan critic's D* substitutes the settled `expiration_value` at every evaluable
print with the fire rule otherwise unchanged. With the settled score known, the
"bound" collapses to a point: for every strike the winning side is known, every
fire wins by construction (net >= +0.5c even at the 0.955 band edge per F8), and
the CI-lower-than-zero gate can never fail. The gate therefore reduces to the
floor count: do >= 30 winning-side prints exist in the executable band across >= 12
clusters, AT ANY TIME in the market's life. Early-window prints on the eventual
winner at mid prices exist essentially surely on a 412,004-print universe (a 0.50
print is on the eventual winner about half the time, across 10-29 strikes per
event). So D* passes trivially, and a trivially passing component that routes to
the family's one shadow slot is exactly the shadow-shopping backdoor the v27
critics closed. The lock's distinction is also correct on the merits: v27 D1
substituted a channel INPUT (flown/sched) while the model error survived; here the
proposed substitution IS the settlement variable, so no error survives. The
refusal reasoning is sound.

### 1.2 But the D slot IS salvageable in a well-posed non-trivial form: D'

The plan critic's own F4 dismissed arrival-only substitution because "the mix, not
the arrival count, drives the score." That objection lives in the H-B world, where
the mix must be MODELED. In the H-A bound world the mix is WORST-CASED, not
modeled; the only estimated quantity in H-A is the arrival cap. Substituting the
realized arrival count therefore prices the ceiling of H-A's one modeling channel
without touching the settlement variable. This is the v27 D1 pattern applied
correctly, and F4 missed it because it analyzed substitution into the score
predictor, not into the bound.

**D' (perfect-arrival bound), exact specification:**

- Identical to H-A in every respect except A_cap is replaced per fire row by
  A_act(row) = max(0, N_final - N_row), the realized critic-count arrivals between
  the row and the settlement read (deliberate look-ahead on the channel input
  only). N_final convention: reviewCount at the first proven row at-or-after
  close_time, within 72h; else the last proven row before close; movies with
  neither are excluded from D'. Overcounting post-close arrivals only widens the
  bound (conservative).
- Worst-case mix retained: low = 100L/(N + A_act), high = 100(L + A_act)/(N +
  A_act). Margins per E5. Same frictions, band, evaluability, one position per
  market per ET day. No 12-prior requirement and no walk-forward need (nothing is
  estimated), so ALL 43 clusters are D'-evaluable, including the early movies the
  12-prior floor burns for H-A.
- NOT degenerate-positive, on two independent grounds: (i) the conditioning can be
  empty: D' fires only when a snapshot-proven state is truly decided even against
  all-adverse remaining arrivals AND an executable print exists afterward, and the
  v26 precedent (decided ladders snap to 0.96+) says this is plausibly rare, which
  is exactly what makes its floor a real kill; (ii) fires can LOSE: P&L is scored
  against actual settlement, and withdrawals, recounts, and read divergence bust a
  D' fire at roughly -0.95, so the CI gate is not vacuous.
- Gates: floors 15 fires / 8 movie clusters (same as H-A; whenever caps hold the
  D' fire set is a superset of H-A's, so D' failing the floor entails H-A failing
  it); cluster-bootstrap CI lower > 0 (10k, seed 28); LOCO; month-block.
- Pre-committed routing: D' fails its floor or CI = FAMILY DEATH, no shadow, no
  rescue (even perfect arrival knowledge finds no executable decided prints: the
  v26 wall extends to this family). D' passes while H-A nulls = H-A's null is
  attributable to estimator width, and the shadow opens testing H-A-LIVE per E11
  (fresh states shrink d and therefore the cap; the live engine is the tighter
  estimator). Both pass = stage-1 $0 read then shadow, as already locked.

**Why the lock should adopt D':** without it, an H-A floor-failure is ambiguous
between "no executable prints on decided states" (wall; family properly dead) and
"A_cap x2.0-max is too wide" (estimator artifact). The H-A-only lock cannot
distinguish these, dies on both, and forfeits the diagnostic for approximately
zero marginal cost (one extra pass over the same rows). Adopting D' replaces D*
one-for-one; the registered set stays at three components and A12 stays closed.

**The conditioning salvage suggested in the brief** (restrict D* to prints after
the state was snapshot-proven decided-adjacent) converges to exactly D' once
"decided-adjacent" is made precise: decided against realized arrivals at
worst-case mix. The decay-rate variant (measure the speed of mispricing decay
after decidedness) is REJECTED as a binding component: it has no pre-registerable
fire rule, and measuring decay needs consecutive proven rows bracketing the
decidedness moment, which the 0.3-1.4 rows/day grid cannot supply. It may run as
a reported diagnostic only.

**If the operator declines D':** the H-A-only scope is honest and
family-death-on-H-A-death is the correct consequence, PROVIDED the verdict wording
states the wall-versus-estimator-width ambiguity explicitly and no shadow is ever
inferred from an H-A floor failure. A trivially passing bound cannot route to a
shadow; equally, an ambiguous death cannot be quietly reopened later.

## PART 2: INDEPENDENT UNIVERSE VERIFICATION (A1 adjudicated by recount)

I recomputed directly from the banked files: data/v28/markets_all.json contains
671 markets, ALL status finalized, across exactly 43 event tickers, closes
2026-01-26 (KXRT-MER) through 2026-06-29 (KXRT-JAC, KXRT-SUPE); every event has
all markets settled; trades.jsonl contains exactly 412,004 lines. The lock's
43/671/412,004 is REAL and the plan critic's 22-event count was indeed an
incomplete live pull (single-page markets query returning 520; the banked pull
evidently paginated or used settled-status paging). A1 is closable, but by
EVIDENCE: 0-U must state the exact pull method (endpoint, params, pagination)
so the reconciliation is reproducible, not asserted.

However, the recount surfaced three factual errors in the universe paragraph and
two data-layer findings the lock does not know about (E1-E3 below).

## PART 3: FINDINGS AND BINDING EDITS

### E1 (universe paragraph corrections; factual)

(a) **DUN/DUNE are NOT settled.** Neither KXRT-DUN nor KXRT-DUNE appears among
the 43 settled events; both close 2026-12-18/21 per the scout (DUN inactive, DUNE
active). The lock's sentence "KXRT-DUN and KXRT-DUNE are distinct settled events
on the same film and both count... they form ONE cluster" is false as written and
must be recast as a LIVE/SHADOW-universe rule (if both ever settle, one cluster;
today, neither is in the backtest).

(b) **The real same-film wrinkle is SEN/SEND.** The banked slug map assigns
send_help to KXRT-SEN (settled 2026-02-02, expiration_value 93, 12 markets). The
scout's KXRT-SEND (closed 2026-02-02, never finalized) is the dead listing of the
SAME film. SEND's exclusion stands; document SEN/SEND as one film so the settled
set carries no duplicate. Duplicate hunt across the 23 mapped events: no slug
maps to two settled events; the 20 unmapped pre-April events cannot be
duplicate-checked until mapped (E2).

(c) **KXRT-SCR's expiration_value is the string "Above 32", not a score.** The
lock's "ALL 671 markets carry expiration_value (the settled score)" is false for
this event. Frozen handling, pinned now: SCR's settled score is band-inferred
from per-market results (max yes strike, min no strike]; SCR is EXCLUDED from all
score-valued computations (0-S diff rows, any calibration) and retained for
fire/settlement scoring via the result field only.

### E2 (slug and crawl coverage; blocking for section 0)

rt_slug_map.json maps 23 of the 43 settled events. The 20 unmapped events are
exactly the pre-April closes, which are the PRIORS feeding A_cap and the 12-prior
floor. rt_vintages.json currently holds 3 events (crawl in progress). The lock
cannot bind until: (i) all 43 events are slug-mapped under the scout's
disambiguation protocol (CDX prefix enumeration + 2026 activity + settled-band
validation; older titles have higher ambiguity risk); (ii) 0-U reports mapping
and crawl success per event. Any unmappable or uncrawlable prior reduces the
contributing-prior count (E4a) and must be counted honestly, not padded.

### E3 (F11-family schema catch; LOAD-BEARING)

H-A is registered on raw counts: "liked L, notLiked M, N=L+M, unrounded ratio
from the scorecard JSON, NEVER the rounded display." The banked vintage rows are
[wayback_ts, score, reviewCount] ONLY: they store the ROUNDED DISPLAY and N, and
DO NOT store likedCount/notLikedCount. As banked today, the registered H-A bound
is unimplementable from the data layer: this is failure mode F11 (dataset schema
phantom), the exact shape that killed V10-A. REQUIRED before lock: extend the
crawl schema to store, per row: likedCount, notLikedCount, reviewCount,
ratingCount, displayed score, and parse source (scorecard vs JSON-LD), with the
A4 integrity check likedCount + notLikedCount == reviewCount enforced at crawl
time (failing rows stored but flagged no-state). 0-L must verify schema
completeness on the finished crawl. Rows with score None (pre-release) are
no-state, as already implied.

### E4 (A_cap pinning; resolves the ambiguities and one real leak)

(a) **Prior row selection:** for prior movie j at horizon d, r_j(d) =
(N_j(read_j) - N_j(s_j)) / N_j(s_j), where s_j is the LAST proven row at-or-before
(read_j - d). If no such row exists, j does NOT contribute at that d. The
12-prior floor counts CONTRIBUTING priors at that d, else NO FIRE. This makes the
bursty-grid ambiguity explicit and self-limiting: large d with thin prior
coverage disables fires instead of fabricating caps. Direction note: a stale s_j
attributes a longer window's arrivals to d days, overestimating r_j and widening
the cap (conservative).

(b) **d convention:** d = days from the fire ROW's timestamp to the settlement
READ, pinned as close_time + 3h (the settlement_ts pattern), rounded UP to whole
days for prior matching. d exceeding the movie's own market life (rows predating
open) is legitimate: the bound covers all arrivals since the row and (a) guards
the cap's estimability at large d. No minimum-row-age rule is needed; state this.

(c) **N_j(read_j) convention:** first proven row at-or-after close_j within 72h,
else last row before close_j; else j is excluded as a prior. Same convention as
D' N_final.

(d) **WALK-FORWARD LEAK (genuine, must fix):** the lock admits priors "settled
before the print's movie closes." A prior settling mid-window, AFTER the print
being evaluated, leaks its final N into a cap governing a fire at a time when
that information did not exist. Fix: priors must be settled at-or-before the
PRINT timestamp.

(e) **Cap-exceedance audit (new 0 item):** for every settled movie with >= 12
contributing priors at the relevant d values, compute whether realized arrivals
exceeded the FIRE-TIME A_cap (walk-forward caps, not recomputed ones; this also
pins the 0-W reversal clause, E7). Report the exceedance rate and the prior-r
distribution per d (n contributing, max, p90) in 0-B. Any historical exceedance
or withdrawal that flips a decided call = H-A KILLED (already the lock's rule;
now computable and pinned to fire-time caps).

(f) **x2.0 times max accepted as frozen.** Two residuals are owned, not fixed:
a first-of-its-kind embargo-timing regime (reviews arriving only in the final
24h, unlike any prior) can exceed any empirical cap; and cross-applying a
small-N prior's relative burst to a large-N title overstates the cap
(conservative, power-eating; 0-B adjudicates whether any fires survive it).
Critic-score bombing is not a real tail (the Tomatometer is critics-only;
audience bombing is irrelevant), but embargo-lift bursts are, and the per-d
max-over-priors captures them only if some prior exhibited the shape.

### E5 (margin semantics; undocumented A4 deviation, must restore)

The lock's decided-YES rule low > K + 1.0 is ONE POINT WEAKER than binding A4
(unrounded >= K + 1 + 1.0). Decomposition: YES requires displayed F >= K + 1
(strict-greater on integer strikes, confirmed). Under the WORST rounding
convention (floor), the unrounded final must reach K + 1, which consumes the
lock's entire 1.0, leaving ZERO for the settlement-read divergence the lock's own
text claims the margin absorbs (the MOR case). The two deciding directions are
also NOT symmetric: NO requires F <= K, which under worst-case (round-half-up)
needs unrounded < K + 0.5, so the lock's high < K - 1.0 carries 1.5 points of
protection while its YES side carries 0. Frozen fix:

- Add **0-R (rounding pin, $0, outcome-blind):** once E3's schema lands, compare
  displayed score vs 100L/N across all crawled rows; determine round-half vs
  floor. If pinned round-half: decided-YES low > K + 0.5 + 1.0; decided-NO
  high < K + 0.5 - 1.0. If unpinnable or inconsistent: worst case per side,
  decided-YES low > K + 1 + 1.0 (A4 restored; yes, effectively ~2 display
  points, and that is the intended price of an unknown convention plus a proven
  1-point read divergence); decided-NO high < K + 0.5 - 1.0.
- The 0-S p95-raise applies ON TOP of these, never below them.

### E6 (0-S sharpening)

The nearest-row |diff| conflates arrivals in the gap (already covered by A_cap)
with true read divergence; that inflates p95 and can only RAISE the margin
(conservative, acceptable), but pin: nearest row AT-OR-BEFORE close only (a
post-close row imports post-read arrivals in the wrong direction); SCR excluded
(E1c); MOR INCLUDED in the 0-S distribution (its 1-point gap is the phenomenon
being measured) but excluded from any snapshot-to-settlement calibration per A7.
Add the end-to-end check: zero historical decided-call violations under the
final frozen rules (this is E4e's audit; one computation, referenced twice).

### E7 (0-W: restore the A6 slack tier; pin the reversal cap)

The lock's 0-W ignores decreases of <= 2 reviews entirely and jumps straight to
kill at > 2 percent of pairs. A 2-review purge at N = 40 moves the unrounded
score up to ~1.3 points, which escapes even the restored E5 margin's rounding
budget: small withdrawals are NOT free. Restore A6 verbatim as the middle tier:
more than 2 percent of pairs with ANY decrease, or any single decrease > 2
reviews, adds a two-sided W_max slack (max observed decrease) to the bound;
more than 5 percent of pairs = H-A dead. KEEP the lock's addition that any
historical decided-bound reversal kills, and pin it to FIRE-TIME A_cap (E4e);
movies lacking 12 contributing priors are vacuous for the reversal check and
are reported as such, not counted as clean. The 2-review / 2-percent / 5-percent
numbers are arbitrary but pre-registered and now carry the W_max slack as the
actual protection; defensible.

### E8 (evaluability audit, missing from section 0)

v27 carried an explicit evaluability kill line (41.3 percent vs a pre-set 40).
The v28 draft has NONE. Add **0-E:** fraction of in-band prints with at least one
proven prior row bearing a valid score-state; pre-set kill line 30 percent
(frozen; lower than v27's 40 because pre-open rows legitimately serve weekend
markets here). Also report the per-movie distribution: with 2.5-11 day windows
and 0.3-1.4 rows/day, some movies will carry zero usable states, and they must
die visibly at 0-E, not silently.

### E9 (band/fee wording; A10 restoration)

"Fire... at prints with cost <= 0.955" is ambiguous between a print-price band
and an all-in-cost band. Pin to the v25/v27 convention: PRINT price in [0.05,
0.955], +3c binding haircut applied in P&L, worst-case quadratic fee
ceil(0.07 x P x (1-P)) per contract. And restore A10's required plain statement:
under the binding convention nothing above roughly 0.92 print can clear
breakeven, so the executable H-A band is effectively prints <= ~0.92; this is a
design fact, not a post-hoc discovery. 0-B reports the +1c side-matched
sensitivity (A8) alongside.

### E10 (gates: what the floor can and cannot certify)

H-A fires win unless the bound busts, so the 15/8 floor plus CI-lower > 0 is
really two questions: feasibility (do executable decided prints exist at all:
the exact v26 kill shape) and bust absence. The floor is HONEST as a kill: 0-B
kills at $0 if 15/8 is unreachable, and one -0.95 bust among ~15 small wins
drives the CI negative correctly. But a floor-level PASS is statistically weak
on the hazard that matters: zero busts in 15 fires bounds the bust rate only at
~3/15 = 20 percent (95 percent, rule of three), against a ~5-7 percent breakeven
hazard at typical fire prices. REQUIRED lattice wording: a PASS at or near the
floor certifies feasibility, NOT safety; unbankable-without-live-read stands,
and the SHADOW is the instrument that bounds the bust hazard (1-3 new movies per
week compounds clusters fast). Month-block guard: with 43 events spanning
Jan-Jun (~6 calendar months) the guard is meaningful, not vacuous; define its
action: if dropping a month leaves clusters below floor MECHANICALLY, the guard
reports FRAGILE (lattice), not NULL.

### E11 (shadow routing: fix the hypothesis swap)

As drafted, H-A's PASS opens a shadow whose content is H-B, a different
hypothesis riding on H-A's evidence: registration-shopping through the shadow
slot. Fix, frozen now: the shadow's BINDING arm tests H-A-LIVE (the same frozen
bound rules at live asks, fresh self-pulled states, live-computed fire-time
A_cap; fired cluster = a movie with >= 1 logged hypothetical fill at the REAL
logged ask). Incorporate v27 E12 BY ITS TERMS, not by date labels: week-13
checkpoint kills only if the shadow cluster-CI UPPER bound < 0 at >= 8 fired
clusters; week-26 binding evaluation at >= 12 fired clusters with CI lower > 0
and LOCO surviving; if under 12 clusters at week 26, ONE extension to week 39,
then binding evaluation, then stop regardless; one shadow ever. H-B runs inside
the same shadow as a REPORTED OVERLAY whose own graduation gate is frozen now
(same E12 numbers on its own fills) or it never graduates. This also composes
with D' (Part 1): D'-pass + H-A-null routes to this same H-A-live shadow, since
the live engine IS the tighter arrival estimator.

### E12 (dropped A7/A11 operational rules; restore)

Missing from the draft lock entirely: (i) A7 live rules: NO FIRE on any event
whose wide-release date is unconfirmed or moving (SEND/SEN is the precedent, now
with the sharper reading that the listing itself died and was replaced); monitor
close_time daily; (ii) A11 parse discipline: media-scorecard-json with JSON-LD
Tomatometer agreement required, disagreement or missing score = no state, no
fire; integrity check per E3; slug re-verification with 3xx following at engine
start; (iii) A11 mandate: SavePageNow + scheduled self-pulls on ALL ACTIVE
events start NOW, regardless of verdict path. All restored verbatim.

### E13 (registration hygiene)

Restate A12 post-adjudication: the registered set is exactly {H-A, D' (if
adopted per Part 1), H-B-shadow-overlay}; closed; no post-data strata; the
ledger counts family #28 once; no third bite. And correct the status line: the
draft claims A1-A12 folded "with ONE documented deviation," but this review
found undocumented deviations at A4 (margin weakened, E5), A6 (slack tier
dropped, E7), A7 (DUN/DUNE misstatement + live rules dropped, E1a/E12), A10
(plain band statement dropped, E9), and A11 (omitted entirely, E12), plus the
walk-forward leak (E4d) and the schema gap (E3). Each is restored or documented
above; the lock's fidelity claim must be rewritten to match reality.

## SUMMARY TABLE

| # | Severity | One line |
|---|---|---|
| E1 | Factual | DUN/DUNE not settled; SEN/SEND is the real same-film pair; SCR expiration_value is a string |
| E2 | Blocking | 20 of 43 settled events unmapped/uncrawled; they are the A_cap priors |
| E3 | Blocking (F11) | Banked vintage schema lacks likedCount/notLikedCount; registered bound currently unimplementable |
| E4 | Blocking (leak) | A_cap row/read conventions pinned; priors must be settled at-or-before the PRINT time |
| E5 | Blocking | A4 margin silently halved; rounding pin 0-R added; per-side worst-case rules frozen |
| E6 | Edit | 0-S at-or-before-close rows only; SCR out; MOR in distribution, out of calibration |
| E7 | Edit | Restore A6 W_max slack tier; reversal check uses fire-time A_cap |
| E8 | Edit | Add 0-E evaluability audit with 30 percent kill line |
| E9 | Edit | Pin print-band wording; restore A10's effective <= ~0.92 statement |
| E10 | Wording | Floor PASS certifies feasibility not safety (rule-of-three hazard bound); month guard action defined |
| E11 | Blocking | Shadow binds on H-A-live; H-B is a reported overlay; E12 terms incorporated explicitly |
| E12 | Edit | Restore A7 live rules and A11 parse/SavePageNow mandates |
| E13 | Hygiene | Restate A12; correct the false single-deviation fidelity claim |

D adjudication: refusal of D* CONFIRMED as specified (degenerate-positive,
routes-to-shadow risk real). D slot salvageable as D' (perfect-arrival bound,
Part 1.2), recommended for adoption; if declined, H-A-only scope with
family-death-on-H-A-death is honest, provided the verdict states the
wall-versus-estimator-width ambiguity and no shadow is ever inferred from an
H-A floor failure.

*Em-dash audit: clean (verified after write).*
