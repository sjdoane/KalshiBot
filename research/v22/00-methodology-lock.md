# v22 Methodology Lock (Pre-Data), v2

**Date:** 2026-06-11 (v2, post methodology-critic revision; see
`02-methodology-critique.md`, verdict LOCK-WITH-EDITS, all must-do edits
below)
**Status:** LOCKED after the full selection chain (2 scouts -> 3-member
council -> data-grounded verifier -> methodology critic; see
`01-selection-process.md`). No outcome data has been read for any v22 axis;
the data scout and verifier ran STRUCTURAL queries only (timing
distributions, counts) plus v1's own perf log.

Operator authorization (2026-06-11): research and test another potential
bot, creative and cross-disciplinary, while v21 Candidate C collects.

## 0. Calibration and inheritance

Everything inherited from v21 lock v3.2 section 0 applies: F11 (no
historical orderbook; print screens are necessary-not-sufficient upper
bounds via incumbent-maker selection), F4, F9, event-cluster inference
mandatory, post-Oct-2024 only, no v1 changes, kill-early, no third bite.
Additional inherited lesson (v16 lock, re-surfaced by the verifier): a
passive-MAKER hypothesis cannot be validated record-only; fill-or-no-fill
is unobservable without a real resting order. The forward test for v22 is
therefore live 1-lot probes, not a phantom-fill shadow.

## 1. The slate (pre-registered; screens are RANKERS, not tests)

### P1 (lead; the ONLY promotable candidate): new-listing cold-start maker premium

Frame: Glosten-Milgrom learning phase. Hypothesis: in the first hours after
listing, before MM competition arrives, maker fills earn excess return above
the same market's mature-life maker fills.

**Per-trade excess:** v21 lock Section 2.2's combined-side maker-excess
construction is incorporated by reference (maker side = non-taker side;
settlement from `result`, finalized yes/no only, void/unsettled/active
excluded never imputed; per-trade net excess; trade-count weighting;
contract-weighted diagnostic). Fee: see the fee table rule below.

**Population (locked; critic M-5):** market `open_time` >= 2024-11-01 (both
fill classes post-flip); market lifetime (close_time - open_time) >= 10
days; market finalized with result in (yes,no); markets with close_time >=
2025-11-01 excluded (censoring, by close_time); close_time > 2028 excluded;
after-close prints dropped from BOTH fill classes (share reported); print
yes_price in [0.03, 0.97] only; KXMVE excluded from inference (descriptive
table only; parlay legs share games ACROSS events so event_ticker
clustering is invalid there); v21-graveyard cells (Media/Entertainment/
Other mid-band series) EXCLUDED from the pooled gate estimand, reported in
diagnostics only (critic M-1).

**Cell construction (locked verbatim; critic C-1, H-2):**
- Cells = frozen category x TTE band x price band. TTE at trade time =
  close_time - trade created_time, bands {[3d,10d), [10d,21d), [21d,42d),
  [42d,90d), [90d,inf)}. Price band on the print's yes_price, bands
  {[0.03,0.20), [0.20,0.40), [0.40,0.60), [0.60,0.80), [0.80,0.97]}.
- COLD fill: trade age since open_time < 6h. AGED fill: age > 3d AND TTE
  > 3d.
- Comparator A_c = mean per-trade excess over AGED fills in cell c, VALID
  only if c has >= 50 aged trades from >= 10 distinct events AFTER the
  leave-one-event-out exclusion (for cold trade t, aged fills sharing t's
  event_ticker are excluded from its comparator). Cold fills in invalid
  cells are EXCLUDED from the estimand; excluded trade count, event count,
  and category breakdown are mandatorily reported.
- Estimand = pooled per-trade mean of v_t = e_t - A_c(t) over all included
  cold trades.

**CI (locked; critic H-1):** a JOINT two-sample event-cluster bootstrap (a
new statistic function, code-reviewed before its output is read): resample
event_ticker clusters with replacement from the UNION of cold and aged
populations; within each resample recompute every A_c (validity re-checked
inside the resample; invalid cells drop from that resample) and the pooled
cold mean of v_t; CI = 2.5/97.5 percentiles of 5,000 resamples,
rng_seed=42. `cluster_bootstrap_mean_ci` is NOT sufficient here (it would
treat A_c as known constants).

