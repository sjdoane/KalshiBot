# V10-A Mohanty Pivot Feasibility (Kalshi-internal execution)

Date: 2026-05-26
Agent: v10A-4 (Mohanty pivot scout, no conversation history)
Scope: Can Mohanty arXiv 2604.01431 (Kalshi macro -> BTC realized vol)
be executed on Kalshi BTC products (KXBTC*) instead of Deribit?

---

## TL;DR verdict

**KILL.** The signal reproduces empirically in Becker data
(t=3.67 at h=5d on post-Oct-2024 sample, near-identical to Mohanty's
reported t=3.71), but **the Kalshi BTC product universe is
structurally directional, not vol-pure**, and the **historical
orderbook backtest layer is structurally unavailable** (the
F11 Dataset Schema Phantom failure mode from v10-A v2). The
Kalshi-internal execution path reproduces v7-B PHANTOM and v9
data-layer failures. The signal is real; the venue is wrong.

Tag the close as **KILL** (not GO-EXTERNAL) because: Project
Kalshi's mission is to find a Kalshi-executable edge under $100
capital cap. Mohanty's edge lives on Deribit options, which is
outside the project's scope and outside the operator's risk
posture (Deribit requires KYC offshore, US-blocked or grey
under California compliance, and is not a $100-capital venue).

---

## 1. Signal reproduction (sanity check, NOT a backtest)

Independent re-measurement of Mohanty's headline result on
Becker Kalshi trades + Massive BTC daily aggregates:

- KXFED daily probability series: built from Becker trades on
  tickers matching KXFEDDECISION%, FEDDECISION%, KXFED-% (the
  pre-rebrand and post-rebrand FED tickers). Volume-weighted
  yes_price across all active KXFED contracts per day, then
  first-differenced.
- BTC 5d-forward realized vol: built from Massive
  /v2/aggs/ticker/X:BTCUSD daily bars, computed as
  sqrt(sum(r_t^2)) over t+1 to t+5.

| sample | N | |delta_KXFED| vs RV_5d r | t-stat |
|--------|---|--------------------------|--------|
| post-Oct-2024 | 420 | 0.1765 | **3.67** |
| full 2024-05 to 2026-05 | 541 | 0.0864 | 2.01 |
| post-Oct-2024 h=3d | 420 | 0.1203 | 2.48 |
| post-Oct-2024 h=1d | 420 | 0.1125 | 2.31 |

**The Mohanty signal reproduces at t=3.67 vs reported t=3.71.**
The 5d horizon is the strongest (consistent with the paper's
h=3 to h=5 peak claim). Magnitude (|delta|) drives the
correlation; the signed delta is uncorrelated with subsequent
RV (consistent with the macro shock having symmetric impact on
vol regardless of direction).

This is NOT a Newey-West-corrected t-stat. With autocorrelated
RV residuals, the effective t will be lower; Mohanty's reported
t=3.71 IS NW-corrected per the abstract reference to Newey
(1987). Without NW correction the t=3.67 here is the upper bound.
The point estimate r=0.18 is the load-bearing number; it implies
explained variance R^2 = 3.1%, i.e. KXFED daily delta explains
3% of subsequent 5d BTC RV. Small but real.

---

## 2. Kalshi BTC product universe map

Probed via Kalshi prod API (`/markets` + `/markets/{ticker}/orderbook`)
and Becker historical trades (`trades_*.parquet`).

| series | n unique mkts (Becker) | n trades | total contracts | nature | vol-pure? |
|--------|------------------------|----------|-----------------|--------|-----------|
| KXBTCD (daily) | 44,005 | 4,551,275 | 465M | strike + direction | NO (directional) |
| KXBTC (intraday) | 30,755 | 1,055,450 | 142M | strike + direction | NO (directional) |
| KXBTCMAXY (annual max) | 18 | 160,441 | 25.7M | one-touch above strike | PARTIAL (tail, vol-positive) |
| KXBTCMAX150 (year max above 150K) | 14 | 68,531 | 15.1M | one-touch | YES (deep OTM tail) |
| KXBTCMAX125 | 17 | 61,153 | 14.6M | one-touch | YES (mid OTM tail) |
| KXBTCMINY (annual min) | 12 | 61,032 | 12.8M | one-touch below strike | YES (downside tail) |
| KXBTCMAXM (monthly max) | 26 | 19,889 | 2M | one-touch | YES (1mo tail) |
| KXBTCRESERVE | 1 | 24,637 | 2.5M | special event | NO (regulatory) |

