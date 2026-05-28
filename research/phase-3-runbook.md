# Phase 3 Paper-Trading Runbook

**Status:** Pre-draft, written during the autonomous run. Activates only
if a Phase 2 strategy gate PASSES and the operator authorizes paper
trading.

This runbook covers the 2-week paper-trading window that
[sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 10 (and the equivalent Politics x H methodology) requires before
any live capital deployment.

## Pre-flight checklist

Before starting paper trading, confirm ALL:

- [ ] Phase 2 gate PASSED for the active strategy (Politics x H OR
  Sports x Long-Horizon).
- [ ] Operator has reviewed the gate results and verbally authorized
  paper trading.
- [ ] Phase 3 design ([phase-3-design.md](phase-3-design.md)) has been
  reviewed.
- [ ] Critic pass on the live-strategy design (spawn a critic similar to
  Phase 2 critics; document findings).
- [ ] `uv run pytest -q` shows all tests passing (>= 214 at handoff
  time).
- [ ] `uv run ruff check src/ scripts/ tests/` is clean.
- [ ] Discord webhook smoke test:
  `uv run python -m scripts.test_discord` returns OK.
- [ ] Kalshi API smoke test:
  `uv run python -m scripts.archive.ec1_kxhigh.check_kalshi` returns OK.
- [ ] State file directory exists: `mkdir -p data/paper_trades`.

## Starting paper trading

For Sports x Long-Horizon (if that's the validated strategy):

```bash
uv run python -m scripts.paper_trade \
    --category Sports \
    --calibrator data/processed/sports_dataset.parquet \
    --min-lifetime-days 30 \
    --cadence 900 \
    --max-concurrent 5 \
    --contracts-per-fill 3 \
    --min-net-edge 0.01 \
    --starting-bankroll 25.0
```

For Politics x H (if politics methodology is revised + revalidated):

```bash
uv run python -m scripts.paper_trade \
    --category Politics \
    --calibrator data/processed/politics_phase2_dataset.parquet \
    --min-lifetime-days 30 \
    --cadence 900
```

The script loops indefinitely. Use Ctrl-C to stop. State persists in
`data/paper_trades/state.json` across restarts.

## What to monitor

### Discord alerts (set up via `.env` DISCORD_WEBHOOK_URL)

Expected alerts:
- `PAPER TRADE STARTED` once at session start
- `PAPER PLACED N order(s)` after each loop placing orders
- `PAPER FILL <ticker> <side> <contracts>@<price>` per simulated fill
- `HALT` / `PAUSE` if drawdown breaches thresholds

Frequency: every 15 min (cadence) the bot may produce 0-1 placement
alerts. Fills are rarer (a fill alert is meaningful).

### Daily checkpoint

Each day during the 14-day window:

```bash
# Bankroll + open / filled / closed counts
uv run python -c "
from kalshi_bot.strategy.order_manager import PaperOrderManager
mgr = PaperOrderManager()
print(f'bankroll: \${mgr.current_paper_bankroll():.2f}')
print(f'open: {len(mgr.state.open_orders)}')
print(f'filled (unsettled): {len(mgr.state.filled_orders)}')
print(f'closed (settled): {len(mgr.state.closed_orders)}')
print(f'realized P&L total: \${mgr.state.realized_pnl_total_usd:.2f}')
"
```

### Weekly review

After 7 days:
1. Count total simulated fills.
2. Compare realized per-fill mean P&L to backtest expected (within
   +/- 2 SE).
3. Check fill rate: filled / placed. Target >= 30% per
   plan-critic finding 9 in the Phase 2 critic.
4. Review any drawdown alerts.
5. Spot-check 5 random closed orders for sanity (did P&L compute
   correctly given outcome).

## Acceptance criteria for go-live

After 14 days OR >= 200 fills (whichever comes first):

1. **Fill rate >= 30%** of placed orders.
2. **Realized net edge** matches backtest expected (sports gate
   bootstrap mean) within +/- 2 SE.
3. **No drawdown events** exceeded 15% (PAUSE threshold).
4. **No methodology-violating events**: no Kalshi fee schedule changes,
   no regulatory disruptions, no infrastructure failures.
5. **Operator review** of accumulated paper trades and explicit go-live
   approval.

If ANY criterion fails:
- Discuss with operator before next step.
- May require methodology revision or strategy abandonment.

## Important caveats

### Thread / process safety

**Run ONLY ONE `paper_trade.py` process at a time.** PaperOrderManager
is not thread-safe; concurrent writers to `data/paper_trades/state.json`
can corrupt state. If you need to inspect state while the bot runs,
use a read-only snapshot copy.

### Round-trip fee model is conservative

The order manager subtracts ROUND-TRIP (2x) maker fees at settlement
per the methodology lock. Kalshi settlement is actually fee-free, so
a real buy-to-hold-to-settle bot only pays the ENTRY fee. Paper P&L
shown by this system will **systematically UNDERSHOOT** a real bot's
P&L by one maker fee per contract (~$0.01 at P=0.30, scaling with
P*(1-P)).

This is intentional: matches the methodology's conservative gating
assumption. The gate result you would have validated against requires
ROUND-TRIP fees to pass; the live bot should outperform paper by the
single-fee delta.

If you want to track "realistic" live P&L (single-fee) for comparison,
add a separate accounting in a Phase 3.1 enhancement.

### Drawdown framing

The drawdown monitor uses HIGH-WATER-MARK-based thresholds (5/10/15/25
percent). The Phase 3 design doc mentions DAILY / WEEKLY / TOTAL
framing as an alternative. The HWM approach is simpler and was chosen
for the autonomous-run scaffolding. If you prefer the
daily/weekly/total framing for live deployment, refactor
`src/kalshi_bot/risk/drawdown.py` to track rolling windows in addition
to HWM.

## Operating cadence

Recommended:
- **Continuous run** on a reliable host (avoid WSL2 sleep/resume per
  Phase 1 notes). Options:
  - DigitalOcean / Linode $5-6/mo droplet
  - AWS Lightsail $5/mo
  - Raspberry Pi at home with ethernet
- **15-minute polling cadence** (matches paper_trade.py default).
  Politics / long-horizon sports don't need second-by-second polling.
- **Daily morning check-in** to review Discord alerts and run the daily
  summary script.

## Abort triggers

Stop paper trading IMMEDIATELY and notify operator if:

1. **Drawdown breaches HALT threshold (25%)** - script halts itself.
2. **Kalshi announces a fee schedule change** - re-evaluation needed.
3. **Persistent fill rate < 20% over 50+ placed orders** - thesis
   may be wrong about retail tradability.
4. **Backtest-paper P&L divergence > 3 SE** - model is invalid for
   live regime.
5. **Bug discovered in the bot code** - fix before continuing.

## Going live (post-paper-trading)

The paper trading runbook is the bridge to live trading. Going live:

1. Acquire Kalshi WRITE-scope API key (request lead time: days).
2. Implement live order placement in `scripts/paper_trade.py` (currently
   a `NotImplementedError` placeholder for live mode).
3. Add another critic pass on the live-mode code.
4. Add more unit tests for live order endpoint shape.
5. Deploy with $25 initial cap. Monitor closely for first 50 fills.
6. Scale to $100 ceiling only after demonstrated alignment with paper
   results.

## Files relevant to Phase 3

- Code:
  - `src/kalshi_bot/strategy/market_scanner.py`
  - `src/kalshi_bot/strategy/pricing.py`
  - `src/kalshi_bot/strategy/order_manager.py`
  - `src/kalshi_bot/risk/drawdown.py`
  - `scripts/paper_trade.py`
- State:
  - `data/paper_trades/state.json` (auto-created on first run)
- Tests:
  - `tests/test_pricing.py`
  - `tests/test_drawdown.py`
  - `tests/test_order_manager.py`
  - `tests/test_market_scanner.py`
- Docs:
  - This runbook
  - [phase-3-design.md](phase-3-design.md)

## What this runbook does NOT cover

- Live trading mode implementation (TODO; see Phase 3 design).
- Tax reporting (operator deferred per CLAUDE.md until $5k bankroll).
- Order cancellation policy on regime change.
- Multi-instrument hedging.
- Cross-platform arbitrage with Polymarket.
