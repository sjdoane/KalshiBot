# v24 Idea 5: index/financial volatility-mispricing taker. NULL (the closest v24 came to a signal).

**Verdict: NULL. Fails the OOS gate; the VIX-model control refutes a real vol edge
(capture phantom in the vol dimension). No capital deployed.**

**Date:** 2026-06-30
**Scripts:** `scripts/v24/index_vol_backtest.py` (Becker KXINX + FRED SP500/VIXCLS).
Crypto vol NOT built (dead on arrival per v23 + the plan critic: the maker version
of KXBTCD/KXETHD/KXBTC range already failed at a ~1pp hurdle; a taker pays ~3pp).

## The idea (operator-requested creative financial model)

Not directional (unforecastable + priced). Instead a VOLATILITY model: forecast
the S&P 500 settlement distribution (sigma) and trade Kalshi index range/threshold
markets (KXINX, S&P 500, HALF taker fee 0.035) where the model-implied P(strike)
diverges from the Kalshi price, to harvest the variance risk premium / any vol
mispricing. Day-before window (12-36h before the 4pm settlement; FRED's daily close
is an accurate 4pm-aligned spot there; same-day KXINX is the most MM-saturated
window = excluded). Realized-vol model (trailing FRED returns) -> lognormal
P(strike), net of the half taker fee, event-clustered by settlement day, OOS split
at 2025-07-01.

## Results (RV windows 5/10/20, all consistent)

| Model | TRAIN net (CI) | OOS net (CI) |
|---|---|---|
| Realized-vol (the strategy) | +7.0pp [+1.0,+13.0] PASS | +4.7pp [-1.7,+11.4] **FAIL** |
| VIX control (market's own vol) | +6.4pp [+1.3,+11.3] PASS | **+0.3pp [-6.7,+7.2]** ~0 |

Capture-phantom diagnostic (n=592): median(Kalshi_price - VIX_model_P) = +3.04pp;
median(realized_model_P - VIX_model_P) = +0.1 to +0.35pp (the realized-vs-VIX wedge
is tiny; realized vol approximately equals VIX over this window).

## Why this is a NULL (three converging reasons)

1. **OOS gate fail.** The realized-vol strategy's OOS CI straddles zero
   ([-1.7,+11.4]pp) at every RV window. Per the locked criteria (OOS CI lower > 0),
   it does not pass. n is modest (30 OOS settlement-day clusters).

2. **The VIX-model control refutes a real vol edge (the decisive test).** Trading
   toward the MARKET'S OWN best public vol forecast (VIX) gives TRAIN +6.4pp
   (significant) but OOS +0.3pp (~0). In-sample-positive / OOS-zero is the textbook
   signature of NO real edge: Kalshi prices index vol efficiently vs the options
   market = the capture phantom in the vol dimension. If the market's best vol
   can't beat Kalshi OOS, a retail realized-vol model can't either.

3. **The realized-model's OOS positive is selection noise, and the +3pp diagnostic
   is model bias.** Realized vol approximately equals VIX here (wedge ~0.2pp), so
   the realized model has no genuine informational advantage over VIX; its +4.7pp
   OOS vs the VIX-control's +0.3pp is small-sample selection luck (different markets
   clear the |g|>=5pp threshold). The median +3.04pp "Kalshi above VIX-model" does
   NOT translate into OOS profit via the control, marking it as my model's
   horizon-approximation bias (driftless 1-day lognormal), not a real Kalshi
   mispricing -- the same naive-model-vs-better-informed-market trap that produced
   the weather phantom.

## Honest framing

This is the CLOSEST v24 came to a signal (a positive, sign-stable OOS point on a
documented phenomenon, the VRP, with the half-fee advantage). It is a NULL, not a
clean phantom, because of underpowering + the control. The reason it does NOT earn
a live capital test: the VIX control is decisive (the market's best public vol does
not beat Kalshi OOS), so a real, large, capturable vol edge is unlikely, and the
positive point is the exact underpowered/model-bias artifact that fooled the
weather idea. Deploying capital here would be a manufactured loss.

A genuinely more powered revisit would need MORE KXINX history (Becker ends
2025-11; ~280 events is thin for a 30-cluster OOS), a horizon-bias fix
(actual trade-to-settlement time + drift), or the same-day intraday version (but
same-day S&P is the most MM-saturated = strongest capture phantom). The
control evidence makes a real edge unlikely enough that this is not worth the build
without a new information advantage the market lacks.

## Conclusion

Index vol-mispricing = NULL. Crypto vol = dead on arrival (v23 + fee arithmetic).
The capture phantom holds in the vol dimension too: Kalshi prices index volatility
efficiently vs the options market. This is consistent with the v24 meta-summary:
financial markets are the MOST efficient (Becker Finance gap 0.17pp), so the
capture phantom is strongest there. No capital deployed.

*Em-dash and en-dash audit: verified clean after write.*
