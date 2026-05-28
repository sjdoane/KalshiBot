# Agent V3-C: Polymarket vs Kalshi Divergence Analysis

**Date:** 2026-05-24
**Author:** Agent V3-C (Phase 1, Polymarket-leads-Kalshi thesis assessment)
**Status:** Research only. Read-only public APIs. No trading.
**Scope:** v1-eligible-style long-horizon MLB Kalshi markets (favorite YES >= 0.70, lifetime 30 to 180 days).

---

## TLDR verdict

**Borderline, leaning Killed.** The "Polymarket leads Kalshi" thesis does NOT hold in the direction v3 needed for it to be tradeable at v1's eligible band.

| Question | Answer |
|---|---|
| Can we match Kalshi to Polymarket events programmatically? | **Yes, 13 of 20 = 65%** with deterministic slug construction. Above the 50% blocker threshold. |
| Are Polymarket prices available at Kalshi's T-35d entry timestamp? | **Yes, 13 of 13 confident matches** had hourly CLOB history. 100% availability. |
| Is the typical Kalshi minus Polymarket divergence > 5 cents at T-35d? | **Yes, 5 of 11 = 45%** of pairs had absolute divergence > 5 cents. |
| Does Kalshi converge toward Polymarket between T-35d and T-7d? | **Yes**, mean absolute spread shrinks from 10.7c (T-35d) -> 4.4c (T-7d). Then DIVERGES again at T-1d because Kalshi races to resolution faster than Polymarket. |
| Is Polymarket better calibrated than Kalshi on this sample? | **Yes**. On strict-eligible pairs (n=5), Kalshi Brier = 0.264, Polymarket Brier = 0.192. Polymarket is ~7pp more accurate. |
| Does Polymarket lead Kalshi (i.e., Kalshi corrects toward Polymarket)? | **NO.** Kalshi prices favorites HIGHER than Polymarket; the realized outcome rate (60%) sits closer to Polymarket's view (65%) than Kalshi's view (85%). Polymarket is more skeptical and more correct. |
| Does the candidate v3 signal (Kalshi cheaper than Polymarket by 5c) trigger? | **NO.** Zero of 11 pairs at T-35d had Kalshi < Polymarket - 5c. The asymmetry is always Kalshi over Polymarket. |
| Settlement divergences (Cardi B / Khamenei equivalents for sports)? | **None observed.** 13 of 13 confident matches resolved YES/NO identically on both platforms. |

**Operator-facing implication.** Polymarket data is INFORMATIVE about v1's eligible markets (Polymarket is more cautious, and that caution is calibrated). But Polymarket information says **v1's favorites are over-priced**, i.e. v1 should buy LESS, not more. A v3 strategy that uses Polymarket as a feature would systematically REDUCE v1's trade entries, not add new ones. This contradicts the "Polymarket leads, Kalshi catches up so go LONG Kalshi YES" thesis from the v2 substack/AhaSignals references.

The narrow positive read: Polymarket-as-second-opinion is a useful FILTER for v1's existing trades, not a generator of NEW trades. That fits hypothesis H3-as-filter, not H3-as-signal. See "Operator decisions" below.

---

## 1. Event-matching feasibility

### 1.1 Method

I sampled 20 Kalshi MLB long-horizon markets from `data/v2/joined_mlb_longhorizon_dataset.parquet`, weighted toward v1's eligibility band:

- All 11 strict v1-eligible markets (favorite YES >= 0.70, lifetime 30-180 days, finalized).
- 9 marginal candidates (favorite YES >= 0.45, same series coverage) for series diversity.

Series mix: 5 KXMLBWINS (season win totals), 6 KXMLBPLAYOFFS, 6 KXMLB{AL,NL}{EAST,CENT,WEST} (division winners), plus a few non-eligible KXMLBPLAYOFFS/KXMLBWINS.

For each Kalshi ticker, I constructed Polymarket queries from the cached `rules_primary` and `title` text, then attempted three strategies in order:

1. **Public-search**: `gamma-api.polymarket.com/public-search?q=<query>`.
2. **Deterministic slug construction**: e.g. KXMLBALEAST-25-NYY -> `al-east-division-winner` event -> per-team market slug `will-the-new-york-yankees-win-the-al-east-division`. Same pattern works for all six divisions and the playoffs event.
3. **Year-substituted slug guess** for win-totals: `mlb-{year}-regular-season-win-totals` etc.

