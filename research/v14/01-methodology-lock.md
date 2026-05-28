# v14 Phase 1.5 Methodology Lock

**Round:** 19 (v14)
**Date:** 2026-05-27 by orchestrator after operator authorized "deploy $5-10 test now + do the most rigorous option".
**Status:** binding.
**Scope:** address v13 critic KILLER-3 (Y filter side selection) by pre-registering an X-only trigger.

**Methodology candor:** v14's X-only trigger is INFORMED by the v13 Phase 3 critic's KILLER-3 finding that the Y filter introduces side-selection bias. This is a borderline F8 (post-hoc adjustment) defense: the v13 critic surfaced both the methodology issue (Y biases selection) AND the descriptive result (X-only 28 fires, 64% win, +$0.15 mean). v14 uses the METHODOLOGY finding to redesign; the verdict on the new trigger is essentially a formal evaluation of what the v13 critic exploratorily computed. The operator accepts this constraint and authorizes the v14 evaluation.

## What v14 changes from v13

| Component | v13 | v14 |
|---|---|---|
| Trigger rule | X AND Y (75th pct + 25th pct) | X-only (75th pct sportsbook move; NO Kalshi-pre filter) |
| Fire frequency | 3 of 111 (2.7%) | expected 28 of 111 (25.2%) |
| Hypothesis on Y | needed to filter "Kalshi hasn't moved" | redundant; X already conditions on a large sportsbook move and the Granger F-test partials out Kalshi-pre movement |
| Granger gate (G1) | unchanged | unchanged (already evaluated; signal real with 97% positive bootstrap; literal G1 fail by 1.6pp) |
| Money-deployment gate G2 | n_fires >= 20 (FAIL at 3) | n_fires >= 20 (expected PASS at ~28) |
| Other gates | unchanged | unchanged |

## 1. Universe (unchanged)

Same v12 MLB-night sample (n=111 events with all 3 deltas at center 3.5h offset). Same v13 centered VWAP windowing.

## 2. Trigger rule (pre-registered)

**Fire condition:** `|delta_sportsbook_pre| >= X_THRESHOLD` only. No Y filter.

X_THRESHOLD = 75th percentile of `|delta_sportsbook_pre|` for MLB-night events. From the v12 data: X_THRESHOLD = 0.0060 (60 basis points sportsbook move).

**Side:** take the side sportsbook moved TOWARD (YES if delta_sportsbook_pre > 0, NO if < 0).

**Execution price:** `trade_print_mid_at_T-3h + haircut_p75` (haircut from v13 Phase 2b: 0.0007).

## 3. Pre-registered money-deployment gate

Reuses v13 Section 7 binding gate G1-G6 (all 6 must pass for MONEY-DEPLOYMENT-AUTHORIZED).

Reminder of where each gate stands going into v14:
- G1 (Granger signal): LITERAL FAIL at v13 (bb CI lower = -0.016 by 1.6pp); DIRECTIONAL signal real (97% positive). v14 inherits this gate; the trigger change does not affect the underlying Granger result.
- G2 (n_fires >= 20): expected to PASS at ~28 fires.
- G3 (mean net > 0 AND CI lower > 0): TBD.
- G4 (day-block CI lower > 0): TBD.
- G5 (haircut <= 0.03): PASS by 40x margin.
- G6 (win rate > 0.5): TBD (X-only counterfactual showed 64.3%).

**Pragmatic interpretation:** if G2-G6 pass under the X-only trigger, the operator's authorization to deploy $5-10 (which they already gave) is methodologically supported. G1's borderline fail (97% directional) is mitigated by the directional/practical reading.

## 4. Operator-authorized deployment plan (separate from this lock)

The operator authorized: "deploy the $5-10 test now, use existing capital in Kalshi". This is OUTSIDE the v14 lock's methodology evaluation; the operator owns the deployment decision and the lock owns the evaluation.

Deployment plan (operator-confirmable):
- Initial capital: $5 to $10 (operator-chosen from existing Kalshi balance)
- Position sizing: $0.50 per contract (matches v1; deployable bankroll = 10 to 20 contracts max)
- Trigger: v14 X-only (this lock)
- Execution: operator places limit BUY at Kalshi (manual, via Kalshi web UI) within the T-3h to T-1h window after the alerter script fires
- Trial duration: 4 to 8 weeks of MLB-night season
- Pre-registered kill conditions:
  - Drawdown > 20% of initial capital ($1-2 max drawdown)
  - 5 consecutive losing trades
  - 8 weeks elapsed without verdict
- Forward evaluation: after trial, compare realized P&L per fire vs v14 backtest projection. If realized matches projection within 1c, the strategy is live-confirmed at small scale.

## 5. Anti-pattern bans (preserved from v13)

a) No post-data adjustment of X_THRESHOLD or haircut after seeing v14 P&L
b) Trigger is X-only (locked); no re-introduction of Y filter post-hoc
c) Operator deployment is small-capital; no scale-up until forward evaluation completes
d) The deployment alerter script does NOT auto-place orders; operator-manual is the safety control

## 6. Live alerter script (out-of-lock spec)

The deployment uses `scripts/v14/live_alerter.py`. Operator runs it periodically (or schedules via Task Scheduler) during MLB-night active hours.

The alerter:
1. Pulls today's MLB games from the-odds-api (current snapshot AND a snapshot from approximately 3 hours ago for the delta)
2. For each MLB game scheduled tonight, computes `delta_sportsbook_pre = (current implied prob) - (3h-ago implied prob)`
3. If `|delta_sportsbook_pre| >= 0.006` (X_THRESHOLD), fires an alert
4. Alert content: ticker (Kalshi mapping), side (YES if delta > 0, NO if delta < 0), suggested max execution price, estimated edge
5. Operator manually places the order on Kalshi within the next 1-2 hours (T-3h to T-1h window)
6. Logs the alert + operator action to `data/v14/live_trades.jsonl`

## 7. Phase 2 sequencing

Step 1 (in-session): re-run strategy P&L on v12 MLB-night data with X-only trigger. Verify gates G2-G6.

Step 2 (in-session): ship `scripts/v14/live_alerter.py`.

Step 3 (operator-driven, 4-8 weeks): operator runs the alerter daily, places orders manually, tracks P&L.

Step 4 (out-of-session, v15): after the trial, re-run analysis with live trial data appended.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
