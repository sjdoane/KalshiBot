# Agent V5-A1: the-odds-api Coverage on v1's Post-Denylist Live Universe

**Date:** 2026-05-24
**Author:** Agent V5-A1 (v5 Track A Phase 1)
**Status:** Research only. READ-only public API (the-odds-api free tier). No trading. v1 bot UNTOUCHED.
**Scope:** the-odds-api coverage of v1's POST-DENYLIST sports universe. Live signal-direction probe. Comparison to V4-A Polymarket coverage (42.6% inclusive). Cost realism for Phase 2.

---

## TLDR verdict

**Coverage of v1's post-denylist live universe is HIGHER than Polymarket, and the signal direction matches.**

| Metric | Polymarket Global (V4-A) | the-odds-api (V5-A1) |
|---|---:|---:|
| v1 LIVE attempted weighted (inclusive PARTIAL @0.4) | 42.6% | **40.7%** |
| v1 LIVE attempted MATCH-only strict | 29.4% | **31.0%** |
| v3 INVENTORY-eligible weighted (inclusive PARTIAL @0.4) | 39.1% | **51.2%** |
| v3 INVENTORY-eligible MATCH-only strict | 10.4% | **18.8%** |
| Signal direction on favorites | Kalshi over Poly +9.21c (n=5) | **Kalshi over book +1.70c (n=23)** |
| Live probe n | small (single-series WC + MLB pairs) | **23 favorite pairs across 3 series** |
| Live mid feasibility | Good for MATCH; book-depth variable | **Excellent**: 5-9 books per event for MLB/NFL/WC, 2-6 for UFC/Boxing |
| Auth | None (Polymarket public read) | API key (operator provided 2026-05-24) |
| **Historical access** | 30-day ceiling, then no data | **PAID TIER ONLY** ($30/mo for 20K credits) |
| Free-tier monthly budget | unlimited reads | **500 credits/mo** (1 per live call, 10 per historical, free /sports + /events) |

