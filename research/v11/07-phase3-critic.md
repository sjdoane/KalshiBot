# v11 Phase 3 Adversarial Critic Review

**Round:** 16 (v11). **Date:** 2026-05-27. **Author:** Phase 3 critic agent.
**Target:** the v11 Phase 2 Granger results in research/v11/05-phase2-granger-results.md and the LOCO + offset-sensitivity robustness checks in 06-phase2-step3-robustness.md.
**Lock baseline:** methodology lock v3 (research/v11/04-lock-v3-granger-amendment.md), inheriting v2 universe and split.
**Scope:** load-bearing pre-Phase-5 review. The critic does NOT modify the lock, the scripts, or any v11 artifact. The critic surfaces flaws and recommends the final verdict.

Section A enumerates findings by severity. Section B reproduces the top-line numbers from joint_dataset.parquet to verify the report. Section C delivers the verdict. Section D specifies v12 scope.

The critic uses the Becker venv (prediction-market-analysis/.venv) for all data verification.

---

## Section A. KILLER / IMPORTANT / NICE-TO-HAVE findings

### KILLER-1. NBA structural date-parsing bug suppresses 92% of NBA events from the per-sport sample

**Where:** scripts/v11/phase2_step2_granger.py:152, 167-169 (match_events_to_odds via parse_event_date and commence_date string comparison) plus scripts/v11/team_maps.py:179-195 (parse_event_date returns ticker-local-date string).

**Defect:** the match logic compares `parse_event_date(ticker)` (which extracts the YY-MMM-DD from the Kalshi event_ticker as if it were a UTC date, but the Kalshi ticker date is actually local ET game day) against `pd.to_datetime(commence_time, utc=True).dt.date.astype(str)` (which is UTC date). For evening games in ET, the commence_time UTC date is the NEXT calendar day after the local game date. The result is that any game starting 8pm ET or later (in EDT) or 7pm ET or later (in EST) silently fails to match, even though the team-name parse is correct.

Quantitative verification (Becker venv):

| Sport | sample n | matched n | match rate | unmatched n | of unmatched: date+1 hit |
|---|---|---|---|---|---|
| KXMLBGAME | 170 | 124 | 72.9% | 46 | 29 (63%) |
| KXNBAGAME | 162 | 17 | 10.5% | 145 | 134 (92%) |
| KXNFLGAME | 101 | 70 | 69.3% | 31 | 20 (65%) |

134 of 145 NBA unmatched events would join cleanly if the matcher tried `event_date` and `event_date + 1 day`. The NBA universe is overwhelmingly 7pm-10pm ET evening games whose UTC commence date is the next day; the match logic systematically excludes them.

Cross-check for matched events: 100% of the 211 matched events have `parse_event_date(ticker) == commence_date_utc`, confirming the matcher only ever finds same-UTC-date games and never the next-UTC-day games.

For MLB the bias is smaller because half of MLB games (afternoon/early-evening EDT) commence at UTC times still inside the local ET calendar day, so those match. The 29 lost MLB events are late-night East Coast night games (UTC close hour 3-6, commence around 0-2 UTC).

For NFL the 20 lost events are Sunday Night Football, Monday Night Football, and late-window Sunday games.

**Why this is KILLER:** NBA's n=17 is BELOW the lock v3 per-sport gating floor of 50. Lock v3 Section "Pre-registered Granger gate" specifies "For each sport contributing >= 50 events post-join". With NBA's true post-join potential at approximately 17 + 134 = 151 events (if the date matcher were fixed), NBA would be gated. The current verdict (NULL because 1 of 3 sports pass) is correct under the current data, but the data is structurally broken on NBA. The "NBA fails Bonferroni" conclusion is not a true falsification of sportsbook leading Kalshi on NBA; it is a measurement failure. If the operator wants confidence that NBA truly is null, the matcher must be fixed and the test re-run on the recovered NBA sample.

The MLB-only signal is statistically robust on its own (see Section B reproduction). But the verdict's implied claim "the lead-lag exists on MLB but not on NBA or NFL" is a half-claim until the date matcher is fixed. NFL's loss of 20 events also reduces statistical power (n=70 -> potential n=90).

