# v21 Methodology Critique (Methodology Critic Report)

**Reviewer:** independent methodology-critic agent (adversarial review of `research/v21/00-methodology-lock.md` v2, pre-data)
**Date:** 2026-06-09
**Scope:** methodology soundness of the v2 lock, distinct from `01-plan-critique.md`. Settled points (F11 audit, ladder math, operator override on C, prior plan-critic findings) are not re-litigated except where the v2 fix itself is defective.

**Code ground-truth (all five references verified on disk):**
- `src/kalshi_bot/analysis/bootstrap.py::cluster_bootstrap_mean_ci(values, cluster_ids, *, n_resamples=5000, ci=0.95, rng_seed=None) -> (mean, lower, upper, n_clusters)` exists and does what the lock claims (resample whole clusters, pool, mean). Note the parameter is `rng_seed`, not `seed`, trivial but lock the call signature.
- `src/kalshi_bot/analysis/dutchbook.py`: `parse_market_quote`, `analyze_group` (mutually-exclusive groups only, as the lock states), `annualized_return` all exist as described.
- `scripts/v10a/becker_combined_side_loco.py`: confirmed trade-level normal-approx CI at lines 88-91, exactly as the plan critic said. **But see M-3: this script cannot be "reused" for the v21 screen at all; it consumes a prefix-level aggregate with no event_ticker and no per-trade values.**
- `src/kalshi_bot/analysis/lead_lag_shadow.py` + `scripts/v16/shadow_logger.py`: record-only, single-instance lock, parquet recovery sidecars, never places orders, as claimed. The harness is heavily MLB/odds-API-specific; "adapt" is a real build, not a config change.

---

## CRITICAL

### C-1. G-A2a (15% fill-rate pass bar) contradicts S-A1d (3% planning assumption); the 15% is a copied gate, an F9 violation inside the lock itself

**Reference:** Sections 2.4 (S-A1d), 2.6 (G-A2a), gate table.

S-A1d funds a cell if projected fills >= 30 over 45 days at a "CONSERVATIVE 3%" fill rate. That requires ~1,000 posting opportunities. A cell that barely passes S-A1d and then realizes exactly the planning assumption (3%) produces ~30 fills: it passes G-A2b but is **guaranteed to fail G-A2a (3% << 15%)**. Under the design's own stated conservative expectation, every just-funded cell is pre-destined to die at G-A2a regardless of edge. The two numbers cannot both be honest: either 3% is sandbagging (then S-A1d is not conservative, it is theater) or 15% is unreachable (then Phase 2 is an expensive scripted kill and the lock is not testing the edge hypothesis at all).

Provenance makes this worse: 15% is lifted verbatim from the Round 15b/c shadow-mode recommendation ("G1 fill rate >= 15%", CLAUDE.md), which was drafted for a six-candidate basket including liquid sports/crypto series. v1's own live fill rate in liquid sports was ~11% pre-fix. Thin non-sports books at back-of-queue best-bid join will be lower, not higher. Copying a threshold derived for a different liquidity regime is exactly failure mode F9, which Section 0 claims this design avoids.

**Fix (must-do, pick one and justify it in the lock):**
(a) Replace G-A2a with an economic throughput gate that does not care about rate per se: e.g. `modeled fills/day x point edge per fill >= $X/day at planned size`, with $X derived from the $5 slice and fixed costs; or
(b) set G-A2a to a value consistent with the planning assumption (e.g. >= 3%, with G-A2b/G-A2c/G-A2d carrying the edge burden); or
(c) keep 15% but derive it in writing from v1's realized maker fill data and accept in the lock that Phase 2 is then primarily a fill-rate experiment with edge measurement as a bonus.
Whichever is chosen, S-A1d's assumption and G-A2a's bar must be the same number or explicitly reconciled.

### C-2. The Phase 2 fill model's denominator and bid lifecycle are undefined, making G-A2a/G-A2b unfalsifiable as written, and the posting price is not constrained to the screened band

**Reference:** Section 2.6 fill model + gates.

Three holes:

1. **Bid lifecycle undefined.** "On a fixed cadence, snapshots ... and records a HYPOTHETICAL resting maker bid" does not say: one bid per market at a time, or one new bid per snapshot? When does a bid retire (re-peg when best bid moves? expire at close only?)? "Fill rate = fills / posted hypothetical bids" is then a free parameter: post a new bid every 5 minutes and the denominator explodes (fill rate -> 0, G-A2a auto-fails); post one bid per market-day and it shrinks (G-A2a easier). The single most important gate in the document ("the fill-rate gate is the single most important field") is currently a function of an unstated logging policy. That is the definition of a gate that can be argued either way post-hoc.
2. **Band mismatch with the screened estimand.** The Becker screen measures maker fills whose execution price printed in [0.40, 0.60) (or [0.60, 0.80)). The shadow "rests at the current best bid", wherever that is. In thin non-sports books the best bid can sit at 0.15 with a 40-cent spread; a fill there is not a draw from the screened population. Phase 2 as written can validate or kill a different strategy than the one Phase 1 screened.
3. **Partial-fill arithmetic.** "Cumulative taker volume at our price since we posted exceeds the depth that was ahead" must be `>= depth_ahead + our_size` (for 1 contract, depth_ahead + 1), else the crossing trade that exactly exhausts the queue ahead is credited to us.

**Fix (must-do):** pre-register the bid lifecycle precisely: ONE hypothetical bid per market at a time; posted only when the best bid lies inside the cell's band; re-pegged (with queue position reset and the event logged) when best bid moves; retired at market close (dead-book row) or on fill; fill requires cumulative crossing volume >= depth_ahead + size. Define fill rate = filled bid-episodes / total bid-episodes, and state the cadence. Also log the spread at post time so fills at pathological spreads are auditable.

### C-3. Candidate C's `yes_sub_title` numeric parse can manufacture FALSE locks: range brackets misread as nested thresholds, plus non-synchronous quote pairs

**Reference:** Sections 3.3 (C0), 3.4 (C1), G-C0.

The lock's own Section 3.1 lists "range ladders" among cumulative ladder examples, and that is the trap. Range-bracket families ("3,500 to 3,999", "4,000 to 4,499") are **mutually exclusive, not nested**. Their YES prices are bell-shaped across strikes, so adjacent pairs violate "monotone non-increasing" constantly and legitimately. A numeric parse of `yes_sub_title` that extracts 3500 < 4000 and treats the family as a cumulative ladder will flag p_i < p_{i+1} "violations" everywhere, and the buy-YES_i/buy-NO_{i+1} basket is then NOT a lock (if X lands in bracket i+1, YES_i pays 0 and NO_{i+1} pays 0: total loss). Because range families are common (KXBTC range markets, etc.), this failure mode does not just risk a false G-C0 pass; it produces exactly the "free money that look like locks" phantom this project exists to avoid, and "conservative: skip anything ambiguous" is not a procedure, since "3,500 to 3,999" parses cleanly and looks unambiguous. Also unhandled: "less than" ladders (monotonicity reversed; misread direction = violations everywhere), date ladders ("by June" vs "by July", nested on a different axis), and subtitles containing two numbers (which one wins?).

Second, independent phantom source: a single paginated `/markets` pull spreads leg quotes over seconds to minutes. A "violation" computed across two non-simultaneous quotes is the stale-pair cousin of F4. Third: `parse_market_quote` returns size 0.0 when `*_ask_size_fp` is absent; if the live `/markets` payload lacks those fields, "depth >= 1" silently auto-fails (or, if a different field is improvised post-hoc, the gate moved).

**Fix (must-do):**
1. Identify ladders from STRUCTURED API fields, not subtitle text: require `strike_type` in an explicit whitelist (`greater`/`greater_or_equal`; handle `less` with reversed ordering or exclude it for C0) and order by `floor_strike`. Hard-exclude `between`/custom/functional strike types. Subtitle parsing only as a cross-check, never the classifier.
2. Before counting any lock toward G-C0: re-read BOTH legs back-to-back (orderbook endpoint, which also gives real depth) and require the net-of-fee violation to persist on the confirm read. Count it once per (ladder, adjacent pair) per day, and define "distinct" that way in the gate.
3. Verify the size fields exist in the live payload before day 1 of the scan; if absent, the confirm-read orderbook depth is the bindable-depth source, pre-registered.

