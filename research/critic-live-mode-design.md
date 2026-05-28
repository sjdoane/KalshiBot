# Adversarial Critic: LIVE Mode Design for Strategy B

**Date:** 2026-05-23
**Reviewer:** Adversarial-critic context (Round 4-equivalent, applied to execution design)
**Subject:** [live-mode-design.md](live-mode-design.md), to be implemented on top of [scripts/paper_trade_favorite.py](../scripts/paper_trade_favorite.py) and [src/kalshi_bot/strategy/order_manager.py](../src/kalshi_bot/strategy/order_manager.py)
**Mandate:** Stress-test mechanical correctness and operational safety before code is written. Operator has $32 of real capital and a $100 ceiling.

## Executive summary

**Verdict: PROCEED WITH CHANGES.** The design is roughly the right shape: a separate LiveOrderManager, deterministic client_order_id, explicit pre-flight, runtime kill triggers, $0.50 sizing. But there are seven specific defects I would not let into a live-capital path unfixed. The single most important: **the idempotency key uses an `epoch_minute` window that collides with retry semantics in a destructive way**. If the bot POSTs at second 59 of minute T, the network drops, the bot retries at second 01 of minute T+1, the client_order_id changes, Kalshi accepts both, and the operator is suddenly long 2 contracts instead of 1. At $0.50/contract this is a $0.95 mistake per occurrence, not catastrophic, but it falsifies the "idempotency makes retries safe" assumption that the entire design hangs off. Fix the time window or replace it with a persisted UUID per intended placement.

Secondary load-bearing issues: the pre-flight does not check WSL clock skew despite agent-c-risk.md flagging it explicitly; the kill-triggers are calibrated to the gate-headline 5pp not the Bürgi-realistic 1-3pp; and there is no dead-man timer for the operator-Ctrl-C-then-walks-away case.

## 1. Idempotency key has a one-minute race window

The design at [live-mode-design.md:123](live-mode-design.md) defines:

```
client_order_id = sha256(f"{ticker}|{side}|{target_price_cents}|{contracts}|{epoch_minute}").hexdigest()[:32]
```

This is broken in two distinct ways.

**Failure mode A: minute-boundary retry.** Bot POSTs at T = 14:32:59 UTC. TCP RST or 502 from Kalshi mid-response. Bot retry logic fires at T = 14:33:01. The two POSTs carry DIFFERENT client_order_ids (epoch_minute differs by 1). If Kalshi accepted the first POST silently (the response was lost in transit, not the request), the second POST is a NEW order from Kalshi's perspective. Both rest. Both fill. The operator is long 2 contracts on a ticker the design says holds 1 max. This is the canonical "lost ack" problem agent-c-risk.md Section 3 names by example.

**Failure mode B: same-minute legitimate re-entry.** The strategy intentionally cancels and re-places on price drift (Section 11 disclaims this is "not done" but the operator will want it eventually). At yes_bid = 0.71, we place. Price drifts to 0.73. We cancel + re-place inside the same minute. Same ticker, same side, same contracts, same target_price... if target_price happens to round to the same cents (0.73 ~ 73c), same client_order_id. Kalshi rejects as duplicate. The "rejection means already-placed, reconcile" fallback the design assumes ([live-mode-design.md:126-127](live-mode-design.md)) will then mis-attribute the rejected new order to the cancelled old one.

**Fix.** Use a persisted-on-disk UUID per intended-placement, written to state.json BEFORE the POST attempt, and reused across all retries of that exact intent. Pseudocode:

```python
intent_id = uuid4().hex
state.pending_intents[intent_id] = PlacementIntent(...)
state.save()  # crash-safe
client_order_id = intent_id[:32]
post_with_retries(client_order_id, ...)
```

The `epoch_minute` field is not buying anything you couldn't get from a UUID, and it loses the load-bearing property "the SAME intent retries safely."

## 2. Pre-flight checklist is missing the WSL clock check

[live-mode-design.md:181-202](live-mode-design.md) lists 9 pre-flight checks. WSL2 clock-skew is NOT one of them. [agent-c-risk.md:45](briefs/agent-c-risk.md) explicitly calls this out: "WSL2 has a well-documented drift problem after sleep/resume. Signed requests with timestamps off by more than a few seconds are rejected." CLAUDE.md line 240-242 confirms the operator runs WSL2 and the check "is documented but not yet implemented."

