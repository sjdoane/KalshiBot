# v30 CHARTER: LIVE PILOT EXECUTOR (operator-directed, real capital, armed-not-burned)

**Date:** 2026-07-03. OPERATOR DIRECTIVE (this session, reaffirming the 2026-06-29
standing authorization on file): live capital deployed in parallel per strategy,
10-20 percent each, immediately, because live fills are better data than paper and
the Kalshi balance is not the operator's whole capital. This charter records how
that directive is executed HONESTLY: both arms fire ONLY on arithmetic conditions;
capital is ARMED continuously and SPENT only when a condition appears. The executor
never fires on a model opinion, and it never takes known-negative-EV filler trades
(a determined strike asked at 0.99 nets zero after the fee; buying it would be a
donation, not data: the kill-early principle applies to trades too).

## The two arms (scripts/v30/live_pilot.py, task KalshiV30LivePilot, every 5 min)

- ARM A, dutch-book capturer (v29 charter's execution half, brought forward under
  the operator directive): when the sentinel arithmetic detects a locked two-leg
  basket with net edge >= 2pp, buy BOTH legs IOC at the detected prices. If the legs
  fill unevenly, the excess is unwound immediately IOC (bounded loss, logged loudly).
- ARM B, RT decided-side taker (the v28 read gate's execution half, brought forward
  the same way): when the live envelope bound decides a KXRT strike and the decided
  side costs <= 0.94 (net-if-right >= +2c after the worst-case fee), buy IOC at the
  quoted level, hold to settlement.

## Hard limits (frozen)

Per-arm allocation 15 percent of the LIVE balance at fire time (inside the
operator's 10-20 band); arm A basket cost cap $40 and max 2 baskets per ET day;
arm B per-fire cap $30, max 3 concurrent, one fire per market lifetime; GLOBAL
daily new-exposure cap $60; kill switch = data/v30/STOP (delete LIVE_ARMED to
de-arm without stopping logging); every order Discord-alerted and appended to
data/v30/orders.jsonl; client_order_id prefix 30; script and task self-expire
2026-09-01. Money-path code review REQUIRED before LIVE_ARMED is created
(research/v30/01-money-path-review.md), and any CRITICAL finding blocks arming.

## Honest expectations, stated up front

Fire frequency is LOW by design: locked baskets appeared zero times in calm
conditions across all prior scans, and the v28 census found only 18 executable
decided prints in five months. Weeks of zero fills are the expected base case and
are themselves the live data (they measure whether these conditions ever exist at
retail speed with real money waiting). The reporting duty is unchanged: fills,
misses, unwind losses, and zero-weeks all get reported exactly as they occur.

## Relationship to the locked research gates

The v28 read gate and v29 sighting gate continue running unchanged and their logs
remain the evidence of record; this executor is the operator-directed live
instrument on top of the same arithmetic conditions. Research conclusions will
cite the executor's REAL fills wherever they exist (strictly better evidence than
the monitors' quotes).

*Em-dash audit: clean (verified after write).*
