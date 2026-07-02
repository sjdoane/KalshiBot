# v25 Adversarial Verdict Critique (post-results, pre-verdict-doc)

Role: attack the double NULL. Question: genuine null, or a false null manufactured by
implementation choices? Also: verify the verdict classes against the locked lattice.
Inputs: 02-methodology-lock.md (v3), data/v25/backtest_results.json, 04-code-review.md,
spot-checks of scripts/v25/gas_model.py and backtest.py. This document does not
resurrect the idea; it audits the inference.

## Bottom line

**NULL-CONFIRMED, with a mandatory wording constraint.** No implementation choice
manufactured the H1 or H2 null. The single decisive fact: the null is MEAN-driven, not
friction-driven and not power-driven. Because the haircut is a constant 3c on every
fire, execution counterfactuals are exact constant shifts of the whole P&L
distribution, and even the FRICTIONLESS shift fails gate 2. The one caveat is
epistemic, not statistical: the operative fallback spec had zero in-sample
point-forecast skill (ledger 0c item 4), so this is a valid null of a weak instrument,
and the verdict doc must be worded per E11 with that weakness stated, claiming nothing
about market calibration. Exact wording in section 9.

## 1. Vector: false null via the +3c haircut. CLOSED.

The haircut is a flat 3c added to every fire's cost (backtest.py pnl_rows, gas_model.py
HAIRCUT). Removing it shifts every pnl by exactly +0.03; the cluster-bootstrap CI
endpoints shift by the same constant (fee changes by at most ~1c on some fires as
p_exec moves; sub-1c fuzz). Counterfactual ladder on the binding H1 run
(mean -0.0241, CI [-0.0779, +0.0233]):

| Execution assumption | mean | 95 CI |
|---|---|---|
| +3c, worst-case fee (binding) | -0.0241 | [-0.0779, +0.0233] |
| +1c, worst-case fee | -0.0041 | [-0.0579, +0.0433] |
| 0c, worst-case fee | +0.0059 | [-0.0479, +0.0533] |
| 0c, ZERO fee (avg fee ~1.7c) | +0.0229 | [-0.0309, +0.0703] |

There is NO execution assumption, including physically impossible frictionless fills,
under which gate 2 (CI lower bound > 0) clears. The haircut cannot be the mechanism of
the null.

