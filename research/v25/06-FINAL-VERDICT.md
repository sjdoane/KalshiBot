# v25 FINAL-VERDICT: AAA retail-gas ladder taker (wholesale pass-through) = DOUBLE NULL

**Date:** 2026-07-02. Hypothesis family ~#25. Verdict per the locked lattice
(02-methodology-lock.md sections 8-9), adversarially audited (05-verdict-critic.md,
NULL-CONFIRMED). Capital: $0 deployed, FLAT throughout.

## H1 verdict (binding)

NULL. Under the locked gates, the frozen FALLBACK spec (symmetric ECM, run by the
pre-committed E4 rule; in-sample point-forecast correlation ~0 at h=7/14, ledger 0c
item 4) does not extract positive net P&L as a taker from KXAAAGASW/KXAAAGASM under
ANY execution assumption from worst-case (+3c haircut, worst-case fee: mean -2.4pp,
CI [-7.8, +2.3]pp, 2,927 fires / 52 clusters) to frictionless (mean ~+2.3pp, CI lower
bound ~-3.1pp). This is a null of THIS frozen spec, which had no measurable
point-forecast skill and cannot see RBOB futures curve information the market can
see. It is NOT evidence that the market prices pass-through efficiently, and it is
weak evidence on whether the ladder sits at the public pass-through frontier, because
the operative instrument was weak. What the results DO adjudicate, per the
pre-committed 0b honesty note, is the 22pp median divergence: it was model
overconfidence, not market miscalibration (YES-side fires -13.7pp; the control's
gross capture exceeded the model's). On the fired print set the ladders are within
worst-case taker frictions of a random-walk-with-empirical-tails benchmark (control
net -0.2pp, CI [-5.1, +4.3]pp); no stronger calibration claim is licensed.
Side-matched attrition was 54.7 percent, so the capacity story is weaker (E15d). The
NO-side +8.7pp breakdown is the mechanical complement of the model's losing YES side,
is 1 of ~10 non-binding post-data cells in hypothesis family ~25, and is logged only
as a future-lock seed.

## H2 verdict (binding)

NULL. 447 fires / 26 clusters (power floor met), mean -0.5pp, CI [-3.9, +1.7]pp: the
certainty stratum offers no net tail edge of THIS spec even where the model and the
random-walk control agree at the 0.995 floor.

## The killer finding, one line

The market-vs-model divergences that generated every fire were the model's own
overconfidence (unstable asymmetric fits, then a skill-less stable fallback), and even
a frictionless taker could not monetize them; the gas ladders sit within taker
frictions of an honest empirical-tails benchmark across 52 settlement-week clusters.

## Loop discipline accounting (lock section 10 duty)

- Families screened to date: ~25. Hypotheses this round: two (H1; H2 kept at 0b).
  Strata added post-data: zero. Third bites: zero.
- The 10 excluded no-strike markets are the old-format KXAAAGASM-23DEC31-T* family
  (floor_strike null in the API objects); all other exclusions are in the funnel.
- The [03:00, 09:00) ET publication-ambiguity window is untested territory by design
  (E1), not evidence of anything.
- Future-lock seeds (NOT v25 results, logged per the critic): (a) real-time NY Harbor
  wholesale feed (the d-3 + 1c stacked-optimistic run sat at the gate boundary,
  CI ~[+0.003, +0.071], but requires an information set FRED does not deliver and two
  post-data assumptions); (b) the NO-side asymmetry as a fresh-data hypothesis.
- Method wins to carry: the settlement-key audit pattern (698/698, decisive at $0);
  the EIA weekly-release visibility calendar (flat lags LEAK; release calendars are
  the honest as-of rule for any EIA-sourced regressor); the outcome-blind 0b fire
  projection catching a guaranteed-underpowered design before lock.

## Routing

Per section 9: both NULL -> pivot. Next queued family: v26 true window-aggregates
(research/v26/00-proposal-draft.md), fresh lock required. No live read for v25.

*Em-dash audit: clean (verified after write).*
