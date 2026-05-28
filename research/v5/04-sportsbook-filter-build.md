# Agent V5-A2: Combined Polymarket + Sportsbook + Cross-Market Filter Build

**Date:** 2026-05-24
**Author:** Agent V5-A2 (v5 Track A Phase 2)
**Status:** Module build complete. Tests pass (28/28). Retrospective backtest limited by free-tier-historical block; documented honestly. No live capital deployed.
**Predecessor reads:** `research/v5/00-master-plan.md` (Track A scope), `research/v5/iterations.md` (Iter 1 synthesis), `research/v5/01-sportsbook-coverage.md` (V5-A1), `research/v4/05-filter-build.md` (V4-E baseline).

---

## TLDR verdict (amended after Phase 3 critic at `07-critic.md`)

**SHIP shadow-mode as a HYPOTHESIS VALIDATION exercise, not as a confirmed-edge deployment.** The combined v5 filter is mechanically clean (28 unit tests pass) and the sportsbook-fade rule fires on live v1 candidates in the right direction. Three load-bearing caveats per the Phase 3 critic:

1. **The 23% fire rate is WITHIN-coverage, not OVER-v1's-FULL-universe.** Of the 13 v1-band candidates V5-A1 cached, 3 have sportsbook-fade activations. But V5-A1's coverage of the full live universe is 40.7% inclusive; the effective A3 fire rate against v1's FULL candidate stream is roughly `0.407 * 0.23 = 9.4%`, not 23%. Frame this honestly.

2. **The Path Y +1.70pp identity to V4-E inherits V4-E's known fragility.** Phase 3 critic Test 1c reproduced V4-E's LOO sensitivity: removing the 4 outlier wins collapses the diff to -0.65pp with CI [-1.12pp, -0.27pp] (cleanly negative). The signal IS real (direction corroborated independently by V3-C and V5-A1) but the magnitude depends on a small set of outcomes.

3. **Bonferroni-corrected TA4 fails by a wider margin.** Phase 3 critic Test 6 counted ~125 statistical trials across v5. At Bonferroni alpha 0.05/125 = 0.0004 the TA4 CI widens to roughly [-1.17pp, +6.80pp], still includes zero.

The retrospective backtest is structurally limited by:

- **The free tier blocks historical odds** (V5-A1 corrected V4-D). Without paid tier, we cannot run a clean signal test against V4-E's resolved n=147 inventory.
- **The v3 inventory has zero overlap with sportsbook MATCH-class series.** V4-E's inventory is dominated by KXNFLWINS / KXMLBPLAYOFFS / KXNBAWINS (season-long futures), while the-odds-api free tier covers game-resolution h2h (MLB/NFL/WC h2h). Sportsbook coverage on the v4 inventory is 0%, so the A3 rule contributes 0 fires on that backtest path.

The combined filter's headline result on the v4 inventory is therefore IDENTICAL to V4-E's: +1.70pp mean P&L improvement, 95% CI [-0.32pp, +4.22pp], 4 of 5 TA pass with TA4 borderline-fail. The sportsbook arm is INDEPENDENT of v4 coverage.

**The right deployment path is shadow-mode logging on v1's live candidate stream for 120-180 days** (matches V4-E's shadow-mode timeline per Phase 3 critic). After accumulating ~150 sportsbook-arm filter activations on resolved markets, run the TA evaluation cleanly. **This deployment is a hypothesis-validation exercise, not a confirmed-edge activation.** The decision rule at the end of the 120-180 day window decides whether to activate.

Same caveat for the small-n MLB resolved sample: see Path X result in Section 2.

**Pre-registered TA criteria status:**