This is not a paranoid checkbox. Kalshi's RSA-PSS signing uses millisecond timestamps ([agent-a-api-infra.md:25-31](briefs/agent-a-api-infra.md)). A 2+ second drift after suspend/resume will make every POST fail with a signature-validation error. The bot's retry loop will hammer the API until rate-limited. Discord alert says "POST failed" but the operator thinks the bug is in the order code.

**Fix.** Add as check #1 (before LIVE_ENABLED): `delta = abs(local_unix_ms - ntp_unix_ms); assert delta < 2000`. Use `pool.ntp.org` or hit Kalshi's `/exchange/status` and read its `Date` response header for the comparison.

Also missing from pre-flight, per the brief in the task mandate:

- **Scope verification.** The key must be WRITE scope. The design's check #6 ("GET /portfolio/balance returns a value") tests authentication but NOT that the key has write permission. A READ-scope key passes #6 and fails on the first POST. Add a low-cost write-scope probe: place a $0.01 GTC limit ON A KNOWN-CLOSED MARKET (rejected by Kalshi for the right reason: closed market, not auth). Inspect the error code to distinguish "auth failure" from "scope failure" from "market closed."
- **Balance covers 2x worst-case-single-loss.** With $0.50/contract at 0.95 cap, worst single loss is $0.95. 2x = $1.90. The design doesn't enforce a balance floor; only the `CAPITAL_CAP_USD` constraint. If balance is $0.30, the first 5-concurrent attempt will fail with `INSUFFICIENT_FUNDS` and the bot won't know whether prior placements partially succeeded. Add: `assert balance >= 2 * LIVE_PER_TRADE_USD * MAX_OPEN_POSITIONS`. At default that's $5; trivially passes for the $32 operator, refuses startup at $1 dust.
- **Fee schedule sanity probe.** [agent-a-api-infra.md:60-61](briefs/agent-a-api-infra.md) warns "Special-event markets (elections, major sports) can have bespoke higher fee schedules, published per-market." Hit `/markets/{known_sports_ticker}` and verify the `fee_schedule` field (if present) matches our assumed 25%-of-taker maker fee. If a sports series quietly adopted a special schedule, our `expected_net_edge` math is wrong before the bot ever places.

## 3. State coupling between paper and live is asserted in prose, not code

The design at [live-mode-design.md:82-87](live-mode-design.md) places live state at `data/live_trades/state.json` separately from paper. Pre-flight check #7 requires "at least one previously-confirmed paper fill on the same strategy in the last 60 days." This is a checkbox, not a gate.

The LIVE_READINESS_DECISION.md acceptance criteria (50+ fills, 3+ leagues, YES rate >= 90%, mean realized >= +1pp, fill rate >= 40%) are enforced... where? By the operator's eyeball review when flipping `LIVE_ENABLED=true`. There is no programmatic enforcement.

This matters because the operator is sleep-deprived, working alone, has $32 of real money on the line, and might convince himself "close enough" on the 1pp criterion at 0.7pp realized. The kill-early principle from the operator's own memory file says the opposite: do not ship something that almost passes.

**Fix.** Pre-flight should programmatically compute the 5 acceptance metrics from `data/paper_trades/state.json` and abort if ANY fails. Specifically:

```python
paper = PaperOrderManager()
settled = list(paper.state.closed_orders.values())
assert len(settled) >= 50, f"need 50+ paper settled, have {len(settled)}"
leagues = {derive_league(o.series_ticker) for o in settled}
assert len(leagues) >= 3, f"need 3+ leagues, have {leagues}"
yes_rate = mean(o.resolution_outcome == 1 for o in settled)
assert yes_rate >= 0.90, f"YES rate {yes_rate:.3f} < 0.90"
mean_pnl_pp = mean(o.realized_pnl_usd / o.contracts for o in settled) * 100
assert mean_pnl_pp >= 1.0, f"mean realized {mean_pnl_pp:.2f}pp < 1.0pp"
# fill rate requires recording attempts; not currently in PaperState (gap)
```

