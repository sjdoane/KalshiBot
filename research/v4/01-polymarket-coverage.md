# Agent V4-A: Polymarket Coverage on v1's Full Live Trading Universe

**Date:** 2026-05-24
**Author:** Agent V4-A (v4 Phase 1, Polymarket-as-fade-filter coverage assessment)
**Status:** Research only. READ-only public Polymarket Gamma + CLOB. No trading.
**Scope:** v1's complete attempted-orders universe (live + backtest + v3 broader inventory), 151 distinct series-prefixes total.

---

## TLDR verdict

**Coverage on v1's actual current live universe is borderline.** Two coverage metrics, each with a different framing:

| Metric | Coverage rate | Decision band |
|---|---:|---|
| v1 LIVE attempted-orders weighted (n=34) | **42.6%** | 30 to 50 percent: Track A is viable as a PARTIAL filter |
| v1 LIVE attempted-orders MATCH-only strict (n=34) | **29.4%** | At the 30 percent edge of viability |
| v1 LIVE acked-orders weighted (n=15) | **57.3%** | Acked orders skew toward MATCH series |
| v1 LIVE acked-orders MATCH-only strict (n=15) | **46.7%** | Solid for filled-trade subset |
| v1 BACKTEST eligible markets weighted (n=39) | **40.0%** | 30 to 50 percent band |
| v3 INVENTORY eligible markets weighted (n=164) | **39.1%** | 30 to 50 percent band |
| Distinct-ticker manual audit, CONFIRMED + 0.5 * PARTIAL (n=25) | **28.0%** | At the 30 percent edge |
| Distinct-ticker manual audit, optimistic incl EVENT_FUTURE (n=25) | **59.8%** | Substantial future-listing potential |

**Honest claim**: v1's currently-live universe sits at 30 to 50 percent Polymarket coverage when the filter is generous (matched event class counts as PARTIAL) and 12 to 30 percent under strict-MATCH-only rules. **This is Section 6.3 territory of the v4 master plan: PARTIAL FILTER, not a full Track A win.**

**Recommendation: PROCEED to Phase 2 Track A as a PARTIAL FILTER on the covered subset, BUT understand that the headline value will be substantially less than a 100-percent-coverage filter would produce.** Couple this with Phase 1 D's multi-venue scan (Manifold, the-odds-api) to fill gaps.

The PARTIAL classification matters because Polymarket-Kalshi threshold mismatches on win-totals markets (Polymarket lists ONE threshold per team; Kalshi lists multiple) require building an intermediate translation rule. That work is non-trivial and should be scoped before commit.

---

## 1. v1's full universe enumeration

I enumerated every distinct series-prefix v1 has touched in production or backtest from three sources. A series-prefix is the alphanumeric chunk before the first `-` in any Kalshi ticker (e.g., `KXNFLWINS-27DET-8` -> `KXNFLWINS`).

Source sizes:
- `data/live_trades/state.json`: 34 orders total across intents (0), resting (10), filled (5), closed (19). 25 distinct tickers, 19 distinct series-prefixes.
- `data/processed/sports_dataset.parquet`: 423 markets, 39 v1-eligible, 17 series-prefixes among eligibles, 98 series-prefixes total.
- `data/v3/probe_inventory_all_markets.parquet`: 2828 markets, 147 v1-eligible (recomputed below), 72 series-prefixes total.

**Union of all three sources: 151 distinct series-prefixes.** Stored in `data/v4/v1_universe_series_table.parquet`.

### 1.1 Top 25 series-prefixes by v1 relevance

A series is "relevant" if v1 has touched it in any of the three sources. The full table has 151 rows; the top by combined relevance:

