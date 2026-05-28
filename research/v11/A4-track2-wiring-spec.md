# A4: v11 Track 2 Shadow-Mode Hook Wiring Spec

**Audit date:** 2026-05-27
**Agent:** v11-A4 (read-only search)
**Target:** v1 production code location for v11 logging-only hook insertion
**Scope:** Track A filter (v4-A Polymarket fade + v5-A sportsbook divergence)

---

## Section 1: Decision Point (FIRE / SKIP)

**File:** scripts/paper_trade_favorite.py
**Lines:** 442-446

**Exact insertion point:** Line 442, immediately after the v5 filter skip block (lines 427-441).

The v1 FIRE decision is made at line 442 with the is_eligible(target_price) gate. If the gate passes, the candidate proceeds to net-edge calculation (line 444) and ultimately to the scoring list (line 447). This is the moment all trading logic converges.

**Variables in scope at line 442:**

- snap (MarketSnapshot): ticker, series_ticker, yes_bid, yes_ask, volume, open_time, close_time
- target_price (float): the yes_bid v1 uses for pricing
- _decision (ShadowDecision | None): the v5 filter decision object (already computed on line 418)
- net (float): expected net edge (computed on line 444, but can be computed at the hook)
- sized (int): position size from dynamic multiplier (line 391)

**Hook contract:** The shadow logger receives snap, target_price, and _decision (when it exists), logs them to JSONL with v1's actual fire/skip outcome, and returns None. No state mutation, no trade-behavior change.

---

## Section 2: Filter Module API

**File:** src/kalshi_bot_v5/filter_combined.py
**Public entry point:** evaluate_market_combined() (lines 269-399)

**Return type:** CombinedFilterDecision (NamedTuple, lines 78-114)

Fields: should_trade (bool), reason (str), poly_mid (float|None), sportsbook_implied (float|None), kalshi_price (float), cross_market_implied (float|None), confidence (float), fired_rules (tuple of str)

**Imports v11 needs:**

from kalshi_bot_v5.filter_combined import (
    evaluate_market_combined,
    CombinedFilterDecision,
    FADE_THRESHOLD_CENTS_POLY_DEFAULT,
    FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
    MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
)

**Module maturity:** 28 tests in tests/v5/test_filter_combined.py (all pass); locked methodology per V5-A2.

---

## Section 3: Shadow Logger Design

**Proposed module path:** src/kalshi_bot_v11/shadow_logger.py

**Entry point:** log_shadow_decision(snap, target_price, v1_decision, filter_decision) -> None

**JSONL schema for data/live_trades/shadow/shadow_filter_decisions.jsonl:**

Each line contains: timestamp, ticker, series_ticker, v1_decision (fire flag, target_price, is_eligible_pass, net_edge), filter_decision (should_trade, reason, fired_rules, confidence, poly_mid, sportsbook_implied, cross_market_implied), polymarket_arm (fetch_status, latency_ms), sportsbook_arm (fetch_status, implied, latency_ms)

**Rotation policy:**
- Append-only JSONL, no explicit rotation in phase 1
- Operator runs external cleanup after 120-180 day evaluation window
- File lives at data/live_trades/shadow/ (separate from state.json, kill_state.json)

**Thread safety:**
- v1's main loop is single-threaded (one_loop_favorite_paper / one_loop_favorite_live)
- No concurrent writes to JSONL
- Use append mode ("a") with line-level atomic writes (one json.dumps per line)

---

## Section 4: Test Baseline

**Baseline test count:** 522 tests collected

**Command:** uv run pytest tests/ --collect-only -q

**Current pass rate:** 340/340 tests pass (per CLAUDE.md Round 5 closure)

**Must remain unchanged after v11 wiring:** All 522 collected tests must pass in Phase 2 Track 2 completion. v11 Hook must not create regressions.

---

## Section 5: Reload Safety

**v1 hot-reload behavior:** ONLY on restart. No dynamic module reloading or env-var hot-patching at runtime.

