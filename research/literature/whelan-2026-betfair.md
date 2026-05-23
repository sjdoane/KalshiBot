# Whelan (Jan 2026): "Agreeing to Disagree: The Economics of Betting Exchanges"

**Author:** Karl Whelan (University College Dublin)
**Reference:** CEPR Discussion Paper DP20633, January 26 2026
**PDF:** http://www.karlwhelan.com/Papers/Betfair.pdf
**Venue:** CEPR working paper (peer-review-adjacent)
**Retrieved:** 2026-05-23

**Why this matters for Project Kalshi.** This is the THEORETICAL
FOUNDATION that Burgi/Deng/Whelan 2026 adapted for Kalshi. Whelan
formalises the Maker/Taker matching equilibrium on a betting exchange
(Betfair), derives why Makers earn more than Takers, and explains
why longshots get systematic over-pricing. The Kalshi paper is a
direct extension of this framework to a prediction market with a
different fee schedule.

## TL;DR

1. Whelan models a betting exchange where participants sort into
   Maker, Taker, or abstain based on their subjective probability
   beliefs and the matching probability.
2. The model predicts **Makers earn higher returns than Takers**,
   with returns getting nonlinearly worse for Takers as win
   probability falls (the favorite-longshot bias is endogenous).
3. **Multiple equilibria exist** - thick markets (high match rate,
   narrow spreads) and thin markets (low match rate, wide spreads).
4. The empirical Betfair data (200k+ soccer matches 2022-2024)
   confirms the predictions for **pre-match and early in-play**.
5. **"Yogi Berra effect" emerges in late in-play:** as soccer
   matches progress, longshots get systematically over-priced even
   for Makers. Bettors apparently overestimate late-game comeback
   probability.
6. The model assumes a 2% commission on winnings (Betfair's actual
   fee), NOT Kalshi's pre-2025 maker-zero/taker-7% structure. Burgi
   et al adapted Whelan by adding Kalshi's asymmetric fee.

## The core equilibrium logic

Participants sort by their subjective belief π about a Yes outcome:
- π very high → **Take Yes** at the offered price (guarantee
  execution; pay a small premium)
- π slightly high → **Make Yes** at a better price (better odds
  but risk not matching)
- π near average → **abstain** (no edge)
- π slightly low → **Make No** at a better price
- π very low → **Take No** at the offered price

This sorting generates an equilibrium where Takers carry stronger
beliefs and Makers carry weaker beliefs. Because Takers willingly
pay a premium (in spread), Makers extract that premium on the
subset of matches that happen.

## Key parameters (mapped to Burgi's Kalshi adaptation)

| Param | Meaning | Whelan Betfair | Burgi Kalshi |
|---|---|---|---|
| β | Probability over-weighting (small-prob overestimate) | Calibrated to match data | 0.09 |
| σ | Belief dispersion (SD of subjective π around true) | Free param | 0.107 |
| θ | Matching probability | Endogenous in Whelan | 0.60 fixed in Burgi |
| Fee | Commission structure | 2% on net winnings | Pre-2025: 7% on Taker price |

**Critical difference for Kalshi:** Whelan's Betfair model has fees
that affect Makers and Takers symmetrically (both pay 2% on
winnings). Kalshi pre-2025 had Maker fees of zero. Burgi adapted by
making the Taker's expected profit calculation explicitly subtract
the fee, which sharpens the maker/taker return gap.

## The favorite-longshot result

In the model, Takers pay a price PY for Yes. Their expected profit
is `π - PY - f(PY)`. For low-probability outcomes (longshot Yes),
the fee is a smaller percentage of price, but the offset between
their over-optimistic π and the true probability is a larger
percentage of price. So Taker returns get nonlinearly worse as the
event becomes more of a longshot.

Specifically: Makers earn higher returns on longshot Yes contracts
than on favorite Yes contracts, because the spread Maker captures is
a larger fraction of the (small) price. Whelan's model predicts this
nonlinear maker-Take spread.

## Multiple equilibria

Same model can support:
- **Thick equilibrium:** high match rate θ, narrow spreads, more
  Takers willing to accept offers because matching is reliable
- **Thin equilibrium:** low θ, wide spreads, Makers demand larger
  price improvement to compensate for execution risk

Selection between equilibria is exogenous in the model. Whelan
doesn't model the dynamics of equilibrium switching but notes the
parallel to Diamond 1982 search-and-matching models.

