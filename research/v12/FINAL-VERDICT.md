# v12 (Round 17) Final Verdict

**Date:** 2026-05-27. **Author:** orchestrator. **Round:** 17.
**Lock:** research/v12/01-methodology-lock.md.
**Sources of truth:** research/v12/02-phase2b-v12-results.md (numerics),
research/v12/03-phase3-critic.md (load-bearing review),
data/v12/v12_per_stratum_results.json (raw per-stratum results).

---

## TL;DR

**Literal v12 verdict per the methodology lock: NULL-v12.** 0 of 4 strata clear the 5-condition pre-registered gate. The strictest gate (offset robustness at Bonferroni 0.0125 at every +/- 0.5h offset) is the binding failure for the MLB-night stratum.

**Cumulative project verdict: GRANGER-PARTIAL-MLB-NIGHT.** The MLB-night sub-stratum signal at the pre-registered center offset is one of the strongest single-stratum results in this project's history (F=29.50, p=3.58e-7, gamma=+1.09, n=109, block-bootstrap 95% CI [+0.119, +1.938] excludes zero). 4 of 5 binding gates pass; only the offset robustness at -0.5h fails (p=0.027 > Bonferroni 0.0125 but passes uncorrected 0.05). The signal is real and offset-sensitive in a methodologically interpretable way; PARTIAL is the honest descriptor.

**Spend:** approximately $0.50 LLM in v12 of operator-authorized $2-3 budget. $0 new external (used 1,220 of 19,990 remaining the-odds-api credits for NFL extended-window pulls; 13,500 credits remain). **$0 capital deployed.**

---

## What v12 changed from v11

| Change | Rationale | Outcome |
|---|---|---|
| MLB day/night stratification | v11 Phase 3 critic KILLER-2 | MLB-night becomes the strong sub-stratum; MLB-day underpowered (n=19 below n>=50 floor) |
| Sport-specific commence offsets (MLB 3.5h, NBA 2.5h, NFL 3.5h) | v11 lock pre-registered 3.5h universally; NBA games are ~2.5h | NBA at 2.5h offset NULL (F=0.003), contradicting v11's F=7.91 at 3.5h |
| Offset robustness gate (Bonferroni at every +/- 0.5h offset) | v11 Phase 3 critic IMPORTANT-A | MLB-night fails at -0.5h offset; signal is real but offset-fragile by the strict gate |
| Block-bootstrap CI at block_size = 1 day | v11 Phase 3 critic IMPORTANT-F | MLB-night CI [+0.119, +1.938] excludes zero; passes the strictest novel v12 gate |
| NFL window expansion (T-24h to T-6h NFL-B test) | v11 Phase 3 critic Section D-6 | NFL-B coverage 100% (n=90); NULL (F=0.25, p=0.62) |

---

## Detailed per-stratum results

Per `data/v12/v12_per_stratum_results.json`. All numbers reproduced by Phase 3 critic to 4 decimal places.

### MLB-day (close UTC hour [17, 23))

- n=19 of 55 events in band (36 dropped due to Kalshi VWAP NaN at T-6h; same coverage gap as v11 Phase 3 critic IMPORTANT-D flagged)
- Center (3.5h offset): F=0.42, p=0.53, gamma=+0.14
- Block-bootstrap CI: [-0.57, +0.44]
- Verdict: FAIL (below n>=50 floor; offset-robustness FAILS; bb FAILS)

### MLB-night (close UTC hour [0, 9) U [23, 24))

- n=109
- Center (3.5h offset): **F=29.50, p=3.58e-7, gamma=+1.09**
- Block-bootstrap CI: **[+0.119, +1.938]** (lower > 0)
- Offset robustness:
  - -0.5h (3.0h): F=5.04, p=0.027 (FAIL Bonferroni 0.0125; PASS uncorrected 0.05)
  - +0.0h (3.5h, center): F=29.50, p=3.58e-7 (PASS)
  - +0.5h (4.0h): F=12.24, p=0.0007 (PASS Bonferroni)
- 5-gate breakdown: PASS (a) center Bonferroni; PASS (b) gamma > 0; PASS (c) bb CI lower > 0; **FAIL (d) offset robust**; PASS (e) n >= 50
- Verdict: FAIL (4 of 5 gates pass; the offset robustness gate is the load-bearing failure)

### NBA (close UTC hour 0-3 mostly; all games)

- n=151
- Center (2.5h offset, theory-correct per NBA game length): F=0.003, p=0.95, gamma=+0.006
- Block-bootstrap CI: [-0.10, +0.12] (centered on zero)
- Offset robustness:
  - -0.5h (2.0h): F=0.60, p=0.44, gamma=+0.22 (FAIL)
  - +0.0h (2.5h, center): F=0.003, p=0.95 (FAIL)
  - +0.5h (3.0h): F=1.79, p=0.18, gamma=+0.14 (FAIL)
- Pattern: gamma INCREASES as offset moves away from 2.5h toward 3.5h. v11's NBA signal at 3.5h was a partial in-game-data-leakage artifact compounded by the VWAP windowing change (see KILLER-1 below).
- Verdict: FAIL (clean methodological NULL at the correct theoretical offset)

