# LIVE Mode Design: Strategy B (Deep-Favorite YES-Maker)

**Date:** 2026-05-23
**Status:** Design v2 (post-critic, pre-code)
**Subject of design:** Adding LIVE order execution to `scripts/paper_trade_favorite.py`
**Constraint:** Live capital cannot deploy until the LIVE_READINESS_DECISION.md
acceptance criteria (50+ paper fills, 3+ leagues, YES rate >= 90%,
mean realized >= +1pp, fill rate >= 40%) are met during paper trading
on the new WRITE-scope key. This design adds the wiring; activation
is a separate operator decision via `.env`.

## CRITIC-REQUIRED CHANGES APPLIED (Round 5 critic, 2026-05-23)

The full critic report at `research/critic-live-mode-design.md` raised
13 findings. All material changes are folded into the sections below.
Key tightenings the implementation MUST honor:

1. **Idempotency**: replace epoch_minute hashing with a persisted
   UUID4 per intended placement. Write to state.json BEFORE the
   first POST; reuse across all retries of that intent. Removes the
   minute-boundary race window. See Section 3 below.
2. **WSL clock skew**: added pre-flight check #1 (delta < 2000ms vs
   Kalshi response Date header). See Section 5.
3. **Acceptance criteria programmatically enforced**: pre-flight
   reads `data/paper_trades/state.json` and aborts if any of the 5
   acceptance metrics fails. Operator can override only with
   `LIVE_OVERRIDE_GATE=true` AND a loud Discord alert fires. See
   Section 5.
4. **6th kill trigger**: rolling-30 fills mean < 0.5pp trips,
   detecting edge compression without waiting for negative. See
   Section 6.
5. **Fill processing**: idempotent via `processed_fill_ids` set;
   on startup, reconcile from `last_reconciled_ts - 1h`. See
   Section 4.
6. **Stale filled reconcile**: each loop polls `GET /markets/{ticker}`
   for every ticker in `state.filled_orders`, NOT just scanner
   candidates. See Section 4.
7. **Sizing floor dropped**: at LIVE_PER_TRADE_USD=$0.50, the bot
   would compute 0 contracts and SKIP placement (with a log).
   `LIVE_PER_TRADE_USD` must be raised to >= 0.95 to actually trade
   1 contract. Forces operator to confront the real cost. See
   Section 4.
8. **Single drawdown gate**: fold `KILL_DRAWDOWN_PCT=0.20` into
   DrawdownThresholds as a new `kill` tier (above `halt`). Only one
   system. See Section 6.
9. **15-winner trigger armed at >=20 winners**: before that, fall
   back to fixed-dollar threshold (single_loss > $2.50 at default
   bankroll). See Section 6.
10. **SIGINT/SIGTERM handler**: best-effort cancel-all-resting on
    exit. Also write heartbeat file each loop iteration. See
    Section 4.
11. **Mock error codes enumerated**: tests must simulate
    INSUFFICIENT_FUNDS, MARKET_CLOSED, POST_ONLY_CROSS,
    FOK_INSUFFICIENT_VOLUME, 429, 401, network timeout, duplicate
    client_order_id. See Section 8.
12. **0.97-vs-0.95 inconsistency eliminated**: delete
    `expected_net_edge_for_favorite` from `paper_trade_favorite.py`;
    use `favorite_maker.expected_net_edge` as single source of
    truth. See Section 4.
13. **`--mode live-demo` added**: points at demo URL, exercises
    full POST/cancel/reconcile path against zero real capital.
    Skips balance and acceptance criteria checks (demo is play
    money). See Section 5.

What the critic flagged but I am DEFERRING (with rationale):

- **Scope verification probe via known-closed market**. v1 uses
  `GET /portfolio/balance` as auth-works check; a true WRITE probe
  needs a no-op POST that Kalshi doesn't fill, and I don't have a
  perfectly-safe candidate market in the eligible band. Documenting
  this as a known v1 gap. The operator told us they set up WRITE
  scope, and the first real POST will fail-fast if scope is wrong.
