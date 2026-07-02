# v27 VERDICT CRITIC: adversarial audit of H1 NULL + D1 FAMILY-DEATH

**Date:** 2026-07-02. Role: attack the inference. Question: is the family death
genuine, or manufactured by implementation choices? Inputs read:
02-methodology-lock.md (incl. AMENDMENTS v2), 03-methodology-critic.md,
data/v27/backtest_results.json, data/v27/backtest_results_h1.json,
data/v27/audit_0b_decision.json, scripts/v27/tsa_backtest.py (line-level).
Evidence base: scripts/v27/verdict_critic_diag.py, a single-pass reimplementation
of the locked funnel that reproduces the shipped fire sets EXACTLY
(491 / 535 / 489 / 490 / 507 across the five modes, means to full float
precision), then computes post-verdict counterfactuals. Output at
data/v27/verdict_critic_diag.json. These diagnostics are inference audits,
NOT gate inputs; nothing below can rescue the locked outcome and nothing
below is offered as a route.

## VERDICT: DEATH-CONFIRMED

The family death is genuine. Every candidate false-death vector was quantified
and each is either absent from the implementation, immaterial (< 1pp), or
conservative in the pro-PASS direction. The strongest possible repair of the
one real implementation subtlety found (cross-mode joint gating) moves the
best D1 mean from -0.6pp to +0.05pp against an 8pp gate. Details per vector.

## 1. Friction vs signal: the ceiling is below the friction floor

Exact friction on the fired sets (haircut 3c + worst-case quadratic fee):
mean 4.62 to 4.63pp across all modes. Frictionless means (haircut 0, fee 0,
same fires, cluster-bootstrap CI seed 27):

| Mode | Net mean (shipped) | Frictionless mean | Frictionless CI |
|---|---|---|---|
| H1 | -2.50pp | +2.13pp | [-4.44, +8.80] |
| control | -8.04pp | -3.46pp | (not computed; point estimate negative even frictionless) |
| D1 beta 0.3 | -3.27pp | +1.36pp | [-4.46, +7.44] |
| D1 beta 0.5 | -0.42pp | +4.20pp | [-1.54, +10.23] |
| D1 beta 1.0 | -0.57pp | +4.05pp | [-2.64, +11.23] |

The decisive number: PERFECT weekend information, at ZERO frictions, on its
own fired set, yields at most +4.2pp gross with a CI that still straddles
zero. That is roughly half the locked 8pp net bar before a single cent of
cost is charged. The death is therefore NOT friction-driven: no fee schedule,
no maker-side migration, no haircut relaxation turns a +4pp-gross
zero-straddling ceiling into an 8pp+ positive-CI channel. The correct verdict
wording is "channel ceiling below the retail friction floor AND below the
locked bar even frictionless," not merely "channel below retail frictions."
The channel is not literally zero (point estimates +4pp gross at betas 0.5
and 1.0, and D1 beats H1 by about +2pp gross on matched machinery), it is
small, statistically indistinguishable from zero, and un-bankable at any
friction level tested or hypothetical.

## 2. E10 conservatism: NOT PRESENT in the implementation; the attack dissolves

The critic's E10 worry (D1 diluted by reusing H1's too-wide walk-forward
errors) does not apply to the shipped code. `Errors.__init__` builds
per-mode distributions and `evaluate()` reads `errors.dist(mode, ...)` with
mode = "d1@beta": D1's P_model is calibrated against its OWN perfect-info
walk-forward errors, exactly as AMENDMENTS v2 E9/E10 registered. The error
supports confirm it: bucket {3} h1 support [-0.224, +0.142] vs d1@1.0
[-0.092, +0.186] (millions of daily-average passengers); D1's bands are
roughly half as wide on the left tail. So D1 received the BENEFIT of
properly narrow, properly centered error distributions and still failed the
gate by 8 to 11pp of mean. A "properly-calibrated D1" is what ran. There is
no wider-error dilution left to blame.

The 0b reconciliation quantifies what killed it instead. At fire time the
H1 model claimed a mean conditional net edge of +23.5pp (audit_0b_decision.json,
reproduced at +23.52pp on the shipped 491 fires). Realized: -2.50pp net,
+2.13pp gross. Claimed gross edge was 23.5 + 4.6 = 28.2pp; captured gross was
2.1pp. Capture ratio 7.6 percent: roughly 92 percent of every model-market
disagreement at fire time was model error, not market error. That 26pp gap IS
the market-already-priced-it evidence, and it is the single fact the
FINAL-VERDICT doc should lead with.

