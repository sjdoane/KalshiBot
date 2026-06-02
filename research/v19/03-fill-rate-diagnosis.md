# v1 fill-rate diagnosis: the lifetime filter excluded the validated universe

**Date:** 2026-06-02. Symptom (operator): v1 places lots of orders that never
fill.

## Symptom, quantified

From v1 state + kill state: of 222 closed orders, **197 were cancelled (never
filled), 25 settled** (~11% fill). Every RESTING order was a September NFL/NCAAF
futures market (3+ months out), and there were ZERO MLB orders despite it being
MLB season.

## Root cause: `min_lifetime_days=30` excluded all game-result markets

The scanner skips any market whose total lifetime (open_time to close_time) is
below `min_lifetime_days` (default 30) or above `max_lifetime_days` (180).

Live market data (2026-06-02):

| Market | lifetime | time-to-close | live volume | passes [30,180]? |
|---|---|---|---|---|
| KXMLBGAME (today/this week) | ~6 days | ~5-6 days | 50-200 (live) | NO (6 < 30) |
| KXATPMATCH / KXWTAMATCH | ~15.5 days | days | live | NO (15.5 < 30) |
| KXNFLGAME-26SEP13 (futures) | ~123 days | ~105 days | stale (no live trades) | YES |
| KXNCAAFGAME-26SEP (futures) | ~117 days | ~104 days | stale | YES |

Game-result markets open only days before the event, so their lifetime is ~6 to
16 days, which is BELOW the 30-day floor. So every in-season game market (where
the validated v18 favorite-longshot edge AND the live liquidity are) was
excluded. What passed the 30-180 window was the opposite: long-lifetime season
FUTURES (Sept games opening months early) that have no live trading until close
to the event. v1 rested maker bids on dead markets, they sat until the stale-bid
TTL cancelled them, and it re-bid the same dead markets: a churn of orders that
cannot fill.

This means v1 has essentially NEVER been trading its validated game-market edge;
the lifetime window routed it to long-horizon futures the whole time, which also
explains why live P&L never matched the Becker game-market validation.

## Fix

Lifetime window changed from [30, 180] to **[0, 21] days** (run_live_bot.ps1 +
the argparse default). Verified against live data: 21d keeps tennis (15.5d) and
MLB (6d) game markets and excludes the season futures (120d+). A scan confirmed
in-season tradeable inventory appears in the window (e.g. WTA favorites with
volume now; MLB favorites materialize as games approach and liquidity builds).
The min_volume>=50 and the favorite-band filters still gate out illiquid /
no-clear-favorite markets, so v1 bids only where there is a favorite and live
volume.

## Secondary (monitored, not changed yet): maker queue position

Even on a liquid market, v1 rests its bid at the current best bid (`yes_bid`),
i.e. at the BACK of the price-time queue, so a seller fills the bids ahead of it
first. After the lifetime fix lands and v1 trades live game markets, watch the
fill rate. If it is still low, the next lever is to rest one tick IN FRONT of the
best bid (become the best bid, capped below the ask so it stays a maker), trading
~1 cent of the +5-8% edge for a large fill-rate gain. Deferred so the primary fix
is isolated and measurable first.

## Deploy

Takes effect on the operator's next v1 restart (.\scripts\restart_bot.ps1). No
code logic changed (scanner filter unchanged); only the lifetime bounds.

---

*Em-dash and en-dash audit: verified clean after write.*
