# v13 Phase 1.5 Methodology Lock

**Round:** 18 (v13)
**Date:** 2026-05-27 by orchestrator after operator authorized "keep going until you find a signal strong enough to put money on".
**Inherits:** v11 lock v2 + v3 amendment (universe, split). v12 lock (strata, offsets, block-bootstrap). v13 amends only the windowing function, P&L execution model, and money-deployment gate.
**Status:** binding. Phase 2 entry permitted.
**Scope:** address v12 KILLER-1 (windowing), KILLER-3 (NBA disentangle), F11 (live execution viability) and produce a binding money-deployment recommendation.

This lock pre-registers a MONEY-DEPLOYMENT GATE. If the gate fires PASS, the operator is authorized to deploy initial small capital (target $5 to $10) to live-test the strategy for 4 to 8 weeks. If the gate fires FAIL, Track 1 closes for this round; no capital.

---

## What v13 changes from v12

| Component | v12 lock | v13 lock |
|---|---|---|
| VWAP windowing | hour-bucket forward-anchored (silent KILLER-1) | v11-centered +/- 30min via direct DuckDB query; PRE-REGISTERED as `centered_30min_vwap` |
| Strata | 4 (MLB-day, MLB-night, NBA, NFL) | 4 same |
| Commence offsets | MLB 3.5h, NBA 2.5h, NFL 3.5h | UNCHANGED |
| Offset robustness gate | Bonferroni at every offset | Bonferroni at center AND uncorrected 0.05 at adjacent offsets |
| Goal | re-test the Granger hypothesis | re-test + LIVE SPREAD PROBE + STRATEGY P&L SIMULATION + MONEY-DEPLOYMENT GATE |
| Live spread probe | none | yes, on currently-open MLB markets |
| Strategy P&L | deferred to future round | yes, pre-registered trigger rule, execution model, fees, sizing |
| Money-deployment authorization | none | conditional pre-registration; PASS = deploy $5-10 for 4-8 weeks |

---

## 1. Universe (unchanged from v12)

Same 408-event matched sample. Same Becker post-Oct-2024 cohort. Same per-sport median chronological splits.

## 2. VWAP function (pre-registered, locked)

```python
def centered_30min_vwap(con, ticker, target):
    """v11-equivalent VWAP centered on target. +/- 30min half-window.
    Returns VWAP in dollars (price/100).
    """
    lo = target - timedelta(minutes=30)
    hi = target + timedelta(minutes=30)
    sql = "SELECT SUM(yes_price*count) / NULLIF(SUM(count),0) AS vwap " \
          "FROM trades WHERE ticker = ? " \
          "  AND created_time >= ? AND created_time < ?"
    result = con.execute(sql, [ticker, lo, hi]).df()
    return result.iloc[0]["vwap"] / 100.0 if result.shape[0] else nan
```

Slower than v12's hour-bucket (one query per event-offset-window cell), but eliminates the unauthorized windowing change from v12 KILLER-1.

## 3. Strata + offsets (unchanged from v12)

- MLB-day: close UTC hour [17, 23)
- MLB-night: close UTC hour [0, 9) UNION [23, 24)
- NBA: all KXNBAGAME
- NFL: all KXNFLGAME

Sport-specific commence offsets:
- MLB-day, MLB-night: 3.5h
- NBA: 2.5h
- NFL: 3.5h

Offset robustness range: +/- 0.5h around each center.

## 4. Granger gate (revised offset-robustness per v12 L4)

For each stratum with n >= 50 (joint coverage):

Binding gates (all must pass):

a) **Center Bonferroni:** p_value at the center offset <= 0.05/4 = 0.0125
b) **gamma > 0:** positive direction at the center offset
c) **Block-bootstrap CI lower > 0:** 95% CI from 10,000 day-block resamples, seed=42
d) **Offset robustness, two-level:**
   - Level 1 (hard): center passes Bonferroni 0.0125
   - Level 2 (soft): both adjacent offsets (+/- 0.5h) pass uncorrected alpha 0.05
   - PASS if Level 1 AND Level 2 hold

Stratum passes overall iff (a) AND (b) AND (c) AND (d).