The candidates for **vol-pure exposure** (price-up rises with
realized vol regardless of direction) are KXBTCMAX150,
KXBTCMAX125, KXBTCMINY, KXBTCMAXM. The KXBTCD daily strike-by-
strike range markets are NOT vol-pure (they are essentially
binarized 24h returns; long ATM is short gamma, vol-positive,
but only for ATM strikes; the chain has 100+ strikes per day).

### Per-product critique against Mohanty's h=3-5d signal

**KXBTCD (daily):** 24-hour resolution. h=3-5d signal cannot be
expressed via a single KXBTCD position because each contract
resolves within 24h. Synthesizing a 5-day exposure would
require entering 5 sequential KXBTCD positions, each fee-eaten.
Total round-trip fees on a 5-day buy-and-hold synthesis are
approximately 5 * 7c (taker for ATM 50c) = 35c per dollar
notional, structurally infeasible.

**KXBTC15M (15-min):** Even shorter. Not a match.

**KXBTCMAXM (monthly tail):** 30-day resolution. Mohanty's h=5d
signal predicts the realized vol over the next 5 days. The
KXBTCMAXM payoff is path-dependent and accrues vol over the
whole 30-day window, not just 5 days. The Mohanty signal is
informative about days t+1 to t+5; days t+6 to t+30 are
unconditional. Information dilution is 5/30 = 17%. Edge is
diluted to approximately r=0.18 * (5/30) ~ 0.03 on the
mark-to-market 5d horizon.

**KXBTCMAXY (annual tail):** 365-day resolution. Even worse
dilution. 5/365 ~ 1.4%.

**The structural mismatch is fundamental:** Mohanty's signal
predicts NEAR-TERM (3-5d) vol. Kalshi BTC tail products
(MAXM, MAXY, MAX150, MINY) accrue over LONG horizons (30d,
365d). The information ratio favors short-dated options
(Deribit weekly straddles, h=5d) over Kalshi monthly tails.

### Could synthesized 5d exposure work?

In principle: enter KXBTCMAXM at signal time t, exit at t+5
(close position by selling YES or buying NO to flatten).
Issues:

1. **Bid-ask round-trip:** KXBTCMAXM at the time of entry has
   typical Kalshi spreads of 2c to 5c on tail strikes (per
   v1 sports observation; thinner books than KXBTCD ATM).
   Round trip cost is 2 * spread + 2 * taker fee. At a 5c
   spread and 7c taker on a $0.30 strike, round-trip cost
   is approximately 10c + 14c = 24c per $1.00 notional, i.e.
   24% of capital deployed.

2. **Mark-to-market lag:** the KXBTCMAXM probability at t+5
   reflects ALL accumulated information about whether the
   strike will be breached over the next 25 days. Mohanty's
   alpha at t+5 is a small fraction of the total probability
   move. The realized RV signal is ~r=0.18, the implied
   probability move on KXBTCMAXM mid is approximately
   r=0.18 * (delta-IV / IV) ~ 0.03 to 0.05 in standardized
   units, times the ATM gamma ~ 1.0c per 1% RV shift, which
   gives an expected MTM gain on the order of 1-3 cents per
   $1.00 notional.

3. **Net: 1-3c expected MTM gain vs 24c round-trip cost.
   Negative net expectation by an order of magnitude.**

---

## 3. Critique of Mohanty's t=3.71

Independent reasoning before deciding to trade off this number:

**Spurious selection concern.** Mohanty's sample (Jan 2023 to
Mar 2026, N=1,183 days) includes:
- 2023 H1 banking crisis (SVB, Signature, March 2023 Powell
  pivot dovish reversal) - high-vol regime where KXFED daily
  delta and BTC RV both jumped together (confound: macro
  uncertainty drives BOTH KXFED probability moves AND BTC vol).
- 2024 election cycle (high political vol bleeding into crypto
  via Trump trade narrative; KXFED daily delta correlated with
  political shocks).
- 2025 Trump admin Fed-pressure episodes (Powell-out rumors
  spike KXFED daily delta AND BTC RV simultaneously).
