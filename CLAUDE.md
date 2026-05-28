# Project Kalshi - Claude Instructions

This file is auto-loaded by Claude Code when working in this project
directory. It is your orientation document.

## What this project is

A retail Kalshi quant trading project with an operator-authorized
$100 capital ceiling (recommended $25 initial deployment; operator
can raise toward the ceiling as strategy validates, currently funded
at $32). Operator: California resident, USC. The mission is to pick
ONE defensible-positive-EV strategy, validate it out-of-sample,
paper-trade it, and go live with strict risk controls.

## Where this project stands

**Round 15c overnight outcomes (2026-05-27): cancel-on-drift safety net
WIRED, four NULL sub-tracks, one COLLECTOR deployed, no new SHIP edge.**

Track 1 (cancel-on-drift wiring) complete. `LiveOrderManager` gained
`reconcile_adverse_selection` + `_fetch_orderbook_mid_cents`.
`scripts/paper_trade_favorite.py` gained three opt-in CLI flags
(`--cancel-on-drift`, `--drift-threshold-cents` default 3,
`--drift-min-age-minutes` default 15), plumbed through
`one_loop_favorite_live(adverse_selection_cfg=...)`. The default v1
behavior is UNCHANGED unless the operator restarts with the new flag.
10 new wiring tests in `tests/test_adverse_selection_wiring.py`, full
suite 151/151 pass. `scripts/v10a/analyze_v1_live.py` gained a
per-fill realized P&L block for once v1's fills settle. Restart
command + operator handoff in `research/v10a/18-cancel-on-drift-wiring.md`.

Track 2 sub-track verdicts:
- 2A Polymarket vs Kalshi cross-venue lead-lag on BTC monthly above-
  threshold pairs: NULL. Best-powered pairs show lag=0 co-movement
  at +0.31 to +0.35 correlation. Ng/Peng/Tao/Zhou 2026 politics-
  specific lead does NOT generalize. See
  `research/v10a/14-polymarket-cross-venue.md`.
- 2B KXBTCD off-money strike analysis (4.5M trades, 5408 events):
  NULL. Apparent +11% edge in deep-OTM yes_px 0.70-0.95 is selection-
  effect contaminated (single-inferred-spot bucketing). Cleanest
  cell reproduces the Round 15b KXBTCD edge. See
  `research/v10a/15-kxbtcd-offmoney.md`.
- 2C ITF tennis forward-record probe: COLLECTOR DEPLOYED. 8-hour
  background job snapshots KXITFMATCH + KXITFWMATCH every 30 min for
  16 cycles. Output `data/v10a/itf_orderbook_log.parquet` +
  `itf_trades_log.parquet`. Operator can analyze maker fill rate
  after job finishes.
- 2D Time-of-day on PERSIST prefixes: NULL on lift hypothesis. NO
  prefix has any 3-hour ET band with event-mean ABOVE the prefix
  overall. NO change to v1 recommended. See
  `research/v10a/16-time-of-day-analysis.md`.
- 2E Tavily news lead-lag probe: SHADOW-CANDIDATE pending follow-up.
  T0 snapshot captured for 20 KXMLBGAME tickers (16 Tavily calls of
  1000/month free tier); T0+6h follow-up snapshot was NOT taken so
  full lead-lag is not computed. Methodology + gates pre-registered;
  operator can complete in Round 16. See
  `research/v10a/17-news-leadlag-probe.md`.

Round 15c LLM spend approximately $1.50 of $13 stop-trigger and $15
nightly budget. No live capital touched. v1 continues on $32 unchanged.
Cumulative project (Rounds 12-14 + v8 + v9 + Round 15a-c): 8 NULLs, 1
PHANTOM, 2 PARTIALs + 4 new Round 15c NULLs. v1's 5 PERSIST prefix
allowlist remains the only Becker-validated edge.

Round 15c final summary doc (operator morning starting point):
`research/v10a/ROUND-15C-FINAL.md`.

**Round 15 outcome (2026-05-27): V10-A NULL at methodology lock (pre
Phase 2 kill); session pivoting to empirical Becker exploration + Mohanty
pivot.** Operator authorized two parallel angles in Round 15: V10-A (Kim
arXiv 2602.07048 Granger lead-lag on Kalshi macro markets, this session)
and V10-B (multi-LLM ensemble on uncertain sports props, other session
window). V10-A revival hypothesis was that Kalshi macro markets pre April
2026 rebrand existed under shorter ticker prefixes (CPI, PAYROLLS, U3,
FEDDECISION) and that Becker prediction-market-analysis dataset (36 GB,
72.1 million Kalshi trades through November 2025) would capture them.

V10-A Phase 1 lit scout (agent v10A-2) surfaced three load-bearing
findings:
- Kim arXiv 2602.07048v2 reports NO fees, NO bid-ask, NO slippage in
  P&L. 54.5% win rate is gross-idealized; no published net-of-fee
  replication exists.
- Becker 2026 Finance category gross excess return is approximately
  +/-0.08% per trade on 4.4 million trades; essentially zero gross.
  Any retail edge from Kim's filter is structurally fragile.
- Only 2026 positive Kalshi-macro published result is Mohanty et al.
  arXiv 2604.01431 (April 2026), which uses Kalshi macro probability
  changes to predict crypto realized volatility at h=3 to h=5 days,
  with execution pivoted to Deribit options, NOT Kalshi.

V10-A Phase 1.5 methodology critic (agent v10A-3) on v2 lock fired
KILL with three KILLER findings:
1. **Becker trades schema lacks orderbook ask at trade time** (only
   trade_id, ticker, count, yes_price, no_price, taker_side,
   created_time). Any execution proxy reproduces v7-B confirmed
   phantom pattern (8/8 live bets lost, mean -$0.20, binomial
   p~0.004).
2. **LOCO + Granger lag-5 structurally infeasible at n=9 train events
   per series.** Reducing to lag 1 only is no longer Kim replication;
   switching to daily VWAP introduces serial correlation that breaks
   the F-test null distribution.
3. **Fee-aware breakeven 51.75% calibrated to wrong execution price.**
   Real breakeven varies from 32% at execution price 0.30 to 72% at
   price 0.70. Kim's 54.5% is below breakeven at any execution price
   above 0.55. Single-number gate G1 is uncalibrated.

Plus six IMPORTANTs (LLM filter rubber-stamp risk, $1 vs $50 notional
contradiction, anchoring audit logic inverted, multi-strike
independence violation, Diercks 2026 frequency mismatch, pre-flip-only
fallback violates load-bearing fact 3).

NEW FAILURE MODE F11 (Dataset Schema Phantom): pre-registering a
backtest gate that depends on an execution-price field that does not
exist in the chosen dataset schema. The strategy looks fireable on
paper but the data layer does not contain the required field. Fix
attempts (proxies, snapshots, next-trade fills) recreate the v7-B
phantom-baseline pattern in disguise. Checklist: before locking any
backtest gate, audit the dataset schema and verify every field
required for signal firing AND for execution pricing exists at the
timestamp the strategy needs it.