| Criterion | Threshold | Path X (live-cached) | Path Y (v4 inv) | Live universe sportsbook coverage |
|---|---|---|---|---|
| TA1 coverage | >= 30% | 100% (n=2) | 0% sportsbook-only | 23% (3/13 fire) |
| TA2 improvement | >= +1pp | n/a (no fires) | +1.70pp (poly+mono, book=0 fires) | n/a |
| TA3 skip rate | <= 50% | 0% (no fires) | 10.9% | 23% (well under 50%) |
| TA4 CI lower > 0 | > 0 | n/a | -0.32pp FAIL | unknown (need resolved sample) |
| TA5 >= 2 series | >= 2 | 1 series (MLBGAME) | 2 (NFLWINS, MLBPLAYOFFS) | unknown |

The fair summary: **mechanism works, direction matches V5-A1's +1.70c measurement, fire rate is non-trivial (23% on live v1 candidates), resolved-outcome sample size is the blocker.** The recommended action is shadow-mode wiring (no live behavior change), not immediate filter activation.

---

## 1. Build summary

### 1.1 Module

`src/kalshi_bot_v5/filter_combined.py`. Exports:

- `CombinedFilterDecision` NamedTuple: `should_trade`, `reason`, `poly_mid`, `sportsbook_implied`, `kalshi_price`, `cross_market_implied`, `confidence`, `fired_rules`.
- `evaluate_market_combined(ticker, kalshi_price, series_ticker, *, poly_lookup, sportsbook_lookup, cross_market_data, fade_threshold_cents_poly, fade_threshold_cents_book, monotonicity_threshold_cents) -> CombinedFilterDecision`.
- `parse_ladder_ticker`, `series_prefix_of`, `is_ladder_series` (mirrors v4).
- Constants `FADE_THRESHOLD_CENTS_POLY_DEFAULT = 7.0`, `FADE_THRESHOLD_CENTS_BOOK_DEFAULT = 5.0`, `MONOTONICITY_THRESHOLD_CENTS_DEFAULT = 5.0`.

Defensive-overlay semantics preserved from v4: filter only REMOVES trades v1 would have made; never ADDS. Under-priced markets are not skipped.

OR-logic across the three sub-rules: `should_trade = NOT (A1 OR A2 OR A3)`. When multiple rules fire, the reason field is `any_fade_rule_fires` and the `fired_rules` tuple lists which.

### 1.2 Locked thresholds (pre-registered before any backtest)

| Threshold | Value | Rationale |
|---|---:|---|
| `fade_threshold_cents_poly` | 7.0 | Matches V4-E locked value; V3-C measured Kalshi-Polymarket mean +9.21c at T-35d. |
| `fade_threshold_cents_book` | 5.0 | V5-A1 measured Kalshi-Sportsbook mean +1.70c on favorites (n=23). 5c is the smallest sensible fade threshold above live-mid noise. Tighter than Polymarket threshold because sportsbook is institutional consensus (smaller divergences). |
| `monotonicity_threshold_cents` | 5.0 | Matches V4-E locked value. |

These were locked BEFORE any backtest run. The v5 iterations.md will be updated alongside this doc to record the pre-registration.

### 1.3 Unit tests

`tests/v5/test_filter_combined.py`: 28 tests pass. Coverage:

- A1 fires, no-fade, no-match, callable lookup
- A3 (new) fires, no-fade, no-match, threshold-at-boundary (5c), callable lookup, under-priced does NOT fire
- A2 monotonicity violation, consistent passes, non-ladder series inactive
- Multi-rule combinations: A1+A3 fire, all three fire, A1-only fires, A3-only fires, neither fires
- Threshold-lock test (defaults are exactly 7c/5c/5c)
- NamedTuple contract test (fields present)
- Edge cases: no inputs at all -> `no_match`; only poly attempted -> `no_poly_match`; only book attempted -> `no_book_match`

All tests run in 0.06s. The module is pure (no IO, no API calls).

### 1.4 Sportsbook lookup builder

`scripts/v5/build_sportsbook_lookup.py`. Takes a list of Kalshi tickers, maps each to the-odds-api sport_key via prefix lookup, finds the matching event in the cached `/v4/sports/{sport}/odds?markets=h2h&regions=us` response, extracts the de-vigged median sportsbook implied probability for the Kalshi YES outcome, and writes `data/v5/sportsbook_lookup_<date>.parquet`.

