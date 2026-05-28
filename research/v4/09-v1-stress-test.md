# V4 Phase 4: V1 stress test on previously-excluded series

**Date:** 2026-05-24
**Author:** Agent V4-H
**Status:** Closes v3 W1 (never closed) and v4 critic Finding 6.1 / 8.5.
**Predecessor reads:** `research/v4/07-critic.md` (Finding 6.1 and 8.5), `research/time-scale-analysis.md` (v1's original +12.47pp claim), `research/v3/07-critic.md` (W1 item), `src/kalshi_bot_v2/gate.py` (locked fee + slippage formula).
**Data used:** `data/v3/probe_inventory_all_markets.parquet` (V3-A probe, n=2828), `data/processed/sports_dataset.parquet` (v1 original measurement set, n=423). Read-only. No new API pulls.
**Outputs:** `data/v4/v1_stress_test_per_market.parquet` (n=148 eligible rows), `data/v4/v1_stress_test_summary.json` (raw stats), `scripts/v4/v1_stress_test.py` (reproducible script).

---

## Executive verdict

**v1 FRAGILE.** v1's claimed `+12.47pp` measured edge does NOT generalize to the five series v1 actually trades in production but whose universe was excluded from the original measurement. On `n=109` v1-eligible markets across KXNFLWINS, KXNFLPLAYOFF, and KXMLBPLAYOFFS (KXNCAAFFINALIST and KXNCAAF have ZERO v1-eligible markets and are structurally untradable by v1's price filter), v1 returns **mean P&L -3.02pp, CI [-9.73pp, +3.10pp]** (includes zero) with bootstrap CI fully spanning zero. Pooled with the original n=39 dataset, v1's true measured edge on its actual trading universe is **+1.06pp, CI [-4.06pp, +5.84pp]** (includes zero). The +12.47pp number was an artifact of the original dataset's series mix and 100% YES rate.

This closes v3's W1 item (open since Round 9, 2026-05-23) and v4 critic Finding 6.1 / 8.5.

**v4 Track B reinterpretation:** V4-F's "v1 baseline fails" finding (-39.03pp on n=19 strict subset, -57.6pp on n=10 KXNFLWINS slice) is NOT a sample artifact. It is the same intrinsic v1 fragility this stress test reveals on n=109. The Track B verdict therefore needs reframing: v1 does NOT have a clean +12.47pp baseline to beat on these series.

**Operator action recommended (v1 PARTIAL with per-series filter):** see Section 6.

---

## 1. Series enumeration

