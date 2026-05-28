# Operator Runbook: Strategy B LIVE Trading

The bot is running on real Kalshi with real capital. This is the
daily-operations cheat sheet.

## Current configuration

| Setting | Value | Source |
|---|---|---|
| Strategy | Deep-favorite YES-maker, buy YES in [0.70, 0.95] | `src/kalshi_bot/strategy/favorite_maker.py` |
| Bankroll (starting) | **auto** (reads `/portfolio/balance` + open positions at startup; persists to `state.json`). After deposits/withdrawals run `restart_bot.ps1` with `--Rebaseline` flag passed through. | CLI `--starting-bankroll auto` |
| Per-trade budget | $0.95 (one contract at the worst price) | `.env LIVE_PER_TRADE_USD` |
| Max concurrent positions | **auto** (self-sizing from current bankroll; floor(total_bankroll / 0.95) per loop). At $32 bankroll computes to ~33. As bankroll grows from wins the cap rises; as losses shrink it the cap falls. | CLI `--max-concurrent auto` |
| Loop cadence | 900s (15 min) | CLI `--cadence 900` |
| Min net edge to place | $0.01 per contract | CLI `--min-net-edge 0.01` |
| Min market lifetime | 30 days (gate methodology) | CLI `--min-lifetime-days 30` |
| Max market lifetime | 180 days (research/time-scale-analysis.md) | CLI `--max-lifetime-days 180` |
| Override on acceptance gate | true (50-fill paper evidence bypassed) | `.env LIVE_OVERRIDE_GATE` |

Worst-case simultaneous exposure (all at $0.95): 33 × $0.95 = $31.35 (~98% of bankroll).
Typical-case (all at $0.85, current eligible-band average): 33 × $0.85 = $28.05 (~88%).
Realistic bad-week loss (20% of 33 contracts resolve NO at $0.85): $5.61 (~18% of bankroll).
Worst-case bad-day loss (50% of 33 contracts resolve NO at $0.85): $14.03 (~44% of bankroll, would deeply trip KILL).
KILL trigger (drawdown >= 20% = $6.40) remains armed and IS EXPECTED TO FIRE on a bad week at this size.

The 33-contract cap targets full $32 deployment per operator's explicit instruction (2026-05-24,
"willing to lose all $32"). This overrides the Kelly-CI-lower fractional-Kelly recommendation
in research/w2-v1-residual-edge.md (which supported ~25-30% deployment). The operator's risk
acceptance is explicit; the KILL trigger at 20% drawdown is the safety net.

The v5 Track A filter (SHADOW_MODE_ENABLED + LIVE_FILTER_ENABLED) is also active. It skips
v1 candidates when Polymarket or sportsbook signals suggest Kalshi is over-pricing the favorite.
Filter abstains safely when fetchers miss. See "Shadow-mode + live filter (W1+W2 follow-on)"
section below.

## How the bot is running (24/7)

Windows Task Scheduler task `KalshiLiveBot`, configured to:
- Start at user logon, restart on failure (1 min interval, 99 retries)
- Run `scripts/run_live_bot.ps1` (the supervisor)
- Supervisor auto-restarts the bot on crash, with exponential backoff

Files written:
- `data/live_trades/state.json` - LiveOrderManager state
- `data/live_trades/kill_state.json` - KillTriggerMonitor state
- `data/live_trades/heartbeat.txt` - last loop start
- `data/live_trades/bot.pid` - active PID (or absent when not running)
- `data/live_trades/logs/launcher.log` - supervisor lifecycle
- `data/live_trades/logs/live.log` - rotating daily, 14d kept
- `data/live_trades/logs/bot-stderr.log` - bot stderr (errors only with httpx silenced)

## Restart the bot (one command)

```powershell
.\scripts\restart_bot.ps1
```

Stops the running bot (graceful STOP file then Stop-ScheduledTask then Stop-Process if needed), launches the Task Scheduler task again, then polls heartbeat for up to 3 minutes and reports clean success or detailed failure. Use `-Force` to skip the confirmation prompt for unattended use.