Supported series and sport_keys:

| Kalshi series | the-odds-api sport_key | Match type |
|---|---|---|
| KXMLBGAME | baseball_mlb | h2h, 2-way devig |
| KXNFLGAME | americanfootball_nfl | h2h, 2-way devig |
| KXWCGAME | soccer_fifa_world_cup | h2h, 3-way devig (with draw) |
| KXUFCFIGHT | mma_mixed_martial_arts | h2h, 2-way devig, substring match |
| KXBOXING | boxing_boxing | h2h, 2-way devig, substring match |

Defaults to cache-only mode (zero new credits). Run-time output on 58 v1 candidates:
- 58 / 58 matched (100% success rate on the pre-cached events)
- 0 credits used (cache hits for all 5 sport_keys)
- Output written to `data/v5/sportsbook_lookup_20260524.parquet` and `sportsbook_lookup_latest.parquet`

### 1.5 Backtest runner

`scripts/v5/run_sportsbook_filter_backtest.py`. Runs two paths per the master plan:

- **Path X**: live-cached pairs from V5-A1 + Kalshi `/markets/{ticker}` lookup to find resolved outcomes. Outcome inference uses Kalshi `status='finalized'` first; falls back to post-expiry `last_price_dollars >= 0.85 or <= 0.15` for markets in late settlement.
- **Path Y**: V4-E's v3 inventory (n=147 v1-eligible) + current sportsbook implied (sampled TODAY, not at T-35d - documented limitation).

Outputs `data/v5/sportsbook_filter_backtest_results.json` with all arm results.

---

## 2. Path X result: live-cached probe with Kalshi resolution

### 2.1 Sample composition

Today (2026-05-24) is mid-MLB season. From V5-A1's 58 cached Kalshi-vs-sportsbook pairs, the count of RESOLVED markets at the time of this build:

| Slice | n resolved | Resolution source |
|---|---:|---|
| v1-eligible band (kalshi_mid in [0.70, 0.95]) | 2 | `finalized` |
| Extended (all kalshi_mid) | 7 | 6 finalized + 1 post-expiry-inferred |

The 2 v1-band resolved markets:

| Ticker | Kalshi mid | Sportsbook median | Divergence | Outcome |
|---|---:|---:|---:|---:|
| KXMLBGAME-26MAY241610ATHSD-ATH | 0.880 | 0.8626 | +1.7c | 1 (YES, Athletics won) |
| KXMLBGAME-26MAY241605CWSSF-SF | 0.795 | 0.7762 | +1.9c | 1 (YES, SF won) |

Both within 5c of the sportsbook implied, so the A3 filter does NOT fire on either, both pass through unchanged. Filter diff = 0pp.

### 2.2 Path X verdict

The locked-threshold combined filter on the v1-band Path X sample fires on 0 of 2 markets. TA1 trivially passes (100% coverage because both markets have a sportsbook lookup), TA3 trivially passes (0% skip rate), TA4 is undefined (no fires, no diff), TA5 fails (only 1 series in sample).

The extended Path X (n=7, all KXMLBGAME) similarly produces zero filter fires because the largest divergence in the resolved subset is < 3c, all well below the 5c threshold. No skip, no diff, no signal.

**Honest interpretation:** Path X is structurally too small to evaluate TA2-TA5. The signal-direction probe from V5-A1 (mean +1.70c on n=23 favorites) is consistent with the no-fire outcome on n=2: most divergences fall below the 5c threshold, and the 3 markets that DO exceed 5c on V5-A1's broader 13-row v1-band sample (KXWCGAME-ENG-vs-GHA, KXWCGAME-SCO-vs-BRA, KXMLBGAME-WSH-vs-ATL on the ATL side) haven't resolved yet as of this build.

