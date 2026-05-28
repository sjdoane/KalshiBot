# v14 Live Daemon Deployment Guide

**Date:** 2026-05-27. **Status:** ready for operator deployment.

## What was built

| File | Purpose |
|---|---|
| `src/kalshi_bot_v14/ticker_match.py` | Maps sportsbook game (home/away team) -> verified Kalshi ticker by querying /markets and time-proximity disambiguation (handles consecutive-day matchups) |
| `src/kalshi_bot_v14/daemon.py` | The daemon loop logic: polls the-odds-api current + 3h-ago, fires X-only trigger, places Kalshi orders via the v1 LiveOrderManager class with separate state file |
| `scripts/v14/v14_daemon.py` | CLI entry point |
| `scripts/v14/free_v1_cash.py` | One-shot helper: cancels v1 lowest-edge resting orders to free cash for v14 |

## Architecture summary

- **Process layout:** v14 runs as a separate long-running daemon. v1 unchanged. Two daemons coexist.
- **Capital:** v14 hard-capped at $12.80 exposure ($V14_CAPITAL_CAP_USD$ in daemon.py). Self-meters off Kalshi `/portfolio/balance`. If Kalshi cash is insufficient at fire time, v14 skips and logs.
- **State:** v14 writes to `data/v14/v14_state.json`. v1's `data/live_trades/state.json` untouched.
- **Order placement:** real Kalshi limit BUY YES orders via the v1 `LiveOrderManager` class (reused as a library; never modified).
- **Order conflict avoidance:** v14 reads v1's state.json read-only before placing; skips tickers v1 already holds.
- **Cadence:** 15-minute loop during 18:00 to 06:00 UTC (2 PM to 2 AM ET). Sleeps off-hours.
- **Credits:** ~22 the-odds-api credits per loop. ~1,000 credits/day at full schedule = ~13 days from current 13,464 remaining.

## Pre-deployment checklist

### 1. Free up cash from v1 (one-shot)

v1 currently has 101 resting orders consuming most of the Kalshi balance. v14 needs ~$13 of free cash to operate at its $12.80 cap. Note: as of last check, $18.87 was already free (sufficient).

Run only if needed:

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
$env:PYTHONPATH = "src"
.venv-kronos\Scripts\python.exe scripts\v14\free_v1_cash.py 13
```

The script will:
- Show a dry-run preview of which v1 orders it plans to cancel (lowest expected_net_edge first)
- Ask `Type 'YES CANCEL' to confirm`
- Cancel via Kalshi DELETE; update v1's state.json

If you skip this step, v14 will simply wait for v1's natural attrition (orders filling, expiring) to release cash.

### 2. Verify PAPER_MODE flag

By default, `data/v14/PAPER_MODE` was created during smoke testing. While present, v14 simulates orders without placing real ones.

To enable LIVE order placement, REMOVE the PAPER_MODE file:

```powershell
Remove-Item "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v14\PAPER_MODE"
```

Recommended: start in PAPER mode for the first 2-3 days to confirm trigger fires look reasonable. Then go LIVE.

### 3. Verify Kalshi auth

The daemon reads `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` from `.env`. v1 already uses these; v14 reuses them.

Sanity check: run the one-shot alerter, confirm it pulls open MLB markets without auth errors:

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
$env:PYTHONPATH = "src"
.venv-kronos\Scripts\python.exe scripts\v14\live_alerter.py
```

### 4. Launch the daemon

