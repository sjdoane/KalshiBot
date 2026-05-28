# v11 Methodology Critic Review (Pre-Phase-2 Gate)

**Round:** 16 (v11)
**Author:** Methodology critic agent
**Date:** 2026-05-27
**Target:** research/v11/01-methodology-lock.md v1
**Source inputs read:** 01-methodology-lock.md, A3-methodology-meta-critique.md,
A1-becker-game-resolution-audit.md, A2-the-odds-api-starter-scout.md,
00-phase1-synthesis.md, A4-track2-wiring-spec.md, CLAUDE.md (Round 15 state),
data/live_trades/state.json (v1 order log shape), data/live_trades/v5_filter_shadow_log.jsonl
(shadow-log row schema), src/kalshi_bot/analysis/metrics.py (verified fee formula).

This document is adversarial. Section A enumerates material flaws that should be
fixed in a v2 lock before Phase 2 fires. Section B confirms what the lock got
right. Final paragraph delivers the verdict.

The critic does not modify the lock. Orchestrator decides whether to revise.

---

## Section A. Material flaws requiring v2 lock revision

### KILLER-1. Kalshi fee formula is misstated and inconsistent with codebase

**Where:** Lock Section 3.5 and Section 6.3.

**Defect:** Section 6.3 of the lock is captioned "Kalshi fee formula (verbatim
from src/kalshi_bot/analysis/metrics.py)" and writes:

```
fee_per_contract(price) = ceil(0.07 * abs(price - 0.5) * 100) / 100
```

The actual verified code in `src/kalshi_bot/analysis/metrics.py` lines 157 to
160 is:

```python
def kalshi_taker_fee_per_contract(price, *, contracts=1):
    cents = np.ceil(7.0 * contracts * price * (1.0 - price))
    return float(cents / 100.0)
```

The two functions diverge because `|p - 0.5|` is V-shaped at 0.5 while `p(1-p)`
is inverted-parabola. Numerically, at the four reference prices that v11 will
hit on game-resolution markets:

| Price | Lock formula (cents) | Actual code (cents) | Delta |
|---|---|---|---|
| 0.55 | ceil(0.35) = 1 | ceil(1.73) = 2 | -1 |
| 0.70 | ceil(1.40) = 2 | ceil(1.47) = 2 | 0 |
| 0.80 | ceil(2.10) = 3 | ceil(1.12) = 2 | +1 |
| 0.90 | ceil(2.80) = 3 | ceil(0.63) = 1 | +2 |

The lock's worked example in Section 3.5 ("at modal_execution_price = 0.55, fee
= 0.0035, haircut = 0.02, target = 0.0335") uses the WRONG formula. With the
codebase-verified formula, fee at 0.55 is 0.0173, not 0.0035, and target rises
from 3.35c to 4.73c. The G_F8 gate becomes ~1.4c stricter at the modal price
and the worked example understates the cost floor by ~40%.

**Why this is KILLER:** the G_F8 cost-floor target is the load-bearing
threshold for the entire SHIP decision. Section 3.5 also explicitly fails the
Phase 2 derivation rule: the recipe is `kalshi_fee + DETERMINISTIC_HAIRCUT +
0.01`, and `kalshi_fee` is computed by Phase 2 code that does not exist yet
but is supposed to follow Section 6.3 "verbatim from metrics.py". Phase 2
script writers will either:
(a) trust Section 6.3 and ship a wrong fee, or
(b) trust the metrics.py verified formula and silently diverge from the lock.
Either path corrupts G_F8.

**Recommended v2 fix:** rewrite both Section 3.5 and Section 6.3 to use
`fee_per_contract(price) = ceil(7.0 * price * (1 - price)) / 100`. Re-derive
the worked example at price 0.55 (yields 1.73c fee, ~3c+ haircut, plus 1c
buffer = ~5.7c target). Add an executable assertion in Phase 2 Step 1 code
that imports `kalshi_taker_fee_per_contract` from the codebase rather than
re-implementing the formula in the v11 script.

---

### KILLER-2. 50/50 chronological split is severely sport-imbalanced

**Where:** Lock Section 2 (Splits).

**Defect:** the lock defines dev = [2024-10-01, 2025-05-31] and val =
[2025-06-01, 2025-11-30]. Per A1's date ranges:

| Sport | Becker date range | Dev split markets | Val split markets | Dev share |
|---|---|---|---|---|
| KXMLBGAME | 2025-04-16 to 2025-10-31 | Apr-May 2025 (1.5 mo) | Jun-Oct 2025 (5 mo) | ~25% |
| KXNBAGAME | 2025-04-15 to 2025-11-22 | Apr-May 2025 playoffs | Jun-Nov 2025 | ~20% to 40% |
| KXNFLGAME | 2025-07-31 to 2025-11-20 | ZERO markets | All 428 markets | 0% |

NFL has zero dev events. The lock's pilot ("first 100 events when sorted by
(sport, ticker, close_time)") will draw zero NFL events; sigma, X, Y, and the
haircut are calibrated on MLB+NBA only. Then G_F3 demands "each contributing
sport to pass independently" on validation with NFL contributing 428 of ~5500
markets (~8% by event count, falling below the 20% gating floor but still in
the universe). The strategy is calibrated on two sports and then asked to
clear a per-sport gate on a third sport whose parameters were not derived
from its own data.

For MLB, the situation is the inverse problem: the season-progression effect
is well documented (V3-B1, V4-H denied series). Calibrating X and Y on
April-May early-season MLB and applying them to June-October peak-season MLB
embeds a structural regime change directly into the train/test gap.

**Why this is KILLER:** the chronological split was supposed to provide
clean OOS. Instead it embeds season-phase mismatch into the OOS test by
sport. G_F10 LOCO-by-sport runs the strategy with each sport dropped, but
the validation per-sport gate is already calibrated on a non-representative
dev sample. F3 (gate-regime mismatch by sport) is therefore not actually
defended.

**Recommended v2 fix:** EITHER (a) move the split to a calendar boundary that
gives each sport at least one full in-season window in each half (e.g., split
each sport at its own median close_time and pool), OR (b) drop the per-sport
gate in G_F3 to "any 2 sports clear" since NFL has zero dev calibration data,
OR (c) explicitly compute X, Y, and haircut on a per-sport basis and tabulate
which sports have enough dev events to support per-sport calibration (a
sport-stratified pilot, not a global one). Option (c) is the most defensible.

---

### KILLER-3. Pilot computes sigma using the haircut the pilot is also computing

**Where:** Lock Section 3.1 plus Section 3.4.

**Defect:** Section 3.1 says sigma_per_event is "Computed on the 100-event
pilot using the F4-Option-B execution formula with the pilot's
DETERMINISTIC_HAIRCUT (which is also being computed in this pilot; the two
computations are consistent because the haircut is set on the pilot, then
applied to the pilot to compute sigma)."

Self-referential. The haircut is the 75th-percentile spread on snapshots
observed in the same 100 events. Per-event net P&L = `realized_outcome -
trade_print_mid - haircut - fee`. Sigma is then bootstrapped from those
100 per-event P&Ls. Two distinct biases:

1. **Variance underestimation by anti-self-fit.** The haircut is set so that
   ~25 of the 100 events have larger snapshot spreads than the haircut; for
   those events the F4-Option-B formula understates execution cost relative
   to what those events would have cost a real taker. The haircut is fit to
   the pilot, then applied to the pilot. This is in-sample evaluation. True
   OOS sigma on the validation split will be wider.

2. **n_required underestimation.** G_F2 computes `n_required = (2 * 1.96 *
   sigma / 0.02)^2`. If sigma is underestimated by 20% (plausible from
   in-sample shrinkage at n=100), n_required is underestimated by ~36%.
   The strategy could pass G_F2 at n=200 when honest n_required is 270.

The lock acknowledges this as "Cross-fitting risk acknowledged but tolerated
because the pilot sample is purged before the validation backtest." Purging
the pilot from the validation backtest does NOT fix the bias; the bias is in
sigma itself, which is then used to set the validation-gate sample-size
requirement. The pilot is calibrating a parameter that the validation gate
depends on.

**Why this is KILLER:** the F2 power calculation is the only quantitative
sample-size defense in the lock. If n_required is biased downward, the
strategy mechanically clears G_F2 on insufficient n.

**Recommended v2 fix:** split the pilot into two non-overlapping halves of
50 events each. Compute the haircut on Pilot-A. Then compute sigma on
Pilot-B using the Pilot-A haircut. This is a one-step cross-fit and produces
an unbiased sigma estimator at the cost of statistical efficiency (sigma
estimated on 50 events instead of 100). Alternatively, replace the in-sample
sigma estimator with an OOS sigma estimator on a held-out sliver of the dev
split disjoint from the pilot.

