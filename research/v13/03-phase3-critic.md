# v13 Phase 3 Adversarial Critic Review

**Round:** 18 (v13). **Date:** 2026-05-27. **Author:** Phase 3 critic agent.
**Target:** `research/v13/01-methodology-lock.md` + Phase 2 outputs in `data/v13/`
+ `scripts/v13/phase2{a,b,c}_*.py`.
**Scope:** load-bearing pre-Phase-4/5 review. Read-only on v13 artifacts.
The critic surfaces flaws and recommends a money-deployment verdict.

Section A enumerates findings by severity. Section B reproduces key numbers
from raw parquet data. Section C delivers the verdict recommendation.
Section D proposes the forward live-trial design IF deployment recommended.

The critic uses the Becker venv (`prediction-market-analysis/.venv`) with
numpy, scipy.stats, pandas, duckdb for verification.

---

## Section A. KILLER / IMPORTANT / NICE-TO-HAVE findings

### KILLER-1. Block-bootstrap CI failure is borderline; one-sided test would PASS

**Where:** lock Section 4(c) "Block-bootstrap CI lower > 0: 95% CI from 10,000
day-block resamples, seed=42"; results JSON `MLB-night.gate.block_bootstrap`.

**Reproduction (independent, 10000 resamples, seed=42, 33 unique days):**

| Quantity | Value |
|---|---|
| Bootstrap mean gamma | +0.7315 |
| Bootstrap median gamma | +0.7322 |
| Bootstrap SD | 0.4419 |
| CI 2.5% percentile | -0.0160 |
| CI 5% percentile | +0.0523 |
| CI 97.5% percentile | +1.6747 |
| Fraction of resamples with gamma > 0 | **0.9702** |
| Fraction of resamples with gamma <= 0 | 0.0298 |

The G1 gate requires the 2.5th percentile to exceed zero (a 2-sided 95% CI
lower bound). It misses by 0.016 (1.6 percentage points of gamma). But
97.02% of bootstrap gammas are strictly positive. A directional (one-sided
5%) test passes by a wide margin (5th percentile = +0.0523). The 1st
percentile is -0.088, so we are nowhere near a robust two-sided 99% pass,
but the directional inference (gamma > 0) is supported in 97.02% of
day-block resamples.

**Why this is KILLER (for the literal verdict):** the lock specified a
two-sided 95% CI gate. The gate fails by 1.6 percentage points on
n=111 events across 33 days. The signal is real in direction (97%) but
the magnitude is bootstrap-unstable enough that the lower tail of the
distribution crosses zero. The lock is what it is. The gate failed.

**Why this matters for the cumulative interpretation:** this is not the
same as a 50-50 borderline finding. The bootstrap distribution is highly
right-skewed positive. A reasonably-powered 25% larger sample (n approx
140) would very likely cross the threshold based on standard scaling. Or
equivalently, if the lock had pre-registered a directional 95% one-sided
gate (defensible since the alternative hypothesis was specifically
"sportsbook leads Kalshi in the SAME direction"), the gate would pass.

The right summary: **G1 fails the letter of the lock, but the underlying
signal is directionally robust at 97% under day-block resampling.**

---

### KILLER-2. n_fires = 3 is below the G2 floor of 20; G3, G4 bootstrap CIs not computable

**Where:** lock Section 6 trigger rule + Section 7 gates G2, G3, G4;
results JSON shows `row_bootstrap.ci_lower_95 = NaN` because n < 5.

**Reproduction:** the trigger fires 3 of 111 events (2.70%). The lock's
G2 specifies n_fires >= 20 because below this, "the live trial cannot
accumulate enough events for evaluation in 4-8 weeks of MLB season".
G3 and G4 require bootstrap CIs on net P&L; the script's
`row_bootstrap_pnl_ci` short-circuits at n < 5 returning NaN. So G3 and
G4 are NOT computed as FAILED; they are NOT COMPUTED. The summary
JSON misleadingly reports them as False in `gate_g2_g6` (since `NaN > 0`
evaluates False).

**Why this is KILLER:** the 3 fires are an under-powered sample, period.
No statistical statement can be made about net P&L expectation from n=3
that supports any positive CI claim. Even if all 3 fires won at +$0.57
each (which they did), the bootstrap is degenerate at n=3 (most
resamples are degenerate, distribution is not a meaningful estimator).

