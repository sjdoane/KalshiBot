# Project Kalshi v3 Master Plan

**Date:** 2026-05-24
**Status:** Research phase, multi-agent autonomous execution
**Author:** Claude (orchestrator)
**Operator authorization:** Build a Polymarket ML model trained on EXTERNAL data, use it plus Kalshi prices to drive automated Kalshi-only trade decisions. Deliver a working v3 strategy that beats v1 on v1's domain OR a clean null finding. Do not repeat v2 failure modes (CV leak, domain mismatch, single-team artifact, false comparisons).

## 1. Project framing

The live v1 favorite-longshot bot runs on $32 of real capital via Windows Task Scheduler. v1 trades Kalshi sports at YES >= 0.70 with market lifetime 30-180d. v2 (ML on MLB game markets) closed 2026-05-23 as a null finding for diagnosable reasons. v3 is a fresh research track. v1 is untouched throughout.

The v3 question, in one sentence: **can external (non-market-price) features improve the calibration of Kalshi prices well enough that informed deviations become tradeable at our scale and v1's domain, OR is the v1 heuristic the right strategy after all?**

Either outcome is acceptable. What is unacceptable is shipping a v2-style false positive.

## 2. Thesis

The candidate edge: **Polymarket leads Kalshi on price discovery for events listed on both platforms** (documented during 2024 election; Wolfers/Zitzewitz literature; AhaSignals/Quantpedia summaries). If external features can predict Polymarket prices, and Polymarket leads Kalshi, then Kalshi prices that diverge from the external-feature model become a tradeable signal.

