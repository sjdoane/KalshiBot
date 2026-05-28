# v11 Methodology Meta-Critique: Pre-Registered Failure-Mode Defenses (F1 to F11)

**Author:** Agent v11-A3 (Methodology meta-critic)
**Date:** 2026-05-27
**Round:** 16
**Target:** v11 Track 1 (sportsbook line-movement lead-lag on Kalshi game-resolution markets)
**Source taxonomy:** `research/v10/03-methodology-meta.md` (F1 to F10) plus `CLAUDE.md` Round 15 V10-A kill (F11 added)
**Scope:** Pre-Phase-1.5 critique. Defines the per-failure-mode methodology requirements and numerical gates that the Phase 1.5 lock MUST embed BEFORE any Phase 2 data pull. No code, no data pulls.
**Budget reserved:** $0.80 LLM. Actual: reads plus this single generation turn.

---

## v11 Track 1 hypothesis under critique

"When a major US sportsbook moves a game-result moneyline implied probability by >= some-threshold pp in the T-6h to T-3h window before a Kalshi game-resolution market closes, AND Kalshi mid has moved < smaller-threshold pp in the same window, taking the side sportsbook moved toward at the stale Kalshi ask captures a positive net-of-fee edge."

Status: NOT YET LOCKED. The critique below specifies what the lock document must contain to defend against each F-mode. Specific numeric thresholds (>= X pp, < Y pp) are NOT pre-registered here; that is the Phase 1.5 lock's job. What IS pre-registered here is the FORMULA each gate must take and the structural choice for each ambiguous design decision.

The strategy decomposes into three operational layers, each with distinct F-mode exposure:

- **Signal layer:** sportsbook line movement detection in the T-6h to T-3h window.
- **Trigger layer:** join to Kalshi mid in the same window, divergence check.
- **Execution layer:** taker BUY at the Kalshi ASK at T-3h or later (NOT at the trade-print mid).

The F-mode analysis below maps each mode to the layer it threatens.

---

## F1: Data ceiling, coverage, dropout

**Prior round citations:** v3 Polymarket 30-day historical CLOB ceiling killed v3 at the data layer; v9 Kalshi historical orderbook structurally unavailable for settled markets (`?ts=` silently ignored); V10-A Round 15 Becker n=72.1M trades looked sufficient until F11 surfaced the field-level gap.

**v11 Phase 1.5 must include:**

a) The Becker-to-odds-api timestamp-matching tolerance, pre-registered numerically. Becker trades carry `created_time` (Unix seconds); the-odds-api Starter returns historical odds at snapshot intervals that are bookmaker-dependent (typically 5 to 60 minutes). The lock must state: "A Kalshi trade at time t joins to the most recent the-odds-api snapshot at or before t, provided (t minus snapshot_time) <= MAX_LAG_SECONDS; otherwise the event is excluded from the qualified universe." Pre-register MAX_LAG_SECONDS based on the actual the-odds-api snapshot cadence (Phase 1 agent v11-A2 to surface this). Default proposal: MAX_LAG_SECONDS = 1800 (30 minutes). The lock document must also state what happens to a Kalshi market that has no the-odds-api snapshot in the T-6h to T-3h window (most likely answer: excluded, not extrapolated).

b) **Coverage gate (pre-registered):** the qualified-event universe after timestamp-join must yield n_events >= N_MIN_QUALIFIED across the full backtest window, where N_MIN_QUALIFIED is computed from the F2 minimum-detectable-effect calculation (see F2 below). Suggested floor: N_MIN_QUALIFIED = 200 across all sports combined.

c) **Open question for Phase 2 to surface:** What fraction of Becker game-resolution markets in the T-6h to T-3h window have at least one corresponding the-odds-api snapshot? If the coverage rate is below 60%, F1 has resurfaced and the strategy is in a dropout regime that systematically excludes the markets sportsbooks moved during.

---

## F2: Sample size insufficient for registered gate

**Prior round citations:** v2 n=11 long-horizon MLB markets (structurally below the C4 floor of 15); v9 n=87 v1-eligible prospective markets at the AIA +0.014 Brier gate (6x to 70x below the n=6000 power requirement).

**v11 Phase 1.5 must include:**