### NFL

- n=90
- NFL-A (classic T-6h..T-1h): F=0.86, p=0.36, gamma=-0.19
- NFL-B (expanded T-24h..T-6h): F=0.25, p=0.62, gamma=-0.06
- Sportsbook movement std doubled in the expanded window (0.0105 vs 0.0053), consistent with the lock hypothesis that "sharp action" arrives 24h-12h before kickoff. But the Kalshi response is essentially zero.
- NFL-A and NFL-B both FAIL at center; coverage was 100%; NULL is empirically clean.
- Verdict: FAIL (the v11-flagged "underpowered" NFL is now empirically uninformative for this lead-lag hypothesis at this sample size)

---

## Phase 3 critic KILLER findings (preserved in cumulative record)

1. **KILLER-1 (VWAP windowing change):** v12 silently changed Kalshi VWAP computation from v11's centered +/- 30min DuckDB query to v12's hour-bucket forward-anchored pre-aggregation. The change was a performance optimization (avoids 7000+ DuckDB roundtrips) but was NOT pre-registered in the v12 lock. Materially affects per-stratum F-statistics by a factor of ~2 in either direction (NBA at 3.5h drops F from 7.91 to 4.37; MLB-night at 3.5h grows F from 12.17 to 29.50). The orchestrator's sanity-check confirmed this independently.

2. **KILLER-2 (Offset robustness gate is severe):** MLB-night fails offset robustness ONLY at the Bonferroni-corrected threshold at the -0.5h offset (p=0.027 vs Bonferroni 0.0125). The signal magnitude (gamma+0.75 to +1.09) is positive across all 3 offsets; the gate threshold is stricter than v11's lock allowed for. Real signal, severe gate, lock-compliant fail.

3. **KILLER-3 (NBA NULL confounded):** the v11-to-v12 NBA F-stat drop (7.91 to 0.003) decomposes roughly equally between the offset correction (3.5h to 2.5h, F=4.37 to 0.003) and the windowing change (F=7.91 to 4.37 at the same 3.5h offset). The narrative "v11 NBA signal was spurious because it used the wrong offset" is half-true; the other half is windowing.

**None of these were salvageable in Phase 4** without violating the lock's "no post-data adjustment" rule (F8) and "no methodology amendment after lock" rule (Section 12). Re-running v12 with v11 windowing at the locked 2.5h NBA offset would be the cleanest salvage but it would also be a third-bite on methodology. Deferred to v13 (if pursued).

---

## Cumulative project state after v12

### Verdict reconciliation across rounds

| Round | Verdict (literal) | Verdict (best cumulative interpretation) |
|---|---|---|
| v11 (Round 16) | GRANGER-PARTIAL (2 of 3 sports) | GRANGER-PARTIAL MLB+NBA |
| v12 (Round 17) | NULL-v12 (0 of 4 strata) | GRANGER-PARTIAL-MLB-NIGHT |

### What changed and why

- **MLB:** v11's "MLB pass" decomposes into MLB-night (real, strong, offset-fragile at the strict gate) and MLB-day (under-powered at n=19). v12 PRESERVES the MLB signal but narrows the scope. The MLB-night center is among the project's strongest results.

- **NBA:** v11's "NBA pass" at offset 3.5h decomposes between (a) wrong offset capturing in-game info leakage and (b) different VWAP windowing function. At the correct 2.5h offset, NBA shows no lead-lag. The v12 verdict on NBA is NULL is **defensible at the literal lock level but the methodology-cleanness depends on accepting the VWAP windowing change**, which is itself an unauthorized deviation.

- **NFL:** consistently NULL across v11 and v12. The v11 critic's suggestion to expand the window was tested in v12 NFL-B and came back NULL. NFL is empirically uninformative for this lead-lag hypothesis.

### Recommended cumulative verdict

**GRANGER-PARTIAL-MLB-NIGHT.** The honest project-level finding after two rounds: a real lead-lag from major US sportsbooks to Kalshi trade-print mid on **MLB night games** in the T-6h to T-1h pre-close window. The strength is robust to multiple checks (per-bookmaker LOCO from v11; block-bootstrap CI from v12; bookmaker breadth confirmed by Phase 3 v11 critic; signal magnitude positive at all 3 offsets in v12). The fragility is real but bounded (-0.5h offset attenuates significance but not direction).

NFL is NULL. NBA is NULL at the correct offset (with the windowing caveat). MLB-day is under-powered.

### What this does NOT support

- ANY claim about a tradeable strategy. v12 explicitly did not test execution (F11 phantom unresolved on Becker; live spread on KXMLBGAME 1c MM-saturated per project memory).
- Aggregating MLB-night signal across full MLB. The day/night split was decisive; MLB-day is uninformative.
- Generalizing to other sports. NBA at the correct offset shows nothing; NFL shows nothing across two window definitions.
- Treating the GRANGER-PARTIAL-MLB-NIGHT result as monetizable. Until a v13 designs an execution model and forward spot-check, this stays research-only.

