# Scout: Rotten Tomatoes score vintages for KXRT (Wayback reconstruction)

Date: 2026-07-02. All findings from actual test pulls (Kalshi elections API, Wayback CDX + snapshot fetches, live rottentomatoes.com GET) run from PowerShell with the Project Kalshi venv Python.

## TL;DR

- Event map: 33 KXRT event tickers found (23 finalized, 1 closed-unsettled, 9 open/inactive). All 33 resolved to a rottentomatoes.com/m/ slug, 32 unique movies (KXRT-DUN is an inactive duplicate of KXRT-DUNE). Every ambiguous slug was disambiguated by 2026 archive activity and validated against the settled result band where possible.
- Snapshot density: 0.3 to 1.4 snaps/day in the last 14 days before close for big titles, 0.14 to 0.5 for small ones. NOT reliably 1-2/day, but every checked title has a snapshot within 2.6 to 20 hours of the settlement timestamp.
- Parse recipe: the `media-scorecard-json` script blob works on every 2026 snapshot tested (6 movies, snapshots Apr 26 to Jun 27). JSON-LD `aggregateRating` is a matching fallback.
- Settlement reproduction: 7 of 8 events checked reproduce (score from the nearest snapshot lands in the implied settled band, or the before/after bracket contains it). 1 of 8 (KXRT-MOR) sits on a 65/66 boundary inside a 46-hour snapshot gap and cannot be confirmed from Wayback alone.
- Live access: plain `requests.get` of a live RT movie page returns 200 with the same scorecard blob, even with the default Python User-Agent. No Cloudflare block observed.

## 1. Event -> movie -> RT slug map

Series: KXRT ("Rotten Tomatoes score?"). Rules text pattern: "If <Movie> has a Tomatometer score of above <K> on <date> at 10:00 AM ET, then the market resolves to Yes." Close time in API = 14:00 UTC on that date (10:00 ET). Markets are all "Above K" floor-strike binaries (10 to 29 strikes per event).

Note: the task brief said "~23 settled events Jan-Apr 2026"; actual settled closes run 2026-04-27 through 2026-06-29.

