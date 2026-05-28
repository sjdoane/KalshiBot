# v10 Candidate Angles: Scouting Report

**Date:** 2026-05-26
**Author:** Agent v9-A3
**Status:** Scouting only. No data pulled, no code written. Operator selects v10 from ranked list.

---

## Preamble: Honest Priors

9 ML attempts, 7 NULLs, 2 PARTIALs (shadow-mode pending). The baseline prior for any new angle is 10-15%. Adjust upward only with specific mechanistic evidence. Scores above 20% require explicit justification below.

---

## Candidate 1: Hyperliquid On-Chain Orderbook Signals

| Field | Value |
|---|---|
| Name | Hyperliquid external orderbook signals on KXBTCD |
| Hypothesis | Hyperliquid BTC-PERP L2 imbalance, depth changes, and funding at T-30/T-15 predict KXBTCD-1h direction beyond Kalshi mid, because Hyperliquid is an external $1B+/day venue whose book updates faster than Kalshi retail. |
| Prior of monetizable signal | 8 to 15% |
| $ cost | $0 one-time + $0/mo (verified 200 OK from CA IP, v7 scoping 2026-05-25) |
| Agent-clock | 8 to 14 hours (recording setup + 60-90d wait + analysis pass) |
| Wall-clock | 60 to 90 days minimum (historical L2 not available; must forward-record) |
| Prerequisites | No paid signups. Forward-recording script needed. |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL |
| Replay-prevention | Must record Hyperliquid L2 AND Kalshi orderbook mid at same timestamps, then orthogonality against ORDERBOOK mid (not trade-print mid), preventing the v7-B phantom. |
| Why this and not v5-C or v6 | v5-C tested slower on-chain (daily); v6 tested Kalshi-internal CVD, Deribit funding. Hyperliquid L2 imbalance at sub-minute from a cross-venue $1B+ perp is untested. Risk: Kalshi MMs likely monitor Hyperliquid already. Wall-clock constraint is prohibitive for a 90-day wait at this project's cadence. |

---

## Candidate 2: Multi-Source LLM Ensemble

| Field | Value |
|---|---|
| Name | Multi-model LLM ensemble (Opus + Gemini Flash + DeepSeek) on sports |
| Hypothesis | A 4-to-5 LLM ensemble mixing independent model families at 67% market weight outperforms single-model because systematic miscalibration biases partially cancel across providers. |
| Prior of monetizable signal | 12 to 22% |
| $ cost | $5 to $15 LLM (Gemini Flash and DeepSeek have free or near-free tiers; Opus 4.7 budget largely consumed by v9) |
| Agent-clock | 10 to 18 hours (multi-provider wiring + calibration + ensemble) |
| Wall-clock | Days to 2 weeks |
| Prerequisites | Gemini API key (free tier), DeepSeek API key (free tier). v9 Angle A result first. |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL |
| Replay-prevention | v4-B was no-tools, single model, no market weight. This adds model diversity. Schoenegger 2024 (n=31 Metaculus questions) found ensemble matches human crowd but does NOT beat best individual model (GPT-4 0.15 vs ensemble 0.20). If sports miscalibration is structural bias (AIA 2025: sports 2x worse than geopolitics for all LLMs), more models from same training-data culture do not fix it. |
| Why this and not v4-B | Closes "was it the model count?" question that v9 Angle A leaves open. Dependency: do not run until v9 Angle A resolves; if v9 fails on sports-miscalibration mechanism, this is near-known-null. |

---

## Candidate 3: Polymarket-as-Feature Redux