V10-A spend approximately $1.50 LLM ($0.50 lit scout, $0.40 critic,
$0.60 orchestrator), under $8 cap with $6.50 buffer.

V10-A artifacts in `research/v10a/` and `scripts/v10a/`:
- `FINAL-VERDICT.md` (kill rationale with F11)
- `A3-methodology-critique.md` (load-bearing kill document)
- `A2-methodology-lock-v2.md` (what V10-A would have looked like)
- `01-lit-delta.md` (2026 lit scout; 8 confirmed first-mover gaps:
  transfer entropy on Kalshi macro, Hawkes processes, cointegration
  VECM, Diebold-Yilmaz connectedness, fee-net P&L on Kim, LLM filter
  on non-Economics categories, cross-venue Polymarket-Kalshi macro
  lead-lag, Kim replication on April 2026 rebrand tickers)
- `03-strategic-synthesis.md` (pre-kill prior analysis)
- `spend-log.md` (running spend tracker)
- `scripts/v10a/inventory_becker_macro.py` (Becker macro inventory)
- `scripts/v10a/extract_becker.py` (Python zstandard extractor for
  Windows; bypasses scripts/install-tools.sh which is Linux/Mac only)
- `scripts/v10a/smoke_test_{fred, gemini, granger}.py` (all PASS)

Becker dataset is fully downloaded (36 GB) and being extracted in
this session. Operator authorized pivot to "investigating more angles
until you can find an edge" with open API budget. Session is now
pursuing empirical Becker exploration (find category x price band x
horizon cells with statistically significant post-Oct-2024 maker
excess return after fees) and Mohanty pivot feasibility (can the
Kalshi macro -> BTC vol signal be executed on Kalshi BTC markets
without going to Deribit). Round 15 NOT closed yet; closure pending
either an edge discovery or definitive exploration completion.

V10-B (parallel window) is also still running; round 15 closure
write-up should consolidate both V10-A and V10-B verdicts.

**Round 15b/c outcome (2026-05-27): EMPIRICAL EDGE DISCOVERY surfaced
six candidate maker-quoting strategies on Becker post-October-2024 data
with cluster-bootstrap CIs excluding zero.** After V10-A Kim replication
NULL'd at methodology lock, operator authorized continued investigation
("keep being thorough and investigating more angles until you can find
an edge"; "i would be willing to fund the API if you think it's the best
edge"). Becker dataset (36 GB compressed, 46 GB extracted, 72.1M Kalshi
trades, 67.9M post-October-2024) was downloaded and analyzed via two
independent passes:

Orchestrator prefix-level analysis (`research/v10a/08-edge-discovery-
results.md`) ran a cluster-bootstrap sweep across 13 candidate prefixes
with proper chronological train (Nov 2024 to Aug 2025) and OOS (Sep
2025 to Nov 2025) split. FIVE prefixes show PERSISTENT EDGE (train AND
OOS cluster-CIs both exclude zero on event-level inference):

| Prefix | Train mean (CI) | OOS mean (CI) | Train events | OOS events |
|---|---|---|---|---|
| KXWTAMATCH (WTA tennis) | +3.66% [+2.45, +4.87] | +3.27% [+2.13, +4.47] | 650 | 421 |
| KXATPMATCH (ATP tennis) | +4.01% [+2.83, +5.18] | +2.63% [+1.50, +3.77] | 656 | 471 |
| KXETHD (Ethereum daily) | +6.45% [+5.69, +7.20] | +2.46% [+1.58, +3.32] | 3543 | 1296 |
| KXBTCD (Bitcoin daily) | +1.86% [+1.62, +2.11] | +1.25% [+0.79, +1.69] | 4076 | 1327 |
| KXBTC (Bitcoin range) | +2.10% [+1.59, +2.58] | +0.93% [+0.16, +1.70] | 4045 | 1321 |

Independent agent at category-level (`research/v10a/05-becker-edge-
discovery.md`) surfaced side-selection bias as a textbook trap and then
identified combined-side LOCO-robust cells: Media maker midprice
[0.40, 0.60) +6.55pp net (138 prefixes, top-3 30%); Other maker
[0.60, 0.80) +2.40pp (1087 prefixes, top-3 7.3%, MOST DIVERSIFIED);
Entertainment maker [0.40, 0.60) +2.22pp. Side-selection bias warning:
naive per-side cells (e.g., "buy NO at 0.30 wins 56%") are a base-rate
artifact since a maker bot cannot choose its fill side; combined-side
analysis is the correct level for forward inference.

Mohanty pivot KILLED (`research/v10a/04-mohanty-pivot-feasibility.md`):
Mohanty arXiv 2604.01431 signal (Kalshi macro probability delta leads
BTC realized vol at h=3-5d) reproduces empirically (t=3.67 vs paper
t=3.71), but Kalshi BTC product universe lacks 3-5 day horizon natively
(KXBTCD daily resolution too short, KXBTCMAXM has 5/30 information
dilution, round-trip taker fees dominate expected MTM gain). Same F11
phantom blocks live capture. Mohanty's natural venue is Deribit, which
is out of project scope.

ALL six candidates remain MARGINAL not SHIP because of failure mode F11
(Dataset Schema Phantom): the Becker dataset has no orderbook bid/ask at
trade time, so the realized maker fills in the data may not represent
what a NEW retail bot's bid would have been filled at. This is the same
data-layer infeasibility that killed V10-A Kim and is in the same family
as v7-B confirmed phantom.

Recommended action: SHADOW MODE on v1 infrastructure. Build paper-trade
logger that prospectively records hypothetical maker fills across the
six candidate categories (Media midprice, Tennis WTA/ATP, Crypto
BTCD/BTC/ETHD, Other). Run 60 to 120 days. Pre-registered gates per
candidate: G1 fill rate >= 15%, G2 n_fills >= 30, G3 mean net P&L > 0,
G4 bootstrap CI excludes zero, G5 within +/- 3pp of Becker baseline,
G6 LOCO event-level positive. 6/6 passes escalate to $5 live; 4-5/6
continue shadow; <=3/6 NULL the candidate. Cost: $0 LLM, $0 capital,
4-8 hours engineering. Verdict in 60-120 days.

Round 15b/c spend: approximately $4 LLM total (V10-A core $1.50, Mohanty
agent $0.20, edge discovery agent $1.00, orchestrator analyses $1.30).
Well under operator's expanded budget. v1 continues on $32 unchanged. No
live capital deployed in Round 15.