a) A power calculation BEFORE the lock fires. Compute minimum detectable effect at 80% power, alpha 0.05, two-sided, using the variance estimator appropriate for v11 (per-event P&L variance from the Becker post-October-2024 game-resolution sample). If MDE_80 exceeds 2x the threshold the strategy needs to clear net of fees, the gate is unregisterable and the strategy must either expand the universe (more seasons of the-odds-api, more sports) or accept a weaker descriptive verdict explicitly.

b) **Pre-registered numerical gate:** n_qualified_events >= max(N_MIN_QUALIFIED from F1, n_required_for_80pct_power(target_MDE = 2 cents per contract net of fee)). The 2-cent net target is derived from Kalshi's fee schedule (approximately 7% of (winning_price minus 0.5) per contract per Kalshi's published fee formula, capped at 7c per contract); a strategy that nets less than 2 cents per contract after fees on the average winning trade is structurally fragile and below the Becker tight-spread historical-baseline noise floor surfaced in Round 15 (1c MM-saturated spreads on Becker tight-spread markets per CLAUDE.md memory). Worked formula: n_required = (2 * 1.96 * sigma_per_event / target_MDE)^2 where sigma_per_event is bootstrapped from a 100-event Becker pilot before the full backtest fires. Lock must contain the actual computed number, not the formula alone.

c) **Open question for Phase 2 to surface:** The per-event variance sigma_per_event is unknown until the Becker pilot runs. The lock must register: "Phase 2 first computes sigma on a stratified 100-event pre-pilot subset, then evaluates whether the remaining universe meets n_required. If not, no full backtest fires." This is a hard gate, not a soft suggestion.

---

## F3: Domain mismatch and coverage gap

**Prior round citations:** v3 holdout was 49% KXNFLWINS while v1's measured +12.47pp edge was on a dataset with zero KXNFLWINS markets; V4-H rebuild surfaced KXNFLWINS mean -1.03pp on n=95 and KXMLBPLAYOFFS -27.84pp on n=5. v1 edge does not generalize across the full sports universe per V4-H. Round 15b/c v1-aggregate OOS decay to -0.23pp also fits F3.

**v11 Phase 1.5 must include:**

a) A pre-locked sport-coverage report at lock time AND at backtest result time. v11's hypothesis is multi-sport (NFL, NBA, MLB, NHL, soccer, plus boxing/UFC if sportsbook odds available). The lock must report what fraction of qualified events each sport contributes, with the lock failing if any one sport exceeds 50% of the qualified-event universe and that sport is in a structurally different category from the others (game-resolution NFL vs in-game continuous MLB vs round-by-round UFC). Stratification by sport is then required.

b) **Pre-registered numerical gate (F3 stratification):** for each sport contributing >= 20% of qualified events, the per-sport mean net P&L must be positive with the per-sport bootstrap 95% CI's lower bound above the per-sport per-trade fee cost. Sports below the 20% contribution floor are reported but not gated individually (insufficient n). At least 3 sports must clear the per-sport gate (not just the pooled gate).

c) **Open question for Phase 2:** the-odds-api Starter coverage by sport-season is not uniformly known. If the actual qualified-event distribution turns out to be 70% NFL because the-odds-api has the densest NFL coverage, the lock must trigger redesign (expand to additional bookmakers or accept the lock fires only on the NFL slice with an explicit single-sport verdict).

---

## F4: Trade-print versus orderbook ASK confusion

**Prior round citations:** v5-B Killer-2c surfaced this when post-settlement `last_price_dollars` (~$0.01 losing-side last print) generated a fake +5.98c per-contract edge; v7-B `kalshi_mid_at_t` from stale trade-print produced +0.208 Brier improvement over the stale proxy but +0.000 over the live orderbook ask; v8-A live test confirmed 8 of 8 strong signals lost (mean -$0.20, binomial p ~0.004). v10A KILLER-1 propagated the same issue into the Becker dataset.

**v11 nuance (load-bearing):** trade-print mid is the FEATURE in v11, not the baseline. The hypothesis ASKS whether sportsbook movement leads Kalshi trade-print movement. v11 is NOT measuring v7-B-style Brier improvement over the orderbook ask. The strategy USES the staleness of Kalshi trade-print mid relative to sportsbook as the signal. But the EXECUTION at the end of the backtest is via a taker fill at the Kalshi ASK, which is structurally different from the trade-print mid. The methodology must distinguish the two and pre-register one of two resolutions.

