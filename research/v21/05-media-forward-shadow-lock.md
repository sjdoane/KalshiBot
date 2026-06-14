# v21 Candidate A (Media) forward shadow: pre-registration + Phase-1.5 KILL

**Date:** 2026-06-13
**Outcome:** KILLED at the Phase-1.5 live-coverage gate, BEFORE any collector
was deployed. The frozen Media cell has aged out of the live 2026 universe; a
forward re-screen cannot satisfy its own pre-registered diversity floor and
would, if forced, overfit a single surviving series. Details in section 4.

This document is the complete honest record: the trigger (1), the corrected
forward design that WOULD have run (2), the coverage gate that had to pass first
(3), the gate result and kill (4), and the revival conditions (5). It mirrors
the discipline of `00-methodology-lock.md` (criteria locked before data) and the
read-only rigor of the Candidate C ladder scan.

## 1. Trigger

The 2026-06-13 accurate-fee re-adjudication found v21 Candidate A's Media cell
(`media_040_060`, maker band [0.40,0.60)) had its statistical gate S-A1a flip
under correct fees. The original screen (`04-candidate-a-null.md`) subtracted the
MODELED maker fee `ceil(1.75*P*(1-P))` cents on every Media trade
(`becker_screen.py:135`), but Media series are all `ALL_OTHER` = ZERO maker fee
in `research/v22/fee_table.json`. Adding back the flat ~1.0pp over-charge moves
Media from +2.06pp, event-CI [-0.28,+4.52] (S-A1a FAIL) to **+3.06pp, CI
[+0.72,+5.52] (S-A1a PASS)**.

But Media was killed on TWO independent gates, and only S-A1a is fee-sensitive.
**S-A1c (>= 200 distinct events AND >= 30 distinct prefixes) remained binding
and is fee-immune** (recency had 84 events / 36 prefixes). So a fee fix alone
does NOT revive Media; the only legitimate path is to forward-accumulate fresh
events to clear S-A1c, and to capture the live orderbook to resolve F11 (the
Becker dataset has no orderbook bid/ask at trade time; settled-market books are
unrecoverable). This document pre-registered that forward test.

## 2. The corrected forward design (what would have run)

Incorporates the 2026-06-13 methodology-critic must-fixes (the first draft of
this lock used a 3x/day, top-of-book-only design that could not support its own
F11 gate; corrected below).

- **Discovery (cheap, fast):** query `/markets?series_ticker=PREFIX&status=open`
  for each of the 50 frozen Media allowlist prefixes (NOT a 2M-market paginate),
  keep markets mid-band (top-of-book YES in [0.40,0.60)).
- **F11 capture (live-only, fine cadence):** poll `/markets/{t}/orderbook` for
  the in-band set every ~10 minutes (the original `00-methodology-lock.md`
  forward shadow specified 5-min; a 3x/day snapshot is 8h stale vs fills and
  cannot establish fillability, critic C2), recording BOTH-sides best bid/ask
  AND maker-side resting depth (depth_ahead), so the re-screen can apply the
  locked depth_ahead+1 fill rule rather than bare price reachability (critic C3).
  Read-only; never places orders. Book snapshots to `data/v21/media_shadow/`
  (gitignored, like the v16 shadow logger).
- **Edge + events (retrospective, no collector needed):** at the single eval
  point, fetch each in-band market's full trade tape + settlement (recoverable
  later) and compute net-excess EXACTLY as `becker_screen.py` (maker side =
  non-taker side; `maker_won = (taker_side != result)`; `net_excess = maker_won
  - maker_price - fee`) but net of ACCURATE fees (Media = zero; re-verify against
  a fee table extended to the eval date, FAIL CLOSED if no dated row matches,
  never assume zero, critic C1). Event-population membership = in-band TRADE
  PRINTS (not quote-in-band-at-snapshot, critic H2). Deterministic ORDER BY
  trade_id so rng_seed=42 pins one realization (critic L1).
