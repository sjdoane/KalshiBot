# v18 follow-ups: capital utilization (a), tennis generalization (c), sizing design (b)

**Date:** 2026-06-01. Builds on `02-results-and-recommendation.md` (MLB band
finding) and the adversarial review (verdict MODIFY: prioritize, do not cap).

## (a) v1 capital utilization: NOT capital-constrained

Live snapshot (2026-06-01): Kalshi total $53.5 (cash $40.4 + positions $13.2).
v1 state: **0 resting orders**, 18 filled positions = **$13.5 deployed**. So v1
is using only ~25% of the full bankroll (and was using ~42% of its old 60%
slice). The 18 held positions are legacy NON-allowlist fills (KXBOXING, KXUFC*,
KXWCGAME, KXNBA*, one KXNFLGAME) from before the 13:01 allowlist restart; they
settle out over time.

**Conclusion:** v1's binding constraint is eligible-fill availability, NOT
capital. It leaves the majority of its bankroll idle. This settles the
prioritize-vs-cap question decisively: a hard band cap would only delete
positive-EV fills without freeing usefully-deployed capital, so it would
strictly reduce profit. The right lever is EDGE-WEIGHTED SIZING, not a cap.

The operator's bankroll-fraction change (0.60 -> 1.00, committed `d81d7cc`)
raises the ceiling further, which only reinforces that capital is not the
constraint; deployment will rise only if v1 finds more eligible bids and/or
sizes the bids it does get larger.

## (c) Tennis: the moderate-favorite sweet spot GENERALIZES

Same method (Becker, event-cluster bootstrap, train/OOS), prefixes KXATPMATCH /
KXWTAMATCH. Script `scripts/v18/band_analysis.py`, data `03-tennis-band-results.json`.

| Prefix | LOW [0.70,0.86) OOS (CI lo) | Heavy [0.86,0.95] OOS (CI) | Baseline OOS | LOW passes gate |
|---|---|---|---|---|
| KXMLBGAME | +8.3% (+6.0) | +3.8% [+1.7,+5.4] | +5.3% | yes (CIs non-overlap) |
| KXATPMATCH | +6.8% (+4.4) | +3.3% [+1.7,...] | +5.1% | yes (CIs touch) |
| KXWTAMATCH | +7.2% (+4.9) | +1.1% [-1.0,...] (includes 0) | +4.3% | yes (CIs non-overlap) |

The LOW band (~+7-8% net, OOS CI excludes zero) holds on all three sports; heavy
favorites are weak everywhere and have NO out-of-sample edge for WTA. The
favorite-longshot concentration is a robust, cross-sport phenomenon. So a
LOW-band-prioritizing refinement is broadly applicable to v1's validated
universe, not MLB-specific.

## (b) Return-on-stake sizing change (DESIGN for review; NOT implemented)

Because v1 is capital-idle, this is about putting MORE size on the higher-edge
fills (good Kelly behavior), NOT rationing scarce capital. No fills are dropped.

**Current sizing** (`scripts/paper_trade_favorite.py`): per-bid contracts =
floor(V1_PER_BID_FRACTION(0.03) * v1_cap_total / price), floor 1. Uniform across
price bands.

**Proposed:** weight per-bid size by the fill's band-conditional expected edge,
which is validated cross-sport:

```
band_multiplier(yes_px):
    if 0.70 <= yes_px < 0.86:  return M_LOW    # default ~1.5 (edge ~8% vs ~5% base)
    if 0.86 <= yes_px <= 0.95: return M_HIGH   # default ~0.7 (edge ~3% to 1%)
    else: return 0.0  # outside v1's band; not eligible

per_bid_contracts = floor(V1_PER_BID_FRACTION * band_multiplier(yes_px)
                          * v1_cap_total / price), floor 1
```

Equivalently (cleaner, more principled): size proportional to return-on-stake
(net_edge / yes_px) from the validated band table, normalized so a baseline
fill keeps the current size. Return-on-stake makes the LOW band's advantage
larger (~2.5x), so a return-on-stake weighting concentrates size on LOW even
more than the raw-edge weighting.

**Risk guards (mandatory):**
- Keep the existing drawdown (20%) and consecutive-loss kills armed.
- Cap any single bid at a max fraction of v1 cap (e.g. 10%) so a multiplier
  cannot create an outsized position; with the bankroll idle there is ample
  headroom, but the cap bounds tail risk.
- Make the multipliers conservative and env-tunable (M_LOW, M_HIGH) so a
  possibly-decayed 2026 edge is not over-levered. Start mild (M_LOW 1.3,
  M_HIGH 0.8), widen only if live realized P&L by band confirms the Becker
  ratio.
- Multipliers apply to all validated prefixes (MLB/ATP/WTA all show the band
  effect); for WTA the heavy band has no OOS edge, so M_HIGH could be set to 0
  for WTA specifically as a follow-up once confirmed live.

**Implementation surface:** a pure `band_size_multiplier(yes_px)` helper +
plumb it into the per-bid sizing call, with unit tests on the band boundaries
and the per-bid cap. ~30 to 50 lines. This is a LIVE v1 behavior change, so it
gets a code reviewer pass and operator-approved restart before deploy.

**Caveats:** F11 (band edges are upper bounds; the relative LOW>heavy ratio is
the F11-robust part the sizing rests on), live adverse selection not yet
confirmed by band, year-over-year decay. Confirm the band edges in v1's own
live realized P&L (tag fills by band) before widening the multipliers.

## Net recommendation

1. Bankroll 100%: DONE (committed; takes effect on next v1 restart).
2. Do NOT cap the band (v1 is capital-idle; capping would cut +EV fills).
3. Implement edge-weighted (return-on-stake) per-bid sizing, conservatively, on
   operator approval, with the risk guards above. This captures the validated
   cross-sport LOW-band concentration without dropping any positive-EV fill.

---

*Em-dash and en-dash audit: verified clean after write.*