A match was classified **confident** if the candidate event mentions the correct team AND year AND market kind (wins / division / playoffs). The matching code is at `scripts/v3/poly_kalshi_divergence.py`.

### 1.2 Results

| Kalshi market_kind | Sample n | Confident matches | Match rate |
|---|---|---|---|
| Playoffs (KXMLBPLAYOFFS) | 7 | 7 | **100%** |
| Division (KXMLBAL/NL{EAST,CENT,WEST}) | 6 | 6 | **100%** |
| Season win totals (KXMLBWINS) | 7 | 0 | **0%** |
| **Total** | **20** | **13** | **65%** |

**Conclusion.** Above the 50% blocker threshold. Programmatic matching works deterministically for division and playoffs. Season win totals fail because **Polymarket did not list per-team MLB regular-season-win-total markets for the 2025 season** (only the 2026 season has them, at slug `mlb-2026-regular-season-win-totals`). All four candidate slug variants returned 404. This is a season-specific gap, not a structural limitation.

Manual spot-check of the 13 confident matches: all are correct (verified by walking the per-team market slug back to the Kalshi team abbreviation). The slug-based approach has effectively zero false-positive rate because the match is structural (deterministic team-slug substring on the correct event), not text search.

### 1.3 Failure mode for KXMLBWINS

The 5 strict-eligible KXMLBWINS markets in this sample (CHC, HOU, LAA, LAD, MIL at thresholds T70-T90) have NO Polymarket counterpart for 2025. The threshold structure also differs: when KXMLBWINS does exist in 2026 on Polymarket, the thresholds are set independently per team (NYY at 86.5, BOS at 85.5, TB at 78.5, etc.). Kalshi can list multiple thresholds per team (T70, T80, T90, T100). A perfect cross-platform match would require both platforms to have the same threshold for the same team in the same season, which is rare.

This is documented as a partial blocker in `research/v3/blockers/01-poly-matching.md`.

---

## 2. Historical Polymarket price availability at T-35d

For each of the 13 confident matches, I queried the Polymarket CLOB price-history endpoint:

```
GET https://clob.polymarket.com/prices-history?market={yes_token_id}&startTs={t35-3d}&endTs={t35+3d}&fidelity=60
```

(7-day window cap; hourly fidelity.)

### 2.1 Results

| Metric | n | % |
|---|---|---|
| Confident matches with price history at T-35d | 13 of 13 | **100%** |
| Hourly price points returned per 6-day window | 100-145 | dense |

Polymarket markets for division winners and playoff qualifiers were active and quoted continuously through the 2025 season. The CLOB returned 100+ hourly samples per 6-day window, which is denser than Kalshi's trade-only data on the same markets.

### 2.2 Cache layout

Polymarket samples and Kalshi extra trades (for T-21d, T-7d, T-1d windows not covered by the v1 trade cache) are cached under:

- `data/v3/poly_kalshi_pairs.parquet`: per-pair summary table.
- `data/v3/poly_kalshi_priceseries.parquet`: long-format mid prices at all four target timestamps.
- `data/v3/poly_kalshi_divergence_meta.json`: run metadata.
- `data/v3/kalshi_trades_extra/`: cached Kalshi `/historical/trades` payloads pulled at the late timestamps via the READ-scope client (LOCALAPPDATA\KalshiBot\kalshi_prod_read.pem).

---

## 3. Divergence quantification at T-35d

### 3.1 Distribution

For the 11 pairs with BOTH Polymarket and Kalshi prices at T-35d (2 of the 13 confident matches lacked Kalshi trades within the +/-2-day window):

| Stat | Value (Kalshi YES minus Polymarket YES, cents) |
|---|---|
| Mean | **+9.21c** (Kalshi prices favorites higher) |
| Median | +4.53c |
| 25th pct | -1.02c |
| 75th pct | +19.68c |
| Fraction with absolute divergence > 2c | **10 of 11 = 91%** |
| Fraction with absolute divergence > 5c | **5 of 11 = 45%** |
| Fraction with absolute divergence > 15c | **4 of 11 = 36%** |

### 3.2 Direction