- **Gates (single pre-committed evaluation point; interim reads may KILL on a
  sign flip but may never PASS, critic H3):**
  - G1 = forward S-A1a: combined-side net > 0 AND **market-day**-cluster
    bootstrap 95% CI lower > 0 (market-day, matching the original forward gate
    G-A2c, not event_ticker, critic H1; n=5000, ci=0.95, rng_seed=42).
  - G2 = forward S-A1c: >= 200 distinct events AND >= 30 distinct prefixes.
  - G3 = F11: depth_ahead+1 fill rule against the captured books for >= 60% of
    edge-contributing event-fills.
  - All three required. Pass -> paper/shadow maker probe (record-only, NOT live
    capital). No criterion re-tuning, no band/allowlist widening, Media only
    (Entertainment +0.20pp and Other -0.79pp did not flip on fees).
- **Overfitting guards:** frozen cell (no re-tuning); time-OOS forward data
  (note: OOS in time only, the cell is a Round 15b survivor, so G1 is a
  pre-registered confirmation of ONE pre-selected cell, not selection-free
  discovery, critic M3); event/market-day clustering (never trade-level, the
  original kill's lesson); analysis code locked before data.

## 3. Phase-1.5 live-coverage gate (must pass before deploying)

`scripts/v21/media_coverage_check.py` (read-only). The forward test can only
clear S-A1c if the frozen 50-prefix allowlist still has a live, DIVERSE 2026
universe. The >= 30-distinct-prefix floor is the binding, time-INDEPENDENT gate:
only prefixes with live in-band flow can ever contribute an in-band event, so
`max reachable prefixes = (allowlist prefixes with in-band flow now)`. If that is
below 30, no amount of collection time can satisfy S-A1c.

## 4. Gate result and VERDICT (2026-06-13)

`media_coverage_check.py` on the live prod API:

- allowlist prefixes: 50 | **alive (>0 open markets): 5** | **with in-band flow: 2**
- open Media markets: 92 | in-band [0.40,0.60) now: 11 | distinct in-band events now: 3
- in-band prefixes: KXVANCEMENTION (10), KXRANKLISTGOOGLESEARCHTOP5 (1). The
  other 48 prefixes are dead or out-of-band (mostly 2024-election-cycle mention
  / ranking series: KXKAMALAMENTION, KXAPRPOTUS, KXSNLMENTION, KXEARNINGSMENTION
  NVDA, etc.).

**VERDICT: KILL at Phase-1.5.** Max reachable distinct prefixes = 2, vs the
locked S-A1c floor of >= 30. The diversity floor is **structurally unreachable
regardless of collection duration**, so the forward re-screen can never pass its
own pre-registered gate. Building a 120-day collector would be knowingly futile,
and any "edge" measured on a sample dominated by one surviving series
(KXVANCEMENTION) would be **overfit by construction** (a single-series result is
exactly what the diversity floor, and the original kill's trade-level-CI lesson,
exist to prevent).

Interpretation (honest): the fee correction flipped Media's *statistical* gate on
*historical* data, but the cell's defining ecosystem was the transient 2024
-election-cycle mention/ranking-market universe, which has largely aged out. The
edge, even if it was real in 2024-25, is **not forward-deployable** because its
markets no longer list. This is consistent with, not contradicted by, the fee
finding: "passes a historical screen with corrected fees" is not "a live
edge", and Phase-1.5 is precisely the check that separates them.

No capital, no orders, no scheduled task registered. Cost: a few read-only API
calls.

## 5. Revival conditions

Do NOT revive on a fee argument alone. Revive ONLY if a future re-run of
`scripts/v21/media_coverage_check.py` shows **>= 30 allowlist prefixes with live
in-band flow** (the S-A1c diversity floor becomes reachable). Only then deploy
the section-2 design (per-prefix discovery + 5-10 min orderbook-depth poll for
F11; NOT the superseded 3x/day top-of-book version). Even then, a passed
re-screen is "passes its own statistical + F11 gate", and live capital still
requires the record-only paper probe first.
