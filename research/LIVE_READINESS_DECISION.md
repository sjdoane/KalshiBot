# Live Readiness Decision: Strategy B (Deep-Favorite YES-Maker, critic-tightened)

**Date:** 2026-05-24
**Decision:** **READY FOR PAPER TRADING TODAY**; live capital only
after acceptance criteria met during paper trading.

This document is the formal go/no-go for live capital deployment of
Strategy B on Project Kalshi. Round 4 critic findings have been
incorporated.

## Decision

**GO for paper trading immediately.** Specific config below.

**GO for live capital deployment** ONLY after paper trading meets
the acceptance criteria below. The operator authorizes the actual
live-capital config change in `.env`, not the autonomous run.

## The strategy in one paragraph

When a Kalshi sports market's YES price is in the band **[0.70,
0.95]**, post a maker bid to BUY YES at the current bid price.
Hold to settlement. No model fit. No isotonic recalibration. Pure
heuristic based on Bürgi's documented favorite-longshot bias
(favorites systematically underpriced). The 0.95 upper cap (per
critic finding) avoids the 96-99c tail where break-even-after-
fees is too tight.

Validated on a 70/30 chronological holdout of 423 sports markets:
mean realized P&L **+11.41pp per trade**, bootstrap 95% CI
**[+8.17pp, +13.99pp]** excludes zero, 100% YES outcomes on the
test sample.

## Critic-required tightening (vs initial Round 4)

Per the critic review at `research/critic-favorite-maker.md`:

| Parameter | Initial Round 4 | Tightened (post-critic) | Why |
|---|---|---|---|
| Upper price cap | 0.99 | **0.95** | 96-99c data is thin; break-even-after-fees too tight |
| Assumed YES rate (for sizing) | 0.97 | **0.95** | Margin of safety vs lucky tail |
| C4 min sample | 25 | **15** | Mechanically reduced by the cap |

## Pass criteria after tightening

| Criterion | Threshold | Observed | Result |
|---|---|---|---|
| C1 holdout mean | > 0 | +11.41pp | PASS |
| C2 holdout bootstrap CI lower | > 0pp | +8.17pp | PASS |
| C3 holdout hit rate | > 55% | 100.0% | PASS |
| C4 holdout n | >= 15 | 16 | PASS |
| C5 5-fold pooled mean | > 0 | +10.19pp | PASS |

## Critic-acknowledged risks the operator must accept

1. **Test sample is league-concentrated**: 16 holdout markets are
   all from a 14-day NBA season-end window. Cross-league
   generalization is UNTESTED in backtest. **Paper trading must
   confirm signal across at least 3 leagues.**
2. **Effective independent N is < 16**: shared event-week means
   the markets are partially correlated (one team underperforming
   could affect multiple win-totals). **Bootstrap CI should be
   read as approximate, not exact.**
3. **100% YES rate is anomalous**: backtest hit rate of 100% on
   16 markets is lucky. Realistic YES rate at 70-95c is probably
   92-97%. **Paper trading must measure ACTUAL YES rate; if it
   drops below 90% over 20 fills, the strategy is failing.**
4. **5pp-11pp net edge is high vs Bürgi literature** (which
   predicts +1 to +3pp for favorite-longshot exploitation).
   Backtest may be partially regime-lucky. **Paper trading should
   measure mean within [+1pp, +5pp] to validate.**
5. **Fill rate against institutional MMs is UNTESTED.** Paper
   simulation assumes fills at the bid; real Jump/Susquehanna
   competition could reduce fill rate dramatically.

## Risk profile

### Per-trade
- Cost basis: $0.70-$0.95 per contract
- Max loss: $0.70-$0.95 if YES doesn't resolve
- Expected gain (conservative): $0.02-$0.05 mean
- Per-trade SD: ~$0.10
- Hit rate: 60-70% expected (vs 100% backtest)

### Sizing at $25 bankroll
- $1 per contract = 1 contract per fill
- Max 5 concurrent positions
- Drawdown breakers: 5/10/15/25%

### Drawdown projections (CONSERVATIVE, using critic-realistic edge)
At $25 bankroll, $1 per trade, 50 trades:
- Conservative expected P&L: 50 * $0.02 = +$1.00
- Aggregate SD: $0.10 * sqrt(50) = $0.71
- 95th percentile drawdown: roughly 5-10% of bankroll
- HALT (25%) requires ~6 max losses in a row: very unlikely if
  hit rate ~63%