- **Fee-schedule sanity probe per market**. Sports special schedules
  vary. v1 trusts the standard maker formula and documents the gap.
  Add to follow-up if a sports market is observed with a non-standard
  fee.
- **Amendments on price drift**. Critic recommends NOT enabling in
  v1 (introduces fill-reconciliation race when added). v1 leaves
  resting orders at original price until cancelled by operator,
  filled, or expired. Acknowledged.

Now proceeding to the (revised) sections below.

## 1. Scope (what this design covers)

In scope:
- Adding `LiveOrderManager` (parallel to existing `PaperOrderManager`)
  that posts real Kalshi orders via `POST /portfolio/orders`,
  reconciles fills via `GET /portfolio/fills`, and settles via
  `GET /portfolio/positions` plus market resolution data.
- A `--mode {paper, live}` CLI flag on `scripts/paper_trade_favorite.py`.
  Default is `paper`; `live` requires explicit `LIVE_ENABLED=true` in
  `.env` AND `--mode live` AND a passed pre-flight checklist (see
  Section 5).
- A `KillTriggerMonitor` that enforces the LIVE_READINESS_DECISION.md
  kill triggers at runtime: 10-trade rolling mean negative for 2
  weeks, YES rate over 20 fills < 0.90, drawdown > 20%, single loss
  exceeds 15-winner P&L equivalent, fill rate < 0.30 over 50 attempts.
- A $0.50-per-trade live sizing default (vs $1 in paper). Per critic.
- Tests for everything above, no live-API calls in tests (mock client).

Out of scope:
- Deploying actual live capital. That is the operator's explicit
  `LIVE_ENABLED=true` flip + restart.
- WebSocket integration (REST polling is sufficient for our cadence).
- Multi-leg / partial-fill handling beyond what Kalshi natively returns.
- Order amendments (we cancel + repost on price drift rather than
  amend; simpler).

## 2. Kalshi API surface used

Per `research/briefs/agent-a-api-infra.md`:

**Place order**
- `POST /trade-api/v2/portfolio/orders`
- Body (JSON):
  ```json
  {
    "action": "buy",
    "side": "yes",
    "ticker": "KX...-...-T",
    "type": "limit",
    "count": 1,
    "yes_price": 75,
    "client_order_id": "<deterministic-hash>",
    "time_in_force": "fill_or_kill"  // we use "good_til_cancel" + post-only flag if supported
  }
  ```
- Returns: `{"order": {"order_id": "...", "status": "...", ...}}`
- Price is **integer cents** in this endpoint (older convention).
  Some endpoints use dollar strings since March 2026; the order
  endpoint accepted integer cents historically. We will probe at
  smoke-test time and fall back to string-dollars if integer-cents
  is rejected.

**Get my orders**
- `GET /trade-api/v2/portfolio/orders?status=resting&ticker=...`
- Pagination via cursor (existing `paginate()` works).

**Cancel order**
- `DELETE /trade-api/v2/portfolio/orders/{order_id}`

**Get my fills**
- `GET /trade-api/v2/portfolio/fills?ticker=...`

**Get my positions**
- `GET /trade-api/v2/portfolio/positions`

**Market resolution check** (for settlement)
- `GET /trade-api/v2/markets/{ticker}` returns `status`, `result`
  (`yes`, `no`, `void`) when settled.

## 3. State model

`LiveOrderManager` holds the same `PaperState`-shaped on-disk JSON,
but at a separate path: `data/live_trades/state.json`. Schema is
identical to PaperState; the only difference is the `OrderStatus`
values used (`LIVE_PENDING`, `LIVE_RESTING`, `LIVE_FILLED`,
`LIVE_CANCELLED`, `LIVE_VOIDED`, `LIVE_SETTLED`).

State transitions:

```
   place_live_order()
      |
      v
   LIVE_PENDING  (POST request in flight or accepted but not yet acked)
      |
      v
   LIVE_RESTING  (Kalshi acked, order id received, resting on book)
      |
      +----> LIVE_FILLED  (fill seen via /portfolio/fills OR returned in
      |                    POST response for FOK-style fills)
      |          |
      |          v
      |       LIVE_SETTLED (market resolved; realized P&L computed)
      |
      +----> LIVE_CANCELLED (we cancelled, or expired)
      |
      +----> LIVE_VOIDED   (market voided by Kalshi)
```

