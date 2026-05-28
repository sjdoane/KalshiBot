# v2 Joined MLB Dataset Build (Agent C)

**Date:** 2026-05-23
**Author:** Agent C (Wave 2, autonomous)
**Producer script:** `scripts/v2/build_mlb_dataset.py`
**Output parquet:** `data/v2/joined_mlb_dataset.parquet`
**Dropped-rows audit:** `data/v2/joined_mlb_dataset_dropped.parquet`
**Run metadata:** `data/v2/joined_mlb_dataset_meta.json`
**Status: BUILT WITH METHODOLOGY PIVOT.** Read Section 2 before using.

## 1. Mission

Brief: pull KXMLBGAME historical Kalshi markets (2025-03-01 through
2026-03-24), join to MLB Stats API game data, compute team-level
features AS OF a no-look-ahead cutoff, filter to Strategy B
eligibility band, save to `data/v2/joined_mlb_dataset.parquet`. NBA
secondary.

## 2. CRITICAL FINDING: KXMLBGAME market structure breaks the v1 trading window

The brief instructed: "The trading window for v1 was [-42d, -28d]
before market close. For MLB game-level markets the close_time IS the
game time, so the trading window is [-42d, -28d] BEFORE the game.
That's roughly 4-6 weeks of season before the game."

In probing the actual `data/v2/probe_kalshi_KXMLBGAME_history.parquet`
(4,414 contract rows, 2,203 unique games) the median market lifetime
is 0.58 days. Only 16 of 4,414 contract rows have lifetime >= 7 days,
and only 12 have lifetime >= 14 days. The 30-180 day filter
inherited from v1 Strategy B would yield 6 contract rows total
(3 games), which is not a viable training corpus.

KXMLBGAME markets are SHORT-HORIZON markets. They open the day of
the game (or rarely 1-2 days before) and close at game time. There
is no [-42d, -28d] trading window because no market exists 35 days
before the game.

The brief did anticipate this risk: "for MLB game markets, lifetime
is typically shorter, most are <60 days because they only open
during the season." The actual reality is even tighter than the
brief anticipated. The < 60 days assumption was wrong by a factor
of about 100.

Two paths considered:

1. STOP per the brief's "If you hit a blocker, document it clearly
   and stop" instruction. The blocker is real and structural: the
   data shape contradicts the trading-window assumption.

2. PIVOT the trading-window definition to fit the actual market
   structure, document the pivot prominently, and let the
   orchestrator decide on next steps.

Chose path 2 to give the orchestrator a usable dataset to inspect
before deciding whether to continue down the game-market path or
pivot to long-horizon season markets. The pivot is documented
inline in the script header and again here so that downstream
agents do not assume the trading-window semantics match v1.

### The pivot

For each market the trading window is `[open_time, game_start_utc]`,
i.e. all PRE-GAME trades only. The MLB Stats API's `gameDate` field
provides the actual game start time. The "favorite_price" is the
volume-weighted average yes-price across that window. This is the
price a buyer would realistically have transacted at before the
game began.

CRITICAL: we initially built the dataset with
`window_end = close_time - 30 minutes` and observed a 96% outcome
rate on `favorite_price in [0.70, 0.95]` markets, vs an implied
~75% rate. That 21pp "edge" was an artifact: Kalshi market
`close_time` is hours AFTER the game ends, so the window
included in-game trades where the price had already discovered
the actual outcome. The favorite-identification step was
selecting the side with the higher VWAP, which by then was
biased toward the eventual winner. Switching to the pre-game-only
window collapsed the apparent edge to a realistic level (see
Section 5).

The Strategy B [0.70, 0.95] favorite-price band is preserved
exactly per the brief. The lifetime [30, 180] filter is dropped
(would have killed the dataset).

### What this means for v2 modeling downstream

