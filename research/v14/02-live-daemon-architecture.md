# v14 Live Daemon Architecture (Design v1)

**Round:** 19 (v14 continued).
**Date:** 2026-05-27.
**Author:** orchestrator (pre-review).
**Status:** DRAFT pending review-agent feedback.

## Operator directive

> "use the kalshi api. you can have this always running too and have it directly write whenever there's a good opportunity. Maybe there's a way to put this together with the v1 bot. Perhaps it could also just be instead the v1 bot manages like 60% of the money in Kalshi and this manages 40% for now. What needs to change? Make the changes. Make the decisions. Use review agents on decisions"

## Goals

1. v14 strategy auto-places real Kalshi orders when its trigger fires (no manual operator step)
2. Always running (daemon, not on-demand)
3. Capital split: v1 ~ 60% ($19), v14 ~ 40% ($13) of the ~$32 total Kalshi balance
4. Both run concurrently without interference
5. v14 inherits the same safety culture as v1 (kill triggers, drawdown caps, etc.)

## Architecture decisions

### D1. Process layout: TWO SEPARATE DAEMONS

Decision: v14 runs as its own scheduled Windows task, separate from v1. Both processes alive in parallel.

Rationale:
- v1's main loop in `scripts/paper_trade_favorite.py` is a load-bearing 700+ line script with 6 kill triggers, drawdown monitor, single-instance lock, structured logging, and Discord alerts. Modifying it to add a v14 strategy doubles its complexity and risks regression.
- Two daemons reuse v1's modules (LiveOrderManager, KalshiClient, KillTriggerMonitor) as libraries via Python import; no source modifications to v1's production scripts.
- Operator can kill either daemon independently (separate STOP files).

Rejected alternative: embed v14 logic in v1's main loop. Too risky for v1.

### D2. State: separate state files, separate kill_state, separate single-instance lock

Decision:
- v1's state stays at `data/live_trades/state.json` and `data/live_trades/kill_state.json` (UNCHANGED)
- v14's state at `data/v14/v14_state.json` and `data/v14/v14_kill_state.json` (NEW)
- v1's single-instance lock at `data/live_trades/bot.pid` (UNCHANGED)
- v14's single-instance lock at `data/v14/v14_bot.pid` (NEW)

Rationale: zero shared mutable state means zero contention. Reuses v1's LiveOrderManager class via the `state_path=` constructor argument (already supported).

### D3. Capital allocation: hard caps via starting_bankroll

Decision:
- v1's starting bankroll capped at $19.00 (edit `scripts/run_live_bot.ps1` to pass `--starting-bankroll 19.00`)
- v14 daemon initializes its own `LiveOrderManager` and `KillTriggerMonitor` with `starting_bankroll_usd=12.80`
- Both bots compute max_concurrent_positions from their own bankroll independently

Rationale:
- The operator's Kalshi balance is ~$32 (per `state.json` `starting_bankroll_usd: 31.30`)
- $19 + $13 = $32 (1c rounding error). Exact split: v1 $19.20 (60%) / v14 $12.80 (40%)
- v1 already accepts numeric `--starting-bankroll` (Round 6 used `--starting-bankroll 32`)
- v14 sets its own cap on initialization

Edge case: if v1 fills orders that drop its balance below $19, the actual deployed capital in v1 falls; v14 unaffected. Vice versa.

### D4. Order conflict avoidance

Decision: before placing an order, v14 reads `data/live_trades/state.json` (read-only) to check whether v1 has an OPEN intent, resting, or filled order on the same ticker. If yes, v14 SKIPS the trade and logs.

Rationale: avoids double-exposure on a single market. v1 takes priority because it has a longer-validated edge and was already running.

Implementation: a small helper `_ticker_in_v1_state(ticker)` that reads v1 state.json and checks intents/resting/filled dicts. Read-only.

### D5. Side handling

Decision: v14 always places **YES BUY** orders. If the sportsbook moves AWAY from the home team (delta_sportsbook_home < 0), v14 takes the AWAY side by placing YES BUY on the away-team market (using the Kalshi ticker for the away side).

Rationale:
- v1's LiveOrderManager hardcodes `side: yes` in the order payload
- Kalshi event has two markets (home YES + away YES); v14 buys whichever side matches our directional bet
- No need to extend LiveOrderManager to support NO-side buys

### D6. Trigger evaluation cadence

Decision: v14 daemon loop runs every 5 minutes during MLB-night hours (UTC 21:00 to UTC 09:00 = 5 PM to 5 AM ET).

Rationale:
- The-odds-api credit cost: 2 calls per loop (current + 3h-ago snapshot). 24 loops per 12h window = ~480 credits/day = ~$0 marginal at the existing pool
- 5-min loop is responsive enough to catch fires within the T-3h to T-1h execution window
- During off-hours (no MLB games), the daemon sleeps

### D7. Order placement details

Decision:
- Target price = `max(min(suggested_max_price + 0.005 safety, 0.99), 0.01)`
- Suggested max = current home implied prob + 0.005 safety buffer + 0.0007 expected haircut
- Contracts = 1 initially. Scale to 2-3 contracts per fire after operator verification (configurable via env var `V14_CONTRACTS_PER_FIRE`)
- time_in_force = `good_til_cancel` (matches v1)

### D8. Kill triggers (v14-specific)

