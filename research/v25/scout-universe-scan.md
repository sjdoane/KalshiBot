# v25 Scout: Universe Scan for Aggregate-Settlement Series

Scan date: 2026-07-02. Read-only, $0. Host: api.elections.kalshi.com/trade-api/v2 (public GETs, no auth).
Method: pulled full series list (GET /series, 11,144 series across 18 categories), keyword-scanned titles (average, total, cumulative, gas, egg, rain, snow, temp, commodity names), then probed 80+ candidate series via GET /series/{ticker} and GET /markets?series_ticker=X&status=open. Raw probe JSON in session scratchpad (probe_results.json, probe2_results.json).

Field conventions used below: volume = volume_fp on the single most active open market; spread = yes_ask_dollars minus yes_bid_dollars on that market; "median spread" = across open markets with a nonzero bid. Fee info is NOT on market objects; it is on the series object as fee_type + fee_multiplier. Every candidate here is fee_type=quadratic, multiplier x1, EXCEPT KXAAAGASM and KXEGGS which are quadratic_with_maker_fees (maker fees apply).

Categories (series counts): Entertainment 2460, Sports 2284, Politics 2020, Elections 1421, Financials 605, Economics 584, Mentions 376, Climate and Weather 286, SciTech 278, Crypto 253, Companies 173, World 143, Health 96, Commodities 63, Social 52, Transportation 39, Exotics 10, Education 1.

## TIER 1: true aggregate-over-window settlement, LIVE markets (the shape we want)

### 1. Monthly rain series (11 cities): KXRAINNYCM, KXRAINCHIM, KXRAINSEAM, KXRAINLAXM, KXRAINHOUM, KXRAINMIAM, KXRAINAUSM, KXRAINDENM, KXRAINDALM, KXRAINSFOM, KXRAINSTPM
- Category: Climate and Weather. Settlement source: NWS Climatological Report for the named station (e.g. "NWS Climatological Report NY" for Central Park, CLIMDW Chicago Midway, CLISEA Seattle, CLILAX, CLISPG St. Petersburg).
- Rule (verbatim, NYC): "If the total precipitation at Central Park, New York City in Jul 2026 is strictly greater than 4 inches, then the market resolves to Yes."
- Underlying: NWS daily CLI report precipitation (published daily, next morning, station-level, near-zero revision). Settlement = SUM of daily values over the calendar month.
- Window: calendar month. Deterministic pinning: YES, textbook. Month-to-date total is a hard floor; YES side of any strike below MTD total is locked, and remaining-days climatology bounds the rest.
- Open markets (2026-07-02): 4-7 strikes per city, all July 2026, close 08-01.
  - KXRAINNYCM: 4 open, top KXRAINNYCM-26JUL-4 vol 1,967, bid/ask 0.52/0.59, median spread 7c, series total vol 2,389.
  - KXRAINCHIM: 7 open, top -26JUL-2 vol 1,301, bid/ask 0.82/0.83, median spread 1c, total vol 4,516. All 7 strikes have bids.
  - KXRAINSEAM: 7 open, top -26JUL-4 vol 8,191 but that strike quotes 0.00/0.01 (resolved-in-practice tail); 3 of 7 with bids, spread 1c; total vol 42,929.
  - KXRAINLAXM: 7 open, total vol 31,405, but July LA rain is degenerate (top strike 0.00/0.01, 0 strikes with bid). Seasonal dead zone; will be live in winter.
  - KXRAINSTPM: 7 open, ZERO volume, 0.01/0.99 quotes = dead.
  - Others (HOU/MIA/AUS/DEN/DAL/SFO): listed with 7 strikes each; liquidity between CHI and STP levels.
- Judgment: YES (deterministic partial pinning). Best-in-class match. Liquidity is thin-but-real on NYC/CHI/SEA in wet-relevant months; several cities are seasonal or dead.

### 2. Monthly snow series (dormant now, seasonal): KXNYCSNOWM, KXCHISNOWM, KXBOSSNOWM, KXDENSNOWM, KXDENSNOWMB, KXPHILSNOWM, KXDCSNOWM, KXDETSNOWM, KXSEASNOWM, KXSLCSNOWM, KXASPSNOWM, KXJACWSNOWM, KXDALSNOWM, KXAUSSNOWM, KXHOUSNOWM, KXLAXSNOWM, KXSFOSNOWM, KXMIASNOWM; also season-total KXSNOWNYM, KXSNOWCHIM
- Same mechanics as rain (NWS CLI daily snowfall summed over month or season). 0 open markets on 2026-07-02 (July). Expect relisting ~Oct-Nov. Judgment: YES when live. Flag for re-scan in autumn.

