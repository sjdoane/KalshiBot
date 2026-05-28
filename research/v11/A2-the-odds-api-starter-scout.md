# v11-A2: the-odds-api.com Starter-Tier Scout

Agent: v11-A2
Date: 2026-05-27
Source pages: https://the-odds-api.com/#get-access, https://the-odds-api.com/liveapi/guides/v4/, https://the-odds-api.com/sports-odds-data/sports-apis.html

## TL;DR

**Verdict: GO** for $30 "20K" tier. v11 Track 1 backtest consumes roughly 30k credits at n=2000 and 60k at n=4000, which **exceeds** the 20k pool, **BUT** can be brought under by scoping to 1 region (us) and 1 market (h2h), which drops cost to ~30k at n=2000 (still over). Re-scoping the snapshot count or sport set fits the pool. See `Backtest cost estimate` and `Recommended scope` sections.

**Net: GO with scoped query plan**, OR upgrade to the $59/100k tier for a comfortable buffer.

## 1. Pricing (confirmed from pricing page)

The brief refers to "Starter $30." On the live pricing page, the tier names are:

- **Free tier** ($0/mo, 500 credits/mo): historical access NOT included. Cannot satisfy v11.
- **20K** ($30/mo, 20,000 credits/mo): all sports, all bookmakers, all markets, **historical data included**.
- **100K** ($59/mo, 100,000 credits/mo): same coverage, 5x the credits.
- **5M** ($119/mo), **15M** ($249/mo): higher pools.

