# v11 Phase 1.5 Methodology Lock (v2)

**Round:** 16 (v11)
**Locked at:** 2026-05-27 by orchestrator
**v1 history:** v1 drafted earlier this session and reviewed by methodology critic
agent which surfaced 3 KILLER + 9 IMPORTANT flaws. See
research/v11/02-methodology-critic.md for the critic report. v2 below
incorporates all 3 KILLER fixes and 8 of the 9 IMPORTANT fixes (IMP-9
absorbed into the IMP-3 sensitivity routine; pilot size of 100 is
retained but with sensitivity reporting at n in {50, 100, 200}).
**Status:** v2 binding. Phase 2 entry permitted on this document.
**Source inputs:** 00-phase1-synthesis.md, A1, A2, A3, A4, 02-methodology-critic.md

This document binds v11's pass / fail criteria BEFORE Phase 2 data
pulls. No criterion in this file may be tuned after seeing Phase 2
data. Adjustments require an explicit operator-authorized v3 of this
lock prior to seeing the result.

---

## Track 1 hypothesis (locked verbatim, unchanged from v1)

"When at least one major US sportsbook (DraftKings, FanDuel, Pinnacle)
moves a game-result moneyline implied probability by >= X percentage
points in the T-6h to T-3h window before a Kalshi game-resolution
market closes, AND the Kalshi trade-print mid has moved < Y percentage
points in the same window, taking the side the sportsbook moved toward
via a taker BUY at the Kalshi orderbook ASK (modeled by the
DETERMINISTIC_HAIRCUT execution proxy below) at any time in the T-3h to
T-1h window captures a positive net-of-fee edge above the cost-floor
target threshold."

X and Y are not pre-registered as numbers in this v2 lock; they are
derived deterministically from Pilot-A (see Section 3 below). The lock
binds the DERIVATION RULE, not the values.

## 1. Scope of universe (unchanged from v1)

**Sports (3, operator-approved):** KXMLBGAME, KXNBAGAME, KXNFLGAME.

**Becker cohort:** all settled (`status = 'finalized'`) Kalshi
game-resolution markets in the three sports with `close_time` in
[2024-10-01, 2025-11-30 (Becker terminal)] AND `created_time` of any
trade falling in the T-6h to T-3h window.

**The-odds-api cohort:** US-region historical h2h moneyline snapshots
for the matched game and matched timestamp window. Bookmakers in
scope: DraftKings (us), FanDuel (us), Pinnacle (eu, may or may not be
returned by the-odds-api in us region; if absent, drop to 2
bookmakers; the LOCO-by-bookmaker rule in G_F10 below accommodates
either 2 or 3 bookmakers in scope).

**Target backtest universe size:** n=1500 qualified events
post-Phase-2-join (subsample if necessary to stay within
the-odds-api $59/100k credit pool: 1500 events * 3 snapshots * 10
credits = 45,000 credits, 55,000 credit buffer).

**Match rule:** team name pair plus date plus official game start
time, sport-specific parser. Many-to-one and one-to-many matches
reject from the qualified universe with rejection rate reported.

## 2. Splits (per-sport median chronological split, REVISED per KILLER-2)

The v1 chronological 50/50 split (dev=2024-10-01 to 2025-05-31,
val=2025-06-01 to 2025-11-30) embedded sport-season mismatch (NFL had
zero dev events; MLB was early-season-only in dev). v2 replaces with a
per-sport median chronological split:

**Per-sport median split:** for each sport in {KXMLBGAME, KXNBAGAME,
KXNFLGAME} independently, compute the median `close_time` across all
qualifying Becker markets in that sport. Events with `close_time <
sport_median_close_time` go to the development split; events with
`close_time >= sport_median_close_time` go to the validation split.
Each sport contributes roughly 50% to dev and 50% to val by event
count. Dev and val are then unioned across sports.

