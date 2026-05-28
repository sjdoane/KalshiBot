# v11 Methodology Lock v3 Amendment: Granger-First Scope

**Round:** 16 (v11)
**Date:** 2026-05-27
**Supersedes for Phase 2:** Methodology lock v2 Sections 3 to 5, 8.
**Inherits unchanged:** Lock v2 Sections 1, 2, 6, 7, 9 (Track 2 already SHIPPED).

This amendment binds v11's revised Phase 2 scope after the operator
authorized Option 1 (Granger-first) following the Phase 2 Step 1a
finding that Becker MARKETS lacks intraday orderbook snapshots (F11
data-layer phantom; F4 Option B infeasible).

The strategy P&L backtest (originally lock v2 Sections 3 to 5 G_F1 to
G_F11 with execution model) is DEFERRED to a future v12 session. v11
Track 1 now answers only the causality question: does sportsbook
moneyline movement lead Kalshi trade-print movement in the T-6h to
T-1h pre-close window?

## What v3 changes from v2

| Component | v2 lock | v3 amendment |
|---|---|---|
| Phase 2 goal | Strategy P&L backtest | Granger F-test only (lead-lag) |
| Execution model | Trade-print mid + DETERMINISTIC_HAIRCUT | Not applicable (no trades) |
| Pilot-A use | Compute haircut, X, Y | Compute X (sportsbook move) and Y (Kalshi move) only |
| Pilot-B use | Compute sigma | Not used in v11; reserved for v12 |
| G_F1 to G_F11 | All 11 binding gates | NOT FIRED in v11 |
| New gates | n/a | G_GRANGER (per-sport F-test) |
| Verdict | SHIP / PARTIAL / NULL | GRANGER-CONFIRMED / GRANGER-PARTIAL / NULL |

## v3 Granger scope

### Universe

Same per-sport median split as lock v2 Section 2 (already computed in
Phase 2 Step 1a). Granger test runs on the validation split only;
pilots used only for X and Y derivation.

### The-odds-api pull scope

Operator purchased the $30/20k Starter tier on 2026-05-27. Env var:
`THE_ODDS_API_KEY` (overwritten in place; not THE_ODDS_API_STARTER_KEY).

Granger sample size:
- Target n=500 to n=660 events post-sport stratification (must stay
  under 20,000-credit cap with 10% buffer)
- 3 sports stratified equally: ~170 events per sport
- 3 snapshots per event (T-6h, T-3h, T-1h)
- 10 credits per snapshot per region (us-only h2h) = 30 credits per event
- Total: 660 events * 30 credits = 19,800 credits, with 200 credit buffer

If the operator's actual purchased credit pool differs from 20k (e.g.,
some plans bundle bonus credits), the script must check
`x-requests-remaining` header after the first call and abort early if
the budget is tighter than expected.

### Sample selection

For each sport in {KXMLBGAME, KXNBAGAME, KXNFLGAME}:
1. From the validation split of that sport, deterministically sample
   220 events stratified by month (so the sample spans the full
   in-season range).
2. If a sport has fewer than 220 validation events, take all of them
   and rebalance the other sports up to fill the 660 total.

KXMLBGAME has the most validation events; NFL has the fewest (per
A1 numbers).

### Granger F-test design

**Variables (per event):**
- `delta_sportsbook` = (implied_prob at T-3h) minus (implied_prob at T-6h)
  using the median across available bookmakers per game
- `delta_kalshi_pre` = (Kalshi VWAP at T-3h) minus (Kalshi VWAP at T-6h)
- `delta_kalshi_post` = (Kalshi VWAP at T-1h) minus (Kalshi VWAP at T-3h)

**Granger F-test specification:**

Hypothesis H0: sportsbook movement in T-6h to T-3h does NOT predict
Kalshi movement in T-3h to T-1h, given Kalshi's own T-6h to T-3h
movement.

Restricted model:
  `delta_kalshi_post = alpha + beta * delta_kalshi_pre + epsilon`

Unrestricted model:
  `delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + epsilon`

F-statistic on the gamma=0 restriction; p-value from F(1, n-3)
distribution.

### Pre-registered Granger gate

**G_GRANGER (per-sport, Bonferroni-corrected):**

For each sport contributing >= 50 events post-join: the per-sport F-test
p-value must be <= 0.05 / 3 = 0.01667 (Bonferroni for 3 sport tests).

Additionally, the gamma coefficient (the cross-venue lead-lag magnitude)
must be POSITIVE in direction: sportsbook moves UP should lead Kalshi
moves UP. Negative gamma at p <= 0.01667 is a SEPARATE finding
(reverse lead-lag) and does NOT trigger GRANGER-CONFIRMED.

### Verdict mapping

- **GRANGER-CONFIRMED:** all 3 sport-strata clear G_GRANGER with positive
  gamma. Recommend v12 follow-up for strategy P&L test with proper
  execution-model design (F4 Option A or live-probe). v11 Track 1
  closes GRANGER-CONFIRMED, no capital.
- **GRANGER-PARTIAL:** 2 of 3 sport-strata clear G_GRANGER with positive
  gamma, OR 3 of 3 clear with at least one negative gamma. Recommend
  v12 follow-up scoped to the passing sport(s).
- **NULL:** 0 or 1 sport-strata clear G_GRANGER. Close v11 Track 1.

### Anti-pattern preserved from v2 Section 7

a) No post-settlement price proxies (F7)
b) Trade-print as feature is OK; trade-print as orderbook ASK
   baseline still banned (v7-B phantom defense; not applicable here
   since v3 has no execution model)
c) No prior-round numerical threshold borrows; the 0.05 alpha and
   Bonferroni-corrected 0.01667 are derived from first principles
   (standard hypothesis test convention; 3 simultaneous tests)
d) X and Y thresholds computed on Pilot-A only; data leak prevention
   via per-sport median split
e) No tuning of (X, Y) or the F-test specification after seeing
   validation data
f) Block bootstrap of F-statistic via 1-day blocks (NOT row-bootstrap)
   when constructing the F-test CI

### Phase 2 sequencing (revised)

Step 1b (in-session): pull historical odds for 660 validation events
using THE_ODDS_API_KEY. Credit budget 19,800 of 20,000.

Step 2 (in-session): build joint dataset (Kalshi trade-print VWAPs at
T-6h, T-3h, T-1h JOINED to sportsbook implied probabilities at same
times). Compute per-sport F-test. Apply G_GRANGER. Report verdict.

Step 3-5 from lock v2: SKIPPED in v11 (strategy P&L test deferred to
v12).

## What this amendment does NOT change

- Lock v2 Section 1 (universe) holds
- Lock v2 Section 2 (per-sport median split) holds
- Lock v2 Section 6 (Kalshi fee formula) holds (not used in v11 since
  no P&L; preserved for v12)
- Lock v2 Section 7 (anti-pattern bans) holds (preserved for v12)
- Lock v2 Section 9 (Track 2 spec) already SHIPPED; no change

## Track 2 status

Already SHIPPED. v11 Track 2 verdict: SHIPPED. See
research/v11/track2-wiring-report.md.

## Track 1 status

Phase 2 Step 1a complete. Step 1b begins now.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or
U+2013 throughout.*