**Round 14 outcome (2026-05-26): v9 NULL on Angle A (AIA-style agentic
LLM ensemble on sports).** Operator authorized v9 Angle A per AIA
Forecaster recipe (arXiv 2511.07678): Claude Opus 4.7 with web search,
news, the-odds-api tool use, output calibrated YES probability,
ensemble with Kalshi mid at 67% market / 33% AI weight on v1's
denylisted-residual sports universe at T-35d to T-7d horizons.
Pre-registered gate +0.014 Brier delta over Kalshi mid (AIA MarketLiquid
lift). Three parallel Phase 1 research agents (v9-A1 data layer,
v9-A2 recipe methodology, v9-A3 v10 candidate scouting) surfaced two
compounding feasibility breaks plus a third design-layer issue
identified by Phase 3 critic.

Three breaks:

1. **Data layer:** historical Kalshi orderbook is structurally
   unavailable. `/markets/{ticker}/orderbook` returns an empty book
   for settled markets; the `?ts=` parameter is silently ignored.
   Per the v7-B phantom-prevention rule (real orderbook mid, not stale
   trade-print), retrospective backtest is dead.

2. **Universe:** post-Opus-cutoff (Jan 2026) v1-residual sports
   universe is seasonal. KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF,
   KXNFLGAME have ZERO settled markets in 2026-01-15 to 2026-05-26.
   Only 5 v1-eligible settled sports markets exist in the OOS window
   (4 boxing + 1 UFC). Currently-open v1-eligible markets closing
   2026-05-27 to 2026-06-30: n=87. Minimum detectable Brier delta at
   80% power, alpha 0.05, n=87 is approximately 0.088 to 0.140
   (depending on variance estimator), 6x to 10x the pre-registered
   gate. AIA used n approximately 3,000 per subcategory to detect
   +0.014 cleanly.

3. **Design layer (Phase 3 critic Test 5):** AIA's +0.014 was
   measured on hard (uncertain) markets, Kalshi mid 0.20 to 0.80, the
   regime where Halawi 2024 shows LLM beats crowd. v1's universe is
   confident favorites 0.70 to 0.95, the regime where Halawi documents
   LLM HEDGING and UNDERPERFORMANCE. Under generous toy assumptions,
   the expected ensemble Brier improvement is approximately 0.00015,
   two orders of magnitude below the gate. The pre-registered gate
   was effectively unfirable from the start.

Operator chose M3 (kill v9 NULL, redirect to v10) per kill-early
preference. Phase 3 adversarial critic CONFIRMED KILL across 7 tests
and surfaced the design-layer issue. v9 closes NULL before any Phase 2
data pull. Total v9 spend approximately $2 LLM (Phase 1 agents), $0
external, $0 capital.

NEW failure mode logged to prevent recurrence: **gate-regime mismatch.**
Pre-registered gates copied from a published benchmark must match the
data regime where the benchmark measured the lift. AIA +0.014 on hard
markets does not transfer to confident favorites. Future rounds must
verify regime alignment when borrowing numerical thresholds from
literature, or derive a regime-matched gate.

v9 work in `src/kalshi_bot_v9/` (empty; Phase 2 never started),
`scripts/v9/` (READ-ONLY probe scripts), `data/v9/` (two small probe
JSONs), `research/v9/`. Final verdict at `research/v9/FINAL-VERDICT.md`.
Phase 3 critic at `research/v9/04-phase3-critic.md` is the load-bearing
review. v10 candidate angle scouting in
`research/v9/00-v10-candidate-angles.md` (9 angles scored; no candidate
prior above 22%; ranked top-3: v8-A prospective recovery, sportsbook
line movement, sports microstructure on game-resolution series).

v1 continues running on $32 with W1 denylist unchanged.

**v8-A live probe closed (2026-05-26 ~22:30 UTC, killed early at
iter 33 of 48 per operator decision after evidence was conclusive):
v7-B PHANTOM CONFIRMED.** 8 of 8 settled strong-signal contracts
LOST. Mean P&L per $1 bet: -$0.20. Total: -$1.60 across 8 bets.
Pattern is directional: 4 BUY_NO bets all settled YES (market was
right, naive too underconfident); 4 BUY_YES bets all settled NO
(market was right, naive too uncertain). Binomial p ~ 0.004
falsifies "naive has edge against orderbook" hypothesis. The
v7-B +0.208 Brier improvement was REAL against stale trade-print
mid but UNMONETIZABLE against the live orderbook ASK which MMs
maintain continuously. v7-B status updated from "PARTIAL-PHANTOM
(suspicion)" to "CONFIRMED PHANTOM (live test)". v10 candidate
"v8-A prospective recovery" drops off the candidate list. Final
verdict at `research/v8/FINAL-VERDICT.md`. Probe data preserved
at `data/v8/live_probe_20260526T194846.parquet` and
`data/v8/strong_signal_settlement_audit.parquet`.

Cumulative project state after Rounds 12+13+14+v8: 8 NULLs (v2,
v3, v4-B, v5-B, v5-C, v6, v7-C, v9), 1 confirmed PHANTOM (v7-B),
2 open PARTIALs (v4-A, v5-A still pending operator shadow-mode
wire). Total spend across rounds 12 to 14 + v8: approximately $5
to $7 LLM of $25 cap, $0 external of $30-$60 authorized, $0
capital risk. v1 continues on $32 with W1 denylist.

**Round 13 outcome (2026-05-26): v7-B PARTIAL-PHANTOM, v7-C NULL.**
Operator authorized v7 with three parallel angles: B Kronos foundation
model on KXBTCD, C TabPFN model-class diagnostic, with pre-locked rule
"escalate to Angle A if either passes." v7-C TabPFN: CLEAN NULL.
Confirms v6 and v5-B NULLs are model-class-robust (TabPFN ties LightGBM
within +0.00040 Brier on v5-B; underperforms identity by -0.00091 Brier
on v6). v7-B Kronos itself: NULL contribution (-0.00148 marginal over
naive). But the v7-B diagnostic exposed a one-line feature
`naive_p_yes = Normal-CDF(Coinbase spot at t, strike, sigma)` that beat
Kalshi mid by +0.20842 Brier on midband holdout. Phase 3 critic Test 7
live snapshot found 0 of 188 currently-open KXBTCD contracts with
strong signal: MMs actively maintain orderbook quotes against spot
independent of trade fires. The +0.208 Brier is improvement over stale
TRADE PRINT, not stale ORDERBOOK. v7-B closes as the v5-B Killer-2c
analog: stale-print-as-baseline phantom, more refined but same
operational gap. Operator chose Option 3 (run Angle A as v9 AND build
v8-A forward-record infrastructure). v8-A launched 2026-05-26 19:48
UTC (4-hour live probe of Kalshi orderbook vs spot to definitively
adjudicate the phantom). v7 work in `src/kalshi_bot_v7/`, `scripts/v7/`,
`data/v7/`, `research/v7/`. Phase 3 critic at
`research/v7/07-naive-p-yes-critic.md`. Phase 2 synthesis at
`research/v7/08-phase2-synthesis.md` is the de-facto verdict (no
separate FINAL-VERDICT.md).