---

## HIGH

### H-1. The purge rule truncates the horizon distribution asymmetrically between train and the recency slice, confounding the compression guard S-A1b

**Reference:** Sections 2.3, 2.4 (S-A1b).

Requiring `close_time` inside the same window means train (10 months wide) admits market lifetimes-to-close up to ~10 months, while the recency slice (2.8 months wide, ending at the dataset terminus) admits only markets resolving within <= ~2.8 months, further filtered by "finalized by the 2025-11-23/24 fetch" (the 328,865 `active` rows have no usable result). So S-A1b compares long+short-horizon train trades against a short-horizon, fast-settling recency subset. Maker excess plausibly varies with horizon (time value, adverse-selection intensity, who quotes long-dated books), so the >= 50% consistency check can fail or pass for composition reasons, not compression. The lock's framing of S-A1b as a pure "compression guard" is therefore wrong as specified. The same truncation also means train systematically excludes the long-dated markets the live bot WOULD quote, the inverse of v1's lifetime-window lesson.

**Fix:** impose a uniform horizon cap in BOTH windows: keep only trades with `(close_time - created_time) <= 60 days` (matching what Phase 2 can actually observe, see H-2) AND `close_time` inside the window. Then train and recency compare like-for-like horizons, and the screened population matches the forward-testable population. Report the dropped long-horizon share per cell so the estimand narrowing is explicit.

### H-2. Phase 2 has settlement-window selection: P&L gates are computed on the fast-resolving subset while the fill-rate gate is computed on everything

**Reference:** Section 2.6, gates G-A2a vs G-A2c/d.

Over a 30-60 day shadow, a fill in a market closing 90 days out never settles inside the gate window. As written, those fills inflate the G-A2a numerator and the G-A2b count but cannot contribute to G-A2c/G-A2d, so the edge gates are evaluated on a fast-settling subsample that need not share the edge of the full fill population (quick-resolution non-sports markets are a different microstructure than long-dated ones). It also creates an ambiguity an adversary can exploit either way at evaluation time: do unsettled fills count toward G-A2b's >= 30?

**Fix:** pre-register that the shadow posts hypothetical bids ONLY on markets with `close_time <= shadow_end - 5 days`. Then every posted bid can both fill and settle inside the window, all four gates share one population, and this dovetails with H-1's 60-day horizon cap so screen and shadow estimands match.

### H-3. S-A1d's opportunity definition references "mid-band quotes", a field that does not exist in Becker: the F11 pattern recurring inside a gate definition

**Reference:** Section 2.4, S-A1d: "distinct market-days with mid-band quotes and >= 1 trade".

Section 1 just spent a page proving Becker has no quotes at any historical time. A pre-registered gate whose measurement procedure requires an unobservable field is precisely F11's checklist failure ("verify every field required ... exists at the timestamp the strategy needs it"), here in the power check rather than the edge gate, but still ambiguous at evaluation time: whoever runs the screen must invent a proxy, post-lock.

**Fix:** define posting opportunities as "distinct (market, day) pairs with >= 1 trade PRINTING inside the cell's band" and state the known bias: this excludes days where a quote sat in-band but nothing traded, so the projected denominator is smaller than the live shadow's denominator and the realized Phase 2 fill rate will mechanically come in below the S-A1d planning rate. (This feeds straight back into C-1: the 15% bar becomes even less coherent once the denominators are honest.)

### H-4. The >= 80%-volume allowlist freeze can collide with S-A1c's >= 30-prefix floor, leaving a gate that is auto-unsatisfiable or negotiable post-hoc

**Reference:** Sections 2.1 (freeze rule) and 2.4 (S-A1c).

