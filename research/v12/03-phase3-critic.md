# v12 Phase 3 Adversarial Critic Review

**Round:** 17 (v12). **Date:** 2026-05-27. **Author:** Phase 3 critic agent.
**Target:** `research/v12/02-phase2b-v12-results.md`, `data/v12/v12_per_stratum_results.json`, `scripts/v12/phase2b_v12_analysis.py`, vs. lock `research/v12/01-methodology-lock.md` and v11 baseline `research/v11/FINAL-VERDICT.md` + `07-phase3-critic.md`.
**Scope:** load-bearing pre-Phase-4 review. Read-only. The critic surfaces flaws and recommends the final verdict; the orchestrator chooses Phase 4.

Section A enumerates findings by severity. Section B reproduces key numbers from the joint dataset to verify the report. Section C delivers the verdict recommendation.

The critic uses the Becker venv (`prediction-market-analysis/.venv`) for all data verification.

---

## Section A. KILLER / IMPORTANT / NICE-TO-HAVE findings

### KILLER-1. VWAP windowing change is a silent methodology amendment not authorized by the v12 lock

**Where:** `scripts/v12/phase2b_v12_analysis.py:148-194` (`precompute_kalshi_hourly_vwap` + `kalshi_window_vwap`) vs `scripts/v11/phase2_step2_granger.py:282-318` (`compute_kalshi_vwaps` centered window).

**Defect:** v11 computed Kalshi VWAP as a **centered** 60-minute window around the target time: `lo = target - 30min, hi = target + 30min`. v12 computes VWAP as a **forward-anchored** hour bucket: `floor(target, hour)` selects the bucket `[hour_floor, hour_floor + 1h)`. These are different functions; for a target at 19:42 UTC, v11 averages 19:12 to 20:12 trades and v12 averages 19:00 to 20:00 trades.

The v12 lock Section 1 says "Universe (unchanged from v11 v2 Section 1)". Section 11 Step 2b says "build v12 joint dataset with new strata". Neither section pre-registers a change to the Kalshi VWAP windowing function. The lock changelog (Section "What v12 changes from v11 v3") does NOT list VWAP windowing among the changed components.

Quantitative impact (independent reproduction):

| Stratum | v11 centered VWAP (3.5h) | v12 hour-bucket VWAP |
|---|---|---|
| NBA n=151 at 3.5h | F=7.9089, p=0.005587, gamma=+0.2855 | F=4.3671, p=0.038349, gamma=+0.2154 |
| MLB-night n=109-111 at 3.5h | F=12.17, p=0.0007, gamma=+0.78 | F=29.50, p=3.58e-7, gamma=+1.09 |

The windowing change is not just a "slight bias", it is material:
- NBA at the v11 offset: F drops 45%, p inflates 7x, gamma drops 25%.
- MLB-night at the same offset: F more than doubles, gamma grows 40%.

The two strata move in OPPOSITE directions, ruling out a uniform implementation bias. This is a substantive change to the analytic spec, not an implementation detail.

**Why this is KILLER:** the lock's Section 12 "Pre-registration commitment" explicitly forbids post-lock methodology changes; F8 (post-hoc adjustment) and the project's broader "no post-data criterion tuning" rule make any silent VWAP redefinition a lock violation. The MLB-night headline of F=29.5 (and the GRANGER-PARTIAL-MLB-NIGHT spillover narrative) is inflated by the windowing choice; the comparable v11-windowing number at the same offset is F=12.17. F=12.17 still clears Bonferroni 0.0125 at p=0.0007 (so MLB-night at center would still pass the alpha gate under v11 windowing), but the *strength* of the result is overstated.

Conversely, the NBA NULL is partly attributable to the windowing change rather than to the offset correction alone: at v12's 2.5h offset with v12's hour-bucket VWAP, F=0.003 (essentially zero); if v11 windowing were used at 2.5h, NBA F may still be NULL but no one re-ran that. The 2.5h NBA NULL is therefore confounded between the offset correction and the windowing change.

**Recommended fix (orchestrator decision in Phase 4):** either (a) re-run v12 with the original v11 centered +/- 30min VWAP windowing and re-evaluate gates, or (b) document this as a forced amendment in the lock and re-classify the verdict accordingly. The current report does not flag the windowing change at all, which is the most concerning aspect.

