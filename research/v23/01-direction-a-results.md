# v23 Direction A Results: WTA-NO moderate-band tennis maker

**Verdict: NULL. KILL Direction A at the Becker screen. No forward work.**

**Date:** 2026-06-28
**Run:** single locked run per `research/v23/00-methodology-lock.md`, no re-runs,
no tuning. Script: `scripts/v23/direction_a_backtest.py` (reproducible, read-only
on the Becker parquet, uses the project `.venv` DuckDB, NOT pandas).
**Inference:** the exact locked callable
`src/kalshi_bot/analysis/bootstrap.py::cluster_bootstrap_mean_ci(values,
cluster_ids, n_resamples=5000, ci=0.95, rng_seed=42)`, cluster unit =
`event_ticker`, `values` = per-fill net per $1, post-October-2024 only.

---

## 1. What was tested (the firable cell)

WTA-NO moderate band, exactly as locked:
- Series `KXWTAMATCH-%`, `taker_side='yes'` (maker resting on NO), `no_price` in
  [70, 86) cents.
- Settlement on the SAME traded ticker (`markets.result` joined on the filled
  `ticker`, AMEND-9 honored), `result IN ('yes','no')` (empty excluded).
- Event cluster = `regexp_replace(ticker,'-[^-]*$','')` (verified 4844/4844 ==
  `markets.event_ticker` on tennis).
- Window assignment by event first-trade-of-any-kind (reproduces the critic-
  verified 669/374 powering exactly).
- Per-fill net per $1 = `(result=='no' ? 1-no_px : -no_px) - fee`.
- Two fee modes: (a) DATED per `research/v22/fee_table.json` (KXWTAMATCH = zero
  the whole window EXCEPT a 5-day `ceil_175` slice 2025-07-08 to 2025-07-13;
  confirmed against the table, AMEND-1), and (b) WORST-CASE `ceil(1.75*P*(1-P))`
  cents = a flat 1c across the whole [0.70,0.86) band (AMEND-2).

Split (locked): TRAIN [2025-06-18, 2025-09-08), PURGE [2025-09-08, 2025-09-15)
(59 events dropped), OOS [2025-09-15, 2025-12-01) (WTA data ends 2025-11-08, cap
harmless; AMEND-8 stale-span note honored).

---

## 2. ATP-NO watch-only diagnostic (written BEFORE the WTA verdict, AMEND-7)

ATP-NO is the carved-out toxic cell. It is reported first and CANNOT rescue WTA.

| Fee | Window | n_fills | n_events | LOCKED cluster mean (per-fill, fill-weighted) | LOCKED cluster 95% CI |
|---|---|---|---|---|---|
| dated | TRAIN | 94008 | 670 | +3.87pp | [-1.14, +8.17] straddles 0 |
| dated | OOS | 151523 | 476 | -0.57pp | [-5.72, +4.53] straddles 0 |
| worst | TRAIN | 94008 | 670 | +2.94pp | [-2.10, +7.28] straddles 0 |
| worst | OOS | 151523 | 476 | -1.57pp | [-6.72, +3.53] straddles 0 |

ATP-NO also fails the locked inference (CI straddles zero on both windows under
both fee modes; OOS point estimate is NEGATIVE). The toxic cell is, as the live
arm suspected, not a clean edge under the binding (fill-weighted) statistic.

---

## 3. WTA-NO GATE result (the binding number)

LOCKED inference (`cluster_bootstrap_mean_ci` on per-fill nets, cluster =
event_ticker; the point estimate is by construction the fill-weighted pooled
mean):

| Fee | Window | n_fills | n_events (k) | LOCKED cluster mean | LOCKED cluster 95% CI | A-2/A-3 |
|---|---|---|---|---|---|---|
| dated | TRAIN | 76918 | 669 | -1.42pp | [-7.26, +4.15] | FAIL (lo < 0) |
| dated | OOS | 107279 | 374 | -1.59pp | [-7.19, +3.86] | FAIL (lo < 0) |
| worst | TRAIN | 76918 | 669 | -2.36pp | [-8.21, +3.21] | FAIL (lo < 0) |
| worst | OOS | 107279 | 374 | -2.59pp | [-8.19, +2.86] | FAIL (lo < 0) |

### Gate adjudication (A-1 .. A-6)