**Round 12 outcome (2026-05-25): v6 K1 NULL.** Operator authorized
research on alternative ML models trained on large outside datasets,
possibly higher-frequency than v1's 15-min loop. Selected angle:
crypto microstructure at sub-hour horizons on KXBTCD hourly contracts.
Five-phase multi-agent execution. Phase 1 returned three killing
blocks on the original external-microstructure angle (Binance.com
geo-blocked from US 451, Deribit options skew published null, OFI
alpha decays in seconds), pivoted to Kalshi-internal taker-flow CVD.
Methodology v1 critic caught Killer-1 (CVD sign convention inverted)
plus 4 Important findings, methodology v2 published. Phase 2 built
3688-row master dataset (2807 KXBTCD contracts post-Oct-2024,
14 features at T-30/T-15). Orthogonality screen: zero features
cleared +0.005 Brier improvement; best was kalshi_cvd_30 at
+0.00214. K1 NULL fired at Phase 2 Stage 2B (no model trained).
Phase 3 critic reproduced K1 verdict to 5 decimal places, attempted
5 in-session retrospective salvages (all FAILED), surfaced 3
diagnostics (D1 train/orth regime shift exposed F1 lift as
regime-flattered: regime-controlled lift is -0.00130; D2 funding-
delta cache-edge artifact contaminated 25% of rows but funding-delta
had no signal; D3 logit baseline underperforms identity by +0.063).
Two prospective salvages documented (S1 forward F1 fresh-mid logging
60-90d, S2 microstructure expansion via /markets snapshots 1-2wk
build) but cannot be tested in-session. v6 closes as CONFIRMED NULL.
Total LLM spend ~$2-3 of $25 cap; total external data spend $0 of
$30-$60 authorized. v1 continues running on $32 unchanged. v5-A
SHIP-shadow-mode candidate still pending operator wire. Final
verdict at `research/v6/FINAL-VERDICT.md`. Phase 3 critic at
`research/v6/09-critic.md` is the load-bearing review.

**Round 1 outcome (2026-05-23):** EC-1 KXHIGH weather maker-quoting
hypothesis was tested and KILLED at the Phase 1.6 out-of-sample
calibration gate. Methodology was sound; weather just has too small
a bias for retail to extract after fees. No live capital was
deployed.

**Round 2 outcome (2026-05-23, autonomous run): TWO MECHANICAL
FAILS.** Politics x H (Phase 2) and Sports x Long-Horizon both
killed at their OOS gates due to sample-size collapse from the
binary-only filter combined with long-horizon filter.

**Round 11 outcome (2026-05-24): v5 research closed with one
PARTIAL (Track A sportsbook filter) and two CONFIRMED NULLs
(Track B Statcast prop ML at n=146k, Track C crypto on-chain).**
After operator chose three parallel angles with downloadable
datasets and external APIs (the-odds-api, pybaseball, Etherscan).
Five-phase multi-agent execution per the established protocol.

Three outcomes:

1. **Track A (sportsbook + Polymarket + cross-market filter):
   PARTIAL, SHIP shadow-mode.** Combined v5 filter module
   (`src/kalshi_bot_v5/filter_combined.py`, 28 tests pass) extends
   V4-E with the-odds-api sportsbook arm. V5-A1 verified 40.7%
   coverage of v1's post-denylist live universe; V5-A2 measured
   23% within-coverage live fire rate (effective ~9.4% over v1's
   full candidate stream) at locked 5c sportsbook threshold.
   Signal direction matches V3-C (Kalshi over sportsbook on
   favorites, mean +1.70c). Path Y reproduces V4-E +1.70pp
   exactly (sportsbook arm contributes 0 fires on v3 inventory
   due to series selection bias). Phase 3 critic LOO collapse
   to -0.65pp on outlier removal still applies; Bonferroni-
   corrected TA4 includes zero. Recommendation: SHIP shadow-mode
   logging for 120-180 days, then re-evaluate.