The $30 plan the brief calls "Starter" is the **20K** tier on the pricing page. (The page actually labels the FREE plan as "Starter," but the brief's $30 reference clearly maps to the 20K plan.)

Credit consumption model (from docs):
- A live-odds call counts as 1 credit per request, where one request = 1 sport + 1 market + 1 region.
- A **historical-odds** call costs **10 credits per region per market per call**. Formula from docs: `cost = 10 x [number of markets] x [number of regions]`. Number of snapshots is the count of separate API calls (each snapshot is its own call).

## 2. Historical-odds endpoint capabilities (confirmed from v4 docs)

- **Endpoint**: `GET /v4/historical/sports/{sport}/odds?apiKey=...&regions=...&markets=...&date=...`
- **Date param**: ISO 8601 timestamp; returns the closest snapshot at or before that timestamp.
- **Archive depth**: data available from **June 6, 2020**. October-2024 to November-2025 is well inside the archive.
- **Snapshot granularity**: 10-minute intervals pre-Sep 2022; **5-minute intervals from September 2022 onward**. v11 needs T-6h, T-3h, T-1h, so 5-minute resolution is more than sufficient.
- **Sport coverage** (from sports-apis.html):
  - NFL (`americanfootball_nfl`): covered, scores + results checkmark.
  - MLB (`baseball_mlb`): covered, scores + results checkmark.
  - NBA (`basketball_nba`): covered, scores + results checkmark.
  - MMA/UFC (`mma_mixed_martial_arts`): **listed but no scores/results checkmark on the public page**. Odds coverage present; settled-outcome data may need to come from Becker side.
  - Boxing (`boxing_boxing`): **listed but no scores/results checkmark**. Same caveat.
- **Bookmaker coverage**: us region returns DraftKings, FanDuel, BetMGM, Caesars, BetRivers, etc. Pinnacle requires the `eu` region (additional cost). The docs do not specify the exact bookmaker count per region for historical queries; **propose a 1-credit test query post-purchase** to enumerate.
- **Historical caveat from docs**: "Bookmakers, sports and markets will only be available in the historical odds API from the time that they were added to the current odds API." For sports added before Oct 2024, this is non-binding for our backtest window. Verify via one test call per sport key.
- **Tier requirement**: historical endpoint requires a **paid plan** (the docs do not single out a tier; the $30/20k plan should qualify, but **verify on the account page after purchase**).

## 3. Backtest cost estimate

Assumed query pattern from brief: per Kalshi game, 3 snapshots (T-6h, T-3h, T-1h), 5 bookmakers, h2h moneyline only.

Key fact: bookmakers are NOT a credit multiplier. One historical call for region=us returns ALL us bookmakers in one response. So "5 bookmakers" does not multiply cost; only markets and regions do.

Per-game cost with 1 market (h2h) and 1 region (us):
- 3 snapshots * (10 credits/snapshot * 1 market * 1 region) = **30 credits per game**

If we add Pinnacle (eu region) for cross-book robustness:
- 3 snapshots * (10 * 1 market * 2 regions) = **60 credits per game**

### Cost table

| Sample size  | us-only (30 cr/game) | us+eu (60 cr/game) |
|---           |---                   |---                 |
| n=1000       | 30,000               | 60,000             |
| n=2000 (working est) | 60,000       | 120,000            |
| n=4000       | 120,000              | 240,000            |

### Comparison to credit pools

| Plan         | Pool    | n=1000 us-only | n=2000 us-only | n=4000 us-only |
|---           |---      |---             |---             |---             |
| 20K ($30)    | 20,000  | 150% over      | 300% over      | 600% over      |
| 100K ($59)   | 100,000 | 30% used       | 60% used       | 120% over      |
| 5M ($119)    | 5,000,000 | <1% used     | <2% used       | <3% used       |

The 20K plan does NOT cover the brief's stated scope at any of the working sample sizes.

### Scoping options to fit the 20K pool

To fit n=2000 into 20k credits (us-only, h2h), we have ~10 credits per game. Options:

- **Option A: 1 snapshot per game**: T-3h only, us-only, h2h. = 10 cr/game. n=2000 fits exactly (20k credits, zero buffer). TIGHT.
- **Option B: 2 snapshots per game**: T-6h and T-1h. = 20 cr/game. n=1000 fits (20k credits, zero buffer). TIGHT.
- **Option C: scope to 1 sport** (KXMLBGAME, our cleanest scale-up per memory): assume ~500 settled games in window. 3 snapshots * 10 cr = 30 cr/game * 500 games = **15,000 credits**. Fits with 5k buffer. **GO.**
- **Option D: upgrade to 100K plan** ($59): full 3-snapshot, us-only scope at n=2000 = 60k credits, fits with 40k buffer. **GO with margin.**

## 4. Verdict

- **Brief-as-written** (n=2000, 3 snapshots, 5 books US, post-Oct-2024 to Nov-2025): **NO-GO on $30/20k tier.** Either upgrade to $59/100k or scope down.
- **Recommended path A** (single-sport KXMLBGAME pilot at $30/20k, full 3-snapshot): **GO.** Costs ~15k credits, validates the v11 hypothesis on the in-season market the operator already wants to scale. If the signal shows, then upgrade and expand.
- **Recommended path B** (full multi-sport at $59/100k): **GO.** Costs ~60k of 100k pool at n=2000. Cleanest path if the operator wants the broad test in one go.

## 5. Sport-coverage sanity check

| Sport          | Sport key                    | Odds coverage | Settlement data | Risk for v11 |
|---             |---                           |---            |---              |---           |
| NFL            | americanfootball_nfl         | yes           | yes (API)       | low          |
| MLB            | baseball_mlb                 | yes           | yes (API)       | low          |
| NBA            | basketball_nba               | yes           | yes (API)       | low          |
| MMA/UFC        | mma_mixed_martial_arts       | yes           | not on public page | **medium**: settlement may need to be sourced from Becker / Kalshi side |
| Boxing         | boxing_boxing                | yes           | not on public page | **medium**: same as above |

For v11 we only need **odds** from the-odds-api (Kalshi resolutions come from Becker). Missing scores/results checkmark on MMA/boxing is therefore NOT a blocker. **Confirm odds coverage back to Oct 2024 via a single 10-credit test query per sport after purchase.**

## 6. Operator action

**If pursuing Recommended Path A (KXMLBGAME pilot, $30/20k):**

1. Go to https://the-odds-api.com/#get-access
2. Click the **"Get API Key"** button under the **20K / $30 per month** plan column.
3. Complete the signup. They'll email an API key.
4. Add this to `.env` in the Project Kalshi root:
   ```
   THE_ODDS_API_STARTER_KEY=<paste-the-key-here>
   ```
5. **Verification step (10 credits)**: run one test historical call for KXMLBGAME equivalent, for example:
   ```
   GET https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds?apiKey=$THE_ODDS_API_STARTER_KEY&regions=us&markets=h2h&date=2024-10-15T20:00:00Z
   ```
   Confirm response includes DraftKings, FanDuel, BetMGM, Caesars in the `bookmakers` array. Note the credit count returned in the `x-requests-remaining` / `x-requests-used` response headers to confirm the 10-credit charge.

**If pursuing Recommended Path B (full multi-sport, $59/100k):** same flow, but click the **"Get API Key"** under the **100K / $59** column. Same env var name `THE_ODDS_API_STARTER_KEY` (keep the name stable so downstream v11 code doesn't need to branch on tier).

**Do NOT purchase until v11-A1 firms up the per-sport n_games count.** If A1 confirms KXMLBGAME ~500 settled in window, Path A is GO. If A1 shows the aggregate is closer to n=4000 and the operator wants the full sweep, jump to Path B.

## 7. Docs gaps (verify with 1 test call post-purchase)

- Exact bookmaker list returned for region=us in a historical call (docs do not enumerate per-region historical bookmaker availability).
- Whether the 20K tier actually unlocks the historical endpoint (docs say "paid plans" but do not name a minimum). Stripe upgrade is trivial if 20K is locked out.
- Whether MMA/boxing odds history actually reaches back to Oct 2024 (docs say "available from when added to current odds API"; MMA and boxing are old listings on the public page, so this should pass, but confirm with one test call per sport).

## 8. Budget note

LLM spend for this scout: 4 WebFetch calls, single write. Estimate well under $0.40.