**Purge buffer:** 7 calendar days around each sport's median boundary.
Events within 7 days of the per-sport median are excluded entirely
(not assigned to either split). Game-resolution label horizons are
3 to 6 hours, so 7 days is ample.

**Why this is the right v2 fix per KILLER-2:** the per-sport median
preserves chronological causality (no train-on-future) per sport while
ensuring every sport has dev calibration data. The pilot, by
construction, will draw from all 3 sports. G_F3 per-sport gate
operates on validation data that has at least 50% of each sport's
historical universe.

## 3. Pre-Phase-2 pilot (split into Pilot-A and Pilot-B per KILLER-3)

The v1 single-pilot design (sigma and haircut from the same 100 events)
was self-referential. v2 splits the pilot into two non-overlapping
halves of 50 events each, with cross-fit calibration:

### 3.1 Sample design

**Pilot pool:** all development-split events.

**Stratification:** within each sport's development split, sort by
(ticker, close_time). Take the first 17 events from KXMLBGAME, 17 from
KXNBAGAME, and 16 from KXNFLGAME for Pilot-A (50 total, stratified). Take
the NEXT 17, 17, 16 (rows 18-34, 18-34, 17-32 by sport) for Pilot-B (50
total, stratified). All 100 pilot events purged from development split
before any subsequent calibration.

### 3.2 Pilot-A (computes haircut, X, Y)

**DETERMINISTIC_HAIRCUT:** pull Becker MARKETS snapshots within the
T-6h to T-1h window for each Pilot-A event. For each snapshot with both
`yes_ask` and a same-event recent trade-print, compute
`gap = yes_ask - trade_print`. DETERMINISTIC_HAIRCUT = 75th-percentile
across all Pilot-A snapshots.

**Sensitivity check (per IMPORTANT-9 / IMP-3 sensitivity):** re-derive
haircut on the first 25 of Pilot-A and on Pilot-A plus the first 50 of
Pilot-B (n=100). If the 75th-percentile haircut changes by more than
0.5c across n in {25, 50, 100}, the pilot is undersampled and v2 lock
escalates to v3 with expanded pilot size.

**X threshold:** for each Pilot-A event, the-odds-api implied prob at
T-3h vs T-6h gives `delta_sportsbook = abs(implied_at_T-3h - implied_at_T-6h)`
(using the bookmaker with the lowest absolute median move across the
3-bookmaker set per game, conservative single-source rule; see Section
3.5 below for the alternative median-across rule). X = median(delta_sportsbook)
across Pilot-A.

**Y threshold:** `delta_kalshi = abs(VWAP_kalshi_at_T-3h - VWAP_kalshi_at_T-6h)`.
Y = median(delta_kalshi | delta_sportsbook >= X) across Pilot-A.

**Snapshot coverage gate:** if Pilot-A snapshot coverage in the
execution window is below 50%, v2 lock is INVALID at Phase 2 stage
(F4 Option B fails); operator must authorize either v3 lock with
F4 Option A (forward live spot-check) or kill Track 1.

### 3.3 Pilot-B (computes sigma)

**sigma_per_event:** apply the Pilot-A frozen (X, Y, DETERMINISTIC_HAIRCUT)
to all 50 Pilot-B events. For each Pilot-B event that satisfies the
signal (`delta_sportsbook >= X` AND `delta_kalshi < Y`), compute net P&L
per contract:

```
net_pnl_per_contract = realized_outcome - (trade_print_mid + DETERMINISTIC_HAIRCUT) - fee_per_contract(trade_print_mid + DETERMINISTIC_HAIRCUT)
```

`realized_outcome` is 1.0 if the side taken wins, 0.0 if it loses.
`fee_per_contract` uses Kalshi's verified formula (Section 6.3).

sigma_per_event = sample standard deviation of net_pnl_per_contract
across Pilot-B firing events.

