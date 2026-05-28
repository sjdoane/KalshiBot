# Project Kalshi v5 Master Plan

**Date:** 2026-05-24
**Status:** Research phase, multi-agent autonomous execution
**Author:** Claude (orchestrator)
**Operator authorization:** After v4 (Track A PARTIAL, Track B NULL, v1 fragility on KXNFLWINS/KXNFLPLAYOFF/KXMLBPLAYOFFS series), operator picked three parallel tracks (A, B, C) with downloadable datasets and external APIs.

## 1. Why v5 (and what is NEW vs v2/v3/v4)

v2 closed null on MLB ML at small n. v3 closed null on external-feature ML at slightly larger n. v4 closed Track B null at correct cutoff with the LLM-forecaster paradigm. v4 Track A surfaced a real but small-n signal (Polymarket-fade-filter, +1.70pp with CI lower -0.32pp, LOO-fragile).

The v2-v3-v4 cumulative learning:

- **Free-public-feature sports prediction caps at +1-3pp gross** against sportsbook-saturated long-horizon favorite markets. Outcome prediction is a dead path at our scale.
- **The signal mechanism that works** is "second-opinion filter on v1" (V3-C measured Polymarket signal direction; V4-A confirmed 42.6% coverage; V4-E built the filter and showed real direction).
- **The data source that hasn't been tried** is the de facto truth in sports prediction: sportsbook closing lines. Polymarket is a proxy; sportsbooks are the source.
- **The market domain that hasn't been tried** is player props (less sportsbook competition) and crypto (different domain entirely).

v5 attacks three angles in parallel that side-step the v2-v3-v4 wall:

- Track A: use sportsbook lines (gold standard) instead of Polymarket as the second-opinion filter on v1.
- Track B: build an ML predictor for Kalshi player-prop markets using Statcast pitch-by-pitch data (huge sample, lower sportsbook competition).
- Track C: pivot to a new market domain (crypto) where free on-chain data exists and sportsbook competition is irrelevant.

## 2. Three thesis statements

- **H-A (Track A, sportsbook filter)**: when v1 considers placing a YES order on a Kalshi market that has a sportsbook counterpart, fetch the sportsbook implied probability from the-odds-api; if Kalshi-Sportsbook > X cents, skip the trade. Same paradigm as v4 Track A but with a stronger second-opinion signal.

- **H-B (Track B, Statcast-driven prop predictor)**: per-player Statcast metrics (xwOBA, xBA, exit velocity distributions, plate-discipline metrics, recent form) predict KXMLBSTATCOUNT-style player-prop outcomes (e.g., "Will Player X have N+ hits") better than the Kalshi market price at a margin sufficient to clear C6's +2pp.

- **H-C (Track C, crypto with on-chain features)**: Kalshi crypto markets (KXBTC daily/weekly settlements, KXETHH hourly settlements) have a tradeable inefficiency that on-chain data (exchange flows, gas prices, funding rates) can predict.

## 3. What falsifies each

- **H-A falsified if**: sportsbook coverage of v1's universe < 30%; OR the filter's retrospective P&L improvement is < +1pp on the covered subset; OR sportsbook and Polymarket signals are so collinear that the-odds-api adds nothing over V4-E.

- **H-B falsified if**: KXMLBSTATCOUNT n < 50 historical resolved markets per player class; OR Statcast features show no orthogonal signal beyond the Kalshi price (orthogonality protocol from v3-B audit); OR the gate's C1-C6 fails on a leak-free holdout.

- **H-C falsified if**: Kalshi crypto markets are too efficient (price moves track on-chain in real-time, no exploitable lag); OR n is too small per market type; OR on-chain features are collinear with the Kalshi price.

## 4. Hard constraints (inherited; locked)

1. v1 bot is mostly untouched but now has the W1 denylist applied (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS). The v5 work must NOT undo or modify this denylist except through deliberate operator-approved scope change.
2. v5 work paths: `src/kalshi_bot_v5/`, `scripts/v5/`, `tests/v5/`, `data/v5/`, `research/v5/`. v1, v2, v3, v4 paths read-only.
3. No real Kalshi orders. READ-scope client only.
4. Locked 6-criteria gate from `src/kalshi_bot_v2/gate.py` for tracks that predict outcomes (B, C). Track A uses TA1-TA5 from master plan v4 Section 6.4 (filter overlay, not new strategy).
5. No em-dashes.
6. Continuous documentation in research/v5/.

## 5. Operator-action items required for full Phase 2

Phase 1 can begin immediately. Phase 2 builds require:

- **A**: the-odds-api free tier signup (5 min email at the-odds-api.com). API key to be added as `THE_ODDS_API_KEY` in `.env`.
- **B**: no external signup. `uv add pybaseball` will be needed at the build stage. ~50GB disk for full Statcast 2015-2026.
- **C**: Etherscan free tier signup (1 min email at etherscan.io/apis). API key to be added as `ETHERSCAN_API_KEY` in `.env`. CoinGecko free tier needs no key.

