# v24 pivot 3: cross-market structural arbitrage (dutch books) = walled (static)

**Date:** 2026-06-30. A genuinely NEW edge CLASS, not another forecasting bet. The
project's two walls are both informational (taker capture phantom, maker adverse
selection), so every prior idea hit them. A cross-market structural arb is
non-informational: within one event (same underlying + settlement) the outcome markets
must be mutually consistent, and a LOCKED dutch book (a basket guaranteed to pay >= $1
for a cost < $1 net of the worst-case taker fee) is risk-free. It dodges the capture
phantom (no forecast) and adverse selection (both legs taken at once), and being
risk-free it is far less capacity/variance-sensitive than the thin-market ideas.

Tool: `scripts/v24/kalshi_arb_scanner.py` (interval-based via floor/cap strike +
strike_type; handles threshold and partition ladders; one-shot + `--monitor` mode).

## Result: no static dutch book in the tradeable ladders

- Snapshot scan of the liquid multi-outcome ladders (KXINXU S&P, KXNASDAQ100U,
  KXBTCD, KXETHD, KXMLBTOTAL, KXHIGH weather across 7 cities): **0 locked arbs** net of
  the worst-case 0.07 fee.
- A 14-poll live burst (every 12s, ~3 min) on the 24/7 crypto ladders (the most
  volatile, most likely to show a transient inconsistency): **0 arbs**.
- Comprehensive full-open-universe drain: the open universe is dominated by tens of
  thousands of auto-generated $0-liquidity KXMVE parlay/combo markets whose legs have
  no executable size, so any inconsistency there is non-capturable; the tradeable
  ladders are the KXINX/crypto/totals/weather ones already covered.

Kalshi enforces within-event consistency in calm conditions (the BIDS are tight and
monotonic; only the far-OTM ASKS are wide, e.g. a 0.03 bid / 0.41 ask on a deep-OTM
S&P strike, but wide asks are not a taker arb: buying the overpriced ask loses, and a
taker cannot sell). So the static structural-arb angle is walled, like the info angles.

## The one live, non-phantom residual: transient arbs during fast moves

The only place a locked arb can appear is DURING a fast move, when MMs pull or lag their
quotes and the ladder momentarily crosses. These are risk-free when they fire and
capturable by a retail taker (Kalshi is not HFT-speed), and they CANNOT be backtested
(Kalshi serves no historical orderbook), which is precisely why they may remain
un-arbed. The `--monitor` mode is the tool for this; it should be run during
volatility windows (US open 9:30 ET, FOMC 2pm, CPI/NFP 8:30am, sharp crypto moves)
rather than calm periods. It is alert-only; capturing a caught arb requires fast manual
execution (or a future auto-exec layer with its own risk controls).

## Verdict

Static cross-market arb: walled (4th distinct angle closed this session, after index
realized-vol, event-vol, and sports props). The transient-arb monitor is the one
standing, risk-free, non-phantom capability worth keeping; its value is conditional on
running during volatility and on fast execution. No capital deployed. The session's
overall finding stands: Kalshi is comprehensively efficient for a retail account
without a new external advantage (private/faster data, or an auto-execution latency
edge on transient arbs).

*Em-dash and en-dash audit: verified clean after write.*
