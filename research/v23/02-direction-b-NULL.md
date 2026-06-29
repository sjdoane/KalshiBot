# v23 Direction B: NULL at the Becker screen (all four sub-cells fail)

**Date:** 2026-06-28
**Status:** KILLED at the Becker screen per the locked kill rule. NULL written.
No forward work. No re-tuning, no re-banding, no re-pooling (no pooling the
crypto sub-cells, no re-surfacing Other on a trade-level statistic).

Inputs: the locked criteria in `research/v23/00-methodology-lock.md` plus the
Phase-1 methodology-critic amendments (AMEND-1 through AMEND-9). Inference =
`src/kalshi_bot/analysis/bootstrap.py::cluster_bootstrap_mean_ci(values,
cluster_ids, n_resamples=5000, ci=0.95, rng_seed=42)`, cluster unit =
`event_ticker`, post-October-2024 only, combined-side (YES-maker and NO-maker
fills pooled), net-of-fee under BOTH fee modes. Raw machine output:
`research/v23/01-direction-b-results.json`.

## Verdict per sub-cell (each tested independently, never pooled)

| Sub-cell | Band | n events (tr/oos) | TRAIN CI (worst-fee) | OOS CI (worst-fee) | Fails |
|---|---|---|---|---|---|
| KXBTCD | [0.30,0.70) | 3796 / 1490 | [+0.55,+1.03]pp | [-0.35,+0.53]pp | B-4 (OOS straddles 0) |
| KXETHD | [0.30,0.70) | 3241 / 1454 | [+1.85,+3.15]pp | [-0.10,+1.45]pp | B-4, B-5 |
| KXBTC range | [0.30,0.70) | 3765 / 1485 | [+0.84,+1.97]pp | [-0.24,+1.19]pp | B-4, B-5 |
| OTHER (v21 allowlist) | [0.60,0.80) | 152 / 183 | [-3.19,+5.49]pp | [-4.36,+10.48]pp | B-2, B-3 (even zero-fee) |

## What killed each cell

**The three crypto cells fail on B-4 (the worst-case fee), exactly as AMEND-2
predicted.** Under the dated-zero-fee mode (mode a) all three crypto cells PASS
B-2/B-3: both windows' cluster-CIs exclude zero. But the binding gate requires
the CI to exclude zero under BOTH fee modes, and per AMEND-1 + the v22 fee table,
crypto daily/range are NOT in any fee row -> mode (a) = zero, so the only
discriminating check is the worst-case `ceil(1.75*P*(1-P))` fee. Across the
[0.30,0.70] band that worst-case fee is a flat 1 cent (the quadratic peaks at
0.4375c at P=0.5 and is below 1c everywhere in-band), so mode (b) is a uniform
1pp haircut. That haircut pushes every crypto OOS cluster-CI lower bound below
zero:

- KXBTCD OOS: zero-fee [+0.65,+1.53]pp -> worst-fee [-0.35,+0.53]pp.
- KXETHD OOS: zero-fee [+0.90,+2.45]pp -> worst-fee [-0.10,+1.45]pp.
- KXBTC range OOS: zero-fee [+0.76,+2.19]pp -> worst-fee [-0.24,+1.19]pp.

This is the honest reading the lock was built to enforce: the Becker fills that
show a positive crypto OOS edge are what HAPPENED to incumbent makers, many of
whom paid zero fee. A NEW retail entrant must be priced at the worst-case fee,
and net of a 1pp fee the crypto OOS edge is statistically indistinguishable from
zero on all three series. KXBTCD additionally has the smallest raw OOS edge
(zero-fee OOS cluster-mean +1.08pp), so it is the most fee-fragile. KXETHD and
KXBTC range also independently fail the B-5 decay guard (OOS worst-fee event-mean
< 50% of train worst-fee event-mean), a second independent failure.

**The Other cell fails B-2 AND B-3 even under the favorable zero-fee mode,
reproducing the v21 kill.** The frozen v21 outcome-blind allowlist (369 prefixes,
[0.60,0.80) band, 60-day horizon cap, close-time-in-window) at the event-cluster
level gives TRAIN cluster-CI [-2.19,+6.49]pp and OOS [-3.36,+11.48]pp; both
straddle zero before any fee is applied. The point estimates are positive
(train +2.24pp, OOS +4.35pp) but the event-cluster CI is wide because the edge is
carried by a small number of correlated events, not a broad diversified base.
This is the exact lesson of v21: the prior +2.40pp Other number was a
trade-level-CI artifact over correlated trades; at the event-cluster level the
sign is not distinguishable from zero. Per the kill rule it is NOT rescued by any
trade-level statistic. Concentration (B-6) and min-n (B-1) both pass, but they
cannot rescue a sign failure.

