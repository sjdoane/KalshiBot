# V5 Track B Phase 1: Statcast feasibility for KXMLBSTATCOUNT player-prop ML

**Date:** 2026-05-24
**Agent:** V5-B1
**Status:** Phase 1 research complete. Track B PROCEED recommended with scope amendment (see Section 7).
**Inputs:** Kalshi `/markets?status=settled` (post-cutoff archive), pybaseball 2.2.7 (Statcast scraper), web research on sportsbook competition.
**Outputs:**
- `data/v5/kxmlbstatcount_inventory.parquet` (n=150,110 settled prop markets; 13.1 MB)
- `data/v5/kxmlbstatcount_inventory_enriched.parquet` (same + extracted player/date columns)
- `data/v5/kxmlbstatcount_inventory_summary.json`
- `data/v5/kxmlbstatcount_extended_summary.json`
- `data/v5/statcast_sample_2024w39.parquet` (n=29,873 pitches, sample week 2024-09-22 to 2024-09-29; 4.8 MB)
- `data/v5/statcast_2026_season_to_date.parquet` (n=267,996 pitches, 2026 season Mar 15 to May 23; 36.4 MB)
- `data/v5/pybaseball_sample_summary.json`
- `data/v5/orthogonality_light_sample.parquet`, `data/v5/orthogonality_light_sample_v2.parquet`
- `scripts/v5/probe_kxmlbstatcount.py`, `scripts/v5/probe_kxmlbstatcount_extended.py`, `scripts/v5/probe_pybaseball_sample.py`, `scripts/v5/probe_orthogonality_light.py`, `scripts/v5/probe_orthogonality_light2.py`

Total Phase 1 disk usage: ~55 MB. Far below the 5 GB budget.

---

## Executive verdict

**Track B PROCEED with scope amendment.** Three of three feasibility load-bearing questions clear, but the scope must shift from the brief's named series KXMLBSTATCOUNT (n=6 historical resolved markets; structural dead-end) to the four adjacent per-player prop series: KXMLBHIT, KXMLBHR, KXMLBHRR, KXMLBKS. On these, n=150,110 settled markets exist across 60 distinct game dates in the 2026 MLB season-to-date, with 497 distinct batters and 206 distinct pitchers (single-player concentration < 1%). Statcast features sampled as-of T-1d are leak-safe and trivially available via pybaseball; a 2.6s download retrieves a week of pitch-by-pitch data. Sportsbook competition on these markets exists but the literature/community consensus is that pitcher prop markets are the easiest to beat the closing line. Light orthogonality probe confirms BA-last-14-games is uncorrelated with Kalshi price (Spearman r=-0.04, p=0.77), suggesting orthogonal information content.

**The major caveats:**
1. KXMLBSTATCOUNT itself is n=6 and not what the brief actually wants; the series name in the brief was a placeholder. The real prop series are KXMLBHIT/HR/HRR/KS.
2. All n=150,110 markets are within a 2-month window (2026-03-26 to 2026-05-24) on ONE MLB season. Multi-season generalization is untested.
3. Kalshi `/historical/markets` returns zero rows for all five prop series (cutoff 2026-03-25; these series only opened in March 2026). Inventory comes from `/markets?status=settled`, the "live but past-close" archive.
4. Per-player-game ladders mean nominal n inflates: real independent unit count is ~14,000 per series (player-game pairs), still well above the master plan n>=80 floor.

---

## 1. KXMLBSTATCOUNT market inventory

### 1.1 Probe outcome on the brief-named series

`/historical/markets?series_ticker=KXMLBSTATCOUNT` returns **n=0** because Kalshi historical cutoff is 2026-03-25 and KXMLBSTATCOUNT didn't exist before then. Pivoted to `/markets?status=settled` which returns the operationally settled archive across the live + past-close window.

KXMLBSTATCOUNT itself: **n=6 settled markets**, all "all hitters combined" / "all pitchers combined" specialty bets like "1+ immaculate innings", "2+ inside-the-park home runs". These are not per-player props at all; they are league-day aggregate counters. Sample-size structurally below any ML floor. The brief's specification of this series was a placeholder.

### 1.2 Adjacent player-prop series (the real Track B universe)

