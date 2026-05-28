# Project Kalshi v5: Final Verdict

**Date:** 2026-05-24
**Author:** Claude (orchestrator)
**Authorization:** Operator instruction (2026-05-24, after v4 mixed): pursue three parallel tracks (sportsbook filter, Statcast props, crypto on-chain) with explicit "ensure you are not giving up before all angles attacked."
**Status:** v5 complete. **One PARTIAL pass (SHIP shadow-mode), two CONFIRMED NULL.**

## Verdict in one paragraph

v5 ran three orthogonal angles after v4. **Track A (sportsbook filter)** is the strongest outcome: V5-A1 verified 40.7% sportsbook coverage of v1's post-denylist live universe with signal direction matching V3-C (+1.70c mean Kalshi-over-sportsbook on favorites). V5-A2 built a combined Polymarket + sportsbook + cross-market-consistency filter module (28 unit tests pass) with locked thresholds; 23% within-coverage live fire rate (~9% over v1's full universe). Phase 3 critic signed off WITH CAVEATS: the v4-inherited +1.70pp identity has LOO fragility (-0.65pp on outlier removal), Bonferroni-corrected TA4 still includes zero. Recommendation: SHIP shadow-mode logging for 120-180 days as a hypothesis-validation exercise. **Track B (Statcast prop ML at n=146,952)** is a CONFIRMED NULL with an interesting twist: positive Brier skill score (BSS +0.57 for G2) at 1000x the sample size of v3 proves the model has calibration skill, but no decision rule (locked +2c take, symmetric -5c fade, Kelly-NO sizing) extracts profitable trades. Phase 3 critic explicitly attempted the two highest-prior salvages and both failed; the Kelly-NO "phantom edge" traced to stale post-settlement prices is documented to prevent future builds repeating it. **Track C (crypto on-chain at n=8274)** is a CLEAN NULL at the orthogonality stage: 0 of 7 features cleared the +0.005 Brier improvement threshold across 3 price bands; the V5-C1 pre-registered prediction of "0-2 features pass" was confirmed at the lower bound. v1 continues running unchanged on $32 with W1 denylist active.

## The five numbers that matter

| Number | Value | Meaning |
|---|---|---|
| Track A sportsbook coverage of v1 post-denylist live universe | **40.7% inclusive** (31.0% strict) | Higher than Polymarket's 42.6% (more in-universe) but slightly lower in raw count |
| Track A live A3 fire rate within-coverage / over-full-universe | **23% / 9.4%** | 3 of 13 v1-band live candidates fire at locked 5c threshold; effective rate vs v1's FULL candidate stream is ~9% |
| Track B sample size and Brier skill | **n=146,952; BSS +0.574** | Largest sample in project history; model HAS calibration skill but CANNOT MONETIZE under any tested decision rule |
| Track B orthogonality survivors | **8 of 74 candidate features** | All 8 are volume/PA-count proxies (V3-B1 league-progress pattern); zero skill-based Statcast features survived |
| Track C orthogonality best Brier improvement | **+0.0015 (best, in-sample)** | 3x below the +0.005 threshold; 0 features pass on any band |

Supplementary context:
- v4 Track A (Polymarket-only) measured +1.70pp on n=147 with CI [-0.32pp, +4.22pp]. v5 Track A reproduces this exactly on the same dataset; the sportsbook arm adds independent live-universe firing capacity.
- LOO-removal of the 4 outlier wins (V4-E HOU/IND-T10/DAL-T7/NYM) collapses Track A diff to -0.65pp with CI [-1.12pp, -0.27pp]. The signal direction is real (corroborated by V3-C, V5-A1) but small-n.
- Total LLM API spend across v4 + v5: $1.03 of $25 budget cap.
- Total the-odds-api credits used: 5 of 500 free-tier monthly (V5-A1 probe + V5-A2 cache-only).
- v1 W1 denylist active: KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS (per v4 V4-H stress test).

## What v5 produced that v4 didn't

### Track A: combined Polymarket + sportsbook filter (PARTIAL)

V4-E built the Polymarket-fade-filter alone (+1.70pp on n=147, CI lower -0.32pp, LOO-fragile). V5 added the sportsbook second-opinion arm:

- **`src/kalshi_bot_v5/filter_combined.py`**: 28 unit tests pass. Combines Polymarket-fade (7c threshold), sportsbook-fade (5c threshold), and cross-market-consistency (5c) via OR-logic.
- **the-odds-api live coverage measured**: 40.7% inclusive of v1's post-denylist live universe; 23% within-coverage A3 fire rate at locked 5c threshold on v1-band live candidates.
- **Signal direction confirmed**: V5-A1 live probe (n=23 v1-eligible-band sportsbook favorites) measured mean Kalshi - sportsbook = +1.70c, 65% Kalshi-over. Direction matches V3-C Polymarket measurement (sportsbook is the consensus, smaller divergence than retail-skewed Polymarket).
- **Phase 3 critic caveats**: 23% fire rate is WITHIN-COVERAGE; effective rate over v1's full universe is ~9.4%. The +1.70pp Path Y identity to V4-E inherits the LOO fragility. Bonferroni-corrected TA4 still includes zero.
- **Cost realism**: free tier supports live shadow-mode (~150 calls/mo, 30% of free 500 credits). Historical access requires $30/mo paid tier (V5-A1 corrected V4-D).

### Track B: Statcast prop ML at massive scale (CONFIRMED NULL)

The most thorough modeling experiment in project history:

- **Dataset n=146,952** binary-resolved KXMLBHIT/HR/HRR/KS markets across 43k player-game pairs (V5-B1). Single-player concentration < 1%. Massive sample.
- **Strict AS-OF discipline**: `game_date < as_of_date`. Unit test verified leak-free.
- **Orthogonality protocol**: 66 of 74 features dropped. The 8 survivors are all volume/PA proxies (analog to V3-B1's `nfl_games_played_pre_t35d`). xBA, xwOBA, K-rate, hard-hit-rate, exit-velo dropped because sportsbooks have already priced these via game lines that propagate to Kalshi prices.
- **Positive Brier skill, unmonetizable**: G2 (price-only LogReg) BSS +0.574, G3 +0.544. The model HAS calibration skill. But the locked +2c take rule cannot extract profitable trades (regularization shrinks extreme prices toward 0.5).
- **Phase 3 critic salvages explicitly closed**:
  - Symmetric -5c fade-direction NO-buy: fires ZERO times because LogReg max delta is +/- 2.3c.
  - Kelly-NO sizing: APPEARS +5.98c per contract on n=20k mid-band, but Phase 3 critic Test 2c traced the phantom to `last_price_dollars` being a stale post-settlement print at ~$0.01. Realistic NO ask is ~$1.00 (illiquid NO side). Net realistic mid-band P&L: -0.13c to -1.93c gross.

### Track C: crypto on-chain with orthogonality probe (CLEAN NULL)

The most-exploratory v5 angle, killed cleanly at the right stage:

- **Sample size is not the issue**: KXBTCD alone has 8,274 v1-band contracts (60x v3's n=147).
- **Coinbase-vs-BRTI tracking error 0.09%** (V5-C1's biggest concern resolved).
- **7 features sampled AS-OF T-1h before close**: realized vol, VWAP dev, spot-futures basis, funding rate, active addresses, DXY, hashrate. All from free US-legal sources (Coinbase, Deribit, Coin Metrics, blockchain.info, FRED).
- **Orthogonality at 3 price bands**: narrow [0.70, 0.95] n=200 (1 NO in train, degenerate); wider [0.55, 0.95] n=300 (0 NOs in train, degenerate); midband [0.55, 0.80] n=250 (7 NOs in train, robust). Best feature Brier improvement +0.00001 to +0.0015 across all bands, 3x to 5000x below the +0.005 threshold.
- **V5-C1's pre-registered prediction confirmed** at the lower bound (0-2 features pass; observed 0).

## Why the operator should accept these as complete answers

### Track A PARTIAL (SHIP shadow-mode)
The signal mechanism is corroborated independently by V3-C (Polymarket), V5-A1 (sportsbook live probe), and now V5-A2 (combined filter live fires). The verdict is honest about the LOO-fragility and Bonferroni gap; shadow-mode-with-120-180-day-evaluation is the right next step. Free tier supports it indefinitely without additional cost.

### Track B NULL at n=146k
At the largest sample any Project Kalshi build has produced, the model has CALIBRATION skill but cannot monetize it. Phase 3 critic attempted the two highest-prior salvages (fade-direction, Kelly-NO) and both failed mechanically. The Kelly-NO phantom edge from stale prices is documented to prevent future builds repeating it. This is a strong null: not a "didn't try hard enough" null, but a "tried hard, the signal isn't extractable through buy-YES or buy-NO" null at scale.

### Track C NULL at orthogonality
V5-C1 pre-registered 0-2 features expected to pass; observed 0. Three different price bands tested. The "central risk" V5-C1 flagged (orthogonality, not n) was confirmed as binding. The crypto market is too efficient for retail with free on-chain features.

## What v5 changes about the live bot

**Two operator-actionable items:**

### IMMEDIATE: Track A shadow-mode wiring (optional)

If the operator wants to proceed with Track A's shadow-mode validation, wire `evaluate_market_combined` into v1's main loop as a LOGGING-ONLY call (no behavior change to v1's actual trades):

- For each v1 candidate, call `kalshi_bot_v5.filter_combined.evaluate_market_combined(...)` and log the `CombinedFilterDecision` to `data/live_trades/v5_filter_shadow_log.parquet`.
- Polymarket arm: live mid via `clob.polymarket.com/midpoint?token_id=...` (free).
- Sportsbook arm: the-odds-api `/v4/sports/{sport}/odds` (1 credit per call, ~150 calls/mo at v1's cadence; 30% of free tier).
- After 120-180 days, run the V5-A2 TA evaluation on the live-resolved sample. If TA4 cleanly passes, activate the filter (skip trades when filter fires). If not, declare null and revisit.

This is OPTIONAL for the operator. The filter is not required for v1's continued operation.

### LONGER-TERM: re-measure v1's edge on denylisted-residual universe (W2)

V4-H closed v3's W1 item by adding the series denylist. W2 (re-measure v1's edge on the remaining universe) is still open. This is a 1-2 hour analytical task, not a fresh research run. Recommended within the next operator working session.

## What v5 produced with lasting value

1. **`src/kalshi_bot_v5/filter_combined.py`** + 28 unit tests: production-ready combined filter for shadow-mode logging or future activation.

2. **`src/kalshi_bot_v5/statcast_features.py` + `statcast_model.py`**: full ML pipeline for MLB player-prop modeling. Even though Track B closed null, the infrastructure is reusable for any future per-player prop analysis.

3. **`data/v5/prop_dataset.parquet` (n=146k)** and **`data/v5/statcast_cache/` (~1GB)**: the largest leak-free Kalshi dataset assembled in project history. Future researchers can rerun any analysis without re-collecting data.

4. **`scripts/v5/build_sportsbook_lookup.py`**: production sportsbook lookup wrapper for the-odds-api. Used by Track A shadow-mode if activated.

5. **`research/v5/07-critic.md`**: Phase 3 critic doc with 5 Killer findings. Especially important: the Kelly-NO phantom-edge finding (Test 2c) documenting how stale `last_price_dollars` post-settlement values can mislead a backtest into a fake +5.98c result. This is the kind of trap that v6 must avoid.

6. **Verified Anthropic / the-odds-api / Etherscan API integrations**: all key validations and rate-limit measurements documented in `01-sportsbook-coverage.md` and `03-crypto-inventory.md`.

7. **Three new null findings honestly documented**: v5's track B/C nulls join v2 (game-markets), v3 (external features), v4 Track B (LLM forecaster). The cumulative project-state evidence: outcome prediction on Kalshi sports markets with free public features is structurally below C6 at our scale. The only edge that survives is the second-opinion-filter direction.

## What we have NOT yet tried (future v6 candidates, if operator wants)

Per operator's standing "do not give up" instruction, here are angles not exhausted:

1. **Per-prop-type orthogonality on Track B**: V5-B2 ran the orthogonality protocol on the AGGREGATE n=146k. KXMLBHIT alone, KXMLBHR alone, KXMLBHRR alone, KXMLBKS alone may have different signal structures. Phase 3 critic Test 3 flagged this as the highest-prior remaining angle. Bleak prior (volume features still dominate), but cheap to test (~1 hour agent-clock).

2. **Track A at $30/mo paid tier**: unlocks historical odds backfill for a clean retrospective gate. Would resolve the LOO-fragility / Bonferroni concerns by giving a much larger resolved sample. Costs $30/mo ongoing; defer until shadow-mode data justifies.

3. **Agentic-retrieval LLM forecaster** (v4 Phase 4 must-do that was de-prioritized): per V4-B literature, agentic retrieval is the documented single biggest gain in LLM forecasting. V4-G2's null was on bare Wikipedia retrieval. Cost: $5-10 in API spend; build effort 4-6h.

4. **Cross-market consistency at scale**: V4-D found 6 of 6 resolved NFL win-total monotonicity violations correctly predicted. V4-E's A2 arm at +0.95pp per fire on NFL was a small-sample finding. Could be extended to other ladder series (KXNBAWINS, KXNHL, KXMLBALEAST). Free, no external data needed.

5. **Microstructure / orderbook analysis on Kalshi itself**: Kalshi has its own historical trades + orderbook depth. A market-making strategy or technical-analysis strategy on Kalshi's own price dynamics has never been tried. Completely different paradigm than outcome prediction.

6. **Prop markets with REAL execution slippage measurement**: V5-B2's verdict assumed +/- 2c LogReg-delta is the signal ceiling, but if Kalshi prop markets have wider spreads (5-10c per V5-B1), then ANY edge must be much larger than 2c to survive execution. A direct measurement of Kalshi prop spread would clarify whether v5-B's null is "no signal" or "signal smaller than spread."

## Time budget accounting

Operator authorized ~12-15 agent-hours for v5. Used approximately:

- Phase 1 three parallel research agents: ~3h agent-clock
- Phase 2 three parallel build agents: ~6.5h
- Phase 3 critic: ~1.5h
- Phase 4 amendments (orchestrator-direct): ~0.5h
- Phase 5 verdict (orchestrator-direct): ~0.5h

Total: ~12h. Within budget. Total Anthropic API spend: $1.03 cumulative across v4 + v5. Total the-odds-api credits: 5 of 500 free-tier monthly.

## v2/v3/v4/v5 cumulative failure-mode comparison

| Failure mode | v5 outcome |
|---|---|
| CV leak (v2 Section 3) | PREVENTED. Track A is overlay (n/a); Track B uses `trainer=` correctly; Track C never ran a model. |
| Feature look-ahead (v2 Section 4) | PREVENTED. Track A live-only; Track B AS-OF discipline verified; Track C T-1h-before-close. |
| Model anchors on price (v2 Section 5) | DETECTED AND DOCUMENTED. Track B orthogonality dropped 66 of 74 features; the 8 survivors are volume proxies (v3-B1 league-progress pattern). Same v3 failure mode at 1000x scale. |
| Single-entity artifact (v2 Section 6) | NOT REPRODUCED. Track B has <1% per-player concentration. Track A has the V4-E inherited 2-team A2 concentration disclosed. |
| False C6 comparison (v2 Section 9 / v3 trap) | PREVENTED. Track A uses post-denylist v1; Track B uses gate's v1_decision_fn verbatim; Track C is new domain (no C6 against v1). |
| Wrong-cutoff-window (v4 Killer 4.2) | n/a (no LLM). |
| Series-prefix coverage mismatch (v3 W1) | CLOSED via v4-H + v1 denylist. Track A respects post-denylist universe; Track B operates on KXMLBHIT/HR/HRR/KS which v1 doesn't trade; Track C is new domain. |
| Stale-price phantom edge (NEW v5 failure mode caught by critic) | CAUGHT BY V5 PHASE 3 CRITIC. Kelly-NO appearance of +5.98c on Track B was traced to `last_price_dollars` being a stale post-settlement print at ~$0.01 (true NO ask was ~$1.00). Documented to prevent future builds repeating. |

v5 introduced ZERO new uncaught failure modes. The Phase 3 critic caught the Kelly-NO phantom before it shipped. The discipline of running the critic before the verdict has now caught uncaught failures in v3, v4, and v5.

## Closing the v5 project

Recommended actions:

1. **Operator decision: shadow-mode logging for Track A?** OPTIONAL but valuable; gives a clean 120-180 day evaluation of the filter on real v1 candidates. Free tier supports it.

2. **Operator decision: W2 (re-measure v1 edge on denylisted-residual universe)?** RECOMMENDED within the next operator working session. 1-2 hours analytical work to verify v1 is still measurably positive on the remaining universe.

3. **Mark v5 master plan complete.** This verdict + `07-critic.md` is the project's terminal state for v5.

4. **Keep v5 artifacts in the repo** as research-mode reference.

5. **Update CLAUDE.md and project memory** to reflect Round 11 (v5 complete with shadow-mode-recommendation + 2 nulls).

6. **The cumulative project state**: v1 is the only active trading strategy; v4 Track A's filter is candidate-for-shadow-mode; everything else has been documented null. The operator's research mission "find an ML model that pairs with the Kalshi bot" has produced: zero ML models that monetize, one filter overlay that may help defensively.

## Closing note

Per the operator's explicit instruction "ensure you are not giving up before all angles attacked," v5 attacked the three highest-prior remaining angles after v4 in parallel, ran the critic, attempted the highest-prior salvages, and documented the results honestly. Track A's PARTIAL ship-recommendation, Track B's CONFIRMED NULL with documented salvage closures, and Track C's CLEAN NULL at orthogonality are each defensible.

The bottom line for the operator's research mission: at our scale and on Kalshi's available markets, free-public-feature ML for outcome prediction does not produce a monetizable edge. The only viable angle is "second-opinion filter" on v1 (Track A direction), and that requires 120-180 days of shadow-mode data to clear the gate honestly. v1 continues running on $32 with the W1 denylist; the filter is OPTIONAL.