If the operator wants to override, that override should be a separate explicit flag (`LIVE_OVERRIDE_GATE=true`) that fires a loud Discord alert. Otherwise this is just trust.

Also note: paper-state schema does NOT currently record attempt count, so the fill-rate criterion cannot even be computed retroactively. This is a paper-mode design gap that should be fixed BEFORE the live design depends on it.

## 4. Kill triggers are calibrated to the gate headline, not the realistic edge

[live-mode-design.md:228-240](live-mode-design.md) implements 5 kill triggers from LIVE_READINESS_DECISION.md lines 124-134. The trigger thresholds are:

- 10-trade rolling mean negative for 2 weeks
- YES rate < 0.90 over 20 fills
- Drawdown > 20%
- Single loss > 15-winner P&L
- Fill rate < 0.30 over 50 attempts

The Round 4 critic ([critic-favorite-maker.md:67](critic-favorite-maker.md)) said the realistic forward-looking net edge is "+1 to +3pp, with headline +5pp being lucky." Now consider: if realized mean drops to +0.2pp per trade (real, just at the low end of the Bürgi range), the rolling mean is positive. None of the 5 kill triggers fire. The bot keeps trading at effectively zero edge, paying fees per round trip, slowly bleeding.

This is the "ship-then-fail" failure mode the operator's memory file `feedback_kill_early.md` explicitly rejects.

**Fix.** Add a 6th trigger: **rolling mean below half of expected**. Pseudocode:

```python
EXPECTED_REALIZED_PNL_PP_LOW = 1.0   # bottom of Burgi range
HALF_OF_EXPECTED = 0.5
# After 30 fills:
if len(recent_pnl_per_trade) >= 30:
    rolling_30_mean_pp = mean(recent_pnl_per_trade[-30:]) * 100
    if rolling_30_mean_pp < HALF_OF_EXPECTED:
        trip("rolling 30-fill mean below 0.5pp; edge has compressed")
```

A 30-fill window is enough to distinguish 0.2pp from 1.0pp with reasonable signal-to-noise. Use 30 not 10 because the per-trade SD on the FULL corpus is 17.88pp ([critic-favorite-maker.md:32](critic-favorite-maker.md)), so rolling-10 standard error is 5.65pp, way too noisy.

## 5. Fill reconciliation has a between-poll race

[live-mode-design.md:152-160](live-mode-design.md) reconciles fills via `GET /portfolio/fills` once per loop (every 900 seconds default). Between two polls, this sequence is possible:

```
T+0:    bot polls, sees order RESTING, no fill yet.
T+5:    Kalshi fills our order (partial: 1 of 1, full).
T+10:   price moves; bot's NEXT loop would cancel+repost (if amendment
        logic existed; let's say operator added it).
T+11:   bot cancels; cancel-ack arrives.
T+12:   bot re-POSTs at new price.
T+900:  bot polls fills, sees the OLD fill, transitions to FILLED.
        Bot also sees the NEW order resting (or filled). Now bot is long
        2 contracts on this ticker but state thinks it's 1.
```

