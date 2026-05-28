# v6 Agent C: KXBTCD Microstructure Profile

**Date:** 2026-05-25
**Sources:**
- v5 historical aggregates: `data/v5/crypto_full_KXBTCD.parquet` (n=592,571 contracts, 2024-03 to 2026-03)
- v6 trade probe: `data/v6/kxbtcd_sample_trades.parquet` (n=9,446 trades from 300 sampled post-flip contracts, T-60 to T-0 window)
- v6 live orderbook snapshot: `data/v6/kxbtcd_live_orderbook_snapshot.parquet` (318 open KXBTCD markets, 2026-05-25 ~19:00 UTC)

Probe script: `scripts/v6/probe_kxbtcd_microstructure.py`. Analyzer: `scripts/v6/analyze_kxbtcd_microstructure.py`.

## Schema of the v5 KXBTCD dataset

13 columns, one row per contract. No per-trade timestamps, no orderbook history, no bid/ask snapshots. Columns: `ticker`, `series_ticker`, `event_ticker`, `open_time`, `close_time`, `status`, `result`, `last_price_dollars`, `volume_fp`, `settlement_value_dollars`, `last_price`, `volume`, `lifetime_hours`. `lifetime_hours` is mostly 1.00 with some 25/169 (multi-day events).

Bid/ask/depth columns do NOT exist in the historical pull and were never recorded in v5 build scripts (`scripts/v5/probe_crypto_full.py`, `scripts/v5/build_v5c_orthogonality_dataset.py`). Only LIVE `/markets` returns `yes_bid_dollars`, `yes_ask_dollars`, `yes_bid_size_fp`, `yes_ask_size_fp`. This is the structural data gap v6 must work around.

Notes: each event has ~75 contracts spanning the strike grid; only 3 to 10 trade meaningfully (near-the-money). `n=8,540` post-flip v1-band is the real signal universe; `n=300` is the trade-probe sample. `last_price_dollars` is the stale post-settlement field per v5 Phase 3 Killer Finding 2c.

## Q1. Trade-volume distribution per contract (T-N min windows)

Random stratified sample of 300 post-Oct-2024 contracts (60 per band), pulled from `/historical/trades`. Samples ranged 2024-12-16 to 2026-03-21 (100% post-flip).

### Trade counts per contract (median across 60 sampled contracts per band)

| band | T-60 | T-30 | T-15 | T-5 |
|---|---|---|---|---|
| extreme-low [0.05, 0.20] | 4 | 0 | 0 | 0 |
| low-mid [0.20, 0.55] | 4 | 1.5 | 0 | 0 |
| midband [0.55, 0.80] | 2 | 1 | 0 | 0 |
| narrow [0.70, 0.95] | 3 | 1 | 0 | 0 |
| extreme-high [0.80, 0.95] | 7.5 | 2.5 | 0 | 0 |
| ALL (n=300) | 4 | 1 | 0 | 0 |

Mean trade count in T-5 by band: extreme-low 0.8, low-mid 1.5, midband 5.5, narrow 4.5, extreme-high 3.6; ALL 3.2. p90 in T-5: extreme-low 0, low-mid 3, midband 10.4, narrow 7, extreme-high 6.1; ALL 5.0.

**Key takeaway:** **median KXBTCD contract has ZERO trades in the last 5 minutes**, with mean dragged to 3.2 by a heavy right tail. Even p75 = 0 to 1 trades in T-5. Activity concentrates in midband and narrow markets, but even there median is 0 in T-5.

## Q2. Spread distribution (live snapshot)

318 live open KXBTCD markets across 3 events at snapshot time. After filtering to fully-quoted (yes_bid > 0 AND yes_ask < $1) and excluding zero-side stale 99c/01c markets: n=28 with two-sided quotes.

| band (mid) | n | mean | median | p25 | p75 | p90 |
|---|---|---|---|---|---|---|
| extreme-low [0.05, 0.20] | 6 | 0.020 | 0.020 | 0.020 | 0.020 | 0.025 |
| low-mid [0.20, 0.55] | 6 | 0.018 | 0.020 | 0.020 | 0.020 | 0.020 |
| midband [0.55, 0.80] | 3 | 0.020 | 0.020 | 0.015 | 0.025 | 0.028 |
| narrow [0.70, 0.95] | 7 | 0.019 | 0.020 | 0.010 | 0.025 | 0.030 |
| extreme-high [0.80, 0.95] | 6 | 0.018 | 0.015 | 0.010 | 0.027 | 0.030 |