If fewer than 10 Pilot-B events fire, sigma is too imprecisely
estimated to support G_F2 power calculation; v2 lock escalates to v3
with expanded Pilot-B or relaxed X (with caveat that relaxed X
re-introduces F6 multi-cell risk and must be pre-registered).

**Why this fixes KILLER-3:** sigma is now computed on events that did
NOT participate in haircut calibration. Anti-self-fit variance shrinkage
is eliminated. The unbiased sigma flows into G_F2 n_required.

### 3.4 Target threshold (regime-derived per A3 F8, formula corrected per KILLER-1)

The v1 formula used `kalshi_fee = 0.07 * abs(price - 0.5)` which is
WRONG per `src/kalshi_bot/analysis/metrics.py`. The verified formula:

```python
def kalshi_taker_fee_per_contract(price, contracts=1):
    cents = np.ceil(7.0 * contracts * price * (1.0 - price))
    return float(cents / 100.0)
```

Returns fee in dollars. At price 0.55: ceil(7 * 0.55 * 0.45) = ceil(1.7325) = 2 cents, $0.02 per contract.

Phase 2 implementation MUST import `kalshi_taker_fee_per_contract`
directly from `src.kalshi_bot.analysis.metrics`, NOT reimplement.

**Target threshold derivation (REVISED):**

```
modal_execution_price = median(trade_print_mid + DETERMINISTIC_HAIRCUT | snapshot in T-3h to T-1h window, computed on Pilot-A)
kalshi_fee_at_target = kalshi_taker_fee_per_contract(modal_execution_price)
target_per_trade_net_pnl = kalshi_fee_at_target + DETERMINISTIC_HAIRCUT + 0.01
```

Worked example with corrected formula at modal_execution_price = 0.55:
fee = $0.02 (2c), placeholder haircut = $0.02 (2c, illustrative), buffer
= $0.01 (1c), target = $0.05 per contract net. Phase 2 produces the
actual computed value.

**G_F2 target_MDE derivation (REVISED per IMPORTANT-1):** target_MDE is
identical to target_per_trade_net_pnl above. v1's 2c MDE was a F8
violation. v2 derives target_MDE from the same cost-floor formula
that G_F8 uses, so the two gates reference the same number.

### 3.5 Bookmaker signal-sourcing rule (REVISED per IMPORTANT-7)

v1 ambiguous "most-liquid bookmaker" sourcing for X. v2 specifies:

**X signal rule:** for each Becker market with multiple bookmaker
snapshots available, compute per-bookmaker delta in the T-6h to T-3h
window. X-signal fires if the MEDIAN delta across available bookmakers
is >= X. This is the conservative "majority of bookmakers moved" rule;
LOCO-by-bookmaker then operates by re-computing the median with one
bookmaker excluded.

**LOCO-by-bookmaker (revised G_F10 sub-rule):** for each bookmaker B in
scope, re-evaluate the strategy with B excluded from the per-game
median. The signal-firing set may change (events where the median
without B differs from the median with B may no longer fire, or new
events may fire). Re-run validation backtest on the post-LOCO-by-B
qualified universe. Net P&L > 0 with block bootstrap 95% CI excluding
zero required. This is a true data-leave-out, not a degenerate
game-drop.

### 3.6 Pre-registered (X, Y, target) tuple (single primary cell, per A3 F6)

After Pilot-A computes haircut, X, Y and Pilot-B computes sigma, the
SINGLE pre-registered cell is `(X, Y, DETERMINISTIC_HAIRCUT, target)`.
No grid search. No alternative X or Y is evaluated.

**Per IMPORTANT-8 conjunctive-correction acknowledgment:** the lock's
verdict structure is a conjunction of 11 gates (G_F1 through G_F11).
Under the null hypothesis, the probability that all 11 sub-tests pass
at alpha 0.05 is much smaller than 0.05; the conjunction is itself a
multi-test correction (each sub-gate failure increases the verdict
falsifiability). The PARTIAL verdict (9 or 10 of 11 pass) is the
boundary at which multi-test concerns are most acute; v2 specifies in
Section 5 below that PARTIAL verdicts require the failing gate to be
non-load-bearing (defined as: not G_F4, G_F8, or G_F11).

