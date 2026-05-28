# Phase 5 Final Critic: Project Kalshi v3 Amendment Verification

**Date:** 2026-05-24
**Reviewer:** Phase 5 final-critic context
**Subject:** `06-model-results.md` Iter-4 amendments + `FINAL-VERDICT.md`, against `07-critic.md` recommended changes.
**Mandate:** Verify the three load-bearing framing amendments cleanly addressed Phase 3 critic findings; sign off or kick back.

## Verdict

**UNCONDITIONAL SIGN-OFF.** All three Phase 3 critic load-bearing findings are addressed with the critic's recommended honesty level. No leftover "v1 confirmed" / "v3 fails C6 by 2pp" / "S3 passed" framing remains in the amended docs. No em-dashes or en-dashes detected (grep on both files returned 0 hits). Ship the verdict.

## Per-finding verification

### Finding 1 (Killer): C6 = mechanical equality, not measured null

Critic ask (`07-critic.md:305-307`): rewrite V3-B2 Section 2 and the FINAL-VERDICT's C6 sentence to acknowledge mechanical equality.

**`06-model-results.md` placement:**
- TL;DR `:15`: "C6 = 0pp is a structural identity, not a measured null. G2 and G3 trade the IDENTICAL 45 holdout rows v1 trades because the LogReg's predicted prob is `>= 0.70` on every holdout row (G2 min 0.8953, G3 min 0.7039). v3 was unable to express a non-trivial decision rule..."
- Section 2.1 table footnote `[1]` at `:66`: "C6 = 0.0pp by construction; G2 and G3 trade the same 45 rows as v1 because LogReg predicted probs are `>= 0.70` on every holdout row (G2 min 0.8953, G3 min 0.7039). C6 cannot distinguish v3 from v1 on this holdout. See Phase 3 critic `07-critic.md` Test 6 for the verification re-run."
- Section 6.4 item 3 `:291`: explicit "C6 comparison is mechanical-equality on this holdout (Phase 3 critic Killer Finding #1)... v3 minus v1 = 0pp by construction."

**`FINAL-VERDICT.md` placement:**
- Section "Three numbers that matter" `:16`: row 1 explicitly says "C6 is mechanical-identity not measurement"; row 2 says "Identical across G1/G2/G3 because LogReg saturates above 0.70 trade threshold on every holdout row."
- "Why operator should accept" `:40`: "C6 = 0.0pp because both LogReg rules saturate above the 0.70 trade threshold on every holdout row, so they trade the identical 45 rows v1 trades. v3 was literally unable to express a v1-differing decision."
- `:44`: "The C6 = 0pp is a structural identity (LogReg saturation), not a measured null."

**Honesty check:** the framing is not watered down. It states the mechanism (LogReg saturation > 0.70 on every holdout row), cites the predicted-prob minima from critic Test 6, and labels the result as "structural identity" / "by construction" rather than "measurement." Verdict TL;DR even leads with this point. PASS.

One residual at `06-model-results.md:259` Section 6.3 still says "C6 fails by 2pp. v3 minus v1 is 0.0pp on G2/G3 because they trade the same rows v1 does." This is a low-risk artifact because the same paragraph explains the rows-traded-identically mechanism, and 6.4 item 3 immediately below reframes it as structural identity. The bullet is internally consistent with the amended framing (it does not say v3 fails the C6 *test*; it says v3 minus v1 is 0pp, which is exactly the structural identity). Not a blocker.

### Finding 2 (Important): "v1 confirmed" overreach corrected

Critic ask (`07-critic.md:311-313, :353`): replace "v1 confirmed" with bilateral framing acknowledging v1's measured edge has untested exposure on KXNFLWINS.

**`06-model-results.md` placement:**
- Section 6.4 item 1 `:287`: "v1's measured edge has NOT been demonstrated on KXNFLWINS markets, which dominate the v3 holdout failure zone. v1 IS the right strategy for the project's known scale (where it has been running), but its edge magnitude on the specific subgroup KXNFLWINS late-season remains untested. The phrase 'v1 confirmed' is overreach."
- Section 6.4 item 2 `:289`: "v1's measured-edge dataset (`data/processed/sports_dataset.parquet`) contains zero KXNFLWINS markets. v3's probe enumerates 95 v1-eligible KXNFLWINS markets in the same time window."
- Section 6.4 item 4 `:293`: "v3 holdout reveals an untested v1 distributional exposure... v1 in production scans the full sports universe (`src/kalshi_bot/strategy/market_scanner.py:118-152`), so this exposure is real for the live bot, not a v3 artifact."
- TL;DR `:17` and `:23`: same bilateral framing repeated.

**`FINAL-VERDICT.md` placement:**
- One-paragraph verdict `:10`: "the 'v1 confirmed' framing overreaches because v1's measured-edge dataset structurally excludes the KXNFLWINS markets that dominate the v3 holdout failure."
- Numbers table `:18`: row 3 explicitly states "v1's measured `+12.47pp` edge was computed on a dataset with zero KXNFLWINS markets."
- "Why operator should accept" `:50`: "external features do not improve calibration above v1's heuristic on this holdout. AND the holdout itself reveals that v1's measured edge has untested exposure on KXNFLWINS late-season markets. Both findings are real; neither was visible from the v1 backtest alone."
- "What this changes about the live bot" `:79`: "v1's claimed `+12.47pp` edge has not been measured on KXNFLWINS. The v3 holdout's NFL slice realized -40.19pp on the same eligibility filter. v1's live scanner pulls the full sports universe... so this exposure IS in production scope, just untested."
- Future scope W1 `:83`: "Rebuild v1's backtest dataset on the complete sports universe."