## Empirical Betfair findings

- Dataset: 200,000+ soccer matches, 2022-2024, full order book at
  1-second intervals, all matched trades.
- Pre-match and early in-play: Model predictions hold. Takers lose
  more on longshots; Makers near breakeven; Maker returns rise as
  win probability drops.
- **Late in-play anomaly:** longshot bets perform progressively
  worse as the match advances. Makers also start losing. Page
  (2012) "Yogi Berra effect" - bettors keep their late-game hope
  alive past the point where it's rational.

The Yogi Berra effect on Betfair is the analog of what Burgi found
on Kalshi closing-day prices: bias intensifies as the resolution
approaches. **Project Kalshi's Phase 1.6 window choice
(pre-resolution, NOT close-window) is consistent with avoiding this
distortion.**

## Methodology details

- Subjective belief distribution: π ~ N(μ(π*), σ²), where μ(π*)
  shrinks π* toward 0.5 via a parameter (Kahneman-Tversky over-
  weighting of small probabilities).
- Maker/Taker identification on Betfair: comparing trade prices to
  the order book at the time of trade. Not as clean as Kalshi's
  API-level identification.
- Calibration on 200k+ soccer matches with full order book at 1-sec.

## Why Burgi extended Whelan (not just used him)

1. Kalshi's fee structure is asymmetric (Maker = 0, Taker > 0 in
   the sample period). Whelan's symmetric-fee model can't directly
   produce this asymmetry's full effect on returns.
2. Kalshi has prices in cents [0.01, 0.99]; Betfair quotes decimal
   odds. The functional forms of payoff differ.
3. Kalshi resolves binary outcomes; Betfair has longer-running
   in-play dynamics during the match.
4. Burgi adds Kalshi's specific 7%·P·(1-P) fee formula and shows
   the model fits the maker/taker return decomposition.

## Implications for Project Kalshi

1. **The theoretical mechanism is well-understood.** Maker > Taker
   isn't a coincidence; it's an equilibrium property of any
   exchange-style market where Takers can choose to wait. Project
   Kalshi's maker-quoting thesis (EC-1) is theoretically grounded.

2. **The Yogi Berra effect validates our Phase 1.6 window choice.**
   Whelan finds the same closing-time price distortion that Burgi
   finds. We avoid both by trading well before resolution.

3. **Multiple equilibria implies regime-shift risk.** A thin market
   can transition to a thick one (or vice versa) without changing
   any fundamentals. Project Kalshi should monitor match rates and
   spread dynamics for signs of regime shift during live trading.

4. **The model assumes traders maximize subjective expected profit
   with a single contract.** Real traders Kelly-size or
   risk-adjust. The structural model is a first-order
   approximation, not a full description.

5. **For Phase 2 strategy design**, the maker-quoting strategy
   should target the "thick" equilibrium - high match rate, narrow
   spreads. EC-1 implicitly assumes this. If a target market is
   too thin, the model predicts Maker returns degrade because
   matching is unreliable.

## Pin quotes

> "Equilibrium odds emerge from the interaction of these choices:
> the share of participants selecting each of the five actions
> [Take/Make Yes, abstain, Make/Take No] must be consistent with
> the matching probabilities that make those choices worthwhile."

> "In thick-market equilibria, match rates are high, bid–ask
> spreads are narrow and more offers are attractive enough for
> Takers to accept. In thin-market equilibria, low match rates
> lead Makers to demand wider spreads to justify posting,
> producing more execution risk and less liquidity."

> "For bets placed before kick-off or early in the first half,
> Takers lose more heavily on longshots while Makers perform close
> to break-even for most bets, as predicted."

> "During the matches, however, a striking anomaly emerges:
> Longshot bets perform ever more poorly as the match progresses,
> with Makers also recording losses. This pattern is consistent
> with the 'Yogi Berra effect' described by Page (2012)."

## Limitations

- Bet size assumed exogenous (single contract per bet). Real
  Kelly-sized or otherwise utility-maximizing sizing not modeled.
- Symmetric fee structure - doesn't capture Kalshi's asymmetric
  Maker/Taker fees in pre-2025 era.
- Sport-specific data may not generalize to weather/macro/etc.
- In-play dynamics in soccer aren't directly analogous to Kalshi's
  one-shot resolution mechanic.
- Multiple equilibria selection is exogenous.
