# Project Kalshi v2: Synthesis + Operator Decision Points

**Date:** 2026-05-23
**Author:** Claude (orchestrator)
**Inputs synthesized:**
- `research/v2/00-master-plan.md`
- `research/v2/01-data-sources.md` (Agent A)
- `research/v2/02-polymarket-arb-research.md` (Agent B)
- `research/v2/03-dataset-build.md` (Agent C)
- `research/v2/05-model-results.md` (Agent E)
- `research/v2/06-critic.md` (Agent F)

## TL;DR

Three paths investigated. Two are archived. One needs operator input.

| Path | Status | Reason |
|---|---|---|
| Polymarket cross-platform arb | **Archived** | Polymarket offshore blocks US; Polymarket US is iOS-only beta with thin liquidity; minimum profitable spread (15c safety) rarely occurs |
| MLB game-market ML model | **Critic-killed as currently implemented** | C5 leak (5-fold CV measures training-set fit), domain mismatch (game markets vs long-horizon), 75% of holdout trades against one team, multiple-testing across 6 iterations |
| MLB long-horizon ML model (rebuild) | **Operator decision required** | Critic's recommended salvage path; not yet attempted |

## What was built that's keep-worthy

Regardless of next steps, these v2 artifacts have lasting value:

- **`src/kalshi_bot_v2/gate.py`** (5/6 criteria + C6 "beat v1 by 2pp"). The C5 leak is real but the gate FRAMEWORK is correct; fixing the leak is a 30-min change per critic Section 3.
- **`scripts/v2/build_mlb_dataset.py`** (pipeline that joins Kalshi historical markets to MLB Stats API). Reusable for any future MLB modeling. Already fixed the in-game leakage bug (Agent C's first attempt had a +21pp fake edge from in-game data; the post-fix dataset is correct).
- **`scripts/v2/probe_data_source.py`** + Agent A's data catalog. Confirmed MLB Stats API, nflverse, ESPN, and 538 ELO archive are all reachable and useful.
- **The empirical finding that on short-horizon MLB game markets, the favorite-longshot bias is +2.3pp implied which collapses to -1.2pp realized after fees + slippage.** This is a genuinely useful "v1 strategy doesn't work on game markets" finding.

The polymarket research (Agent B) saved us from chasing an arb that's not retail-tractable in 2026.

## The critic's three killer findings (re-stated)

### Finding 1: C5 leakage inflates the model's apparent OOS edge

The 5-fold pooled mean of +15.98pp [+8.82, +21.56] looks robust. It is not OOS. Folds 1, 2, 3 test on rows that were INSIDE the model's chronological training set, because the production model was trained once on the first 70% and then evaluated on K-fold splits of the same eligible subset.

When restricted to genuinely-OOS rows (test rows after the training cutoff), pooled mean drops to **-0.32pp on n=17** (critic Section 3).

The fix: `gate.py:_kfold_splits` should require fresh per-fold training, not re-evaluation of the chronological-train model. 30-minute code change. After the fix, the 5-fold CV will measure what we want it to measure.

### Finding 2: Domain mismatch

v1's live strategy trades long-horizon sports markets (lifetime 30-180 days, season-long bets). v2 was built on short-horizon MLB game markets (median lifetime 0.55 days).

These are different products. v1's edge thesis (the favorite-longshot bias hasn't compressed yet because markets have months to run) does not apply to game markets where the bias has already been arbed down by close. The dataset itself shows this: realized edge on the full eligible set is +0.17pp in the 0.70-0.75 bucket, statistically indistinguishable from zero.

The "+6.74pp v2 beats v1" framing is misleading because v1 does not actually trade game markets. Both sides of the comparison run on a market type neither strategy operates in live.

### Finding 3: Single-team artifact

15 of 20 holdout trades are against Colorado Rockies. The 2025 Rockies finished 43-119, the worst MLB record by a margin. The model "discovered" that COL loses a lot. This is not a generalizable signal; it is overfitting to one team's one-season collapse.

The non-COL holdout shows 4/5 wins (n=5). The effective independent sample size is closer to 3-5 (a handful of opponent-team series), not 20. Bootstrap CI on n=5 is hopelessly wide.

## Operator decision required

The critic explicitly recommended NOT paper-trading the current model. The three options it laid out:

### Option A: Kill v2 as a null finding

