# v25 Idea 1 PLAN CRITIC: AAA gas ladder taker (adversarial review)

**Date:** 2026-07-02. Role: adversarial plan critic under the v24 charter. Mandate: kill
the idea if it deserves killing, before any data is pulled. Inputs: 00-proposal.md, the
v24 handoff charter, the v24 meta-summary (the wall), 11-realized-vol-powerup-NULL.md
(the stale-spot lesson), scout-universe-scan.md, scout-data-sources.md.

**Verdict up front: PROCEED-WITH-AMENDMENTS, with the honest prior marked DOWN from 12%
to approximately 10%, sitting exactly on the charter's kill line. Two of the amendments
(A2 settlement-key audit, A5 power floor) are conditional kill switches: if either
cannot be satisfied, the idea dies before the data pull. The proposal's central escape
claim is partially false as written and must be corrected in the lock.**

---

## Attack 1: Is "no sharp reference exists" actually distinct from the weather NULL?

**Finding: the proposal's escape claim is FACTUALLY WRONG as stated, and this is the
single largest prior deflator.**

The proposal claims: "Every prior capture-phantom confirmation (crypto spot, sports
books, NWP consensus, SPX/VIX options) involved a sharp external reference the MM could
mechanically mirror." Read that list again. NWP consensus is IN it. The weather markets
had NO tradeable sharp reference either: there is no derivatives market on tomorrow's
Central Park high. The NWS/NBM consensus is a public MODEL, not a tradeable price, and
the market still priced it better than the retail naive model (2 to 6F off, station bias
and sigma both ruled out, doc referenced in the meta-summary). So "the settlement
variable is administered and non-tradeable" does NOT by itself escape the phantom. The
weather case proves the MM does the modeling work when the public model is good enough
and the market is salient enough. Gas had election-cycle salience (median 24k to 47k
contracts per settled market in the 2024 era) and still has real volume today (weekly
top strike 14k in 2 days per the scout). An MM that priced S&P same-day vol to within
2pp of a correct model (v24 doc 11) is not going to be structurally unable to run a
distributed-lag regression that appears in every energy-economics textbook.

**The honest residual distinction, which the proposal should have led with:** in
weather, the public frontier model (NWP/NBM ensemble consensus) is enormously
sophisticated and the retail model was strictly WORSE than it; the null mechanism was
"market is at the frontier, my model is below it." In gas, the public frontier for
forecasting the AAA level 1 to 4 weeks out is approximately: current AAA level plus an
asymmetric distributed lag on wholesale. That frontier is implementable by this project
in full. So the gas test genuinely asks a question the project has never tested:
"is the market at the public frontier on a sleepy administered series," rather than
"is my below-frontier model worse than the market" (which was already answered five to
seven times: yes). That is a real difference in test content, not marketing.

**Consequence for the prior.** The 12% stated prior implicitly credits the false
version of the escape claim. Deflate for: (a) weather precedent directly analogous on
the no-tradeable-reference axis; (b) demonstrated MM sophistication transfer
(index vol); (c) 2024-era volume implying attention. Inflate slightly for: (d) the
frontier-implementability point above, which is genuine and new; (e) the failure mode
here is benign (if the market is at the frontier, the model agrees with the market,
few fires, cheap clean null, no manufactured loss). Net: honest prior approximately
10%, not 12%. That is ON the charter's kill line, not clearly above it. The lock must
restate the prior at ~10% and must rewrite the escape argument to the frontier form.
Amendment A1.

## Attack 2: Signal size vs the fee + spread hurdle

**Finding: survivable in principle; the arithmetic does not kill it. But the lock must
derive the firing threshold from this arithmetic explicitly.**

The hurdle: worst-case taker fee ceil(7*P*(1-P)) = 2c at P=0.5, 1c at P=0.9, plus
spread haircut 1-3c weekly and 1-5c monthly. Call the all-in hurdle 3-5pp near the
money.

