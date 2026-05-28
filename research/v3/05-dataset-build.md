# V3 Dataset Build (Phase 2, Agent V3-B1)

**Date:** 2026-05-24
**Agent:** V3-B1
**Inputs:** `data/v3/probe_inventory_eligible_with_team.parquet` (147 rows from V3-A)
**Outputs:** `data/v3/joined_v3_dataset.parquet`, `data/v3/v3_orthogonality_report.json`, `scripts/v3/build_v3_dataset.py`, this doc.
**Build time:** ~2s wall-clock (after one-time nflverse + MLB cache fill).

## Headline numbers

- **n_rows:** 147 (matches V3-A inventory exactly; no row drops).
- **Leak audit:** 0 violations across 147 rows.
- **Per-league feature-population rate:**
  - **NFL:** 101 / 104 = 97.1% feature-complete.
  - **MLB:** 15 / 16 = 93.75% feature-complete.
  - **NBA / NCAA / NHL:** 0% (no working AS-OF API for these leagues per V3-B audit).
- **Orthogonality verdict:** **1 of 12 candidate features retained** (`nfl_games_played_pre_t35d`). All team-stat features (NFL win pct, NFL Pythagorean, NFL recent-5 form, NFL point-diff, all MLB stats) dropped. The single retained feature is effectively a league-dummy + season-progress signal, not a true team-stat.
- **Single-entity sanity (S1):** max single-team share 6.80% (SEA, 10/147). Below the v2-COL artifact threshold of 30%. Top-5 share 26.5%. Matches V3-A inventory exactly post-build.
- **Train/test split shape (chrono 70/30):** train n=102, YES rate 96.08%; holdout n=45, YES rate 68.89%. **The training portion has only 4 NO outcomes**, all in MLB/NCAA. NFL training portion has zero NOs.

## 1. Build method

### 1.1 Sources

- **NFL:** `https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet`. This is the full historical NFL schedule with `gameday`, `game_id`, `home_team`, `away_team`, `home_score`, `away_score`, `game_type`. Cached to `data/v3/nflverse_cache/games.parquet`.
- **MLB:** `GET https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={year}&date={date}&standingsTypes=regularSeason` with `date` set to T-35d minus 1 day. Cached per (season, date) to `data/v3/mlb_stats_cache/standings_{season}_{date}.json`.
- **NBA / NCAA / NHL:** no working AS-OF API per V3-B's audit. Per the brief, we leave features NaN and document.

### 1.2 AS-OF rule (leak discipline)

For every external-feature query, we use the timestamp `t35d_minus1 = close_time - 35 days - 1 day` as the conservative AS-OF cutoff. This is strictly less than `close_time - 35 days` for every row.

- **NFL:** `games.parquet` filtered by `gameday < t35d_minus1.date()` (strict less-than on the date, so we never include a same-day game). Additionally restricted to `game_type == 'REG'` and to the season the close_time belongs to (NFL season Y = games played Sept-Dec of year Y + Jan-Feb of year Y+1; for close_time after July, we use close_time.year; for close_time in Jan-Feb (playoffs), we use close_time.year - 1).
- **MLB:** standings endpoint with `date=t35d_minus1.strftime('%Y-%m-%d')`. The MLB Stats API returns the standings as of end-of-day of that date, so a same-day late game is excluded by construction (we already subtracted 1 day from T-35d).

### 1.3 Feature derivations

Per-row, league-specific features are computed using ONLY data available at or before `t35d_minus1`.

NFL (from nflverse games.parquet filtered to season + `gameday < cutoff`):
- `nfl_w_pct_pre_t35d` = (wins + 0.5 * ties) / games_played
- `nfl_pyth_w_pct_pre_t35d` = (pts_for^2.37) / (pts_for^2.37 + pts_against^2.37), PFR exponent
- `nfl_recent5_w_pct` = wins-or-ties percentage over the most recent 5 played games
- `nfl_games_played_pre_t35d` = count of regular-season games already played (integer)
- `nfl_point_diff_per_game` = (pts_for - pts_against) / games_played

MLB (from standings endpoint):
- `mlb_w_pct_pre_t35d` = wins / gamesPlayed (from `leagueRecord`)
- `mlb_pyth_w_pct_pre_t35d` = (RS^1.83) / (RS^1.83 + RA^1.83), Bill James canonical exponent
- `mlb_games_back` = `gamesBack` as float (0.0 for division leader, where API returns '-')
- `mlb_run_diff_per_game` = (runsScored - runsAllowed) / gamesPlayed
- `mlb_games_played_pre_t35d` = `gamesPlayed` (integer)

Kalshi team-code mapping: Kalshi uses `JAC` for Jacksonville Jaguars but nflverse uses `JAX`. The build script maps `JAC -> JAX` before the nflverse query.