**v11 Phase 1.5 must include:**

a) **Resolution choice, pre-registered (pick ONE, no post-hoc):**

- Option A (live spot-check): the backtest reports edge using trade-print mid as the execution proxy, AND in parallel, a live forward spot-check runs for at least 30 calendar days BEFORE any capital is risked. The spot-check posts no orders; it pulls the live orderbook ask and the most-recent trade-print for any candidate market during the T-6h to T-3h window and records (ask_minus_print) per snapshot. If the median (ask_minus_print) across the spot-check sample is >= 2c, the backtest's trade-print-baseline edge is reduced by 2c per trade in the final result and the strategy must still pass the F2 gate after this haircut.

- Option B (worst-case haircut, no live spot-check required): every backtest trade pays a deterministic execution haircut equal to the 75th-percentile (ask_minus_print) observed in the Becker MARKETS snapshots (the orderbook snapshot table) joined to the same trade timestamp via the nearest-snapshot rule. If the 75th-percentile haircut cannot be computed (snapshot coverage too thin), Option A is mandatory.

**v11-A3 recommendation: Option B is preferred** because Option A delays the verdict by 30+ days and exposes the strategy to seasonal sport shifts (F9) during the spot-check window. Option B is computable entirely from the Becker dataset and produces a session-final verdict.

b) **Pre-registered numerical gate (F4):** after the chosen execution-haircut treatment is applied, the mean per-trade net P&L (gross P&L minus 7% Kalshi fee minus execution haircut) must remain >= 1c per contract with the bootstrap 95% CI lower bound above 0. This is in addition to the F2 sample-size gate.

c) **Open question for Phase 2:** the Becker MARKETS snapshot table cadence (per CLAUDE.md V10-A finding: irregular `_fetched_at`) may not include the T-6h to T-3h window for many events. If MARKETS snapshot coverage in the execution window is below 50%, Option B's 75th-percentile haircut is itself a phantom and Option A becomes mandatory regardless of the time cost.

---

## F5: Single-strategy bias and no comparator

**Prior round citations:** F5 in the v10 taxonomy covered methodological leak (label-horizon overlap in v2 C5; v6 D2 funding-delta cache-edge artifact). The v11-specific interpretation per the brief is "single-strategy bias and no comparator," which combines the original F5 with the absence of a falsification baseline.

**v11 Phase 1.5 must include:**

a) Two pre-registered comparator strategies that run on the same qualified-event universe and same execution model as the v11 hypothesis. Comparator 1: random-side taker (buy YES or NO at the Kalshi ask with equal probability, regardless of sportsbook signal). Comparator 2: anti-signal taker (take the side OPPOSITE to where sportsbook moved). The v11 hypothesis must beat BOTH comparators on mean net P&L with non-overlapping bootstrap 95% CIs.

b) **Pre-registered numerical gate (F5):** v11_mean_net_pnl - comparator_mean_net_pnl > 0 with bootstrap 95% CI excluding zero, separately for each comparator. The anti-signal comparator is the strict falsification test: if the v11 signal carries information, the anti-signal must lose; if both win or both lose, the v11 signal is a base-rate artifact (consistent with the F9 side-selection-bias warning in Round 15b/c). Additionally, the lock must specify per-fold purge buffer equal to MAX_LABEL_HORIZON (the Kalshi market resolution time minus the signal-fire time, maximum across the universe; for game-resolution markets this is 3 to 6 hours).

c) **Open question for Phase 2:** if Comparator 2 (anti-signal) shows positive net P&L because the Kalshi maker-quoting environment is structurally favorable to takers (Round 15b/c found 5 prefixes with persistent positive maker edge; the inverse implication for takers is structurally negative, but the magnitude on game-resolution markets is unknown). If anti-signal is also positive, the v11 hypothesis's true marginal contribution is v11 minus anti-signal, not v11 minus zero.

---

## F6: Compounded multiple-test inflation

**Prior round citations:** Bonferroni reduction applied retroactively to v4-A and v5-A; F6 in the v10 taxonomy covered single-feature / single-entity artifact (v2 75% COL concentration). The v11-specific interpretation per the brief is multiple-comparison inflation.

**v11 Phase 1.5 must include:**