| Event | Status | Close (UTC) | Movie | RT slug (`rottentomatoes.com/m/`) | Notes |
|---|---|---|---|---|---|
| KXRT-MIC | finalized | 2026-04-27 14:00 | Michael (MJ biopic) | `michael` | Ambiguous name; `michael` has 42 snaps in 2026, validated vs settled band |
| KXRT-MOT | finalized | 2026-04-27 14:00 | Mother Mary | `mother_mary` | |
| KXRT-ANI | finalized | 2026-05-04 14:00 | Animal Farm (Serkis) | `animal_farm_2025` | NOT `animal_farm`; validated (score 23 in band (22,25]) |
| KXRT-DEV | finalized | 2026-05-04 14:00 | The Devil Wears Prada 2 | `the_devil_wears_prada_2` | |
| KXRT-BIL | finalized | 2026-05-11 14:00 | Billie Eilish - Hit Me Hard and Soft: The Tour (Live in 3D) | `billie_eilish_hit_me_hard_and_soft_the_tour_live_in_3d` | |
| KXRT-MOR | finalized | 2026-05-11 14:00 | Mortal Kombat II | `mortal_kombat_ii` | Settlement not Wayback-reproducible (see section 4) |
| KXRT-SHEE | finalized | 2026-05-11 14:00 | The Sheep Detectives | `the_sheep_detectives` | |
| KXRT-INT | finalized | 2026-05-18 14:00 | In the Grey | `in_the_grey` | |
| KXRT-OBS | finalized | 2026-05-18 14:00 | Obsession | `obsession_2025` | NOT `obsession` (0 snaps); validated (94 in (93,94]) |
| KXRT-STA | finalized | 2026-05-25 14:00 | Star Wars: The Mandalorian and Grogu | `star_wars_the_mandalorian_and_grogu` | `the_mandalorian_and_grogu` exists but only 3xx redirects |
| KXRT-BAC | finalized | 2026-06-01 14:00 | Backrooms | `backrooms` | Validated (89 in (88,89]) |
| KXRT-PRE | finalized | 2026-06-01 14:00 | Pressure | `pressure_2026` | Validated via bracket (86 before, 87 after, settled 87) |
| KXRT-MAS | finalized | 2026-06-08 14:00 | Masters of the Universe | `masters_of_the_universe_2026` | NOT the 1987 `masters_of_the_universe`; validated (67 in (65,67]) |
| KXRT-POW | finalized | 2026-06-08 14:00 | Power Ballad | `power_ballad` | |
| KXRT-SCA | finalized | 2026-06-08 14:00 | Scary Movie (reboot) | `scary_movie_2026` | `scary_movie_6` exists but near-dead in archive; validated via bracket (27 Jun 6, settled 23-25, 24 Jun 10) |
| KXRT-DIS | finalized | 2026-06-15 14:00 | Disclosure Day | `disclosure_day` | |
| KXRT-STO | finalized | 2026-06-15 14:00 | Stop! That! Train! | `stop_that_train` | |
| KXRT-DEA | finalized | 2026-06-22 14:00 | The Death of Robin Hood | `the_death_of_robin_hood` | |
| KXRT-GIR | finalized | 2026-06-22 14:00 | Girls Like Girls | `girls_like_girls` | Thinnest archive coverage of the checked set |
| KXRT-TOY | finalized | 2026-06-22 14:00 | Toy Story 5 | `toy_story_5` | |
| KXRT-JAC | finalized | 2026-06-29 14:00 | Jackass: Best and Last | `jackass_best_and_last` | |
| KXRT-SUPE | finalized | 2026-06-29 14:00 | Supergirl | `supergirl_2026` | NOT `supergirl_woman_of_tomorrow` (0 snaps); validated (57 in (55,57]) |
| KXRT-SEND | closed (NOT finalized) | 2026-02-02 15:00 | Send Help | `send_help` | Only 4 markets, no results in API despite Feb close; treat as anomaly, check determination before using |
| KXRT-AVE | active | 2026-12-21 15:00 | Avengers: Doomsday | `avengers_doomsday` | |
| KXRT-DUN | inactive | 2026-12-18 15:00 | Dune: Part Three | `dune_part_three` | Superseded by KXRT-DUNE |
| KXRT-DUNE | active | 2026-12-21 15:00 | Dune: Part Three | `dune_part_three` | |
| KXRT-EVI | active | 2026-07-13 14:00 | Evil Dead Burn | `evil_dead_burn` | |
| KXRT-INV | active | 2026-07-13 14:00 | The Invite | `the_invite` | |
| KXRT-MIN | active | 2026-07-06 14:00 | Minions & Monsters | `minions_and_monsters` | `minions_3` exists but stale since Feb |
| KXRT-MOA | active | 2026-07-13 14:00 | Moana (live action) | `moana_2026` | `moana_2026_2` exists with 0 snaps; watch for slug swap |
| KXRT-ODY | active | 2026-07-20 14:00 | The Odyssey (Nolan) | `the_odyssey_2026` | Bare `the_odyssey` had 1 stray snap in Jun; use `_2026` |
| KXRT-SPI | active | 2026-08-03 14:00 | Spider-Man: Brand New Day | `spider_man_brand_new_day` | |
| KXRT-YOUN | active | 2026-07-06 14:00 | Young Washington | `young_washington` | |

Coverage: 33/33 events mapped, 0 unresolved. Disambiguation method: Wayback CDX prefix search (`matchType=prefix` on `rottentomatoes.com/m/<fragment>`) to enumerate candidate slugs, then per-candidate 2026 snapshot counts; the market-window-active slug wins. Six ambiguous picks were additionally confirmed by comparing a near-close snapshot score to the settled strike band (section 4).

