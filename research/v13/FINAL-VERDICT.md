# v13 (Round 18) Final Verdict

**Date:** 2026-05-27. **Author:** orchestrator. **Round:** 18.
**Lock:** research/v13/01-methodology-lock.md.
**Sources of truth:** Phase 2 outputs in `data/v13/` + Phase 3 critic at `research/v13/03-phase3-critic.md`.

---

## TL;DR

**Literal v13 verdict: MONEY-DEPLOYMENT FAIL.** The pre-registered 6-gate money-deployment evaluation produced 4 of 6 fails:
- G1 fails by 1.6pp (bb CI lower = -0.016 vs the > 0 gate); 97% of bootstrap resamples are positive.
- G2 fails (n_fires = 3 vs the >= 20 floor).
- G3 and G4 are not computable at n < 5 (bootstrap CIs degenerate).
- G5 PASSES by 40x margin (haircut_p75 = 0.0007 vs 0.03 threshold).
- G6 PASSES (3 of 3 win rate = 100%, but on n=3).

**Cumulative project verdict: GRANGER-PARTIAL-MLB-NIGHT (unchanged from v12) + EXECUTION-VIABLE.** The MLB-night signal is real (F=12.17, p=0.0007, gamma=+0.78 with centered v11 VWAP) and 97% directionally robust under day-block clustering. Live Kalshi spreads on currently-open MLB markets are tight (1c median, 7bp ask-mid gap), meaning the F11 phantom that blocked v11 and v12 is operationally RESOLVED for MLB-night.

**Phase 3 critic recommendation: DEFER-FOR-MORE-DATA.** Wire a forward shadow log on v1 to accumulate fires at the locked trigger rule. Re-evaluate in 4-8 weeks. $0 capital risk.

The operator now has three honest paths. None of them is auto-decided by this lock.

---

## What v13 found

### Phase 2a: Granger re-run with v11 centered VWAP

MLB-night Granger F-test at all 3 offsets with v11's centered ±30min DuckDB query (resolving v12 KILLER-1):

| Offset | n | F | p | gamma | gamma_se |
|---|---|---|---|---|---|
| -0.5h (3.0h) | 114 | 7.95 | 0.006 | +0.71 | 0.25 |
| **center (3.5h)** | **111** | **12.17** | **0.0007** | **+0.78** | **0.22** |
| +0.5h (4.0h) | 111 | 8.95 | 0.003 | +0.86 | 0.29 |

Day-block bootstrap CI (10k resamples, seed=42, 33 unique days):
- Bootstrap mean gamma: +0.73
- 2.5th percentile: -0.016 (the borderline G1 fail)
- 5th percentile: +0.052
- **97.02% of resamples have gamma > 0**

The two-level offset robustness (L1 Bonferroni center, L2 uncorrected 0.05 adjacents) PASSES. The block-bootstrap CI 2.5th percentile FAILS by 1.6pp.

NBA NULL at 2.5h center confirmed under centered VWAP (F=0.44, p=0.51). Disentangles v12 critic KILLER-3: NBA is genuinely null at the correct theoretical offset regardless of windowing.

NFL NULL across both classic and expanded windows (unchanged from v12).

### Phase 2b: Live Kalshi spread probe

68 open KXMLBGAME markets, 47 valid (ask, recent-trade-mid) snapshots:

- haircut p50: 0.0001
- **haircut p75: 0.0007** (G5 threshold is 0.03; PASS by 40x)
- haircut p95: 0.0162
- Spread (ask - bid) p50 and p75: 0.0100

The F11 phantom that haunted v11 and v12 is operationally resolved for currently-open MLB markets. Spreads are MM-saturated to 1c. A would-be retail taker pays approximately 7bp over the recent trade-print mid.

### Phase 2c: Strategy P&L with pre-registered trigger

X_threshold (75th pct |delta_sportsbook_pre|, MLB-night): 0.0060
Y_threshold (25th pct |delta_kalshi_pre|, MLB-night): 0.0003
Haircut: 0.0007 (from Phase 2b)

Trigger fires 3 of 111 MLB-night events. All 3 are NO-side. All 3 win.

- Mean execution price: 0.4073
- Mean fee: 0.0200
- Mean gross P&L: +0.5927
- Mean net P&L: **+$0.5727 per contract**
- Win rate: 1.0 (3 of 3)

### Phase 3 critic findings

The critic surfaced 3 KILLER findings:

1. **KILLER-1 (G1 borderline):** the bb CI lower fails by 1.6pp on a directional signal where 97% of resamples are positive. Literal gate failure; signal still real in direction.