The divergence is **asymmetric**: every pair where Kalshi disagreed with Polymarket by >5c had Kalshi HIGHER. Zero pairs had Kalshi cheaper than Polymarket by >5c.

This is the OPPOSITE direction expected by a "Polymarket leads, Kalshi catches up" thesis. If Polymarket led Kalshi UP, we should see Kalshi cheap at T-35d, then converging UP to Polymarket. Instead Kalshi is rich at T-35d, then DOWN-converges toward Polymarket as the season plays out.

### 3.3 Per-pair detail (strict-eligible subset)

| Kalshi ticker | favorite | poly@T-35 | kalshi@T-35 | divergence | resolved |
|---|---|---|---|---|---|
| KXMLBPLAYOFFS-25-SEA | 0.862 | 0.622 | 0.916 | **+0.294** | YES |
| KXMLBPLAYOFFS-25-NYY | 0.868 | 0.727 | 0.921 | **+0.194** | YES |
| KXMLBPLAYOFFS-25-NYM | 0.778 | 0.575 | 0.774 | **+0.199** | NO |
| KXMLBPLAYOFFS-25-HOU | 0.809 | 0.585 | 0.825 | **+0.240** | NO |
| KXMLBPLAYOFFS-25-BOS | 0.752 | 0.734 | 0.834 | +0.100 | YES |
| (KXMLBPLAYOFFS-25-SD)   | 0.940 | 0.989 | (no Kalshi trade in window) | n/a | YES |

Two of the four pairs where Kalshi priced the favorite >= 0.77 ultimately resolved NO (NYM 0.78 -> NO, HOU 0.81 -> NO). In both cases Polymarket priced them substantially lower (0.575 and 0.585 respectively). **Polymarket was the better-calibrated forecaster on these.**

---

## 4. Convergence test

For each pair, I sampled prices at T-21d, T-7d, T-1d.

### 4.1 Mean absolute spread over time

| Timestamp | n | mean(K - P) cents | mean|K - P| cents | median(K - P) cents |
|---|---|---|---|---|
| T-35d | 11 | +9.21 | 10.74 | +4.53 |
| T-21d | 10 | +6.98 | 7.35 | +2.55 |
| T-7d | 12 | +2.86 | 4.44 | -0.59 |
| T-1d | 5 | -9.11 | 11.25 | -0.15 |

### 4.2 Interpretation

- T-35d to T-7d: the mean absolute spread shrinks from 10.74c to 4.44c, a 59% reduction. This IS convergence.
- T-7d to T-1d: the spread blows up again, but with a SIGN FLIP. At T-1d, Kalshi is LOWER than Polymarket by 9c on average. This happens because Kalshi races to 0.99 or 0.01 cleanly on resolution day while Polymarket sometimes lags by 24 hours (or vice versa for losers).
- The convergence is in the direction Kalshi -> Polymarket, NOT Polymarket -> Kalshi. Polymarket starts more cautious; Kalshi prices initially overshoot, then drift down toward Polymarket as the season clarifies.

### 4.3 Statistical significance

Sample is too small (n=11 with both T-35d prices, n=3 with all 4 timestamps) for a formal test. The convergence direction is consistent across all 11 pairs at the population level: mean spread monotonically decreases T-35 -> T-21 -> T-7 (9.21 -> 6.98 -> 2.86 cents). The pattern fits a "Polymarket is right early, Kalshi corrects" story, NOT the reverse.

---

## 5. Settlement-divergence audit

For all 13 confident matches that have already settled (the 2025 MLB season concluded September 29, 2025):

| Kalshi ticker | Kalshi outcome | Polymarket outcome | Agree? |
|---|---|---|---|
| KXMLBPLAYOFFS-25-SEA | 1 | 1 | YES |
| KXMLBPLAYOFFS-25-SD | 1 | 1 | YES |
| KXMLBPLAYOFFS-25-NYY | 1 | 1 | YES |
| KXMLBPLAYOFFS-25-NYM | 0 | 0 | YES |
| KXMLBPLAYOFFS-25-HOU | 0 | 0 | YES |
| KXMLBPLAYOFFS-25-BOS | 1 | 1 | YES |
| KXMLBALCENT-25-DET | 0 | 0 | YES |
| KXMLBALEAST-25-TOR | 1 | 1 | YES |
| KXMLBALWEST-25-HOU | 0 | 0 | YES |
| KXMLBNLCENT-25-MIL | 1 | 1 | YES |
| KXMLBNLEAST-25-PHI | 1 | 1 | YES |
| KXMLBNLWEST-25-LAD | 1 | 1 | YES |
| KXMLBPLAYOFFS-25-TOR | 1 | 1 | YES |