Each `LiveOrder` carries:
- `order_id` (Kalshi-issued, after acked)
- `client_order_id` (we issue, idempotency key)
- ticker, series_ticker, event_ticker
- side="yes", target_price (cents), contracts
- expected_net_edge, market_mid_at_placement
- placed_ts, acked_ts, filled_ts, settled_ts
- status (enum above)
- filled_price (cents), filled_count (may be < contracts on partial)
- resolution_outcome (1/0/-1 for void)
- realized_pnl_usd

Idempotency: `client_order_id = sha256(f"{ticker}|{side}|{target_price_cents}|{contracts}|{epoch_minute}").hexdigest()[:32]`.
Same minute + same ticker + same price = same id. Kalshi rejects
duplicates with a known error, which we treat as "already placed,
reconcile from /portfolio/orders" rather than an error.

## 4. The execution loop (per market)

Modified `one_loop_favorite` with a `mode` parameter:

```
For each candidate market that passes is_eligible(yes_bid):
  1. Compute expected_net_edge at yes_bid.
  2. If net_edge < min_net_edge: skip.
  3. Check no existing resting/filled order for this ticker.
  4. Compute size:
     - paper: contracts_per_fill (default 1)
     - live:  max(1, floor(LIVE_PER_TRADE_USD / yes_bid))
       (at yes_bid=0.70, $0.50 -> 1 contract; at yes_bid=0.50, would
        be 1; we never enter below 0.70 anyway. Effective: always 1
        contract per live order at this band and budget.)
  5. paper: PaperOrderManager.place_paper_order(...) (unchanged)
     live:  LiveOrderManager.place_live_order(...) which:
            a. Builds order body with client_order_id.
            b. POSTs /portfolio/orders.
            c. Stores record in LIVE_PENDING; on ack flips to
               LIVE_RESTING with Kalshi order_id.
            d. On ack failure: log + Discord alert + state stays
               PENDING for next-loop reconciliation.

  For each known live resting order:
    1. GET /portfolio/fills?ticker=... (paginated, recent).
    2. If a fill matches our client_order_id (or Kalshi order_id):
       transition LIVE_RESTING -> LIVE_FILLED, record filled_price
       and count.
    3. If a fill increases progress on an existing partial fill:
       update filled_count; if filled_count == contracts: mark
       LIVE_FILLED fully.

  For each known live filled order (not yet settled):
    1. GET /markets/{ticker}: if status == "settled", read result.
    2. Compute realized P&L (same formula as paper):
         payoff_per_contract = (1.0 if result == "yes" else 0.0)
                                  - filled_price
         fee = 2 * kalshi_maker_fee_per_contract(filled_price)
         realized_pnl = (payoff_per_contract - fee) * filled_count
       (Same conservative round-trip-fee approximation as paper.
       Real Kalshi settlement is fee-free so this UNDERSTATES P&L
       by one maker-fee per contract; matches the methodology lock.)
    3. Transition to LIVE_SETTLED.

Each iteration also:
  - Updates DrawdownMonitor.
  - Updates KillTriggerMonitor with new fills / settlements.
  - If any kill trigger trips: HALT (cancel all resting, refuse new
    placements, Discord alert).
```

## 5. Pre-flight checklist (live mode startup)

When `--mode live` is invoked, the script does NOT immediately start
trading. It runs a pre-flight checklist; ANY failure aborts:

1. `settings.LIVE_ENABLED is True` (in .env)
2. `settings.KALSHI_ENV == "prod"`
3. `settings.CAPITAL_CAP_USD <= 100` (operator-authorized ceiling)
4. `settings.LIVE_PER_TRADE_USD <= 1.00` (no surprises)
5. `client.ping()` returns trading_active=True
6. `GET /portfolio/balance` returns a value (auth works, scope is WRITE)
7. There is at least one previously-confirmed paper fill on the same
   strategy in the last 60 days (proof of operator competence). If
   the paper state has < 1 settled order, abort with the explicit
   message "no paper-trading evidence; run --mode paper first."
   This is a soft check, NOT the formal 50-fill acceptance criterion;
   that is enforced by the operator's review of the .env decision.
