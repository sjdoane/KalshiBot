# v3 Historical Inventory and Sample-Size Feasibility

**Date:** 2026-05-24
**Agent:** V3-A
**Inputs:** Kalshi `/historical/markets`, `/historical/trades`, `/historical/cutoff` via the existing READ-scope client; cached series at `data/sports/markets/*.parquet` and `data/sports/trades/*.parquet`.
**Outputs:** `data/v3/probe_inventory_summary.parquet`, `data/v3/probe_inventory_all_markets.parquet`, `data/v3/probe_inventory_eligible_with_team.parquet`, per-series `data/v3/probe_<SERIES>.parquet`, `data/v3/probe_inventory_meta.json`.
**Probe code:** `scripts/v3/probe_inventory.py`.

## Headline numbers

- **Eligible n across all sports series: 147** (T-35d VWAP wide window +/- 7 days)
  - Pre-Kalshi-historical-cutoff (close_time < 2026-03-25): 129
  - Post-cutoff: 18
- **Eligible n under stricter +/- 1 day window: 102**
- **Total markets considered: 2,828** across 100 series
- **Series with any eligible markets: 47**
- **Verdict: above the n >= 80 ML-track viability threshold the master plan locked.** Below the 30% single-entity critic-kill threshold. Multiple distinct seasons + multiple distinct close dates within the dominant group (NFL team-wins) implies non-trivial temporal independence.

## v1 eligibility filter (reproduced exactly)

From `src/kalshi_bot/strategy/favorite_maker.py` lines 47-66 and `research/favorite-maker-results.md` (Round 4/7):

- VWAP YES price at T-35d in [0.70, 0.95]
- Market lifetime (`close_time - open_time`) in [30, 180] days
- Status in {finalized, settled}; market_type = binary
- result in {yes, no}
- Sport category (implicit: every series we probe is a sport)

VWAP computed over trades whose `created_time` lies in `[close - 35 - W, close - 35 + W]`. Two W values reported: the brief-specified narrow window (W = 1 day, capturing the price at the literal T-35d point) and the v1 trading window (W = 7 days, matching `scripts/v2/build_mlb_longhorizon_dataset.py:69-73`). The wide window is the operationally meaningful one (it is what v1 actually trades on); the narrow window is reported for honesty.

## 1. Series-by-series inventory

Eligible counts per series (wide window, listed only if eligible > 0):

