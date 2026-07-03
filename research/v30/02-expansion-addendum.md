# v30 ADDENDUM: four-arm expansion under 100 percent authorization (2026-07-03)

OPERATOR DIRECTIVE: 100 percent of the Kalshi balance is authorized for live tests;
multiple edges tested in parallel; full deployment later for whatever shows a real
edge in the live data. This addendum expands the pilot within that authorization,
still under the honesty constraint that no arm ever fires on a nulled model or a
known-negative-EV price (live-testing v25/v26/v27 would be paying to re-confirm
their own perfect-information ceilings; that is not a test, it is a donation).

## The four arms

- ARM A (unchanged): locked dutch-book taker capture, both legs IOC.
- ARM B (unchanged): KXRT envelope-bound decided-side TAKER at cost <= 0.94.
- ARM C (NEW): KXRT decided-side MAKER. On a bound-decided strike whose ask is
  above the taker band (the 99.25 percent census case), REST a GTC bid on the
  decided side at min(best bid + 1c, 0.95). KXRT fee_type is plain quadratic:
  maker fills pay ZERO fee; a 0.95 fill on a decided-YES nets +5c at settlement
  if the bound holds. Adverse selection requires informed counterparties; on an
  arithmetic-decided outcome the only information risk is the bound itself
  (envelope + margins, same rules as arm B). Bids are re-derived every run and
  CANCELLED immediately if the bound no longer decides the strike.
- ARM D (NEW): KXTSAW determined-strike MAKER, same construction using the v26
  bound (published Mon-Thu vintage-basis values plus 15-percent-widened same-
  weekday extremes; settlement basis validated 82/82). Rest at min(best bid + 1c,
  0.97). No maker fee on KXTSAW either. Weekly settlement cycle = fast data.

## Expanded limits (frozen)

Per-arm allocation 25 percent of live balance; GLOBAL live exposure cap 90 percent
of balance (10 percent buffer for unwinds); daily new-exposure cap $120; arm C/D
resting caps: max 4 resting orders per arm, max $30 notional per order; resting
orders are cancelled when their bound weakens, when close is past, or on STOP.
All other v30 controls unchanged (STOP, LIVE_ARMED, Discord, cents accounting,
fail-closed reconciles, prefix 30). Money-path review round 3 REQUIRED on the new
resting-order surface (place GTC, cancel, per-run reconcile) before the new arms
arm.

## High-frequency, answered honestly

Sub-second speed is not reachable from this stack and v24 proved the latency race
is lost at retail (the-odds-api lagged Kalshi settlement; MMs converge at
determination on liquid sports). The retail equivalents ARE deployed: burst
polling at 2.5s for transient books (arm A + v29 sentinel), and maker resting
(arms C/D), where fills arrive at the counterparty's speed, not ours.

## Review cadence for the full-deployment decision

The orders and positions ledgers are the dataset. Weekly: per-arm fills, net P&L,
bound violations (should be zero), unwind costs. An arm earns the 100 percent
full-deployment proposal when its LIVE record shows positive net P&L over >= 20
fills across >= 8 distinct events with zero bound violations; that proposal comes
back to the operator explicitly.

*Em-dash audit: clean (verified after write).*
