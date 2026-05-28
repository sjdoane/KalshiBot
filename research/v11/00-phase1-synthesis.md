# v11 Phase 1 Synthesis

**Round 16 (v11). Authored:** 2026-05-27. Orchestrator session.

Phase 1 ran four parallel research agents (A1 to A4). All returned within
budget. This document synthesizes their findings and identifies two
operator-decision blockers that must be resolved before Phase 1.5
methodology lock.

## Agent outputs (all in research/v11/)

| Agent | File | Verdict | Cost |
|---|---|---|---|
| A1 Becker game-resolution audit | A1-becker-game-resolution-audit.md | data layer FEASIBLE | ~$0.30 |
| A2 the-odds-api Starter scout | A2-the-odds-api-starter-scout.md | TIGHT (scope-down or $59 tier) | ~$0.15 |
| A3 methodology meta-critic | A3-methodology-meta-critique.md | composite gate pre-registered | ~$0.30 |
| A4 Track 2 wiring scout | A4-track2-wiring-spec.md | spec written; current state is more complete than prompt assumed | ~$0.20 |

Phase 1 spend ~$0.95 LLM (vs $2.00 reserved). Budget tracking healthy.

## Track 1: sportsbook line movement on game-resolution markets

### Data-side feasibility (A1)

Becker dataset has clean post-Oct-2024 game-resolution coverage:

| Prefix | Settled n | Window coverage | Verdict |
|---|---|---|---|
| KXMLBGAME | 4,408 | 98.8% | FEASIBLE (primary) |
| KXNBAGAME | 738 | 98.4% | FEASIBLE (deepest books) |
| KXNFLGAME | 428 | 99.8% | FEASIBLE (3-sport LOCO arm) |
| KXUFCFIGHT | 374 | 95.2% | MARGINAL (thin sportsbook archive) |
| KXBOXING | 12 | n/a | INFEASIBLE |

Aggregate: 5,960 settled markets, all entirely post-Oct-2024 (sign-flip
cohort). Trade-time-of-day distribution supports the T-6h, T-3h, T-1h
snapshot pattern in all 4 FEASIBLE prefixes.

Critical caveat preserved from A1: Becker has no orderbook bid/ask at
trade time. Trade-print mid as proxy is the F11 phantom risk. A3
pre-registered the methodology lock to address this with a frozen
75th-percentile haircut derived from Becker MARKETS snapshots plus a
forward live spot-check before any capital deploys.

### External-data cost (A2)

The-odds-api pricing correction: the operator's intended "Starter" is
labeled "20K" on the live pricing page ($30, 20,000 credits/month).
Historical endpoint cost is `10 credits * markets * regions` per call,
with bookmakers bundled inside region (no multiplier). At 3 snapshots
per game and us-only h2h:

- 30 credits per game (3 calls * 10 credits)

A1's actual n is far above A2's 500-game working estimate. Full Track 1
cost estimates:

| Scope | n_games | Credits | Tier needed |
|---|---|---|---|
| KXMLBGAME-only pilot, subsample n=666 | 666 | 19,980 | $30/20k (TIGHT) |
| KXMLBGAME full | 4,408 | 132,240 | exceeds $59/100k |
| KXMLBGAME + KXNBAGAME + KXNFLGAME pilot subsample n=1,500 | 1,500 | 45,000 | $59/100k (fits with 55k buffer) |
| KXMLBGAME + KXNBAGAME + KXNFLGAME full n=5,574 | 5,574 | 167,220 | exceeds $59/100k |

KXMLBGAME currently in season (per memory). Cleanest scale-up surface.

A2 recommends operator waits for A1 numbers before purchasing. A1 is in,
so the decision is unblocked. See operator decision Q1 below.

### Methodology pre-registration (A3)

A3 derived per-failure-mode gates for F1 to F11 plus a composite gate.
Highlights:

- **F4 (trade-print vs orderbook ask):** trade-print is the FEATURE in
  v11 (we test whether sportsbook movement leads Kalshi trade-print
  movement). The strategy backtest execution must use a deterministic
  haircut model. A3 recommends the 75th-percentile spread from Becker
  MARKETS snapshots, frozen on a development split, applied to every
  trade. This is the v8-A pattern applied prospectively.
- **F8 (gate-regime mismatch):** the v11 gate is derived from cost
  structure, NOT from any prior round's number. The pre-registered gate:
  `mean_net_pnl > fee + frozen_haircut + 1c safety buffer`, with 95%
  bootstrap CI lower bound also above this threshold.
- **F11 (Becker schema phantom):** the execution proxy must pass a
  30-day forward live spot-check (median absolute deviation of
  live_ask vs proxy <= 1c) before any capital deploys. Backtest result
  alone is not a ship signal. The composite gate output is at most
  PARTIAL until the forward check completes.
- **F10 (LOCO fragility):** both leave-one-sport-out AND
  leave-one-bookmaker-out, with block bootstrap at block_size=1 day to
  handle weekend cross-game correlation.

A3's composite gate (paraphrased): SHIP requires all 11 pre-registered
gates to pass simultaneously on a chronological validation split. Any
single gate failure drops the verdict from SHIP to PARTIAL. Eight or
more failures NULL the strategy.

## Track 2: shadow-mode wiring on v1

### Current state (audited 2026-05-27)

The v11 prompt's premise that Track 2 is "shadow-mode-pending" is
OUTDATED. Audit findings:

1. `src/kalshi_bot/strategy/shadow_filter.py` exists. It defines
   `shadow_evaluate(snap, kalshi_price)` reading two independent env
   flags: `SHADOW_MODE_ENABLED` (log to JSONL) and `LIVE_FILTER_ENABLED`
   (actively skip v1 candidates that fail the filter).
2. `scripts/paper_trade_favorite.py:418` and `:662` both call
   `shadow_evaluate(snap, target_price)`.
3. `scripts/run_live_bot.ps1:126,127` sets BOTH `SHADOW_MODE_ENABLED=true`
   AND `LIVE_FILTER_ENABLED=true`. Comment in the file:
   "Enable v5 Track A shadow-mode + active filter (operator-authorized
   2026-05-24 for live testing). The v5 combined filter (Polymarket +
   sportsbook + cross-market consistency) logs decisions to JSONL AND
   actively skips v1 candidates when it says fade."
4. `data/live_trades/v5_filter_shadow_log.jsonl` exists; the shadow log
   is actively accumulating data.
5. `OPERATOR_RUNBOOK.md:31` confirms: "The v5 Track A filter
   (SHADOW_MODE_ENABLED + LIVE_FILTER_ENABLED) is also active. It skips
   v1 candidates when Polymarket or sportsbook signals suggest Kalshi
   is over-pricing the favorite."

Net effect: the v5 filter has been BOTH shadow-logging AND actively
skipping v1 trades since 2026-05-24 (3 days). It is BEYOND the v11
prompt's "shadow-mode-only logging" ask.

### Reconciliation with v11 prompt

The v11 prompt asks for a LOGGING-ONLY hook writing to
`data/live_trades/shadow/shadow_filter_decisions.jsonl` (new path) with
fields `ticker, v1_decision, shadow_filter_decision, sportsbook_arm_decision, polymarket_arm_decision, timestamp`.

The existing infrastructure writes to
`data/live_trades/v5_filter_shadow_log.jsonl` (different path) with
fields `timestamp, ticker, series_ticker, kalshi_price, poly_mid,
sportsbook_implied, cross_market_implied, should_trade, fired_rules,
reason, confidence, fetch_status, fetch_latency_ms`.

The existing schema is missing one field the prompt wants: `v1_decision`
(whether v1 actually fired the trade after the filter call). The
existing schema records what the filter said, not whether v1 ended up
trading. Joining the two requires correlating with v1's order log.

### Track 2 status

**Operationally:** SHIPPED in a stronger form than the prompt described.
The filter is both logging AND actively affecting trades; live data has
been accumulating for 3 days.