| Field | Value |
|---|---|
| Name | Polymarket historical depth redux (post-2026 API check) |
| Hypothesis | Polymarket's 2026 CLOB /prices-history exposes 60-180d of historical data on Kalshi-parallel markets; if so, v3's kill constraint (30-day ceiling) is removed and a backtest at n > 100 is possible. |
| Prior of monetizable signal | 10 to 20% |
| $ cost | $0 (Polymarket CLOB is free for read endpoints) |
| Agent-clock | 4 to 8 hours (API probe + backtest if depth confirmed) |
| Wall-clock | Days (API probe is fast) |
| Prerequisites | One WebFetch probe to verify depth. If ceiling still at 30d, kill immediately at $0. |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL |
| Replay-prevention | v3 was killed at data layer only. Direction finding from V3-C (Kalshi prices HIGHER than Polymarket on favorites) is the correct mechanism: divergence feature not raw price, preventing market-anchoring. Ng/Peng/Tao/Zhou 2026 shows Polymarket leads Kalshi only on 2024 politics (higher Polymarket volume); for US sports, Kalshi at $2.7B/wk likely leads. Polymarket Global offshore at $2.1B/wk is the only plausible lead-lag venue for sports. |
| Why this and not v3 | v3's kill was purely data-layer. If ceiling lifted, the angle is testable. Run probe first; invest 0 hours unless probe confirms 90+ days of depth. |

---

## Candidate 4: News/Sentiment Alignment (GDELT + ESPN)

| Field | Value |
|---|---|
| Name | News sentiment alignment as v1 filter overlay |
| Hypothesis | When GKG tone for a sports team turns sharply negative within 24h of close, and Kalshi mid has not adjusted, the market lags information; sentiment delta feature added to v1 filter captures the lag. |
| Prior of monetizable signal | 5 to 12% |
| $ cost | $0 (GDELT free if accessible; ESPN free; Alpha Vantage 25/day fallback) |
| Agent-clock | 8 to 16 hours |
| Wall-clock | Days (GDELT bulk download if accessible) |
| Prerequisites | GDELT re-probe from current build host (3 timeouts in v7 scoping; must verify before committing). ESPN fallback is thinner coverage. |
| Novelty | NEW |
| Replay-prevention | No prior round tested sentiment features on sports. Feature must be pure sentiment CHANGE (delta), not level, and must verify whether Kalshi mid moved before or after sentiment shift to avoid anchoring. |
| Why this and not nothing | Only named candidate with zero prior-round coverage. GDELT accessibility uncertainty is the binding risk; if GDELT times out again, fallback coverage is too thin to justify the build. |

---

## Candidate 5: Self-Supervised Pretraining on Kalshi 72M Trades

| Field | Value |
|---|---|
| Name | Small transformer pretrained on Kalshi trade tape |
| Hypothesis | Pretraining a 2-8M param transformer on Kalshi's 72M-trade corpus learns prediction-market-specific sequence patterns that classical features and Kronos (pretrained on crypto candles) do not capture. |
| Prior of monetizable signal | 5 to 10% |
| $ cost | $10 to $20 GPU compute + $0 API |
| Agent-clock | 30 to 60 hours |
| Wall-clock | 1 to 3 weeks |
| Prerequisites | GPU access; full Kalshi historical trades pull (days of crawling at rate limits). |
| Novelty | NEW |
| Replay-prevention | v7-C (TabPFN) confirmed transformer architecture alone does not escape "mid absorbs everything" failure mode. v7-B (Kronos) showed pretrained model on crypto candles contributed -0.00148 over naive. Self-supervised on KALSHI binary outcomes is genuinely new, but if the signal is in the mid (as v6 and v7 suggest), pretraining on mid-price sequences will replicate the mid. Engineering cost is 10x any other candidate relative to prior. |
| Why this and not Kronos or TabPFN | Different from both (not tabular, not crypto-candle pretrained). Not recommended for v10 primary given engineering cost vs prior. |

---

## Candidate 6: RL / Contextual Bandit Overlay on v1