## 4. The 11 binding gates (REVISED with KILLER + IMPORTANT fixes embedded)

All applied to the VALIDATION split using the pre-registered (X, Y,
target, DETERMINISTIC_HAIRCUT) from Pilot-A and sigma from Pilot-B.
Each gate is evaluated independently; verdict is the conjunction.

### G_F1 coverage and dropout (dual-stage per IMPORTANT-4)

- **Pilot-stage check:** at Pilot-A + Pilot-B (n=100), join coverage
  rate >= 50% with Wilson 95% lower CL above 40%. If fails, v2 lock
  invalid at Phase 2 stage; v3 required.
- **Full-universe check:** at full validation join, coverage rate
  >= 60% AND n_qualified_validation >= 200.
- MAX_LAG_SECONDS = 1800 (30 minutes); no extrapolation.
- Result: PASS only if BOTH stages pass.

### G_F2 power

- sigma_per_event from Pilot-B (unbiased per KILLER-3 fix).
- target_MDE = target_per_trade_net_pnl from Section 3.4 (per
  IMPORTANT-1; NO 2c borrow).
- `n_required = ceiling((2 * 1.96 * sigma_per_event / target_MDE)^2)`
- PASS if `n_qualified_validation >= n_required AND >= 200`.

### G_F3 per-sport (unambiguous floor per IMPORTANT-6)

- For each sport contributing >= 50 qualified events on validation:
  per_sport_mean_net_pnl > 0 with bootstrap 95% CI lower bound >
  per_sport_per_trade_fee_cost (computed at per-sport median
  execution price)
- v2 rule: at least 2 of 3 sports must clear the per-sport gate AND
  have >= 50 qualified events. Sports with <50 are reported but not
  gated.
- PASS if 2 or more sports clear; FAIL if fewer than 2.

### G_F4 haircut application (unchanged)

- F4 Option B applied via DETERMINISTIC_HAIRCUT from Pilot-A.
- Mean per-trade net P&L (gross minus fee minus haircut) >= 1c per
  contract with bootstrap 95% CI lower bound > 0.

### G_F5 comparator and falsification (unchanged)

- Comparator 1: random-side taker
- Comparator 2: anti-signal taker (opposite side)
- v11_mean_net_pnl - comparator_mean_net_pnl > 0 with non-overlapping
  bootstrap 95% CIs, both comparators.

### G_F6 multiple-test inflation (conjunctive correction acknowledged)

- Single pre-registered (X, Y, target, haircut) tuple from Pilot-A +
  Pilot-B.
- Conjunctive verdict structure already controls family-wise Type-I
  rate.
- PASS by construction at Phase 2 entry; descriptive multi-cell
  reports may accompany but do not gate.

### G_F7 no post-settlement trades (unchanged)

- BUFFER_SECONDS = 60
- Loader assertion: zero trades with `created_time >= close_time - 60`
  in qualified universe.
- PASS if assertion holds; backtest aborts otherwise.

### G_F8 regime-derived cost floor (corrected fee formula per KILLER-1)

- target_per_trade_net_pnl = kalshi_taker_fee_per_contract(modal_execution_price)
  + DETERMINISTIC_HAIRCUT + 0.01
- Validation mean per-trade net P&L > target_per_trade_net_pnl
- Bootstrap 95% CI lower bound > target_per_trade_net_pnl (NOT > 0).

### G_F9 side symmetry (unchanged)

- YES-side and NO-side per-trade net P&L means both positive.
- abs(YES_mean - NO_mean) <= 2 * min(YES_mean, NO_mean) with
  bootstrap 95% CI on the difference excluding the larger mean.

