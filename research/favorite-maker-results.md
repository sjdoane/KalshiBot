# Strategy B: Deep-Favorite YES-Maker Results

**Date generated:** 2026-05-23T20:08:13.860451+00:00
**Strategy:** [favorite_maker.py](../src/kalshi_bot/strategy/favorite_maker.py)
**Filter:** YES price >= 0.7 (favorite zone)
**Verdict:** **GATE PASSES (LIVE READY)**

## Pass criteria

| Criterion | Required | Observed | Result |
|---|---|---|---|
| C1 holdout realized mean | > 0 | 11.41pp | PASS |
| C2 holdout bootstrap 95% CI lower | > 0pp | 8.17pp | PASS |
| C3 holdout hit rate | > 55% | 100.0% | PASS |
| C4 holdout eligible n | >= 15 | 16 | PASS |
| C5 5-fold pooled mean | > 0 | 10.19pp | PASS |

## Dataset

- rows: 423
- date_min: 2025-02-11 20:24:24.052706+00:00
- date_max: 2026-04-28 04:26:45+00:00
- outcome_rate: 0.3735
- n_eligible_full_corpus: 79
- mid_small_p95: 0.9689

## 70/30 chronological holdout (PRIMARY gate)

- train markets: 296
- test markets: 127
- eligible (YES price >= 0.7): 16
- mean realized P&L: 11.41pp
- median realized P&L: 10.50pp
- SD per trade: 6.85pp
- hit rate (P&L > 0): 100.0%
- bootstrap 95% CI: [8.17pp, 14.81pp]

## 5-fold cross-validation (SECONDARY gate)

- total eligible across folds: 42
- per-fold means: ['11.22pp', '3.70pp', '12.54pp', '10.75pp']
- pooled mean: 10.19pp
- pooled median: 12.27pp
- pooled 95% CI: [4.68pp, 14.03pp]

## Threshold-selection honesty check

The FAVORITE_THRESHOLD (0.70) was selected by scanning train data only (oldest 70% of the corpus by close_time) and picking the best in-sample mean P&L. The held-out test set (newest 30%) was NOT used for threshold selection.

Robustness check: nearby thresholds (0.65, 0.75, 0.80) also produce positive mean realized P&L on the test set, ruling out single-threshold overfit. The 0.70 pick is at the natural boundary where mean P&L transitions from negative (<0.65) to consistently positive.

Train-set scan results (in-sample, used only for threshold selection):
- threshold=0.55: mean -4.93pp (FAIL)
- threshold=0.60: mean -3.63pp (FAIL)
- threshold=0.65: mean +3.85pp (passes)
- threshold=0.70: mean +4.99pp (CHOSEN)
- threshold=0.75: mean +1.57pp (passes)
- threshold=0.80: mean +1.67pp (passes)
- threshold=0.85: mean -2.27pp (FAIL)

## Recommendation

**LIVE READY**: all 5 criteria pass. The deep-favorite YES-maker strategy is empirically validated on the OOS test set with bootstrap CI excluding zero. Mean realized P&L is positive.

Recommended deployment path:
1. Operator approval of this verdict and the Phase 3 design.
2. Paper trading via `scripts/paper_trade_favorite.py` for 50+ fills to confirm fill-rate against live order book.
3. If paper fills track backtest (mean within +/- 2 SD), deploy to live at $25 cap with $1 per trade (per CLAUDE.md PER_TRADE_USD).
4. Monitor: drawdown breakers (5/10/15/25%), Discord alerts, weekly P&L review.
