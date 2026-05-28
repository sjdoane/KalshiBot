# Adversarial Critic: Project Kalshi v2 (MLB Game-Market Model)

**Date:** 2026-05-23
**Reviewer:** Agent F (adversarial critic context)
**Subject:** [05-model-results.md](05-model-results.md) gate report, [src/kalshi_bot_v2/model.py](../../src/kalshi_bot_v2/model.py), [src/kalshi_bot_v2/gate.py](../../src/kalshi_bot_v2/gate.py), [03-dataset-build.md](03-dataset-build.md)
**Mandate:** Stress-test before any move toward paper trading. Operator runs live v1 on $32 real capital.

## Executive summary

**Verdict: DO NOT PROCEED to paper trading as currently scoped.** The v2 model results document acknowledges most of the right caveats but understates how load-bearing several of them are. Three findings dominate this review:

1. **The +6.74pp "v2 beats v1" delta is computed on a domain where v1 doesn't actually trade.** The v1 live strategy runs on long-horizon sports markets (lifetime 30 to 180 days); the v2 dataset is short-horizon MLB game markets (median lifetime 0.55 days). v1's holdout mean of -3.15pp on this dataset is what v1's heuristic would do if it traded a product it never trades. Beating that baseline is not evidence v2 beats live v1.

2. **75% (15 of 20) of the holdout trades the model selects are bets against the Colorado Rockies as underdog.** The "+3.59pp holdout mean" is essentially "the model spotted that COL is the worst team in 2025 MLB." This is not a generalizable signal; the model has plausibly memorized a single-team artifact during a single-team late-season collapse.

3. **The "5-fold pooled mean +15.98pp" headline is contaminated by in-sample evaluation.** The gate applies the same trained model to all 5 walk-forward folds, but the model was trained on the chronological train portion. Folds 1, 2, and 3 are 100%, 100%, and 83% INSIDE the training data. Only fold 4 is genuinely out-of-sample, and its mean (+8.73pp) shrinks to near-zero (-0.32pp) when I restrict pooled stats to genuinely-OOS rows.

Below, ten specific findings with file:line citations and re-run numbers.

## 1. Domain transfer: there is no defensible argument

[03-dataset-build.md:9-102] is honest about the pivot: median KXMLBGAME lifetime is 0.58 days. v1's live universe is `data/processed/sports_dataset.parquet` long-horizon markets (lifetime 30 to 180 days) where the favorite-longshot bias compresses over weeks. These are structurally different products. Per [literature/burgi-deng-whelan-2025.md] Section 3.4, ψ (the favorite-longshot magnitude) shrinks as markets clear; game markets have hours to clear, season markets have months. The dataset's own calibration table [03-dataset-build.md:325-348] confirms it: the 94-market bulk at 0.70-0.75 price shows +0.17pp realized edge versus implied. That is statistical noise. The "extra" +12pp in the 26-market 0.75-0.80 sub-bucket is the entire claimed aggregate edge, sitting in a small bucket where bootstrap CI plausibly includes zero.

**There is no domain-transfer argument.** Agent E flags this honestly [05-model-results.md:28-41], but then proceeds to compute "C6 beats v1 by +6.74pp" against a v1 baseline run on this same dataset. Both sides of the comparison run on a market type v1 does not actually trade.

## 2. C2 failure analysis and multiple-testing exposure

[gate.py:48,244-247] sets C2 as holdout 95% bootstrap CI lower > 0. Reported [gate_v2_result.json:44]: holdout mean +3.59pp, 95% CI [-16.43pp, +18.99pp], n=20, SD=40.34pp.

I re-ran the bootstrap at multiple alpha levels and computed the n required to push the lower bound positive:

| CI level | CI lower | CI upper |
|---|---|---|
| 95% (gate) | -16.43pp | +18.99pp |
| 99% | -21.67pp | +23.90pp |
| 99.17% (Bonferroni n=6) | -21.79pp | +23.96pp |