**Deployment pattern for v11 wiring:**
1. Operator deploys v11 code (new v11 logger module and updated paper_trade_favorite.py call site)
2. Operator restarts the bot with --mode paper or --mode live
3. SIGTERM handler (lines 759-790) cancels resting orders cleanly on exit
4. No in-flight order is aborted; all open orders remain resting until manually cancelled or filled
5. Restart takes <5 seconds to acquire lock, read state.json, and resume the main loop

**Downtime impact:** None. The single-instance lock (src/kalshi_bot/strategy/single_instance.py) ensures only one bot instance runs; on restart it acquires the lock immediately and resumes the same state (resting orders persist across restart on Kalshi's side).

---

## Section 6: Risks

**1. Fetcher-induced latency in hot path**

The v5 combined filter calls fetch_polymarket_midpoint() and fetch_sportsbook_implied() on every candidate in the main loop (line 418 in paper_trade_favorite.py). If both fetchers respond slowly (API latency, network), the loop stalls waiting for the decision.

*Mitigation:* Fetchers already have timeout logic; v11 will inherit it. Monitor latency_ms field in the JSONL log to detect when fetches exceed the loop cadence (900 seconds default). Consider disabling Polymarket fetch if latency dominates.

**2. Cross-market (monotonicity) disabled in shadow-mode**

Line 230 of shadow_filter.py sets cross_market_data=None, disabling Track A2 (ladder consistency). This is intentional for the initial shadow run: no ladder data is available in the current live environment. v11 will log only A1 (Polymarket) and A3 (sportsbook) signals.

*Mitigation:* Acceptable trade-off for Phase 1 (shadow-log-only, no behavioral change). If A2 signal becomes available later, re-enable by passing cross_market_data dict to evaluate_market_combined().

**3. Sportsbook fetcher credit budget**

Line 401-404 in paper_trade_favorite.py calls reset_loop_budget() to reset the sportsbook fetcher's per-loop credit allowance. If the fetcher is modified to be stateful, the hook must ensure credits are not exhausted prematurely.

*Mitigation:* Current sportsbook_fetcher.py has no shared state between loops. Each loop gets a fresh budget. v11 will inherit this design.

**4. No automatic directory creation**

The v11 logger must create data/live_trades/shadow/ on first write, or the write will fail. shadow_filter.py (line 254) uses mkdir(parents=True, exist_ok=True), which is safe.

*Mitigation:* v11 logger will use same pattern.

**5. Decision point surrounded by filtering logic**

Lines 427-441 skip candidates based on the v5 filter (when LIVE_FILTER_ENABLED is true). The v1 FIRE decision point (line 442) occurs only for candidates that passed the v5 filter skip. This means v11's shadow log will see only candidates v1 actually considered; skipped candidates will not appear.

*Mitigation:* This is the correct behavior for a LOGGING-ONLY hook. v11 should only log candidates v1 trades on. Skipped candidates are logged by shadow_filter.py itself (line 432), not by v11.

**6. Dependency on MarketSnapshot class**

v11 logger uses snap.ticker, snap.series_ticker from MarketSnapshot. This is a public data class in src/kalshi_bot/strategy/pricing.py, used throughout v1, so stable.

*Mitigation:* No risk. MarketSnapshot is part of the public v1 API.

---

## Summary

**v1 Decision point:** scripts/paper_trade_favorite.py:442 (is_eligible gate)
**Filter module:** src/kalshi_bot_v5/filter_combined.py, public API evaluate_market_combined()
**Logger module:** src/kalshi_bot_v11/shadow_logger.py (to be created)
**JSONL sink:** data/live_trades/shadow/shadow_filter_decisions.jsonl
**Test baseline:** 522 collected, 340 passing
**Restart-only reload:** Yes, no hot-patching
**Key risk:** Fetcher latency in hot path (acceptable, monitored via log)

v11 is ready for Phase 2 Track 2 implementation. The insertion point is clean, the filter API is stable, and the shadow logging pattern is already proven in shadow_filter.py.