Agents will flag if a key is missing and proceed with what's available.

## 6. Phase structure

### Phase 1: parallel research (target 3-4h agent-clock)

Three agents in parallel:

- **Agent V5-A1: the-odds-api coverage of Kalshi sports universe.** Verify the-odds-api docs, map Kalshi sports series to the-odds-api sport/market endpoints, estimate coverage of v1's actually-traded universe (post-denylist). Test live-mid feasibility and historical-call rate-limit math. If `THE_ODDS_API_KEY` is present, do live probes; if not, document what would be tested. Output: `research/v5/01-sportsbook-coverage.md`.

- **Agent V5-B1: Statcast feasibility + KXMLBSTATCOUNT inventory.** Pull a sample season of Statcast via pybaseball (e.g., 2024 final season) and measure: download time, disk size per season, per-pitch data shape. Then enumerate Kalshi's KXMLBSTATCOUNT historical markets (V3-A's probe inventory should have them; verify) and quantify: n eligible by player, stat type, threshold structure. The orthogonality question: do Statcast features add signal beyond the Kalshi market price at T-X days before settlement? Output: `research/v5/02-statcast-feasibility.md`.

- **Agent V5-C1: Kalshi crypto market inventory + on-chain feature audit.** Enumerate Kalshi crypto series (KXBTCD, KXBTC, KXETH, KXETHH, etc.) from the Kalshi historical archive. Measure n per series, settlement frequency, typical lifetime. Audit free on-chain data sources (Etherscan, blockchain.info, CoinGecko, Binance public API) for features sample-able at T-X minutes/hours before settlement without look-ahead. Output: `research/v5/03-crypto-inventory.md`.

### Phase 2: build (depends on Phase 1)

Per-track Phase 2 agent:

- **V5-A2 (sportsbook-filter build)**: add the-odds-api fetch to `src/kalshi_bot_v5/filter_sportsbook.py`, extend the v4 filter module to combine Polymarket + sportsbook second-opinions, retrospective backtest. Gate: TA1-TA5 (overlay).

- **V5-B2 (Statcast-prop model)**: build `src/kalshi_bot_v5/statcast_features.py` + `statcast_model.py`. Train on historical seasons, evaluate on a leak-free holdout. Gate: locked C1-C6 from v2 gate.py.

- **V5-C2 (crypto model)**: build `src/kalshi_bot_v5/crypto_features.py` + `crypto_model.py`. Train on historical Kalshi crypto markets, evaluate on a leak-free holdout. Gate: locked C1-C6.

### Phase 3: adversarial critic

One critic-per-track OR a unified critic covering all three, depending on outcomes. The critic must specifically test for the v2/v3/v4 failure modes that apply per track.

### Phase 4: iterate

Per operator's standing instruction "do not give up before all angles attacked," each track gets at least 3 pre-registered pivot attempts before any null declaration.

### Phase 5: final verdict

`research/v5/FINAL-VERDICT.md` summarizing per-track outcomes and operator-facing recommendations.

## 7. Specific v2/v3/v4 failure modes to NOT repeat per track

| Failure mode | Track A defense | Track B defense | Track C defense |
|---|---|---|---|
| CV leak | use v2 gate.py `trainer=` for any ML; A is overlay not ML so n/a | mandatory `trainer=` retrain per fold | mandatory `trainer=` retrain per fold |
| Feature look-ahead | sportsbook prices sampled at T-X discipline | Statcast filtered to games BEFORE T-X | on-chain data with proper timestamp filter |
| Model anchors on price | A is overlay; n/a | orthogonality protocol per v3-B audit | orthogonality protocol; verify Statcast features add signal beyond price |
| Single-entity artifact | check filter fires not concentrated in 1 team | check player concentration in holdout | check single-day or single-asset concentration |
| False C6 comparison | v1 baseline = post-denylist v1; honest comparison | use the locked v1_decision_fn | n/a (crypto is a new domain; C6 may not apply) |
| Sample-size below T=252 | n/a (A is overlay) | aim for n >= 200; supplement with multiple stat types if needed | aim for n >= 200; daily/hourly crypto markets should have plenty |
| Wrong-cutoff-window | n/a (no LLM) | n/a (no LLM) | n/a (no LLM) |
| Series-prefix coverage mismatch (v3 W1) | use post-denylist v1 universe for the filter; do not measure on series v1 doesn't trade | KXMLBSTATCOUNT is a v1-traded series; baseline on the SAME universe | crypto is a NEW domain; C6 against v1 is not meaningful, use Brier-skill against price baseline |

## 8. Time budget

~12-15 agent-hours.

- Phase 1 parallel: 3-4h
- Phase 2 build (3 tracks in parallel where possible): 4-6h
- Phase 3 critic: 1.5h
- Phase 4 iterate: 2h
- Phase 5 verdict: 0.5h

If approaching the limit and a track is clearly bottoming out, accept partial coverage.

## 9. Decision log

- 2026-05-24 (Iter 0): v5 master plan written. Three parallel tracks. v1 bot now has W1 denylist applied (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS).