## 3. False-null generators in the machinery: all checked, all immaterial

- **Cross-mode joint gating (the one real implementation subtlety).**
  `evaluate()` computes all five modes' probabilities per print and discards
  the print for the SIGNAL mode if ANY mode fails min-errors or the E6
  support rule. This is not in the lock text and is exactly the shape that
  could manufacture a false death (H1 out-of-support in meltdown weeks
  vetoing D1's best fires). Quantified by independent-gating counterfactual:
  D1 gains only 20 to 30 prints (beta 1.0: 507 -> 525 fires, 57 -> 58
  clusters), and the independent D1 beta 1.0 mean is +0.05pp net,
  CI [-6.67, +7.30]; frictionless +4.66pp, CI [-2.05, +11.92]. Still fails
  the 8pp mean gate by a factor of two frictionless and by two orders of
  magnitude net. The vector is real in principle, quantified, and immaterial.
- **E6 support rule deleting perfect-info gems.** Directly contradicted by
  the disrupted-week record: D1 FIRED in force in disruption weeks (146
  joint / 154 independent fires at beta 1.0, covering ALL 17 disrupted
  clusters, vs H1's 128), so the support rule did not fence D1 out of its
  target territory. And those perfect-info disrupted-week fires netted
  approximately zero: beta 1.0 mean -0.61pp joint / +1.02pp independent,
  beta 0.5 mean -1.93pp. The market had the weekend cancellations priced
  inside the fire window. Contrast H1 disrupted-week mean -10.9pp and
  control -15.9pp: information helps exactly where it should, and even
  perfect information only climbs back to zero.
- **The 0.08 threshold.** Chosen pre-lock per the A11 rule (projected
  conditional edge 23.5pp >= 8pp at 0.08), outcome-blind, recorded in
  audit_0b_decision.json. At 0.12 the projected conditional edge was HIGHER
  (28.2pp), so no threshold in the registered candidate set changes the
  conclusion that conditional edge was a mirage; the sub-5pp-edge fraction
  was 8.4 percent, so the fires were not a thin-edge mass either.
- **The [0.05, 0.95] band and evaluability.** The funnel (39,639 in-band,
  21,256 unevaluable, 9,400 errs/no-support, 491 fired) shows evaluability
  is the dominant restriction, but it restricts SCOPE, not sign: it is
  outcome-blind (A7 snapshot proof at print time) and identical across H1,
  control, and D1, so it cannot generate a differential false null on the
  D1 bound. The 26 percent of clusters with no evaluable fire-candidate
  remain untested territory, correctly named in the lock.
- **Error-build training convention.** Signed walk-forward error means are
  +0.3 to +1.7pp of weekly average (actual above prediction, the expected
  trailing-median lag on a growing series), but the empirical-distribution
  method feeds that bias INTO P_model, self-correcting the level. No
  systematic fire-side bias survives: H1 fired 281 YES / 210 NO.

## 4. Control worse than H1 (-8.0 vs -2.5): ordering is informative, not artifactual

The candidate artifact story (baseline median lags trend, all models fire NO
too often, all lose on NO) is refuted by the side decomposition: fires are
majority YES in every mode, and the LOSSES are concentrated on the YES side
(H1 YES mean -4.6pp vs NO +0.4pp; control loses BOTH sides, YES -8.8pp and
NO -7.2pp). A shared directional bias would lose on one side and win on the
other; losing on both sides of the control and on the model-overconfident
YES side of H1 is the signature of a market that is simply closer to the
truth than either model wherever they disagree. The ordering therefore means
exactly what it appears to mean: the schedule term adds about 5.5pp of real
information relative to pure seasonality (and the D1 perfect-info term adds
about 2pp more, shifting fires toward NO, the side that at least breaks
even), but the market sits ahead of the entire model family. This is a clean
monotone information ladder (control < H1 < D1 < market) and it is the
strongest structural evidence that the family, not the implementation, is
dead.

## 5. Lattice fidelity: VERIFIED, with three scope caveats

- **H1 = NULL is the correct locked class.** Power floor cleared (491 >= 40
  fires, 57 >= 30 clusters), binding CI lower -0.090 <= 0, control does NOT
  clear its own floor-plus-CI (its CI is fully negative), so the plain NULL
  branch, not the seasonality branch, is correct. LOCO and month-block are
  reported and consistent (both negative-leaning).
- **D1 = FAMILY-DEATH is the correct locked class.** All three frozen betas
  clear the 20/8 power floors and all three fail the A2 gate (mean >= 8pp
  AND CI lower > 0): means -3.3 / -0.4 / -0.6pp, all CIs straddle zero. E9
  requires ALL THREE to fail for death; all three failed, and not by a
  whisker: the best beta misses the mean gate by 8.4pp. Per E11 the gate was
  monster-signal-only BY DESIGN; the miss is a mean miss, not a CI
  technicality at the floor.
- **A4 ordering firewall.** backtest_results_h1.json exists and contains the
  complete H1/control block only, written before any D1 P&L; audit_0b was
  outcome-blind (model-conditional quantities only, no settlement P&L).
  Verified in code: the D1 pass runs after the H1 json dump.
- **No post-hoc strata consulted in the shipped verdict.** Every reported
  block (control, LOCO, month-block, reported-matched, disrupted 5c
  sensitivity) is pre-registered in the lock. The post-hoc numbers in THIS
  document were computed after and outside the verdict, by the critic, for
  inference-audit purposes only.
- Caveats to carry into FINAL-VERDICT: (a) the tested universe is
  strike_type "greater" markets only; between-type KXTSAW brackets were
  never fired on, so the death claim's scope is threshold-style markets;
  (b) the Errors builder's training as-of uses fixed 17:00 UTC rather than
  ET-aware noon (one hour late in EDT for TRAINING rows only; fire-time
  evaluability uses true snapshot first_seen, so no leak; immaterial but an
  E15g deviation to note); (c) the cross-mode joint gating of section 3 is
  an unlocked implementation choice, now quantified as immaterial.

## 6. Required verdict wording (FINAL-VERDICT doc)

H1: "NULL under the locked A10 gate. 491 fires / 57 event clusters cleared
the power floor; binding cluster CI [-9.0pp, +4.2pp] includes zero (mean
-2.5pp net). The control (no schedule term) fired 535 times at -8.0pp with a
fully negative CI, so the schedule term carries real information, but the
market carries more: at fire time the model claimed +23.5pp mean conditional
edge and realized +2.1pp gross (-2.5pp net), a 7.6 percent capture ratio.
Roughly 92 percent of the model-market divergence was model error. The
market already prices the weekly TSA pattern to within about 2pp gross at
every divergence this pipeline can identify."

D1 / family: "FAMILY-DEATH under the locked E9/A2 gate: all three frozen
betas fail (means -3.3 / -0.4 / -0.6pp net, all CIs straddling zero, best
miss of the 8pp mean gate 8.4pp). What the bound proves: with deliberate
look-ahead (exact weekend flown/scheduled), calibrated on its own
perfect-info error distributions, this pipeline's gross edge tops out at
about +4.2pp on its fired set (frictionless CI [-1.5, +10.2], still
straddling zero) against an average retail taker friction of 4.6pp; in the
17 disrupted-week clusters, where the channel's whole thesis lives, perfect
cancellation information nets approximately zero (-1.9 to +1.0pp). The
channel ceiling sits below the retail friction floor AND below the locked
bar at zero friction, so this is a channel death, not a friction artifact.
What the bound does NOT prove: it does not measure between-type KXTSAW
brackets, the 59 percent of prints that are snapshot-unprovable, the 26
percent of clusters with no evaluable fire-candidate, or a maker-side
execution (which would inherit the same +4pp-gross zero-straddling ceiling,
minus adverse selection). Per the lock these are scope statements, not
routes: ANY D1 failure is family death, no shadow, no rescue, no third
bite."

## Final line

DEATH-CONFIRMED. No vector survives: friction is not the killer (the
frictionless perfect-info ceiling is ~+4pp gross with a zero-straddling CI),
the E10 dilution never existed in code (own-mode calibration was
implemented), the joint-gating and support-rule vectors are quantified at
under 1pp of mean, the control ordering is an information ladder rather than
a shared bias, and the locked lattice classes and A4 firewall are faithful.
The family died of the market already knowing.

*Em-dash audit: clean (verified after write).*
