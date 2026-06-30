# v24 META-SUMMARY: the retail-taker hunt and the wall it found

**Date:** 2026-06-30
**Scope:** the v24 autonomous TAKER-pivot loop (after the maker family was
exhausted). Capital FLAT throughout; $0 deployed; one idea (weather) taken all the
way to a live read that resolved it for $0.

## What was tried, and the verdict

| # | Idea (mechanism) | Honest prior | Outcome | Killed by |
|---|---|---|---|---|
| 1 | Market-price RECALIBRATION, taker | ~7% | REJECTED at plan critic | FLB relabeled; phase-1.6 precedent; taker fee; capture phantom |
| 2 | Weather EXTERNAL-FORECAST divergence, taker | ~12-15% | NULL at a $0 live read | capture phantom (market prices the public NWP better than a naive model) |
| 3 | Microstructure overreaction-reversal, taker | ~5% | REJECTED at plan critic | uncomputable on Becker (no mid; bid-ask-bounce); v8-A direction |
| (sports) | External projections on thin props, taker | ~10-12% | not built | capture phantom (v14 borderline-NULL); prop-rich sports offseason now |

Plus the inherited, pre-v24 evidence that points the same way: the maker family
(v1 break-even, v18/v23 NULL) died to ADVERSE SELECTION; v8-A (crypto naive model)
and the v14 sports lead-lag taker both confirmed the CAPTURE PHANTOM live.

## The one wall, stated plainly

Every retail edge idea on Kalshi dies to one of two mechanisms, and they are two
faces of market efficiency:

1. **MAKER side -> ADVERSE SELECTION.** A resting quote fills more on the books
   that move against it. The idealized event-mean edge is a mirage; the
   fill-weighted truth straddles zero (v23: +6.6pp event-mean vs -1.4pp
   fill-weighted; v1 lived this at break-even).

2. **TAKER side -> the CAPTURE PHANTOM.** For any PUBLIC-information signal, the
   market/MM already prices it into the live ask AT LEAST AS WELL as a retail
   model, so crossing the ask captures nothing. Confirmed live four ways now:
   v8-A (crypto, 8/8 losses p~0.004), v1 (favorites fairly priced at the fill),
   v14 (sports lead-lag CI straddles zero), and v24 weather (today: my naive NWP
   model is 2-6F off the settlement-anchored market; the market correctly discounts
   NWP's over-predicted extremes; station bias and sigma both ruled out).

The taker fee (worst-case `ceil(0.07*P*(1-P))` = 1-2pp of the $1 contract) is a
modest hurdle, NOT the main wall (the 2026-06-29 "15pp" arithmetic was corrected).
The main wall is efficiency: the market prices public info, and retail has no
private info and no latency edge.

## Why the remaining menu does not escape the wall

- **Sports-props (the highest remaining prior, ~10-12%):** the edge would have to
  live in THIN props with NO sharp-book reference (so Kalshi cannot track a sharp
  line). But (a) Kalshi tracks the sharp books where they exist (v14 borderline-
  NULL on the in-season MLB moneylines), (b) the prop-rich sports (NFL/NBA/NCAAF)
  are OFFSEASON right now, so a live test is impractical until fall, and (c) the
  "thin because lazy market" vs "thin because unforecastable" cut is unfavorable.
  A real shot needs a fall-season live test (NFL/NBA props) + a projection model;
  it is a multi-week build with a low prior against the same capture phantom.
- **Conformal / selective prediction:** a MULTIPLIER on a base edge; no base edge
  exists, so it is dead standalone.
- **Smart-money flow, manipulation-reversal, high-bias-thin categories,
  new-listing:** all sub-10%, all either capture-phantom-exposed or
  capacity-dead, several already nulled.

## Honest conclusion

The high-prior retail-taker space on Kalshi is exhausted. Across recalibration,
weather, microstructure, crypto, favorites, and sports lead-lag, the same wall
holds: the market efficiently prices public information (capture phantom on the
taker side) and adversely selects resting quotes (on the maker side), and retail
has neither private information nor a latency edge to get around it. This is a
clean, well-evidenced NULL pattern, not a failure of effort. The kill-early
principle says this is the correct posture: do not deploy capital where the only
"edges" are phantoms.

The single methodological win worth keeping: the read-only-first live check
resolved the weather capture phantom for $0, instead of losing capital on a
phantom. That pattern (cheap live read BEFORE capital) is the right gate for any
future public-info taker idea.

## What would change this (the genuine next directions, in priority order)

1. **A fall-season sports-props live test (NFL/NBA thin props with no sharp line).**
   The one untested escape, but it is months away (offseason) and needs a
   projection build; honest prior ~10-12%.
2. **A genuine information advantage the market lacks** (a private/proprietary or
   structurally-faster data source). None is currently available to this project.
3. **Stand down on the clean null** and keep capital flat until such an advantage
   appears.

My best-judgment recommendation: do NOT deploy capital now (every current "edge"
is a phantom); treat the v24 wall as the deliverable; revisit sports-props in the
fall season if the operator wants the build. Capital stays flat. If the operator
points me at a specific data advantage or wants the fall sports-props build, I run
it fully autonomously under the standing authorization.

*Em-dash and en-dash audit: verified clean after write.*
