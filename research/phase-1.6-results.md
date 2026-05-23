# Phase 1.6 Results: Zerve Out-of-Sample Replication

**Date generated:** 2026-05-23T06:26:18.882790+00:00
**Methodology:** [phase-1.5-methodology.md](phase-1.5-methodology.md)
**Window:** [open + 1h, open + 13h]
**Verdict:** **GATE FAILS**

## Pass criteria

| Criterion | Required | Observed | Result |
|---|---|---|---|
| C1 median OOS ECE improvement | >= 5x | 1.44x | FAIL |
| C2 median shoulder gross edge | >= 2pp | 1.49pp | FAIL |
| C3 at least 4 splits with >= 3x | >= 4 | 0 | FAIL |
| C4 leave-one-city-out positive | >= 3 of 5 | 4 of 5 | PASS |
| C5 shoulder net edge (after fees) | > 0 | -0.51pp | FAIL |

## Dataset

- rows: 24744
- cities: ['CHI', 'DEN', 'LAX', 'MIA', 'NY']
- date_min: 2021-08-06
- date_max: 2026-04-28
- outcome_rate: 0.2132
- mid_price_p05: 0.0202
- mid_price_p50: 0.1967
- mid_price_p95: 0.5124
- window: [open + 1h, open + 13h]

## Informational (not part of pass criteria)

- median hit rate on trades > 2pp edge: 82.0% (50% = no directional skill)
- median realized P&L per contract after maker fees: $0.0790

## Walk-forward splits

| Split | n_train | n_test | raw ECE | cal ECE | ratio | shoulder edge | net edge | hit rate >2pp | median PnL/contract |
|---|---|---|---|---|---|---|---|---|---|
| wf_01_2024-01-01_to_2024-08-05 | 8386 | 403 | 0.0516 | 0.0487 | 1.06x | 1.51pp | -0.49pp | 64.2% | $0.0811 |
| wf_02_2024-01-31_to_2024-09-04 | 8818 | 386 | 0.0553 | 0.0476 | 1.16x | 1.82pp | -0.18pp | 59.4% | $0.0799 |
| wf_03_2024-03-01_to_2024-10-04 | 9229 | 352 | 0.0398 | 0.0610 | 0.65x | 1.92pp | -0.08pp | 58.4% | $0.0766 |
| wf_04_2024-03-31_to_2024-11-03 | 9622 | 331 | 0.0614 | 0.0506 | 1.21x | 2.06pp | 0.06pp | 59.2% | $0.0700 |
| wf_05_2024-04-30_to_2024-12-03 | 9974 | 555 | 0.0350 | 0.0255 | 1.37x | 2.05pp | 0.05pp | 71.7% | $0.0841 |
| wf_06_2024-05-30_to_2025-01-02 | 10480 | 620 | 0.0205 | 0.0218 | 0.94x | 1.94pp | -0.06pp | 72.6% | $0.0804 |
| wf_07_2024-06-29_to_2025-02-01 | 11158 | 715 | 0.0470 | 0.0310 | 1.52x | 1.76pp | -0.24pp | 75.1% | $0.0862 |
| wf_08_2024-07-29_to_2025-03-03 | 11887 | 775 | 0.0362 | 0.0229 | 1.58x | 1.59pp | -0.41pp | 75.9% | $0.0877 |
| wf_09_2024-08-28_to_2025-04-02 | 12700 | 735 | 0.0426 | 0.0325 | 1.31x | 1.46pp | -0.54pp | 83.1% | $0.0952 |
| wf_10_2024-09-27_to_2025-05-02 | 13482 | 739 | 0.0382 | 0.0245 | 1.56x | 1.38pp | -0.62pp | 79.2% | $0.0923 |
| wf_11_2024-10-27_to_2025-06-01 | 14285 | 738 | 0.0390 | 0.0270 | 1.45x | 1.19pp | -0.81pp | 82.4% | $0.0816 |
| wf_12_2024-11-26_to_2025-07-01 | 15078 | 749 | 0.0299 | 0.0273 | 1.09x | 1.36pp | -0.64pp | 79.8% | $0.0789 |
| wf_13_2024-12-26_to_2025-07-31 | 15869 | 753 | 0.0484 | 0.0267 | 1.81x | 1.43pp | -0.57pp | 85.0% | $0.0744 |
| wf_14_2025-01-25_to_2025-08-30 | 16690 | 751 | 0.0500 | 0.0265 | 1.88x | 1.35pp | -0.65pp | 84.3% | $0.0641 |
| wf_15_2025-02-24_to_2025-09-29 | 17481 | 739 | 0.0271 | 0.0353 | 0.77x | 1.36pp | -0.64pp | 81.6% | $0.0593 |
| wf_16_2025-03-26_to_2025-10-29 | 18279 | 787 | 0.0505 | 0.0220 | 2.29x | 1.40pp | -0.60pp | 87.6% | $0.0736 |
| wf_17_2025-04-25_to_2025-11-28 | 19103 | 793 | 0.0421 | 0.0259 | 1.62x | 1.56pp | -0.44pp | 85.5% | $0.0791 |
| wf_18_2025-05-25_to_2025-12-28 | 19956 | 839 | 0.0377 | 0.0243 | 1.55x | 1.64pp | -0.36pp | 86.1% | $0.0720 |
| wf_19_2025-06-24_to_2026-01-27 | 20846 | 840 | 0.0161 | 0.0254 | 0.63x | 1.25pp | -0.75pp | 86.5% | $0.0683 |
| wf_20_2025-07-24_to_2026-02-26 | 21746 | 840 | 0.0563 | 0.0393 | 1.43x | 1.40pp | -0.60pp | 89.9% | $0.0812 |
| wf_21_2025-08-23_to_2026-03-28 | 22646 | 840 | 0.0227 | 0.0119 | 1.90x | 1.40pp | -0.60pp | 87.7% | $0.0729 |
| wf_22_2025-09-22_to_2026-04-27 | 23546 | 838 | 0.0370 | 0.0192 | 1.93x | 1.51pp | -0.49pp | 86.0% | $0.0708 |

## Leave-one-city-out

| Held-out city | n_train | n_test | raw ECE | cal ECE | ratio |
|---|---|---|---|---|---|
| CHI | 17514 | 7230 | 0.0211 | 0.0144 | 1.46x |
| DEN | 21783 | 2961 | 0.0293 | 0.0204 | 1.44x |
| LAX | 22084 | 2660 | 0.0317 | 0.0095 | 3.33x |
| MIA | 20056 | 4688 | 0.0294 | 0.0215 | 1.37x |
| NY | 17539 | 7205 | 0.0136 | 0.0141 | 0.97x |

## Recommendation

At least one pass criterion was not met. Per the methodology lock-in (no post-data criterion tuning), the project ends here. EC-1 is not a tradable hypothesis at this scale and infrastructure. The engineering artifacts remain in the repo as a reference implementation.
