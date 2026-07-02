# Data source scout: KXTSAW (TSA weekly) and KXRAIN*M (monthly rain)

Scouted 2026-07-02 (Thu), ~12:00 PT / 15:00 ET. All findings below are from actual test pulls made today, not docs. Network via PowerShell (Bash sandbox has no network).

## 1. TSA daily throughput history

### Retrieval method (verified by pull)

- Current year: `https://www.tsa.gov/travel/passenger-volumes` (plain HTML table, Date / Numbers, newest first). Pulled today: 183 rows = header + Jan 1 to Jul 1, 2026.
- Historical years: `https://www.tsa.gov/travel/passenger-volumes/<year>` for year = 2019..2025 (links discovered in the page itself; each is a full-year table, oldest first). Verified 2023 and 2025 pages: 366 rows each = header + all 365 days. So full 2023-01-01..today coverage = pages /2023, /2024, /2025 + main page.
- No JSON API or CSV endpoint exists on tsa.gov; it is a Drupal HTML table. Parsing is trivial (regex on `<tr>` rows).

PowerShell recipe (working, used for every number in this doc):

```powershell
function Get-TsaYear($year) {
  $u = "https://www.tsa.gov/travel/passenger-volumes"
  if ($year -lt (Get-Date).Year) { $u += "/$year" }
  $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 60
  $out = @{}
  foreach ($row in [regex]::Matches($r.Content, '<tr[^>]*>.*?</tr>', 'Singleline')) {
    $t = ($row.Value -replace '<[^>]+>', ' ' -replace '\s+', ' ').Trim()
    if ($t -match '^(\d+/\d+/\d+)\s+([\d,]+)') { $out[[datetime]$Matches[1]] = [int]($Matches[2] -replace ',', '') }
  }
  $out
}
```

Python equivalent: `requests.get(url)`, then `re.findall(r'<tr.*?</tr>', html, re.S)` and strip tags; or `pandas.read_html(url)[0]`.

### Sample values (pulled 2026-07-02)

| Date | Screenings | Same date 2025 |
|---|---|---|
| 6/27/2026 | 2,575,625 | 2,988,614 |
| 6/28/2026 | 2,930,672 | 2,624,407 |
| 6/29/2026 | 2,690,919 | 2,959,224 |
| 6/30/2026 | 2,477,905 | 2,780,012 |
| 7/1/2026 | 2,654,017 | 2,402,675 |

### Publication timing (verified)

- Page states verbatim: "Passenger travel numbers are updated Monday through Friday by 9 a.m. Travel numbers during holiday weeks though may be slightly delayed."
- Spot check today (Thu 2026-07-02, checked ~15:00 ET): latest row is 7/1/2026, i.e. yesterday's number is up. Consistent with next-day-by-9am.
- CRITICAL for the weekly market: updates are Mon-Fri ONLY. Saturday and Sunday numbers post on Monday morning. So for a week ending Sunday, the last two dailies (Sat + Sun) are unknown until Monday ~9am ET; Friday's number posts Saturday? NO: Friday's number posts Monday too (no weekend updates), so the last THREE dailies (Fri, Sat, Sun) all land Monday morning. Backtests of intra-week trading must not assume Fri/Sat/Sun data before Monday.

### Revision policy (verified via Wayback diffs, this is the big finding)

- TSA numbers DO get revised. Diffing the live 2023 table against the Wayback snapshot of 2023-07-15: 183 of 194 overlapping dates changed, almost all revised UPWARD. Typical delta +0.1 to +0.5 percent; worst cases 1/16/2023 2,115,696 -> 2,244,873 (+129k, +6.1 pct), 5/12/2023 +81k, 2/21/2023 +70k, 3/6/2023 +68k, 4/29/2023 +67k. Even days-old figures moved (7/11/2023 was 4 days old at snapshot time and later went +31k).
- The revisions were NOT ongoing forever: the Wayback snapshot of the /2023 page from 2024-05-23 is byte-identical in values to today's /2023 page (365 checked, 0 diffs). So the restatement window was between Jul 2023 and May 2024.
- Recent behavior: snapshot of 2026-06-10 vs today, 159 overlapping 2026 dates, ZERO revisions. Current regime looks stable over a 3-week horizon.
- Implication: current-page history equals final revised values, which may differ from the numbers visible at settlement time in 2023-2024. For 2026 settled weeks this does not matter empirically (next point).