If the bot fails preflight on a transient network hiccup (e.g., DNS resolving while the host is just waking up), `check_clock_skew` now retries 4 times with exponential backoff (2s, 4s, 8s, 16s) before giving up. Persistent failures still surface in Discord and the launcher log.

## Manage the task

```powershell
# Status
.\scripts\install_scheduled_task.ps1 -Status

# Manually start now (without waiting for next logon)
.\scripts\install_scheduled_task.ps1 -Start

# Pause supervisor (creates STOP file; bot keeps running until next restart)
New-Item data\live_trades\STOP -ItemType File

# Resume
Remove-Item data\live_trades\STOP

# Uninstall the task entirely
.\scripts\install_scheduled_task.ps1 -Uninstall
```

## Daily review (5 minutes)

```bash
uv run python -m scripts.live_review --lines 30
```

Snapshot includes:
- **Heartbeat age**: should be < 20 min (cadence is 15 min)
- **Resting / filled / closed counts** + per-order detail
- **Realized P&L total** since start
- **Kill-trigger metrics**: YES rate, fill rate, rolling means, winners count
- **Last 30 log lines** of bot activity

## Visual dashboard (live)

For an auto-refreshing browser view of bot status, orders, P&L, and v5 filter
activity:

```powershell
.\scripts\dashboard.ps1
```

Opens at `http://localhost:8501`. Auto-refreshes every 30 seconds. Shows:
- Status badge (green RUNNING / orange STALE / red DOWN) with heartbeat age + PID
- Bankroll, realized P&L, drawdown, open exposure, hit rate
- Kill trigger panel (ARMED vs TRIPPED)
- Order tabs: Resting / Filled / Closed / Intents
- Cumulative realized P&L chart over time
- v5 Track A filter activity: skipped vs passed today + recent decisions
- Live log tail (last 40 lines) + launcher log (expandable)

The dashboard is READ-ONLY. It only reads `data/live_trades/state.json`,
`kill_state.json`, `heartbeat.txt`, `logs/live.log`, `logs/launcher.log`,
and `v5_filter_shadow_log.jsonl`. Safe to run alongside the live bot.

Stop with Ctrl-C in the dashboard terminal. The bot keeps running.

## Watch for

| Indicator | Action |
|---|---|
| `STATUS: STALE` (no heartbeat in >30 min) | Bot crashed. Check log for traceback. Restart with same command. |
| `kill_trigger_tripped` event | Bot has halted itself. Read `trip_reason` + `trip_detail`. Decide: clear state to resume, OR change strategy. |
| YES rate dropping toward 90% over 20 fills | Edge eroding. Watch closely. |
| Fill rate <0.30 after 50+ attempts | Institutional MMs are stepping inside us. Strategy may not work for retail. |
| Rolling-30 mean P&L below +0.5pp | Edge has compressed (the critic-added 6th trigger). |
| Drawdown >15% of high-water mark | Pause threshold; >20% kills the bot. |

## Common operations

### Tail logs in real time

```bash
# PowerShell on Windows:
Get-Content -Path "data\live_trades\logs\live.log" -Tail 50 -Wait
```

### Inspect resting orders directly

```bash
uv run python -c "
from kalshi_bot.strategy.live_order_manager import LiveOrderManager
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.config import load_settings
s = load_settings()
with KalshiClient(s) as c:
    lm = LiveOrderManager(client=c)
    for o in lm.state.resting.values():
        print(o.ticker, o.target_price_cents, o.contracts, o.order_id)
"
```

### Stop the bot cleanly

Find the Python process running paper_trade_favorite in Task Manager
or via:

```bash
# Windows / PowerShell
Get-Process python | Where-Object {$_.CommandLine -like "*paper_trade_favorite*"} | Stop-Process
```

Sending SIGINT/SIGTERM triggers the cleanup handler:
- best-effort cancel of every resting order (DELETE /portfolio/orders/{id})
- final state.json write
- Discord alert

Ctrl-C in the terminal that launched the bot also works.

### Restart the bot

```bash
uv run python -m scripts.paper_trade_favorite \
    --mode live --yes-i-authorize \
    --starting-bankroll 32 --cadence 900 \
    --max-concurrent 5 --min-net-edge 0.02
```

