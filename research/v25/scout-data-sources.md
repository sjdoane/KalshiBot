# Data-source scout: underlying series for Kalshi aggregate markets

Date: 2026-07-02. All sources below were ACTUALLY test-pulled from this machine via PowerShell (Bash sandbox has no network). Every command shown was executed and returned the sample values quoted.

## 1. AAA national average regular gasoline (Kalshi gas settlement source)

### VERIFIED best source: web.archive.org snapshots of gasprices.aaa.com

AAA publishes no history itself. The Wayback Machine has near-daily snapshots and the national average parses cleanly from the archived HTML.

Coverage (tested via CDX API, statuscode 200, collapsed to one per day):

- Window checked: 2024-10-01 to 2026-07-02 (640 days)
- Days with at least one snapshot: 547 (85.5%)
- Missing days: 93. Full list (yyyymmdd): 20241010, 20241015, 20241016, 20241028, 20250103, 20250109, 20250226, 20250303, 20250329, 20250403, 20250413, 20250504, 20250510, 20250512, 20250520, 20250526, 20250527, 20250530, 20250602, 20250604, 20250607, 20250610, 20250617, 20250619, 20250624, 20250625, 20250626, 20250627, 20250704, 20250727, 20250731, 20250806, 20250807, 20250810, 20250814, 20250822, 20250826, 20250827, 20250902, 20250916, 20250918, 20250919, 20250922, 20250925, 20250930, 20251004, 20251005, 20251011, 20251019, 20251021, 20251024, 20251025, 20251026, 20251027, 20251102, 20251103, 20251106, 20251109, 20251112, 20251114, 20251115, 20251123, 20251127, 20251128, 20251201, 20251204, 20251205, 20251230, 20260102, 20260103, 20260112, 20260129, 20260201, 20260205, 20260207, 20260213, 20260215, 20260216, 20260218, 20260222, 20260224, 20260225, 20260226, 20260227, 20260228, 20260301, 20260306, 20260313, 20260314, 20260315, 20260328, 20260425, 20260503
- Worst gap cluster: late Feb 2026 (20260222 to 20260301, 8 of 9 days missing). Mid-2025 has many scattered single-day holes. Late June 2026 onward is complete (a daily crawler at ~11:01 UTC is now hitting the site).
- Some missing snapshot-days are recoverable anyway: a snapshot taken before ~08:00 UTC shows the PRIOR day's price (see gotcha below), so keying on the page's "Price as of" date fills some holes and creates others. Recompute coverage on the as-of date after a full pull.

Working commands (executed):

```powershell
# List snapshot days
Invoke-RestMethod -Uri "https://web.archive.org/cdx/search/cdx?url=gasprices.aaa.com&from=20241001&to=20260702&output=json&collapse=timestamp:8&fl=timestamp,statuscode&limit=2000"

# Pull one snapshot and parse
$html = (Invoke-WebRequest -Uri "https://web.archive.org/web/20260701110104/https://gasprices.aaa.com/" -UseBasicParsing).Content
$m = [regex]::Match($html, "National Average.{0,200}?\`$(\d\.\d{3,4}).{0,200}?Price as of\s*(\d+/\d+/\d+)", 'Singleline')
"$($m.Groups[1].Value) as of $($m.Groups[2].Value)"
```

Sample retrieved values (all parsed from live pulls today):

| Snapshot ts | Parsed price | Page "as of" date |
|---|---|---|
| 20241001013402 | $3.216 | 9/30/24 |
| 20250401 | $3.201 | 4/1/25 |
| 20251001 | $3.160 | 10/1/25 |
| 20260101 | $2.833 | 1/1/26 |
| 20260615 | $4.0650 | 6/15/26 |
| 20260701110104 | $3.8470 | 7/1/26 |

Gotchas:

1. Timestamp vs settlement date. Snapshots are UTC; AAA updates around 3 to 4am ET. The 2024-10-01 01:34 UTC snapshot still shows 9/30/24. ALWAYS parse the "Price as of M/D/YY" string next to the number and key the series on that, never on the snapshot timestamp.
2. Display precision changed. Through at least late 2025 the page shows 3 decimals ($3.216); by mid-2026 it shows 4 ($3.8470, $4.0650). Regex must accept `\d\.\d{3,4}`. Check which precision Kalshi settlement rules reference.
3. Rate limits and flakiness. One pull returned 503 Server Unavailable on first try and succeeded on retry. Expect intermittent 503/429 from web.archive.org; pull with 2 to 3s spacing, retry with backoff. A full 547-day pull is roughly 30 to 45 min at polite pacing.
4. Match phrase: "Today's AAA National Average $X.XXX Price as of M/D/YY" appears in the HTML (page also repeats it in a second element). The dollar figures after it are the state map bucket boundaries; do not grab those.

### GitHub scrapers (checked, none carries the national headline)

