# v14 Live Daemon Architecture Review

**Round:** 19 (review of 02-live-daemon-architecture.md).
**Date:** 2026-05-27.
**Reviewer:** review-agent.
**Status:** pre-implementation gating review. Read-only inspection of v1 and v14 source.

## Section A. KILLER findings (must fix before implementation)

### K1. v1 currently holds $31.30 against v1's existing $32 cap; capping v1 at $19 leaves $12.30 of EXISTING resting exposure outside the new cap

state.json `starting_bankroll_usd` is 31.299999999999997 (line 2254). state.json
shows 101 resting orders (`grep -c '"target_price_cents"'` = 101). Several
resting orders are at 74 to 75 cents per contract on real Kalshi tickers
(e.g., KXUFCFIGHT-26JUN14NICDAU-NIC at 74c, KXNBADRAFTTOP-26-10-KFLE at 75c,
KXWCSTAGEOFELIM-26JOR-GS at 75c). Even allowing for most being unfilled
maker bids (which Kalshi does NOT lock cash against per the
2026-05-25 note in paper_trade_favorite.py lines 110-115), the LIVE
`portfolio_value` field plus cash is approximately $31.30.

When `run_live_bot.ps1` is edited to pass `--starting-bankroll 19.00`:

1. The bot's `--starting-bankroll` arg is a *baseline for drawdown
   measurement*, not a hard cap on deployed capital. `DrawdownMonitor`
   compares current bankroll against `starting_bankroll`. With actual
   live bankroll $31.30 and new starting_bankroll $19, the bot will
   measure a SPURIOUS +65% RUN-UP at startup ($31.30 / $19 - 1), not
   a drawdown. This will not trigger any kill in the wrong direction,
   but the drawdown metric becomes uninterpretable until v1 burns
   $12.30 of P&L.

2. The actual cap on new orders is the budget gate in
   `paper_trade_favorite.one_loop_favorite_live` lines 750-763:
   `projected_exposure > cash_usd`. cash_usd reads from Kalshi's
   `/portfolio/balance`. Since Kalshi's view of cash is the SAME
   whether you tell the bot "$19" or "$32" starting bankroll, the
   capital split is NOT enforced by `--starting-bankroll 19`. The bot
   will continue to place orders up to the actual Kalshi cash
   available (the full ~$32, minus whatever v14 has consumed).

3. Worse: `compute_dynamic_max_concurrent` in `_resolve_max_concurrent_live`
   uses `cash + portfolio_value` (line 168-173), NOT starting_bankroll.
   So `--max-concurrent auto` divides the FULL Kalshi balance by
   FAVORITE_UPPER_CAP. The 60% cap is not enforced anywhere.

**The proposed capital split mechanism does not work.** `--starting-bankroll 19`
gives v1 the wrong drawdown baseline AND does not cap v1's spending.
v1 and v14 will both race against the same shared Kalshi cash pool.

Fix options:
- (a) Introduce a NEW arg `--max-cash-deployment-usd 19.00` to
  `paper_trade_favorite.py` that hard-caps `cash_usd` in the budget
  gate at `min(actual_cash, 19.00 - current_resting_exposure - portfolio_value)`.
  This is the only true cap.