Can genuine probability divergences exceed that? Yes, structurally. The reason is that
probability is steep in drift when sigma is small. Weekly: strike spacing 2c, weekly
change sigma on the order of 2-3c (calm) to 5c+ (shock regime). At a near-money strike
the probability sensitivity is roughly phi(0)/sigma per cent of drift disagreement,
i.e. ~0.4/2.5 = 16pp of probability per cent of weekly drift disagreement. During a
pass-through episode (wholesale has moved 15-30c, retail has caught up only partially)
the mechanical drift prediction can differ from a no-drift view by 1-3c/week. That is
a 15-45pp divergence against a random walk, and even a market that prices HALF the
pass-through leaves a 7-20pp divergence. Monthly: 10c spacing, sigma perhaps 5-8c over
the horizon, similar steepness at 1c of monthly drift disagreement giving ~5-7pp. So
the geometry leaves room above the hurdle; this is unlike sports favorites where the
whole edge candidate was 1-2pp under a 2pp fee.

The catch, stated honestly: a large divergence vs the RANDOM WALK is not edge; edge
requires divergence vs the MARKET, and the market very likely prices at least the
direction of pass-through drift. The proposal's control handles the distinction
correctly. The amendment is procedural: the divergence firing threshold in the lock
must be DERIVED as hurdle (worst-case fee at the fill price band + measured median
spread of that series) plus a pre-stated margin, per band, not a single round number.
Amendment A5 ties this to power (below).

## Attack 3: Wayback as-of discipline (the stale-spot phantom vector)

**Finding: the proposal's plan contains a live fabricated-edge vector: interpolated
AAA inputs. This is EXACTLY the v24 stale-spot mechanism and must be excised, not
sensitivity-tested.**

The v24 realized-vol lesson in one line: a stale level input plus a moving driver
manufactures divergence, the divergence IS the staleness, and the fake edge flips sign
when the input is made as-of. Map it here: if the as-of AAA level is stale (a missing
Wayback day filled by interpolation or carry-forward) while wholesale has been ramping,
the model thinks retail still has catching-up to do that has in fact already happened,
diverges from the market (which sees the real current AAA number every morning), and
"wins" a fake fill. The worst Wayback gap cluster (2026-02-22 to 03-01, 8 of 9 days
missing) sits INSIDE the $2.83 to $4.07 run-up, i.e. the missing days concentrate
exactly where the model would fire hardest. This is attack surface 2 of the proposal's
own list, and it is real.

Note also that the proposal's control does NOT catch this artifact. The random-walk
control uses the SAME as-of AAA level, so a stale level distorts both models in the
same direction relative to the market; the pass-through model can then legitimately
beat the control on wholesale information while the market-beating component of its
P&L is pure staleness artifact. The gate (beat market AND beat control) passes on a
fabricated edge. The freshness rule is therefore load-bearing and cannot be replaced
by the control.

**Amendment A2 (hard, binding):**
1. Model INPUTS: backward-fill only, keyed on the page's own "Price as of" date, never
   interpolation (interpolation uses future snapshots; it is look-ahead by
   construction).
2. Firing eligibility: a simulated trade is only valid if the as-of AAA level available
   at the trade timestamp has staleness zero days (the morning print of the trade date,
   or the prior date for timestamps before ~03:30 ET publication). Trades on stale-input
   days are EXCLUDED, not filled in. Report the excluded-day count.
3. Settlement truth comes ONLY from Kalshi settlement records (market result field),
   never from reconstructed AAA values. The Wayback series is a model input, full stop.
4. Pre-lock settlement-key audit: on at least 20 settled KXAAAGASW/M markets, compare
   the Kalshi settled result against the reconstructed AAA value under BOTH day-key
   hypotheses (AAA print published the morning of close date D vs the morning of D-1).
   The close semantics (close 03:59Z day D = trading ends 11:59pm ET day D-1;
   settlement reads the AAA print of day D morning) imply the trader never sees the
   final overnight print. If the audit cannot unambiguously determine which print
   settles, KILL before the data pull; a one-day key error is a systematic fabricated
   edge on every near-tie market.