## Gate-by-gate (binding cut-offs from the lock)

| Gate | KXBTCD | KXETHD | KXBTC range | OTHER |
|---|---|---|---|---|
| B-1 min-n >=60 both | PASS | PASS | PASS | PASS |
| B-2/B-3 zero-fee CI excl 0 | PASS | PASS | PASS | FAIL |
| B-4 worst-fee CI excl 0 | FAIL | FAIL | FAIL | FAIL |
| B-5 decay (OOS >= 50% train, >0) | PASS | FAIL | FAIL | PASS |
| B-6 concentration <50% | PASS | PASS | PASS | PASS |
| Overall | FAIL | FAIL | FAIL | FAIL |

## Honesty notes (F11, capacity, how the data was queried)

- **F11 (the load-bearing caveat).** Even the cells that pass under zero-fee are
  NOT a live edge. The Becker trades table carries no orderbook bid/ask at trade
  time; a Becker pass shows an edge EXISTED in realized incumbent fills, not that
  a NEW resting maker bid would CAPTURE it. Crypto is the acute case (AMEND-5):
  pro HFT makers maintain continuous two-sided crypto quotes against spot, so a
  new retail bid sits at the back of the queue and fills mostly on adverse moves.
  The forward shadow (not run here, because nothing survived the screen) was the
  only F11-free adjudicator. Nothing earned one.
- **Capacity (~$200 bankroll).** Moot given the kill, but for the record: even
  the zero-fee crypto edges are sub-2pp on contracts priced 30-70c, so per-bet
  expected net is fractions of a cent on a ~$1 bet; a $200 bankroll cannot size
  into a 1pp edge meaningfully, and the worst-case-fee net is ~zero anyway.
- **AMEND-1 honored.** Confirmed crypto daily/range are absent from
  `research/v22/fee_table.json` and fall through to ALL_OTHER = zero; mode (a) =
  zero for all four sub-cells, so the worst-case mode (b) is the sole
  discriminating fee check. No "dated crypto fee" was reported because none
  exists.
- **AMEND-2 honored.** The worst-case in-band fee is a flat 1 cent for both the
  crypto [0.30,0.70] and the Other [0.60,0.80) bands (per the ceil). It was the
  binding kill for crypto exactly as flagged.
- **AMEND-3 honored.** B-5 evaluated on the worst-fee event means and the raw
  means + CIs are in the JSON; the 50% ratio is treated as a documented
  heuristic, not the sole discriminator (crypto already dies on B-4 regardless).
- **AMEND-6 honored.** Concentration family = the allowlist prefix
  (`regexp_extract(event_ticker,'^([A-Z0-9]+)',1)`) for Other; for crypto it is
  the event_ticker (naturally diffuse, largest family < 0.6% of abs P&L).
- **Query method.** DuckDB 1.5.3 in the project `.venv` (pandas is broken there;
  not imported). event_ticker derived as `regexp_replace(ticker,'-[^-]*$','')`.
  Session TimeZone set to UTC so the calendar-date split boundaries are
  deterministic. Powering reproduced the lock's pre-data counts within rounding
  (KXBTCD train 3800 vs claimed 3811, etc.; totals 5417/5016/5391 matched
  exactly). Settlement join uses `markets.result` on the SAME ticker that was
  filled (result in {yes,no}; '' excluded), not an event-level OR (AMEND-9).
- **F11 status of this result:** the headline numbers rely on realized fills that
  a new maker bid may not capture; this is a NECESSARY screen, not a sufficient
  go-live. It does not matter here because nothing passed.

## Kill

All four Direction B sub-cells fail. Direction B is KILLED at the Becker screen.
NULL filed. No third bite: no criterion re-tuning, no band re-scanning, no
re-pooling, no re-surfacing Other on a trade-level statistic. The crypto result
is the strongest-prior cell in the project and it dies on the worst-case fee, not
on a coding artifact: the zero-fee edge is real-but-small and the fee eats it.
This is the expected, acceptable kill-early outcome (lock Section 6: crypto
strongest prior but with documented OOS decay; Other LOW prior, already killed in
v21).

*Em-dash and en-dash audit: verified clean after write.*
