# v9 FINAL VERDICT: NULL on Angle A

**Round:** 14
**Date:** 2026-05-26
**Outcome:** **NULL on Angle A** (kill-early, pre Phase-2 data pull)
**Type:** Combined data-layer and design-layer infeasibility
**Operator decision:** M3 (kill v9, redirect to v10)
**Phase 3 critic:** KILL CONFIRMED, added design-layer finding
**Total v9 spend:** approximately $2 LLM (Phase 1 agents only). $0 external data. $0 capital.

---

## TLDR

v9 Angle A (agentic LLM ensemble on sports per the AIA Forecaster recipe) was scoped against v1's denylisted-residual sports universe at horizons T-35d to T-7d with a pre-registered +0.014 Brier delta gate. Phase 1 surfaced two compounding feasibility breaks:

1. **Data layer:** historical Kalshi orderbook is structurally unavailable. The `/markets/{ticker}/orderbook` endpoint returns an empty book for settled markets and silently ignores the `?ts=` parameter on open markets. Retrospective backtest is dead because the only honest baseline (real orderbook mid, per v7-B phantom prevention) cannot be reconstructed for resolved markets.

2. **Universe:** the post-Opus-cutoff sports universe is seasonal. KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF, KXNFLGAME all have zero settled markets in 2026-01-15 to 2026-05-26. Only 5 v1-eligible settled sports markets exist in the OOS window (4 boxing + 1 UFC). Currently-open v1-eligible markets closing 2026-05-27 to 2026-06-30: n = 87. Detectable Brier delta at 80 percent power, alpha 0.05, n = 87: approximately 0.088, which is 6x the pre-registered gate. The detection floor at n = 87 sits between 0.088 and 0.140 depending on variance estimator (Test 3 of the Phase 3 critic). The AIA Forecaster used n approximately 3,000 per subcategory to detect +0.014 cleanly.

3. **Design layer (surfaced by Phase 3 critic Test 5):** the +0.014 lift figure was measured by AIA on uncertain markets (Kalshi mid 0.20 to 0.80, the regime where Halawi 2024 shows LLM beats crowd). v1's universe is confident favorites (0.70 to 0.95), the regime where Halawi 2024 documents LLM HEDGING and UNDERPERFORMANCE. The numerical mismatch: under a generous toy assumption (LLM is correctly directional, hedges from 0.85 toward 0.70, Platt corrects to 0.813), the expected ensemble Brier improvement is approximately 0.00015, two orders of magnitude below the pre-registered gate. The gate was effectively unfirable from pre-registration onward.

The honest move was to kill on the data-layer break; the Phase 3 critic identified the design-layer issue as an even stronger reason for the same outcome. v9 closes NULL.

---

## Replay-prevention insight (new failure mode logged)

**Gate-regime mismatch.** Pre-registered gates copied from a published benchmark must match the data regime where the benchmark measured the lift. AIA Forecaster's +0.014 was on hard (uncertain) markets; applying it to confident favorites guarantees a gate-misses-mechanism in the methodology.

This pairs with the prior rounds' replay-prevention list:
- v2: false comparison failure (label horizon overlap)
- v5-B: stale post-settlement `last_price_dollars` as ask proxy
- v6: feature framing failure (returns vs levels)
- v7-B: stale trade-print mid as orderbook baseline
- v9 (new): pre-registered gate from a benchmark measured in a different price regime

In future rounds, when borrowing a numerical gate from a paper, verify that the paper's experimental regime (price band, market type, horizon, news availability) materially matches our intended target. If it does not, derive a regime-matched gate or write the gate as a function of the regime.

---

## What v9 produced

Documents (all in `research/v9/`):

- `00-v10-candidate-angles.md` (ranked v10 candidate list, 9 angles scored)
- `01-data-universe.md` (Kalshi orderbook + universe + the-odds-api + ESPN + GDELT scoping with live probe results)
- `02-recipe-methodology.md` (full AIA recipe replication spec; reusable verbatim for any future LLM forecasting attempt)
- `03-phase1-synthesis.md` (the synthesis and decision point doc)
- `04-phase3-critic.md` (Phase 3 adversarial critic, 7 tests, KILL CONFIRMED with design-layer addition)
- `FINAL-VERDICT.md` (this doc)

Code (all in `scripts/v9/`):

- `probe_v9_universe.py` (Kalshi orderbook + universe probe, READ-ONLY, no /portfolio/orders calls)
- `probe_settled_markets.py`, `probe_sports_closed_deep.py`, `probe_sports_oos.py`

Data (`data/v9/`): two small probe-output JSONs only. No model artifacts, no forecasts, no parquet.

Source (`src/kalshi_bot_v9/`): empty. Phase 2 never started.

These artifacts are reusable. The `02-recipe-methodology.md` AIA replication spec is a complete blueprint should a future round target a wider universe with a regime-matched gate.

