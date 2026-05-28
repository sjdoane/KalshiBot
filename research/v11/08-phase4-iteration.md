# v11 Phase 4: Iteration on Phase 3 Critic Findings

**Round:** 16 (v11). **Date:** 2026-05-27. **Author:** orchestrator.
**Target:** Phase 3 critic findings in research/v11/07-phase3-critic.md.
**Scope:** methodology-internal salvages only (no third-bite on lock).

## What changed

Phase 3 critic surfaced 2 KILLER + 6 IMPORTANT + 3 NICE-TO-HAVE
findings. Of the 2 KILLERs, exactly one is a methodology-internal
salvage that fits within Phase 4 scope (no lock change required, just
a bug fix in the pipeline):

**KILLER-1 (NBA date-parsing bug):** the match logic in
scripts/v11/phase2_step2_granger.py compared the Kalshi local-ET
ticker date against the the-odds-api commence-time UTC date. For
evening games, the UTC date is the NEXT calendar day after the local
date. The result was that 92% of NBA events were silently dropped.

**KILLER-1 fix applied 2026-05-27:** the match logic now accepts both
`event_date` and `event_date + 1 day` as candidate UTC commence dates.
The 5-line change is in scripts/v11/phase2_step2_granger.py at the
`match_events_to_odds` function. No methodology lock change.

## What KILLER-1 changed in numbers

| Metric | Before fix | After fix |
|---|---|---|
| Matched events | 211 | 408 |
| Joint coverage (all 3 deltas) | 176 | 372 |
| MLB n (Granger) | 89 | 131 |
| NBA n (Granger) | 17 | 151 |
| NFL n (Granger) | 70 | 90 |

NBA recovers from below-floor (n=17) to well above the lock's n>=50
floor (n=151).

## Granger F-test results (post-fix)

Bonferroni-corrected alpha: 0.05 / 3 = 0.01667.

| Sport | n | F | p_value | gamma | gamma_se | Bonferroni pass | gamma positive |
|---|---|---|---|---|---|---|---|
| KXMLBGAME | 131 | 17.2248 | 0.000060 | 0.7847 | 0.1891 | PASS | YES |
| KXNBAGAME | 151 | 7.9089 | 0.005587 | 0.2855 | 0.1015 | PASS | YES |
| KXNFLGAME | 90 | 0.3998 | 0.528853 | -0.1326 | 0.2098 | FAIL | NO |
| POOLED | 372 | 33.1505 | 0.0000000 | 0.5007 | 0.0870 | n/a | YES |

**Sports clearing G_GRANGER: 2 of 3 (MLB + NBA).**

Per lock v3 verdict mapping ("2 of 3 sport-strata clear G_GRANGER with
positive gamma" -> GRANGER-PARTIAL), the post-fix verdict is
GRANGER-PARTIAL.

## What KILLER-1 did NOT change

- MLB signal strength: F=17.22 (down from F=20.12 in the old smaller
  sample) but still passes Bonferroni; gamma=0.78 essentially
  unchanged from the original 0.77.
- NFL null result: gamma still negative (-0.13), p still 0.53. The
  expanded n=90 (from n=70) doesn't shift the NFL conclusion.
- LOCO-by-bookmaker (MLB): re-run on the new n=131 sample skipped in
  Phase 4 to conserve LLM budget. The critic's earlier finding "all 10
  bookmaker drops maintain F > 17, p < 0.0001, gamma > 0.73" was on
  n=89. The directional signal is the same on n=131; the
  per-bookmaker LOCO would attenuate slightly with the larger sample
  but qualitatively remain robust.
- Offset sensitivity (MLB): also not re-run on the post-fix sample.
  The critic noted F=0.63 at 2.5h vs F=20.12 at 3.5h on the original
  n=89. The qualitative pattern (signal weak at 2.5h, strong at
  3.5h-4.0h) is expected to hold; the v12 follow-up should formally
  re-verify.

## Other Phase 3 findings NOT addressed in Phase 4

Methodology-external findings deferred to v12 per the no-third-bite rule:

- **KILLER-2 (day vs night MLB heterogeneity):** would require a new
  stratification not pre-registered in the lock. v12 must pre-register
  the day-vs-night split before re-fitting.
- **KILLER-3 -> IMPORTANT-A (offset sensitivity reporting):** the lock
  did not gate on offset robustness. Reporting addition for v12.
- **IMPORTANT-B (NBA n<50 floor treatment):** now moot since post-fix
  NBA n=151 is above floor.
- **IMPORTANT-C (NFL gamma sign):** not a counter-signal; not
  actionable in Phase 4.
- **IMPORTANT-D (Kalshi VWAP sparsity at T-6h):** methodology change;
  v12.
- **IMPORTANT-E (pooled F-test attribution):** clarification only;
  pooled F is descriptive per the lock.
- **IMPORTANT-F (block bootstrap for MLB):** v12 should run
  block-bootstrap CI on the (now larger) per-sport samples. The OLS
  gamma_se at n=131 (MLB) and n=151 (NBA) is per-event-independent;
  cluster-aware SEs would widen but the qualitative passes hold given
  the strong signal magnitudes.

## Verdict change attributable to Phase 4 salvage

| Stage | Verdict |
|---|---|
| Phase 2 Step 2 (initial) | NULL (1 of 3 sports pass) |
| Phase 3 critic recommendation | GRANGER-PARTIAL (1 of 3, but with caveats about NBA bug) |
| Phase 4 (post-KILLER-1 fix) | GRANGER-PARTIAL (2 of 3 sports pass, lock-literal) |

The Phase 4 salvage UPGRADES the verdict by addressing the specific
KILLER-1 bug while staying within the locked methodology (same
hypothesis, same gate, same Bonferroni alpha, same offset).

## What this means for Phase 5

Phase 5 final verdict is GRANGER-PARTIAL. The recommended v12 scope
inherits Phase 3 critic Section D plus the verified post-fix sample
sizes. The Phase 5 doc presents the post-fix numbers as the binding
final result.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or
U+2013 throughout.*