### 1.4 Output schema

`data/v3/joined_v3_dataset.parquet` (147 rows x 26 cols):

```
ticker, series_ticker, event_ticker, team, league, group, season_year,
open_time, close_time, t35d_time, lifetime_days, season_month,
favorite_price, outcome,
nfl_w_pct_pre_t35d, nfl_pyth_w_pct_pre_t35d, nfl_recent5_w_pct,
nfl_games_played_pre_t35d, nfl_point_diff_per_game,
mlb_w_pct_pre_t35d, mlb_pyth_w_pct_pre_t35d, mlb_games_back,
mlb_run_diff_per_game, mlb_games_played_pre_t35d,
feature_complete, coverage_note
```

`feature_complete` is True iff the league-relevant features are all observed for that row. `coverage_note` flags rows with NaN features and the reason.

The dataset is sorted chronologically by `close_time` ASC, so downstream walk-forward CV can simply slice contiguously.

## 2. Per-league feature coverage

| League | n rows | feature_complete (n) | feature_complete (rate) | coverage_note distribution |
|---|---:|---:|---:|---|
| NFL | 104 | 101 | 97.1% | 3 rows pre-season T-35d (IND week-1, SEA week-1, IND week-2) |
| MLB | 16 | 15 | 93.75% | 1 row mlb_awards (TSKU, an award initialism, no team) |
| NBA | 17 | 0 | 0% | All 17 marked `NO_AS_OF_API_FOR_LEAGUE_NBA` |
| NCAA | 8 | 0 | 0% | All 8 marked `NO_AS_OF_API_FOR_LEAGUE_NCAA` |
| NHL | 2 | 0 | 0% | Both marked `NO_AS_OF_API_FOR_LEAGUE_NHL` |
| **Total** | **147** | **116** | **78.9%** | |

Per the brief, the NBA/NCAA/NHL gaps are documented, not papered over: V3-B's audit Section 1.3 noted ESPN team-by-season is the only candidate and that its FPI endpoint 404'd on the obvious paths. Building a custom ESPN AS-OF feature is out of the time budget for this phase. The downstream V3-B2 model agent will have to either (a) train NFL+MLB-only (n=120 with features), (b) treat the NaN-feature rows as a "league effect" indicator only, or (c) drop NaN-feature rows from training and document the smaller effective n.