8. There is no orphan resting order in /portfolio/orders that we
   don't know about (we list resting orders; if any are unknown to
   our state, abort and surface them).
9. Operator interactive confirmation prompt:
   `Type 'I authorize live trading at $X.XX bankroll, $Y.YY/trade' to proceed:`
   (If the input doesn't match exactly, abort.)

After pre-flight, the loop starts. Discord alert: "LIVE TRADING
STARTED $X bankroll $Y/trade".

## 6. KillTriggerMonitor

State (persisted across restarts to `data/live_trades/kill_state.json`):
- `recent_pnl_per_trade: list[float]` (oldest first, capped at 100)
- `recent_outcomes: list[int]` (1=YES, 0=NO; capped at 100)
- `placement_attempts_total: int`
- `placement_filled_total: int`
- `single_winner_avg_pnl: float` (running mean for the 15-winner test)
- `tripped: bool`
- `trip_reason: str | None`
- `trip_ts: str | None`

Methods:
- `record_attempt()` increments `placement_attempts_total`.
- `record_fill(filled_count)` increments `placement_filled_total`.
- `record_settlement(realized_pnl, outcome)` updates rolling lists,
  updates `single_winner_avg_pnl` (if outcome==1, blend in).
- `check_triggers() -> KillReason | None` evaluates each rule:
  - **10-trade rolling mean for 2 consecutive weeks**: needs
    timestamps. Track per-week buckets; if last 2 ISO weeks both have
    rolling-10 mean negative, trip. Conservative impl: simpler is to
    track if the LAST 10 fills' mean < 0 for >= 14 days continuously
    (we record the ts of when mean first went negative; if 14 days
    elapse without recovery, trip).
  - **YES rate < 0.90 over last 20 fills**: if `len(recent_outcomes)
    >= 20 and mean(recent_outcomes[-20:]) < 0.90`: trip.
  - **Drawdown > 20%**: DrawdownMonitor already exposes this; we tap
    its state.
  - **Single loss > 15-winner P&L**: track the running mean of
    winning trades; if any settlement realizes a loss with
    `abs(loss) > 15 * winner_mean_pnl_per_contract`: trip.
  - **Fill rate < 0.30 over 50+ attempts**: if
    `placement_attempts_total >= 50 and (placement_filled_total /
    placement_attempts_total) < 0.30`: trip.

When tripped:
- Set `tripped=True`, write `trip_reason`, `trip_ts`.
- Cancel all resting orders.
- Discord alert with reason.
- Subsequent loop iterations: refuse new placements; only continue
  to reconcile existing fills / settlements until clean.
- Operator must manually clear `kill_state.json` (delete or set
  `tripped=False`) to resume.

## 7. Config additions (`src/kalshi_bot/config.py`)

```python
# LIVE mode safety
LIVE_ENABLED: bool = False
LIVE_PER_TRADE_USD: float = Field(default=0.50, gt=0.0, le=1.00)
LIVE_MAX_OPEN_POSITIONS: int = 5

# Kill triggers (from LIVE_READINESS_DECISION.md)
KILL_YES_RATE_MIN: float = 0.90
KILL_YES_RATE_WINDOW: int = 20
KILL_ROLLING_MEAN_WINDOW: int = 10
KILL_ROLLING_MEAN_DAYS_NEGATIVE: int = 14
KILL_DRAWDOWN_PCT: float = 0.20
KILL_LOSS_VS_WINNERS_RATIO: float = 15.0
KILL_FILL_RATE_MIN: float = 0.30
KILL_FILL_RATE_MIN_ATTEMPTS: int = 50
```

The `LIVE_ENABLED` default is `False`. Setting `True` requires editing
`.env` (which the operator has to do interactively).

## 8. Test coverage plan

New test files / additions:

`tests/test_live_order_manager.py` (new):
- `place_live_order` builds correct POST body (action="buy",
  side="yes", type="limit", count=N, yes_price=cents).
- Idempotency: same `client_order_id` for same (ticker, price, size,
  minute).
- `reconcile_live_fills`: GET fills, matches by client_order_id,
  transitions state.
- `settle_at_resolution` for live: same arithmetic as paper.
- Mock the Kalshi client; no real HTTP.

`tests/test_kill_triggers.py` (new):
- YES rate < 0.90 over 20 trips correctly; under 20 trades doesn't.
- Drawdown > 20% trips.
- Single loss > 15-winner avg trips.
- Fill rate < 0.30 after 50 attempts trips; before 50 doesn't.
- Rolling-mean negative for 14 days trips; recovery before 14 days
  doesn't.
- Tripped state: `allowed_to_place_orders()` is False.
- Trip state persists across instantiations (load from disk).

`tests/test_paper_trade_favorite.py` (extend):
- `--mode paper` is default and existing behavior unchanged.
- `--mode live` without `LIVE_ENABLED=True` aborts at pre-flight.
- `--mode live` with LIVE_ENABLED=True but no paper history aborts.

Total expected test delta: ~25 new tests. Final target: 240 + 25 =
265.

## 9. CLAUDE.md update sketch

Add a Round 5 entry:
"Round 5 (2026-05-23, operator-authorized): LIVE mode wired into
scripts/paper_trade_favorite.py. Defaults to PAPER; LIVE requires
.env LIVE_ENABLED=true + pre-flight checklist + interactive
confirmation. Kill triggers per LIVE_READINESS_DECISION.md enforced
at runtime. No live capital deployed by this change."

## 10. Risk acknowledgement

The critic in critic-favorite-maker.md called out fill-rate against
institutional MMs as "the load-bearing untested assumption." This
design does not solve that problem; it only INSTRUMENTS it. The
KillTriggerMonitor's fill-rate check enforces a 0.30 floor after 50
attempts as the empirical guard. If real fill rate is below 0.30,
the bot halts itself.

The 5pp-vs-1pp expected-edge gap also stands. If real net P&L per
fill is below +0.5pp, the bot continues trading (since +0.5pp is
positive) but the operator should watch the daily mean and make a
manual decision to stop if the realized number disappoints.

## 11. What this design EXPLICITLY does not do

1. Does NOT bypass paper-trading acceptance criteria. The operator
   must run paper, gather 50+ fills, and only then flip
   `LIVE_ENABLED=true` in .env. This design hard-codes
   `LIVE_ENABLED=False` as the safe default.
2. Does NOT raise `CAPITAL_CAP_USD` above $100. Per the existing
   pydantic constraint `le=100.0`.
3. Does NOT change the strategy math (favorite_maker.py is untouched).
4. Does NOT change paper-mode behavior. PaperOrderManager and the
   existing `--once` smoke test still work identically.
5. Does NOT auto-cancel orders on script exit. If the operator hits
   Ctrl-C, resting orders STAY resting. (Standard practice; bot
   restart reconciles them on next loop.) An optional `--cancel-all-
   on-exit` flag can be added but is not in this design.

## 12. Open questions for the critic

1. Is the deterministic `client_order_id` collision-resistant enough?
   What if the bot restarts within the same minute and tries to
   re-place an order that Kalshi already accepted?
2. Should LIVE state persistence be the same JSON file as paper, or
   different? (Design says different; reasoning: avoids accidental
   confusion + lets operator audit live separately.)
3. Should we cancel resting orders if their target_price drifts more
   than N cents away from current bid? (Not in design; orders just
   sit at original price. May lock us out of better prices.)
4. Should we batch-place multiple orders in one loop, or one-at-a-
   time with confirmation? (Design says one loop = up to slots_left
   placements, batched. Critic may flag this as too aggressive at
   startup.)
5. The 14-day rolling-mean-negative trip is hard to test deterministically
   (needs time-mocking). Should we use a simpler "10 of last 14
   bucketed days with negative mean" instead?
6. The single-loss-vs-15-winners trigger relies on a running mean
   of winners. Early in trading, with few winners, the threshold
   could be unstable. Should we require a minimum of 20 winners
   before this trigger arms?