The WSHATL ATL-side market is particularly interesting: V5-A1 captured Kalshi 0.725 vs sportsbook 0.6295 (divergence +9.55c, well above 5c). Today's current Kalshi `last_price_dollars` on that market is 0.34, suggesting ATL lost. If this resolves NO (outcome=0), the filter would have correctly saved a -77c v1 loss. This is the single most important data point pending; the operator should re-run this backtest after KXMLBGAME-26MAY24 markets finalize (typically within hours of game end).

---

## 3. Path Y result: v4 inventory + current sportsbook overlay

### 3.1 Coverage of v3 inventory by current sportsbook

The v3 inventory (n=147 v1-eligible markets) is dominated by season-long-winners series:
- KXNFLWINS: 95 (denylisted by W1 but kept in inventory for this comparison; KXNFLWINS-25B 2025 NFL season)
- KXNBAWINS: 17 (2025-26 NBA season win totals)
- KXMLBWINS: 10 (2025 MLB season win totals)
- KXNFLPLAYOFF: 9 (denylisted)
- KXNCAAFPLAYOFF: 8 (2025-26 CFB playoff)
- KXMLBPLAYOFFS: 5 (denylisted; 2025 MLB playoffs)
- Other: 4

None of these are h2h game-resolution markets, which is what V5-A1's coverage matrix MATCH-class spans. The-odds-api h2h sportsbook coverage on v3 inventory is therefore **0%**.

A future build could add the-odds-api OUTRIGHTS endpoints (championship_winner sport keys for KXNCAAFPLAYOFF, KXMLBPLAYOFFS, KXNBAPLAYOFFWINS, etc.) but that requires per-team outright probability extraction which is out of scope for this Phase 2 deliverable. V5-A1 documented that path as feasible (PARTIAL-class) but it doubles the matching complexity.

### 3.2 Combined filter headline arm on v3 inventory

The combined filter on v3 inventory at locked thresholds reproduces V4-E's result exactly:

```
n_eligible = 147
n_filter_traded = 131 (89.1%)
n_filter_skipped = 16 (10.9%)
n_filter_activated = 122 (83.0% coverage)

Rule fires:
    polymarket_fade        : 4
    sportsbook_fade        : 0   (no MATCH-class coverage on this inventory)
    monotonicity_violation : 12

Bare v1 mean P&L: -0.93pp, hit_rate 87.8%, CI [-6.07pp, +4.00pp]
Filter+v1  mean P&L: +0.77pp, hit_rate 79.6%, CI [-4.00pp, +5.17pp]
Diff: +1.70pp, CI [-0.32pp, +4.22pp]
```

TA verdict: 4 of 5 pass, TA4 borderline-fail at -0.32pp. IDENTICAL to V4-E's result. The sportsbook arm contributes ZERO additional value on this backtest path because the inventory does not include MATCH-class series.

### 3.3 Per-rule decomposition on v3 inventory

| Arm | n filter fired | Diff (pp) | CI lower | TA criteria pass |
|---|---:|---:|---:|---:|
| Combined (poly + book + mono) | 16 | +1.70pp | -0.32pp | 4 / 5 |
| Book-only | 0 | 0.00pp | 0.00pp | 1 / 5 (TA3 only) |
| Poly-only | 4 | +1.08pp | -0.16pp | 2 / 5 |
| Cross-market only | 12 | +0.62pp | -0.72pp | 2 / 5 |

The book-only arm has ZERO coverage on this inventory. The poly + cross-market combination accounts for all 16 filter fires.

### 3.4 Honest caveat on Path Y

Sportsbook prices for Path Y are sampled TODAY (2026-05-24), not at the historical T-35d window when v1 would have entered each trade. The-odds-api free tier blocks historical odds (V5-A1 documented HTTP 401 HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN), so a clean signal test on the resolved inventory is not possible without the $30/mo paid tier.

Even with paid tier, the v3 inventory's series mix means the sportsbook signal would NOT cover game-resolution h2h markets where it's strongest. The right shadow-mode universe is v1's LIVE candidate stream, not v3's historical inventory.

---

