# v8-A Probe: Final Verdict

**Date:** 2026-05-26
**Status:** Probe killed early at iter 33 of expected 48 per operator decision after 8 of 8 settled strong-signal contracts lost. Phantom conclusively confirmed.
**Predecessor:** `research/v7/07-naive-p-yes-critic.md` (v7-B Phase 3 critic, PARTIAL-PHANTOM verdict)

## Verdict: PHANTOM CONFIRMED. Closing v7-B.

v8-A was launched to definitively adjudicate whether the v7-B `naive_p_yes = Normal-CDF(Coinbase spot at t, contract strike, sigma)` finding represented a real monetizable edge or a phantom over stale Kalshi trade-print mid. v7 Phase 3 critic's one-shot live snapshot (0 of 188 currently-open contracts with strong signal) suggested phantom; v8-A provides the multi-iteration, multi-settlement audit.

**Verdict: PHANTOM. 8 of 8 settled strong-signal bets lost.** Mean P&L: -$0.20 per $1 contract. Total loss across 8 bets: -$1.60.

## Probe execution summary

| Metric | Value |
|---|---|
| Iterations completed | 33 of 48 (killed at operator request after evidence was conclusive) |
| Wall-clock runtime | 2h 40min of planned 4h |
| Total row observations | 4,908 |
| Unique tickers observed | 644 |
| Mean book spread | 1.14c (tight) |
| Mean abs signal | 0.98c (small) |
| Strong signals (|signal| >= 0.05) | 34 observations across 12 unique tickers |
| Strong signals (|signal| >= 0.10) | 6 observations |
| Strong signals (|signal| >= 0.20) | 1 observation |
| Settled strong-signal contracts | 8 of 12 (4 still in active status, KXBTCD-26MAY2619-* series) |

## Settlement audit (the decisive number)

8 of 8 settled strong-signal contracts went AGAINST naive in BOTH directions:

| Direction | n | naive said YES rate | market mid YES rate | actual settled YES | mean P&L per bet |
|---|---|---|---|---|---|
| BUY_NO (signal < 0) | 4 of 4 | 0.35 to 0.85 | 0.47 to 0.92 | 4 of 4 settled YES | -$0.22 |
| BUY_YES (signal > 0) | 4 of 4 | 0.12 to 0.42 | 0.03 to 0.36 | 0 of 4 settled YES (all NO) | -$0.18 |

The pattern is directional and consistent: in both regimes, the orderbook was MORE confident than naive about the actual outcome, and the orderbook was right.

Binomial probability of 8 random losses if naive had no edge (50/50): 1 in 256. The data falsifies the "naive has edge against orderbook" hypothesis at p ~ 0.004.

## What this means

1. The v7-B +0.20842 Brier improvement against `kalshi_mid_at_t` (last trade print) was REAL but UNMONETIZABLE.
2. The improvement measured **how stale the last trade print is** relative to current spot.
3. The orderbook mid (best bid + best ask)/2 is MAINTAINED CONTINUOUSLY by MMs, independent of whether trades fire. MMs see current spot AND order flow AND near-term vol context that naive Normal-CDF does not.
4. Against the orderbook mid, naive performs WORSE than the market.
5. The +2c-take rule against the actual ask extracts negative P&L on every strong-signal contract observed in live data.

This is the **v5-B Killer-2c analog**: stale-price-proxy as baseline. v5-B used post-settlement `last_price_dollars`; v7-B used legitimate pre-close `kalshi_mid_at_t`. Both proxies systematically diverge from the true transactable orderbook in regimes where no trade has fired recently. The CATEGORY of failure is the same; v7-B's instance is more refined but operationally identical.

## What v8-A produced with lasting value

1. **`data/v8/live_probe_20260526T194846.parquet`** (4,908 rows, 33 iterations): the cleanest live-orderbook-with-spot-and-naive-p record assembled in Project Kalshi. Reusable for any future microstructure question that needs to compare live book to model.

2. **`data/v8/strong_signal_settlement_audit.parquet`** (12 strong-signal contracts with peak signal, would-be P&L, settlement outcomes): the definitive phantom audit.

3. **`data/v8/probe_summary.json`** (machine-readable summary).

4. **`scripts/v8/live_probe.py`** (the continuous probe; reusable for any future live-Kalshi monitoring task).

5. **A new failure-mode entry for the project's collective memory**: the v7-B variant of stale-trade-print phantom edge. Future rounds borrowing the orthogonality baseline must verify the baseline reflects the actual transactable price at sample time, not just any pre-close price reference. **kalshi_mid_at_t from /historical/trades is NOT a valid execution proxy outside of trade-print moments.**

## Status of the 4 unsettled signal contracts

KXBTCD-26MAY2619-T75599.99, T75699.99, T75799.99, T75899.99 closed at 19:00 UTC; status returned active at audit time, likely API-lag finalization. Final settlement would extend the 8/8 sample by 4, but the verdict does not depend on them. Given the 8/8 directional pattern, expected outcome is 4 more losses.

## What this closes for the project

- **v7-B** closes as PHANTOM, not PARTIAL. Update v7 status from "PARTIAL-PHANTOM (suspicion)" to "CONFIRMED PHANTOM (8 of 8 settled live test)".
- **v8 forward-record infrastructure** has served its diagnostic purpose. No further extension recommended.
- **v8-C (real-money micro-test)** is NOT recommended. Cancelled.
- **No live capital deployed.** $32 in v1 bot unchanged.

## What's next

Per parallel session's v9 NULL and v10 candidate scouting at `research/v9/00-v10-candidate-angles.md`: 9 candidate angles scored, no prior above 22%, top-3 ranked are (1) v8-A prospective recovery (this round, now closed), (2) sportsbook line movement (requires the-odds-api Starter $30/mo), (3) sports microstructure on game-resolution series.

With v8 closing PHANTOM, candidate (1) drops off. Operator should choose between:
- v10 candidates 2 or 3
- Accepting the cumulative evidence (8 nulls + 1 phantom + 2 PARTIALs) and shifting to engineering / ops mode (wire v4-A and v5-A SHIP shadow-modes; scale v1 cautiously if W2 verdict supports)
- Closing Project Kalshi research mode permanently at this stage

## Spend accounting (v8 + v7)

- LLM API spend across v7 + v8: approximately $5 to $7 of $25 cap. Headroom ~$18-20.
- External data spend: $0 of $30 to $60 authorized.
- Capital risk: $0 (probe was read-only).
- Total Project Kalshi spend across all 9 research rounds: approximately $8 to $10 LLM, $0 external, $0 capital risk.

## Project rules respected throughout

- No em-dashes anywhere (grepped after each write).
- No touching of `.env`, `data/live_trades/`, `data/paper_trades/`, v1 source.
- Kill-early honored: probe killed at iter 33 of 48 once 8/8 evidence was conclusive.
- No real money deployed (would have required separate operator authorization per v8-C protocol).
- v7-B updated from "PARTIAL with phantom suspicion" to "CONFIRMED PHANTOM" only after live multi-settlement evidence supports the call.