| Field | Value |
|---|---|
| Name | Thompson-sampling bandit overlay on v1 fire decision |
| Hypothesis | A contextual bandit on v1's P&L reward signal with context (series prefix, price, sportsbook divergence) learns series-specific fire rates that reduce tail-loss probability in KXMLBWINS and KXNCAAFPLAYOFF. |
| Prior of monetizable signal | 8 to 18% |
| $ cost | $0 |
| Agent-clock | 6 to 12 hours (backtest on n=60 W2 parquet) |
| Wall-clock | Weeks to months (online learning requires live order flow) |
| Prerequisites | v1 production logs (already in `data/live_trades/`). W2 parquet for backtest. |
| Novelty | NEW |
| Replay-prevention | Not a forecasting model; policy optimization on existing v1 rule. v7-B phantom and v5-B Killer 2c do not apply (reward is realized gross P&L from actual fills). Sample-size constraint is the dominant risk: n=60 backtest is too small to validate; online convergence requires 200-300 live observations, which is 1-2 years at v1's current fire rate. |
| Why this and not static threshold | W2 found KXMLBWINS and KXNCAAFPLAYOFF fragile. Bandit could learn series-specific rates. Not recommended for v10 primary due to sample-size constraint. |

---

## Self-Identified Candidate 7: v8-A Prospective Recovery

| Field | Value |
|---|---|
| Name | v8-A prospective orderbook data as v10 anchor |
| Hypothesis | v8-A's live probe (PID 66132, completing 2026-05-26 23:48 UTC) finds Kalshi orderbook mid durably lags naive_p_yes in a meaningful fraction of snapshots, confirming the v7-B +0.208 Brier improvement survives against ORDERBOOK mid (not stale trade-print mid) and is monetizable. |
| Prior of monetizable signal | 20 to 40% CONDITIONAL on v8 finding durable signals; 5 to 12% unconditionally (v7 critic Finding 7.1: 0 of 188 strong signals at live snapshot time) |
| $ cost | < $1 API (v8-A already running); $0 for extended recording |
| Agent-clock | 2 to 6 hours (analysis pass after data collects) |
| Wall-clock | Data already arriving; analysis pass runs immediately after 23:48 UTC |
| Prerequisites | v8-A output parquet. Operator decision to extend recording beyond 4 hours if initial signal is promising. |
| Novelty | NEW (prospective orderbook mid vs trade-print mid never tested before v8) |
| Replay-prevention | This IS the replay-prevention measure for v7-B. v8-A captures yes_bid, yes_ask, book_mid at snapshot time. If book_mid tracks naive_p_yes within 2c (live snapshot evidence suggests it does), phantom closes cleanly. If book_mid lags, real edge exists. The v7 critic's recommended prior for this path was 40%. |
| Why this is not just "wait" | v8-A is running NOW. Analysis cost is near-zero. If the initial 4-hour run shows no persistent strong signals, eliminate this candidate at $0 cost. If it shows signal, extend recording at $0/mo. Highest EV per dollar among all candidates. |

---

## Self-Identified Candidate 8: Sports Microstructure on Game-Resolution Series

| Field | Value |
|---|---|
| Name | Kalshi-internal microstructure on KXNFLGAME / KXMLBGAME / KXBOXING / KXUFCFIGHT |
| Hypothesis | Game-resolution sports markets have retail-dominated, news-driven microstructure distinct from KXBTCD-1h; CVD and quote-imbalance at T-24h to T-1h before game time have signal that v6's hourly-crypto null does not cover. |
| Prior of monetizable signal | 10 to 18% |
| $ cost | $0 (Kalshi /historical/trades available with existing key) |
| Agent-clock | 8 to 14 hours |
| Wall-clock | Days (historical data available retrospectively for resolved markets) |
| Prerequisites | Kalshi API read key (already in .env). v6 `build_v6_master.py` pattern is reusable with series-prefix change. |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL |
| Replay-prevention | v6 FINAL-VERDICT explicitly states: "Kalshi-internal microstructure on non-crypto series: v6's null on KXBTCD does NOT automatically extend to game-resolution markets." Structural difference: KXBTCD-1h is MM-priced against Coinbase spot in real time; game-resolution sports are priced by retail bettors reacting to news. v6 CVD sign convention (Killer-1 in methodology critic) must be re-verified empirically on the sports trade tape. Orthogonality screen against Kalshi mid per v6 protocol prevents anchoring. |
| Why this and not v6 | v6 was KXBTCD-1h only. This is a structurally different market type with a different participant mix. The v6 dataset and scripts are reusable; only the series filter changes. The v6 null does not close this question. |

---

## Self-Identified Candidate 9: Sportsbook Line Movement as Leading Indicator