- `jgreathouse9/AAAGas`: daily state/city/county CSVs via GitHub Actions, but `Prices/MasterGas.csv` covers only 2024-11-16 to 2024-12-01 (repo has a pruner workflow) and has NO national row. State rows only. Not usable as the settlement series; averaging states does not reproduce AAA's station-weighted national number.
- `corintxt/gas-tracker-frontend`: `data/gas_prices.csv` (branch master) is exactly the right shape (date, regular, mid_grade, premium, diesel, e85) but only 12 rows starting 2026-02-27, and values carry 4 decimals of a computed mean (2026-02-27 regular 2.9823), so it is likely a derived average, not the headline. Useful only as a cross-check from Mar 2026 on.
- Others found (ryan-serpico, lykmapipo, rapthar, msdavidson, artfulKraken, RowanFlynnPilot) are state/metro/county scoped. None has national daily history back to 2024-10.

### EIA cross-check (weekly, not the settlement source)

Tested `https://api.eia.gov/v2/petroleum/pri/gnd/data/` without a key: returns 403 `API_KEY_MISSING` with a pointer to free registration at https://www.eia.gov/opendata/register.php. So the API works but needs a (free, instant) key. Series `EMM_EPMR_PTE_NUS_DPG` = US regular all-formulations retail, weekly (Mondays). Use only as a sanity band around the AAA series; do NOT use for settlement.

## 2. NWS/NOAA daily climate observations (Kalshi weather cities)

### VERIFIED source: NOAA ACIS (data.rcc-acis.org). Free JSON API, no key, POST JSON.

Single-station pull (executed, values below are real):

```powershell
Invoke-RestMethod -Method Post -Uri "https://data.rcc-acis.org/StnData" -ContentType "application/json" -Body '{"sid":"KNYC","sdate":"2026-06-01","edate":"2026-06-10","elems":[{"name":"maxt"},{"name":"mint"},{"name":"avgt"}]}'
```

Sample (NY City Central Park, June 2026): 06-01 max 71 min 53, 06-02 max 76 min 52, 06-03 max 83 min 61, 06-04 max 86 min 64, 06-05 max 88 min 66.

Multi-station pull (executed, all 8 Kalshi stations resolved in one call):

```powershell
Invoke-RestMethod -Method Post -Uri "https://data.rcc-acis.org/MultiStnData" -ContentType "application/json" -Body '{"sids":"KNYC,KMDW,KMIA,KAUS,KDEN,KPHL,KLAX,KIAH","sdate":"2026-06-15","edate":"2026-06-15","elems":[{"name":"maxt"},{"name":"mint"}]}'
```

Verified station resolution (ACIS returns full sid cross-map, GHCN ids included):

| Kalshi city | ICAO sid | ACIS resolved name | GHCN-D id |
|---|---|---|---|
| NYC | KNYC | NY CITY CENTRAL PARK | USW00094728 |
| Chicago | KMDW | CHICAGO MIDWAY AP | USW00014819 |
| Miami | KMIA | MIAMI INTERNATIONAL AP | USW00012839 |
| Austin | KAUS | AUSTIN BERGSTROM INTL AP | USW00013904 |
| Denver | KDEN | DENVER INTL AP | USW00003017 |
| Philadelphia | KPHL | PHILADELPHIA INTL AP | USW00013739 |
| Los Angeles | KLAX | LOS ANGELES INTL AP | USW00023174 |
| Houston | KIAH | HOUSTON INTERCONTINENTAL AP | USW00012960 |

Coverage: ACIS serves the full 2024-10-01 to present window and decades back; it is the same threaded-station data the NWS climate reports (CLI/CF6) publish, which is what Kalshi weather markets settle on. Verified KNYC 2026-06-15 maxt 74, KDEN 81 in the MultiStnData sanity check.

Gotchas:

1. Values come back as JSON strings ("83"), not numbers, and missing data is "M", trace is "T". Cast explicitly; in PowerShell do NOT index into the value ("83"[0] returns the char '8', which burned this scout for one round).
2. Units: maxt/mint/avgt are whole degrees F. avgt is (max+min)/2 to one decimal.
3. Same-day data lands after the station's daily climate report; previous day is safe by ~08:00 local. For intraday settlement checks use the NWS CLI product, not ACIS.
4. No key, no documented hard rate limit, but it is a courtesy service run by the RCCs; batch via MultiStnData instead of hammering StnData.

## 3. USDA egg prices (low priority, partially tested)

- USDA AMS Market News API (MARS, `https://marsapi.ams.usda.gov/services/v1.2/reports/...`): tested without a key, returns 403 Forbidden. Free key via self-service signup at my.marketnews.usda.gov. Egg reports live here (e.g. report 2848 daily national shell eggs; the weekly Egg Markets Overview). NOT verified end to end; needs the free key first.
- MPR datamart (`https://mpr.datamart.ams.usda.gov/services/v1.1/reports`): open, no key, verified working (150 reports listed) but it is livestock/dairy mandatory price reporting; zero egg reports (searched). Not useful for eggs.
- Recommendation if a Kalshi egg market becomes a target: register the free MARS key (minutes), then re-test report pull; until then treat egg coverage as UNVERIFIED.

## Bottom line for v25

- Gas: build the AAA history from Wayback (547 of 640 days directly, keyed on the page's "as of" date), EIA weekly (free key) as sanity band. The 93 missing days are a known, listed gap set; late Feb 2026 is the only bad cluster.
- Weather: ACIS is fully sufficient, keyless, and matches the settlement stations one for one. No gaps expected.
- Eggs: blocked on a free MARS key; nothing else needed.