**Agreement: 13 of 13 = 100%.** No Cardi B or Khamenei type events on MLB long-horizon markets in this 2025 sample.

This was expected: sports markets have unambiguous objective resolution criteria (won the division yes or no; made the playoffs yes or no). Resolution-source divergence affects entertainment and political markets primarily. For v3's domain (long-horizon sports), Polymarket-as-feature does not carry resolution-divergence risk.

---

## 6. Verdict and operator-facing summary

### 6.1 Bucket placement: **Borderline**, leaning Killed

Per the master plan thresholds:

| Threshold | Result | Pass? |
|---|---|---|
| Match rate > 50% | 65% | YES |
| Match rate > 30% | 65% | YES |
| Divergence > 5c rate > 20% | 45% | YES |
| Convergence statistically significant | Direction is clear; n too small for p-value | Partial |

Headline criteria all pass, which by the master plan literal would put this in **Tradeable**. BUT the direction of the divergence kills the originally-hypothesized strategy:

- The thesis was: Polymarket leads Kalshi; Kalshi cheap relative to Polymarket implies an undervalued YES; v3 buys Kalshi YES on those deviations.
- The data shows: Kalshi prices favorites HIGHER than Polymarket; Polymarket is BETTER CALIBRATED (Brier 0.192 vs Kalshi 0.264 on n=5 eligibles); the "Kalshi cheap" signal NEVER FIRED in this sample (0 of 11 pairs).

So while Polymarket carries genuine signal, the signal says **Kalshi favorites are over-priced**, which would tell a v3 model to do LESS of v1's trading, not more. The thesis as stated is **falsified for this domain in this direction**.

### 6.2 What Polymarket actually tells us

A reformulated v3 hypothesis that DOES fit the data:

> **H3-prime (Polymarket as fade-filter)**: when Polymarket prices a v1-favorite below Polymarket-implied 0.70, fade or skip the v1 trade. Use Polymarket as a "second opinion" filter that REMOVES v1 trades that are most likely to be Kalshi overpricing.

This would reduce v1's trade count rather than increase it. Given v1 is currently making +12.5pp on n=39 (Round 7) at 100% YES rate, and the eligible n is already small, fading two of every five trades on a Polymarket disagreement would:

- Probably improve hit rate (Polymarket caught two of five eligible NO outcomes in this sample).
- Cut sample size further (39 -> ~24), which makes statistical inference harder.
- Not generate any NEW trades.

This is not what v3 was authorized to build. v3 was authorized to ADD external features that GENERATE additional or better trades. Polymarket-as-fade-filter is a defensive overlay on v1, not a new strategy.

### 6.3 Expected edge if v3-as-stated is built anyway

Suppose we ignore the direction and build the model regardless. The mean divergence at T-35d is +9.2c with Kalshi > Polymarket. To trade Kalshi YES profitably we would need Polymarket > Kalshi by enough to overcome 2c Kalshi taker fees (1c maker if filled). The signal that needs to fire NEVER FIRES in this sample (0 of 11). Expected trades per season at this sample shape: **zero**.

Sample is small (n=11) so the true firing rate is likely 0-30%, not exactly zero. But for v1's eligibility band the asymmetry is structural: Kalshi taker liquidity on long-horizon favorites attracts retail flow that prices the favorites up to 0.85-0.95 even when the underlying base rate is 0.60-0.75. Polymarket's election-adjacent audience prices the same favorites at the lower implied probability.

A model that learns "Polymarket priced this lower than Kalshi" will not find Kalshi-cheap markets to long; it will find Kalshi-rich markets to fade or short. v1's bot only longs YES. v3-as-Kalshi-only-longer is functionally dead.

### 6.4 Recommended next step

Three options for the orchestrator:

1. **Pivot the v3 hypothesis** to "use Polymarket as a fade filter on v1" (Polymarket-as-second-opinion in DEFENSIVE form). Lower payoff than v3's original thesis. Easier to validate with the n we have.
2. **Kill the Polymarket-feature track and focus v3 on non-market external features** (FanGraphs, injury reports, etc., per Agent V3-B's audit). Polymarket carries signal but in the wrong direction for v1's trade selection.
3. **Pivot away from v1's long-only favorite band** and explore whether SHORT-YES (i.e., buy NO at 0.10-0.30 when Polymarket prices it higher than Kalshi) is tradeable. This requires v1 to start placing NO orders, which is a strategy change, not a v3 model add-on.

My recommendation as Agent V3-C: option 2 (kill Polymarket-as-feature track) plus document option 1 (Polymarket-as-fade-filter) for a future Phase 2 if the orchestrator wants a small-edge defensive overlay. The clean answer in the bucket framework is **Borderline (filter use case)**, NOT Tradeable for v3's authorized goal.

---

## 7. Caveats and unknowns

1. **Sample size.** n=11 pairs with both prices at T-35d is small. Direction of the asymmetry is consistent across all 11 pairs but the magnitude estimates have wide CIs. A Phase 2 expansion to 2023-2024 seasons would 3x the sample.

2. **MLB only.** This analysis covers only MLB long-horizon markets. NFL season-wins, NBA championship futures, and NHL division markets may show different patterns. v1 trades 4 leagues; this analysis covered 1.

3. **2025 season only.** This was a year where strong favorites (SEA, NYY, SD, LAD, MIL, PHI) heavily outperformed regression-to-mean models. The Brier gap might shrink in a less favorite-friendly season.

4. **Polymarket liquidity check skipped.** The 13 confident matches all had hourly price history available, but I did not audit ORDER-BOOK DEPTH at T-35d. If Polymarket's quoted mids are reliable indicators of fair value (not just one-trade-stale prices), the conclusions hold. If Polymarket mids are noisy due to thin retail flow, the divergence statistics overstate the true signal.

5. **Kalshi VWAP method.** I used trade-weighted average price within a +/-2 day window around each target timestamp. Where trades were sparse, this defaults to simple mean. For two pairs (SEA, SD playoffs) no Kalshi trades occurred within the T-35d window even after authenticated fetch, so divergence is missing.

6. **Convergence direction caveat.** The T-7d -> T-1d sign flip suggests Kalshi MAY be the better short-horizon forecaster while Polymarket is the better long-horizon one. This is consistent with the "different audience" structural story: Polymarket has more sophisticated long-horizon traders, Kalshi has more retail betting-line followers who react to in-season news faster.

---

## 8. Output artifacts

| Path | Contents |
|---|---|
| `data/v3/poly_kalshi_pairs.parquet` | 20 rows: match status + Polymarket and Kalshi mids at T-35d/T-21d/T-7d/T-1d + Polymarket resolution. |
| `data/v3/poly_kalshi_priceseries.parquet` | Long-format mids at each timestamp. |
| `data/v3/poly_kalshi_divergence_meta.json` | Summary stats and run metadata. |
| `data/v3/kalshi_trades_extra/` | Cached Kalshi `/historical/trades` payloads for T-21d, T-7d, T-1d windows. |
| `scripts/v3/poly_kalshi_divergence.py` | Reproducible end-to-end script. Run via `KALSHI_PRIVATE_KEY_PATH=...kalshi_prod_read.pem uv run python -m scripts.v3.poly_kalshi_divergence`. |
| `scripts/v3/match_kalshi_to_polymarket.py` | Earlier text-search variant (kept for the comparison docs). |
| `research/v3/blockers/01-poly-matching.md` | Notes on the 7 of 20 markets that did not match (5 KXMLBWINS for 2025 + 2 trades-availability gaps). |

---

## 9. Reproducibility note

To re-run this analysis with the read-scope key:

```powershell
$env:KALSHI_PRIVATE_KEY_PATH = 'C:\Users\SamJD\AppData\Local\KalshiBot\kalshi_prod_read.pem'
uv run python -m scripts.v3.poly_kalshi_divergence
```

Total runtime ~70 seconds. All Polymarket calls are unauthenticated; only Kalshi `/historical/trades` requires the read key.