---

### IMPORTANT-1. F8 fee-target derivation re-introduces a borrowed "2c MDE"

**Where:** Lock Section 4 G_F2, "target_MDE = 0.02 dollars per contract net."

**Defect:** Section 7 (anti-pattern bans) item (c) reads: "Borrow a numerical
gate threshold from any prior round's result (F8 defense; the +12.47pp,
+0.014, +3.58pp, +0.208 numbers from prior rounds are explicitly banned from
v11's gate)." The lock then uses target_MDE = 2c per contract. A3 sourced
this 2c from "the Becker tight-spread historical-baseline noise floor
surfaced in Round 15 (1c MM-saturated spreads)" per CLAUDE.md memory.

Round 15 b/c was a MAKER edge analysis on tight-spread Becker markets. v11
is a TAKER strategy on game-resolution moneyline markets. The 1c MM-saturated
spread number described maker fills, not taker breakeven. The 2c MDE is a
prior-round empirical number applied to a different regime; this is the
exact F8 anti-pattern.

**Why this is IMPORTANT (not KILLER):** the gate itself (G_F8 strict cost
floor with CI lower bound above fee+haircut+1c) is the operationally binding
test. G_F2 target_MDE only sets the power calculation, which determines
n_required. If 2c is too generous (i.e., the true detectable target on
takers is smaller because spreads are wider), n_required is too small. The
strategy could clear G_F2 yet fail the live spot-check.

**Recommended v2 fix:** derive target_MDE from G_F8's own cost-floor formula:
target_MDE = G_F8 threshold = `fee + DETERMINISTIC_HAIRCUT + 1c`, computed
deterministically from pilot data after the haircut is frozen. The two
constants should reference the same number, not two different ones.

---

### IMPORTANT-2. G_F11 spot-check window is sport-asymmetric

**Where:** Lock Section 4 G_F11 Part B.

**Defect:** the 30-day forward spot-check from late May 2026 runs through
late June 2026. Per sport seasonality:

- KXMLBGAME: in regular season throughout. ~30 games per day, plenty of
  signal-fires.
- KXNBAGAME: 2025-26 season ended in June 2026 (NBA Finals); by late June
  the next season has not started. Few or zero qualifying events.
- KXNFLGAME: regular season starts September. ZERO qualifying events in the
  spot-check window.

The G_F11 Part B gate threshold (median(gap_live) <= 1c, n >= 30) will be
hit on MLB data only. The haircut was calibrated on (mostly) dev-split MLB
data already. The spot-check is therefore validating a single sport against
its own near-distribution. NFL and NBA are not spot-checked at all even
though the backtest's verdict allegedly depends on the haircut applying to
all three.

**Why this is IMPORTANT (not KILLER):** the spot-check is Part B of G_F11
and is OUT-OF-SESSION. The session backtest fires regardless. But the SHIP
verdict is gated on Part B passing, so a single-sport spot-check is being
treated as multi-sport evidence.

**Recommended v2 fix:** v2 should require either (a) the spot-check window
be extended to span at least one full in-season window of each sport in
scope (which means late August 2026 at earliest to reach NFL), OR (b) the
G_F11 Part B gate be applied PER SPORT and the SHIP verdict gated on each
sport's haircut surviving its own forward check, OR (c) the lock explicitly
acknowledges that Part B is an MLB-only spot-check and NFL/NBA stay in
PROVISIONAL-SHIP-PENDING-SPOTCHECK indefinitely until their season returns.

---

### IMPORTANT-3. Track 2 v1_decision rule conflates four operator-distinct outcomes

**Where:** Lock Section 9.4.

**Defect:** the lock's mapping for `v1_decision` is "True if v1 placed an
order on `ticker` within +/- 5 minutes of `timestamp`, else False." Inspection
of `data/live_trades/state.json` reveals v1 records:

```
placed_ts: 2026-05-25T03:29:16.458Z
acked_ts: 2026-05-25T03:29:16.554Z
filled_ts: null
filled_price_cents: null
filled_count: 0
cancelled_ts: null
status: live_resting
```

A v1 "order placed" can resolve into four operator-distinct outcomes:

1. Placed, acked, filled (count > 0 at fill price). The trade actually happened.
2. Placed, acked, never filled, never cancelled, expired at resolution. Resting
   order made it to settlement at filled_count=0. No P&L.