**Required holdout n to clear C2 at 95%, given mean +3.59pp and SD 40pp: ~485 trades.** At 99% Bonferroni it's ~837. The dataset has 123 eligible total, 20 in holdout. C2 is not "failing on a small sample by chance"; it is structurally unreachable at this effect size on this sample.

Agent E's defense [05-model-results.md:288-299] is "5-fold CI robustly positive; C2 too strict for game-market sample size." That is rationalization. The C2 criterion was locked in [STRATEGY_BRIEF.md] before this dataset existed. The honest read: the model's signal-to-noise ratio is below what the locked gate requires. That is a kill condition under the project's own methodology rules ([phase-1.5-methodology.md] Section 9).

Bonferroni across the 6 iterations in [05-model-results.md:344-350]: the +6.74pp v2-minus-v1 delta does NOT survive a Bonferroni correction at the holdout level because the holdout CI does not clear zero in the first place. The +6.74 figure is a single point estimate, not a CI-bound finding.

## 3. The 12pp gap between 5-fold CV (+15.98pp) and holdout (+3.59pp): in-sample leak

This was the single biggest finding of the review. Reproduction in [scripts/v2/critic_drop_price.py] and direct kfold analysis:

[gate.py:131-141] defines `_kfold_splits(df, n_folds=5)` on the eligible dataframe (123 rows), yielding 4 walk-forward folds. [gate.py:206-218] then applies the same `decision_fn` (which wraps the production model trained on the chronological train 70%) to each fold's test slice.

But the production model was trained on rows where `close_time < 2025-08-14 23:08 UTC` (split_idx_full of the 2173-row full dataset). The 5-fold splits on the eligible set put fold test windows at:

| Fold | Test window | % IN training set | Pooled mean |
|---|---|---|---|
| 1 | 2025-05-12 to 2025-05-30 | **100%** | +22.86pp |
| 2 | 2025-05-31 to 2025-06-28 | **100%** | +22.82pp |
| 3 | 2025-06-29 to 2025-08-20 | **83%** | +9.01pp |
| 4 | 2025-08-24 to 2025-09-25 | 0% (OOS) | +8.73pp |