a) A pre-registered count of the total number of hypothesis tests v11 will fire. Specifically: how many (threshold pair, sport, bookmaker) cells will be evaluated. The hypothesis takes the form "fire if sportsbook moves >= X_pp AND Kalshi moves < Y_pp" with X and Y free parameters. Without pre-registration, a grid search over (X in {3, 5, 7, 10}, Y in {0.5, 1, 2, 3}, sport in {NFL, NBA, MLB}, bookmaker in {DraftKings, FanDuel, Pinnacle}) yields 4 * 4 * 3 * 3 = 144 cells, each individually testable. A nominal alpha 0.05 across 144 cells yields a 99.94% probability of at least one false positive under the null. The lock must either (i) pre-register a single (X, Y, sport, bookmaker) tuple from theory before seeing the data, or (ii) apply Bonferroni or Benjamini-Hochberg correction to the alpha used in the bootstrap CI gate.

b) **Pre-registered numerical gate (F6):** if K hypothesis cells are evaluated, the bootstrap CI gate must use alpha_corrected = 0.05 / K (Bonferroni) for the primary verdict OR Benjamini-Hochberg FDR at q = 0.05 with the discovery rule that the lowest-p cell must clear q-corrected alpha. The lock must commit to one. Recommended: Bonferroni for K <= 20 (transparent), BH for K > 20 (less conservative). If the analyst's intent is a single best-cell selection rule rather than a "any cell passes" rule, the lock must state that the primary verdict is on the SINGLE pre-registered cell and all other cells are descriptive only.

c) **Open question for Phase 2:** the natural pre-registration for v11's threshold pair (X, Y) is to derive from theory: X = the median sportsbook 3-hour move on game-resolution events (so the strategy fires on above-median moves), Y = the median Kalshi 3-hour move conditional on a sportsbook above-median move (so "Kalshi did not move" is operationally defined). Both medians are estimable from the Becker plus the-odds-api join WITHOUT looking at the P&L outcome. Phase 1.5 should pre-register that the threshold pair is set at these medians on a 50%-time-stratified development split, with the validation split used only for the final gate.

---

## F7: Stale post-settlement price as edge proxy

**Prior round citations:** W2 +5.98c phantom from `last_price_dollars` post-settlement (v5-B Killer-2c); the v10 taxonomy F7 covered topic mismatch for LLM methods (v4-B sports BSS -2.17), which is not applicable to v11. The v11-specific interpretation per the brief is post-settlement stale-price proxy.

**v11 Phase 1.5 must include:**

a) An explicit ban on using any Kalshi price field timestamped at or after the official market resolution time. The Becker trades table contains trades up to and possibly including the settlement print (which Kalshi sometimes generates as a system fill at 0c or 100c for the losing or winning side). The lock must specify: signal computations and execution-price proxies use ONLY trades with `created_time < market_close_time MINUS BUFFER_SECONDS`. BUFFER_SECONDS pre-registered. Suggested: BUFFER_SECONDS = 60 (one minute before official close, matching Kalshi's typical pre-close trading-halt timing for game-resolution markets).

b) **Pre-registered numerical gate (F7):** zero post-settlement trades in either the signal window or the execution window. This is a hard binary check at backtest time: the loader function returns the count of trades with `created_time >= market_close_time - 60`, and if any such trade appears in the qualified universe, the loader fails and the backtest aborts. Implemented as an assertion, not a warning. The lock document must contain the assertion's text.

c) **Open question for Phase 2:** Becker's `created_time` precision and Kalshi's `market_close_time` precision may not match (different timezones, possible UTC vs ET mismatch). The loader must verify both are in UTC seconds before applying the buffer rule.

---

## F8: Gate-regime mismatch

**Prior round citations:** v9 pre-registered +0.014 Brier gate sourced from AIA MarketLiquid uncertain 0.20 to 0.80 subset; v1's universe was confident 0.70 to 0.95 favorites; expected lift under generous assumptions was 0.00015 (two orders of magnitude below the gate). The v9 FINAL-VERDICT replay-prevention insight was: do not borrow a numerical gate from a benchmark measured in a different price regime.

**v11 nuance (load-bearing per brief):** v11's hypothesis IS regime-specific to game-resolution markets in the sportsbook-leading regime. Whether that regime actually holds is the empirical question. The gate must NOT borrow a number from a different regime. The gate must be derived from cost structure (Kalshi fees) plus LOCO-robust CI excluding zero in each sport.