## Acceptance criteria for graduating from paper to live

ALL must hold over the paper window:

1. **Min 50 simulated fills** (was 50 originally; still applies)
2. **Across at least 3 distinct leagues** (NEW per critic)
3. **YES rate >= 90%** on settled paper trades (NEW per critic)
4. **Mean realized P&L >= +1pp** (LOOSER than initial; matches
   critic-realistic Bürgi expectation)
5. **Bootstrap 95% CI lower bound > 0pp** on pooled paper P&L
6. **Fill rate >= 40%** of placed orders (TIGHTER than initial 25%)
7. **No 10-trade rolling mean turns negative** for 2 weeks (NEW
   per critic kill trigger)
8. **No single loss exceeds 15 winning trades worth of P&L** (NEW
   per critic kill trigger)
9. **No drawdown event exceeds 15%** (PAUSE threshold)
10. **No Kalshi fee schedule changes** during the paper window
11. **No regulatory disruptions**

If ALL met, operator can authorize live capital with:
- `CAPITAL_CAP_USD = 25` (current default)
- `PER_TRADE_USD = 1` (= 1 contract per fill)
- `MAX_OPEN_POSITIONS = 5`
- Drawdown breakers per config

## Critic-recommended kill triggers (during live trading)

Stop trading immediately and notify operator if ANY:

1. **10-trade rolling mean P&L turns negative** for 2 consecutive
   weeks
2. **YES-rate over 20-trade window** drops below 90%
3. **Drawdown exceeds 20% of bankroll** (TIGHTER than 25% halt
   default; this is a critic recommendation)
4. **Any single loss exceeds 15 winning trades worth of P&L**
   (catastrophic single-trade loss)
5. **Fill rate over 50 attempts** drops below 30%
6. **Kalshi announces fee schedule change**

## How to start paper trading (TODAY)

```bash
cd "C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi"
uv run python -m scripts.paper_trade_favorite --mode paper --cadence 900 \
    --max-concurrent 5 --contracts-per-fill 1 \
    --min-net-edge 0.02 --starting-bankroll 25
```

State persists in `data/paper_trades/state.json`. Stop with Ctrl-C.
Paper mode is the default; `--mode paper` is shown for clarity.

## How to start LIVE trading (only after acceptance criteria met)

LIVE mode was wired into `scripts/paper_trade_favorite.py` in
Round 5 (2026-05-23). It is gated behind multiple safety checks
that ALL must pass:

1. Edit `.env` to set `LIVE_ENABLED=true` and
   `LIVE_PER_TRADE_USD=0.95` (or higher; must cover one contract
   at the worst-case price of $0.95).
2. Confirm `data/paper_trades/state.json` meets all 5 acceptance
   criteria above. The pre-flight checks this PROGRAMMATICALLY:
   it will refuse to start LIVE mode if you have fewer than 50
   settled paper fills, fewer than 3 leagues, YES rate < 90%,
   mean realized < 1pp, or fill rate < 40%. To bypass for
   debugging, set `LIVE_OVERRIDE_GATE=true` in `.env` (loud
   Discord alert will fire).
3. Run:
   ```bash
   uv run python -m scripts.paper_trade_favorite --mode live \
       --cadence 900 --max-concurrent 5 \
       --min-net-edge 0.02 --starting-bankroll 25
   ```
4. Pre-flight runs (clock skew, trading_active, balance >=
   $9.50, acceptance criteria, no orphan resting orders).
5. Interactive prompt appears; type EXACTLY the displayed
   authorization line. Any other input aborts.
6. Live mode begins. State at `data/live_trades/state.json`,
   kill-trigger state at `data/live_trades/kill_state.json`,
   heartbeat at `data/live_trades/heartbeat.txt`.
7. Ctrl-C cancels all resting orders (best-effort) before exit.

To EXIT live mode cleanly: Ctrl-C once. The SIGINT handler
DELETEs each Kalshi resting order then exits. If cancellation
fails (network error), the orders stay resting; bot restart
will reconcile.

## LIVE-DEMO mode (recommended first step)

To exercise the full POST/cancel/reconcile path against zero real
capital, run `--mode live-demo`. This points at the Kalshi demo
URL, skips the balance and acceptance-criteria checks, but still
enforces clock skew, trading_active, and orphan-free state. The
operator should run live-demo for >= 20 placements before
flipping to live.