- **A-1 (min-n >= 60 both windows):** PASS (TRAIN 669 events, OOS 374 events).
- **A-2 (TRAIN cluster CI lower > 0):** FAIL. dated lo = -7.26pp, worst lo =
  -8.21pp. The CI straddles zero; the point estimate is NEGATIVE.
- **A-3 (OOS cluster CI lower > 0):** FAIL. dated lo = -7.19pp, worst lo =
  -8.19pp. Straddles zero; point estimate NEGATIVE.
- **A-4 (both fee modes):** FAIL (A-2/A-3 fail under both).
- **A-5 (decay guard):** PASS on the unweighted-event-mean reading (OOS +5.0pp >=
  50% of TRAIN +6.6pp), but A-5 is moot because A-2/A-3 already fail. Reported
  for completeness, not load-bearing.
- **A-6 (concentration < 50%):** PASS (largest tournament-day token = 5.9% TRAIN,
  7.5% OOS of absolute P&L). Not the binding failure.

**WTA-NO FAILS A-2, A-3, A-4. KILL.**

---

## 4. The load-bearing subtlety: fill-weighted vs event-weighted DISAGREE

This run surfaced the single most important honest finding of v23 Direction A, and
it is exactly the trap the methodology was built to catch.

Two event-clustered statistics give OPPOSITE verdicts on the same data:

1. **The LOCKED statistic** (resample whole events, POOL all their fills, take the
   pooled mean = the documented behavior of `cluster_bootstrap_mean_ci`): WTA-NO
   TRAIN **-1.42pp**, OOS **-1.59pp**, CI straddles zero on both. This is the gate.
   It is fill-weighted: an event with 2658 fills counts 2658x an event with 11.

2. **An alternative unweighted-event-mean bootstrap** (resample events, statistic =
   the mean of per-event mean nets; this is NOT the locked callable and is reported
   as a robustness note only): WTA-NO TRAIN **+6.56pp** CI [+4.32, +8.69], OOS
   **+5.05pp** CI [+1.91, +8.07], EXCLUDES zero under both fee modes. ATP-NO
   similarly +5 to +7pp excluding zero.

Why they disagree (verified): `corr(event_nfills, event_mean) = -0.153`. Heavily
traded WTA matches are systematically NO-maker LOSERS. Per-EVENT P(result=no) =
83.9% (the unweighted underdog-NO win rate) but per-FILL P(result=no) = 75.7%:
the matches where the favorite wins (the NO maker loses) attract far more fill
volume. A resting NO maker fills MUCH more on the books that go against it.

The fill-weighted number (-1.4pp) is the one a real maker bot experiences, because
a bot fills more on the toxic, heavily-traded-against books. The +6.6pp event-mean
is an equal-weight-per-match abstraction no bot can realize. The lock binds the
fill-weighted statistic, and it is right to: this is the SAME volume-/adverse-
selection mechanism that left v1 at break-even live (75-76% live win rate ==
price-implied breakeven). The event-weighted +6.6pp is, in effect, the v18
"idealized" upper bound; the realized, fill-weighted truth straddles zero / is
mildly negative.

This also resolves the v10a-era +3.66pp/+3.27pp WTA "PERSIST" number: that earlier
sweep used a DIFFERENT band ([0.30,0.70] maker-side, combined YES+NO) and a
different fee, and it equal-weighted per event. The v23 locked, fill-weighted,
moderate-NO-band number does not reproduce a clean edge.

---

## 5. F11 status (realized fills vs new-bid capture)

Even the favorable event-weighted reading would be a Becker realized-fill UPPER
BOUND, not proof a NEW resting NO bid captures it. Becker has no orderbook at
trade time (F11, confirmed in the lock Section 1); these are the fills incumbent
makers GOT. But the question is now moot: the binding fill-weighted gate FAILS at
the screen, so there is no survivor to send to a forward shadow. F11 did not even
get the chance to bite, because the realized fills themselves do not show a
zero-excluding edge under the locked statistic.

---

## 6. Kill (no third bite)

Per the locked kill rule: WTA-NO fails A-2/A-3/A-4, so Direction A is KILLED at the
Becker screen. The ATP-NO diagnostic also fails and cannot rescue it. No criterion
re-tuning, no band re-scanning, no re-pooling. This NULL is the expected outcome
given the honest ~40% prior. Direction A ends here.

Honest prior was ~40%; outcome NULL. Consistent with the kill-early principle.
