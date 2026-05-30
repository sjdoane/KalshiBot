# v14 settlement follow-ups: stuck-escape, Discord batch, orphan adoption (2026-05-30)

Follow-up to `06-settlement-status-bugfix.md`. After the finalized-vs-settled
fix, the operator asked to "do all the fixes and verify them with council."
Three remaining items were designed via a 4-member council + verifier, then
implemented, reviewed, and tested.

## Council + verifier (per session rule 1)

4 members (Realist, Builder, Risk, Operator-experience) + Verifier deliberated
three decisions. Verdict (binding, verifier-synthesized):

- **A (orphan adoption) = A1 one-shot script**, NOT a general startup
  self-heal. Root cause (multi-daemon race) is already locked out by the
  single-instance lock, so permanent auto-adopt machinery would be a standing
  foot-gun (it could absorb a non-v14 order). Adopt into `filled` only; let
  `reconcile_settlements` be the single P&L writer; dry-run + operator approve.
- **B (stuck position) = B3 + B2**: consult `/portfolio/positions`; settle
  locally ONLY when `position_fp == 0` (Kalshi-confirmed flat); a missing key
  is UNKNOWN, never flat; otherwise leave in `filled` and alert once. B1
  (auto-void-on-a-timer) rejected unanimously as a phantom-exit foot-gun.
- **C (Discord burst) = C1**: one batched summary per settle pass.

**Verifier caught two member errors:**
1. The Risk member's "v14 fee model understates fees 4x (taker vs maker)" is
   WRONG. A held-to-settlement position pays only the ENTRY fee (no exit
   trade). The bot's `2 * maker_fee` equals the single taker fee at v14's mid
   prices (verified against `/portfolio/fills` `fee_cost`: HOUTEX 1c@58c gives
   -$0.60 on both the bot path and Kalshi's real path). Fee model is fine and
   slightly conservative; OUT OF SCOPE.
2. The Builder's "A2 reusable for v1" is overstated; v1 has its own reconcile
   scripts. A1 chosen.

## Implemented

1. **`LiveOrderManager.reconcile_stuck_positions(stuck_age_hours=24)`**: for a
   filled order older than the threshold (its market never finalized), poll
   `/portfolio/positions` once. Flat (ticker present, `position_fp == 0`) ->
   void-settle via the bot's own `_compute_realized_pnl(order, -1)` (single
   P&L writer), release capital. Still-held or ticker-absent -> leave + flag
   once via new `LiveOrder.stuck_alert_ts`. Wired into the v14 daemon with
   `V14_STUCK_AGE_HOURS` (default 24) and one-time Discord alerts.
2. **Batched settlement Discord** (daemon): one message per settle pass;
   single settlement keeps the familiar format; W/L/V tallied with voids
   separated so W + L + V == count (post-review fix; voids are not losses).
   Per-order detail stays in the jsonl log.
3. **`scripts/v14/adopt_v14_orphans.py`**: dry-run-first one-shot that adopts
   the 4 orphan orders (from the 2026-05-29 multi-daemon clobber) into
   `state.filled`. Guards: prefix "14" AND ticker `KXMLBGAME-` (series guard)
   AND not in v14 state AND not in v1 state (cross-bot dedup). Rejects
   non-physical prices (1..99c). Seeds `processed_fill_ids`. Prints a kill
   projection before writing.

## Real-data catch (why rule 6 matters)

The first dry-run flagged 5 orphans; one was `KXNBAPLAYOFFWINS-26OKC-11`, an
NBA market with client_order_id `14ea6db7...`. That is a PRE-tagging-era v1
order whose raw uuid happens to start with "14", and it is tracked in v1's
filled pool. A naive prefix filter would have stolen a live v1 position into
v14. The series guard + v1 cross-dedup now exclude it; dry-run shows exactly
the 4 real MLB orphans. Mocked tests would never have surfaced this.

## Review (post-implementation, general-purpose agent)

1 High + 2 Medium addressed inline:
- H1: the all-time Discord tally counted voids as losers and W+L != total.
  Fixed: separate V bucket, W/L exclude voids (now consistent with the kill
  streak).
- M1: a 0-cent / missing-price adopted fill would book a phantom +$1 win.
  Fixed: `reconstruct_filled_order` raises on a non-1..99c price; main skips.
- Balance read in the projection aligned to the daemon's `portfolio_balance`
  fallback.
- M3 (true-void fee): the void path charges `2 * maker_fee`, matching the
  existing system-wide convention in `reconcile_settlements`. If Kalshi
  refunds all fees on a true void, both paths should switch to `0.0`; flagged
  for an operator decision, NOT changed unilaterally.
Reviewer confirmed: no double-count, no stranded capital, no v1-into-v14
adoption, no wrong kill. Safety guards (missing-key-not-flat, single P&L
writer, void-transparent streak, idempotent prefix-guarded adoption) verified.

## Tests + verification

- 79 targeted tests pass (live-order-manager incl. 5 new stuck-position cases
  + adopt-helper unit/units/rejection + kill-triggers + v14-sizing +
  adverse-selection). Broader suite: 489 pass; 2 pre-existing unrelated fails
  (`test_resolve_starting_bankroll_live_auto_uses_state_when_present`, and the
  flaky `test_filter_candidates_max_lifetime_boundary` which calls
  `pd.Timestamp.now()` twice across a 180-day boundary; both fail without this
  change and touch nothing here).
- Real-data dry-run: adopts exactly the 4 MLB orphans, projects realized
  ~-$5.17 after restart and DRAWDOWN KILL WILL TRIP = YES.
- Settlement smoke (`scripts/v14/smoke_settlement_fix.py`) unchanged: 9/10
  tracked back-settle, live state untouched.

## Deploy + restart sequence (operator-run; bots NOT restarted here)

The orphan adoption MUST run with the v14 bot STOPPED (concurrent-writer
race). The drawdown kill WILL arm after restart (true P&L ~-$5.17 vs the
~-$3.84 threshold); that is the safety net working, not a fault. See restart
steps in the session handoff / OPERATOR_RUNBOOK.
