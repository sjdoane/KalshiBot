# V10-A FINAL VERDICT

**Date:** 2026-05-27
**Round:** 15
**Author:** V10-A orchestrator
**Status:** NULL (pre Phase 2 kill at methodology lock)
**Total V10-A spend (this session):** approximately $1.50 LLM ($0.50 lit scout, $0.40 methodology critic, plus orchestrator reads at roughly $0.60); well under the $8 cap

---

## Verdict: NULL

V10-A (Kim et al. arXiv 2602.07048 replication of Granger + LLM filter on Kalshi Economics markets, using the Becker dataset) closes NULL before any backtest data is queried, on the strength of a Phase 1.5 adversarial methodology critique that fired three independent KILLER findings.

This is a kill-at-methodology-lock, the same outcome class as v9 NULL but on different mechanism. v9 killed at design layer (gate-regime mismatch); V10-A kills at data-schema layer plus structural-statistical infeasibility plus gate-calibration error.

---

## Why kill, not run

The methodology critic agent (`research/v10a/A3-methodology-critique.md`) raised three KILLER-tier findings that cannot be jointly fixed without changing the methodology so much that it is no longer a Kim replication:

### KILLER 1: Becker dataset has no orderbook ask at trade time (recreates v7-B phantom risk)

The Becker `kalshi/trades` parquet schema contains only `trade_id, ticker, count, yes_price, no_price, taker_side, created_time, _fetched_at`. There is NO `yes_ask` or `yes_bid` at trade time. The `kalshi/markets` schema has bid/ask snapshots but at irregular `_fetched_at` timestamps, not aligned to signal-fire moments.

Consequence: any execution-price baseline reproduces v7-B's confirmed phantom failure mode (CLAUDE.md: 8 of 8 live bets lost, mean -$0.20, binomial p ~ 0.004). The signal step (cross-market lead-lag) is sound; the execution step is data-layer infeasible.

The orchestrator's revision attempt (next-trade fill as execution proxy) does not fully address this: the next trade may have been an MM-driven fill at a price that the strategy could not realistically have taken, and look-ahead bias enters at the chosen fill window.

### KILLER 2: LOCO at sample size 9 cannot run Granger F-test at lag 5