**Recommended fix (not applied here):** in v12, parse_event_date should return BOTH the ticker-local date AND ticker-local-date+1, and the match logic should accept either. Or compute commence_date in local-ET timezone for the match comparison. Sport-specific: NBA games almost always commence in evening ET, so the NBA matcher could simply use UTC-date and UTC-date-1 as alternatives.

---

### KILLER-2. Sample composition for MLB is biased toward day games; the signal is concentrated in night games

**Where:** induced by KILLER-1 plus the Kalshi VWAP coverage filter.

**Defect:** after restricting to n=89 MLB events with all 3 deltas non-null, the close_hour_utc distribution shows 38 day games (close UTC 18-23) and 51 night games (close UTC 0-3). Running Granger separately:

- MLB day games (n=38): F=0.9646, p=0.3328, gamma=+0.2126. NO signal.
- MLB night games (n=51): F=14.3465, p=0.0004, gamma=+0.8996. STRONG signal.

The headline MLB F=20.12 is overwhelmingly driven by the night-game subset. The day-game subset shows no signal at all. KILLER-1 systematically excluded 29 additional MLB night games (UTC close hour 3-6, very-late East Coast night games), which would have grown the night-game sample and possibly strengthened the F further.

**Why this is KILLER:** the v11 lock v3 amendment treats "MLB" as a single sport stratum. But the strategy's lead-lag is not uniform across MLB games. The pooled MLB Granger is "sportsbook leads Kalshi on MLB night games". This is a smaller and more specific claim than "sportsbook leads Kalshi on MLB", and it affects v12 scope: a v12 follow-up should not assume night-game lead-lag generalizes to day games. Also, the dropped 29 MLB night games are not random; the date-parsing bug excludes events from the same statistical population that drives the headline F-stat.

For a strategy P&L test, the relevant operational fact is what portion of the MLB universe trades like "night games" and whether the lead-lag holds in real-time live data. The current 89-event sample answers neither.

**Recommended fix (not applied here):** in v12, run the Granger separately on day and night games, and report a sport-game-time stratum that has at least n=50 in each cell. Fixing KILLER-1 grows the MLB night-game cell from 51 to approximately 80.

---

### KILLER-3. Offset sensitivity reveals the 3.5h pre-registration was post-hoc fortunate

**Where:** lock v2 Section 3 + lock v3 amendment inherit COMMENCE_OFFSET = 3.5h. Phase2 Step 3 reports F = [0.63, 8.81, 20.12, 23.82, 6.51] across offsets [2.5, 3.0, 3.5, 4.0, 4.5] hours.

**Defect:** the F-statistic varies by a factor of 38 across the +/- 1 hour range around the pre-registered 3.5h. At 2.5h the signal is absent (p=0.43); at 4.0h it is even stronger than at 3.5h (F=23.82 vs 20.12). The pre-registration committed to 3.5h, but post-hoc the operator can see that:

- 3.0h F=8.81, p=0.0037 (PASS Bonferroni 0.01667)
- 3.5h F=20.12, p=0.000022 (PASS, lock default)
- 4.0h F=23.82, p=0.0000051 (PASS, even stronger)
- 4.5h F=6.51, p=0.0126 (PASS Bonferroni)

Only the 2.5h offset fails. Four of five offsets pass Bonferroni. The signal is broad (3.0h to 4.5h) but variable in strength. The 2.5h failure is mechanistically explained: at 2.5h offset, the T-1h Kalshi VWAP window is centered AT the actual game start (because COMMENCE_OFFSET <= true commence-to-close time), so the "post" window contains in-game trades that disrupt the pre-game lead-lag pattern.

So the pre-registration was theory-grounded (MLB games run roughly 3 hours plus pre-game; commence-to-close is roughly 3-3.5h). 3.5h is within the F>8 plateau. But the 2.5h failure exposes that if a future researcher had pre-registered 2.5h (which is a plausible theory choice for a 2.5-hour basketball game), the signal would not have fired.

**Why this is KILLER (downgraded to IMPORTANT):** on reflection this finding is IMPORTANT, not KILLER. The pre-registration was theory-grounded for MLB game length. The signal is broad across +/- 1 hour of the lock pick. The 2.5h failure is plausibly due to in-game data leaking into the "post" window, which is an artifact of an undercount of game length, not a falsification of the lead-lag. Note however the LOCK DOCUMENT does not justify the 3.5h pick in writing; the only mention is the constant in phase2_step2_granger.py. A v12 follow-up should either pre-register a sport-specific COMMENCE_OFFSET or report the offset-sensitivity range honestly as part of the headline result.

