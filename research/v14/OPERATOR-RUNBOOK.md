# v14 Live Deployment Operator Runbook

**Purpose:** day-to-day instructions for running the MLB-night sportsbook lead-lag strategy at $5-10 small capital.

## Quick start

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
$env:PYTHONPATH = "src"
.venv-kronos\Scripts\python.exe scripts\v14\live_alerter.py
```

Run this any time during MLB season when you want to check for alerts. Best times: 3-7 PM ET on game days (covers evening commence times of 6-10 PM ET).

## What the alerter does

1. Calls the-odds-api twice: once for current MLB odds, once for the snapshot from 3 hours ago. Cost: ~20 credits per run.
2. Compares the implied probability for each game's home team between the two snapshots.
3. Filters to games commencing in the next 1-3 hours (your action window).
4. If any qualifying game has a sportsbook home-side delta >= 60 basis points (or <= -60 bp), it FIRES an alert.

## What to do when it fires

Each alert prints something like:

```
Tampa Bay Rays vs Boston Red Sox
  commence: 2026-06-15T23:10:00Z (1.8h away)
  sportsbook (home): 0.555 -> 0.598 (delta +0.0430)
  ACTION: BUY YES on HOME (Tampa Bay Rays) at <= 0.604
  Kalshi ticker hint: KXMLBGAME-26JUN15TBBOS* OR KXMLBGAME-26JUN15BOSTB*
```

Steps to execute the trade:

1. Open Kalshi web UI (https://kalshi.com)
2. Search for the ticker prefix. Try the first hint; if not found, try the second.
3. Find the YES-side market for the team in `ACTION` (e.g., "Tampa Bay Rays" YES market)
4. Place a **LIMIT BUY** order:
   - Price: at or below the suggested max (in the example, 0.60)
   - Size: 1 contract initially. If your bankroll allows, up to 20 contracts max (each contract is $1 max risk).
5. Wait for fill. If unfilled within 30 minutes, you can cancel and re-place at slightly higher price, but DO NOT exceed the suggested max price + 1 cent.

## Capital rules

- Maximum total deployment: $10 (operator authorized)
- Maximum per-trade size: $1 (1 contract)
- Position concurrency: up to 10 contracts open simultaneously
- Initial deployment: start at $5, scale to $10 only after 5+ winning trades

## Kill conditions (you stop placing trades if any fires)

- **Drawdown:** if your realized cumulative P&L drops below -20% of initial capital (-$2 on $10), pause and review.
- **Consecutive losses:** if you lose 5 trades in a row, pause.
- **Time:** stop at 8 weeks from first trade for v15 evaluation, regardless of P&L.

## Tracking your trades

Every alert is appended to `data/v14/live_alerts.jsonl`. After you place a trade, manually edit your tracking log (suggested: `data/v14/operator_trades.jsonl`) with these fields per trade:

```json
{
  "alert_ts": "2026-06-15T19:15:00Z",
  "ticker": "KXMLBGAME-26JUN15TBBOS-TB",
  "side": "yes",
  "limit_price": 0.604,
  "filled_price": 0.605,
  "n_contracts": 1,
  "filled_ts": "2026-06-15T19:18:00Z",
  "settlement": "yes",
  "settled_ts": "2026-06-16T02:30:00Z",
  "gross_pnl": 0.395,
  "fee": 0.020,
  "net_pnl": 0.375
}
```

(The settlement and P&L fields fill in after the market resolves.)

## What to expect

Per the v14 backtest:
- **Fire rate:** ~25% of MLB-night games show a >= 60bp sportsbook delta
- **Forward 4 weeks (120 MLB-night games):** ~30 fires
- **Mean per-fire net P&L:** +$0.15 (range -$0.04 to +$0.33 in 95% CI)
- **Win rate:** 64%
- **Expected 4-week P&L on $10 capital:** -$1 to +$10 (realistic) with point estimate around +$4.50

## Common gotchas

- **No fires for several days:** normal. Sportsbook lines often stay stable when no new info hits. Just keep running daily.
- **Multiple alerts in one evening:** prioritize by `hours_to_commence` (smaller = more urgent), but try to place all of them if capital allows.
- **Kalshi ticker not found:** the alerter's ticker hint uses Becker conventions which may not match Kalshi's current ticker. Search Kalshi by team names; the format is usually `KXMLBGAME-{YYMMMDD}{HOMETEAM}{AWAYTEAM}-{TEAM_WINNER}` or reversed.
- **Spread > 1c:** if you see the Kalshi spread is more than 1 cent, the strategy expected edge is smaller than v14 modeled (haircut was 7bp). Use your judgment.
- **the-odds-api credits exhausted:** the alerter prints `credits remaining`. If below 1,000, ask the orchestrator to consider re-purchasing or scaling back.

## When to escalate to the orchestrator

- After 4 weeks of trading: run v15 evaluation (orchestrator will read the alerts log + your trades)
- If win rate drops below 30% (5 losses in a row triggers this implicitly)
- If you observe Kalshi market behavior that contradicts v14 assumptions (e.g., live spreads >= 3 cents consistently)
- If the-odds-api credits run low

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
