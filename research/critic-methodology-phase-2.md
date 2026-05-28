# Phase 2 Methodology Critic: Politics x H Maker-Quote Lock-In

**Date:** 2026-05-23
**Author:** Methodology-Critic sub-agent
**Scope:** Adversarial pre-data review of [phase-2-methodology.md](phase-2-methodology.md).
The plan-critic round ([critic-plan-phase-2.md](critic-plan-phase-2.md)) is
already incorporated; this review targets the LOCKED methodology itself.

## Executive summary

The methodology is broadly sound and incorporates the nine plan-critic
findings faithfully, but it should NOT be locked as-is. Two of the five
pass criteria are not correctly calibrated to detect the strategy's true
performance: C3 (9 of 17 splits net > 0) accepts a true-zero strategy
roughly 50% of the time by chance and walk-forward correlation pushes
that false-acceptance rate higher; and C1 (slope >= 1.2 on small-trade
VWAP) is internally inconsistent with the trade-size scale effect that
the methodology itself flags via [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Trade-size scale effect". Three other items rise to IMPORTANT: the
14-day purge is insufficient for long-horizon politics markets where
train-set resolutions can post-date test-set market opens; the
one-sided-flow filter conflates informed toxicity with consensus on
true-high-probability markets; and survivorship / sample-composition
bias from election-cycle dominance in the corpus is not addressed. Lock
the methodology after the BLOCKING fixes; flag IMPORTANT items in the
change log and address before unlock.

## Leakage stress-test findings

### Walk-forward purge: 14 days is insufficient for long-horizon politics

The methodology purges 14 days between train_end and test_start
([phase-2-methodology.md](phase-2-methodology.md) Section 5.1), with
markets assigned to a partition by `resolution_time`. The VWAP window
sits at `[resolution - 35d, resolution - 28d]`
([phase-2-methodology.md](phase-2-methodology.md) Section 3).

Walk through a concrete leakage path:

- Train_end = day 180. Test_start = day 195 (14-day purge).
- A train-set market resolves on day 175 (just before train_end). Its
  trading-window VWAP was computed over [day 140, day 147]. Trades
  before day 140 contributed to its lifetime prints but are not in the
  measurement window.
- A test-set market opened on day 80, resolves on day 196 (just after
  test_start). Its VWAP window is [day 161, day 168].
- The two markets' VWAP windows are temporally disjoint (147 < 161)
  but their LIFETIMES overlap substantially: both were trading during
  days 100-175. If a major political event (Trump indictment, FOMC
  cut, polling release) on day 165 moved BOTH markets, the
  isotonic / logistic fit on train absorbed the joint structure and
  can artificially help the test fit.

Politics median per-market liquidity is 127 trades and the highest of
any Kalshi domain ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Per-domain breakdown on Kalshi"). Politics markets routinely open
60-180 days before resolution (Le notes this as "long-horizon" trades
the >1mo bin; [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Domain-by-horizon trajectories"). A 14-day purge cannot decorrelate
markets whose lifetimes overlap by months. Le's own four-component
decomposition assigns 26.0% of variance to domain-by-horizon
interactions ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"The four components of calibration error"); this is exactly the kind
of structure that bridges train and test under a short purge.

Severity: IMPORTANT (not BLOCKING because the bias inflates rather than
fabricates signal, and the leave-one-event-out check partly compensates).

Recommended fix: purge by `market_open_time` not just `resolution_time`.
A market is "in train" only if BOTH market_open_time and resolution_time
fall before train_end. A market is "in test" only if market_open_time
falls after train_end + 14d. Markets that straddle (open in train,
resolve in test) are dropped from the test partition. This loses sample
but is the only way to prevent train-fit absorbing test-market price
dynamics.

### Trading window cannot span train and test

For a market resolving exactly on test_start (day 195), the VWAP window
is [day 160, day 167], entirely inside train. The methodology computes
the VWAP for ALL markets at dataset-build time
([phase-2-methodology.md](phase-2-methodology.md) Section 2.4) and only
later assigns markets to partitions by resolution_time. So the VWAP
itself does not leak across partitions; the model fit on train sees only
train-resolution markets. The leakage path here is the lifetime-overlap
correlation above, not direct VWAP contamination. The 28-day pre-
resolution buffer is robust to news-day jumps; the
[phase-2-methodology.md](phase-2-methodology.md) Section 3 anti-Phase-
1.5-bug check is correct in spirit.

Severity: not a leakage problem in isolation. Captured under purge-
extension fix above.

### Isotonic / logistic absorbing cross-market correlation

The methodology fits a single isotonic calibrator on the full train
partition ([phase-2-methodology.md](phase-2-methodology.md) Section 6.3).
"Trump wins Iowa" and "Trump wins New Hampshire" both resolve in early
2024; isotonic on the combined train set learns a joint mapping that
implicitly conditions on the Trump-favorable regime. If late-2024 test
markets are also Trump-related, the calibrator transfers state knowledge
without seeing the actual outcomes.

The leave-one-event-out check
([phase-2-methodology.md](phase-2-methodology.md) Section 5.2) holds out
entire event windows (e.g., all Nov 2024 markets), which IS a control
for this. But the four event windows are large and inhomogeneous:
"Q1 2025 FOMC + policy events" combines Fed-related markets with
unrelated state-level politics, so the LOCO check tests cross-event
generalization but not within-event independence. Acceptable given the
small number of event windows available; flag as a known limitation.

Severity: NICE-TO-HAVE. The C4 threshold (>= 3 of 4 windows) is a
reasonable hedge.

## Pass-criteria calibration findings

### C1 (slope >= 1.2 on small-trade VWAP): internally inconsistent

The methodology justifies C1 = 1.2 as "80% of Le's posterior 95% CI
lower bound" (1.46 * 0.82 ~ 1.2)
([phase-2-methodology.md](phase-2-methodology.md) Section 7.1). Le's
posterior CI is 1.46-1.83 at >1mo horizon for politics
([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Domain-by-horizon trajectories"). But Le's slope is fit on the FULL
trade distribution; the methodology fits the slope on SMALL-TRADE VWAP
only ([phase-2-methodology.md](phase-2-methodology.md) Section 6.1).

Le's trade-size scale effect documents that large trades in Kalshi
politics are MORE compressed than small trades by Delta = 0.53 (95% CI
[0.29, 0.75]; [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Trade-size scale effect"). Interpretation: when you regress outcome on
small-trade VWAP, the implied slope is LOWER than when regressing on
all-trade VWAP, because small trades are closer to truth.

Quantification: if all-trade slope is the posterior mean ~1.65
([phase-2-methodology.md](phase-2-methodology.md) Section 7.1
implicitly via 1.46-1.83 CI), and Delta = 0.53 separates large from
small, then small-trade slope is somewhere between 1.65 - 0.265 = 1.39
(equal large / small mix) and 1.65 - 0.53 = 1.12 (slope on small trades
only, large trades fully driving the all-trade signal). The C1
threshold of 1.2 falls INSIDE this range. So even if Le's regime is
exactly correct, C1 may pass marginally on the SAME mechanism that the
methodology's small-trade VWAP requirement is supposed to filter out.

This is not catastrophic but it makes C1 weak as a regime-presence
gate. A median slope of 1.21 would clear C1 but imply, at YES = 0.30,
a recalibrated truth of sigmoid(1.21 * -0.847) = 0.265 - only 3.5pp
mispricing vs 12.5pp at slope 1.83. The implied per-trade gross edge
would be ~4-5pp, marginally above C2 = 2.04pp, but with 2pp fees and
1.5pp slippage = 3.5pp deductions, NET edge approaches zero.

Severity: BLOCKING for C1 as currently specified.

Recommended fix: tighten C1 to require BOTH (a) median per-partition
slope >= 1.2 AND (b) per-partition slope lower-quartile (25th
percentile across splits) >= 1.0. The (b) clause rules out the case
where C1 passes because one or two splits have very high slopes
dragging the median up.

### C2 (gross edge >= 2.04pp): correctly calibrated, redundant with C5

C2 = 2x Becker politics 1.02pp per-trade gap
([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
"Per-category maker-taker gap" table). The 2x multiplier is defensible
because we sub-slice (long-horizon, mid-band, small-trade VWAP) and
the literature does not justify a 4x multiplier
([critic-plan-phase-2.md](critic-plan-phase-2.md) Risk 2).

The issue: C2 is essentially auto-passed when C5 passes, and C5 fails
when C2 just-passes. At YES = 0.30 the round-trip maker fee is ~2pp
([phase-2-proposal.md](phase-2-proposal.md) Q2) plus 1.5pp slippage =
3.5pp deduction. For median net > 0 (C5 first clause), gross must be >
3.5pp. For mean net > 0 with adverse-selection-driven left tail (C5
second clause), gross must be even higher. So C5 binds at ~3.5pp;
C2 binds at 2.04pp. C2 is the looser constraint in nearly all of the
relevant parameter space.

Severity: NICE-TO-HAVE. C2 retains diagnostic value: if C2 passes but
C5 fails, the diagnosis is "edge is real but fees + slippage eat it";
if C2 fails, "no edge at all." Keep C2 as a check that the slope-
implied edge matches the directly-measured gross edge. Do NOT relax C5
to align with C2; if anything strengthen C5.

### C3 (9 of 17 splits net > 0): BLOCKING; accepts a true-zero strategy 50% of the time

Walk through the binomial null. Under H0: true per-split net edge is
exactly 0 (independent splits), each split independently has P(net >
0) = 0.5 (symmetric noise around 0). Then
`P(>= 9 of 17 | H0) = sum_{k=9}^{17} C(17,k) * 0.5^17 = 0.500` by
binomial symmetry around the mean of 8.5. The criterion is effectively
a coin flip under the null.

Power calculation under H1: true per-trade net edge ~ 2pp, with binary
outcome variance bounded by p(1-p) ~ 0.25, so SD of (outcome - p) ~ 0.5
per market. With ~1000 markets per test partition, the SE of per-split
mean net edge is 0.5 / sqrt(1000) ~ 1.58pp. For a true 2pp edge, P(net
> 0 in one split) ~ Phi(2 / 1.58) = Phi(1.27) ~ 0.90. Then P(>= 9 of 17
| H1: edge = 2pp) ~ 1 - Binomial(17, 0.9).cdf(8) ~ 0.999.

Power is high under H1; false-acceptance under H0 is ALSO high. C3
discriminates poorly because the threshold is set at the binomial null
median.

Aggravating factor: walk-forward splits are NOT independent. Consecutive
splits share 150 days of training and 14 days of buffered overlap (180d
train + 14d purge - 30d step = 164d overlap between consecutive train
windows). Per-split test outcomes are positively correlated through
shared training-data state. Effective independent sample size is less
than 17, so the binomial null gives FALSE-acceptance > 50% in practice.

Severity: BLOCKING.

Recommended fix: raise C3 threshold from 9 of 17 to 13 of 17 (binomial
null cumulative = 0.05, restoring meaningful Type I control). OR
replace per-split count with a pooled test: estimate the mean per-trade
net edge over ALL test partitions concatenated, and require the lower
bound of a bootstrap 95% CI to exceed 0. The pooled test sidesteps the
correlation problem and uses the full ~17,000-market sample.

### C5 (median AND mean net > 0): correctly genuinely additive to C3

The plan-critic correctly identified that median > 0 alone hides news-
event tail losses ([critic-plan-phase-2.md](critic-plan-phase-2.md)
Section 2 C5). With a heavy left tail driven by Bartlett's adverse-
selection on news days
([bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR item 6), median can stay near 0.5pp while mean is -1pp. The
"median AND mean > 0" requirement is the correct adverse-selection
catcher.

C5 is NOT redundant with C3. C3 is a per-split count; C5 is a per-trade
distributional statement on the pooled sample. A strategy with positive
median in 9 splits but a single bad split's -10pp mean dragging pooled
mean negative fails C5, passes C3. Conversely a strategy with positive
pooled mean but only 8 of 17 splits net > 0 fails C3, passes C5. The
intersection is genuinely stricter than either alone.

Severity: PASS. Keep as locked.

## Small-trade VWAP thesis-collapse stress-test

The methodology computes BOTH all-trade and small-trade VWAP, then gates
on the small-trade variant ([phase-2-methodology.md](phase-2-methodology.md)
Section 6.3, 7 C5). The slope (C1) is fit on small-trade VWAP
([phase-2-methodology.md](phase-2-methodology.md) Section 6.1). This is
the correct construction for measuring whether THE PRICE WE WILL FILL AT
is mispriced.

But the thesis itself rests on Le's slope = 1.83, which was estimated on
ALL trades ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Domain-by-horizon trajectories"). The trade-size scale effect (Delta =
0.53, 95% CI [0.29, 0.75];
[le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Trade-size scale effect") explicitly says large trades drive part of
this compression. If small trades are LESS compressed (closer to truth),
the small-trade slope is lower than 1.83.

Boundary calculation: if all-trade slope is 1.65 and Delta = 0.53 is
the large-vs-small difference, then small-trade slope estimate sits
somewhere in [1.65 - 0.265, 1.65 - 0.53] = [1.12, 1.39] depending on
the trade-size mix in our small-trade subset (<=10 contracts per
methodology Section 2.4). Under the worst-case 1.12, the implied edge
at YES = 0.30 is sigmoid(1.12 * -0.847) = 0.281, gross edge 1.9pp on
cost basis - LESS than C2's 2.04pp threshold and unable to clear 3.5pp
fees + slippage. The thesis collapses in this worst case.

Under the optimistic 1.39, edge is sigmoid(1.39 * -0.847) = 0.241,
gross edge 7.5pp on cost basis (Bürgi normalization;
[burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md)
"Headline numbers to pin") and ~4pp on Becker's normalization. C5 just
passes.

The honest reading: the thesis survives small-trade slopes in roughly
the upper half of the Delta-implied range, fails in the lower half. The
methodology must NOT silently pass C1 in the lower half. The fix in the
C1 section above (lower-quartile constraint) is the relevant guard.

Additional risk the methodology under-weights: Le finds the scale
effect does NOT replicate on Polymarket
([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Trade-size scale effect"), attributing it to "Kalshi-specific
microstructure." If the maker-taker fee schedule that drove the 2024
sign flip ([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
"The 2024 sign flip") also drives the scale effect, then a future fee
change could collapse the small-trade-vs-large-trade compression
differently, invalidating the small-trade-VWAP gate. The methodology
should note this as a regime-monitoring item for Phase 3.

Severity: BLOCKING - this risk is the reason the C1 fix is BLOCKING.

## Election filter and one-sided-flow filter critiques

### "30% non-federal-election" filter: heuristic that does not cleanly enforce its intent

The methodology operationalizes the election-cycle diversity requirement
via "ticker / event metadata references federal-election keywords"
([phase-2-methodology.md](phase-2-methodology.md) Section 4). This is a
necessary-not-sufficient signal.

Failure modes:

1. State ballot initiatives that don't reference federal-election
   keywords are still election-cycle-driven via correlated voter
   turnout, ad spend, and partisan engagement. They will be tagged as
   "non-federal-election" but trade with election-driven flow.
2. Markets on FOMC outcomes, Supreme Court decisions, or international
   events resolve during federal-election months but have no federal-
   election keyword. Their behavior is not election-driven but they get
   tagged as "potentially federal-election" if they share an event
   namespace.
3. The 30% target is hard to verify pre-data: if the corpus has only
   15% non-federal-election markets, the filter cannot be enforced
   without dropping samples in a way the methodology has not
   pre-committed to.

Severity: IMPORTANT.

Recommended fix: after data pull and BEFORE running the gate, manually
review the top 50 most-traded markets and tag them as "federal-
election-driven / not-federal-election-driven" by inspection. If <30%
manually verify as non-federal-election, the methodology must either
(a) widen the corpus window per pre-commitment Section 2.2 Option A, or
(b) honestly report the bias and proceed with the explicit caveat that
gate results apply only to federal-election-cycle markets. The
methodology should pre-commit which choice and the threshold for making
it.

### One-sided-flow filter (>65% same-side trades): conflates toxicity with consensus

Bartlett's one-sided-flow finding is a VPIN-style INFORMED-TRADING
metric ([bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR item 6): one-sided flow on a 50-50 market suggests an informed
trader is on one side. The methodology operationalizes this as
`one_sided_flow_pct <= 0.65`
([phase-2-methodology.md](phase-2-methodology.md) Section 4).

The conflation: a 70-30 prior market with 75% YES buys is NOT a toxic
flow signal - it's consensus on a high-probability outcome. The filter
will drop a heavily-favored incumbent's market (true prob 0.85, market
prob 0.80, retail and informed both buying YES) precisely because the
market is unanimous, even though the maker (selling YES) is taking the
RIGHT side of the trade.

This matters because the strategy's core thesis (Le's compression) is
SHARPEST on markets where the truth is far from 0.5 but the price is
compressed toward 0.5. For a true-prob-0.85 market priced at 0.80, the
recalibration mapping says the truth is closer to 0.95 (compressed by
factor 1.83) and the maker NO side is the trade. The 65% filter
excludes exactly these markets.

The mid-band price filter ([0.20, 0.45] union [0.55, 0.80];
[phase-2-methodology.md](phase-2-methodology.md) Section 4) partially
controls for this by excluding extreme strikes. A 0.75 market filtered
by one-sided-flow at >65% YES is still inside the band but the YES
predominance does not necessarily signal informed activity.

Severity: IMPORTANT.

Recommended fix: compute the one-sided-flow metric ONLY among trades in
the [-35d, -28d] window (current methodology) AND compare to the
market's mid-band VWAP. If one_sided_flow_pct > 65% AND the price is
in [0.30, 0.70] (the narrow mid-band where Bartlett's adverse-selection
effect concentrates per [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR items 2 and 4), exclude. If price is in [0.20, 0.30] or
[0.70, 0.80] and one-sided-flow > 65%, KEEP the market - the
consensus is consistent with the prior. This adds a price-conditional
clause to the filter.

## Unaddressed considerations

### Survivorship and corpus composition

Kalshi added many new politics markets through 2024-2026 as it scaled.
The 2024-10-01 to 2026-04-30 corpus is heavily weighted toward the Nov
2024 federal election cycle (Becker shows Q3 2024 volume = $30M, Q4
2024 = $820M ; [becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
"The 2024 sign flip"). Early-window markets are election-cycle-
dominated; late-window markets (mid-2025 to 2026-04) are a different
composition of state-level, FOMC, primary, and special-election
markets.

If the strategy generalizes only because training data is election-
cycle-dominated, Phase 3 deployment in late-2026 (post-Nov 2026
midterms) or 2027 (off-cycle) will face structurally different markets
and the backtest gate may not predict live performance. The bias-
shrinkage trend ([burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md)
"Time-period trend (Table 9)") compounds this: bias has been compressed
each year, and the 2024 peak may not recur.

Severity: IMPORTANT.

Recommended fix: report per-split mean net edge SEPARATELY for splits
where the test partition is >50% federal-election-month markets vs not.
If the strategy passes only on federal-election-dominated splits, flag
that the Phase 3 deployment regime may not match the validation regime,
and require operator authorization on the regime caveat.

### Power: per-split sample size and walk-forward correlation

Per the C3 analysis above, per-split SE on mean net edge is ~1.58pp
with ~1000 markets per test partition. The C5 threshold (median AND
mean net > 0) thus has SE ~1.5pp; detecting a true 2pp net edge has
power ~89% per split. POOLED across all 17 splits with effective
independent sample size ~10 (accounting for walk-forward overlap), SE
on pooled mean is 0.5pp; power to detect 2pp net edge is essentially
1.0.

The pooled mean test would be a strictly more powerful version of C3
and is recommended above. The methodology should add a pooled-mean-
with-bootstrap-CI estimate to Section 6 as an ADDITIONAL diagnostic
(not a gate; gates are locked). Diagnostic addition does not violate
no-post-data-tuning.

Severity: NICE-TO-HAVE if C3 is fixed to 13 of 17 OR replaced with
pooled bootstrap.

### Transaction-cost realism: fill rate not in the gate

Critic finding 9 ([critic-plan-phase-2.md](critic-plan-phase-2.md)
Section 5 item 9) identifies that fill rate is untested in historical
trade data and proposed a >=100-fill paper-trade measurement in Phase
3. The methodology incorporates this via
[phase-2-methodology.md](phase-2-methodology.md) Section 10 items 3
and 5.

But the BACKTEST gate itself does not apply a fill-rate discount. A
real maker bot with 30-40% fill rate (per critic finding 9) incurs
opportunity cost on unfilled quotes (the price moves, the maker cancels
and re-quotes, paying nothing in fees but losing the option value of
the original quote). The gate measures per-fill net edge; per-attempt
net edge is lower.

This is acceptable because Phase 2's question is "is there a real
mispricing to exploit?" not "is the strategy net-positive at the
implementation level?" The fill-rate discount belongs in Phase 3 paper-
trade validation, where it is included. But the gate's pass should be
treated as NECESSARY-NOT-SUFFICIENT for Phase 3 to proceed, not as a
green light for deployment.

Severity: NICE-TO-HAVE. The methodology already handles this correctly
in Section 10; flag explicitly in the gate verdict that Phase 3 must
still measure fill rate.

## Recommended changes before unlocking

Priority order. BLOCKING items must be fixed before the methodology
unlocks; IMPORTANT items must be addressed within the next change-log
entry; NICE-TO-HAVE items can be tracked separately.

1. **BLOCKING: Raise C3 threshold from 9 of 17 to 13 of 17, OR replace
   with pooled bootstrap mean test.** Current threshold is at the
   binomial null median, giving ~50% false acceptance under H0. With
   walk-forward correlation, effective false acceptance is higher.

2. **BLOCKING: Tighten C1 to require BOTH median per-partition slope
   >= 1.2 AND per-partition slope lower-quartile >= 1.0.** The current
   single-statistic median check can be passed by 2-3 high-slope splits
   pulling the median up, even if the small-trade slope is below the
   thesis-survival range across most splits.

3. **BLOCKING: Document the small-trade-slope-collapse risk** in
   Section 7.1 explicitly. Note that small-trade VWAP is the ONLY
   regime that matters for retail tradability AND that the small-trade
   slope is structurally lower than Le's all-trade slope by up to 0.53
   per [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
   "Trade-size scale effect".

4. **IMPORTANT: Extend the purge to filter on market_open_time, not
   just resolution_time.** Markets that open in train and resolve in
   test (lifetime-straddling) must be dropped from the test partition.
   This loses sample but is the only honest decorrelation in the
   long-horizon regime.

5. **IMPORTANT: Add price-conditional clause to the one-sided-flow
   filter.** Apply the >65% exclusion only to markets in [0.30, 0.70];
   outside that range, allow consensus on high-prior markets.

6. **IMPORTANT: Document election-cycle composition explicitly.**
   Report per-split breakdown of federal-election-month markets vs
   not; report whether the strategy passes on election-dominated splits
   only or also on non-election splits. The methodology must NOT
   silently accept a result that passes only in election dominance.

7. **IMPORTANT: Pre-commit the election-filter inspection process.**
   Add to Section 4: "After data pull and BEFORE running gate, manually
   verify top-50-traded markets election-cycle status. If <30% non-
   federal-election, choose Option A (widen window) or Option B
   (report bias) per pre-commitment."

8. **NICE-TO-HAVE: Add pooled-bootstrap mean net edge as a diagnostic**
   in Section 6.4. Not a gate, just a more powerful complementary
   measurement of pooled effect.

9. **NICE-TO-HAVE: Flag in gate verdict that Phase 2 pass is necessary-
   not-sufficient for Phase 3 deployment.** Fill rate, regime
   stability, and order-book liquidity remain to be tested.

10. **NICE-TO-HAVE: Add note in Section 7.1 about fee-schedule regime
    risk.** Becker's 2024 sign flip
    ([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
    "The 2024 sign flip") demonstrates that fee changes can flip the
    sign of the maker advantage. Le's trade-size scale effect may also
    flip if Kalshi alters the fee schedule. Phase 3 must include fee-
    schedule regime monitoring.

## Citations table

| Claim in this report | Paper file | Section / Table / Figure |
|---|---|---|
| Le posterior 95% CI on politics slope at >1mo is 1.46-1.83 | le-2026-crowd-wisdom.md | "Domain-by-horizon trajectories" |
| Le four-component decomposition explains 87.3% of variance | le-2026-crowd-wisdom.md | "The four components of calibration error" |
| Domain-by-horizon interactions = 26.0% of variance | le-2026-crowd-wisdom.md | "The four components of calibration error" |
| Trade-size scale effect Delta = 0.53, 95% CI [0.29, 0.75] | le-2026-crowd-wisdom.md | "Trade-size scale effect" |
| Scale effect does not replicate on Polymarket | le-2026-crowd-wisdom.md | "Trade-size scale effect" |
| Politics median 127 trades per market lifetime | le-2026-crowd-wisdom.md | "Per-domain breakdown on Kalshi" |
| Politics slope at long horizon = 1.83 (one-bin point estimate) | le-2026-crowd-wisdom.md | "Domain-by-horizon trajectories" |
| Becker politics gap 1.02pp on 4.9M trades | becker-2026-microstructure.md | "Per-category maker-taker gap" |
| Becker Q3 2024 vs Q4 2024 volume ($30M to $820M, 27x) | becker-2026-microstructure.md | "The 2024 sign flip" |
| Becker documents 2024 sign flip (taker won pre, maker won post) | becker-2026-microstructure.md | "The 2024 sign flip" |
| Bürgi >= 50c maker average return +2.6% | burgi-deng-whelan-2025.md | "Headline numbers to pin" |
| Bürgi 33% per-trade SD on >= 50c maker subpopulation | burgi-deng-whelan-2025.md | Section 6 |
| Bürgi bias-shrinkage trend 2021-2025 (psi 0.041 -> 0.021) | burgi-deng-whelan-2025.md | "Time-period trend (Table 9)" |
| Bartlett VPIN-style one-sided-flow predicts maker losses in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR item 6 |
| Bartlett single-name has higher informed price impact | bartlett-ohara-2026-adverse-selection.md | TL;DR item 2 |
| Bartlett behavioral surplus 2x adverse selection in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR item 4 |
| Methodology C3 threshold 9 of 17 splits net > 0 | phase-2-methodology.md | Section 7 C3 |
| Methodology C1 threshold slope >= 1.2 (small-trade VWAP) | phase-2-methodology.md | Section 7 C1, Section 7.1 |
| Methodology C5 requires median AND mean net edge > 0 | phase-2-methodology.md | Section 7 C5 |
| Methodology purge buffer = 14 days, doubled from Phase 1.5's 7 | phase-2-methodology.md | Section 5.1 |
| Methodology VWAP window [-35d, -28d] | phase-2-methodology.md | Section 3 |
| Methodology one-sided-flow filter at 0.65 | phase-2-methodology.md | Section 4 |
| Methodology election-filter operationalized via ticker keywords | phase-2-methodology.md | Section 4 |
| Plan-critic findings 1-9 incorporated | critic-plan-phase-2.md | Section 5 |
| Phase 1.5 vs 1.6: window choice swamps model choice | phase-1.5-methodology.md | Section 10 change log |
