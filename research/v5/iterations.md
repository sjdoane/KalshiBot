# v5 Iteration Log

Continuous trail of orchestrator decisions, pivots, and gate runs. Append-only.

## Iter 0 (2026-05-24, master plan)

`research/v5/00-master-plan.md` written. Three parallel tracks: A (sportsbook filter via the-odds-api), B (Statcast for MLB player props), C (crypto markets with on-chain features). v1 bot has W1 denylist applied (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) per v4 finding.

## Iter 1 (2026-05-24, Phase 1 synthesis)

Three research docs returned:
- `01-sportsbook-coverage.md` (V5-A1)
- `02-statcast-feasibility.md` (V5-B1)
- `03-crypto-inventory.md` (V5-C1)

### V5-A1 outcome: PROCEED Phase 2 at free tier

- Post-denylist v1 universe: 84 series-prefixes, 29 live attempted orders, 32 v3-eligible markets.
- the-odds-api coverage: 40.7% inclusive on live universe, 51.2% on v3 inventory.
- Match-class series: KXBOXING, KXNCAAFPLAYOFF, KXNFLGAME, KXUFCFIGHT, KXWCGAME, KXMLBGAME.
- Live signal-direction probe (n=23 v1-eligible-band sportsbook favorites): mean Kalshi - book = +1.70c, 65% Kalshi over. Direction MATCHES V3-C Polymarket measurement. Magnitude smaller (sportsbook is consensus, less divergence than Polymarket's retail-skewed offshore).
- Free tier: 500 credits/mo, 1/live + 10/historical. Historical access requires $30/mo paid tier (V4-D's assumption corrected; free tier is live-only).
- Phase 2 path: live-mode shadow-logging filter (live-only, 150 calls/mo = 30% of free tier).
- Credits used in Phase 1: 5 of 500 (1%).

### V5-B1 outcome: PROCEED Phase 2 with SCOPE AMENDMENT

- KXMLBSTATCOUNT is structurally dead (n=6 specialty markets). Replace with KXMLBHIT, KXMLBHR, KXMLBHRR, KXMLBKS (per-player props).
- Total sample: 146,952 binary resolved markets across ~43k player-game pairs. Single-player concentration < 1%. Massive scale.
- pybaseball install clean via `uv add pybaseball`. 10-year archive projected ~1.4 GB / 13 min.
- AS-OF discipline simple: `game_date < market_game_date`. Median market lifetime 6h.
- Light orthogonality probe (n=54 KXMLBHIT 2+ markets): Spearman r(BA14g, price) = -0.04 (orthogonal). r(price, outcome) = +0.70 (price is informative). Brier improvement of -0.0007 small but in right direction.
- Critical caveat: all 150k markets within ONE 60-day window (2026-03-26 to 2026-05-24). Only 60 distinct game-dates. Cross-season generalization untested.
- Sportsbook competition: prop markets are documented retail-edge zone (especially pitcher Ks).

### V5-C1 outcome: PROCEED Phase 2 with NARROW SCOPE

- KXBTCD alone has 8,274 v1-band contracts across 4,136 events on 635 close-dates. Massive vs v3's n=147.
- 232 total crypto series probed; 148 settle on CF Benchmarks RTI indices (BRTI for BTC, ERTI for ETH).
- Fee structure identical to sports (quadratic taker formula).
- ETHERSCAN_API_KEY validated. Free tier 3 req/sec, daily aggregates paywalled.
- Binance.com hard-blocked from US. Substitutes work: Coinbase, Kraken, Deribit (funding rates), CoinGecko, mempool.space, Coin Metrics community.
- 15 candidate features documented (funding rate, orderbook imbalance, realized vol, spot-futures basis, on-chain exchange flows, gas prices, etc.).
- Central risk: orthogonality. Pre-registered prediction: 0-2 features will clear +0.005 Brier improvement on 200-market orthogonality probe.

### Decision: PROCEED all three tracks to Phase 2

The three tracks are independent and use different data sources. They can be built in parallel by three agents. Each track's Phase 2 must:
- Apply the orthogonality protocol (v3-B audit) BEFORE training
- Use the v2 leak-free gate (where outcomes are predicted, not where overlay rules are applied)
- Document pivots when blocked (operator's standing instruction)

### Phase 2 plan

- **V5-A2 (sportsbook filter build)**: extend `src/kalshi_bot_v4/filter.py` to a v5 module `src/kalshi_bot_v5/filter_combined.py` that combines Polymarket-fade (existing) and sportsbook-fade (new) into one filter. Retrospective backtest restricted to current/recent markets (since free tier is live-only).
- **V5-B2 (Statcast prop model)**: build `src/kalshi_bot_v5/statcast_features.py` + `statcast_model.py`. Train on KXMLBHIT/HR/HRR/KS. Apply orthogonality protocol. Run leak-free gate with `trainer=`. Use cluster-bootstrap by date for CI (since all data is in a 60-day window).
- **V5-C2 (crypto orthogonality + conditional model)**: run the orthogonality probe FIRST per V5-C1 recommendation. If 0 features clear +0.005 Brier improvement, declare null. Otherwise, build a narrow model on KXBTCD with the surviving features.

Phase 2 budget: ~5-6h agent-clock for the three builds in parallel.

## Iter 2 (2026-05-24, V5-A2 build)

`research/v5/04-sportsbook-filter-build.md` written. Module + tests + backtest delivered. PRE-REGISTERED thresholds locked before any backtest run:

- `fade_threshold_cents_poly = 7.0` (matches V4-E)
- `fade_threshold_cents_book = 5.0` (V5-A1 measured +1.70c mean, smaller magnitude, tighter threshold)
- `monotonicity_threshold_cents = 5.0` (matches V4-E)

Headline results:

- Path X (live-cached resolved markets): n=2 v1-band, n=8 extended. Too small for TA evaluation. Documented as low-power.
- Path Y (v4 inventory with current sportsbook): book-only coverage 0% (inventory has no MATCH-class h2h game-resolution series). Combined filter reproduces V4-E exactly (+1.70pp diff, CI [-0.32pp, +4.22pp], 4 of 5 TA pass).
- Live universe fire rate at locked threshold: 3 of 13 v1-band candidates fire A3 (23%). All 3 at divergence >= +9c. None resolved yet at build time.

Per-rule decomposition documented. The book-only arm on v3 inventory has 0 fires because v3 selection bias (inventory is season-long-winners, not h2h games). On forward-looking v1 live universe, A3 fire rate is 23% with 5c locked threshold.

Recommendation: **SHIP shadow-mode** (no live behavior change). Wire `evaluate_market_combined` into v1's main loop as a logging-only call. After 120-180 days of accumulated resolutions, run a clean TA evaluation. Do NOT recommend $30/mo paid tier yet; free-tier shadow-mode gives the data to make that decision rationally in ~90 days.

Credits used: 0 (cache-only on V5-A1's pre-cached sport_key responses).
## Iter 3 (2026-05-24, V5-C2 build)

`research/v5/06-crypto-model.md` written. Track C closes as NULL.

V5-C1's pre-registered prediction (0-2 features pass orthogonality) confirmed
at the lower bound. Three orthogonality probes at three different price bands
all produced 0 features clearing the +0.005 Brier improvement threshold:

- Narrow [0.70, 0.95] at n=200: train_NOs=1 -> single-class LogReg; in-sample
  full-bootstrap supplement: best feature +0.0001 Brier improvement
- Wider [0.55, 0.95] at n=300: train_NOs=0 -> single-class LogReg (NOs
  concentrated in late-2025 BTC volatility)
- Mid [0.55, 0.80] at n=250: train_NOs=7, test_NOs=20 -> non-degenerate
  bootstrap; best feature +0.00001 Brier improvement on holdout (f7_dxy);
  several features have NEGATIVE Brier improvement (feature hurts model)

Maximum observed Brier improvement across all 7 features (realized vol,
VWAP dev, spot-futures basis, funding rate, active addresses, DXY, hashrate)
at all 3 bands: +0.0015 (f8_hashrate in-sample on widerband). 3x below the
+0.005 threshold.

Coinbase-vs-BRTI tracking error measured at 0.09% mean absolute (200 v1-band
markets); p99 abs err 0.40%. Below V5-C1's 0.1% concern threshold. Coinbase
is a faithful BRTI proxy.

No model trained. No locked C1-C6 gate run. Per kill-early principle.

Pivots attempted: 2 of 3 (price-band widening, midband). T-15min sampling
and KXBTCD weekly not attempted (low prior probability of changing verdict;
time budget consumed by builds).

Track C closes. v1 continues running unchanged on $32.

## Iter 4 (2026-05-24, V5-B2 build)

`research/v5/05-statcast-model.md` written. Track B closes as NULL.

Dataset built honestly at n=144,873 (V5-B1 inventory + 2026 Statcast,
675 of 701 player names mapped to MLBAM IDs; 15,005 unique
(player, game_date, is_pitcher_prop) feature computations cached).

Orthogonality protocol retained 8 of 74 candidate features. All 8 are
batter pitch-count / PA-count proxies in various windows. None of the
skill metrics (xBA, xwOBA, K-rate, hard-hit-rate, exit velo) cleared
the +0.005 AUC delta threshold. Survivors are league-progress /
opportunity proxies analogous to V3-B1's `nfl_games_played_pre_t35d`.

Gate result on locked C1-C6:

- G1 (v1 always-trade): holdout n=43,462, mean -6.50c, fails C1/C2/C3/C5/C6
- G2 (LogReg price-only, prob > price + 0.02): n=43, mean -47.71c, fails all
- G3 (LogReg price + 8 survivors): n=233, mean -26.35c, fails all

Cluster-bootstrap-by-game-date C2 CI applied. C5 5-fold pooled mean
ranges -6.14c to -7.67c across variants.

POSITIVE: model has calibration skill. G2 Brier skill score against
raw market price = +0.574 on n=43,462 holdout. G3 BSS = +0.544.
Model IS better calibrated than the price baseline.

But: the calibration improvement does NOT translate to profitable
trades under the locked +2c edge rule + Kalshi maker fees + 1.5c
slippage. The model's regularization shrinks extreme prices toward
0.5, which is the WRONG direction for the prob > price + 0.02 rule
on most markets (which are priced at the empirical rate near 0.99
or 0.01).

This is the v2 critic Section 5 "model anchors on price" failure mode
appearing at 1000x the v2 dataset scale, in a different shape
(positive BSS, negative P&L). Operator's pre-registered
model-worse-than-baseline kill condition is satisfied in spirit.

11 pre-registered pivots attempted: wider edge (+5c), per-prop-type
subset (HIT-only, HR-only, HRR-only, KS-only), mid-band [0.20, 0.80]
filtering. Every pivot fails. The single positive variant (KXMLBHRR
mid-band price-only) has n=1, statistical noise from one fortuitous
trade.

Sanity checks (S1/S2/S3) pass except for an S2 close_time-tie leak
that affects < 0.05% of training data per fold; documented but
impact is negligible.

Sportsbook-spread realism check (subtract 5c per trade): model fails
even worse with realistic execution slippage.

Total build wall: ~25 min agent-clock. ~70 MB disk added.

Track B closes. v1 continues running unchanged on $32.