The design's intra-loop ordering ([live-mode-design.md:148-160](live-mode-design.md)) reconciles fills BEFORE placing new orders, which mitigates this if it's a single-loop event. But the cancel-and-repost on price drift is NOT in the design (operator's question #3), so when it's added, this race is born.

Even without amendments, the same race exists for the auto-cancel-on-exit case: bot exits at T+5 (Ctrl-C), order fills at T+30, operator restarts at T+3600. Bot has no record of the fill until reconciliation, which is bounded by the 15-minute cadence. For 14 minutes the bot's state lies.

**Fix.** Two things:
- Idempotent fill processing. Track a set of `processed_fill_ids` in state; skip fills already seen. The Kalshi fill object has a unique `trade_id`. Without this, restart-after-fill could attribute the same fill TWICE (paper code has this bug latent at [order_manager.py:182-206](../src/kalshi_bot/strategy/order_manager.py) because it iterates trades each loop with no dedup; the live design inherits the pattern).
- On the FIRST loop after startup, do a full `GET /portfolio/fills` paginated from `min_ts = state.last_reconciled_ts - 1h`, NOT just "recent." The 1h overlap covers crash-during-reconcile.

## 6. Settlement-pending orders rot forever after restart

[live-mode-design.md:161-171](live-mode-design.md) settles by polling `GET /markets/{ticker}` for status == "settled". This is fine while the bot is RUNNING and visits each market in `candidates` each loop. But the candidate set comes from the scanner, and the scanner ([paper_trade_favorite.py:170-175](../scripts/paper_trade_favorite.py)) filters to OPEN markets in the eligible band. **Markets that have closed but not yet settled are no longer in the scanner output.**

Kalshi settlement can take "a few hours" up to "extends to a later date defined in the market rules" per [agent-a-api-infra.md:104-107](briefs/agent-a-api-infra.md). If the bot is restarted at 11pm and the market settles at 3am while a candidate sweep at 3:15am does not include the now-closed-and-settled ticker, the LIVE_FILLED record sits forever.

**Fix.** Add a "stale filled" reconcile pass each loop that explicitly polls `GET /markets/{ticker}` for EVERY ticker in `state.filled_orders` regardless of whether it appears in candidates. Cost: at 5 max concurrent positions, 5 extra GETs per loop = trivial against the 200-token/sec read budget ([agent-a-api-infra.md:43-46](briefs/agent-a-api-infra.md) Basic tier).

Same fix should be applied to paper mode for symmetry, but that's out of scope for THIS design; flag it as a follow-up.

## 7. $0.50 sizing math: confirm the operator intends "always 1 contract"

[live-mode-design.md:139-142](live-mode-design.md) computes live size as:

```python
max(1, floor(LIVE_PER_TRADE_USD / yes_bid))
```

At yes_bid=0.70: floor(0.50/0.70) = floor(0.71) = 0. max(1, 0) = 1.
At yes_bid=0.95: floor(0.50/0.95) = floor(0.52) = 0. max(1, 0) = 1.

So live mode is "always exactly 1 contract" across the entire eligible band. Cost ranges from $0.70 to $0.95. The `max(1, ...)` clamp means the $0.50 budget number is fiction; actual capital at risk per trade is up to $0.95, almost 2x the named budget. 5 concurrent positions = up to $4.75 at risk vs the named $2.50.

This is not catastrophic given the $32 bankroll, but it's a documentation/naming defect. Two reasonable fixes:

- **Option A:** Rename `LIVE_PER_TRADE_USD` to `LIVE_MAX_PRICE_PER_CONTRACT_USD` and assert `LIVE_MAX_PRICE_PER_CONTRACT_USD >= FAVORITE_UPPER_CAP * contracts_per_fill`. So $0.95 minimum at 1 contract. Eliminates the naming mismatch.
- **Option B:** Keep the name but DROP the `max(1, ...)` floor. At yes_bid > 0.50, you'd compute 0 contracts and skip the placement. Then to actually trade, the operator must raise `LIVE_PER_TRADE_USD` to >= the worst-case price. Forces the operator to confront the cost. **Recommended.** It also makes scaling more honest later: at $2/trade, you get 2 contracts at 0.95 = $1.90, 2 at 0.70 = $1.40, naturally price-weighted.

The current design has a third risk: the floor masks a bug. If `LIVE_PER_TRADE_USD` is accidentally set to 0.05 (typo), `max(1, floor(0.05/0.70)) = 1`, still trades. The guard `LIVE_PER_TRADE_USD <= 1.00` ([live-mode-design.md:255](live-mode-design.md)) catches the upside; nothing catches the downside.

## 8. Two drawdown systems checking the same thing

[drawdown.py:55-61](../src/kalshi_bot/risk/drawdown.py) sets `halt = 0.25`. The new design adds `KILL_DRAWDOWN_PCT = 0.20` ([live-mode-design.md:262](live-mode-design.md)). At 20% drawdown, KillTriggerMonitor trips. At 25%, DrawdownMonitor HALTs.

Both are checked per loop. Both write to state. Operator now must reset TWO state files to resume.

It's also unclear which one "wins" on the order-permission gate. Both `dd.allowed_to_place_orders()` ([drawdown.py:123-124](../src/kalshi_bot/risk/drawdown.py)) and KillTriggerMonitor's `allowed_to_place_orders()` are presumably ANDed. So the order is "first to trip wins" but the OPERATOR sees a Discord alert from one and may not realize the other also tripped.

**Fix.** Either route the 20% threshold INTO the DrawdownMonitor (add a `kill` tier above `halt`, or shift `halt` to 0.20 for live mode only), or document that KillTriggerMonitor is authoritative and DrawdownMonitor is informational in live mode. Pick one. Two systems = double the resume complexity for the operator.

## 9. The 15-winner trigger is unstable early

[live-mode-design.md:233-235](live-mode-design.md) implements the single-loss-vs-15-winners check. After 1 winner of +5pp = $0.05, the threshold is 15 * 0.05 = $0.75. A single $0.95 loss (95c contract resolves NO) trips this immediately. After 2 winners averaging +3pp = $0.03 average, threshold is $0.45 and STILL trips on any 70-95c NO resolution.

This trigger is mathematically guaranteed to fire on the first loss until ~20 winners accumulate to stabilize the average. Operator's question #6 explicitly raises this.

**Fix.** Arm this trigger ONLY when `len(winners) >= 20`. Before that, fall back to a fixed-dollar single-loss threshold (e.g., `single_loss > 0.10 * starting_bankroll = $2.50` at $25 bankroll). This catches a runaway-bug single fill while not auto-tripping on the first natural NO.

## 10. No dead-man timer; orphan-resting-order check is one-shot

[live-mode-design.md:198-199](live-mode-design.md) pre-flight check #8: "There is no orphan resting order in /portfolio/orders that we don't know about." This is checked AT STARTUP only.

[live-mode-design.md:339-342](live-mode-design.md) Section 11 #5 explicitly says: "Does NOT auto-cancel orders on script exit. If the operator hits Ctrl-C, resting orders STAY resting. (Standard practice; bot restart reconciles them on next loop.)"

Combine these. Operator hits Ctrl-C at T=0. Order rests. Operator forgets. Goes to class. Comes back at T+8h. Market has filled at T+30min, resolved at T+6h, and the operator's bankroll changed without the bot knowing. The bot restart reconciles eventually, but in between, OTHER markets might have been candidates the bot could have traded; or the price might have crashed and the operator's exposure widened beyond the design's intent.

[agent-c-risk.md:83](briefs/agent-c-risk.md) explicitly prescribes: "Heartbeat dead-man timer: bot writes timestamp to file every 30s; a separate watchdog (cron / systemd) flattens if file is stale > 5 min."

**Fix.** Add a heartbeat file write each loop iteration. Add an OPTIONAL `--cancel-all-on-exit` flag (default OFF for now per Section 11, but available). MORE importantly: add a SIGTERM handler that cancels resting orders before exit. Operator Ctrl-C generates SIGINT, which Python normally raises as KeyboardInterrupt; catch it at the top of `main()`, attempt cancel-all, then exit. The risk is partial cancellation; document the failure mode in the runbook.

## 11. Mocked test client must enumerate Kalshi error codes

[live-mode-design.md:275-296](live-mode-design.md) test plan: "Mock the Kalshi client; no real HTTP." This is fine in principle but the mock is only useful if it returns the SAME error shapes Kalshi actually returns. The design doesn't enumerate which errors. At minimum the mock should be tested against:

- `INSUFFICIENT_FUNDS` (balance too low)
- `MARKET_CLOSED` (eligible-band market closed between scan and POST)
- `POST_ONLY_CROSS` ([agent-a-api-infra.md:113](briefs/agent-a-api-infra.md): "FOK_INSUFFICIENT_VOLUME and POST_ONLY_CROSS, so post-only and FOK appear supported but documentation is thin")
- `FOK_INSUFFICIENT_VOLUME` (if the design later uses FOK)
- HTTP 429 ([agent-a-api-infra.md:51-52](briefs/agent-a-api-infra.md): "No Retry-After or X-RateLimit-* headers")
- HTTP 401/403 (key revoked mid-session, OR scope mismatch surfaces on actual POST not on `/portfolio/balance` ping)
- Network timeout (TCP RST, slow read, connection refused)
- Duplicate `client_order_id` (the idempotency happy path)

For each, the test should assert the bot's RESPONSE: state transition, Discord alert, retry count, eventual halt. Without enumerating these, "no live-API calls in tests" gives false confidence.

## 12. The 0.97-vs-0.95 inconsistency makes the bot oscillate

[paper_trade_favorite.py:48-49](../scripts/paper_trade_favorite.py) hard-codes `empirical_yes_rate=0.97` in `expected_net_edge_for_favorite`. [favorite_maker.py:49](../src/kalshi_bot/strategy/favorite_maker.py) was updated to `EMPIRICAL_YES_RATE_DEFAULT=0.95` per the prior critic. **Both functions are called from the same script.** Which one does live mode use?

`one_loop_favorite` ([paper_trade_favorite.py:115](../scripts/paper_trade_favorite.py)) calls `expected_net_edge_for_favorite` (the 0.97 version). It does NOT call `favorite_maker.expected_net_edge`. So today, the paper bot is computing `net_edge` with the OLD rate (0.97), even though the critic-tightened module-level default is 0.95.

At yes_bid = 0.85, the difference is:
- 0.97 gross: 0.97 - 0.85 = 0.12. Net (after fees and slippage): ~0.10. PASSES min_net_edge=0.02 easily.
- 0.95 gross: 0.95 - 0.85 = 0.10. Net: ~0.08. STILL passes.

At yes_bid = 0.93:
- 0.97 gross: 0.04. Net: ~0.02. AT THE THRESHOLD.
- 0.95 gross: 0.02. Net: ~0.00. SKIPS.

So the inconsistency materially affects placement decisions in the 0.90-0.95 sub-band. For 1 contract at $0.93 with the 0.97-rate filter, we place; with 0.95, we don't. The $0.50 sizing question is irrelevant; the placement decision is what matters.

**Fix.** Delete `expected_net_edge_for_favorite` from `paper_trade_favorite.py` entirely. Import and use `favorite_maker.expected_net_edge`. Single source of truth. Same import in the new LiveOrderManager.

## 13. Demo environment is the right next step, not prod-direct

The design assumes `KALSHI_ENV=prod` ([live-mode-design.md:187](live-mode-design.md)). [agent-a-api-infra.md:185-191](briefs/agent-a-api-infra.md) notes demo "has no real counterparty liquidity for fills... you cannot trust execution quality measurements from demo as predictive of production slippage."

True, but that's not the only reason to use demo. The first time live code runs against a real exchange, you want to find the auth bugs, the JSON-shape bugs, the rate-limit bugs WITHOUT real money exposure. Demo is the right venue for that even if fill quality is unrealistic.

**Recommendation.** Add a `--mode live-demo` variant that points at `external-api.demo.kalshi.co`, exercises the FULL POST/cancel/reconcile path, but against zero real capital. Pre-flight changes: skip the "balance covers 2x worst-case" check (demo balance is play money) but still enforce auth-works and clock-skew. Operator runs `live-demo` for ~20 placements to flush integration bugs, THEN flips to `prod`.

This is the cheapest possible derisking step. Doesn't require operator action beyond a separate demo API key.

## Recommended Changes Before Code

- **Replace `epoch_minute` idempotency with persisted UUID.** Write the intent to state.json before the first POST attempt; reuse the UUID across all retries of that intent.
- **Add WSL clock-skew check to pre-flight** (compare local time vs NTP, abort if delta > 2s). Re-check on any wake/sleep boundary if detectable.
- **Add scope verification probe** (low-cost POST to a closed market, inspect error code to confirm WRITE scope before trading).
- **Add balance floor check** (`balance >= 2 * worst_case_loss_per_position * MAX_OPEN_POSITIONS`).
- **Add fee-schedule sanity probe** against one known sports market; verify it matches our assumed maker formula.
- **Programmatically enforce the 5 acceptance criteria** from LIVE_READINESS_DECISION.md (50 fills, 3 leagues, YES rate >= 90%, mean realized >= 1pp, fill rate >= 40%). Hard abort. Override requires a separate explicit `LIVE_OVERRIDE_GATE=true` env flag plus loud Discord alert.
- **Add a 6th kill trigger:** rolling 30-fill mean < 0.5pp. Detects edge compression without waiting for outright negative.
- **Idempotent fill processing.** Track `processed_fill_ids` in state; on startup reconcile from `last_reconciled_ts - 1h`.
- **Reconcile filled-but-not-settled tickers explicitly each loop**, not just when they appear in scanner candidates.
- **Drop the `max(1, ...)` floor in sizing.** Force operator to set `LIVE_PER_TRADE_USD` to >= worst-case price, or skip the placement. Naturally price-weights at higher budgets.
- **Decide on ONE drawdown gate.** Either fold `KILL_DRAWDOWN_PCT` into DrawdownMonitor as a new tier or document KillTriggerMonitor as authoritative. Don't ship two parallel systems.
- **Arm the 15-winner trigger only after >= 20 winners.** Before that, use a fixed-dollar single-loss threshold ($2.50 default).
- **Add SIGINT/SIGTERM handler** that attempts cancel-all on exit. Add a heartbeat file write per loop (informational, no auto-flatten yet, but available for cron watchdog).
- **Enumerate Kalshi error codes the mock must simulate:** INSUFFICIENT_FUNDS, MARKET_CLOSED, POST_ONLY_CROSS, FOK_INSUFFICIENT_VOLUME, 429, 401, network timeout, duplicate client_order_id. Test each with a corresponding bot-response assertion.
- **Eliminate the 0.97-vs-0.95 inconsistency.** Delete `expected_net_edge_for_favorite` from `paper_trade_favorite.py`; import and use `favorite_maker.expected_net_edge`.
- **Add `--mode live-demo` variant** pointing at demo URL. Operator runs >= 20 placements against demo before flipping to prod.

## What I would NOT do

1. **Do not ship `epoch_minute` idempotency.** It's worse than no idempotency for the retry case (introduces collisions without protecting against duplicates). Replace it.
2. **Do not rely on operator eyeball review of acceptance criteria.** Encode them in pre-flight.
3. **Do not run prod-mode as the first live execution.** Run demo first to flush integration bugs, even though demo fill quality is fake.
4. **Do not add `--cancel-all-on-exit` as default-on.** Current default-off is fine. But DO add SIGTERM/SIGINT-best-effort-cancel.
5. **Do not skip the WSL clock check.** It's the single highest-probability silent failure on the operator's machine per agent-c-risk.md.
6. **Do not enable amendments (cancel + repost on price drift) in the FIRST live deploy.** The fill-reconciliation race in Section 5 is born when amendments are added. Defer until 50+ live fills are observed without amendment, then add amendments behind a feature flag with its own acceptance criteria.
7. **Do not let the 15-winner trigger auto-arm.** Gate it behind >= 20 winners.
8. **Do not use the gate's +5pp number for any live monitoring threshold.** Bürgi-realistic +1 to +3pp is the calibration target.

## Citations

- Design under critique: [live-mode-design.md](live-mode-design.md) lines 38-365
- Strategy code: [../src/kalshi_bot/strategy/favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py) lines 47-82
- Paper script: [../scripts/paper_trade_favorite.py](../scripts/paper_trade_favorite.py) lines 48-53, 134, 170-175
- Paper manager: [../src/kalshi_bot/strategy/order_manager.py](../src/kalshi_bot/strategy/order_manager.py) lines 163-206, 217-255
- Drawdown: [../src/kalshi_bot/risk/drawdown.py](../src/kalshi_bot/risk/drawdown.py) lines 55-61, 123-134
- Config: [../src/kalshi_bot/config.py](../src/kalshi_bot/config.py) lines 30-40
- Prior critic: [critic-favorite-maker.md](critic-favorite-maker.md) lines 67, 32, 153
- Readiness decision: [LIVE_READINESS_DECISION.md](LIVE_READINESS_DECISION.md) lines 98-115, 124-134
- API brief: [briefs/agent-a-api-infra.md](briefs/agent-a-api-infra.md) lines 25-31, 43-46, 51-52, 60-61, 104-107, 113, 185-191
- Risk brief: [briefs/agent-c-risk.md](briefs/agent-c-risk.md) lines 45, 83
- CLAUDE.md operator-environment note lines 240-242