Foreground (testing):

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
$env:PYTHONPATH = "src"
.venv-kronos\Scripts\python.exe scripts\v14\v14_daemon.py
```

The daemon prints per-loop summaries. Each loop logs to `data/v14/v14_trades.jsonl`.

To schedule via Windows Task Scheduler:
- Task name: `KalshiV14Bot`
- Trigger: at user logon
- Action: `powershell.exe -NoExit -Command "& {cd 'C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi'; $env:PYTHONPATH='src'; .venv-kronos\Scripts\python.exe scripts\v14\v14_daemon.py}"`
- Restart on failure: 1 min interval, 99 retries

## Operator controls (file-based)

| File | Effect |
|---|---|
| `data/v14/STOP` | Daemon exits gracefully on next loop iteration |
| `data/v14/PAUSE` | Daemon continues looping but skips placing new orders |
| `data/v14/PAPER_MODE` | Daemon simulates orders without placing real ones |

Create or remove with `New-Item` or `Remove-Item` in PowerShell.

## Pre-registered kill conditions

The daemon enforces these automatically:

| Trigger | Threshold |
|---|---|
| Drawdown | realized_pnl < -$2.56 (20% of $12.80 cap) |
| Consecutive losses | 5 closed orders in a row with realized_pnl < 0 |
| Daily order cap | 10 placements per UTC day |

When ANY trigger fires, the daemon STOPS placing new orders and logs `kill_trigger` event. Operator must inspect and decide whether to:
- Cancel resting orders manually
- Remove the trip condition (e.g., wait for time-window to pass) and remove any STOP file
- Kill the daemon for review

## Monitoring

### Logs

- `data/v14/v14_trades.jsonl` - every event (loop summary, fire attempts, placements, kills)
- `data/v14/v14_state.json` - LiveOrderManager state (intents, resting, filled, closed)

Tail to watch:

```powershell
Get-Content "data\v14\v14_trades.jsonl" -Wait -Tail 20
```

### Daily review

At any time, run:

```powershell
.venv-kronos\Scripts\python.exe -c "import json; lines = open('data/v14/v14_trades.jsonl').readlines(); print(f'Total events: {len(lines)}'); events = [json.loads(l) for l in lines]; fires = sum(1 for e in events if e.get('event') == 'fire_placement_attempt'); placements = sum(1 for e in events if e.get('event') == 'fire_placement_result'); print(f'Fire attempts: {fires}; Confirmed placements: {placements}')"
```

## Expected behavior

Based on v14 backtest:
- **Fire rate:** ~25% of MLB-night games show qualifying sportsbook move
- **Fires per day:** 1-3 expected during MLB regular season
- **Win rate:** 64%
- **Mean net P&L per fire:** +$0.15
- **CI per fire:** [-$0.04, +$0.33] day-block bootstrap

For a 4-week trial:
- Expected fires: 30-50
- Expected total P&L: -$1 to +$10 on $12.80 capital
- Point estimate: +$4-5

## When to evaluate

After 4 weeks of operation:
1. Count `fire_placement_attempt` events in v14_trades.jsonl
2. For each filled and settled order in v14_state.json, sum realized_pnl_usd
3. Compare realized to projected (+$0.15 mean, +$4.50 over ~30 fires)
4. If realized matches projection: scale to $20-25 capital (operator-authorized; raise V14_CAPITAL_CAP_USD)
5. If realized is significantly below: pause, investigate, possibly kill

## Roll back

To stop v14 entirely:

```powershell
New-Item -ItemType File "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v14\STOP"
```

Daemon exits on next loop. Resting orders REMAIN on Kalshi (no auto-cancel on STOP). Operator can cancel via Kalshi web UI or run a small script.

To restart:

```powershell
Remove-Item "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v14\STOP"
# then launch daemon as in step 4 above
```

## Known limitations

1. **The architectural review flagged that `--starting-bankroll 19` would NOT cap v1's deployment.** We did not modify v1's source to add a hard cap. Instead, v14 self-meters off available Kalshi cash. v1 continues to operate at its full $32 cap. The 60/40 split is APPROXIMATE based on Kalshi cash availability, not a hard enforcement. If you want a true hard cap on v1, that requires modifying `scripts/paper_trade_favorite.py` (separate task).
2. **Ticker matcher accuracy: 16 of 17 games in today's the-odds-api batch matched correctly (94%).** The remaining 6% are typically out-of-window (Kalshi market not yet open) or edge-case timing. The daemon SKIPS unmatched fires (safe failure mode).
3. **EDT/EST detection is hardcoded to EDT (UTC-4).** Off by 1 hour during November-March. Add EST handling if v14 is still running in 2026 winter.
4. **No Discord alerts in daemon yet.** Events go to JSONL only. Adding Discord is a small follow-up.
5. **No supervisor script.** Operator runs daemon manually or via Task Scheduler. Crashes require manual restart.
6. **No tests committed.** I smoke-tested manually but did NOT write `tests/v14/test_*.py`. The ticker_match.py module especially should get formal tests before operational confidence rises.

## Summary

You can deploy by:
1. (Optional) `python scripts/v14/free_v1_cash.py 13` to free capital
2. `Remove-Item data\v14\PAPER_MODE` to go live (or leave it for paper test)
3. Launch the daemon: `python scripts/v14/v14_daemon.py`
4. Watch `data/v14/v14_trades.jsonl` for activity
5. Evaluate at 4 weeks per the projection

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