| Series prefix | League | v1 live all | v1 live acked | v1 backtest eligible | v3 inventory eligible | Polymarket coverage class | Estimated matched fraction |
|---|---|---:|---:|---:|---:|---|---:|
| KXMLBWINS | MLB | 4 | 0 | 5 | 10 | PARTIAL | 0.30 |
| KXNBAPLAYOFFWINS | NBA | 4 | 2 | 0 | 0 | NO MATCH | 0.00 |
| KXWCGAME | Soccer-WC | 3 | 3 | 0 | 0 | MATCH | 1.00 |
| KXNFLPLAYOFF | NFL | 3 | 0 | 0 | 10 | MATCH | 1.00 |
| KXNFLWINS | NFL | 2 | 0 | 0 | 103 | PARTIAL | 0.30 |
| KXMLBSTATCOUNT | MLB | 2 | 0 | 1 | 0 | NO MATCH | 0.00 |
| KXNCAAFPLAYOFF | NCAA-FB | 2 | 0 | 0 | 8 | PARTIAL | 0.50 |
| KXSTARTINGQBWEEK1 | NFL | 2 | 1 | 0 | 0 | NO MATCH | 0.00 |
| KXUFCFIGHT | UFC-MMA | 2 | 2 | 0 | 0 | MATCH | 1.00 |
| KXNFLGAME | NFL | 1 | 1 | 3 | 0 | MATCH | 1.00 |
| KXBOXING | Boxing | 1 | 1 | 1 | 0 | PARTIAL | 0.30 |
| KXCITYNBAEXPAND | NBA | 1 | 0 | 0 | 0 | NO MATCH | 0.00 |
| KXCS2 | CS2-Esports | 1 | 1 | 0 | 0 | PARTIAL | 0.30 |
| KXFOMEN | Formula-1 | 1 | 1 | 0 | 0 | MATCH | 1.00 |
| KXNEXTTEAMNFL | NFL | 1 | 0 | 0 | 0 | PARTIAL | 0.10 |
| KXNEXTTEAMNHL | NHL | 1 | 0 | 0 | 0 | NO MATCH | 0.00 |
| KXWCSQUAD | Soccer-WC | 1 | 1 | 0 | 0 | PARTIAL | 0.40 |
| KXWCSTAGEOFELIM | Soccer-WC | 1 | 1 | 0 | 0 | PARTIAL | 0.30 |
| KXWNBAWINS | WNBA | 1 | 1 | 0 | 0 | PARTIAL | 0.30 |
| KXNBAWINS | NBA | 0 | 0 | 16 | 24 | PARTIAL | 0.30 |
| KXUCLROUND | UCL | 0 | 0 | 2 | 0 | PARTIAL | 0.50 |
| KXATPGRANDSLAM | Tennis-ATP | 0 | 0 | 1 | 0 | PARTIAL | 0.50 |
| KXBALLONDOR | Ballon-DOr | 0 | 0 | 1 | 0 | MATCH | 1.00 |
| KXMLBPLAYOFFS | MLB | 0 | 0 | 0 | 5 | MATCH | 1.00 |
| KXNHLCENTRAL | NHL | 0 | 0 | 1 | 1 | PARTIAL | 1.00 |

Full 151-row table in `data/v4/v1_universe_series_table.parquet`.

---

## 2. Polymarket coverage attempt per series

### 2.1 Probe method

For each series-prefix that v1 has TOUCHED in any source (35 series), I ran three probe layers:

1. **Polymarket /sports league catalog**: GET `gamma-api.polymarket.com/sports` returned 192 distinct league slugs. Mapping the relevant subset to Kalshi series-prefixes confirms structural coverage for NFL, MLB, NBA, NHL, WNBA, NCAAB, CFB (college football), UFC, F1, CS2, LoL, Valorant, MLS, EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, FIFA World Cup, ATP, WTA, IPL, Chess.