## 4. Sportsbook fire-rate on live v1 universe

This is the binding measurement for whether A3 deserves shadow-mode deployment.

### 4.1 V5-A1 sample re-analysis at locked 5c threshold

From V5-A1's `divergence_summary.json` (n=58 total, n=23 favorites by sportsbook >= 0.55, n=13 v1-band by Kalshi in [0.70, 0.95]):

| Slice | n | A3 fire count at 5c | A3 fire rate |
|---|---:|---:|---:|
| All favorites (book >= 0.55) | 23 | 3 | 13.0% |
| v1-band candidates | 13 | 3 | 23.1% |

The 3 fires at the locked 5c threshold:

| Ticker | Kalshi mid | Book median | Divergence | A3 fires? |
|---|---:|---:|---:|:---:|
| KXWCGAME-26JUN23ENGGHA-ENG | 0.715 | 0.5536 | +16.14c | YES |
| KXWCGAME-26JUN24SCOBRA-BRA | 0.730 | 0.5851 | +14.49c | YES |
| KXMLBGAME-26MAY241610WSHATL-ATL | 0.725 | 0.6295 | +9.55c | YES |

All 3 fires are at divergences >= +9c, much higher than the 5c threshold. At fade_threshold_cents_book = 7c, the same 3 markets fire. At 3c the same 3 fire (because the gap between 3c and 9c is empty on this sample). At 10c, only 2 fire (the WC pair).

### 4.2 Coverage TA1

The sportsbook lookup builder matched **58 of 58 candidates (100%)** with the cached responses. On v1's actual live universe (post-denylist, 29 attempted orders per V5-A1 Section 1.1), the MATCH-class coverage is 31.0% per V5-A1 Section 3.5. So on the FORWARD-looking shadow-mode deployment, A3 would have inputs for ~30% of v1 candidates.

This clears TA1 (>= 30% coverage). Combined with A1's 42.6% Polymarket coverage on the same universe (V4-A), the COMBINED filter's coverage on v1's live universe is likely 55-70% (union of both, with overlap on h2h-soccer / boxing / UFC).

### 4.3 Skip rate TA3

If 23% of v1-band candidates would fire A3, the combined filter's skip rate (A1 + A2 + A3 OR-logic) is bounded above by 23% from A3 alone. Adding A1 fires (V4-A measured 5-15% expected fire rate on v1's live universe based on its 42.6% coverage + 12-30% within-coverage divergence rate) keeps the combined skip rate well below 50% (TA3 floor).

### 4.4 TA2, TA4, TA5: deferred to shadow-mode

The mean P&L improvement (TA2), bootstrap CI lower bound (TA4), and per-series coverage (TA5) all require resolved outcomes. With Path X n=2 (or n=8 extended) and Path Y zero sportsbook fires, we cannot evaluate. Shadow-mode logging on v1's live stream will accumulate the necessary resolutions over 120-180 days (matches V4-E's revised shadow-mode timeline per Phase 3 critic).

---

## 5. Per-rule contribution decomposition

### 5.1 Where each rule fires

Based on V5-A1's coverage matrix + V4-A's coverage matrix:

| Rule | Best coverage | Best signal direction observed | Independence |
|---|---|---|---|
| A1 (Polymarket-fade, 7c) | KXMLBPLAYOFFS (5 of 5 v3 inv), WC squad, MLB win-totals | +9.21c mean (V3-C, n=5) | Polymarket retail-driven |
| A2 (Monotonicity, 5c) | KXNFLWINS ladder (~12 fires on 95), KXNBAWINS ladder (sparse), KXMLBWINS ladder | Logical, not empirical | Same-exchange, structural |
| A3 (Sportsbook-fade, 5c) | h2h games (MLB/NFL/NCAAF/WC), boxing, UFC, championship outrights | +1.70c mean (V5-A1, n=23 favorites); +2.95c on v1-band (n=13) | Institutional consensus |