2. **Track B (Statcast prop ML, n=146,952): CONFIRMED NULL.**
   Largest ML sample in project history (1000x v3's n=147).
   Orthogonality protocol dropped 66 of 74 candidate Statcast
   features; the 8 survivors are all volume/PA-count proxies
   (V3-B1 league-progress pattern). Model has POSITIVE Brier
   skill (G2 BSS +0.574, G3 +0.544 vs raw price baseline) but
   cannot monetize under +2c take rule (regularization shrinks
   extremes to 0.5). Phase 3 critic attempted symmetric fade-
   direction NO-buy (fires zero times at -5c) and Kelly-NO
   sizing salvages. Kelly-NO appeared to show +5.98c per
   contract but Phase 3 critic Test 2c traced the PHANTOM to
   stale `last_price_dollars` post-settlement values being
   used as NO ask proxy (realistic NO ask is ~$1.00; illiquid
   side). Both salvages closed null. Model has signal but
   cannot extract through any tested decision rule.

3. **Track C (crypto on-chain, KXBTCD): CLEAN NULL at
   orthogonality.** 8,274 v1-band contracts available (60x
   v3's n=147). Coinbase-vs-BRTI tracking error 0.09% (V5-C1
   concern resolved). 7 candidate features across 3 price bands
   (narrow, wider, midband) yielded 0 features clearing the
   +0.005 Brier improvement threshold. V5-C1's pre-registered
   prediction (0-2 features pass) confirmed at lower bound.
   Best improvement +0.0015 in-sample on widerband; 3x to 5000x
   below threshold across all bands.

v5 work in `src/kalshi_bot_v5/`, `scripts/v5/`, `tests/v5/`,
`data/v5/`, `research/v5/`. Final verdict at
`research/v5/FINAL-VERDICT.md`. Phase 3 critic at
`research/v5/07-critic.md` is the load-bearing review. Total
Anthropic API spend cumulative v4+v5: $1.03 of $25 cap. Total
the-odds-api credits used: 5 of 500 monthly free tier.

**W2 closed (2026-05-24, doc surfaced 2026-05-25): v1
denylisted-residual edge is YELLOW (leaning GREEN).** Headline:
combined residual mean +7.68pp on n=60, row-bootstrap CI
[+2.63pp, +11.68pp] (excludes zero); v3-only residual CI
[-2.79pp, +11.15pp] (INCLUDES zero). Original +12.47pp was
inflated 4.79pp by sample mix + 100% YES selection. Operator
recommendation in the doc: continue v1 at $32, do NOT scale up
past $32 until either (a) v3 inventory refresh tightens the
v3-only CI off zero, OR (b) Track A sportsbook shadow-mode
logging delivers a working filter. KXMLBWINS shows the same
fragility pattern as the denied KXMLBPLAYOFFS / KXNFLWINS series;
add to watchlist (not denylist) at n=11. See
`research/w2-v1-residual-edge.md`.

NEW failure mode caught by critic and documented to prevent
recurrence: stale-price phantom edge in backtest. Using
`last_price_dollars` for the NO side of a settled binary market
returns ~$0.01 (the losing-side last print), creating a fake
+5.98c per-contract apparent edge that does NOT survive
realistic-spread auditing. Future builds must use bid/ask
snapshots at execution time, not post-settlement last prints.

v1 status: continues running unchanged on $32 with W1 denylist
(KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) applied per v4 V4-H.
Optional operator action: wire Track A shadow-mode for 120-180
day evaluation. W2 (re-measure v1 edge on denylisted-residual
universe) still pending; 1-2 hours analytical work.

**Round 10 outcome (2026-05-24): v4 research closed with mixed
findings + consequential v1 side-finding.** Operator authorized
two parallel tracks after v3 null: Track A (Polymarket-live-fade
filter) and Track B (LLM-as-forecaster). Five-phase multi-agent
execution. Explicit operator instruction: "ensure you are not
giving up before you attack all possible angles."

Three outcomes:

1. **Track A: PARTIAL pass.** Unified filter module
   (`src/kalshi_bot_v4/filter.py`) combines Polymarket-fade and
   Kalshi cross-market consistency. Backtest n=147 shows +1.70pp
   mean P&L improvement over bare v1, 4 of 5 TA criteria clear,
   but TA4 (CI excludes zero) borderline-fails at -0.32pp. Phase
   3 critic LOO showed signal hinges on 4 outlier wins. Real
   direction, small n. Recommendation: ship in shadow-mode
   logging on v1 for 120-180 days, then re-evaluate.

2. **Track B: CONFIRMED NULL.** LLM-as-forecaster (Claude Haiku
   4.5 with Prompt C, no Kalshi price, no-memory injunction).
   Phase 3 critic caught a wrong-cutoff bug in V4-F (assumed Jan
   2026, actual Jul 2025 training cutoff). V4-G2 rerun on
   correct cutoff at n=238 strict-eligible: LLM Brier 0.261 vs
   Kalshi 0.082, BSS -2.17. Far worse than market calibration.
   Consistent with V4-B literature's 5-15% honest prior. All 7
   documented pivots failed. Close as null.

3. **v1 side-finding (V4-H): v1 measured edge does NOT
   generalize.** Closes v3 W1 item. v1's `+12.47pp` claim was on
   `data/processed/sports_dataset.parquet` (n=39 eligible) which
   has ZERO KXNFLWINS, ZERO KXNFLPLAYOFF, ZERO KXMLBPLAYOFFS.
   V4-H rebuild: KXNFLWINS mean -1.03pp on n=95, KXMLBPLAYOFFS
   -27.84pp on n=5. **Operator action required: add series
   denylist to v1 scanner BEFORE next scale.** Three series:
   KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS.

v4 work in `src/kalshi_bot_v4/`, `scripts/v4/`, `data/v4/`,
`research/v4/`. Final verdict at `research/v4/FINAL-VERDICT.md`.
Phase 3 critic at `research/v4/07-critic.md` is the load-bearing
adversarial review. Total LLM spend $1.03 of $25 cap.

v1 continues running on $32 unchanged until operator applies the
denylist. After denylist applied, v1's edge on the remaining
universe should be re-measured.

**Round 9 outcome (2026-05-24): v3 external-feature ML research
closed as null finding.** Operator authorized a fresh research run
to test whether external (non-Kalshi-price) features could beat
v1 on v1's domain, with Polymarket as a candidate signal source.
Five-phase multi-agent execution (Phase 1 four parallel research
agents, Phase 2 dataset + model, Phase 3 adversarial critic,
Phase 4 amendments, Phase 5 final verdict).

Phase 1 findings devastated the original thesis:
- Polymarket CLOB price-history endpoint has a hard ~30-day rich-
  detail ceiling. Historical Polymarket data is unavailable for
  training. H1 and H2 (Polymarket-as-target / Polymarket-as-feature)
  killed at data layer.
- Polymarket-Kalshi divergence direction is wrong: every pair with
  > 5c spread on MLB v1-eligible markets had Kalshi PRICED HIGHER
  than Polymarket. Polymarket signal is "fade v1's favorites" not
  "buy more Kalshi YES." H3 long-form killed.
- Free-public-feature sports prediction ceiling is +1-3pp gross,
  at or below C6's +2pp pass floor. Literature ceiling makes any
  passing gate at our n=30-100 a high-prior false positive.

Pivoted to H4 (non-Polymarket experiment): do external team-stat
features improve calibration over v1 at n=147 with leak-free CV?
Orthogonality protocol dropped 11 of 12 candidate features. The
retained feature (`nfl_games_played_pre_t35d`) is a league-NFL-
and-season-progressed dummy, not a true team-stat. Gate FAILED
all four binding criteria.

Phase 3 critic flagged that the v3 effort partially reproduced
v2's false-comparison failure mode: v1's measured `+12.47pp` was
computed on a dataset with ZERO KXNFLWINS markets, but v3 holdout
is 49% KXNFLWINS. v1's edge has not been demonstrated on the
dominant subgroup of v3's failure zone (-40.19pp on NFL slice).
S3 domain-match also fails: v1's live attempted-orders cover 19
series-prefixes, v3 holdout covers 5, overlap is 2/19 = 10.5%.

v3 closes as null. v1 continues running unchanged. Two future-
scope items flagged for operator: W1 (rebuild v1 backtest on
full sports universe; v1's measured edge has unknown coverage
relative to v1's live universe), v4 (Polymarket-as-fade-filter
on v1, OR prospective Polymarket-feature build after 60-90 days
of accumulated data; both deferred). v3 work in `src/kalshi_bot_v3/`,
`scripts/v3/`, `data/v3/`, `research/v3/`. Final verdict at
`research/v3/FINAL-VERDICT.md`. Phase 3 critic at
`research/v3/07-critic.md` is the load-bearing review.

**Round 8 outcome (2026-05-23 very late night): v2 ML research
project completed as null finding.** Operator authorized
multi-agent autonomous research to build a sports prediction ML
model that might beat v1's heuristic. 7 agent waves executed:
data sources (MLB chosen), Polymarket arb (archived: US-blocked),
short-horizon MLB game dataset, baseline LightGBM model (passed
5/6 gate criteria headline, but critic found C5 leak, domain
mismatch, single-team artifact), critic devastated the headline,
operator chose salvage Option B. Salvage: fixed C5 leak in
gate.py (now requires per-fold retraining), rebuilt dataset on
long-horizon MLB markets (v1's actual domain). Long-horizon
dataset has only n=11 eligible markets, structurally below C4
floor of 15. **Skipped modeling step (would mechanically fail).**
The salvage CONFIRMED v1's edge thesis on overlap (+10.41pp on 5
KXMLBWINS markets, matching v1's +9.12pp). v2 ML path closed.
v1 continues running unchanged. 340/340 tests pass. See
`research/v2/10-final-verdict.md`.

**Round 7 outcome (2026-05-23 night): time-scale filter added.**
Operator noticed most resting orders were long-horizon (NBA expansion,
season-long bets). Research agent analyzed eligible >=70c subset by
lifetime bucket: 30-180d (n=39, 100% YES rate, mean +12.47pp, zero
losses) vs 180-365d (n=8, one -81pp catastrophic loss, CI includes
zero). Capital efficiency 8x better at 30-90d (130% annualized) vs
180-365d (16%). Added `--max-lifetime-days 180` filter, default-on.
Strict subset filter of gate-validated regime. 314/314 tests pass.
See `research/time-scale-analysis.md`.

**Round 6 outcome (2026-05-23): LIVE TRADING ACTIVATED.** Operator
explicitly authorized go-live with the $32 currently in Kalshi.
LIVE_ENABLED=true + LIVE_OVERRIDE_GATE=true set in .env (acceptance
criteria bypassed; operator accepts the risk of going live without
50-fill paper evidence). Bot running in background with --mode live
--yes-i-authorize --starting-bankroll 32 --cadence 900.

Two integration bugs discovered + fixed during live smoke:
- `time_in_force` enum: probed the endpoint, found valid values are
  only `immediate_or_cancel` and `good_till_canceled` (American
  spelling, snake_case). All uppercase variants (IOC, EOD, FOK) are
  rejected. Now using `good_till_canceled` for resting maker bids.
- `/portfolio/fills?min_ts=...` requires Unix integer seconds, not
  ISO format. Fixed in `_look_back_ts`.

Initial 5 live orders placed: KXWCSQUAD-26ESP-BIGL (soccer),
KXMLBSTATCOUNT-26IMMACULATE-AP-2 (MLB), KXNCAAFPLAYOFF-26-UGA
(NCAA-FB), KXNFLWINS-27DET-8 (NFL), KXNEXTTEAMNFL-26KPITTS-ATL
(NFL). 4 distinct leagues, $0.70 each = $3.50 exposure of $32
bankroll.

Daily review: `uv run python -m scripts.live_review`.
Logs: `data/live_trades/logs/live.log` (rotated daily, 14d kept).
Stop: Ctrl-C / SIGTERM (handler cancels resting orders first).

**Round 5 outcome (2026-05-23): LIVE MODE WIRED (default-off, gated).**
Operator obtained WRITE-scope Kalshi key and authorized implementing
LIVE mode in `scripts/paper_trade_favorite.py`. Critic pass at
`research/critic-live-mode-design.md` raised 13 findings; design at
`research/live-mode-design.md` was tightened accordingly and all
material recommendations implemented:
- `LiveOrderManager` posts real /portfolio/orders with persisted
  UUID4 client_order_id (idempotent across retries / crashes).
- `KillTriggerMonitor` enforces 6 runtime triggers including the
  critic-added rolling-30 mean < 0.5pp edge-compression check.
- `preflight.py` checklist (WSL clock skew, balance floor,
  programmatic acceptance criteria from LIVE_READINESS_DECISION.md,
  orphan-resting check, interactive confirmation).
- `DrawdownMonitor` extended with new `kill` tier at 20% for live
  mode (folded in per critic; one gate, not two).
- SIGINT/SIGTERM handler cancels resting orders on exit. Heartbeat
  file written each loop.
- `--mode {paper, live, live-demo}` flag. Default `paper`.
- Test suite: 310/310 pass (was 240; added 70 new). Ruff clean.
- Paper-mode smoke test against live Kalshi successful: 4 paper
  orders placed across multiple leagues, Discord alert fired,
  placement_attempts_total persisted to state.
- LIVE preflight aborts cleanly when LIVE_ENABLED=false.

No live capital deployed by this change. LIVE mode requires editing
`.env` (`LIVE_ENABLED=true` + `LIVE_PER_TRADE_USD >= 0.95`) plus the
operator-typed authorization line at the interactive prompt.

See `research/live-mode-design.md` (post-critic design v2) and
`research/critic-live-mode-design.md` (critic report).

**Round 4 outcome (2026-05-24): STRATEGY B LIVE READY.** Operator
authorized continued exploration: "make the decision on something
that is not END the project, do the research, figure out how to
pass the tests, pivot as needed." Diagnosed the funnel collapse,
relaxed binary filter to <=10 contracts per event (40x sample),
ran the Round 3 PROVISIONAL_PASS gate. Then ANOTHER pivot to a
SIMPLER strategy: deep-favorite YES-maker (buy YES at >= 0.70 on
Kalshi sports). This heuristic strategy has no model overfit risk.

Strategy B gate verdict: **GATE PASSES (LIVE READY)**. All 5
criteria pass:
- C1 holdout mean: +5.13pp PASS
- C2 holdout bootstrap CI lower: +2.60pp PASS (excludes 0)
- C3 hit rate: 63.6% PASS (>55%)
- C4 holdout eligible n: 33 PASS (>=25)
- C5 5-fold pooled mean: +4.50pp PASS

Threshold selection was OOS-valid: scanned on TRAIN ONLY (oldest
70%), picked 0.70 by in-sample mean, then tested on held-out 30%.
Robustness confirmed: nearby thresholds (0.65/0.75/0.80) also
show positive test mean P&L. Literature support: Bürgi's
favorite-longshot bias (favorites underpriced).

Paper trading smoke test against LIVE Kalshi successful: 3 paper
orders placed on real markets (KXMLBSTATCOUNT, KXMLBWINS-NYY-26-T90,
KXNCAAFPLAYOFF-26-UGA), Discord alert fired, state persisted.

See [favorite-maker-results.md](research/favorite-maker-results.md)
and [phase-2-autonomous-log.md](research/phase-2-autonomous-log.md)
Round 4 entries.

**Round 3 outcome (2026-05-24, operator-authorized pivot):
PROVISIONAL PASS on Sports x Long-Horizon (relaxed-binary).**
Operator authorized "do the research, figure out how to pass the
tests, pivot as needed" upon wake-up review. Methodology revised
to:
- Relax binary filter to events with <= 10 sibling contracts
  (from strict 1-per-event); add market_tier tag.
- Lower MIN_TRAIN_SIZE 200 -> 50, MIN_TEST_SIZE 30 -> 15
- Lower MIN_LEAGUE_SAMPLE 50 -> 15, MIN_TRADES_IN_WINDOW 20 -> 5
- Drop C1 (slope) from binding gate criteria; report as
  informational.
- Add C6 (realized P&L bootstrap CI > 0) as honest realization test.

**Gate verdict: PROVISIONAL PASS.** All methodology criteria
(C2/C3/C4/C5) pass; C6 fails because realized n=26 with SD=47pp
gives CI [-19pp, +17pp] (includes 0). Realized mean P&L is
positive (+0.27pp). Compression-thesis ACTUALLY HOLDS at this
sample (slope = 1.20, q25 = 1.09, both meet C1 thresholds).

**Recommendation:** operator-approved Phase 3 paper trading at
MINIMAL position size ($0.50 per trade) to gather 100+ realized
fills before scaling. Phase 3 paper trading scaffolding is built
and tested (222/222 unit tests). See
[OPERATOR_HANDOFF.md](research/OPERATOR_HANDOFF.md),
[sports-results.md](research/sports-results.md), and
[round-3-methodology-revision.md](research/round-3-methodology-revision.md)
for the full narrative.

## The five files to read first, in order

1. **[STRATEGY_BRIEF.md](STRATEGY_BRIEF.md)** - the formal mission
   for this phase. Decision framework, required process, best
   practices.
2. **[research/key-findings.md](research/key-findings.md)** - distilled
   research lessons. The four facts every strategy must respect.
3. **[research/strategy-comparison.md](research/strategy-comparison.md)** -
   the candidate (category, strategy) matrix. **Pick your strategy
   from here, or justify additions.**
4. **[research/literature/INDEX.md](research/literature/INDEX.md)** -
   index of the 7 papers studied with TLDR each. Pull full
   extractions from `research/literature/{paper}.md` as needed.
5. **[research/phase-1.5-methodology.md](research/phase-1.5-methodology.md)** -
   the methodology lock-in pattern. Sections 7 ("what we will NOT
   do") and 9 (kill-on-fail) are non-negotiable rules you will
   inherit.

If you only have time to read one, read STRATEGY_BRIEF.md.

## Operating principles

### Research grounding

Every numerical claim about Kalshi economics must cite a paper file
from `research/literature/`. Do not assert numbers from memory. If
you make a claim that isn't in any of the 7 papers, mark it as a
hypothesis to be empirically tested.

The four load-bearing facts (from research/key-findings.md):

1. **Makers > Takers structurally** (Whelan, confirmed by Bürgi,
   Becker, Bartlett). Default to maker-side strategies.
2. **Per-category bias magnitudes vary by 40x** (Becker: Finance
   0.17pp gap, World Events 7.32pp). Higher-bias categories are
   thinner; the sweet spot is mid-bias, mid-liquidity.
3. **The 2024 sign flip** (Becker): pre-October-2024 takers won,
   makers now win. Use only post-flip data for modeling.
4. **Bias shrinks each year** (Bürgi 2025 ψ half of 2024).
   Discount historical numbers for further compression.

### Methodology discipline (non-negotiable)

- **Lock pass criteria BEFORE pulling any data.** Adapt
  `research/phase-1.5-methodology.md` into a phase-2 methodology
  doc.
- **No post-data criterion tuning.** If the gate fails, report
  honestly. No "but this one criterion almost passed" rationalizing.
- **No third bite.** Per the locked methodology section 7: if a
  strategy fails its gate, the strategy ends. Operator must
  authorize any pivot.
- **Walk-forward and LOCO splits with purge buffers.** Simple
  holdout is insufficient. Anti-leakage matters.
- **Distinguish trading window from measurement window.** Phase
  1.5's 9pp shoulder edge was an artifact of measuring post-
  resolution prices in a window no bot could trade in. Validate
  your window represents trades the bot could realistically place.

### Review agents (spawn at three decision points)

Subagent pattern from Phase 1:

- **Plan critic** after strategy proposal, before methodology lock.
  Identify weak assumptions, find counter-evidence, flag unknowns.
- **Methodology critic** after methodology lock, before data pull.
  Stress-test split design, challenge criteria, check purge buffer.
- **Code reviewer** after each engineering milestone, before
  decisions depend on output. Silent failures, race conditions,
  off-by-one P&L, secrets leakage, deviations from plan.

Use the same approach: spawn via Agent tool with a thorough,
self-contained brief that includes the project context. Bring
findings back into the project docs, not just chat.

### Maintaining context as you work

When you discover a new fact or change a decision, write it down
in the right place IMMEDIATELY:

- **New literature studied:** extraction to `research/literature/`,
  TLDR to `research/literature/INDEX.md` AND
  `~/.claude/.../memory/project_kalshi_literature.md`.
- **Strategy decisions:** update the active methodology doc. Don't
  leave decisions in chat only.
- **Phase results:** write `research/phase-N-results.md`.
- **Project state change:** update
  `~/.claude/.../memory/project_kalshi.md`.

Per operator request: "ensure files are set up to update to pick
up with all info whenever I start new context window."

### Other inherited rules

- **No em-dashes** anywhere. Code, README, commits, messages. Run
  `grep -P '[\x{2014}\x{2013}]'` after any file write to verify
  (matches both em-dash U+2014 and en-dash U+2013).
- **Kill early** rather than ship something broken (operator
  feedback memory `feedback_kill_early.md`).
- **California is the operative jurisdiction.** Use CA defaults
  for any legal/tax/regulatory analysis. WA is not in scope.
  Operator is a USC student physically in CA most of the year;
  Kalshi KYC is registered with the CA address. (This is context
  for analysis, not a constraint on what the bot can trade.)
- **Capital cap: $100 operator-authorized ceiling.** Recommended
  initial deployment is $25 per the post-Phase-1 critic. Raising
  past $100 requires explicit operator authorization plus a code
  change in `src/kalshi_bot/config.py`.

## What's reusable

Engineering is mostly category-agnostic and survives the EC-1
kill. 310/310 tests pass, ruff is clean. New modules in Round 5:

- `src/kalshi_bot/data/auth.py` - RSA-PSS signing
- `src/kalshi_bot/data/kalshi_client.py` - rate-limited HTTP
- `src/kalshi_bot/data/kxhigh.py` - KXHIGH ticker parser (template
  for other series parsers)
- `src/kalshi_bot/analysis/calibration.py` - isotonic wrapper
- `src/kalshi_bot/analysis/train_test_split.py` - time-based splits
  with purge + leave-one-X-out
- `src/kalshi_bot/analysis/metrics.py` - ECE, edge, hit rate,
  realized P&L, Kalshi fee formulas (verified)
- `src/kalshi_bot/analysis/gate.py` - the 5-criteria evaluator
  (adapt thresholds per strategy)
- `src/kalshi_bot/analysis/dataset.py` - market+trade join with
  VWAP computation
- `src/kalshi_bot/alerts/discord.py` - tested webhook client
- `src/kalshi_bot/config.py` - capital cap and drawdown constants
- `scripts/test_discord.py` - one-shot webhook smoke test
- `scripts/extract_pdf.py` - pypdf extractor for new papers
- `scripts/archive/ec1_kxhigh/run_gate.py` - the gate runner. Copy
  to `scripts/phase_2/` and adapt window labels.
- `src/kalshi_bot/strategy/live_order_manager.py` - LiveOrderManager;
  posts to /portfolio/orders with persisted UUID intent IDs.
- `src/kalshi_bot/risk/kill_triggers.py` - 6 runtime kill triggers.
- `src/kalshi_bot/strategy/preflight.py` - live-mode pre-flight
  checklist with programmatic acceptance-criteria enforcement.

## What is NOT reusable (archived)

- `scripts/archive/ec1_kxhigh/fetch_kxhigh_*.py` - KXHIGH-specific
  data pulls. Copy the pattern but write a new fetcher for your
  category.
- `scripts/archive/ec1_kxhigh/probe_*.py` - one-off endpoint
  explorations.

These stay in the repo as reference but should not be re-run
without explicit operator authorization.

## Operational facts the operator has confirmed

- Discord webhook works (configured in `.env`, tested in commits
  92fe168 and ddf2c63).
- Kalshi production API key (READ scope only) is in `.env`,
  pointing to a PEM at `%LOCALAPPDATA%\KalshiBot\kalshi_prod_read.pem`.
- Smoke check passes: `uv run python -m scripts.test_discord` and
  `uv run python -m scripts.archive.ec1_kxhigh.check_kalshi` both
  return OK.
- WSL2 clock-skew check is documented but not yet implemented in
  the operator's environment (this is needed before live trading;
  the operator runs Windows + WSL2 + uv).

## Memory files that auto-load

In `C:\Users\SamJD\.claude\projects\C--Users-SamJD-OneDrive-Desktop-AI-Projects\memory\`:

- `MEMORY.md` - global index (loaded every session)
- `user_basics.md` - operator is in CA, .usc.edu
- `feedback_no_em_dashes.md` - the em-dash rule
- `feedback_kill_early.md` - kill-early principle
- `project_kalshi.md` - project state (Round 1 KILLED; Round 2
  active)
- `project_kalshi_literature.md` - 7-paper index with TLDRs

When you start a new context window, these load automatically and
give you the foundation. Project files in this directory are
discovered via the path references in those memory files.

## How a phase concludes

Each strategy attempt produces:

1. **Locked methodology doc** (`research/phase-N-methodology.md`)
2. **Results doc** (`research/phase-N-results.md`) with PASS / KILL
   verdict
3. **Memory and CLAUDE.md updates** reflecting the new state
4. **A clean commit per phase boundary**

When the project finishes (live trading working, or definitively
killed), update this file to reflect the terminal state for the
next context window to pick up cleanly.

## Git workflow (BINDING for every context window)

Operator authorized 2026-05-28: this repo pushes to
`https://github.com/sjdoane/KalshiBot.git` (remote `origin`, branch
`main`) continually as work is done. Every Claude window operating on
this project follows this workflow:

### Commit cadence

- **Per meaningful unit of work**, not per file edit. A "meaningful
  unit" is: a methodology lock, a script + run + report bundle, a
  bugfix, a verdict close, an operator-decision response.
- Do NOT batch unrelated work into one commit.
- Do NOT commit incomplete / broken code; if a change spans
  multiple files, finish them all before committing.
- Mid-task uncommitted changes are fine; commit at task boundary.

### Commit message format

```
<type>: <short imperative summary under 70 chars>

<optional body explaining what + why, wrapped to 72 chars. Reference
research/v{N}/ docs by path. State the operator decision or critic
finding that motivated the change.>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `snapshot`.

### Push cadence

- Push after every commit (`git push origin main`). Do NOT
  accumulate unpushed commits; the GitHub repo is the canonical
  off-machine backup of state.
- If push fails (network, auth, etc.), retry once, then surface the
  failure to the operator. Do NOT silently leave commits unpushed.

### What NEVER goes into the repo

Enforced by `.gitignore`:

- `.env`, `*.pem`, any `kalshi_key*` or `private_key*` (secrets)
- `.venv*` and any virtual env (regeneratable)
- `data/**` (operational state including `state.json` with order details;
  also reproducible from APIs)
- `prediction-market-analysis/` (85+ GB Becker repo; separate upstream)
- `logs/`, `*.log` (rotated runtime artifacts)
- `last_seen_total.txt` and other sidecar bot state

If you find yourself wanting to commit something matching these
patterns, STOP and ask the operator.

### Before any push, verify no secrets

```powershell
git diff --cached --name-only | Select-String -Pattern '\.env|\.pem|kalshi_key|private_key'
# Output should be empty.
```

### Branching

Stay on `main` for now. Operator has not asked for branch isolation.
If a future change is risky enough to warrant a feature branch, ASK
the operator before creating one.

### When a bot is live

Both v1 (`KalshiLiveBot`) and v14 (`KalshiV14Bot`) run as Windows
scheduled tasks placing real Kalshi orders. Code changes to either
require operator-initiated restart (`.\scripts\restart_bot.ps1` for
v1; `Stop-ScheduledTask` + `Start-ScheduledTask` for v14). Do NOT
restart bots without explicit operator authorization; document
expected restart steps in the commit body instead.

## v14 + v1 live deployment status (snapshot 2026-05-28)

- **v1 (`KalshiLiveBot`)** runs `scripts/paper_trade_favorite.py` under
  `scripts/run_live_bot.ps1` supervisor. Strategy: deep-favorite
  YES-maker on Kalshi sports, 60% bankroll fraction
  (`V1_BANKROLL_FRACTION=0.60`), stale TTL 6h, `--cancel-on-drift`
  enabled, intent_id prefix `11`.
- **v14 (`KalshiV14Bot`)** runs `scripts/v14/v14_daemon.py` under
  `scripts/v14/run_v14_bot.ps1` supervisor. Strategy: MLB-night
  sportsbook lead-lag taker (60bp threshold), 40% bankroll fraction
  (`V14_BANKROLL_FRACTION=0.40`), intent_id prefix `14`, 15-min loop
  during 18:00 to 06:00 UTC.
- Both bots **fully Kalshi-state-aware**: each loop polls
  `/portfolio/balance`, `/portfolio/orders`, `/markets`; detects
  operator-initiated deposits, withdrawals, and order cancellations
  automatically. NO hardcoded dollar values; everything fraction-based
  off live Kalshi total.
- The 60/40 split applies to v1/v14 deployments specifically; operator
  manual positions on Kalshi count toward the total but aren't claimed
  by either bot.
- Order ownership: `client_order_id` first 2 chars = `11` (v1), `14`
  (v14), other (operator manual or pre-tagging-era).
- Discord webhook (configured in `.env` as `DISCORD_WEBHOOK_URL`) used
  by both bots for STARTED, PLACED, FILLED, KILL events.
- Deployment guide at `research/v14/04-LIVE-DEPLOYMENT-GUIDE.md`.
  Architecture review at `research/v14/03-architecture-review.md`.
  Operator runbook at `OPERATOR_RUNBOOK.md`.
