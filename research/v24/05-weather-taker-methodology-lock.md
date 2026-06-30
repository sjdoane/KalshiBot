# v24 Idea 2 (weather external-forecast taker): METHODOLOGY LOCK

**Date:** 2026-06-30
**Status:** LOCKED before pulling the outcome/screen data. Feasibility checks
already done (network OK; Open-Meteo historical-forecast MAE vs realized = 2.7F =
genuinely skillful, not leaky reanalysis; the `previous_dayN` as-of variables are
not on the free tier). Operator standing authorization (2026-06-29): choose
best-potential autonomously; on real potential DEPLOY LIVE at ~20-30% of the
Kalshi balance rather than run a zero-capital ghost probe; ensure we do not
already have the data first.

This locks the signal, the pre-registered decision rule, the worst-case fee, the
NECESSARY historical screen, and the LIVE deployment trigger + sizing + kill rules
for the weather high-conviction external-forecast taker, before any
outcome-conditioned query.

---

## 0. What this idea is, and why it is not the killed ideas

- NOT idea 1 (price recalibration): the probability comes from an EXTERNAL NWP
  forecast (Open-Meteo), independent of the Kalshi price. ROLE/FEATURES differ.
- NOT the killed weather MAKER (EC-1 Round 1): this is a TAKER on the
  high-divergence tail, operator-authorized as a different mechanism.
- The arithmetic that "killed" this on 2026-06-29 was wrong (see
  `04-arithmetic-correction-and-checkpoint.md`): the taker fee is 1-2pp of the $1
  contract, hurdle ~2-3pp, which a high-divergence edge can clear.

The binding open question is the CAPTURE PHANTOM (does the live ask already embed
the public forecast?). Becker cannot resolve it (no orderbook). Per the operator
authorization, the resolver is a LIVE deployment, not a ghost probe.

## 1. Universe (locked)

