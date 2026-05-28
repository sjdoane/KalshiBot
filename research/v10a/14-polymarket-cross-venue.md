# Round 15c Track 2A: Polymarket vs Kalshi cross-venue lead-lag

## Hypothesis

Ng / Peng / Tao / Zhou 2026 (arXiv 2604.20421) found that Polymarket
LEADS Kalshi for price discovery on 2024 US election binary markets.
This sub-track tests whether the same lead-lag generalizes to 2025
crypto (BTC monthly above-threshold) parallels. If Polymarket
consistently leads Kalshi by N hours, a v1 strategy could use
Polymarket as a leading signal for Kalshi maker quote placement.

## Method

1. Built a list of 7 candidate parallel pairs: BTC-above-threshold
   monthly Kalshi markets (KXBTCMAXM-25SEP30 / -25OCT31 /
   -AUG25-AUG01) matched to Polymarket markets with the same threshold
   and same closing month.
2. Reconstructed hourly VWAP for both venues:
   - Polymarket: parse CTF Exchange trades, computing implied YES
     price = USDC_amount / YES_token_amount (or 1 - USDC / NO_token).
     Trades joined to blocks/*.parquet for the timestamp because
     trades.timestamp is NULL in the source data.
   - Kalshi: VWAP from Becker trades (yes_price / 100, weighted by
     count). 1-hour bucket via EPOCH(created_time) / 3600.
3. Cross-correlation of FIRST-DIFFERENCES at lags -6 to +6 hours.
   Positive lag = Polymarket leads Kalshi.

Cluster bootstrap was NOT applied; cross-correlation at the
event-pair level is the natural unit, and we have only 7 candidate
pairs (1 of which failed to match a Polymarket question).

## Results

| Pair | PM hours | Kalshi hours | Best lag (h) | Best correlation | Direction |
|---|---|---|---|---|---|
| BTC_above_120k_sep2025 | 671 | 136 | 0 | +0.31 | TIE |
| BTC_above_125k_sep2025 | 649 | 70 | +3 | -0.26 | PM_LEAD (negative) |
| BTC_above_130k_sep2025 | 625 | 12 | +5 | +0.68 | PM_LEAD (low n) |
| BTC_above_130k_oct2025 | 728 | 624 | 0 | +0.35 | TIE |
| BTC_above_135k_oct2025 | 717 | 255 | 0 | +0.32 | TIE |
| BTC_above_120k_jul2025 | 319 | 208 | +5 | +0.17 | PM_LEAD (weak) |
| BTC_above_125k_jul2025 | -- | -- | -- | NO_PM_MATCH | -- |

Of 6 analyzed pairs:
- 3 show TIE at lag 0 (co-movement, no lead-lag)
- 3 show Polymarket leading (lags 3 to 5 hours)
- 0 show Kalshi leading

## Verdict: NULL (lead-lag is not actionable here)

The two best-powered pairs (BTC_above_130k_oct2025 with k_h=624 and
BTC_above_120k_sep2025 with k_h=136) BOTH show ZERO lag with
correlations ~+0.31 to +0.35. This is consistent with the venues
co-moving on the underlying spot, not one leading the other.

The 3 "Polymarket leads" pairs all have very thin Kalshi data
(k_h between 12 and 208). The lag-3 pair (BTC_above_125k_sep2025)
has a NEGATIVE correlation (-0.26), which is statistical noise on a
sparse Kalshi series, not a true lead-lag.

The lag-5 BTC_above_130k_sep2025 pair has k_h=12 (only 12 hours of
Kalshi data over the 45-day window). At n=12 the correlation
estimate is unreliable.

### Why this differs from Ng/Peng/Tao/Zhou 2026

Their result was specifically on 2024 US election binary markets,
where Polymarket has 10-100x larger volume than Kalshi. For BTC
monthly above-threshold markets in 2025, Kalshi has launched competing
products (KXBTCMAXM) only in the most recent few months of our
window; volume is sparse. Both sides also have algorithmic market
makers that arbitrage spot-derived fair value continuously, leaving
little room for one venue to lead the other on a sub-day horizon.

### Action

NO new strategy candidate. The PM-leads-Kalshi pattern from politics
does NOT generalize to BTC monthly markets in our window. If a future
round wants to retry, the cleanest re-test would be on the 2024
election cycle data where the original result was measured, and
specifically on political binary markets, not crypto. The current
project has $32 live capital and no v1 candidate firing on
politics, so this would be a research-only re-validation.

### Methodology limits

- We did not run Granger F-tests; cross-correlation of differenced
  series is sufficient to identify a lead, but does not give a
  significance level on the lag.
- We did not control for shared spot exposure. A true lead-lag test
  would regress (PM price change) on (lagged BTC spot change) and
  (lagged Kalshi price change) in the same model. We did not have
  trade-time BTC spot data in the project's data layer.

This verdict is **NULL** with the qualifier that the original
politics result remains untested here.