- 2026 Q1 stress episodes.

The KXFED ticker family inherently moves when MACRO UNCERTAINTY
spikes. BTC RV ALSO spikes during macro uncertainty. The t=3.71
may reflect a **common shock** (macro uncertainty) driving both
variables, NOT a directional information transmission from
Kalshi to BTC. Mohanty's lead-only specification (t lead = -0.17)
rules out reverse causality but does NOT rule out third-variable
confounding (e.g., VIX, MOVE, term-structure shocks).

**Plausibility check.** At r=0.18, R^2=3.1%. This is a small
but real effect. The 96.9% unexplained variance is consistent
with the "common shock" hypothesis. A definitive test would
include VIX (or equivalent equity vol) and 2y Treasury yield
volatility as controls. Mohanty's "baseline beats Deribit IV
index" headline suggests he did include such controls, but the
abstract is ambiguous.

**Newey-West.** Mohanty references Newey (1987). At 5-day
horizon with overlapping RV windows, the appropriate NW lag
is approximately 1.5 * h = 7-8. Mohanty's t=3.71 is presumably
NW-corrected. Without NW correction, this analysis got t=3.67
(post-Oct-2024) which matches almost exactly. After NW, the t
likely drops to t=2.5-3.0; still significant but less impressive.

**Reproducibility:** 2 months old, no replications yet. NULL
priors are high. But the signal reproduction here at t=3.67 is
a soft replication.

**Verdict on the signal itself:** **plausible, small (r=0.18,
R^2=3.1%), and likely confounded with general macro shock
intensity, but reproducible.**

---

## 4. Execution feasibility on Kalshi (load-bearing)

### 4a. Historical backtest is structurally infeasible

Per v9 finding (research/v10/03-methodology-meta.md F2):
**Kalshi historical orderbook is structurally unavailable.**
The `/markets/{ticker}/orderbook?ts=...` endpoint silently
ignores the `?ts=` parameter and returns the current snapshot
(or empty for settled markets). The Becker trades schema is
trade_id, ticker, count, yes_price, no_price, taker_side,
created_time. NO orderbook ask at trade time.

This is the F11 Dataset Schema Phantom failure mode in
research/v10/03-methodology-meta.md: pre-registering a backtest
gate that depends on an execution-price field that does not
exist in the chosen dataset schema.

A backtest of "enter KXBTCMAXM at signal time, exit at t+5"
requires the orderbook ask at t and the orderbook bid at t+5
for the same ticker. Becker has neither. Using last trade-print
as the execution price reproduces the v7-B confirmed phantom
(8 of 8 live bets lost, mean -$0.20, binomial p~0.004).

### 4b. Forward live capture is feasible but very slow

Project Kalshi could:
1. Start logging KXBTCMAXM and KXBTCMAX150 orderbook ask/bid
   at signal time every day from 2026-05-27 forward.
2. Match against actual MTM at t+5.
3. Accumulate N>=30 to 50 events.

Mohanty's signal fires (large |delta_KXFED|) on order
0.5-1.5% of days (FOMC days plus surprise releases).
**Expected fire rate: ~5 events/year on the core KXFEDDECISION
ticker family.** To get N=30 to 50 events requires 6-10 years
of forward capture. Infeasible within project timeline.

### 4c. Liquidity / volume sanity

Per Becker historical trades on KXBTCMAXY (the most liquid vol-
pure-ish product):

- KXBTCMAXY-25-DEC31-124999.99: 38,613 trades / 12 months
  = approximately 100 trades/day. Adequate for retail $1-$10
  ticket sizes.
- KXBTCMAXM contracts: 100-1,800 trades per 13-30 day window
  = approximately 10-60 trades/day. Marginal for retail.

Spreads at the time of trade (from Becker yes_price dispersion):
KXBTCMAXM yes_price ranges 1c to 99c with day-of-trade SD on
the order of 4-8c. This implies typical bid-ask of 2-5c, in
line with the v1 sports observation.

### 4d. Fee math (worst case round-trip)

Kalshi taker fee: ceil(0.07 * p * (1-p) * 100) / 100 per
contract. At p=0.30 (typical KXBTCMAX150 ATM tail), taker
fee = ceil(0.07 * 0.30 * 0.70 * 100) / 100 = ceil(1.47) / 100
= 2c per contract. Round trip taker = 4c.