With 4 series at approximately 9 train events per series (after the 60/40 train/OOS split on post Oct 2024 data through Becker's November 2025 boundary), the lag-5 Granger F-test needs at least 11 observations to compute. The system is underdetermined.

Reducing the lag set to {1} only is no longer a Kim replication. Switching to daily VWAP introduces serial correlation that violates the F-test's null distribution, plus the frequency mismatch with monthly release events.

Gate G3 (LOCO robustness) is structurally infeasible regardless of how G1/G2 perform.

### KILLER 3: Breakeven 51.75% calibrated to wrong execution price

The fee-aware breakeven varies from approximately 32% at execution price 0.30 to approximately 72% at execution price 0.70. Kim's reported 54.5% win rate is below breakeven at any execution price above 0.55. The strategy's signal definition fires on delta_X regardless of Y's price, so the single-number gate G1 is uncalibrated for the trade distribution the strategy actually generates.

Per-trade EV gating (collapsing G1 into G2) is the fix, but at our small n the CI on dollar-per-trade P&L is too wide to clear breakeven exclusion.

### Compounding effect

Each KILLER alone might be repaired with substantial revision. The joint repair requires:
- Different dataset (no replacement exists for historical Kalshi orderbook)
- Different unit of analysis (no longer Kim replication)
- Different gate (per-trade EV at small n is too wide to clear)

The result of all three repairs is no longer "Kim replication on Kalshi macro." It is a different angle entirely, which is out of V10-A scope per the operator brief.

---

## Supporting context

The kill is also supported by:

- **Lit scout finding (`research/v10a/01-lit-delta.md`):** Kim arXiv 2602.07048 paper has NO fees, NO bid-ask, NO slippage in its reported P&L. The 51.4% to 54.5% win rate is gross-idealized. Independent replication is needed to test whether the gross signal survives realistic execution. The only positive 2026 Kalshi-macro result (Mohanty arXiv 2604.01431) pivots execution to crypto volatility on Deribit, not Kalshi itself.

- **Becker Finance category baseline (`research/literature/becker-microstructure-prediction-markets-2026.md` summary in lit scout):** gross excess return is approximately +/-0.08% per trade on 4.4 million trades. The market category Kim's strategy targets is gross-zero empirically; any retail edge is structurally fragile after fees.

- **Diercks/Katz/Wright 2026 (FEDS):** Kalshi macro markets are efficient against Bloomberg consensus and FRBNY SoMA. Susquehanna actively makes these markets. Cross-market lead-lag at daily VWAP frequency is at the wrong frequency to evade institutional arb.

- **Cumulative project history:** 8 NULLs, 1 confirmed PHANTOM, 2 PARTIAL shadow-mode pending across Rounds 1 to 14. The base rate for any new angle clearing all gates is approximately 10 to 15 percent unconditional. V10-A's methodological constraints push the prior below this floor.

---

## What was built and preserved

These artifacts remain useful for future rounds (Round 16+) or for project audit:

| File | Purpose |
|---|---|
| `research/v10a/A2-methodology-lock-v2.md` | Speculative methodology lock; documents what the Kim replication WOULD have required |
| `research/v10a/A3-methodology-critique.md` | The KILL critique with three KILLER findings and six IMPORTANT findings |
| `research/v10a/01-lit-delta.md` | 2026 literature scout output; Kim's paper has no fees, Mohanty pivot to crypto vol, transfer entropy and Hawkes process gaps confirmed |
| `research/v10a/03-strategic-synthesis.md` | Pre-kill strategic synthesis explaining the high-NULL prior |
| `research/v10a/spend-log.md` | LLM spend tracking |
| `scripts/v10a/inventory_becker_macro.py` | Becker macro inventory script (deferred but reusable in Round 16) |
| `scripts/v10a/extract_becker.py` | Python zstandard extractor for Becker .tar.zst on Windows |
| `scripts/v10a/smoke_test_fred.py` | FRED API smoke test (PASS as of 2026-05-27) |
| `scripts/v10a/smoke_test_gemini.py` | Gemini Flash filter smoke test (PASS as of 2026-05-27; LLM is a strict filter, may rubber-stamp at runtime depending on lag) |
| `scripts/v10a/smoke_test_granger.py` | Granger F-test smoke test on synthetic data (PASS as of 2026-05-27) |
| `prediction-market-analysis/` | Becker dataset (clone + uv venv); 36 GB data download started, may finish in background; reusable in Round 16 |

The Becker .tar.zst download was kicked off but is not required for the V10-A NULL verdict. If the operator wants to keep the data for future rounds, let the curl process complete (estimated 30 to 60 more minutes from V10-A NULL fire). If not, the operator can interrupt and remove the partial file.

---

## New failure mode to log

Per CLAUDE.md methodology discipline, any new failure mode caught by a critic should be added to the F1 to F10 taxonomy. This round's surfaced failure mode:

**F11 (new): Dataset Schema Phantom**

Definition: Pre-registering a backtest gate that depends on an execution-price field that does NOT exist in the chosen dataset schema. The strategy looks fireable on paper but the data layer does not contain the required field. The fix attempts (proxies, snapshots, next-trade fills) recreate the v7-B phantom-baseline pattern in disguise.

Checklist item: Before locking any backtest gate, audit the dataset schema and verify that every field required for signal firing AND every field required for execution pricing exists at the timestamp the strategy needs it. If the execution-price field is unavailable, the gate cannot be calibrated and the strategy is data-layer infeasible.

This is distinct from F1 (data-availability ceiling, which is about access) and F4 (phantom from stale-price proxy, which is about the signal-vs-baseline gap in a single market). F11 is about the absence of the execution-price field altogether at the trade-by-trade level.

---

## Operator handoff items

The operator (this round closer is the main session, NOT V10-A orchestrator) should:

1. Update CLAUDE.md with the V10-A NULL closure summary plus the new F11 failure mode entry.
2. Update memory file `project_kalshi.md` with Round 15 V10-A NULL outcome.
3. Decide whether to keep the partially-downloaded Becker dataset (currently at approximately 14 GB of 36 GB) for Round 16 use, or interrupt and remove.
4. Coordinate Round 15 closure write-up with V10-B verdict (the other session window).

V10-A does not touch CLAUDE.md or memory directly per the orchestrator brief. The closure is left to the main session that owns both V10-A and V10-B summary.

---

## What V10-A NOT killing would have looked like (kill-early audit)

If we had proceeded into Phase 2 instead of killing here:

- Spend would have grown by approximately $2 to $3 (Phase 2 modeling agent, Phase 3 critic agent, final synthesis), bringing V10-A total to roughly $5.
- The phase 2 backtest would likely have produced a point-estimate win rate near Kim's 54.5% (replication is plausible) but a CI too wide to clear the 51.75% breakeven (KILLER-3 demonstrated this).
- The phase 3 critic would have caught the same KILLER-1 (no orderbook ask in dataset) at that stage anyway, but the verdict would be PHANTOM-RISK rather than NULL, because by then we would have a number to point at.
- The cumulative ledger would gain 1 more PHANTOM, not 1 more NULL. Operationally identical outcome at higher cost.

The kill-early choice saves approximately $2 to $3 LLM and avoids a second confirmed PHANTOM entry (which would be worse for the project's stated $100 cap discipline). This is the right call per `feedback_kill_early.md`.

---

## Possible pivots for Round 16 (NOT in V10-A scope; for operator consideration)

From the lit scout's `confirmed gaps` section and the alternative angles in `research/v10/03-methodology-meta.md`:

| Angle | Rationale | Cost estimate |
|---|---|---|
| Mohanty replication: KXFED daily delta leads BTC realized vol at h=5d on Deribit | Only 2026 positive Kalshi-macro result; pivots execution off Kalshi | Variable; Deribit data + crypto options |
| Transfer entropy alternative to Granger on Kalshi macro pairs | First mover at small n; nonlinear robust | Low LLM, $0 data |
| Sportsbook dynamic line movement (research/v10/03-methodology-meta.md Proposal 1) | Different mechanism, $30 the-odds-api data | $30 external |
| Game-resolution sports microstructure (Proposal 2) | $0 cost, fresh slice of v6 KXBTCD null | $0 |

Each is a Round 16 candidate, not a V10-A revival. The Kim replication path is structurally closed at this dataset and time window.

---

## Anti em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013). All separations use commas, semicolons, "to" / "vs", or double hyphens.