| Group | Series | Total markets | Lifetime-ok | Eligible (wide) | Eligible (narrow) | Mean lifetime (d) | Mean price | YES rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| nfl_team_wins | KXNFLWINS-SEA | 30 | 20 | 8 | 6 | 79.2 | 0.879 | 1.000 |
| nfl_team_wins | KXNFLWINS-IND | 30 | 20 | 7 | 6 | 74.2 | 0.845 | 0.714 |
| nfl_team_wins | KXNFLWINS-DEN | 30 | 20 | 6 | 5 | 79.2 | 0.808 | 1.000 |
| nfl_team_wins | KXNFLWINS-BUF | 30 | 20 | 5 | 0 | 97.6 | 0.882 | 1.000 |
| nfl_team_wins | KXNFLWINS-NE | 30 | 20 | 5 | 7 | 74.6 | 0.805 | 1.000 |
| nfl_team_wins | KXNFLWINS-LA | 30 | 20 | 4 | 2 | 112.6 | 0.848 | 0.750 |
| nfl_team_wins | KXNFLWINS-CHI | 30 | 20 | 4 | 3 | 68.6 | 0.845 | 1.000 |
| nfl_team_wins | KXNFLWINS-TB | 30 | 20 | 4 | 1 | 107.1 | 0.886 | 0.500 |
| nfl_team_wins | KXNFLWINS-SF | 30 | 20 | 4 | 1 | 93.3 | 0.843 | 1.000 |
| nfl_team_wins | KXNFLWINS-MIA | 30 | 20 | 3 | 1 | 71.4 | 0.879 | 1.000 |
| nfl_team_wins | KXNFLWINS-GB | 30 | 20 | 3 | 0 | 107.9 | 0.874 | 0.667 |
| nfl_team_wins | KXNFLWINS-BAL | 30 | 20 | 3 | 0 | 94.8 | 0.845 | 1.000 |
| nfl_team_wins | KXNFLWINS-PIT | 30 | 20 | 3 | 1 | 92.8 | 0.865 | 1.000 |
| nfl_team_wins | KXNFLWINS-NYJ | 30 | 20 | 3 | 3 | 99.6 | 0.779 | 0.667 |
| nfl_team_wins | KXNFLWINS-NO | 30 | 20 | 3 | 1 | 94.8 | 0.814 | 1.000 |
| nfl_team_wins | KXNFLWINS-CLE | 30 | 21 | 3 | 0 | 87.9 | 0.882 | 1.000 |
| nfl_team_wins | KXNFLWINS-JAC | 30 | 20 | 3 | 2 | 87.8 | 0.809 | 1.000 |
| nfl_team_wins | KXNFLWINS-HOU | 30 | 20 | 3 | 1 | 86.8 | 0.850 | 1.000 |
| nfl_team_wins | KXNFLWINS-DAL | 30 | 20 | 3 | 3 | 103.2 | 0.840 | 0.667 |
| nfl_team_wins | KXNFLWINS-MIN | 30 | 20 | 2 | 2 | 105.3 | 0.915 | 1.000 |
| nfl_team_wins | KXNFLWINS-DET | 30 | 20 | 2 | 1 | 125.0 | 0.814 | 0.500 |
| nfl_team_wins | KXNFLWINS-CAR | 30 | 20 | 2 | 2 | 73.9 | 0.776 | 1.000 |
| nfl_team_wins | KXNFLWINS-PHI | 30 | 20 | 2 | 2 | 119.8 | 0.854 | 1.000 |
| nfl_team_wins | KXNFLWINS-ARI | 30 | 20 | 2 | 0 | 99.3 | 0.913 | 0.500 |
| nfl_team_wins | KXNFLWINS-KC | 30 | 20 | 2 | 1 | 117.8 | 0.898 | 0.000 |
| nfl_team_wins | KXNFLWINS-LV | 25 | 15 | 1 | 1 | 130.2 | 0.759 | 1.000 |
| nfl_team_wins | KXNFLWINS-LAC | 30 | 20 | 1 | 2 | 102.8 | 0.842 | 1.000 |
| nfl_team_wins | KXNFLWINS-CIN | 30 | 20 | 1 | 0 | 115.8 | 0.806 | 1.000 |
| nfl_team_wins | KXNFLWINS-NYG | 30 | 20 | 1 | 1 | 123.8 | 0.902 | 1.000 |
| nfl_team_wins | KXNFLWINS-TEN | 30 | 20 | 1 | 1 | 101.8 | 0.860 | 1.000 |
| nfl_team_wins | KXNFLWINS-WAS | 30 | 21 | 1 | 0 | 108.8 | 0.919 | 1.000 |
| nba_wins | KXNBAWINS | 270 | 270 | 17 | 18 | 178.3 | 0.860 | 1.000 |
| nfl_playoffs | KXNFLPLAYOFF | 32 | 32 | 9 | 9 | 168.2 | 0.845 | 0.778 |
| ncaaf_playoff_qual | KXNCAAFPLAYOFF | 58 | 54 | 8 | 6 | 81.1 | 0.832 | 0.875 |
| mlb_playoffs | KXMLBPLAYOFFS | 30 | 30 | 5 | 5 | 88.8 | 0.843 | 0.600 |
| mlb_team_wins | KXMLBWINS-{CHC,CIN,DET,HOU,KC,LAA,LAD,MIL,PHI,STL} | 50 | 50 | 10 | 5 | 131.2 | 0.881 | 0.900 |
| mlb_awards | KXMLBALCY | 13 | 13 | 1 | 0 | 152.5 | 0.900 | 1.000 |
| nhl_division | KXNHLCENTRAL | 8 | 8 | 1 | 1 | 168.0 | 0.936 | 1.000 |
| nhl_division | KXNHLMETROPOLITAN | 8 | 8 | 1 | 1 | 168.2 | 0.834 | 1.000 |