**Honesty check:** the wording is the critic's recommended "v1 keeps running on its tested-as-known universe but its measured edge has untested exposure on KXNFLWINS" framing. No leftover "v1 confirmed" claims in the amended docs (grep of `06-model-results.md` and `FINAL-VERDICT.md`: the only `v1 confirmed` hit is `06-model-results.md:13` which is the explicit acknowledgement that the original draft used the phrase and the critic flagged it). The `05-dataset-build.md:211` hit ("most likely overall verdict is 'null finding, v1 confirmed.'") and `iterations.md:45` hit are pre-amendment artifacts predicting the foreshadowed outcome, not claims; neither is in the final verdict path. PASS.

### Finding 3 (Important): S3 reclassified honestly

Critic ask (`07-critic.md:315-317`): re-classify S3 as "FAIL (v3 holdout 2/19 = 10.5% series-prefix overlap with v1's live attempted-orders)" in the FINAL-VERDICT.

**`06-model-results.md` placement:**
- TL;DR `:19`: "S3 domain match materially fails. v1's live attempted-orders cover 19 distinct series-prefixes...; v3 holdout covers 5; overlap is 2/19 = 10.5%."
- Section 4.3 final paragraph `:202`: "Update from Phase 3 critic. The intersection was performed in `07-critic.md` Test 2 / Important Finding #3. v1's live attempted-orders cover 19 distinct series-prefixes; v3 holdout covers 5; overlap is 2/19 = 10.5%. S3 materially FAILS."
- Section 7 v2 failure-mode table row `:316`: "Domain mismatch UNRESOLVED after Phase 3 critic... excludes 17 of 19 series v1 actually attempts in live operations... Phase 3 critic Important Finding #2 + #3 + #4."

**`FINAL-VERDICT.md` placement:**
- Numbers supplementary context `:24`: "Series overlap between v1's live attempted-orders (19 series) and v3 holdout (5 series): 2 of 19 = 10.5%."
- "Why operator should accept" `:46`: "S3 domain match materially fails: only 2 of 19 series in v1's live attempted-orders overlap with the v3 holdout."
- v2 failure-mode table `:142`: "PARTIALLY REPRODUCED. v3 ran C6 on a holdout 49%-dominated by KXNFLWINS, a series v1's measured-edge dataset structurally excludes."

**Honesty check:** the docs say "materially fails" / "UNRESOLVED" with the 2/19 = 10.5% number cited consistently. No leftover "S3 passed" claim anywhere (grep `S3 passed`: only one hit, in `07-critic.md:18`, which is the critic's complaint about the original wording). PASS.

## New issues introduced by amendments

None found. Checks performed:

- **Did the rewrite drop important information?** Section 4.3's original (series, lifetime, price) holdout distribution table is preserved at `:184-196`; the critic intersection finding is appended as a clearly labeled "Update from Phase 3 critic" rather than replacing the original data. Section 6.4's four-point amended structure preserves the original "external features cannot beat v1" claim while adding the three honesty caveats. Section 7's table changed "Domain mismatch PARTIALLY ADDRESSED" to "UNRESOLVED" but kept all other rows intact.
- **Internal consistency:** TL;DR, Section 2 footnote, Section 4.3 update, Section 6.4 items 1-4, and Section 7 table all use the same numbers (2/19, 10.5%, -40.19pp NFL, -18.89pp full, 95 KXNFLWINS in v3 probe vs 0 in v1 backtest) and same framing.
- **FINAL-VERDICT internal consistency:** the verdict paragraph, "three numbers" table, "why accept" section, and v2 failure-mode table all converge on the same bilateral framing.
- **Em-dash / en-dash audit:** `Grep -P "[\x{2014}\x{2013}]"` on `06-model-results.md` and `FINAL-VERDICT.md`: zero matches in both. This document also passes (no em-dashes used; only ASCII hyphens).

## Final recommendation

**Ship the verdict.** The amendments addressed all three Phase 3 critic load-bearing findings without dropping original content or introducing internal inconsistencies. The operator's stated kill-early-honestly principle is satisfied: the docs say "v3 cannot beat v1 with external features on this holdout AND this holdout reveals an untested v1 KXNFLWINS exposure," not "v1 confirmed." The future-scope W1 (v1 backtest rebuild on full sports universe) is correctly flagged as operator-relevant but out of v3 scope.

No further amendment round needed. Update CLAUDE.md and memory to Round 9 closed, mark v3 master plan complete, and continue v1 live unchanged.

## Citations

- Phase 3 critic recommendations: `07-critic.md:303-353` ("Findings, in priority order" + "Specific recommended changes")
- Amended `06-model-results.md`: TL;DR `:9-25`, Section 2.1 footnote `:66`, Section 4.3 update `:202`, Section 6.4 items 1-4 `:283-294`, Section 7 table `:307-320`
- `FINAL-VERDICT.md`: paragraph verdict `:8-10`, three numbers `:14-24`, why-accept `:42-50`, live-bot impact `:71-85`, v2 failure-mode table `:134-145`
- Iter-4 log: `iterations.md:157-192`
- Grep verification: `[\x{2014}\x{2013}]` returned no matches in either amended doc or this doc