### Weekly-average convention (verified against settled markets)

- Kalshi rules text: "If weekly average TSA airport screenings are above X million for the week ending <Sunday date>, according to the TSA".
- Convention confirmed = arithmetic mean of the 7 TSA dailies Monday..Sunday inclusive, ending that Sunday. All 10 settled KXTSAW weeks (26APR26 through 26JUN28, the full series history) reproduce EXACTLY from today's page:

| Week ending | Page Mon-Sun avg | Kalshi expiration_value |
|---|---|---|
| 2026-04-26 | 2,462,491.7 | 2.46 |
| 2026-05-03 | 2,428,610.1 | 2,428,610 |
| 2026-05-10 | 2,397,280.1 | 2,397,280 |
| 2026-05-17 | 2,572,666.1 | 2,572,666 |
| 2026-05-24 | 2,626,290.7 | 2,626,291 |
| 2026-05-31 | 2,596,810.7 | 2,596,811 |
| 2026-06-07 | 2,571,679.9 | 2,571,680 |
| 2026-06-14 | 2,678,645.7 | 2,678,646 |
| 2026-06-21 | 2,769,250.9 | 2,769,251 |
| 2026-06-28 | 2,775,070.7 | 2.775 |

- Series metadata (GET /trade-api/v2/series/KXTSAW): frequency weekly, fee_type quadratic, fee_multiplier 1, settlement source url = the passenger-volumes page.

## 2. KXRAIN series to station mapping (all 11 pulled from Kalshi API 2026-07-02)

Settlement source from GET /series/<ticker>; CLI product code from market rules_primary text ("total precipitation at CLIxxx"). ACIS sid = ICAO id, verified by ACIS StnMeta pull (station name and period of record below).

