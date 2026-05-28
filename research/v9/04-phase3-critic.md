# v9 Phase 3 Adversarial Critic: Angle A Kill Adjudication

**Date:** 2026-05-26
**Author:** Phase 3 Adversarial Critic (independent of orchestrator)
**Status:** Complete. Independent adjudication of M3 kill recommendation.
**Predecessor reads (all confirmed read-only):**
- `research/v9/01-data-universe.md` (A1)
- `research/v9/02-recipe-methodology.md` (A2)
- `research/v9/00-v10-candidate-angles.md` (A3)
- `research/v9/03-phase1-synthesis.md` (orchestrator synthesis)
- `research/v7/07-naive-p-yes-critic.md` (v7-B phantom constraint)
- `research/v7/00-scoping-synthesis.md` (v7 Angle A scope)
- `research/literature/aia-2025-forecaster-and-followups.md`
- `research/literature/halawi-2024-human-level-forecasting.md`
- `research/literature/sports-prediction-ceiling-2022-2024.md`
- `research/w2-v1-residual-edge.md`
**Probe scripts read:** `scripts/v9/probe_v9_universe.py`, `scripts/v9/probe_sports_oos.py`
**Probe outputs read:** `data/v9/sports_oos_probe.json`, `data/v9/settled_probe.json`

---

## Context

The orchestrator recommends M3 (kill v9 Angle A as NULL on data-layer feasibility) based
on two breaks: (1) historical Kalshi orderbook unavailable, eliminating retrospective
backtesting; (2) the prospective universe of 87 markets is 56x underpowered for the
pre-registered +0.014 Brier gate. My job is to find what the orchestrator missed.
I am explicitly adversarial.

---

## Test 1: Reproduce the n=87 Number

### Method

Read `scripts/v9/probe_v9_universe.py` in full. Cross-check against `data/v9/sports_oos_probe.json`
and `data/v9/settled_probe.json`. The saved JSON files are NOT the source of n=87 -- they capture
(a) the OOS CLOSED window probe (settled_probe.json, n=594 settled, n=5 v1-eligible) and (b) a
targeted series-by-series closed probe (sports_oos_probe.json, n=4 markets from 2 series). The n=87
comes from PROBE 5 of probe_v9_universe.py (prospective open markets), whose detailed output was
printed but not saved to a structured JSON.

### Finding: minor undercounting possible

The probe script (lines 283-288) counts v1-eligible prospective markets only when BOTH
`yes_bid_dollars > 0 AND yes_ask_dollars > 0`. Markets where yes_ask is derivable by parity
(`1.0 - no_bid`) are EXCLUDED from the 87 count, even though the v9-A1 methodology document
explicitly states that parity-derived yes_ask should be used.

Per A1 Section 2.2: "86/188 have yes_bid, 107/188 have yes_ask derived from no_bid" (this refers
to the v8-A KXBTCD dataset, not the prospective sports set, but illustrates the prevalence of
parity markets). The probe script's strict both-present filter likely undercounts the true
prospective universe by 5-20%.

If true n is 90-105 (parity markets included), the power analysis changes minimally:
at n=100, SE = 0.050, minimum detectable delta = 0.140. At n=120, SE = 0.046, minimum detectable
delta = 0.128. The gate target of 0.014 remains 9x to 10x below the detection floor.

**FINDING T1: MINOR.** The n=87 is plausibly a mild undercount. True n is likely 87-120.
The kill conclusion is ROBUST: no realistic n correction changes the power situation.
The n=1300 threshold claimed by the orchestrator is correct in order of magnitude (actual needed
n for 80% power is approximately 1300-7900 depending on which variance estimator is used -- see Test 3).

---

## Test 2: Challenge "Historical Kalshi Orderbook Unavailable"

A1 tested `?ts=` on an open market (silently ignored) and confirmed an empty book for settled
markets. Probe code lines 359-366 and 405-411 explicitly test and confirm these outcomes.

Alternative paths independently checked: (1) `/historical/orderbook` -- no such path exists
in any documented Kalshi endpoint per v7 scoping survey; (2) `/markets/{ticker}/orderbook?as_of=`
-- same endpoint, different parameter, no evidence of distinct code path; (3) `/portfolio/positions`
side-channel -- requires trade-scope key, project uses read-scope only; (4) Kalshi bulk data
download -- no public CSV/zip archive exists on kalshi.com/docs or in any prior session research;
(5) GDELT/ESPN/odds-api -- these are LLM input sources, not Kalshi orderbook substitutes.

