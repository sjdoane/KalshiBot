# Project Kalshi v3: Final Verdict

**Date:** 2026-05-24
**Author:** Claude (orchestrator)
**Authorization:** Operator-authorized v3 research run, full decision-making authority within research scope
**Status:** **NULL FINDING. v3 ML PATH CLOSED.**

## Verdict in one paragraph

**v3 is a clean null finding with one consequential side-discovery about v1.** The originally-stated v3 thesis (Polymarket leads Kalshi -> external model -> Kalshi convergence) was structurally undermined by three Phase 1 findings: Polymarket's CLOB price-history endpoint has a 30-day rich-detail ceiling that blocks historical training, KXMLBWINS markets (v1's clearest domain) have zero Polymarket counterparts for 2025, and where Polymarket-Kalshi spreads exist they go in the wrong direction for adding long-Kalshi-YES trades. We pivoted to a clean non-Polymarket experiment (H4: do external team-stat features improve calibration over v1 at n=147 with leak-free CV?). The Phase 2 gate failed all four binding criteria (C1, C2, C5, C6). The Phase 3 critic flagged that C6=0pp is mechanical equality on this holdout, not a measured null, and that the "v1 confirmed" framing overreaches because v1's measured-edge dataset structurally excludes the KXNFLWINS markets that dominate the v3 holdout failure. v3 closes as null; v1 continues unchanged; a v1 universe-rebuild item is flagged for future scope.

## The three numbers that matter

| Number | Value | Meaning |
|---|---|---|
| v3 gate criteria passed | **2 of 6** (C3 hit rate, C4 n>=15) | C1, C2, C5 fail; C6 is mechanical-identity not measurement |
| v3 holdout mean P&L (all three rules) | **-18.89pp** (n=45) | Identical across G1/G2/G3 because LogReg saturates above 0.70 trade threshold on every holdout row |
| v3 holdout NFL slice mean P&L | **-40.19pp** (n=26 = 49% of holdout) | This is the failure-zone subgroup; v1's measured `+12.47pp` edge was computed on a dataset with zero KXNFLWINS markets |

Supplementary context:
- v3 holdout NBA + NHL slice: **+10.26pp** (n=19, 100% YES). Consistent with v1's claimed edge on its NBA-heavy backtest universe.
- v1's documented edge on its backtest source `data/processed/sports_dataset.parquet`: +12.47pp on n=39 eligible markets, 17 series-prefixes, but **zero KXNFLWINS markets**.
- v3 probe `data/v3/probe_inventory_all_markets.parquet`: n=2828 markets on the same time window, 95 KXNFLWINS eligible, but enumerates only 5 series-families (NFL/NBA/NHL/MLB/NCAA).
- Series overlap between v1's live attempted-orders (19 series) and v3 holdout (5 series): **2 of 19 = 10.5%**.

## Why the operator should accept this as a complete answer

The original v3 question: "can external features predict Polymarket prices well enough that Kalshi's diverging prices become a tradeable signal, at the scale and data availability we actually have?"

After Phase 1, that question's premises were diagnosed as broken:

- **Polymarket historical data is unavailable for training.** The free CLOB endpoint has a hard ~30-day ceiling. We cannot sample Polymarket prices at the T-35d moment for any Kalshi market closed > 30 days ago. H1 and H2 (Polymarket-as-target / Polymarket-as-feature) are dead at the data-availability layer.
- **Polymarket-Kalshi divergence direction is wrong for long-only Kalshi-YES.** Of 11 pairs at T-35d on MLB v1-eligible markets, every pair with > 5c spread had Kalshi PRICED HIGHER than Polymarket. Polymarket is more cautious and more accurate (Brier 0.192 vs Kalshi 0.264). The Polymarket signal says "fade v1's favorites," not "buy MORE Kalshi YES." H3 in its "long Kalshi" form is dead.
- **2026 sports volume asymmetry inverts the natural Polymarket-leads-Kalshi reading.** Kalshi handles $2.7B/wk with 90% from NFL/NBA/MLB; Polymarket US handles $5M/wk; Polymarket Global handles $2.1B/wk. By the order-flow-mechanism of Ng et al. 2026, the larger venue leads. For US-tradeable Kalshi vs Polymarket-US, Kalshi probably leads, not Polymarket. Only Polymarket Global could plausibly lead Kalshi on sports, and US retail cannot trade it.

After Phase 2 (the H4 non-Polymarket experiment), the result was unambiguously null:

- The orthogonality protocol dropped 11 of 12 candidate team-stat features at the dataset stage. The retained feature (`nfl_games_played_pre_t35d`) is a league-NFL-and-season-progressed dummy, not a true team-stat signal.
- The chronological 70/30 holdout puts most NFL favorite-NO outcomes outside the train set: NFL train YES rate is 100%, NFL holdout YES rate is 46%. No price-or-thin-feature ML rule can flag the 14 holdout NFL NOs because the train set has zero NFL NOs to learn from.
- C6 = 0.0pp because both LogReg rules saturate above the 0.70 trade threshold on every holdout row, so they trade the identical 45 rows v1 trades. v3 was literally unable to express a v1-differing decision.

After Phase 3 (adversarial critic), the verdict survived in direction but required framing fixes:

- The C6 = 0pp is a structural identity (LogReg saturation), not a measured null.
- v1's "+12.47pp" claim is not a clean baseline because v1's measured-edge dataset structurally excludes the KXNFLWINS markets that dominate v3's holdout failure.
- S3 domain match materially fails: only 2 of 19 series in v1's live attempted-orders overlap with the v3 holdout.

The Phase 3 critic explicitly sub-scenario-tested for "is v3 cleaner with a different gate construction?" Three variants (60/40 split, 80/20 split, rolling-origin pooled) all fail. The verdict is robust to design variation within the leak-free constraints.

The honest answer the v3 effort produced: **at our scale and on the available free data, external features do not improve calibration above v1's heuristic on this holdout. AND the holdout itself reveals that v1's measured edge has untested exposure on KXNFLWINS late-season markets.** Both findings are real; neither was visible from the v1 backtest alone.

## What v3 produced that has lasting value

Keep-worthy artifacts even though the model path closed:

1. **`scripts/v3/probe_inventory.py` + `data/v3/probe_inventory_*` parquets.** A reproducible Kalshi historical-market inventory probe across 100 series and the v1 eligibility filter. The probe's known limitation (hardcoded 5-family series list, misses KXBOXING, KXUFCFIGHT, KXWCGAME, etc.) is documented in `07-critic.md` and is the starting point for a future v1 rebuild.

2. **`scripts/v3/build_v3_dataset.py` + `data/v3/joined_v3_dataset.parquet`.** A leak-free 147-row multi-sport dataset with strict AS-OF discipline and an orthogonality protocol. The build script is reusable for any future v4-style work on a similar universe.

3. **`src/kalshi_bot_v3/model.py` + `scripts/v3/run_v3_gate.py`.** A leak-free model + gate runner using the v2 gate's `trainer=` parameter. Reusable scaffolding.

4. **`research/v3/03-poly-kalshi-divergence.md`** plus its probe + cache. Quantifies that Polymarket-Kalshi divergence direction on long-horizon MLB markets is consistently Kalshi-over-Polymarket (Polymarket more cautious, better calibrated). This is the most actionable Polymarket finding so far: NOT a long-Kalshi-YES signal, BUT a candidate fade-filter for v1. Deferred to v4 scope.

5. **`research/v3/04-literature.md`** plus three new literature extractions (`ng-peng-tao-zhou-2026-price-discovery.md`, `lopez-de-prado-2018-cv.md`, `sports-prediction-ceiling-2022-2024.md`). The free-public-feature ceiling of +1-3pp on season-long markets at 0.70-0.95 YES is now documented, with the Bonferroni correction math for future hyperparameter-grid honesty.

6. **`research/v3/07-critic.md`.** The full Phase 3 adversarial-critic doc with 8 reproduced tests, including the C6 mechanical-equality finding and the v3-vs-v1-domain mismatch math. This is the kind of pre-publication critique that v2's null finding also benefited from.

7. **The empirical finding that v1's measured-edge dataset structurally excludes KXNFLWINS markets.** This is a project-state correction that will outlive v3. Flagged for the operator below.

## What this changes about the live bot

**Nothing immediate.** v1 keeps running on its $32 with the current configuration:

- max_concurrent 15, min_net_edge 0.01, max_lifetime_days 180, kill triggers armed
- Running via Windows Task Scheduler task `KalshiLiveBot` per `OPERATOR_RUNBOOK.md`
- 340/340 existing tests pass
- v3 work touched zero files under `src/kalshi_bot/`, `scripts/` (except `scripts/v3/`), `tests/` (except `tests/v3/`), `data/` outside `data/v3/`, `.env`, or `data/live_trades/`