**Fee table (locked; critic H-4):** a dated (series-prefix x date-range)
maker-fee table built from archived Kalshi fee-schedule documents,
committed with hash BEFORE the screen script exists. Where the archive is
silent for a series-period: dual run with fee = 0 and fee =
ceil(1.75*P*(1-P)) cents; K-P1 may PASS only if it passes under BOTH.
Forward economics use the current (Feb-2026) schedule in integer cents.

**Category map (locked; critic H-5):** the frozen rebrand-unified
prefix-to-category map = the existing v10a mapper's prefix assignments,
unified across the KX-rebrand break by ticker-structure rules ONLY (no
outcome columns), built by a standalone script committed with hash before
the screen script exists (v21 freeze discipline).

- **Pre-count gate (critic H-3, runs FIRST, structural only, no
  outcomes):** count events with >= 1 print at age < 6h on qualifying
  markets. If < 300, the round dies before the screen runs.
- **K-P1 (kill):** pooled contrast <= 0, OR the joint-bootstrap 95% CI
  includes zero, OR fewer than 300 events contribute INCLUDED cold fills
  (post-matching). Any NULL must report the realized MDE next to the
  verdict. Honesty line (critic L-3): the contrast of two differently
  selected F11 upper bounds is not itself an upper bound on the cold-start
  premium; only live probes measure the deployable quantity.
- **Whelan guard (critic M-6):** if the 2025-only contrast point estimate
  is <= 0, that goes verbatim into the probe go/no-go council packet, and
  the probe's required-N formula uses the 2025-only effect, never the
  pooled one.
- Diagnostics (report-only): per-category and per-band contrasts;
  contract-weighted version; 2024Q4-vs-2025 split; WITHIN-MARKET paired
  cold-aged difference, event-clustered (critic H-2): if pooled K-P1
  passes but the paired diagnostic is negative, P1 does NOT auto-claim the
  forward slot; the discrepancy goes to a council review. Cold-vs-aged
  composition tables (price, lifetime, calendar month, prints/market-day)
  per cell, mandatory. KXMVE descriptive table with game-level grouping
  caveat.

### P2 (overlay; NOT promotable; no gate module this round): flow toxicity

Two pre-registered pieces, both report-only this round:
- **P2a Becker screen (definitions per critic M-2):** maker net excess by
  trailing ORIENTED taker-imbalance half. Imbalance for print t = signed
  taker contract sum over the prior 60 minutes in the same market, strictly
  before t, sign POSITIVE when the trailing flow matches t's taker side
  (flow the maker leans against; a plain net-YES/NO split would be the dead
  directional-CVD use). Computed only where >= 5 prior prints exist WITHIN
  the 60-minute window. Median split computed WITHIN category on the
  activity-matched population; ties to the <= median half; half sizes
  reported. Event-clustered. Purpose: does oriented imbalance predict worse
  maker outcomes (loss-conditioning)?
- **P2b v1-own-fills diagnostic (the clean one, accumulating):** for each v1
  settled fill, compute the same trailing-imbalance signal causally from the
  public tape; compare net P&L across the median split. READ ONLY when v1
  has >= 200 settled fills AND >= 60 event-day clusters (currently 83
  fills: noise; not read this round). Escapes incumbent selection because
  the fills are our own.
- No kill (overlay informs future hosts); no gate module is built until a
  host strategy exists.

### P3 (screen only; NON-PROMOTABLE, funding veto pre-registered): affirmation tax