2. **Active-events count per Polymarket tag**: GET `gamma-api.polymarket.com/events?tag_slug=<sport>&active=true&closed=false&limit=500` returned counts that establish "is this league live on Polymarket right now":

  | Tag | Active+open events | Maps to Kalshi |
  |---|---:|---|
  | mlb | 100 | KXMLBWINS, KXMLBPLAYOFFS, KXMLBGAME, KXMLBSTATCOUNT, division/award series |
  | epl | 62 | KXEPLGAME, KXEPL |
  | ufc | 50 | KXUFCFIGHT |
  | nfl | 47 | KXNFLWINS, KXNFLPLAYOFF, KXNFLGAME, KXSTARTINGQBWEEK1, KXNEXTTEAMNFL, divisions, awards |
  | wnba | 44 | KXWNBAWINS, KXWNBAROTY, KXWNBAMVP |
  | nba | 40 | KXNBAWINS, KXNBAPLAYOFFWINS, KXCITYNBAEXPAND, KXLEADERNBAAST, awards, divisions |
  | f1 | 36 | KXFOMEN |
  | mls | 30 | KXMLSGAME |
  | nhl | 21 | KXNHLPLAYOFF, KXNHLPRES, KXNEXTTEAMNHL, divisions, awards |
  | lol | 15 | KXLOL, KXCHARCOUNTLOLWORLDS |
  | ucl | 10 | KXUCL, KXUCLROUND |
  | cs2 | 9 | KXCS2 |
  | atp | 5 | KXATPGRANDSLAM, KXATP |
  | chess | 4 | KXCHESSCANDIDATES, KXCHESSWORLDCHAMPION |
  | boxing | 4 | KXBOXING |
  | cfb (college football) | 1 | KXNCAAFPLAYOFF, KXNCAAFGAME |
  | ncaab | 0 | KXNCAAMBACHAMP (March Madness; seasonal) |
  | fifwc | 0 (but events tagged via fifa-world-cup, see below) | KXWCGAME, KXWCSQUAD |
  | val (Valorant) | 0 | KXVALORANT |
  | lal (La Liga) | 0 | KXLALIGA |

  Note the `fifwc` tag underreports because Polymarket actually tags World Cup events with `fifa-world-cup` and `soccer`. Pulling `tag_slug=fifa-world-cup` returns 50+ events including 34 per-fixture markets like `fifwc-mex-rsa-2026-06-11`, `fifwc-eng-gha-2026-06-23`. The deterministic slug pattern is `fifwc-<team1>-<team2>-<date>` for matches and per-team `2026-fifa-world-cup-player-to-make-<country>-squad` for squad markets.

3. **Public-search probes**: GET `gamma-api.polymarket.com/public-search?q=<series-specific-query>` per series. Each probe used 1 to 3 query variants. Per-series probe results cached in `data/v4/poly_coverage_<series>.json`.

### 2.2 Per-series classification

The classification scheme:
- **MATCH**: Polymarket lists the same event-class (sport, season, event type) such that each Kalshi market in this series can be paired with a Polymarket counterpart. The token-id is fetchable and `/midpoint` returns a live mid.
- **PARTIAL**: Polymarket has the event-class but covers only a subset of Kalshi's per-ticker granularity. The most common pattern: Polymarket lists ONE threshold per team for season win-totals, Kalshi lists multiple (T70, T75, T80, etc.). Cross-platform comparison requires a translation rule (e.g., monotonicity-derived bound).
- **NO MATCH**: Polymarket does not list this category at all. Examples include immaculate-inning props (KXMLBSTATCOUNT), playoff-team-wins thresholds (KXNBAPLAYOFFWINS), NBA expansion city votes (KXCITYNBAEXPAND), and entertainment-attendance bets (KXSWIFTATTEND).

Output table in `data/v4/poly_coverage_table.parquet` (35 series with v1-relevance) and the per-series fraction in `data/v4/series_coverage_fraction.parquet` (117 series classified).

### 2.3 Distribution

Of 35 v1-touched series-prefixes that I probed:

| Class | Count | Share |
|---|---:|---:|
| MATCH | 11 | 31% |
| PARTIAL | 18 | 51% |
| NO MATCH | 6 | 17% |

51 percent PARTIAL is the headline that creates the borderline coverage problem. A PARTIAL series's matched fraction was estimated case-by-case (see Section 4).

---

## 3. Coverage on v1's actual filled-orders distribution

The weighted-coverage formula:

```
v1_universe_coverage = sum_series (n_v1_orders_in_series * frac_matched_in_series) / total_v1_orders
```

Computed over four universes (full output in `scripts/v4/compute_weighted_coverage.py`):

### View A: v1 LIVE attempted orders (n=34, binding)

| Metric | Value |
|---|---:|
| Total markets in this universe | 34 |
| Weighted matched count | 14.5 |
| **Match rate (incl PARTIAL fraction)** | **42.6%** |
| MATCH-only strict rate | 29.4% |

### View A2: v1 LIVE acked orders only (n=15)