**One operator-relevant flag for future scope.** v1's backtest source (`data/processed/sports_dataset.parquet`) structurally omits KXNFLWINS markets in the v1 eligible band. v1's claimed `+12.47pp` edge has not been measured on KXNFLWINS. The v3 holdout's NFL slice realized -40.19pp on the same eligibility filter. v1's live scanner pulls the full sports universe (`src/kalshi_bot/strategy/market_scanner.py:118-152`), so this exposure IS in production scope, just untested.

Recommended future scope (not part of v3):

- **W1. Rebuild v1's backtest dataset on the complete sports universe.** Use `scripts/v3/probe_inventory.py` (expanded series list per `07-critic.md` Important #3 finding) as the starting point. Re-measure v1's edge on the full universe including KXNFLWINS, KXBOXING, KXUFCFIGHT, KXWCGAME, etc. If the rebuild reveals a smaller-than-claimed edge or distributional fragility, the operator can decide whether to add a per-series filter to v1's live config.
- **W2. Operate v1's current configuration unchanged in the meantime.** The bot has Round-7 kill triggers armed, including the rolling-30 mean compression check; a -40pp realization on a single subgroup would trip these well before causing material capital damage.

## What v3 produced as new operator-actionable findings

Beyond the lasting artifacts, three findings that affect future decisions:

1. **Polymarket historical data is NOT a viable feature source today.** The 30-day CLOB price-history ceiling blocks any historical-training thesis. Future work that wants Polymarket as a feature must run a prospective logger for 60-90+ days to accumulate the training data. Defer to v4.

2. **Polymarket-as-fade-filter on v1 IS a candidate v4 thesis.** Polymarket's signal direction (Kalshi favorites over-priced relative to Polymarket) suggests v1 could improve by skipping trades when Polymarket disagrees. This is a defensive overlay that REDUCES v1's trade count, not v3's mandate. Filed for v4 (`07-critic.md` and `iterations.md` Iter 1).

3. **v1's known-good universe is narrower than its live-trading universe.** Per the v3-vs-v1 dataset comparison, v1's backtest source skipped KXNFLWINS while v1's live scanner trades it. This is a project-data-pipeline issue, not a strategy issue, but it has implications for any future "v1 rebuild" or "v1 expansion" work.

## What would need to change for a future ML attempt

Per the master plan Section 6 null-finding criteria, here are the specific conditions under which a future v4-style ML attempt could clear the gate honestly:

1. **Multi-season pull (~400-500 markets minimum).** n=147 is below AFML's recommended T=252; per Bailey/Lopez de Prado, the deflated-Sharpe penalty at this n is severe. A 3+ season pull would reach the methodological floor.
2. **Match the v3-style probe to v1's actual live universe.** Add the 17 missing series-prefixes to the probe (KXBOXING, KXUFCFIGHT, KXWCGAME, KXFOMEN, KXCS2, KXMLBSTATCOUNT, etc.). This is also W1 above.
3. **Prospective Polymarket-feature build** if the operator decides to pursue v4. Set up a daily logger; train after 60-90 days of accumulated data.
4. **Lower-fee venue.** Polymarket has structurally lower fees (sports 0.3% taker vs Kalshi 2c/contract). At our retail scale the fee stack is the dominant cost, but US retail cannot trade Polymarket offshore. Skip until Polymarket US matures.
5. **Different time horizon.** Long-horizon season-win markets are path-dependent and have small effective sample. Short-horizon markets (KXMLBGAME, KXNBAGAME) have larger n but inherit v2's domain-mismatch problem.

Per the operator's kill-early preference in `feedback_kill_early.md`, the cleanest action is to write this null verdict, leave v1 running on its tested-as-far-as-known universe, and stop. The Phase 3 critic agreed.

## Closing the v3 project

Recommended actions:

1. **Mark v3 master plan complete.** This verdict file is the project's terminal state for v3.

2. **Keep v3 artifacts in the repo** as research-mode reference. Do not delete `src/kalshi_bot_v3/`, `scripts/v3/`, `tests/v3/`, `data/v3/`, `research/v3/`. They have lasting value per the section above.

3. **Continue v1 live as the operating strategy.** No changes to v1 config or behavior. Daily review via `scripts/live_review` remains the right ops cadence. Kill triggers remain armed.

4. **Update CLAUDE.md and project memory** to reflect Round 9 (v3 null finding). Add a project-state line so a future context-cleared reader can orient.

5. **Optional future work (operator decides):** W1 (rebuild v1 backtest on full sports universe) and/or v4 (Polymarket-as-fade-filter or prospective Polymarket-feature build). Neither blocks anything; both are clean future scope items.