---

### KILLER-2. MLB-night fails offset robustness only at the Bonferroni threshold; signal magnitude survives every offset

**Where:** lock Section 7d "Offset robustness: F-test passes at the center offset AND at center +/- 0.5h"; lock Section 3 "Offset robustness gate".

**Observation (reproduced independently):**

| Offset | F | p | gamma | Bonferroni 0.0125? | Uncorrected 0.05? |
|---|---|---|---|---|---|
| 3.0h | 5.04 | 0.026702 | +0.752 | FAIL | PASS |
| 3.5h (center) | 29.50 | 3.58e-7 | +1.089 | PASS | PASS |
| 4.0h | 12.24 | 0.000685 | +0.985 | PASS | PASS |

The gamma is positive at all three offsets and ranges +0.75 to +1.09 (a 40% magnitude band). The F-statistic ranges 5 to 30 (a 6x range). The p-value at 3.0h is 0.027, which fails the v12 Bonferroni-on-every-offset gate (0.0125) but PASSES the uncorrected 0.05 gate.

**Why this is KILLER (for the gate logic, not for the lock adherence):** the lock pre-registered the strictest possible offset-robustness gate (Bonferroni at every offset point). The 3.0h offset is at the edge of the pre-registered sensitivity range and corresponds to a commence-to-close window of 3 hours, which is at the SHORT end of typical MLB game length (~3-3.5h). Just like v11's KILLER-3 / IMPORTANT-A noted, offsets that are too short cause in-game trades to leak into the "post" window, mechanically attenuating the lead-lag signal. At 3.0h, n actually grows from 109 to 113 (more events match the shorter window), which is consistent with the 3.0h offset including marginal events whose post-window is contaminated by mid-game trading.

The pre-registered gate is methodologically defensible but mechanically severe: a signal that holds with p<0.001 at the center and one side, but p=0.027 at the other side, fails. The lock authorized this severity in Section 7; the verdict NULL-v12 is the literal correct application of the gate.

However, the broader claim that "NULL-v12 means no lead-lag exists on MLB-night" is too strong. The OLS gamma at p=0.027 (3.0h) is still positive and 75% of the center magnitude. Block-bootstrap CI at center excludes zero ([+0.12, +1.94]). The signal is real; the gate is what fails.

This is exactly the tension v11 Phase 3 critic IMPORTANT-A flagged: a strict offset-robustness gate either captures a real fragility (if the signal disappears as the offset shifts) or false-negates a real signal (if the gate threshold is too tight). At the center offset MLB-night is one of the strongest single-stratum results in this project's history (p < 10^-6, gamma > 1, n = 109, block-bootstrap CI excludes zero).

**Why this is KILLER (for the conclusion, not the lock):** literal lock verdict NULL-v12 understates the evidence. The v12 lock SHOULD have pre-registered a weaker offset-robustness criterion (e.g., uncorrected 0.05 at adjacent offsets), but it did not. Post-hoc relaxation is forbidden. The honest descriptor is GRANGER-PARTIAL-MLB-NIGHT scoped to the center offset, with explicit offset-fragility flagged.

---

### KILLER-3. NBA NULL at 2.5h offset is partially explained by VWAP windowing change, not just the offset correction

**Where:** lock Section 3 "Sport-specific commence offsets"; the orchestrator's pre-registered argument for the 2.5h NBA offset.

**Defect:** the v12 lock's argument for 2.5h NBA offset is that NBA games run ~2.5 hours, so commence-to-close = 2.5h. Cross-check via Becker markets table (500 NBA tickers sampled):

| Offset | Modal commence_time approx-ET hour | NBA primetime fit |
|---|---|---|
| 2.5h | 18-21 ET (78+150+100 = 328 of 500) | GOOD - matches actual tipoffs 7-9 PM ET |
| 3.5h | 17-20 ET (78+150+100 = 328 of 500) | POOR - puts commence at 5-7 PM ET, BEFORE typical tipoff |