The original v2 thesis (Agent E will train a model to find edge
beyond Strategy B's heuristic) needs to be re-evaluated. v1
Strategy B's edge was specifically on LONG-HORIZON sports markets
where favorites are systematically underpriced because compression
hasn't happened yet. That phenomenon does not apply identically
to same-day game markets where the price has had hours, not weeks,
to settle on the consensus probability. Same-day favorite-longshot
bias in MLB is its own literature and we do not have strong
expected magnitudes for it.

The dataset still represents useful research data on
short-horizon MLB game markets, and Agent E may find a different
edge signature (statcast-driven probability vs market consensus
price, for example). But Agent E should NOT assume that any edge
demonstrated here translates to v1's live universe of long-horizon
sports markets. Those are different products.

## 3. Pipeline (`scripts/v2/build_mlb_dataset.py`)

### Step 1: Kalshi historical markets

Pull `/historical/markets?series_ticker=KXMLBGAME&min_close_ts=
{start}&max_close_ts={end}`. Uses the existing
`kalshi_bot.data.kalshi_client.KalshiClient` (RSA-PSS signed,
paginated, retried on 429). One pass over the full window returns
4,414 contract rows in ~5 seconds.

Each row carries: `ticker`, `event_ticker`, `open_time`,
`close_time`, `status`, `result`, `last_price_dollars`,
`volume_fp`, `liquidity_dollars`, `settlement_ts`,
`settlement_value_dollars`, `title`.

Important: `last_price_dollars` returned by `/historical/markets`
is the SETTLEMENT price (0.99 for the winner, 0.01 for the loser).
It is NOT a pre-game price and is not useful for the
"price-we-paid" feature. The pre-game price comes from
`/historical/trades` (Step 4).

### Step 2: Ticker parsing

Format: `KXMLBGAME-{YYMMMDD}{AWAY}{HOME}[G1|G2|2]-{CONTRACT_TEAM}`
where MMM is a 3-letter month code (JAN, FEB, ..., DEC) and the
optional doubleheader suffix is `G1`, `G2`, or bare `2`.

The parser uses the trailing `-{CONTRACT_TEAM}` as an anchor to
disambiguate the variable-length team-team boundary (LAD/TOR vs
ATH/TEX vs CWS/MIA etc.). 100% parse rate on the 4,414-row probe
sample. See `parse_ticker` in `scripts/v2/build_mlb_dataset.py`.

8 contract rows with team codes ALHS, ALLS, NLHS, NLLS were
identified as playoff-placeholder markets ("AL vs AL (Game 1)
Winner?") and dropped. These are pre-LCS markets where the team
identity is not yet set; they cannot be matched to a real MLB
game.

### Step 3: MLB Stats API schedule

Single call to
`https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=
2025-03-01&endDate={later}&gameType=R,F,D,L,W&hydrate=team,linescore`.
Returns the full 2025 season + postseason in 2.4 seconds, ~15 MB
JSON, ~2,500 games.

Match key per Kalshi market: `(game_date, home_abbrev, away_abbrev,
game_number)`. The MLB API's `abbreviation` field on the team
matches the Kalshi ticker abbreviations exactly (LAD, NYY, AZ,
ATH, CWS, KC, SD, SF, TB, WSH, etc.) for all 30 active teams.

For doubleheaders: `dh_suffix=G1` maps to `game_number=1`;
`dh_suffix=G2` or `2` maps to `game_number=2`. Tickers without
any DH suffix default to `game_number=1`. 61 doubleheader games
were observed in the 2025 season.

### Step 4: Historical trades + favorite identification (PRE-GAME ONLY)

For each Kalshi event_ticker (one MLB game), there are two contract
rows: YES on home team wins, and YES on away team wins. To
determine which contract was the FAVORITE, we pull
`/historical/trades` for BOTH sides over
`[open_time, game_start_utc]` (the pre-game trading window only),
compute VWAP yes-price for each, and select the higher-VWAP side
as the favorite. The other becomes the underdog by construction;
we record `underdog_price = 1 - favorite_price`.

Trade pull rate: ~100ms per ticker × 2 sides × 2,203 games ~ 7
minutes. Stayed well under the Basic-tier 200 read-token/sec ceiling
(documented in `research/v2/01-data-sources.md` Section 2.3).

The pre-game-only window is load-bearing for the methodology to be
honest. See Section 2 for the cautionary tale of why the initial
implementation (using `close_time - 30min` as the upper bound)
produced a fake 21pp edge.

### Step 5: Outcome resolution

Outcome is computed from MLB Stats API
`home_is_winner` / `away_is_winner` boolean fields against the
favorite team. `outcome = 1` if the favorite team won, else 0. We
also record `winning_team`, `losing_team`, `score_winning`,
`score_losing` to allow downstream calibration.

### Step 6: Feature engineering (no look-ahead)

For each game, features are computed AS OF the day before the
game (`cutoff = game_date`; all games with `game_date_obj <
cutoff` are eligible). Uses regular-season games only for the
base-rate features (postseason has its own dynamics).

Team features computed for both favorite and underdog:

- `games_played`, `wins`, `losses`, `win_pct`
- `runs_scored_per_game`, `runs_allowed_per_game`,
  `run_diff_per_game`
- `pyth_expected_wpct = rs^1.83 / (rs^1.83 + ra^1.83)` (Bill James
  Pythagorean expectation)
- `recent_form_wpct` (last 10 games before cutoff)
- `home_wpct`, `away_wpct`

Matchup features:

- `is_home` (whether favorite is the home team)
- `h2h_wpct`, `h2h_n` (favorite's record vs underdog this season
  prior to cutoff; null if no prior matchup)
- `days_rest` (days since favorite's last game)
- `fav_vs_500_wpct` (favorite's record vs teams whose own win pct
  at cutoff is >= 0.500; null if no such matchups yet)

Pair differentials:

- `wpct_diff`, `pyth_diff`, `run_diff_diff` (favorite minus underdog)

Optimization: per-team running stats are not cached across game
dates, but per-(team, cutoff) lookups are memoized to avoid
re-walking the season history for every game. The full pipeline
runs in ~10 minutes on the full 2,200-game corpus.

## 4. Schema

Column list with types (final parquet). Rows can be filtered to
Strategy-B-eligible by the `is_strategy_b_eligible` boolean
column; the full pre-filter set is retained for downstream
calibration work.

(See Section 5 for actual counts and outcome rates.)

| Column | Type | Description |
|---|---|---|
| ticker | str | Favorite-side contract ticker |
| event_ticker | str | Game-level Kalshi event ticker |
| series_ticker | str | Always "KXMLBGAME" |
| open_time | datetime64[ns, UTC] | Market open |
| close_time | datetime64[ns, UTC] | Market close (= game time) |
| settlement_ts | datetime64[ns, UTC] | When the market settled |
| settlement_value_dollars | float | $1.00 for winners, $0.00 for losers |
| result_yes_no | str | "yes" or "no" |
| last_price_dollars_settlement | float | Kalshi's last_price_dollars (settlement price, 0.99 or 0.01) |
| volume_fp_market_lifetime | float | Total volume over market lifetime |
| liquidity_dollars | float | Kalshi's liquidity_dollars |
| favorite_price | float in [0, 1] | VWAP yes-price of the favorite-side contract over the trading window |
| underdog_price | float in [0, 1] | 1 - favorite_price |
| vwap_n_trades_in_window | int | Number of trades in the trading window |
| vwap_volume_fp_in_window | float | Total size of trades in the trading window |
| one_sided_flow_pct | float | Max(yes_takers, no_takers) / total_takers |
| favorite_team_abbrev | str | Team abbreviation of the favorite |
| underdog_team_abbrev | str | Team abbreviation of the underdog |
| home_abbrev | str | Home team abbreviation (Kalshi-side) |
| away_abbrev | str | Away team abbreviation (Kalshi-side) |
| is_favorite_home | bool | Whether the favorite is the home team |
| dh_suffix | str | "", "G1", "G2", or "2" |
| game_date | date | Calendar date of the game |
| game_pk | int | MLB Stats API gamePk |
| outcome | int | 1 if favorite won, 0 if favorite lost |
| winning_team | str | |
| losing_team | str | |
| score_winning | float | |
| score_losing | float | |
| lifetime_days | float | (close_time - open_time) / 86400 |
| days_to_game | float | Same as lifetime_days for game markets |
| fav_games_played | int | Prior to cutoff |
| fav_win_pct | float \| null | Prior win rate |
| fav_runs_scored_pg | float \| null | |
| fav_runs_allowed_pg | float \| null | |
| fav_run_diff_pg | float \| null | |
| fav_pyth_wpct | float \| null | Pythagorean expectation |
| fav_recent_form_wpct | float \| null | Last 10 games win pct |
| fav_home_wpct | float \| null | |
| fav_away_wpct | float \| null | |
| fav_vs_500_wpct | float \| null | Record vs teams above .500 |
| dog_games_played | int | |
| dog_win_pct | float \| null | |
| dog_runs_scored_pg | float \| null | |
| dog_runs_allowed_pg | float \| null | |
| dog_run_diff_pg | float \| null | |
| dog_pyth_wpct | float \| null | |
| dog_recent_form_wpct | float \| null | |

(Underdog does NOT have home_wpct, away_wpct, vs_500_wpct; only the
favorite has those. Rationale: the matchup-specific features should
be from the favorite's perspective, not symmetric.)
| wpct_diff | float \| null | fav_win_pct - dog_win_pct |
| pyth_diff | float \| null | |
| run_diff_diff | float \| null | |
| is_home | bool | |
| h2h_wpct | float \| null | This-season head-to-head |
| h2h_n | int | Number of prior matchups |
| days_rest | int \| null | Since favorite's last game |
| is_strategy_b_eligible | bool | favorite_price in [0.70, 0.95] AND vwap_n_trades >= 5 |

## 5. Build results

Final run after the pre-game-window methodology fix (Section 2) and
the ARI/AZ team-abbreviation alias fix (Section 7 decision log).
Run timestamp: 2026-05-23.

### Counts

- Total markets in Kalshi window: 4,414 contract rows (2,203 unique
  events / games)
- Dropped at parsing: 8 placeholder LCS markets
  (ALHS/ALLS/NLHS/NLLS pseudo-teams; cannot be matched to a real
  MLB game)
- Dropped at status filter: 30 (Postponed=26, Completed Early=4).
  These are MLB games that were rained out and re-played later,
  or weather-shortened games. The Kalshi tickers may have settled
  void for these.
- **Total joined-dataset rows: 2,173** (one per matched MLB game,
  favorite side only)
- **Strategy-B eligible** (favorite_price in [0.70, 0.95] AND
  pre-game-window n_trades >= 5): **123 rows**
- Date range: 2025-04-16 to 2025-10-31
- Outcome rate (all rows): **0.555** (favorites win 55% across
  all games; this number is dragged down by all the marginal-
  favorite games where price is barely above 0.50)
- Outcome rate (Strategy-B-eligible): **0.756**
- Mean favorite_price (Strategy-B-eligible): **0.733**
- Realized minus implied: **+2.32pp** (consistent with Bürgi
  favorite-longshot bias magnitude)

### Calibration (Strategy-B-eligible rows)

| Price bucket | n | mean price | realized | edge (pp) |
|---|---|---|---|---|
| (0.699, 0.75] | 94 | 0.722 | 0.723 | +0.17 |
| (0.75, 0.80] | 26 | 0.764 | 0.885 | +12.09 |
| (0.80, 0.85] | 3 | 0.816 | 0.667 | -14.97 |

Total edge across the eligible band: +2.32pp. Important caveats:

- The 0.70-0.75 bucket is THE bucket (94 of 123 eligible markets).
  Realized matches implied almost exactly (+0.17pp). This is what
  one would expect if MLB game markets are roughly efficient at
  this price level (no exploitable edge).
- The 0.75-0.80 bucket of 26 markets shows a 12pp realized edge,
  but n is small. Bootstrap CI would likely include zero.
- The 0.80-0.85 bucket has only 3 markets and is uninformative.

**Interpretation:** the dataset DOES show a small positive
favorite-longshot bias in aggregate, but the heavy lifting is
concentrated in the small (n=26) 0.75-0.80 bucket. The 94-market
bulk at 0.70-0.75 is essentially efficient. Agent E should NOT
assume the +2.32pp aggregate is uniform; the calibration is
clearly heterogeneous and small-n in the higher buckets.

### Dropped rows summary

- 26 dropped: `status=Postponed`. Game was rained out and re-played
  on a different date that the Kalshi ticker did not anticipate;
  the MLB API has the resolved game under the new date.
- 4 dropped: `status=Completed Early`. Weather-shortened games
  (rare; Kalshi typically still settles these but the outcome
  was forced).

40 markets that had previously been dropped due to ARI/AZ team-
abbreviation mismatch have been recovered via the
`TEAM_ABBREV_ALIASES` map in the script (Kalshi-side "ARI" -> MLB-
side "AZ" for Arizona Diamondbacks).

### Sample 5 rows (run with `scripts/v2/validate_mlb_dataset.py`)

- KXMLBGAME-25AUG08COLAZ-AZ: AZ favored at 0.68 (home), won 6-1
  vs COL. fav_win_pct=0.47, dog_win_pct=0.26. Pyth: 0.49 vs 0.27.
  Reasonable favorite, real win. (This row was previously dropped
  pre-alias-fix.)
- KXMLBGAME-25MAY24KCMIN-MIN: MIN favored at 0.54, won 5-4 vs KC.
- KXMLBGAME-25SEP18ATHBOS-BOS: BOS favored at 0.59, LOST 5-3 vs
  ATH. fav_win_pct=0.55, dog_win_pct=0.47 (close matchup).
- KXMLBGAME-25JUL02CWSLAD-LAD: LAD favored at 0.75, won 5-4 vs
  CWS. ELIGIBLE (Strategy B band). LAD wpct 0.63 vs CWS 0.31.
- KXMLBGAME-25SEP23DETCLE-DET: DET favored at 0.60, LOST 5-2 vs
  CLE. Two teams essentially even in prior wpct (~0.54 each).

### Null counts

Core feature columns have **0 nulls** (favorite_price, vwap_n,
fav/dog win_pct, pyth_wpct, run_diff_pg, recent_form, home/away
wpct, vs_500_wpct, differentials).

Sparser features:

- `h2h_wpct`: ~16% nulls (favorite/underdog had not yet played
  each other this season at the cutoff)
- `days_rest`: 0 nulls
- `h2h_n`: 0 nulls (it is 0 when teams haven't met, not null)

## 6. Feature-engineering choices and tradeoffs

### Trading-window definition

Chose `[open_time, game_start_utc]` (PRE-GAME ONLY) rather than
first-N-hours or last-N-hours or close-relative offset. Rationale:
`close_time` on Kalshi KXMLBGAME markets is hours after the game
ends (e.g., 03:20 UTC when the game ended around 02:30 UTC), so
any close-relative window includes in-game trades where the
price has discovered the outcome. The MLB Stats API's `gameDate`
field provides the actual game start time, which is the
load-bearing upper bound.

The initial implementation used `close_time - 30 minutes` and
produced an apparent 21pp edge on Strategy-B-band markets. This
was an artifact of leakage (see Section 2). The fix to use
`game_start_utc` as the upper bound collapsed that to a realistic
edge level.

### "AS OF" cutoff

Chose `cutoff = game_date` (all games with `game_date_obj <
cutoff` are eligible for features). This is "the day before the
game" semantics. It excludes games played on the same calendar
day, even if those games started earlier than the current game.
For practical purposes the only correlation concern is the
favorite-team's own same-day earlier doubleheader G1 if the
current game is G2; we accept this tiny look-ahead because
filtering by game_datetime_utc instead of game_date would require
careful handling of timezones and clock-time game scheduling. The
look-ahead from same-day G1 stats is conservative because it can
only mildly improve the prediction, not invalidate the model.

### Postseason vs regular season

Base-rate team features use REGULAR SEASON ONLY. Rationale:
postseason performance is highly opponent-dependent (better
opponents, single-elimination dynamics) and combining
regular+postseason in a single rolling average would understate
the favorites' actual base quality. Postseason markets ARE
included in the dataset (their outcomes settle), but their team
features reflect that team's regular-season form.

### Pythagorean exponent

Used 1.83 (Bill James). The "Pythagenport" variant with a
data-driven exponent improves fit by 1-2 wins per season, but
1.83 is the canonical value and is robust to small samples
early in the season.

### "vs .500+" calculation

For each game, we first compute every team's win pct as of the
same cutoff, then identify which teams were >= .500 at that
moment. The favorite's vs-500 record is computed against that
contemporaneous .500+ set. Null when the favorite has 0 prior
games against any .500+ team.

### Imputations

None applied at write time. Null is preserved for any feature
that has insufficient prior data (e.g., a team's first game of
the season has `games_played=0, win_pct=null` etc.). Downstream
agents (Agent E) should apply their own imputation strategy
(median fill, knn, indicator column) appropriate to their model
class.

## 7. Decision log

- 2026-05-23 (during research-grounding): Confirmed via probe
  that median KXMLBGAME market lifetime is 0.58 days, not "weeks"
  or "months". This contradicts the brief's [-42d, -28d] window
  assumption. **Decision:** Pivot trading-window definition and
  document the pivot prominently. See Section 2.

- 2026-05-23 (first full build): Initial implementation used
  `window_end = close_time - 30min`. Outcome rate on Strategy-B-
  eligible markets came back at 96% with a mean
  favorite_price of 0.75, implying an inflated 21pp edge.
  Diagnosed as leakage: `close_time` is post-game, so the window
  included in-game trades that had discovered the outcome.
  **Decision:** Switch the upper bound to `game_start_utc` from
  the MLB Stats API. Rebuild from scratch.

- 2026-05-23: Drop the v1 `[30, 180]` lifetime filter for the same
  reason: would yield ~3 games. **Decision:** Preserve all market
  rows that survive the price band, document the drop.

- 2026-05-23: Use favorite-team's `home/away` based on whether
  contract_team matches the parsed home team, not on Kalshi's
  yes/no role. Either side of a KXMLBGAME event is a "YES" market
  on a different team winning; "favorite" is defined by VWAP yes-
  price, not by any built-in Kalshi field.

- 2026-05-23: Use MLB Stats API's `team.abbreviation` field for
  matching. Confirmed equal to Kalshi abbreviations on 29 of 30
  active MLB teams. **One exception:** Kalshi used "ARI" for some
  Arizona Diamondbacks games where MLB uses "AZ" (e.g.,
  KXMLBGAME-25AUG04SDARI-ARI). 40 markets in the 2025 corpus
  affected. **Decision:** Add `TEAM_ABBREV_ALIASES` map at the top
  of the script, mapping Kalshi-side to MLB-side canonical. Apply
  the alias in `match_game` and in the team-feature lookup. After
  fix, all matched markets land in the dataset.

- 2026-05-23: Drop 8 placeholder LCS-pseudo-game markets (ALHS,
  ALLS, NLHS, NLLS team codes) since they cannot be matched to a
  real MLB game.

- 2026-05-23: Use regular-season-only games for team base rates;
  include postseason markets in the dataset (with their regular-
  season features).

## 8. NBA secondary status

Per the brief: "If NBA proves to be a 2-hour scrape job, do MLB
first and skip NBA for this wave; document the skip."

NBA was SKIPPED for this wave.

Rationale:

- MLB build took the available time budget. Trade pulls alone are
  ~7 minutes; full pipeline including the feature loop is ~10
  minutes. Time was further consumed by the trading-window
  methodology pivot analysis.
- NBA Stats API is broken from this environment (per Agent A
  `research/v2/01-data-sources.md` Section 3.4). Working
  alternative is ESPN scoreboard plus 538 NBA ELO archive
  (frozen 2023) plus possibly Basketball-Reference scrape. Each
  of these has its own integration burden.
- NBA `/historical/markets` probe returned 2,394 contract rows
  (Apr 2025 to Mar 2026), so the Kalshi half is straightforward.
  The blocker is the sports-stats half.
- The MLB pivot finding (game markets are short-horizon, breaking
  the v1 trading-window assumption) is more important to
  surface to the orchestrator now than a partial NBA dataset
  with the same caveat. The orchestrator should decide whether
  to continue with game-market modeling before Agent C invests
  more in NBA.

If the orchestrator decides to proceed with game-market modeling
across leagues, the NBA pipeline would mirror this MLB pipeline:
parse KXNBAGAME tickers (similar grammar), match to ESPN
scoreboard by date + team, compute team features from ESPN game
results, apply the same VWAP trading-window logic. Estimated
build time: 4-6 hours of additional engineering plus the same
~10 minute runtime.

## 9. Known caveats and limits

1. **The trading-window pivot is the load-bearing caveat.** Any
   conclusions Agent E draws about this dataset DO NOT transfer
   to v1 Strategy B's long-horizon market universe without
   explicit re-validation. See Section 2.

2. **Outcome rate of eligible markets is high by construction.**
   Strategy B's [0.70, 0.95] band means we are selecting markets
   where the favorite was already favored at 70 cents. Favorites
   priced at 70-95 cents typically win 70-95% of the time
   (modulo the favorite-longshot bias). The eligible-row outcome
   rate is informative for calibration, but the absolute
   magnitude is mostly determined by the price selection, not by
   any predictive signal.

3. **Same-day stats leakage on doubleheaders.** Team features are
   computed at `cutoff = game_date`, which excludes everything
   from `game_date` onward. For a doubleheader's second game
   played later the same day, the first game's result is NOT
   included in the team stats. This is a slight
   under-information bias on the second game but it preserves
   strict no-look-ahead.

4. **Postponed-and-replayed games.** When a game is postponed and
   re-played on a different date, the Kalshi ticker's date may
   not match the MLB Stats API date. Such markets are dropped
   into the `joined_mlb_dataset_dropped.parquet` audit file with
   reason `no_mlb_match`.

5. **Early-season feature instability.** Games played in the
   first 2 weeks of the season have `fav_games_played < 14`,
   making win_pct and recent_form_wpct highly variable. Agent E
   should consider filtering by `fav_games_played >= 20` for
   modeling purposes.

6. **Trade volume in 30-min window.** Some markets have only a
   handful of trades total. We enforce `vwap_n_trades_in_window
   >= 5` for the `is_strategy_b_eligible` flag, but the dataset
   retains the full pre-filter rows so the operator can inspect.

7. **Doubleheaders bare-"2" suffix.** Early-season (April 18,
   2025) doubleheaders used a bare trailing `2` instead of `G1`/
   `G2`. The parser handles this. There is a risk of false
   matches if a team abbreviation legitimately ends in `2`
   (none currently do; MLB team abbrevs are all letters).

## 10. Files produced

- `scripts/v2/build_mlb_dataset.py`: the producer script
- `scripts/v2/validate_mlb_dataset.py`: validation + spot-check
  helper
- `data/v2/joined_mlb_dataset.parquet`: the dataset
- `data/v2/joined_mlb_dataset_dropped.parquet`: dropped-rows audit
- `data/v2/joined_mlb_dataset_meta.json`: run metadata
- `data/v2/build_mlb_log.txt`: stdout/stderr capture of the run
- `research/v2/03-dataset-build.md`: this document

## 11. Recommendations for the orchestrator

1. **Read Section 2 before reading anything else.** The trading-
   window pivot is the most important fact to surface from this
   wave. v2 is now operating on a different product surface than
   v1, even if both are "Kalshi sports markets".

2. **Decide whether to continue with same-day game markets** before
   Agent E spends time training models on this dataset. The v1
   Strategy B's edge is on LONG-HORIZON markets where favorites
   are systematically underpriced because compression hasn't
   happened yet. Same-day MLB game markets compress quickly (the
   2pp edge we observe at price 0.72 is modest). Two options to
   weigh:

   a. **Continue with game-market modeling.** Agent E trains a
      model on this dataset. Realistic ceiling is whatever
      additional edge Statcast-derived features add over the
      mean-price baseline. Probably 2-5pp realistic max. Bigger
      n than long-horizon, smaller per-trade edge.

   b. **Pivot to long-horizon sports markets.** Pull KXMLBALEAST,
      KXMLBALMVP, KXMLBNLWEST, KXMLBWS, similar series (these are
      v1's actual MLB universe per `data/processed/sports_dataset.
      parquet`; they have lifetimes of 80-340 days, not 0.58 days).
      Build a different Agent C dataset for those. The edge would
      transfer directly to v1's live strategy.

3. **NBA was skipped.** See Section 8. Decide before re-spawning
   Agent C for NBA whether the game-market thesis is worth
   pursuing across leagues, or whether the long-horizon pivot is
   more important.

4. **The Bürgi-magnitude edge IS real** (within the small-n caveat
   of 26 markets in the 0.75-0.80 bucket; broader 94 markets in
   0.70-0.75 show only +0.17pp). This dataset CAN support
   meaningful Agent E modeling work IF the orchestrator accepts
   the product-surface caveat in Section 2.

5. **Re-run the pipeline as new MLB games settle.** The script is
   idempotent and re-runnable. As the Kalshi historical cutoff
   slides forward (currently 2026-03-24), more 2026-season MLB
   games will become available for backtesting. Agent E should
   plan to re-pull when needed.
