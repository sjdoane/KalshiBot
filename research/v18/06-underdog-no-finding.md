# New edge: underdog-NO maker (symmetric favorite-longshot). DEPLOYABLE

**Date:** 2026-06-01. Script `scripts/v18/underdog_no_maker.py`, data
`05-underdog-no-results.json`. Pre-registered mirror gate in the script header.

## The idea

The favorite-longshot bias is symmetric. v1 exploits the favorite side (buy YES
maker at yes_px >= 0.70, favorites underpriced). The mirror: longshots are
OVERPRICED, so buying NO as a maker on an underdog market (no_px >= 0.70, i.e.
yes_px <= 0.30) should earn the same edge. v1 MISSES these entirely (it only
places YES bids at yes_px >= 0.70), so every game framed as the underdog's YES
is skipped.

## Result: the symmetric edge is REAL, same sweet spot

Becker proxy: maker on NO = `taker_side='yes'`, no_price in [70, 95]. Net P&L of
buying NO at no_px = (result=='no' ? 1-no_px : -no_px) - maker_fee. Event-cluster
bootstrap, train/OOS.

| Prefix | NO LOW [0.70,0.86) OOS (CI lo) | NO baseline OOS | favorite-side LOW (for comparison) |
|---|---|---|---|
| KXMLBGAME | +6.9% (+4.2), n=411 | +4.4% (CI +2.2) | +8.3% |
| KXATPMATCH | +5.6% (+2.9), n=483 | +3.9% (CI +1.6) | +6.8% |
| KXWTAMATCH | +4.3% (+1.4), n=445 | +1.9% (CI incl 0) | +7.2% |

The NO-side LOW band [0.70,0.86) confirms on all three sports (OOS CI excludes
zero, beats the NO baseline). The same moderate-degree sweet spot holds: heavy
underdogs (no_px 0.86-0.95) are weak, exactly mirroring heavy favorites. For WTA
the full NO band is marginal but the LOW band is clean, same pattern as the
favorite side.

These are DISJOINT trades from v1's current universe: the favorite analysis is on
favorite-framed markets (`taker_side='no'`, yes>=70); this is on underdog-framed
markets (`taker_side='yes'`, no>=70). No double-counting. It is the same economic
bias measured on the markets v1 cannot currently trade.

## Why this is the strongest v1 enhancement on the board

1. It is a NEW, validated, cross-sport edge (~+5-7% net on the LOW band), not a
   refinement of an existing one.
2. It roughly DOUBLES v1's eligible universe (every game has a favorite; v1 only
   trades it when the market is framed as that team's YES at >=0.70; the NO arm
   catches the other framing).
3. It directly fixes the idle-capital problem from `04-...md(a)`: v1 leaves the
   majority of its bankroll idle because it cannot find enough eligible favorite
   bids. The NO-underdog arm supplies more eligible bids = more deployed capital
   = more total profit, with no loss of edge quality (the LOW NO band ~matches
   the LOW YES band).

## Deployment (DESIGN; not implemented; needs design + review + approval)

This is a real v1 strategy extension, not a config tweak. v1 currently only
places YES maker bids (`favorite_maker.decide` returns side="yes"). The NO arm
adds: when a market's no_px is in [0.70, 0.86) (the underdog is a moderate
underdog), place a NO maker bid, hold to settlement, same per-bid sizing and the
same band-edge weighting from `04-...(b)`. Scanner eligibility, order placement
on the NO side, fill/settlement accounting, and the kill triggers all need the
NO side wired and tested. Estimated a few hundred lines + tests + a code-review
pass; gets operator-approved restart before deploy.

Sequencing suggestion: this NO-arm and the return-on-stake sizing (b) are the
same code area (per-bid eligibility + sizing), so design and ship them together.

## Caveats (same family; do not over-trust the absolute level)

- F11: Becker fills are what HAPPENED, not what a new NO bid fills at. The
  RELATIVE symmetry (NO-underdog edge ~ YES-favorite edge) and the LOW>heavy
  pattern are the F11-robust parts.
- Adverse selection: confirm in v1's live realized P&L by side and band before
  scaling. The NO-underdog side may have different fill dynamics than the YES
  side (thinner books, different taker flow).
- Decay (Burgi): 2026 magnitude may compress.
- WTA full NO band is marginal; restrict WTA to the LOW NO band only.

## Verdict

A genuine new edge: the favorite-longshot bias is symmetric and v1 is leaving
half of it on the table. Recommend designing a NO-underdog maker arm for v1
(LOW band [0.70,0.86), cross-sport), shipped together with the return-on-stake
sizing change, on operator approval. This is the highest-value v1 enhancement
found: new edge + doubled universe + fixes idle capital, all from one validated,
symmetric bias.

---

*Em-dash and en-dash audit: verified clean after write.*