State at `data/live_trades/state.json` persists across restarts. The
first loop after restart reconciles intents (lost-ack recovery) and
fills (with a 1-hour overlap window).

### Reset the kill-trigger after manual review

If a kill trigger fired and you've decided to keep trading:

```bash
uv run python -c "
from kalshi_bot.risk.kill_triggers import KillTriggerMonitor
m = KillTriggerMonitor(starting_bankroll_usd=32.0)
print('Was tripped:', m.state.tripped, 'reason:', m.state.trip_reason)
m.clear()
print('Cleared.')
"
```

## Tuning ideas (only after data accumulates)

These are deferred from the Round 5 critic. Re-evaluate after >= 50
live fills:

1. **Lower the upper price cap** if the 90-95c slice is loss-heavy
   (Bürgi-realistic edge is +1 to +3pp, not the +5pp gate headline).
2. **Raise FAVORITE_THRESHOLD** if 70-75c is loss-heavy.
3. **Tighten min-net-edge** from 0.02 to 0.03 if marginal placements
   dominate the loss column.
4. **Lower LIVE_PER_TRADE_USD** if drawdown gets uncomfortable;
   raise it once a 100+ fill positive track record exists.
5. **Add cancel-and-repost on price drift** if fill rate < 40%
   indicates we're not getting the favorable bid. Needs its own
   critic pass (introduces a fill-reconciliation race per the
   Round 5 critic).

## Files reference

- `data/live_trades/state.json` - all live orders (intents, resting,
  filled, closed) with full history
- `data/live_trades/kill_state.json` - kill-trigger counters + trip
  status
- `data/live_trades/heartbeat.txt` - last-loop timestamp
- `data/live_trades/logs/live.log` - rotating log (daily, 14d kept)

## Shadow-mode filter (W1+W2 follow-on)

The Track A v5 combined filter (Polymarket-fade + sportsbook-fade +
cross-market-consistency, locked thresholds 7c / 5c / 5c) has been
wired into v1's main loop as a SHADOW-MODE-ONLY hook. It is OFF by
default and has ZERO effect on v1's trade behavior unless explicitly
enabled by the operator.

### What shadow-mode does

For every candidate v1 scans (in both paper and live loops), the hook
calls `kalshi_bot.strategy.shadow_filter.shadow_evaluate(snap,
target_price)`. That helper:

1. Returns immediately if `SHADOW_MODE_ENABLED` is not exactly "true".
2. Calls Polymarket midpoint and sportsbook implied-probability
   fetchers. Each fetcher has a 3s HTTP timeout, one retry on
   transient failure, and never raises.
3. Runs the locked v5 combined filter against the fetched signals.
4. Appends a JSONL line to
   `data/live_trades/v5_filter_shadow_log.jsonl` capturing the
   decision (should_trade flag, fired rules, reason, confidence,
   fetch latency, fetch status).
5. Returns the decision to the caller. **v1's caller IGNORES the
   returned decision; it is for logging only.**

The hook is wrapped in TWO try/except layers (the helper catches all
internally; the v1 call site wraps it in a second try/except for
defense-in-depth). Under no failure scenario can the hook affect v1's
order placement or kill-trigger accounting.

### How to enable

```powershell
# In the PowerShell window that will spawn the bot:
$env:SHADOW_MODE_ENABLED = "true"

# Then start (or restart) the bot:
uv run python -m scripts.paper_trade_favorite `
    --mode live --yes-i-authorize `
    --starting-bankroll 32 --cadence 900 `
    --max-concurrent 15 --min-net-edge 0.01