Frame: prospect-theory probability weighting at the longshot tail.
**Screen estimand (locked, verifier's fix + critic M-3):** one leg per
event = the leg with max FILL VOLUME (sum of `count`, contracts) among legs
printing 3-8c YES; ties broken by more qualifying prints, then
lexicographically smallest ticker. Indicator = that leg settles YES.
Benchmark p_i = that leg's own fill-weighted implied probability; p-bar =
the UNWEIGHTED mean over events of p_i. Test = exact ONE-SIDED binomial
(lower tail on the YES count) as the conservative bound on the
Poisson-binomial (Hoeffding; verified by the critic), PLUS the standard
event-cluster bootstrap on per-event excess as robustness, PLUS a
series-prefix-clustered CI as mandatory report-only sensitivity (same-
underlying dependence: a week of BTC ladder events rides one BTC path);
if it includes zero, that is named verbatim in the K-P3 write-up.
Population: market open_time >= 2024-11-01, inheriting the after-close
print drop, the censoring exclusion, and the close_time > 2028 exclusion
(the lifetime >= 10d floor is explicitly NOT inherited); EXCLUDING the dead
Media/Entertainment/Other cells; mandatory 2024Q4-vs-2025 decay split
(Whelan); v18 heavy-underdog-weak prior registered.
- **K-P3 (kill):** NO-side excess <= +2pp net of era-correct fee, or
  conservative-bound p > 0.05, or the 2025 split shows the edge below +1pp.
- **Funding veto (locked):** P3 cannot receive capital or probes this round
  regardless of screen outcome (capital efficiency ~95c locked per <= 6c
  gross; correlated same-game settlements are the realistic ruin path).

### Excluded (recorded so future rounds do not re-litigate blind)

- Hazard-clock decay: UNIDENTIFIED on prints (stale-print confound is the
  observable); excluded for collector cost on forward data. Not graveyard;
  revisit only with a purpose-built high-frequency collector.
- Cross-horizon coherence map: killed (maintenance rot, unbounded researcher
  degrees of freedom, adjacent to the 0-in-2,791 dutch-book null).
- Ladder-shape RV: deferred zero-cost read of the accumulating C0 JSONL,
  read date = G-C0 verdict day + 7 (see branch table); no build before then.

## 2. Selection and forward-test structure

- Screens are non-inferential rankers. The forward slot belongs to P1 IFF P1
  survives K-P1. P2/P3 inform v23 only. (The council's "largest effect
  wins" rule was vacuous: P1 is the only fundable candidate; verifier
  finding 12.)
- **Forward test = live 1-lot maker probes** (v16 lesson; record-only cannot
  measure maker fills): separate bot identity, own intent-id prefix (NOT
  v1's), own state file, own scheduled task, triple kill (20pct drawdown of
  its slice, 5-consecutive-loss, fill-starvation stand-down).
- **Probe population and quoting rule (locked outline; critic H-6):** the
  probe universe = the SAME population as the screen estimand (all matched
  categories pooled, graveyard cells excluded); NO category or band
  sub-selection conditioned on screen diagnostics, under any outcome.
  Quoting: one 1-lot bid per qualifying newly-listed market, JOINING (never
  improving) the maker-side best bid within the screened price bands,
  placed within the cold window (< 6h from open), canceled at age 6h if
  unfilled, held to settlement if filled. Refinements at probe build (under
  its own plan critic) only in directions that do not condition on screen
  diagnostics.
- **Power and feasibility (locked formulas; critic C-2):** at the K-P1
  verdict the screen script writes into the verdict doc: required N =
  ceil((1.96 + 0.8416)^2 * s^2 / (0.5 * effect_2025)^2) where s^2 = the
  screen's event-cluster-level variance and effect_2025 = the 2025-only
  contrast (critic M-6). FEASIBILITY KILL before any launch: projected
  settled probe fills (qualifying listing flow from a structural query x a
  fill-rate band of 10-30pct, stated now) must reach required N within a
  maximum probe duration of 16 IN-SEASON weeks; if not, P1 is killed at the
  power gate with no capital deployed.
- **Launch trigger and starvation (locked numbers):** launch = first day
  after the C0 branch decision on which qualifying listing flow >= 25
  qualifying listings/week (the season turn-on signature). At launch + 8
  weeks: < 30 settled probe fills = stand-down + council review; < 10 =
  kill.
- **Forward read (locked; critic C-2.4, L-2):** `cluster_bootstrap_mean_ci`
  with cluster = event_ticker (market-day reported as sensitivity, v21
  precedent), n_resamples=5000, rng_seed=42, TWO-SIDED 95pct CI (one-sided
  size 0.025); read only at >= required N settled fills AND Kish effective
  sample size of clusters >= 30. Economic floor: CI lower bound > 0 AND
  point >= +1.0pp net of CURRENT-schedule fees in integer cents.
- **Probe capital (critic M-7):** the G-C0-FAIL-branch ceiling is the P1
  PROBE ceiling (not "Stage-C"): min($40, $100 - v1 balance at promotion);
  minimum viable probe bankroll $15 (below it, launch blocks pending
  operator action). Bankroll-capped skipped quotes are logged and EXCLUDED
  from the fill-rate denominator; skipped share > 20pct flags the sample as
  selection-biased in the verdict.
- **Shelf life (critic M-8):** if probes have not launched by 2026-10-01,
  the K-P1 screen verdict EXPIRES and the screen must be re-run on extended
  data before any probe.
- **External VOID kill (critic L-1):** VOID (not null) fires if CA accounts
  lose the ability to place new orders on ANY P1-qualifying series during
  the probe phase; restrictions touching only non-qualifying series do not
  fire it.

## 3. Capital and C0 branch table (Jun-23)

Shared $100 operator ceiling; v1 currently holds ~$80 at fraction 1.0.
ANY new live deployment (ladder executor or P1 probes) requires the
operator to restore a v1 bankroll fraction split and restart v1: explicit
operator action, never done by a session unprompted.

| Branch | Candidate C | v22 |
|---|---|---|
| G-C0 PASS (>= 3 locks) | C takes the build slot + first capital claim (execution bot design, own plan critic) | Screens complete; P1 probe deferred until C's build decision lands; P1 survives as the next-in-line candidate |
| G-C0 FAIL | C NULL, v21 closes; KalshiC0LadderScan task kept ALIVE 7 more days solely to feed the ladder-shape deferred read, then unregistered | P1 probe phase may start (operator approval + fraction split first); Stage-C ceiling = min($40, $100 minus v1 balance at promotion) |

## 4. What we will NOT do (locked)

- NOT read any outcome data before the pre-count gate, fee table, and
  category map are committed.
- NOT change buckets, windows, fee math, or kill thresholds after results.
- NOT alter TTE/price band edges, cell-validity minimums (>= 50 aged trades
  / >= 10 events), or the fee table after the screen runs (critic L-4).
- NOT select probe categories or bands using screen diagnostics (critic
  L-4/H-6).
- NOT promote P2 or P3 this round under any screen outcome.
- NOT run KXMVE inference on event_ticker clusters.
- NOT start live probes without operator approval, a v1 fraction split, the
  C0 branch decision, the feasibility-kill pass, and the launch trigger.
- NOT touch v1 (the P2b diagnostic READS its perf log only).

## 5. Review plan

Selection chain DONE (scouts -> council x3 -> verifier, all on record in
`01-selection-process.md`). NEXT: one methodology critic on THIS lock before
the screen script runs; code review of the screen script before its output
is read; if P1 survives: plan critic + code review + post-impl review on the
probe bot before any live order; council + verifier at the go/no-go.

## 6. Change log

- 2026-06-11 v1: initial lock, incorporating all 12 verifier amendments
  (TTE-matched comparator, lifetime >= 10d, ~130 events/month ground truth,
  KXMVE demoted to descriptive, era-correct vs current fee split, capital
  branch table, live-probe forward test per the v16 lesson, season-aware
  start, P2 reframed as accumulating diagnostic, P3 one-leg Poisson-binomial
  + funding veto, VOID kill, C0 branch table).
- 2026-06-11 v2: methodology-critic revision (`02-methodology-critique.md`,
  LOCK-WITH-EDITS). C-1: exact cell construction locked (frozen TTE + price
  bands, >= 50 aged trades / >= 10 events validity, unmatched-cold
  exclusion + reporting, leave-one-event-out comparator, pooled per-trade
  estimand). H-1: joint two-sample event-cluster bootstrap replacing the
  constant-comparator CI. C-2: forward probe re-derived (locked required-N
  formula on 2025-only effect, pre-launch feasibility kill, 16 in-season
  week max, listing-flow launch trigger, numeric starvation thresholds
  30/10, cluster unit + Kish ESS + two-sided read locked). H-3: structural
  pre-count gate added before the screen. H-4: dated per-series fee table
  or dual-fee conservative gate. H-5: category-map construction rule. H-6:
  probe population + quoting rule outline locked. H-2/M-1: price band in
  the matching key, within-market paired diagnostic with council
  consequence, graveyard cells excluded from the pooled estimand. M-2: P2a
  oriented imbalance + within-category median. M-3: P3 mechanics locked,
  conservativeness verified. M-4/M-5: v21 2.2 incorporated by reference,
  timestamps defined. M-6/M-7/M-8, L-1 through L-4 as written. LOCK
  COMPLETE; next artifacts = pre-count, fee table, category map (committed
  before the screen script exists).