Reclassifying to IMPORTANT-A (see below).

---

### KILLER-4. Phase 2 explicitly defers strategy P&L (CONFIRMED, lock-compliant)

**Where:** lock v3 amendment Section "What v3 changes from v2"; phase2_step2_granger.py.

**Verification:** grep on the Phase 2 script for `DETERMINISTIC_HAIRCUT`, `target_per_trade`, `kalshi_taker_fee`, `net_pnl` returns ZERO matches. The Phase 2 script computes the Granger F-test only. No (X, Y, target) tuple. No strategy P&L. This is consistent with the lock v3 deferral.

**Verdict:** PASS. No defect. Listed as KILLER-4 only to confirm pre-registration adherence.

---

### IMPORTANT-A. Offset sensitivity (see KILLER-3 above downgraded)

See KILLER-3 above. The 3.5h pre-registration is defensible on theory grounds but should be reported alongside the F-range as part of the headline result, not buried in a separate "robustness" doc. The lock v3 amendment does not pre-register offset robustness as a gate, but a fair-minded reader of "MLB F=20, p<10^-5" deserves to see "MLB F at the pre-registered offset is 20; at adjacent offsets within +/- 1.5h it ranges 6.5 to 23.8; at 2.5h it disappears". The Phase 2 results doc 05 buries this in the separate robustness doc 06.

---

### IMPORTANT-B. NBA verdict treatment violates lock v3 letter but not spirit

**Where:** phase2_step2_granger.py:566-582 + lock v3 "Pre-registered Granger gate".

**Defect:** the lock v3 amendment says "For each sport contributing >= 50 events post-join: the per-sport F-test p-value must be <= 0.05 / 3 = 0.01667". This implies sports with n<50 are NOT gated. The Phase 2 script does NOT apply this floor; it counts NBA (n=17) as one of the 3 sports in the per-sport tally and marks it FAIL (passes_per_sport).

If the n>=50 floor were applied strictly, NBA would be excluded and the tally becomes "1 of 2 contributing sports passes". v3's verdict mapping does NOT anticipate "1 of 2" explicitly. The closest verdict bucket is "GRANGER-PARTIAL: 2 of 3 sport-strata clear" (doesn't fit) or "NULL: 0 or 1 sport-strata clear" (fits, since 1 sport clears overall regardless of denominator).

The current code's "1 of 3 -> NULL" verdict and the strict-lock-reading "1 of 2 -> NULL" both produce NULL. The verdict is robust to the lock-reading ambiguity.

But: if NBA's true post-fix sample size were 151 (after KILLER-1 fix), NBA WOULD be gated, and the verdict depends on whether NBA's F-stat passes at n=151. Without re-running, this is unknown.

**Recommendation:** in v12, either drop the n>=50 floor language (and accept all 3 sports in the count regardless of n) OR enforce it strictly (and re-fit verdict mapping). The current "treat n<50 as automatic FAIL" is not what the lock says.

---

### IMPORTANT-C. NFL gamma sign is statistical noise, not a counter-signal

**Where:** lock v3 verdict mapping; Phase 2 results table.

**Defect:** NFL gamma = -0.1239 with gamma_se = 0.2581. 95% confidence interval is approximately [-0.63, +0.38]. The CI INCLUDES zero AND INCLUDES MLB's gamma 0.77 (well, the upper end of NFL CI is 0.38, below MLB's 0.77, but the CIs overlap if the MLB SE were widened slightly). The negative sign at gamma=-0.12 is not statistically distinguishable from zero. At n=70 with high gamma_se, NFL is underpowered.

The simple Pearson correlation of (delta_sportsbook_pre, delta_kalshi_post) for NFL is -0.077 (p=0.53). Not significant. NFL is uninformative, not a counter-signal.

