# v1 settlement parity with v14 (2026-05-30)

Operator: "Update v1 with the same rigor. Make sure it's detecting everything
and outputting everything correctly (rn it says 0.00 PL also which is wrong)."

## Why v1 showed $0.00 (same root cause, already fixed)

v1 shares `LiveOrderManager.reconcile_settlements()` with v14, so the
finalized-vs-settled fix (committed `abdb220`) already applies to v1. v1
reports realized $0.00 only because the RUNNING process predates the fix; a
restart back-settles. Real-data smoke (temp copy, live API, read-only):
reconcile_settlements settles **5 finalized** v1 orders to true realized
**-$0.74**; filled drops 29 -> 24; live state untouched.

## v1 is structurally different from v14

v1 filled=29 = **5 finalized + 24 legitimately-OPEN long-horizon** positions
(season-long bets: KXNBAPLAYOFFWINS, KXIPLFINALS, ... that resolve weeks or
months out). So v14's filled-age stuck clock (24h) would FALSE-FLAG all 24
normal positions. v1 needs close_time-based detection, not fill-age.

## Council (4 members + verifier hit session limit; orchestrator synthesized)

- **D1 (kill-trigger voids):** v1's `KillTriggerMonitor` records outcome into
  `recent_outcomes`; the YES-rate trigger is `sum(window)/len`, so a void's
  `-1` drags the sum negative -> false YES_RATE_DROP kill (dominant hazard per
  Risk member). FIX: in the v1 settlement loop, skip `kt.record_settlement`
  when `s.resolution_outcome == -1`. Guard on the EXPLICIT field (not the
  `-1`-defaulted local). The void's capital release + P&L are still booked by
  reconcile_settlements; only the kill-trigger recording is skipped.
- **D2 (stuck escape): TIE BROKEN -> v14 unchanged + v1 gets a NEW alert-only
  method.** `flag_stuck_past_close(min_hours_past_close=48)`: flags ONCE (via
  `stuck_alert_ts`) a filled order whose market is past its own `close_time` +
  buffer but not terminal. It does NOT void or mutate P&L (operator-tracked
  season-long positions; the operator decides). Gates on close_time, so normal
  future-close positions are never flagged. v14 keeps its auto-void escape
  (short-horizon, capital-fluidity); v1 is alert-only (Risk + Operator).
  Rejected: refactoring the shipped v14 method to close_time (blast radius on 5
  tests) and auto-voiding v1 long-horizon positions (phantom-exit risk).
- **D3 (ambiguous orphan): report-only, never AUTO-adopt; adopt only on
  operator confirmation.** v1 had 1 untracked executed order
  `KXUFCOCCUR-26CMCGMHOL-26JUL13` (coid `342f2cb1`, a PRE-tagging raw uuid
  unattributable to v1 vs a manual operator position by inspection). Auto-
  adopting a possibly-manual position could trip a kill on operator capital,
  so it was surfaced, not auto-adopted. **Operator confirmed 2026-05-30 it is
  a lost v1 order** (active deep-favorite YES 1c @ $0.75, resolves
  2026-07-13). Adoption tool: `scripts/adopt_v1_orphan.py` (operator NAMES the
  order by coid prefix; never auto-detects; dedups vs v1 AND v14; adopts into
  v1 `filled` with NO P&L; seeds processed_fill_ids; dry-run default,
  --i-mean-it to write with the bot stopped). It is active/long-horizon, so it
  settles in July, not on restart; `flag_stuck_past_close` will not flag it
  (future close).
- **D4 (settlement Discord):** same bugs as v14 existed in v1 (one webhook per
  settled order = burst on first back-settle; voids miscounted as losers).
  FIX: one batched message per pass, W/L/V separated. CRITICAL: the per-order
  `kt.record_settlement` stays in its own loop OUTSIDE the Discord try/except,
  so a webhook failure can never skip a kill check.

## Implementation
- `scripts/paper_trade_favorite.py`: settlement block rewritten (D1 void-skip +
  D4 batch/void-separated + kill_reason captured and pinged outside the Discord
  try/except) + D2 `flag_stuck_past_close` wiring (env `V1_STUCK_HOURS_PAST_CLOSE`,
  default 48; alert-only; runs every loop even when killed).
- `src/kalshi_bot/strategy/live_order_manager.py`: new `flag_stuck_past_close`.
- W/L/V bucketed by `resolution_outcome` (1/0/-1), not P&L sign, so a fee-eroded
  YES win still reads as a win and W+L+V == count (post-review Low-1 fix, applied
  to v14's `_wlv` too).

## Review (post-impl, general-purpose agent)
No Critical, no High. Confirmed: kill-check never skipped by a Discord failure;
void-skip does not skip the settlement; `flag_stuck_past_close` never voids /
never touches P&L / never flags a future-close position / safe on fetch-error +
missing/garbage close_time. One Low-1 (W/L/V invariant) fixed inline; added a
garbage-close_time test.

## Verification
- 102 targeted tests pass (6 new flag_stuck_past_close + garbage-close-time
  case). The 1 suite failure (`test_resolve_starting_bankroll_live_auto_uses_state_when_present`)
  is pre-existing and unrelated (fails without these changes).
- Real-data: v1 back-settle smoke -> -$0.74 on 5; `flag_stuck_past_close`
  flags **0** of v1's real 29 filled (24 future-close + 5 terminal), proving
  the close_time gate does not false-flag long-horizon positions.

## Operator notes for the v1 restart
- After restart, v1 realized goes 0.00 -> **-$0.74** (5 settled: wins + losses;
  24 positions remain legitimately OPEN, resolving over weeks/months). This is
  the meter turning on, not a new loss.
- No v1 kill should arm: -$0.74 on a ~$32 bankroll is ~2.3% drawdown (kill at
  20%); Trigger 1 needs 20 non-void fills (only 5 settled). The void-skip
  ensures the rare void doesn't false-trip the YES-rate trigger.
- The lost UFC order is now confirmed v1's; adopt it during the restart.
- Restart sequence (adopt requires the bot STOPPED, like v14): (1)
  `Stop-ScheduledTask KalshiLiveBot`; (2) verify stopped; (3)
  `PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.adopt_v1_orphan --i-mean-it`;
  (4) `Start-ScheduledTask KalshiLiveBot`. (Plain `.\scripts\restart_bot.ps1`
  works too if you skip the adoption.)