---

## v10 candidates and immediate next actions

Per `00-v10-candidate-angles.md` and the Phase 3 critic Test 6:

### Action A (zero cost, runs essentially for free): v8-A analysis pass

v8-A live probe (PID 66132) is recording prospective Kalshi orderbook data through 2026-05-26 23:48 UTC. When it finishes, an analysis pass against the captured snapshots either:
- **Confirms v7-B is phantom (expected per the v7 critic's live snapshot):** v7-B closes definitively as PHANTOM (was PARTIAL-PHANTOM). No further v8-B prospective build needed.
- **Finds durable strong signals:** elevates v8-A to the v10 anchor at the v7 critic's 40 percent conditional prior, which is the highest evidence-backed prior across all candidates.

This analysis is in the OTHER session (different PID, different conversation); this session does not run it.

### Action B (zero cost, 30 minutes): Polymarket CLOB depth re-probe

v3 was killed at the data layer because Polymarket CLOB had a hard 30-day rich-detail ceiling. If 2026 Polymarket endpoints expose 90+ days of depth on Kalshi-parallel markets, Candidate 3 (Polymarket-as-feature redux) becomes viable at zero further cost. Single API call needed.

### Action C (operator decision): v10 angle selection

A3's ranked top 3:
1. v8-A prospective recovery (conditional on Action A finding signal)
2. Sportsbook line movement on game-resolution markets (priors 12 to 22 percent; $30 the-odds-api Starter one-time within authorized budget)
3. Sports microstructure on game-resolution series (priors 10 to 18 percent; zero cost; reuses v6 infrastructure)

No candidate priced above 22 percent. The cumulative state is 7 NULLs + 2 PARTIALs + 1 PHANTOM in 9 ML attempts.

---

## Capital and v1 status

Unchanged. v1 production bot continues to run on $32 with the W1 denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) applied. W2 audit YELLOW (leaning GREEN) at +7.68pp residual mean still stands. No new live decisions in this round. No edits to `.env`, `data/live_trades/`, `data/paper_trades/`, or any v1 production path.

---

## Spend accounting

| Bucket | Authorized | Spent | Remaining |
|---|---|---|---|
| LLM (Anthropic API) | $25 of $25 cap (cumulative across rounds) | approximately $2 this round, $17-19 cumulative | approximately $6-8 remaining |
| External data | $30 to $60 | $0 this round, $0 cumulative | $30 to $60 |
| Capital (operator-deployed) | $100 cap | $32 (unchanged) | $68 |

Honest assessment: v9 spent under budget because we killed at Phase 1 instead of running Phase 2. The cumulative LLM spend approaches the cap but is not yet there. v10 should be selected with the remaining headroom in mind.

---

## Cumulative project state after Round 14

| Round | Approach | Outcome |
|---|---|---|
| v1 (Round 6, live) | Favorite-maker on Kalshi sports | LIVE on $32 with W1 denylist; W2 YELLOW lean GREEN |
| v2 | Game-market ML | NULL |
| v3 | Polymarket-as-feature + team stats | NULL |
| v4-A | Polymarket fade filter | PARTIAL (SHIP shadow-mode pending wire) |
| v4-B | LLM-as-forecaster (no tools) | NULL (BSS -2.17) |
| v5-A | Sportsbook fade filter | PARTIAL (SHIP shadow-mode pending wire) |
| v5-B | Statcast prop ML | NULL (n=146k, model-class robust) |
| v5-C | Crypto on-chain features | NULL |
| v6 | Crypto microstructure T-30/T-15 internal | NULL |
| v7-B | Kronos + naive_p_yes | PARTIAL-PHANTOM (v8 prospective test pending) |
| v7-C | TabPFN model-class diagnostic | NULL |
| v8-A | Prospective orderbook snapshot recording | RUNNING (analysis pending after 2026-05-26 23:48 UTC) |
| v9 | AIA-style LLM ensemble on sports | NULL (data-layer + design-layer infeasibility) |

Eight NULLs total, two PARTIALs in shadow-mode-pending state, one PHANTOM under prospective test, one live $32 strategy with a YELLOW lean GREEN edge audit. The frontier of cheap retail Kalshi alpha is exhausted across nine ML attempts.

---

## What the operator decides next

Per the M3 commitment: no further v9 spend, redirect to v10. The operator owns the v10 angle pick. The cleanest sequencing:

1. Wait for v8-A to finish (2026-05-26 23:48 UTC) and the other session's analysis pass.
2. Probe Polymarket depth (action B above) to upgrade or eliminate Candidate 3.
3. Choose v10 from updated ranked list.

If v8-A finds durable strong signals, v10 = v8-A prospective recovery (Candidate 7). If it does not, v10 = v10 Candidate 9 (sportsbook line movement) at $30 external spend, or Candidate 8 (sports microstructure) at $0, per operator preference.