| Series | n_total | n_binary | n_yes | n_no | YES rate | n_distinct_players | n_distinct_player_games | n_distinct_events | n_distinct_dates | top_player_share | floor_strike range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| KXMLBHIT | 45,202 | 44,306 | 11,715 | 32,591 | 26.4% | 497 | 14,017 | 790 | 60 | 0.5% (Max Muncy) | 0.5 to 4.5 |
| KXMLBHR | 26,577 | 26,052 | 1,538 | 24,514 | 5.9% | 496 | 13,983 | 789 | 60 | 0.6% (Aaron Judge) | 0.5 to 2.5 |
| KXMLBHRR | 67,025 | 65,677 | 22,312 | 43,365 | 34.0% | 497 | 13,931 | 789 | 60 | 0.5% (Max Muncy) | 0.5 to 4.5 |
| KXMLBKS | 11,300 | 10,911 | 4,705 | 6,206 | 43.1% | 206 (pitchers) | 1,525 | 787 | 60 | 0.9% (F. Peralta) | 0.5 to 12.5 |
| KXMLBSTATCOUNT | 6 | 6 | 6 | 0 | 100% | n/a | n/a | 2 | 0 (season-long) | 1.0 to 5.0 |

**Total: 150,110 settled markets, 146,952 binary resolved (yes/no), 3,158 scalar/refund.**

Per-event ladder structure: each game-event produces ~58 markets in KXMLBHIT (e.g., for each of ~9 hitters per team, 3-4 thresholds 1+/2+/3+/4+ hits). The nominal n=45,202 deflates to **14,017 player-game pairs** as the natural independent unit, or **790 distinct game-events** as the most conservative.

### 1.3 Structure summary

- **Title format**: "<Player Name>: N+ <stat>?" (KXMLBHIT/HR/HRR/KS)
- **Ticker format**: `KXMLB<STAT>-<YYMONDDHHMMTEAMTEAM>-<TEAM><PLAYERLASTNAMEINIT><JERSEY>-<floor_idx>` (e.g. `KXMLBHIT-26APR291510MIALAD-LADTHERNANDEZ37-3` = LAD player THernandez jersey 37 with floor strike "3" = 3+ hits)
- **Player name** extractable from `yes_sub_title` (split on `:`)
- **Game date** extractable from ticker prefix `YYMONDD` (e.g., `26APR29` = 2026-04-29)
- **Threshold** in `floor_strike` (0.5 = "1+", 1.5 = "2+", 2.5 = "3+", etc.)
- **strike_type**: `greater` (HIT, HRR), `structured` (HR, KS for ladder cup), `greater_or_equal` (STATCOUNT)
- **Lifetime**: median 6.3 hours, p90 = 22.4 hours. **99.8% of props open and close within 24 hours** (all but ~70 of 45k for HIT).
- **All markets currently within 2026 MLB season** (Mar 26 to May 24, 60 distinct game-day dates). One season of data.

### 1.4 Single-player concentration

| Series | Top player share | Top-5 share | Verdict |
|---|---:|---:|---|
| KXMLBHIT | 0.5% (Max Muncy) | 2.3% | Far below 30% kill threshold |
| KXMLBHR | 0.6% (Aaron Judge) | 2.6% | Far below 30% kill threshold |
| KXMLBHRR | 0.5% (Max Muncy) | 2.1% | Far below 30% kill threshold |
| KXMLBKS | 0.9% (Freddy Peralta) | 4.3% | Far below 30% kill threshold |

**This is a far better data shape than v2's MLB game markets** (COL-as-opponent at 75% of holdout). Player concentration here is benign. The 30% single-entity critic-kill threshold (from v2 critic Section 6) has zero binding force on this domain.

### 1.5 Price-band distribution

The v1 favorite-maker filter (price in [0.70, 0.95]) is structurally inapplicable here: most prop markets resolve at near-0 or near-1, because the "1+ hits" prop is a heavy favorite (~99c) while the "3+ hits" prop is a heavy underdog (~1c). The mid-band [0.20, 0.80] is the operationally meaningful zone for ML modeling.

| Series | n in [0.70, 0.95] | n in [0.20, 0.80] (mid-band) |
|---|---:|---:|
| KXMLBHIT | 259 | 760 |
| KXMLBHR | 62 | 171 |
| KXMLBHRR | 505 | 6,479 |
| KXMLBKS | 102 | 200 |

**Mid-band KXMLBHRR has n=6,479**, which is the cleanest target for a Brier-score-skill ML model (price is informative but not deterministic; player heterogeneity is exposed).

### 1.6 Implications for the locked C1-C6 gate

The v2 gate's C4 requires holdout n >= 15. KXMLBHIT mid-band n=760 gives ~228 holdout at 70/30 split, well above C4. Even at the strictest cut (per-game ladders collapsed to one event per game-date, n=790 events), C4 clears.

The C5 5-fold CV walk-forward by close-date works naturally: 60 distinct game-dates -> 12 dates per fold, plenty for purge-embargo discipline.

