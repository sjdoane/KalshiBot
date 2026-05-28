# v10 Methodology Meta: Failure Taxonomy, Plausible Edge Types, and Ranked Angle Proposals

**Author:** Agent v10-S3 (Methodology / Angle Meta-Scout)
**Date:** 2026-05-26
**Round:** 15
**Scope:** Meta-level analysis only. No code, no data pulls, no writes to sensitive paths.
**Budget consumed:** Reads only. Under $1 LLM.

---

## Section 1: Failure-Mode Taxonomy (F1-F10) Across v2-v9

Eight NULLs, one confirmed PHANTOM, two LOO-fragile PARTIALs in shadow-mode limbo across nine ML attempts. The pattern warrants explicit taxonomy before committing to v10. Each failure mode below includes the round(s) where it appeared, its mechanism, and the checklist item that v10 methodology must embed to prevent recurrence.

### F1: Data-Availability Ceiling

**Rounds:** v3 (Polymarket 30-day historical CLOB ceiling), v9 (Kalshi historical orderbook structurally unavailable for settled markets; `?ts=` silently ignored)
**Mechanism:** A data source appears accessible but returns useless data for historical analysis. The ceiling is discovered only after significant scoping work. The v9 version was particularly subtle: the endpoint exists and returns a 200, but the book is empty for settled markets and the timestamp parameter does nothing.
**v9 Phase 3 critic reference:** Test 2 confirmed all alternative historical orderbook paths closed; finding tagged KILLER-REFUTED (no workaround).
**Checklist item for v10:** Before any Phase 2 commitment, a Phase 1 sub-agent must explicitly probe historical data availability on the exact endpoint and time range needed for backtesting. A 200 response is not sufficient; the probe must retrieve actual historical records at a date >= 30 days in the past and verify non-empty content.

### F2: Sample Size Insufficient for Registered Gate

**Rounds:** v2 (n=11 long-horizon MLB, structurally below C4 floor of 15), v9 (n=87 prospective v1-eligible, 6x to 70x below detection floor for the pre-registered +0.014 Brier gate; v9 Phase 3 critic Test 3 showed AIA-implied variance requires n~6,000 for 80% power)
**Mechanism:** The strategy's universe is smaller than required to detect the claimed edge at any reasonable power. v2 was killed before modeling because n=11 was obviously below the locked minimum; v9 required a power calculation to surface the same problem at n=87. Both are the same failure: gate registered without verifying that the universe can produce a verdict.
**Checklist item for v10:** Before locking a gate, compute the minimum detectable effect at 80% power with the actual available n, using the variance structure consistent with the benchmark being borrowed from. If minimum detectable effect exceeds the target gate by more than 2x, the gate is unregisterable with the current universe. Either expand the universe (different series, cross-category, multi-season) or accept a weaker gate explicitly.

### F3: Domain Mismatch / Coverage Gap