- Series: `KXHIGH` daily-high temperature markets for the 5 cities with station
  mappings + existing data: NY (Central Park/KNYC), CHI (O'Hare/KORD), MIA
  (Miami Intl/KMIA), LAX (LAX/KLAX), DEN (Denver Intl/KDEN). Coordinates per
  `src/kalshi_bot/data/weather.py::CITIES`.
- Settlement: the contract resolves on whether the observed daily high exceeds
  the strike. Backtest outcomes from Becker `markets.result` (and cross-checked
  against the Open-Meteo archive observed high). Live outcomes from Kalshi
  settlement.
- Post-October-2024 only for the backtest (the maker-taker sign flip).

## 2. Signal (locked): external forecast probability of the strike

For a market on city C, occurrence date D, strike S (in F):

1. **Forecast point** f = the Open-Meteo forecast of D's daily-high for C, issued
   at the AS-OF trade time (1 to 2 days before D). Backtest: historical-forecast-
   api `temperature_2m_max` for D (honest caveat in Section 6: its effective lead
   is ambiguous, so the backtest is treated as an OPTIMISTIC necessary screen, not
   a clean OOS proof). Live: the current forecast for D pulled at trade time
   (leakage-free by construction).
2. **Forecast-error model** (fit on TRAIN only): sigma_C = std of (forecast point
   minus observed high) for city C at the 1-2 day lead, estimated on the training
   window. A single per-city Gaussian error; report the empirical error CDF as a
   robustness check. NO market price enters this model (it is forecast-vs-weather,
   not recalibration).
3. **Model probability** p_model = P(high_D > S) = 1 - Phi((S - f) / sigma_C).

## 3. Decision rule (locked, pre-registered, one frozen spec)

- Market price p_mkt = the Kalshi price for the YES side (high > S), measured from
  the AS-OF trade window (1 to 2 calendar days before D). Backtest: the
  volume-weighted trade price (Becker `yes_price`) over trades in
  [D - 2 days, D - 1 day]; require >= 1 trade in that window (else no observation).
  Live: the current marketable ask (taker) at trade time.
- **Divergence** g = p_model - p_mkt.
- **Trade (taker) iff |g| >= 0.08 (8pp)** AND p_mkt in [0.10, 0.90] (avoid the
  deepest longshots; pre-registered band). Buy YES (cross the YES ask) if
  g >= +0.08; buy NO (cross the NO ask) if g <= -0.08. Hold to settlement (binary,
  no exit fee).
- The 8pp threshold is pre-registered to clear the ~3pp taker hurdle with ~5pp
  margin (per the corrected arithmetic). ONE threshold, ONE band, ONE lead window:
  no post-hoc scan across thresholds/bands/leads.

## 4. Fee + spread (locked, worst-case)

- Worst-case TAKER fee = `ceil(0.07 * P * (1-P))` cents per contract on the entry
  price P (`kalshi_taker_fee_per_contract`). Applied to every modeled fill.
  (KXHIGH had a brief zero-fee taker window 2025-03-04 to 04-01; worst-case
  ignores it.) Held to settlement: no exit fee.
- Spread haircut (backtest): entry price = the as-of trade VWAP + 1 cent
  (lift-the-ask proxy). Live: the real ask.

## 5. NECESSARY historical screen (pass criteria, before any live capital)

Inference: event-cluster bootstrap `cluster_bootstrap_mean_ci(values, cluster_ids,
n_resamples=5000, ci=0.95, rng_seed=42)`, cluster = (city, occurrence_date) event,
values = per-fill net P&L per $1. Chronological split: TRAIN = post-Oct-2024 to
2025-08-15; PURGE 7 days; OOS = 2025-08-22 to Becker end. Sigma_C fit on TRAIN
only.

The screen PASSES (necessary, not sufficient) iff ALL:
- **W-1 (powered):** >= 40 settled traded events in each of TRAIN and OOS at the
  locked threshold+band (KXHIGH is daily x 5 cities x strikes, so this should be
  satisfiable; if not, the slow 1-2-day window is too illiquid -> documented and
  the live test uses whatever window is liquid).
- **W-2 (TRAIN sign):** aggregate net P&L per contract > 0 with cluster CI lower
  bound > 0, net of worst-case fee + spread haircut.
- **W-3 (OOS sign):** same on OOS (CI lower bound > 0).
- **W-4 (forecast skill, sanity):** the per-city forecast MAE on OOS < the
  per-city climatological std of the daily high (the forecast must beat
  climatology; already indicated by the 2.7F MAE feasibility check).

KILL if W-1..W-4 do not all hold: this is an OPTIMISTIC screen (the backtest
forecast lead is ambiguous and if anything leaky-favorable), so a NEGATIVE result
is a strong kill (it cannot even win with optimistic leakage). NULL weather, pivot.

## 6. The backtest's honest limitation (F4/as-of)

The historical-forecast-api's effective lead is not controllable on the free tier
(no `previous_dayN`). Its 2.7F MAE indicates a short-lead (~0-1 day) forecast, so
using it as a "1-2 day as-of forecast" is OPTIMISTIC (mild look-ahead). This makes
the screen a NECESSARY (not sufficient) filter: a pass is required to risk capital
but is not proof; a fail kills. The leakage-free evidence is the LIVE test
(Section 7), where the forecast is pulled at trade time by construction.

## 7. LIVE deployment (the capture-phantom resolver; operator-authorized)

If the necessary screen PASSES, deploy LIVE (no ghost probe), per the operator
authorization:
- **Signal:** at trade time, pull the current Open-Meteo forecast for D (1-2 days
  out) for each open KXHIGH market, compute p_model, compare to the live Kalshi
  marketable price; fire the locked rule (|g| >= 0.08, p_mkt in [0.10,0.90]).
- **Sizing:** total live exposure capped at 20-30% of the live Kalshi balance
  (poll `/portfolio/balance`). Fixed dollar-risk-per-bet ~ $1 (operator's
  ~$200 bankroll context; cap contracts = floor(per_bet_$ / price)). Hard
  contract cap per market derived from the balance, NOT any backtest peak.
- **Circuit breaker:** stop all new entries if cumulative realized P&L over any
  rolling 7-day window < -20% of deployed capital, OR after 6 consecutive losing
  settlements, OR after 4 weeks. (The standing kill-early + drawdown rules.)
- **Execution:** real marketable (taker) orders via the existing
  `LiveOrderManager` with persisted idempotent client_order_id; READ the live ask
  before crossing; net P&L tracked from `/portfolio/fills` real `fee_cost`.
- **Verdict:** after >= 30 settled live fills, net per fill > 0 with a
  market-day-clustered 95% CI excluding zero AND point >= +1.0pp -> scale toward
  full per operator approval; else NULL and stand down.

## 8. What this lock will NOT do

- NOT scan thresholds/bands/leads post-hoc (one frozen spec).
- NOT use the Kalshi price in the forecast model (no recalibration).
- NOT treat the optimistic backtest as a clean OOS proof (live is the proof).
- NOT exceed 30% of balance, NOT size off a backtest peak, NOT skip the drawdown
  breaker.
- NOT deploy if the necessary screen fails.

*Em-dash and en-dash audit: verified clean after write.*