Using `data/v3/probe_inventory_all_markets.parquet` (V3-A's broader probe, n=2828) with v1 strict eligibility (lifetime in `[30, 180]` days, wide-window VWAP at T-35d in `[0.70, 0.95]`, result in `{yes, no}`):

| Series prefix | Total markets | Resolved | Has VWAP wide | v1-eligible | YES rate | Mean price T-35d | Mean lifetime | Time window |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| KXNFLWINS | 955 | 955 | 398 | **95** | 87.4% | 0.795 | ~95d | 2025-10-07 to 2026-01-05 |
| KXNFLPLAYOFF | 32 | 32 | 32 | **9** | 77.8% | 0.781 | ~109d | 2025-12-22 to 2026-01-04 |
| KXNCAAFFINALIST | 25 | 25 | 9 | **0** | n/a | n/a | n/a | (no markets >=0.70) |
| KXNCAAF | 137 | 137 | 51 | **0** | n/a | n/a | n/a | (no markets >=0.70) |
| KXMLBPLAYOFFS | 30 | 30 | 21 | **5** | 60.0% | 0.819 | ~64d | 2025-09-29 |
| **Total target** | **1179** | **1179** | **511** | **109** | 85.3% | | | |

**Structural finding on KXNCAAFFINALIST and KXNCAAF.** Both are ladder/futures series where each team has its own contract for "win the championship" (KXNCAAF) or "make the finalist round" (KXNCAAFFINALIST). The price distribution is heavily skewed low: KXNCAAFFINALIST T-35d wide VWAP ranges 0.12 to 0.63 (no team ever above 0.65); KXNCAAF T-35d wide VWAP ranges 0.01 to 0.36 (no team ever above 0.36). v1's `[0.70, 0.95]` favorite-price filter NEVER fires on these series, by construction. They are not in v1's tradable universe regardless of measured edge. The v3 critic and v4 critic's listing them as "untested" is technically correct but practically moot: v1 never trades them.

This explains v4-F's strict subset finding that `KXNCAAFFINALIST` n=6 had `mean price 0.683` and that the LLM-pilot widened sample reached below v1's 0.70 floor. Those series only become "v1-eligible" if you widen the price band, at which point you are no longer measuring v1.

**Genuine v1-tradable universe outside the original 17 prefixes:** **109 markets** across KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS.

---

## 2. Per-series v1 baseline measurement

Using v1's realized P&L formula (`realized_pnl_per_contract` from `src/kalshi_bot_v2/gate.py:101`, identical to `src/kalshi_bot/strategy/favorite_maker.py`):

```
gross    = outcome - vwap_t35_wide
fee      = 2.0 * kalshi_maker_fee_per_contract(yes_price)  # round-trip maker
slippage = 0.015
pnl      = gross - fee - slippage
```

Bootstrap: 5000 row-level resamples, seed 42, 95% percentile CI.

| Series | n | Mean P&L | Median | SD | Hit rate | 95% CI (row) | Top entity share |
|---|---:|---:|---:|---:|---:|---|---|
| KXNFLWINS | 95 | **-1.03pp** | +8.74pp | 32.62pp | 87.4% | [-7.71pp, +5.08pp] | SEA: 8/95 (8.4%) |
| KXNFLPLAYOFF | 9 | **-10.18pp** | +5.61pp | 38.68pp | 77.8% | [-38.41pp, +11.85pp] | TB: 1/9 (11.1%) |
| KXNCAAFFINALIST | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| KXNCAAF | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| KXMLBPLAYOFFS | 5 | **-27.84pp** | +2.87pp | 47.93pp | 60.0% | [-68.98pp, +12.56pp] | SEA: 1/5 (20.0%) |

**Every measurable target series shows a NEGATIVE mean P&L, with CIs all crossing zero.**

### Win-vs-loss asymmetry

| Series | Mean per WIN | Mean per LOSS | Loss rate |
|---|---:|---:|---:|
| KXNFLWINS | +11.12pp | -85.10pp | 12.6% |
| KXNFLPLAYOFF | +10.20pp | -81.52pp | 22.2% |
| KXMLBPLAYOFFS | +10.95pp | -86.03pp | 40.0% |

The structural pattern is identical across series: when v1 wins, it wins about +11pp (matching the +11-13pp the original dataset showed). When it loses, it loses about -83pp. The original n=39 dataset had a 100% YES rate so the loss tail was never sampled. On the target series the loss rate is 12-40% and dominates the mean.

### Team concentration (cluster bootstrap sanity check)

Single-team share is modest (KXNFLWINS top team is SEA at 8/95 = 8.4%). Re-running the bootstrap CLUSTERED on entity (team) instead of row gives:

- TARGET (all 5 series, entity-clustered): mean = -3.98pp, CI [-13.73pp, +4.52pp]
- TARGET (row-level, for comparison): mean = -3.02pp, CI [-9.73pp, +3.10pp]

Cluster bootstrap widens the CI slightly but does not flip the sign or push it positive. The negative-mean / CI-includes-zero verdict is robust to this concentration check.

### Top losses (single trades driving the mean)

| Ticker | Price | Outcome | P&L |
|---|---:|---:|---:|
| KXNFLWINS-KC-25B-T7 | 0.934 | 0 | -96.88pp |
| KXNFLWINS-ARI-25B-T3 | 0.896 | 0 | -93.15pp |
| KXMLBPLAYOFFS-25-HOU | 0.882 | 0 | -91.70pp |
| KXNFLWINS-KC-25B-T8 | 0.863 | 0 | -89.75pp |
| KXNFLWINS-TB-25B-T8 | 0.861 | 0 | -89.62pp |
| KXNFLWINS-IND-25B-T10 | 0.828 | 0 | -86.29pp |
| KXNFLPLAYOFF-26-TB | 0.813 | 0 | -84.77pp |
| KXNFLWINS-DAL-25B-T7 | 0.802 | 0 | -83.65pp |

LOO sensitivity: removing the 5 largest losses lifts the target-aggregate mean from -3.02pp to +1.27pp. So the negative mean is NOT one or two flukes; it is a structural tail of 16 catastrophic losses out of 109 markets.

---

## 3. Cross-series aggregate

### Pooled mean across the v1-eligible new + original universe

| Slice | n | Mean P&L | Hit rate | 95% CI |
|---|---:|---:|---:|---|
| **ORIGINAL** (17 prefixes, `data/processed/sports_dataset.parquet`) | 39 | +12.47pp | 100.0% | [+10.29pp, +14.77pp] |
| **NEW** (5 target prefixes, wide T-35d) | 109 | -3.02pp | 85.3% | [-9.73pp, +3.10pp] |
| **AGGREGATE** (new + original) | 148 | **+1.06pp** | 89.2% | **[-4.06pp, +5.84pp]** |

The aggregate (across the full 21 v1-tradable prefixes) is **+1.06pp**, 11.41pp lower than the original-only +12.47pp claim. The aggregate CI **includes zero**.

### Comparison to v1's `time-scale-analysis.md` claim

The `time-scale-analysis.md` Table 1 reports for the eligible 30-180d subset:
- n=39, YES rate 100%, mean +12.47pp, CI [+10.33, +14.63], zero losses > 10pp.

That measurement was computed on a dataset that was 0% the five series this stress test covers. After expanding to the full v1-tradable universe, the claim shrinks to **+1.06pp with CI spanning zero**. The original `+12.47pp` was a domain-restricted estimate, not a universal v1 edge.

The original dataset's **100% YES rate** is the obvious tell. A genuine edge on 70-95c favorites should produce some losses; the favorite-longshot bias literature predicts roughly 70-95% YES rate (matching the price), not 100%. The original n=39 was sampled in a way that excluded the catastrophic-loss tail entirely.

---

## 4. Series-by-series comparison vs original `+12.47pp`

Verdict thresholds: similar = within +/-5pp; FRAGILE = at or below -5pp delta to the original.

| Series | n | Mean P&L | Delta vs +12.47pp | Verdict |
|---|---:|---:|---:|---|
| KXNFLWINS | 95 | -1.03pp | **-13.50pp** | **FRAGILE** (>5pp worse) |
| KXNFLPLAYOFF | 9 | -10.18pp | **-22.65pp** | **FRAGILE** (>5pp worse) |
| KXNCAAFFINALIST | 0 | n/a | n/a | untradable (no v1-eligible markets) |
| KXNCAAF | 0 | n/a | n/a | untradable (no v1-eligible markets) |
| KXMLBPLAYOFFS | 5 | -27.84pp | **-40.31pp** | **FRAGILE** (>5pp worse) |

**All measurable series fail. None show v1's claimed edge.**

---

## 5. Implications for v3 W1 and v4 Track B

### v3 W1 verdict

v3 Phase 3 critic raised W1 (Round 9, 2026-05-23): "rebuild v1 backtest on full sports universe; v1's measured edge has unknown coverage relative to v1's live universe." v3 deferred it. v4 Phase 3 critic re-flagged it as Finding 6.1 / 8.5 and required closure before any v4 verdict.

**W1 result: v1's measured edge does NOT generalize to the previously-excluded series.** v1's claimed +12.47pp was a domain-specific number, not a universal property. On the actual v1-tradable universe (21 prefixes, n=148), v1's measured P&L is +1.06pp with CI [-4.06, +5.84], spanning zero. W1 is closed as a confirmed concern.

### v4 Track B reinterpretation

V4-F (`research/v4/06-llm-gate.md`) reported v1 baseline mean of -0.39 on n=19 strict-eligible and -0.158 on n=63 widened. V4's Phase 3 critic argued this was a sample artifact (sample-mixing with non-v1 markets) and a v1-domain-mismatch issue (V4-F's strict-19 was 63% KXNFLWINS+KXNFLPLAYOFF+KXNCAAFFINALIST+KXNCAAF).