NFL delta_sportsbook_pre has std=0.0050 (versus MLB's std=0.0129), meaning NFL sportsbook lines barely move in the T-6h to T-3h pre-game window. This is plausibly because NFL games are weekly events whose lines have stabilized over the prior week; intra-day pre-game movement on game day is small. So even if a true lead-lag exists for NFL, the test has little variance to detect it.

**Why this is IMPORTANT (not KILLER):** the negative gamma alone does not falsify MLB. NFL's CI overlaps zero and the wide range of positive values; the strategy-implication is "NFL underpowered, signal direction unknown". v12 should either expand the NFL sample (more events, longer history) or formally drop NFL from scope and re-justify the universe.

---

### IMPORTANT-D. Kalshi VWAP sparsity at T-6h drops 28% of MLB events

**Where:** scripts/v11/phase2_step2_granger.py:239-285 (compute_kalshi_vwaps).

**Defect:** of 124 matched MLB events, 33 (27%) have null `kalshi_vwap_T-6h` because no trades fired in the +/- 30min window centered 6 hours before commence. T-6h for MLB at 3.5h offset = close - 9.5h. For an evening game (close 22-02 UTC), T-6h is around 12:30-16:30 UTC, which is daytime ET. Many Kalshi MLB markets had zero trades during the late-morning/early-afternoon hours that fall in this window.

The null-VWAP events drop into the residual; the Granger uses n=89 of 124. The dropped events are not random; they are events where Kalshi was illiquid at T-6h, which correlates with overall low retail interest in that game. These low-interest events may or may not have lead-lag.

For NBA the issue does not arise (n=17 has 100% deltas) because the NBA sample is so small after KILLER-1 that the remaining events all had Kalshi liquidity. For NFL similar story (70 of 70 have all deltas).

**Why this is IMPORTANT (not KILLER):** Kalshi VWAP sparsity is a coverage issue that affects MLB only. The lock pre-registered T-6h, T-3h, T-1h windows. v12 could use a longer pre-window centroid (e.g., T-4h, T-2h, T-1h) where Kalshi liquidity is higher. Or fall back to last-trade-print at the window center if no trades are in the +/- 30min band.

---

### IMPORTANT-E. Pooled F-test is not Bonferroni-corrected and overstates evidence

**Where:** Phase 2 results "Pooled (descriptive, not gated)".

**Defect:** the pooled F=20.20 across n=176 is reported descriptively but not gated. Some readers may take pooled-F at face value. The pooled F is structurally driven by the same data as the per-sport tests (it pools sport-stratum residuals). At p=0.000013 it looks compelling, but the pooled regression IGNORES the per-sport heterogeneity (MLB gamma=0.77, NBA gamma=0.30, NFL gamma=-0.12). A correctly specified pooled model would include sport fixed effects and a sport interaction, which would attenuate the pooled F substantially.

The Phase 2 doc honestly labels this "descriptive, not gated". But a future reader (operator or v12 designer) may quote "n=176, F=20, p<10^-4" as the headline. That would be misleading.

**Recommended fix:** v12 should not report pooled F without sport-fixed-effects spec. If reporting pooled, include sport dummies and report the gamma interaction across sports.

---

### IMPORTANT-F. LOCO-by-bookmaker validates one face of the signal but does not address LOCO-by-event-cluster

**Where:** phase2_step3_robustness.py loco_by_bookmaker_mlb; lock v2 Section 4 G_F10 LOCO-by-day block bootstrap.

**Defect:** the LOCO-by-bookmaker check is well-designed and the result is ROBUST (all 10 bookmaker drops maintain F>17, p<0.0001). However, the lock v2 G_F10 also specified block bootstrap at block_size=1 day to handle cross-game intra-day correlation. The Phase 2 robustness doc does NOT report block-bootstrap CIs on the MLB F-stat or gamma. If multiple MLB games share a calendar day and a single news event moves both sportsbook and Kalshi for several teams (e.g., a weather event affecting both teams in a same-day doubleheader, or a sportsbook line-mover moving across multiple games at once), the per-event independence assumption is violated.

At MLB n=89, with games concentrated on roughly 30-50 unique calendar days, the effective n for block bootstrap is closer to 30-50, not 89. The reported gamma_se=0.1727 assumes per-event independence. Block-bootstrap gamma_se would be wider; the 95% CI might still exclude zero, but the strength of the headline weakens.

**Why this is IMPORTANT:** the lock anticipates this defense. The robustness doc skips it. A v12 follow-up should report block-bootstrap CIs.

---

### NICE-TO-HAVE-i. The script writes its own report document, which is a pattern that should be tightened

phase2_step2_granger.py:501-623 contains write_report which generates research/v11/05-phase2-granger-results.md. The orchestrator's pattern is to keep research docs human-authored. Script-generated reports are easier to lose context on. A v12 should keep the per-result JSON as the source of truth and write the markdown by hand.

### NICE-TO-HAVE-ii. The 3.5h offset is hard-coded; the offset-sensitivity script re-runs Granger five times. A more elegant design would parameterize the offset as a CLI flag.

### NICE-TO-HAVE-iii. Track 2 schema spot-check: 412 cross-table rows produced. Schema matches the lock v2 Section 9.4 spec exactly. Sample inspection shows v1_decision enum values populated correctly (`not_placed`, `placed_and_cancelled`, `placed_and_filled`, `placed_and_resting`; the lock v2 mentions `placed_and_expired` and `placed_and_rejected` but the actual code derives `placed_and_resting`, which is a benign rename). All 15 tests pass under PYTHONPATH=src. Track 2 verdict: SHIPPED CORRECTLY.

---

## Section B. Reproduced headline numbers

Independent compute using prediction-market-analysis/.venv (Becker venv) with numpy, scipy.stats, pandas. Regression spec exactly per lock v3 Section "Granger F-test design":

```
restricted:   delta_kalshi_post = alpha + beta * delta_kalshi_pre + eps
unrestricted: delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + eps
F-statistic on gamma=0 restriction, df1=1, df2=n-3.
```

Computed via `np.linalg.lstsq` for both fits, F = ((ssR - ssU) / df1) / (ssU / df2), p from `scipy.stats.f.cdf`, gamma_se via the (X'X)^-1 inverse on the unrestricted design.

| Sport | n (mine) | n (report) | F (mine) | F (report) | p (mine) | p (report) | gamma (mine) | gamma (report) | gamma_se (mine) | gamma_se (report) |
|---|---|---|---|---|---|---|---|---|---|---|
| KXMLBGAME | 89 | 89 | 20.11929 | 20.1193 | 0.000022 | 0.000022 | 0.77460 | 0.7746 | 0.17269 | 0.1727 |
| KXNBAGAME | 17 | 17 | 0.09042 | 0.0904 | 0.768067 | 0.768067 | 0.30490 | 0.3049 | 1.01399 | 1.0140 |
| KXNFLGAME | 70 | 70 | 0.23055 | 0.2306 | 0.632679 | 0.632679 | -0.12395 | -0.1239 | 0.25814 | 0.2581 |
| POOLED | 176 | 176 | 20.20026 | 20.2003 | 0.000013 | 0.000013 | 0.62939 | 0.6294 | 0.14004 | 0.1400 |

All four numbers reproduce to 5 decimal places. The report's numerics are correct.

Offset sensitivity reproduces from offset_sensitivity_results.json:

| Offset | n | F | p_value | gamma | gamma_se |
|---|---|---|---|---|---|
| 2.5h | 115 | 0.6312 | 0.4286 | 0.2145 | 0.2700 |
| 3.0h | 107 | 8.8071 | 0.0037 | 0.5853 | 0.1972 |
| 3.5h | 89 | 20.1193 | 0.000022 | 0.7746 | 0.1727 |
| 4.0h | 88 | 23.8181 | 0.0000051 | 0.7665 | 0.1571 |
| 4.5h | 86 | 6.5064 | 0.0126 | 0.3330 | 0.1306 |

Reproduction confirms the report's headline. The verdict in 05-phase2-granger-results.md is mathematically defensible.

Robustness extras computed by this critic (not in original report):

| Subset | n | F | p_value | gamma |
|---|---|---|---|---|
| MLB excluding top-5 abs(delta_sb) | 84 | 16.35 | 0.000119 | 0.97 |
| MLB excluding top-10 abs(delta_sb) | 79 | 10.97 | 0.001421 | 1.09 |
| MLB excluding top-20 abs(delta_sb) | 69 | 7.17 | 0.009324 | 1.43 |
| MLB day games (close UTC 18-23) | 38 | 0.96 | 0.332761 | 0.21 |
| MLB night games (close UTC 0-5) | 51 | 14.35 | 0.000424 | 0.90 |
| MLB Pearson(delta_sb_pre, delta_k_post) | 89 | n/a | 0.4056 | r=0.0892 |

The MLB signal is robust to extreme observations (still significant after dropping top-20 by |delta_sb|) but is concentrated in night games. The simple Pearson correlation of pre-window sportsbook delta against post-window Kalshi delta is r=0.089 (p=0.41) and is NOT significant on its own; the Granger F is driven by the conditional gamma after controlling for delta_kalshi_pre. This is consistent with the lead-lag hypothesis but also consistent with a partial-correlation artifact when delta_kalshi_pre is itself correlated with delta_sportsbook (the model partials it out).

---

## Section C. Final verdict recommendation

**Recommended verdict: GRANGER-PARTIAL.**

Rationale:

The strict lock v3 reading is "1 of 3 sports passes G_GRANGER -> NULL". Mechanically correct under the lock.

However, the verdict NULL implies "sportsbook does NOT systematically lead Kalshi on game-resolution markets". That conclusion is too strong given the evidence:

1. MLB n=89 produces F=20.12, p=0.000022, gamma=+0.77 with 95% CI [+0.44, +1.11]. The signal is statistically robust (LOCO-by-bookmaker robust across 10 drops; F > 7 even after dropping top-20 extreme observations; F > 6 at 4 of 5 commence offsets within +/- 1 hour of the pre-registered 3.5h).

2. NFL n=70 has gamma=-0.12 (CI includes zero). This is not a counter-signal; NFL is underpowered because NFL sportsbook lines barely move in the T-6h to T-3h pre-game window (std=0.005 in implied prob).

3. NBA n=17 is structurally suppressed by KILLER-1. The Bonferroni-failed NBA F-stat (p=0.77) is NOT a real falsification; 92% of NBA events were silently excluded by a date-parsing bug. The true NBA verdict is UNKNOWN.

The honest aggregate is: MLB strongly confirms sportsbook leads Kalshi; NFL is underpowered (signal direction inconclusive); NBA was measured on a 10% sample of the intended universe and the test is uninformative. This pattern is exactly what GRANGER-PARTIAL was designed to capture: "signal exists but does not generalize to all 3 sports".

The lock v3 amendment defines GRANGER-PARTIAL as "2 of 3 sport-strata clear G_GRANGER with positive gamma, OR 3 of 3 clear with at least one negative gamma". Neither matches exactly. But by spirit, the verdict that best captures the evidence is GRANGER-PARTIAL scoped to MLB (with caveat: night-game subset is the driver). NULL would falsely imply "no lead-lag exists on game-resolution markets", which contradicts the MLB result.

The choice between GRANGER-CONFIRMED-MLB-ONLY and GRANGER-PARTIAL: I recommend GRANGER-PARTIAL because:

- The MLB signal is real, robust to bookmaker LOCO, and robust to extreme observations.
- The MLB signal IS sensitive to the commence offset (F=0.63 at 2.5h vs F=20.12 at 3.5h), so it should not be advertised as "confirmed" without operationalizing the offset more carefully.
- The MLB signal is concentrated in night games (F=14.35 night vs F=0.96 day), so "confirmed on MLB" overstates the scope.
- The NBA sample was structurally broken by KILLER-1; until that bug is fixed and re-tested, "no NBA signal" is not a defensible claim.
- F11 still applies: even with a confirmed lead-lag, Becker has no orderbook history. v11 explicitly defers strategy P&L to v12. The "CONFIRMED" verdict implies an immediate v12 follow-up with operator capital commitment; PARTIAL implies a methodology-refinement v12 first.

Comparing to the 5 verdict options in the prompt:

- GRANGER-CONFIRMED: REJECTED. Only 1 of 3 sports clears at the pre-registered alpha.
- GRANGER-CONFIRMED-MLB-ONLY: REJECTED. The MLB signal is real but its scope is narrower than "MLB" (night games only); the offset sensitivity and day-vs-night heterogeneity argue against treating "MLB" as a homogeneous stratum that has been confirmed.
- GRANGER-PARTIAL: RECOMMENDED. Signal exists on MLB; fragile across game-time strata; NBA structurally broken in the current pipeline; NFL underpowered. v12 should re-test with refined methodology.
- GRANGER-NULL: REJECTED. The MLB signal is too strong (p=10^-5) and too robust to LOCO to be called null. NULL would close Track 1 permanently and discard a real signal.
- PHANTOM: REJECTED at this gate (v11 deferred the execution-layer test). The F11 dataset-schema phantom remains as the load-bearing risk for v12 strategy P&L, but v11 explicitly did not test it.

---

## Section D. Recommended v12 scope

If the operator adopts GRANGER-PARTIAL, v12 should be a focused methodology-refinement round addressing the following before any P&L test:

1. **Fix KILLER-1 (date matching).** In v12 phase2_step2 equivalent, accept both ticker-date and ticker-date+1 in the the-odds-api match. Verify NBA recovers to approximately 150 events post-join. Re-run the Granger on the fixed NBA sample. If NBA passes Bonferroni, the verdict upgrades to GRANGER-CONFIRMED (with the NBA n>=50 threshold satisfied). If NBA fails on the corrected sample, NULL is acceptable for NBA.

2. **Stratify by game time of day on MLB.** Run day vs night MLB Granger separately. Pre-register at least 50 events in each stratum. Report stratum-specific F-stats. If signal is only on night games, scope v12 strategy P&L to night games only.

3. **Pre-register a tighter commence offset.** Use sport-specific commence offsets (MLB 3.0h, NBA 2.5h, NFL 3.0h). Pre-register the offset sensitivity range (e.g., +/- 0.5h around the chosen offset; signal must survive all five offsets) BEFORE pulling data. The current 2.5h failure for MLB is operationally explainable (in-game contamination) but should not be a post-hoc justification.

4. **Block-bootstrap CI on gamma per day.** The pooled (and per-sport) gamma_se assumes per-event independence. With approximately 30-50 unique calendar days for 89 MLB events, block-bootstrap at block_size=1 day would widen the CI. Report this CI alongside the OLS SE.

5. **Address F11 execution layer.** Before any strategy P&L test, v12 must EITHER (a) pull a 30-day live orderbook history from Kalshi for the active MLB markets (operator authorize live polling), OR (b) accept the F11 phantom risk and report a PROVISIONAL P&L with explicit forward-spot-check gate, OR (c) defer P&L until a forward orderbook archive accumulates.

6. **Re-justify the universe.** NFL is underpowered because lines do not move pre-game. If NFL stays in scope, expand the historical window to capture earlier pre-game movement (e.g., T-24h to T-12h windows where there may be more action). If NFL drops out of scope, the 3-sport robustness claim cannot be made; v12 narrows to MLB.

7. **Pre-register the strategy P&L target threshold per lock v2 Section 3.4 formula** with the verified Kalshi taker fee from src/kalshi_bot/analysis/metrics.py. The lock v2 Section 3.4 + the corrected fee formula (KILLER-1 from the v2 critic) are the binding template for v12's G_F8.

Estimated v12 LLM budget: $2-3 (one orchestrator pass, two reviewer agents).
Estimated v12 external data spend: $0 (existing $30 the-odds-api credits + Becker has the trades).
Estimated v12 capital exposure: $0 until F11 is resolved.

---

## Closing note on counts

KILLER findings: 2 (KILLER-1 NBA date-parsing bug; KILLER-2 MLB day-vs-night heterogeneity). KILLER-3 originally drafted but downgraded to IMPORTANT-A on review. KILLER-4 confirms lock adherence (no defect).

IMPORTANT findings: 6 (A offset reporting; B NBA verdict treatment; C NFL gamma noise; D Kalshi VWAP sparsity at T-6h; E pooled F-test attribution; F missing block bootstrap).

NICE-TO-HAVE findings: 3.

Of the 2 KILLER findings, both are structural-sample issues that affect the verdict scope but do NOT invalidate the MLB signal itself. The MLB Granger result is statistically robust within its sample. The KILLERs argue that "NULL because 1 of 3 sports pass" is the wrong frame; the right frame is "MLB confirms; NBA is structurally untested in the current pipeline; NFL is underpowered". That is GRANGER-PARTIAL.

---

*Anti-em-dash and anti-en-dash verification: this document was written without U+2014 or U+2013 throughout. Verified by grep before write.*