- Document v2 as a clean methodology run that produced a null result.
- Per the project's "kill early" principle, this is the most-defensible action.
- Total cost: zero additional engineering. Run `pytest`, commit research docs, move on.
- Operator's continuing v1 live trading is unaffected.

### Option B: Salvage attempt - long-horizon dataset + leak fix

The critic's specific recommendations (Section 7 of `06-critic.md`):

1. Fix the C5 leakage in `gate.py` (30 min).
2. Re-pull data for **long-horizon Kalshi sports series** (KXMLBALEAST, KXMLBALMVP, KXMLBWINS-{team}-T{n}, etc.) and rebuild the dataset on the actual market type v1 trades. ~4-6 hours of engineering per Agent C.
3. Re-run the model with the fixed gate.
4. Add a per-team holdout: drop the dominant underdog team and check if the model's edge survives.

Total estimated cost: 6-10 hours of subsequent agent work. If the v2 model passes a properly-leak-free gate on long-horizon data, v2 becomes a credible candidate for paper trading on v1's actual domain. If it fails, we have a true null finding.

### Option C: Accept v2 as exploratory, paper-trade anyway

Agent E (Wave 3) recommended this. The critic explicitly says do not. The critic's argument:

- Operator-time cost is non-zero (debugging fills, daily comparison logic, monitoring).
- Cognitive bandwidth competing with the live v1 bot.
- Sunk-cost dynamics push toward "let's try $1/trade live" before evidence supports it.
- Same kill-trigger calibration mistake the Round 4 critic flagged would repeat here.

I AGREE WITH THE CRITIC on rejecting C. The model's signal-to-noise ratio is below what the locked gate requires. Paper-trading a model whose 5-fold CV is contaminated and whose holdout is one-team-dependent is research-process erosion, not validation.

## My recommendation

**Pursue Option B with a hard stop**:

1. Fix the C5 leak (low cost, high value: at minimum we get a correct gate).
2. Re-attempt the model on long-horizon series.
3. Set a tight time budget: 8 agent-hours max. If the model can't clear the leak-fixed gate (5/6 PASS including a properly-OOS C5) on long-horizon data within that budget, kill v2 cleanly.

This is a research-time investment that buys us either (a) a real v2 candidate that beats v1 on v1's own domain, or (b) a clean null finding confirming the favorite-longshot heuristic is the right call. Both outcomes are useful.

**Option A is acceptable** if the operator wants to conserve research time and is satisfied that the work-to-date is a sufficient honest investigation.

**Option C is rejected** by the critic's findings and I concur.

## What does NOT change regardless of decision

- Live v1 keeps running on its $32 with its existing 6 short-horizon resting orders.
- v1's runtime kill triggers, drawdown breakers, and acceptance criteria remain in force.
- No v2 capital deployment of any kind. All v2 work stays research-mode.
- The `kalshi_bot_v2/` package remains in the repo as research-only code. The live bot's imports do not touch it.

## Concrete files to inspect if operator wants the technical detail

| File | Purpose |
|---|---|
| `research/v2/03-dataset-build.md` Section 2 | Why short-horizon game markets pivoted away from v1's window |
| `research/v2/05-model-results.md` Section 7 | The gate result table |
| `research/v2/06-critic.md` Sections 1, 3, 6 | The three killer findings (domain, leak, COL) |
| `scripts/v2/critic_drop_price.py` | Critic's reproduction of the leak finding |
| `data/v2/joined_mlb_dataset.parquet` | The 2,173-row dataset; 123 eligible |
| `data/v2/gate_v2_result.json` | Full gate output including v1 baseline |

## Summary of operator decision points

1. **Kill v2 now (Option A), or attempt Option B salvage?** Default to A if you want to minimize research time. Default to B if you want a clean answer on whether ML beats heuristic on v1's actual domain.

2. **Should the deferred Wave 2C arb logger be activated?** Polymarket arb path is archived for trading, but a passive paper-only logger could collect 90 days of empirical spread data at low engineering cost. Default: defer until v2 ML question is resolved.

3. **Should the live v1 bot keep its current configuration** through whatever v2 decision is made? Default: yes. v1 is its own track and is unaffected by v2 outcome.

## What's next without operator input

I will NOT proceed with any further v2 engineering without operator direction. Per the original instruction "Stop only when user input is needed," this is that moment. The critic has flagged structural methodology issues that require operator authorization to either fix or accept-and-move-on.

Live v1 continues running.
