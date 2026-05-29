# v14 Position Sizing (Round 20, 2026-05-29)

**Author:** parallel-context orchestrator. **Status:** SHIPPED (half-Kelly default).
**Code:** `src/kalshi_bot_v14/daemon.py` (`v14_per_fire_budget_usd`).

## Problem

v14 fires rarely (1-2 MLB-night games/day clear the 60bp X-trigger) and
was placing only 1 contract (~$0.47) per fire, leaving most of its
allocated capital idle. Operator asked for larger, dynamically-sized
orders, scaled by balance and possibly by confidence.

## Method: fractional Kelly on allocated capital, NO confidence scaling

### Confidence scaling tested and REJECTED

Tested whether signal strength (`|delta_sportsbook_pre|`) predicts
per-fire net P&L on the 28 backtest fires (`data/v14/x_only_fires.parquet`):

| Metric | Value |
|---|---|
| corr(\|delta\|, net P&L) | +0.150 |
| corr(\|delta\|, win) | +0.189 |

Tercile breakdown by `|delta|`:

| Bucket | n | \|delta\| range | win rate | mean net P&L |
|---|---|---|---|---|
| low | 10 | 0.0061 to 0.0074 | 40.0% | -$0.119 |
| mid | 8 | 0.0086 to 0.0117 | 87.5% | +$0.405 |
| high | 10 | 0.0136 to 0.0604 | 70.0% | +$0.215 |

high-minus-low mean P&L difference: +$0.334, cluster bootstrap CI
**[-0.108, +0.736] (includes zero)**.

**Verdict: do NOT scale by confidence.** The relationship is weak
(+0.15), NON-MONOTONIC (the middle bucket is the best, not the
strongest signal), and the high-vs-low difference CI includes zero.
At n=28 split into terciles of ~9, any apparent pattern is noise.
Sizing on it would be textbook overfitting and violates the project's
no-post-hoc-tuning discipline.

Side observation (NOT acted on here): the lowest-delta bucket (fires
just over the 0.006 threshold) had NEGATIVE mean P&L and a 40% win
rate. This hints that raising the X-trigger threshold might help, but
that is a FIRING-LOGIC change requiring its own backtest and gate, not
a sizing knob. Logged for a future round.

### Kelly derivation

From the v14 backtest (`research/v14/FINAL-VERDICT.md` +
`strategy_pnl_xonly.json`):
- win rate p = 0.643
- avg win gain = +$0.508/contract, avg loss = -$0.495/contract
- net odds b = 0.508 / 0.495 = 1.026
- full Kelly f* = (p*b - (1-p)) / b = (0.643*1.026 - 0.357) / 1.026 = **0.295**

Rounded to **V14_FULL_KELLY_ESTIMATE = 0.30**.

### Why FRACTIONAL Kelly, not full

v14's edge is UNCONFIRMED. The day-block bootstrap CI on per-contract
net P&L is **[-0.020, +0.332]** (includes zero). Full Kelly assumes the
edge equals the point estimate; if the true edge is near the CI lower
bound (zero or slightly negative), full Kelly over-bets a non-edge and
produces real drawdown. Fractional Kelly is the standard remedy for
estimation uncertainty.

**Operator chose 1/2 Kelly (2026-05-29).**

### Formula

```
per_fire_budget_usd = V14_KELLY_FRACTION        # 0.50 (half Kelly), env-tunable
                    * V14_FULL_KELLY_ESTIMATE   # 0.30 (from backtest)
                    * v14_cap_usd               # 40% of live Kalshi total bankroll
per_fire_budget_usd = min(per_fire_budget_usd,
                          V14_MAX_FIRE_FRACTION_OF_CAP * v14_cap_usd)  # 0.40 hard ceiling
contracts = floor(per_fire_budget_usd / target_price)
contracts = min(contracts, floor(cash / price), floor(v14_headroom / price))
contracts = max(1, contracts)   # floor of 1 if any room exists
```

`v14_cap_usd` is recomputed every loop from the LIVE Kalshi
`/portfolio/balance` (cash + portfolio_value) times
`V14_BANKROLL_FRACTION`, so deposits/withdrawals auto-scale the bet
size with no rebaseline command.

### Sizing table (half Kelly)

| Total bankroll | v14 cap (40%) | per-fire budget | ~contracts @ $0.47 |
|---|---|---|---|
| $33 | $13.20 | $1.98 | 4 |
| $51 | $20.40 | $3.06 | 6 |
| $75 | $30.00 | $4.50 | 9 |
| $100 | $40.00 | $6.00 | 12 |
| $200 | $80.00 | $12.00 | 25 |

### Risk envelope at $51 (half Kelly, ~$3/fire, ~6 contracts)

- Edge real (+$0.15/contract): ~+$0.90/fire; over a 30-fire trial ~+$27.
- Edge zero (day-block CI lower -$0.02/contract): ~-$0.12/fire; over 30
  fires ~-$4 (about 8% of v14's allocated cap; well within the 20%
  drawdown kill).

## Env knobs

| Var | Default | Effect |
|---|---|---|
| `V14_KELLY_FRACTION` | 0.50 | Fraction of full Kelly. 0.25 conservative, 1.0 full. |
| `V14_FULL_KELLY_ESTIMATE` | 0.30 | (constant in code) Kelly from backtest. |
| `V14_MAX_FIRE_FRACTION_OF_CAP` | 0.40 | Hard per-fire ceiling vs mis-estimated edge. |
| `V14_BANKROLL_FRACTION` | 0.40 | v14's share of total bankroll. |

The deprecated flat `V14_PER_TRADE_USD` no longer sizes orders; it is
retained only as a minimum-headroom floor gate.

## Anti em-dash audit

Verified after writing.