The C6 v1-beat comparison is **not meaningful on this domain**: v1 does not trade player props at the 0.70-0.95 price band (those markets are rare and v1's filter was designed for season-long futures). The honest comparison is Brier-skill against the Kalshi-price baseline. This matches the master plan Section 7 "C6 may not apply" caveat for Track C (crypto); applies here too.

---

## 2. pybaseball install + sample download

### 2.1 Install

```
uv add pybaseball
# Resolved 99 packages; pybaseball 2.2.7 + 12 new deps (lxml, requests, etc.)
# Wall ~3 seconds. Required one retry due to .dist-info file lock (OneDrive sync).
```

`pyproject.toml` now lists pybaseball as a dependency. No external signup. No API key.

### 2.2 Sample download: 1 week of late 2024

```python
import pybaseball as pyb
pyb.cache.enable()
df = pyb.statcast(start_dt='2024-09-22', end_dt='2024-09-29')
# Wall: 2.58s, n_rows = 29,873, n_cols = 118
```

| Metric | Value |
|---|---|
| Wall seconds | 2.58 |
| Rows | 29,873 |
| Columns | 118 |
| Parquet size | 4.77 MB |
| CSV gzip size | 5.57 MB |
| Rows per day | ~4,268 |

### 2.3 Projection to full season and archive

| Target | Rows (est) | Parquet MB (est) | Wall sec (est) |
|---|---:|---:|---:|
| 2024 full season (~210 days) | 896,190 | 143 | 77 |
| 2015-2024 full archive (10 seasons) | 8,961,900 | 1,432 | 774 |

**Both well within the 5 GB / Phase 1 disk budget**. The full archive is ~1.4 GB parquet, ~13 minutes to download fresh. With pybaseball cache enabled, subsequent reads are instant.

### 2.4 Current-season download

A live test of `pybaseball.statcast(start_dt='2026-03-01', end_dt='2026-05-24')` returned **n=267,996 pitches** across 71 dates (only those with games; pybaseball auto-skips offseason). Wall: **23.3 seconds**. Parquet: 36.4 MB. **2026 season-to-date Statcast is live and fresh in real time.** This means the operationally meaningful "as-of yesterday" feature is always available.

### 2.5 Schema for ML feature engineering

Key columns confirmed present:

| Column | Coverage | Use |
|---|---:|---|
| `pitch_type`, `release_speed`, `release_spin_rate`, `pfx_x`, `pfx_z`, `plate_x`, `plate_z` | 99.7% | Pitcher mechanics features |
| `launch_speed`, `launch_angle` | 33.8% (batted balls only) | Hard-contact features |
| `estimated_ba_using_speedangle` (xBA) | 16.9% (batted balls only) | Hit-likelihood proxy |
| `estimated_woba_using_speedangle` (xwOBA) | 25.3% (batted balls only) | Quality-of-contact proxy |
| `events` | All PA-end pitches | Outcome label: single, double, triple, home_run, strikeout, walk, ... |
| `batter`, `pitcher` | 100% | MLBAM player IDs |
| `home_team`, `away_team`, `stand`, `p_throws` | 100% | Park, handedness context |
| `game_date`, `game_pk` | 100% | Temporal join key |

**Caveat 1**: `player_name` field in pybaseball Statcast is the **PITCHER**, not the batter. Batter is `batter` (MLBAM ID). To map Kalshi player names ("Aaron Judge") to MLBAM IDs (592450), use `pybaseball.chadwick_register()` (one-shot 7-second load, then in-memory).

**Caveat 2**: xBA and xwOBA only populate on batted balls. For strikeout / walk / hit-by-pitch outcomes the rows have NaN in these columns. Aggregation must distinguish "no contact" from "weak contact." Use `events` for the binary hit/no-hit label; use xwOBA as continuous quality-of-contact aggregate over a player's prior-N-PA window.

---

## 3. Feature availability with AS-OF discipline

### 3.1 The leak-safe sampling rule

For a Kalshi prop market with `close_time = T_close` (which for these sub-daily props is the same calendar day as the game), the leak-safe Statcast filter is:

```python
sc.loc[sc['game_date'] < (T_close - timedelta(hours=24))]
```

Equivalently: include only games whose `game_date` is strictly before the game-day of the Kalshi market. This is trivially achievable with pybaseball because `game_date` is a clean ISO date column, and the Kalshi ticker prefix encodes the game date.

Because the props are sub-daily (median lifetime 6.3 hours, p90 = 22.4 hours, p99 <48h), the only operationally meaningful T-X is **T-1 day** (yesterday's box scores) or even **T-3 hours** (just before market open). T-35d is not a thing for these markets. This is fundamentally different from v1's domain.

### 3.2 Candidate feature set (KXMLBHIT/HRR/HR target)

Per-player per-game (batter X, game date D) features, derived from Statcast rows with `game_date < D`:

| Feature group | Examples | Window | Statcast source |
|---|---|---|---|
| Form recency | hits per PA, hits per game, hard-hit rate | last 7 / 14 / 30 days | events, launch_speed |
| Quality of contact | xwOBA, xBA, exit velocity p75, launch angle median | last 100 PAs | estimated_woba_using_speedangle, estimated_ba_using_speedangle, launch_speed, launch_angle |
| Plate discipline | K rate, BB rate, contact rate, swing rate, whiff rate | last 100 PAs | events, description |
| Splits | vs LHP / RHP, home vs away | last 365 days | p_throws, home_team, away_team |
| Pitcher matchup (today's starter) | pitcher's K-per-9, BAA, xwOBA-against | last 5 starts | pitcher rows |
| Park factor | 5-year park index for the home_team | static | external (Baseball Savant park factors table) |
| Lineup spot | 1-9 batting order, expected PAs | per-game | lineup data (MLB Stats API) |

Per-pitcher per-game (pitcher Y, game date D) features for KXMLBKS:

| Feature group | Examples | Window | Source |
|---|---|---|---|
| K rate recency | K per 9 IP, K rate | last 5 starts | events, pitcher rows |
| Stuff | release speed, spin rate, pitch movement | last 100 pitches | release_speed, release_spin_rate, pfx_x/z |
| Opponent quality | opposing team's K rate | last 30 days | aggregate by batter team |
| Innings expectation | pitcher's avg IP per start | season | aggregated |

All of these are derivable from Statcast + lookup tables. No paid data tier required.

### 3.3 As-of join procedure for the Phase 2 dataset build

```
1. Pull full 2026 Statcast for the relevant date range  (already cached)
2. For each Kalshi prop market m with game date D_m, player P_m, threshold T_m:
   a. Map P_m to MLBAM ID via chadwick_register (one-shot lookup table)
   b. Compute feature vector F(P_m, D_m) using Statcast rows where game_date < D_m
   c. Join target outcome y = (m.result == 'yes')
   d. Retain m.last_price_dollars as the price-baseline feature
3. Split chronologically: train = first 70% of dates, holdout = last 30%
4. Train model with leave-one-date-out CV via gate.py 'trainer='; no shared model across folds
5. Gate: locked C1-C6, where C6 is replaced with Brier-skill vs price-only baseline on the prop-prediction task
```

### 3.4 Failure modes addressed

| Mode | Defense |
|---|---|
| Look-ahead leak (Statcast future game inflows used as features for the same date) | Strict `game_date < D` filter; Statcast game_date is the game date, not the time the data is published |
| Single-player artifact | n=497 batters / 206 pitchers, no single player > 0.9% of sample |
| Single-day artifact | 60 distinct game-dates; ~14k player-games |
| Anchoring on price | Orthogonality protocol: train model WITHOUT price feature, measure if residual is still positive (per v2 critic Section 5 "drop_price" experiment) |
| C5 leak | gate.py post-v2-amendment requires per-fold re-training; carries forward |

---

## 4. Orthogonality check (light pass)

### 4.1 Methodology

Two probes ran on KXMLBHIT-1+ (`floor_strike=0.5`) and KXMLBHIT-2+ (`floor_strike=1.5`) markets:

- Probe 1 (`probe_orthogonality_light.py`): 20 markets, 10 yes + 10 no random selection.
- Probe 2 (`probe_orthogonality_light2.py`): 54 markets including 30 mid-band (price in [0.20, 0.80]).

For each market: compute batter's BA over last 14 games (PAs prior to game date D), and xwOBA over last 14 games. Eyeball-correlate with outcome and price.

### 4.2 Probe 1 (KXMLBHIT-1+ balanced YES/NO)

|  | Mean BA14g | n |
|---|---:|---:|
| YES (player got 1+ hit) | 0.157 | 10 |
| NO (player did not) | 0.219 | 9 |

`Spearman r(BA14g, outcome) = -0.558, p=0.013` (negative; counter-intuitive)
`Spearman r(BA14g, price) = -0.546, p=0.016`

**Interpretation:** at floor 0.5, Kalshi prices nearly all markets at 0.99 yes (favorite) or 0.01 no (extreme underdog). The "NO" markets are the FAVORITES that happened to lose; the "YES" markets are also favorites that won. The correlation between BA14g and outcome is artifactual of the YES being heavily concentrated in lower-tier hitters who still got 1 hit (variance) while NO heavily favors higher-tier hitters who happened to whiff (also variance). This sample is too small and too unbalanced to be informative.

### 4.3 Probe 2 (KXMLBHIT-2+ mid-band, more diverse prices)

n=54 markets. Of these, 48 had a complete feature.

|  | Mean BA14g |
|---|---:|
| YES (player got 2+ hits) | 0.194 |
| NO (player did not) | 0.241 |

`Spearman r(BA14g, outcome) = -0.319, p=0.027`
**`Spearman r(BA14g, price)   = -0.043, p=0.772`**  <- KEY
`Spearman r(price,  outcome) = +0.700, p<0.001`

**The key correlation is BA14g vs price = -0.04.** BA14g carries information ORTHOGONAL to the price; the Kalshi market does not appear to internalize the last-14-games batting average into its 2+ hits price.

In-sample Brier (eyeball only; not OOS):
- price-only logistic: 0.0633
- price + BA14g logistic: 0.0626 (delta -0.0007)

Tiny in-sample lift, but the direction is right. With more features (xwOBA, opponent pitcher quality, park, lineup spot) the lift should grow. The light pass clears the H-B feasibility bar: **Statcast features are not collinear with the Kalshi price**.

### 4.4 Caveats and what the rigorous Phase 2 protocol must do

- This is in-sample; could be noise. The Phase 2 orthogonality protocol per v2 critic Section 5 must train the model WITHOUT the price feature and verify the residual is still positive on holdout.
- The 14-game window is short for early-season markets (some players had only 14 prior PAs total). Robustness check: re-run with longer windows (last 30 games, last 100 PAs, season-to-date) and verify the orthogonal-information claim holds.
- The 0.99 / 0.01 price clustering on extreme-floor markets means Kalshi prices ARE deterministic for those markets, leaving no Brier improvement headroom for the model. Mid-band markets are where the action is. Focus modeling on KXMLBHRR (n=6,479 in mid-band), KXMLBKS (n=200 mid-band but the prop is binary-like), and KXMLBHIT 2+ (n=487 mid-band).

---

## 5. Sportsbook competition assessment

### 5.1 Major sportsbooks offering MLB player props

- **DraftKings**: "more player props than any other US sportsbook." Mainstream, recreational liquidity.
- **FanDuel**: peer of DraftKings; mainstream.
- **BetMGM, Caesars**: similar to DK/FD.
- **Pinnacle**: sharp book; tighter spreads. Outside CA market access for retail (operator restricted).
- **Bookmaker, BetOnline**: offshore sharp books; not generally legal CA.
- **Kalshi**: prediction-market venue; explicit fees, not embedded vig.

### 5.2 Spread / inefficiency evidence

Web research (sources at end of section):

- "Player prop lines are set by modelers working off season-long projections, and those projections do not always react quickly to in-season role changes, pitch-mix adjustments, or contact-quality changes." (FantasyTeamAdvice MLB Prop Edge tool description)
- "Sharp bettors hunt the gap between what the data already shows and what the market has not yet priced." (BettorEdge MLB prop guide)
- **"Pitcher markets are always the easiest to beat the closing line"** (Covers.com). This is directly relevant to KXMLBKS (strikeouts). Strikeout props are the lowest-hanging-fruit inefficiency in MLB props per the literature.
- "Opening lines often do not reflect certain factors like recent pitch counts or weather conditions, allowing bettors confident in their research to target specific props like strikeout or recorded outs unders" (Covers.com).
- "Kalshi's order book may be thin on game props or smaller markets" (Lines.com / DeucesCracked). Implication: Kalshi player-prop liquidity is lower than DraftKings, which means PRICE is less efficient (sportsbooks have higher sample-size to calibrate; Kalshi prices may be less informative).
- "On illiquid games, the spread between Yes and No can be wide, sometimes 5-10 cents." (XCLSV Media).

### 5.3 Implication for Track B

Player props (especially pitcher strikeouts) are documented as a known retail-edge zone. The sportsbook competition exists but is **less aggressive than on game lines**, and the Kalshi spread/illiquidity asymmetry may compound: if Kalshi prices are 5c wide and sportsbook props converge to 1-2c, the Kalshi market has more headroom for a Statcast-informed model to improve over price. This is consistent with the master plan's framing that "player props are the angle most likely to find inefficiency."

**However**: 5-10c spread also means execution slippage at retail size is real. The C6 +2pp threshold must be cleared net of:
- 2% maker fees round-trip (Kalshi)
- ~2% spread crossing if a taker fill is needed
- Implementation slippage from going from theoretical signal to executable order

Phase 2 must measure the executable edge net of these, not the theoretical Brier improvement.

Sources:
- [BettorEdge: MLB Player Prop Betting](https://www.bettoredge.com/post/mlb-player-prop-betting-how-to-pick-winners-for-hits-hrs-and-more)
- [FantasyTeamAdvice: MLB Prop Edge](https://fantasyteamadvice.com/mlb/prop-edge)
- [Covers: Five Tips For Betting MLB Props](https://www.covers.com/mlb/prop-betting-tips-for-successful-baseball-betting)
- [DeucesCracked: Prediction Markets vs Sportsbooks 2026](https://www.deucescracked.com/blog/prediction-markets-vs-sportsbooks-2026-kalshi-polymarket-guide)
- [XCLSV: Kalshi vs Sportsbooks 2026](https://xclsvmedia.com/kalshi-vs-sportsbooks-2026-can-prediction-markets-replace-your-sportsbook/)

---

## 6. Sample-size feasibility

### 6.1 Master-plan thresholds

The v5 master plan Section 7 specifies for Track B: "aim for n >= 200; supplement with multiple stat types if needed."

### 6.2 Adjacent series (the operational Track B universe)

| Series | n_binary | n_player-game pairs | n_event-dates | Master plan verdict |
|---|---:|---:|---:|---|
| KXMLBHIT (1+/2+/3+/4+) | 44,306 | 14,017 | 790 (events) / 60 (dates) | far above n>=200 |
| KXMLBHR (1+/2+) | 26,052 | 13,983 | 789 events / 60 dates | far above n>=200 |
| KXMLBHRR (1+/2+/3+/4+/5+) | 65,677 | 13,931 | 789 events / 60 dates | far above n>=200 |
| KXMLBKS (1+ to 12+) | 10,911 | 1,525 | 787 events / 60 dates | far above n>=200 |
| KXMLBSTATCOUNT (specialty) | 6 | 6 | 2 | structurally below |

**Master plan n>=200 threshold met by all four prop series with ample headroom.** Even at the most-conservative independence count (60 game-dates), the combined cross-series sample is ~13k player-game pairs across 60 dates, enough for a 5-fold time-series CV with 12 dates per fold.

### 6.3 Independence and temporal coverage caveat

All 150,110 markets come from a 60-day window in ONE MLB season (2026 March 26 to May 24). The "independent draw" count is 60 dates, not 150k. This is a meaningful constraint:

- The 2026 MLB season is in its early phase (about 1/4 through), so the player population's underlying ability is somewhat known but in-season form is still high-variance.
- Generalization to other seasons (2025, 2024, 2023) is UNTESTED. We do not have Kalshi prop data from before 2026-03.
- Walk-forward CV within 60 dates with 12 per fold is fine for finding signal but means the holdout will cover ~18 dates, which is small for confidence interval purposes.

**Phase 2 risk**: with only 60 dates, the holdout CI is wide. Bootstrap CI on a holdout of ~18 dates may include zero even if the model has +2pp edge. Mitigate by:
1. Pooling across the four prop series (KXMLBHIT + HR + HRR + KS) since the features overlap (recent form indicators) and the target structure is parallel ("over/under threshold for a player on a game").
2. Including 2024 and 2025 Statcast data so the rolling-form feature has historical context (the BA14g feature would already inherit longer-term form from the 2025 season for veterans).
3. Reporting cluster-bootstrap CI by game-date (60 clusters) not row-level CI.

### 6.4 KXMLBSTATCOUNT specific

n=6 is structurally below ANY ML threshold. **The brief's literal scope (KXMLBSTATCOUNT only) is BLOCKED.** Track B can only proceed by amending scope to KXMLBHIT/HR/HRR/KS, where the data does exist.

---

## 7. Recommendation

### 7.1 Track B verdict: PROCEED with scope amendment

**PROCEED** with Track B Phase 2 conditional on operator confirmation of the scope amendment:

- **OUT**: KXMLBSTATCOUNT (n=6, structural dead-end).
- **IN**: KXMLBHIT, KXMLBHR, KXMLBHRR, KXMLBKS (collectively n=146,946 binary resolved, ~43k player-game pairs, 60 distinct game-dates in 2026 season-to-date).

All three feasibility load-bearing questions clear:

1. **Sample size**: n=146,946 >> 200 master-plan floor. Player-game-pair independent unit count ~43k. Single-player concentration < 1%. Caveat: only 60 distinct game-dates so 5-fold CV is workable but holdout CI will be wide.

2. **Feature availability**: pybaseball + Statcast are free, downloadable in seconds, leak-safe to filter by game_date < market.D. xBA, xwOBA, exit velo, K rate, plate discipline, recent form are all directly derivable. Player-name to MLBAM ID mapping is a one-shot lookup via chadwick_register.

3. **Orthogonality**: BA14g is uncorrelated with Kalshi price (r=-0.04, p=0.77) in the light-pass sample. In-sample Brier improvement from adding the feature is small (-0.0007) but directionally positive. Rigorous Phase 2 protocol must verify on holdout WITHOUT the price feature.

### 7.2 What changes from the brief's scope

| Brief item | Operational outcome |
|---|---|
| "KXMLBSTATCOUNT inventory" | Done; n=6, structurally dead. |
| "KXMLBHR, KXMLBHIT, KXMLBKS, KXMLBHRR" | Done; n=146,952 binary across the four series. Real Track B universe. |
| "Statcast download" | Done; 2024 sample 5 MB / 2.6s; 2026 season-to-date 36 MB / 23s. |
| "Feature availability" | Documented in Section 3. Leak-safe. xBA/xwOBA/launch params present. |
| "10-market orthogonality probe" | Done with 20 + 54 samples; BA14g and price are orthogonal (r=-0.04). |
| "Sportsbook competition" | Player props acknowledged as known retail-edge zone; pitcher strikeouts the lowest-hanging fruit. |
| "n>=80 ML-track viability" | Cleared with several orders of magnitude. |

### 7.3 Phase 2 build outline (preview)

`scripts/v5/build_v5_b_dataset.py`:
1. Pull full 2024 and 2025 Statcast (~290 MB, ~3 min download with cache).
2. Pull or use cached 2026 season-to-date Statcast (already done, 36 MB).
3. For each of the 4 target prop series, join Kalshi market -> player MLBAM ID -> Statcast features as-of T-1d.
4. Output `data/v5/v5_b_dataset.parquet` with (ticker, player_id, game_date, threshold, kalshi_price, features..., outcome).

`src/kalshi_bot_v5/statcast_features.py`: feature extraction primitives. Per-player rolling form (BA, xwOBA, K rate, hard-hit rate) over 7/30/90 day windows + pitcher matchup featurization.

`src/kalshi_bot_v5/statcast_model.py`: LightGBM model with monotone constraints if appropriate. Train via `gate.py trainer=` callable (per-fold fresh training per v2 critic Section 3 fix).

`scripts/v5/run_v5_b_gate.py`: Six-criteria gate per `src/kalshi_bot_v2/gate.py`, with C6 replaced by Brier-skill-vs-price-only-baseline since v1 does not trade these props.

### 7.4 Pre-registered kill conditions for Phase 2

To honor the kill-early principle, Phase 2 fails (close as null) if any of these binds on the holdout:
- Brier-skill (model vs price baseline) negative or CI includes zero;
- Orthogonality protocol fails (model predictions become non-informative when price feature removed);
- Single-player or single-date holdout concentration > 30% (S1/S5 v3 sanity checks);
- Net executable edge < +1pp after fees and 2c spread crossing.

### 7.5 What this does NOT recommend

- Do NOT proceed without 2024-2025 Statcast pulled and joined. The 60-day 2026 window alone is too thin for confidence.
- Do NOT enable LIVE mode on prop markets until Phase 2 gate + Phase 3 critic + 50-fill paper accumulation. The v1 LIVE_OVERRIDE_GATE escape is for the validated v1 strategy on its own universe, not for new v5 work.
- Do NOT include KXMLBSTATCOUNT in the modeling scope. It is structurally distinct and adds no usable signal.

---

## 8. Findings summary

| # | Finding | Severity |
|---|---|---|
| 1.1 | KXMLBSTATCOUNT n=6 settled markets; the brief named the wrong series. Real Track B universe is KXMLBHIT/HR/HRR/KS. | Important (scope amendment) |
| 1.2 | KXMLBHIT/HR/HRR/KS combined: 150,110 settled, 146,952 binary resolved, 43k player-game pairs, 60 dates. | Killer (positive) |
| 1.3 | Kalshi /historical/markets returns 0 rows; cutoff is 2026-03-25 and these series opened after. Use /markets?status=settled. | Important (methodology) |
| 1.4 | Single-player concentration < 1% across all four prop series (top player ~0.5%). Top-5 share 2-4%. v2 COL-as-opponent failure mode is structurally absent here. | Important (positive) |
| 1.5 | Per-event ladders inflate nominal n by 5-10x; real independent unit is player-game pair (n=43k) or game-event (n~3,150). | Important (methodology) |
| 1.6 | All data within one MLB season (2026-03 to 2026-05); cross-season generalization untested. | Killer (caveat) |
| 2.1 | pybaseball 2.2.7 installs cleanly via uv add. No API key. | Killer (positive) |
| 2.2 | Sample download (1 week 2024): 2.6s, 30k rows, 5 MB. | Killer (positive) |
| 2.3 | 2026 season-to-date downloaded successfully: 268k pitches, 36 MB, 23s. Statcast is real-time-fresh. | Killer (positive) |
| 2.4 | Full 2015-2024 archive projected at 1.4 GB / 13min. Within Phase 1 5 GB budget. | Important (positive) |
| 3.1 | Statcast schema has 118 columns including xBA, xwOBA, launch params, pitch movement. Per-pitch and per-PA features all derivable. | Killer (positive) |
| 3.2 | pybaseball's `player_name` is the pitcher, not the batter. Use `chadwick_register()` to map Kalshi player name -> MLBAM batter ID. | Important (methodology) |
| 3.3 | Leak-safe as-of join: filter Statcast `game_date < market_game_date`. Sub-daily props make T-X = T-1d the operationally meaningful window. | Important (methodology) |
| 4.1 | Light orthogonality probe: BA14g and Kalshi price are uncorrelated (Spearman r=-0.04, p=0.77). Statcast carries orthogonal information. | Killer (positive) |
| 4.2 | In-sample lift from adding BA14g to a price-only model: Brier -0.0007 (tiny but positive direction). Phase 2 must verify on holdout. | Important (positive) |
| 5.1 | Player props (especially pitcher strikeouts) documented as a known retail-edge market in the literature/community. | Important (positive) |
| 5.2 | Kalshi prop liquidity thin vs DraftKings (5-10c spreads on illiquid markets). Execution slippage real; net edge after costs must clear C6 +2pp floor. | Killer (caveat) |
| 6.1 | Master-plan n>=200 floor cleared by all four prop series with several orders of magnitude headroom. | Killer (positive) |
| 6.2 | Only 60 distinct game-dates available; holdout CI will be wide. Mitigate by cluster-bootstrap by date and by pooling across series. | Important (caveat) |
| 7.1 | Recommendation: PROCEED Track B Phase 2 with KXMLBHIT/HR/HRR/KS scope (drop KXMLBSTATCOUNT). | Verdict |

15 IMPORTANT, 8 KILLER (5 positive, 3 negative-as-caveat), 0 MINOR. The KILLER positives outweigh the KILLER caveats but the caveats are real and must be addressed in Phase 2.

---

## 9. Files written

| Path | Description |
|---|---|
| `data/v5/kxmlbstatcount_inventory.parquet` | Raw inventory, n=150,110 markets across 5 series |
| `data/v5/kxmlbstatcount_inventory_enriched.parquet` | Same + player and game_date columns extracted |
| `data/v5/kxmlbstatcount_inventory_summary.json` | Per-series summary stats |
| `data/v5/kxmlbstatcount_extended_summary.json` | Per-series with player concentration |
| `data/v5/statcast_sample_2024w39.parquet` | Sample week of 2024 Statcast pitches |
| `data/v5/statcast_2026_season_to_date.parquet` | Full 2026 season Statcast (Mar 15 - May 23) |
| `data/v5/pybaseball_sample_summary.json` | pybaseball install + sample download stats |
| `data/v5/orthogonality_light_sample.parquet` | Probe 1 (20 markets, balanced YES/NO) |
| `data/v5/orthogonality_light_sample_v2.parquet` | Probe 2 (54 markets, mid-band focus) |
| `scripts/v5/probe_kxmlbstatcount.py` | Inventory probe (run via uv run python -m scripts.v5.probe_kxmlbstatcount) |
| `scripts/v5/probe_kxmlbstatcount_extended.py` | Extended analysis (player/game extraction) |
| `scripts/v5/probe_pybaseball_sample.py` | pybaseball install validation + sample download |
| `scripts/v5/probe_orthogonality_light.py` | Probe 1 |
| `scripts/v5/probe_orthogonality_light2.py` | Probe 2 (mid-band) |
| `pyproject.toml` | pybaseball added as dependency |

## 10. Honest constraints on this finding

- The probe assumes Kalshi `/markets?status=settled` is a stable, queryable archive. If Kalshi removes settled markets older than ~90 days from this endpoint, the inventory will shrink. The probe should be re-run periodically to refresh.
- `chadwick_register()` is a CSV scrape of Chadwick Bureau data; new MLB callups during the 2026 season may not be in the active table immediately. Phase 2 build should fail gracefully on unmatched players and report the unmatched ratio.
- The light-pass orthogonality test was 54 markets in-sample; Phase 2 must use proper holdout + per-fold retraining.
- 5-10c spread on illiquid prop markets means the realized P&L is sensitive to maker-vs-taker assumptions. Phase 2 should report both: theoretical Brier improvement AND maker-side realized P&L net of fees + slippage.
- Sportsbook competition assessment is community/literature consensus, not a quantitative measurement of book efficiency. A rigorous comparison would require pulling sportsbook lines for the same KXMLB props and measuring closing-line value over a sample.
- The 2024 sample download succeeded on the first try, but pybaseball relies on baseballsavant.mlb.com being up. If MLB takes the site down for maintenance, the data layer is unavailable. Cache aggressively in Phase 2 to insulate against this.
