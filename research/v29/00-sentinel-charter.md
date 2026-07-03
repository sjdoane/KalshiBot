# v29 CHARTER: transient dutch-book sentinel (deployed measurement, pre-committed pilot gate)

**Date:** 2026-07-03. Class: LIVE-ONLY mechanical edge (the single class never closed
across families 1-28; v24 closed static books and post-determination, and left
transient crossed books during fast moves explicitly open: not backtestable because
Kalshi serves no orderbook history). This is a DEPLOYED MEASUREMENT with an
arithmetic capture rule, not a statistical hypothesis: a locked basket (two taker
legs whose YES-intervals cover the whole outcome space for total cost < $1 net of
worst-case taker fees) is risk-free BY ARITHMETIC when it fills; no cluster CI is
needed to validate one. The open questions are frequency, size, and duration, which
only live measurement answers.

## The deployed engine

scripts/v29/arb_sentinel.py, scheduled task KalshiV29ArbSentinel, every 5 minutes,
task + script self-expire 2026-09-01, read-only, $0, exit 0 always.

- BURST MODE (poll target ladders every ~2.5 seconds for up to 8 minutes) when:
  (a) ET time in 09:28-09:50 Mon-Fri (equity open), (b) 08:28-08:45 Mon-Fri (macro
  release window), (c) 13:58-14:25 ET Wednesdays (FOMC-type afternoons), or
  (d) CRYPTO TRIGGER: |BTC spot move| >= 0.4 percent since the last run (Coinbase
  public spot, state kept on disk). Burst series: KXBTCD, KXETHD always; KXINXU,
  KXNASDAQ100U during equity-hours bursts.
- CALM MODE otherwise: one scan pass per run across the full default list (crypto,
  index, weather ladders): keeps the log alive and catches calm anomalies.
- Detection: the v24 pair rule on structured strikes (two positions whose YES
  intervals union to the real line, cost + worst-case taker fees < $1; reduced
  0.035 coefficient only on KXINX/KXNASDAQ prefixes, 0.07 otherwise). Every locked
  sighting logs legs, net edge, min-leg size, and timestamps; consecutive-poll
  persistence is measurable from the log.

## Pre-committed gates (immutable)

- PILOT GATE: if the log records >= 3 DISTINCT locked arbs (different events, or the
  same event >= 10 minutes apart), each with net edge >= 2pp and min-leg size >= 5
  contracts, and AT LEAST ONE seen on >= 2 consecutive polls (~2.5s apart, i.e.
  plausibly capturable duration), I bring the operator a proposal for a $20-capped
  auto-execution pilot (both legs IOC, one basket per event per day, hard daily
  loss cap, kill switch, operator approval REQUIRED before it exists). No pilot,
  no order-placing code, before that gate and that approval.
- CLOSE GATE: zero locked sightings by 2026-08-15 across >= 25 completed burst
  sessions = the transient class joins the wall (final entry: Kalshi ladders stay
  consistent even under fast moves at retail polling speed), and the sentinel is
  retired at its expiry.

## Honesty notes

Bursts at 2.5-second cadence bound what a retail poller can see; sub-second arbs
are invisible to this engine and remain out of scope (that is a statement about
retail capturability, which is the only question that matters here). The fee model
is worst-case; any sighting is therefore conservative. The engine never places
orders. Removal: Unregister-ScheduledTask -TaskName KalshiV29ArbSentinel.

*Em-dash audit: clean (verified after write).*