| Field | Value |
|---|---|
| Name | the-odds-api line movement leading Kalshi mid on game-resolution markets |
| Hypothesis | When a major sportsbook (DraftKings, FanDuel, Pinnacle) moves a game-result line by more than X basis points in the 1 to 6 hours before a KXNFLGAME or KXMLBGAME close, Kalshi mid lags; a taker at stale Kalshi mid captures the adjustment. |
| Prior of monetizable signal | 12 to 22% |
| $ cost | $30 one-time (the-odds-api Starter, one month, buy and drain historical; within authorized $30-60 budget) |
| Agent-clock | 6 to 10 hours |
| Wall-clock | Days (historical odds back to 2020 per v7 scoping verification) |
| Prerequisites | the-odds-api Starter signup at $30. Kalshi game-resolution historical trades (existing key). |
| Novelty | NEW |
| Replay-prevention | v5-A tested a STATIC Kalshi-vs-sportsbook divergence snapshot (+1.70c mean; PARTIAL, LOO-fragile). This tests DYNAMIC time-series: does sportsbook movement precede Kalshi mid movement? These are distinct hypotheses. Static divergence could be structural (Kalshi always prices favorites higher, non-tradeable) or could be a lag artifact. Line-movement angle distinguishes them. No stale-price proxy is used; the feature is sportsbook line change over a time window. |
| Why this and not v5-A | v5-A measured divergence at a point in time. This tests whether the divergence WIDENS then NARROWS, indicating a lag. If confirmed, there is a taker opportunity at the stale Kalshi price. If Kalshi moves simultaneously with sportsbook, v5-A's divergence is structural and non-tradeable. The $30 buys a one-time historical dataset, not a recurring dependency. |

---

## Ranked Top-3 for v10

### Rank 1: Candidate 7 (v8-A Prospective Recovery)

The conditional prior (20-40%) is the highest evidence-backed number in the list. The v7 critic's own assessment (S1 prospective collection = 40%) supports it. Cost is near-zero because v8-A is already running. The decision tree is binary: v8-A analysis pass shows durable strong signals (extend recording) or does not (eliminate at $0). This should be the FIRST action taken regardless of v10 selection: run the analysis pass when v8-A finishes at 23:48 UTC 2026-05-26.

If v8-A shows no persistent strong signals (expected outcome per live snapshot evidence), this candidate is eliminated and Rank 2 becomes the primary.

### Rank 2: Candidate 9 (Sportsbook Line Movement)

The only named candidate that (a) has not been tested in any form, (b) has a specific mechanistic basis distinct from all prior NULLs, (c) requires a small one-time spend within the authorized budget, and (d) resolves in days. The prior (12-22%) is in the second tier. The $30 cost buys the ability to backtest on 5 full NFL/NBA/MLB seasons of historical odds, giving a sample of 200-500 qualified game-resolution markets with matching sportsbook coverage, far above the n=60-147 typical of prior rounds.

### Rank 3: Candidate 8 (Sports Microstructure on Game-Resolution Series)

Zero cost, days wall-clock, reuses v6 infrastructure directly, and tests a gap the v6 FINAL-VERDICT explicitly called out as un-covered. Prior (10-18%) is lower than Rank 2 but cost is also zero. If v8-A closes v7-B as phantom and the operator is unwilling to spend $30 on the-odds-api, Candidate 8 is the natural v10 primary. Can run in parallel with Rank 2 since both use game-resolution sports markets.

---

## Pre-Decision Zero-Cost Checklist

Before any v10 build commitment:

1. **Check v8-A results (0 cost, 2-6 hours after 23:48 UTC).** If Rank 1 is viable, it becomes primary.
2. **Probe Polymarket CLOB depth (0 cost, 30 min).** One API call checks if the 30-day ceiling is still in force. If depth is 180d+, Candidate 3 upgrades to consideration.
3. **Re-probe GDELT from current build host (0 cost, 30 min).** If 200 OK, Candidate 4 becomes a viable secondary.

These three checks cost under $1 in agent time and may eliminate or upgrade candidates before any build commitment is authorized.
