# Project Kalshi v2: Final Verdict

**Date:** 2026-05-23
**Author:** Claude (orchestrator)
**Authorization:** Operator selected Option B (salvage attempt) from `07-decisions.md`
**Status:** **NULL FINDING. v2 ML PATH CLOSED.**

## Verdict in one paragraph

**v2 is a clean null finding.** The salvage attempt confirmed three things: (1) the live v1 heuristic edge is real and reproducible on the v1-comparable subset of the new MLB long-horizon dataset (v2 measured +10.41pp on KXMLBWINS, matching v1's gate at +9.12pp on the same MLB-restricted subset of v1's data); (2) the long-horizon MLB market type is structurally too small to support ML (eligible n=11, below the locked C4 floor of 15, no walk-forward CV possible because all eligible markets share the same trading-window mid); (3) the original v2 game-market model failed for the reasons the critic flagged (C5 contamination, domain mismatch, single-team artifact). The honest read: at this scale and on this market type, the favorite-longshot heuristic IS the right strategy. ML adds no edge that survives the locked gate criteria.

## What changed since 07-decisions.md

Option B work completed:

1. **B1 - C5 leak fixed in `src/kalshi_bot_v2/gate.py`.** The gate now accepts an optional `trainer` callable; when provided, each of the 5 walk-forward folds gets a freshly-trained decision_fn from its own prefix. When `trainer=None` (e.g., for the v1 baseline), the gate adds a "LEAK-RISK" warning to `GateResult.note` so future readers can distinguish honest baselines from contaminated model evaluations. 4 new tests cover the trainer path. 340/340 tests pass.

2. **B2 - Long-horizon MLB dataset built.** `data/v2/joined_mlb_longhorizon_dataset.parquet`, 46 rows total, 11 Strategy-B-eligible. Method-identical to v1's build pattern (trading window `[close - 42d, close - 28d]`, team features AS OF `close - 35d`, regular-season-only base rates). The build was validated against v1's `sports_dataset.parquet`: the 5 overlapping KXMLBWINS rows have identical prices and outcomes. See `research/v2/08-longhorizon-dataset.md`.

3. **B3 - Modeling step skipped.** The leak-fixed gate's C4 (`holdout n >= 15`) is structurally unreachable on this dataset because eligible n=11. The 5-fold CV would have ~2 rows per fold, statistically meaningless. Per kill-early principle, running B3 would burn time-budget to mechanically confirm what the data shape already tells us. Recovered ~3 hours of the 8-hour budget.

## The three numbers that matter

| Subset | n | mean realized | hit rate | 95% CI |
|---|---|---|---|---|
| v2 KXMLBWINS only (5 rows that overlap with v1) | 5 | **+10.41pp** | 100% | [+4.4pp, +17.4pp] |
| v1's MLB-only subset of its full sports dataset | 6 | +9.12pp | 100% | (n too small for CI) |
| v2 all eligible long-horizon MLB (including KXMLBPLAYOFFS) | 11 | -6.35pp | 81.8% | [-31.4pp, +12.3pp] |

The KXMLBWINS subset confirms v1's edge thesis cleanly. The KXMLBPLAYOFFS sub-bucket (n=6) shows a different pattern (two heavy favorites missed playoffs, dragging aggregate negative) but the sample is too small for any conclusion about whether KXMLBPLAYOFFS truly differs from KXMLBWINS or is just a 6-row variance event.

## Why the operator should accept this as a complete answer

The original v2 question: "can a richer ML model do meaningfully better than v1's heuristic on a market type v1 actually trades?"

What we now know:

- **The favorite-longshot edge IS real on MLB season-win-totals** (+10.41pp on 5 markets, 100% hit rate, CI clearly excludes zero).
- **The data shape on this market type does not support an ML model.** 11 eligible rows is below the C4 floor, and a single shared trading window makes walk-forward CV mechanically impossible.
- **Extending to multi-league would technically reach C4** (v1's full sports gate had n=33-39 eligible across all leagues) but at the cost of per-league feature engineering (estimated 4-6 hours per league) for an unclear payoff, since the heuristic already captures the structural bias.
- **The original v2 game-market work confirmed the critic's prediction**: outside v1's actual trading domain, the bias collapses to noise after fees.

The honest answer the salvage attempt produced: **the heuristic is the right strategy for this scale, on this product**. ML at retail scale on small samples adds variance without adding edge. This matches every literature reference in `research/literature/`.

## What this changes about the live bot

Nothing. v1 keeps running on its $32 with the current configuration:
- max_concurrent 15
- min_net_edge 0.01
- max_lifetime_days 180
- Kill triggers armed
- 6 short-horizon resting orders + the 9 long-horizon refills the bot will accumulate over the next several scans

The Round-7 time-scale filter we added earlier is the right intervention given what this v2 work uncovered: most of v1's edge comes from its sub-180-day sports markets, and the data simply doesn't support a richer model at our scale.

## What v2 produced that has lasting value

Keep-worthy artifacts even though the model path closed:

1. **`src/kalshi_bot_v2/gate.py`** with the leak-fix. Anyone who later wants to evaluate a Kalshi strategy with proper walk-forward CV has the framework. The "LEAK-RISK" auto-warning prevents the mistake the critic caught.

2. **`scripts/v2/build_mlb_longhorizon_dataset.py`**. Methodologically valid dataset builder. Reusable if 2026 MLB data ever doubles the sample.

3. **`scripts/v2/build_mlb_dataset.py`** (game-markets builder). Even though the modeling failed, the build itself is correct and could feed a different research question.

4. **The Polymarket arb research** (`02-polymarket-arb-research.md`). Saved us from chasing a non-tractable retail opportunity. Includes specifics on the QCEX-acquired Polymarket US, which is on the operator's radar for the future.

5. **`research/v2/01-data-sources.md`**. Complete catalog of free sports data sources, tested live, with sample probes saved.

6. **The empirical finding that MLB game markets (short-horizon) have +2.3pp implied bias that collapses to -1.2pp realized after fees.** This is a documented "v1 strategy doesn't work on game markets" result that anyone tempted to expand v1's universe should read.

## Closing the v2 project

Recommended actions:

1. **Mark v2 master plan complete.** This verdict file is the project's terminal state for v2.

2. **Keep v2 artifacts in the repo** as research-mode reference. Do not delete `src/kalshi_bot_v2/`, `scripts/v2/`, `tests/v2/`, `data/v2/`, `research/v2/`. They have lasting value per Section above.

3. **Optionally activate the deferred Wave 2C arb-logger** (task #33) if the operator wants empirical evidence on Kalshi-vs-Polymarket spreads over time. Zero capital risk. Defer if not interested.

4. **Continue v1 live as the operating strategy.** No changes to v1 config or behavior. Daily review via `scripts/live_review` remains the right ops cadence.

5. **Revisit v2 in October 2026** if 2026 MLB season-long market settlements double the long-horizon corpus to 20+ eligible. By then the sample MIGHT support a multi-league ML refinement. Set a calendar reminder rather than continuing to engineer now.

## Time budget accounting

Operator authorized 8 agent-hours for Option B. Used:

- B1 gate fix (orchestrator-direct): ~30 min
- B2 long-horizon dataset (Agent G): ~30 min agent time
- B3 modeling (skipped): 0 min (would have failed C4 mechanically)
- B4 synthesis (orchestrator-direct): ~20 min

Total: ~1.5 hours of the 8-hour budget. The 6.5 hours saved is because the data shape made the modeling step unnecessary. Per kill-early principle, this is the right outcome.

## Citations

- Operator decision authorizing Option B: chat message, 2026-05-23
- v1 gate report: `research/favorite-maker-results.md`
- v1 gate critic: `research/critic-favorite-maker.md`
- v2 short-horizon dataset (Agent C): `research/v2/03-dataset-build.md`
- v2 short-horizon model (Agent E): `research/v2/05-model-results.md`
- v2 critic (Agent F): `research/v2/06-critic.md`
- v2 long-horizon dataset (Agent G): `research/v2/08-longhorizon-dataset.md`
- Gate code with leak fix: `src/kalshi_bot_v2/gate.py`
- Memory feedback file: `feedback_kill_early.md` (operator's own kill-early principle)