### G_F10 LOCO (revised bookmaker rule per IMPORTANT-7)

- LOCO-by-sport: for each sport in {MLB, NBA, NFL}, remove all
  events of that sport, re-run validation; net P&L > 0 with block
  bootstrap (block_size = 1 calendar day) 95% CI excluding zero.
- LOCO-by-bookmaker: for each bookmaker in scope, re-compute the
  per-game median across the REMAINING bookmakers, re-determine the
  signal-firing events, re-run validation; net P&L > 0 with block
  bootstrap 95% CI excluding zero.
- PASS if ALL one-out runs clear (3 sport-out + 2 or 3 bookmaker-out).
- Diagnostic LOO: report any single-event removal that shifts pooled
  mean by > 0.5 * SE_pooled; LOO is diagnostic, not gate.

### G_F11 execution-model phantom defense (REVISED per IMPORTANT-2 + IMPORTANT-5)

**Part A (in-session, hard gate, unchanged):** DETERMINISTIC_HAIRCUT
from Pilot-A frozen before validation backtest. Pilot-A snapshot
coverage >= 50%.

**Part B (forward live spot-check, OUT-OF-SESSION, REVISED):**
- Test is two-sided per IMPORTANT-5: PASS if abs(median(gap_live)) <= 0.01
  where gap_live = live_yes_ask - (trade_print_mid + DETERMINISTIC_HAIRCUT)
- Sport-aware acceptance per IMPORTANT-2: the spot-check sample must
  include qualifying events from at least 2 of the 3 in-scope sports.
  If a sport is out of season at the spot-check window, the SHIP
  verdict for that sport is held at PROVISIONAL-SHIP-PENDING-SPOTCHECK
  until the next in-season window completes and a per-sport spot-check
  passes.
- Minimum n: >= 30 qualifying events across the 2+ sport coverage.

## 5. Verdict mapping (REVISED PARTIAL rule per IMPORTANT-8 conjunctive logic)

- **All 11 gates pass (Parts A AND B of G_F11):** SHIP-shadow-mode at
  $0.50 per trade for 60 to 120 calendar days. Live capital not
  deployed before G_F11 Part B completes.
- **All 11 gates pass except G_F11 Part B incomplete:** PROVISIONAL-
  SHIP-PENDING-SPOTCHECK, no capital.
- **10 of 11 pass, failing gate is non-load-bearing:** PARTIAL.
  Non-load-bearing gates are: G_F1 (coverage), G_F3 (per-sport, only
  if the failing sport has <50 events; n>=50 failures are load-bearing),
  G_F5 (comparators), G_F6 (already pass-by-construction), G_F7
  (would have aborted earlier), G_F9 (symmetry, if asymmetry direction
  matches the signal direction). Load-bearing gates that MUST pass for
  ANY non-NULL verdict: G_F2, G_F4, G_F8, G_F10, G_F11 Part A.
- **9 of 11 pass:** PARTIAL only if BOTH failing gates are non-load-bearing.
  Otherwise NULL.
- **8 or fewer pass:** NULL. Close v11 Track 1 at $0 capital, update
  CLAUDE.md failure-mode taxonomy.

## 6. Execution mechanics (Phase 2 reference)

### 6.1 Becker schema fields used

- `markets`: ticker, series_ticker, close_time, status (filter status='finalized'),
  title, event_ticker, yes_resolution
- `trades`: trade_id, ticker, count, yes_price, no_price, taker_side, created_time
- `markets` MARKETS-SNAPSHOT subtable (V10-A finding): _fetched_at,
  yes_bid, yes_ask, no_bid, no_ask (orderbook snapshot, irregular cadence)

### 6.2 The-odds-api fields used

- Endpoint: GET /v4/historical/sports/{sport}/odds
- Sport keys: americanfootball_nfl, baseball_mlb, basketball_nba
- Region: us (primary), eu (fallback for Pinnacle)
- Markets: h2h
- Snapshot rule: query at T-6h, T-3h, T-1h relative to Kalshi close_time;
  first matching snapshot at or before target time within MAX_LAG_SECONDS