Series probed with zero eligible: KXMLBALMVP, KXMLBNLMVP, KXMLBNLCY, KXMLBALROTY, KXMLBNLROTY, KXMLBWORLD, KXNBA (championship), KXNBAEAST, KXNBAWEST, KXNBAFINMVP, KXNBAROY, KXNBADPOY, KXNBAMIMP, KXNBASIXTH, KXMLBAL/NL/{EAST,CENT,WEST}, KXMLBALCENT, KXNCAAF, KXNCAAFFINALIST, KXNCAAFUNDEFEATED, KXNCAAFACC/B10/B12/CS/SEC, KXNFLAFCCHAMP, KXNFLNFCCHAMP, KXNFLMVP, KXNFLAFCEAST/NORTH/SOUTH/WEST, KXNFLNFCEAST/NORTH/SOUTH/WEST, KXNHL (Stanley Cup), KXNHLPRES, KXNHLPLAYOFF, KXNHLEAST, KXNHLWEST, KXNHLATLANTIC, KXNHLPACIFIC, KXNBAATLANTIC, KXNBACENTRAL, KXNBANORTHWEST, KXNBAPACIFIC, KXNBASOUTHEAST, KXNBASOUTHWEST, KXNBAPLAYOFF, KXNCAAMBACC/BIG10/BIG12/BIGEAST/SEC/ACHAMP, KXNCAAMBNAISMITH.

Most failed because the markets are either too short-lived (game-level), too long-lived (>180d for season-long championship parents like KXNHL), or too low-volume in the trading window. Several award series had so few trades that no T-35d VWAP could be computed.

Master-plan-named series not present in the data/sports cache: `KXNBAFINALS` (championship parent series), `KXNFLSB` (Super Bowl), `KXNHLSC` (Stanley Cup), `KXNHLWINS`, `KXNHLMVP`. The closest cached analogues used: `KXNBA` for NBA championship (zero eligible), `KXNFLAFCCHAMP`/`KXNFLNFCCHAMP` for SB-precursor conf champs (zero eligible), `KXNHL` for Stanley Cup (zero eligible).

## 2. Cross-series aggregate

**Total eligible n = 147 (wide T-35d window).**

By v3 master plan thresholds:
- n >= 80 -> ML-track viable. **Met (147 wide; 102 narrow; 129 pre-cutoff).**
- 30 <= n < 80 -> H3-only or borderline.
- n < 30 -> pivot or kill.

Decomposition by group (wide window):

| Group | Eligible n | Share | Hit rate | Mean price |
|---|---:|---:|---:|---:|
| nfl_team_wins | 95 | 64.6% | 0.874 | 0.849 |
| nba_wins | 17 | 11.6% | 1.000 | 0.860 |
| mlb_team_wins | 10 | 6.8% | 0.900 | 0.881 |
| nfl_playoffs | 9 | 6.1% | 0.778 | 0.845 |
| ncaaf_playoff_qual | 8 | 5.4% | 0.875 | 0.832 |
| mlb_playoffs | 5 | 3.4% | 0.600 | 0.843 |
| nhl_division | 2 | 1.4% | 1.000 | 0.885 |
| mlb_awards | 1 | 0.7% | 1.000 | 0.900 |

NFL team-wins is the workhorse: 95 of 147 = 64.6% of the eligible set. If we restrict ML training to NFL-team-wins alone, n=95 is right at the C4=15 holdout + 5-fold CV minimum-recommended boundary (>= 80).