| Series | City | CLI product (WFO) | Station | ACIS sid | ACIS pcpn POR |
|---|---|---|---|---|---|
| KXRAINNYCM | New York | CLINYC (OKX) | Central Park | KNYC | 1869-01-01 |
| KXRAINCHIM | Chicago | CLIMDW (LOT) | Midway AP (NOT O'Hare) | KMDW | 1928-02-29 |
| KXRAINSEAM | Seattle | CLISEA (SEW) | Seattle-Tacoma AP | KSEA | 1945-01-01 |
| KXRAINHOUM | Houston | CLIHOU (HGX) | Hobby AP (NOT Bush/IAH) | KHOU | 1930-08-01 |
| KXRAINMIAM | Miami | CLIMIA (MFL) | Miami Intl AP | KMIA | 1937-03-01 |
| KXRAINAUSM | Austin | CLIAUS (EWX) | Austin-Bergstrom (NOT Camp Mabry) | KAUS | 1942-10-17 |
| KXRAINDENM | Denver | CLIDEN (BOU) | Denver Intl AP | KDEN | 1994-07-20 |
| KXRAINLAXM | Los Angeles | CLILAX (LOX) | LAX (NOT downtown/USC) | KLAX | 1944-08-01 |
| KXRAINDALM | Dallas | CLIDFW (FWD) | DFW AP (NOT Love Field) | KDFW | 1974-01-01 |
| KXRAINSFOM | San Francisco | CLISFO (MTR) | SFO AP (NOT downtown) | KSFO | 1945-07-01 |
| KXRAINSTPM | St. Petersburg FL | CLISPG (TBW) | Albert Whitted AP | KSPG | 1998-06-15 |

Gotchas found:

- KXRAINSTPM is St. Petersburg FLORIDA (Albert Whitted, KSPG), not St. Paul MN. The series settlement_sources url is just generic https://www.weather.gov; the station comes from the market rules text ("total precipitation at CLISPG in St. Petersburg").
- KXRAINNYCM rules say "Central Park" in prose (no CLI code); the settlement url carries OKX/NYC.
- Series metadata for the rain family: frequency monthly, fee_type quadratic, contract terms RAINM.pdf.
- Strikes observed are "strictly greater than X inches" (Jul 2026 ladder at 5, 6, 7 inches etc.).

## 3. ACIS daily precip vs official NWS monthly total (CLM)

ACIS recipe (verified): POST to `https://data.rcc-acis.org/StnData`, JSON body `{"sid":"KNYC","sdate":"2026-03-01","edate":"2026-03-31","elems":[{"name":"pcpn"}]}`, no key needed. Values are strings: numeric, "T" (trace), or "M" (missing). Treat T as 0.00 when summing; that convention reproduced the official totals exactly in all six tests.

Official monthly totals pulled from the NWS CLM (monthly climate summary) product via the IEM AFOS archive: `https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?pil=CLM<xxx>&fmt=text&sdate=<d1>&edate=<d2>` (CLM for month M is issued on the 1st of month M+1; the same archive serves daily CLI products, pil=CLINYC etc., which is the actual settlement document family and gives point-in-time month-to-date values for backtesting).

Result: 6 of 6 station-months match EXACTLY (T summed as zero; no missing days in any tested month):

| Station | Month | sum(ACIS daily pcpn) | CLM official total | Traces in month | Match |
|---|---|---|---|---|---|
| KNYC | Mar 2026 | 3.60 | 3.60 | 4 | exact |
| KNYC | May 2026 | 3.05 | 3.05 | 3 | exact |
| KSEA | Mar 2026 | 6.71 | 6.71 | 3 | exact |
| KSEA | May 2026 | 1.14 | 1.14 | 3 | exact |
| KDEN | Mar 2026 | 0.66 | 0.66 | 1 | exact |
| KDEN | May 2026 | 1.63 | 1.63 | 6 | exact |

Verdict: ACIS daily pcpn summed with T=0 is settlement-grade for these markets, at least for the tested months. (Caveat: only 6 station-months tested; before going live, run the same check across all 11 stations x 24+ months and watch for late CLM corrections.)

## 4. Climatology depth (ACIS StnMeta valid_daterange, plus 1995 completeness pull)

- KNYC: POR from 1869; 1995 test year 365/365 non-missing. 150+ years.
- KSEA: POR from 1945; 1995 test year 365/365 non-missing. 80+ years.
- KDEN: POR from 1994-07-20 (Denver Intl opened Feb 1995); 1995 has 59 missing days (Jan-Feb, pre-opening). Usable daily record ~31.3 years, just clears 30. Pre-1995 Denver climatology would need Stapleton (ThreadEx "DEN" thread) which is a DIFFERENT site; do not silently splice.
- KSPG: POR from 1998-06-15 only, and 1995 pull returned 0/365. That is ~28 years, UNDER 30. Flag: KXRAINSTPM climatology is the shallowest of the family.
- All other stations: POR 1974 or earlier (see table above), depth is not a concern.

## Open items / risks

1. TSA revision risk: historical (2023) values on today's page are post-restatement; if reconstructing what a 2023-era settlement would have seen, use Wayback snapshots. For 2026, no revisions observed over a 3-week window and all 10 settled weeks reproduce from the live page.
2. TSA weekend gap: Fri/Sat/Sun numbers all land Monday ~9am ET; the weekly market's final 3 inputs are unobservable until settlement morning.
3. CLI vs CLM: settlement text references the CLI (daily) product; the monthly total in the final CLI of the month and the CLM agree by construction, but the live-trading pipeline should read the CLI month-to-date line (IEM AFOS pil=CLIxxx) as the authoritative running total.
4. KSPG depth (28y) and KDEN depth (31y) limit climatology-based priors for those two series.
5. Not yet tested: ACIS multi-station batch endpoint (MultiStnData), CF6 cross-check, and whether ACIS ingests late NWS corrections to daily pcpn (compare ACIS vs archived CLI on a correction case before trusting for training labels).