Media has 138 prefixes with top-3 concentration ~30% of abs PnL; the top prefixes covering 80% of trade volume may well number fewer than 30. If a frozen allowlist contains, say, 22 prefixes, S-A1c (">= 30 distinct allowlist prefixes contributing in the recency slice") cannot be satisfied by construction, and the evaluator will face an undocumented choice: kill a possibly-fine cell on an artifact, or quietly widen the allowlist (post-hoc tuning). Both outcomes are methodology failures.

**Fix:** freeze the allowlist as `top prefixes covering >= 80% of band volume, OR the top 30 prefixes by band trade count, whichever set is LARGER`, and state it before the freeze runs. S-A1c then stays meaningful for every cell.

---

## MEDIUM

### M-1. The combined-side estimand is an upper bound on what a naive both-sides quoter experiences, beyond the already-acknowledged "necessary not sufficient"

**Reference:** Section 2.2.

Two residual selection effects survive v2's honesty framing: (1) incumbent maker fills are filtered by incumbents' quote placement and cancellation decisions. The Becker maker pool is "fills that some maker, possibly informed, chose to leave resting"; a naive bot joining best bid unconditionally inherits a strictly worse fill mix (it takes the fills smart makers dodged). (2) Trade-count weighting approximates a 1-lot bot; the live bot quotes multiple contracts (v1 now fills ~4 at LOW band), so its P&L is closer to contract-weighted, and large prints skew informed. Neither breaks the design (the forward shadow bears the inferential weight and costs $0), but the screen number should not be allowed to anchor expectations. **Fix:** pre-register a contract-weighted excess as a reported diagnostic next to the trade-weighted gate number, and one sentence in the screen report stating the incumbent-filter upper-bound caveat.

### M-2. event_ticker clustering leaves cross-event dependence in exactly these categories

**Reference:** Section 2.2 CI spec.

Media/Entertainment events correlate ACROSS event_tickers: weekly box-office events on the same film, award-season markets resolving off the same ceremony, franchise/series events sharing one underlying news process. Event-cluster CIs will be anti-conservative to that extent. S-A1c already guarantees >= 30 contributing prefixes, so a series-prefix-clustered bootstrap is feasible (k >= 30). **Fix:** keep S-A1a gated on event_ticker clusters (as locked), and pre-register a series-prefix-clustered CI as a MANDATORY reported sensitivity; if the prefix-clustered CI includes zero, that fact goes verbatim into the go/no-go council packet. Decide NOW that it is report-only, so it cannot be argued either way later.

### M-3. "Aggregation per becker_combined_side_loco.py" is misleading provenance: the screen needs a new trade-level pipeline that does not exist yet

**Reference:** Section 2.2.

The cited script consumes `05-phase3-prefix-agg.parquet` (per-prefix means/SDs); it has no event_ticker, no per-trade observations, and its pooled-variance machinery is unusable for `cluster_bootstrap_mean_ci`, which needs one value per trade plus a cluster id. The v21 screen therefore re-derives per-trade maker excess from raw trades + markets join, with the lock's fee formula, from scratch. That is fine, but the lock should say so, because "per script X" implies a validated path that is not there, and the fee/net definition inside the old aggregate may not match the lock's formula. **Fix:** state that the screen builds per-trade observations directly from the trades/markets parquets (maker side from `taker_side`, settlement from `result`, fee per the locked formula), and that this new script gets the session-rules code review BEFORE its output is read.

### M-4. Four gate-evaluation ambiguities to pin down pre-data

1. **G-A2c "event/day-cluster bootstrap":** pick ONE cluster unit now (recommend market-day for fills, since one event can produce serially correlated fills across days; whichever, write it down).
2. **"Measured over 30-60 calendar days":** a cell could fail at day 35 and pass at day 60. Fix the verdict date: gates evaluated ONCE at day 60; day 30 exists only as the pre-registered hard-stop kill (< 10 fills). No early passes.
3. **G-C0 sampling:** "~3 scans/day (manual or loose scheduled invocations)" lets the operator scan opportunistically after near-misses, biasing toward detection. Fix a schedule (e.g. 09:00/14:00/20:00 PT, 21 scans) and define "distinct" per C-3.
4. **G-C1c is unmeasurable at the harness's default cadence:** a 60-second JOINT persistence median cannot be estimated from 5-minute snapshots (every observation is censored to 0 or >= 300s). Pre-register a burst mode: on lock detection, re-snapshot both legs every 15-20s for 3 minutes.