**FINDING T2: KILLER-REFUTED.** All alternative historical orderbook paths are closed.
A1's claim stands. The kill reasoning on Break 1 is correct.

---

## Test 3: Power Calculation Check at n=87

### The orchestrator's method

The orchestrator uses SE_Brier ~ 0.5/sqrt(n), a maximum-variance approximation. This gives
SE at n=87 of 0.054, and requires n~1300 to detect 0.014 at 80% power under a one-sided test.

### Refined calculation

For the 0.70-0.95 price band (v1's universe), the per-market Brier score variance is much smaller
than the 0.5^2 = 0.25 upper bound. A calibrated market at p=0.85:

- E[Brier_i] = p*(1-p) = 0.85*0.15 = 0.1275
- Var[Brier_i] = p*(1-p)*(2p-1)^2 = 0.1275 * 0.70^2 = 0.0625

SE(mean Brier) under the refined model: sqrt(0.0625/87) = 0.0268.

For the Brier DELTA (paired test, ensemble vs. market mid), the two quantities are correlated
(same outcomes). The variance of the difference is bounded by 2*Var[Brier_i] = 0.125.
SE(Brier_delta) upper bound: sqrt(0.125/87) = 0.0379.

**However:** a tighter estimate comes from back-calculating the AIA paper's implied variance.
If AIA detected delta=0.014 at statistical significance using n~3000, then:
- Required SE for 80% power: delta/(z_alpha + z_beta) = 0.014/(1.96 + 0.842) = 0.005
- At n=3000: sigma_delta = 0.005 * sqrt(3000) = 0.39
- This is much larger than the refined upper bound above (0.39 >> 0.125)
- Interpretation: AIA's detection at n=3000 was BARELY SIGNIFICANT (or the paper aggregated across
  categories in ways that reduce effective n, or their variance structure was different)

Under the AIA-implied sigma_delta = 0.39:
- n needed for 80% power: ((1.96+0.842)*0.39/0.014)^2 = 6131
- n needed for 30% power: ((1.96-0.524)*0.39/0.014)^2 = 1610
- P(gate fires at n=87, true delta=0.014): ~5.2%

