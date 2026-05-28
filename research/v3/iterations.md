# v3 Iteration Log

Continuous trail of orchestrator decisions, pivots, and gate runs. Append-only. Most recent at the bottom.

## Iter 0 (2026-05-24, master-plan write-up)

Master plan committed at `research/v3/00-master-plan.md`. Three working hypotheses (H1 Polymarket-as-target, H2 Polymarket-as-feature, H3 Polymarket-as-second-opinion). Phase 1 four-agent fan-out launched.

## Iter 1 (2026-05-24, Phase 1 synthesis and pivot)

Phase 1 returned four research docs:
- `01-historical-inventory.md` (Agent V3-A)
- `02-features-audit.md` (Agent V3-B)
- `03-poly-kalshi-divergence.md` (Agent V3-C)
- `04-literature.md` (Agent V3-D)

### Findings summary

1. **Data shape is acceptable.** n=147 eligible markets across all sports series; NFL team-wins is the workhorse at n=95 with 26 distinct close dates. Max single-team share 6.8% (well below v2's COL 75%). The "147 markets compress to ~37 distinct closing events" caveat means independent observations are fewer than rows; CV must partition by close date.

2. **Polymarket historical price data is structurally unavailable for training.** The CLOB price-history endpoint has a hard ~30-day rich-detail ceiling; older windows degrade or 400. Polymarket order book is current-only. Any Kalshi market that closed > 30 days ago has no recoverable Polymarket history at the T-35d sampling moment.

3. **Polymarket-Kalshi divergence direction is the opposite of what v3 needed.** Of 20 sampled MLB long-horizon Kalshi markets: 65% matched a Polymarket counterpart; 100% of matches had hourly Polymarket history at T-35d; 45% had Kalshi-Polymarket spread > 5c at T-35d; but EVERY pair with > 5c spread had Kalshi HIGHER than Polymarket. Zero pairs in the sample had the "Kalshi cheap relative to Polymarket" signal that would have generated long-Kalshi-YES trades. Polymarket is better calibrated (Brier 0.192 vs 0.264) and tells us v1's favorites are over-priced; that's a fade-v1-trades signal, not an add-v3-trades signal.

4. **Literature ceiling sits at or below C6's pass floor.** Free-public-feature sports prediction tops out at 65-67% game-level accuracy, translating to +1-3pp gross edge on season-long binary markets at the 0.70-0.95 YES band. C6 requires +2pp over v1. The literature gives v3 maybe coin-flip odds of clearing C6 honestly, before any leak-free CV penalty. v3 sample size (n=30-100) is below AFML-recommended T=252 minimum; the gate should be treated as a kill-test, not a discovery test.

### Decision: PIVOT to non-Polymarket external-feature track

**The three originally-stated hypotheses are dead in their current form:**
- H1 (Polymarket-as-target) requires historical Polymarket prices for training. Unavailable per V3-B.
- H2 (Polymarket-as-feature) inherits the same blocker.
- H3 (Polymarket-as-second-opinion) has data shape (65% match rate) but the divergence direction is wrong for adding long-Kalshi-YES trades.

**The honest residual v3 question is:** at n=147 with proper leak-free walk-forward CV, do EXTERNAL TEAM-STAT features improve calibration enough to clear the gate, or does the answer match v2's n=123 finding ("team stats add nothing detectable; model collapses to price")?

This is a clean experiment with two acceptable outcomes:

- **Pass:** v3 model adds detectable lift over v1 baseline (>= +2pp by C6) on the larger n=147 set with multi-sport coverage. Documented signal beyond the literature ceiling.
- **Null:** repeated v2 finding at larger n. Confirms v1 heuristic is the right strategy at our scale. Document and stop.

### Pivot specifics

**Hypothesis H4 (replaces H1/H2/H3):** A small ensemble of team-stat features (Pythagorean differential, run-or-point differential, recent form, lifetime, season-month, league dummy), trained with proper leak-free CV at n=147, does NOT improve v1's calibration enough to pass C6 on its actual domain.

This is a null hypothesis we are TESTING. The experiment either rejects it (v3 model passes the gate) or fails to reject (null finding, v1 confirmed). Either result is publishable as a project deliverable.

**What we DROP from the original v3 plan:**
- Polymarket as feature (data shape blocks training; direction inverts thesis)
- Polymarket as target (same)
- News/sentiment features (Reddit + GDELT) for Phase 2 (deferred to optional Phase 2b if budget allows; orthogonality risk is high)
- the-odds-api features (no free historical)
- 538 ELO frozen (only useful for 2022-2023 Kalshi data which has minimal v1-eligible overlap)

**What we KEEP:**
- The n=147 multi-sport eligible set with NFL focus (n=95).
- The locked 6-criteria gate from `src/kalshi_bot_v2/gate.py` with `trainer=` for leak-free CV.
- The orthogonality protocol from `02-features-audit.md` Section "Orthogonality check protocol".
- The S1/S2/S3 sanity checks from the master plan (no single entity, OOS-only holdout, domain match).

**Features in scope for Phase 2:**
- MLB Stats API team byDateRange stats (effort 1)
- nflverse stats_team_week parquet (effort 2)
- Optional: GDELT TimelineVolRaw news count (effort 2) IF the orthogonality check survives at the dataset stage; otherwise drop.
- Open-Meteo weather is dismissed for season-long markets (per-game weather averages out).

### Deferred future opportunities (not part of v3, but documented for posterity)

1. **Polymarket-as-fade-filter on v1.** When Polymarket prices a v1-favorite below an implied threshold, skip the v1 trade. Defensive overlay, would REDUCE v1's trade count. Could potentially raise v1's hit rate but would also shrink an already-small sample. Not in v3 scope. Documented in `03-poly-kalshi-divergence.md` Section 6.2 as "H3-prime."

2. **Prospective Polymarket-feature build (v4 candidate).** Start logging Polymarket prices daily for v1-eligible Kalshi markets. After 60-90 days, retrain v3-style with Polymarket-as-feature on the new live-collected dataset. Not Phase-2-compatible due to wall-clock delay. Could be a future v4.

3. **Short-Kalshi-YES strategy** (buy NO at low prices when Polymarket disagrees with high-priced Kalshi YES). Requires v1 to start placing NO orders. Strategy change, not v3 scope.

### Updated time budget

Used so far: ~3-4 agent-hours of Phase 1 parallel work. Remaining: ~5-6 hours of the 9-hour budget. Allocation:
- Phase 2 build: 3h (dataset + model)
- Phase 3 critic: 1h
- Phase 4 iterate: 0.5-1h
- Phase 5 final: 0.5-1h

Headroom is tight but sufficient.

## Iter 2 (2026-05-24, Phase 2 build complete)

Phase 2 returned: dataset (V3-B1) + model results (V3-B2). Two research docs:
- `research/v3/05-dataset-build.md` (V3-B1, dataset)
- `research/v3/06-model-results.md` (V3-B2, model + gate)

### V3-B1 outcome

Dataset built at `data/v3/joined_v3_dataset.parquet`, 147 rows. NFL feature-complete 97.1%, MLB 93.75%, NBA/NCAA/NHL 0% (no AS-OF API). Leak audit 0 violations. Orthogonality protocol dropped 11 of 12 candidate features; only `nfl_games_played_pre_t35d` retained (effectively a league-NFL-and-season-progressed dummy, not a true team-stat). NFL training portion is 100% YES; orthogonality cannot honestly evaluate NFL team-stat features in this window. V3-B1's recommendation: Path A (run the gate on the thin survivor feature set) for completeness, with the foreshadow that the result will be a null finding.

### V3-B2 outcome

Three gate evaluations on the locked FULL n=147 split:

| Rule | C1 mean | C2 CI lower | C3 hit rate | C4 n | C5 pooled | C6 v3-v1 | overall |
|---|---:|---:|---:|---:|---:|---:|---|
| G1 v1-baseline | -18.89pp | -32.54pp | 68.89% | 45 | -1.03pp | 0.0pp | **FAIL** |
| G2 LogReg(price) | -18.89pp | -32.54pp | 68.89% | 45 | -1.49pp | 0.0pp | **FAIL** |
| G3 LogReg(price + nfl_gp) | -18.89pp | -32.54pp | 68.89% | 45 | -1.26pp | 0.0pp | **FAIL** |

Binding failures: C1 (mean P&L deeply negative), C2 (CI lower far below zero), C5 (folds 3-4 are -11.8pp and -12.5pp once the chronological window enters the late-season NFL collapse), C6 (G2 and G3 trade identically to v1 because the train set's 96% YES rate saturates the LogReg above 0.70 on every holdout row).

Calibration: G2 Brier 0.281, G3 Brier 0.318; both WORSE than raw favorite_price baseline (0.224). Brier skill score is -0.26 (G2) and -0.42 (G3); both negative. ECE is misleading because most predictions cluster above 0.95.

Sanity checks: S1 (drop top team TB, 4 rows) FAILS for all three rules - the loss is broad-based, not a single-team artifact (this is the OPPOSITE failure mode of v2's COL concentration). S2 (CV OOS verification) PASSES on all 4 folds. S3 (domain-match) reports the holdout's (series, lifetime, price) cells for Phase 3 critic comparison against v1's filled-orders log.

Per-league: NFL-only (n=104) has single-class train (100% YES), G2/G3 abstain entirely. MLB-only (n=16) has C4 structurally unreachable (holdout n=5).

### Root cause (root cause, not just symptom)

Chronological 70/30 split puts ALL NFL favorite-NO outcomes in the holdout. NFL train rows are 78/78 YES; NFL holdout rows are 12/26 YES. No price-or-thin-feature ML rule can flag those 14 NFL NOs because train has zero NFL NOs to learn from. The retained league dummy is wrong-direction OOS (pushes NFL predictions to near-certainty exactly when NFL collapses).

### Verdict: NULL FINDING

v3's H4 hypothesis ("external team-stat features at n=147 with leak-free CV improve v1 by >= +2pp on v1's domain") is REJECTED in the null direction. All four binding gate criteria fail by margins far larger than the locked thresholds. The v3 ML rules cannot find a way to abstain from the bad-outcome NFL holdout rows because the training set provides no NFL counter-examples.

Per the operator brief's "Final note": "If the gate fails (most likely outcome per V3-B1's foreshadow), do NOT treat this as a failure of your work. The honest gate run on the leak-free dataset IS the deliverable." This is that delivery.

### Decision for Phase 3

Proceed to Phase 3 critic. The critic should validate:
1. C5 leak retest (verify S2 finding).
2. Domain-match audit (intersect S3 holdout cells with v1's `data/live_trades/` filled-orders log).
3. Single-entity at sub-categorical level (drop all NFL playoff markets, or one fold's NFL win-totals).
4. False-comparison audit (`v1_decision_fn` unchanged from `gate.py:152-160`).
5. Feature look-ahead retest (spot-check `nfl_games_played_pre_t35d` against NFL schedule for 5 random rows).
6. Multiple-testing audit (confirm G2/G3 hyperparameters were locked, no holdout-tuning).

No iteration is proposed yet. Phase 3 critic is what gates whether we iterate (Phase 4) or write FINAL-VERDICT (Phase 5).

## Iter 3 (2026-05-24, Phase 3 critic returned)

Critic returned at `research/v3/07-critic.md`. Verdict: **CONDITIONAL SIGN-OFF.** Direction (null) correct; framing must be amended on three load-bearing points.

### Critic findings

- **Killer #1: C6 is mechanical equality, not a measured null.** G2 holdout predicted probs min 0.8953, G3 min 0.7039; both >= 0.70 on every row. G2/G3 trade the same 45 rows as v1; v3 minus v1 = 0pp by construction. V3-B2's "v3 fails C6" framing must be rewritten to "v3 was unable to express a v1-differing decision."
- **Important #2: "v1 confirmed" overreaches.** v1's measured `+12.47pp` was on `data/processed/sports_dataset.parquet` (n=39, 17 series-prefixes, ZERO KXNFLWINS). v3 holdout is 49% KXNFLWINS. v1's measured edge has not been demonstrated on the dominant subgroup of v3's failure zone (-40.19pp on the NFL slice).
- **Important #3: S3 domain match materially fails.** v1's live attempted-orders cover 19 distinct series-prefixes (KXBOXING, KXUFCFIGHT, KXWCGAME, KXFOMEN, KXCS2, KXMLBSTATCOUNT, etc.); v3 holdout covers 5; overlap is 2/19 = 10.5%. v3's probe (`scripts/v3/probe_inventory.py:93-156`) hardcoded a 5-family sports series list and skipped 17 series v1 actually trades.
- **Important #4: v1's backtest dataset is structurally narrower than v3's probe.** Same eligibility filter and time window; v1 source returns 39 markets across 17 series-prefixes, v3 probe returns 147 across 8 groups (2.4x disagreement). v1's "+12.47pp" has unknown coverage relative to v1's live universe.
- **Minor #5-7:** Stratified bootstrap retains `season_month` (marginal protocol over-aggression; running the gate with the additional feature makes it FAIL HARDER, so verdict unchanged); Fold-4 boundary is 7 seconds (clean now but tight); feature look-ahead spot-check on 5 NFL rows passed cleanly.

### Critic's other tests that PASSED clean

- C5 leak retest: all 4 folds chronologically clean (verified via `_kfold_splits` re-run).
- Feature look-ahead: clean (5 random rows spot-checked).
- Multiple-testing audit: no hidden hyperparameter sweep; locked constants verified.
- Counter-narratives (60/40 split, 80/20 split, rolling-origin pooled): all fail by similar magnitude. No leak-free gate-design variation flips the verdict.

### Decision: Phase 4 amendments are doc-only

The critic's recommended changes are framing fixes to `06-model-results.md` plus the eventual FINAL-VERDICT. No additional modeling or dataset work needed. Phase 4 is orchestrator-direct documentation amendments.

## Iter 4 (2026-05-24, Phase 4-5 amendments + FINAL-VERDICT)

Orchestrator-direct work:

### 4.1 Amendments applied to `06-model-results.md`

Per Phase 3 critic's "Specific recommended changes" section:

- Verdict TL;DR rewritten to acknowledge mechanical equality of C6, untested v1 KXNFLWINS exposure, and S3 domain-match failure.
- Section 2.1 criteria table: footnote [1] added to C6 rows explaining the structural identity (G2 min predicted prob 0.8953, G3 min 0.7039; LogReg saturates above 0.70 on every holdout row).
- Section 4.3 S3 domain-match: added Phase 3 critic intersection result (2/19 = 10.5% overlap with v1's live attempted-orders).
- Section 6.4 ("What this null finding means"): rewritten from "v1 confirmed" framing to bilateral framing acknowledging that v1's measured edge has untested exposure on KXNFLWINS specifically.
- Section 7 v2 failure-mode table: changed "Domain mismatch PARTIALLY ADDRESSED" to "UNRESOLVED after Phase 3 critic" with explicit citation of the false-comparison failure-mode partial reproduction.

### 4.2 FINAL-VERDICT.md written

`research/v3/FINAL-VERDICT.md` shipped per the master-plan Section 6 structure:

- Question that was asked, in one paragraph.
- Three numbers that matter (gate criteria passed 2/6, holdout mean -18.89pp, NFL slice mean -40.19pp).
- Why operator should accept as complete: H1/H2 dead at Phase 1 (Polymarket data unavailable historically), H3 dead at Phase 1 (divergence direction wrong), H4 dead at Phase 2 (orthogonality dropped 11 of 12 features; chronological train portion is 96% YES).
- What v3 produced with lasting value: probe script, dataset builder, leak-free gate runner, Polymarket-Kalshi divergence baseline, three new literature extractions, Phase 3 critic doc.
- What changes about the live bot: nothing immediate; one operator-relevant flag (v1's backtest source structurally omits KXNFLWINS, exposure is untested but in production scope).
- Future scope items: W1 (rebuild v1 backtest on full sports universe), v4 (Polymarket-as-fade-filter or prospective Polymarket logger).
- Time budget accounting: ~7 of 9 hours used.
- v2 failure-mode comparison table: 5 of 6 prevented, 1 partially reproduced (false comparison) and explicitly noted in the verdict.

### Verdict in one sentence

**v3 closes as a clean null finding with one consequential side-discovery about v1.** External features at n=147 cannot improve over v1 on the available data, AND the v3 holdout reveals that v1's measured edge has never been demonstrated on KXNFLWINS late-season markets, which are 49% of the v3 holdout failure zone.

### Project state update

- Round 9 closed (v3 null finding).
- v1 continues running live unchanged on $32 via Windows Task Scheduler.
- CLAUDE.md and project_kalshi.md memory file to be updated with Round 9 entry.

