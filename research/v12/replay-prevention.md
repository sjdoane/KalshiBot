# v12 Replay-Prevention Notes for Cumulative Failure-Mode Taxonomy

**Round:** 17 (v12). **Date:** 2026-05-27.
**Inherits:** v11 replay-prevention.md (F1-tz-mismatch + operational lessons L1 and L2).

v12 did NOT discover a new top-level failure mode. It DID surface two new instances and one new operational lesson worth adding for v13.

---

## New instance of F8 (Gate-regime mismatch)

### F8-vwap-windowing-silent-change: re-implementing a derived feature differently between rounds

Surfaced by Phase 3 v12 critic KILLER-1. The v11 codebase used a centered +/- 30min DuckDB query for Kalshi VWAP at each target time. The v12 codebase optimized this to a forward-anchored hour-bucket pre-aggregation. The change was an unflagged performance optimization, not a deliberate methodology amendment.

Impact: for the same data at the same offset, F-statistic shifts by a factor of ~2 in either direction depending on stratum. NBA at 3.5h offset drops from F=7.91 (v11 windowing) to F=4.37 (v12 windowing). MLB-night at 3.5h offset grows from F=12.17 to F=29.50.

**Why this is F8 (not F11):** the FIELD exists in both rounds (Kalshi trades with prices). The dataset SCHEMA is unchanged. The change is in how the field is AGGREGATED into a derived feature. F8 covers "gate-regime mismatch" which includes "computing the same gate input differently across rounds without flagging the change."

**Replay check for future rounds:** when a v_n codebase derives a feature from raw data, the v_{n+1} codebase MUST either (a) reuse the v_n implementation exactly, OR (b) implement a different aggregation BUT pre-register the change in the methodology lock with rationale. Silent re-implementation is a lock violation.

**Concretely for v13:** if v13 wants to use v12's hour-bucket VWAP (faster), the v13 lock must explicitly pre-register this and explain the bias direction (forward-anchored means a target at HH:42 includes 42min of pre-target trades and 18min of post-target trades, vs v11's centered which uses 30/30).

---

## New instance of F10 (LOO / LOCO fragility)

### F10-offset-robustness-severity: a robustness gate at Bonferroni threshold can false-negate real signals

Surfaced by Phase 3 v12 critic KILLER-2. v12 lock pre-registered offset robustness at Bonferroni 0.0125 at every +/- 0.5h offset. MLB-night fails ONLY at the -0.5h point (p=0.027 fails Bonferroni 0.0125 but passes uncorrected 0.05). The center is p=3.58e-7 (one of the strongest results in project history); the +0.5h is p=0.000685 (also strong); the failing -0.5h is p=0.027 (still significant uncorrected). The lock's strict gate treats this stratum identically to one that returns gamma=0 at all 3 offsets.

**Why this is F10 (a new instance, not a new mode):** F10 covers fragility under cross-validation-style perturbations. Offset sensitivity is a perturbation: shift the time anchor and see if the signal holds. v11 lock did not gate on this; v11 Phase 3 critic flagged the absence; v12 lock added it. v12's gate is severe enough to false-negate strong signals that show smooth dependence on the offset (the signal exists across the range but with varying significance level).

**Replay check for future rounds:** if pre-registering a robustness gate at Bonferroni-corrected alpha at multiple perturbation points, ALSO compute and report the equivalent gate at uncorrected alpha 0.05. A signal that passes uncorrected-0.05 at all perturbation points but fails Bonferroni-corrected at one is genuinely robust in direction and approximately robust in magnitude; the gate fails for being too severe, not because the signal is missing.

**Recommendation for v13 lock:** for offset robustness specifically, use a TWO-LEVEL gate: (level 1, hard) Bonferroni at the center; (level 2, soft) uncorrected 0.05 at adjacent offsets. The stratum passes if BOTH levels clear. This preserves the falsification value (a stratum that fails uncorrected 0.05 at adjacent offsets has a fragile signal) without overlapping the strict-alpha test (which is what the center gate already does).

---

## Operational lesson 3: VWAP windowing function should be a versioned interface

v11 and v12 both compute Kalshi VWAP at target times. They use different functions. The functions are not versioned, named, or documented; they are inline implementations in the per-round phase2 scripts.

**Lesson:** package the VWAP function as a versioned module: `kalshi_bot_vN.vwap.v1(...)`. Each round's lock explicitly imports the version it uses. Methodology amendments require lock changes. Future v13 should refactor to enforce this.

**Concretely for v13:** create `src/kalshi_bot_v13/vwap.py` with named functions `centered_30min(con, ticker, target)` and `hour_bucket_forward_anchored(vwap_index, ticker, target)`. Each function is documented with its bias direction and trade-off. The lock pre-registers which function the analysis uses.

---

## Operational lesson 4: pre-register robustness-gate severity AND backup version

v12 pre-registered Bonferroni offset robustness. The signal fails by a small margin (p=0.027 vs 0.0125 = 2.16x). If the lock had ALSO pre-registered "and also report uncorrected-0.05 results for completeness", the verdict would have the same NULL-v12 label but the Phase 4 + 5 documentation would carry the operationally useful "signal exists at uncorrected 0.05 across the offset range" descriptor.

**Lesson:** for any pre-registered severe gate, also pre-register a less-severe descriptor that gets reported alongside the verdict. The verdict label is binary; the descriptor is continuous.

---

## Updated cumulative failure-mode taxonomy

F1 to F11 are unchanged in TYPE. v12 added two NEW INSTANCES (F8-vwap-windowing and F10-offset-robustness-severity) and two OPERATIONAL LESSONS (L3 and L4).

| Mode | Type | Instances |
|---|---|---|
| F1 | Data ceiling / coverage / dropout | v11: F1-tz-mismatch |
| F2 | Sample size insufficient | (none) |
| F3 | Domain mismatch | (none) |
| F4 | Trade-print vs orderbook ASK | v11: deferred to v12+ for execution |
| F5 | Single-strategy bias / no comparator | (none) |
| F6 | Compounded multiple-test inflation | (none) |
| F7 | Stale post-settlement price | (none) |
| F8 | Gate-regime mismatch | v12: F8-vwap-windowing-silent-change |
| F9 | Side-selection bias | (none) |
| F10 | LOO / LOCO fragility | v12: F10-offset-robustness-severity |
| F11 | Dataset schema phantom | v11: Becker has no orderbook history; F4 Option B infeasible |

Operational lessons cumulative:

- **L1 (v11):** lock authors should pre-register an offset-sensitivity range for any derived target time
- **L2 (v11):** data probe before locking gates against specific fields (F11 strict generalization)
- **L3 (v12):** VWAP windowing function should be a versioned interface across rounds
- **L4 (v12):** for any pre-registered severe gate, also pre-register a less-severe descriptor reported alongside the verdict

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