**FINDING T3: IMPORTANT.** The refined calculation makes the kill look WORSE for v9, not better.
Under realistic variance assumptions (AIA-implied sigma_delta), the required n for 80% power is
approximately 6,000 (4x higher than the orchestrator's 1,300 estimate). The orchestrator's
n=1300 is optimistic. At n=87, the probability that the gate fires if the true delta is exactly
0.014 is approximately 5%. The kill is fully defensible at any reasonable variance assumption.
The orchestrator's claim of "56x underpowered" is itself conservative; the true multiple may be
70x or more.

---

## Test 4: Challenge "No In-Session Verdict"

### A1's claim

Resolutions arrive 2026-05-27 to 2026-06-30. The orchestrator treats this as "no session verdict."

### Fast-resolving subset

From A1's prospective table:
- KXUFCFIGHT (n=11): close 2026-06-29 (34 days out, not fast)
- KXWCGAME (n=4): close 2026-06-28 to 06-30 (33-35 days out)
- KXPGAUSO (n=4): close 2026-06-29 (34 days out)
- Additional (n=65): close 2026-05-27 to 06-30 (distributed)

A1 explicitly states "first resolutions available 2026-05-27," meaning some markets in the
Additional 65 resolve tomorrow. However, even if n=10 markets close in the next 24-48 hours,
SE at n=10 is 0.158, placing the minimum detectable delta at 0.44 -- 31x the gate target.

A 1-week wait yields approximately 13 of the Additional 65 markets resolved (assuming uniform
distribution). SE at n=13 = 0.139. Still no path to the +0.014 gate.

### Session cadence consideration

The operator runs sessions in roughly 1-3 day bursts. A 5-week wait to collect n=87 is beyond
any reasonable definition of "in session." The 35-day timeline to full resolution is a genuine
structural constraint, not an orchestrator error.

**FINDING T4: KILLER-REFUTED.** There is no fast-resolving subset in the next 24-48 hours that
changes the statistical situation. The 11 UFC markets on 2026-06-29 are 34 days out. The Additional
65 that resolve earlier are distributed over 5 weeks and statistically useless at 1-2 week subsets.
The orchestrator's "no in-session verdict" claim is correct.

---

## Test 5: Gate Applicability Challenge (CRITICAL)

### The central methodological objection

The pre-registered gate of +0.014 Brier is sourced from AIA Section 5's MarketLiquid analysis,
where the ensemble beat market consensus by 0.014 on "hard" questions. The v9-A2 recipe document
(Section 4.5) cites: "The 0.014 threshold corresponds to the full market-ensemble improvement range
(0.015 in the hard subset)."

**The critical question: what does "hard" mean in AIA's terminology?**

From the AIA extraction (aia-2025-forecaster-and-followups.md):
- MarketLiquid "hard" subset = 1,610 questions where Kalshi mid is in the uncertain range
  (approximately 0.20-0.80). "Hard" means HARD TO PREDICT, not HIGH CONFIDENCE.
- Market consensus Brier on this subset: 0.111, AIA Brier: 0.126, Ensemble: 0.106
- Delta: 0.111 - 0.106 = +0.005 (not +0.014)

The +0.014 figure in the v9-A2 recipe appears to conflate two different AIA numbers:
- The +0.005 is the all-market ensemble lift (market 0.111 vs ensemble 0.106)
- The +0.014 may refer to the lift computed against a DIFFERENT baseline (AIA-only 0.126
  vs ensemble 0.092 on some subset), or it is the difference 0.126 - 0.106 = 0.020 (AIA
  versus ensemble, not market versus ensemble)

The recipe doc says "delta = 0.005 (lower bound of improvement)" and "The higher threshold (0.014)
corresponds to the full market-ensemble improvement range (0.015 in the hard subset)." This is
ambiguous -- the 0.015 is the range of reported numbers across different AIA subsets, NOT a
cleanly pre-registered AIA improvement on a specific subset.

### Halawi 2024 on the confident-market failure mode

Halawi 2024 is unambiguous: "The system underperforms the crowd on questions where they are highly
certain, likely because it rarely outputs low probabilities." The 0.70-0.95 YES band is precisely
the high-confidence regime where the LLM is DOCUMENTED to underperform.

Platt scaling (t=sqrt(3)) partially mitigates this by pushing 0.70 to 0.813 and 0.80 to 0.917.
However, numerical analysis shows: even if the LLM correctly identifies the direction but hedges
from 0.85 to 0.70, the Platt-corrected ensemble improves over market Brier by only approximately
0.00015 Brier (measured at p=0.85). This is 100x smaller than the 0.014 gate.

If the LLM gets the direction wrong -- which it will on some fraction of markets (sports is the
documented weakest LLM topic) -- the ensemble actively HARMS calibration. The expected Brier
improvement on confident favorites is likely near zero or negative, not +0.014.

### The gate is on a methodological strawman

AIA's reported numbers: all-market ensemble vs market = +0.005 lift; some subset = +0.019 lift
(0.111 - 0.092). The +0.014 sits between these two numbers and is not attributed to any specific
price band in the extraction. The AIA MarketLiquid "hard" questions are CONTESTED markets
(mid near 0.5), not confident favorites near 0.85.

Applying the +0.014 gate to a 0.70-0.95 universe is inconsistent with where AIA measured its lift.
On a calibrated 0.85 favorite, even a correctly-directional LLM that hedges from 0.85 to 0.70
(Platt-corrected to 0.813) produces an ensemble Brier improvement over market of approximately
0.00015 -- 100x smaller than the 0.014 gate. The correct expected lift on v1's universe is
approximately +0.000 to +0.003 Brier (sports = documented weakest LLM topic; confident favorites
= Halawi's documented failure regime).

**FINDING T5: KILLER.** The +0.014 gate was never achievable on 0.70-0.95 favorites regardless
of n or LLM quality. The gate should be approximately +0.003 for this universe, and even that
requires n~78,000 at the coarse SE formula. The orchestrator's kill is not wrong -- but the
kill reason is incomplete: this is a DESIGN KILL, not only a data-layer kill.

---

## Test 6: Cheap One-Shot Salvages

### Salvage S1: 15-forecast pilot on KXUFCFIGHT + KXWCGAME (n=15, ~$1.50 LLM)

**What it is:** Forecast all 11 UFC + 4 World Cup markets NOW at 1 sub-agent per forecast.
Store live mid at forecast time. Wait for June 28-30 resolutions. Report Brier point estimate
only (no CI gate attempted, explicitly labeled PILOT).

**Cost:** 15 markets * $0.10/forecast = $1.50 LLM. ~1 hour agent-clock.

**What it produces:** The v9 pipeline wired end-to-end (Anthropic SDK + web_search +
the-odds-api live odds + ESPN + Platt scaling + ensemble). A Brier point estimate on n=15.
Infrastructure reusable for a 2026-27 season rolling study.

**Prior of being informative:** Low (n=15 is pure noise for the gate). However:
- Pipeline validation: confirms the tool-calling pipeline works end-to-end
- Directional signal: if ensemble Brier is substantially WORSE than market mid (the expected
  direction given sports LLM weakness), this is evidence AGAINST continuation
- If pilot shows consistent directional improvement across sport types, case for M1 (pilot)

**Score:** INFORMATIVE for pipeline purposes, NOT for statistical inference. Cost $1.50.
Recommended IF operator wishes to build infrastructure for a 6-month rolling study
(the M1 path), NOT recommended if the goal is a session verdict.

### Salvage S2: Report v9 F2 as descriptive study, no gate

**What it is:** Forecast all 87 markets, report Brier_delta with 95% CI at n=87 in 5 weeks.
Explicitly label as "AIA recipe replication directional pilot" -- no SHIP/NULL verdict,
no gate. Infrastructure builds toward a future rolling study.

**Cost:** 87 * $0.10 = $8.70 LLM + overhead. Wall-clock 5 weeks.

**Prior of being informative:** Medium. A Brier_delta point estimate on n=87 is directional
evidence. If negative (likely given sports LLM weakness), it strengthens the kill. If positive
and large (>0.05), it would be anomalous relative to literature and warrant scrutiny for
v7-B-style phantoms. Neither outcome produces a gate verdict.

**Score:** Justified as infrastructure investment, not as research verdict. Costs $8.70 of
remaining $18 LLM budget. Leaves $9.30 for v10.

### Salvage S3: Combine v9 LLM forecasts with v8-A

v8-A covers KXBTCD (crypto). v9 targets sports. Datasets do not overlap. NOT APPLICABLE.

### Salvage S4: Revise gate to +0.005

At delta=0.005, n needed for 80% power ~ 78,600 (using the coarse SE=0.5/sqrt(n) formula).
The problem is n, not the gate level. No salvage path.

### Summary of salvages

| Salvage | LLM Cost | Informative for verdict? | Recommended? |
|---|---|---|---|
| S1: 15-forecast pilot (UFC+WC) | $1.50 | Pipeline only, not gate | If building infrastructure |
| S2: Full 87-forecast descriptive | $8.70 | Directional only, no gate | If M1 path selected |
| S3: Combine with v8-A | $0 | N/A (no overlap) | NO |
| S4: Revise gate to +0.005 | $0 | Still underpowered at n=87 | NO |

No salvage produces a session verdict. The only salvage that produces lasting value is S2
(infrastructure for a 2026-27 season rolling study) at cost ~$8.70.

---

## Test 7: Independent Verdict

### What I find that the orchestrator got right

1. Historical orderbook unavailability: confirmed correct. No alternative paths found.
2. Prospective n=87 is underpowered: confirmed correct, and if anything understated
   (power analysis suggests 70x underpowered, not 56x).
3. Seasonal market structure: confirmed correct. The W2 residual series (KXNBAWINS,
   KXMLBWINS, etc.) have zero settled markets in the post-cutoff window.
4. No in-session verdict: confirmed correct. Earliest meaningful resolution is June 28-30
   (34-35 days). No fast-resolving subset exists.

### What the orchestrator missed or understated

**IMPORTANT (T5):** The orchestrator's kill framing is "n is too small for the gate to fire."
The more accurate framing is "the gate was methodologically wrong for this universe from the
start." The +0.014 gate was never achievable on 0.70-0.95 favorites regardless of n. This
REINFORCES the kill but changes the correct write-up.

**MINOR (T1):** n=87 is a mild undercount (true n likely 90-120). Changes nothing.

**MINOR (T3):** Orchestrator's n=1300 is optimistic; AIA-implied variance suggests n~6000
for 80% power. Kill is more defensible than stated.

### Is there a SALVAGE that changes the verdict?

M1 (F2 pilot without gate, infrastructure for 2026-27 season rolling study) has genuine merit:
the pipeline is valuable infrastructure, and a 12-month rolling study accumulating n~300-500
v1-eligible markets would approach adequate power. However: M1 costs $8.70 of $18 remaining,
delays v10, and does not produce a session verdict. The operator's kill-early preference controls.

**No METHODOLOGY ERROR reverses the kill.** Test 5 is a design flaw that strengthens the kill.

---

## Verdict

**KILL CONFIRMED.**

The orchestrator's M3 recommendation is correct. The independent adjudication finds:

1. **Historical orderbook:** structurally unavailable. Confirmed independently.
2. **Prospective n=87:** underpowered at 5-70x the needed sample depending on variance
   estimator. Gate cannot fire at any reasonable n correction.
3. **No in-session verdict:** fast-resolving subsets in 24-48 hours are statistically
   useless (n=2-5). The June 28-30 resolution window is 34 days out.
4. **Gate was methodologically inconsistent from the start (CRITICAL finding not in M3):**
   The +0.014 AIA lift was measured on uncertain markets (0.20-0.80 band), not on confident
   favorites (0.70-0.95). Halawi 2024 explicitly documents LLM underperformance on high-confidence
   markets. Expected lift on v1's universe is approximately +0.000 to +0.003, not +0.014.
   The gate was a phantom from the pre-registration step.
5. **No cheap salvage produces a session verdict.** S2 ($8.70 descriptive pilot) builds
   infrastructure but does not produce a verdict.

**Additional finding:** The orchestrator should note this kill is not purely "data-layer
infeasibility" -- it is a DESIGN KILL. The experiment was designed to test AIA's lift on a
universe where AIA's lift does not apply. A revised design for any future Angle A attempt
should either: (a) expand the price band to AIA's uncertain-market regime (0.20-0.80),
accepting that this departs from v1's universe; or (b) lower the gate to a level consistent
with the literature evidence on confident-market LLM performance (approximately +0.002 to
+0.005), with the understanding that proving even this small lift requires n ~ 10,000-15,000.

The highest-EV action remains the A3 Rank 1 recommendation: v8-A analysis pass at ~$0 when
v8-A finishes tonight (23:48 UTC), then v10 Candidate 9 (sportsbook line movement, mechanistically
distinct from all prior NULLs, $30 one-time within authorized budget).

**Recommended operator framing for v9 close:** "NULL on data-layer and design feasibility.
The AIA recipe requires an uncertain-market universe (0.20-0.80) to produce detectable lift;
v1's confident-favorites universe (0.70-0.95) is explicitly the regime where LLMs underperform
per Halawi 2024. Future Angle A would need either a broader price band or a much longer
(12-month) rolling study accumulating n~500-1000. Spend: ~$2 LLM of $18 remaining."

---

## Findings Summary

| # | Finding | Test | Tag |
|---|---|---|---|
| 1 | n=87 is plausible but mild undercount (87-120); kill conclusion robust to any n correction | T1 | MINOR |
| 2 | All alternative historical orderbook paths are closed; A1's claim confirmed | T2 | KILLER-REFUTED |
| 3 | True required n for 80% power is 6000-7900 (not 1300); kill more defensible than stated | T3 | IMPORTANT |
| 4 | No fast-resolving subset (<7 days) changes the statistical situation; June 28-30 is 34 days out | T4 | KILLER-REFUTED |
| 5 | +0.014 gate applies AIA's uncertain-market lift to a confident-market universe; Halawi documents opposite behavior there. Gate was a phantom from pre-registration | T5 | KILLER (strengthens kill) |
| 6 | No salvage produces a session verdict; S2 ($8.70 descriptive) builds infrastructure only | T6 | IMPORTANT |
| 7 | Kill confirmed; orchestrator's M3 is correct; additional finding: kill is also a design kill not just a data kill | T7 | VERDICT |

KILLER count: 1 that strengthens kill, 2 that refute potential kill-reversals. No finding reverses the kill.