NFL has the OR-of-2 (NFL-A classic AND NFL-B expanded) within-stratum Bonferroni alpha 0.05/8 = 0.00625 at center.

## 5. Live Kalshi spread probe (Phase 2b)

Goal: quantify the actionable haircut between Kalshi orderbook ASK and trade-print mid for currently-open KXMLBGAME markets in the T-6h to T-1h pre-close window (when MLB games are mid-day to evening per the current operator clock).

### Method (pre-registered)

1. Query Kalshi /events endpoint for currently-active KXMLBGAME events with close_time in the next 24 hours.
2. For each event, for each market (YES and NO sides):
   a. Pull /markets/{ticker}/orderbook (current bid/ask/depth)
   b. Pull last 30 minutes of trades via /markets/trades?ticker={ticker}&limit=200
   c. Compute trade_print_VWAP_30min, current yes_ask, current yes_bid
   d. Record (timestamp, ticker, yes_ask, yes_bid, trade_print_VWAP_30min, n_trades_30min)
3. Repeat the snapshot every 30 minutes for a 4-hour window during one trading session.
4. Compute distribution of `gap_ask = yes_ask - trade_print_VWAP_30min` across all snapshots.

### Pre-registered haircut

- `haircut_p75 = 75th percentile of gap_ask` across the live probe sample
- This is the haircut used in Phase 2c strategy P&L (worst-case for typical fills)

### Abandon condition

If `haircut_p75 > 0.05` (5 cents per contract), the execution model is non-viable for a 1c to 3c expected lift; v13 verdict is PHANTOM-EXECUTION and money-deployment gate fails.

### Sample-size floor

If the live probe sample is below n=20 (markets * snapshots after dedup), the probe is inconclusive. Default in this case: haircut_p75 = 0.02 (a conservative 2c haircut, used only if sample is too small to estimate).

## 6. Strategy P&L simulation (Phase 2c)

### Trigger rule (pre-registered from v12 data BEFORE the v13 re-run)

For each Becker MLB-night event in the v12 joint dataset (n=109 with all 3 deltas non-null):

- Compute `delta_sportsbook_pre = p_sb_yes_T-3h - p_sb_yes_T-6h` at center offset 3.5h
- Compute `delta_kalshi_pre = kalshi_vwap_T-3h - kalshi_vwap_T-6h` at center offset 3.5h
- **Fire condition:** `|delta_sportsbook_pre| >= X_THRESHOLD` AND `|delta_kalshi_pre| < Y_THRESHOLD`
- **Side:** take the side sportsbook moved TOWARD (YES if delta_sportsbook_pre > 0, NO if < 0)
- **Execution price:** `trade_print_mid_at_T-3h + haircut_p75` (from Phase 2b)
- **Settlement:** at market close, market resolves to 1 if YES wins, 0 if NO wins

### Pre-registered thresholds

Computed from the v12 MLB-night delta distribution BEFORE running P&L:
- X_THRESHOLD = 75th percentile of `|delta_sportsbook_pre|` for MLB-night events
- Y_THRESHOLD = 25th percentile of `|delta_kalshi_pre|` for MLB-night events

These are distributional quantities derived from the deltas alone (no P&L peek). Pre-registered values to be filled in after Phase 2a re-run + threshold computation; locked before P&L simulation.

### Fee model

```python
from src.kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract
fee = kalshi_taker_fee_per_contract(price=execution_price_proxy, contracts=1)
```

Verified-from-research formula: `ceil(7 * price * (1-price))` cents, capped at 7c per contract.

### Position sizing