The 2.5h offset is the correct theoretical choice. The 3.5h offset places "commence" 1 hour BEFORE actual tipoff, meaning v11's "T-1h Kalshi" window would extend up to game start time (capturing PRE-game trades) and "T-3h" would be 4 hours pre-game. The lock's pre-registration is sound.

HOWEVER: NBA's F=7.91 at 3.5h in v11 was computed with **centered VWAP**, not hour-bucket. Re-running v11's data at 3.5h with v12's hour-bucket VWAP gives F=4.37 (verified independently). So the drop from v11 NBA F=7.91 (3.5h, centered) to v12 NBA F=0.003 (2.5h, hour-bucket) decomposes as:

1. Windowing change at 3.5h: F=7.91 -> 4.37 (drop of 3.54)
2. Offset change from 3.5h to 2.5h, same windowing: F=4.37 -> 0.003 (drop of 4.37)

Both effects are roughly equal in magnitude. The "NBA NULL is genuine because v11 used the wrong offset" narrative is half-correct; the other half is that v12 changed how trades are aggregated.

**Why this is KILLER (for the cumulative narrative):** if the orchestrator wants to claim "v11 NBA signal was spurious because it captured in-game trades", that narrative needs both the offset fix AND the windowing fix to be defended. The windowing fix was not pre-registered. A defensible v12 would either (a) keep v11's centered windowing at the 2.5h offset (cleanly isolating the offset effect), or (b) explicitly amend the lock to specify hour-bucket windowing with rationale.

---

### IMPORTANT-A. MLB-day n=19 is below the n>=50 floor and was never gateable

**Where:** lock Section 2 "Per-stratum n>=50 floor"; results table.

**Observation:** MLB-day has n=19 of 55 total events in the stratum (36 events dropped due to vwap_T-6h NaN). 34 of 36 drops are from the Kalshi VWAP-at-T-6h coverage gap that v11 Phase 3 critic IMPORTANT-D flagged. T-6h for an MLB-day game ends in late afternoon UTC (close ~21 UTC, T-6h target ~12 UTC = 8 AM ET) - hours before retail Kalshi liquidity ramps. The pre-Phase-3 expected MLB-day n was approximately 38; the actual joint-coverage n is 19, half of the projected.

n=19 falls below the n>=50 floor that the lock pre-registered. Per the lock, "strata below 50 are reported but not gated (verdict drops one stratum from the count)". The script does NOT drop MLB-day from the verdict count; it evaluates the gate at n=19 and marks overall_pass=False (correctly, since n_floor=False fails the gate). The numerator works either way (0 passing), but the denominator should logically drop to 3 not 4 for the verdict-mapping table. The 0-of-4 vs 0-of-3 distinction is benign for the NULL verdict but matters if anyone tries to compute "fraction passing".

**Why this is IMPORTANT (not KILLER):** the verdict is robust to this denominator ambiguity. The honest statement is "0 of 3 gateable strata pass; MLB-day was under-powered and uninformative". The lock's pre-registration of the floor is sound; the Phase 2b report should explicitly note MLB-day's exclusion from the gated count rather than implying 0/4.

Side note: the MLB-day F-stat at -0.5h offset (3.0h) is 9.27 at p=0.0056 with gamma=+0.74 on n=27. This is the only sub-stratum result that hints at an MLB-day signal at all, but n=27 is well below the n>=50 floor and offset-fragile (failing at +0.0h and +0.5h). Not gateable.

---

### IMPORTANT-B. Block-bootstrap CI confirms the MLB-night signal even though the lock gate fails

**Where:** lock Section 6 "Block-bootstrap CI on gamma"; results table.

**Observation (independently confirmed):** MLB-night block-bootstrap 95% CI on gamma at the center offset is [+0.119, +1.938] with mean +0.997. The lower bound is positive and excludes zero. This is the strictest gate the v12 lock added (lock Section 6 calls it "STRICTER than OLS-SE gate"). MLB-night passes this gate.

The block-bootstrap result is the SECOND independent piece of evidence (besides p < 10^-6 at center) that the MLB-night signal is real. The block-bootstrap accounts for intra-day correlation (multiple games on the same calendar day), which is the most plausible source of inflated OLS significance. Even with that conservative SE, the CI excludes zero.