3. Placed, acked, cancelled by v1 (kill-trigger, time-in-force, manual). No P&L.
4. Placed, REJECTED by Kalshi before ack. Order never lived.

Joining `v1_decision = True` on ALL of these treats "v1 considered firing"
identically to "v1 actually traded". For the cross-table to be useful as a
filter-decision-vs-actual-trade comparison, only outcome 1 should count.

The shadow log row schema confirms the ambiguity. Inspection of
`v5_filter_shadow_log.jsonl` line 1 shows `should_trade: true, reason:
"no_match"`. The filter said go but on a market where Polymarket lookup
missed. v1 may or may not have ended up firing that ticker. If the join
script records `v1_decision=True` whenever v1 placed an order within 5
minutes, and v1 cancelled the order 30 seconds later, the cross-table
falsely reports filter+v1 agreement.

**Why this is IMPORTANT (not KILLER):** Track 2 is a logging tool, not a
ship-decision input for Track 1. But the lock's Section 9.7 "Track 2 SHIPS
when" includes "Output schema validates against the prompt's spec", and the
prompt's spec is `v1_decision`. If `v1_decision` is operationally meaningless
because it includes all four outcome classes, Track 2's output is decorative,
not analytical.

**Recommended v2 fix:** redefine v1_decision as a 4-state enum
(`placed_and_filled`, `placed_and_expired`, `placed_and_cancelled`,
`placed_and_rejected`) derived from state.json fields (filled_ts,
filled_count, cancelled_ts, acked_ts, resolution_ts). The cross-table is
then operationally useful. A boolean projection becomes `v1_decision ==
'placed_and_filled'` if a downstream consumer wants binary; encode at the
higher precision and let the consumer collapse.

---

### IMPORTANT-4. G_F1 coverage gate measured on pilot, not full universe

**Where:** Lock Section 4 G_F1.

**Defect:** G_F1 requires "Becker-to-odds-api timestamp join coverage rate
>= 60% across all pilot events." The pilot is 100 events. Binomial standard
error at p=0.6, n=100 is `sqrt(0.6*0.4/100) = 0.049` or ~5pp. The 60%
threshold could be passed at a true coverage rate of 50% (Z = +2.0, p~0.02)
or failed at a true rate of 65% (Z = -1.0, p~0.16). The gate's discriminative
power is weak at n=100.

Worse, the pilot is "the first 100 events when sorted by (sport, ticker,
close_time)". Per the KILLER-2 finding, the first 100 events are mostly
MLB and NBA from April-May 2025. The-odds-api coverage by sport-season is
not uniform; A2 specifically flagged that "MMA and boxing are old listings,
so this should pass, but confirm with one test call per sport." If
the-odds-api has different coverage on early-season MLB vs peak-season NFL,
the pilot's coverage rate does not predict the validation universe's
coverage rate.

**Why this is IMPORTANT (not KILLER):** if the full-universe coverage rate
is below 60%, the backtest can still complete; G_F1 just fails. But because
the gate is checked at pilot stage (per Section 3.4 + 4), a borderline pass
could mask a large coverage hole on the validation set.

**Recommended v2 fix:** G_F1 coverage gate runs TWICE: once at pilot stage
(at n=100, threshold 50% with 10pp Wilson buffer) and once at full Phase 2
join (at the full qualified universe, threshold 60% strict). Both must pass.

---

### IMPORTANT-5. G_F11 Part B asymmetric tolerance allows over-haircut to pass

**Where:** Lock Section 4 G_F11 Part B.

**Defect:** the formula is `gap_live = live_yes_ask - (trade_print_mid +
DETERMINISTIC_HAIRCUT)` and the gate passes if `median(gap_live) <= 0.01`.
This is a one-sided test. Two cases:

1. Live ask is HIGHER than the proxy (live_ask > trade_print_mid + haircut).
   Then gap_live > 0. If median > 1c, the backtest UNDERESTIMATED execution
   cost; gate fails. Correct.

2. Live ask is LOWER than the proxy (live_ask < trade_print_mid + haircut).
   Then gap_live < 0. Median is negative and trivially <= 0.01. Gate passes.
   But this means the backtest OVERESTIMATED execution cost. The backtest's
   net P&L is biased downward. The strategy is BETTER than the backtest
   says, but the gate doesn't catch the over-haircut because it doesn't
   test it.