**v11 Phase 1.5 must include:**

a) An explicit ban on importing the v1 +12.47pp number, the AIA +0.014 Brier number, the Becker +3.58% to +4.25% maker excess return numbers from Round 15b/c (which were MAKER edges in a regime where v11 is a TAKER), or any other prior-round numerical threshold. The v11 gate is derived from first principles. The derivation: target_per_trade_net_pnl > Kalshi_fee_per_trade_at_target_price + execution_haircut + 1c safety buffer. Worked example assuming execution price 0.55 (the modal game-resolution market mid in the qualified universe; to be confirmed in Phase 2): Kalshi fee = 0.07 * (0.55 - 0.5) = 0.0035 dollars = 0.35c; haircut from F4 Option B = 1c to 3c (placeholder; actual from Becker MARKETS snapshot); safety = 1c. Total target_per_trade_net_pnl >= 2c to 5c per contract.

b) **Pre-registered numerical gate (F8):** mean per-trade net P&L > (Kalshi_fee + F4_haircut + 1c) with bootstrap 95% CI lower bound above this same threshold (not above zero). This is a STRICTER gate than zero-CI because the fee and haircut are deterministic costs, not noise; the strategy must beat them in expectation, not merely tie.

c) **Open question for Phase 2:** the modal execution price in the qualified universe is unknown until Phase 2 runs the pilot. The lock must state: "Pilot computes median(execution_price) on the first 100 qualified events; the gate threshold is then computed deterministically from this median using the formula above. No tuning of the threshold after seeing the full P&L distribution." This is a one-step pilot-to-gate calibration, not a post-hoc adjustment.

---

## F9: Side-selection bias

**Prior round citations:** Round 15b/c v10a category analysis: naive per-side cells (e.g., "buy NO at 0.30 wins 56%") are a base-rate artifact because a maker bot cannot choose its fill side; combined-side analysis is the correct level for forward inference. Independent agent at `research/v10a/05-becker-edge-discovery.md` surfaced this as a textbook trap.

**v11 nuance:** v11 is a TAKER strategy, not a maker strategy. The taker DOES choose its fill side (which is the entire point of the signal: take the side sportsbook moved toward). So the maker side-selection bias does NOT mechanically apply. However, the analogous bias for takers is: the taker can only fill at the orderbook ask on the side it wants to take; if the ASK is wider than the BID on the chosen side at the moment of the signal, the strategy mechanically picks the more expensive side. The selection is bookmaker-direction-conditional but ALSO orderbook-depth-conditional.

**v11 Phase 1.5 must include:**

a) A symmetry check: compute the per-trade net P&L separately for (BUY YES on the sportsbook-favored side) and (BUY NO on the sportsbook-faded side). Under the v11 hypothesis, both should be positive with similar magnitudes (the signal carries information about which side will win, regardless of YES vs NO framing). If only YES trades are positive and NO trades are flat or negative, the strategy has a side-selection bias and the apparent edge is partly a base-rate artifact of which markets happen to be YES-favored vs NO-favored in the universe.

b) **Pre-registered numerical gate (F9):** both YES-side and NO-side per-trade net P&L means must be positive, and the difference (YES_mean - NO_mean) must NOT exceed 2x the smaller of the two with the 95% CI on the difference excluding the larger. If one side is positive and the other is at zero or negative within CI, the gate FAILS even if the pooled mean clears F8.

c) **Open question for Phase 2:** for game-resolution moneyline markets, the YES side typically maps to "home team wins" or "favored team wins" depending on Kalshi's listing convention. The Becker dataset's `ticker` field plus the trade `yes_price` plus the resolution outcome lets us reconstruct which side was the sportsbook-favored side per trade. The lock must specify how this mapping is computed and that it is computed deterministically from market metadata BEFORE seeing the P&L outcome.

---

## F10: LOO and LOCO fragility

**Prior round citations:** v4-A signal +1.70pp mean PARTIAL, but LOO collapse to -0.65pp on outlier removal; Bonferroni-corrected TA4 CI includes zero. v5-A same LOO collapse applies. Round 15 V10-A LOCO at lag-5 Granger structurally infeasible at n=9 train events per series (different mechanism, same family).

**v11 Phase 1.5 must include:**