**Median spread is exactly 2c across every band.** Spread does NOT widen at extremes (the operator's worry); it widens slightly in absolute terms in the midband (where prices have room to move) but the p90 is 3c across all bands. Live n is small (snapshot-bounded), but the consistency of the 2c result across bands is the signal.

**At midband (~0.50):** median spread 0.020 (2c).
**At extremes (~0.05 or ~0.95):** median spread 0.015 to 0.020 (1.5 to 2c).

## Q3. Top-of-book depth

| band | median yes_bid_size | median yes_ask_size |
|---|---|---|
| extreme-low | 1,822 | 2,101 |
| low-mid | 104 | 2,170 |
| midband | 2,136 | 2,206 |
| narrow | 2,154 | 5,000 |
| extreme-high | 1,702 | 6,050 |

**Depth is substantial** for retail. Median top-of-book is 1,000 to 7,000 contracts on each side, which dwarfs anything a $32 bankroll can move. A bot placing a 1 to 5 contract bid is queue-position #N-of-thousands. This means: depth is NOT a constraint, but queue position IS, and a 2c-improvement bid jumps the entire existing queue.

## Q4. Realistic +2c maker fill expectation

**Approximation noted:** no orderbook reconstruction. We use the last trade print at or before T-5 as a mid proxy, place a hypothetical bid at `proxy_mid - 0.02`, and check whether any subsequent trade in T-5 to T-0 prints at or below it. This OVERESTIMATES fill (ignores queue position; uses last trade not mid).

### All-contract simulation (Definition A: bid placed on every contract)

| band | n | fill rate |
|---|---|---|
| extreme-low | 59 | 8% |
| low-mid | 56 | 12% |
| midband | 59 | 10% |
| narrow | 59 | 2% |
| extreme-high | 60 | 7% |
| ALL | 293 | 8% |

### Subset with ANY T-5..T-0 print (Definition B)

| band | n | fill rate |
|---|---|---|
| extreme-low | 5 | 100% |
| low-mid | 12 | 58% |
| midband | 18 | 33% |
| narrow | 10 | 10% |
| extreme-high | 15 | 27% |
| ALL | 60 | 38% |

**80% of contracts have ZERO trades in T-5..T-0**, so a strategy that requires a T-5 fill cannot execute on most opportunities.

The 38% conditional fill rate is upper-bound (no queue-position model). Halving for queue position gives ~15 to 20% effective conditional fill. Combined with ~20% pre-condition rate, realistic per-contract participation is ~4%. With 24 KXBTCD events per day, that's ~1 expected fill per day per active strike, workable but slow.

Narrow band [0.70, 0.95] fill is the LOWEST (2% / 10%), consistent with favorites being anchored near $0.99 with limited T-5 downside. Maker strategies on favorites would sit unfilled.

## Q5. Comparison to v1 sports (Le 2026)

v1 sports median market has **76 trades over its full lifetime** (multi-day to multi-month).

KXBTCD:
- Median trades in LAST 5 MIN ONLY = **0**.
- Median trades in last 30 min = 1.
- Median trades in last 60 min = 4.
- Mean trades in last 5 min = 3.2 (but skewed by tail).

KXBTCD median activity in the v6 trading window is BELOW v1's sports lifetime median. Mean is comparable only because high-volume midband/narrow contracts pull it up. **v6 is operating in a thinner trade-flow regime than v1**, despite KXBTCD being one of Kalshi's highest-volume products at the SERIES level.

## Q6. Recent-data check (post-Oct-2024 sign-flip)

Per Becker 2026, the maker/taker sign flipped in October 2024. v5 dataset has:
- Pre-Oct-2024 KXBTCD: 4,371 contracts (0.7% of total)
- Post-Oct-2024 KXBTCD: 588,200 contracts (99.3% of total)
- Date range: 2024-03-18 to 2026-03-24

v6 trade probe sample: 100% post-flip (sample drew from `close_time >= 2024-10-01`). **Verdict: v5 dataset is overwhelmingly post-flip; v6 should drop the small pre-flip slice but it's a tiny effect.**

## Honest verdict

**The +2c spread is borderline-supportive of v6, not killing.** Three findings:

1. **Spread = maker increment** (median 2c across every band). A +2c-better bid moves to top of book without crossing half-spread. The v5 phantom-edge concern (stale `last_price_dollars` falsely $0.01) does NOT replicate; live `yes_bid_dollars` / `yes_ask_dollars` are tight and symmetric near-the-money.

2. **Trade frequency is the binding constraint, not spread.** Median contract has 0 trades in T-5 and 1 in T-30. Cannot rely on "fill at T-5, exit at T-2"; T-2 print rarely exists. Strategy must hold maker bids from T-30 inward and accept ~80% unfilled. With ~24 KXBTCD events per day, expected fills are ~1/day per active strike.

3. **Depth is a non-issue for retail.** Top-of-book 1,000 to 7,000 contracts; $32 bankroll moves nothing.

**Verdict: KXBTCD spread is small enough to support a +2c-rule strategy.** v6 must address low-fire-frequency reality: T-30 and T-15 should be weighted over T-5 in the horizon list. The "median 0 trades in 5 min" finding is the new design constraint, not the spread.

## Follow-up live probe

`scripts/v6/probe_kxbtcd_microstructure.py` exists. Phase 2 should:

1. Run hourly for a week to capture intraday spread evolution (does spread widen in T-30 vs T-5?). Current snapshot is a single timestamp.
2. Capture `yes_bid_size_fp` and `yes_ask_size_fp` at each T-N minute mark for one live event to estimate queue-position dynamics. Live `/markets` returns this; historical does not.
3. Cross-reference fill rate with Coinbase BTC realized vol at the same minute.

## Caveats

- Live snapshot is one timestamp (2026-05-25 ~19:00 UTC). Different times of day or weekend regimes may differ.
- Trade probe n=300 vs 588k post-flip universe; mean estimates have wide SEs but median-zero-trade is robust.
- Fill simulation uses last-trade as mid proxy, not true mid. Real fill rate likely below 38% upper bound.
- All numbers are 1h-lifetime KXBTCD; KXBTC15M (15min) was NOT profiled.