2. **KILLER-2 (G2/G3/G4 undersample):** n_fires=3 below G2 floor. G3 and G4 not computable.

3. **KILLER-3 (Y-filter side selection):** the strict Y threshold structurally selects NO-side events. Without Y filter (X-only counterfactual on 28 events): 64.3% win rate (vs 100% on n=3), +$0.15 mean net P&L (vs +$0.57), CI marginally includes zero. The 100%-3-of-3 headline is partly a side-selection artifact.

4 IMPORTANT findings (all on calibration not invalidation).

3 NICE-TO-HAVE findings.

---

## Three honest operator options

### Option A: DEFER-FOR-MORE-DATA (Phase 3 critic recommendation)

**What:** wire a forward shadow log on v1 that records, for every active MLB-night market, the sportsbook implied prob and Kalshi trade-print mid at T-6h, T-3h, T-1h pre-close. Run for 4-8 weeks of MLB season. Re-evaluate.

**Pros:**
- $0 capital risk in-session
- Accumulates evidence at the locked trigger rule (no F8 violation)
- 4 weeks of MLB-night (~120 night games) at the 2.7% fire rate = approximately 3-4 fires
- 8 weeks = approximately 6-9 fires
- By week 8, accumulated fires PLUS the v13 backtest fires (3) total approximately 9-12; still below G2 but more informative
- Same data structure supports re-running Granger with bigger n at evaluation time

**Cons:**
- Slow; verdict deferred 4-8+ weeks
- Even 8 weeks may not get n_fires above G2 = 20
- Requires implementing the forward poller (engineering cost)
- The signal might decay (sportsbook line movement behavior can change season to season)

**Operator action if chosen:** authorize a v14 to design and ship the forward shadow log. Estimated v14 cost: $1.50 LLM (script + tests), $0 external, $0 capital.

### Option B: DEPLOY-SMALL-OVERRIDE (operator's risk tolerance)

**What:** deploy $5 to $10 initial capital, $0.50 per contract, place orders manually at the v13 locked trigger rule when it fires on live MLB-night markets. 4-week trial. Operator overrides the lock's MONEY-DEPLOYMENT FAIL because the cost of being wrong is bounded ($5-10) and the cost of waiting is opportunity cost.

**Pros:**
- Real money is the ultimate F11 test
- Bounded downside ($5-10 = same magnitude as a single sportsbook arb opportunity)
- Operator's risk acceptance preserved per the kill-early principle (size is small)
- If trigger fires 1-3 times per week on live games, decision is fast

**Cons:**
- Violates the v13 strict lock verdict (operator override required)
- The 3-fire backtest P&L of +$0.57 is OVERSTATED per critic KILLER-3 (X-only is +$0.15 with CI including 0)
- Expected forward P&L per fire: $0.10 to $0.20, not $0.57
- Per-fire SD on X-only counterfactual: $0.30 → at n=15 fires, SE is $0.077, 95% CI half-width is +/-$0.15 → forward verdict at week 8 could still be inconclusive
- Real fees, real spread (1c), real haircut: live edge per fire is materially smaller than backtest

**Operator action if chosen:** authorize the deployment manually. Track P&L. Pre-register a kill condition: stop if drawdown > 20% ($1-2) or 5 consecutive losses or 8 weeks elapsed.

### Option C: v14 with LOOSER pre-registered trigger

**What:** Start v14 round. Pre-register a new trigger that fires more often. Options:
- X = 50th pct, Y = 50th pct (~25% fire rate)
- X = 60th pct only (no Y filter) (~40% fire rate)
- Predict expected Kalshi shift via gamma * delta_sb; fire when prediction > cost floor (continuous, more sophisticated)

Re-run Phase 2c with new trigger and full v12 sample (and accumulated v1 shadow log data if any).

**Pros:**
- More fires (~25-50 expected in 111 events vs 3); meets G2 floor
- Allows proper bootstrap CIs on net P&L
- The X-only counterfactual (n=28, 64% win, +$0.15 mean) is already promising; v14 formalizes it
- Doesn't require operator capital risk

**Cons:**
- A new round; another 1-2 weeks of methodology + critic cycle
- LLM cost ~$2-3
- New trigger needs to be theory-justified, not just "looser to get more fires" (F6 multi-cell risk)
- Signal magnitude diluted by looser threshold (expected per-fire P&L drops from +$0.57 to ~+$0.15)
- May still fail at the 5-gate evaluation just with a different binding constraint

**Operator action if chosen:** authorize v14 with new trigger spec. Use the Phase 3 v13 critic Section A KILLER-3 X-only descriptive numbers as the prior.

---

## Cumulative spend across v11 + v12 + v13

