# v30 ADDENDUM: ARM E, KXHIGH determined-strike capture (2026-07-12)

OPERATOR DIRECTIVE unchanged from the 02 expansion: multiple edges tested in parallel
under the honesty constraint that no arm fires on a nulled model or a known-negative-EV
price. ARM E adds a fifth arm on the KXHIGH daily-high temperature markets, shipped
STAGED-DISARMED so it produces its own calibration data before a single real order.

## Mechanism

The intraday running MAX temperature at a station is monotone non-decreasing through the
local day, and the settled daily high H satisfies H >= running_max and can only rise. A
market side is DECIDED (locked) only when it stays the outcome for EVERY possible final H
in [running_max, +inf):

- An open-ended-up YES tail (">K" / ">=K", cap open) LOCKS YES once running_max crosses
  the floor by the margin: a higher max keeps it YES.
- An upper-bounded YES interval (a "<K" / "<=K" tail, or a "[floor,cap]" band) LOCKS NO
  once running_max exceeds the cap by the margin: a higher max keeps it NO.
- A band is NEVER lockable YES intraday (a later spike can still exit it upward), and a
  ">K" tail is never lockable NO. Everything else stays undecided.

The determination lives in scripts/v30/highs.py (feed + strike parsing + monotone lock);
live_pilot.py owns placement only. Strike semantics were verified against live KXHIGH
market objects: tails are strike_type "greater" (floor_strike, cap open) and "less"
(cap_strike), bands are "between"; the parse matches the scripts/v24/weather_* settlement
precedent. Determination is recomputed FRESH every run; decided state is never cached
across runs.

## Backtest evidence

68 days, 2,856 settled KXHIGH markets, 7 cities. At the +1.0F safety margin the lock rule
had 0 determination violations in 879 decided events (a 0F margin showed 6.5 percent
violations, so MARGIN_F = 1.0 is mandatory and hard-coded). The feed is IEM ASOS hourly
METAR (report_type 3 and 4, data=tmpf), the same obs the NWS CLI daily high settles on;
stations map one-for-one to the v26 RAIN_PIL settlement stations. A city with fewer than
3 usable obs so far today is treated as feed-down for that city (anti-footgun against a
thin early-day feed).

Fills in the backtest arrived 3.7 to 7.2 per week at 90 to 97c bids on the decided side.
Point estimate at charter scale is roughly $7 to $16 per week. HONEST LATENCY CAVEAT: the
decided sub-0.97 prints post-crossing persist about 90 seconds at the median with a fat
tail out to about 11 minutes. A 5-minute executor cadence samples only that fat tail, not
the median window, so realized fills will run below the backtest count. This is the same
retail-latency reality the 02 addendum documented for the sports books; maker resting is
the honest way to harvest it, and the armE_intent calibration rows (below) will measure
the true reachable rate before any capital is committed.

## Modes and caps

Per decided, non-held strike, at most one mode per ticker per run:

- E-TAKER first: decided-side ask <= 93c and (100 - ask - worst-case quadratic taker fee)
  >= 5c net -> one IOC buy per run through the arm B plumbing, $30 cost cap, ledger kind
  armE_open. Fee uses the shared taker_fee helper at coeff 0.07.
- E-MAKER otherwise: a flat 90c GTC bid on the decided side, placed only if the current
  best bid on that side is below 90c (skip if already >= 90c), through the existing
  reconcile_and_place_rests plumbing with arm "armE". Cap 4 resting orders, $30 notional
  per order. Rests are cancelled when the bound no longer decides the strike or the close
  passes, exactly as arms C/D. Feed-down is per-city: a station whose IEM feed is down or
  short (or whose Kalshi market fetch fails) is skipped for the run, its markets are not
  acted on and its existing rests are LEFT resting (not cancelled on absence), while the
  healthy cities proceed. A rest is bound-weakened only when its city's feed is healthy this
  run AND its event day is the station-local today; prior-day rests (day rollover) are left
  to the close-passed/settled cleanup. The E-maker reconcile runs EVERY run regardless of
  arm E's armed state, so existing rests are always fill-detected and bound-cancelled.

All existing global controls apply unchanged: the $120 daily new-exposure cap, the 90
percent global-cap halt (which blocks NEW placement only, never the reconcile/cancel/fill
pass), one new rest per arm per run, cents accounting, fail-closed reconciles, and Discord
alerts on real orders. Arm E skips any ticker already held by any arm (same no-stacking
rule as C/D).

## Staged-arming protocol

Arm E is DISARMED by default. Real arm E orders require BOTH data/v30/LIVE_ARMED (the
pilot-wide live gate) AND data/v30/ARM_E_ARMED. The operator arms arm E by creating the
empty file data/v30/ARM_E_ARMED and de-arms it by deleting that file. De-arming stops all
NEW arm E placement while the other arms keep running, but the existing arm E rests are
still reconciled every run: fill detection and bound-weakened cancels keep running exactly
as while armed, so a de-arm after fills never strands a live rest unmanaged. Only new
orders stop. data/v30/STOP still kills everything, arm E included.

While ARM_E_ARMED is ABSENT the arm computes the full taker/maker decision for every
decided, non-held strike each run and writes kind "armE_intent" rows (ticker, side,
running_max, yes bid/ask, the chosen mode taker or maker or skip, and the would-be price)
but places NOTHING. Those intent rows are themselves the calibration dataset: they record,
run by run, exactly which strikes arm E would have acted on and at what price, so the
reachable-fill rate under the real 5-minute cadence can be measured against the backtest
before the arm is ever armed.

## Review gate for arming and for full deployment

Same bar as the other arms. Arm E earns the proposal to stay armed, and later the full
deployment proposal, only when its LIVE record shows positive net P&L over >= 20 fills
across >= 8 distinct events with zero bound violations. Until then the armE_intent rows
carry the honest picture. The orders and positions ledgers remain the dataset; weekly
review covers per-arm fills, net P&L, bound violations (should be zero), and unwind costs.

*Em-dash audit: clean (verified after write).*
