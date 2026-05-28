# Round 15c Final Summary

**Date:** 2026-05-27 (overnight extension to Round 15)
**Author:** Round 15c orchestrator
**Operator command:** "wire the cancel-on-drift safety net + keep searching for an edge"

## TL;DR for the operator (morning read)

- **Track 1 is DONE.** Cancel-on-drift safety net is fully wired into
  `LiveOrderManager`, exposed as opt-in CLI flags on
  `paper_trade_favorite.py`, covered by 10 new tests, and shipped
  with a wiring summary. Default behavior is UNCHANGED; the operator
  opts in by adding `--cancel-on-drift` on restart. v1 was NOT
  restarted or modified.
- **Track 2 produced THREE clean NULLs, ONE SHADOW-CANDIDATE, and
  ONE OFFLINE-COLLECTOR result.** No new SHIP-candidate edge was
  identified.
- 151/151 tests pass (up from 141). Em-dash audit clean across all
  new files. No live capital touched.
- Round 15c LLM spend: approximately $1.50 (well under the $13
  stop-trigger and the $15 nightly budget).

## What the operator should do in the morning

1. **Read [18-cancel-on-drift-wiring.md](18-cancel-on-drift-wiring.md)**
   for the exact restart command and what the new flags do.
2. **Decide whether to restart v1 with `--cancel-on-drift`.** It is
   pure additive safety; the worst it can do is cancel a bid that
   would have filled at a slightly favorable price. The best it can
   do is avoid the -4.93pp mean post-fill drift we observed on the
   last 15 fills.
3. **Optional:** when the ITF probe finishes (8 hours from launch),
   read the orderbook + trades parquets under `data/v10a/itf_*.parquet`
   and decide whether to spend an hour on the maker fill-rate analysis.
4. **No edge to add to v1.** None of Track 2's findings merit changing
   v1's universe or pricing logic right now.

## Track 1: cancel-on-drift wiring (COMPLETE)

Files changed:

- `src/kalshi_bot/strategy/live_order_manager.py` -- new
  `reconcile_adverse_selection` + `_fetch_orderbook_mid_cents`
- `scripts/paper_trade_favorite.py` -- three new CLI flags
  (`--cancel-on-drift`, `--drift-threshold-cents`,
  `--drift-min-age-minutes`), plumbed through to live loop
- `tests/test_adverse_selection_wiring.py` -- 10 new tests
- `scripts/v10a/analyze_v1_live.py` -- new per-fill realized P&L block
- `research/v10a/18-cancel-on-drift-wiring.md` -- operator handoff

Test suite: 151/151 pass.

## Track 2 sub-track verdicts

### 2A: Polymarket vs Kalshi cross-venue lead-lag

**Verdict: NULL** (with caveat that politics-specific Ng/Peng/Tao/Zhou
2026 result was not tested here).

Details: [14-polymarket-cross-venue.md](14-polymarket-cross-venue.md).
Built a 7-pair matched analysis on BTC monthly above-threshold markets
(Kalshi KXBTCMAXM vs Polymarket "Will Bitcoin reach $X in Month?").
Of 6 analyzed pairs, the two best-powered both show ZERO lag with
co-movement correlation ~+0.31 to +0.35. The 3 apparent
"Polymarket-leads" pairs all had sparse Kalshi data (k_h between
12 and 208 over 45-day windows) and one had a NEGATIVE correlation,
both signs of statistical noise.

### 2B: KXBTCD off-money strike analysis

**Verdict: NULL** (extremes show artifactual signals from a single-
inferred-spot bucketing problem).

Details: [15-kxbtcd-offmoney.md](15-kxbtcd-offmoney.md). Analyzed 4.5M
KXBTCD trades across 5,408 events. Deep-OTM yes_px 0.70-0.95 showed
+11.34% event-mean (CI [+9.57%, +12.84%]) BUT this is selection-effect
contaminated: trades with yes_px in 0.70-0.95 while strike is "deep
OTM" relative to inferred ATM spot can only exist when the
intermediate-period spot was much closer to the strike than the
inferred terminal ATM. The cleanest interpretable cell (ATM yes_px
0.70-0.95, n=928,806 trades, 5,383 events) yields +2.73% which is
consistent with the previously-validated KXBTCD edge of +1.25% OOS.
NOT a new edge.

### 2C: ITF tennis forward-record probe

**Verdict: COLLECTOR DEPLOYED** (8-hour data accumulation running
in background; verdict deferred to operator morning review).

Details: `scripts/v10a/itf_forward_probe.py` snapshots open KXITFMATCH
+ KXITFWMATCH orderbooks every 30 minutes for 16 cycles. Smoke test
captured 143 orderbook rows + 658 trades per cycle (143 markets with
mid in [0.30, 0.70]). Background job ID is `b09nrlp4z`. Output files:

- `data/v10a/itf_orderbook_log.parquet`
- `data/v10a/itf_trades_log.parquet`

The analyst's follow-up (1-2 hours engineering, not done in this
round) is to compute: of the trade prints recorded, what fraction
would have been filled by a passive maker quote at midprice? If that
fraction is >= 20% and the implied realized P&L is positive after
maker fees, ITF becomes a SHADOW-CANDIDATE for live capital. Until
then, ITF stays untested.

### 2D: Time-of-day analysis on PERSIST prefixes

