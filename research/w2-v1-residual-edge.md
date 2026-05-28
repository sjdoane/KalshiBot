# W2: V1 measured edge on the denylisted-residual universe

**Date:** 2026-05-24
**Author:** Agent W2
**Status:** Closes the W2 item flagged in CLAUDE.md Round 10 (post-v4) and Round 11 (post-v5). Companion to V4-H's `research/v4/09-v1-stress-test.md`. This is the most important number the operator hasn't yet seen.
**Inputs (READ-only):** `data/v3/probe_inventory_eligible_with_team.parquet` (n=147), `data/processed/sports_dataset.parquet` (n=423; v1 original measurement set).
**Code:** `scripts/v5/w2_v1_residual_edge.py`. Reproducible (bootstrap seed 42).
**Outputs:** `data/v5/w2_residual_per_market.parquet`, `data/v5/w2_residual_summary.json`.

---

## TLDR

**Headline number:** v1's measured edge on the denylisted-residual universe is **+7.68pp on n=60, row-bootstrap 95% CI [+2.63pp, +11.68pp]**. The +12.47pp original number was inflated by the original dataset's series mix and 100% YES rate; the residual is **4.79pp lower than the original**. Cluster-bootstrapped by series prefix (19 prefixes), CI is [+3.19pp, +12.99pp] -- still excludes zero.

**However the residual is fragile in ways that don't show in the headline.** The 96.7% hit rate (58 wins, 2 losses out of 60) is structurally similar to the original n=39's 100% rate; the two known losses (KXMLBWINS-DET -85.4pp, KXNCAAFPLAYOFF-ND -80.1pp) drag the v3-only-residual mean from +9.94pp (LOO drop-2) down to +5.06pp. **The v3-only residual subset (n=38) has row-bootstrap CI [-2.79pp, +11.15pp], which INCLUDES zero**, and only flips to CI-excludes-zero when the v1 original n=22 unique markets (100% hit by selection) are added.

**Operator verdict: YELLOW (lean GREEN).** v1's residual edge is measurably positive on the combined-universe row bootstrap, and survives a 19-prefix cluster bootstrap. It does NOT survive a v3-only row bootstrap. The W1 denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) appears to have removed the dominant loss source but the remaining loss tail is still real (2/60 = 3.3%, mean per loss -82.7pp). Continue v1 at current $32 scale. **Do NOT scale up** until either (a) the v3 inventory is refreshed with another season's data and the v3-only CI excludes zero, or (b) Track A sportsbook-shadow logging delivers a second-arm filter that reduces the loss tail.

