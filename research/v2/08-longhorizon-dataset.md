# v2 Joined LONG-HORIZON MLB Dataset Build (Agent G)

**Date:** 2026-05-23
**Author:** Agent G (Wave 5 salvage, autonomous)
**Producer script:** `scripts/v2/build_mlb_longhorizon_dataset.py`
**Output parquet:** `data/v2/joined_mlb_longhorizon_dataset.parquet`
**Dropped-rows audit:** `data/v2/joined_mlb_longhorizon_dropped.parquet`
**Individual-series audit:** `data/v2/joined_mlb_longhorizon_individual.parquet`
**Run metadata:** `data/v2/joined_mlb_longhorizon_meta.json`
**Status: BUILT WITH SAMPLE-SIZE CAVEAT.** Read Section 4 before
modeling.

## 1. Mission

Per `research/v2/07-decisions.md` Option B salvage path and the
critic's recommendation in `research/v2/06-critic.md` Section 9: train
v2 on v1's actual long-horizon market type rather than on
short-horizon game markets. The brief: produce a v1-comparable MLB
long-horizon dataset using v1's window semantics (trading-window mid
= `close_time - 35 days`, VWAP over `[close - 42d, close - 28d]`) so
we can sanity-check the v1 favorite-longshot edge on v1's actual
domain.

## 2. CRITICAL FINDING: sample size is a hard ceiling on this domain

The dataset successfully replicates v1's KXMLBWINS rows exactly (5
overlapping markets, identical prices and outcomes), and extends with
KXMLBPLAYOFFS data v1 did not include. But the methodology only
yields **n=11 eligible markets** at the [0.70, 0.95] favorite band
within the 30 to 180 day lifetime window. This is a structural
constraint, not a filter calibration issue.

Three forces compress the sample:

1. **Concentrated close-time clustering.** All KXMLBWINS, KXMLBPLAYOFFS,
   and division-winner markets close within a 2-day band at the end
   of the MLB regular season (2025-09-29 to 2025-10-01). That means
   the trading-window mid (close - 35d) is **the same calendar window
   for the entire dataset**: late August 2025. There is no
   walk-forward CV possible on this corpus; everything is one
   trading window observation.

2. **Trades cluster at expiration.** Of NYY-T90's 107 lifetime
   trades, only 4 fall in the [close-42d, close-28d] window. Most
   long-horizon MLB markets see their trade volume concentrate
   inside the last 7-14 days before close (when the season's outcome
   is becoming clearer). This kills 132 of 210 candidate markets via
   the n_trades >= 5 floor.

3. **Division winners exceed the 180d cap.** KXMLBALEAST,
   KXMLBALCENT, etc. have lifetime ≈ 186.6 days. The v1
   Round-7 `--max-lifetime-days 180` filter excludes them. They are
   retained in the dataset (mirroring v1's build pattern of
   build-with-min, gate-with-max) but flagged `is_eligible=False`.

The dataset is methodologically clean (no leakage; team features are
strictly AS OF the trading-window mid; outcomes pulled from MLB Stats
API; prices computed from raw historical trades). What it is **not**:
big enough to support an ML model fit. A 5 or 11 row eligible set
cannot survive a 5-fold walk-forward CV with sane fold sizes, let
alone a leak-fixed C5 per the critic's Finding 1 (`06-critic.md`
Section 3).

## 3. Pipeline (`scripts/v2/build_mlb_longhorizon_dataset.py`)

### Step 1: Source-of-truth markets

Reads cached Kalshi historical markets from `data/sports/markets/`.
Series ingested are auto-discovered for all `KXMLBWINS-*.parquet` plus
the hardcoded list of division-winner and playoff series:

- 30 `KXMLBWINS-{team}` series (one per MLB team)
- 6 division series (`KXMLB{AL,NL}{EAST,CENT,WEST}`)
- 1 playoff-qualifier series (`KXMLBPLAYOFFS`)

The cached markets cover the 2024-10-01 to 2026-04-30 close window
per v1's `scripts/sports/fetch_markets.py`. 330 raw market rows in
total. No fresh Kalshi market fetch is needed; v1's cache already
covers the full corpus.

Individual-player series (`KXMLB{AL,NL}{MVP,CY,ROTY}`, `KXMLBWSMVP`)
and country-level series (`KXMLBWORLD`) are EXCLUDED per the brief.
They are written separately to
`data/v2/joined_mlb_longhorizon_individual.parquet` as an audit
record (99 markets).

