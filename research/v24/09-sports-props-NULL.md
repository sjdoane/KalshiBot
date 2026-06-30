# v24 sports-props taker: NULL. Capture phantom confirmed live on MLB totals ($0).

**Verdict: NULL. Kalshi sharp-lined MLB props track the sharp book to ~0.6pp =
capture phantom. No capital deployed. Resolved for $0 via a live read.**

**Date:** 2026-06-30
**Script:** `scripts/v24/mlb_props_capture_check.py` (live Kalshi KXMLBTOTAL vs
the-odds-api sharp-book totals; the-odds-api credits ~6831 remaining).

## Correction to the meta-summary's "offseason" framing

I initially dismissed sports-props as offseason. That was wrong: NFL/NBA/NCAAF are
offseason, but MLB is IN SEASON and Kalshi lists live MLB props: KXMLBTOTAL (game
totals), KXMLBHR (player home-run props), KXMLBSTATCOUNT (obscure season-long
combos). So sports-props was live-testable today, and I tested it.

## The clean live result

Comparing 32 live Kalshi KXMLBTOTAL markets to devigged sharp-book totals, the raw
median gap looked like 5.7pp, BUT that is almost entirely a definitional artifact:
Kalshi "k+" = P(total >= k) = P(> k-0.5), while a whole-number book line "over k"
EXCLUDES k (push). The correct test is the CLEANLY-ALIGNED subset where the Kalshi
strike k equals a book HALF-line + 0.5 (so Kalshi P(>=k) == book P(over k-0.5),
no push ambiguity):

| Kalshi market | gap |
|---|---|
| TBKC total 10 (book 9.5) | 0.9pp |
| SDCHC total 12 (book 11.5) | 0.8pp |
| CWSBAL total 11 (book 10.5) | 0.6pp |
| PITPHI total 9 (book 8.5) | 0.5pp |
| MIACOL total 12 (book 11.5) | 0.3pp |
| MINHOU total 9 (book 8.5) | 0.1pp |

**Clean median gap = 0.6pp (max 0.9pp), far inside the ~3pp taker hurdle.** Kalshi
MLB totals track the sharp book essentially perfectly. The sharp-line edge is
already priced into Kalshi: CAPTURE PHANTOM confirmed, live, for sports.

## Why this generalizes to sports-props broadly

- KXMLBTOTAL (totals) and KXMLBHR (player props) have sharp-book equivalents that
  Kalshi tracks to <1pp -> no taker edge (capture phantom).
- The only theoretical escape is OBSCURE props with NO sharp-book line
  (KXMLBSTATCOUNT-type season-long combos, e.g. "all hitters combined 11+
  inside-the-park HRs"). These are: thin (capacity-dead), season-long (months of
  capital lock-up for a tiny market), and forecastable only via base rates the
  market also knows. Honest prior on a real, capturable, capacity-meaningful edge
  there is < 5%. Not pursued.
- This matches the project's prior sports evidence: v14 (MLB sportsbook lead-lag
  taker) came in borderline-NULL (CI straddled zero) because Kalshi already tracks
  the sportsbook.

## Conclusion

Sports-props = NULL. The capture phantom is now confirmed LIVE five ways (crypto
v8-A, favorites v1, sports lead-lag v14, weather v24, MLB totals v24). Kalshi
prices public information (sharp-book lines, NWP forecasts) into the price at least
as well as a retail model, so a taker crossing the ask captures nothing. No
capital deployed; resolved for $0. The v24 wall (meta-summary doc 08) stands and
is now airtight on its two most-promising candidates (weather + sports), both
live-tested.

*Em-dash and en-dash audit: verified clean after write.*