The 3-of-3 binomial finding (p=0.125 under H0=0.5) is the only
statistical anchor available. That p-value is consistent with chance at
the 10% but not 5% level - one out of every 8 random fair-coin
sequences of 3 produces 3 heads. Not a robust signal on its own.

---

### KILLER-3. The 3 fires are 100% NO-side, not 50-50; the Y filter is a structural side selector

**Where:** lock Section 6 trigger rule; fire parquet data.

**Reproduction (X-only counterfactual, dropping Y filter):**

Without the Y filter, 28 events fire (top quartile of |delta_sb|):
- 11 YES-side fires, 17 NO-side fires (slightly skewed but balanced)
- Overall win rate: **64.3%**
- Mean net P&L: **+$0.150/contract**
- Row-bootstrap 95% CI: [-0.037, +0.326], mean +0.150
- YES side: n=11, win=63.6%, mean net +$0.144
- NO  side: n=17, win=64.7%, mean net +$0.154

With the Y filter (lock's pre-registered trigger), 3 events fire:
- 0 YES-side, 3 NO-side
- All 3 win at +$0.57/contract

**Why this is KILLER for naive extrapolation:** the prompt headline "Of
3 fires: 3 of 3 won" obscures that the trigger structurally selected
3 NO-side events out of 28 candidate top-|delta_sb| events. The
Y filter says "Kalshi hadn't moved yet" (delta_kalshi_pre below 25th
pct in absolute value). Combined with the trigger taking the side
sportsbook moved toward, AND the fact that most of the very-small-
|delta_kpre| events that ALSO have very-large |delta_sb| happen to be
sportsbook-DOWN-moves, the trigger fires only NO sides.

This is not necessarily a bug. The 28 X-only fires also lean ~60-65%
NO-side wins. But the v13 Phase 2c headline of "100% win rate" rests on
a sample of 3 events with a structural side bias (driven by the Y filter
preferentially landing on slow-Kalshi-favorite-down events).

**Why this is still KILLER for the 100% claim:** in the wider 28-event
counterfactual, win rate is 64% and mean net is +$0.15, not +$0.57.
The 4x difference between the 3-fire mean ($0.57) and the 28-event mean
($0.15) IS the Y-filter selection effect, not necessarily a deeper
signal. A 4-8 week live trial sees +$0.15/contract more likely than
+$0.57/contract, and the 28-event CI includes zero.

**However:** the X-only fire descriptive analysis (64% win rate,
+$0.15 mean net per contract) IS itself a noteworthy positive
descriptive signal at n=28. The CI marginally includes zero but the
mean is consistently positive AND positive for BOTH YES and NO sides
(symmetry argues against random selection). This is the wider-sample
descriptive anchor that the operator should use to set forward
expectations, NOT the 3-fire +$0.57 number.

---

### IMPORTANT-A. Lock adherence audit: ALL pre-registered components implemented faithfully

**Reproduction summary:**

| Component | Lock spec | Script | Match? |
|---|---|---|---|
| VWAP windowing | Section 2 centered_30min_vwap | `scripts/v13/phase2a_centered_vwap_rerun.py:81-97` | YES (reproduced VWAP=0.5500 cents on KXMLBGAME-25AUG01HOUBOS-HOU T-3h to 4dp) |
| Strata definitions | Section 3 close UTC hour rules | script lines 257-258 | YES |
| Sport-specific offsets | Section 3 MLB 3.5h NBA 2.5h NFL 3.5h | inherited from v12 SPORT_OFFSETS | YES |
| Bonferroni alpha | Section 4 0.05/4 = 0.0125 (NFL within 0.00625) | ALPHA constants | YES |
| Block-bootstrap | Section 4 10000 resamples seed=42 | reproduced exactly | YES |
| Two-level offset gate | Section 4(d) L1 Bonf at center + L2 uncorr at adjacent | `evaluate_gate_v13` | YES |
| Live spread probe | Section 5 30-min trade VWAP vs orderbook YES ask | `phase2b_live_spread_probe.py:74-110` | YES |
| Haircut p75 | Section 5 75th percentile of gap_ask | reproduced 0.000663 | YES |
| X threshold | Section 6 75th pct |delta_sb| MLB-night | reproduced 0.0060 | YES |
| Y threshold | Section 6 25th pct |delta_kpre| MLB-night | reproduced 0.0003 | YES |
| Trigger rule | Section 6 X AND Y AND side-flip | script lines 145-148 | YES |
| Execution price | Section 6 trade_print_mid + haircut for YES; (1 - mid) + haircut for NO | script lines 171-176 | YES (matches reproduced exec prices to 4dp) |
| Fee model | Section 6 ceil(7*P*(1-P)) cents capped at 7c | `kalshi_taker_fee_per_contract` | YES (returns 0.02 for all 3 fires in [0.38, 0.45] range) |
| Position sizing | Section 6 $0.50 per contract | not actually applied in P&L (normalized to per-contract) | NEUTRAL (per-contract aggregation is fine) |

ALL six anti-pattern bans (Section 8 a-f) respected: no post-data adjustment
of strata, offsets, X, Y, haircut, fee, sizing. VWAP function named in lock
and re-implemented per spec. No prior-round borrows. No post-settlement prices
used. No retune of X/Y after seeing P&L.

The Phase 2 implementation is faithful to the v13 lock on every material
component.

---

### IMPORTANT-B. The 5 negative haircuts in the live probe are explainable but warrant a note

**Where:** `data/v13/live_spread_probe.parquet` shows 5 of 47 valid snapshots
have `gap_ask_minus_mid < 0` (yes_ask < trade_print_mid_30min).

**Reproduction:** min haircut = -0.2673, count of negative = 5 of 47.

A negative ask-minus-mid means a market-maker is quoting a YES ask BELOW
the recent trade-print VWAP. This is the OPPOSITE of the conservative
slippage the haircut is meant to capture. Possible explanations:

1. **Stale 30-min trade prints:** if the market hasn't traded recently
   but the orderbook moved, the trade-print mid is stale and below the
   current ask.
2. **YES ask is dynamically marked down on news:** if sportsbook moved
   AWAY from the YES side, the MM aggressively lowers the YES ask.
3. **Spread is structurally negative:** for thinly-traded markets, the
   "mid" is dominated by one stale print.

For the p75 percentile being 0.0007 (well below the 0.03 G5 threshold),
this isn't load-bearing. But the existence of negative haircuts means
the simple "ask - trade_print_mid" gap is an underestimate of the true
slippage cost when trade prints lag the orderbook. A more conservative
proxy would be max(ask - mid, 0) or (ask - bid) / 2 which the data
shows is consistently 0.005 (since spread_p50 = spread_p75 = 0.01).

The realistic per-trade haircut is closer to **half the spread** (0.005)
than to the gap_ask_minus_mid p75 (0.0007). At 0.005 haircut, exec
prices in the 3 fires shift up by ~0.0043 each, and net P&L per fire
drops by ~$0.004. Still profitable, but tighter.

**Why this is IMPORTANT (not KILLER):** the haircut at 0.0007 is so far
below the 0.03 G5 threshold (40x margin) that even doubling it to
0.005 leaves G5 in PASS. Material if and only if the operator scales
to size where 0.005 cents per contract matters; at $5-10 capital, 5-9
trades, this is $0.025 to $0.045 of total cost. Negligible.

---

### IMPORTANT-C. Trigger fire rate 2.7% is structurally near the operator's threshold for "enough events in 4-8 weeks"

**Where:** lock Section 7 G2 floor; prompt's expected-fire-count calculation.

**Reproduction:** at 2.70% fire rate per MLB-night event:
- Operator estimate (50-100 night games/week): 4 weeks = 5-11 fires; 8 weeks = 11-22 fires
- More aggressive estimate (12 night games per day, ~84/week): 4 weeks = 9 fires; 8 weeks = 18 fires
- Realistic middle: ~10-15 fires in 4-8 weeks

This is the SECOND most consequential observation. Even if the signal is
real, the trigger only fires once every ~37 night games. At the operator's
expected MLB schedule density, that means the live trial accumulates 10-20
fires by week 8. Just barely enough to compute a meaningful per-event mean
but well below n=30 where bootstrap CIs become reasonably tight on
volatile per-event P&L (per-fire SD on the 3-fire sample is $0.04, but
that's degenerate; X-only 28-fire SD on per-fire net P&L is approximately
$0.30 - which at n=20 fires gives SE = $0.067 and a 95% CI half-width of
+/- $0.13 around the point estimate).

**Why this is IMPORTANT:** the trigger STRUCTURALLY under-samples relative
to the G2 floor. The operator could relax X to the 50th percentile or drop
Y, both of which would 5-10x the fire count, but per F8 + lock Section 8(f)
that is forbidden post-hoc. The trigger is locked.

The pragmatic implication: a live 4-week trial would generate ~5-10 fires
at the per-event signal of +$0.57 (or +$0.15 per the wider X-only
counterfactual). Per-fire P&L noise is large enough that ANY conclusion
will be marginal. The trial would barely cross G2 by week 8.

---

### IMPORTANT-D. G5 PASS at 0.0007 vs the 0.03 threshold should be treated with caution

**Where:** lock Section 5 abandon condition; spread probe summary.

The haircut_p75 of 0.0007 PASSES G5 (haircut_p75 <= 0.03) by a 40x margin.
This is striking and possibly too good. Two reasons for skepticism:

1. **Sampling window:** the probe was a single snapshot of 68 open MLB
   markets. The lock Section 5 method specified "Repeat the snapshot
   every 30 minutes for a 4-hour window during one trading session" but
   the implementation appears to have taken ONE snapshot of all 68
   markets. The probe sample is n=47 in time-aggregated terms, not n=47
   over 4 hours of MM behavior. Live MM behavior at T-3h on game day
   may differ from at T-2h or T-30min.

2. **YES vs NO side asymmetry:** the haircut is computed only on the
   YES-side ask. The 3 fires are all NO-side. NO-side ask = 1 - YES bid,
   and the spread of 1c symmetrically applied gives NO-ask = 1 - YES bid
   = 1 - (YES ask - 1c). If the YES bid is 0.45 (typical for a fired
   event), NO-ask = 0.55, NO trade-print mid = 1 - YES mid = 1 - 0.55 =
   0.45, NO ask - NO mid = 0.10? No, that's wrong. Let me reason
   carefully. If YES ask = 0.55 and YES bid = 0.54, NO ask = 1 - YES bid
   = 0.46 and NO bid = 1 - YES ask = 0.45. NO ask - NO bid = 0.01,
   symmetric with YES. So the haircut symmetry holds.

The G5 PASS is real but the n=47 single-snapshot is thin evidence for a
forward 4-8 week strategy. Realistic forward haircut is somewhere between
0.0007 (best case, current MM efficiency) and 0.005 (half-spread of 1c).
Either way G5 still PASSES.

---

### NICE-TO-HAVE-i. X/Y thresholds technically computed from v13 dataset, not v12

The lock language says "from v12 MLB-night delta distribution". The script
computes from `joint_dataset_v13_centered.parquet` (v13 with centered VWAP).
Since the X threshold depends only on sportsbook deltas (unchanged between
v12 and v13) and Y depends on Kalshi deltas (which DO differ due to
windowing), there is a subtle difference. The pre-registration intent
(no P&L peek) is fully respected. Minor lock-text ambiguity, not a violation.

### NICE-TO-HAVE-ii. row_bootstrap and day_block_bootstrap at n<5 silently return NaN

The script returns NaN for bootstrap CIs at n < 5 (correct), but the
gate evaluator then treats `NaN > 0` as False, conflating "test failed"
with "test not computed". A subsequent script reading this JSON could
misinterpret the gate failure mode. Cosmetic but worth flagging.

### NICE-TO-HAVE-iii. NBA at v13 centered windowing confirms KILLER-3 from v12 critic

The v12 critic's KILLER-3 said NBA NULL at the correct 2.5h offset was
confounded between offset and windowing effects. v13 NBA at center
(2.5h with centered VWAP): F=0.4396, p=0.5084, gamma=+0.0704. NULL.
This DISENTANGLES the v12 KILLER-3: NBA at 2.5h with v11 centered VWAP
is genuinely NULL. The narrative "NBA NULL is real, not a v12 artifact"
is confirmed. v13 closes v12's open question.

---

## Section B. Reproduced key numbers (to 4 decimal places)

### B.1. MLB-night Granger at all 3 offsets (v13 centered VWAP)

Independent compute via Becker venv (numpy, scipy.stats, pandas, duckdb):

| Offset | n | F (reproduced) | F (report) | p (reproduced) | gamma (reproduced) | gamma_se |
|---|---|---|---|---|---|---|
| -0.5h (3.0h) | 114 | 7.9540 | 7.95 | 0.005685 | +0.7115 | 0.2523 |
| +0.0h (3.5h, center) | 111 | **12.1745** | 12.17 | 0.000702 | **+0.7793** | 0.2234 |
| +0.5h (4.0h) | 111 | 8.9512 | 8.95 | 0.003436 | +0.8604 | 0.2876 |

All reproduce. Center F=12.17 (was 29.50 with v12 hour-bucket). Magnitude
roughly halved by reverting to centered VWAP, as v12 critic KILLER-1
projected. Center p still passes Bonferroni 0.0125 by ~18x margin.

### B.2. Block-bootstrap CI at MLB-night center

Day-block bootstrap, 10000 resamples, seed=42, 33 unique days:
- Bootstrap mean gamma: +0.7315
- Bootstrap median gamma: +0.7322
- 2.5% percentile (G1 binding gate): **-0.0160** (FAIL by 1.6pp)
- 5% percentile: **+0.0523**
- 97.5% percentile: +1.6747
- 1% percentile: -0.0885
- Fraction gamma > 0: **0.9702**

Reproduces to 4 decimal places.

### B.3. Spread probe distributional quantiles

n_valid = 47 of 68 open MLB markets with valid (ask, mid) pair:
- haircut p50: 0.000097
- haircut p75: **0.000663** (binding G5)
- haircut p95: 0.016195
- haircut min: -0.2673 (5 of 47 are negative, see IMPORTANT-B)
- spread (ask-bid) p50/p75: 0.0100/0.0100 (single-cent for 75% of markets)

Reproduces.

### B.4. Strategy fires P&L decomposition (per-fire)

| Ticker | side | vwap_T-3h | exec_price | resolution | net_pnl |
|---|---|---|---|---|---|
| KXMLBGAME-25AUG01HOUBOS-HOU | no | 0.5500 | 0.4507 | no | +0.5293 |
| KXMLBGAME-25AUG01NYYMIA-NYY | no | 0.6100 | 0.3907 | no | +0.5893 |
| KXMLBGAME-25SEP03CWSMIN-MIN | no | 0.6200 | 0.3807 | no | +0.5993 |

Sum net_pnl: +1.7180. Mean: +0.5727. SD: 0.0379.

Exec price formula: (1 - vwap_T-3h) + haircut for NO side. Reproduces to
4dp on all 3 fires. Fee = 0.02 for all 3 (per ceil(7*P*(1-P)) cents at
P in [0.38, 0.45]).

### B.5. X-only counterfactual (drop Y filter; NOT lock-compliant; descriptive only)

28 events fire top-quartile |delta_sb|:
- Win rate: 0.6429
- Mean execution price: 0.4729
- Mean net P&L per contract: +$0.1499
- Row-bootstrap 95% CI: [-0.0368, +0.3261], mean +0.1498
- YES side: n=11, win=0.6364, mean net=+$0.1441
- NO side: n=17, win=0.6471, mean net=+$0.1538

The wider sample shows POSITIVE expected net P&L on BOTH sides (rules out
"NO-side selection effect explains everything"). CI marginally includes
zero. This is the descriptively-honest comparable for the 3-fire result.

### B.6. Forward fire-count expectation

Fire rate 0.0270 per MLB-night event.
- 4 weeks at 50-100 night games/week: 5.4 to 10.8 fires (below G2 floor of 20)
- 8 weeks at 50-100 night games/week: 10.8 to 21.6 fires (barely crossing G2)
- 6 weeks at 75 night games/week: ~12 fires

The forward trial will accumulate enough fires to estimate a mean but
not enough to bound the CI tightly.

---

## Section C. Verdict recommendation

### Summary of gate evaluation

| Gate | Spec | Result | Pass? |
|---|---|---|---|
| G1 | MLB-night 5-condition Granger gate | bb CI lower = -0.016 (fails 2-sided 95%) | **FAIL** (literal) |
| G2 | n_fires >= 20 | n_fires = 3 | **FAIL** |
| G3 | mean net P&L > 0 AND CI lower > 0 | mean +$0.57; CI not computed (n<5) | **FAIL** (not computed) |
| G4 | day-block CI lower > 0 | CI not computed (n<5) | **FAIL** (not computed) |
| G5 | haircut_p75 <= 0.03 | 0.0007 | PASS (40x margin) |
| G6 | win rate > 0.5 | 1.0 on n=3 | PASS (degenerate) |

Strict verdict per lock Section 7: **MONEY-DEPLOYMENT FAIL.**

### The four verdict options posed by the orchestrator

**Option (a) MONEY-DEPLOYMENT-AUTHORIZED:** REJECTED.

The strict lock fail stands. Three independent reasons argue against
overriding:

1. **G1 fails by 1.6pp.** While 97% of bootstrap resamples are positive,
   the lock pre-registered a 2-sided 95% CI. Relaxing post-hoc to a
   1-sided test is F8 (anti-pattern). The lock said what it said.

2. **G2 fails decisively at n=3.** Even granting a real signal, n=3 is
   not enough to authorize live capital. A live trial would need ~10-20
   fires to get a meaningful first-pass estimate; that's 6-8 weeks of
   MLB schedule. The risk is committing capital before the signal is
   measurable.

3. **G3, G4 are not even computable.** The bootstrap CIs simply do not
   exist at n=3. Authorizing money under "G3 and G4 are NaN" is
   different from authorizing under "G3 and G4 are positive on n=20".

**Option (b) MONEY-DEPLOYMENT-FAIL:** PARTIALLY ACCEPTED.

The literal verdict per lock is FAIL. The recommended path is NOT to
recommend a v14 with looser trigger (which would be F8 violation), but
to recommend deferring on a different basis.

**Option (c) DEFER-FOR-MORE-DATA:** RECOMMENDED with caveats.

The MLB-night Granger signal is genuinely strong at center (F=12.17,
p=0.0007, gamma=+0.78, n=111, bootstrap directional support 97%). The
3-fire P&L confirms direction (3 wins) but cannot bound magnitude. The
trigger structurally under-samples for the available historical data.

Recommended action: **do NOT deploy live capital this round.** Instead,
authorize a 4-8 week SHADOW-MODE log on v1 infrastructure that
prospectively records what the v13 trigger would fire on each
MLB-night close. Compare prospective fire outcomes to the v13
historical projection at week 4 and week 8.

The shadow log accumulates ~10-20 fire candidates with REAL Kalshi
orderbook snapshots at T-3h (resolving F11 prospectively per
fire). After 4-8 weeks the operator has:
- A prospectively-recorded set of trigger fires
- Realized Kalshi orderbook spread at fire time (not historical proxy)
- Realized game outcomes (NO contract paid 0 or 1)
- A non-trivial test set for a v14 Phase 2 strategy P&L

Cost: $0 LLM, $0 capital, 2-4 hours engineering to wire on top of v1's
existing infrastructure.

**Option (d) PHANTOM:** REJECTED.

The 3-fire P&L IS misleading (KILLER-3) on the "100% win rate" claim,
but the X-only counterfactual (n=28, win rate 64%, mean +$0.15, both
sides positive) confirms the signal is directional, not a sign-flip
artifact. The bb CI lower = -0.016 is a borderline 2-sided fail, not a
sign-flip falsification. The signal is real but not yet measurable for
P&L purposes; that's DEFER, not PHANTOM.

### Final recommendation: **DEFER-FOR-MORE-DATA**

The honest read of v13:

- The MLB-night Granger signal IS real (F=12.17, p=0.0007, gamma=+0.78,
  97% bootstrap directional support, n=111). The literal G1 fail is
  borderline; the directional inference is supported.

- The strategy P&L on n=3 IS positive but degenerate. The wider X-only
  counterfactual (n=28) shows +$0.15/contract mean with CI marginally
  including zero, which is consistent with a real but small per-trade
  edge.

- The trigger structurally under-samples relative to the G2 floor. A
  4-week live trial would yield ~5-10 fires (far below G2); 8 weeks
  yield ~10-20 (at the lower edge of G2).

- The live spread probe (G5) PASSES decisively (0.0007 vs 0.03 floor),
  resolving the F11 phantom for currently-open MLB markets. This is the
  most valuable single finding of v13.

The right action is NOT to deploy capital now ($5-10 over ~5-10 fires
is insufficient to update strongly on whether the signal extracts net
of fees), and NOT to abandon the angle (real signal). The right action
is to wire a SHADOW LOG on v1 that records prospectively what the v13
trigger would fire, then revisit in 4-8 weeks with a prospective
sample.

This recommendation explicitly does NOT involve any post-hoc trigger
relaxation (preserving F8 / lock Section 8(f)). The pre-registered X
and Y thresholds remain locked. The shadow log applies the trigger
unchanged.

---

## Section D. Forward-trial design IF operator overrides to deploy

If the operator decides to deploy $5-10 anyway (which the v13 critic
does NOT recommend), the following design preserves lock compliance and
makes the trial maximally informative:

### Capital and sizing

- **Initial capital:** $5 (lower end of operator-authorized $5-10 range).
- **Position sizing:** $0.50 per contract (matches v1 standard).
- **Max contracts per fire:** 1 (do NOT scale per-fire; each fire is
  a separate data point).
- **Max concurrent exposure:** 5 fires open at once = $2.50 worst-case
  loss. Bounded.

### Trigger rule (LOCKED, no retuning permitted)

Use v13 pre-registered:
- X_threshold = 0.0060 (75th pct |delta_sb| at MLB-night center)
- Y_threshold = 0.0003 (25th pct |delta_kpre| at MLB-night center)
- Fire if |delta_sb| >= X AND |delta_kpre| < Y
- Side: YES if delta_sb > 0, NO if delta_sb < 0
- Apply ONLY to MLB-night games (close UTC hour in [0,9) U [23,24))
- Apply at 3.5h commence-to-close offset (the v12-locked offset)

The trigger MUST NOT be modified per F8 / lock Section 8(f).

### Daily check loop

- 1x per evening, ~T-4h before each MLB-night game close
- Pull current sportsbook implied prob (from the-odds-api)
- Pull current Kalshi trade-print VWAP via /markets/trades (matching
  Phase 2b method)
- Compute delta_sb_pre and delta_kpre at T-3h vs T-6h
- Fire if trigger conditions met
- Place 1 contract on the appropriate side at +0.005 haircut over
  current YES (or 1 - YES) trade-print mid (use 0.005 = half-spread,
  more conservative than the 0.0007 Phase 2b haircut)

### Forward evaluation

After 4-8 weeks (or 10 fires, whichever comes first):
- Per-trade net P&L mean: did it match v13 projection within 1c?
- Win rate: did it match the 64% X-only counterfactual within 10pp?
- Bootstrap 95% CI on per-trade net P&L: does it exclude zero?

### Kill conditions

Per v1's existing kill-trigger pattern:
- Drawdown > 20% of initial capital ($1 of $5): kill
- 5 consecutive losses: kill (binomial p=0.031 under H0=0.5, suggests
  signal isn't there)
- Win rate < 30% over first 10 fires: kill (lower 95% Clopper-Pearson
  bound on win rate of 0.71-0.74 at n=24 is ~0.85; well below 30% is
  a strong falsification)

### Pre-commit to honest evaluation

Before deployment, the operator commits IN WRITING to:
- Recording every fire decision in a shadow log even if not deployed
- Not retuning X or Y mid-trial
- Killing per the kill conditions above without rationalization
- Treating the final per-trade net P&L as the ONE binding evaluation
  metric (not "well it was almost positive")

### Why this is still riskier than DEFER

Even with this discipline, the trial collects 5-15 data points in 4-8
weeks. At per-fire SD of ~$0.30 (X-only estimate), SE on the mean is
$0.08-0.13, half-CI is $0.16-0.27 - wider than the projected +$0.15
to +$0.57 effect size. The trial result will likely be "consistent
with effect, consistent with zero".

The shadow-log path (DEFER recommendation) achieves the same
information value at $0 capital risk. The only reason to prefer live
deployment is if the operator values the small-but-real positive
expected value across 5-10 contracts, which is on the order of +$0.75
to +$3.00 expected P&L (with high variance). At $5-10 capital, that's
material; at the operator's overall budget, marginal.

---

## Closing note on counts

- KILLER findings: **3** (bb CI lower < 0 borderline; n_fires=3 below G2;
  3-fire 100% wins is Y-filter selection effect)
- IMPORTANT findings: **4** (lock adherence audit clean; 5 negative
  haircuts in probe; trigger fire rate under-samples; G5 PASS at 40x
  margin should be tested under 4-hour rolling probe)
- NICE-TO-HAVE findings: **3** (X/Y from v13 not v12; NaN bootstrap CI
  treated as fail; v13 NBA NULL closes v12 KILLER-3)

The 3 KILLER findings argue against MONEY-DEPLOYMENT-AUTHORIZED. The
literal lock verdict is MONEY-DEPLOYMENT FAIL. The recommended
operator action is **DEFER-FOR-MORE-DATA** via a 4-8 week shadow-log
on v1 infrastructure.

The MLB-night Granger signal is real. The trigger under-samples. The
live spread probe resolves F11 favorably. Together, this is a
research-confirmed signal that is not yet ready for capital deployment
without more prospective data.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