API notes: `GET https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXRT&limit=1000` returns all 520 markets in one page (no auth needed). There is no `/historical/markets` route needed; `status=settled` returns 400 markets, `status=open` 106. `result` field is `yes`/`no` per market once finalized, so the settled score band per event = (max yes strike, min no strike].

## 2. Snapshot density (5 representative settled titles)

200-status Wayback snapshots of the movie page, window relative to close:

| Event / slug | Size | Last 14d before close | Last 28d | Nearest snap to close | Last snap at-or-before close |
|---|---|---|---|---|---|
| KXRT-MIC `michael` | big | 14 snaps, 7/14 days (1.00/day) | 16, 9/28 days | 20.2h before | 2026-04-26 17:46 UTC |
| KXRT-STA `star_wars_the_mandalorian_and_grogu` | big | 11 snaps, 5/14 days (0.79/day) | 15, 9/28 days | 8.2h before | 2026-05-25 05:49 UTC |
| KXRT-TOY `toy_story_5` | big | 20 snaps, 7/14 days (1.43/day) | 21, 8/28 days | 17.0h after | 2026-06-21 05:19 UTC |
| KXRT-INT `in_the_grey` | small | 7 snaps, 7/14 days (0.50/day) | 8, 8/28 days | 3.5h after | 2026-05-18 05:12 UTC |
| KXRT-GIR `girls_like_girls` | small | 4 snaps, 4/14 days (0.29/day) | 4, 4/28 days | 2.6h after | 2026-06-19 20:05 UTC |

Verdict: the "1-2 snapshots per day" bar is NOT met consistently. Coverage is bursty (multiple snaps on some days, none on others); small titles can go 3+ days dark (girls_like_girls covered only 4 of the final 28 days). However, every title checked has a snapshot within 21 hours of the settlement timestamp, and near-close coverage was good enough to bracket settlement for 7 of 8 events checked. Adequate for: settlement reproduction (mostly), coarse as-of score curves (1 to 3 day granularity). Not adequate for: intraday score dynamics or guaranteed daily curves on small titles.

## 3. Parse recipe (verified on 2026-layout pages)

Snapshot URL form (raw HTML, no Wayback chrome): `https://web.archive.org/web/<TS>id_/https://www.rottentomatoes.com/m/<slug>`

Primary (worked on all 9 snapshots fetched, Apr 26 to Jun 27 2026, and on the live page):

```python
m = re.search(r'<script[^>]*id="media-scorecard-json"[^>]*>(.*?)</script>', html, re.S)
d = json.loads(m.group(1))
score        = d["criticsScore"]["score"]         # displayed Tomatometer percent (str/int)
review_count = d["criticsScore"]["reviewCount"]   # critic review count
# also available: ratingCount (== reviewCount in all tests), likedCount, notLikedCount,
# averageRating, certified, sentiment; d["audienceScore"]["score"] for Popcornmeter
```

Fallback (same values, present on same pages): JSON-LD block `<script type="application/ld+json">` with `aggregateRating: {"name": "Tomatometer", "ratingValue": "38", "reviewCount": 210}`.

Do NOT use a bare `[0-9]+%` or `critics-score` text regex: on tested pages it grabbed the audience score first.

Extracted test values:

| Slug | Snapshot (UTC) | Tomatometer | Review count |
|---|---|---|---|
| `michael` | 20260426174639 | 38 | 210 |
| `star_wars_the_mandalorian_and_grogu` | 20260525054930 | 62 | 235 |
| `in_the_grey` | 20260518051259 | 46 | 37 |

## 4. Settlement spot-checks (booleans only)

Implied settled band per event = (max strike settled yes, min strike settled no]. Snapshot score = media-scorecard parse of nearest 200 snapshot at-or-before close.

Primary two (decisive, snapshot close to settlement):