The three rules have LITTLE OVERLAP in WHERE they fire on the v1 universe:
- A1 dominates the futures / season-long markets where Polymarket has retail flow but sportsbooks lack listings.
- A2 dominates the ladder markets within a single team-season.
- A3 dominates the game-resolution markets where sportsbooks have deep h2h liquidity.

The combined filter benefits from this disjoint coverage: it catches over-pricing signals across more of v1's universe than any single rule. V4-A's Polymarket-only coverage was 42.6%; V5-A1's the-odds-api coverage was 40.7%; the UNION coverage by series is likely 55-70%, with ~10% double-covered.

### 5.2 Backtest evidence per rule

- **A1 (Polymarket-fade):** From V4-E and reproduced here, A1 fires 4 times on the n=147 v3 inventory, all on KXMLBPLAYOFFS-25. Diff = +1.08pp on n=147, CI [-0.16pp, +2.91pp]. TA4 borderline-fail; mechanism corroborated by V3-C.
- **A2 (Cross-market):** Fires 12 times on KXNFLWINS-25B in v3 inv. Diff = +0.62pp on n=147, CI [-0.72pp, +2.47pp]. TA4 borderline-fail; sensitivity sweep shows signal collapses at higher monotonicity thresholds (V4-E Section 5.1).
- **A3 (Sportsbook-fade):** Fires 0 times on v3 inventory (no h2h game-resolution markets in that inventory). On V5-A1's live universe sample of 13 v1-band candidates, A3 fires 3 times (23% fire rate). Resolved P&L on those 3 awaits market close.

The combined OR-logic on v3 inventory matches V4-E's result identically: +1.70pp diff, CI [-0.32pp, +4.22pp]. The A3 rule is value-additive on FORWARD-LOOKING live data, not retrospective v3 inventory.

---

## 6. Pivots attempted

Per master plan Section 5, here are the pivots attempted in this build:

### 6.1 Path X v1-band only (n=2)
Result: too small for TA2-TA5 evaluation. Documented.

### 6.2 Path X extended to all bands (n=8)
Result: still too small. No A3 fires (max divergence in resolved subset is < 3c).

### 6.3 Path Y v4 inventory backtest
Result: book-only coverage 0% (inventory has no MATCH-class series). Combined filter reproduces V4-E exactly. No new signal.

### 6.4 Book threshold sensitivity (3c, 5c, 7c, 10c)
Result: at the locked 5c threshold, 3 fires on v1-band live sample. At 3c, same 3 fires (no markets in 3-5c band). At 7c, same 3 (all are at 9c+). At 10c, 2 fires (loses the MLBGAME ATL at 9.55c). The signal is concentrated at the 9c+ tail.

### 6.5 Prospective-logger pattern (recommended)
This is the recommended Phase 3 deliverable: wire the combined filter into v1's main loop in shadow-mode (logs decisions; no behavior change). After 120-180 days of accumulated resolutions, run a clean TA evaluation. This matches V4-E's revised shadow-mode timeline.

### 6.6 Paid tier (NOT recommended yet)
The $30/mo 20K-credit tier would unlock historical odds for a one-time backtest on v3 inventory's KXMLBPLAYOFFS-25 sub-stack and any other MATCH-class series that existed at the historical time. Estimated 150 credits per resolved-eligible-series; fits comfortably in the 20K monthly budget.

Recommend paid tier ONLY IF shadow-mode logging shows A3 firing at a meaningful rate on v1's live stream AND the signal direction holds across 30-60 days of new data. The kill-early principle says do NOT spend $30 to confirm a signal we cannot yet validate at small n.

### 6.7 Inverse-signal direction check (not triggered)
Master plan Section 5 notes: if sportsbook says Kalshi is UNDER-priced (Kalshi - book < -threshold), that's a different signal worth flagging (would imply BUYING more). V5-A1 measured the OPPOSITE direction (Kalshi over book on favorites, +1.70c mean). The defensive overlay correctly does NOT fire on under-pricing, but a future build could log "inverse-signal candidates" as flag-only telemetry.

