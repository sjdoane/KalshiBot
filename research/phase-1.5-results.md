# Phase 1.5 Results: Zerve Out-of-Sample Replication

**Date generated:** 2026-05-23T05:32:31.569793+00:00
**Methodology:** [phase-1.5-methodology.md](phase-1.5-methodology.md)
**Verdict:** **GATE FAILS**

## Pass criteria

| Criterion | Required | Observed | Result |
|---|---|---|---|
| C1 median OOS ECE improvement | >= 5x | 4.77x | FAIL |
| C2 median shoulder gross edge | >= 2pp | 10.52pp | PASS |
| C3 at least 4 splits with >= 3x | >= 4 | 13 | PASS |
| C4 leave-one-city-out positive | >= 3 of 5 | 5 of 5 | PASS |
| C5 shoulder net edge (after fees) | > 0 | 8.52pp | PASS |

## Dataset

- rows: 5786
- cities: ['CHI', 'DEN', 'LAX', 'MIA', 'NY']
- date_min: 2021-11-16
- date_max: 2026-04-28
- outcome_rate: 0.2826
- mid_price_p05: 0.01
- mid_price_p50: 0.01
- mid_price_p95: 0.99

## Informational (not part of pass criteria)

- median hit rate on trades > 2pp edge: 100.0% (50% = no directional skill)
- median realized P&L per contract after maker fees: $0.0300

## Walk-forward splits

| Split | n_train | n_test | raw ECE | cal ECE | ratio | shoulder edge | net edge | hit rate >2pp | median PnL/contract |
|---|---|---|---|---|---|---|---|---|---|
| wf_04_2024-03-31_to_2024-11-03 | 490 | 112 | 0.0216 | 0.0107 | 2.01x | 0.25pp | -1.75pp | 87.5% | $0.0149 |
| wf_05_2024-04-30_to_2024-12-03 | 538 | 225 | 0.0208 | 0.0072 | 2.89x | 2.34pp | 0.34pp | 81.8% | $0.0087 |
| wf_06_2024-05-30_to_2025-01-02 | 808 | 183 | 0.0239 | 0.0114 | 2.10x | 10.56pp | 8.56pp | 87.0% | $0.0435 |
| wf_07_2024-06-29_to_2025-02-01 | 1006 | 136 | 0.0259 | 0.0060 | 4.34x | 4.69pp | 2.69pp | 78.6% | $0.0175 |
| wf_08_2024-07-29_to_2025-03-03 | 1157 | 132 | 0.0382 | 0.0460 | 0.83x | 5.86pp | 3.86pp | 70.4% | $0.0100 |
| wf_09_2024-08-28_to_2025-04-02 | 1315 | 101 | 0.0150 | 0.0030 | 4.99x | 10.47pp | 8.47pp | 100.0% | $0.0271 |
| wf_10_2024-09-27_to_2025-05-02 | 1432 | 88 | 0.0150 | 0.0031 | 4.77x | 5.95pp | 3.95pp | 100.0% | $0.0315 |
| wf_11_2024-10-27_to_2025-06-01 | 1521 | 84 | 0.0161 | 0.0027 | 6.02x | 11.45pp | 9.45pp | 100.0% | $0.0664 |
| wf_12_2024-11-26_to_2025-07-01 | 1610 | 78 | 0.0119 | 0.0007 | 18.07x | nanpp | nanpp | 100.0% | $0.0200 |
| wf_13_2024-12-26_to_2025-07-31 | 1692 | 118 | 0.0230 | 0.0122 | 1.88x | 5.59pp | 3.59pp | 100.0% | $0.7567 |
| wf_14_2025-01-25_to_2025-08-30 | 1812 | 109 | 0.0105 | 0.0004 | 24.31x | nanpp | nanpp | 100.0% | $0.0134 |
| wf_15_2025-02-24_to_2025-09-29 | 1938 | 111 | 0.0108 | 0.0005 | 21.53x | nanpp | nanpp | 100.0% | $0.0231 |
| wf_16_2025-03-26_to_2025-10-29 | 2052 | 172 | 0.0104 | 0.0001 | 76.84x | nanpp | nanpp | 100.0% | $0.0142 |
| wf_17_2025-04-25_to_2025-11-28 | 2188 | 228 | 0.0180 | 0.0072 | 2.49x | 14.64pp | 12.64pp | 85.7% | $0.0701 |
| wf_18_2025-05-25_to_2025-12-28 | 2453 | 513 | 0.0188 | 0.0045 | 4.16x | 12.38pp | 10.38pp | 77.4% | $0.0313 |
| wf_19_2025-06-24_to_2026-01-27 | 2906 | 654 | 0.0197 | 0.0063 | 3.11x | 10.80pp | 8.80pp | 88.2% | $0.0364 |
| wf_20_2025-07-24_to_2026-02-26 | 3547 | 564 | 0.0112 | 0.0005 | 22.09x | nanpp | nanpp | 100.0% | $0.0316 |
| wf_21_2025-08-23_to_2026-03-28 | 4214 | 667 | 0.0142 | 0.0019 | 7.50x | 12.37pp | 10.37pp | 83.3% | $0.0300 |
| wf_22_2025-09-22_to_2026-04-27 | 4856 | 633 | 0.0108 | 0.0002 | 46.53x | 11.22pp | 9.22pp | 100.0% | $0.0484 |

## Leave-one-city-out

| Held-out city | n_train | n_test | raw ECE | cal ECE | ratio |
|---|---|---|---|---|---|
| CHI | 4519 | 1267 | 0.0166 | 0.0041 | 4.06x |
| DEN | 5023 | 763 | 0.0136 | 0.0029 | 4.73x |
| LAX | 4760 | 1026 | 0.0097 | 0.0021 | 4.60x |
| MIA | 4607 | 1179 | 0.0121 | 0.0012 | 10.22x |
| NY | 4235 | 1551 | 0.0193 | 0.0069 | 2.79x |

## Recommendation

At least one pass criterion was not met. Per the methodology lock-in (no post-data criterion tuning), the project ends here. EC-1 is not a tradable hypothesis at this scale and infrastructure. The engineering artifacts remain in the repo as a reference implementation.
