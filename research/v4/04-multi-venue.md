# Agent V4-D: Multi-Venue Alternative-Signal Scan

**Date:** 2026-05-24
**Author:** Agent V4-D (Phase 1 / v4 master plan Section 6.3)
**Status:** Research only. Read-only public APIs. No trading. No `.env` modification.
**Scope:** If V4-A finds Polymarket Global coverage is too low for Track A, what other venues or signals can serve as a second opinion on v1's candidate trades?

---

## TLDR verdict

Of the four external venues plus one internal-Kalshi fallback that I tested:

1. **ManifoldMarkets** is REACHABLE and free, but its coverage on v1's resting orders is shallow and the prices are MANA (play money). On 8 v1 resting tickers probed with 4 query variants each (32 queries), 23 returned at least one search hit, but ZERO returned an EXACT-event YES/NO contract that maps to v1's market. Best-case is a tangentially related multi-outcome event (e.g. "Will OKC win the 2026 NBA Finals" vs v1's "OKC playoff wins >= 15"). Median liquidity on relevant open NBA markets is ~$1,000 MANA with 4-36 bettors. Honest read: NOT a reliable second-opinion source for v1's live universe.

2. **PredictIt** is reachable and free, but **100% political** as expected. 292 active markets total: 227 politics (78%), 0 sports, 2 economy. Useful for any future political Kalshi markets v1 might consider; useless for the current sports universe.

3. **the-odds-api** is reachable, returns 401 without a key as documented. Operator has NOT signed up (no `THE_ODDS_API_KEY` in `.env`). The free tier has been UPDATED since v2 docs: it is now **500 credits/month INCLUDING historical odds access**. At 10 credits per historical-odds call, that yields ~50 historical lookups per month, OR 500 live-odds lookups. The first paid tier is $30/mo for 20,000 credits. This is the most promising external alternative if operator signs up.

4. **Polymarket US** (polymarketexchange.com) landing page reaches 200; the developer API docs at `apidocs.polymarketexchange.com` 307-redirect (gated). Liquidity is still ~$5M/week vs Polymarket Global's ~$2.1B/week. Sports beta only. Not yet viable for retail at $32 scale.

5. **Internal Kalshi cross-market consistency** (the no-external-venue fallback) is the strongest finding of this report. On 174 adjacent-threshold pairs in KXNFLWINS team-season ladders, **20.7% are monotonically inconsistent** at T-35d with mean spread 11.2c, p95 spread 38c. Of the 6 violations where BOTH contracts resolved with different outcomes, the "short the high-threshold" trade was right 6/6 times. Sample is small but DIRECTIONALLY CLEAN and the data is FREE and ALWAYS-AVAILABLE.

**Priority order recommendation for v4 Track A fallback:**

1. If V4-A finds Polymarket Global coverage > 30%: use it as the primary filter (per master plan).
2. **(NEW) Internal Kalshi cross-market consistency** as the universal backup for the NFLWINS and NBAWINS series. Free, no external dependency, no auth, fires on series v1 actually trades.
3. **the-odds-api free tier** as the second-opinion source for v1's game-resolution markets (KXNFLGAME, KXMLBGAME, KXNCAAFGAME, KXMLSGAME) once operator signs up. 5-minute operator action, $0.
4. ManifoldMarkets remains a "nice to know" reference only. Not load-bearing.
5. PredictIt deferred until v1 considers political markets.
6. Polymarket US deferred at least 6 months until liquidity grows.

---

## 1. ManifoldMarkets

### 1.1 API status

`https://api.manifold.markets/v0/` is reachable, no auth required. Probed endpoints:

| Endpoint | Status | Notes |
|---|---|---|
| `GET /markets?limit=5` | 200 | Returns 22 fields per market (id, question, slug, probability, totalLiquidity, volume, uniqueBettorCount, mechanism, outcomeType, isResolved, closeTime, ...) |
| `GET /search-markets?term=<q>&limit=5` | 200 | Text search; returns 0 results on overly specific queries, 5 on broad queries |
| `GET /market/<id>` | 200 (per docs) | Per-market detail |

Polite throttle of 0.6-0.7s between calls. No rate-limit errors hit in this probe.

### 1.2 Coverage on v1's live universe

I sampled 8 of v1's currently-resting orders from `data/live_trades/state.json` (state snapshot 2026-05-24 18:17 UTC). For each ticker I tried 4 free-text query variants (total 32 queries) to give Manifold a fair shot. Results in `data/v4/manifold_widened_probe.json`.

| Kalshi ticker | League | Any text-search hit? | Best candidate question | EXACT event match? |
|---|---|---|---|---|
| KXWCSQUAD-26ESP-BIGL | Soccer-WC | YES | "Will Lamine Yamal win The Fifa Best Young Player award at the World Cup?" | NO (different question: Best Young Player award vs squad selection of Lamine) |
| KXSTARTINGQBWEEK1-W1-26SEP15-LV-KCOU | NFL | YES | "2026 NFL Offseason - The Quarterback Carousel" (multi-outcome) | NO (multi-team carousel, not specific to LV Raiders week 1 starter) |
| KXWCGAME-26JUN23ENGGHA-ENG | Soccer-WC | YES | "2026 FIFA World Cup Mega-Market: Group Stage" (multi-outcome) | NO (no per-game Eng-Gha contract) |
| KXUFCFIGHT-26JUL11MCGHOL-HOL | UFC-MMA | YES | Past Holloway fights (UFC 318, UFC 326) all resolved | NO (no UFC July 11 2026 contract) |
| KXWNBAWINS-26PHX-20 | WNBA | NO | (zero results across all 4 query variants) | NO |
| KXNBAPLAYOFFWINS-26SAS-10 | NBA | YES | "Thunder vs Spurs, NBA Western Conference Final Series Winner" | NO (series winner, not Spurs playoff wins >= 10) |
| KXNBAPLAYOFFWINS-26OKC-15 | NBA | YES | "Will the Oklahoma City Thunder win 2026 NBA Finals" | NO (Finals win, not playoff wins >= 15) |
| KXCS2-ASIA26-FAL | CS2-Esports | YES | "Which team will win IEM Cologne Major 2026?" | NO (different tournament) |

**Exact-event match rate: 0/8.** Even the BEST candidates (Thunder Finals contract for the Thunder playoff-wins ticker) are CORRELATED but NOT THE SAME contract; using them as a direct fade-filter would introduce a basis-risk error that depends on the conditional probability P(15+ playoff wins | win Finals), which v1 has no clean way to estimate.

### 1.3 Liquidity audit

Sampled the top 10 open NBA markets sorted by liquidity. Headline numbers:

- All 10 are denominated in **MANA** (play money). Manifold does have a real-money sweepstakes-cash track ("CASH" tokens) but no sampled open NBA market used it.
- `totalLiquidity` clusters tightly at **$100-1000 MANA**. The single highest was $1590 ("Who will win the 2027 NBA Championship").
- `uniqueBettorCount` ranges 4-36 with median around 20.
- Several listed markets are joke questions ("There would be an NBA player over 8ft tall by 2045", "An NBA game features AI commentary by 2030?") which suggests the AMM-priced `probability` field is NOT a calibrated consensus, it is the result of a few small bets and the AMM curve.

### 1.4 Mid-price reliability at low volume

Manifold uses a CPMM (constant product market maker) for binary markets. At totalLiquidity = $100 MANA with 5 bettors, the displayed probability is essentially "where one or two participants' modest bets pushed the curve". It is not informative as a crowd consensus. Even at $1000 MANA, the AMM is thin: a $20 directional bet moves the price by several cents.

For v1's purposes, **Manifold mids on these sample markets are not signal-bearing relative to Kalshi mids that have actual retail USD orderflow attached.** This is even before the play-money-vs-real-money calibration question.

### 1.5 Could Manifold work for a different v1 universe?

Probably not at v1's scale. Manifold is designed for personal-curiosity questions and political markets. Where it has volume and bettor count, it tends to be on politics, AI/tech, or social topics. Sports markets are sparse and shallow.

### 1.6 Verdict on Manifold

**Not useful as a fade-filter for v1.** Reference-only. Listed in the recommendation matrix for completeness, but I would not have v4 Track A depend on it.

---

## 2. PredictIt

### 2.1 API status

`https://www.predictit.org/api/marketdata/all/` returned 200 with 292 active markets. No auth, no rate-limit hit. The schema is documented (`name`, `shortName`, `image`, `url`, `contracts`, `timeStamp`, `status`) with per-contract fields `lastTradePrice`, `bestBuyYesCost`, `bestBuyNoCost`, `bestSellYesCost`, `bestSellNoCost`, `lastClosePrice`.

### 2.2 Coverage on v1's universe

I categorized the 292 markets by keyword:

| Topic | Market count | % |
|---|---|---|
| Politics | 227 | 77.7% |
| Sports | **0** | 0.0% |
| Economy | 2 | 0.7% |
| Other (mostly political-adjacent) | 63 | 21.6% |

Sample political markets: "How many House seats will Republicans win in the 2026 midterm election?", "Who will win the 2028 Republican presidential nomination?", "Which party will control the Senate after the 2026 election?", "Will SCOTUS side with Trump on birthright citizenship?".

**PredictIt has zero coverage of v1's current sports universe.** This is consistent with PredictIt's CFTC no-action-letter scope (political and economic questions, capped at $850 per trader per market).

### 2.3 Future relevance

v1 currently does not trade political markets. If a future v4 iteration extends v1's eligible domain to include political Kalshi markets (KXPRES, KXSENATE, etc.), PredictIt becomes useful as a free second-opinion source on those markets. The API surface is simple enough that adding a "PredictIt second opinion" later is a one-day engineering task. For now, defer.

### 2.4 Verdict on PredictIt

**Not useful for v1's current sports universe. Document as known future reference for political-domain v1 extensions.**

---

## 3. the-odds-api

### 3.1 API status and free-tier scope (updated 2026-05-24)

`https://api.the-odds-api.com/v4/sports` returned 401 (MISSING_KEY) without a key, as documented. Documentation page at `https://the-odds-api.com/liveapi/guides/v4/` is publicly reachable.

**The free tier scope appears to have CHANGED since v2's `01-data-sources.md` was written.** v2 documented "free tier: 500 requests/month, sufficient for live closing-line snapshots, NOT for historical backfill" implying historical was paid-only. Re-reading the current pricing page (`https://the-odds-api.com/#get-access`) on 2026-05-24:

| Tier | Price | Credits/mo | Historical access? |
|---|---|---|---|
| Starter (Free) | $0 | 500 | YES (all tiers include it) |
| 20K | $30/mo | 20,000 | YES |
| 100K | $59/mo | 100,000 | YES |
| 5M | $119/mo | 5,000,000 | YES |
| 15M | $249/mo | 15,000,000 | YES |

Credit math from `the-odds-api.com/liveapi/guides/v4/#usage-quota-costs`:

- `GET /odds`: cost = (markets) x (regions). One market, one region = 1 credit.
- `GET /historical/odds`: cost = 10 x (markets) x (regions). One market, one region = **10 credits**.
- `GET /sports`, `GET /events`, `GET /historical/events`: FREE (no credit cost).

At 500 credits/mo free, that gives the operator one of:
- 500 live single-market odds checks (which is ~16 per day), OR
- 50 historical single-market odds lookups (one historical week of NFL plus headroom), OR
- some weighted combination

For Track A's purposes (live second opinion when v1 considers a trade): 500 live calls/mo is enough for the current cadence (v1 places ~15-20 attempted orders per 15-minute loop bursts, with most trades in resting state for days). The bot would only need to consult the-odds-api at the moment of considering a new entry, and only on markets that v1's scanner has already pre-qualified. That is maybe 30-60 candidate checks per week or 120-240/month, well within 500.

### 3.2 League coverage vs v1's universe

The documentation example response lists these sport keys, all relevant to v1:

| odds-api sport key | v1 series-prefixes covered |
|---|---|
| `americanfootball_nfl` | KXNFLGAME, KXNFLWINS, KXNFLPLAYOFF (with caveats: futures availability not confirmed) |
| `americanfootball_ncaaf` | KXNCAAFGAME, KXNCAAFPLAYOFF |
| `basketball_nba` | KXNBAPLAYOFFWINS, KXNBAWINS, KXNBAPLAYOFF |
| `basketball_wnba` | KXWNBAWINS |
| `baseball_mlb` | KXMLBGAME, KXMLBWINS, KXMLBPLAYOFFS |
| `icehockey_nhl` | KXNEXTTEAMNHL (via team-related futures), KXNHL* series |
| `soccer_usa_mls` | KXMLSGAME, KXMLSPLAYOFFS |
| `soccer_fifa_world_cup` (likely; need to confirm with key) | KXWCGAME, KXWCSQUAD, KXWCSTAGEOFELIM |
| `mma_mixed_martial_arts` | KXUFCFIGHT |
| `boxing_boxing` | KXBOXING |

This is **excellent coverage** of v1's sports universe. The-odds-api aggregates 30+ US-licensed sportsbooks (DraftKings, FanDuel, BetMGM, etc.). For game-resolution markets (KXNFLGAME and similar), the sportsbook line is essentially a competing institutional consensus. For futures (KXNFLWINS, KXNBAWINS), sportsbook win-totals lines are also available though less frequently updated.

### 3.3 What the-odds-api does NOT do

- It does NOT cover Kalshi's idiosyncratic series like KXMLBSTATCOUNT (statcast "immaculate inning" props), KXNFLTRADE (player trade markets), KXNEXTTEAMNFL (player destination markets), KXCS2 (esports), KXFOMEN (Formula 1), KXBALLONDOR. Sportsbooks DO carry F1 winner and Ballon d'Or but the-odds-api does not enumerate them by default.
- It cannot serve as a Polymarket-equivalent "second prediction market" since it is sportsbook lines, not prediction-market mids. The data shape is different: market line (e.g. -110 / +250) vs implied probability. The conversion to implied probability has a vig component (~5-7% overround) that must be removed.
- Historical bounded by sportsbook history. According to the docs, historical depth varies by sport but is typically months to a few years.

### 3.4 Polymarket-vs-the-odds-api compatibility note

The master plan asked specifically whether the-odds-api is a "live filter" candidate (compatible with v4 Track A) or a "historical training" candidate. **Free tier supports BOTH** under the updated pricing, but the historical credit cost (10x multiplier) makes it expensive for full backfill. For a TRACK-A-LIVE-FILTER role at v1's cadence, free tier is sufficient indefinitely.

### 3.5 Operator action required

The operator has NOT signed up. Confirmed by checking `.env` for any `ODDS` keys: none present.

To sign up:
1. Visit https://the-odds-api.com/#get-access
2. Choose "Starter (Free)" tier
3. Enter email and create account
4. Copy the API key from the dashboard
5. Add `THE_ODDS_API_KEY=<key>` to `.env` (operator-only action; do not have agents touch `.env`)

Total time: 5 minutes. Cost: $0. No payment information requested. No credit card on file.

### 3.6 Verdict on the-odds-api

**The most promising external second-opinion source for v1's universe.** Free tier suffices for live filter use. Operator action is trivial. **Recommend the operator sign up and that v4 Phase 2 Track A include the-odds-api as a secondary second-opinion source on game-resolution markets, alongside Polymarket Global where Polymarket has the corresponding event.**

---

## 4. Polymarket US

### 4.1 Status as of 2026-05-24

- Landing page `https://www.polymarketexchange.com/` returns 200 and renders.
- Developer API docs at `https://apidocs.polymarketexchange.com/` return 307 (redirect), implying access-gated as documented in v2.
- iOS app launched May 12, 2026 (waitlist removed) per `research/v2/02-polymarket-arb-research.md`.
- API access still requires `onboarding@qcex.com` code.

### 4.2 Coverage vs v1's universe

I cannot probe the Polymarket US market catalog without API access. Public industry coverage (which I cross-checked against the v2 brief) says:

- "Only sports markets in beta" as of May 2026.
- Aggregate volume ~$5M/week (Sacra cite from v2 brief), versus Polymarket Global's ~$2.1B/week. About 1/420th of the Global liquidity.
- Specific leagues live: unverified without API access. The May 21 2026 Covers article on parlay-style contracts being filed with the CFTC suggests Polymarket US is still adding feature scope, not building out league catalog.

### 4.3 Why this is not yet viable for v4

Three structural reasons (inherited from v2 brief, still hold):

1. **API gating.** The retail individual eligibility for partner-API access is unconfirmed. Reaching `onboarding@qcex.com` is an operator-only action that may not even succeed for an individual retail account.
2. **Liquidity.** $5M/week aggregate is way below the threshold where prediction-market mids carry meaningful signal. Even at 1/100th of v1's $32 capital, the per-market depth at v1's resting price band would be too thin to give reliable second-opinion signal.
3. **Setup cost.** Ed25519-signing client + KYC + ACH funding + onboarding email + uncertain API approval. For a "small fraction of v1's universe might be covered" expected payoff, the engineering and operational cost is wildly disproportionate.

### 4.4 When this becomes worth revisiting

Per the v2 brief, the trigger to revisit is: Polymarket US weekly volume reaches ~$50M (10x current) AND public API access is opened. Realistically this is 6-12+ months out.

### 4.5 Verdict on Polymarket US

**Not yet viable. Defer to a future v5+ research cycle if Polymarket US grows significantly.**

---

## 5. Internal Kalshi cross-market consistency

This is the no-external-venue fallback the master plan asked V4-D to think creatively about. I built and ran a feasibility probe (`scripts/v4/probe_cross_market_consistency.py`).

### 5.1 The mechanism

Within Kalshi, several series form a consistent "implied team strength" lattice:

- **KXNFLWINS-{TEAM}-{YEAR}-T{k}** = P(team wins >= k games) is monotonically NON-INCREASING in k.
  - If T8 trades at 0.77 and T7 trades at 0.37, ARBITRAGE: P(wins>=7) cannot be LESS THAN P(wins>=8). One of the two prices must be wrong.
- **KXNFLPLAYOFF-{YEAR}-{TEAM}** = P(team makes playoffs). Should be RELATED to win-total: roughly, P(playoff) ~ P(wins >= some-threshold-call-it-k*) where k* is the historical NFL wins-cutoff for playoff seeding (~9 wins in the 17-game era).
- **KXNFLSB-{YEAR}-{TEAM}** = P(team wins Super Bowl). Should be < P(playoff). The ratio P(SB|playoff) ~ 1/14 for a generic playoff team in a 14-team-playoff format, though varies by team strength.

This is a CONSTRAINT-CHECK approach, not a forecast-extension approach. v1 needs a "second opinion" before placing a trade. The internal second opinion is: **if the rest of the implied-team-strength lattice disagrees with the price v1 is about to pay, fade the trade.**

### 5.2 Empirical feasibility on v3's inventory snapshot

`data/v3/probe_inventory_all_markets.parquet` has T-35d VWAP prices for v1-eligible-style sports markets. I audited monotonicity violations within team-season win-total ladders. Pre-results audit definition: a violation is a pair (Tk, Tk+1) where price(Tk+1) > price(Tk) + 1c (1c noise band).

**Results:**

| Series | Total markets | With T-35 price | Team-seasons with 3+ thresholds | Pairs audited | Pairs in violation | Violation rate | Mean violation spread (c) | p95 spread (c) |
|---|---|---|---|---|---|---|---|---|
| KXNFLWINS | 955 | 234 | 32 | 174 | **36** | **20.7%** | 11.2 | 37.7 |
| KXMLBWINS | 150 | 19 | 2 | 4 | 0 | 0.0% | n/a | n/a |
| KXNBAWINS | 270 | 101 | 22 | 65 | 1 | 1.5% | 1.0 | 1.0 |

**Key reading:** NFL has a lot of violations and the spreads are large. MLB and NBA do not.

Why the asymmetry? MLB has only 2 team-seasons with 3+ threshold ladders in this inventory, so we cannot draw conclusions. NBA has 22 ladders and is essentially MONOTONE (1 trivial 1c violation in 65 pairs). NFL has 32 ladders with substantial violations.

Hypothesis on the NFL asymmetry: KXNFLWINS markets have wider threshold spacing (every integer 2 through 16) and lower per-threshold liquidity because retail interest is concentrated on a few "round number" thresholds (7, 8, 9, 10). The thin thresholds drift away from monotonicity due to last-trade noise. This is the same mechanism that creates the cross-market arbitrage opportunity in the first place.

### 5.3 Realized direction on violations

For each violation pair, I checked whether both contracts resolved. The "monotone-fix correct" outcome is: high-threshold resolves NO, low-threshold resolves YES (i.e. the high-threshold contract was OVERPRICED).

| Series | Realized "short high-threshold correct" | "short high-threshold wrong" | Resolved-as-tie | Hit rate excluding ties |
|---|---|---|---|---|
| KXNFLWINS | **6** | **0** | 30 | **100.0%** |

Six non-tie cases is small but the cleanness is striking. The 30 ties happened because both contracts resolved YES (the team blew past both thresholds) or both NO (the team fell short of both). In the 6 cases where the two contracts resolved DIFFERENTLY, the high-threshold contract resolved NO in all 6.

### 5.4 Realized illustration: IND 25B ladder

The Indianapolis Colts 2025 season (`ARI` truly was `IND` after re-parsing) was a textbook case:

| Ticker | Threshold | T-35 price | Resolved |
|---|---|---|---|
| KXNFLWINS-IND-25B-T4 | 4 | 0.860 | YES |
| KXNFLWINS-IND-25B-T5 | 5 | 0.860 | YES |
| KXNFLWINS-IND-25B-T6 | 6 | 0.823 | YES |
| KXNFLWINS-IND-25B-T7 | 7 | **0.370** | YES |
| **KXNFLWINS-IND-25B-T8** | 8 | **0.765** | **NO** |
| KXNFLWINS-IND-25B-T9 | 9 | 0.728 | NO |
| KXNFLWINS-IND-25B-T10 | 10 | 0.839 | NO |

T7 at 0.37 and T8 at 0.77 is a 40c monotonicity violation. T7 resolved YES (Colts won at least 7) and T8 resolved NO (did not win 8). A trader who bought T7 at 0.37 made +63c (less 2c fees = +61c net). A trader who SHORTED T8 at 0.77 (or bought NO at 0.23) made +23c minus fees.

A v1-equivalent strategy ("buy YES at >= 0.70") would NOT have triggered on T7 (price below 0.70) and WOULD have triggered on T8 (price 0.765, just above 0.70). v1 would have BOUGHT a losing position on T8 at 0.765. **An internal-consistency check would have flagged T8 as cross-market-overpriced (T7 at 0.37 implies T8 should be < 0.37, not 0.77) and a v1+cross-market-filter would have skipped this trade.**

### 5.5 Operationalization sketch

Pseudocode for the Track A fallback when Polymarket is unavailable:

```python
def cross_market_filter(kalshi_ticker, kalshi_mid):
    series = ticker_series(kalshi_ticker)
    if series not in {"KXNFLWINS", "KXNBAWINS", "KXMLBWINS"}:
        return "no_signal"
    team, year, threshold = parse(kalshi_ticker)
    siblings = fetch_kalshi_markets_for_team_season(series, team, year)
    if len(siblings) < 3:
        return "no_signal"
    # Build the implied step function: price(T_k) for each k
    ladder = sorted([(s.threshold, s.mid) for s in siblings])
    # Monotone fit (isotonic regression, non-increasing)
    fit = isotonic_decreasing_fit(ladder)
    fit_at_target = fit(threshold)
    if abs(kalshi_mid - fit_at_target) < CROSS_MARKET_THRESHOLD_C / 100:
        return "consistent"
    if kalshi_mid > fit_at_target + CROSS_MARKET_THRESHOLD_C / 100:
        return "fade"  # this contract is over-priced relative to siblings
    return "favor"  # this contract is under-priced
```

The `CROSS_MARKET_THRESHOLD_C` analogue of Polymarket's `FADE_THRESHOLD_CENTS`. v3's Polymarket-fade-filter used 5-15c; the NFLWINS p75 violation spread is 11.7c, so a 10c threshold would fire on roughly half the violations.

### 5.6 Coverage of v1's universe

The internal cross-market consistency approach IS USEFUL for any series with a threshold ladder. Looking at v3 inventory:

| Series | Has threshold ladder? | v1 universe weight (orders attempted) |
|---|---|---|
| KXNFLWINS | YES | 2 attempted orders, 103 v3-eligible historical |
| KXNBAWINS | YES | 0 attempted, 16 v3-eligible historical |
| KXMLBWINS | YES | 4 attempted orders, 10 v3-eligible historical |
| KXWNBAWINS | YES (smaller) | 1 attempted order |
| KXNBAPLAYOFFWINS | YES | 4 attempted orders, 2 acked |
| KXNFLPLAYOFF | weak (binary not ladder) | 3 attempted orders |
| KXBOXING, KXUFCFIGHT, KXWCGAME, KXCS2, KXFOMEN | NO (single-event binary) | dominant slice of currently-resting orders |

**The internal cross-market filter is well-suited to win-total ladder series but does NOT apply to game-resolution binaries or single-event prop binaries.** That is most of v1's currently-resting universe.

A natural complement: for game-resolution binaries (KXWCGAME, KXNFLGAME, etc.), use the-odds-api sportsbook line as second opinion. For win-total ladders (KXNFLWINS, KXNBAWINS), use internal cross-market consistency. For single-event props with no obvious second-opinion source (KXBOXING, KXUFCFIGHT), this approach offers NO filter; the trade proceeds on v1's bare logic.

### 5.7 Verdict on internal cross-market consistency

**Mechanically sound, free, always-available, but coverage is limited to threshold-ladder series.** Recommend including it as a complementary filter alongside whatever external second-opinion the operator activates. Highest value on KXNFLWINS series (n=32 ladders, 20.7% violation rate, large spreads).

Critic flag for future work: the n=6 realized non-tie cases is small. A Phase-2 implementation should include leak-free retrospective backtesting (which is easy because the v3 inventory already has T-35 prices and resolved outcomes for 32 NFL team-seasons).

---

## 6. Recommendation matrix

For each alternative venue/approach:

| Venue / approach | Coverage of v1 (qualitative) | Auth required | Cost | Latency | Recommendation |
|---|---|---|---|---|---|
| Polymarket Global | medium-low (V4-A measures) | none | free | low | Primary if V4-A coverage > 30% |
| ManifoldMarkets | low; correlated not exact | none | free | low | Reference only; not load-bearing |
| PredictIt | very low (sports = 0) | none | free | low | Future-only; political markets if v1 extends |
| the-odds-api free tier | HIGH for v1 sports universe | email signup | free 500 credits/mo | low | **Strongly recommend operator sign up** |
| the-odds-api 20K paid | HIGH | email + $30/mo | $30/mo | low | Future if free tier insufficient |
| Polymarket US | low (sports beta only) | code from onboarding@qcex.com | free in theory | low | Defer 6+ months |
| Internal Kalshi cross-market (NFLWINS) | HIGH on win-total ladders, ZERO on binaries | none | free | low | **Always-on backup for ladder series** |

### Priority order for v4 Track A's fallback

1. **Primary**: Polymarket Global as live fade-filter (per master plan), conditional on V4-A finding > 30% coverage.
2. **Universal backup #1**: internal Kalshi cross-market consistency on threshold-ladder series (KXNFLWINS, KXNBAWINS, KXMLBWINS, KXWNBAWINS, KXNBAPLAYOFFWINS). Adds defensive filter on the team-strength-implied price ladder. Free, no operator action.
3. **External backup #2**: the-odds-api free tier as live sportsbook-line second-opinion on game-resolution markets (KXNFLGAME, KXMLBGAME, KXNCAAFGAME, KXMLSGAME, KXWCGAME). Requires 5-minute operator signup.
4. ManifoldMarkets and PredictIt: documented but not load-bearing.
5. Polymarket US: explicit defer.

---

## 7. Operator-action items

Required for v4 Track A as architected:

1. **Sign up for the-odds-api free tier.** 5 minutes, email only, no payment information. Add `THE_ODDS_API_KEY=<key>` to `.env`. Free 500 credits per month, covers v1's anticipated live cadence.

Optional / future:

2. If v4 Phase 2 demonstrates value from the-odds-api second-opinion AND the 500-credit cap binds, consider upgrading to the $30/mo 20,000-credit tier. Approve only after Phase 2 has retrospective evidence of value.
3. If v1's universe later extends to political Kalshi markets, sign up for nothing on PredictIt (the public marketdata feed is keyless), but write a PredictIt fetch module.
4. If Polymarket US grows substantially in the next 6-12 months, revisit access via `onboarding@qcex.com`.

NOT required:

- ManifoldMarkets needs nothing (no auth) but is not recommended for use.
- Polymarket Global is the V4-A primary path, not this report.

---

## 8. Caveats and unknowns

1. **the-odds-api 500-credit free tier consumption.** I have NOT confirmed live credit consumption rate against v1's actual cadence (cannot test without operator sign-up). The estimate of 120-240 calls/month assumes Track A checks the-odds-api ONLY when v1 has a candidate. If Track A logic ever loops every 15 minutes on all open candidates, the credit count could blow past 500.

2. **Manifold MANA-vs-CASH calibration.** Manifold does have a small real-money "CASH" track and tournament markets. I did not probe that subset because the 8 v1 tickers I tried returned MANA matches across all variants. A more thorough audit could check whether Manifold's CASH markets have better calibration; I judged this not worth the agent-clock given how thin Manifold's sports coverage is generally.

3. **Internal cross-market n=6 realized cases.** Statistically insignificant. The 100% hit rate is a directional indicator, not a confidence-bounded measurement. A Phase 2 implementation MUST do leak-free retrospective backtest on the full v3 inventory before any live activation.

4. **Polymarket US public catalog.** I could not enumerate it without API access. Public industry coverage says sports beta only and ~$5M/week volume; this could be inaccurate. The verdict ("not yet viable") would hold even if catalog is 2x larger than reported, given the structural liquidity gap.

5. **Settlement-divergence risk for the-odds-api second-opinion role.** Sportsbooks settle their LINES on specific stat-source rules. Kalshi settles its markets on its own source rules. These can disagree (especially on injured-player rulings, weather cancellations, suspension events). When using the-odds-api as a fade-filter, the divergence risk is muted (we are NOT trading both sides; we are using the sportsbook line as a probability estimate for the Kalshi market). But the second-opinion is only as good as the sportsbook line's resolution agreement with the Kalshi rule. Worth noting but not a blocker.

6. **NFL ladder violation rate likely degrades with finer threshold spacing.** The 20.7% violation rate on KXNFLWINS T-35d prices may shrink as we get closer to game time (T-7d, T-1d) when liquidity concentrates. The CROSS_MARKET_THRESHOLD_C parameter would need OOS calibration across the time horizons that v1 actually trades at.

---

## 9. Output artifacts

| Path | Contents |
|---|---|
| `data/v4/multi_venue_probe.json` | Raw probe results for Manifold/PredictIt/the-odds-api/Polymarket US |
| `data/v4/manifold_widened_probe.json` | Multi-query Manifold coverage audit on 8 v1 tickers |
| `data/v4/cross_market_consistency.json` | NFL/MLB/NBA monotonicity-violation audit on v3 inventory |
| `scripts/v4/probe_multi_venue.py` | Reproducible primary probe |
| `scripts/v4/probe_manifold_widen.py` | Reproducible widened Manifold probe |
| `scripts/v4/probe_cross_market_consistency.py` | Reproducible cross-market consistency audit |

---

## 10. Sources

- `research/v2/01-data-sources.md` Section 3.7 (the-odds-api v2 baseline; pricing now superseded)
- `research/v2/02-polymarket-arb-research.md` (Polymarket US baseline from v2)
- `research/v3/03-poly-kalshi-divergence.md` (V3-C Polymarket-Kalshi divergence)
- `research/v4/00-master-plan.md` Section 6.3 (V4-D scope)
- `https://api.manifold.markets/v0/` (Manifold API; reachable, no auth)
- `https://www.predictit.org/api/marketdata/all/` (PredictIt public feed; reachable, no auth)
- `https://the-odds-api.com/liveapi/guides/v4/` (the-odds-api docs)
- `https://the-odds-api.com/#get-access` (the-odds-api current pricing tiers)
- `https://www.polymarketexchange.com/` (Polymarket US landing; 200 but no public catalog)
- `https://apidocs.polymarketexchange.com/` (Polymarket US dev docs; 307 redirect, access-gated)
- `data/v3/probe_inventory_all_markets.parquet` (V3 inventory used for cross-market consistency audit)
- `data/live_trades/state.json` (v1 currently-resting orders snapshot at probe time)