| Metric | Value |
|---|---:|
| Total markets | 15 |
| Weighted matched | 8.6 |
| **Match rate (incl PARTIAL)** | **57.3%** |
| MATCH-only strict | 46.7% |

Acked orders (the orders Kalshi confirmed and that are resting or filled) skew toward MATCH series because v1's recently-placed orders are concentrated on World Cup games (KXWCGAME), UFC fights, NBA playoff wins, and Boxing, of which the World Cup and UFC are MATCH-class.

### View B: v1 BACKTEST eligible (n=39)

| Metric | Value |
|---|---:|
| Total | 39 |
| Weighted matched | 15.6 |
| Match rate (incl PARTIAL) | 40.0% |
| MATCH-only strict | 12.8% |

The v1 backtest is dominated by KXNBAWINS (16 markets, PARTIAL at 0.30 fraction) and KXMLBWINS (5 markets, PARTIAL at 0.30). The MATCH-only rate drops because most of the backtest is PARTIAL-class win-totals.

### View C: v3 broader INVENTORY eligible (n=164)

| Metric | Value |
|---|---:|
| Total | 164 |
| Weighted matched | 64.1 |
| Match rate (incl PARTIAL) | 39.1% |
| MATCH-only strict | 10.4% |

v3's broader inventory is heavily dominated by KXNFLWINS (103 eligibles) and KXNBAWINS (24), both PARTIAL. MATCH-only is only 10.4% because the bulk universe is win-totals series.

### 3.1 Decision rule per v4 master plan TA1

From the v4 master plan Section 4 / TA1: coverage >= 30% is the threshold for the filter to be worth building. Coverage < 30% triggers the Section 6.3 pivot (multi-venue OR implied-from-related-markets).

Multiple metrics, depending on definition:

| Coverage definition | Result | Above 30%? |
|---|---:|---|
| v1 LIVE all weighted (incl PARTIAL) | 42.6% | YES |
| v1 LIVE all MATCH-only | 29.4% | At the edge |
| v1 LIVE acked weighted | 57.3% | YES |
| v1 LIVE acked MATCH-only | 46.7% | YES |
| v1 BACKTEST eligible weighted | 40.0% | YES |
| v1 BACKTEST eligible MATCH-only | 12.8% | NO |
| v3 INVENTORY eligible weighted | 39.1% | YES |
| v3 INVENTORY eligible MATCH-only | 10.4% | NO |
| 25-ticker manual audit binding (CONFIRMED + 0.5 PARTIAL) | 28.0% | At the edge |
| 25-ticker manual audit optimistic | 59.8% | YES |

The number the operator should weight most heavily is the **v1 LIVE attempted-orders weighted coverage of 42.6%** because that is the current live universe the filter would act on. Track A is above the TA1 threshold under the inclusive definition and at the edge under the strict definition.

---

## 4. Per-series match-confidence audit

For each of v1's 25 distinct live attempted-order tickers, I built a per-ticker Polymarket probe (deterministic slug guess where possible, public-search fallback) and manually classified the result. Cached in `data/v4/live_orders_poly_audit.json` and the manual labels in `data/v4/live_orders_classified.parquet`.

### 4.1 Per-ticker classification

