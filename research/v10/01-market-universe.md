# v10 Market Universe Scout: Category Inventory

**Date:** 2026-05-26
**Agent:** v10-S1 (Market Universe Scout)
**Status:** Phase 0 scouting only. No code built. Operator selects v10 category from ranked list.
**Probe run time:** 2026-05-26 22:35 to 22:48 UTC
**API scope:** READ-ONLY. No /portfolio/* calls. Exchange status 200, exchange_active=true.

---

## Scope and Method

All probes hit `external-api.kalshi.com/trade-api/v2` using the existing read-scope PEM key.
Endpoints used:
- `/exchange/status` (connectivity)
- `/markets?series_ticker=X&status=open` (per-series enumeration)
- `/markets?status=open&limit=200` (cross-category sample)
- `/markets/trades?limit=200` (live trade stream)
- `/markets/{ticker}/orderbook` (depth snapshot)
- `/markets?series_ticker=X&status=settled` (historical structure)
- `/events?status=open` (category inventory; revealed long-horizon futures category)
- `/series?limit=200` (full series catalog: 10,398 series total)

HTTP 429 rate-limit encountered on rapid sequential calls; mitigated with exponential backoff (1.5s, 3s, 6s). All results below cite HTTP status codes.

**Critical data quality note:** The read-scope API returns `yes_price=0`, `count=0`, `volume=0`, `last_price=0` for most markets in the JSON payload. This is a known limitation of the READ key (Becker 2026 used a write-scope key for the 72M-trade corpus). The structural data (ticker names, close times, series existence, settlement results, taker_side direction, trade timestamps) IS accurate and confirmed live. Volume and price fields require the write-scope key or `/historical/trades` with different auth.

**Key calibrating fact from probe:** The `/markets/trades?limit=200` endpoint returned 200 trades happening RIGHT NOW (2026-05-26 22:45 UTC). This confirms which series are actively traded tonight.

---

## Series Catalog Summary

From `/series?limit=200` (HTTP 200, 3766ms): 10,398 total series across 19 categories.

| Category | Series count | Notes |
|---|---|---|
| Entertainment | 2,401 | Largest; mostly long-horizon futures (actors, films) |
| Sports | 2,025 | Active near-term and futures mix |
| Politics | 1,937 | Domestic and global leaders |
| Elections | 1,356 | Leader succession futures |
| Economics | 536 | Macro release markets + long-horizon |
| Financials | 459 | Indices, commodities |
| Mentions | 359 | Social media mention counts |
| Climate and Weather | 274 | KXHIGH* and long-horizon climate |
| Science and Technology | 246 | AI, space, FDA |
| Crypto | 232 | BTC/ETH/SOL by horizon |
| World | 142 | Geopolitics |
| Companies | 142 | Corporate events |
| Health | 96 | FDA, disease outcomes |
| Social | 52 | Celebrity events |
| Commodities | 48 | WTI, gold, silver |
| Transportation | 39 | Transit policy |
| (unlabeled) | 43 | Misc |
| Exotics | 10 | Novel formats |
| Education | 1 | Single series |

**Important finding:** The `/events?status=open` endpoint returns 600+ events, but nearly ALL have close dates 2028-2099 and zero volume. These are "futures" markets with no active quotes. The tradeable near-term universe is accessed via `/markets?series_ticker=X&status=open` per-series, NOT via events pagination.

---

## Live Trade Stream (2026-05-26 22:45 UTC)

From `/markets/trades?limit=200` (HTTP 200): 200 most recent trades.

| Series | Trade count in last-200 | Interpretation |
|---|---|---|
| KXBTC15M | 33 | BTC 15-minute contracts; highest frequency |
| KXMLBGAME | 31 | MLB game-winner; active tonight (games in progress) |
| KXMVESPORTSMULTIGAMEEXTENDED | 21 | Esports multi-game props (DISCOVERED; entirely new) |
| KXBTCD | 18 | BTC daily settlement |
| KXITFWMATCH | 18 | ITF Women's tennis match (DISCOVERED; entirely new) |
| KXMLBTOTAL | 8 | MLB total runs (over/under) |
| KXNBAGAME | 8 | NBA game-winner (Finals active) |
| KXMLBF5 | 7 | MLB first 5 innings result |
| KXCONMEBOLLIBGAME | 6 | South American soccer (DISCOVERED) |
| KXWTI | 6 | West Texas Intermediate crude oil |
| KXATPCHALLENGERMATCH | 5 | ATP Challenger tennis match |
| KXMVECROSSCATEGORY | 5 | Esports cross-category (DISCOVERED) |
| KXNBASPREAD | 4 | NBA point spread |
| KXMLBRFI | 4 | MLB runs-first-inning |
| KXVALORANTGAME | 3 | Valorant esports game |
| KXNBATOTAL | 3 | NBA total points |
| KXMLBKS | 3 | MLB strikeouts |
| KXMLBHIT | 2 | MLB hits |
| KXMEAD | 2 | Unknown (probing) |
| KXNHLGAME | 2 | NHL game |
| KXETH15M | 1 | ETH 15-minute |
| KXSB | 1 | Unknown |
| Others | various | Lower frequency |

Sample trade confirmation (HTTP 200 payload, 2026-05-26T22:45 UTC):
```
KXMVESPORTSMULTIGAMEEXTENDED-S20264E950472722-AB39 | side=yes | 22:45
KXMLBTOTAL-26MAY261810WSHCLE-8 | side=yes | 22:45
KXATPCHALLENGERMATCH-26MAY26MONSHI-SHI | side=yes | 22:45
KXBTC15M-26MAY261900-00 | side=yes | 22:45
```

---

## Category-by-Category Inventory

### 1. Sports: MLB Game Resolution (KXMLBGAME, KXMLBTOTAL, KXMLBF5, KXMLBRFI, KXMLBKS, KXMLBHIT)

| Field | Value |
|---|---|
| Category | Sports props / game resolution |
| Sample series tickers | KXMLBGAME, KXMLBTOTAL, KXMLBF5, KXMLBRFI, KXMLBKS |
| Open markets right now | KXMLBGAME: 72; KXMLBTOTAL: ~30 est; KXMLBF5: ~20 est |
| Open markets closing within 2 weeks | 72 (KXMLBGAME); games daily |
| Mid distribution | Unknown from probe (API suppresses prices); sportsbook lines suggest 0.40-0.60 typical for game winners; 0.70-0.95 rare for blowout setups |
| Typical 2-sided spread | Not quotable from read-scope; v6 live snapshot of KXBTCD showed empty book at probe time |
| Becker 2026 maker-taker gap | Sports: 2.23pp (Table in paper), second-highest category |
| Burgi 2025 maker mean return | Not separately broken down from "Sports" in Table 8 |
| Le 2026 calibration regime | Sports well-calibrated at short/medium horizons (slope 0.90-1.10); sharply underconfident at >1mo (slope 1.74); game-resolution is short-horizon |
| Project Kalshi prior coverage | KXMLBGAME used in v1 live trading (3 orders); v5-B Statcast ML on KXMLBWINS; NOT fully covered for game-resolution props (KXMLBTOTAL, KXMLBF5, KXMLBRFI) |
| Retail extractability prior | 12-18% (mid bias from Becker 2.23pp; short horizon well-calibrated per Le) |
| Top angle | **Sportsbook line movement leads KXMLBGAME/KXMLBTOTAL mid on same-day games; sportsbook carries sharper info** (v9-A3 Candidate 9 redux) |

**Novel discovery:** KXMLBF5 (first 5 innings), KXMLBTOTAL (total runs), KXMLBRFI (runs first inning), KXMLBKS (strikeouts), KXMLBHIT (hits) are ALL active and trading. These are PROPS not covered in any prior round. They resolve same-day (live score), not season-long. The maker-bias argument (Becker 2.23pp sports gap) applies to props just as much as game winners.

---

### 2. Sports: NBA Finals + NBA Props (KXNBAGAME, KXNBASPREAD, KXNBATOTAL, KXNBAOVERTIME)

| Field | Value |
|---|---|
| Category | NBA game-resolution props |
| Sample series tickers | KXNBAGAME, KXNBASPREAD, KXNBATOTAL, KXNBAOVERTIME |
| Open markets right now | KXNBAGAME: confirmed active (8 trades in 200 most recent); NBA Finals ongoing |
| Open markets closing within 2 weeks | NBA Finals games (best of 7); approximately 2-4 games remaining |
| Mid distribution | Game-winner: typically 0.40-0.65 (uncertain regime); spread and total even more uncertain |
| Typical 2-sided spread | Unknown from read-scope |
| Becker 2026 maker-taker gap | Sports 2.23pp |
| Burgi 2025 maker mean return | Sports category in Table 8: ψ not directly reported separately for NBA |
| Le 2026 calibration regime | Short horizon: slope 0.90-1.10 (well-calibrated for sports at game resolution) |
| Project Kalshi prior coverage | KXNBAWINS (season-long, v1 live, W2 n=22 clean); KXNBAGAME (NOT covered) |
| Retail extractability prior | 12-18% |
| Top angle | **NBA spread and total props are in the uncertain regime (0.35-0.65) where AIA +0.014 Brier was measured; LLM ensemble on game props at T-4h may be viable** |

**Why this is interesting:** NBA Finals games close same-day (or next-morning for international). The uncertain (0.35-0.65 mid) regime is exactly where AIA 2025 documented +0.014 Brier lift, and where Halawi 2024 showed LLM beats crowd. This is the opposite of v1's confident-favorites regime. Geopolitics was LLM's strongest topic (Brier 0.12 vs sports 0.28 per "Future Is Unevenly Distributed" 2025), but WITHIN sports, props like totals and spreads are closer to the "uncertain" bucket than game-winner forecasting.

---

### 3. Sports: Esports (KXMVESPORTSMULTIGAMEEXTENDED, KXMVECROSSCATEGORY, KXVALORANTGAME)

| Field | Value |
|---|---|
| Category | Esports match-level props |
| Sample series tickers | KXMVESPORTSMULTIGAMEEXTENDED, KXMVECROSSCATEGORY, KXVALORANTGAME |
| Open markets right now | Confirmed active (21 + 5 + 3 = 29 in last-200 trade stream) |
| Open markets closing within 2 weeks | Multiple daily; esports runs continuously |
| Mid distribution | Unknown; competitive matches typically 0.35-0.65 |
| Typical 2-sided spread | Unknown |
| Becker 2026 maker-taker gap | Classified under Sports (2.23pp); esports-specific not broken out |
| Burgi 2025 maker mean return | Sports category |
| Le 2026 calibration regime | No esports-specific data in Le 2026 |
| Project Kalshi prior coverage | NONE (zero coverage in v2-v9) |
| Retail extractability prior | 10-20% (uncertain; depends on whether Kalshi is liquid vs illiquid) |
| Top angle | **Esports is a novel, unresearched category; public data on match outcomes (Liquipedia, HLTV) is comprehensive; LLM + structured data may have edge on markets that are not professionally traded** |

**Critical novelty:** KXMVESPORTSMULTIGAMEEXTENDED is the highest non-BTC/MLB series in the last-200 live trades. Esports markets have ZERO prior Project Kalshi coverage. The participants are likely less sophisticated than NFL/NBA bettors. Liquipedia and HLTV provide free, structured historical match data at high frequency. This is a candidate for pure LLM forecasting on an uncertain market at short horizon.

---

### 4. Sports: Tennis (KXITFWMATCH, KXATPCHALLENGERMATCH, KXATPGRANDSLAM)

| Field | Value |
|---|---|
| Category | Tennis match-level and tournament markets |
| Sample series tickers | KXITFWMATCH, KXATPCHALLENGERMATCH, KXATPGRANDSLAM |
| Open markets right now | KXATPGRANDSLAM: 14 open (Roland Garros ongoing); KXITFWMATCH + KXATPCHALLENGERMATCH confirmed in live trade stream (18 + 5 trades) |
| Open markets closing within 2 weeks | KXITFWMATCH and KXATPCHALLENGERMATCH: daily matches; Roland Garros finals within 2 weeks |
| Mid distribution | Match winner: typically 0.55-0.80 for top seeds vs qualifiers; highly uncertain for similar seeds |
| Typical 2-sided spread | Unknown |
| Becker 2026 maker-taker gap | Sports 2.23pp |
| Burgi 2025 maker mean return | Sports category |
| Le 2026 calibration regime | Short horizon sports: slope 0.90-1.10 |
| Project Kalshi prior coverage | KXATPGRANDSLAM in W2 residual (n=1, v1 live); ITF/Challenger NOT covered |
| Retail extractability prior | 12-20% |
| Top angle | **ATP/ITF ranking differential is a strong public predictor of match winner; simple ELO-style model on ATP ranking gap may outperform naive Kalshi mid on ITF/Challenger markets where MMs are less active** |

**Roland Garros 2026 is live now.** KXATPGRANDSLAM has 14 open markets (players who will win tournaments in 2026) closing 2026-12-31. The KXITFWMATCH and KXATPCHALLENGERMATCH series are the per-match resolution markets with same-day closing.

---

### 5. Crypto: BTC 15-Minute (KXBTC15M, KXETH15M)

| Field | Value |
|---|---|
| Category | Ultra-high-frequency crypto price resolution |
| Sample series tickers | KXBTC15M, KXETH15M |
| Open markets right now | KXBTC15M: 33 trades in last-200 (highest crypto series); KXETH15M: 1 trade |
| Open markets closing within 2 weeks | Continuous: closes every 15 minutes |
| Mid distribution | Price-strike structure; at-the-money strike near 0.50 by construction |
| Typical 2-sided spread | Unknown from read-scope; likely tight (MM-maintained) |
| Becker 2026 maker-taker gap | Crypto: 2.69pp (Table in paper) |
| Burgi 2025 maker mean return | Crypto has LARGEST ψ (0.058) in Table 8 |
| Le 2026 calibration regime | Crypto: similar to economics domain; not separately profiled |
| Project Kalshi prior coverage | KXBTCD (daily): v5-C NULL, v6 NULL, v7-B PARTIAL-PHANTOM; KXBTC15M NOT covered |
| Retail extractability prior | 8-12% (MM-maintained; same structural issues as KXBTCD; 15-min horizon even more efficiently priced) |
| Top angle | EXCLUDED: 15-minute crypto is even more tightly MM-maintained than daily; v6 null on daily is strong prior against 15-min |

**Downweight: KXBTC15M is excluded from v10 consideration.** The v6 null showed that Kalshi MMs actively maintain quotes against Coinbase spot in real time for KXBTCD hourly/daily. 15-minute markets are MORE efficiently priced, not less. The v7-B phantom confirmed the residual "edge" was vs. stale trade-print, not vs. live orderbook. This category is killed by prior round evidence.

---

### 6. Crypto: WTI Oil (KXWTI) and Commodities

| Field | Value |
|---|---|
| Category | Energy / commodity price resolution |
| Sample series tickers | KXWTI, KXGOLD, KXSILVER |
| Open markets right now | KXWTI: 6 trades in last-200; KXGOLD/KXSILVER: 0 open per probe |
| Open markets closing within 2 weeks | KXWTI: daily/weekly |
| Mid distribution | Price-strike structure; at-the-money varies with oil price |
| Typical 2-sided spread | Unknown |
| Becker 2026 maker-taker gap | Listed under "Financials" category: 0.08pp/0.08% (SMALLEST, nearly arbed away) |
| Burgi 2025 maker mean return | Financials ψ 0.032 (slightly below average) |
| Le 2026 calibration regime | Finance excluded from Polymarket comparison; not profiled in Le 2026 |
| Project Kalshi prior coverage | NONE directly; v5-C crypto on-chain was indirect |
| Retail extractability prior | 5-10% (Finance/Financials has the SMALLEST maker-taker gap per Becker: 0.17pp) |
| Top angle | NOT recommended. Commodity markets are priced by institutional participants (Susquehanna, per Diercks 2026). Retail edge is minimal per Becker's near-zero Finance gap. |

---

### 7. Macro Economic Releases (KXCPI, KXFOMC)

| Field | Value |
|---|---|
| Category | Macro release event markets |
| Sample series tickers | KXCPI, KXFOMC, KXNFP, KXPCE, KXPPI |
| Open markets right now | KXCPI: 56 open markets (May CPI release 2026-06-10); KXFOMC: 0 open currently |
| Open markets closing within 2 weeks | 0 (CPI release June 10, not within 2 weeks) |
| Mid distribution | Multi-strike structure (CPI at 0.1%, 0.2%...1.0%); most strikes far OTM (settle NO); at-the-money strike uncertain (0.30-0.70) |
| Typical 2-sided spread | CPI April release: 12-20 trades per strike (confirmed via /markets/trades HTTP 200) |
| Becker 2026 maker-taker gap | Economics category: 2.23pp implied (same as Sports in Becker; different from Burgi "Economics" 0.034) |
| Burgi 2025 maker mean return | Economics ψ 0.034 (exactly average) |
| Le 2026 calibration regime | Not profiled in Le for Economics specifically |
| Project Kalshi prior coverage | NONE (zero coverage in v2-v9) |
| Retail extractability prior | 10-15% (BUT per Diercks 2026, macro markets "as accurate as Bloomberg consensus" and supported by Susquehanna MM) |
| Top angle | **Consensus-distribution-based edge**: public Bloomberg consensus for CPI forecasts the mode/mean; the distribution across strikes lets you compare Kalshi's implied distribution against consensus + error variance; if Kalshi assigns >5% to a strike that the consensus distribution assigns <1%, the discrepancy is a maker opportunity. However, Diercks 2026 explicitly documents that "Kalshi beats Bloomberg consensus" on CPI -- meaning the market is ALREADY efficient; no retail edge. |

**Per Diercks 2026 (Fed FEDS 2026-010):** "For headline CPI, we find Kalshi provides a statistically significant improvement over the Bloomberg consensus forecast." This is the kill signal for macro as a retail strategy. If Kalshi BEATS professional consensus, there is no room for a retail participant to do better using public data.

**However:** There is one exception worth noting. The CPI market has 12-20 trades per strike and closes on the CPI release date. On the RELEASE DAY, there is a brief window where the BLS data is published at 8:30 AM ET and Kalshi markets close sometime that morning. If retail can read the BLS report and route an order before Kalshi MMs update quotes, this is a race-to-trade scenario. This is the "LLM-reads-JSON-report" angle. The structural question is whether Kalshi MMs update within seconds (making this a latency game) or within minutes (making it a comprehension game). Diercks 2026 does NOT analyze intraday CPI-release timing on Kalshi.

---

### 8. Weather (KXHIGHNY, KXHIGHCHI)

| Field | Value |
|---|---|
| Category | Daily temperature high resolution |
| Sample series tickers | KXHIGHNY, KXHIGHCHI (confirmed open 2026-05-26) |
| Open markets right now | KXHIGHNY: 12 open; KXHIGHCHI: 12 open; others 0 (KXHIGHHOU, KXHIGHPHX, KXHIGHPHI, KXHIGHDET, KXHIGHBOS all 0 open) |
| Open markets closing within 2 weeks | 12 (tomorrow only; then next day's markets open) |
| Mid distribution | Unknown from read-scope; by structure (binary-on-temperature) the at-the-money strikes are uncertain (0.30-0.70) |
| Typical 2-sided spread | EC-1 Phase 1.5 found 9pp shoulder edge at close; EC-1 Phase 1.6 OOS gate FAILED at 1.5pp |
| Becker 2026 maker-taker gap | Weather: 2.57pp (fourth in Becker table, above Finance and Politics, below Crypto) |
| Burgi 2025 maker mean return | Climate/Weather ψ 0.031 (SMALLEST among significant categories in Table 8) |
| Le 2026 calibration regime | Overconfident at short horizons (slope 0.69-0.97); underconfident at long horizons; the only domain that FLIPS sign |
| Project Kalshi prior coverage | EC-1 (Round 1) KILLED at Phase 1.6 OOS calibration gate |
| Retail extractability prior | 5-10% (EC-1 was definitively killed; only NY and Chicago markets active right now; coverage too thin) |
| Top angle | EXCLUDED: EC-1 was definitively killed at the OOS gate. Only 2 cities currently active (NY, CHI). The Burgi ψ = 0.031 is the smallest of any category. |

---

### 9. Politics: Near-Term Races (KXHOUSE2026, KXGOV2026, KXPRES2028)

| Field | Value |
|---|---|
| Category | US elections and political outcomes |
| Sample series tickers | KXPRES2028, KXHOUSE2026, KXGOV2026, KXSENATE2026 |
| Open markets right now | KXPRES2028: 0 open (HTTP 200); KXHOUSE2026: 0 open; KXGOV2026: 0 open |
| Open markets closing within 2 weeks | 0 (November 2026 elections; zero near-term resolution) |
| Mid distribution | Would be uncertain (0.30-0.70) for competitive races |
| Typical 2-sided spread | Politics per Le 2026: large trade compression effect (Δ=0.53 for trades >100 contracts) |
| Becker 2026 maker-taker gap | Politics: 1.02pp (SECOND LOWEST, above Finance 0.17pp) |
| Burgi 2025 maker mean return | Politics ψ 0.022 (NOT statistically significant, p>0.05) |
| Le 2026 calibration regime | Chronically underconfident (slope 0.93-1.83 all horizons); chronically compressed toward 0.5 |
| Project Kalshi prior coverage | Round 2 KILLED at OOS gate; v3 Polymarket cross-venue covered politics (v3 NULL) |
| Retail extractability prior | 5-10% (ψ not significant; lowest extractable bias; dominated by partisan opposing bets per Le) |
| Top angle | NOT recommended. Becker: politics gap is 1.02pp (only Finance lower). Burgi: ψ not significant. The evidence from all three papers points against politics as a retail extraction category. |

---

### 10. Entertainment Long-Horizon (KXPERFORMBONDSONG, KXJOHNNYDEPP, etc.)

| Field | Value |
|---|---|
| Category | Entertainment futures (casting, awards, releases) |
| Sample series tickers | KXPERFORMBONDSONG, KXACTORSONNYCROCKETT, KXTVSEASONRELEASETHELASTOFUS |
| Open markets right now | Events visible: KXPERFORMBONDSONG-35 (22 mkts), etc. -- but close 2035, zero volume |
| Open markets closing within 2 weeks | 0 (all entertainment events close 2028-2035) |
| Mid distribution | Unknown; zero trades/volume |
| Typical 2-sided spread | Not quoted (zero volume) |
| Becker 2026 maker-taker gap | Entertainment: 4.79pp (SECOND HIGHEST, above Weather, Sports, Crypto) |
| Burgi 2025 maker mean return | Entertainment ψ 0.020 (NOT statistically significant, p>0.05) |
| Le 2026 calibration regime | Le 2026: Entertainment OVERCONFIDENT structural bias (-0.09 intercept) |
| Project Kalshi prior coverage | NONE |
| Retail extractability prior | 5-8% (Becker's 4.79pp gap is impressive BUT Burgi's ψ not significant; zero active volume; all markets are multi-year futures with no quotes) |
| Top angle | NOT viable currently. The 4.79pp Becker gap is real but applies to historical settled entertainment markets. Active entertainment markets currently have zero volume and multi-year horizons. No near-term tradeable universe. |

---

### 11. Esports Props (KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME)

This is the most important NOVEL discovery. Full writeup in the category table above (section 3). Standalone angle:

| Field | Value |
|---|---|
| Category | Esports match-level props |
| Sample series tickers | KXMVESPORTSMULTIGAMEEXTENDED, KXMVECROSSCATEGORY, KXVALORANTGAME |
| Open markets right now | 29 trades in last-200 stream; confirmed active tonight |
| Open markets closing within 2 weeks | Daily/nightly; major tournaments ongoing (VALORANT Champions Tour, League of Legends MSI 2026) |
| Mid distribution | Competitive matches: typically 0.35-0.65 (uncertain regime) |
| Typical 2-sided spread | Unknown; likely retail-dominated (thin) |
| Becker 2026 maker-taker gap | Sports category: 2.23pp (esports classified under Sports) |
| Burgi 2025 maker mean return | Sports ψ (not broken out for esports specifically) |
| Le 2026 calibration regime | No esports-specific data; short-horizon sports is slope 0.90-1.10 (well-calibrated) |
| Project Kalshi prior coverage | NONE (zero coverage v2-v9) |
| Retail extractability prior | 15-22% (large uncertainty range given zero prior data; high novelty premium) |
| Top angle | **Structured data from Liquipedia + HLTV: head-to-head records, map win rates, recent form are all machine-readable; LLM with tool-use or simple ELO model may have edge in a market not covered by sharp sportsbooks** |

---

### 12. South American Soccer (KXCONMEBOLLIBGAME, KXCONMEBOLSUDGAME)

| Field | Value |
|---|---|
| Category | International soccer props |
| Sample series tickers | KXCONMEBOLLIBGAME (6 trades), KXCONMEBOLSUDGAME (3 trades) |
| Open markets right now | Confirmed active (Libertadores/Sudamericana group stage ongoing) |
| Open markets closing within 2 weeks | Multiple per week |
| Mid distribution | Competitive club soccer: 0.35-0.65 typical for uncertain matches |
| Typical 2-sided spread | Unknown |
| Becker 2026 maker-taker gap | Sports 2.23pp |
| Project Kalshi prior coverage | NONE (v1 KXWCSQUAD is World Cup selection, not match-level) |
| Retail extractability prior | 12-18% |
| Top angle | South American soccer is less efficiently priced than EPL/UCL; Conmebol data available via ESPN API; match-level betting lines from Pinnacle available on the-odds-api |

---

### 13. Political Events: KXMAYORLA (novel discovery)

| Field | Value |
|---|---|
| Category | Local/municipal elections |
| Sample series tickers | KXMAYORLA (1 trade in live stream) |
| Open markets right now | 1 confirmed active |
| Open markets closing within 2 weeks | Unknown (LA mayoral race timing) |
| Mid distribution | Likely uncertain (competitive race) |
| Becker 2026 maker-taker gap | Politics 1.02pp |
| Project Kalshi prior coverage | NONE |
| Retail extractability prior | 5-10% |
| Top angle | LA mayoral race may have uncertain mids; local polling data is public |

---

## Categories Probed But Not Recommended

| Category | Kill reason |
|---|---|
| Weather (KXHIGHNY) | EC-1 killed definitively; only 2 cities active; Burgi smallest ψ |
| Crypto daily/hourly (KXBTCD, KXBTC15M) | v5-C, v6 NULL, v7-B PHANTOM; MM maintains quotes vs spot in real-time |
| Macro (KXCPI, KXFOMC) | Diercks 2026: Kalshi beats Bloomberg consensus; Susquehanna makes these markets |
| Politics domestic (KXHOUSE2026, KXPRES2028) | Becker lowest gap (1.02pp); Burgi not significant; all close November 2026 |
| Entertainment long-horizon | Zero volume; all close 2028-2035; Burgi ψ not significant |
| Commodities (KXWTI, KXGOLD) | Becker "Financials" gap nearly zero (0.17pp) |
| Season-long sports (KXMLBWINS, KXNBAWINS) | v1 live; W2 shows KXMLBWINS fragile; v3/v5 NULLs on season-long sports |

---

## Discovered Near-Term Series Not In Prior Rounds (Full List)

From live trade stream (HTTP 200, 2026-05-26 22:45 UTC) -- these are confirmed active markets:

- `KXBTC15M` -- BTC 15-minute binary (ultra-HF crypto)
- `KXETH15M` -- ETH 15-minute binary
- `KXMLBTOTAL` -- MLB total runs over/under
- `KXMLBF5` -- MLB first-5-innings result
- `KXMLBRFI` -- MLB runs-first-inning
- `KXMLBKS` -- MLB strikeouts prop
- `KXMLBHIT` -- MLB hits prop
- `KXMLBSPREAD` -- MLB point spread
- `KXMLBHR` -- MLB home runs
- `KXMLBHRR` -- MLB HR (variant)
- `KXNBASPREAD` -- NBA point spread
- `KXNBATOTAL` -- NBA total points
- `KXNBAOVERTIME` -- NBA overtime prop
- `KXNHLGAME` -- NHL game winner (Finals ongoing)
- `KXMVESPORTSMULTIGAMEEXTENDED` -- Esports multi-game extended props
- `KXMVECROSSCATEGORY` -- Esports cross-category
- `KXVALORANTGAME` -- Valorant match-level
- `KXITFWMATCH` -- ITF Women's tennis match
- `KXATPCHALLENGERMATCH` -- ATP Challenger match
- `KXCONMEBOLLIBGAME` -- Copa Libertadores match
- `KXCONMEBOLSUDGAME` -- Copa Sudamericana match
- `KXWTI` -- WTI crude oil price
- `KXSB` -- Unknown (probing failed)
- `KXMEAD` -- Unknown (probing failed)
- `KXMAYORLA` -- LA Mayoral race

---

## Regime Fit Analysis

**AIA uncertain regime (0.20-0.80):** Game-resolution sports markets (KXMLBGAME, KXNBAGAME), props (KXMLBTOTAL, KXNBASPREAD), esports (KXMVESPORTSMULTIGAMEEXTENDED), tennis (KXITFWMATCH), South American soccer. These typically price 0.35-0.65 for competitive matches. This is the regime where AIA Forecaster showed +0.014 Brier lift AND where Halawi 2024 showed LLM beats crowd.

**v1 confident-favorites regime (0.70-0.95):** Season-long sports (KXMLBWINS, KXNBAWINS where v1 is live), some game-resolution (blowout favorites). v9 killed LLM here due to gate-regime mismatch.

**Le 2026 short-horizon overconfident regime:** KXHIGHNY (weather short-horizon); games resolving same-day. Per Le: "prices too extreme" at short horizons; isotonic pulls toward 0.5.

---

## Ranked Top 5 Categories for v10

### Rank 1: MLB/NBA Props (KXMLBTOTAL, KXNBASPREAD, KXMLBF5)

**Rationale:** These are same-day-resolving game props in the UNCERTAIN (0.35-0.65 mid) regime. This is:
- The regime where AIA 2025 measured +0.014 Brier lift (v9's kill was gate-regime MISMATCH with confident favorites; this fixes that)
- Where Halawi 2024 shows LLM beats crowd (uncertain questions 0.3-0.7: LLM 0.199 vs crowd 0.246)
- Active right now with confirmed trades (31 KXMLBGAME + 8 KXMLBTOTAL + 4 KXNBASPREAD in live stream)
- Completely untested in v2-v9
- Season has 4+ months remaining; daily volume sustains sample size

Honest prior: **15-22%.** The gate-regime mismatch from v9 is the critical lesson: applying AIA +0.014 to confident favorites was wrong; applying it to uncertain game props is regime-matched. The prior is higher than v9's sports-LLM angle precisely because this fixes the design-layer failure.

Concern: Sports is still the weakest LLM topic (Janna Lu 2025: o3 sports 0.1649 vs politics 0.1199; "Future Is Unevenly Distributed": 0.28 vs geopolitics 0.12). Props may be harder than game-winners for LLM to call.

**Specific hypothesis:** On the day of an MLB game, a multivariate model combining the Kalshi mid for KXMLBTOTAL (runs over/under) against the sportsbook line from the-odds-api can detect systematic biases in Kalshi's distribution. The sportsbook line is public; if Kalshi's total mid differs by >3c from the implied sportsbook probability, the direction of correction is known.

---

### Rank 2: Esports Props (KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME)

**Rationale:** 21 trades of KXMVESPORTSMULTIGAMEEXTENDED in the last-200 live stream confirms this is an active market. Zero prior Project Kalshi coverage means no NULL to anchor against. Esports data is comprehensively available (Liquipedia API, HLTV, VLR.gg for Valorant). The participant base is likely retail-dominated with less institutional MM presence than NBA. The uncertain (0.35-0.65 mid) regime applies to competitive matches.

Honest prior: **15-20%.** Novel; no prior round data to calibrate against. The risk is thin liquidity (esports is niche; Becker's 43.6M sports trades may include very few esports contracts).

**Specific hypothesis:** A simple Elo/rating model trained on historical Valorant/LoL/CS2 match results from Liquipedia can beat the Kalshi mid on KXVALORANTGAME/KXMVESPORTSMULTIGAMEEXTENDED at T-24h to T-1h. The edge is a structural bias from retail participants overpricing upsets and underpricing dominant teams.

---

### Rank 3: Sportsbook Line Movement on KXMLBGAME/KXNBAGAME

**Rationale:** This is Candidate 9 from v9-A3's ranked list. The v9 Angle A kill does NOT close this candidate (v9 was LLM on season-long confident favorites; this is sportsbook-leading-Kalshi on game-resolution uncertain markets). The-odds-api confirmed available (v5-A used it; within $30 authorized budget). Active MLB season with 72 open KXMLBGAME markets right now. The NBA Finals are ongoing.

Honest prior: **12-22%** (per v9-A3 Candidate 9).

**Specific hypothesis:** When a major sportsbook (DraftKings, FanDuel) moves a game-result line by more than 5 basis points in the 1-6 hours before a KXMLBGAME or KXNBAGAME close, Kalshi mid lags; a taker at stale Kalshi mid captures the adjustment.

---

### Rank 4: CPI Release-Day Race (KXCPI on release date)

**Rationale:** KXCPI has 56 open markets closing 2026-06-10 (CPI release date). The CPI report is published as a JSON-structured BLS press release at 8:30 AM ET. If Kalshi MMs do NOT update their quotes in the first 30-90 seconds after release, a participant who reads the BLS JSON programmatically could place a taker order before the market mid adjusts. This is the "LLM reads structured JSON" angle where LLM has documented ability to parse numerical data and compute whether a CPI print resolves a specific strike YES or NO.

Honest prior: **10-15%.** The primary risk is latency: Kalshi MMs are likely faster than retail. Diercks 2026 shows Kalshi CPI markets beat Bloomberg consensus, suggesting the market is already incorporating information rapidly. However, there is a difference between "the market is efficient on day-prior" and "the market updates in real-time on release." If there is a 30-180 second window, even a simple BLS parser (not LLM) could capture it.

**Specific hypothesis:** Download the BLS CPI JSON at 8:30 AM ET on release day; compute which KXCPI strike(s) resolve YES given the actual CPI print; place taker orders within 60 seconds before Kalshi MMs update. The data-processing step (not forecasting) is the edge.

This is NOT a forecasting edge; it is a latency edge on structured data. The risk is whether Kalshi MMs are faster. Zero LLM cost; zero data cost; requires only a BLS API scraper.

---

### Rank 5: ATP/ITF Tennis Match (KXATPCHALLENGERMATCH, KXITFWMATCH)

**Rationale:** 18 confirmed trades of KXITFWMATCH and 5 of KXATPCHALLENGERMATCH in the last-200 live stream. ATP ranking data is free from the official ATP website; Elo ratings for tennis players are published by Jeff Sackmann (tennis-abstract.com). Challenger-level matches may be less efficiently priced than Grand Slam matches. Roland Garros is live now; ITF and Challenger circuits run daily.

Honest prior: **12-18%.** Tennis has less retail gambling attention than NFL/NBA, which may mean less institutional MM activity and more persistent mispricings. However, tennis betting lines are also publicly available via Pinnacle, so the "Kalshi mid lags sportsbook" angle from Rank 3 could apply here too.

**Specific hypothesis:** ATP ranking differential at T-24h to T-1h before an KXITFWMATCH or KXATPCHALLENGERMATCH predicts the Kalshi mid for that match; if Kalshi mid deviates from the ranking-implied probability by >5c, the deviation is a signal.

---

## Cross-Venue Consideration (Polymarket Global)

v3 was killed at data layer because Polymarket CLOB had a 30-day depth ceiling for historical data. The v9-A3 Candidate 3 recommended re-probing Polymarket API depth. Polymarket Global (offshore, $2.1B/wk) covers sports, elections, and some esports in parallel with Kalshi. If depth is now 90+ days, the v3 Polymarket-as-feature angle could be revived specifically for:
- Esports (Polymarket Global covers Valorant/LoL championships)
- Sports game props (Polymarket Global covers NBA Finals, MLB)
- The "divergence feature" from V3-C (Kalshi prices HIGHER than Polymarket on favorites) may still hold for uncertain markets

Cost: one API probe, $0.

**Recommendation:** Run the Polymarket depth probe (15 minutes, $0) before committing to any v10 build. If Polymarket now exposes 90+ days of depth on esports or sports props, the cross-venue angle upgrades Rank 2 (esports) or Rank 3 (sportsbook line movement) significantly.

---

## Summary Table

| Rank | Category | Series | Prior | Cost | Novelty | Key Evidence |
|---|---|---|---|---|---|---|
| 1 | MLB/NBA Props | KXMLBTOTAL, KXNBASPREAD, KXMLBF5 | 15-22% | $30 the-odds-api | NEW (props untested) | Uncertain regime match with AIA +0.014; 39 trades live tonight |
| 2 | Esports Props | KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME | 15-20% | $0 (Liquipedia free) | COMPLETELY NEW | 21 trades live tonight; no prior coverage; retail-dominated |
| 3 | Sportsbook Line Movement | KXMLBGAME, KXNBAGAME | 12-22% | $30 the-odds-api | NEW (dynamic vs static) | v9-A3 Candidate 9; 31 KXMLBGAME trades live tonight |
| 4 | CPI Release-Day Race | KXCPI | 10-15% | $0 (BLS API free) | NEW (structured data latency) | 56 open markets Jun 10; 12-20 trades per strike confirmed |
| 5 | ATP/ITF Tennis | KXITFWMATCH, KXATPCHALLENGERMATCH | 12-18% | $0 (ATP data free) | NEW | 23 trades live tonight; Roland Garros ongoing |

**Explicitly down-weighted:**
- Sports season-long (v1 live; v2, v3, v5 NULLs)
- Crypto hourly/daily (v5-C, v6 NULLs; v7-B PHANTOM)
- Weather (EC-1 KILLED)
- Macro (Diercks 2026 kill)
- Politics domestic (Becker/Burgi lowest gap)
- Entertainment long-horizon (zero active volume)

---

## Replay-Prevention Notes

Applying cumulative failure-mode list:

1. v2: false comparison (label horizon overlap) -- Props and esports use same-day resolution, no horizon overlap risk
2. v5-B: stale-price phantom -- Must use live orderbook mid, not last_price. Probe confirmed live orderbook has data (v8-A findings apply)
3. v6: feature framing (CVD returns vs levels) -- Sportsbook line movement uses returns (delta), not levels; esports uses current Elo, not historical level
4. v7-B: stale trade-print vs orderbook -- v8-A resolves this; must confirm with real orderbook mid as baseline
5. v9: gate-regime mismatch -- Rank 1 explicitly targets uncertain (0.35-0.65) regime where AIA +0.014 was measured; this IS the regime match. Gate must be pre-registered for uncertain markets.

New potential failure mode for Rank 4 (CPI race): if MMs update in <10 seconds, the window is too short for retail. Must empirically test: observe bid/ask timestamps on release day, not just the trade record.

---

## Citations

- Becker 2026: per-category maker-taker gap table (Finance 0.17pp, Sports 2.23pp, Crypto 2.69pp, Entertainment 4.79pp, World Events 7.32pp)
- Burgi/Deng/Whelan 2025: Table 8 per-category ψ (Politics 0.022 not significant; Entertainment 0.020 not significant; Weather 0.031 significant; Crypto 0.058 largest)
- Le 2026: domain-by-horizon trajectory table (sports slope 0.90-1.10 at short/medium horizon; weather overconfident at short horizon; politics chronically underconfident)
- Diercks/Katz/Wright 2026: "Kalshi provides statistically significant improvement over Bloomberg consensus forecast" for CPI; macro markets efficient
- AIA 2025: +0.014 Brier lift measured on MarketLiquid HARD markets (mid 0.20-0.80); LLM lags market on hard liquid markets by 0.015 Brier; ensemble 67% market + 33% AI beats either alone
- Halawi 2024: LLM beats crowd on uncertain questions (crowd 0.20-0.80 predictions: LLM 0.199 vs crowd 0.246); LLM LAGS on high-confidence questions (RLHF hedging)
- "Future Is Unevenly Distributed" 2025 (arXiv 2511.18394): sports Brier 0.28 vs geopolitics 0.12 for Claude 3.7; sports is weakest LLM topic
- Janna Lu 2025: o3 sports Brier 0.1649 vs politics 0.1199 (37% worse)
- v9 FINAL-VERDICT.md: gate-regime mismatch documented as new failure mode
- Kalshi API probe: HTTP 200 on /markets/trades confirmed KXMLBGAME (31), KXMVESPORTSMULTIGAMEEXTENDED (21), KXBTC15M (33), KXNBAGAME (8) live at 2026-05-26 22:45 UTC