This is consistent with V4-H's conclusion: v1's edge holds on its original measurement universe (the v1-only n=22 subset shows +12.20pp, CI [+9.28, +15.12], matching the original's +12.47pp claim), but is much thinner once the v3 inventory's broader sample is included. The W1 denylist was a necessary fix; it was not sufficient to recover the original +12.47pp claim.

---

## 1. Residual universe enumeration

### 1.1 Construction

Two inputs are unioned:

1. **v3 inventory.** `data/v3/probe_inventory_eligible_with_team.parquet`, n=147 v1-eligible markets (already filtered for `eligible_wide`, lifetime in [30, 180] days, T-35d wide-window VWAP in [0.70, 0.95], result in {yes, no}).
2. **v1 original.** `data/processed/sports_dataset.parquet`, n=423 rows; re-applied v1 eligibility criteria (lifetime in [30, 180] days, `mid_price_at_T_small` in [0.70, 0.95], outcome in {0, 1}) yielding n=39 (matching the `time-scale-analysis.md` baseline).

Apply the W1 denylist `{KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS}` to series prefixes (split on hyphen, so `KXNFLWINS-ARI` matches prefix `KXNFLWINS`):

| Source                                   |    n |  After denylist |
|------------------------------------------|-----:|----------------:|
| v3 inventory (V3-A eligible_with_team)   |  147 |              38 |
| v1 original sports_dataset (n=39 elig.)  |   39 |              39 |

The v1 original has ZERO denylisted markets (confirming V4-H Section 1's finding that the +12.47pp claim was on a dataset with zero KXNFLWINS / KXNFLPLAYOFF / KXMLBPLAYOFFS markets).

Dedup by ticker, keeping the v3 row when both sources have the same ticker (the v3 wide-VWAP T-35d window is closer to v1's live execution price than v1's `mid_price_at_T_small` narrow-window proxy, although for the 17 overlap rows the two prices are within ~1pp of each other in practice).

| Slice                              |  n |
|------------------------------------|---:|
| v3 residual (denylist applied)     | 38 |
| v1 residual (denylist applied)     | 39 |
| Overlap by ticker (v3 wins dedup)  | 17 |
| v1-only rows added to residual     | 22 |
| **COMBINED RESIDUAL UNIVERSE**     | **60** |

### 1.2 Per-series counts in residual

| Series prefix         |  n |  Source mix                       |
|-----------------------|---:|-----------------------------------|
| KXNBAWINS             | 22 | 17 v3 + 5 v1-only                 |
| KXMLBWINS             | 11 | 10 v3 + 1 v1-only                 |
| KXNCAAFPLAYOFF        |  8 | 8 v3                              |
| KXNFLGAME             |  3 | 3 v1-only                         |
| KXUCLROUND            |  2 | 2 v1-only                         |
| KXATPGRANDSLAM        |  1 | 1 v1-only                         |
| KXBALLONDOR           |  1 | 1 v1-only                         |
| KXBOXING              |  1 | 1 v1-only                         |
| KXCHARCOUNTLOLWORLDS  |  1 | 1 v1-only                         |
| KXLEADERNBAAST        |  1 | 1 v1-only                         |
| KXMLBALCY             |  1 | 1 v3                              |
| KXMLBSTATCOUNT        |  1 | 1 v1-only                         |
| KXNCAAFGAME           |  1 | 1 v1-only                         |
| KXNFLTRADE            |  1 | 1 v1-only                         |
| KXNHLCENTRAL          |  1 | 1 v3                              |
| KXNHLMETROPOLITAN     |  1 | 1 v3                              |
| KXSTARTCLEBROWNS      |  1 | 1 v1-only                         |
| KXSWIFTATTEND         |  1 | 1 v1-only                         |
| KXWNBAROTY            |  1 | 1 v1-only                         |

19 distinct series prefixes in the residual. The two heavy slices (KXNBAWINS n=22, KXMLBWINS n=11) account for 55% of n.

### 1.3 Date range

- **Combined residual close-time range:** 2025-04-15 to 2026-04-22 (~1 year coverage).
- **v3 residual:** 2025-09-17 to 2026-04-13. Skewed toward 2025-26 NFL/NBA/MLB seasons.
- **v1-only additions:** 2025-04-15 to 2026-04-22. Includes 2024-25 NBA/MLB tail.

The dominant KXNBAWINS slice (n=22) clusters tightly in March-April 2026; the dominant KXMLBWINS slice (n=11) clusters tightly in September 2025 (MLB season-end). The v1-only adds extend backward to include UEFA Champions League (Apr 2025) and forward into April 2026 player props.

---

## 2. v1 P&L measurement on the residual universe

P&L formula matches `src/kalshi_bot_v2/gate.py:realized_pnl_per_contract`:

```
gross    = outcome - yes_price
fee      = 2 * kalshi_maker_fee_per_contract(yes_price)
slippage = 0.015
pnl      = gross - fee - slippage
```

Bootstrap: 5000 resamples, seed 42, 95% percentile CI (per the project standard).

### 2.1 Headline result

| Slice                  |   n |     Mean P&L |  Hit rate |   Median |     SD | Bootstrap 95% CI       |
|------------------------|----:|-------------:|----------:|---------:|-------:|------------------------|
| **COMBINED RESIDUAL**  |  60 |  **+7.68pp** |    96.7% |   +6.48pp | 18.39pp | **[+2.63pp, +11.68pp]** |
| v3 residual only       |  38 |    +5.06pp  |    94.7% |   +5.87pp | 22.07pp | [-2.79pp, +11.15pp]   |
| v1-only (residual)     |  22 |   +12.20pp  |   100.0% |  +13.81pp |  6.96pp | [+9.28pp, +15.12pp]   |

**The CI on the combined residual mean excludes zero (CI lower +2.63pp).** This is the headline operator number.

**The CI on the v3-only residual mean INCLUDES zero (CI lower -2.79pp).** This is the honest stress-test number. The v3 inventory is the only post-denylist evidence whose markets the v1 original dataset did not also sample; on that subset alone, the edge is not measurably positive.

### 2.2 Cluster bootstrap by series prefix

Series prefix is the most natural cluster (same market structure, same season, same favorite-longshot regime). With 19 prefixes in the combined residual (5000 resamples seed 42):

| Slice                  |   n |  Mean P&L |  Cluster-prefix CI    |
|------------------------|----:|----------:|------------------------|
| Combined residual      |  60 |   +7.68pp | [+3.19pp, +12.99pp]   |
| v3 residual only       |  38 |   +5.06pp | [-0.63pp, +10.29pp]   |

Combined residual: cluster bootstrap CI is slightly wider but still excludes zero. v3-only residual: cluster CI grazes zero (-0.63pp lower bound). Pattern consistent: the v3 inventory subset alone is fragile under both row and cluster bootstrap; combining with the v1-only adds (which carry the original sample's 100% YES survivorship) pushes the CI off zero.

### 2.3 Loss tail (the 2 losses driving variance)

The residual has **two losses among 60 rows (3.3%)**, both in the v3-residual subset:

| Ticker                 |    Price |   Outcome |   P&L     |
|------------------------|---------:|----------:|----------:|
| KXMLBWINS-DET-25-T90   |    0.819 |         0 |  -85.35pp |
| KXNCAAFPLAYOFF-25-ND   |    0.766 |         0 |  -80.13pp |

Win-vs-loss asymmetry (combined residual):

- Wins (n=58, 96.7%): mean +10.79pp per contract
- Losses (n=2, 3.3%): mean -82.74pp per contract

LOO sensitivity on combined residual (n=60, mean +7.68pp):

- Drop top-1 loss (KXMLBWINS-DET): mean -> +9.25pp (n=59)
- Drop top-2 losses: mean -> +10.79pp (n=58)

LOO on v3-only residual (n=38, mean +5.06pp):

- Drop top-1: mean -> +7.50pp (n=37)
- Drop top-2: mean -> +9.94pp (n=36)

**The win-side mean is +10-11pp and matches the original n=39's mean per-row. The losses are catastrophic (-80 to -85pp) because the contract price was ~0.80, so a 0 outcome loses roughly 80pp of paid premium.** Two losses out of 60 contributes -(2 * 82.74) / 60 = -2.76pp to the row mean. Without those two losses, the residual mean would be +10.43pp, comparable to the original +12.47pp.

---

## 3. Per-series breakdown

| Series prefix         |   n |   Mean P&L |  Hit rate |  Row CI                |  Flag                  |
|-----------------------|----:|-----------:|----------:|------------------------|-----------------------:|
| KXNBAWINS             |  22 |   +9.94pp  |   100.0% | [+6.76pp, +13.46pp]   | clean                  |
| KXMLBWINS             |  11 |   -1.21pp  |    90.9% | [-19.42pp, +10.34pp]  | **FRAGILE** (similar to denied series) |
| KXNCAAFPLAYOFF        |   8 |   +0.83pp  |    87.5% | [-23.97pp, +16.52pp]  | **FRAGILE**            |
| KXNFLGAME             |   3 |  +20.59pp  |   100.0% | [+16.64pp, +25.91pp]  | clean (small n)        |
| (15 other prefixes)   |   1-2 each | (mostly +12 to +23pp at 100% hit) | n/a | n<3, no CI inference |  -                     |

### Fragile-series observations

- **KXMLBWINS (n=11, mean -1.21pp):** one of the 11 markets is a loss (KXMLBWINS-DET); the other 10 win at +6-23pp each. The CI [-19, +10] spans a wide negative tail. This is the same pattern V4-H found for KXMLBPLAYOFFS / KXNFLWINS / KXNFLPLAYOFF: high hit rate (90.9%), but one catastrophic loss drags the mean below zero. **The W1 denylist removed KXMLBPLAYOFFS but did NOT remove KXMLBWINS-DET-style team-specific failure modes.** This is the strongest signal that the denylist as-applied is insufficient.

- **KXNCAAFPLAYOFF (n=8, mean +0.83pp):** one loss (KXNCAAFPLAYOFF-25-ND, Notre Dame), CI spans [-24, +17]. NCAA FB playoff is structurally similar to NFL playoff (single-elimination, high upset risk). The +0.83pp mean is essentially a wash after fees + slippage.

- **KXNBAWINS (n=22, mean +9.94pp, 100% hit, CI excludes zero):** this is the safest residual slice. All 22 markets resolve YES. CI [+6.76pp, +13.46pp]. The same caveat applies: 100% hit is suspicious; one season of bad NBA picks at price 0.70-0.95 could produce a -80pp tail. The v3 inventory's NBA window is March-April 2026 (regular-season end); team-wins markets that close before the playoff cutoff are highly favored to settle YES once the price is already 0.70-0.95.

### v4-H comparison

V4-H found (denied universe):

| V4-H series          |    n |     Mean      |  CI                  |
|----------------------|-----:|--------------:|----------------------|
| KXNFLWINS            |   95 |    -1.03pp    | [-7.71, +5.08]      |
| KXNFLPLAYOFF         |    9 |   -10.18pp    | [-38.41, +11.85]    |
| KXMLBPLAYOFFS        |    5 |   -27.84pp    | [-68.98, +12.56]    |

This W2 finds (residual):

| W2 fragile series    |    n |     Mean      |  CI                  |
|----------------------|-----:|--------------:|----------------------|
| KXMLBWINS            |   11 |     -1.21pp   | [-19.42, +10.34]    |
| KXNCAAFPLAYOFF       |    8 |     +0.83pp   | [-23.97, +16.52]    |

KXMLBWINS in the residual shows -1.21pp / 90.9% hit -- a thinner version of the V4-H KXNFLWINS pattern (-1.03pp / 87.4% hit on n=95). The signature is the same: one catastrophic loss per ~10 markets at 80-95% price, dragging the mean negative.

---

## 4. Comparison to the original +12.47pp

### 4.1 Magnitudes

| Measurement                                            |    n |    Mean    | Hit rate | Row 95% CI            |
|--------------------------------------------------------|-----:|-----------:|---------:|----------------------|
| Original `time-scale-analysis.md` (n=39)               |   39 |  +12.47pp  |  100.0%  | [+10.29pp, +14.77pp]  |
| W2 combined residual (this measurement, n=60)          |   60 |   +7.68pp  |   96.7%  | [+2.63pp, +11.68pp]   |
| W2 v3-only residual (n=38)                             |   38 |   +5.06pp  |   94.7%  | [-2.79pp, +11.15pp]   |
| V4-H denied universe (n=109)                           |  109 |   -3.02pp  |   85.3%  | [-9.73pp, +3.10pp]    |
| V4-H aggregate (original + denied, n=148, no denylist) |  148 |   +1.06pp  |   89.2%  | [-4.06pp, +5.84pp]    |

### 4.2 What the gap means

**Original - residual = 12.47 - 7.68 = 4.79pp.** The W1 denylist removed the worst exposure (the denied-universe -3.02pp drag), but the residual still falls 4.79pp short of the original claim. Three drivers:

1. **The v3 inventory adds 22 markets the original sample did not have access to.** These are mostly 2025-26 NBA/MLB/NCAA-FB playoff markets sampled at the closer T-35d wide-VWAP. Two of those 22 markets resolved NO at high prices, dragging the v3 mean down by ~7pp relative to the v1-only mean.

2. **The v1-only n=22 retains the original 100% YES rate.** That is structurally implausible -- the favorite-longshot literature predicts 70-95% YES at price 0.70-0.95, not 100%. The v1 original was sampled in a way that excluded the catastrophic-loss tail (small sample, narrow set of well-resolved series, possible survivorship in the joined-event filter). The residual measurement starts to expose this tail (96.7% rate vs 100% original).

3. **The two known residual losses (KXMLBWINS-DET, KXNCAAFPLAYOFF-ND) are within the v1 PRICE/LIFETIME eligibility window but were structurally excluded by the original 17-prefix sample.** Both losses are series that the original n=39 happened to have only one or zero of. This is consistent with V4-H Section 7's "n=39 has 100% YES rate which is statistically suspicious" caveat.

### 4.3 The honest CI interpretation

- **Combined residual CI [+2.63pp, +11.68pp] (row bootstrap):** the residual edge is at least +2.6pp at the 2.5% lower quantile, which exceeds the +1.0pp YELLOW threshold but does not robustly exceed +5pp at the lower bound. The point estimate (+7.68pp) is comfortably above GREEN's +5pp floor, but the CI lower bound is below it.

- **v3-only residual CI [-2.79pp, +11.15pp]:** if we ignore the v1-only adds (which carry the original sample's selection-biased 100% YES rate), the residual edge has CI that INCLUDES ZERO. The v3 subset alone is not measurably positive.

The honest read is: **v1's residual edge is "probably positive at the lower-bound +2.6pp level, but the only post-denylist evidence whose markets are genuinely new (the v3 inventory) does not measurably exceed zero by itself."** The combined +7.68pp CI excluding zero is partly held up by reusing the original measurement's 22 winning rows.

---

## 5. Operator-facing recommendation

### Verdict: YELLOW (leaning GREEN)

The W2 mean (+7.68pp) exceeds the GREEN threshold (>+5pp) and the row-bootstrap CI excludes zero, which satisfies the literal GREEN criteria. **However**, the combined CI is only +2.63pp at the lower bound (below +5pp), the v3-only residual CI INCLUDES zero, and KXMLBWINS shows the same fragility pattern that drove the W1 denylist additions for KXMLBPLAYOFFS. The probability that a 13th catastrophic-loss-type market will land in the next n=20-30 production exposure is meaningful.

The conservative classification is **YELLOW: continue v1 unchanged at current $32 scale, do NOT scale up**, with the following operator actions:

### 5.1 Specific actions

1. **(Immediate; no code change)** Continue v1 at $32. The combined residual measurement gives the operator the most defensible "v1's measured edge after the W1 fix" number to date. The headline +7.68pp / CI [+2.63, +11.68] is the number to put in any forward-looking projection or scale-up justification document.

2. **(Immediate)** Do NOT scale v1 beyond $32 until at least one of the following resolves:
   - The v3-only residual CI excludes zero on a refreshed inventory (~2-3 months additional season data). The current v3 inventory snapshot was taken in May 2026; adding 2026-2027 NFL/NBA preseason markets to the inventory before scaling up would refresh n.
   - Track A sportsbook shadow-mode logging delivers a working secondary filter (per CLAUDE.md Round 11 Track A recommendation; tasks #91-#97 in the current todo list). A working sportsbook arm would reduce the loss-tail probability by adding a divergence-check before any v1 fire.
   - Manual KXMLBWINS series review: examine whether KXMLBWINS-DET-25-T90 (the residual's largest loss) was foreseeable from sportsbook futures or W/L records at T-35d. If yes, the operator can consider extending the W1 denylist or adding a per-team filter.

3. **(Optional, low-cost)** Add `KXMLBWINS` to a "watch list" (not a denylist) in the scanner config. If v1 fires on a KXMLBWINS market in production, log a warning (the bot still trades; the warning just makes the operator aware of the elevated tail risk). This is a documentation-only change, no production code change required if the operator prefers to defer.

4. **(Optional)** Re-run W2 once Track A sportsbook shadow logging has accumulated 30-60 days of v1-fires. If the sportsbook divergence filter would have skipped one of the two residual losses (KXMLBWINS-DET or KXNCAAFPLAYOFF-ND), that's evidence the Track A arm tightens the residual CI to GREEN. If it would have skipped neither, the loss tail is irreducible at the data we have.

### 5.2 What this does NOT support

- **Scaling v1 to the $100 cap.** The residual CI lower bound is +2.63pp (row bootstrap) and -0.63pp (cluster bootstrap). At $32 the per-trade dollar exposure is bounded; at $100 the same fractional draw becomes 3x the dollar loss on a tail-loss-trade like KXMLBWINS-DET (-85pp on a $0.82 contract is -$0.70 per contract, or about 2.2% of the $32 bankroll per losing market). Scaling without tightening the CI is a bad bet.
- **Adding KXMLBWINS to the denylist immediately.** The KXMLBWINS slice as a whole shows -1.21pp / 90.9% hit, which is at the same fragility level as KXNFLWINS in V4-H but with a much smaller sample (n=11 vs n=95). A denylist add at n=11 is overfitting to one observed loss. Defer denylist expansion until at least n=30-50 on the suspected series.
- **Trusting the +7.68pp residual number as a forward-looking forecast.** The point estimate is sensitive to the v1-only adds (which carry selection bias). The forward-looking expectation, in the operator's place, should be: +3 to +5pp gross, before further compression from bias-shrinks-each-year (Bürgi 2025), market-microstructure friction at $0.70-0.95, or any new denylist additions.

### 5.3 Why not RED

The combined residual mean is positive at both row and cluster bootstrap lower bounds. The two losses are not concentrated in a single series prefix (they're in KXMLBWINS and KXNCAAFPLAYOFF, not a single new failure mode). The W1 denylist removed the worst exposure (V4-H's -3.02pp on n=109 denied series). The v1 strategy is not fragile in the same way the v3 ML and v5 ML tracks were fragile (those failed at the gate threshold; v1 passes its row bootstrap with margin). RED would require a clear sign-flip on the row bootstrap, which the data does not show.

### 5.4 Why not pure GREEN

The combined residual CI lower bound (+2.63pp) is below the GREEN floor of +5pp. The v3-only residual CI includes zero. The KXMLBWINS slice shows the same fragility pattern that drove the W1 denylist for KXMLBPLAYOFFS. A purely "GREEN: scale up" recommendation would be over-confident.

---

## 6. Robustness checks

- **Row bootstrap (5000 resamples, seed 42, 95% percentile):** combined residual +7.68pp, CI [+2.63pp, +11.68pp]. Reported above.
- **Cluster bootstrap by series prefix (19 clusters):** combined residual +7.68pp, CI [+3.19pp, +12.99pp]. CI slightly wider; still excludes zero.
- **LOO drop top-1 loss:** combined residual mean -> +9.25pp; LOO drop top-2: +10.79pp. Robustness pattern matches V4-H Section 2: the residual mean is partly held up by the absence of catastrophic losses, not by a uniform edge across all wins. The two losses contribute -2.76pp; without them the residual mean is +10.43pp (vs the original +12.47pp claim).
- **v3-only row bootstrap (n=38):** +5.06pp, CI [-2.79pp, +11.15pp]. CI includes zero.
- **v3-only cluster bootstrap (6 prefixes):** +5.06pp, CI [-0.63pp, +10.29pp]. CI grazes zero.

The reproducibility holds: re-run `uv run python -m scripts.v5.w2_v1_residual_edge` to regenerate identical numbers given seed 42.

---

## 7. Honest constraints on this finding

1. **n=60 is still modest.** The CIs are wide. A larger sample (n=150-200) from another season's worth of v3 inventory refresh would significantly tighten the bounds.

2. **The v3 inventory's VWAP at T-35d is a wide-window aggregation (-42d to -28d) of trade prices.** The v1 bot's actual fill price in production may be slightly different. The wide-window VWAP is the closest proxy we have; tighter-window proxies (vwap_t35_narrow) shrink the eligible n further.

3. **The v1-only n=22 adds carry the original sample's 100% YES rate selection bias.** Removing them gives the v3-only residual which has CI spanning zero; including them inflates the combined CI off zero. The honest interpretation is somewhere between the two extremes.

4. **The 19 series prefixes in the residual span very different sports and structures (NBA team-wins, MLB team-wins, NCAA-FB playoff, NFL game outcomes, soccer Champions League, tennis grand slam, boxing, esports League of Legends championship, etc.).** v1's edge may be heterogeneous across these. The cluster bootstrap accounts for this at the series level but treats within-series rows as exchangeable.

5. **The two residual losses are at price 0.819 and 0.766, both within v1's [0.70, 0.95] band but not at the price extremes.** They are not "fat-tail" prices; they are mid-band favorites that just resolved NO. This pattern -- 10-13% loss rate among 80-95% favorites -- is exactly what the favorite-longshot literature predicts.

6. **Future iterations on this number should refresh the v3 inventory snapshot.** The current snapshot (`data/v3/probe_inventory_eligible_with_team.parquet`) was taken in May 2026. Adding 2026-27 preseason markets would add another ~50-100 rows on the same structural mix.

---

## 8. Findings summary table

| # |  Finding                                                                               | Severity |
|---|----------------------------------------------------------------------------------------|----------|
| 1 | Combined residual n=60: mean +7.68pp, row CI [+2.63, +11.68] (excludes zero)         | Important |
| 2 | v3-only residual n=38: mean +5.06pp, row CI [-2.79, +11.15] (INCLUDES zero)          | Important |
| 3 | Cluster bootstrap by series (19 clusters) on combined: CI [+3.19, +12.99]            | Confirming |
| 4 | KXMLBWINS n=11: mean -1.21pp, CI [-19.42, +10.34], fragility pattern matches denied series | Important |
| 5 | KXNCAAFPLAYOFF n=8: mean +0.83pp, CI [-23.97, +16.52], also fragile                  | Important |
| 6 | KXNBAWINS n=22: mean +9.94pp, CI [+6.76, +13.46], CLEAN positive                     | Confirming |
| 7 | 2 losses out of 60 (3.3%) drag mean by -2.76pp; LOO-drop-2 -> +10.79pp               | Confirming |
| 8 | Gap to original +12.47pp: -4.79pp. Original was an inflated artifact of series mix + 100% YES rate | Killer |
| 9 | Operator verdict: YELLOW (leaning GREEN). Continue $32, do NOT scale up.             | Killer (operator action) |

3 KILLER (Items 8, 9, plus the combined-CI excludes zero as the GREEN-eligible point), 5 IMPORTANT, 1 CONFIRMING.

---

## 9. Reproducibility

Code path:

```
uv run python -m scripts.v5.w2_v1_residual_edge
```

Inputs (READ-only):

- `data/v3/probe_inventory_eligible_with_team.parquet` (n=147)
- `data/processed/sports_dataset.parquet` (n=423)

Outputs:

- `data/v5/w2_residual_per_market.parquet` (60 rows)
- `data/v5/w2_residual_summary.json`
- This research doc

Constants:

- Denylist: `{KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS}`
- Price band: [0.70, 0.95]
- Lifetime band: [30, 180] days
- Slippage allowance: 0.015
- Bootstrap: 5000 resamples, seed 42, 95% percentile CI
- Fee formula: `2 * kalshi_maker_fee_per_contract(yes_price)`

---

## 10. Citations and code references

- **v1 P&L formula:** `src/kalshi_bot_v2/gate.py:101-108` `realized_pnl_per_contract`
- **Kalshi maker fee:** `src/kalshi_bot/analysis/metrics.py:kalshi_maker_fee_per_contract`
- **Bootstrap helper:** `src/kalshi_bot/analysis/bootstrap.py:bootstrap_mean_ci`
- **V4-H stress test (denied series):** `research/v4/09-v1-stress-test.md`
- **Original +12.47pp claim:** `research/time-scale-analysis.md` Section 1
- **v3 W1 item (open since Round 9):** `research/v3/07-critic.md`
- **v4 critic Finding 6.1 / 8.5:** `research/v4/07-critic.md`
- **W1 denylist applied to v1 scanner:** completed Round 10 Task #48
- **W2 measurement script:** `scripts/v5/w2_v1_residual_edge.py`
- **Per-market output:** `data/v5/w2_residual_per_market.parquet`
- **Summary JSON:** `data/v5/w2_residual_summary.json`