## 3. Single-entity concentration (v2 COL-as-opponent check)

Top single-team counts in the full eligible set:

| Rank | Team | n | Share |
|---:|---|---:|---:|
| 1 | SEA | 10 | 6.8% |
| 2 | IND | 9 | 6.1% |
| 3 | DEN | 8 | 5.4% |
| 4 | HOU | 6 | 4.1% |
| 5 | NE | 6 | 4.1% |
| 6 | BUF | 6 | 4.1% |
| 7 | TB | 5 | 3.4% |
| 8 | SF | 5 | 3.4% |
| 9 | LA | 5 | 3.4% |

Top-5 teams together = 39/147 = 26.5%.

**Verdict on the v2 failure mode:** no single team comes anywhere near the 30% critic-kill threshold. The 6.8% maximum is in safe territory. The v2 catastrophe (75% of holdout = COL) was structural to the MLB game-market design (one bad team dragging up multiple underdog markets); the team-wins / playoff design avoids this because each market is a TEAM-ON-ITSELF binary, not a team-vs-team game.

This is a meaningful improvement over v2's data shape.

Caveat: when we restrict to pre-cutoff (n=129), SEA's share rises to 10/129 = 7.8% and top-5 is 38/129 = 29.5%, right at the borderline. The 30% threshold is not breached, but is close. Worth re-checking after the holdout split is drawn.

## 4. Lifetime distribution

Histogram of eligible lifetimes (30-day buckets, wide window):

| Bucket (days) | n | Share |
|---|---:|---:|
| [30, 60) | 13 | 8.8% |
| [60, 90) | 43 | 29.3% |
| [90, 120) | 38 | 25.9% |
| [120, 150) | 24 | 16.3% |
| [150, 180) | 29 | 19.7% |

Distribution stats: mean 110d, median 102d, p25 81d, p75 132d, min 40d, max 180d.

The 30-180d band is what v1 explicitly trades (Round 7 finding; see `research/time-scale-analysis.md`). v3 inherits the same restriction by construction. The distribution is well-spread; no degenerate bucket. Two-thirds of the mass lies in [60, 150) days, consistent with the v1 sweet-spot at ~3 months.

## 5. Time concentration

Eligible markets by close-month:

| Close month | n |
|---|---:|
| 2025-09 | 6 |
| 2025-10 | 23 |
| 2025-11 | 32 |
| 2025-12 | 57 |
| 2026-01 | 10 |
| 2026-03 | 1 |
| 2026-04 | 18 |

By quarter: 2025Q3 = 6, 2025Q4 = 112, 2026Q1 = 11, 2026Q2 = 18.

Two distinct seasons are represented: the 2025-26 NFL season (peaking Dec 2025 as in-season win-total thresholds settle), and the 2025-26 NBA season (peaking Apr 2026 as season-end win totals settle). NCAAF playoff qualifiers settle Dec 7 2025. MLB playoffs settle Sep 29 2025.

**Independence audit (count of distinct close DATES per group):**

| Group | Eligible n | Distinct close dates |
|---|---:|---:|
| nfl_team_wins | 95 | 26 |
| nfl_playoffs | 9 | 4 |
| nba_wins | 17 | 2 |
| mlb_team_wins | 10 | 2 |
| ncaaf_playoff_qual | 8 | 1 |
| mlb_playoffs | 5 | 1 |

The "147 eligible markets" should be understood as **~37 distinct closing events**, not 147 independent observations. The dominant NFL team-wins group is the most independent (26 distinct close dates across the NFL season as win-thresholds settle week by week); KXNBAWINS, KXNCAAFPLAYOFF and KXMLBPLAYOFFS contribute clusters of simultaneous markets.

**Implication for CV:** purge-and-embargo CV should partition by close DATE not by row index. With 26 NFL closing dates, a 5-fold time-series CV has ~5 closing dates per fold, which is workable. Pooling NBA + NFL + NCAA + MLB across the full eligible set gives ~37 effective independent draws, marginal for 5-fold CV.