**The +15.98pp "5-fold pooled mean" is dominated by in-sample test fold means of +22.86pp and +22.82pp.** When I restrict the pooled set to genuinely-OOS rows (test rows AFTER the model's chronological cutoff), the mean drops to **-0.32pp on n=17** [scripts/v2/critic_drop_price.py re-run].

This is not a subtle leak. The "5-fold CV CI [+8.82pp, +21.56pp] robustly positive" claim that Agent E uses to defend the model [05-model-results.md:225-227, 293-297] is essentially measuring training-set fit. C5 as currently implemented does not provide independent OOS evidence.

**This is the most important fixable bug in the gate code.** A correct walk-forward CV would re-train the model on each fold's prefix; [model.py:243-295] has `_walk_forward_oos_predictions` for exactly this purpose but [train_mlb_model.py:94-96] explicitly disables it: `use_walk_forward_for_scan=False`. Even if walk-forward were enabled, the gate's `_kfold_splits` does not invoke fresh training; it just resamples the same model output.

## 4. Feature leakage: not from the build side, but downstream in the gate's CV

Team-stat features [build_mlb_dataset.py:299-419]: `cutoff = game_date`, mask requires `game_date_obj < cutoff`. Strict same-day exclusion. Doubleheaders G1 -> G2 leak vector is a non-issue (only 2 G1 doubleheaders in eligible set, no G2s). Microstructure features [build_mlb_dataset.py:694-715]: VWAP window is `[open_time, game_start_utc]` using MLB Stats API's `gameDate`, not Kalshi's `close_time`. Markets where `open_ts >= game_start_ts` are explicitly dropped [build_mlb_dataset.py:700]. This is the correct fix to the original 21pp-fake-edge bug [03-dataset-build.md:67-79]. **No look-ahead from the dataset build side.** The leakage is downstream in the gate's CV (Section 3).

## 5. Feature-importance interpretation: the model anchors on price

[feature_importance.csv via 05-model-results.md:243-256]: `favorite_price` gain = 501.78, more than 2x the next feature (`run_diff_diff` = 249.18). To test whether the team-stat features add independent signal, I retrained the model with `favorite_price` removed from the feature set ([scripts/v2/critic_drop_price.py]).

**Result** [data/v2/critic_drop_price_result.json]:

- Holdout eligible n: **0** (zero trades passed the hybrid rule).
- Folds pooled mean (in-sample, contaminated per Section 3): +19.38pp on n=24.
- Genuinely OOS: model's max prediction on the holdout is 0.6744; with threshold 0.70 nothing fires.

**The team-stat features alone do not produce a prediction above 0.70 on any holdout market.** The "model anchored on price plus small adjustments" interpretation is exactly right. The model's selected trades are filtered by a rule that requires the model to agree with the market that the favorite is at least 70% likely; without the price feature, the model's median prediction on eligible markets is 0.62.

What this means: the "+3.59pp holdout mean" is essentially the **favorite-longshot residual at the price band** (the model's tiny lift above the market consensus). On a 0.75-0.80 sub-bucket [03-dataset-build.md:330] of the dataset that sub-bucket alone shows +12pp realized edge with n=26. The model is not adding signal; it is concentrating on the sub-bucket where the price-conditioning is most favorable.

## 6. Failure analysis: 75% of selected trades are against Colorado

[05-model-results.md:317-322] notes all 4 holdout losses were against COL or WSH and calls them "high-confidence favorites baseball just lost." I ran the full breakdown:

**Holdout selected trades (n=20) by underdog team:**

| Underdog | n | Win rate |
|---|---|---|
| COL | 15 | 0.800 |
| WSH | 4 | 0.750 |
| LAA | 1 | 1.000 |

**75% (15/20) of holdout trades are vs COL.** Across the full eligible 123-row set, COL appears as underdog in 57 of 123 markets (46%). The model is not "trading favorites against weak teams"; it is **almost entirely trading against COL specifically**, who collapsed to a 43-119 season in 2025 and dragged the favorite-side eligible price up against them.

This is the same warning sign Round 4 produced on Strategy B: critic-favorite-maker.md Section 5 noted "test sample is structurally one playoff series, not 33 independent observations." Here the holdout is structurally "MLB September 2025 vs the Colorado Rockies," not 20 independent observations. The effective independent sample size is closer to 3 to 5 (a handful of opponent-team series), not 20.

**A single COL late-season-rally-week of any future season could flip this** ranking. The model's selected-trade hit rate on non-COL holdout markets is 4 of 5 (80%, n=5). The model has no demonstrated edge against any other team in the holdout.

## 7. Calibration assumption: skipped, not justified

[train_mlb_model.py:80-86] disables isotonic calibration because "5 eligible val rows produces discrete plateaus." [model.py:298-306] then has `calibrate: bool = False` flowed through. Calibration was discarded, not deferred.

Two issues:

(a) **Use the full training set, not a 5-row val slice, to fit isotonic.** [model.py:282-291] supports this inside `_walk_forward_oos_predictions` (calibrates on the last 20% of each fold's train prefix). The production path skips it entirely. There is no methodological reason calibration must be limited to 5 rows.

(b) **The raw model outputs are NOT well-calibrated for the threshold decision.** Section 5's experiment showed the model's max prediction on the holdout is 0.67 when `favorite_price` is removed and 0.78 [feature_importance.csv mean predicted in 0.7+ bucket] when it is included. The 0.70 threshold is satisfied roughly when the input `favorite_price` is >=0.71, i.e. the model is using its own input as the threshold. That is not calibration; that is identity.

The honest decision rule given the model's behavior would be: trade when `favorite_price >= 0.70 AND fav_pyth_diff > 0`. That collapses to a heuristic, not an ML model. Per the [STRATEGY_BRIEF.md] principle that heuristics with no ML risk are preferred when ML adds no incremental edge, the dataset does not support the model premise.

## 8. The hybrid decision rule: defaults reverse-engineered from iteration history

[model.py:147-148]: `DEFAULT_THRESHOLD = 0.70` and `DEFAULT_EDGE = -0.10`. Agent E [05-model-results.md:176-188] argues these are "domain-motivated" not data-fit. The 0.70 floor is defensible (matches Strategy B eligibility), but `-0.10` is the most permissive value in `EDGE_GRID` [model.py:134]: `[-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10]`. Why not -0.20? Why not -0.05? The grid was modeler-defined; -0.10 is the choice that admits ~16% of eligible markets and produces the headline +3.59pp.

The 6 iterations [05-model-results.md:344-350] explored calibration on/off, walk-forward scan on/off, three decision-rule modes. Iterations 1, 3, 4 produced negative holdout means; iteration 6 (hybrid + defaults) is the one that passes 5/6. That is selection on holdout, not pre-registration. Bonferroni across the 6 iterations (Section 2): the +3.59pp mean has SE = 9.02pp, roughly 0.4 standard errors above zero. There is no defensible statistical argument the model has demonstrated signal over noise on holdout, before OR after correction.

## 9. Comparison to v1: framing is misleading

[gate.py:144-152]: the v1 baseline `v1_decision_fn` trades EVERY eligible row at the v1 default prob 0.95. On the v2 game-market dataset that produces holdout mean -3.15pp [gate_v2_result.json:7].

The v1 LIVE strategy (per [favorite-maker-results.md:36]) trades long-horizon sports markets at a claimed +5.13pp test mean (critic-realistic +1 to +3pp net per [critic-favorite-maker.md] Section 3). v1 does NOT trade game markets. **The -3.15pp baseline is what v1 would do if applied to a domain it does not operate in.**

The "+6.74pp v2 beats v1" framing in [05-model-results.md:21-22, 222-227] is technically computed correctly under [gate.py] C6, but the comparison is operationally meaningless. It tests whether the ML model adds value over a trivial "always-trade" rule on a domain where neither v2 nor v1 has demonstrated production edge. It does NOT test whether v2's signal would generalize to v1's actual live universe.

A faithful comparison would be: train v2's model on long-horizon sports markets ([data/processed/sports_dataset.parquet]) and beat v1's actual live edge there. That is the experiment the master plan envisaged but the dataset pivot [03-dataset-build.md] explicitly moved away from.

## 10. Cost of false positives: paper trading is not free

Per [00-master-plan.md] all v2 work is paper-mode only, so financial cost is zero. Non-zero costs: operator-time (daemonizing, monitoring, distinguishing model-wrong from fill-missed each week); cognitive bandwidth (the operator is a USC student running live v1 on $32 of real capital and will be tempted to compare daily P&L between tracks); and sunk-cost dynamics (once paper-trading runs for N weeks, the gradient is toward "let's try $1/trade live"). The Round 4 [critic-live-mode-design.md] Section 3 finding (kill triggers calibrated to gate-headline rather than realistic edge) is the exact failure mode that would repeat here.

The next correct step is NOT paper trading. It is one of: (a) rebuild Agent C's dataset on the long-horizon sports series (KXMLBALEAST, KXMLBALMVP, per [03-dataset-build.md:618-624]) and re-run Agent E there; or (b) accept v2 as a research-mode null finding and stop.

## What I would specifically NOT do

1. **Do not paper-trade v2 on 2026 MLB games as the next step.** The model has not demonstrated independent OOS edge, and the holdout signal is concentrated against one specific underdog team.

2. **Do not cite the "+6.74pp better than v1" delta as evidence to graduate v2.** The v1 baseline in the C6 comparison runs on a market type v1 does not trade. The delta is a property of the trivial baseline, not the v2 model.

3. **Do not cite the "5-fold pooled mean +15.98pp" as evidence the model has CV-validated signal.** Folds 1-3 are inside the model training set; pooling them with fold 4 misrepresents in-sample fit as OOS performance. The OOS-only mean on the same data is essentially zero (-0.32pp on n=17).

4. **Do not add starting-pitcher features as the "fix"** [05-model-results.md:328-335]. The model already overfits the price feature and the COL-as-opponent signal; adding more features will not address the structural problems. The proposed addition would expand the feature set on a 123-row eligible set and worsen the variance.

5. **Do not flip the C2 criterion** from "95% CI > 0" to "5-fold CI > 0" to make this pass. C5 as currently implemented is contaminated by Section 3 leakage; relaxing C2 would compound the methodology drift.

6. **Do not raise the per-trade edge threshold from -0.10 to a higher value** in an effort to "improve precision." The current value was already selected from a grid post-hoc; tightening it further on this dataset is more data peeking, not less.

7. **Do not pivot to NBA without addressing the underlying structural problems** [03-dataset-build.md:503-538]. The same domain-transfer and per-team concentration issues will recur on NBA.

## Recommended actions

If Agent E or the orchestrator wants to salvage the v2 thread:

1. **Fix the C5 leakage in gate.py.** [gate.py:206-218] should require fresh per-fold training, not reuse of the chronological-train model. This is a 30-minute code change. Re-run the gate; expect the 5-fold pooled mean to drop substantially.

2. **Run a per-team holdout.** Drop COL from the dataset entirely, retrain, re-evaluate. If the model's edge is concentrated against one team, removing that team should collapse the +3.59pp holdout mean toward zero or negative. If the model still shows edge against the remaining teams, that is evidence of generalization.

3. **Run the pipeline against the long-horizon series** the dataset doc suggests in [03-dataset-build.md:618-624]. That tests the model on v1's actual market type. If v2 cannot demonstrate edge there, the project should kill v2 per [feedback_kill_early.md].

4. **Accept the null finding** if (2) and (3) come back negative. Per project rule: kill early, document honestly, do not paper-trade a model whose signal is concentrated on one team in one season.

## Citations

- Gate code: [../../src/kalshi_bot_v2/gate.py](../../src/kalshi_bot_v2/gate.py)
- Model code: [../../src/kalshi_bot_v2/model.py](../../src/kalshi_bot_v2/model.py)
- Training script: [../../scripts/v2/train_mlb_model.py](../../scripts/v2/train_mlb_model.py)
- Dataset build: [../../scripts/v2/build_mlb_dataset.py](../../scripts/v2/build_mlb_dataset.py)
- Gate JSON: [../../data/v2/gate_v2_result.json](../../data/v2/gate_v2_result.json)
- Critic experiment (drop favorite_price): [../../scripts/v2/critic_drop_price.py](../../scripts/v2/critic_drop_price.py), output [../../data/v2/critic_drop_price_result.json](../../data/v2/critic_drop_price_result.json)
- Master plan: [00-master-plan.md](00-master-plan.md)
- Dataset doc: [03-dataset-build.md](03-dataset-build.md)
- Model results: [05-model-results.md](05-model-results.md)
- Reference critic style: [../critic-favorite-maker.md](../critic-favorite-maker.md), [../critic-live-mode-design.md](../critic-live-mode-design.md)
- v1 favorite-maker results: [../favorite-maker-results.md](../favorite-maker-results.md)
- Burgi et al: [../literature/burgi-deng-whelan-2025.md](../literature/burgi-deng-whelan-2025.md)

All numerical claims re-ran against the dataset directly or the production code, not from the gate report. Reproduction script: [../../scripts/v2/critic_drop_price.py](../../scripts/v2/critic_drop_price.py).