### 6.8 Coverage gap check (Polymarket vs the-odds-api)
Per V5-A1 Section 5: Polymarket and the-odds-api cover roughly the same 40% of v1's live universe but on different subsets. Polymarket strengths: WC squad, F1 futures, MLB win-totals; the-odds-api strengths: h2h MLB/NFL/NCAAF games, boxing, UFC. The combined filter's union coverage is HIGHER than either alone. This Phase 2 deliverable enables the union; the realized union coverage will surface during shadow-mode.

---

## 7. Recommendation

**SHIP shadow-mode**, formally:

1. Activate `src/kalshi_bot_v5/filter_combined.py` in shadow-mode by wiring `evaluate_market_combined(...)` into v1's `favorite_maker.py` main loop. **NO BEHAVIOR CHANGE** to v1's trades; log decisions to `data/live_trades/filter_combined_shadow_log.parquet`.

2. The wiring must populate `sportsbook_lookup` from `scripts/v5/build_sportsbook_lookup.py` (cache-only at startup; refresh once per market close window). Initial estimate: ~150 calls/month at 1 credit/call = 30% of the free 500-credit budget.

3. Collect 120-180 days of resolved filter activations. Then re-run `scripts/v5/run_sportsbook_filter_backtest.py` against the accumulated log (replace Path X build with the shadow log + Kalshi resolution lookup).