$0.50 per contract (matches v1's per-trade budget). One contract per fire.

### Net P&L per trade

```
gross = realized_outcome (1 or 0) - execution_price_proxy
net = gross - fee
```

### Strategy aggregate metrics

- n_fires: number of events where the trigger rule fires
- mean_net_pnl_per_trade
- bootstrap_95_CI_lower (per-event row bootstrap, 10k resamples, seed=42)
- LOCO-by-day pass: net_pnl > 0 with day-block bootstrap CI excluding 0
- win_rate: fraction of trades with net > 0

## 7. Money-deployment gate (PRE-REGISTERED)

PASS = recommend operator deploy $5 to $10 initial capital for 4-8 week live trial.
FAIL = close Track 1 for this round; no capital.

All of the following must hold for PASS:

G1. **MLB-night Granger gate passes the v13 5-condition test** (per Section 4 above). Live-or-die requirement.

G2. **n_fires >= 20** in Phase 2c strategy P&L simulation. Below this, the live trial cannot accumulate enough events for evaluation in 4-8 weeks of MLB season.

G3. **Strategy mean net P&L per trade > 0** with bootstrap 95% CI lower bound > 0 in Phase 2c.

G4. **Strategy LOCO-by-day robust:** net P&L > 0 with day-block bootstrap 95% CI excluding 0.

G5. **Phase 2b live spread probe haircut_p75 <= 0.03** (3 cents). If higher, execution is unviable.

G6. **Win rate > 50%** in Phase 2c. A directional taker strategy with win rate below 50% is structurally fragile.

ANY failure of G1 through G6 = money-deployment FAIL.

Verdict mapping:
- ALL of G1-G6 pass: **MONEY-DEPLOYMENT-AUTHORIZED**
- G1 passes, G3-G6 fail: **SIGNAL-CONFIRMED-NOT-MONETIZABLE** (clean kill of money plan)
- G1 fails: **NULL-v13** (signal didn't survive v13 cleanup)

## 8. Anti-pattern bans (preserved + extended)

Inherited from v11+v12:

a) No post-data adjustment of strata, offsets, X/Y thresholds, haircut, fee, sizing, or gates
b) No silent re-implementation of derived features (VWAP, fee, etc.); all functions are named modules, lock cites them
c) No prior-round borrows for the money-deployment thresholds (G2 n>=20 derived from "4-8 weeks of MLB season at ~15 games/day * 0.X fire rate"; G3 CI > 0 from first-principles return required; G5 haircut <=3c from cost-structure derivation; G6 50% from random-baseline)
d) No use of post-settlement prices for any computation (F7 defense)
e) No live capital deployment based on backtest alone; the money-deployment gate explicitly requires Phase 2b live spread probe to pass (resolves F11 by direct measurement, not just backtest assumption)

v13-specific extension:

f) No re-running Phase 2c with different X/Y thresholds after seeing P&L. The thresholds are derived from the delta distribution BEFORE P&L computation.

## 9. Phase 2 sequencing

### Step 2a (in-session): re-run with v11 centered VWAP

Run Phase 2b-equivalent of v12 but with `centered_30min_vwap` (Section 2). 4 strata at center + +/- 0.5h offsets. Same block-bootstrap. Same 5-condition gate with v13's revised offset robustness (level 1 hard + level 2 soft).

Per-stratum result table. KILLER-3 disentangle: at the locked NBA 2.5h offset with centered VWAP, what is F?

### Step 2b (in-session): live Kalshi spread probe

Run the probe per Section 5. Save raw orderbook snapshots to data/v13/live_spread_probe.parquet. Compute haircut_p75. Apply abandon condition.

### Step 2c (in-session): strategy P&L

Compute X_THRESHOLD, Y_THRESHOLD from v12 MLB-night delta distribution (no P&L peek). Lock the thresholds. Run trigger rule on v12 MLB-night events. Apply execution model with Phase 2b haircut. Compute net P&L per trade + aggregate metrics.

Money-deployment gate evaluated.

### Step 3 (in-session): Phase 3 adversarial critic

Spawn critic agent. Reproduce numbers. Audit pre-registration adherence. Recommend verdict.

### Step 4 + 5 (in-session): salvage + FINAL-VERDICT

## 10. Operator handoff at lock close

The v13 verdict is binding for THIS round only. If MONEY-DEPLOYMENT-AUTHORIZED fires, the operator's separate authorization to actually deploy capital is required (this lock does not auto-authorize capital). The lock pre-registers the EVIDENCE BAR; the operator authorizes the ACTION.

If money is deployed, set up a forward observation:
- 4-8 week live trial
- Pre-registered evaluation at end: did per-trade net P&L match the v13 Phase 2c projection within 1c?
- Future v14 (if pursued) would evaluate the live trial results.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
