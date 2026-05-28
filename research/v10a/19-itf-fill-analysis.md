# Round 15c Track 2C: ITF tennis synthetic maker fill analysis

Method: for each retail trade print in the ITF probe trade log,
look up the most recent orderbook snapshot (within 35 minutes)
for the same ticker and compute mid = (yes_bid + yes_ask) / 2.
A synthetic maker passive quote at mid is ASSUMED to fill any
taker trade that crossed mid (which is every observed trade,
since a maker at mid is at the inside of the book ahead of
the existing yes_bid / yes_ask).

This is a synthetic upper bound on fill rate. In reality,
multiple makers would compete for the same inside; ours might
win 30-50% of races, not 100%.

Cycles collected: 13
Orderbook snapshots: 2451
Trade prints: 13490

## Per-prefix summary

| Prefix | n_trades | n_matched | n_synth_fills | fill_rate (%) | midband fills | median spread at fill (c) | mean entry price |
|---|---|---|---|---|---|---|---|
| KXITFMATCH | 6105 | 4381 | 4381 | 100.0 | 4381 | 2.0 | 0.504 |
| KXITFWMATCH | 7385 | 4801 | 4801 | 100.0 | 4801 | 3.0 | 0.482 |

## Interpretation

If `median spread at fill` is materially above 1c, retail-
competing markets are rare to absent on ITF and a maker at
mid would have a real spread to capture. If `n_trades_matched`
is a large fraction of total trades, the 30-minute snapshot
cadence is adequate for ITF dynamics.

## Next step (deferred)

Realized P&L requires settled results. Take the top 10 to 50
tickers from `payload.top10_tickers_by_fills`, wait for their
close_time + 6h, then GET /markets/{ticker} for each and
compute payout = (1.0 - maker_entry if YES else -maker_entry)
minus 2 * maker_fee. Cluster bootstrap by event (which here
is the match) gives the realized maker edge CI.

If the realized maker per-fill mean is positive after fees AND
the fill rate (after a realistic competition haircut, e.g.
30%) is sufficient for the 8-hour cycle volume, ITF becomes a
SHADOW-CANDIDATE for live capital at $5 to $10 size.

## Em-dash audit

(verified after write)
## Verdict (Round 15c, full 13-cycle dataset, 17 snapshots)

**SHADOW-CANDIDATE.** ITF tennis maker quoting at mid is marginally
positive on expected value before adverse-selection adjustments and
worth a small live probe to validate.

### Spread distribution (the full-dataset picture)

| Prefix | Median spread at fill | Mean spread at fill | Fills |
|---|---|---|---|
| KXITFMATCH (men) | 2c | **3.8c** | 4,381 |
| KXITFWMATCH (women) | 3c | **5.8c** | 4,801 |

Mean materially exceeds median because of a fat right tail of
wide-spread trades. The earlier single-cycle snapshot caught only
the tightest cells (1c) and misled the verdict toward NULL.

### Per-fill economics at mean spread (entry mid 0.48-0.50)

- Half-spread captured: 1.9c (men), 2.9c (women)
- Round-trip Kalshi maker fee at mid 0.50: 1c
- **Net per fill before adverse selection: +0.9c (men), +1.9c (women)**

### Caveats

1. **Synthetic 100% fill rate.** Our maker model assumes our quote
   wins every race to the inside. Real fill rate against competing
   MMs is more like 30-50%, so the achievable fill VOLUME is 1/3 to
   1/2 of the 4,381 / 4,801 reported here in an 8-hour window.
2. **Adverse selection unaccounted.** A maker at mid is filled when
   the underlying moves; some of those fills will go AGAINST the
   maker (mid was right before the news; we get hit just before the
   move). Realized P&L could be materially below the
   spread-capture estimate.
3. **No realized P&L yet.** Top tickers close June 10, 2026. Real
   verdict requires `GET /markets/{ticker}` after settlement and
   computing payout vs entry per fill.
4. **Volume cyclicality.** This dataset spanned 6 hours of US
   afternoon / Eurasian evening. Other windows (US morning, US
   late night) may have different spread / flow regimes.

### Recommended next step

Two cheap follow-ups for the operator:

1. **Settlement P&L follow-up (deferred until ~June 11):** join
   the top-85 ticker list from this run to `GET /markets/{ticker}`
   for each, compute realized maker P&L at mean_maker_entry,
   cluster-bootstrap by event_ticker (which is the match), get a
   real CI on the per-fill edge. If CI lower > 0 after fees,
   escalate.
2. **Small live probe (cost <= $10):** add KXITFMATCH and
   KXITFWMATCH to `scanner_config.series_allowlist`, set
   `mid_band_lower=(0.40,0.50)`, `mid_band_upper=(0.50,0.60)`
   (the ITF maker band, NOT v1's favorite band), `min_minutes_to_close=30`,
   `--cancel-on-drift --drift-threshold-cents 2`. Run for 7-14 days
   parallel to v1. Gate to escalate: >=30 realized fills, mean net
   P&L per fill > 0, CI lower > 0.

### Why this changed from "leaning NULL"

The single-cycle snapshot earlier (only 1 cycle of clean data, 37
matched trades) showed median spread 1-2c and the verdict was NULL
because at 1c spread the maker net is negative after fees. The
full 13-cycle dataset captured the broader spread distribution
including the wide right tail. The MEAN spread (3.8c men, 5.8c
women) is what determines maker economics across the universe of
fills, not the median. With mean spread of 4-6c, a maker at mid
captures ~2-3c half-spread which clears the 1c round-trip fee.

Still NOT a SHIP candidate without realized-P&L validation, but
the spread economics are good enough to justify a shadow probe.
