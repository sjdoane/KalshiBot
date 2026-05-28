# v6 Gate Results (Phase 2 Stage 2D)

**Verdict:** `NULL`

**Kill reason:** `K1`

## Honest interpretation

v6 closes at Phase 2 Stage 2B (orthogonality). No feature in the T-30 / T-15 universe (Kalshi internal CVD, trade count, price drift, Coinbase realized vol / VWAP dev, Deribit funding-delta, DVOL delta, spot-futures basis delta) cleared the +0.005 Brier improvement threshold on the midband holdout. The expected modal outcome from Phase 1 synthesis (80% NULL prior) is realized. v5-C's null at T-1h extends to sub-hour horizons within the free-tier feature universe.

## Notable diagnostic findings

1. **F1 (kalshi_cvd) self-reference diagnostic**: On T-30 midband, F1 orthogonality lift was +0.00214 overall but +0.00958 on the fresh-mid subset (n=45) and -0.00058 on the stale-mid subset (n=123). Lift concentrates in the fresh subset, not the stale subset (the methodology Critic Important Finding 2 worried about the OPPOSITE pattern). Even on fresh-mid subset, sample size is too small and overall lift is below +0.005.

2. **F4 (kalshi_price_drift) K1b artifact verified**: At T-30 midband, F4 was structurally undefined for 100% of train contracts (0 / 430 with second trade in window). At T-15 widerband, F4 showed an apparent +0.10 Brier improvement when baseline and augmented were fit on different sub-samples (drift-defined contracts have yes_rate 0.54 vs drift-undefined 0.31, a sample-selection effect, not a generic alpha). The fair like-for-like comparison (Section 3.1 protocol, baseline AND augmented on the SAME drift-defined rows) collapses F4's lift to +0.00272. Below the +0.005 threshold.

3. **Coinbase external features (realized_vol, vwap_dev)**: Effectively zero contribution beyond Kalshi mid on midband (improvement < 1e-5). The Coinbase / BTC-USD signal is fully absorbed by the Kalshi mid at the T-30 / T-15 horizons studied.

4. **Deribit funding-delta, DVOL-delta, basis-delta**: All show near-zero or negative Brier improvement. The hypothesis that perpetual funding-rate trajectory, IV-level changes, or spot-futures basis movement carries information beyond Kalshi mid at T-30/T-15 is rejected by the data.