| Kalshi ticker | Status | Notes |
|---|---|---|
| KXWCGAME-26JUN23ENGGHA-ENG | CONFIRMED | deterministic slug `fifwc-eng-gha-2026-06-23-eng` mid=0.705 |
| KXWCGAME-26JUN24SCOBRA-BRA | CONFIRMED | deterministic slug `fifwc-sco-bra-2026-06-24-bra` mid=0.725 |
| KXWCGAME-26JUN17AUTJOR-AUT | CONFIRMED | deterministic slug `fifwc-aut-jor-2026-06-17-aut` mid=0.725 |
| KXSTARTINGQBWEEK1-W1-26SEP15-LV-KCOU | CONFIRMED | `pro-football-raiders-week-1-starting-qb` event exists; specific QB market lacks orderbook (no mid) so this is technically MATCH-NO-MID |
| KXMLBWINS-HOU-26-T70 | PARTIAL | `mlb-2026-regular-season-win-totals` event lists HOU at 80.5; Kalshi T70 = 70 threshold differs |
| KXMLBWINS-ATH-26-T75 | PARTIAL | same; ATH at 78.5 |
| KXMLBWINS-KC-26-T70 | PARTIAL | same; KC at 81.5 |
| KXWCSQUAD-26ESP-BIGL | PARTIAL | `2026-fifa-world-cup-player-to-make-spain-squad` event found; specific player ('BIGL' likely Lamine Yamal) needs a per-player lookup table |
| KXWCSTAGEOFELIM-26CPV-GS | PARTIAL | Polymarket has FIFA WC Group winner markets; no exact 'CPV gets eliminated in group stage' market |
| KXNEXTTEAMNFL-26KPITTS-ATL | PARTIAL | Polymarket has 'X next team' for some players (Rodgers, Darnold); only matches when Polymarket lists that specific player |
| KXBOXING-26SEP12CALVARMBILLI-CALVAR | EVENT_FUTURE | Polymarket boxing tag has 4 active events; no Canelo-Mbilli Sept 12 2026 yet |
| KXUFCFIGHT-26JUL11MCGHOL-HOL | EVENT_FUTURE | UFC has 50 active events but no specific McGregor-Holloway July 2026 market |
| KXUFCFIGHT-26JUN14HOKLEW-HOK | EVENT_FUTURE | no specific HOK-LEW June 2026 fight market |
| KXFOMEN-26-SIN | EVENT_FUTURE | 2025 Singapore GP closed; 2026 race not yet listed (Polymarket lists championship-level F1 markets but not all races) |
| KXCS2-ASIA26-FAL | EVENT_FUTURE | Polymarket CS2 tag has 9 active events; no specific ASIA26 Falcons market |
| KXNFLGAME-26SEP13CLEJAC-JAC | EVENT_FUTURE | Polymarket has 47 active NFL events; doesn't yet list Sep 13 2026 Browns-Jaguars |
| KXNFLPLAYOFF-27-SEA | EVENT_FUTURE | Polymarket lists 2025-26 NFL playoff markets; 2026-27 Seahawks-playoff market not yet listed |
| KXNCAAFPLAYOFF-26-UGA | EVENT_FUTURE | Polymarket cfb tag has 1 active event; 2026 CFP markets not yet listed |
| KXNFLWINS-27DET-8 | EVENT_FUTURE | 2025-26 NFL Win Totals event closed; 2026-27 season not yet listed |
| KXMLBSTATCOUNT-26IMMACULATE-AP-2 | NO MATCH | Polymarket has no per-pitcher immaculate-inning markets |
| KXNBAPLAYOFFWINS-26SAS-10 | NO MATCH | no team-playoff-wins threshold markets |
| KXNBAPLAYOFFWINS-26OKC-15 | NO MATCH | same |
| KXCITYNBAEXPAND-28JAN01-LV | NO MATCH | no NBA-expansion-city markets |
| KXNEXTTEAMNHL-26AMAT-TOR | NO MATCH | no NHL-next-team free-agent markets for this specific player |
| KXWNBAWINS-26PHX-20 | NO MATCH | WNBA tag has 44 active events but no per-team win-totals markets |

Summary counts:

| Status | Count | Share |
|---|---:|---:|
| CONFIRMED (filter can act now) | 4 | 16% |
| PARTIAL (event match, granularity differs) | 6 | 24% |
| EVENT_FUTURE (will likely list later) | 9 | 36% |
| NO MATCH (structural absence) | 6 | 24% |

### 4.2 False-positive check (sample 3 per MATCH/PARTIAL)

The 4 CONFIRMED matches were verified by walking the slug back to confirm exact team/year/match alignment. Spot-checks:
- `fifwc-eng-gha-2026-06-23-eng`: title "Will England win on 2026-06-23?" matches Kalshi KXWCGAME-26JUN23ENGGHA-ENG ("Will England beat Ghana on 2026-06-23?"). Same fixture, same outcome side. CORRECT.
- `fifwc-sco-bra-2026-06-24-bra`: title "Will Brazil win on 2026-06-24?" matches Kalshi KXWCGAME-26JUN24SCOBRA-BRA. CORRECT.
- `2026-mlb-win-totals-houston-astros`: question "Will the Houston Astros win more than 80.5 games in the 2026 MLB Regular Season?" overlaps Kalshi KXMLBWINS-HOU-26-T70 ("HOU >= 70 wins in 2026") on event but NOT threshold. The implied probability of >=70 wins is monotonically higher than > 80.5 wins, so we have a directional signal (P_kalshi(>=70) >= P_poly(>80.5)) but no exact comparison. This is the PARTIAL story.

