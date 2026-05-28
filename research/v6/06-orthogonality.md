# v6 Orthogonality Results (Phase 2 Stage 2B)

Per phase-1.5-methodology.md Section 3. Each candidate feature is tested for Brier improvement on a held-out 25% chronological slice above the baseline `kalshi_mid_at_t`. Pass criterion: Brier improvement >= 0.005.

## Build summary

- Rows total: 3688
- Midband (mid in [0.55, 0.80]): 971
- Widerband (mid in [0.20, 0.80]): 1382
- Midband yes_rate: 0.7559217301750772
- Date range: ['2024-12-12 10:00:00+00:00', '2026-03-24 23:00:00+00:00']

## Overall K1 verdict

`K1_NULL_NO_FEATURES_PASS`

- Midband passes (horizon, feature): `[]`
- Widerband passes: `[]`

## Per-horizon detail

### Horizon T-30 min

- Band used: **midband**
- n_train: 430, n_orth_holdout: 168
- F4 drift defined in train (K1b guard): n=0

#### Correlation pre-screen drops (|rho| > 0.85)

None.

#### Feature orthogonality test

| feature | Brier base | Brier aug | improvement | n_test | pass +0.005 |
|---|---|---|---|---|---|
| `kalshi_cvd_30` | 0.27971 | 0.27756 | 0.00214 | 168 | False |
| `kalshi_trade_count_30` | 0.27971 | 0.31297 | -0.03326 | 168 | False |
| `coinbase_realized_vol_30` | 0.28757 | 0.28757 | -0.00000 | 168 | False |
| `coinbase_vwap_dev_30` | 0.28757 | 0.28756 | 0.00000 | 168 | False |
| `time_since_last_trade_at_t` | 0.27971 | 0.30265 | -0.02294 | 168 | False |
| `funding_rate_delta_4h_at_t` | 0.27964 | 0.27964 | 0.00000 | 168 | False |
| `dvol_delta_1h_at_t` | 0.27971 | 0.28013 | -0.00042 | 168 | False |
| `basis_delta_1h_at_t` | 0.27971 | 0.27980 | -0.00009 | 168 | False |

**n_passed: 0**
Passed features: `[]`

#### F1 self-reference diagnostic (Section 3.5)

Holdout split by `time_since_last_trade < 5 min` (fresh) vs >= 5 min (stale). F1 lift on each subset:

- n_stale: 123, n_fresh: 45
  - stale: n=123, lift=-0.0005762367097705834
  - fresh: n=45, lift=0.009579852805059602

### Horizon T-15 min

- Band used: **widerband**
- n_train: 325, n_orth_holdout: 131
- F4 drift defined in train (K1b guard): n=267

#### Correlation pre-screen drops (|rho| > 0.85)

None.

#### Feature orthogonality test

| feature | Brier base | Brier aug | improvement | n_test | pass +0.005 |
|---|---|---|---|---|---|
| `kalshi_cvd_15` | 0.37309 | 0.37534 | -0.00224 | 131 | False |
| `kalshi_trade_count_15` | 0.37309 | 0.44344 | -0.07035 | 131 | False |
| `kalshi_price_drift_15` | 0.27441 | 0.27169 | 0.00272 | 64 | False |
| `coinbase_realized_vol_15` | 0.37351 | 0.37351 | 0.00000 | 131 | False |
| `coinbase_vwap_dev_15` | 0.37351 | 0.37351 | -0.00000 | 131 | False |
| `time_since_last_trade_at_t` | 0.37309 | 0.41373 | -0.04064 | 131 | False |
| `funding_rate_delta_4h_at_t` | 0.37185 | 0.37185 | -0.00000 | 131 | False |
| `dvol_delta_1h_at_t` | 0.37309 | 0.37277 | 0.00032 | 131 | False |
| `basis_delta_1h_at_t` | 0.37255 | 0.37257 | -0.00001 | 131 | False |

**n_passed: 0**
Passed features: `[]`

#### F1 self-reference diagnostic (Section 3.5)

Holdout split by `time_since_last_trade < 5 min` (fresh) vs >= 5 min (stale). F1 lift on each subset:

- n_stale: 41, n_fresh: 90
  - stale: n=41, lift=-0.001428188465908642
  - fresh: n=90, lift=-0.0026152762462234858