**Per the prompt's literal ask:** PARTIALLY done. The new
`data/live_trades/shadow/shadow_filter_decisions.jsonl` path does not
exist; the `v1_decision` field is not explicitly written; the wiring
required to add it touches `scripts/paper_trade_favorite.py` which is
on v11's do-not-touch list.

Resolution needs operator input. See operator decision Q2 below.

## Operator decision blockers

### Q1: Track 1 scope and the-odds-api purchase

Track 1 backtest cost depends on game sample size. The four options:

A. Pilot scope. KXMLBGAME-only, n=666 (subsample). $30/20k tier.
   Single-sport edge confirmation only. Cannot LOCO-by-sport. Cost: $30
   external. Power: detects 2c MDE at 80% power, fee net of 30 bp
   haircut. Roughly half the analyst headroom under the composite gate.

B. Full MLB. KXMLBGAME at n=4408. $59/100k tier still NOT enough
   (132k credits needed). Recommend dropping this option unless we
   reduce snapshots from 3 to 1 (44k credits = fits $59 tier with 56k
   buffer, but loses the T-6h to T-3h-to-T-1h time-series).

C. Three-sport robustness. KXMLBGAME + KXNBAGAME + KXNFLGAME pilot
   subsample n=1,500. $59/100k tier (45k credits, 55k buffer). Full
   F10 LOCO arm support. Cost: $59 external. Recommended if methodology
   discipline takes priority.

D. No purchase. v11 Track 1 deferred. Build infrastructure on Becker
   alone (Becker has Kalshi trades, but no sportsbook history; without
   the-odds-api there is no leading-indicator test). Effectively kills
   Track 1.

### Q2: Track 2 disposition

Given the existing infrastructure, three options:

X. SHIPPED as-is. Mark Track 2 done. The current LIVE_FILTER_ENABLED +
   SHADOW_MODE_ENABLED state IS the shadow-mode evaluation; data is
   accumulating; future review at 120-180 days. v11 takes credit for
   the audit + documentation. Zero code changes.

Y. Add complementary join script. Build a post-hoc reconstruction tool
   that joins `v5_filter_shadow_log.jsonl` with v1's order log to
   produce the cross-table the prompt wanted (filter decision vs v1
   decision). Lives in `scripts/v11/`, runs nightly or on demand. No
   modification to v1 production code.

Z. Touch the do-not-touch file. Add one log line at
   `scripts/paper_trade_favorite.py:442` (and the matching :662) that
   writes the prompt's exact schema. Requires operator authorization
   since `scripts/paper_trade_favorite.py` is on v11's do-not-touch
   list. ~10 lines code change, 522-test pass-count regression check
   required, restart-only rollout.

## Recommendations

Track 1: **Option C** ($59/100k tier, three-sport subsample). Reasoning:
F10 LOCO-by-sport is a load-bearing pre-registered gate in A3; without
3-sport robustness, the v11 verdict could only ever reach PARTIAL even
on a positive backtest. The marginal $29 buys statistical legitimacy.

Track 2: **Option Y** (post-hoc join script). Reasoning: it produces the
exact prompt-specified cross-table without modifying v1 production code.
The existing shadow log captures the filter side of the cross-table
already; we just need to join with v1's order log. Lower-risk than Z,
more value than X.

If the operator declines C and wants A (pilot scope), the methodology
lock will fall back to single-sport (KXMLBGAME) and the composite gate
adjusted to drop F10 LOCO-by-sport. Verdict ceiling caps at PARTIAL.

If the operator declines Y and wants X (SHIPPED as-is), Track 2 closes
this round and v11 focuses entirely on Track 1. Net same outcome for
the operational 120-180 day evaluation clock that was the original goal.

## Phase 1.5 entry criteria

Phase 1.5 methodology lock proceeds once Q1 and Q2 are resolved. A3's
composite gate is already pre-registered; Phase 1.5 wraps the
operator-selected scope into the binding gate document and runs the
methodology critic agent.