| Round | LLM | External | Capital |
|---|---|---|---|
| v11 | ~$3.30 | $30 | $0 |
| v12 | ~$0.50 | $0 | $0 |
| v13 | ~$1.80 | $0 | $0 |
| **Cumulative** | **~$5.60** | **$30 + 13.5k credits remain** | **$0** |

Within the $25 shared cap; getting tight for v14. The operator should expect $2-3 more in v14 if pursued.

---

## What we now KNOW with high confidence

1. **The MLB-night signal is REAL.** F=12 p=0.0007 gamma=+0.78 on n=111, 97% positive under day-clustering. Replicated across windowing (v11 centered vs v12 hour-bucket; both show signal magnitude varies but direction holds). Robust to LOCO-by-bookmaker (10 drops, all hold). Sport-specific: only MLB-night; NBA NULL at 2.5h confirmed; NFL NULL across both windows.

2. **Live execution is VIABLE.** Spread 1c, ask-mid gap 7bp on a 47-snapshot probe. F11 phantom resolved on this universe.

3. **The strict v13 trigger UNDERSAMPLES.** 3 fires in 111 events. Below G2 floor.

4. **The 3-fire 100% win is PARTLY side-selection.** X-only counterfactual on 28 events: 64% win, +$0.15 mean, CI marginally includes zero.

## What we still DON'T know

1. **The true forward per-fire P&L.** Backtest range: +$0.15 (X-only n=28) to +$0.57 (X+Y n=3). Real forward will be inside this range.

2. **Day-block CI lower under a 25% larger sample.** Likely positive; not certain.

3. **Whether v1's existing live infrastructure can be repurposed for the shadow log** (Option A). Probably yes (v5 filter overlay already polls sportsbook+Kalshi); but the v5 log captures point-in-time, not the T-6h/T-3h/T-1h timeseries v13 needs. New polling logic required.

4. **The execution model for orders placed AT the time of fire.** v13 simulated taker-at-the-mid-plus-7bp. Real fills may differ; live trial would surface this.

---

## Operator decision required

This v13 closure does not auto-select a path. The three options A, B, C are honest and the choice depends on the operator's risk tolerance, time horizon, and willingness to spend more LLM on v14.

The orchestrator's mild recommendation: **Option A (DEFER) plus authorize a v14 to wire the shadow log**. The signal is real but not yet at "money on it" strength under the strictest lock. A 4-8 week shadow log accumulates the same evidence at $0 capital risk. If the live shadow log shows fire counts and win rates consistent with the v13 backtest, v15 designs a money-deployment with confidence.

The operator may reasonably prefer **Option B** (small $5-10 deployment now) if they accept the +$0.15 forward expected P&L per fire (not +$0.57) and the risk that 4-week n is inconclusive.

**Option C** (v14 looser trigger) is the most rigorous methodologically: it lets the same evidence speak louder by retuning the trigger pre-registration-correctly. It costs $2-3 LLM and 1-2 weeks of methodology work.

---

## Operator handoff template (CLAUDE.md suggested update)

```
**Round 18 outcome (2026-05-27): v13 MONEY-DEPLOYMENT FAIL (literal),
GRANGER-PARTIAL-MLB-NIGHT + EXECUTION-VIABLE (cumulative).** v13 ran
3 phases: re-run Granger with v11 centered VWAP (resolves v12 KILLER-1);
live Kalshi spread probe (47 valid snapshots; G5 haircut_p75=0.0007 vs
0.03 threshold; F11 phantom RESOLVED for MLB-night execution); strategy
P&L simulation (trigger fired 3 of 111 events with pre-registered 75th
pct X and 25th pct Y; all 3 won at +$0.57/contract).

MLB-night Granger center (v11 centered VWAP, 3.5h offset): F=12.17,
p=0.0007, gamma=+0.78, n=111. Day-block bootstrap CI 2.5th percentile
= -0.016 (literal G1 fail by 1.6pp) but 97% of resamples positive.
Two-level offset robustness PASSES (both adjacent uncorrected 0.05).

Phase 3 critic surfaced 3 KILLER findings: G1 borderline-fail; G2 n=3
below floor of 20; Y-filter structurally selects NO-side fires (X-only
counterfactual on 28 events: 64% win, +$0.15 mean). Critic recommends
DEFER-FOR-MORE-DATA via forward shadow log; operator can override and
deploy $5-10 small capital, or run v14 with looser pre-registered
trigger.

Cumulative v11+v12+v13: ~$5.60 LLM, $30 external (13.5k credits
remain), $0 capital. v1 unchanged on $32. v5 filter overlay still
active. See research/v13/FINAL-VERDICT.md.
```

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