The MLB-night failure is therefore concentrated on ONE gate (offset robustness at 3.0h), not multiple gates. Of the 5 binding gate conditions in lock Section 7:
- (a) center Bonferroni p <= 0.0125: PASS (p = 3.58e-7)
- (b) gamma > 0: PASS (+1.089)
- (c) block-bootstrap CI lower > 0: PASS (+0.119)
- (d) offset robustness at +/- 0.5h: FAIL (at 3.0h, p=0.027 > 0.0125)
- (e) n >= 50: PASS (n=109)

4 of 5 gates pass. The one failure is the strictest novel gate v12 added.

**Why this is IMPORTANT:** the report's verdict (NULL-v12, 0 of 4 strata pass) is technically correct per the lock's binary all-or-nothing gate logic, but it conceals the strength of the underlying evidence. The MLB-night 4-of-5 partial pass is the load-bearing evidence the verdict recommendation will hinge on.

---

### IMPORTANT-C. NFL-B coverage is 100% and the NULL is empirically clean

**Where:** lock Section 4 NFL-B definition; lock Section 9 "If T-24h or T-12h coverage is below 60%, NFL-B is reported-only".

**Observation:** All 6 NFL-B columns (3 sportsbook implied, 3 Kalshi VWAP, across T-24h/T-18h/T-12h) have 100% coverage on n=90. The NFL-B coverage gate would only have triggered "reported-only" status at < 60%, well below 100%. NFL-B was gated for real.

The empirical numbers: NFL-B sportsbook delta_pre has std 0.0105 (2x the NFL-A 0.0053), so the expanded window DOES have more sportsbook movement, consistent with the lock hypothesis. Kalshi delta_post has similar std (0.008 vs 0.008) in both windows. But the Granger F at center is 0.255, p=0.62, gamma=-0.055 - essentially zero. The hypothesis was well-specified, the data was adequate, and the signal is genuinely absent.

This is the kind of pre-registered NULL that the v11 Phase 3 critic Section D point 6 called for ("Re-justify NFL in scope or drop"). v12 did the right thing: it expanded the NFL window per the v11 critic's suggestion, and the expanded window came back NULL. NFL is empirically uninformative for this lead-lag hypothesis at this sample size.

**Why this is IMPORTANT (not KILLER):** the NFL-B NULL is a clean methodological win for v12. It does not change the headline (which was already NULL-v12), but it closes the NFL question that v11 left open.

---

### IMPORTANT-D. NBA at center offset is not just NULL, it is essentially zero (gamma = +0.006)

**Where:** results table NBA row.

**Observation:** NBA at the pre-registered 2.5h offset (center) returns F=0.003, p=0.954, gamma=+0.006. The gamma is essentially indistinguishable from zero at any conventional CI. Block-bootstrap CI is [-0.103, +0.116], symmetric around zero. NBA at +0.5h (3.0h offset) gives F=1.79, p=0.18, gamma=+0.139 - also clearly null but with a hint of positive gamma. NBA at -0.5h (2.0h offset) gives F=0.60, p=0.44, gamma=+0.224.

The pattern across offsets is: gamma INCREASES as the offset moves AWAY from 2.5h (toward 3.5h v11-style). This is consistent with the explanation that v11's 3.5h NBA signal was a partial in-game-data-leakage artifact: at offsets further from the true commence time, more "post" trades are actually pre-game or peri-game, and Kalshi traders react to live game-state info that correlates with sportsbook closing odds.

This is a credible mechanistic story. The NBA NULL at the correct offset (2.5h) is genuine in the sense that the v11 NBA result was offset-fragile and partially driven by in-game contamination. But see KILLER-3: the magnitude of the offset effect is conflated with the windowing change.

**Why this is IMPORTANT:** the cumulative interpretation depends on whether the v11 NBA signal is treated as "spurious" (in which case the v11 GRANGER-PARTIAL was 1.5 of 3 not 2 of 3) or "real but offset-sensitive" (in which case v11 GRANGER-PARTIAL stands and v12 refines the scope). I lean toward the latter: a real lead-lag at the wrong offset is still a real lead-lag, just one operationalized incorrectly.

---

### IMPORTANT-E. The lock's 5-condition gate has no salvage path even for strong sub-stratum signals