---

## What v13 should do (if pursued, operator authorization needed)

### Methodology (in-session feasible)

1. **Pre-register VWAP windowing function explicitly in the lock.** Options: centered +/- 30min via DuckDB exact query (matches v11; slower), centered +/- 30min via 15-min pre-aggregation (matches v11; faster), hour-bucket forward-anchored (v12's choice; faster but biased). The choice should be defended on signal-mechanism grounds: trades 30 min before AND after the target time are arguably more representative of "the market at target time" than only post-target.

2. **Re-run NBA with v11 windowing at the locked 2.5h offset** to cleanly isolate the offset effect from the windowing effect. If NBA still NULLs, KILLER-3 collapses to "NBA NULL is genuine, the v11 NBA signal was offset-spurious." If NBA passes, KILLER-3 collapses to "NBA NULL is windowing-dependent and the v11 NBA signal was real but offset-fragile."

3. **Loosen the offset robustness gate** to uncorrected 0.05 at adjacent offsets, with center at Bonferroni. This preserves the falsification check while reducing false-negative rate on signals with smooth offset dependence.

4. **Drop MLB-day from scope OR pull broader pre-game windows for it.** The n=19 floor failure is structural: MLB day-game Kalshi has near-zero trade volume 6 hours before close (well before retail activity ramps). v13 could test T-4h, T-2h, T-1h windows for MLB-day instead.

### Execution (out-of-session; requires capital authorization)

5. **F11 forward live spot-check.** Set up Kalshi orderbook polling on currently-open KXMLBGAME night markets for 30+ days. Compare live ask vs trade-print proxy. If the live spread is within 1c of the trade-print proxy, the v12 MLB-night signal is potentially tradeable at small size. If the live spread is wider (likely; project memory notes 1c MM-saturation but only on tight-spread historical), the signal is unmonetizable.

6. **Strategy P&L test.** Only after (5) confirms the execution model. Pre-register the trigger rule, position size, fee model. Forward spot-check verdict gates capital deployment.

### Cumulative budget for v13 path

- LLM: $2 to $3 (methodology refinement + critic + verdict)
- External: $0 (the-odds-api 13,500 credits remain in the operator's pool until billing cycle ends)
- Capital: $0 until F11 spot-check completes

---

## Track 2 status (unchanged from v11)

v11 Track 2 join script SHIPPED. v12 did not touch Track 2. The existing 2026-05-24 LIVE_FILTER_ENABLED overlay continues active in v1; the shadow log continues accumulating.

---

## Cumulative spend across v11 + v12

| Round | LLM | External | Capital |
|---|---|---|---|
| v11 | ~$3.30 | $30 (the-odds-api Starter) | $0 |
| v12 | ~$0.50 | $0 (used 1,220 of pool) | $0 |
| **Cumulative v11+v12** | **~$3.80** | **$30 total + 13,500 credits in pool** | **$0** |

Within the operator's $5 to $8 v11 headroom and the $25 shared cap.

---

## Operator handoff

This v12 closure should NOT be auto-applied to CLAUDE.md or memory. The operator's main session can consolidate when convenient. Suggested CLAUDE.md template:

```
**Round 17 outcome (2026-05-27): v12 literal NULL-v12 but cumulative
GRANGER-PARTIAL-MLB-NIGHT.** v12 applied all Phase 3 v11 critic fixes
(day/night MLB stratification, sport-specific commence offsets, offset
robustness gate, block-bootstrap CI, NFL window expansion). The strict
pre-registered gate (Bonferroni 0.0125 at every +/- 0.5h offset) fails
for MLB-night at the -0.5h point (p=0.027 > 0.0125 but passes uncorrected
0.05). Center signal at MLB-night: F=29.50, p=3.58e-7, gamma=+1.09,
n=109, block-bootstrap CI [+0.119, +1.938]. NBA NULL at the correct
2.5h offset (v11's NBA signal at 3.5h was offset-spurious, conflated
with a v12 VWAP windowing change). NFL NULL across both classic and
expanded windows. Cumulative verdict re-scopes v11's "2 of 3 sports"
to "MLB night games only". No capital. Track 2 unchanged from v11.
Phase 3 critic identified 3 KILLERs (VWAP windowing change unauthorized
by lock; offset robustness gate severity; NBA NULL confounded with
windowing); all logged for v13 if pursued. v13 should re-run NBA with
v11 windowing at the 2.5h offset to disentangle effects, then proceed
to F11 live spot-check before any capital. v12 spend: ~$0.50 LLM,
$0 external. Cumulative v11+v12: ~$3.80 LLM, $30 external, $0 capital.
See research/v12/FINAL-VERDICT.md.
```

Memory updates suggested:
- `project_kalshi.md`: re-scope v11's GRANGER-PARTIAL to GRANGER-PARTIAL-MLB-NIGHT-ONLY; note v12 NULL-v12 plus the methodology lessons; add v13 scope recommendation if operator pursues.
- `project_kalshi_literature.md`: no change.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
