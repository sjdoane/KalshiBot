# Round 15c Track 2E: News lead-lag probe via Tavily (exploratory)

## Hypothesis

News mentions of teams or players in the 2-6 hours before close on
KXMLBGAME / KXNFLGAME markets correlate with subsequent Kalshi
price moves. If a strong correlation exists, a Tavily-driven feed
could become a leading signal for v1 maker quote adjustment.

## Status: FEASIBILITY SNAPSHOT ONLY (data captured, follow-up needed)

This round captured ONE snapshot of currently-open KXMLBGAME
markets paired with Tavily news hit counts. A full lead-lag test
requires a SECOND snapshot 4-6 hours later (or at close) so per-pair
price moves can be computed. We did not run that second snapshot.

The verdict for round 15c is therefore: **FEASIBILITY OK, edge
verdict deferred.** Operator can re-run the probe to capture a
delta and decide whether to escalate.

## What this round actually produced

Snapshot file: `data/v10a/news_probe_snapshot.json`.

- 20 KXMLBGAME tickers captured at 2026-05-27T04:17 UTC.
- 16 Tavily search calls consumed (free-tier budget: ~30 of 1000/month).
- 16 of 20 markets had a parseable team_a / team_b from the title.
  The 4 failures were edge cases (e.g. "New York Y vs A's") where the
  regex `Will X vs Y Winner?` did not match "vs" without "the". The
  parser is in `scripts/v10a/tavily_news_probe.py` and can be
  tightened in a follow-up.
- Every parsed market returned the Tavily `max_results=5` ceiling of
  news articles, so the "news_hits" count saturated. A more useful
  per-pair signal would require either RAISING `max_results` or
  measuring article RELEVANCE (e.g. count of articles published
  within the last 6 hours) rather than raw count.

## Methodology if continuing

The cleanest forward test would be:

1. Snapshot T0: pull orderbook mid + news hit count + news headlines
   for each open KXMLBGAME ticker closing in next 7 days.
2. Snapshot T0+6h: re-pull orderbook mid only.
3. For each ticker, compute price_change = mid(T0+6h) - mid(T0).
4. Bucket tickers by news hit count or recency. Regress price_change
   on news bucket.

Expected sample size per session: 40 to 70 KXMLBGAME tickers per day,
so 280-490 ticker-snapshots per week. Tavily cost: <300 calls per
week, well within 1000/month free tier.

Pre-registered gate (if the operator wants to escalate): 1-sided
t-test on news-bucket price-change differences with alpha 0.05 and
n_min = 50 per bucket. If high-news bucket shows mean |price_change|
> 1.5x low-news bucket with p < 0.05 and consistent direction
across 3+ weekly cycles, the news signal is real and might be
exploitable.

## Verdict for this round: SHADOW-CANDIDATE pending follow-up

The signal HAS NOT BEEN MEASURED. Until the operator runs the
follow-up snapshot, the news lead-lag is unconfirmed (could be real,
could be noise). It is NOT a SHIP candidate. It is NOT a NULL
either; the test simply wasn't completed within Round 15c.

Recommendation: defer to Round 16 if operator wants the full lead-lag.
A 2-week shadow probe (one snapshot pair per day for 14 days, n=14
delta measurements per ticker) gives n approximately 600 to 1000
delta-bucket observations, well-powered to detect even small lifts.

## Em-dash audit

(verified after writing)