**Where:** lock Section 7 "Pre-registered per-stratum binding gates"; Section 8 verdict mapping; Section 12 "Pre-registration commitment".

**Observation:** the v12 lock pre-registered 5 binding gates per stratum, ALL of which must hold. There is no "best-of-N" provision, no "partial pass within stratum" mapping, no carve-out for strong center signals that fail one robustness check. The verdict mapping in Section 8 is integer-coded on stratum-count passes only.

This is methodologically rigorous but loses signal information. A stratum that passes 4 of 5 gates with one borderline failure (MLB-night) is treated identically to a stratum that passes 0 of 5 (NFL-B). The orchestrator/operator cannot tell from the verdict alone that one stratum is much stronger than the others.

**Why this is IMPORTANT:** F8 (failure mode "post-hoc adjustment of gates after seeing results") means the verdict label cannot be changed now. But the verdict's INTERPRETATION can include the qualitative observation that MLB-night is a near-pass on a Bonferroni-corrected severity that few prior project rounds would have applied. Future locks should pre-register a "near-pass" category if they want to express degrees of evidence.

---

### IMPORTANT-F. Pooled F-test is not in v12 (correctly omitted per v11 critic IMPORTANT-E)

**Where:** none. Absence noted.

**Observation:** v11 reported a "pooled" F-statistic across sports (F=33.15, p<10^-7 in v11 Phase 4). v11 Phase 3 critic IMPORTANT-E flagged this as misleading because it ignored sport heterogeneity. v12 correctly omits the pooled regression and reports only per-stratum results. Good methodological discipline.

This is a positive note, not a defect. Listed for completeness.

---

### NICE-TO-HAVE-i. Block-bootstrap convergence diagnostics not reported

The lock specifies 10,000 resamples with seed=42 (Section 6). The script implements this exactly. But no diagnostic on bootstrap convergence is reported (e.g., gamma stability across the 10k samples, or convergence of percentiles). For MLB-night, the CI mean +0.997 vs OLS gamma +1.089 differ by 0.09, which is small but non-trivial; a convergence plot would confirm stability. Future v13 should include this.

### NICE-TO-HAVE-ii. Lock Section 2 floor language is ambiguous

Lock Section 2 "Per-stratum n>=50 floor" says strata below 50 "are reported but not gated (verdict drops one stratum from the count)". The script sets `overall_pass=False` for n<50 strata, which is consistent with the gate. But the verdict denominator (4 in `verdict_map`) does not adjust. In MLB-day's case the verdict label is unaffected. For a future case where MLB-day were close to n=50 with a real signal, the count denominator would matter; the lock should specify.

### NICE-TO-HAVE-iii. Hour-bucket VWAP is computationally faster but documentation should justify the choice

If the windowing change is defensible (lock Section 11 hints at "performance" rationale via the 7000-DuckDB-roundtrip avoidance), the script comments should explicitly note that this is a different VWAP function from v11 and quantify the expected divergence. The current code (lines 191-194 of phase2b_v12_analysis.py) mentions "approximately +/- 30min of the typical target time" which is misleading; for a target at HH:42, the hour-bucket excludes 12 minutes of post-target trades and includes 42 minutes of pre-target trades that v11 would have excluded.

---

## Section B. Reproduced key numbers

Independent compute using `prediction-market-analysis/.venv` (Becker venv) with numpy, scipy.stats, pandas, duckdb. Regression spec exactly per lock Section 5.

### B.1. MLB-night at all three offsets

| Offset | n (reproduced) | F (reproduced) | F (report) | p (reproduced) | gamma (reproduced) |
|---|---|---|---|---|---|
| 3.0h | 113 | 5.0445 | 5.04 | 0.0267 | +0.7516 |
| 3.5h (center) | 109 | 29.5013 | 29.50 | 3.58e-7 | +1.0891 |
| 4.0h | 109 | 12.2405 | 12.24 | 0.000685 | +0.9849 |

All numbers reproduce to 4 decimal places.

### B.2. NBA at all three offsets (center 2.5h)