**Rounds:** v3 (holdout 49% KXNFLWINS; v1's measured +12.47pp edge on a dataset with zero KXNFLWINS; v4-H confirmed KXNFLWINS mean -1.03pp on n=95), v1 general (edge does not generalize across full sports universe per V4-H finding)
**Mechanism:** The training distribution excludes the categories that dominate the holdout or live universe. A model that "passes" on training data is tested on a systematically different slice. Le 2026 (Section 3: domain-by-horizon interactions explain 26% of calibration variance) provides theoretical grounding: calibration trajectories differ by domain, so domain mismatch is not a sampling accident but a structural issue.
**Checklist item for v10:** For any strategy tested on a sports or multi-category universe, report domain coverage statistics at methodology lock time: what fraction of training data and holdout data each series prefix contributes. If any single series exceeds 30% of either split and has a qualitatively different profile (game-resolution vs season-total, crypto vs sports), flag as mismatch risk and stratify the test.

### F4: Phantom from Stale-Price Proxy

**Rounds:** v5-B (Killer 2c: `last_price_dollars` post-settlement used as NO ask proxy; the losing-side last print is ~$0.01, generating fake +5.98c per-contract edge), v7-B (CONFIRMED PHANTOM via v8-A: `kalshi_mid_at_t` from stale trade-print diverges from live orderbook ask; MMs actively reprice independent of trade fires; live probe 8/8 bets lost, mean -$0.20, binomial p~0.004)
**Mechanism:** The backtest baseline is the last printed trade price rather than the real-time orderbook ask or bid. In thin markets or post-settlement, the trade-print is stale. Any feature that correlates with the true mid appears to have predictive power over the stale proxy even though MMs have already repriced. The +0.208 Brier in v7-B was genuine improvement over the stale proxy; it was zero improvement over the live ask.
**Checklist item for v10:** All backtests must baseline against the orderbook bid or ask at the intended execution time, not the most-recent trade print. For retrospective backtests on settled markets: this is currently IMPOSSIBLE on Kalshi (F1 above), which means ANY retrospective backtest is exposed to this failure mode on the taker side. For maker-quoting strategies, the baseline is the posted bid; for taker strategies, the baseline is the ask. Explicitly verify the data source used for each.

### F5: Methodological Leak

**Rounds:** v2 (C5 leak: label horizon overlap in CV allowed the model to train on future outcome information; Phase 3 critic caught this; gate.py now requires per-fold retraining), v6 (D2 funding-delta cache-edge artifact: 25% of rows contaminated with a feature that contained a timing artifact; did not flip verdict because the feature had no signal anyway)
**Mechanism:** CV or feature construction uses information that would not be available at execution time. The v2 version was a classic label-horizon leak in k-fold. The v6 version was a subtler data-construction timing artifact that contaminated rows but happened not to carry signal.
**Checklist item for v10:** A methodology critic must review the feature construction chronology before Phase 2 and attest that for every row, every feature was computable from data timestamped strictly before the execution decision timestamp. For any CV split, verify that purge buffers equal the maximum label horizon, and that per-fold retraining is enforced (no model trained on the full dataset then evaluated on a fold).

### F6: Single-Feature / Single-Entity Artifact

**Rounds:** v2 (75% of trades vs COL in the MLB dataset; single-team concentration made the model's cross-team generalization meaningless)
**Mechanism:** The dataset is concentrated in one entity, producing a model that fits that entity rather than the general pattern. The artifact is invisible without a concentration audit.
**Checklist item for v10:** Before Phase 2 modeling, run a concentration report: what fraction of rows does the top-1, top-3, and top-5 entity (team, series prefix, strike, or other natural grouping) represent? If top-1 entity exceeds 25% of training rows, add leave-one-entity-out (LOCO) validation explicitly.

### F7: Topic Mismatch for LLM Methods

**Rounds:** v4-B (BSS -2.17; bare LLM on sports with wrong cutoff), v9 (design kill: sports is documented weakest LLM topic across all frontier benchmarks per AIA cluster; Halawi 2024 documents LLM HEDGING in the 0.70-0.95 regime; v4-B also underperformed because of wrong training-cutoff assumption)
**Mechanism:** LLM forecasting evidence is topic-conditional and regime-conditional. Sports is the documented weakest topic: "Future Is Unevenly Distributed" 2025 shows Claude 3.7 sports Brier 0.28 vs geopolitics 0.12 (2.3x worse); Janna Lu 2025 shows o3 sports 37% worse than politics. Halawi 2024 documents LLM hedging specifically in the high-confidence regime (0.70-0.95), which is v1's universe. Any LLM-based strategy on sports confident favorites carries a double penalty: worst topic AND worst regime.
**Checklist item for v10:** If a strategy uses LLM forecasts, specify at methodology lock time: (a) the target price regime (low uncertainty 0.20-0.80 vs confident 0.70-0.95), (b) the target topic, and (c) which benchmark measured the claimed lift. The benchmark's price regime must overlap the target regime, or a regime-specific adjustment must be computed. AIA +0.014 applies to uncertain markets (0.20-0.80) only.

### F8: Gate-Regime Mismatch (new failure mode, v9)

**Rounds:** v9 (pre-registered +0.014 Brier gate sourced from AIA MarketLiquid "hard" = uncertain 0.20-0.80 subset; v1's universe is confident 0.70-0.95; v9 Phase 3 critic Test 5 computed expected lift under generous assumptions at 0.00015, two orders of magnitude below the gate; v9 FINAL-VERDICT Section "Replay-prevention insight")
**Mechanism:** A numerical gate is borrowed from a published benchmark that measured the lift in a different price regime. The gate is formally correct as written but is structurally unachievable in the actual experiment because the mechanism only operates in the benchmark's regime. This is distinct from F7 (topic) and F2 (sample): the universe is large enough, the topic is right, but the gate level is calibrated to a different population.
**Checklist item for v10:** When borrowing a numerical gate from a benchmark (paper, prior round, or external reference), append to the methodology doc: the regime in which the benchmark measured the lift (price band, horizon, market type, news availability). Then verify that the intended target regime is within 0.10 probability-units of the benchmark regime. If not, derive a regime-matched gate from first principles or use the benchmark only as a direction signal, not as a threshold.

### F9: Backward-Incompatible Scope

**Rounds:** v1 W1 (KXNFLWINS denylist added after v1 was live; v1's edge on the non-denylisted residual is YELLOW lean GREEN but fragile seasonally; v9 universe was seasonal -- zero settled KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF in post-Opus-cutoff window)
**Mechanism:** The scope of a strategy or test is time-dependent in ways that are not apparent at design time. Sports universe coverage collapses to boxing and UFC in the May-June off-season. A study designed for a full cross-sport universe runs on a thin, unrepresentative slice.
**Checklist item for v10:** Before committing to a sports-adjacent strategy, audit the calendar: which series resolve in the intended study window (next 30-180 days), and what fraction of the total universe does that represent? If more than 40% of planned volume falls outside the study window due to seasonality, redesign to a category with year-round coverage (crypto, macro, weather, politics) or extend the study window explicitly.

### F10: LOO Fragility

**Rounds:** v4-A (PARTIAL, shadow-mode pending: +1.70pp mean, but LOO collapse to -0.65pp on outlier removal; Bonferroni-corrected TA4 CI includes zero), v5-A (same LOO collapse applies; sportsbook arm contributes zero fires on v3 inventory)
**Mechanism:** The estimated edge depends critically on a small number of large positive outliers. Removing one observation collapses the CI through zero. The gate technically passes on the mean but not on the LOO-robust version. This is documented in Lopez de Prado 2018 (Section 9 of the literature index: multiple-testing correction and purged CV requirements for small-n prediction markets).
**Checklist item for v10:** Before declaring any gate PASS on a sample smaller than n=200, run LOCO (leave-one-cluster-out) validation and report whether the CI still excludes zero after each single-cluster removal. For gate criteria requiring CI exclusion of zero, the CI must exclude zero in LOCO as well as on the full sample, or report as PARTIAL with explicit LOO fragility note.

---

## Section 2: What Types of Edge Remain Plausible

Given F1-F10, what categories of edge have NOT been cleanly ruled out? The eight-NULL prior is strong: any new angle starts at 10-15% unconditional. The analysis below scores each on the left-tail risk of NULL and the specific failure modes it survives or risks.

### 2.1 Maker Quoting in Uncertain Liquid Markets (0.40-0.60 band)

v1 is a maker on confident favorites (0.70-0.95). Whelan 2026 (Section 3: thick-vs-thin equilibria) and Becker 2026 (per-category table: crypto 2.69pp gap, sports 2.23pp gap, weather 2.57pp gap) both confirm maker advantage is real. Bartlett and O'Hara 2026 decompose it into behavioral surplus (retail YES-overbet on NO-settling markets) minus adverse selection.

What we have NOT tested: maker quoting in the 0.40-0.60 (uncertain) price band where Halawi 2024 documents LLM calibration is BETTER and crowd is less reliable. In this regime, Whelan's model predicts the spread Maker captures is smaller per contract but matching probability may be higher (thick equilibrium characteristics at mid-price). The behavioral surplus mechanism (Bartlett) operates differently: retail YES-overbet is weaker at 0.50 than at 0.90, but the competition from sophisticated informed traders may also be weaker because information asymmetry is lower near 0.50.

**Left-tail NULL risk:** Medium-low. The maker advantage is structurally documented across all categories and price bands (Becker covers the full 0-100c distribution). The 0.40-0.60 band is less profitable per-contract than the favorites band (smaller spread) but may be more reliable (better fill rates, less adverse selection per Bartlett). This is NOT a prediction edge; it does not require forecasting. Survives F7 (no LLM), F4 (no stale proxy if using orderbook mid), F3 (category-agnostic by design). Risks: F10 (LOO fragile at small n if targeting specific category), F9 (scope collapse if category is thin).

**Note:** This is the theoretical direction for a "v11" strategic pivot, not necessarily a v10 backtest angle, because it requires live forward data to evaluate fill rates.

### 2.2 Calibration Regime Arbitrage (Le 2026)

Le 2026 (Section 3: domain-by-horizon interactions explain 26% of calibration variance) documents that weather is overconfident at short horizons and underconfident at long horizons, and that politics is chronically underconfident (slope 0.93-1.83 across horizons). The Phase 1.5/1.6 work showed the calibration regime flips for weather specifically; the +9pp edge in Phase 1.5 was the overconfident regime. Other categories have NOT been systematically profiled for regime-horizon mapping.

**Untested sub-question:** Is there a specific (category, horizon) combination where calibration error is large, consistent, and in the same direction over time (not regime-flipping), making isotonic or Platt post-processing reliably profitable? Le's cross-platform replication (politics calibration replicates from Kalshi to Polymarket; weather and entertainment do not replicate to Polymarket) suggests the Kalshi-specific component is largest in weather, politics, and entertainment.

**Left-tail NULL risk:** Medium-high. The Phase 1.6 result (EC-1 killed at OOS gate) showed that even with Le's documented regime structure, the exploitable edge after fees is thin in weather. Politics is chronically underconfident but Diercks 2026 (literature #6) confirms macro and politics markets are priced efficiently by institutions. Entertainment has 4.79pp maker gap per Becker but very low volume (1.5M trades vs sports 43.6M). The sweet spot may not exist at retail scale. Still, cross-category calibration regime mapping using Le's framework and Becker's category data is conceptually clean and has not been done in this project.

### 2.3 Cross-Venue Time-Delay Arbitrage (Ng/Peng/Tao/Zhou 2026)

Ng et al. 2026 (abstract: "Polymarket leads Kalshi in price discovery, particularly when liquidity and trading activity are high") demonstrated the lead-lag relationship for 2024 US politics. The mechanism is order-flow conditional: the venue with greater directional large-trade flow leads.

For 2026 sports: Kalshi at $2.7B/week leads Polymarket US ($5M/week) per the same mechanism. But Polymarket Global at $2.1B/week may lead Kalshi for specific event types where global crypto-native traders have information earlier. v3 was killed at the data layer (Polymarket 30-day historical CLOB ceiling). The v9-A3 scouting report (Candidate 3) proposed a zero-cost probe to check whether the ceiling is still in force.

**Left-tail NULL risk:** Medium-high for sports. The arbitrage windows are "seconds to minutes" per Ng et al. (Quantpedia summary), which is incompatible with a 15-minute polling cadence. For macro events (KXFEDFUNDS, KXCPI, KXNFP) where announcement times are known and the entire price movement happens in 1-5 minutes, a time-lagged cross-venue signal has different dynamics. Ng et al. explicitly measured liquid markets during high-information-flow periods. The FOMC announcement window is exactly such a period.

### 2.4 LLM Forecasting in Regime-Matched Application

v4-B (bare LLM, sports, no tools) NULL at BSS -2.17. v9 (AIA-style LLM ensemble, sports, regime mismatch) NULL at design layer. UNTESTED: LLM with agentic search on UNCERTAIN (0.30-0.70) Kalshi macro/politics markets, where Halawi 2024 documents LLM BEATS crowd (Brier 0.199 vs crowd 0.246 on crowd-predicted-0.3-0.7 subset), and where AIA +0.014 lift was actually measured.

The F8 failure (gate-regime mismatch) in v9 identified this gap explicitly: the pre-registered gate was calibrated to the uncertain-market regime, but the universe was confident favorites. Running LLM on the uncertain-market regime -- where the gate was actually calibrated -- is the logical next step, and it has not been done.

**Left-tail NULL risk:** Medium. The literature evidence for LLM lifting uncertain-market predictions is the strongest published evidence in the project's literature base (Halawi 2024 Section 4: LLM beats crowd on uncertain questions 0.199 vs 0.246). The obstacles are: (a) Kalshi uncertain-market inventory is thin on high-liquidity non-sports categories (macro is efficiently priced by institutions per Diercks 2026); (b) the AIA gate requires n~3,000 per category for 80% power (F2); (c) sports uncertain markets are still sports-weak for LLMs (F7).

### 2.5 Pure Microstructure on Known-Announce-Time Macro Markets

KXFEDFUNDS, KXCPI, KXNFP have known announcement times. In equity options, the vol-crush dynamic at announcement is well-documented (Diercks 2026, Section 4: "Kalshi beats fed funds futures for day-before-FOMC fed funds rate mode forecast"). The analogous Kalshi question: does price systematically drift toward announcement, or does it overshoot and revert in the minutes after announcement?

This is a NEW angle with no prior round coverage in this project. The structural attractiveness: announcement times are deterministic (no seasonal collapse per F9), high volume around announcement (no F2 sample-size concern if aggregating across multiple events per year), and the mechanism does not depend on forecasting -- it depends on order-flow dynamics around a known shock.

**Left-tail NULL risk:** Medium-low. The risk is that institutional MMs (Diercks confirms Kalshi macro is efficiently priced) already arbitrage any predictable announcement drift within seconds. But "efficiently priced" for the day-before-announcement forecast does not imply "no drift in the minutes before announcement." The v6 pattern (fresh-mid sliver: kalshi_cvd_30 showed P(lift > 0) = 98% on per-row bootstrap on n=45 fresh-mid rows) suggests there is micro-regime signal in thin-activity windows. Announcement periods are high-activity, which is the opposite regime. Requires forward-recording of orderbook snapshots at 1-5 minute intervals around announcement events.

### 2.6 Sportsbook Line Movement as Time-Series Feature

v5-A tested STATIC sportsbook-vs-Kalshi divergence (snapshot at one point in time, +1.70pp mean, LOO-fragile). The v9-A3 scouting report (Candidate 9, prior 12-22%) proposed DYNAMIC line movement: does sportsbook move before Kalshi on game-resolution markets? This directly tests whether the F10 fragility in v5-A is a measurement artifact (static divergence is structural, not tradeable) or a real lag (dynamic movement IS tradeable).

**Left-tail NULL risk:** Medium. The $30 the-odds-api Starter provides 5+ seasons of historical odds, enabling a sample of 200-500 qualified game-resolution markets. This is large enough to detect a 3-5pp effect with reasonable power, bypassing F2. The mechanism is distinct from all prior NULLs: it is not ML, not LLM, not crypto microstructure. It is a time-series causality test. Ng et al. 2026 provides the cross-venue lead-lag framework; the sports implementation has not been attempted. Risks: F10 (LOO fragility if signal concentrates in one sportsbook or one sport); F9 (sports seasonality may thin the backtest window).

### 2.7 Maker on NO-Side of Structural YES-Overbet Markets

Bartlett and O'Hara 2026 (abstract: "traders systematically overbet YES in markets that predominantly settle NO, generating a behavioral surplus") document the mechanism. v5-B's Kelly-NO salvage tried to extract this on Statcast prop markets and failed because the NO ask was illiquid (~$1.00 stale price phantom -- F4). The mechanism may exist in OTHER Kalshi categories where retail YES-overbet is structural and the NO side has genuine orderbook liquidity.

Becker 2026 (Table: 5c YES contracts win only 4.18% -- 16pp mispricing) shows the effect is largest in the sub-10c price band. A maker offering NO at the equivalent 95c YES-fair-value price -- in markets where retail consistently overpays for YES -- is the behavioral surplus capture in its purest form. v1 is already exploiting this on the YES side at 70-95c (favorites). The NO side at 5-30c is a different, possibly uncrowded regime.

**Left-tail NULL risk:** Medium-high. The risk is that the sub-10c YES band is heavily MM-competed because the Becker mispricing is well-documented. The 2024 sign flip and Burgi's ψ-compression trend (ψ dropped from 0.048 in 2024 to 0.021 in 2025) suggest the behavioral surplus is being arbitraged away rapidly. By 2026, the sub-10c band may already be efficiently priced.

### 2.8 Recurring Intraday Markets (Self-Supervised)

Kalshi hourly contracts (KXBTCD-1h, KXNFLGAME intraday) recur. Self-supervised learning across recurring instances accumulates sample counts faster than long-horizon markets. v6 tested KXBTCD-1h with classical ML features and got NULL; v7-C confirmed model-class-robust. But self-supervised pretraining on the sequence structure of hourly markets has not been tested. Candidate 5 in the v9-A3 scouting report scored 5-10% prior with engineering cost of $10-20 GPU + 30-60h build.

**Left-tail NULL risk:** High. v7-C's TabPFN result (ties LightGBM within +0.00040 Brier) is model-class-robust: the NULL is not an architecture issue, it is a signal issue. The Kalshi mid absorbs all available information at sub-hour horizons in crypto. A transformer pretrained on the same price sequences will replicate the mid's information content, not add to it. Without genuinely new features that pretraining could extract (e.g., sequence patterns invisible to classical features), this is near-known-null.

---

## Section 3: v10 Angle Proposals, Ranked

The updated context after v8-A: v7-B is CONFIRMED PHANTOM (8/8 bets lost, -$1.60, binomial p~0.004). Candidate 7 (v8-A prospective recovery) is eliminated. The ranked list below updates v9-A3's Ranked Top-3 accordingly.

### Proposal 1 (Rank 1): Sportsbook Dynamic Line Movement on Game-Resolution Markets

| Field | Value |
|---|---|
| Name | Line-movement lead-lag on KXNFLGAME / KXMLBGAME |
| Hypothesis | When a major sportsbook (DraftKings, FanDuel, Pinnacle) moves a game-result line by >= 3 basis points in the 1-6 hours before a Kalshi game-resolution market closes, Kalshi mid lags and a taker position at the stale Kalshi mid captures the adjustment before settlement. |
| Target market category | KXNFLGAME, KXMLBGAME, KXBOXING, KXUFCFIGHT (game-resolution, not season-total) |
| Methodology | the-odds-api Starter historical pull (2021-2026 NFL/NBA/MLB), join to Kalshi historical trades and mid via existing v6 build pattern; compute sportsbook line change over T-6h to T-1h window; orthogonality screen: does line-change magnitude predict Kalshi mid change in the same window? Gate: regression beta > 0 with bootstrap CI excluding zero at n >= 100 qualified events; LOO-robust at k=10 club removal. |
| Regime-matched gate | v5-A's static snapshot measured +1.70pp at n=147. The dynamic version requires n >= 100 qualified game-resolution events with >= 3bp sportsbook move AND Kalshi mid available at the same time. Bootstrap CI excluding zero on the taker P&L of following sportsbook direction is the binding criterion. LOCO across sport types required per F10. |
| Prior | 15-22% |
| Cost | $30 one-time (the-odds-api Starter, within authorized budget) + $0 Kalshi historical |
| Wall-clock | 5-8 days (data pull 1-2d, join 1d, analysis 1-2d, critic 1d) |
| Failure modes survived | F2 (n=200-500 qualified events available across 5 seasons), F4 (feature is sportsbook price change, not Kalshi stale print), F5 (line-movement timing is unambiguous), F7 (no LLM), F8 (no borrowed gate), F9 (game-resolution markets are year-round unlike season-total) |
| Failure modes risked | F3 (sport-type concentration: NFL may dominate sample; LOCO by sport required), F10 (LOO fragility remains if signal comes from a single sport or bookmaker), F1 (Kalshi historical trades available but mid reconstruction requires verification against v7-B phantom constraint) |
| Novelty | NEW. Distinct from v5-A (static snapshot) and from any prior round. |

Cross-reference vs v9-A3 Rank 2: this is the same angle. v9-A3 listed it at 12-22% prior; updated to 15-22% given v8-A PHANTOM confirmation (removes the competing explanation that the orderbook lag is the source of divergence). The v8-A result narrows the explanation space: if Kalshi MMs reprice continuously against spot in crypto, they may NOT reprice continuously against sportsbook in sports (different information channel, different MM behavior).

### Proposal 2 (Rank 2): Kalshi-Internal Microstructure on Game-Resolution Sports Series

| Field | Value |
|---|---|
| Name | CVD and quote imbalance on KXNFLGAME / KXBOXING / KXUFCFIGHT |
| Hypothesis | Game-resolution sports markets have retail-dominated, news-driven trade flow with CVD signal at T-24h to T-1h that v6's hourly-crypto NULL does not cover, because the participant mix and information arrival structure differ fundamentally from KXBTCD-1h. |
| Target market category | KXNFLGAME, KXMLBGAME, KXBOXING, KXUFCFIGHT |
| Methodology | Reuse v6 `build_v6_master.py` pattern with series-prefix change; collect Kalshi historical trades for game-resolution markets; compute CVD at T-24h, T-6h, T-1h horizons; orthogonality screen per v6 K1 protocol against orderbook mid (F4 constraint); gate: +0.005 Brier improvement threshold (same as v6). |
| Regime-matched gate | v6's K1 threshold (+0.005 Brier improvement on held-out midband) is appropriate: same methodology, same currency. The binding question is whether n is large enough. Game-resolution NFL season has 272+ regular season games/year, producing 272+ KXNFLGAME markets with historical trades available. Add MLB (162+ games/year) and combat sports. Total n potentially 500-800 pre-post-flip qualified markets, far above v6's n=971 at T-30. |
| Prior | 12-18% |
| Cost | $0 (Kalshi API read key exists; v6 scripts reusable) |
| Wall-clock | 3-6 days (data pull 1-2d, build 1d, analysis 1d, critic 1d) |
| Failure modes survived | F1 (historical trades available for settled game-resolution markets -- distinct from orderbook history), F2 (n=500-800 is adequate power), F4 (CVD computed from historical trades, not stale print -- methodology critic must verify sign convention per v6 Killer-1), F7 (no LLM), F9 (game-resolution markets are not seasonal) |
| Failure modes risked | F3 (sport-type concentration -- NFL volume likely dominates; LOCO required), F5 (v6 Killer-1 CVD sign inversion was caught by methodology critic; must re-verify empirically on sports tape before Phase 2), F10 (LOO fragility if CVD signal concentrates in one team or one sport type) |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL. v6 explicitly flagged this as uncovered; game-resolution sports is a mechanistically distinct market type from KXBTCD-1h. |

Cross-reference vs v9-A3 Rank 3: identical angle. Updated prior upward slightly (10-18% to 12-18%) because v8-A PHANTOM result confirms that Kalshi MMs maintain real-time crypto prices; sports game-resolution markets with retail-heavy flow may have slower MM repricing.

### Proposal 3 (Rank 3): Regime-Matched LLM Forecasting on Uncertain Kalshi Politics/Macro Markets

| Field | Value |
|---|---|
| Name | AIA-recipe LLM ensemble on KXFEDFUNDS / KXCPI / KXELECTION (uncertain band) |
| Hypothesis | An AIA-recipe LLM ensemble (agentic search + Platt scaling + 67% market / 33% AI weight) on Kalshi macro/politics markets in the 0.30-0.70 price band produces measurable Brier lift consistent with Halawi 2024's documented LLM-beats-crowd result in the uncertain regime, resolving the F8 failure mode by targeting the correct regime. |
| Target market category | KXFEDFUNDS, KXCPI, KXNFP, KXELECTION (any category where Kalshi mid sits 0.30-0.70 and market liquidity is >= $10k notional) |
| Methodology | v9's `02-recipe-methodology.md` AIA replication spec is a complete blueprint and reusable verbatim. Universe probe to identify 0.30-0.70 open markets with >= 30d horizon; prospective pilot of n=30-50 forecasts (one per market, at T-30d); Brier point estimate against orderbook mid at forecast time (F4 constraint); report with 95% CI; descriptive only (not a gate verdict at this sample size per F2). Full gate verdict requires n >= 500 and a 6-month prospective rolling study. |
| Regime-matched gate | For a pilot at n=30-50: descriptive pilot only; Brier_delta point estimate with sign and CI as the deliverable, not a SHIP/NULL verdict. For a gate-worthy verdict: n >= 500, 80% power at delta=0.005 (the correct regime-matched lift from AIA ensemble vs market), rolling 6-month accumulation. |
| Prior | 20-28% (the Halawi 2024 uncertain-market LLM-beats-crowd result is the strongest evidence-backed prior in the literature base for any LLM application) |
| Cost | $3-5 LLM for n=30-50 pilot + $0 external |
| Wall-clock | 2-4 weeks to get n=30-50 resolutions if targeting 30-45 day markets |
| Failure modes survived | F8 (regime-matched: uncertain 0.30-0.70 target matches where AIA measured +0.014), F7 (politics/macro is NOT the documented LLM-weak topic; sports is), F9 (politics and macro markets are year-round), F4 (baseline is orderbook mid at forecast time, not stale print) |
| Failure modes risked | F2 (pilot n=30-50 is not gate-worthy; full verdict requires 6-month accumulation), F3 (politics markets may have domain coverage gaps if specific elections are off-cycle), F9 (macro announcement schedule may cluster certain months) |
| Novelty | NEW relative to all prior rounds. v4-B was no-tools sports confident-favorites (wrong regime, wrong topic). v9 was agentic-tools sports confident-favorites (wrong regime). This is agentic-tools politics/macro uncertain-band: three distinct changes simultaneously, each fixing a documented failure mode. |

Cross-reference vs v9-A3: this angle was NOT in A3's 9-candidate list. A3's list was dominated by crypto and sports angles; it did not include a regime-corrected LLM application. The v9 FINAL-VERDICT Section "Replay-prevention insight" and v9 Phase 3 critic Test 5 explicitly described this as the correct re-design: "a revised design for any future Angle A attempt should either expand the price band to AIA's uncertain-market regime (0.20-0.80)." This proposal implements that re-design.

**Ranking rationale:** Prior of 20-28% is the highest in the list because Halawi 2024 is direct empirical evidence for the claimed mechanism in the exact regime. The pilot cost ($3-5 LLM) is lower than Proposals 1 or 2. The risk is that n=30-50 is only a descriptive pilot; a gate-worthy result requires months of accumulation. If the operator's preference is a session-final verdict, Proposals 1 or 2 are faster to verdict. If the operator's preference is the highest prior-evidence angle with willingness to accumulate over months, Proposal 3 is the right call.

### Proposal 4 (Rank 4): Cross-Category Calibration Regime Mapping (Le 2026 Framework)

| Field | Value |
|---|---|
| Name | Calibration regime audit across Kalshi categories using Le 2026 decomposition |
| Hypothesis | Applying Le 2026's four-component calibration decomposition to Kalshi's post-flip (October 2024+) data reveals one or more (category, horizon) combinations with large, consistent, same-direction calibration error that isotonic/Platt post-processing can extract as a maker edge after fees. |
| Target market category | All Kalshi categories with post-October 2024 data; focus on Entertainment (4.79pp Becker gap) and World Events (7.32pp Becker gap), which have the largest documented mispricing and least MM competition. |
| Methodology | Pull Kalshi `/historical/markets` and `/historical/trades` across all categories post-October 2024; replicate Le's slope estimation (logistic recalibration slope by domain x horizon bin); identify (category, horizon) cells with slope consistently > 1.10 or < 0.90 and n >= 100 in the cell; check whether the bias is in the maker-extractable direction (makers post limit orders at stale mid). Gate: same as EC-1 Phase 1.6 OOS ECE ratio test, adapted for the identified category. |
| Regime-matched gate | Category and horizon specific: the calibration slope for the identified cell must be reproducible on a held-out 20% time-slice and must produce ECE ratio > 1.20 (same EC-1 threshold). |
| Prior | 10-18% |
| Cost | $0-5 LLM + $0 external (Kalshi API read key sufficient for all categories) |
| Wall-clock | 5-10 days |
| Failure modes survived | F7 (no LLM prediction), F4 (calibration analysis uses settled outcomes, not proxies), F5 (no CV; pure descriptive calibration slope estimation) |
| Failure modes risked | F2 (Entertainment and World Events have thin volume: 1.5M and 0.2M trades respectively -- small cells may be underpowered), F3 (domain coverage: the Le slope analysis requires >= 50 settled markets per cell), F9 (Entertainment event calendars may be seasonal) |
| Novelty | NEW. EC-1 tested weather calibration in a single regime (Phase 1.6). Systematic cross-category mapping using Le's framework has not been done. |

Cross-reference vs v9-A3: not in A3's list. A3 was scoped before the v9 failure-mode taxonomy was written; this proposal follows directly from Le 2026's four-component structure and the F3/F9 lessons about domain mismatch.

### Proposal 5 (Rank 5): Polymarket Depth Re-Probe + Redux

| Field | Value |
|---|---|
| Name | Polymarket historical CLOB depth re-probe and v3 redux if ceiling lifted |
| Hypothesis | Polymarket's 2026 `/prices-history` endpoint has expanded beyond the 30-day ceiling that killed v3 at the data layer; if 90+ days of historical depth is now available, a backtest at n >= 100 Kalshi-parallel markets is feasible and the v3 direction finding (Kalshi prices higher than Polymarket on favorites) becomes a testable taker signal. |
| Target market category | Any Kalshi market with a parallel Polymarket listing (politics 2026-2028, crypto, macro) |
| Methodology | Single WebFetch probe to verify depth: retrieve Polymarket `/prices-history` for a 90-day-old resolved market and check non-empty result. If ceiling lifted: fetch all Kalshi-parallel markets, compute divergence at T-30d snapshots, run v3-H4 style backtest on divergence as taker signal. If ceiling still at 30 days: close at $0. |
| Regime-matched gate | If data available: same as v4-A gate (CI excluding zero on mean P&L improvement, LOO-robust). |
| Prior | 5-15% conditional on data probe success. 3-8% unconditionally (80%+ probability ceiling is still at 30 days based on v3 timing and Polymarket's historical retention policy). |
| Cost | $0 probe; $3-5 LLM if backtest runs |
| Wall-clock | 1-2 days if probe succeeds; 30 minutes if it fails |
| Failure modes survived | F7, F8 (no LLM, no benchmark gate borrowed) |
| Failure modes risked | F1 (data ceiling may still apply), F10 (LOO fragile if signal concentrates in election-specific markets), F3 (Ng et al. 2026 shows lead-lag direction inverts for sports 2026) |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL (v3 was the prior attempt) |

**Recommendation note:** This is a 30-minute zero-cost probe before committing to any other angle. Run it first. If ceiling has expanded, it upgrades Proposal 5 substantially (data is the only prior kill reason). If ceiling is unchanged, eliminate at $0.

---

## Summary: Ranked Decision Tree for Operator

| Rank | Proposal | Prior | Cost | Wall-clock | Session-final verdict? |
|---|---|---|---|---|---|
| 1 | Sportsbook Dynamic Line Movement | 15-22% | $30 | 5-8 days | YES (if n >= 100 achieved) |
| 2 | Game-Resolution Sports Microstructure | 12-18% | $0 | 3-6 days | YES |
| 3 | Regime-Matched LLM on Uncertain Politics/Macro | 20-28% | $3-5 LLM | 2-4 weeks (resolutions) | Descriptive pilot only; gate-worthy requires 6 months |
| 4 | Cross-Category Calibration Regime Mapping | 10-18% | $0-5 LLM | 5-10 days | YES if cell n >= 100 |
| 5 | Polymarket Depth Re-probe | 5-15% cond. | $0 probe | 30 min probe | YES if data exists |

**Operator recommendation:** Run Proposal 5 (Polymarket probe) in the first 30 minutes as a free information update. If ceiling lifted, escalate Proposal 5 to primary alongside Proposal 1.

If the operator wants a session-final verdict at lowest cost with highest prior, Proposal 2 (game-resolution microstructure) at $0 and 3-6 days is the natural first run. It reuses v6 infrastructure directly and explicitly fills a gap the v6 FINAL-VERDICT identified.

If the operator is willing to spend $30 for higher sample quality, Proposal 1 (sportsbook line movement) is the primary with highest expected value per dollar: the $30 buys 5 seasons of historical odds, yielding n=300-500 qualified events vs v6's n=971 which was a mid-tier sample. The dynamic-vs-static distinction from v5-A also gives a clean falsification test.

Proposal 3 (regime-matched LLM) has the highest stated prior (20-28%) because Halawi 2024's uncertain-market LLM result is direct empirical evidence, but it cannot produce a gate-worthy verdict in a single session. It should be wired as a prospective rolling study if the operator has a 3-6 month horizon for evaluation.

---

*Anti-em-dash verification note: this document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout.*