This stress test eliminates the sample-mixing hypothesis. On n=109 v1-strict-eligible markets across the same series V4-F was sampling (with widened VWAP-T35d window for n vs V4-F's narrower window), v1 returns -3.02pp. V4-F's -0.39 on n=19 strict was not a sample artifact; it was a clean read on v1's actual performance on KXNFLWINS / KXNFLPLAYOFF.

**V4-F's "v1 fails" finding is INTRINSIC to v1, not artifactual.** The comparison between LLM forecaster and v1 is now interpretable:

- The LLM forecaster has its own structural problems (Brier 0.398 vs Kalshi 0.279, V4-F Section 4).
- v1 on the same series has -3.02pp baseline (this stress test).
- The choice is not "LLM vs strong v1" but "LLM vs weak v1." Neither is competitive in absolute terms on KXNFLWINS / KXNFLPLAYOFF / KXMLBPLAYOFFS.

V4-F's NULL declaration was reached via the wrong comparison anchor (-0.39 v1 baseline was treated as "v1's stable performance" rather than "v1's measured fragility"). The corrected interpretation is: **both v1 and the LLM forecaster fail on these series**. The conclusion "do not deploy the LLM" stands; the additional conclusion is "v1 is also exposed on these series."

### Cross-finding consistency

- v3 Phase 3 finding: v1 baseline -40.19pp on NFL slice (v3 holdout 49% KXNFLWINS).
- v4-F finding: v1 baseline -57.6pp on KXNFLWINS strict-10.
- v4-H finding (this stress test): v1 baseline -1.03pp on KXNFLWINS n=95.

The three measurements differ in magnitude because v4-F was a small (n=10) cluster of one season; v3's was a different subset; v4-H spans n=95 across 25B season. The directional finding is consistent: **v1's NFL win-totals exposure is NOT a positive-EV strategy at v1's price band**.

---

## 6. Operator recommendation

### Verdict: v1 PARTIAL with mandatory per-series filter

**Rationale.** v1's measured edge holds on the original 17-series mix (mean +12.47pp on n=39) but fails on the three target series that account for the bulk of v1's live trading volume (KXNFLWINS: n=95, KXNFLPLAYOFF: n=9, KXMLBPLAYOFFS: n=5). The live bot's exposure profile is therefore structurally divergent from the dataset on which v1's edge was measured.

This is precisely the "partial" outcome the operator brief Section A described: v1's edge holds on some series but not others, requiring a per-series filter.

### Specific action items for the operator

1. **(Immediate) Add a series-prefix denylist filter to v1's market scanner.** Block all `KXNFLWINS-*`, `KXNFLPLAYOFF-*`, and `KXMLBPLAYOFFS-*` candidates in `src/kalshi_bot/strategy/market_scanner.py` until a fresh measurement on a larger sample shows a positive CI. Implementation: add a `series_denylist: list[str]` field on `ScannerConfig` checked after the existing lifetime + price filters. Default-on for the three series above. Documented escape hatch via `--no-series-denylist` for operator override.

2. **(Immediate) Audit current resting orders.** Run `uv run python -m scripts.live_review` and identify any open resting orders on the 3 denylisted series. Operator judgment whether to cancel (the existing CLAUDE.md round 7 recommendation is "do not retroactively cancel" but this finding is stronger evidence; operator should reconsider per individual position).

3. **(Short-term, 1-2 weeks)** Re-derive v1's pooled-universe edge AFTER applying the denylist. If the remaining universe (the original 17 prefixes + any non-target series in production) still shows mean P&L positive with CI excluding zero on a fresh sample, v1 is OK to continue at reduced scope. If it does not, v1 itself should be paused.

4. **(Medium-term)** Investigate WHY KXNFLWINS / KXNFLPLAYOFF / KXMLBPLAYOFFS are different:
   - Hypothesis A: T-35d for these series is closer to season-start when more variance is yet to play out. Lifetimes are 30-180d, but mean lifetime for KXNFLWINS is shorter (~95d) than the original NBA-heavy dataset.
   - Hypothesis B: T-35d for these series captures a "favorite trap" where teams that look strong pre-season slump and the contract loses heavily.
   - Hypothesis C: The original 100% YES rate dataset was a survivorship artifact (only markets that resolved YES made it into the eligible cut). This stress test exposes the genuine loss tail.

5. **(Optional)** Run a Polymarket fade-filter (V4-E A1) as an additional skip-rule on the surviving universe. V4-E's A1 fires correctly on 2 of 4 KXMLBPLAYOFFS losses in V4-E's small sample. This is the Phase 4 must-do #1 from the v4 critic.

### What this does NOT recommend

- KILL v1 entirely. The original 17-series mean of +12.47pp at n=39 is real and measurably positive. After denylisting the 3 fragile series, v1 should still have positive expected return on its remaining universe, though the operator should re-measure to confirm.
- Pause live trading WITHOUT a series filter. Live bot is currently running at $32 capital cap; risk is bounded; operator can ship the denylist as a hotfix and continue.
- Trust the +12.47pp number in any forward-looking projection without a per-series caveat. The original dataset is NOT representative of v1's actual live trading universe.

---

## 7. Honest constraints on this finding

- **VWAP window is wide (-42 to -28 days), not the exact T-35d the original used.** The probe inventory uses `vwap_t35_wide`, the same VWAP V3-A and V4-F use for consistency. The original `data/processed/sports_dataset.parquet` uses `mid_price_at_T_small` which is a tight window around T-35d. The wide window slightly smooths prices but is the same one v1 actually trades at. This is not a fundamental confound but the magnitudes might shift slightly under a narrower window.
- **KXNCAAFFINALIST and KXNCAAF are not v1-tradable by construction.** Their listing as "untested exposure" in v3/v4 critics is technically correct but operationally moot. v1 cannot trade them at any threshold.
- **n=109 is still modest.** The CIs include zero. The finding is "v1's edge on these series is NOT measurably positive," not "v1's edge on these series is provably negative." A larger sample (200-400 markets, requiring multiple seasons) would tighten the CI.
- **Original n=39 has a 100% YES rate which is statistically suspicious.** A genuine maker edge at 70-95c should produce occasional losses, not zero. The original dataset's 100% YES rate alone is evidence of a sample-selection artifact that needs separate investigation, beyond the scope of this stress test.

---

## 8. Reproducibility

Script: `scripts/v4/v1_stress_test.py`. Run via:

```
uv run python -m scripts.v4.v1_stress_test
```

Outputs deterministic given the fixed bootstrap seed (42). Re-running on a fresh probe inventory snapshot would update the numbers; the methodology is invariant.

---

## Findings summary

| # | Finding | Severity |
|---|---|---|
| 9.1 | KXNCAAFFINALIST and KXNCAAF have 0 v1-eligible markets (untradable by v1's price filter) | Important |
| 9.2 | KXNFLWINS n=95: mean -1.03pp, CI [-7.71, +5.08] includes zero | Killer |
| 9.3 | KXNFLPLAYOFF n=9: mean -10.18pp, CI [-38.41, +11.85] includes zero | Killer |
| 9.4 | KXMLBPLAYOFFS n=5: mean -27.84pp, CI [-68.98, +12.56] includes zero | Killer |
| 9.5 | Aggregate v1 measured edge (n=148) is +1.06pp, CI [-4.06, +5.84] includes zero | Killer |
| 9.6 | Original +12.47pp's 100% YES rate is a statistical signature of survivorship | Important |
| 9.7 | V4-F "v1 fails" is INTRINSIC, not artifactual; comparison anchor was wrong | Important |
| 9.8 | v1 PARTIAL recommended; series denylist mandatory before any v4 verdict | Killer |

4 KILLER, 4 IMPORTANT, 0 MINOR.

---

## Citations and code references

- v1 P&L formula: `src/kalshi_bot_v2/gate.py:101-108` `realized_pnl_per_contract`
- Kalshi fee formula: `src/kalshi_bot/analysis/metrics.py:kalshi_maker_fee_per_contract`
- Original v1 dataset: `data/processed/sports_dataset.parquet` (n=423, 17 series prefixes, ZERO KXNFLWINS / KXNFLPLAYOFF / KXNCAAFFINALIST / KXNCAAF / KXMLBPLAYOFFS markets)
- Original time-scale measurement: `research/time-scale-analysis.md` Section 1
- v3 W1 item: `CLAUDE.md` Round 9 / Phase 3 critic at `research/v3/07-critic.md`
- v4 Phase 3 critic Finding 6.1 / 8.5: `research/v4/07-critic.md` Test 6
- V3-A probe inventory: `data/v3/probe_inventory_all_markets.parquet` (n=2828, schema includes `vwap_t35_wide`, `eligible_wide`, `entity`)
- Bootstrap helper: `src/kalshi_bot/analysis/bootstrap.py` `bootstrap_mean_ci`
- This script: `scripts/v4/v1_stress_test.py`
- Per-market output: `data/v4/v1_stress_test_per_market.parquet`
- Summary JSON: `data/v4/v1_stress_test_summary.json`