- (b) Cancel enough v1 resting orders to bring v1's `portfolio_value +
  resting_exposure` below $19 BEFORE swapping in the new
  `--starting-bankroll` and starting v14. (Operator step.)
- (c) Both. Recommend both.

Without one of these, v14 cannot get $13: v1 will hold $31.30 forever
and v14 will be denied any cash on the budget gate (Kalshi cash
already committed to v1's portfolio_value).

### K2. v1's existing $31.30 resting exposure does NOT auto-cancel on starting_bankroll reduction; v14 is starved at startup

Inspection of `LiveOrderManager.__init__` and `_resolve_starting_bankroll_live`
(paper_trade_favorite.py lines 238-290) confirms: changing
starting_bankroll has no effect on existing resting orders. The 101
resting orders in state.json continue to sit on Kalshi consuming
projected cash. v14's `_read_kalshi_balance_and_positions` will see
the same cash and positions and conclude there is no headroom.

If the operator wants the 60/40 split to take effect TODAY, v1 must
cancel enough orders to free $13 of headroom before v14 launches. v1
has no built-in mechanism to do this proportionally; the operator
would have to manually run `LiveOrderManager.cancel_all_resting()` or
write a one-shot script that cancels in priority order. The
architecture doc does not mention this step.

Fix: Section D11 needs an operator pre-launch step that brings v1's
combined (cash on order + filled positions) under $19, OR the
`--max-cash-deployment-usd` cap from K1 (which would cause v1's
budget gate to skip new orders until natural attrition brings it
under cap, accepting that the split takes weeks to materialize as
old orders cancel/fill/settle).

### K3. v14 ticker matching is unreliable; the daemon will frequently fail to find the right Kalshi market

`scripts/v14/live_alerter.py` line 142-163 (`kalshi_ticker_from_game`)
literally documents that it CANNOT determine team order, returns
BOTH possible orderings, and says "let the operator find the exact
ticker on Kalshi." This is fine for a one-shot human-in-the-loop
alerter. It is a KILLER for an automated daemon.

The Becker ticker convention per `scripts/v11/team_maps.py` is
`KX{SPORT}-{YY}{MMM}{DD}{TEAM1}{TEAM2}-{WINNER_ABBR}` with the
comment "Team1+Team2 are concatenated without separator; abbreviation
lengths vary (typically 2-4 chars). Longest-match-first split
heuristic." There is NO documented home-first vs away-first vs
alphabetical rule. Worse, abbreviations are AMBIGUOUS: MLB_MAP shows
ATL means both Atlanta Braves (MLB) and Atlanta Hawks (NBA);
WSH/WAS both map to Washington Nationals; KC/KCG both map to Kansas
City Royals; OAK/ATH both map to Oakland Athletics. Two-way maps
silently drop entries.

The daemon must:
1. Call Kalshi `/events?series_ticker=KXMLBGAME&status=open` (or
   `/markets?series_ticker=KXMLBGAME&status=open`) on each loop
2. For each open event today, extract the actual ticker
3. Match by date AND by checking the two-team abbreviation substring
   against the-odds-api home/away teams via the inverse map (handle
   ambiguity: TB could be Tampa Bay Rays but in NBA WSH could be
   Wizards, etc., so restrict map to MLB for MLB events)
4. Return the WINNER-side market (e.g., the `KXMLBGAME-...-TB`
   ticker for Tampa Bay) for the side we want to take

The daemon needs a tested `find_kalshi_ticker(home_team, away_team,
commence_dt) -> str | None` function that consumes the Kalshi
`/markets` listing. Without this, the daemon will either: (i) silently
skip every fire because the constructed ticker prefix does not match,
or (ii) place orders on the WRONG ticker (e.g., the wrong team's YES
market). Either is catastrophic for live capital.

Fix: D5 needs to be rewritten. Add a new module
`src/kalshi_bot_v14/ticker_match.py` that queries Kalshi `/markets`
and returns a verified ticker, plus 5+ tests with real ticker
patterns from Becker sample. Move the v11 longest-match-first split
heuristic into this module so the bot can roundtrip ticker -> teams.
If the function returns None, the daemon SKIPS the fire and logs
`ticker_match_failed` to Discord. This is the safe failure mode.

### K4. v14 KillTriggerMonitor cannot be reused with v14-specific config without code change; class wires v1 settings via Settings.KILL_* fields

`KillTriggerMonitor.__init__` accepts a `KillTriggerConfig`, so
constructor wiring is fine. But the v14 daemon's design (D8) says it
will use a "slimmer" KillTriggerMonitor. Inspecting kill_triggers.py
shows 6 triggers all baked into `_check_triggers`. There is no way
to enable a subset; passing a permissive config (e.g.
`yes_rate_min=0.0`, `fill_rate_min=0.0`) functionally disables triggers
1 and 5 but the YES-rate trigger still expects to be checked. This is
fine but the architecture doc claims "Drawdown: stop at 20% of v14
starting bankroll" while `KillTriggerMonitor` per finding 8 has NO
drawdown check (it's owned by `DrawdownMonitor`). The v14 daemon
MUST instantiate both `DrawdownMonitor` AND `KillTriggerMonitor`,
plus add a NEW "daily orders cap" and "consecutive losses" trigger
not present in v1's config.

Specifically, D8 lists:
- Drawdown 20% -> NOT in KillTriggerMonitor; needs DrawdownMonitor
- Consecutive losses 5 -> NOT in KillTriggerMonitor; needs new logic
- Time 8 weeks -> NOT in either; needs new logic
- Daily orders cap 10 -> NOT in either; needs new logic
- Per-trade size $0.95 -> NOT in either; the per-trade cap is in
  paper_trade_favorite.py args, not in any risk class

Fix: D8 needs to be rewritten as: "v14 instantiates DrawdownMonitor
with kill threshold 20%, plus a v14-specific
`V14KillTriggerMonitor` class that wraps KillTriggerMonitor with
permissive config AND adds consecutive_losses, time_elapsed, and
daily_orders_count checks." Architecture doc currently overstates
reuse and underestimates new code. Implement and test the additional
triggers.

## Section B. IMPORTANT findings (fix before deploy, not blocking implementation start)

### I1. D4 file-read race: v14 reads v1 state.json non-atomically

v14 reads `data/live_trades/state.json` for collision check. v1
writes state via tempfile-rename (LiveOrderManager._save line 184-187),
which is atomic on POSIX but on Windows the rename may not be atomic
in all cases (per Python docs, `os.replace` on Windows uses
`MoveFileExW` which is atomic since Vista for the same drive). This
is safe enough.

But the design's open question of "should v14 also check
Kalshi /portfolio/positions" is a YES. Reading state.json gives v14
v1's INTENT; it does not give v14 a guarantee. A v1 order could
fill in between v14's read and v14's POST. The collision is rare
(both bots evaluating the same ticker in the same 5-min window is
unlikely) but for a fire-and-forget daemon, the cost of an extra
GET `/portfolio/positions` per fire is negligible. Recommend
adding both checks: v1 state.json (intent-level) AND Kalshi
`/portfolio/positions?ticker={X}` (filled-level). Skip if either
shows v1 holds the ticker.

Note: there is no existing usage of `/portfolio/positions` in src/
(grep returned no matches). The daemon will need to add this
endpoint to KalshiClient usage. Trivial; just a GET. Or it can
read v1's state.json `filled` dict, since `reconcile_fills` updates
state.json on every loop.

### I2. D6 cadence + the-odds-api credit math is wrong

The architecture doc says "24 loops per 12h window = ~480
credits/day." Wrong arithmetic. 12 hours at 5-min loop = 144 loops
per day, not 24. At 2 credits per loop = 288 credits/day. At 5
credits per loop (the alerter's docstring says ~30 credits per run
because the historical endpoint is more expensive) = much higher.

`live_alerter.py` docstring (line 30-31) says "~30 the-odds-api
credits per run." If v14 mirrors the alerter and runs 144 times per
day, that's 4,320 credits per MLB day. Over a 4-week MLB-night
season (about 28 days), that is approximately 121,000 credits.
Operator has 13,489 remaining. v14 will exhaust the-odds-api
credits in approximately 3 days at 5-min cadence.

Fix: D6 cadence MUST be 15 or 20 minutes, not 5. At 15-min
cadence: 48 loops/day * 30 credits = 1,440/day, ~40,000/month, still
above 13,489. At 30-min cadence: 24 loops/day * 30 credits =
720/day, ~21,000/month, still above. Sustainable cadence with
current credit pool is approximately 1 hour (~360/day,
10,800/month).

Additionally, the alerter ALREADY runs on a 1-3 hour pre-commence
window with the LOOKBACK_HOURS = 3 sportsbook delta. Faster polling
does NOT find new fires; the underlying sportsbook signal updates
every 5-15 min, but credit cost is per call regardless. Recommend
10-min cadence ONLY during the 21:00 UTC to 04:00 UTC MLB-night
firing window, snooze otherwise. This narrows to about 7 hours of
firing per day = 42 loops * 30 credits = 1,260/day, 35,000/month.
Still over the pool. Either reduce cadence to 15 min (28 loops * 30
= 840/day, 23,500/month), or operator must top up credits before
deploy. Recommend operator top up first OR pick 15-20 min.

Update: actually rechecking the alerter, it calls the historical
endpoint once and the current endpoint once. Per the-odds-api
pricing, historical is 10x base, h2h market = ~1x multiplier, so
each call is approximately 1 base + 10 historical = 11 credits, not
30. The alerter docstring of 30 is a conservative high-side
estimate. With 11 credits per loop at 15-min cadence and 7-hour
window: 28 loops * 11 = 308/day, ~8,600/month. Sustainable.

Fix: lock cadence at 15 min within a 21:00-04:00 UTC firing window.
Re-verify credit cost per loop in implementation and add an alert
when credits < 2,000 (matches the existing alerter heuristic).

### I3. Kill triggers: 20% drawdown = $2.56 is correctly sized but consecutive-losses 5 is too tight given expected loss-rate

v14 backtest: 64% win rate, mean +$0.150 per fire, CIs [-0.037,
+0.326] row and [-0.020, +0.332] day-block. Under a 64% win rate
i.i.d. binomial, probability of 5 consecutive losses in any window
of 28 fires is 1 - (1 - 0.36^5)^24 = approximately 14%. Over a
4-week trial with ~30 fires that's a 1 in 7 chance of a SPURIOUS
trip. Not negligible.

Worst-case scenario: 5 consecutive $0.95 losses = -$4.75. Already
exceeds 20% drawdown trigger ($2.56). So the consecutive-losses
trigger trips BEFORE the drawdown trigger, but actually after
$2.56 of loss the drawdown trigger would already have fired (at
~3 consecutive worst-case losses). The triggers are layered:
drawdown is the binding constraint. Consecutive-losses is mostly
a sanity check.

But: a 14% spurious-trip rate over the trial is high enough that
the operator should set 7 or 8 consecutive losses, not 5. At 7
consecutive: spurious rate drops to ~2%. Operator's
OPERATOR-RUNBOOK.md ALREADY says 5 (line 53), so this is a
documentation inheritance, not new. Still recommend bumping to 7-8
for the daemon. Cost of late kill is small ($0.95 per extra loss),
benefit of fewer false trips is real.

Fix: bump consecutive-losses kill from 5 to 7 in D8.

### I4. D2 single-instance lock: bot.pid check is fine but the lock path differs from v1

v1's `single_instance.py` uses `DEFAULT_LOCK_PATH = Path("data/live_trades/bot.lock")`
and `DEFAULT_PID_PATH = Path("data/live_trades/bot.pid")`. v14 must
override BOTH to `data/v14/v14_bot.lock` and `data/v14/v14_bot.pid`.
The acquire_live_lock function signature
(`lock_path: Path = DEFAULT_LOCK_PATH, pid_path: Path = DEFAULT_PID_PATH`)
DOES accept overrides, so this works mechanically.

But: if v14 is accidentally launched twice (manual + Task Scheduler),
the SECOND instance reads v14_bot.lock, sees the first PID alive (via
psutil), and raises `SystemExit`. Good. Lock contention is handled.

However the lock check uses `_BOT_PROCESS_NAMES = frozenset({"python.exe",
"python", "uv.exe", "uv"})`. If v14 daemon is launched via something
OTHER than python.exe (e.g., via a different uv wrapper or as a
service wrapper), the check could incorrectly conclude the lock is
held by an "unrelated process" and overwrite it. Probably fine for
launching via PowerShell `python.exe` directly. Document the launch
command explicitly in run_v14_bot.ps1.

Fix: ensure run_v14_bot.ps1 launches via `uv run python` or `python.exe`
directly, NOT a wrapper script that would change ProcessName. Add a
launch-time check that logs the actual process name to facilitate
diagnosis.

### I5. KalshiClient rate limit concerns are low but require monitoring

KalshiClient uses tenacity with `wait_exponential(min=1, max=60)`
and `stop_after_attempt(8)`. Token bucket is per-key (Kalshi
documents this). Both v1 and v14 use the SAME `KALSHI_API_KEY_ID`
in `.env`. Combined request rate:
- v1: 15-min loop. Per loop: scan markets (1-5 calls), reconcile
  intents/resting (1 call per resting order, up to 100+), fills (1+),
  settlements (1 per filled order). At 101 resting orders in
  current state, that's ~110 reqs per loop, or about 440/hr.
- v14: 15-min loop. Per loop: ~1 markets call, 0-3 portfolio
  reads. ~5 reqs per loop, ~20/hr.

Combined ~460/hr. Kalshi's published token bucket is 100/sec
sustained for trade API, which is 360,000/hr. We are nowhere near.
429 backoff is robust.

Concern: v1's reconcile_resting iterates over EVERY resting order
each loop (101 calls today). If v1 grows beyond ~600 resting orders,
loop time exceeds 5 minutes and v1 starts overlapping itself.
Architecture-doc-independent issue but worth noting; v14 is not the
cause.

Recommendation: NICE-TO-HAVE that the v14 daemon emit per-loop
KalshiClient request counts to a log, so combined rate is observable.
Trivial to add.

### I6. D11 STOP handler does not currently exist; must be implemented

`paper_trade_favorite.py` SIGTERM handler (lines 794-821) cancels
v1's resting orders. v14 needs the SAME pattern. The architecture
doc says "STOP file handler cancels resting" but does not specify
implementation. Need:
- Watch for `data/v14/STOP` in the loop start
- On STOP detection, call `lm.cancel_all_resting()` and exit
- SIGINT/SIGTERM handler also calls `cancel_all_resting`

Fix: implement explicitly. Add test.

### I7. D8 kill trigger trip does NOT cancel v14 resting orders

The architecture doc lists kill triggers but does not say what
happens when one fires. By inspecting v1: `KillTriggerMonitor.tripped`
prevents NEW placements (paper_trade_favorite line 527-528 and
line 589-591) but does NOT cancel existing resting orders. Resting
bids continue to live on Kalshi, can still fill, and the bot will
continue to record their settlements. This may or may not be what
v14 wants.

Operator's stated kill conditions are "stop placing trades" not
"stop existing trades from filling." v1's behavior matches that.
For v14, recommend the SAME behavior: trip = no new orders, but
existing fills continue. If operator wants full unwind, document
that they should also `touch data/v14/STOP`.

Fix: clarify in D8: "Kill trigger trip stops new placements only;
operator must STOP to also cancel resting orders." Add Discord
message guidance: "v14 kill trigger tripped: stopping new orders.
Touch data/v14/STOP if you want to cancel remaining resting bids."

### I8. v1 regression risk: --starting-bankroll behavior change in run_live_bot.ps1

Inspected tests/test_paper_trade_favorite.py (lines 124-343 hit on
the `starting_bankroll` grep). Tests cover:
- `_parse_starting_bankroll_arg` for float and "auto" values
- `_resolve_starting_bankroll_paper` with explicit/auto/rebaseline
- `_resolve_starting_bankroll_live` with explicit/auto/rebaseline/
  fallback/SystemExit paths

These tests DO exercise the `_resolve_starting_bankroll_live` path
with explicit float values. Adding `--starting-bankroll 19.00` to
run_live_bot.ps1 hits `_resolve_starting_bankroll_live(19.0, ...)`
which goes down the explicit-value branch on line 257-258
(`if setting != STARTING_BANKROLL_AUTO: return float(setting)`).
That branch is covered by `test_resolve_starting_bankroll_live_explicit`
(line 276-284) and `test_resolve_starting_bankroll_paper_explicit`
(line 185-190).

But: changing `starting_bankroll_usd` in state.json from 31.30 to
19.00 causes:
1. DrawdownMonitor sees `current_bankroll > starting_bankroll`
   (since Kalshi cash + portfolio_value is still $31.30). This
   reports negative drawdown which DrawdownMonitor handles as
   "no drawdown" (drawdown_pct = max(0, ...)). Existing tests in
   test_drawdown.py should cover; verify.
2. The kill_state.json `starting_bankroll_usd` field used by
   `loss_dollar_fallback_pct` (kill_triggers.py line 251) drops
   from $31.30 to $19. The threshold for "catastrophic single loss"
   shrinks from $3.13 to $1.90. v1 trades at $0.95 per contract;
   even a full-loss single trade is $0.95, well under $1.90. So
   the trigger is still safe. But the kill_state.json is loaded
   from disk and its persisted bankroll could mismatch. Need to
   verify whether KillTriggerMonitor re-reads bankroll on each
   start, or persists the old value. Inspecting:
   `kill_triggers.py` `_load` line 109-132 uses
   `raw.get("starting_bankroll_usd", default_bankroll)` so persisted
   wins over new. v1 currently has $31.30 persisted; changing the
   command line won't change it.

Fix: confirm `kill_state.json` `starting_bankroll_usd` value after
edit. If $31.30, operator must either (a) accept that the v1 kill
threshold stays at $31.30-derived $3.13 (which is FINE; less
conservative is not unsafe at $0.95/trade), or (b) delete
kill_state.json before relaunch so it re-initializes at $19.

Recommend: leave kill_state.json alone (option a). Document in
deployment sequence.

## Section C. NICE-TO-HAVE findings (post-deploy improvements)

### N1. Architecture doc credit-budget arithmetic should be re-verified empirically before launch

I2 above showed the doc's "480 credits/day at 2 credits each" is
wrong on both counts (loops/day and credits/call). Recommend the
implementation phase runs the daemon for 1 hour in observe-only
mode and counts actual credits consumed. Adjust cadence based on
empirical rate, not theoretical.

### N2. Add credit-exhaustion alert to v14 daemon

Per the alerter's pattern (FINAL-VERDICT.md line 129: "Each alerter
run costs ~20 credits"), the daemon should print credits remaining
each loop and Discord-alert if < 2000.

### N3. v14 daemon should NOT use --rebaseline semantics; just pass explicit $12.80 each launch

The auto-rebaseline pattern works for v1 because v1 IS the only bot
on the account. For v14, "auto" would read $31.30+ from Kalshi
which is the WRONG starting point. v14 should ALWAYS pass an
explicit `--starting-bankroll 12.80` (well, v14 doesn't use
paper_trade_favorite.py so this is about v14's own analog).
Translate D3 explicit value into the v14 daemon code path.

### N4. State.json schema versioning

If v14 ever evolves to NO-side BUY (vs current YES-only), the
LiveOrderManager `LiveOrder.side` field would need extension. No
versioning currently exists. Not v14-launch-blocking but worth a
TODO.

### N5. Discord alert volume

D9 lists 5 event types for v14 Discord alerts (start, place, fill,
settle, kill). At 30 fires per 4 weeks, that's ~120
non-kill messages per month, on top of v1's existing alert volume.
Operator may want a separate Discord channel for v14, or a
muted-by-default-info-channel setup. NICE-TO-HAVE.

### N6. The v14 backtest expected-loss-distribution is asymmetric; design v14 to ALSO log realized P&L per fire after each settlement

The 5-cycle expected window is wide (-$0.04 to +$0.33). At 30 fires
over 4 weeks, the realized mean will be very noisy. After 5 fires
the empirical mean has standard error of approximately
0.18 / sqrt(5) = $0.08, so the operator cannot conclude much from
the first 5 fires. The architecture should explicitly call out:
"DO NOT update kill triggers based on the first 10 fires; wait for
n >= 20 before any human intervention." Document in OPERATOR
runbook.

### N7. Test test_v1_collision.py needs to cover BOTH state.json read AND positions endpoint (per I1)

If the operator adopts I1's recommendation of dual collision check,
test must cover both. NICE-TO-HAVE; KILLER if dual-check accepted.

### N8. Recommend a paper-mode period of 7 days before live D7 placement

Open Question 3 in the architecture doc asks "Should v14 use
paper-mode first?" and tentatively says no. Given K3 (ticker
matching is unreliable until tested) and I2 (credit budget is
wrong), recommend a 7-day paper-mode period where v14 logs intended
orders but does NOT place. Cost: ~$1 of credits, zero capital risk.
Benefit: confirm ticker matching works on at least 5 fires, confirm
credit cost is sustainable.

## Section C. Verdict

**Verdict: PROCEED WITH CHANGES.** The core architecture is sound,
but the four KILLER findings (capital cap mechanism does not enforce
the 60/40 split, v1's existing $31.30 exposure starves v14 at
startup, ticker matching is not reliable for an automated daemon,
and the kill trigger design under-specifies new code) must all be
addressed before any code is written, otherwise the daemon will
either deadlock on capital, place orders on wrong tickers, or
silently fail to trip safety triggers.

Recommended sequence:
1. Update D3 with `--max-cash-deployment-usd` arg AND operator
   pre-launch cancel step (fixes K1+K2)
2. Specify ticker_match.py module with Kalshi /markets lookup and
   verification tests (fixes K3)
3. Re-design D8 as DrawdownMonitor + V14KillTriggerMonitor with
   explicit new-code listing (fixes K4)
4. Update D4 to add `/portfolio/positions` second check (I1)
5. Lock D6 cadence at 15 min within 21:00-04:00 UTC window after
   correcting the credit math (I2)
6. Bump consecutive-losses kill from 5 to 7 (I3)
7. Then begin implementation

KILLER count: 4. IMPORTANT count: 8. NICE-TO-HAVE count: 8.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013.*