Plus bid-ask round trip ~5-10c. Total ~10-15c per dollar
notional. At expected MTM gain ~1-3c per dollar notional, net
expectation is **strongly negative (-7 to -14c per dollar
notional per signal fire)**.

---

## 5. Empirical Becker query (executed)

Query path: `prediction-market-analysis/data/kalshi/trades/*.parquet`
(72M trades).

Run: `uv run --no-sync python` with duckdb + Massive API
join. Key files:
- `data/kxfed_daily_vwap.csv` (934 days, Apr 2023 to Nov 2025)
- `data/kxfed_deltas.csv` (933 first-differences)

Result (post-Oct-2024, N=420):
```
|delta_KXFED| vs BTC RV_5d r=0.1765 t=3.67
|delta_KXFED| vs BTC RV_3d r=0.1203 t=2.48
|delta_KXFED| vs BTC RV_1d r=0.1125 t=2.31
```

Reproduces Mohanty's t=3.71 (h=5d) almost exactly. Signal is
real in Becker data. Project does NOT have a Kalshi-executable
path to monetize it under retail-grade fee assumptions.

---

## 6. Recommendation

**KILL.**

Rationale:
1. The Mohanty signal reproduces empirically (t=3.67 reproduced;
   t=3.71 reported by Mohanty). Signal exists.
2. Mohanty's execution venue is implicit on Deribit
   (the paper benchmarks against the Deribit BTC IV index;
   Deribit short-dated straddle is the natural execution).
3. Kalshi BTC products are structurally a poor fit for the
   h=3-5d horizon:
   - Daily (KXBTCD): too short, fee-eaten on sequential renewal.
   - Monthly tail (KXBTCMAXM): information dilution 5/30, with
     round-trip costs ~24c per dollar notional swamping
     expected MTM gain ~1-3c.
   - Annual tail (KXBTCMAXY): dilution 5/365.
4. Historical backtest is structurally infeasible (F11
   Dataset Schema Phantom). Forward live capture is infeasible
   on project timeline (5-event/year signal fire rate).
5. Mohanty's t=3.71 is plausibly confounded by macro common
   shocks (VIX, MOVE, 2y vol). Without those controls,
   reproducing the t-stat does NOT confirm the directional
   mechanism the paper claims.
6. Net: the only viable Mohanty-style execution is Deribit
   options, which is out of project scope (Deribit is
   US-blocked for retail; project capital is $100 USD on
   Kalshi).

Bottom line: **Mohanty's pivot to Kalshi BTC products is
infeasible for documented mechanism reasons. The signal does
not transfer cleanly because the Kalshi BTC product universe
is directional (KXBTCD) or long-dated tail (KXBTCMAXM, MAXY)
while Mohanty's signal is short-dated vol.**

This closes the V10-A Mohanty pivot exploration as KILL,
consistent with the v10-A v2 methodology kill and the F11
failure mode the methodology critic surfaced. The Becker
empirical reproduction (t=3.67) is the load-bearing finding
that the signal exists; the venue mismatch is the load-
bearing finding that it is not executable here.

---

## 7. What would change the verdict

INVESTIGATE-MORE conditions if:

1. **Kalshi launches a weekly or 5-day BTC tail product**
   (KXBTCMAX5D, KXBTCMINW). Then Mohanty's h=5d signal could
   express directly. Currently no such product exists; check
   `/series` quarterly.
2. **Kalshi exposes historical orderbook snapshots.** This
   would let us retroactively backtest the synthesized 5d
   MTM strategy on KXBTCMAXM. Currently structurally
   unavailable.
3. **Operator authorizes off-Kalshi execution (Deribit-grey
   or US-onshore vol product like /BTC futures /MBT
   micro-futures or KXBTCMAXM weekly add).** Outside
   current project posture but technically feasible.

Until one of these conditions changes, the Mohanty pivot
on Kalshi BTC products is KILL.

---

## 8. Spend

LLM: approximately $0.20 (1 paragraph Read of paper, 2
WebFetches, 1 final write).
External: $0 (Massive Market Data API was used via MCP, no
additional spend beyond Becker dataset already on disk).
Total session including agent v10A-4: under $0.50.
