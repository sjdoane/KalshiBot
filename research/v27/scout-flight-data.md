# Scout: Daily US Flight Activity + Cancellation Data (v27 TSA nowcast)

Date: 2026-07-02. All claims below verified by actual test pulls from this machine (PowerShell; Bash sandbox has no network). Mission: (a) backtest ground truth for daily flights/cancellations 2025-05-01 to present, (b) AS-OF series: what was knowable by Sunday 11:59pm ET about that weekend's (Fri/Sat/Sun) flight activity, to nowcast TSA checkpoint numbers that post Mon-Fri only.

## 0. Target premise CONFIRMED (TSA page as-of behavior)

- Live pull of tsa.gov/travel/passenger-volumes (2026-07-02): daily table includes ALL days including weekends. Latest row 7/1/2026 = 2,654,017. Samples: 6/28 (Sun) 2,930,672; 6/27 (Sat) 2,575,625; 6/26 (Fri) 2,904,610.
- Wayback snapshot taken Sunday 2025-05-18 ~23:59: latest posted row was THURSDAY 5/15/2025 (2,847,304). So as of Sunday night, Fri/Sat/Sun (and even Friday) screenings are unpublished. Weekend numbers appear Monday. This is exactly the nowcast gap.
- Wayback coverage of the TSA page: 112 snapshot-days in 2025-05-01..2026-07-01. Useful for reconstructing the knowable-information set per historical weekend.

## 1. FAA OPSNET / ATADS (aspm.faa.gov): BLOCKED for scripted pulls

- The report UI loads registration-free: https://aspm.faa.gov/opsnet/sys/Airport.asp returns 200, page JS shows guest=true, secLevel=5, i.e. guest report access is intended.
- Reverse-engineered the submit: POST to https://aspm.faa.gov/opsnet/sys/opsnet-server-x.asp with cmd=air_bas, dstyle=r, dfld=yyyymmdd, keylist=YYYYMMDD, fromdate/todate, reportformat=asp|msexcel, and line = uppercased pseudo-SQL over table TOWER_DAY, e.g. `SELECT YYYYMMDD ,SUM(TOTAL) AS TOTAL FROM TOWER_DAY WHERE YYYYMMDD>=20260601 AND YYYYMMDD<=20260701 GROUP BY YYYYMMDD ORDER BY YYYYMMDD`.
- Result: every POST variant (with/without session, referer, full field set, Excel format) returns HTTP 200 with a ZERO-BYTE body. GET returns 500. The server never issues a session cookie. Conclusion: the backend silently rejects non-browser sessions; would need a headless browser or a free MyAccess/Direct login to test further. NOT verified, do not count on it.
- Even if unlocked: ATADS counts towered-airport operations (all aircraft incl. GA/military), a loose proxy for passenger volume. OPSNET data is nominally next-day (FAA docs), which would fail the Sunday-night cutoff for Sunday itself anyway.

## 2. FlightAware /live/cancelled: VERIFIED live; Wayback too sparse for a backtest series

- Live page https://www.flightaware.com/live/cancelled is plain server-rendered HTML, trivially regex-able. Four totals present: `Total delays today`, `Total delays within, into, or out of the United States today`, `Total cancellations today`, `Total cancellations within, into, or out of the United States today`. Variants exist: /live/cancelled/yesterday and /live/cancelled/tomorrow.
- Sample live values (2026-07-02 ~17:50 ET): delays 23,928 worldwide / 4,628 US; cancellations 737 worldwide / 101 US.
- Wayback samples: snapshot 2025-05-04 20:51 UTC (Sunday afternoon): cancellations today 538 worldwide / 246 US (partial day). Snapshot of /yesterday on Monday 2025-05-05 12:01 UTC: Sunday 2025-05-04 full day = 659 worldwide / 318 US. Scale is consistent with BTS (BTS domestic reporting carriers logged 177 cancellations that day; FlightAware US includes international plus all carriers).
- Wayback CDX coverage 2025-05-01..2026-07-01: main page 237 snapshots on 157 distinct days; /yesterday 78 snapshots on 68 days.
- Weekend as-of reconstruction test (61 weekends Fri 2025-05-02 .. Fri 2026-06-26): Fri full-day knowable by Sun 11:59pm ET for 13/61, Sat 9/61, Sun-partial 13/61, ALL THREE only 1/61. Even relaxed (any-hour snapshot on each of Fri/Sat/Sun) is 5/61. VERDICT: Wayback FlightAware gives spot checks, NOT a historical as-of series.
- Going FORWARD it is the best free live as-of feed: poll the page Sun ~23:00 ET (Sun partial + US split), and /yesterday Sat/Sun/Mon mornings (full-day Fri/Sat/Sun). Also worth pushing daily snapshots to web.archive.org/save for auditability.
- Retrieval recipe (live):
  `$r = Invoke-WebRequest "https://www.flightaware.com/live/cancelled" -UseBasicParsing -UserAgent "Mozilla/5.0"` then regex `Total cancellations( within, into, or out of the United States)? today:&nbsp;&nbsp;([\d,]+)`.