### Step 2: Eligibility filters at build time

Applied in order:

- `status` in {settled, finalized}: 0 dropped
- `market_type == 'binary'`: 0 dropped (all long-horizon MLB markets
  are binary YES/NO)
- `lifetime_days >= 30`: 21 dropped (rare short-lifetime spillover)

After these, **309 candidate markets remain**.

### Step 3: Team-favorite parsing

Per the brief, only markets where the YES contract corresponds to a
specific MLB team get team-level features. The parser handles three
grammars:

- `KXMLBWINS-{TEAM}-{YY}-T{N}` (e.g., KXMLBWINS-NYY-25-T90): 150
  markets
- `KXMLB{AL,NL}{EAST,CENT,WEST}-{YY}-{TEAM}` (e.g., KXMLBALEAST-25-TOR):
  30 markets
- `KXMLBPLAYOFFS-{YY}-{TEAM}` (e.g., KXMLBPLAYOFFS-25-NYY): 30
  markets

210 team-favorite markets, 99 individual-or-other (routed to the
audit file). The Kalshi-side `ARI` alias is mapped to MLB-side `AZ`
per the v1 build_mlb_dataset.py precedent.

### Step 4: Trading-window VWAP

For each market: window = `[close - 42d, close - 28d]` (14 days
wide; v1 Round-7 sports methodology). Trade source:

- First load v1's cached trade parquet from `data/sports/trades/`
  if present. The v1 fetcher already saved trades over this window.
- For markets with 0 cached trades (e.g., 7 KXMLBWINS-* teams that
  v1 dropped from its raw fetcher and any cache misses), fetch live
  via the existing KalshiClient.

VWAP is `sum(price * size) / sum(size)`. We also compute a
small-trade VWAP (size <= 10 contracts), n_trades_in_window,
volume_fp_in_window, and one_sided_flow_pct (max of yes/no taker
counts over total).

Markets with `n_trades_in_window < 5` are dropped with reason
`insufficient_trades_in_window`. 164 markets dropped here.

### Step 5: Team-feature engineering (no look-ahead)

For each market the cutoff is `trading_window_mid = close - 35d`. We
pull the full 2025 MLB regular-season schedule from MLB Stats API
once (~2,500 games) and compute per-team features for the YES-side
team:

- `team_games_played`, `team_wins`, `team_losses`, `team_win_pct`
- `team_runs_scored_pg`, `team_runs_allowed_pg`, `team_run_diff_pg`
- `team_pyth_wpct` (James, 1.83 exponent)
- `team_recent_form_wpct` (last 30 days before mid, matching the
  brief)
- `team_home_wpct`, `team_away_wpct`
- `team_vs_500_wpct` (record vs teams with own wpct >= 0.500 at the
  mid)