---

## LOW

- **L-1 (allowlist freeze hygiene):** the "structural-fields-only" freeze reads trade counts out of an outcome-laden parquet. The ranking statistic is genuinely outcome-free and the residual outcome-correlation (via the cell's survival of the 168-cell sweep) is already covered by the non-inferential framing, so the v2 fix is sound; but make it procedural: a small script that loads ONLY (prefix, band, n, contracts) columns, writes `cell3_prefix_allowlist` (and the Media/Entertainment lists) to a committed file, and is run before the screen script exists. Commit hash = freeze proof.
- **L-2 (maker fee schedule):** Kalshi levies maker fees only on designated series; the lock applies `ceil(0.0175*P*(1-P)*100)/100` to all fills. In the screen that is conservative (fine), but verify the live fee schedule for the frozen allowlist series during Phase 1.5 and apply the SAME schedule in Phase 2 P&L and Phase 3 sizing, so the screen, the shadow, and live are net of the same costs.
- **L-3 (annualized_return edge cases):** `annualized_return` returns None for cost <= 0 or days <= 0. Define for G-C1b: None observations are excluded from the median and logged (cannot occur for a real lock with positive cost, but a zero-days-to-close leg can).
- **L-4 (G-C0 honesty note):** 21 snapshots cannot bound the frequency of sub-minute locks; G-C0 actually tests "locks persistent enough to catch at residential scan cadence", which is the right tradable question, but the NULL write-up template should say that, not "ladder violations do not exist."
- **L-5 (nit):** lock says "seed=42"; the function parameter is `rng_seed`. Record the exact call (`n_resamples=5000, ci=0.95, rng_seed=42`) so the screen is bit-reproducible.

---

## Verdict: LOCK-WITH-EDITS

The v2 lock's architecture is sound where it matters most: the F11 audit is correctly load-bearing, Phase 1 is honestly demoted to a non-inferential screen, all inferential weight sits on a $0-risk forward shadow, and every kill path is pre-registered. But three internal incoherences would let a skeptical reviewer reject the study, and one (C-3) can manufacture exactly the phantom "free money" this project has died on twice.

**Must-do edits before any outcome data is pulled:**

1. **C-1:** reconcile S-A1d's 3% with G-A2a's 15% (replace G-A2a with a derived economic gate, or align the numbers); document the derivation so the bar is not a Round 15b/c hand-me-down (F9).
2. **C-2:** fully specify the Phase 2 bid lifecycle (one bid per market, in-band posting constraint, re-peg rule, episode-based fill-rate denominator, depth_ahead + size fill arithmetic).
3. **C-3:** ladder identification via structured `strike_type`/`floor_strike` whitelist, never subtitle parsing; synchronized two-leg confirm read before counting any G-C0 lock; verify depth-field availability pre-scan.
4. **H-1 + H-2:** uniform 60-day horizon cap in both Becker windows AND restrict shadow postings to markets settling inside the gate window, so screen, S-A1b, and Phase 2 all measure one population.
5. **H-3:** redefine S-A1d posting opportunities on observable fields (in-band trade prints), with the stated denominator bias.
6. **H-4:** allowlist freeze = max(80% volume coverage, top 30 prefixes), locked before the freeze runs.
7. **M-4:** pin the four ambiguities (G-A2c cluster unit; day-60 single verdict date; fixed G-C0 scan schedule + distinctness; G-C1c burst cadence).

Recommended but not blocking: M-1 (contract-weighted diagnostic), M-2 (prefix-cluster sensitivity, report-only), M-3 (state the new trade-level pipeline + code review before reading its output), L-1 through L-5.

With these edits incorporated as a v3 change-log entry, the lock is fit to gate the data pull.
