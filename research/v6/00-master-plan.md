# Project Kalshi v6: Master Plan

**Date opened:** 2026-05-25
**Predecessor:** v5 (Round 11). Track A SHIP shadow-mode, Track B Statcast NULL at n=146k, Track C crypto on-chain NULL at orthogonality.
**Authorization:** Operator session 2026-05-25. Explicit ask: alternative ML models on large outside datasets, possibly higher-frequency than v1's 15-min cadence. Five candidate angles offered; operator-approved primary: crypto microstructure at sub-hour horizons. One-time $30-60 paid-tier authorization for tardis-dev / Deribit history if Phase 1 warrants. Research now, build production runtime later if signal.

## The v6 thesis

KXBTCD hourly contracts in the T-30 to T-5 minute window before settlement carry information that the on-chain features (v5-C) and point-in-time fundamentals (v3, v4) could not extract. The hypothesis: **classical crypto market microstructure (orderbook imbalance, CVD, options skew, funding-rate delta) at sub-hour horizons predicts settlement direction beyond what is already in the raw Kalshi mid.**

## Why this angle survives the kill-early filter

Operator listed 5 candidate angles; only this one combines (a) backtestable historical data (b) sample size > 10k decision points (c) feature space NOT exhausted by v5 (d) high-frequency alignment with operator mission. The other four were rejected with reasons:

- Angle 1 (Kalshi own orderbook): no historical endpoint, prospective-only.
- Angle 2 (sports line-movement time-series): the-odds-api free tier no historical.
- Angle 4 (sports news/sentiment): expensive APIs, hard alignment.
- Angle 5 (within-market re-quoting): engineering not research.

v5 split across 3 tracks and only 1 returned PARTIAL. v6 concentrates effort on the single highest-prior remaining angle.

## What's new vs v5-C (the critical novelty audit)

v5-C tested at T-1h with 7 features: realized vol, VWAP dev, spot-futures basis, funding rate level, active addresses, DXY, hashrate. Got 0/7 features clearing +0.005 Brier improvement.

v6 introduces (Phase 1 Agent D will verify this list is complete and non-overlapping):

1. **Orderbook imbalance** at L5 and L20 depths (untested)
2. **Cumulative Volume Delta (CVD)** = taker-buy minus taker-sell volume (untested)
3. **Deribit 25-delta options skew** and term-structure delta (untested; v5-C tested basis, not options skew)
4. **Sub-hour horizons** T-30 / T-15 / T-5 (v5-C tested only T-1h; Phase 3 v5 critic explicitly flagged this as the untested pivot)
5. **Funding rate *delta*** (vs the level v5-C tested and failed orthogonality on)

Optional / secondary (recorded forward, not historically backtested):
6. **Kalshi own orderbook**: spread, top-of-book depth, queue position estimate. Recorded starting Phase 2; usable as a secondary feature in any shadow-mode validation.

## Prior on outcome

| Outcome | Subjective probability | Rationale |
|---|---|---|
| SHIP-clean PASS | ~5% | Would require model beats +2c rule AND survives realistic-spread audit |
| PARTIAL (ship shadow-mode) | ~25% | Positive Brier + 1-2 features survive orthogonality, but +2c rule fails or LOO-fragile |
| CONFIRMED NULL | ~70% | Most likely failure mode = v5-B pattern (positive Brier, model anchors on price, can't monetize) |

Even the modal NULL outcome closes the "have we tried microstructure?" frontier the operator mission requires, and reuses ~80% of v5's orthogonality/CV infrastructure.

## Phase structure (five phases)

### Phase 1: Parallel research agents (in progress)

Four agents in parallel:

- **Agent A, Literature scope**: crypto microstructure literature, predictive power of OB imbalance / CVD / options skew at 5-30min, adverse selection cost decay.
- **Agent B, Data feasibility**: ccxt + Binance L2, Coinbase, Deribit options, Kalshi historical, free-tier vs paid-tier deltas.
- **Agent C, Kalshi crypto profile**: KXBTCD trade volume / spread / depth in T-30/T-15/T-5 windows. The "will spread eat the edge" pre-test.
- **Agent D, v5-C audit**: definitive list of (feature, horizon, threshold) tuples tested in v5-C; novelty verification.

### Phase 1.5: Methodology lock + critic

After Phase 1 returns, write `phase-1.5-methodology.md` with:
- Locked gate criteria (orthogonality threshold, BSS bar, +2c-rule P&L floor, sample-size minimums).
- Cluster-bootstrap by contract-day design with 24h purge buffer.
- Spread-realism audit protocol (use bid/ask at sample time, NEVER `last_price_dollars` per v5 phantom-edge lesson).
- Methodology critic agent before any data pull.

### Phase 2: Build dataset + model

- 2A: pull data feeds (operator-approved one-time spend if needed).
- 2B: feature engineering + orthogonality pre-screen.
- 2C: train calibrated models at locked horizons.
- 2D: apply gate criteria.

### Phase 3: Adversarial critic

Independent agent reproduces gate verdict, attempts known salvages (fade-direction NO-buy, Kelly sizing variants), audits for stale-price phantom edge per v5 lesson.

### Phase 4: Iterate

Address critic findings. No third-bite on methodology, but salvages within methodology are allowed.

### Phase 5: Final verdict

`research/v6/FINAL-VERDICT.md` with PASS / PARTIAL / NULL disposition + memory + CLAUDE.md update.

## Budget

- Anthropic LLM: $1.03 cumulative spent of $25 cap. Headroom ~$24.
- the-odds-api: 5 of 500 free monthly credits used (not relevant to v6).
- Tardis-dev / Deribit: $30-60 one-time, operator-pre-authorized, deferred until Phase 1 Agent B returns.

## Non-negotiable inherited rules

- No em-dashes anywhere. Grep `[\x{2014}\x{2013}]` after every file write.
- Orthogonality protocol per v5: drop features correlating with raw price > threshold, or features that don't add Brier > +0.005.
- Cluster-bootstrap or LOCO splits with purge buffers; not naive holdouts.
- NEVER use `last_price_dollars` post-settlement as an ask proxy. Use live or recorded bid_dollars / ask_dollars at sample time. This was v5 Phase 3 critic Killer Finding 2c.
- Critic at three points: plan (this doc + Phase 1.5), methodology (Phase 1.5), code (Phase 2 + Phase 3).
- Kill-early > ship-then-fail. If orthogonality fails clean, write the NULL verdict immediately.
- Do not touch v1 live bot, .env, data/live_trades/, data/paper_trades/.

## Operator-explicit constraints recorded

- Operator email: sjdoane@usc.edu, CA resident (USC).
- $100 capital cap; currently $32 deployed; v6 will NOT recommend raising past $100.
- Live bot on $32 unchanged through v6 research.
- Operator authorized "any external packages or githubs" for v6.