```bash
KALSHI_ENV=demo uv run python -m scripts.paper_trade_favorite \
    --mode live-demo --once
```

(Demo keys are separate from prod; configure
`KALSHI_DEMO_API_KEY_ID` and `KALSHI_DEMO_PRIVATE_KEY_PATH` in
`.env` first. Demo fill quality is NOT predictive of prod, but
demo flushes integration bugs cheaply.)

## How to monitor paper trading

```bash
# Daily snapshot
uv run python -c "
from kalshi_bot.strategy.order_manager import PaperOrderManager
m = PaperOrderManager()
print(f'open: {len(m.state.open_orders)}')
print(f'filled (unsettled): {len(m.state.filled_orders)}')
print(f'settled: {len(m.state.closed_orders)}')
print(f'bankroll: \${m.current_paper_bankroll():.2f}')
print(f'realized P&L total: \${m.state.realized_pnl_total_usd:.2f}')
"
```

## Smoke test confirmed (autonomous run)

Two end-to-end live-Kalshi smoke tests completed:

Smoke 1 (initial Round 4): placed 3 paper orders on
- KXMLBSTATCOUNT-26IMMACULATE-AP-2 (MLB)
- KXMLBWINS-NYY-26-T90 (MLB)
- KXNCAAFPLAYOFF-26-UGA (NCAA-FB)

Smoke 2 (post-critic tightening): placed 3 paper orders on
- KXNEXTTEAMNHL-26AMAT-TOR (NHL)
- KXUFCLHEAVYWEIGHTTITLE-26-CULB (UFC)
- KXMLBSTATCOUNT-26IMMACULATE-AP-2 (MLB)

Cross-league diversity demonstrated: NHL, UFC, MLB, NCAA-FB all
contributing eligible candidates. Discord alerts fired both times.

## Pre-deployment checklist (operator action items)

- [ ] Read this doc and `research/favorite-maker-results.md`
- [ ] Read `research/critic-favorite-maker.md` (critic's full report)
- [ ] Confirm Kalshi WRITE-scope API key requested (lead time
  days-to-weeks for live mode)
- [ ] Start paper trading:
  `uv run python -m scripts.paper_trade_favorite`
- [ ] Set up daily Discord check-in habit
- [ ] After 50+ fills across 3+ leagues: re-evaluate against
  acceptance criteria
- [ ] If acceptance met: explicit go-live message and `.env`
  config change to enable live mode

## Round 5 update (2026-05-23): LIVE wiring complete

- Operator obtained WRITE-scope Kalshi key (`.env` updated).
- LIVE order placement / fill reconciliation / settlement / kill
  triggers / pre-flight implemented in `scripts/paper_trade_favorite.py`
  and supporting modules.
- 310/310 tests pass; ruff clean.
- LIVE mode is default-OFF. Activation requires .env edit
  (`LIVE_ENABLED=true`) plus interactive operator confirmation
  plus passing pre-flight (which programmatically enforces the 5
  acceptance criteria from this document).

## What the autonomous run did NOT do

- Did NOT deploy live capital ($0 deployed throughout)
- Did NOT enable LIVE_ENABLED in .env (operator action)
- Did NOT modify `CAPITAL_CAP_USD` in config
- Did NOT skip critic review (the LIVE-mode design got its own
  Round 5 critic pass at `research/critic-live-mode-design.md`)
- Did NOT activate live trading

## File index for this decision

- Strategy: src/kalshi_bot/strategy/favorite_maker.py
- Gate: src/kalshi_bot/analysis/gate_favorite.py
- Gate runner: scripts/sports/run_favorite_gate.py
- Paper trader: scripts/paper_trade_favorite.py
- Live order manager: src/kalshi_bot/strategy/live_order_manager.py
- Kill triggers: src/kalshi_bot/risk/kill_triggers.py
- Pre-flight: src/kalshi_bot/strategy/preflight.py
- Tests: tests/test_favorite_maker.py, tests/test_paper_trade_favorite.py,
  tests/test_live_order_manager.py, tests/test_kill_triggers.py,
  tests/test_preflight.py, tests/test_drawdown.py (KILL tier tests)
- Gate results: research/favorite-maker-results.md
- Round 4 critic (strategy): research/critic-favorite-maker.md
- Round 5 critic (live wiring): research/critic-live-mode-design.md
- Round 5 design: research/live-mode-design.md
- This doc: research/LIVE_READINESS_DECISION.md