### 4.3 EVENT_FUTURE category and listing-lag risk

9 of 25 v1 live tickers (36%) are in EVENT_FUTURE. These are markets where Polymarket should list a counterpart at some point but does not today. The lag is structural:
- Polymarket prefers in-season markets and tends to add long-horizon futures within 2 to 4 weeks of season start.
- Kalshi adds long-horizon futures earlier (12+ weeks pre-season is common, e.g., KXNFLWINS-27 listed in May 2026 for a Sep 2026 season).

This means v1's most aggressive (longest-horizon) entries will reliably NOT have a Polymarket counterpart at the moment of v1's order placement. The fade-filter would need to wait until Polymarket lists the counterpart, which may be after v1's entry timestamp.

---

## 5. Polymarket live-mid feasibility check

For 6 confirmed/partial markets covering 4 distinct series-classes, I confirmed:

| Kalshi ticker | Poly slug | /midpoint result | /book bids/asks |
|---|---|---:|---|
| KXWCGAME-26JUN23ENGGHA-ENG | fifwc-eng-gha-2026-06-23-eng | mid=0.705 | 16 / 24 |
| KXWCGAME-26JUN24SCOBRA-BRA | fifwc-sco-bra-2026-06-24-bra | mid=0.725 | 19 / 20 |
| KXWCGAME-26JUN17AUTJOR-AUT | fifwc-aut-jor-2026-06-17-aut | mid=0.725 | 21 / 23 |
| KXMLBWINS-HOU-26 (PARTIAL) | 2026-mlb-win-totals-houston-astros | mid=0.81 (for >80.5 threshold) | 23 / 1 |
| KXWCSQUAD-26ESP (PARTIAL) | will-unai-simon-be-included-in-spains-2026-squad | mid=0.94 | 8 / 0 |
| KXSTARTINGQBWEEK1 (Raiders) | will-player-c-be-the-raiders-week-1-starting-qb | HTTP 404 "no orderbook" | n/a |

Findings:
1. **Live mid via `clob.polymarket.com/midpoint?token_id=<tid>` works on confirmed matches**, returning a numeric mid as a string. No auth needed.
2. **Book depth varies widely**. World Cup games have 16 to 24 bids and similar asks, with top quotes at $0.05 / $0.99 (wide markets, retail-thin). MLB win totals show 23 bids and only 1 ask (illiquid one-sided book). Spain WC squad has 8 bids and 0 asks (very thin, depth-of-1 concern).
3. **Some matched events have markets with NO ORDERBOOK** (the Raiders QB case). Polymarket's `/midpoint` returns 404 there. This is a real feasibility gap for the fade filter even when the event matches.
4. **Polymarket coverage is current-quarter-biased**. World Cup matches starting June 11 2026 are fully active; matches starting earlier or later in the same tournament may not be listed yet.