Decision: v14 uses a slimmer KillTriggerMonitor configuration than v1 (v14 has no acceptance criteria to track since it bypasses v1's gate logic). v14 monitors:
- Drawdown: stop at 20% of v14 starting bankroll ($2.56)
- Consecutive losses: stop at 5 consecutive losing fires
- Time: pause for operator review at 8 weeks of v14 deployment regardless of P&L
- Daily orders cap: max 10 orders per UTC day (defense against API runaway)
- Per-trade size: max $0.95 (matches v1)

Reuses `KillTriggerMonitor` class with custom `KillTriggerConfig`.

### D9. Discord alerts

Decision: reuse v1's webhook URL from `.env`. v14 fires Discord alerts on:
- Daemon start / stop
- Each order placement (info)
- Each fill (info)
- Each settlement with P&L (info)
- Kill trigger trip (error, @ mention if configured)

### D10. Failure modes

Decision:
- the-odds-api 401/422 -> daemon logs and continues (transient; retry next loop)
- the-odds-api 429 (rate limit) -> exponential backoff
- Kalshi API errors -> log and continue (LiveOrderManager already handles intent_id idempotency)
- v14 state.json corruption on load -> daemon exits with non-zero status; supervisor restarts; if persistent, operator intervention required

### D11. Operator controls

Decision: lightweight file-based controls
- `data/v14/STOP` -> daemon exits gracefully on next loop iteration (cancels resting orders first)
- `data/v14/PAUSE` -> daemon continues looping but skips placing new orders
- `data/v14/REQUIRE_APPROVAL` -> daemon logs intended orders but does NOT place; operator inspects log and removes file when ready

### D12. Tests

Required (minimum):
- tests/v14/test_strategy.py: trigger fires for >= 60bp delta; no fire below; YES/NO side mapping correct
- tests/v14/test_capital_cap.py: v14 refuses to place if would exceed $12.80 exposure
- tests/v14/test_v1_collision.py: v14 skips ticker already in v1 state
- tests/v14/test_kill_triggers.py: 5 consecutive losses pauses
- tests/v14/test_daemon_loop.py: one-iteration smoke test with mocked API

## File layout

NEW:
```
src/kalshi_bot_v14/
  __init__.py                  (already exists)
  strategy.py                  trigger logic + side mapping
  sportsbook.py                the-odds-api client wrapper
  ticker_match.py              the-odds-api game -> Kalshi ticker
  state_check.py               read v1 state.json for collision detection
  daemon_loop.py               the main loop function

scripts/v14/
  v14_daemon.py                CLI entry point; instantiates loop
  run_v14_bot.ps1              supervisor (mirrors run_live_bot.ps1)

tests/v14/
  test_strategy.py
  test_capital_cap.py
  test_v1_collision.py
  test_kill_triggers.py
  test_daemon_loop.py

data/v14/                      (already exists)
  v14_state.json               LiveOrderManager state
  v14_kill_state.json          KillTriggerMonitor state
  v14_bot.pid                  single-instance lock
  logs/                        rotated daily
```

MODIFIED:
```
scripts/run_live_bot.ps1       add --starting-bankroll 19.00
```

UNCHANGED:
```
scripts/paper_trade_favorite.py  (v1 main loop; no changes)
src/kalshi_bot/strategy/*        (v1 strategy modules; no changes)
src/kalshi_bot/data/*            (KalshiClient reused as library)
src/kalshi_bot/risk/*            (KillTriggerMonitor reused as library)
```

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| v14 places duplicate orders on v1's markets | D4 collision check before each order |
| Cumulative drawdown across BOTH bots exceeds $32 ceiling | Hard caps at $19 + $12.80 = $31.80; 20c safety margin |
| v14 places orders during a v1 kill-trigger event | v14's KillTriggerMonitor is independent; v1 trip does NOT auto-trip v14, but operator should manually STOP v14 if v1 trips on a structural issue |
| the-odds-api credit exhaustion mid-trial | Daemon prints credit count each loop; alerts when below 2,000 remaining |
| Kalshi spread widens beyond 1c | Order limit price clamps to suggested max; orders unfilled rather than overpaying |
| Daemon crash mid-loop | Supervisor in run_v14_bot.ps1 restarts; LiveOrderManager intent_id idempotency prevents duplicate fills |
| v14 trigger fires on a market v1 is about to enter | Order arrival race; first wins, second skipped (Kalshi side); v14's collision check is best-effort, race possible |

## Open questions

1. **Should v14 alert before placing OR place silently?** Tentatively: place silently, log to Discord post-hoc. Operator can flip to REQUIRE_APPROVAL mode if they want pre-trade review during initial trial.
2. **What if v14's daemon is running but the operator wants to deploy a third strategy later?** Not a v14 concern; v15 if pursued.
3. **Should v14 use paper-mode first?** Operator already authorized live. v14 has well-defined kill triggers ($2.56 max drawdown). Live is safe enough at this size.

## Deployment sequence

1. Review agent feedback on this doc -> apply fixes
2. Implement (v14 modules + scripts + tests)
3. Test suite passes
4. Update run_live_bot.ps1 with $19 cap
5. Restart v1 with new bankroll cap (existing restart_bot.ps1)
6. Initialize v14 state with $12.80
7. Run v14 once manually (in REQUIRE_APPROVAL mode) to verify trigger logic on live data
8. Operator inspects intended orders; removes REQUIRE_APPROVAL
9. Schedule v14 via Windows Task Scheduler (`KalshiV14Bot`)
10. Discord alerts confirm v14 operational

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