We trade on Kalshi only (US retail can't trade Polymarket offshore; Polymarket US is iOS beta with separate liquidity). Polymarket data enters as a feature OR as a model target, never as a trading venue.

**Three working hypotheses** (we will keep the one that survives Phase 1):

- **H1 (Polymarket-as-target)**: train a model on external features to predict the SETTLED Polymarket outcome (0/1) for events also listed on Kalshi. Use the model's probability as the "informed estimate." Trade Kalshi YES when model_prob > kalshi_price by some threshold, at v1's eligible price band [0.70, 0.95].

- **H2 (Polymarket-as-feature)**: train a model on external features PLUS Polymarket mid-price to predict the Kalshi market's settled outcome directly. Polymarket price is one of many features. Trade Kalshi YES when model_prob > kalshi_price by some threshold.

- **H3 (Polymarket-as-second-opinion)**: simpler statistical rule. When Kalshi YES price < Polymarket YES price by > X cents AND external-data sanity check agrees, trade Kalshi YES. No ML, just a structured deviation rule.

H3 is the kill-early fallback. If H1 and H2 both fail their gates, we test H3 as the simplest non-ML formulation of the same thesis. If H3 also fails, v3 closes as null.

## 3. What would falsify each hypothesis

- **H1 falsified if**: model trained on external features has holdout calibration no better than (a) the raw Polymarket mid-price taken at the same timestamp, or (b) v1's flat-prior on the eligible set. The external features add no information.

- **H2 falsified if**: the model with external + Polymarket features has holdout-on-Kalshi-outcome P&L that does NOT beat the v1 baseline by C6's locked +2pp on the SAME data with proper leak-free walk-forward CV.

- **H3 falsified if**: historical Polymarket vs Kalshi spreads on the v1-eligible price band (0.70-0.95 YES, 30-180d lifetime) are either (a) too rare (< 30 events with > 5c spread after fees), or (b) the Kalshi side does not converge toward Polymarket within the holding period (i.e., divergence is settlement-rule artifact, not mispricing).

In all three cases we document the failure and either pivot to the next hypothesis or accept null.

## 4. Hard constraints (inherited from operator brief, locked)

1. The live v1 bot is untouched. No changes to `src/kalshi_bot/`, `scripts/` (except `scripts/v3/`), `tests/` (except `tests/v3/`), `data/` outside `data/v3/`, `.env`, or `data/live_trades/`. No interference with the Windows scheduled task.
2. No real Kalshi orders. READ-scope client only. Paper-mode only on the v3 side.
3. No Polymarket WRITE endpoints. Use only public READ APIs (gamma-api.polymarket.com, clob.polymarket.com prices, data-api.polymarket.com).
4. The locked 6-criteria gate from `src/kalshi_bot_v2/gate.py` is binding. C5 must use the `trainer=` parameter for genuinely leak-free walk-forward CV. C6 (beats v1 by >= 2pp) is not negotiable.
5. No skipping or redefining the gate to make a marginal model "pass." Same discipline as v2's null finding.
6. No claim of signal that hasn't been validated on genuinely OOS data with leak-free CV.
7. No em-dashes anywhere (project rule).
8. Document every iteration, blocker, and pivot. The trail must be visible to a future context-cleared reader.

## 5. Success criteria (gate, locked)

The v2 gate at `src/kalshi_bot_v2/gate.py` is reused as-is. Six criteria, all must pass on a chronological 70/30 holdout with leak-free walk-forward CV:

- C1: holdout realized mean P&L > 0
- C2: holdout bootstrap 95% CI lower > 0
- C3: holdout hit rate > 0.55
- C4: holdout eligible n >= 15
- C5: 5-fold pooled mean > 0 with `trainer=` providing per-fold retraining
- C6: v3 model's holdout P&L mean exceeds v1's holdout P&L mean on the SAME data by >= 2pp

Additional v3-only sanity criteria (additive, not replacing C1-C6):

- **S1 (no-single-entity-artifact)**: when the top single entity (team, candidate, etc.) is dropped from the holdout, the holdout mean must stay > 0. Direct check against v2's COL-as-opponent failure mode.
- **S2 (full-corpus-OOS-only)**: if any holdout row's `close_time` is before the model's training cutoff, that row is dropped from the holdout evaluation. Direct check against v2's "pooled mean = in-sample fit" failure mode (caught by the leak fix, but verified here for paranoia).
- **S3 (domain-match-on-v1)**: holdout dataset's market characteristics (series, price band, lifetime distribution) must overlap v1's actual trading universe. Computed by intersecting the v3 holdout's (series, price_bucket, lifetime_bucket) tuples with v1's filled-orders log distribution.

S1/S2/S3 fail = the model does not honestly beat v1; do not "save" via threshold tuning.

## 6. Null-finding criteria (what we write up if no path passes)

A clean null finding mirrors v2's `10-final-verdict.md`:

1. State the question that was asked.
2. State the three (or more) numbers that matter.
3. Diagnose why the model did not pass (sample size? domain mismatch? feature poverty? structural inefficiency too small for our cost stack?).
4. State what would need to change for a future attempt (more data, lower-fee venue, paid data, etc.).
5. Recommend continuing v1 unchanged.

A null finding written like this is a success outcome. Per `feedback_kill_early.md`, the operator prefers an honest kill at research stage over a contaminated ship.

## 7. Phase structure and agent assignments

### Phase 1: parallel research (target 2.5h agent-clock)

Four agents run in parallel via the Agent tool with `subagent_type=general-purpose`. Each produces a numbered research doc under `research/v3/`.

- **Agent V3-A: Historical-market inventory and sample-size feasibility.**
  Pull all sports historical Kalshi markets across every series with v1-overlap (KXMLBWINS, KXMLBALEAST, KXNBAWINS, KXNFLWINS, KXNHLWINS, KXMLBPLAYOFFS, KXMLBALMVP, NCAA equivalents). Apply v1's eligibility filter (>=0.70 mid-price at T-35d, 30-180d lifetime, finalized result). Report: eligible n per series, total cross-series eligible n, time span, and the largest single-entity (team) concentration. Output: `research/v3/01-historical-inventory.md`.

- **Agent V3-B: External-features audit and Polymarket feature feasibility.**
  Build a catalog of external features that could predict sports market outcomes beyond what v1 already captures. Categories: team performance stats (Pythagorean records, run differential, FanGraphs WAR), injury reports, news/sentiment (Reddit JSON API), betting-line consensus (the-odds-api free tier), Polymarket mid-price + price history. For each: latency, history depth available to us, OOS-discipline rule (when can we sample without look-ahead), and cost. Output: `research/v3/02-features-audit.md`.

- **Agent V3-C: Polymarket vs Kalshi historical divergence analysis.**
  For events Kalshi lists in v1's domain (long-horizon sports >=70c YES, 30-180d lifetime), is there ALSO a matched Polymarket event we can identify? Sample 20 candidate Kalshi markets; attempt programmatic matching to Polymarket via `gamma-api.polymarket.com/public-search`. For matched pairs: was there a price divergence > 5c at any point in the trading window? Did Kalshi converge toward Polymarket before settlement? Quantify the match-success rate and the divergence-convergence rate. Output: `research/v3/03-poly-kalshi-divergence.md`.

- **Agent V3-D: Literature review of price discovery and external-feature prediction.**
  Pull recent papers/blogs on (i) Polymarket vs Kalshi price discovery (Wolfers/Zitzewitz, Quantpedia, Substack pieces from v2 research), (ii) sports outcome prediction with public stats (any open-source models cited in literature), (iii) Lopez de Prado time-series CV best practices (purge, embargo, walk-forward). Each paper gets a one-paragraph TLDR + "implications for v3" section. Update `research/literature/INDEX.md` with new entries. Output: `research/v3/04-literature.md`.

### Phase 2: build (target 3h agent-clock)

After Phase 1, orchestrator picks (a) market type, (b) feature set, (c) hypothesis (H1, H2, or H3). Two agents in series (B1 builds, B2 trains; B2 depends on B1).

- **Agent V3-B1: Dataset construction.**
  Build `data/v3/joined_v3_dataset.parquet` with leak-discipline:
    - Trading window T-35d (matches v1 method).
    - Outcome from Kalshi `/historical/markets` settled `result`.
    - Features sampled AT OR BEFORE T-35d for every row, with explicit timestamp logged.
    - Polymarket features (if used) sampled at the same T-35d.
    - Per-row sanity assertion that no feature has timestamp >= close_time.
  Output: parquet + `research/v3/05-dataset-build.md`.

- **Agent V3-B2: Model training and leak-free gate evaluation.**
  Train a baseline (logistic regression with 3-5 features) AND a tuned (gradient-boosted, 8-15 features) model. Run the v2 gate `evaluate()` with `trainer=` set so 5-fold CV retrains per fold. Apply S1/S2/S3 sanity checks. Output: `src/kalshi_bot_v3/` code + `research/v3/06-model-results.md` with the GateResult JSON.

### Phase 3: critic (target 1.5h agent-clock)

- **Agent V3-C1: Adversarial critic.**
  Style-matched to `research/critic-favorite-maker.md` and `research/v2/06-critic.md`. The critic must specifically test for the v2 failure modes:
    - C5 leak: re-run kfold and check that fold test windows are after the model's chronological cutoff
    - Domain mismatch: verify holdout markets resemble v1's filled-orders distribution
    - Single-entity artifact: re-run with the top-frequency entity removed
    - False comparison: confirm v1 baseline is computed on a domain v1 actually trades
    - Feature leakage: walk every feature for look-ahead potential
    - Multiple testing: account for every hyperparameter that was tuned on holdout
  Output: `research/v3/07-critic.md`.

### Phase 4: iterate (target 1h agent-clock)

Based on critic findings, the orchestrator picks:
- Fix the design and re-run B2 with the fix.
- Pivot to a different hypothesis (H1 -> H2 -> H3 -> null).
- Document why iteration is exhausted and write null verdict.

Every iteration appended to `research/v3/iterations.md` with: what changed, why, what the new gate result is, whether it cleared the critic.

### Phase 5: final critic + verdict (target 1h agent-clock)

- **Agent V3-C2: Final critic.** Re-runs the v3 critic against the iterated design.
- **Orchestrator synthesis**: write `research/v3/FINAL-VERDICT.md`. Either:
  - A passing v3 strategy with all six C-criteria, all three S-criteria, and a clean final critic. Include a runbook stub for what paper-trading the operator would need to authorize next.
  - A clean null finding with diagnosis, citing the specific failure(s).

## 8. Data sources, decided

Already-validated free sources from `research/v2/01-data-sources.md`:
- Kalshi `/historical/*` (READ-scope key in `.env`)
- MLB Stats API (no auth)
- nflverse parquet releases
- ESPN site API
- 538 NBA ELO archive (Wayback)
- Polymarket Gamma/CLOB/Data APIs (no auth)
- Retrosheet (MLB fallback)
- the-odds-api free tier (500/mo)

Reused but examined: Reddit JSON API for sentiment (free, undocumented but stable), GDELT for news/event signals (free, large), Etherscan free tier for on-chain (irrelevant unless we pivot to crypto markets).

No paid data tier. No new credentials needed beyond v2.

## 9. What to do if Phase 1 finds the data shape is too small

This is the most-likely outcome based on v2's experience. If the cross-series eligible n is < 80 even across multiple seasons, the path forks:

1. **Drop the >=70c YES filter from v1 to widen the dataset.** Use the full price range and have the model decide the entry threshold. Risk: leaves v1's domain, complicates C6.
2. **Multi-season pull (2023, 2024, 2025).** Test whether Kalshi's `/historical/cutoff` exposes earlier data.
3. **Multi-sport pull at the same time-scale.** v1 already trades multi-sport; v3 just needs to match.
4. **Pivot to a different market type with higher n** (crypto markets, KXMLBGAME if v1 expansion is in scope, etc.). But this surfaces v2's domain-mismatch problem and must be handled honestly.
5. **Null finding.** Document the data-shape blocker and stop.

The Phase 1 inventory drives which fork we take. The orchestrator will document the chosen fork in `research/v3/iterations.md` BEFORE starting Phase 2.

## 10. Failure-mode handling

Per operator brief:

1. If a blocker hits, write `research/v3/blockers/NN-{what-failed}.md` describing what failed and why.
2. Spawn a critic-style agent to validate the blocker is real.
3. Enumerate 3 alternative angles routing around it.
4. Pick the most promising; document the pivot in this master plan.
5. Only escalate to operator if alternatives are exhausted or an authorization is needed (paid data, new credentials, real money).

If the model fails the gate but the design is sound: iterate (more features, different target, different time horizon, simpler model, ensemble). Document each iteration in `iterations.md`. Do NOT redefine the gate to make a marginal result pass.

## 11. Continuous documentation rule

The operator cannot orient if there are no docs. Every 30 minutes of agent-clock-time, SOMETHING gets written to `research/v3/`. Master-plan updates, iteration entries, decision-log lines, blocker docs. Continuous trail.

## 12. Time budget

~9 hours of agent-clock. Allocation:
- Phase 1 parallel: 2.5h
- Phase 2 build: 3h
- Phase 3 critic: 1.5h
- Phase 4 iterate: 1h
- Phase 5 final: 1h

If finished early, spend remaining budget on a parallel research track (e.g., test H3 even if H1 or H2 already passed).

If near the limit and no model is working: write a v2-style null verdict and stop.

## 13. Decision log

Orchestrator appends decisions here as the run progresses.

- 2026-05-24 (Iter 0): Master plan written. Phase 1 four-agent fan-out being launched in parallel. v1 bot untouched.
- 2026-05-24 (Iter 1): Phase 1 returned. PIVOT decision committed. See `iterations.md` Iter 1 for the full pivot reasoning. Summary: H1/H2 (Polymarket-as-target / Polymarket-as-feature) killed by Polymarket's 30-day historical data ceiling. H3 (Polymarket-as-second-opinion) data shape exists (65% match rate) but divergence direction inverts the signal needed for long-Kalshi-YES trades. New working hypothesis H4: test whether non-Polymarket external team-stat features improve calibration over v1 at n=147, with proper leak-free CV. Two acceptable outcomes: pass C6 (real edge) or honest null (v1 confirmed).
- 2026-05-24 (Iter 1 cont): Phase 2 agent fan-out: V3-B1 dataset build (sequential), V3-B2 model train (depends on B1).
- 2026-05-24 (Iter 1 cont): Phase 2 features locked: MLB Stats API byDateRange, nflverse stats_team_week. GDELT only if orthogonality holds at dataset stage. Polymarket DROPPED.
