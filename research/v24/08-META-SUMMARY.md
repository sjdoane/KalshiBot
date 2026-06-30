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
| 4 | Sports-props (MLB totals/HR), taker | ~10-12% | NULL at a $0 live read | capture phantom: Kalshi MLB totals track the sharp book to ~0.6pp (doc 09) |

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
   model, so crossing the ask captures nothing. Confirmed live FIVE ways now:
   v8-A (crypto, 8/8 losses p~0.004), v1 (favorites fairly priced at the fill),
   v14 (sports lead-lag CI straddles zero), v24 weather (my naive NWP model is
   2-6F off the settlement-anchored market; station bias and sigma both ruled
   out), and v24 sports-props (today: Kalshi MLB totals track the sharp book to
   a clean ~0.6pp, doc 09).

The taker fee (worst-case `ceil(0.07*P*(1-P))` = 1-2pp of the $1 contract) is a
modest hurdle, NOT the main wall (the 2026-06-29 "15pp" arithmetic was corrected).
The main wall is efficiency: the market prices public info, and retail has no
private info and no latency edge.

## Why the remaining menu does not escape the wall

- **Sports-props (DIRECTLY TESTED LIVE, now NULL, doc 09):** MLB is in season and
  Kalshi lists live MLB props. The sharp-lined ones (KXMLBTOTAL totals, KXMLBHR
  player props) track the sharp book to a clean ~0.6pp (capture phantom). The only
  theoretical escape is OBSCURE props with no sharp line (KXMLBSTATCOUNT-type
  season-long combos): thin (capacity-dead), season-long (months of capital
  lock-up), forecastable only via base rates the market also knows; honest prior
  < 5%. Fall NFL/NBA props would be the same capture phantom on the sharp-lined
  props; not worth a multi-week build.
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

1. **A genuine information advantage the market lacks** (a private/proprietary or
   structurally-faster data source). This is the ONLY thing that breaks the
   capture phantom, and none is currently available to this project. Every
   public-info signal tested (5 live confirmations) is already priced.
2. **Obscure no-sharp-line props** (e.g. KXMLBSTATCOUNT season-long combos): the
   last theoretical escape, but capacity-dead, slow (season-long capital lock),
   and base-rate-forecastable-by-the-market; honest prior < 5%.
3. **Stand down on the clean null** and keep capital flat until such an advantage
   appears.

My best-judgment recommendation: do NOT deploy capital now. Both most-promising
candidates (weather, sports-props) were taken all the way to a LIVE read and both
confirmed the capture phantom for $0. Every current "edge" is a phantom. Treat the
v24 wall as the deliverable; keep capital flat. If the operator can supply a
genuine information advantage the market lacks (the only thing that breaks the
phantom), I run it fully autonomously under the standing authorization.

*Em-dash and en-dash audit: verified clean after write.*