### 3. KXTORNADO: Number of Tornadoes (monthly)
- Economics of shape: monthly cumulative COUNT. Source: NOAA (SPC preliminary tornado reports, published daily).
- Rule: "If the preliminary number of tornadoes in Jul is above 150, then the market resolves to Yes."
- Underlying: SPC daily storm reports, daily cadence. Window: calendar month. Pinning: YES, monotone count; MTD count locks YES side progressively.
- Open: 11 markets (July strikes), top vol 1,290, bid/ask 0.32/0.67 (wide, 35c), median spread across strikes 14c, total vol 3,382. Caveat: "preliminary" count definition; SPC preliminary reports have duplicates vs final count. Judgment: YES, but wide spreads and a definitional wrinkle.

### 4. Hurricane season cumulative counts: KXHURCTOT, KXHURCTOTMAJ, KXTROPSTORM, KXNAMEDSTORM
- Source: NOAA NHC. Rules (verbatim, KXHURCTOT): "If the NOAA's National Hurricane Center records more than 6 hurricanes of hurricane category 1 or above between January 1, 2026 and December 01, 2026, then the market resolves to Yes."
- Underlying: NHC advisories (real-time, public). Window: Jan 1 to Dec 1 (KXNAMEDSTORM has basin variants, e.g. Central Pacific from May 15). Pinning: YES, monotone running count.
- Open + liquidity (all close 2026-12-01/02):
  - KXHURCTOT: 9 open, top T6 vol 7,618, bid/ask 0.32/0.33, median spread 4c, total vol 27,516.
  - KXHURCTOTMAJ: 8 open, top T2 vol 15,684, bid/ask 0.44/0.49, median spread 4c, total vol 44,561.
  - KXTROPSTORM: 8 open, top T18 vol 9,020, bid/ask 0.10/0.11, median spread 3c, total vol 27,257.
  - KXNAMEDSTORM: 14 open, top CPACTOT-2 vol 1,682, bid/ask 0.74/0.85, median spread 8c, total vol 7,439.
- Judgment: YES. Most liquid of the Tier 1 set. Long window (5 months left), so pinning is slow; the informational edge is seasonal forecasting, not arithmetic, until late season.

### 5. KXTSAW: TSA check-ins this week
- Category: Economics/Transportation-ish. Source: Transportation Security Administration (daily throughput, published next day).
- Rule: "If weekly average TSA airport screenings are above 2.6 million for the week ending July 05, 2026, according to the TSA, then the market resolves to Yes."
- Underlying: TSA daily checkpoint numbers, daily cadence, no revision. Settlement = AVERAGE of 7 daily values. Window: week.
- Open: 21 markets (3 weeks x ~7 strikes), closest close 2026-07-06. Top vol 1,558, bid/ask 0.72/0.79, median spread 3c, total vol 3,838. 19 of 21 with bids.
- Judgment: YES, textbook: by Friday, 5 of 7 days are known exactly. Short window means fast pinning every week. Liquidity thin (hundreds to ~1.5k contracts per strike).

### 6. KXLAUNCHCOUNTM: Total launches in month
- Category: Science and Technology. Source: Federal Aviation Administration.
- Rule: "If all U.S.-licensed commercial launch providers cumulatively have Above 17 launches in Jul 2026, then the market resolves to Yes."
- Underlying: launch events, observable in real time (public trackers); FAA-licensed launch list. Window: calendar month (settles up to a week after, close 08-07).
- Open: 8 strikes for July. Top vol 1,409, bid/ask 0.11/0.12, median spread 1c across all 8 (all have bids), total vol 3,049.
- Judgment: YES, monotone count with tight quotes. Main risk: whether a given launch counts as FAA-licensed.

### 7. KXUSFLYCAN: US flight cancellations this week
- Source listed on rules: FlightAware displayed weekly total. Rule: "If the total cancellations within, into, or out of the United States figure displayed on FlightAware for week ending July 3, 2026 is above 5500, then the market resolves to Yes."
- Underlying: FlightAware daily cancellation counts, real-time public. Window: week. Pinning: YES, cumulative sum.
- Open: 9 markets. Effectively DEAD: top vol 36, bid/ask 0.02/0.48, median spread 80c, total vol 145. Judgment: YES on shape, but untradeable liquidity today.