5. Precision: the 3-to-4 decimal display change (late 2025 to mid 2026) must be handled
   in the parser and checked in the audit above for near-tie strikes ("strictly greater
   than" at 3.800 vs 3.8001 is a settlement flip).

**Amendment A3 (wholesale as-of):** "one business day publication lag" for FRED daily
spot gasoline is asserted, not verified. EIA daily spot postings on FRED can lag 1 to 3
business days and holidays stretch it. Verify empirically via ALFRED vintages (real-time
publication dates are exactly what ALFRED exists for); if unverifiable, run the primary
at a conservative 3-business-day lag with 1-day as sensitivity, not the reverse.

## Attack 4: Trade-print execution proxy (F11)

**Finding: survivable, but only with a side-aware dual-bound design. A raw
"take at the print price plus haircut" is not acceptable on thin ladders.**

Two problems with recorded prints on thin ladders:
1. **Side.** A print at yes_price 0.45 where taker_side=no means someone SOLD into the
   bid; a strategy wanting to BUY YES at that moment would have paid the ask, which on
   a 3c-spread book is materially higher. Simulating our buy at that print price is a
   fabricated price improvement.
2. **Timing selection.** Prints cluster at informed moments (right after the AAA
   morning update, after wholesale moves). Conditioning fills on the existence of a
   print conditions on someone else having traded, which correlates with the signal
   itself and can flatter the measured edge.

**Amendment A4 (binding):**
- Primary (upper bound): fill only at prints whose taker_side matches our direction
  (we buy YES only at prints where a real taker bought YES), at that price, plus the
  worst-case fee. This is an honest "a marketable order at this price actually
  executed" statement, the strongest F11 answer available in this data.
- Lower bound: all fires filled at print price PLUS the full median quoted spread of
  that series/band as haircut, plus worst-case fee.
- The PASS gate binds on the LOWER bound CI. The upper bound is reported for context.
- Report fire-to-print attrition (fires with no eligible same-side print within the
  eligibility window are dropped and counted); if attrition exceeds ~50% the capacity
  story is weaker than the proposal claims and the verdict must say so.

## Attack 5: Cluster math and power (this one nearly kills the idea)

**Finding: the test as sketched is close to structurally underpowered, and the lock
must confront this with arithmetic, not vibes.**

The universe is ~82 weekly + ~19 monthly settlement events post-Oct-2024, total ~110
lifetime clusters, of which fires are a subset (divergence-gated, tradeable-band-gated,
freshness-gated per A2, print-gated per A4). Be honest about what survives all four
gates: 30 to 45 fired clusters is the realistic ceiling, and walk-forward burn-in eats
the front end.

Per-cluster P&L per contract on a binary is high-variance: buying at 0.75, outcomes
are +25 or -75, SD ~ 35-43pp; at 0.5 the SD is ~50pp. Within-event averaging across
strikes barely helps (same-event strikes are near-perfectly correlated). At n=35 fired
clusters and SD 40pp, the 95% CI half-width is roughly 13pp. The gate (CI lower bound
> 0) is therefore only reachable if the realized net edge per fire is on the order of
12-15pp. An edge that large on a smooth administered series with 100k+ contract weekly
volume implies the market is grossly wrong, which contradicts every attention fact in
the proposal's own tempering list. Meanwhile a plausible real edge (3-6pp net) is
UNDETECTABLE at this n: the test would return NULL even if the idea works. Two ways to
read that: (a) benign, the project treats nulls as wins and the cost is one session at
$0; (b) fatal, the test cannot validate the only edge sizes that are plausible, so it
is not a real test of the hypothesis. The truth is between: the design is only a test
of the "market is lazily wrong during pass-through episodes" hypothesis, and the lock
must SAY that.

**Amendment A5 (binding):**
- The lock states the minimum detectable edge at the expected fire count (show the
  arithmetic) and pre-declares a minimum-fires floor: at least 30 fired OOS settlement
  clusters (weekly and monthly pooled). Below the floor, the verdict is UNDERPOWERED
  (a named sub-species of NULL); no post-hoc extension of the universe, no adding the
  daily series to rescue n.
- The divergence firing threshold is set high enough (per Attack 2 arithmetic: hurdle
  plus margin such that the model-conditional expected net edge per fire is >= 8-10pp)
  that a true pass is at least arithmetically reachable at the achievable n. Firing on
  3pp divergences at this sample size guarantees an uninformative straddle.
- Pre-commit the interpretation: PASS requires lower-bound CI > 0 (per A4) AND model
  beats control; a "model beats control but CI straddles zero" outcome is a NULL with
  a noted direction, never a soft pass.

## Attack 6: Multiple testing and the garden of forking paths

**Finding: standard but non-negotiable at round ~25 of the project.**

This is approximately the 25th distinct hypothesis family the project has screened. A
marginal pass is suspect BY DEFAULT at this point, and the strata surface here is wide:
2 series x moneyness bands x horizon bands x up/down asymmetry is easily 12+ cells.

**Amendment A6 (binding):**
- ONE binding statistic: pooled (weekly + monthly, all fires) OOS net P&L per contract,
  event-cluster bootstrap CI, lower bound under the A4 lower-bound execution and the
  worst-case fee. Everything else (moneyness, horizon, direction, series split) is
  exploratory and cannot be promoted after data.
- Model spec FROZEN in the lock: lag length, asymmetry parameterization, residual
  method, refit cadence. No post-data spec search; if the frozen spec is degenerate on
  real data (e.g. singular fits), that is a NULL of the spec, and one pre-registered
  simpler fallback spec (named in the lock, not chosen later) may be run and reported
  as such.
- KXAAAGASD stays exploratory forever within v25 Idea 1: it cannot become evidence, it
  cannot be pooled into the binding stat, and its results appear only in an appendix.
- The verdict doc must carry the running hypothesis-count ledger per the charter.

## Attack 7: Regime nonstationarity (2024-25 calm, 2026 shock)

**Finding: the walk-forward design survives formally but the CI can be quietly broken
by cross-cluster dependence during the 2026 trend, and the verdict can be decided by a
single episode.**

The AAA series ran $2.83 (Jan 2026) to $4.07 (Jun 2026) to $3.85 (Jul 1). Two problems:
1. **Dependence.** Weekly settlement events during a 5-month one-way run share one
   macro shock. Treating them as independent clusters makes the bootstrap CI too
   narrow exactly where the fires concentrate. A pass whose significance depends on
   counting 15 shock-run weeks as 15 independent draws is not a pass.
2. **Fit transfer.** Asymmetric pass-through coefficients fitted on 2024-25 calm data
   meet a 2026 shock OOS; the rockets side of rockets-and-feathers is estimated from
   almost no calm-period variance. Walk-forward refit mitigates but the early-shock
   fires use pre-shock coefficients.

**Amendment A7 (binding sensitivity, pre-committed language):**
- Run a coarser-block bootstrap (calendar-month blocks) as a REQUIRED sensitivity next
  to the event-cluster primary. Pre-commit the language: if the primary passes and the
  month-block sensitivity does not, the result is labeled FRAGILE-PASS, which routes to
  the $0 live read and never to capital on backtest evidence alone.
- Report the binding stat with and without the Feb-Jun 2026 shock episode as a
  diagnostic (not a second gate). A pass that exists only inside the shock window must
  be described as a shock-window result.
- Note the interaction with A2: the worst Wayback gap sits inside this exact window, so
  the freshness exclusions and the decisive regime overlap. If A2 exclusions gut the
  shock window, the power floor in A5 will likely trip; that is the honest outcome, not
  a problem to engineer around.

## Attack 8: Everything else found

1. **Settlement overnight gap.** Trading ends 11:59pm ET on D-1; settlement reads the
   AAA print of D morning. The model's terminal distribution must run to the settlement
   print, not the close timestamp (one extra sub-cent overnight step; small for weekly
   and monthly, one more reason the daily series is excluded). The lock's horizon math
   must state this explicitly.
2. **"on Jul 31" wording vs close date.** Covered by the A2 settlement-key audit; do
   not lock without it.
3. **Fee facts check out.** Scout-verified quadratic (W) and quadratic_with_maker_fees
   (M, taker side same quadratic); the proposal's worst-case full 0.07 treatment with
   no reduced rate is correct and conservative. One taker fee per entry, none at
   settlement. No objection.
4. **Fractional pricing.** Current books quote sub-cent (fp fields). Fee remains
   ceil() per contract in cents; keep worst-case rounding up. Minor, note in lock.
5. **Pass-through speed literature is a double-edged sword.** The proposal leans on
   1-4 week lag. The literature (Borenstein/Cameron/Gilbert; Bachmeier/Griffin and
   successors) has retail responding within DAYS with roughly half of a wholesale
   shock passed through in ~2 weeks on the upside. Two consequences the lock must
   absorb: (a) at the WEEKLY horizon much of the pass-through is already in the
   current AAA level by the time the market lists, shrinking the exploitable drift
   gap; the monthly series is where the mechanical story is strongest, and it is the
   thinner, wider-spread one (1-5c spreads, 10c strikes); (b) fast pass-through is
   precisely what makes the regression easy for the MM too. The R^2 of the pass-through
   regression at 1-2 weeks is load-bearing for weekly fires and should be reported
   in-sample at lock-fit time, before any outcome data is touched (it uses only AAA +
   FRED, not Kalshi outcomes; this is schema-audit-grade, not peeking).
6. **Current regime is the feathers (down) leg.** AAA $4.07 to $3.85 and falling.
   Feathers means slow retail decline: drift is predictable but SMALL per week, so
   live-read divergences right now will be modest; do not let the live read quietly
   become the evidence base because the backtest was underpowered. The live read is a
   staging gate only (charter method win), and its role must be pre-stated.
7. **Bankroll/capacity.** Depth quoted (145 x 0.50 / 64 x 0.51 on the monthly ATM) is
   ample for $200. Not a factor either way. Agreed with proposal.

## What the proposal gets right (credit where due)

- Taker mechanism, no resting orders: cleanly outside the adverse-selection family.
- Worst-case fee treatment verified from live series objects, not memory.
- The random-walk control is a genuine methodological asset (with the A2 caveat that
  it does not detect stale-level artifacts; it detects wholesale-information
  emptiness).
- Settlement-event cluster CI as binding statistic, post-Oct-2024 only, no third bite.
- $0 live-read staging regardless of backtest outcome, per the v24 method win.
- The Tier 1 aggregate family (true window sums with deterministic pinning) is
  correctly queued as a separate idea rather than smuggled into this lock.

## VERDICT: PROCEED-WITH-AMENDMENTS

Prior re-marked to approximately 10% (from 12%): the "no sharp reference" escape claim
is factually wrong as written (weather had none either and died), but the corrected
escape claim (retail can implement the public frontier model here, which was never
true in weather/vol/sports) is genuine, the failure mode is benign and cheap, and the
data plan is real. This sits ON the charter's kill line, not above it; what keeps it
alive is that the expected cost of an honest null is one $0 session and the test
content is genuinely new for the project.

Binding amendments (the lock is invalid without all of them):
- **A1**: rewrite the escape argument in frontier form; restate prior ~10%.
- **A2**: as-of freshness regime: backward-fill only, zero-staleness firing rule,
  settlement truth from Kalshi records only, pre-lock settlement-key audit on >= 20
  settled markets. KILL SWITCH: audit ambiguity = kill before data.
- **A3**: verify FRED/EIA publication lag via ALFRED vintages; conservative lag
  primary if unverified.
- **A4**: side-matched print fills as upper bound, full-spread haircut as lower bound,
  gate binds on the lower bound; report attrition.
- **A5**: power arithmetic in the lock, minimum 30 fired OOS clusters floor,
  firing threshold derived from hurdle arithmetic so a true pass is reachable.
  KILL SWITCH: if the pre-lock fire-rate estimate (from divergence geometry, not
  outcome data) cannot plausibly reach the floor, kill before data.
- **A6**: one pooled binding statistic; frozen model spec plus one named fallback;
  daily series permanently exploratory; hypothesis ledger.
- **A7**: month-block bootstrap sensitivity with pre-committed FRAGILE-PASS language;
  shock-window in/out diagnostic.

If any amendment is rejected rather than adopted, this critic's verdict converts to
KILL.

*Em-dash and en-dash audit: to be verified after write (Select-String U+2014/U+2013).*