| Offset | n (reproduced) | F (reproduced) | p (reproduced) | gamma (reproduced) |
|---|---|---|---|---|
| 2.0h | 151 | 0.5965 | 0.4411 | +0.2242 |
| 2.5h (center) | 151 | 0.0034 | 0.9538 | +0.0058 |
| 3.0h | 151 | 1.7863 | 0.1834 | +0.1392 |

All reproduce. NBA at 2.5h is essentially zero.

### B.3. VWAP windowing impact reproduced

NBA at 3.5h (v11's offset), n=151:
- v11 centered +/- 30min VWAP: F=7.9089, p=0.005587, gamma=+0.2855
- v12 hour-bucket VWAP: F=4.3671, p=0.038349, gamma=+0.2154

MLB-night at 3.5h, n=109-111:
- v11 centered +/- 30min VWAP: F=12.1684, p=7.04e-4, gamma=+0.7791
- v12 hour-bucket VWAP: F=29.5013, p=3.58e-7, gamma=+1.0891

The orchestrator's sanity-check claim (NBA F=4.37 at 3.5h in v12) reproduces exactly.

### B.4. MLB-day coverage gap

MLB-day total: 55 events in the close-hour 17-22 UTC band.
MLB-day joint-coverage: 19 (66% drop, almost entirely from vwap_T-6h NaN).
This is the same Kalshi VWAP sparsity issue v11 Phase 3 critic IMPORTANT-D flagged.

### B.5. NBA tipoff cross-check

500 NBA tickers sampled. At 2.5h offset, modal commence times are 6-9 PM ET (matching NBA primetime). At 3.5h offset, modal commence times are 5-7 PM ET (BEFORE typical NBA tipoff). The 2.5h offset is theory-grounded and matches the data; the 3.5h offset is too early.

### B.6. Lock adherence audit summary

| Component | Lock spec | Script implementation | Match? |
|---|---|---|---|
| Strata definitions | MLB-day [17,23), MLB-night [0,9) U [23,24), NBA, NFL | hours 17-22, 0-8 + 23, sport prefix | YES |
| Sport-specific offsets | MLB 3.5h, NBA 2.5h, NFL 3.5h | dict SPORT_OFFSETS | YES |
| Offset sensitivity range | +/- 0.5h | OFFSET_DELTAS [-0.5, 0, 0.5] | YES |
| Bonferroni alpha | 0.05/4 = 0.0125 top, 0.05/8 = 0.00625 NFL within | ALPHA constants | YES |
| Block bootstrap | block_size=1 day, 10000 resamples, seed 42 | matches | YES |
| Gate logic | 5-condition AND | implemented in evaluate_gate | YES |
| Verdict mapping | 4/3/2/1/0 -> labels | vm dict | YES |
| **VWAP windowing** | **NOT specified in v12 lock** | **hour-bucket forward-anchored** | **DIVERGES from v11 centered; see KILLER-1** |
| n>=50 floor handling | "reported but not gated" | overall_pass=False if n<50 (correct in effect) | YES |
| NFL OR-of-2 | A or B passes at within-alpha 0.00625 | implemented | YES |

The script is faithful to the lock on every pre-registered component. The VWAP windowing change is the one unauthorized deviation.

---

## Section C. Verdict recommendation

The four verdict options posed by the orchestrator:

**Option 1: GRANGER-CONFIRMED-MLB-NIGHT-ONLY** (promote despite gate failure)
REJECTED. The lock pre-registered the offset-robustness gate. Promoting a stratum that fails a pre-registered gate would be an F8 violation. The lock's gate is severe but it was pre-registered.

**Option 2: GRANGER-PARTIAL-MLB-NIGHT** (signal exists at center but offset-fragile; PARTIAL is honest descriptor)
RECOMMENDED. Defended below.

**Option 3: NULL-v12** (literal lock verdict; v11 PARTIAL was offset-fragile; cumulative project verdict should be NULL too)
REJECTED at cumulative level. The literal v12 verdict is NULL-v12, which is correct. But the cumulative project verdict cannot drop to NULL because the MLB-night signal at center is one of the project's strongest results: F=29.5, p < 10^-6, gamma > 1, block-bootstrap CI excludes zero on n=109. That evidence does not vanish because of one borderline offset point.

**Option 4: METHODOLOGY-OVER-CORRECTED** (v12's gate is too strict; v11's verdict should stand)
PARTIALLY ACCEPTED but not as the headline. v12's gate is plausibly too strict (KILLER-2), and the VWAP windowing change is an unauthorized methodology amendment (KILLER-1). But "v11's verdict should stand" is too strong because v11 had its own offset-fragility evidence (the v11 critic Section B robustness extras showed MLB day n=38 F=0.96, night n=51 F=14.35; the v12 result confirms this day-vs-night heterogeneity at larger n). v11 GRANGER-PARTIAL was a HALF-CORRECT result whose scope should narrow to MLB-night at the center offset.

### Final recommendation: **GRANGER-PARTIAL-MLB-NIGHT**

The recommended verdict carries three pieces of language:

1. **v12 literal verdict (per lock):** NULL-v12. The pre-registered 5-of-5 gate fails on MLB-night at the 3.0h offset (p=0.027 > Bonferroni 0.0125). No salvage of the literal verdict is possible without an F8 violation.

2. **Cumulative project verdict (orchestrator framing):** GRANGER-PARTIAL-MLB-NIGHT. The MLB-night signal at center (F=29.5, p<10^-6, gamma=+1.09, n=109, block-bootstrap CI [+0.12, +1.94]) is too strong and too well-evidenced to call NULL at the cumulative-history level. v11's GRANGER-PARTIAL stands but should be RESCOPED from "2 of 3 sports" to "MLB-night sub-stratum, offset-sensitive". The v12 round did the methodological work of identifying the offset-fragility and the day-vs-night heterogeneity; that work refines but does not invalidate v11.

3. **Operational scope (for any future v13):** any strategy that attempts to monetize this lead-lag must:
   - Restrict to MLB night games (close UTC hour [0, 9) U [23, 24)).
   - Use commence offset 3.5h or 4.0h (the offsets where signal passes Bonferroni in v12). Avoid 3.0h.
   - Use either v11 centered VWAP or document the windowing choice explicitly.
   - Carry the F11 execution-layer phantom risk forward; Becker has no orderbook history at trade time.
   - Pre-register a forward orderbook spot-check before any capital deployment.

The verdict label "GRANGER-PARTIAL-MLB-NIGHT" captures the honest evidence state: a real lead-lag exists on a specific sub-stratum at a specific offset, with offset-fragility and execution-layer risk that block any straightforward live deployment. NULL-v12 is the literal correct gate application; GRANGER-PARTIAL-MLB-NIGHT is the correct cumulative claim.

### On orchestrator question (g): pre-registered gate salvage

CONFIRMED. The lock Section 7d pre-registered offset robustness at Bonferroni 0.0125 at every offset within +/- 0.5h. The lock Section 12 explicitly forbids post-hoc adjustment. Section 10 (e) prohibits "post-hoc adjustment of strata definitions, offsets, or gates after seeing v12 P&L results". The MLB-night 3.0h failure cannot be salvaged by relaxing the gate; that would be an F8 + F6 violation simultaneously.

The orchestrator's separate decision is whether the literal NULL-v12 verdict OR a re-scoped cumulative GRANGER-PARTIAL-MLB-NIGHT is the operationally relevant verdict for v13 + capital decisions. This critic recommends the cumulative GRANGER-PARTIAL-MLB-NIGHT, scoped narrowly, with the explicit caveats above.

---

## Closing note on counts

KILLER findings: 3 (VWAP windowing unauthorized change; MLB-night offset-robustness gate severity vs signal strength; NBA NULL conflated between offset and windowing effects).

IMPORTANT findings: 6 (MLB-day under-power; block-bootstrap confirms MLB-night; NFL-B clean NULL; NBA gamma essentially zero at center; lock gate has no near-pass salvage; pooled F correctly omitted).

NICE-TO-HAVE findings: 3 (bootstrap convergence; floor language; hour-bucket comment misleading).

The 3 KILLER findings argue against the literal NULL-v12 verdict at the cumulative-project level. The lock-level verdict stands (NULL-v12). The cumulative-project verdict should be GRANGER-PARTIAL-MLB-NIGHT with operational scope as specified above.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