### 8. Annual fiscal cumulatives (monthly-cadence underlying): KXTARIFFREVENUE, KXIRSCOLLECT, KXTRADEDEFICIT
- KXTARIFFREVENUE: "If US tariff revenue for 2026 is above $200 billion..." 6 open, top vol 3,869, bid/ask 0.53/0.56, median spread 6c, total vol 8,058. Underlying: monthly Treasury statement (customs duties), monthly cadence; YTD sum locks progressively. Judgment: YES (cumulative), cadence monthly not daily.
- KXIRSCOLLECT: "If the IRS collects more tax revenue in 2026 than 2025..." 1 open market, vol 11,483, bid/ask 0.84/0.89. Same monthly-cumulative logic. Judgment: YES.
- KXTRADEDEFICIT: "If US trade deficit for 2026 is above 170 billion..." 12 open, top vol 2,397, bid/ask 0.90/0.96, only 1 of 12 with a bid, total vol 11,805. Monthly Census/BEA releases sum to annual. Judgment: YES on shape, mostly dead quotes.

## TIER 2: settlement = single-day READ of a slow-moving DAILY public series (not an average, no deterministic pinning, but the underlying is observable daily with tiny increments)

### 9. AAA gas price family: KXAAAGASM (monthly), KXAAAGASW (weekly), KXAAAGASD (daily)
- Source: AAA (gasprices.aaa.com daily national average). Fee note: KXAAAGASM is quadratic_with_maker_fees; W and D are plain quadratic.
- Rule (verbatim, monthly): "If average regular gas prices for United States are strictly greater than $3.80 on Jul 31, 2026 according to AAA, then the market resolves to Yes." The word "average" refers to AAA's cross-station daily average, NOT a time average. Settlement is the AAA number ON the close date.
- Open + liquidity:
  - KXAAAGASM: 42 open (July + Aug strikes), top vol 2,020 (JUL31-3.80), bid/ask 0.35/0.40, median spread 2c across 42 strikes (all bid), total vol 9,443.
  - KXAAAGASW: 15 open, top vol 14,192 (JUL06-3.800), bid/ask 0.57/0.60, median spread 3c, total vol 104,530. Most liquid gas market.
  - KXAAAGASD: 17 open, top vol 4,788, bid/ask 0.91/1.00, median spread 4c, total vol 15,036.
- Judgment: NO deterministic pinning (point read). BUT: AAA national average moves a fraction of a cent per day and is published every morning; a weekly market is essentially a 5-step random walk with publicly visible state. This is the family the v25 prompt asked about (KXGASM does not exist; the ticker is KXAAAGASM). State-level variants exist only as yearly max/min touch series (KXAAAGASMAX/MIN + CA/TX/FL/NY): those ARE monotone (running extremum pins), all currently 0 open except yearly ones not probed live here.
- Legacy tickers GAS, GASD, GAS-MONTH, KXGAS, KXGASD, KXGAS-MONTH, DIESEL/KXDIESEL/KXDIESELM: all 0 open (dead).

### 10. KXMEAD: Lake Mead water levels
- Source: U.S. Bureau of Reclamation. Rule: "If Lake Mead's end-of-month water elevation at Hoover Dam for Jun 2026 is strictly greater than 1044.5 feet..."
- Underlying: daily elevation published by USBR; end-of-month point read. 12 open, top vol 5,880, bid/ask 0.99/1.00, median spread 1c, total vol 16,709. Judgment: NO pinning (point read) but extremely slow-moving daily-public state; June market is already at 0.99.

### 11. KXJETFUEL: US Gulf Coast jet fuel weekly average spot
- Rule: "If the Kerosene-Type Jet Fuel Prices: U.S. Gulf Coast weekly average spot price for the week ending July 3, 2026 is above 2.60 dollars per gallon..." (EIA weekly average of daily spot).
- This IS a weekly average of daily spot prices, but EIA publishes the dailies with a lag; intraweek the Platts assessments are paywalled. Partial pinning: PARTIALLY (public free dailies lag). Liquidity: DEAD (9 open, zero volume, no bids). Judgment: right shape, no market.

## TIER 3: adjacent shapes, recorded for completeness (excluded or degenerate)