a) Two layered LOCO requirements: LOCO-by-sport (leave each sport out in turn) AND LOCO-by-bookmaker (leave each major bookmaker out in turn). The strategy must survive both. Additionally, single-observation LOO (leave-one-event-out) is run as a diagnostic; if any single event's removal moves the pooled mean by more than 0.5x the standard error of the pooled mean, the strategy's apparent edge is concentrated in one outlier and the verdict drops to PARTIAL pending further investigation.

b) **Pre-registered numerical gate (F10):** LOCO-by-sport drop must remain net P&L > 0 with the 95% bootstrap CI excluding zero in each one-sport-removed run. Same for LOCO-by-bookmaker. If 3 sports are in the qualified universe, that is 3 LOCO-by-sport runs; if 3 major bookmakers, 3 LOCO-by-bookmaker runs. The strategy must clear ALL of these, not a majority. Block bootstrap (not row-shuffle bootstrap) must be used because game-resolution events within a day or weekend can be cross-correlated (same sportsbook info shock moving multiple games); block size = 1 calendar day.

c) **Open question for Phase 2:** if the qualified universe ends up with only 2 sports or only 2 major bookmakers (one of them dominating), LOCO loses its power: each removal halves the n, which may drop below the F2 MDE_80 floor. The lock must include a contingency: "If LOCO-by-sport requires N_qualified / K_sports >= N_MIN_QUALIFIED, recompute N_MIN_QUALIFIED for the one-sport-removed sample. If the floor cannot be met, the gate is unregisterable at K_sports = number_of_available_sports and the strategy must expand the universe."

---

## F11: Dataset schema phantom

**Prior round citations:** V10-A kill (Round 15): Becker has no orderbook ask at trade time (schema in `prediction-market-analysis/docs/SCHEMAS.md` lines 32 to 47: `trade_id, ticker, count, yes_price, no_price, taker_side, created_time, _fetched_at`); any execution proxy reproduces v7-B confirmed phantom (8 of 8 live bets lost). New failure mode logged in CLAUDE.md.

**v11 nuance (load-bearing per brief):** v11 inherits the Becker no-orderbook-ask constraint. The strategy backtest must use a deterministic execution model, and the choice must be pre-registered, NOT post-hoc tuned.

**v11 Phase 1.5 must include:**

a) **Deterministic execution model, pre-registered (recommended):** "buy at trade-print mid + DETERMINISTIC_HAIRCUT" where DETERMINISTIC_HAIRCUT is computed once from the Becker MARKETS snapshot table on a pre-pilot stratified subset (100 events, NOT in the validation split) and held fixed for the entire backtest. The haircut is the 75th-percentile of (orderbook_ask minus most_recent_trade_print) over MARKETS snapshots that have both fields populated. Specifically NOT "buy at next-trade-after-signal price," because next-trade can be a same-direction trade by another participant reacting to the same signal, producing optimistic look-ahead bias.

**v11-A3 recommendation: trade-print mid plus 75th-percentile haircut from MARKETS snapshot**, computed once on a development split disjoint from the validation split, frozen before the validation backtest runs.

b) **Pre-registered numerical gate (F11):** the chosen DETERMINISTIC_HAIRCUT value, the development-split event-IDs used to compute it, and the SQL or Python expression that computes it must all be written into the locked methodology doc BEFORE the validation backtest fires. The validation backtest's pre-trade P&L formula is then: `net_pnl_per_contract = realized_outcome (1.0 or 0.0) - (trade_print_mid_at_signal + DETERMINISTIC_HAIRCUT) - fee_function(trade_print_mid_at_signal + DETERMINISTIC_HAIRCUT)`. Fee_function uses Kalshi's published formula (7% of |winning_price minus 0.5|, capped at 7c).

c) **Open question for Phase 2 (MUST surface):** even with a pre-registered deterministic haircut, the strategy's apparent edge is computed against a baseline that no live taker would actually pay (the haircut is a sample statistic, not a real-time quote). The final pass condition for v11 must include a forward live spot-check IF the backtest clears all gates (F1 to F10 plus the F11 gate above): post no orders, but record the live orderbook ask for any qualifying signal-fire during a 30-day forward window, and verify that the median (live_ask minus (trade_print_mid + DETERMINISTIC_HAIRCUT)) is <= 1c. If the live live-vs-backtest gap exceeds 1c, the strategy stays in PARTIAL status and capital is NOT deployed. This is the same forward-check pattern that v8-A used to refute v7-B. Without it, F11 remains structurally unrefuted.