### 6.3 Kalshi fee formula (CORRECTED per KILLER-1; import from codebase)

```python
from src.kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract

# fee_per_contract(price=0.55) -> 0.02 (2 cents)
# fee_per_contract(price=0.70) -> 0.02
# fee_per_contract(price=0.80) -> 0.02
# fee_per_contract(price=0.90) -> 0.01
```

Underlying implementation: `cents = ceil(7.0 * contracts * price * (1 - price))`
returning `cents / 100.0` dollars. Phase 2 scripts MUST import; MUST NOT
reimplement.

### 6.4 P&L formula per trade

```
execution_price_proxy = trade_print_mid_at_signal + DETERMINISTIC_HAIRCUT
fee = kalshi_taker_fee_per_contract(execution_price_proxy)
gross_pnl = realized_outcome - execution_price_proxy
net_pnl = gross_pnl - fee
```

### 6.5 Bootstrap mechanics

- Pooled bootstrap CI: 10,000 row-bootstrap resamples on per-event net P&L
- LOCO bootstrap CI: 10,000 block-bootstrap resamples grouped by
  `floor(created_time, day)`; block_size = 1
- Comparator CI difference: paired bootstrap on (v11_net - comparator_net)
  per event, same 10,000 resamples seed
- Random seed: 42

## 7. What v11 will NOT do (anti-pattern bans, unchanged from v1)

a) Use post-settlement `last_price_dollars` as any kind of price proxy
b) Use stale trade-print mid as a Brier-comparison BASELINE (v7-B
   phantom defense; v11 uses trade-print as FEATURE, allowed)
c) Borrow a numerical gate threshold from any prior round's result
   (F8 defense; +12.47pp, +0.014, +3.58pp, +0.208, 2c MDE all banned)
d) Tune (X, Y) after seeing validation P&L (F6 defense)
e) Apply DETERMINISTIC_HAIRCUT computed on validation events (F11 defense)
f) Pool YES-side and NO-side without symmetry check (F9 defense)
g) Use single-row bootstrap when events share a calendar day (F10 defense)
h) Deploy capital before G_F11 Part B 30-day spot-check completes
i) Re-implement Kalshi fee formula in Phase 2 scripts (KILLER-1 defense;
   import from metrics.py)

## 8. Phase 2 sequencing

Step 1 (no external spend): build Becker side of the dataset. Pull all
3-sport game-resolution markets and trades. Compute per-sport median
close_time; assign dev/val splits per Section 2. Identify Pilot-A and
Pilot-B per Section 3.1. Compute Pilot-A haircut, X, Y. Sensitivity
report on haircut at n in {25, 50, 100}. Verify G_F7 loader assertion.
Compute provisional Pilot-A target threshold.

Step 2 (BLOCKED on operator $59 the-odds-api purchase):
- Operator action: purchase the-odds-api $59/100k tier
- Operator action: add `THE_ODDS_API_STARTER_KEY=<key>` to .env
- Pull historical odds for 3 sports, 3 (or 2) bookmakers, dev and val windows
- Join to Becker markets via per-sport parser
- Report join coverage rate (G_F1 numerator); G_F1 pilot-stage check fires

Step 3 (in-session, after Step 2): re-run Pilot-A and Pilot-B with full
join data; freeze final (X, Y, DETERMINISTIC_HAIRCUT, sigma, target).

Step 4 (in-session, after Step 3): run validation backtest. Apply 11
binding gates. Report verdict per Section 5.

Step 5 (out-of-session, operator-driven if SHIP-PROVISIONAL): 30-day
forward live spot-check for G_F11 Part B. Multi-sport coverage required
per revised IMPORTANT-2 fix. v11 closes as PROVISIONAL-SHIP-PENDING-SPOTCHECK
until the spot-check completes.