```

For Windows Task Scheduler installations: edit
`scripts/run_live_bot.ps1` (or the equivalent supervisor script) to
set `$env:SHADOW_MODE_ENABLED = "true"` before launching the bot
process. The env var is read on every `shadow_evaluate` call, so a
restart picks up the change immediately.

THE_ODDS_API_KEY must be present in the environment (or .env) for
the sportsbook arm to fire. Without it, the sportsbook fetcher
abstains cleanly and only the Polymarket arm contributes.

### Where logs go

```
data/live_trades/v5_filter_shadow_log.jsonl
```

One JSONL line per candidate. Each line has fields: timestamp,
ticker, series_ticker, kalshi_price, poly_mid, sportsbook_implied,
cross_market_implied, should_trade, fired_rules, reason, confidence,
fetch_status, fetch_latency_ms. File is append-only.

Runtime fetcher caches (best-effort, optimization-only) write to
`data/v5/runtime_cache/polymarket_<YYYYMMDD>.parquet` and
`data/v5/runtime_cache/sportsbook_<YYYYMMDD>.parquet`. Safe to
delete; they regenerate on the next loop.

### How to inspect recent shadow decisions

```powershell
# Tail the last 20 decisions:
Get-Content -Path "data\live_trades\v5_filter_shadow_log.jsonl" -Tail 20

# Quick count of "should_trade=false" (filter-skip-only) entries:
Get-Content "data\live_trades\v5_filter_shadow_log.jsonl" `
  | Select-String '"should_trade": false' `
  | Measure-Object | Select-Object -ExpandProperty Count

# Pretty-print one decision:
Get-Content "data\live_trades\v5_filter_shadow_log.jsonl" -Tail 1 `
  | ConvertFrom-Json | Format-List
```

Python summary:

```python
import json
from pathlib import Path
lines = Path("data/live_trades/v5_filter_shadow_log.jsonl").read_text().splitlines()
records = [json.loads(line) for line in lines]
fired = [r for r in records if not r["should_trade"]]
print(f"Total candidates logged: {len(records)}")
print(f"Filter would skip: {len(fired)} ({100*len(fired)/max(len(records),1):.1f}%)")
print(f"By rule:")
from collections import Counter
print(Counter(rule for r in fired for rule in r["fired_rules"]))
```

### Evaluation timeline

120 to 180 days of accumulated shadow decisions on real v1
candidates. The V5 verdict (`research/v5/FINAL-VERDICT.md`) and the
V5-A2 build doc (`research/v5/04-sportsbook-filter-build.md`
Section 7) lock this timeline. After accumulation, run the TA
evaluation from `scripts/v5/run_sportsbook_filter_backtest.py`
against the shadow log + Kalshi resolution lookups. If TA4 cleanly
passes (CI lower bound > 0), activate the filter as a SKIP overlay
(a separate operator-authorized change). If still borderline,
extend shadow-mode another 60 days or revisit the paid-tier
historical-odds approach.

### How to disable

```powershell
# Remove the env var, then restart the bot:
Remove-Item Env:\SHADOW_MODE_ENABLED
# Or set to anything other than "true":
$env:SHADOW_MODE_ENABLED = "false"
```

The bot reads the env var on every call; the next loop after the
change will skip the shadow hook entirely (cost: one env-var lookup
per candidate).

### Safety summary

- Shadow-mode is LOGGING ONLY. v1's trade decisions are unchanged.
- Default OFF. Operator must explicitly enable.
- No new writes to `state.json`, `kill_state.json`, `.env`, or any
  v1 trading-state file.
- READ-only on Polymarket Gamma + CLOB and the-odds-api.
- Per-loop sportsbook credit budget: 5 calls maximum (configurable
  via `SHADOW_SPORTSBOOK_LOOP_BUDGET` env var). At v1's 15-min scan
  cadence the expected monthly burn stays under the free 500-credit
  tier even on the worst-case month.
- Every fetcher and the hook itself can fail without raising; the v1
  bot continues exactly as it would with shadow-mode disabled.

## Emergency operator protocol

If something is clearly broken (huge unexpected loss, Kalshi balance
diverges from state, fill rate at zero):

1. Stop the bot immediately (SIGINT or kill the process).
2. Check `data/live_trades/state.json` for any unexpected orders.
3. List Kalshi resting orders directly via the dashboard or the API.
4. Cancel any orphan orders manually via the Kalshi UI.
5. Move `data/live_trades/state.json` to a backup file
   (`state.json.bak-YYYY-MM-DD`).
6. Investigate before restarting.

The bot's $4.75 max simultaneous exposure means worst-case daily
loss in a runaway-bug scenario is bounded. If you see loss > $5 in
one day, something is wrong with the code, not the strategy.