This is benign from a phantom-prevention standpoint (over-haircut is
conservative). But it means a backtest that BARELY passes G_F8 at the
overstated haircut would, with a corrected haircut, pass G_F8 by a much
larger margin. The lock's Section 7(e) bans "Apply DETERMINISTIC_HAIRCUT
computed on validation events" but does not prohibit retroactively correcting
the haircut downward when Part B reveals over-haircut.

**Why this is IMPORTANT (not KILLER):** the asymmetric tolerance is
conservative on phantom risk (the load-bearing concern). But it is a
"silent" Type II error for the strategy itself; v11 may declare PARTIAL
when SHIP is warranted, with no mechanism to recover. Operator may walk
away from a real edge.

**Recommended v2 fix:** change the G_F11 Part B test to a two-sided
`abs(median(gap_live)) <= 0.01`. If gap_live is centered on -0.5c (haircut
overshot by 50 bp on average), the SHIP verdict can still proceed but the
operator is informed. If gap_live is centered on +1.5c (haircut undershot),
SHIP is held.

---

### IMPORTANT-6. G_F3 per-sport gate ambiguous on NFL given KILLER-2

**Where:** Lock Section 4 G_F3.

**Defect:** "For each sport in {KXMLBGAME, KXNBAGAME, KXNFLGAME} contributing
>= 20% of validation qualified events." Per A1 numbers: validation split is
~5,500 markets across 3 sports. NFL has 428 markets total (entire season in
validation, per KILLER-2). 428 / 5500 = 7.8%. NFL falls below the 20% floor.
Lock says "Sports below the 20% contribution floor are reported but not
gated individually" per A3 inheritance.

So G_F3 in practice gates on MLB + NBA only. The strategy can SHIP on
2-sport robustness while NFL is dropped from the gate but not from the
verdict. Section 4 G_F3 then says "PASS if all 3 sports clear the per-sport
gate, with at least n=50 qualified events per sport (else degrade to
2-sport per-sport evaluation and treat as PARTIAL)". This contradicts the
20% floor language; the n=50 floor lets NFL contribute as long as 50 events
qualify (and 428 markets certainly produces > 50 qualified events post-join).

So which floor applies? 20% contribution OR n=50? Lock should pick one.