---

## v11-specific composite gate

The strategy is declared SHIP only if ALL of the following pass simultaneously on the validation split. Any single failure drops the verdict to PARTIAL or NULL per the per-mode rules above.

| Gate | F-mode | Pre-registered formula |
|---|---|---|
| G_F1_coverage | F1 | qualified-event timestamp-join coverage rate >= 60% AND n_qualified >= 200 |
| G_F2_power | F2 | n_qualified >= n_required_for_80pct_power(target_MDE = 2c per contract net) computed deterministically from pilot sigma |
| G_F3_per_sport | F3 | for each sport contributing >= 20% of qualified events, per-sport mean net P&L > 0 with per-sport bootstrap 95% CI lower bound > per-sport per-trade fee cost; at least 3 sports clear |
| G_F4_haircut | F4 | F4 Option B execution-haircut applied; mean per-trade net P&L >= 1c per contract with bootstrap 95% CI lower bound > 0 |
| G_F5_comparator | F5 | v11 net P&L beats both random-side comparator and anti-signal comparator with non-overlapping bootstrap 95% CIs |
| G_F6_correction | F6 | EITHER single pre-registered (X, Y, sport, bookmaker) cell clears uncorrected alpha 0.05, OR multi-cell evaluation passes Bonferroni or BH at alpha 0.05 |
| G_F7_no_settlement | F7 | zero trades with `created_time >= market_close_time - 60` in either signal or execution window (assertion at loader) |
| G_F8_regime_threshold | F8 | mean per-trade net P&L > (Kalshi_fee + DETERMINISTIC_HAIRCUT + 1c) with bootstrap 95% CI lower bound > this same threshold (NOT > 0) |
| G_F9_side_symmetry | F9 | both YES-side and NO-side per-trade net P&L means positive; |YES_mean - NO_mean| <= 2x min(YES_mean, NO_mean) |
| G_F10_LOCO | F10 | LOCO-by-sport AND LOCO-by-bookmaker each retain net P&L > 0 with block-bootstrap 95% CI excluding zero in every single one-out run |
| G_F11_execution | F11 | DETERMINISTIC_HAIRCUT pre-computed on development split and frozen; PLUS 30-day forward live spot-check confirms median(live_ask - (trade_print_mid + DETERMINISTIC_HAIRCUT)) <= 1c |

**Verdict mapping:**

- All 11 gates pass: SHIP-shadow-mode for 60 to 120 calendar days at $0.50 per trade, then re-evaluate. Live capital not deployed before the forward spot-check (G_F11) completes.
- 9 or 10 of 11 pass: PARTIAL. Document which gates failed; do not deploy capital; consider redesign at the failed-gate layer.
- 8 or fewer of 11 pass: NULL. Close v11 Track 1 at $0 capital, log learnings to CLAUDE.md, update F-mode taxonomy if a new mode is identified.

---

## Composite gate one-paragraph summary

The v11 Track 1 hypothesis SHIPs only when all 11 pre-registered gates pass simultaneously on the validation split: data coverage and sample size suffice for 80% power at a 2-cent net-of-fee MDE, the edge survives per-sport and per-bookmaker LOCO with block-bootstrap CIs excluding zero, both YES-side and NO-side trades carry positive mean P&L with symmetric magnitudes, the strategy beats random-side and anti-signal comparators on non-overlapping CIs, the F4 execution haircut is computed from Becker MARKETS snapshots and pre-frozen before backtest, multi-cell threshold tuning is Bonferroni-corrected, no post-settlement trades leak into signal or execution windows, the strategy beats the (fee plus haircut plus 1c safety buffer) deterministic cost floor not merely zero, and a 30-day forward live spot-check confirms the Becker-derived execution proxy is within 1c of the live orderbook ask. Any single gate failure drops the verdict from SHIP to PARTIAL; eight or more failures NULL the strategy. The composite gate is engineered specifically to prevent recurrence of v3 F1, v9 F8, v7-B and v10-A F11, v5-A F10, and the Round 15b/c F9 side-selection trap.

---

*Anti-em-dash and anti-en-dash verification: this document was written without U+2014 or U+2013 throughout. Verified by ASCII-only character set in source.*