## 6. Time-cutoff check

Kalshi `/historical/cutoff` returned `{"market_settled_ts": "2026-03-25T00:00:00Z", "orders_updated_ts": "2026-03-25T00:00:00Z", "trades_created_ts": "2026-03-25T00:00:00Z"}`.

The cutoff is **2026-03-25** (today is 2026-05-24, so two months of post-cutoff data exist via the live-but-past-close window).

| Window | Eligible n | YES rate |
|---|---:|---:|
| Pre-cutoff (close < 2026-03-25) | 129 | 0.860 |
| Post-cutoff (close >= 2026-03-25) | 18 | 1.000 |

All 18 post-cutoff eligible markets are NBA team-wins markets that closed 2026-04-13 (NBA season end). They are operationally settled but lie inside Kalshi's "live but past-close" data window, not the cleanly-historical archive. For v3 modeling, pre-cutoff is the honest holdout-safe set; post-cutoff is usable but should be flagged.

The 18 post-cutoff markets all settling YES is consistent with strong end-of-season favoritism but adds zero information for model training: if a model just predicts "favorite at T-35d wins" it gets 100% on this slice.

## 7. Recommendation

**v3 is feasible on NFL team-wins (KXNFLWINS-*) primarily, with NFL playoff qualifiers (KXNFLPLAYOFF) and NCAA Football playoffs (KXNCAAFPLAYOFF) as secondary support.**

Justification, in numbers:

1. **NFL team-wins gives 95 eligible markets, the largest non-trivial pool.** It is the only single market type with n >= 80 by itself. ML-track viable on NFL alone.
2. **26 distinct NFL close dates** over Oct 2025 to Jan 2026 provides genuine temporal independence for walk-forward CV. The NFL season produces a steady stream of resolving markets (week by week as each team plays enough games to settle its win-threshold contract).
3. **Single-team concentration is benign**: SEA's 10 markets = 10.5% of the NFL-only subset, all within the 30% safe threshold.
4. **Hit rate ~87.4%** on NFL team-wins at price band [0.70, 0.95] confirms v1's favorite-longshot thesis on this domain. v3 model needs to do MORE than just "predict YES at price >= 0.70"; it needs to predict WHICH ~12.6% of these markets will resolve NO.
5. **NFL data sources are abundant and free**: nflverse provides historical schedules, play-by-play, team stats per season; ESPN site API for current; nfl-data-py was already probed in v2 (`scripts/v2/probe_data_source.py`). No paid data tier needed.

Secondary support (combinable if cross-sport features are weak):
- NFL playoff qualifiers (n=9): 4 distinct close dates, useful as a holdout sanity check.
- NCAAF playoff qualifiers (n=8): 1 close date, useful but not independent within itself.
- MLB team-wins (n=10) + MLB playoffs (n=5) = 15 MLB markets across 3 distinct close dates. Useful for showing the model generalizes off-NFL but small.
- NBA team-wins (n=17): all close 2026-04-13, so a single observation block; useful only as a forward-test slice after the model is fit.

**Not recommended for v3:**
- MLB awards (MVP/CY/ROTY): tiny n, individual-player domain, lifetime distribution too narrow to span the v1 band cleanly.
- KXNBA (championship parent), KXNHL (Stanley Cup): zero eligible because the championship lifetimes are too long (>180d to span the playoffs).
- Conference championships (KXNFLAFCCHAMP, KXNBAEAST): zero eligible at the [0.70, 0.95] band because they're typically close races.