## Time budget accounting

Operator authorized ~9 agent-hours for v3. Used approximately:

- Phase 1 four-agent parallel research: ~3 hours total agent-clock
- Phase 2 dataset build (V3-B1): ~1 hour
- Phase 2 model + gate (V3-B2): ~1 hour
- Phase 3 critic (V3-C1): ~1.5 hours
- Phase 4 amendments + Phase 5 verdict (orchestrator-direct): ~0.5 hour

Total: ~7 hours of the 9-hour budget. The 2-hour headroom is intentional; per kill-early principle, additional iteration on a confirmed null does not change the outcome.

## v2 failure-mode comparison (final)

| v2 failure mode | v3 outcome |
|---|---|
| C5 in-sample CV leak (v2 critic Section 3) | PREVENTED. `trainer=` wired in v2 gate; S2 verified all 4 folds chronologically clean (`07-critic.md` Test 1). |
| Feature look-ahead (v2 critic Section 4) | PREVENTED. V3-B1 leak audit + V3-C1 spot-check on 5 random NFL rows both passed (`07-critic.md` Test 3). |
| Model anchors on price (v2 critic Section 5) | ADDRESSED PROACTIVELY. Orthogonality protocol dropped 11 of 12 candidate features before training. The retained feature is a league dummy, not a team-stat; this is the same finding v2 hit at smaller n. |
| Single-entity artifact (v2 critic Section 6, COL = 75% of holdout) | NOT REPRODUCED. v3 holdout max single-team share 6.8% (TB), broad-based loss not concentrated (`07-critic.md` Test 2 + V3-B2 S1). |
| False C6 comparison on a domain v1 doesn't trade (v2 critic Section 9) | **PARTIALLY REPRODUCED.** v3 ran C6 on a holdout 49%-dominated by KXNFLWINS, a series v1's measured-edge dataset structurally excludes. v1's "+12.47pp" was never measured on this subgroup. The Phase 3 critic flagged this as Important #2; the verdict above incorporates it. (`07-critic.md` Tests 2 + 8.) |
| Pooled-mean = in-sample fit (v2 critic Section 3) | PREVENTED. Per-fold retraining via `trainer` verified by S2; fold means are honestly OOS. |

v3 did not repeat v2's exact pattern but ALMOST reproduced the false-comparison failure mode in a different shape. The Phase 3 critic caught it. The verdict above acknowledges it explicitly.

## Citations

- Operator decision authorizing v3: chat message, 2026-05-24 morning, "Build a Polymarket ML model trained on a dataset EXTERNAL to Polymarket... end product is either a working v3 strategy that passes a leak-free 6-criteria gate AND has a defensible argument for why it would beat v1 on v1's actual domain, OR a clean, documented null finding"
- v3 master plan: `research/v3/00-master-plan.md`
- v3 iterations: `research/v3/iterations.md`
- Phase 1 docs: `01-historical-inventory.md`, `02-features-audit.md`, `03-poly-kalshi-divergence.md`, `04-literature.md`
- Phase 2 docs: `05-dataset-build.md`, `06-model-results.md`
- Phase 3 critic: `07-critic.md`
- v2 final verdict for structural parallel: `research/v2/10-final-verdict.md`
- v2 critic for inherited failure modes: `research/v2/06-critic.md`
- v1 production runbook: `OPERATOR_RUNBOOK.md`
- v1 measured-edge claim: `research/time-scale-analysis.md`
- Project memory: `~/.claude/projects/C--Users-SamJD-OneDrive-Desktop-AI-Projects/memory/project_kalshi.md` (to be updated to Round 9)
- v1 live scanner: `src/kalshi_bot/strategy/market_scanner.py:118-152`
- v1 backtest dataset: `data/processed/sports_dataset.parquet` (n=423, 39 v1-eligible, 0 KXNFLWINS)
- v3 probe inventory: `data/v3/probe_inventory_all_markets.parquet` (n=2828, 147 v1-eligible, 95 KXNFLWINS)
- v1 live state: `data/live_trades/state.json` (34 orders across 19 series-prefixes)
- Memory feedback: `feedback_kill_early.md`

## Final note

Both acceptable v3 outcomes were the operator's choice. We delivered the second (clean null finding). The work that produced this null was honest, leak-free, critic-reviewed, and documented. v1 continues running unchanged. The next decision is the operator's: accept the verdict and continue v1; or open one of the future-scope items (W1 or v4) as a separate research track.