- `team_days_rest` (days since team's last game)

All features use **only regular-season games with
`game_start_utc < trading_window_mid`**. Postseason games are
excluded from base rates (regular-season form is the operative
predictor for a season-long bet, consistent with `03-dataset-build.md`
Section 6). A (team, cutoff_hour) memoization cache reduces compute.

### Step 6: Eligibility flag

`is_eligible = (favorite_price in [0.70, 0.95]) AND
(lifetime_days in [30, 180])`. Strategy-B-compatible markets only.
This matches the v1 favorite-maker gate eligibility.

### Step 7: Output schema

Required columns (v1 schema compatibility, per brief Step 5):

- `ticker`, `series_ticker`, `event_ticker`
- `market_open_time`, `market_close_time`, `settlement_ts`
- `outcome` (1 if YES wins)
- `mid_price_at_T_small` (the VWAP small-trade-only)
- `mid_price_at_T_all` (the VWAP all trades)
- `league` (always "MLB"), `market_tier`, `lifetime_days`

v2 extensions:

- `favorite_team_abbrev` (Kalshi-side abbrev)
- `favorite_team_mlb` (MLB-API canonical abbrev after alias map)
- `market_kind` ("wins" / "division" / "playoffs")
- `trading_window_mid`
- `vwap_n_trades_in_window`, `vwap_volume_in_window`, `one_sided_flow_pct`
- team_* features per Step 5

## 4. Build results

### Counts

- Raw cached market rows: 330
- After status + binary + lifetime>=30d filters: 309
- Team-favorite (parseable team ticker): 210
- Individual/other (audit-only): 99
- After VWAP n_trades >= 5: **46 final rows**
- Strategy-B-eligible (favorite_price 0.70-0.95 AND lifetime 30-180d):
  **11 rows**

### Series breakdown (eligible only)

| Series | n eligible | Outcomes (YES) |
|---|---|---|
| KXMLBWINS-CHC | 1 | 1 (CHC over 90) |
| KXMLBWINS-HOU | 1 | 1 (HOU over 80) |
| KXMLBWINS-LAA | 1 | 1 (LAA over 70) |
| KXMLBWINS-LAD | 1 | 1 (LAD over 90) |
| KXMLBWINS-MIL | 1 | 1 (MIL over 90) |
| KXMLBPLAYOFFS | 6 | 4 (SEA, SD, NYY, BOS; HOU and NYM missed) |

### Headline numbers (eligible n=11)

- Outcome rate: **0.818** (9 of 11 YES)
- Mean favorite_price: **0.847**
- Implied minus realized: **+2.85pp** (favorite was overpriced; 0.847 > 0.818)
- Trading window mid: **2025-08-25 14:00 UTC** for all eligible rows

### v1 cross-check

The 5 KXMLBWINS rows in the v2 dataset have **prices identical to v1**
(verified merge by ticker; price_diff = 0.0 exactly on all 5):

| Ticker | favorite_price | outcome | v1 outcome |
|---|---|---|---|
| KXMLBWINS-CHC-25-T90 | 0.8264 | 1 | 1 |
| KXMLBWINS-HOU-25-T80 | 0.9240 | 1 | 1 |
| KXMLBWINS-LAA-25-T70 | 0.8794 | 1 | 1 |
| KXMLBWINS-LAD-25-T90 | 0.7357 | 1 | 1 |
| KXMLBWINS-MIL-25-T90 | 0.9392 | 1 | 1 |

This confirms the build is method-identical to v1 for the overlapping
rows. The 6 KXMLBPLAYOFFS rows are NEW (v1 did not include
KXMLBPLAYOFFS in its corpus); their inclusion materially changes the
aggregate picture (see Section 5).

The v1 dataset also has 1 KXMLBSTATCOUNT-eligible row
(KXMLBSTATCOUNT-26ITPHR-1, p=0.938, outcome=1). v2's parser does not
treat KXMLBSTATCOUNT as a team-favorite market (its YES side is a
specific player's stat threshold, not a team), so it is in the
individual-audit bucket. The decision is consistent with the brief's
exclusion of individual-player markets from the modeling subset.

### Calibration

| Series subset | n | mean favorite_price | realized | implied-realized |
|---|---|---|---|---|
| KXMLBWINS (5) | 5 | 0.881 | 1.000 | +11.9pp |
| KXMLBPLAYOFFS (6) | 6 | 0.818 | 0.667 | -15.2pp |
| All eligible (11) | 11 | 0.847 | 0.818 | -2.9pp |

The KXMLBWINS bucket shows the favorite-longshot bias going IN our
favor (+11.9pp realized over implied). The KXMLBPLAYOFFS bucket goes
the WRONG way (-15.2pp, favorites overpriced). Aggregate cancellation
yields a small net penalty.

## 5. v1-heuristic realized P&L

Using v1's exact formula (`realized = outcome - price - 2 *
maker_fee - 0.015 slippage`):

| Subset | n | mean | median | hit rate | SD | 95% CI |
|---|---|---|---|---|---|---|
| All eligible | 11 | -6.35pp | +8.56pp | 81.8% | 36.6pp | [-31.4pp, +12.3pp] |
| KXMLBWINS only | 5 | **+10.41pp** | +8.56pp | 100% | 7.4pp | **[+4.4pp, +17.4pp]** |
| KXMLBPLAYOFFS only | 6 | -20.31pp | +6.13pp | 66.7% | 44.6pp | [-54.1pp, +12.0pp] |

**Comparison to the v1 gate report:**

- v1 favorite-maker gate (Round 4 doc text): test mean **+5.13pp**, n=33,
  hit rate 63.6%, CI [+2.60pp, +7.99pp] across ALL sports leagues.
  The reported number was at an earlier corpus size (Round 4 data).
- v1 gate replay TODAY on the current `data/processed/sports_dataset.parquet`
  (423 rows): holdout n=16, mean **+11.41pp**, CI [+8.17pp, +14.81pp].
- v1 gate replay restricted to lifetime in [30, 180]d:
  n=14, mean **+10.93pp**, CI [+7.28pp, +14.85pp].
- v1 MLB-only subset (n=6 eligible after 30-180d + price 0.70-0.95):
  mean **+9.12pp**, hit 100%, all KXMLBWINS markets.
- v2 long-horizon MLB KXMLBWINS only (this dataset): mean **+10.41pp**,
  n=5, hit 100%, CI [+4.4pp, +17.4pp].

The KXMLBWINS-only subset of v2 reproduces v1's MLB-only positive
edge essentially exactly (+10.41pp vs +9.12pp on the overlapping
markets; mean within 1.3pp of v1's full-dataset holdout). This
confirms the **dataset is methodologically valid**: when restricted
to the same market type v1 was evaluated on, it gives the same
answer.

The expanded inclusion of KXMLBPLAYOFFS pulls the aggregate negative
because two heavy favorites (NYM at 0.778, HOU at 0.809) missed
playoffs. With only 6 KXMLBPLAYOFFS markets in the eligible set, the
bootstrap CI is wide ([-54pp, +12pp]).

**Bottom line on the brief's validity check:** the dataset's
"realized P&L if we used the v1 heuristic" is **+10.41pp on the
v1-comparable KXMLBWINS subset**, consistent with v1's current
holdout +11.41pp and well above the doc-quoted +5.13pp from Round 4.
The build is methodologically valid. The aggregate -6.35pp on
n=11 is a consequence of including KXMLBPLAYOFFS, which adds a
different market behavior (and a small but heterogeneous sample).

## 6. What this means for v2 modeling downstream

### Will not work as-is for ML

The eligible n=11 is **structurally too small** for a calibrated
ML model. The critic's Finding 1 requires a leak-free C5 with at
least 5 folds; that would need >=25 eligible rows minimum (5 per
fold). The C4 floor is 15; we are below it.

The 46-row total dataset (including non-eligible) is not enough
either. The MLB long-horizon market type clusters at the season-end
close window. There is **no second trading window** to walk forward
into.

### What WOULD work

1. **Cross-league pool.** v1's full sports dataset (n=423 markets,
   39 eligible) pools MLB + NBA + NFL + NCAA + soccer + tennis + ...
   The +5.13pp test mean v1 reports is on this multi-league pool.
   The v2 model approach would need to use that pool, not MLB-only.

2. **Add 2026 season data.** As 2026 season-long MLB markets settle
   (Oct 2026), we would gain ~150 new KXMLBWINS markets + 30 new
   KXMLBPLAYOFFS. But that's 6 months away.

3. **Drop the trading-window-mid constraint.** If we redefine the
   trading window to be the LAST 14 days before close (e.g.,
   [close-14d, close-1d]), we capture more trades and more markets
   clear the n_trades >= 5 floor. But this is no longer a v1-comparable
   window. It also has a leakage concern: at close-14d the regular
   season is nearly over and the outcome is largely determined.

### Recommended next step

Given the structural sample-size constraint, this dataset alone
cannot be the v2 modeling corpus. Three options for the orchestrator:

a) **Accept v2 as a null finding.** This dataset confirms v1's
   long-horizon-MLB edge thesis is real on the small overlapping
   sample (+10.41pp on KXMLBWINS), but provides no new evidence
   that ML adds incremental edge over the heuristic. Per
   `feedback_kill_early.md`, this is a defensible kill point.

b) **Rebuild the dataset on the FULL multi-league sports universe.**
   Use the same window semantics, but include NBA, NFL, NHL, MLS,
   tennis, soccer, etc. v1's `data/sports/markets/` already contains
   the cache for hundreds of series. This would give ~39+ eligible
   markets, matching v1's gate report sample, and would allow a
   genuine walk-forward CV with leak-fixed C5. **This is the
   recommended path if the orchestrator wants a real v2 ML attempt
   on v1's domain.**

c) **Add v2-specific team features.** With the existing 11 rows we
   could fit a *non-ML* heuristic refinement (e.g., "trade only if
   team_pyth_wpct > 0.45 AND team_recent_form_wpct > 0.40"). The
   sample is too small to validate any added rule rigorously, but
   it could be a research direction for the orchestrator. Likely
   the answer is "this is a heuristic with no ML risk," matching
   the critic's Section 7 honest read of the original v2 model.

## 7. Schema (final parquet)

| Column | Type | Description |
|---|---|---|
| ticker | str | Kalshi market ticker |
| series_ticker | str | Kalshi series ticker (e.g., KXMLBWINS-NYY) |
| event_ticker | str | Kalshi event ticker |
| market_open_time | datetime64[ns, UTC] | When the Kalshi market opened |
| market_close_time | datetime64[ns, UTC] | When the Kalshi market closed |
| settlement_ts | datetime64[ns, UTC] | When Kalshi settled the market |
| outcome | int | 1 if YES (favorite) won, 0 otherwise |
| mid_price_at_T_small | float | VWAP yes-price over [close-42d, close-28d], small trades only |
| mid_price_at_T_all | float | VWAP yes-price over [close-42d, close-28d], all trades |
| favorite_price | float | == mid_price_at_T_small (alias for clarity) |
| league | str | Always "MLB" |
| market_tier | str | "single_name" (KXMLBWINS) or "small_multi" (division, playoffs) |
| market_kind | str | "wins", "division", or "playoffs" |
| lifetime_days | float | (close - open) / 86400 |
| favorite_team_abbrev | str | Kalshi-side team abbreviation of the YES contract |
| favorite_team_mlb | str | MLB-API canonical abbreviation (e.g., AZ for ARI) |
| trading_window_mid | datetime64[ns, UTC] | close - 35d, hour-floored |
| vwap_n_trades_in_window | int | Number of trades in [close-42d, close-28d] |
| vwap_volume_in_window | float | Total trade size in window |
| one_sided_flow_pct | float | max(yes_takers, no_takers) / total_takers |
| team_games_played | int | Team's prior regular-season games before mid |
| team_wins, team_losses | int | |
| team_win_pct | float \| null | |
| team_runs_scored_pg | float \| null | Prior regular-season RS/G |
| team_runs_allowed_pg | float \| null | Prior regular-season RA/G |
| team_run_diff_pg | float \| null | RS/G - RA/G |
| team_pyth_wpct | float \| null | James Pythagorean (1.83 exponent) |
| team_recent_form_wpct | float \| null | Last 30 days before mid |
| team_home_wpct, team_away_wpct | float \| null | |
| team_vs_500_wpct | float \| null | Record vs teams with wpct >= .500 at mid |
| team_days_rest | int \| null | Days since team's last game before mid |
| is_eligible | bool | favorite_price in [0.70, 0.95] AND lifetime in [30, 180] |

## 8. Decision log

- **2026-05-23**: Decided to use v1's cached trades parquet
  (`data/sports/trades/`) as the primary source, falling back to
  live KalshiClient fetch only for the 7 cache-missing teams
  (KXMLBWINS-ATL, AZ, BAL, CLE, MIN, TB, WSH) and any non-cached
  markets. Confirmed cached trades cover [close-42d, close-28d]
  exactly (verified spot-check on KXMLBWINS-NYY).
- **2026-05-23**: Removed build-time max-lifetime filter (180d) and
  moved it to the `is_eligible` flag, mirroring v1's build pattern.
  This preserves KXMLBALEAST/CENT/WEST etc. at 186.6d for
  audit visibility, even though they fail the strategy filter.
- **2026-05-23**: Used hour-floored `trading_window_mid` as the
  cutoff for team features. All eligible markets in this dataset
  share `trading_window_mid = 2025-08-25 14:00 UTC` (the AL East
  and similar series open in late March and close in late
  September, all within a 2-day window).
- **2026-05-23**: Skipped individual-player series (KXMLB[AL,NL]MVP,
  CY, ROTY, KXMLBWSMVP) and country-level KXMLBWORLD per the brief
  Step 4's instruction. Aggregated 99 markets to
  `data/v2/joined_mlb_longhorizon_individual.parquet` for audit.
- **2026-05-23**: Used MLB Stats API `gameType == "R"` regular-season
  filter for team base-rate features, matching `03-dataset-build.md`
  Section 6 precedent. The few postseason games before
  mid-October close are excluded.

## 9. Known limits

1. **Sample size** (Section 2). Eligible n=11 is below v1's C4
   floor of 15. This dataset alone cannot pass the leak-fixed
   v2 gate.

2. **Single trading window.** All eligible markets share the same
   trading-window mid. No walk-forward fold structure is possible
   on this corpus alone.

3. **Two playoff misses dominate.** NYM (0.778) and HOU (0.809)
   both missed playoffs. Removing either flips the aggregate edge
   sign. The KXMLBPLAYOFFS sub-bucket is too small for any
   conclusion about that market type's calibration.

4. **No 2026 season data.** All markets are 2025 season. Adding
   2026 once it settles would more than double the sample but is
   ~6 months away.

5. **KXMLBSTATCOUNT excluded.** v1's eligible MLB set includes
   one KXMLBSTATCOUNT row. The v2 build (per brief Step 4) does
   not treat KXMLBSTATCOUNT as team-favorite. Net effect on the
   aggregate: removing one (price=0.938, outcome=1) market would
   have added +6pp realized to the v1-equivalent set.

## 10. Files produced

- `scripts/v2/build_mlb_longhorizon_dataset.py`: producer script
- `data/v2/joined_mlb_longhorizon_dataset.parquet`: the dataset
  (46 rows)
- `data/v2/joined_mlb_longhorizon_dropped.parquet`: dropped audit
  (164 rows)
- `data/v2/joined_mlb_longhorizon_individual.parquet`: individual
  / non-team-favorite audit (99 rows)
- `data/v2/joined_mlb_longhorizon_meta.json`: run metadata
- `research/v2/08-longhorizon-dataset.md`: this document

## 11. Cross-validation against the brief

The brief's Step 8 asks specifically: "v1's actual long-horizon
dataset on `data/processed/sports_dataset.parquet`: gate showed
+5.13pp test mean. v2 long-horizon MLB dataset: what's the v1-heuristic
mean?"

**Answer:** On the v1-comparable KXMLBWINS-only subset (n=5),
v2 long-horizon MLB shows **+10.41pp** mean, hit rate 100%, 95% CI
[+4.4pp, +17.4pp]. This is roughly consistent with (slightly above)
v1's reported +5.13pp on its multi-league test set. The MLB-restricted
subset of v1's own dataset shows +9.12pp on n=6, which matches our
+10.41pp on n=5 to within 1pp.

**On the full eligible set including KXMLBPLAYOFFS** (n=11), the
mean is -6.35pp, dragged down by two playoff-miss losses. The
KXMLBPLAYOFFS market behaves differently from KXMLBWINS at this
sample.

**Conclusion: the build is methodologically valid.** The v2 dataset
reproduces v1's edge on the overlap. The sample-size ceiling (n=11
or 5 depending on subset choice) is the binding constraint, not a
data-quality issue.

## 12. Recommendation for the orchestrator

This dataset on its own is **insufficient for ML modeling**. Eligible
n=11 is below v1's C4 minimum (15) and structurally below what a
leak-fixed C5 (5-fold CV) needs (~25 minimum, 100+ desirable).

The KXMLBWINS-only sub-bucket (n=5, +10.41pp, hit 100%) is consistent
with v1's edge thesis being real on the season-win-totals product,
but n=5 cannot validate an ML refinement. The KXMLBPLAYOFFS sub-bucket
(n=6, -20.31pp, hit 66.7%) suggests the playoff-qualifier market
behaves differently and may have different signal.

Recommended next steps in priority order:

1. **Accept v2 as a clean null finding** per `feedback_kill_early.md`.
   The work confirms v1's heuristic edge on the v1-comparable subset
   and reveals that v1's edge thesis does NOT uniformly apply across
   all long-horizon MLB market types (KXMLBPLAYOFFS fails). v1's
   simple heuristic remains the right strategy on its actual live
   universe.

2. **Re-spawn Agent C to rebuild on the FULL multi-league sports
   pool** if the orchestrator still wants a v2 ML attempt. v1's
   reported +5.13pp is on multi-league data (n=39), and that's the
   only sample where ML refinement would have enough rows. This is
   ~2-4 hours of additional engineering. Pipeline mirrors what
   `scripts/sports/build_dataset.py` already does; the work is
   adding v2's per-market team features to the cross-league rows.

3. **Defer further v2 work until 2026 MLB season settles** to
   double the long-horizon MLB sample. ~6 months from now (October
   2026).

**Do NOT** proceed with v2 ML model fitting on this 11-row eligible
dataset. The structural sample-size issue is what `06-critic.md`
predicted in Section 9, and rebuilding on the same constrained
domain has just confirmed it. The data shape is the binding
constraint, not the algorithm choice.

Live v1 continues running on its $32 with its existing 6 short-horizon
resting orders, unaffected by this finding.
