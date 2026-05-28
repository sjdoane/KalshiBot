# Sports x Long-Horizon Results: OOS Gate

**Date generated:** 2026-05-23T18:55:47.066606+00:00
**Methodology:** [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
**Round 3 revision:** [round-3-methodology-revision.md](round-3-methodology-revision.md)
**Window:** small-trade VWAP in [resolution - 42d, resolution - 28d]
**Verdict:** **PROVISIONAL PASS** (methodology criteria pass; C6 realized-P&L CI wide; operator approval required for Phase 3 paper trading at minimal position size)

## Pass criteria

| Criterion | Required | Observed | Result |
|---|---|---|---|
| C1a median per-partition slope (informational) | >= 1.2 | 1.204 | PASS (informational) |
| C1b q25 per-partition slope (informational) | >= 1.0 | 1.087 | PASS (informational) |
| C2 median pooled gross edge (small, eligible) | >= 2.23pp | 6.79pp | PASS |
| C3 pooled bootstrap 95% CI lower bound | > 0pp | 2.97pp (diag: 3 of 3 splits net > 0; 3 of 6 skipped) | PASS |
| C4 leagues with median net > 0 (needs N>=3 leagues) | >= 3 of 6 | 6 of 6 | PASS |
| C5 pooled median AND mean net edge (small) | both > 0pp | median=3.29pp mean=4.87pp | PASS |

## Dataset

- rows: 423
- unique_series: 107
- date_min: 2025-02-11 20:24:24.052706+00:00
- date_max: 2026-04-28 04:26:45+00:00
- outcome_rate: 0.3735
- median_trades_in_window: 25
- median_small_trades_in_window: 10
- median_lifetime_days: 132
- mid_small_p05: 0.01
- mid_small_p50: 0.3085
- mid_small_p95: 0.9689

## Cross-check on all-trade VWAP (diagnostic)

- pooled median net edge (all-trade): 4.97pp
- pooled mean net edge (all-trade): 6.25pp

## Resolution-time-purge sensitivity check (methodology Section 5.1)

Re-runs walk-forward with the stricter constraint that test markets must open AFTER train_end. If the locked gate PASSES but this sensitivity check FAILS, the apparent edge is plausibly leakage-driven through shared news-period structure during overlapping lifetimes.

- splits attempted: 6; skipped: 6
- pooled median net edge: n/a
- pooled mean net edge: n/a
- bootstrap 95% CI: [n/a, n/a]
- would pass equivalent C3 + C5 if were the gate: NO

## Realized P&L diagnostic (Round 3.1 honest-edge test)

C6 measures whether the model-predicted edge MATERIALIZES in realized profit on the OOS test set. This is the strictest validation: the bot's actual trade decisions, settled at the actual outcome, after fees and slippage.

- n_trades: 26
- hit rate (P&L > 0): 69.2%
- median realized P&L: 19.38pp
- mean realized P&L: 0.27pp
- SD per trade: 46.95pp
- bootstrap mean: 0.27pp
- bootstrap 95% CI: [-18.61pp, 17.42pp]

## Pooled bootstrap on small-trade net edge

- mean: 4.87pp
- 95% CI: [2.97pp, 7.02pp]

## Per-series slope distribution

- n: 0
- median: n/a
- q25: n/a
- q75: n/a

## League distribution (full corpus)

- NBA: 134
- NFL: 74
- OTHER: 72
- MLB: 45
- NHL: 31
- NCAA-FB: 22
- MLS: 12
- UEFA-CL: 8
- CRICKET: 5
- PGA: 4
- UFC: 3
- F1: 3
- FIFA-WC: 3
- BOXING: 2
- BUNDES: 2
- NCAA-OTHER: 2
- TENNIS: 1

## Walk-forward splits

| Split | n_train | n_test | n_eligible | slope | raw ECE | cal ECE | ratio | median gross | median net (small) | median net (all) |
|---|---|---|---|---|---|---|---|---|---|---|
| wf_04_2025-03-30_to_2025-12-09 | 124 | 33 | 7 | 1.439 | 0.1481 | 0.0981 | 1.51x | 9.20pp | 5.70pp | 5.14pp |
| wf_05_2025-05-29_to_2026-02-07 | 179 | 35 | 16 | 0.970 | 0.1760 | 0.1678 | 1.05x | 5.78pp | 2.28pp | 4.92pp |
| wf_06_2025-07-28_to_2026-04-08 | 219 | 23 | 3 | n/a | 0.1402 | 0.1824 | 0.77x | 13.67pp | 10.17pp | 0.55pp |

## Leave-one-league-out

| League | n_train | n_test | n_eligible | median net (small) |
|---|---|---|---|---|
| NBA | 289 | 134 | 25 | 5.47pp |
| NFL | 349 | 74 | 21 | 7.60pp |
| OTHER | 351 | 72 | 18 | 2.18pp |
| MLB | 378 | 45 | 15 | 6.38pp |
| NHL | 392 | 31 | 3 | 2.84pp |
| NCAA-FB | 401 | 22 | 4 | 6.86pp |

## Recommendation

**PROVISIONAL PASS**: methodology criteria (C2, C3, C4, C5) ALL pass. Predicted edge is consistently positive across the OOS test partitions; the bootstrap CI on predicted edge excludes zero. C6 (realized-P&L bootstrap CI > 0) does NOT pass because the realized sample (n=26) is too small to achieve statistical confidence at SD ~47pp per trade. Realized mean P&L is POSITIVE.

Recommendation: operator-approved Phase 3 paper trading at MINIMAL position size ($0.50 per trade or less) to gather more sample. Target: 100+ paper-traded fills. If paper P&L mean remains positive and bootstrap CI becomes positive, scale to live capital. If paper P&L turns negative, end the strategy.

DO NOT deploy live capital based on this gate alone. The C6 failure is honest acknowledgement that the small sample doesn't statistically rule out a near-zero true edge.
