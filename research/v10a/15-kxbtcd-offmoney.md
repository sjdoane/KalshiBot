# Round 15c Track 2B: KXBTCD off-money strike analysis

Method: parse strike from KXBTCD ticker (T<strike>$ suffix).
Infer event-level spot by finding the strike whose median
yes_price is closest to 0.50 (ATM proxy). Bucket each
trade by (strike - spot) / spot. For each (bucket, price
range), compute maker-side event-level cluster bootstrap
CI on net P&L after Kalshi maker fees.

Maker side: if taker_side='no' the maker is YES side at
yes_price; if taker_side='yes' the maker is NO side at
no_price. Net P&L computed accordingly.

Window: Becker 2024-11-01 to 2025-11-25.

## Per-bucket per-price-range results

### deep_ITM_below_-5pct

| Price range | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| yes_px_0.05_to_0.30 | 6410 | 111 | +0.0935 | +0.0272 | +0.1634 |
| yes_px_0.30_to_0.50 | 5167 | 65 | +0.1230 | +0.0165 | +0.2215 |
| yes_px_0.50_to_0.70 | 4870 | 54 | +0.2283 | +0.1623 | +0.2918 |
| yes_px_0.70_to_0.95 | 5838 | 142 | +0.1125 | +0.0958 | +0.1281 |
| yes_px_any | 25573 | 262 | +0.1014 | +0.0749 | +0.1284 |

### ITM_-5_to_-1pct

| Price range | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| yes_px_0.05_to_0.30 | 55624 | 1171 | -0.0884 | -0.0948 | -0.0820 |
| yes_px_0.30_to_0.50 | 45618 | 477 | -0.1419 | -0.1601 | -0.1228 |
| yes_px_0.50_to_0.70 | 41615 | 551 | +0.1885 | +0.1693 | +0.2080 |
| yes_px_0.70_to_0.95 | 52095 | 1309 | +0.1042 | +0.0992 | +0.1091 |
| yes_px_any | 219432 | 1701 | +0.0133 | +0.0099 | +0.0165 |

### ATM_-1_to_+1pct

| Price range | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| yes_px_0.05_to_0.30 | 980512 | 5384 | -0.0042 | -0.0084 | -0.0004 |
| yes_px_0.30_to_0.50 | 870613 | 5380 | -0.0003 | -0.0045 | +0.0036 |
| yes_px_0.50_to_0.70 | 890939 | 5379 | +0.0307 | +0.0261 | +0.0354 |
| yes_px_0.70_to_0.95 | 928806 | 5383 | +0.0273 | +0.0232 | +0.0314 |
| yes_px_any | 4011079 | 5408 | +0.0129 | +0.0113 | +0.0145 |

### OTM_+1_to_+5pct

| Price range | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| yes_px_0.05_to_0.30 | 49418 | 1160 | -0.0823 | -0.0892 | -0.0755 |
| yes_px_0.30_to_0.50 | 36665 | 502 | -0.0881 | -0.1101 | -0.0661 |
| yes_px_0.50_to_0.70 | 34789 | 578 | +0.2274 | +0.2100 | +0.2427 |
| yes_px_0.70_to_0.95 | 50987 | 1341 | +0.1062 | +0.1013 | +0.1110 |
| yes_px_any | 197221 | 1745 | +0.0238 | +0.0209 | +0.0268 |

### deep_OTM_above_+5pct

| Price range | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| yes_px_0.05_to_0.30 | 9889 | 90 | -0.0756 | -0.0986 | -0.0479 |
| yes_px_0.30_to_0.50 | 9062 | 45 | -0.0626 | -0.1288 | +0.0166 |
| yes_px_0.50_to_0.70 | 9527 | 54 | +0.1974 | +0.1240 | +0.2658 |
| yes_px_0.70_to_0.95 | 10177 | 100 | +0.1134 | +0.0957 | +0.1284 |
| yes_px_any | 43323 | 152 | +0.0270 | +0.0128 | +0.0433 |

## Verdict

**Result: NULL on the lottery-ticket / off-money hypothesis.** The deep
OTM and deep ITM cells with extreme event-means (+9% to +23%) all
suffer from one or both of the following methodological problems:

### Methodology caveat: spot proxy is per-event, not per-trade

The `inferred_spot` is computed once per event_ticker as the strike
whose median yes_price across the event is closest to 0.50. BTC spot
can move 5%+ during a single daily KXBTCD event. A trade timestamped
early in the event where strike was actually 1% from real-spot may
later be bucketed as "deep_ITM" or "deep_OTM" if spot drifted during
the event. This creates a structural confounder: the buckets at
extremes are systematically selecting trades where spot was very
different from the event's terminal ATM strike.

### Selection-effect contamination at the extremes

deep_OTM yes_px_0.70_to_0.95 (+11.34% CI [+9.57, +12.84]) can only
exist when the market priced YES highly AND the strike is far above
the inferred terminal ATM. That combination implies the spot at
trade time was much closer to the strike than the inferred-spot
suggests. We are reading the SELECTION as if it were a discovered
edge. Same logic in reverse for deep_ITM yes_px_0.05_to_0.30
(+9.35%): trades that priced YES at 5-30% while strike is below
terminal ATM imply intermediate-period spot below the strike.

### Cleanest interpretable cell confirms existing v1 edge

ATM yes_px_0.70_to_0.95 (928,806 trades, 5,383 events) yields
+2.73% event-mean with CI [+2.32%, +3.14%]. This is consistent with
the Round 15b cluster-bootstrap KXBTCD edge of +1.25% OOS; the
larger magnitude here is because we combined train and OOS in one
window. NOT a new finding.

### Action

NO change to v1 or v2 strategy. Deep-OTM off-money trading is NOT
recommended based on this evidence. The cells that look like an
edge are dominated by spot-bucketing artifacts. A clean version
of this analysis would require trade-time BTC spot data joined to
each trade, which is outside the current Becker schema and outside
the project's data layer.

This is a NULL verdict, not a SHADOW-CANDIDATE.