## 9. Track 2 spec (REVISED v1_decision schema per IMPORTANT-3)

### 9.1 Goal

Produce the prompt-specified cross-table at
`data/live_trades/shadow/shadow_filter_decisions.jsonl` with operator-
distinguishable v1 outcomes.

### 9.2 Input sources

- `data/live_trades/v5_filter_shadow_log.jsonl` (existing shadow log)
- v1 order log: `data/live_trades/state.json` (LiveOrderManager state
  with per-order: placed_ts, acked_ts, filled_ts, filled_price_cents,
  filled_count, cancelled_ts, status, ticker)

### 9.3 Script location

`scripts/v11/join_filter_vs_v1.py`. Read-only with respect to both
input sources. Write target: `data/live_trades/shadow/shadow_filter_decisions.jsonl`.
Auto-create parent dir.

### 9.4 Schema (REVISED v1_decision as 4-state enum per IMPORTANT-3)

JSONL row schema:

| Output field | Type | Source / derivation |
|---|---|---|
| timestamp | ISO8601 string | shadow_log row `timestamp` |
| ticker | string | shadow_log row `ticker` |
| v1_decision | enum string in {`placed_and_filled`, `placed_and_expired`, `placed_and_cancelled`, `placed_and_rejected`, `not_placed`} | derived from state.json fields per rule below |
| shadow_filter_decision | bool | shadow_log row `should_trade` |
| sportsbook_arm_decision | bool or null | derived from shadow_log row `sportsbook_implied` + `fired_rules` |
| polymarket_arm_decision | bool or null | derived from shadow_log row `poly_mid` + `fired_rules` |

**v1_decision derivation rule (per state.json field semantics):**

- `placed_and_filled`: order exists with `ticker == row.ticker`, placed within +/- 5 min of `row.timestamp`, `filled_count > 0`
- `placed_and_expired`: order exists with `ticker == row.ticker`, placed within +/- 5 min, `filled_count == 0`, `cancelled_ts is None`, market past resolution
- `placed_and_cancelled`: order exists with `ticker == row.ticker`, placed within +/- 5 min, `cancelled_ts is not None`
- `placed_and_rejected`: order exists with `ticker == row.ticker`, placed within +/- 5 min, `acked_ts is None`
- `not_placed`: no v1 order on `ticker` within +/- 5 min of `timestamp`

A downstream consumer wanting binary placed-vs-not-placed collapses
`{placed_and_filled, placed_and_expired, placed_and_cancelled, placed_and_rejected}`
to True and `not_placed` to False. The cross-table preserves the higher
precision so consumers can analyze fill-rate effects separately from
placement effects.

### 9.5 Operator deployment

Operator runs `uv run python scripts/v11/join_filter_vs_v1.py` on demand.

### 9.6 Test coverage

`tests/v11/test_join_filter_vs_v1.py` with at least 7 test cases:
- empty inputs
- no v1 orders
- all v1 orders match filter
- mismatched ticker
- mismatched timestamp window
- v1 order placed then cancelled
- v1 order placed then never filled

### 9.7 Verdict gate

Track 2 SHIPS when:
a) Script runs cleanly on the current `v5_filter_shadow_log.jsonl`
b) Output schema validates against the revised spec in Section 9.4
c) All 7 unit tests pass
d) Existing 522 collected tests still pass (no regression)

## 10. Operator handoff at lock close

v2 lock is binding. Phase 2 Step 1 (Becker side, no external spend)
proceeds immediately. Step 2 blocks on operator the-odds-api purchase.

The operator's pre-Phase-2-Step-2 action: purchase the-odds-api $59/100k
tier and add `THE_ODDS_API_STARTER_KEY` to .env. The v11 session will
explicitly ask via AskUserQuestion at the Step 2 entry point.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or
U+2013 throughout. Verified by post-write grep.*