| Event | Snapshot | Score | Settled band | Agree? |
|---|---|---|---|---|
| KXRT-MIC | 2026-04-26 17:46 UTC (20.2h before close) | 38 | (37, 40] | YES |
| KXRT-STA | 2026-05-25 05:49 UTC (8.2h before close) | 62 | (61, 62] | YES (exact) |

Extended validation set (also serves as slug confirmation):

| Event | Before-close snap -> score | Band | After-close snap -> score | Verdict |
|---|---|---|---|---|
| KXRT-ANI | 05-01 -> 23 | (22,25] | | agree |
| KXRT-OBS | 05-17 -> 94 | (93,94] | | agree (exact) |
| KXRT-MAS | 06-08 04:06 -> 67 | (65,67] | | agree (exact) |
| KXRT-SUPE | 06-27 -> 57 | (55,57] | | agree (exact) |
| KXRT-BAC | 05-31 -> 89 | (88,89] | | agree (exact) |
| KXRT-PRE | 05-30 -> 86 | (86,87] | 06-03 -> 87 | agree via bracket (drifted 86 -> 87 pre-close) |
| KXRT-SCA | 06-06 -> 27 | (22,25] | 06-10 -> 24 | agree via bracket (drifted 27 -> ~24) |
| KXRT-MOR | 05-10 11:37 -> 65 | (65,66] | 05-12 10:00 -> 65 | NOT reproduced: both neighbors read 65, settlement implies 66 at 10:00 ET 05-11; 46h gap straddles close |

Takeaway: settlement reproduction from Wayback works when a snapshot exists within roughly a day of the 10:00 ET stamp AND the score is not sitting on a strike boundary. Scores still move 1 to 3 points day-over-day near close (PRE, SCA), so a day-old snapshot is not a settlement oracle for at-the-strike markets. KXRT-MOR is the concrete example: a one-point flicker (65 vs 66) inside a snapshot gap makes that settlement unverifiable from the archive.

## 5. Live page access

`requests.get("https://www.rottentomatoes.com/m/minions_and_monsters")` from this machine: HTTP 200, 209KB, `media-scorecard-json` present (criticsScore 90, reviewCount 102), with BOTH a Chrome User-Agent and the default python-requests User-Agent. No 403, no Cloudflare challenge headers. A live polling engine can use plain GETs (keep frequency polite; RT sits behind an origin that could enable bot rules at any time, so keep the browser UA and a fallback plan).

## Blockers / caveats

1. KXRT-MOR settlement is not reproducible from Wayback (boundary flicker in a 46h gap). Expect a small number of such events in any backtest; treat at-the-boundary settlements with a day-old vintage as uncertain, not known.
2. Small titles have thin archives (girls_like_girls: 4 snaps in final 28 days). As-of curves for minor releases will have multi-day holes. Mitigation for live/open events: run our own scheduled pulls plus Wayback SavePageNow requests near close.
3. KXRT-SEND (Send Help) closed 2026-02-02 but is status `closed` with no results in the API; excluded from the settled set until its determination is understood.
4. Slug churn risk on open events: RT sometimes re-slugs pages pre-release (`moana_2026_2`, `supergirl_2026_2` exist as empty placeholders). Re-verify slugs for open events at engine start; follow 3xx redirects.
5. CDX API is slow and occasionally times out; retries with backoff required. Snapshot HTML fetches are ~1-3s each; a full history rebuild for all 23 settled events is roughly 600-900 fetches, comfortably feasible.

## Repro pointers

- Kalshi pull: `GET https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXRT&limit=1000` (no auth, host is api.elections.kalshi.com).
- CDX: `http://web.archive.org/cdx/search/cdx?url=rottentomatoes.com/m/<slug>&output=json&fl=timestamp,statuscode&from=YYYYMMDD&to=YYYYMMDD&filter=statuscode:200` (add `matchType=prefix` + `collapse=urlkey` for slug discovery).
- Snapshot: `https://web.archive.org/web/<TS>id_/https://www.rottentomatoes.com/m/<slug>` then the media-scorecard regex above.