**Why this is IMPORTANT (not KILLER):** the two-rule ambiguity is procedurally
fixable but creates wiggle room for post-hoc selection ("NFL had only 17%
contribution but n=83, so it didn't gate; we got 2/3 sports to pass, PARTIAL
verdict but signal robust"). This is exactly the kind of post-hoc rationalizing
that the lock document was supposed to prevent.

**Recommended v2 fix:** pick one rule. Recommended: "at least 2 of 3 sports
must have >= 50 qualified events AND each must clear the per-sport CI
threshold; sports with < 50 events are reported but not gated; verdict is
PARTIAL if all three have < 50, SHIP only if 2 of 3 with >= 50 pass." This
encodes the 2-sport-minimum without leaving room for borderline
re-interpretation.

---

### IMPORTANT-7. G_F10 LOCO-by-bookmaker has no signal-sourcing rule

**Where:** Lock Section 4 G_F10.

**Defect:** the bookmaker-out LOCO requires identifying which bookmaker
"sourced" each signal. In multi-bookmaker reality, on a single game, all
three of DraftKings, FanDuel, and Pinnacle may move similarly. The lock's
Section 3.2 X-derivation says X is computed using "the most-liquid bookmaker
for the matched game", implying one bookmaker per game. But Section 4 G_F10
says "remove all events for which the sportsbook signal was sourced from
that bookmaker" without defining the sourcing rule.

If sourcing is "most-liquid", LOCO-by-bookmaker removes events where
DraftKings was most liquid; but if FanDuel and Pinnacle ALSO moved on those
games, the signal carried by them is silently dropped along with the
DraftKings indicator. This conflates "removing the bookmaker" with "removing
the games the bookmaker was assigned to".

**Why this is IMPORTANT (not KILLER):** LOCO-by-bookmaker is meant to test
robustness to a single bookmaker carrying the signal. If sourcing is
deterministic-per-game (most-liquid), the test is degenerate (it just drops
games, doesn't really test cross-book robustness).

**Recommended v2 fix:** either (a) redefine LOCO-by-bookmaker as
"signal-fires-when-only-that-bookmaker-moved-above-X-and-others-did-not"
(true LOCO), or (b) clarify the X-derivation uses the MEDIAN move across
all available bookmakers per game and LOCO-by-bookmaker excludes that
bookmaker from the median (proper data-leave-out), or (c) drop
LOCO-by-bookmaker as the operationally unsupported test it is and rely on
LOCO-by-sport alone.

---

### IMPORTANT-8. F6 "single pre-registered cell" is actually 4 binding tests + 9 descriptive

**Where:** Lock Section 3.6 and G_F6.

**Defect:** Section 3.6 says "this is a single primary cell. Bonferroni
correction is NOT applied because we are pre-registering ONE cell, not
searching across 144." But the lock then has:

- G_F4: pooled mean per-trade net P&L test (1 hypothesis)
- G_F3: per-sport test (3 hypotheses if 3 sports)
- G_F8: cost-floor test (1 hypothesis, but using same data as G_F4)
- G_F9: side-symmetry test (2 hypotheses, one per side)
- G_F5: random-side comparator + anti-signal comparator (2 hypotheses)
- G_F10: 3 sport-LOCO + up to 3 bookmaker-LOCO (up to 6 hypotheses)

Plus "9 strata are reported descriptively". Descriptive reports in a verdict
document are read by humans who can implicitly multi-test against them; A3
acknowledged this.

The "single cell" claim is true only for the (X, Y) tuple at the threshold-
derivation layer. At the gate-evaluation layer, the lock fires ~15 hypothesis
tests. Each is at alpha 0.05 uncorrected. Under the null, the family-wise
Type-I rate is non-trivial.

A3 said "Bonferroni for K <= 20 (transparent)". The lock chose option (i)
"single best-cell selection rule" but the operational reality is more like
option (ii) "any cell passes" since the gate is a conjunction with each
sub-gate independently testable.

**Why this is IMPORTANT (not KILLER):** the verdict structure is conjunctive
(ALL must pass), so the Type-I error on the GATE is actually LOWER than 0.05,
not higher. A conjunctive composite gate naturally controls false-positive
rate downward (each must pass under the null is unlikely). The flaw is in the
LOCO and per-sport SUB-tests, where the lock allows "PARTIAL on 9 or 10 of 11"
verdicts. PARTIAL is positive enough to keep the strategy alive for further
testing, and PARTIAL on 9-of-11 is exactly where a multiple-comparison-naive
gate produces a false positive.

**Recommended v2 fix:** make the verdict map explicit about multiple
comparisons. "10 of 11 pass" should require the failing gate to be
non-load-bearing (e.g., a single LOCO arm failing on a low-n sport). The
PARTIAL verdict should require Bonferroni correction at the alpha level of
the failing gate. Alternatively, just accept the conjunctive structure and
note in the lock that the verdict map already implicitly multi-test corrects
by requiring conjunction.

---

### IMPORTANT-9. Pilot size n=100 has no theoretical derivation

**Where:** Lock Section 3 (pilot stage).

**Defect:** the pilot is 100 events with no derivation. A3 used 100 as a
placeholder ("100-event Becker pilot"). v11 borrowed it. The choice of 100
controls:

- Pilot sigma precision: at n=100, sigma SE is ~7% of true sigma
- X median precision: at n=100, median SE is ~`1.2533 * sigma_xmove / sqrt(100)` = ~13%
- Y median precision (conditional median given X-fire): the conditional set
  is smaller than 100; if ~50 events have X above median, conditional Y is
  estimated on n=50 with median SE ~20%
- Haircut percentile (75th-pct) precision: at n=100 events times multiple
  snapshots per event, the 75th percentile of snapshot-gap is reasonably
  precise IF snapshot coverage is ~50% (Section 3.4); but the 75th-pct
  itself has ~`0.75 * 0.25 / sqrt(n_snapshots)` precision

n=100 was a round number. It is not a theory-derived sample size. By F8
spirit, the lock should EITHER derive 100 from a power calculation on the
pilot's quantities OR accept that 100 is a convention.

**Why this is IMPORTANT (not KILLER):** pilot n=100 is the LEAST load-bearing
F8-borrow concern; it is methodological convention. But if v11's verdict
hinges on a 4c gate that was set by a haircut computed on 100 events, the
robustness of the gate to pilot n is itself a research question.

**Recommended v2 fix:** add a sensitivity check at Phase 2 Step 3: re-derive
the haircut with the FIRST 50 events and the FIRST 200 events (if the latter
fits within the pilot purge constraint). If the haircut changes by more than
0.5c across n in {50, 100, 200}, the haircut is undersampled and v11 should
expand the pilot. This is the cheapest pilot-stability check available.

---

## Section B. Confirmations

The lock got the following right and these should remain in v2:

1. **Track 1 hypothesis is locked verbatim with deterministic-derivation rule
   for X and Y.** Section 3.6's "single pre-registered (X, Y, target) tuple"
   approach correctly avoids the 144-cell grid that A3 flagged as the F6
   risk. The medians-based derivation is theory-anchored (the median is a
   distribution-shape-derived breakpoint, not a P&L-fitted threshold).

2. **Section 3.4 escalation path is well-designed.** "If
   pilot_snapshot_coverage_rate < 0.50, the methodology lock v1 is INVALID
   at Phase 2 stage and v2 must be authored before continuing" is the right
   way to handle the F4 Option B failure mode. It blocks the backtest from
   firing rather than silently degrading to Option A.

3. **G_F7 buffer assertion is well-specified.** The 60-second buffer plus
   loader assertion with explicit assertion text is the strictest form of
   F7 defense; this is correct.

4. **G_F11 Part A is correctly designed.** The development-split-purge plus
   pilot-frozen-haircut is the right operational implementation of A3's
   recommendation. The structural separation between pilot calibration and
   validation backtest is intact (modulo the cross-fit risk addressed in
   KILLER-3, which is a sigma-estimation issue, not a haircut-leak issue).

5. **Section 7 anti-pattern bans are comprehensive and well-aligned with
   prior rounds' failure modes.** The list correctly bans the W2 +5.98c
   phantom pattern, the v7-B stale-mid pattern, the v9 +0.014 borrow
   pattern, the F6 grid search, the F11 validation-haircut leak, the F9
   pooled-without-symmetry pattern, the F10 row-bootstrap-on-day-correlated
   pattern, and the v8-A premature-capital-deploy pattern. This is the
   strongest section of the lock.

6. **Validation split is read once at gate time.** Section 2's "The
   validation split is read once at gate time and never again before the
   verdict fires" is the load-bearing methodological commitment. This is
   the single most important methodology constraint and is correctly stated.

7. **Block bootstrap at block_size = 1 day for G_F10.** Correct response to
   the cross-game intra-day correlation that breaks row-bootstrap. Inherited
   from A3 correctly.

8. **Track 2 limits damage by being read-only on v1's production code.**
   Section 9.3 commitment to "Read-only with respect to
   v5_filter_shadow_log.jsonl and v1 order log" is the right safety
   constraint. Section 9.7 includes the regression check (522 tests still
   pass).

9. **The phase 2 sequencing is correct.** Step 1 (Becker side, no external
   spend) blocking Step 2 (the-odds-api purchase) lets the operator confirm
   Becker-side feasibility (G_F7 assertion clearing, pilot quantities looking
   sane) before committing $59 external.

10. **Verdict mapping is honest.** Section 5 distinguishes SHIP-shadow-mode
    from PROVISIONAL-SHIP from PARTIAL from NULL with clear thresholds. The
    "All 11 gates pass except G_F11 Part B is incomplete at the deadline:
    PROVISIONAL-SHIP-PENDING-SPOTCHECK, no capital" is correctly designed
    to handle the 30-day forward delay without falsely upgrading the
    verdict.

---

## Verdict

**v2 REQUIRED.** Three KILLER findings (fee formula mismatch with codebase;
50/50 chronological split is sport-imbalanced with NFL having zero dev
events; pilot sigma calibration is self-referential through the haircut)
each independently invalidate the load-bearing G_F2 power calculation and
the G_F8 cost-floor target. Any single one would corrupt the SHIP/PARTIAL/NULL
boundary; together they make the v1 lock unfit to gate Phase 2. v2 must
re-derive Section 3.5 + 6.3 fee formula to match metrics.py, re-design the
split so each sport has dev calibration data, and split the pilot into
non-overlapping calibration and sigma-estimation halves before Phase 2 Step
1 fires. The seven IMPORTANT findings should also be addressed in v2 to
avoid procedural ambiguity at gate-evaluation time; the most operationally
costly of these are the G_F11 spot-check seasonality (IMPORTANT-2) and the
Track 2 v1_decision conflation (IMPORTANT-3) because both produce silently
wrong outputs that would survive Phase 2.

---

*Anti-em-dash and anti-en-dash verification: this document was written
without U+2014 or U+2013 throughout. Verified by ASCII-only character set
in source.*