The 3 NFL no-feature rows are NOT bugs: they have `t35d_time` BEFORE the 2025 NFL season opener (2025-09-04). Specifically:
- KXNFLWINS-IND-25B-T3 closes 2025-10-07, T-35d = 2025-09-02 (pre-season)
- KXNFLWINS-IND-25B-T4 closes 2025-10-13, T-35d = 2025-09-08 (one day after IND's week-1 game, but the strict-less-than filter excludes 9-07 itself)
- KXNFLWINS-SEA-25B-T3 closes 2025-10-13, T-35d = 2025-09-08 (same situation for SEA)

For these rows, the AS-OF correctly returns 0 games played. This is the leak-safe behavior the brief specifies.

The 1 MLB no-feature row is `KXMLBALCY` (Cy Young Award; team field is `TSKU`, a player initialism not a team). Award markets are out of scope for team-stat features.

## 3. Orthogonality results

The protocol from V3-B audit Section "Orthogonality check protocol" was applied to 12 candidate features against the baseline `LogReg(outcome ~ favorite_price)` on the chronologically-earliest 70% (n_train = 102, period 2025-09-17 to 2025-12-22).

**Baseline (price-only) train AUC: 0.7270.**

Per-feature results (5000 bootstrap resamples, seed=42, retain rule: CI excludes zero AND AUC delta >= 0.005):

| Feature | n_train (with feat) | Coef CI on X_resid | AUC delta | Decision |
|---|---:|---|---:|---|
| lifetime_days | 102 | [-0.024, +0.010] | -0.059 | drop |
| season_month | 102 | [-0.182, +1.483] | +0.074 | drop (CI includes 0) |
| nfl_w_pct_pre_t35d | 75 | failed (single-class subsamples) | failed | drop |
| nfl_pyth_w_pct_pre_t35d | 75 | failed | failed | drop |
| nfl_recent5_w_pct | 75 | failed | failed | drop |
| nfl_point_diff_per_game | 75 | failed | failed | drop |
| nfl_games_played_pre_t35d | 102 | [+0.145, +0.602] | +0.224 | **retain** |
| mlb_w_pct_pre_t35d | 15 | [-0.102, +0.028] | +0.051 | drop (CI includes 0) |
| mlb_pyth_w_pct_pre_t35d | 15 | [-0.082, +0.081] | +0.051 | drop (CI includes 0) |
| mlb_run_diff_per_game | 15 | [-0.495, +0.597] | -0.033 | drop |
| mlb_games_back | 15 | [-0.068, +0.453] | -0.116 | drop |
| mlb_games_played_pre_t35d | 102 | [-0.027, +0.001] | +0.186 | drop (CI includes 0) |

### 3.1 Why the NFL team-stat block failed orthogonality

The chronologically-earliest 70% spans 2025-09-17 to 2025-12-22. Within this window, the NFL training rows (78 rows) have **100% YES outcomes** because the NFL win-total markets that close in October/November are settled by favorites who, in this sample, all hit their thresholds. The NFL losers concentrate in late-December and January markets, which sit in the holdout.

Because the NFL training subset has zero outcome variance, every bootstrap resample of NFL-feature-observed rows produces a one-class y vector. `LogisticRegression.fit` rejects single-class inputs. The protocol therefore registers "drop, too few successful bootstraps" for every NFL team-stat feature. **This is a faithful protocol output, not a code bug.** No reasonable orthogonality test can find independent signal in a feature whose target has no variance in the test window.

### 3.2 Why `nfl_games_played_pre_t35d` retained

`nfl_games_played_pre_t35d` is zero for all non-NFL rows (MLB and NCAA) and ranges 0-11 for NFL rows. It therefore acts as a near-perfect proxy for `is_NFL AND season_progressed`. The 4 NO outcomes in the train set are 3 MLB (out of 16 MLB train rows) and 1 NCAA (out of 8 NCAA train rows). NFL is 78/78 YES. The coefficient on `nfl_games_played_pre_t35d` reflects this **league effect**: rows with games-played > 0 (= NFL after week 1) hit YES; rows with games-played == 0 (= non-NFL, in this sample) hit YES less often.

This is correctly identified as "signal beyond price" by the orthogonality protocol, but the SOURCE of the signal is the league composition of the train set, not team strength. **The feature is effectively a "league=NFL during football season" dummy.** V3-B2's model agent should be aware that retaining this feature means the model is anchoring on "is this an NFL win-total market in the regular-season run-up", not on a team's actual record.

### 3.3 Why MLB features all failed

Only 16 MLB rows total; 15 with features observed (1 mlb_awards row excluded). Of those 15, only 13 fall in the chronologically-earliest 70% (n_train_with_feature = 15 in the report because the cutoff was applied per-row not per-league; verified the report's "n=15" for MLB features means 15 of 16 MLB rows with the feature observed, of which all happen to be in train_full because MLB markets close in Sept/Oct, well before the 2025-12-22 train/test split cutoff). With only 13 effective rows and 3 NOs, the bootstrap CI for any of these features is wide enough to include zero. The MLB pool is too small to honestly support a team-stat feature in this orthogonality check.

### 3.4 Why `lifetime_days` and `season_month` failed

Both are pure metadata, not team-stat features. They were included in the candidate set as "free" sanity checks. Neither showed independent signal:
- `lifetime_days` CI: [-0.024, +0.010], spans zero. AUC delta -0.059 (hurts the model).
- `season_month`: CI [-0.182, +1.483], spans zero. AUC delta +0.074 looks promising but the CI inclusion of zero means the apparent improvement is bootstrap noise.

Note: `season_month` survives strict literal-AUC-delta but not the CI test. Per protocol, both must pass; protocol drops it.

## 4. Final feature set passed to V3-B2

**Feature set: `{favorite_price, nfl_games_played_pre_t35d}`.**

That is the price feature plus a single retained orthogonality survivor, which is effectively a league + season-progress indicator rather than a true team-stat feature.

In practical terms, V3-B2 has TWO honest paths:

**Path A: Use the protocol-survivors as-is.** Train `LogReg(outcome ~ favorite_price + nfl_games_played_pre_t35d)` and evaluate on the gate. The model will essentially be a price-only model with a small league/season-progress adjustment. The result will almost certainly be a null finding because the feature does not carry true team-stat information.

**Path B: Acknowledge the data shape rejection.** The 70/30 chronological split has only 4 NO outcomes in train; NFL features cannot be honestly orthogonality-tested at this sample size and split. Document this as the dataset-stage null and skip the modeling step. Per the brief's "Final note": "If the orthogonality check drops ALL candidate features ... THAT IS A LEGITIMATE FINDING. Document it as 'v3 dataset cannot support an ML model that improves on price-only baseline' and write a clean null-conclusion section."

V3-B1 recommends Path B as the honest interpretation. The "retained" feature is structurally a league dummy, not a team-stat signal. V3-B2 may still run Path A for completeness so the gate is exercised, but the result is foreshadowed.

## 5. Leak audit

The build script enforces leak discipline by construction:
- All external-feature queries use `t35d_time - 1 day` as the AS-OF cutoff.
- nflverse rows filtered by strict `gameday < cutoff_date.date()`.
- MLB Stats API `date=` parameter set to that same cutoff.

Post-build assertion (in `leak_audit()` in the build script):
- For every NFL row, if `t35d < season_start (Sept 1)` then `nfl_games_played_pre_t35d` must be 0. Verified: 0 violations.
- For every MLB row, if `t35d < season_start (Mar 15)` then `mlb_games_played_pre_t35d` must be 0. Verified: 0 violations.

Result: **0 violations across 147 rows.** The audit JSON contains the per-row check trail.

A second informal check: for the 3 NFL "pre-season" rows (close_time 2025-10-07 / 2025-10-13), the AS-OF cutoff falls before/very-close-to 2025-09-04 (NFL week-1 start). The build correctly returns `games_played = 0`, not synthetic data. This is the AS-OF semantics the brief specifies.

The MLB cache directory `data/v3/mlb_stats_cache/` was populated with 2 standings JSON files (one for the 2025-08-12 AS-OF cutoff, one for the 2025-08-26 AS-OF cutoff; the 16 MLB rows all have T-35d in this Sep-2025 window).

## 6. Single-entity sanity check (S1)

Top 5 teams in the dataset:

| Rank | Team | n | share |
|---:|---|---:|---:|
| 1 | SEA | 10 | 6.80% |
| 2 | IND | 9 | 6.12% |
| 3 | DEN | 8 | 5.44% |
| 4 | HOU | 6 | 4.08% |
| 5 | NE | 6 | 4.08% |

Top-5 share 26.5%. Matches V3-A inventory exactly. **Well below the 30% v2-COL-artifact threshold.** The model agent's S1 check (drop the top team, verify holdout mean stays > 0) should be trivially clean on this dataset.

## 7. Files written

- `data/v3/joined_v3_dataset.parquet` (147 rows, 26 cols, sorted by close_time ASC)
- `data/v3/v3_orthogonality_report.json` (per-feature bootstrap CI, decisions, league-breakdown diagnostic)
- `data/v3/mlb_stats_cache/standings_2025_2025-08-12.json`
- `data/v3/mlb_stats_cache/standings_2025_2025-08-26.json`
- `data/v3/nflverse_cache/games.parquet` (full nflverse historical schedule cache)
- `scripts/v3/build_v3_dataset.py` (the build script; reproducible via `uv run python -m scripts.v3.build_v3_dataset`)
- This research doc: `research/v3/05-dataset-build.md`

Reproducibility note: re-running the script with the cache present takes ~2s. With cold cache, nflverse parquet download is ~1s and MLB standings calls (2 distinct AS-OF dates) total ~0.3s. The build is deterministic.

## 8. Findings for V3-B2 model agent

1. **n=147, train_n=102, test_n=45.** Train YES rate 96.08%, test YES rate 68.89%. Train has 4 NO outcomes (3 MLB + 1 NCAA). The chronological 70/30 split puts most outcome variance in the holdout.

2. **One feature retained** (`nfl_games_played_pre_t35d`), and it is effectively a league dummy rather than a team-stat. The model agent should NOT interpret this as "v3 team-stat features add signal."

3. **NBA, NCAA, NHL rows have NO features.** That is 27 of 147 rows (18.4%). The model agent must either (a) drop them from training, (b) train one model per league subset, or (c) tolerate NaN inputs (sklearn LogReg does not).

4. **The favorite_price feature is the only honest feature.** The gate evaluation should be on `LogReg(outcome ~ favorite_price + nfl_games_played_pre_t35d)` vs `LogReg(outcome ~ favorite_price)` vs v1's flat-prior heuristic.

5. **C6 expectation is bleak.** Per V3-D literature, free-public-feature sports models top out at +1-3pp lift. Here we have one effective feature that is structurally not a team-stat. The most likely C6 outcome is fail; the most likely overall verdict is "null finding, v1 confirmed."

6. **Per brief Section 'Final note':** "If only 1-2 features survive orthogonality, document that and proceed; the model agent will see a thin feature set and produce a small model. That's fine." V3-B1 endorses this interpretation. The dataset is honestly built; the orthogonality result is honestly reported. V3-B2 has a thin but clean feature set to model with.

## 9. v2 failure mode internalization (per brief)

| v2 failure mode | v3 dataset stage status |
|---|---|
| C5 in-sample leak | not applicable at dataset stage; dataset is chronologically sorted so V3-B2's per-fold retraining will be honest |
| Feature look-ahead | leak audit passed 0 violations across 147 rows; all external queries strictly AS-OF at t35d_minus1 |
| Model anchors on price | proactively addressed by orthogonality check; result is that all candidate team-stat features were dropped before training, so the model agent literally cannot use them to fool itself |
| Single-entity artifact | max share 6.80% (SEA); below 30% v2-COL threshold |