- KXUSGASCPI (US gasoline CPI in month): single BLS release, EXCLUDED per spec, but note the print is approximately the month-average of station prices, so AAA month-to-date data quasi-pins it. 41 open, top vol 3,571, bid/ask 0.85/0.90, median spread 59c (mostly dead tails). Same for KXAIRFARECPI, KXUSEDCARCPI, KXUSGBEEF (0 open), KXCHCUTS etc.
- KXEGGS (BLS egg price MoM direction): single release, EXCLUDED. 1 open, vol 2,607, 0.01/0.29. KXEGGPRICEW/KXEGGPRICEM (USDA weekly/monthly): 0 open, dead. There is no KXEGGS aggregate-window market live.
- KXCHIPBURRITO: "average U.S. price of a Chipotle Chicken Burrito for July 2026" - month-average wording, but settlement source on the series is mislabeled (BLS boilerplate) and actual sampling source unclear from rules_primary. 6 open, top vol 141, 0.38/0.42. Too small + source ambiguity. Watch item only.
- KXHMONTH / KXHMONTHRANGE (NOAA/NCEI global monthly temperature anomaly): settlement is a single monthly index release (Land-Ocean Temperature Index). Not a sum of published dailies, so no deterministic pinning from the settlement series itself, but ERA5 daily reanalysis publicly tracks it closely = strong informational (not arithmetic) constraint. KXHMONTHRANGE: 12 open, top vol 12,203, 0.53/0.56 (tails dead, median spread 55c). KXHMONTH: 2 open, top vol 41,904, 0.04/0.08. Borderline; worth a separate memo if v25 wants model-vs-release games.
- Touch/extremum markets on slow public series (running extremum pins one side monotonically): KXFERT (USDA Illinois urea price touch by Jan 2027; 7 open, top vol 17,639, 0.15/0.47, median spread 29c), KXBARRELS (US oil production touch 13.9M bpd; 7 open, top vol 8,544, 0.98/1.00), KXDEBTGROWTH (debt hits 40T by Q4 2028, FRED; 3 open, top vol 44,967, 0.971/0.98), KXSPRLVL (SPR level point read, weekly EIA; 7 open, vol 25, dead), KXAAAGASMAX/MIN state families (yearly extremum of AAA daily; not probed live individually). These are monotone-lock, not averaging; same "already-observed data pins settlement" property on ONE side.
- Pyth-settled commodity series (KXNATGASD/W, KXGOLDD/W, KXSILVERW, plus MON variants): settle on a single 1-minute candle close at expiry. EXCLUDED (point-in-time, no window). Noted because their titles ("Weekly", "Monthly") are misleading. The old legacy commodity average series (KXWTIMONTHLY, KXBRENTMON, KXCOPPERMON, KXWHEATW/MON, KXCOFFEEW/MON, KXSUGARMON, KXSTEELMON, KXNICKELMON, KXCOBALTW/MON, KXLITHIUMW/MON, KXSOYBEANW, KXCOCOAW, KXLCATTLEW/MON, KXHOILW, KXOIL, KXOILW, KXNGAS, KXNGASW, KXWTIMAXM): ALL 0 open markets. Dead universe.
- COVID case-average series (KXCASE7D etc.): legacy, presumed dead (not probed; titles are averages of daily public data; re-probe only if relisted).
- Dormant but shape-correct, watch for relisting: KXAIJOBLOSS (weekly total AI-linked job losses), KXNYCCBDENTRY (MTA congestion-pricing entries, daily public data), KXFLIGHTJFK / FLIGHTLAX (airport delay totals), KXTRUFTSA, KXERCOTX (monthly renewables share = month-average of 5-min ERCOT fuel mix, daily public), KXSUEZTRAFFIC (IMF PortWatch daily transits), KXMICHTEMP (monthly avg lake temp, GLERL daily data), KXPRIMESPEND, KXEARTHQUAKEM, snow family (sec. 2). KXERCOTX and KXNYCCBDENTRY are the two best "would be perfect if relisted" tickers.

## Cross-cutting facts

- Fee schedule: no fee fields on market objects. Series-level fee_type is "quadratic" (x1) for every candidate except KXAAAGASM and KXEGGS ("quadratic_with_maker_fees"). Implication: maker fees only apply on the flagged series; everything else is taker-fee-only per the standard Kalshi quadratic schedule (cross-check against the archived dated fee table from the v22 work).
- Liquidity reality check (volume_fp on most active market, spread): tradeable-ish today: KXAAAGASW (14k, 3c), KXHURCTOTMAJ (16k, 4-5c), KXTROPSTORM (9k, 1-3c), KXHURCTOT (8k, 1c), KXAAAGASD (5k, 4c), KXAAAGASM (2k, 2c), KXTSAW (1.6k, 3c), KXRAINNYCM (2k, 7c), KXRAINCHIM (1.3k, 1c), KXLAUNCHCOUNTM (1.4k, 1c), KXTORNADO (1.3k, 14c). Dead despite correct shape: KXUSFLYCAN, KXJETFUEL, KXRAINSTPM, KXSPRLVL, all legacy commodity averages, egg weekly/monthly.
- The only LIVE series that are strict "average/sum of daily public values over a window" with quotes you could actually trade: monthly rain (NYC/CHI/SEA now; more cities seasonally), KXTSAW, KXLAUNCHCOUNTM, KXTORNADO, hurricane count family. The gas family is point-read, not averaging; treat it as a separate (random-walk-forecast) class.
- Season note: it is July. The snow family (16+ series) and cold-city rain markets are dormant; the aggregate-window universe roughly doubles in Oct-Nov. Recommend re-running this scan in early October.