- Wayback CDX recipe: `http://web.archive.org/cdx/search/cdx?url=flightaware.com/live/cancelled&from=20250501&to=20260701&output=json&fl=timestamp,statuscode&filter=statuscode:200`.

## 3. BTS TranStats prezip: VERIFIED, the backtest ground truth

- URL pattern works with no auth, no login:
  `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_YYYY_M.zip`
- HEAD checks 2026-07-02: 2026_2 (25.8MB), 2026_3 (31.2MB), 2026_4 (30.5MB), 2026_5 (31.7MB) all HTTP 200. May 2026 already posted on July 2 means the effective lag is about 4-5 weeks (file sizes indicate complete months). Useless live, perfect for backtest.
- Real-data verification: downloaded 2025_5 (30,830,593 bytes), parsed the 110-column CSV. May 2025: 605,648 flights, 6,344 cancellations across 31 days. Daily samples (flights / cancelled):
  - 2025-05-01: 20,383 / 231
  - 2025-05-02: 20,458 / 503
  - 2025-05-03: 17,302 / 212
  - 2025-05-04: 20,369 / 177
  - 2025-05-05: 20,361 / 416
- Columns needed: FlightDate, Cancelled (plus CRSDepTime, Origin etc. if we want per-airport or scheduled-vs-operated). Scope caveat: US domestic flights of reporting carriers only (no international, no non-reporting regionals), but it is the canonical series and internally consistent for a daily nowcast target regressor.
- Recipe: `Invoke-WebRequest -Uri <prezip url> -OutFile x.zip -UserAgent "Mozilla/5.0"` then Python zipfile+csv (pandas import is broken in the Kalshi venv when run from the AI Projects cwd; run from another cwd or use csv module).

## 4. OpenSky Network: BLOCKED for our purpose

- Anonymous live API works: /api/states/all over CONUS bbox returned 6,901 aircraft states just now.
- No anonymous history: historical queries need an account plus approval, and the daily-counts (covid19) dataset is discontinued. Not usable for either the backtest series or the as-of series. Skip.

## 5. Other as-of candidates

- FAA NAS status (nasstatus.faa.gov): live API VERIFIED: https://nasstatus.faa.gov/api/airport-status-information returns XML of ground stops / ground delay programs (live sample: GS at HPN, YYZ; GDP SFO avg 42 min, JFK avg 1h02m). Good LIVE weekend disruption signal (severity of ops trouble), but Wayback history is unusable: the page is a JS shell with no data in snapshots and the API endpoint has only 17 archived days.
- TSA page Wayback (see section 0): 112 snapshot-days; this is the right artifact for validating what-was-knowable-when about the TARGET, not a feature source.
- TSA same-day X/Twitter posts: not testable from here (X requires auth for search); TSA's official daily number is the Mon-Fri web posting. Do not rely on it.
- Airline ops pages (Delta/United): no public daily systemwide ops/cancel counters found worth testing; FlightAware already aggregates them.

## Bottom line

- (i) Backtest ground truth: BTS prezip, full stop. Daily flights and cancellations for every day of the backtest window at ~4-5 week lag, verified with real May 2025 data. Download 2025_5 through the latest posted month once and cache.
- (ii) AS-OF weekend-visible series:
  - HISTORICAL (backtest): there is NO adequate free archived as-of disruption series. FlightAware Wayback covers only ~1-5 of 61 weekends usably; NAS status archive is empty. Honest options: (a) use BTS actual Fri/Sat/Sun flights and cancellations as a PROXY for what a live disruption feed would have shown, and flag the look-ahead approximation explicitly (defensible for cancellations since FlightAware displays them in real time; the live feed tracks the same physical quantity), or (b) restrict as-of features to things that ARE reconstructible: scheduled flight volume (known in advance from BTS CRS schedule fields), day-of-week/holiday calendar, and TSA's own posted-through-Thursday numbers (Wayback-verified).
  - LIVE (deployment): FlightAware /live/cancelled + /yesterday polling (verified parseable, free) plus the NAS status API for severity. Start self-archiving both NOW so the live period accumulates a true as-of record.
- Paid sources: materially better for the BACKTEST, only marginally better live. Cirium or FlightAware AeroAPI can supply historical DAILY cancellation counts with real timestamps, which would replace the look-ahead proxy in (ii-a) and let us validate the FlightAware-page-to-BTS mapping over the whole window. For live deployment the free page polling already carries the signal; ~$100/mo AeroAPI is not required to go live, but a one-time historical cancellations pull (even a single month of Cirium/AeroAPI history) would be a cheap validation of the proxy assumption. Worth asking the operator only if the edge survives the free-data backtest.

## Artifacts

- Test scripts and raw pulls in session scratchpad (cdx_weekend.py, bts_parse.py, bts_2025_5.zip, opsnet_airport.html, opsnet_result*.html).
- Weekend coverage analysis code is reproducible: CDX pulls plus ET conversion, 61 weekends enumerated Fri 2025-05-02 through Fri 2026-06-26.
