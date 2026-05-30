# v14 + v1 settlement-detection bugfix (2026-05-30)

**Trigger:** operator observed v14 exposure never releasing ("filled=10
closed=1 realized_pnl=+0.00") despite games resolving. Asked to verify
v14 was detecting order closure correctly.

## Root cause

`LiveOrderManager.reconcile_settlements()`
(`src/kalshi_bot/strategy/live_order_manager.py`) gated settlement on
`if status != "settled": continue`. The live Kalshi API returns
`status = "finalized"` for a resolved market, never `"settled"`. Verified
against prod (READ key) on 2026-05-30 UTC:

| Ticker | status | result | settlement_ts |
|---|---|---|---|
| KXMLBGAME-26MAY282005HOUTEX-TEX | `finalized` | no | 2026-05-29T03:03:06Z |
| KXMLBGAME-26MAY291840ATLCIN-CIN | `finalized` | no | 2026-05-30T01:29:10Z |
| KXMLBGAME-26MAY292040SFCOL-COL | `determined` (then `finalized`) | yes | 2026-05-30T03:58:00Z |
| KXMLBGAME-26MAY292210AZSEA-SEA | `active` (in play) | (none) | (none) |

Lifecycle is `active -> determined -> finalized`. `"settled"` does not
appear. Result: NO filled order ever settled.

## Blast radius

- **Both live bots affected.** v1 (`scripts/paper_trade_favorite.py:773`)
  and v14 (`src/kalshi_bot_v14/daemon.py:597`) call the same method.
  Neither had ever recorded a settlement: both showed
  `realized_pnl_total_usd = 0.0`. v1's 146 "closed" orders were all
  cancellations, never settlements.
- **Exposure frozen.** `compute_v14_exposure()` sums `filled`; orders never
  left `filled`, so v14's self-measured exposure stuck at $16.79 and
  headroom never recovered as positions actually resolved on Kalshi.
- **Both kill triggers silently disabled.** The 20%-of-cap drawdown kill
  reads `realized_pnl_total_usd` (stuck at 0); the 5-consecutive-loss kill
  scans `state.closed` for negative realized P&L (settlements never landed
  there). v14 went 6 losses of 8 on 2026-05-29 with neither net armed.
- **Self-inconsistency:** the project's research code already knew the
  value: `scripts/v6/build_v6_master.py:106`,
  `scripts/v15/thread_a_wta_friday.py:57`,
  `scripts/v11_tmp/audit_game_resolution.py:51` all filter
  `status == 'finalized'`. Only the live-trading path used `"settled"`.
- **Tests masked it:** `tests/test_live_order_manager.py` mocked
  `{"status": "settled"}`, so the suite was green while live failed.
  Textbook session-rule-6 (mocks necessary, not sufficient).

## Fix

`reconcile_settlements()`:
1. Settle when `status in ("finalized", "settled")` (`"settled"` kept
   defensively). `"determined"` and all pre-resolution states wait for a
   later loop (finalizes within ~120s).
2. On a terminal status, yes -> win, no -> loss, and ANY other result
   (explicit `"void"`, a non-binary token like `"scalar"`, or empty) ->
   void (refund-to-entry, fees only) with a `log.warning`. A terminal
   market is NEVER left in `filled`, so capital always releases. (This was
   the post-review correction; see below.)
3. `resolution_ts` now prefers `settlement_ts` (the field the live API
   actually returns) over `settled_time`.

v14 `check_kill_triggers()`: voids (`resolution_outcome == -1`) are
transparent to the consecutive-loss streak (a rained-out game is not a
strategy loss and does not reset a real run).

## Review (general-purpose agent)

One HIGH: the first draft used `else: continue` for unrecognized results,
which re-stranded finalized-but-non-binary markets forever (the exact bug
being fixed). Corrected to settle-as-void on terminal status. Adopted the
reviewer's M2 (`.strip()` on result) and M4 (voids excluded from loss
streak). Deferred (follow-ups, not blocking): M1 age-based forced
settlement for a market stuck in `determined`/void-without-finalized; M3
Discord burst + O(n^2) winners/losers recompute on the first back-settle
loop (best-effort webhook, swallows errors; cosmetic).

## Verification

- `tests/test_live_order_manager.py` 31/31 pass; rewritten to the real
  `finalized` + `settlement_ts` shape, plus `determined`-waits and
  terminal-unrecognized-result-voids cases. Kill-trigger + v14-sizing +
  adverse-selection suites pass (71/71 in that batch). Full suite
  483 pass, 1 pre-existing unrelated failure
  (`test_resolve_starting_bankroll_live_auto_uses_state_when_present`,
  confirmed failing on `main` without this change), 1 collection error in
  `tests/v2` (lightgbm not installed in the kronos venv).
- Real-data smoke (`scripts/v14/smoke_settlement_fix.py`, read-only,
  isolated temp state copy): back-settles 9 of 10 v14 filled orders
  against the live API; AZSEA still `active` stays open. Net realized
  **-$3.13** (6 losses, 3 wins incl. SFCOL +$3.30). Live state file
  untouched.

## Operator consequence on deploy

After restart, the next loop back-settles all finalized positions and
`realized_pnl_total_usd` jumps to its true value (about -$3.13 with AZSEA
still live as of this writing). The kill triggers then evaluate against
reality:
- Drawdown kill threshold is -20% of v14 cap (cap ~$18.72 -> ~-$3.74).
  Current -$3.13 is just inside it; if AZSEA loses, the kill likely arms.
- This is the safety net working as designed; it was masked before.

## Deploy steps (operator-initiated; bots NOT restarted by this change)

Code change only; takes effect on restart of each bot.
- v14: `Stop-ScheduledTask KalshiV14Bot; Start-ScheduledTask KalshiV14Bot`
- v1: `.\scripts\restart_bot.ps1`