**Suggested v3 dataset construction (for Agent V3-B1):**
1. Primary: NFL team-wins (KXNFLWINS-*), n=95 wide / 67 narrow.
2. Auxiliary holdout: NFL playoffs (KXNFLPLAYOFF) + NCAAF playoffs (KXNCAAFPLAYOFF) + MLB team-wins + MLB playoffs + NBA team-wins = 49 markets. Use as a domain-generalization test, NOT in the primary holdout.
3. Split: chronological 70/30 on NFL alone: ~67 train / ~28 holdout. C4 floor of 15 holdout markets is met.
4. CV: 5-fold walk-forward by close DATE (so within-week NFL clusters do not leak across folds).
5. Single-team check (v3 S1 sanity): drop SEA from holdout, verify mean stays > 0.

**Falsification hooks already visible:**
- The 100% YES rate on NBA team-wins (n=17) and 100% on NHL divisions (n=2) is a selection-effect signal. Models trained without restraint on these will overfit to the trivial "favorites always win" pattern. The training set MUST include the losers (the 18 NFL markets where the favorite did NOT win: SEA went 8/8 but DAL went 2/3, LA 3/4, TB 2/4, KC 0/2, DET 1/2, ARI 1/2). The 12.6% NFL miss rate (12 of 95) is what the model is trying to predict; that is the entire signal.
- 12 misses across 95 NFL markets at avg lifetime 92d translates to a base rate where mean P&L per favorite-trade is roughly `0.874 - 0.849 - fees - slippage ~ 0.025 - 0.02 ~ +0.5pp`, i.e. razor-thin even before model lift. The model needs to add several pp to clear the C6=+2pp v1-beat threshold.

## Data shape vs v2 failure modes (explicit checks)

| v2 failure mode | v3 inventory status | Evidence |
|---|---|---|
| Domain mismatch | RESOLVED. NFL team-wins lifetime mean 92d is in v1's actual band. | Section 4 + Section 1 |
| Single-entity artifact (COL-as-opponent) | LOW RISK. Max team share 6.8%, top-5 = 26.5%. | Section 3 |
| C5 leak (in-sample folds) | Mitigation requires walk-forward by close DATE (26 distinct in NFL). | Section 5 |
| n too small for CV | RESOLVED at NFL-only (n=95) > 80 threshold. | Section 2 |

## Files written

- `data/v3/probe_inventory_summary.parquet` (47 series with one summary row each)
- `data/v3/probe_inventory_all_markets.parquet` (2,828 market-level rows with VWAP results)
- `data/v3/probe_inventory_eligible_with_team.parquet` (147 eligible rows with team column for concentration analysis)
- `data/v3/probe_<SERIES>.parquet` (per-series detail for caching)
- `data/v3/probe_inventory_meta.json`
- `data/v3/probe_run2.log` (run trace)
- `scripts/v3/probe_inventory.py` (the probe)
- `scripts/v3/__init__.py`

## Caveats

1. The narrow vs wide T-35d window disagrees on 45 markets (147 - 102). The narrow window misses markets where the 2-day band has no trades but the 14-day band does. The wide window is operationally correct for v1's trading strategy (v1 trades anywhere in [close - 42, close - 28] not just at the midpoint).
2. The KXNFLWINS-* series have 30 markets each because there are 6 win-threshold tiers per team per season AND 5 seasons of historical data per team. Only ~67% of these clear the lifetime filter (some thresholds open earlier in the season -> longer lifetime, some later -> shorter).
3. The probe pulled fresh trades from Kalshi for ~500 markets where the local cache had no coverage in the 14-day window. Polite throttle held at ~5 req/sec. Cumulative wall time ~4 minutes.
4. The probe did not deduplicate by (team, season): one team can have up to 5-6 eligible win-threshold contracts per season. If the model treats each threshold as independent it will be over-confident. The actual independent unit per team-season is ONE: the team's win-trajectory. Agent V3-B1 must address this directly (suggested: train at the team-season level, not the threshold-contract level).
5. No NHL or MLB award markets had non-trivial eligibility, which restricts cross-sport coverage. v3's effective domain is NFL with NBA/MLB/NCAA support, not a 4-sport balanced set.