The side-matched +1c run (mean -0.079, CI fully negative, n=1327) does not close this
vector by itself, and it does not need to. It is a selection-filtered subset (prints
where the real taker traded the model's direction), so an adverse-flow story is live
for THAT run: matched prints are precisely the moments real money agreed with the
model, and those moments lost more. But the binding run is not selection-filtered, and
the constant-shift table above closes the vector on the binding run directly. The
matched run's extra negativity is, if anything, evidence AGAINST a middle execution
assumption rescuing the edge: real same-direction flow did worse, not better. The
54.7 percent attrition must be stated per E15d (it is, in the JSON) and the capacity
story called weaker.

One honest exception found, reported in section 8 (d3 + 1c), which is a future-lock
seed and not a v25 result.

## 2. Vector: false null via model degeneracy (vacuous null). PARTIALLY CONCEDED, wording-binding.

The attack: the operative fallback spec has in-sample point-forecast corr -0.02 (h=7)
and -0.065 (h=14), so "a skill-less model loses money as a taker" was near-inevitable
and the null is vacuous.

The concession: yes, this null is weak evidence about the ECONOMIC hypothesis (does
the ladder sit at the public pass-through frontier). A spec with zero point skill is a
weak instrument; failing to reject with a weak instrument says little about the
market. The verdict doc MUST say this, and the lock already forces it: E11 plus the
ledger 0c item 4 disclosure were pre-committed exactly for this outcome.

The non-concession: the test was not vacuous ex ante, and the results carry one real
adjudication the lock pre-authorized. The 0b honesty note said the 22pp median
divergence means EITHER the market is grossly miscalibrated OR the fallback model is
overconfident at extremes, and that gates 2-3 adjudicate. They did: model overconfident.
Three independent, mutually consistent reads:

- The control (random walk plus its own empirical tails) fired 2928 times, net mean
  -0.2pp, gross of simulated frictions roughly +4.5pp; the model's fires gross roughly
  +2.3pp (different fire sets, so this comparison is loose, but the direction is that
  the regression component SUBTRACTED gross capture relative to a random walk).
- The YES/NO decomposition is an exact partition of the pooled mean
  (1446 x -0.1373 + 1481 x +0.0865 = 2927 x -0.0241, verified to machine precision):
  YES fires, which the model generates when its point path plus thin sqrt(h) tails
  says up, lost 13.7pp; the mirror side gained. That is the signature of a
  mis-centered, overconfident forecaster, not of a mispriced market.
- H2, which needed BOTH model and control to agree at the 0.995 floor, also nulls
  (mean -0.005), so there is no free tail money net of fees even where the random
  walk agrees.

What the evidence supports, and the ONLY calibration-adjacent sentence I will accept
in the verdict doc: "On the fired print set, the ladders are within worst-case taker
frictions of a random-walk-with-empirical-tails benchmark (control net mean -0.2pp,
CI [-5.1, +4.3]pp); no stronger market-calibration claim is licensed, and the E11
rule forbids wording this as the market pricing pass-through efficiently." The stronger
reading (market well-calibrated) is NOT supported: the control CI is 9pp wide, the
control shares the same friction stack, and neither run sees RBOB futures curve
information.

## 3. Vector: false null via pooling over the 2026 shock. CLOSED.

Concentration is real: 2216 of 2927 fires (75.7 percent) close inside the shock window
2026-02-15..2026-06-30 (19 of 52 ISO-week clusters). But the direction of the attack
fails everywhere you look:

- ex_shock (711 fires / 33 clusters): mean -0.067, CI [-0.127, +0.012]. OUTSIDE the
  shock the spec did WORSE, not better. The pooled number is flattered by the shock,
  not hiding a good regime.
- chrono halves: pre-2025-10 mean -0.027 (n=353), from-2025-10 mean -0.024 (n=2574).
  Both negative; no era worked.
- The positive breakdown cells are tiny: h 8-14 +0.8pp (n=367), high moneyness +0.8pp
  (n=1116). Both are under one fee increment (1-2c) and are 2 of ~10 reported
  post-data cells. No hidden working regime exists at any magnitude that survives one
  tick of friction.

There is no partition in the JSON in which this spec makes gate-2-relevant money.

## 4. Vector: the NO-side +8.7pp (n=1481). MECHANICAL MIRROR plus multiplicity; future-lock seed only.

The locked position (a) is correct: future-lock hypothesis only, not partial falsity
of the null. Grounds:

- Exact-partition arithmetic (section 2): given a pooled mean pinned near -2.4pp and a
  YES side crushed at -13.7pp by the model's demonstrated upward overconfidence, the
  NO side is the complement almost by construction. A biased forecaster mechanically
  sorts prints into a losing side and a mirror side; the mirror's positivity is not
  independent evidence.
- Multiplicity: this is 1 of ~10 reported breakdowns, in hypothesis family ~25, on a
  direction stratum the lock explicitly listed as REPORTED, NON-BINDING (section 6).
  No cluster CI was computed for it pre-lock and none is registered.
- The JSON does not report the control's side breakdown, so "NO-side taker on these
  ladders is profitable regardless of model" (a longshot-tax read) cannot be
  distinguished from "model mirror" with the artifacts on hand. The project's own v22
  found the longshot-tax NO capture INVERTED (-1.94pp) at maker on other series, a
  prior against the tax read.
- 75.7 percent of fires sit in one directional wholesale shock; a NO-side mean built
  during and after a historic run-up is regime-soaked.

Correct treatment: one line in the verdict doc naming +8.7pp as a mechanically
suspect, multiplicity-burdened observation logged as a FUTURE-lock seed. Any wording
implying the v25 null is "partially false" is rejected.

## 5. Vector: verdict lattice fidelity. VERIFIED CORRECT, both hypotheses.

Traced gates_h1/gates_h2 in backtest.py against lock sections 8-9 with the JSON values:

- H1 gate 1: 2927 >= 40 fires and 52 >= 30 clusters, power_ok true. So the class is
  NULL, not UNDERPOWERED-NULL, per E11. Correct in JSON.
- H1 gate 2: binding lo = -0.0779, not > 0, ci_ok false. The elif chain reaches "NULL"
  before the control, LOCO, month, and shock branches; loco_ok / month_ok /
  ex_shock_ok are correctly emitted as null (moot) because they are conditioned on
  ci_ok. Correct.
- H1 gate 3 (moot but reported per lock): control 2928 fires / 52 clusters meets the
  floor, lo = -0.0512 < 0, control_clears false, control_ok true. Had gate 2 passed,
  nothing here would have demoted it. Reported as required.
- E15d duty: attrition 0.547 > 0.5 and the attrition_note is present. Correct.
- H2: kept at lock (h2_keep true read from audit_0b_decision.json per review H3 fix);
  447 >= 30 fires, 26 >= 8 clusters, power_ok true; lo = -0.0388 < 0, ci_ok false,
  verdict NULL. Regime guards are wired (review H2 fix) and correctly moot. Correct.
- Routing: NULL routes to FINAL-VERDICT doc, memory update, commit, pivot, NO live
  read (section 9). The classification "NULL" is the exact lattice class for both.

## 6. Vector: other false-null mechanisms. SWEPT; none found. Two documentation duties.

- Fee double-counting: none. taker_fee applied once, on p_exec, entry only; Kalshi
  charges no settlement fee. The worst-case ceil per 1-lot overstates a multi-lot
  amortized fee by under 1c; the section-1 zero-fee counterfactual already bounds
  this: irrelevant to the verdict.
- Dedup / one-per-market-per-day: first-QUALIFYING-print selection (taken key set only
  on fire), outcome-blind, pre-committed in section 4. 345,490 suppressed prints are
  correlated repeats of the same signal; including them multiplies n inside clusters
  without moving cluster means, and the null is mean-driven. Cannot manufacture a null.
- Cluster definition / bootstrap: ISO-week-UTC clusters, whole-cluster resampling,
  10k, fixed seed, reviewed clean in 04. Variance inflation from coarse clusters can
  only widen the CI, and a wider CI cannot rescue a NEGATIVE point estimate; gate 2
  needs lo > 0. Moot by the same mean-driven logic. Same for H2.
- Binding-window filter: applied on close_time to fires, sensitivities, and control
  alike; symmetric.
- Ambiguity window (E1): 79,375 prints in [03:00, 09:00) ET excluded. This is a SCOPE
  limit, not a bias: the excluded region (right after AAA publication) is plausibly
  where information advantage peaks, and a live trader at 09:00+ is inside the tested
  set anyway. The null claim simply does not cover 3-9am ET fires. Verdict doc should
  state this as untested territory, one line.
- Settlement-key audit logic (0a): sound. Straddle markets are the only discriminating
  class and went 35/35 for key D; 100 percent consistency on all 698 testable markets
  bounds parser and reconstruction error jointly; the 95 percent D-1 rate on
  non-straddles is exactly the expected same-side agreement. No circularity: booleans
  and rates only, per the E12a firewall.
- M1 residue: the 10 old-format markets (strike only in ticker suffix) are still
  silently inside the nostrike counter. Documentation duty from the code review stands:
  the verdict doc must NAME the 10 excluded markets.
- Alt-threshold run is a true re-run at 0.12 (review M7 fixed: run_variant re-fires),
  not a filter of the 0.08 set. Verified in backtest.py.

## 7. The one adversarial catch worth recording: d3 + 1c nominally clears

Applying the exact +2c constant shift to the d3 sensitivity (mean +0.0159,
CI [-0.0166, +0.0511]) gives mean +0.0359, CI approximately [+0.003, +0.071]. That
cell, flat d-3 wholesale visibility at +1c haircut, would sit at or just above the
gate 2 boundary (the lower bound is inside the sub-1c fee-shift fuzz, so "at the
boundary" is the honest phrase). This does NOT reopen v25: it stacks two pre-labeled
NON-BINDING optimistic assumptions post-data (the d-3 lag grants DGASNYH values
before their actual weekly EIA release, so it is an infeasible information set on
FRED; the 1c haircut contradicts the binding assumption and the matched-run adverse
flow), and no such run was registered. It is, however, exactly the shape of a
legitimate future lock: fresher wholesale data (a commercial real-time NYH feed, not
FRED) plus tight execution. Recorded as a seed, nothing more.

## 8. Live-read recommendation (vector 7)

Per the lock, NULL routes to pivot with no live read, and that routing stands; nothing
here authorizes a v25 stage-1 read. The only thing worth carrying out of v25 for $0 is
a LEDGER SEED, not an action: a future lock could register, before seeing any new
data, the joint hypothesis that (i) fresher-than-FRED wholesale visibility (the d3+1c
boundary cell of section 7) and/or (ii) NO-side taker fires on these ladders (the
+8.7pp mirror cell, prior-burdened by the v22 longshot-tax inversion) carry edge, with
its own power arithmetic and a non-shock evaluation window. Both cells are
multiplicity-soaked children of round 25 breakdowns and should be assigned a prior at
or below the 10 percent v25 started with. No monitoring, no snapshots, no capital.

## 9. Exact wording the verdict doc must use (E11-compliant)

H1: "NULL. Under the locked gates, the frozen FALLBACK spec (symmetric ECM, run by
the pre-committed E4 rule; in-sample point-forecast correlation ~0 at h=7/14, ledger
0c item 4) does not extract positive net P&L as a taker from KXAAAGASW/KXAAAGASM
under ANY execution assumption from worst-case (+3c, worst-case fee: mean -2.4pp, CI
[-7.8, +2.3]pp, 2927 fires / 52 clusters) to frictionless (mean ~+2.3pp, CI lower
bound ~-3.1pp). This is a null of THIS frozen spec, which had no measurable point-
forecast skill and cannot see RBOB futures curve information the market can see. It
is NOT evidence that the market prices pass-through efficiently, and it is weak
evidence on whether the ladder sits at the public pass-through frontier, because the
operative instrument was weak. What the results do adjudicate, per the pre-committed
0b honesty note, is the 22pp median divergence: it was model overconfidence, not
market miscalibration (YES-side fires -13.7pp; the control's gross capture exceeded
the model's). On the fired print set the ladders are within worst-case taker
frictions of a random-walk-with-empirical-tails benchmark (control net -0.2pp, CI
[-5.1, +4.3]pp); no stronger calibration claim is licensed. Side-matched attrition
was 54.7 percent, so the capacity story is weaker (E15d). The NO-side +8.7pp
breakdown is the mechanical complement of the model's losing YES side, is 1 of ~10
non-binding post-data cells in hypothesis family ~25, and is logged only as a
future-lock seed."

H2: "NULL. 447 fires / 26 clusters (power floor met), mean -0.5pp, CI [-3.9, +1.7]pp:
the certainty stratum offers no net tail edge of THIS spec even where the model and
the random-walk control agree at the 0.995 floor."

Ledger restatement (section 10 duty): families screened ~25; hypotheses this round:
two (H1, H2 kept at 0b); strata added post-data: zero; the 10 nostrike old-format
markets named; the [03:00, 09:00) ET region stated as untested.

Em-dash audit: clean (verified after write).