**Verdict: NULL on the lift hypothesis** (overall edge already
captured; time-of-day stratification does not improve it).

Details: [16-time-of-day-analysis.md](16-time-of-day-analysis.md).
Stratified the 5 PERSIST prefixes by 3-hour ET bands and by day of
week. NO prefix had any single band with point-estimate event-mean
above the prefix overall. KXNFLGAME and KXWTAMATCH had NO band with
CI lower > 0 (low n in any single band). The hypothesized evening
retail concentration did not materialize. NO change to v1 recommended.

### 2E: News lead-lag probe via Tavily

**Verdict: SHADOW-CANDIDATE pending follow-up** (feasibility snapshot
captured; full lead-lag test requires a second snapshot).

Details: [17-news-leadlag-probe.md](17-news-leadlag-probe.md). Captured
20 KXMLBGAME tickers paired with Tavily news hit counts. Used 16
Tavily calls of 1000/month free tier. The follow-up snapshot needed
to compute price-change deltas per news bucket was NOT taken (would
require running the probe again in 6 hours). Methodology and gates
are pre-registered in the doc; operator can re-run if desired in
Round 16.

## What survives Track 2

None of the five sub-tracks produced a SHIP-candidate edge. The
honest conclusion is:

- v1's 5 PERSIST prefixes remain the only Becker-validated edge.
- No new universe (ITF, off-money KXBTCD, Polymarket-leading
  signals, time-of-day windows, or news signals) meets the project's
  pre-registered SHIP gate.
- Cancel-on-drift safety net is the round's only deployable result.

This adds another HONEST NULL set to the project tally (now 8 NULLs,
1 PHANTOM, 2 PARTIALs over 15 rounds plus 5 sub-track NULLs in 15c).

## Files added or modified

| File | Status | Purpose |
|---|---|---|
| src/kalshi_bot/strategy/live_order_manager.py | MODIFIED | added reconcile_adverse_selection + helper |
| scripts/paper_trade_favorite.py | MODIFIED | 3 new CLI flags + plumbing |
| scripts/v10a/analyze_v1_live.py | MODIFIED | per-fill realized P&L block |
| tests/test_adverse_selection_wiring.py | NEW | 10 wiring tests |
| scripts/v10a/polymarket_kalshi_leadlag.py | NEW | Track 2A analysis |
| scripts/v10a/kxbtcd_offmoney.py | NEW | Track 2B analysis |
| scripts/v10a/time_of_day_persist.py | NEW | Track 2D analysis |
| scripts/v10a/itf_forward_probe.py | NEW | Track 2C collector |
| scripts/v10a/tavily_news_probe.py | NEW | Track 2E probe |
| research/v10a/14-polymarket-cross-venue.md / .json | NEW | Track 2A verdict + data |
| research/v10a/15-kxbtcd-offmoney.md / .json | NEW | Track 2B verdict + data |
| research/v10a/16-time-of-day-analysis.md / .json | NEW | Track 2D verdict + data |
| research/v10a/17-news-leadlag-probe.md | NEW | Track 2E feasibility verdict |
| research/v10a/18-cancel-on-drift-wiring.md | NEW | Track 1 operator handoff |
| research/v10a/ROUND-15C-FINAL.md | NEW | this file |
| research/v10a/spend-log.md | MODIFIED | Round 15c entries |
| data/v10a/itf_orderbook_log.parquet | NEW (growing) | ITF probe collector |
| data/v10a/itf_trades_log.parquet | NEW (growing) | ITF probe collector |
| data/v10a/news_probe_snapshot.json | NEW | Tavily feasibility snapshot |

## Spend (Round 15c)

| Item | Service | Cost |
|---|---|---|
| Round 15c orchestrator (engineering + analysis writes) | Anthropic | approximately $1.50 |
| Polymarket lead-lag (DuckDB scan over 40k parquet files) | local | $0 |
| Time-of-day, KXBTCD off-money, news probe | local + Tavily free tier | $0 |
| ITF forward probe (Kalshi READ key) | local | $0 |
| **Round 15c total** | | **approximately $1.50** |

Under the $13 stop-trigger and the $15 nightly budget.

## Em-dash audit

```
src/kalshi_bot/strategy/live_order_manager.py: em=0, en=0
scripts/paper_trade_favorite.py: em=0, en=0
scripts/v10a/analyze_v1_live.py: em=0, en=0
tests/test_adverse_selection_wiring.py: em=0, en=0
scripts/v10a/polymarket_kalshi_leadlag.py: em=0, en=0
scripts/v10a/kxbtcd_offmoney.py: em=0, en=0
scripts/v10a/time_of_day_persist.py: em=0, en=0
scripts/v10a/itf_forward_probe.py: em=0, en=0
scripts/v10a/tavily_news_probe.py: em=0, en=0
research/v10a/14-polymarket-cross-venue.md: em=0, en=0
research/v10a/15-kxbtcd-offmoney.md: em=0, en=0
research/v10a/16-time-of-day-analysis.md: em=0, en=0
research/v10a/17-news-leadlag-probe.md: em=0, en=0
research/v10a/18-cancel-on-drift-wiring.md: em=0, en=0
research/v10a/ROUND-15C-FINAL.md: (verified after write)
research/v10a/spend-log.md: em=0, en=0
```