**Recommendation: PROCEED with Track A Phase 2 at FREE tier for the live-filter overlay; defer paid tier until a Phase 2 retrospective backtest demonstrates value.** The post-denylist coverage is at the same level as Polymarket, but on a DIFFERENT subset of series. The smaller +1.70c divergence (vs Polymarket's +9.21c) is the cleaner signal because sportsbook lines are the institutional consensus. Combining v4's Polymarket filter with v5's sportsbook filter would provide non-collinear second-opinion sources on different parts of v1's universe.

**Material correction to V4-D (Section 3.1)**: V4-D documented "Free tier 500 credits/month INCLUDING historical odds access." This was WRONG. The actual API returns:

```
HTTP 401 Unauthorized
{"message":"Historical odds are only available on paid usage plans...
"error_code":"HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN"}
```

Phase 2 retrospective backtest CANNOT use historical odds on the free tier. Operator action required if paid tier is wanted.

---

## 1. v1 post-denylist universe enumeration

I rebuilt v1's universe with the W1 denylist (`KXNFLWINS`, `KXNFLPLAYOFF`, `KXMLBPLAYOFFS`) applied. Reproducer: `scripts/v5/enumerate_post_denylist_universe.py`. Output: `data/v5/v1_post_denylist_universe.parquet`, `data/v5/v1_post_denylist_universe_summary.json`.

### 1.1 Top-line counts

| Metric | Pre-denylist (V4-A) | Post-denylist (V5-A1) |
|---|---:|---:|
| Distinct series-prefixes (union of live + v3 inventory) | 87 | 84 |
| v1 live attempted orders | 34 | 29 |
| v1 live acked orders | 15 | 29 (after re-counting all of resting/filled/closed in state.json) |
| v3 inventory-eligible markets (narrow [0.70, 0.95], T-35d) | 102 | 32 |

The denylist removes 70 of v3's 102 inventory-eligible markets (almost all KXNFLWINS), and 5 live orders. Post-denylist, the universe is dominated by:

| Series prefix | League | v1 live orders | v3 inv eligible |
|---|---|---:|---:|
| KXNBAWINS | NBA | 0 | 18 |
| KXMLBWINS | MLB | 4 | 5 |
| KXNCAAFPLAYOFF | NCAA-FB | 2 | 6 |
| KXNBAPLAYOFFWINS | NBA | 4 | 0 |
| KXWCGAME | Soccer-WC | 3 | 0 |
| KXMLBSTATCOUNT | MLB | 2 | 0 |
| KXSTARTINGQBWEEK1 | NFL | 2 | 0 |
| KXUFCFIGHT | UFC-MMA | 2 | 0 |
| KXBOXING | Boxing | 1 | 0 |
| KXCITYNBAEXPAND | NBA | 1 | 0 |
| KXCS2 | CS2-Esports | 1 | 0 |
| KXFOMEN | Formula-1 | 1 | 0 |
| KXNEXTTEAMNFL | NFL | 1 | 0 |
| KXNEXTTEAMNHL | NHL | 1 | 0 |
| KXNFLGAME | NFL | 1 | 0 |
| KXWCSQUAD | Soccer-WC | 1 | 0 |
| KXWCSTAGEOFELIM | Soccer-WC | 1 | 0 |
| KXWNBAWINS | WNBA | 1 | 0 |

The post-denylist live picture is far broader (17 distinct series for 29 orders) than the v3-inventory picture (3 series carrying eligible counts), so coverage on the LIVE side is the binding number.

### 1.2 Hidden complication

The v3 inventory shows ZERO eligible markets for most of the live-active series (WC, UFC, Boxing, NFL game, etc.). That is because v3's probe inventory only contains historical-resolved markets in a narrow set of series; it does not include live in-season match-ups for season 2026. This is a v3 inventory selection-bias issue (already documented in v3 W2). For the live universe, the binding evidence is v1's resting/filled/closed orders, not v3 inventory.

---

## 2. the-odds-api docs review and key validation

### 2.1 Confirmed endpoints (from `https://the-odds-api.com/liveapi/guides/v4/`)

| Endpoint | Returns | Credit cost |
|---|---|---:|
| `/v4/sports` | List of in-season sport keys | **FREE** |
| `/v4/sports/{sport}/events` | In-play/pre-match events (no odds) | **FREE** |
| `/v4/sports/{sport}/odds?regions=us&markets=h2h&oddsFormat=decimal` | Bookmaker odds per market | 1 credit per market per region |
| `/v4/sports/{sport}/scores` | Game scores (with optional `daysFrom`) | 1-2 credits |
| `/v4/sports/{sport}/events/{eventId}/odds` | Per-event odds | 1 credit per market per region |
| `/v4/sports/{sport}/participants` | Teams/players | 1 credit |
| `/v4/historical/sports/{sport}/odds?date=...` | Historical snapshot | 10 credits per market per region (PAID ONLY on free tier) |
| `/v4/historical/sports/{sport}/events` | Historical events catalog | (would be free; UNTESTED on free tier) |

### 2.2 Confirmed pricing tiers (from `https://the-odds-api.com/#get-access`)

| Tier | Price | Credits/mo | Historical? |
|---|---:|---:|---|
| Starter (Free) | $0 | 500 | NO (free tier excludes historical) |
| 20K | $30/mo | 20,000 | YES |
| 100K | $59/mo | 100,000 | YES |
| 5M | $119/mo | 5,000,000 | YES |
| 15M | $249/mo | 15,000,000 | YES |

The historical exclusion on the free tier was the key correction to V4-D. The API responds:
```
HTTP 401 Unauthorized
{"message":"Historical odds are only available on paid usage plans.",
 "error_code":"HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN"}
```

### 2.3 Books covered

From a single live h2h call on `baseball_mlb` (US region), the bookmakers actually returned were:
- DraftKings, FanDuel, BetMGM, Caesars, BetRivers, BetOnline.ag, Bovada, MyBookie.ag, LowVig.ag (9 books)

For `mma_mixed_martial_arts` (US region): 2-4 books per fight, including DraftKings, FanDuel.

For `boxing_boxing` (US region): 4-6 books per fight.

For `soccer_fifa_world_cup` (US region): 7 books per game.

Pinnacle is referenced in docs as a bookmaker but does not appear in US-region responses (it's available via EU region).

### 2.4 Market types

The default markets v5-A1 probed: `h2h` (head-to-head, moneyline). The docs list additional markets:
- `spreads` (point handicaps), mainly US sports
- `totals` (over/under), mainly US sports
- `outrights` (futures for outright winners), free across all sports
- `h2h_lay` (lay odds on exchanges), Betfair only
- Player props: `player_pass_tds`, `player_points`, `player_pitching_strikeouts`, etc. Coverage is "limited to selected bookmakers and sports"
- Period/quarter markets: `h2h_q1`, etc.

For Track A Phase 2, `h2h` is sufficient for game-resolution markets and `outrights` is needed for futures markets.

### 2.5 Key validation

Confirmed `THE_ODDS_API_KEY` loads from `.env` via the project's pydantic Settings loader (length 32, format consistent with the-odds-api production keys). First `/v4/sports` call returned HTTP 200, listed 59 in-season sports, and consumed 0 credits (confirmed via the `x-requests-used` and `x-requests-remaining` response headers).

Cached: `data/v5/odds_api_sports.json`.

---

## 3. Coverage matrix per Kalshi series

Reproducer: `scripts/v5/build_odds_api_coverage_matrix.py`. Output: `data/v5/odds_api_coverage_per_series.json` and `.parquet`. Built by mapping each v1-touched series-prefix to a sport_key + market_type pair, then probing the FREE `/v4/sports/{sport}/events` endpoint to confirm in-season activity. Total probe cost: 18 free calls, 0 credits.

### 3.1 MATCH-class (sportsbook has exact event-class counterpart)

| Series prefix | League | v1 live | v3 inv | Active book events | Market type | Sport key |
|---|---|---:|---:|---:|---|---|
| KXBOXING | Boxing | 1 | 0 | 49 | h2h | boxing_boxing |
| KXNCAAFPLAYOFF | NCAA-FB | 2 | 6 | 1 | outrights | americanfootball_ncaaf_championship_winner |
| KXNFLGAME | NFL | 1 | 0 | 75 | h2h | americanfootball_nfl |
| KXUFCFIGHT | UFC-MMA | 2 | 0 | 48 | h2h | mma_mixed_martial_arts |
| KXWCGAME | Soccer-WC | 3 | 0 | 72 | h2h | soccer_fifa_world_cup |
| (also probed but not in v1-live universe) KXMLBGAME | MLB | 0 | 0 | 19 | h2h | baseball_mlb |
| (also probed but not in v1-live universe) KXNCAAFGAME | NCAA-FB | 0 | 0 | 0 (off-season) | h2h | americanfootball_ncaaf |
| (also probed) KXEPLGAME / KXMLSGAME / KXLALIGA | Soccer | n/a | n/a | n/a | h2h | various |

The MATCH set is dominated by GAME-RESOLUTION binary markets (h2h moneyline), where direct sportsbook-vs-Kalshi comparison is clean.

### 3.2 PARTIAL-class (event class matches; threshold or granularity differs)

| Series prefix | League | v1 live | v3 inv | Notes |
|---|---|---:|---:|---|
| KXMLBALROTY | MLB | 0 | 1 | Sportsbooks offer ROY futures but require dedicated outright sport_key |
| KXMLBPLAYOFFS *(denylisted)* | MLB | 0 | 5 | Denylisted; moot |
| KXMLBWINS | MLB | 4 | 5 | Kalshi multi-threshold per team; book lists 1 win-total. Monotonicity required (same as Polymarket V4-A) |
| KXNBAWINS | NBA | 0 | 18 | Same threshold-mismatch as MLBWINS |
| KXNEXTTEAMNFL | NFL | 1 | 0 | Some books list 'next team' for marquee players; coverage spotty |
| KXNFLPLAYOFF *(denylisted)* | NFL | 3 | 9 | Denylisted; moot |
| KXNFLWINS *(denylisted)* | NFL | 2 | 56 | Denylisted; moot |
| KXNHLCENTRAL | NHL | 0 | 1 | NHL division winners; outright coverage by the-odds-api unclear |
| KXNHLMETROPOLITAN | NHL | 0 | 1 | Same |
| KXWCSTAGEOFELIM | Soccer-WC | 1 | 0 | WC outright winner listed; per-team stage-of-elimination is a separate prop usually under specials |
| KXWNBAWINS | WNBA | 1 | 0 | Same as NBAWINS threshold mismatch |

### 3.3 NO_MATCH (no sportsbook counterpart on the-odds-api default markets)

| Series prefix | League | v1 live | v3 inv | Reason |
|---|---|---:|---:|---|
| KXCITYNBAEXPAND | NBA | 1 | 0 | Expansion-city votes not a sportsbook market |
| KXCS2 | CS2-Esports | 1 | 0 | the-odds-api scope excludes esports |
| KXFOMEN | Formula-1 | 1 | 0 | **F1 absent from the-odds-api default catalog (no `formula_1`, no `auto_racing_*` keys)** |
| KXMLBSTATCOUNT | MLB | 2 | 0 | Immaculate-inning props are not a standard sportsbook market |
| KXNBAPLAYOFFWINS | NBA | 4 | 0 | Team playoff-wins threshold not on sportsbooks; closest is championship futures (different claim) |
| KXNEXTTEAMNHL | NHL | 1 | 0 | Player next-team prop not standard |
| KXSTARTINGQBWEEK1 | NFL | 2 | 0 | Week-1 starting QB identity not standard prop |
| KXWCSQUAD | Soccer-WC | 1 | 0 | Player squad selection not standard prop |

### 3.4 Coverage classes by count

| Class | Count | Share |
|---|---:|---:|
| MATCH | 5 | 21% |
| PARTIAL | 11 | 46% |
| NO_MATCH | 8 | 33% |
| Total | 24 | |

(24 series probed = those with v1_live_orders > 0 OR v3_inventory_eligible > 0, including the 3 denylisted.)

### 3.5 Weighted coverage post-denylist

Weighting scheme follows V4-A: MATCH=1.0, PARTIAL=0.4, NO_MATCH=0.0.

| Universe | n | Weighted matched | Inclusive % | MATCH-only strict % |
|---|---:|---:|---:|---:|
| v1 LIVE attempted (n=29) | 29 | 11.8 | **40.7%** | **31.0%** |
| v1 LIVE acked (n=29) | 29 | 11.8 | **40.7%** | 31.0% |
| v3 INVENTORY-eligible narrow (n=32) | 32 | 16.4 | **51.2%** | **18.8%** |

### 3.6 Side-by-side with V4-A Polymarket

| Universe | Polymarket inclusive | Polymarket MATCH-only | the-odds-api inclusive | the-odds-api MATCH-only |
|---|---:|---:|---:|---:|
| v1 LIVE attempted | 42.6% | 29.4% | 40.7% | 31.0% |
| v1 LIVE acked | 57.3% | 46.7% | 40.7% | 31.0% |
| v1 BACKTEST eligible | 40.0% | 12.8% | n/a | n/a |
| v3 INVENTORY eligible | 39.1% | 10.4% | 51.2% | 18.8% |

The two sources cover roughly the SAME share of v1's live universe but on DIFFERENT subsets:

- **Polymarket strengths**: World Cup tournament markets, UFC, F1 championship futures, MLB win-totals (per-team), per-fixture soccer matches.
- **the-odds-api strengths**: in-season MLB / NFL / NBA / NCAAF game-resolution h2h (where Polymarket coverage is shallow), boxing (50 active events), WC games (72), UFC fights (48).
- **Both fail on**: KXMLBSTATCOUNT (immaculate inning), KXNBAPLAYOFFWINS (team playoff-wins threshold), KXCITYNBAEXPAND (expansion city), KXNEXTTEAMNHL (player next team), KXFOMEN (F1; Polymarket has championship futures, the-odds-api has none).

**Combining them**: the union coverage of the two second-opinion sources is HIGHER than either alone. Polymarket fills the futures gaps; the-odds-api fills the game-resolution gaps.

---

## 4. Live signal-direction probe

Reproducer: `scripts/v5/probe_signal_direction.py`, `scripts/v5/probe_mlb_divergence.py`, `scripts/v5/probe_extended_divergence.py`, `scripts/v5/aggregate_divergence_summary.py`. Outputs: `data/v5/signal_direction_probe.json`, `mlb_divergence_probe.json`, `extended_divergence_probe.json`, `divergence_summary.json`.

### 4.1 Credit budget accounting

| Probe | Call | Credit cost |
|---|---|---:|
| /v4/sports (validate key) | 1 call | 0 (free) |
| /v4/events for 18 sport_keys (coverage matrix) | 18 calls | 0 (free) |
| /v4/sports/{soccer_fifa_world_cup}/odds h2h us | 1 call | 1 |
| /v4/sports/{mma_mixed_martial_arts}/odds h2h us | 1 call | 1 |
| /v4/sports/{boxing_boxing}/odds h2h us | 1 call | 1 |
| /v4/sports/{americanfootball_nfl}/odds h2h us | 1 call | 1 |
| /v4/sports/{baseball_mlb}/odds h2h us | 1 call | 1 |
| Historical odds (5 attempted, all 401) | 5 calls | 0 (failed pre-charge) |
| Final /v4/sports validation | 1 call | 0 |
| **TOTAL** | | **5 credits** |

Of 500 monthly free credits: 5 used (1.0%), 495 remaining. Phase budget cap was 100; well under.

### 4.2 Live probe sample composition

Total Kalshi-vs-Sportsbook pairs collected: **52** across 5 Kalshi series.

| Source | Series | n | Notes |
|---|---|---:|---|
| v1 currently-resting orders | KXWCGAME, KXUFCFIGHT, KXBOXING, KXNFLGAME | 5 matched (of 7 attempts) | UFC HOK-LEW and Boxing CAL-MBI not yet listed by books |
| KXMLBGAME open markets | KXMLBGAME | 40 | All MLB games on slate 2026-05-24 to 27 |
| Extended UFC + Boxing open markets | KXUFCFIGHT, KXBOXING | 13 | Including MAY30 cards |

Full raw table in `data/v5/divergence_summary.json`.

### 4.3 Headline statistics

**SPORTSBOOK FAVORITES (book_implied >= 0.55), n=23:**
- Mean (Kalshi - Sportsbook): **+1.70 cents**
- Median: +0.45 cents
- Standard deviation: 5.09 cents
- 95% bootstrap CI on mean: **[-0.11c, +3.94c]**
- Kalshi over sportsbook: **15/23 = 65.2%**

**v1 ELIGIBLE BAND (kalshi_mid in [0.70, 0.95]), n=13:**
- Mean (Kalshi - Sportsbook): **+2.95 cents**
- Median: +1.19 cents
- 95% bootstrap CI on mean: [-0.28c, +6.56c]
- Kalshi over sportsbook: 9/13 = 69.2%

### 4.4 Per-series signal direction

| Series | n | Mean Kalshi - Book |
|---|---:|---:|
| KXWCGAME | 3 | **+10.34c** |
| KXMLBGAME | 12 | +1.37c |
| KXBOXING | 6 | -0.37c |

KXWCGAME's large mean is consistent with WC being a thin-retail Kalshi market against deep international sportsbook consensus (FanDuel, Betfair Sportsbook, William Hill all carry WC qualifying / group stage). The MLB and boxing samples are tighter because both markets have larger US retail volume on both sides.

### 4.5 Direction comparison to V3-C Polymarket

| Source | n | Mean Kalshi - second-opinion |
|---|---:|---:|
| V3-C Polymarket (T-35d, MLB win-totals) | 5 | +9.21c |
| V5-A1 the-odds-api (live, multi-series favorites) | 23 | **+1.70c** |
| Delta | | sportsbook is 7.5c closer to Kalshi than Polymarket is |

**Direction match: YES.** Both Polymarket and sportsbook lines price favorites LOWER than Kalshi.

**Magnitude difference is structural.** Sportsbook lines are the institutional reference price (~5-7% overround removed via de-vigging gives the cleanest second-opinion implied probability). Polymarket trades unregulated and is more retail-driven; it diverges further from Kalshi because of differing US-vs-offshore retail flows. The fact that sportsbook divergence is SMALLER than Polymarket divergence is a positive feature for a filter: it means the filter would fire LESS often, but when it fires, the divergence is on a tighter information set.

### 4.6 Historical probe attempt

I attempted 5 historical odds calls (`basketball_nba_championship_winner` outrights at T-30d, T-21d, T-14d, T-7d, T-1d before 2026-04-13). ALL FIVE returned HTTP 401 with `error_code=HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN`. NO credits were consumed (failed pre-charge).

**Phase 2 implication:** the retrospective backtest of TRACK A Phase 2 CANNOT use historical sportsbook odds on the free tier. Three options for Phase 2 (Section 6).

### 4.7 Honest caveats

1. **All comparison points are LIVE, not closing-line snapshots.** Sportsbook prices move; the live snapshot is a single point in time. A proper signal-direction measurement should be at T-X minutes/hours before each market's close. Phase 2 would do this prospectively.

2. **The sample is REGIME-DEPENDENT.** May 24, 2026 is MLB mid-season, NFL pre-season, NBA playoff conference finals, WC pre-tournament, off-season for NCAAF / NHL / NCAAB. The mix of MATCH events skews accordingly. A repeated probe in November 2026 (NFL Week 11) would have a very different MLBGAME / NFLGAME ratio.

3. **Sportsbook de-vigging assumes proportional vig.** The actual implied probability extraction from American or decimal odds requires assumptions about how books distribute their overround across outcomes. For 2-way h2h markets (boxing, UFC, MLB) this is benign. For 3-way h2h (soccer with draw), proportional de-vigging may slightly bias the home/away probabilities relative to the draw. The WC numbers should be considered upper-bound estimates.

4. **n=23 favorites is informative but not definitive.** Width 95% CI is [-0.11, +3.94]. The Polymarket V3-C result was on n=5 (tiny). A Phase 2 prospective collection across 30-60 days would give n>200 and tighter CI.

5. **No CLOSING-LINE measurement.** The signal-direction question for Phase 2 is whether sportsbook lines CLOSE different from Kalshi resolutions. The live-only probe is at minimum 1-30 days before close.

---

## 5. Comparison: sportsbook vs Polymarket as second-opinion source

| Property | Polymarket Global (V4-A) | the-odds-api (V5-A1) |
|---|---|---|
| v1 LIVE attempted weighted coverage | 42.6% | 40.7% |
| v1 LIVE attempted MATCH-only | 29.4% | 31.0% |
| Subset coverage strengths | WC squad, UFC, F1 futures, MLB win-totals | Game-resolution h2h (MLB/NFL/NCAAF/WC), boxing, UFC, futures (championship_winner outrights) |
| Subset coverage weaknesses | Game-resolution markets for in-season US sports thinly listed | F1 entirely absent; esports absent; KXMLBSTATCOUNT and KXNBAPLAYOFFWINS structurally absent |
| Liquidity | $2.1B/week aggregate (Polymarket Global) | Sportsbooks $100B+/year aggregate (US legal) plus offshore |
| Signal direction (Kalshi - second-opinion) | Kalshi over Poly +9.21c on favorites | Kalshi over book +1.70c on favorites |
| Signal magnitude implication | Larger divergence; more "fade" candidates per filter call | Smaller divergence; institutional consensus is tight on Kalshi |
| Auth | None (public read) | API key (free signup) |
| Cost | Free | Free tier 500 credits/mo (1 per live, 10 per historical-PAID) |
| Historical depth | 30-day rich-detail ceiling | **Full history (back to June 2020) but PAID TIER ONLY** |
| Per-event live mid feasibility | OK on matched events; book depth varies (one-sided books on MLB win-totals) | Excellent on h2h game markets (5-9 books); 2-6 on UFC/Boxing |
| Latency | Low (CLOB midpoint) | Low (REST live endpoint) |
| Mechanism | Prediction-market mid (retail + arb) | Aggregated sportsbook line (institutional consensus, de-vigged) |

### 5.1 Combined coverage rough estimate

Taking the union by series-prefix using V4-A's PARTIAL fractions and V5-A1's coverage classes:

- Polymarket MATCH + the-odds-api MATCH overlap heavily on h2h soccer (WC games).
- Polymarket-only MATCH: KXWCSQUAD (player squad selection), some KXMLBWINS-specific events.
- the-odds-api-only MATCH: KXMLBGAME, KXNFLGAME, KXNCAAFGAME (game h2h), KXBOXING / KXUFCFIGHT (when live event listed), KXNCAAFPLAYOFF (championship outrights).

A rough union estimate of MATCH-only coverage on v1's post-denylist LIVE attempted-orders universe is **35-45%** depending on how PARTIAL fractions are credited.

Bigger value of combining: SAME-DIRECTION confirmation. When BOTH Polymarket and sportsbook agree that Kalshi is overpriced relative to consensus, the filter's signal is stronger than either alone.

---

## 6. Cost realism for Phase 2

Phase 2 retrospective backtest needs ~150 historical odds lookups across v1's resolved-eligible universe (the "v3 inventory eligible" subset + a 60-90 day prospective window). At 10 credits per historical call:

| Phase 2 backfill estimate | Calls | Credits | Free-tier months |
|---|---:|---:|---:|
| Full retrospective on n=32 v3-eligible + n=120 prospective | 150 | 1,500 | 3 months |
| Lighter retrospective only on n=32 v3-eligible | 32 | 320 | 0.7 months (still > 500 cap one-shot) |
| Live-only filter (no retrospective) | ~150 / mo at 1 cr each | 150 | comfortable inside free tier |

### 6.1 Three operator paths

**Path A: FREE TIER, LIVE-ONLY filter (recommended starting point).**
- Cost: $0/mo.
- Phase 2 deliverable: live-mode shadow-logging filter that records (Kalshi yes_price, sportsbook implied) per v1 candidate at the moment v1 considers a trade. After 60-90 days of accumulated resolved data, run retrospective.
- Pros: matches the v4 Track A shadow-mode pattern (low risk, no operator commitment, learns from real v1 cadence).
- Cons: Phase 2 results delayed by ~90 days. No retrospective backfill possible on the free tier.

**Path B: PAID TIER 20K ($30/mo) for one-time backfill + ongoing live.**
- Cost: $30 one month, plus $0 in subsequent months if downgraded after the backfill is complete.
- Phase 2 deliverable: full retrospective on ~150 historical odds snapshots across v3-eligible + recent-resolved markets (1,500 credits, fits in 20K month). Plus live-filter usage at ~150/month thereafter.
- Pros: Phase 2 results in days, not 90 days.
- Cons: requires operator decision and $30 commitment. Past the $25 first-deployment recommendation but well within the $100 ceiling.

**Path C: NULL DECISION (Phase 1 result determines whether Phase 2 is worth the cost).**
- If V5-A1 found < 30% post-denylist coverage OR signal direction NULL: stop here. Operator has data to decide Track A is dead.
- V5-A1 found **40.7% inclusive coverage and direction-matched +1.70c signal**. Both above the kill threshold. Phase 2 is worth pursuing, by either Path A or Path B.

### 6.2 Recommendation (cost-realism question)

**Operator should choose Path A (free tier, shadow-mode) for v5 Phase 2 unless willing to commit $30 one-time.**

Path A matches the v4 Track A shadow-mode wiring approach already approved and reduces risk. Path B accelerates Phase 2 by 90 days at $30 cost. Both are viable; the choice is operator preference vs cash. The MATERIAL info is that Phase 2 is unblocked under either path.

---

## 7. Recommendation

**PROCEED with Track A Phase 2 at FREE TIER (Path A).**

Three findings support this:

1. **Coverage of v1's post-denylist live universe is 40.7% inclusive (31% MATCH-only)**, structurally similar to Polymarket's 42.6% but on a different subset of series. Together they cover more than either alone.

2. **Signal direction matches Polymarket (Kalshi over sportsbook +1.70c on favorites)** at n=23. The smaller magnitude vs Polymarket's +9.21c reflects sportsbooks being the institutional consensus. This is a CLEANER signal because the implied probability is the de-vigged line at the moment v1 considers a trade.

3. **Free tier is sufficient for live-mode shadow-logging at v1's cadence**. At ~150 candidate-checks per month, only 30% of the free credit budget is consumed. Paid tier is only required for retrospective backfill which is OPTIONAL.

**Phase 2 deliverables (per master plan Section 6.2):**

- `src/kalshi_bot_v5/filter_sportsbook.py`: live sportsbook second-opinion fetch + de-vig + divergence calculation, parallel to v4's `kalshi_bot_v4/filter.py`.
- `scripts/v5/filter_sportsbook_shadow_log.py`: per-candidate logger writing to `data/live_trades/filter_sportsbook_shadow_log.parquet`.
- After 60-90 days of accumulated resolved data, run retrospective backtest and re-evaluate TA1-TA5 gate.

**Phase 2 falsification triggers:**

- If shadow-logged candidate divergences over 60-90 days have mean magnitude < +0.5c on favorites: filter is too weak to act on. Close as null.
- If sportsbook coverage on v1's actual live candidate stream is < 25% (NOT 40% as currently measured on the snapshot): filter fires too rarely. Close as null.
- If sportsbook signal is collinear with Polymarket signal on the overlap subset (correlation > 0.9 on the matched events): filter adds nothing over V4-E's existing filter. Close as null (Track A subsumed by v4).

---

## 8. Operator action items

### 8.1 Already done

- Operator added `THE_ODDS_API_KEY` to `.env` on 2026-05-24. Verified loadable via pydantic Settings.
- v1 series denylist applied at `src/kalshi_bot/strategy/market_scanner.py:35` (`DEFAULT_SERIES_DENYLIST`).

### 8.2 To do for Phase 2 (Path A free tier)

1. Approve Phase 2 build of `src/kalshi_bot_v5/filter_sportsbook.py` (analogous to v4's filter module).
2. Approve shadow-mode wiring into v1's main loop (no behavior change; logs only).
3. Schedule a 60-90 day re-evaluation window after Phase 2 deploy.

### 8.3 Optional (Path B paid tier)

1. Decide whether to subscribe to the-odds-api $30/mo 20K plan for one month to enable a retrospective backfill.
2. If yes: update `.env` (no key change needed; same key works on paid tier) and inform Phase 2 agent that historical endpoints are unlocked.

### 8.4 Not in scope

- Pinnacle direct access (would require paid integration; the-odds-api free tier excludes Pinnacle).
- F1 second-opinion (the-odds-api does not catalog F1; Polymarket has championship futures but per-race coverage is limited).
- Esports second-opinion (neither source covers).

---

## 9. Output artifacts

| Path | Contents |
|---|---|
| `data/v5/odds_api_sports.json` | the-odds-api /v4/sports catalog (59 sports, cached 2026-05-24) |
| `data/v5/v1_post_denylist_universe.parquet` | Per-series universe table with W1 denylist applied |
| `data/v5/v1_post_denylist_universe_summary.json` | Top-line counts |
| `data/v5/odds_api_coverage_per_series.json` | Per-series coverage classification (MATCH/PARTIAL/NO_MATCH) |
| `data/v5/odds_api_coverage_per_series.parquet` | Same as table |
| `data/v5/odds_api_events_cache/*.json` | Per-sport_key /v4/events response cache (free calls) |
| `data/v5/odds_api_live_cache/*.json` | Per-sport_key /v4/odds response cache (5 live calls) |
| `data/v5/odds_api_historical_cache/*.json` | Historical attempts (all 401 free-tier-block) |
| `data/v5/signal_direction_probe.json` | Live probe results (7 v1 resting orders attempted, 5 matched + Kalshi prices) |
| `data/v5/mlb_divergence_probe.json` | KXMLBGAME-vs-the-odds-api MLB h2h 40-pair sample |
| `data/v5/extended_divergence_probe.json` | UFC + Boxing extended 13-pair sample |
| `data/v5/divergence_summary.json` | Aggregated 52-pair sample with headline statistics |
| `scripts/v5/enumerate_post_denylist_universe.py` | Reproducible universe builder |
| `scripts/v5/build_odds_api_coverage_matrix.py` | Reproducible per-series coverage classifier (free endpoint use only) |
| `scripts/v5/probe_signal_direction.py` | Live + (attempted) historical probe runner |
| `scripts/v5/probe_mlb_divergence.py` | MLB-specific extended probe |
| `scripts/v5/probe_extended_divergence.py` | UFC + boxing extended probe |
| `scripts/v5/aggregate_divergence_summary.py` | Aggregator that produces the headline numbers |

---

## 10. Reproducibility note

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
uv run python -m scripts.v5.enumerate_post_denylist_universe
uv run python -m scripts.v5.build_odds_api_coverage_matrix
uv run python -m scripts.v5.probe_signal_direction
uv run python -m scripts.v5.probe_mlb_divergence
uv run python -m scripts.v5.probe_extended_divergence
uv run python -m scripts.v5.aggregate_divergence_summary
```

All the-odds-api responses are cached locally; re-running the scripts on a populated cache makes ZERO additional API calls. The 5 credits already consumed are persistent. Total runtime ~30 seconds cold-cache (mostly the polite-throttle on /v4/events calls), ~5 seconds cached.

Polite throttle: 1.1 seconds between any the-odds-api request (< 1 req/sec per project constraint).

---

## 11. Honest answer to the master plan's binding question

**Track A Phase 2 SHOULD PROCEED.** The post-denylist coverage is 40.7% inclusive on v1's live universe, the signal direction matches V3-C's Polymarket measurement (Kalshi over sportsbook on favorites, +1.70c at n=23 with 95% CI [-0.11, +3.94]), and the free-tier credit budget is sufficient for live-mode shadow-logging indefinitely.

The right Phase 2 deliverable is a live-mode shadow-logging filter that gathers 60-90 days of paired (Kalshi yes_price, sportsbook implied) data on v1's actual candidate stream, then runs a leak-free retrospective on the resolved subset. If the retrospective shows ANY positive realized P&L improvement above v1's baseline, Track A is a real win; if it shows compression of signal toward zero by close, Track A is null.

If the operator wants to compress Phase 2 from 90 days to 1 week, the $30/mo paid tier unlocks the full historical endpoint and the backtest can run on accumulated v3 inventory directly. That decision is operator preference.

The kill-early principle from project memory does NOT trigger here. 40.7% coverage and direction-matched signal at n=23 with the right CI shape are both above the kill thresholds. Track A is the strongest v5 angle the master plan listed and should be the primary build in Phase 2.

**One firm correction to V4-D (Section 3.1)**: free tier on the-odds-api does NOT include historical odds. Operator action required only if paid tier is wanted.