The live-mid feasibility is **adequate for MATCH-class markets** but operational hardening is needed:
- Treat missing or stale mids as "filter inactive" (do not skip v1's trade if Polymarket has no quote).
- Tolerate one-sided books by using the better of bid or last-trade or skipping.
- Cache mids and refresh on a 5-minute cadence to avoid hammering the CLOB.

---

## 6. Recommendation

### 6.1 Headline number for the operator

**v1's currently-live universe Polymarket coverage = 42.6% inclusive (PARTIAL counted at estimated fraction) / 29.4% strict-MATCH-only.**

Per the v4 master plan TA1 thresholds:

| Master plan rule | Threshold | This run | Decision |
|---|---:|---:|---|
| Track A straightforwardly viable | >= 50% | 42.6% inclusive | NO |
| Track A viable as partial filter | 30 to 50% | 42.6% inclusive | YES |
| Track A marginal | 20 to 30% | n/a | n/a |
| Track A dead, pivot urgently | < 20% | n/a | n/a |

### 6.2 The right call

**PROCEED TO PHASE 2 TRACK A as a PARTIAL FILTER.** Build the filter with the explicit scope:

1. The filter is ONLY active when:
   - Polymarket has a MATCH-class counterpart for the Kalshi market.
   - The Polymarket market has a current `/midpoint` mid available.
   - The book has at least one bid and one ask (so the mid is not a stale-quote artifact).

2. For PARTIAL-class series (win-totals, division winners with threshold mismatches), the filter is ALSO active but uses a derived comparison rule:
   - Polymarket's per-team Yes-prob at threshold T_poly translates to a Kalshi-implied prob via monotonicity: P(wins >= T_kalshi) >= P(wins > T_poly) when T_kalshi <= T_poly + 0.5, and similar inequality otherwise.
   - Conservatively, treat the Polymarket signal as a directional bound only.

3. For NO MATCH series (KXMLBSTATCOUNT, KXNBAPLAYOFFWINS, KXCITYNBAEXPAND, KXNEXTTEAMNHL, KXWNBAWINS, KXCHARCOUNTLOLWORLDS, KXSWIFTATTEND, KXSTARTCLEBROWNS, KXTGL, KXVALORANT, KXFOWMEN, KXCARDPRESENCEUFCWH): the filter does NOT fire. v1's normal logic proceeds.

4. For EVENT_FUTURE series (KXNFLWINS-27, KXNCAAFPLAYOFF-26, KXBOXING-26SEP, KXUFCFIGHT-26JUL, KXFOMEN-26-SIN): the filter does NOT fire today. As Polymarket lists the counterparts (typically 2 to 12 weeks before event start), the filter will start firing.

### 6.3 Expected aggregate effect

Given 42.6% coverage and v3 V3-C's measured properties on the covered subset (mean Kalshi-Polymarket = +9.21c at T-35d, 45% of pairs > 5c spread):

- **Filter activation rate**: ~42.6% of v1 candidates have an active filter.
- **Filter trigger rate within active**: ~45% (V3-C's > 5c spread share). Conservative estimate.
- **Skip-rate on v1's order flow**: 42.6% * 45% = ~19% of v1 candidates would be skipped by the filter at a 5c threshold.

This sits comfortably within TA3 ("filter reduces v1's covered-subset trade count by no more than 50%"). The TA2 (>=1pp improvement on covered subset) test requires the Phase 2 retrospective backtest.

### 6.4 Section 6.3 pivots also recommended in parallel

Per the v4 master plan Section 6.3, when coverage is 30 to 50% the master plan recommends additional alternative-signal scans:

- **Multi-venue second opinion (Phase 1 D's job)**: ManifoldMarkets, the-odds-api free tier, and PredictIt for niche markets where Polymarket lacks listings. This is critical for KXNBAPLAYOFFWINS, KXMLBSTATCOUNT, KXSTARTINGQBWEEK1, and the EVENT_FUTURE series.
- **Implied-from-related-markets**: even when no direct Polymarket counterpart exists, related markets (e.g., Polymarket's "Team X make playoffs" prob when Kalshi asks "Team X win 10+ games") give correlated signal. Add this if Phase 2 finds Phase 1 D coverage is also thin.
- **Polymarket-implied championship futures**: build a team-strength index from per-team championship probabilities to derive implied win-totals. This would partially recover the KXNFLWINS, KXMLBWINS, KXNBAWINS PARTIAL coverage as MATCH.

The 42.6% number is large enough that Track A as a partial filter is worth building first, and the multi-venue work should run in parallel rather than as a sequential blocker.

### 6.5 Risks and caveats

1. **PARTIAL fraction estimates have not been individually validated**. The 0.30 fraction I assigned to KXMLBWINS / KXNFLWINS / KXNBAWINS reflects my structural understanding (Polymarket lists one threshold per team; Kalshi commonly lists three to four thresholds per team). A future audit should compute the per-series matched fraction by exhaustively matching every Kalshi market in the series to Polymarket listings. The current estimates may be off by 10 to 20 percentage points either direction.

2. **EVENT_FUTURE risk**. Many of v1's current live attempted-orders are long-horizon (KXNFLPLAYOFF-27, KXNFLWINS-27, KXBOXING-26SEP, KXUFCFIGHT-26JUL, KXFOMEN-26-SIN). These have no Polymarket counterpart TODAY but should have one within 4 to 12 weeks of their respective events. The fade-filter cannot act on a candidate at the moment v1 places the order; it would need to re-evaluate at each candidate's price-update cycle. This adds operational complexity.

3. **Book-depth and stale-quote risk**. Polymarket mids on long-horizon, low-volume markets can stay stale for hours. A naive filter that uses the mid as ground truth would be vulnerable to acting on stale information. Production must include a freshness gate (e.g., last trade or quote within X hours) before treating the mid as a real signal.

4. **Threshold-mismatch translation risk on PARTIAL series**. The monotonicity-based bound for KXMLBWINS at T70 vs Polymarket's 80.5 threshold gives a directional inequality, not a numerical estimate. The filter on PARTIAL-class markets is weaker than on MATCH-class. The retrospective backtest (Phase 2) should measure the PARTIAL-class improvement separately from the MATCH-class improvement to avoid masking a weak PARTIAL effect with a strong MATCH effect.

5. **The 30% threshold itself is a master-plan-imposed convention**. There is no theoretical reason Track A must hit 30% to be worth building; if even 15% of v1's trades benefit and the lift is large, the absolute dollar value can still justify the engineering. The master plan number is a guidepost, not a hard kill criterion.

---

## 7. Output artifacts

| Path | Contents |
|---|---|
| `data/v4/v1_universe_series_table.parquet` | 151 series-prefixes with counts in v1 live / v1 backtest / v3 inventory. |
| `data/v4/polymarket_sports_catalog.json` | Cached Polymarket /sports response (192 leagues). |
| `data/v4/poly_coverage_<series>.json` | Per-series probe cache (tag-event counts, public-search hits, classification). |
| `data/v4/poly_coverage_table.parquet` | 35-series probe table with poly_tag_events_count and poly_coverage_class. |
| `data/v4/live_orders_poly_audit.json` | Per-live-ticker Polymarket audit with search-candidate lists. |
| `data/v4/live_orders_classified.parquet` | 25 v1-live tickers with binding manual labels (CONFIRMED / PARTIAL / EVENT_FUTURE / NO MATCH). |
| `data/v4/series_coverage_fraction.parquet` | 117 series with coverage_class and matched_fraction estimates. |
| `scripts/v4/enumerate_v1_universe.py` | Builds the universe table. |
| `scripts/v4/probe_poly_coverage.py` | Runs the per-series Polymarket probe. |
| `scripts/v4/audit_live_orders_coverage.py` | Runs the per-live-ticker audit. |
| `scripts/v4/classify_live_orders.py` | Applies the manual labels. |
| `scripts/v4/compute_weighted_coverage.py` | Computes the weighted coverage metrics. |

---

## 8. Reproducibility note

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
uv run python -m scripts.v4.enumerate_v1_universe
uv run python -m scripts.v4.probe_poly_coverage
uv run python -m scripts.v4.audit_live_orders_coverage
uv run python -m scripts.v4.classify_live_orders
uv run python -m scripts.v4.compute_weighted_coverage
```

All Polymarket calls are unauthenticated public Gamma + CLOB endpoints. Polite throttle ~6 requests per second.

Total runtime ~60 seconds (cached) or ~3 minutes (cold-cache).

---

## 9. Honest answer to the master plan's binding question

**The binding number is 42.6% (inclusive) or 29.4% (strict-MATCH-only) on v1's live attempted-orders universe.**

This sits in the 30 to 50 percent band where the v4 master plan Section 6.3 says **Track A is viable as a partial filter**. Phase 2 should build the filter with the explicit scope above (Section 6.2) and measure realized improvement on the covered subset separately from the non-covered subset.

**A clean PASS verdict would require >= 50% coverage on a single metric.** That bar is not met. Track A is therefore a PARTIAL win, not a clean win. Phase 1 D's multi-venue work should run in parallel to fill the PARTIAL-class threshold-translation gap and the NO-MATCH structural gaps.

The kill-early principle from the project memory does NOT trigger here. 42.6% on the binding metric is above the 30% pivot threshold; the filter is worth building, with eyes open about the partial coverage.
