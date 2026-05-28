# Phase 3 Live Strategy Design (Pre-Draft)

**Status:** Pre-draft, written BEFORE the Phase 2 gate verdict. Activates
only if the gate PASSES. If the gate FAILS, this document is preserved
as the template for a future strategy's live design.

**Authorization scope:** The operator's 2026-05-23 "full authority" +
"validate the model and sector" + "mostly set up to start setting up
live trading" message authorizes the BUILD of paper-trading
infrastructure. It does NOT authorize live capital deployment - that
remains gated on:
1. Phase 2 gate PASS
2. Operator wake-up approval of the live strategy design
3. 2 weeks paper trading on real Kalshi prod data, zero capital
4. Paper P&L matching backtest within +/- 2 SDs over 200+ fills
5. Operator explicit go-live approval
6. Deploy with $25 initial cap, $100 ceiling

## What the live strategy does

Mechanically: continuously scans open Kalshi politics markets, identifies
those matching the Phase 2 strategy filters, computes a recalibrated fair-
value probability using the isotonic-fit-on-train-data, and either
(PAPER MODE) records a simulated order or (LIVE MODE) posts a maker bid
via Kalshi `/portfolio/orders`. Hold to settlement. No intraday exit.

## Components

### 1. `src/kalshi_bot/strategy/discovery.py` (new)

Functions:
- `list_open_politics_markets(client)` -> DataFrame of currently-open
  binary politics markets with metadata (price, volume, time-to-close).
- `apply_phase2_filters(df)` -> subset matching mid-band, one-sided-flow,
  >= 30 days to resolution, binary, federal-election diversity.

Discovery cadence: every 15 minutes (configurable). Politics markets
don't move fast enough to need second-by-second polling.

### 2. `src/kalshi_bot/strategy/pricing.py` (new)

Functions:
- `recalibrate(market_price, isotonic_model)` -> truth estimate.
- `compute_maker_bid_price(market_orderbook, recalibrated, side)` ->
  the price at which to post the maker order. Inside the spread by 1-2
  ticks; capped at recalibrated minus fee buffer.
- `expected_net_edge(market_price, recalibrated)` -> per-contract net
  edge after round-trip maker fee and 1.5pp slippage. Used for filtering.

### 3. `src/kalshi_bot/strategy/order_manager.py` (new)

Functions:
- `OrderManager.scan_and_post()` -> main entry point. Scans markets,
  filters, prices, places orders (LIVE) or records intent (PAPER).
- `OrderManager.update_fills()` -> reconciles open orders with actual
  fills (LIVE) or simulated fills based on subsequent trade tape (PAPER).
- `OrderManager.compute_pnl()` -> realized P&L per fill since paper
  trading started.

State: open orders + filled positions stored in a SQLite DB or JSON file
(`data/paper_trades/state.json`). Persistent across restarts.

PAPER mode simulated-fill rule: if any taker trade in the market matches
or crosses our paper-bid price within the order's lifetime, mark as
filled at our bid price. This OVERESTIMATES fill rate vs reality
(institutional MMs would have stepped inside). Document this caveat.

### 4. `src/kalshi_bot/risk/drawdown.py` (new)

Functions:
- `DrawdownMonitor.update(bankroll_now)` -> check thresholds, fire alerts.
- Thresholds from config.py: DAILY_DD_HALT_PCT=0.10,
  WEEKLY_DD_HALT_PCT=0.15, TOTAL_DD_HALT_PCT=0.25.
- On threshold breach: halt new orders, alert Discord, log incident.

### 5. `src/kalshi_bot/strategy/runtime.py` (new)

Main loop entry point. Configurable cadence. Modes:
- `paper`: discovery + filter + price + record (no Kalshi orders endpoint).
- `live`: discovery + filter + price + post orders (uses Kalshi prod API).

CLI: `python -m scripts.paper_trade --mode paper --cadence 900`

### 6. `scripts/paper_trade.py` (new)

Entry point. Calls runtime.run() in either paper or live mode. Reads
config from .env. Writes Discord status alerts on:
- Start of session
- Each fill
- End of session
- Drawdown threshold breaches

## Pre-deployment checks

Before activating paper trading:
- [ ] Phase 2 gate PASS verdict
- [ ] Critic pass on this design (spawn after activation)
- [ ] Unit tests for all 5 new modules
- [ ] Smoke test: paper-trade for 30 minutes against demo Kalshi env
  (KALSHI_ENV=demo). Verify orders endpoint shape matches expectation.
- [ ] Smoke test: drawdown monitor fires Discord at 5% simulated drop
- [ ] Documented runbook: how to start, how to read alerts, how to
  abort

## Paper trading runbook (pre-draft)

To be finalized after gate. Outline:

1. **Start**: `uv run python -m scripts.paper_trade --mode paper`
2. **Monitor**: Discord channel for fill alerts + drawdown alerts.
3. **Daily checkpoint**: run `scripts/phase_3_summary.py` to get daily
   P&L summary; compare to backtest expected.
4. **Weekly checkpoint**: review accumulated paper trades vs expected
   net edge distribution.
5. **After 14 days**: gather final stats. If realized matches backtest
   within +/- 2 SDs over 200+ fills, present go-live readiness report.
6. **Abort triggers**:
   - 2-SD-or-worse deviation in realized vs expected
   - Fill rate < 30% (per critic finding 9)
   - Any Kalshi fee schedule announcement
   - Operator pause request

## What this design does NOT yet specify

- Exact LIMIT order params for Kalshi `/portfolio/orders` endpoint
  (need to read API docs at activation time).
- WebSocket subscription strategy (vs polling via REST).
- Order cancellation policy on regime change.
- Position sizing function beyond flat $1.
- Cross-instrument hedging (out of scope for Phase 3).
- Tax reporting hooks (operator deferred per CLAUDE.md; CPA consult
  required before $5k bankroll).

## Estimated implementation effort

If gate passes:
- Modules 1-5: 4-6 hours coding + tests
- Smoke tests: 1 hour
- Code review milestone 3: 30 min
- Runbook finalization: 30 min

Roughly half a day. The autonomous run budget can accommodate this if
the gate passes within the first 2 hours.

## Reusability across strategies

This scaffolding is mostly category-agnostic. If the runner-up Sports x
Long-Horizon strategy is ever activated, the discovery + pricing +
order_manager modules can be re-parameterized rather than rewritten.
The strategy-specific knowledge (mid-band, one-sided-flow, horizon
filter) lives in `apply_phase2_filters` which can be swapped.