4. Re-evaluate TA1-TA5 at that point. If TA4 cleanly passes (CI lower > 0), activate the filter (turn shadow-mode into a SKIP overlay in v1's `order_manager`). If still borderline, extend shadow-mode another 60 days or request operator's paid-tier authorization for historical backfill.

**Do NOT immediately activate as a SKIP overlay.** Same kill-early principle as V4-E: a borderline TA4 + small-n signal direction does not justify modifying v1's $32 live capital flow. The cost of waiting 120-180 days is zero (v1 keeps running as today); the cost of premature activation is unbounded (filter could subtract value if the signal collapses on more data).

**Do NOT recommend paid tier at this point.** $30/mo is a meaningful spend relative to the $32 deployed capital. The free-tier shadow-mode generates enough signal in 90 days to make the paid-tier decision rationally.

---

## 8. Output artifacts

| Path | Contents |
|---|---|
| `src/kalshi_bot_v5/__init__.py` | v5 package init |
| `src/kalshi_bot_v5/filter_combined.py` | Combined filter module (CombinedFilterDecision + evaluate_market_combined) |
| `tests/v5/__init__.py` | Test package init |
| `tests/v5/test_filter_combined.py` | 28 unit tests for combined filter |
| `scripts/v5/build_sportsbook_lookup.py` | Sportsbook lookup builder (cache-first; max-credits gated) |
| `scripts/v5/run_sportsbook_filter_backtest.py` | Retrospective backtest runner (Path X + Path Y + decomposition arms) |
| `data/v5/sportsbook_lookup_20260524.parquet` | Per-ticker sportsbook implied probability table (58 rows, 58 matched) |
| `data/v5/sportsbook_lookup_latest.parquet` | Symlink-copy of latest |
| `data/v5/sportsbook_lookup_meta.json` | Build metadata (credits used, fetch attempts, unmatched reasons) |
| `data/v5/sportsbook_filter_backtest_results.json` | All arm results with per-series breakdowns and TA criteria |
| `data/v5/sportsbook_candidate_status.csv` | Per-ticker Kalshi status snapshot at build time |
| `research/v5/04-sportsbook-filter-build.md` | This document |

---

## 9. Reproducibility

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
uv run python -m pytest tests/v5/test_filter_combined.py -v
uv run python -m scripts.v5.build_sportsbook_lookup --verbose
uv run python -m scripts.v5.run_sportsbook_filter_backtest
```

The lookup builder runs cache-only by default (zero new credits). The backtest runner hits Kalshi's read-only `/markets/{ticker}` endpoint for each of the 58 V5-A1 candidates to check resolution status (no write actions, no auth-state changes).

Credits used in this Phase 2 build: 0 (cache-only, all sport_key h2h responses cached from V5-A1's Phase 1). Combined V5-A1 + V5-A2 credit consumption: 5 of 500 free-tier monthly.

---

## 10. Honest constraints

1. **Path X sample size n=2 (v1-band) / n=8 (extended) is too small to clear TA2-TA5.** Shadow-mode wiring is the correct remediation, not threshold tuning.

2. **Path Y v3 inventory has zero MATCH-class overlap with the sportsbook arm.** The sportsbook coverage on v3 inv is 0% because the inventory was built from long-horizon resolved markets, while the-odds-api MATCH-class is dominated by short-horizon h2h game-resolution. This is a v3-inventory selection-bias issue documented in V4-E Section 6.3 and V5-A1 Section 1.2.

3. **The locked book threshold 5c is calibrated to V5-A1's sportsbook divergence distribution (mean +1.70c, sd 5.09c).** A larger live sample could justify either tightening (3c if mean shrinks toward 1c) or loosening (7-10c if the +9c tail dominates), but the threshold is LOCKED for shadow-mode evaluation. Any change after shadow-mode data accumulates is a pre-registered new test, not a re-tune.

4. **Sportsbook lookup uses live h2h prices, not closing-line.** The right signal-direction measurement is at T-X minutes before each market closes (mirrors V3-C's T-35d measurement). Shadow-mode logging will capture the timestamp at each filter activation; closing-line comparison comes from the accumulated log + Kalshi resolution timestamps.

5. **De-vigging assumes proportional vig.** For 2-way h2h markets (MLB, UFC, boxing, NFL) this is benign. For 3-way h2h (WC with draw outcome) proportional de-vigging is an upper-bound approximation. WC fires (n=2 of the 3 in V5-A1's v1-band sample) carry slightly more measurement noise.

6. **The combined filter's sportsbook arm is INDEPENDENT of the Polymarket arm in terms of WHERE it fires.** This is the master plan's "non-collinear second-opinion sources" thesis. The empirical confirmation requires shadow-mode forward-test.

7. **No new credits consumed by V5-A2 build.** All 58-ticker sportsbook lookups hit V5-A1's pre-cached responses. The live operational deployment in shadow-mode would consume ~150 credits/month per V5-A1 Section 6.

---

## 11. Decision for v5 Phase 3 / 4

Per master plan Section 4 (adversarial critic):

The critic should test:
- Whether the 23% fire rate on V5-A1's 13-row v1-band sample generalizes to v1's actual live candidate stream. The sample is regime-dependent (mid-MLB, pre-NFL season; WC pre-tournament). A repeated probe in November (NFL Week 11) would have a different MLBGAME / NFLGAME / WCGAME mix.
- Whether the 5c threshold is robust to seasonal shifts in sportsbook calibration (some books tighten lines in playoffs; offshore books drift).
- Whether the combined filter's union coverage actually fires on disjoint markets in production, or if Polymarket and the-odds-api end up co-firing on the same h2h soccer / boxing matches (collinearity risk).

Per Phase 4 iteration plan:

If the critic agrees the shadow-mode recommendation is honest, the v5 Phase 4 deliverable is wiring `evaluate_market_combined` into v1's main loop as a SHADOW-mode call. Same wiring pattern V4-E recommended for the Polymarket-only filter, plus the sportsbook_lookup builder. No v1 trade behavior changes.

If the operator wants accelerated Phase 4, the $30/mo paid tier unlocks historical sportsbook lookup for v3 inv's resolved KXMLBPLAYOFFS-25 / KXMLBWINS-25 / KXNFLWINS-25B markets at their actual T-X entry windows. Estimated 150 credits/snapshot per series-cohort, well within 20K budget. This would let us test the A3 rule on a CLEAN historical signal sample without waiting 6 months.

Both paths honor the master plan. The free-tier shadow-mode is the kill-early-friendly default.
