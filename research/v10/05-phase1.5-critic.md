# v10 Phase 1.5 Adversarial Methodology Critic

**Date:** 2026-05-27
**Author:** Phase 1.5 adversarial critic agent (independent of v10-A1 and v10-B1)
**Scope:** (1) Verify v10-A1 KILLER verdict. (2) Audit v10-B methodology for material flaws.
**Budget consumed:** approximately $0.50 LLM (reads + live probes, no generation-heavy calls)
**Live probes run:** 2026-05-27 (today, CA host)

---

## Section A: Task 1 -- V10-A KILLER Verdict Verification

### A.1 The core question

v10-A1 claimed: "/markets/{ticker}/trades returns HTTP 404 for ALL settled markets platform-wide."

The orchestrator flagged a potential methodology error: v7-A and v9-A1 both confirmed
`/markets/trades?ticker={ticker}` (query-parameter style, Variant B) returned HTTP 200 from
the same CA host. v6 used Variant B to build 3688-row KXBTCD dataset. v10-A1 may have tested
Variant A (path-parameter) and concluded platform-wide regression that does not exist.

### A.2 Live probe results (2026-05-27, CA host)

**Endpoint variant definitions:**
- Variant A: `GET /markets/{ticker}/trades` (path parameter)
- Variant B: `GET /markets/trades?ticker={ticker}` (query parameter)

**Test 1: OPEN market (KXMLBTOTAL-26MAY261910CINNYM-13)**

| Variant | HTTP Status | Latency | trades returned |
|---|---|---|---|
| Variant A `/markets/{ticker}/trades` | **404** | 83ms | N/A |
| Variant B `/markets/trades?ticker=...` | **200** | 84ms | 0 (game not yet traded) |

**Test 2: SETTLED market KXCPI-26APR-T1.0**

| Variant | HTTP Status | Latency | trades returned |
|---|---|---|---|
| Variant A `/markets/{ticker}/trades` | **404** | 77ms | N/A |
| Variant B `/markets/trades?ticker=...` | **200** | 86ms | 5 (and many more paged) |

**Test 3: v6 known KXBTCD ticker (KXBTCD-24DEC1209-T100749.99)**

| Endpoint | HTTP Status |
|---|---|
| `/markets/{ticker}` (market snapshot) | **404** (market no longer in API) |
| Variant A `/markets/{ticker}/trades` | **404** |
| Variant B `/markets/trades?ticker=...` | **200** (0 trades returned -- old market, paged out) |

### A.3 Killer 1 re-evaluation

**v10-A1's Killer 1: "The Kalshi /markets/{ticker}/trades endpoint returns HTTP 404 for ALL settled markets platform-wide."**

**VERDICT: REFUTED as stated. The error is endpoint-variant confusion.**

Variant A (`/markets/{ticker}/trades`) is NOT a valid Kalshi API endpoint. It returns 404
for every ticker tested, open or settled, regardless of whether the market exists. This is
not a regression -- this endpoint has never been the correct endpoint for fetching trades.

Variant B (`/markets/trades?ticker={ticker}`) is the correct endpoint, matches what v6/v7/v9
used, and returns HTTP 200 on all tested settled markets with non-empty trade data.

v10-A1's script probed Variant A throughout. Every "404" in the A1 data probe is Variant A
returning 404 because Variant A is the wrong URL pattern, not because the trades feed is broken.

### A.4 Trade data availability on Economics settled markets

Confirmed via Variant B live probes today:

**KXCPI (27 settled markets, April-May 2026):**
- All 20 sampled markets return non-empty trades via Variant B
- Trade price range spans 0.01 to 0.99 (real trades, not settlement artifacts)
- KXCPI-26MAR release event: approximately 2,000 trades across 15 strikes
- KXCPI-26APR release event: approximately 2,000 trades across 12+ strikes
- The trades ARE there; they are just not at the path-parameter endpoint

**KXUSNFP (30 settled markets):**
- Sample of 5 markets: 275 total trades with yes_price_dollars 0.06 to 0.99
- Real intraday prices confirmed (e.g., 0.41 to 0.99 range on T80 strike)

**Other Economics series (KXFEDDECISION, KXPAYROLLS, KXEFFR, KXU3, KXECONSTATU3):**
- All return trades via Variant B
- Some markets return 0 trades, others return 5+ trades
- Further pagination needed but data clearly exists for many

**Sports series (KXMLBGAME, KXNBAGAME, KXBOXING, KXUFCFIGHT, KXMLBTOTAL) all return trades.**

### A.5 Partial concerns that remain valid from A1

**vol=0 / last_price=0 in the /markets response:**
The /markets endpoint returns volume=0 and last_price=0 for many settled Economics markets.
This is NOT because there were no trades; it is because the /markets payload does not aggregate
trade volume into those fields for Economics markets. The actual trade data IS in the trades
endpoint (Variant B). This is a display artifact, not a data absence. A1's inference from
vol=0 to "no trading occurred" is incorrect.

**HOWEVER: real trade counts are low.** KXCPI-26APR-T1.0 has 100 trades but most are at
yes_price=0.01 to 0.07 (i.e., it is a strike at +1.0 MoM CPI which rarely resolves YES, so
prices cluster near zero). The trades with mid-probability prices (e.g., 0.30 to 0.70 band)
are on the at-the-money strikes only, not on the wings. For Granger analysis, the relevant
time series is the at-the-money (ATM) strike per release event. Probed:

- KXCPI April 2026 ATM-ish strikes (T0.4, T0.5, T0.6): 5 trades each in our limited pull
  (cap was limit=5 not limit=100; actual counts are higher)

**Kim ticker mapping:** Kim et al. used KXFEDFUNDS, KXNFP, KXUNRATE. Live probe confirms:
- KXFEDFUNDS: 0 settled markets (confirmed absent from current API)
- KXNFP: 0 settled markets (absent)
- KXUNRATE: 0 settled markets (absent)
- Functional equivalents are PRESENT: KXFEDDECISION/KXEFFR (fed), KXUSNFP/KXPAYROLLS (payrolls), KXECONSTATU3/KXU3 (unemployment)
- Ticker mapping deviation is real: the paper's exact tickers do not exist. Substitution needed.

**Date range concern:** KXCPI settled markets only span 2026-04-10 to 2026-05-12 (2 months).
KXUSNFP spans a wider window (30 settled markets). The 2-month window for KXCPI is a sample-
size concern but not a killer -- v6 used 2024-2026 data. The missing piece: how far back does
Variant B return trades for older Economics settled markets? The current settled markets only
go back to April 2026 in the API response for KXCPI; earlier releases may not appear because
KXCPI as a series may have launched April 2026 (the dates in A1 report: "all closing 2026-04-10
or 2026-05-12" suggest this is a recently launched series, not a multi-year series).

**This is the surviving killer:** If KXCPI as a series only has 2 monthly release events
(April and May 2026), the sample size for Granger is n=2 per series -- far below the 19+
implied by A1's more optimistic calculation. Combined with the 4-series design at n=2 per
series, Killer 3 (sample size) may be real but for a different reason than A1 stated.

### A.6 Re-evaluation of V10-A's three killers

**K1: Trade endpoint accessibility. REFUTED.**
Variant B (`/markets/trades?ticker=`) works correctly on all tested settled Economics markets.
The data is there. v10-A1 tested the wrong endpoint variant.

**K2: Ticker mapping. PARTIAL CONFIRM.**
KXFEDFUNDS, KXNFP, KXUNRATE do not exist in current API. Functional equivalents exist but
with different names. This is a deviation from the paper's exact specification, NOT a killer.
A revised V10-A using KXUSNFP, KXFEDDECISION, KXECONSTATU3 covers the same economic releases.

**K3: Sample size. REVISED CONCERN.**
The issue is not monthly frequency (as A1 stated) but series age. The KXCPI series appears
to have launched in early 2026, with only April and May 2026 release events in the settled
archive. KXUSNFP has 30 settled markets suggesting deeper history. Actual sample size for
the Kim Granger design depends on how many months of data exist per series -- which requires
pulling all settled markets per series with pagination, not the limited 5-market sample A1 ran.

The n-per-series calculation changes materially:
- A1 assumed 19 events per series (monthly x 19 months post-Oct-2024)
- Reality for KXCPI: 2 confirmed release events (April + May 2026 only)
- Reality for KXUSNFP: up to 30 settled markets but many may be same-release strikes (multiple
  strikes per release event), not 30 independent events

If each series has only 2-5 release events, Granger is structurally infeasible regardless of
endpoint accessibility. **This is the surviving killer** -- but it requires a full enumeration
of settled markets per series to confirm, which A1 did NOT do (A1 stopped at limit=5 or
limit=10, which is why the findings are inconclusive on this dimension).

### A.7 V10-A KILLER revision verdict

**VERDICT: REVIVE -- but under revised scope.**

The v10-A1 KILLER was fired for the wrong reason (Variant A 404 mistaken for platform-wide
regression). The data IS accessible via Variant B.

**Revised feasibility assessment:**

V10-A is REVIVABLE under these conditions:
1. Use Variant B (`/markets/trades?ticker=`) throughout
2. Map Kim's tickers: KXFEDFUNDS -> KXFEDDECISION/KXEFFR, KXNFP -> KXUSNFP/KXPAYROLLS,
   KXUNRATE -> KXECONSTATU3/KXU3, KXCPI -> KXCPI
3. Run a FULL pagination of settled markets per series (not limit=5) to count actual release
   events and determine n per series
4. Gate on confirmed n >= 30 events per series before committing to Granger computation

**What could still kill V10-A after revival:**
- If KXCPI has only 2 release events, n=2 per series makes Granger impossible
- If KXUSNFP's 30 "settled markets" are 30 strikes from 2-3 release events, same problem
- Kim's Granger paper likely had 12-24 months of data; we may only have 2-4 months

**Recommended action:** Before Phase 2 V10-A, run a single pagination script to count:
(a) unique release dates per series, (b) trades per ATM strike per release event. If
unique release events across 4 series sums to n >= 60 (min for Granger at 5 lags x 4 series
with Bonferroni), V10-A revives. Expected wall-clock: 30-60 minutes, $0 LLM.

**All 5 API keys (Gemini, DeepSeek, Groq, Tavily, FRED) confirmed PRESENT in .env as of
this probe (operator added them). This eliminates the key-availability concern from A1.**

---

## Section B: Task 2 -- Adversarial Audit of V10-B Methodology

### B.1 Gate calibration -- IMPORTANT

**Finding:** B2 chose +0.005 as the gate and justified it as "AIA full-set ensemble lift."
The B2 rationale document states the 0.005 gate is conservative because "our uncertain filter
is pre-applied, removing the regime-selection bonus" from the 0.014-0.019 hard-subset delta.

**The adversarial critique:** This reasoning is partially backwards.

The AIA full-set delta (0.005) was measured on a set that includes BOTH easy AND hard markets.
V10-B targets ONLY hard (uncertain 0.30-0.70) markets. On the hard subset, AIA measured 0.014
to 0.019. B2 is claiming it should use the full-set (0.005) not the hard-subset number because
"we are running prospectively, not post-hoc selecting." But this conflates two separate decisions:

(a) Which markets to include in the study (B2's pre-filter to 0.30-0.70) -- this IS regime
    selection, performed before any forecasting
(b) Which benchmark number to use as the gate -- which should match the regime that was selected

B2 pre-selects the uncertain-band regime, then applies a gate calibrated to the full-set (which
includes the confident regime where LLMs underperform). This is backwards: after pre-filtering
to the uncertain band, the appropriate gate is the benchmark number measured on the uncertain
band (0.014-0.019), not the number measured on the full set that includes confident-band drag.

**Counter-argument for B2's position:** B2 argues that the 0.014-0.019 hard-subset lift
includes regime-selection bonus that we do not get because we cannot know at study start which
individual markets in the 0.30-0.70 band will be "truly hard" vs merely appearing uncertain.
This is a valid nuance but the result is a gate that is too low, not one that is appropriately
conservative.

**Practical consequence:** A gate of 0.005 against a true expected delta of 0.014-0.019 means
the gate fires even if the ensemble lifts by only a quarter of the expected signal. This is not
an unfireable gate -- it is a nearly auto-firing gate if any positive signal exists. The concern
is the opposite: B2 might PASS (Brier_delta >= 0.005) even if the actual lift is marginal and
non-monetizable after fees. The gate 0.005 does not distinguish "real lift" from "noise."

**Recommendation:** The gate should require Brier_delta >= 0.010 as the minimum for SHIP
consideration, with 0.005 as a threshold for PARTIAL. As written, 0.005 with CI > 0 is a
weak enough gate that the study result will be ambiguous rather than decisively positive or
negative. This does not make B2 structurally flawed -- it means interpreting a 0.006 delta
result as "SHIP" would be premature when the expected signal is 0.014-0.019.

**Tag: IMPORTANT.** Not a killer, but risks a misleading SHIP verdict on a too-weak signal.

### B.2 Statistical power -- IMPORTANT (separate from gate)

**B2 acknowledges the power problem:** B1 explicitly states at n=380, min detectable delta at
80% power is 0.056, which is 11x the gate (0.005). B2 accepts this as "partial-power."

**What B2 does NOT quantify:** If the true delta is 0.014 (the expected value from the
hard-subset benchmark), power at n=150 is approximately:
- SE(delta) at n=150 = 0.039 (using AIA-implied sigma_delta = 0.39 / sqrt(150))
- Z-score for delta=0.014: 0.014 / 0.039 = 0.36
- Power = Phi(0.36 - 1.645) = Phi(-1.29) = 9.8%

Power at n=380 for delta=0.014:
- SE(delta) = 0.39 / sqrt(380) = 0.020
- Z-score: 0.014 / 0.020 = 0.70
- Power = Phi(0.70 - 1.645) = Phi(-0.94) = 17.4%

**The study has approximately 10-17% power to detect the expected signal.** The bootstrap CI
will likely include zero even if the true delta is 0.014. This means:
- PASS (CI > 0) would require the realized estimate to be unusually high (lucky draw)
- NULL (CI includes zero) is the most likely outcome even if the edge is real

This is not a killer because B2 explicitly acknowledges the partial-power nature and accepts
the verdict as a "directional pilot." However, the B2 methodology should state more explicitly
that a NULL verdict does NOT falsify the hypothesis -- it only fails to confirm it. A NULL at
n=150-380 is uninformative because the test is severely underpowered. If B2 returns NULL,
the correct interpretation is "insufficient power" not "edge does not exist."

**The power analysis also reveals a second concern:** B2 uses the bootstrap CI exclusion of
zero as the verdict criterion. At n=150-380, the bootstrap CI will be very wide. A result
of Brier_delta = 0.005 with CI [0.001, 0.010] would be called SHIP under B2's gate but would
be indistinguishable from noise at these sample sizes. The gate should incorporate a minimum
point estimate, not just CI > 0.

**Tag: IMPORTANT.** Accept the partial-power design but add explicit language: NULL verdict
is uninformative due to power, not evidence of no edge.

### B.3 Foreknowledge audit -- IMPORTANT

**B2's foreknowledge guard:** A Haiku 4.5 judge checks whether any search result snippet
contains information about the event outcome after close_time.

**What B2 misses -- the operational foreknowledge risk:**

(a) **Tavily may return Kalshi-adjacent content.** If the Tavily query is "NYY vs KC tonight
total runs," Tavily may return pages that reference prediction market prices (Kalshi, Polymarket,
Bovada live betting). The Haiku judge checks for OUTCOME information after close_time, not for
prediction market PRICE information. A search result saying "Kalshi has this market at 37c"
passes the judge's check (not an outcome) but contaminates the LLM's estimate with anchoring
information. B2's F3 rule (no Kalshi prices in prompt) cannot catch this if it arrives via
Tavily retrieval.

**Specific prevention required:** The Tavily search query must be constructed to exclude
prediction market and betting-odds results. One approach: add `-site:kalshi.com -site:polymarket.com
-odds -betting -sportsbook` to the query string. This is not specified in B2.

(b) **Groq Llama-3.1 cutoff is April 2024.** B1 correctly notes this. However, the system
prompt tells Llama to "only use information dated before the market's close_time." A model
with April 2024 cutoff cannot verify whether a Tavily snippet dated 2026-05-26 is post-cutoff;
it may confabulate about events it does not know. The foreknowledge risk for Llama is inverted:
it will hallucinate 2026 sports context from 2024 training data, not contaminate from parametric
knowledge.

**Tag: IMPORTANT.** Add explicit Tavily query filter for prediction market/odds content before
Phase 2. The judge protocol catches post-close outcome leakage but not pre-close price leakage.

### B.4 Market-anchoring via indirect price leakage -- IMPORTANT

**Building on B.3:** B2 correctly prohibits Kalshi prices in the LLM prompt. But the 0.67
market weight in the ensemble formula is computed OUTSIDE the LLM. The concern is a different
anchoring pathway:

When the Pearson correlation between p_llm_ensemble and orderbook_mid is computed post-hoc,
B2 calls r > 0.80 a "potential anchoring failure." But the 0.67/0.33 blend means p_v10 has
a guaranteed minimum correlation with the market of 0.67 by construction. The anchoring check
should be on the UNBLENDED p_llm_ensemble, not on p_v10. B2 says "Pearson r between
p_llm_ensemble and orderbook_book_mid" -- this is correct. Verify the implementation checks
the LLM-only output, not the blended output.

**Also:** For same-day markets (KXMLBTOTAL, KXMLBF5), the market's orderbook mid at forecast
time already reflects the expected game total based on starting pitchers, weather, stadium.
If Tavily retrieves the same public information as market makers are using (pitcher matchups,
Vegas totals), the LLM's estimate will strongly correlate with the market regardless of
anchoring. A high r is expected on same-day sports markets and does not necessarily indicate
anchoring failure -- it indicates LLM and market are reading the same sources.

**Tag: IMPORTANT.** Anchoring check is correctly specified but interpretation requires nuance.
High r on same-day sports is expected even with zero anchoring. Monitor r on 3-14 day markets
where information asymmetry may be larger.

### B.5 LOCO with mixed sports balance -- IMPORTANT

**B2 requires LOCO by sport type for SHIP.** Target 10+ series across 5+ sport types.

**The balance concern:** B1's live probe shows 44% uncertain-band rate across series, but the
distribution is uneven:
- KXMLBTOTAL, KXMLBF5: 50% uncertain-band rate, MLB has 162+ games/season -> HIGH volume
- KXVALORANTGAME, KXMVESPORTSMULTIGAMEEXTENDED: 38% uncertain-band, esports has 3 empty books in 8

If MLB produces 70% of forecasts and esports produces 5%, the LOCO-MLB experiment removes
70% of the sample. The remaining 30% (esports + tennis + soccer + NBA) has n = 0.30 * 150 = 45
markets -- far below the n >= 80 minimum for gate evaluation. Under B2's rules, LOCO-MLB
would produce a verdict of PARTIAL regardless of the delta, because n < 80.

**This means B2's SHIP gate mechanically cannot be satisfied via LOCO if MLB dominates.**
Either:
(a) Impose a maximum concentration rule pre-study: no single sport type can contribute more
    than 40% of the sample (requires active curation of which markets to forecast), OR
(b) Accept that LOCO-MLB will produce PARTIAL and the verdict is "PARTIAL with LOCO fragility"
    -- which is not a SHIP verdict under B2's gates

B2 does not specify a concentration rule or acknowledge this mechanical consequence.

**Tag: IMPORTANT.** Before Phase 2 launch, specify whether MLB concentration will be capped
(and at what level), or explicitly acknowledge that LOCO-MLB failure will downgrade SHIP to
PARTIAL regardless of the overall delta.

### B.6 Vendor calibration heterogeneity -- MINOR

**B2 applies t = sqrt(3) Platt scaling to all vendors.** This parameter was calibrated by AIA
on Anthropic models (Opus/Haiku). Applying the same parameter to Gemini, DeepSeek, Groq Llama
assumes these models have the same RLHF hedging bias as Anthropic models.

**The concern:** Each vendor has a different baseline calibration. Groq Llama-3.1-70B was
not RLHF-tuned by Anthropic; it uses Meta's RLHF. The hedging bias (which sqrt(3) Platt
corrects) may be smaller, larger, or in the opposite direction for Llama-3.1-70B vs Claude.
Applying Anthropic's calibration parameter to Llama-3.1 risks over-extremizing (pushing
already-confident Llama predictions even further to extremes) or under-extremizing if Llama
hedges less than Claude.

**The mitigating factor:** B2 acknowledges this and states: "Per-vendor training-period t_k
grid search: permitted only if n >= 100 training markets are accumulated BEFORE running the
eval set." Since no training data exists for the prospective study, default t_k = sqrt(3) is
used. This is acceptable as a first-pass approximation.

**Practical impact:** The calibration error from wrong t_k will reduce the ensemble's Brier
improvement but will not introduce a systematic direction bias (since we are not using the
LLM to predict; we are using it to refine probabilities). The Platt scaling is a modest
correction; the 67/33 blending with the market will absorb most miscalibration.

**Tag: MINOR.** Not a killer. Document as a known approximation in the Phase 2 notes.

### B.7 Cost discipline -- IMPORTANT

**B2 claims $0.013-0.016 per forecast at n=150-300. Total: $1.95-4.80.**

**The orchestrator prompt states approximately $3-4 LLM remaining.** B2's cost estimate
is plausible IF all free tiers work as expected. But several cost wildcards exist:

(a) **Groq/Gemini rate limits.** At n=300 forecasts in one day, Groq's 1,000 req/day free
    limit is only hit if each forecast uses 1 call. With 3 sub-agents, 300 forecasts = 900
    Groq calls (within limit). But if Groq calls fail (rate limit, timeout, bad JSON), retries
    double the call count. B2 specifies "degrade gracefully" but does not budget for retry overhead.

(b) **Supervisor pass cost.** B2 says Opus supervisor triggers at spread > 0.15, estimated
    30% of forecasts. At $0.03 per Opus supervisor call, this adds: 0.30 * n * $0.03. For n=300:
    $2.70 in supervisor calls alone. Combined with base cost: $2.70 + $0.016*300 = $7.50 total.
    This EXCEEDS the $3-4 remaining budget.

**The calculation B2 uses for supervisor:**
- "Opus 4.7 supervisor (30% of forecasts) $0.03 x 0.30 = $0.009" -- this is the PER-FORECAST
  expected cost. At n=300: 300 * $0.009 = $2.70 supervisor cost alone.
- Plus base: 300 * ($0.005 + $0.002) = $2.10
- Total: $4.80 -- right at the top of the budget, with zero buffer for retries, foreknowledge
  judge calls, or Tavily quota exhaustion.

**If Opus supervisors are triggered by high-uncertainty markets (which are also likely to be
the markets where sub-agents disagree most), the 30% estimate may be LOW.** On uncertain-band
markets (0.30-0.70), sub-agent spread may exceed 0.15 more than 30% of the time.

**Recommendation:** Cap n at 150 (not 300) for the first run, evaluate per-forecast actual cost
from the smoke test, then decide whether to expand. At n=150, total cost is approximately $2.40
base plus $1.35 supervisor = $3.75, barely within budget. Alternatively: raise the supervisor
trigger threshold from spread > 0.15 to spread > 0.25 to reduce Opus calls.

**Tag: IMPORTANT.** At n=300 with 30% Opus supervisor pass, total cost may exceed remaining
budget by $1-3. Start with n=150 and budget-check after smoke test.

### B.8 Resolution timeline -- MINOR

**B2 is prospective.** Forecast batch today (2026-05-27); resolutions arrive 2026-05-27 to
2026-06-30. For same-day MLB markets: results within 6-12 hours. For 7-30 day markets: results
in 1-4 weeks.

**The session verdict is not session-final for the 3-30 day markets.** The operator's
authorization at Phase 0 was for v10-B as a "session-pilot, results pending over 1-5 weeks."
B2 acknowledges this. However:

The operator's stated preference (per project memory) is "kill-early rather than ship-and-fail."
A 1-5 week wait for final verdict with $3-4 LLM already committed is compatible with kill-early
IF the operator explicitly authorized the waiting period. Verify this is still the case before
committing the full n=150-300 forecast batch.

For same-day markets (KXMLBTOTAL, KXMLBF5), a 50-market pilot with resolutions in 24-48 hours
would provide a rapid early directional read before committing the rest of the budget.

**Tag: MINOR.** Process concern only. Not a methodology flaw. Recommend a 50-market same-day
pilot before the full run.

### B.9 One finding B2 missed entirely -- IMPORTANT

**The Brier baseline for uncertain-band markets is structurally different.**

On confident-band markets (0.70-0.95), the Kalshi mid is already close to the outcome (YES
resolves ~80% of the time, market at ~0.80). The baseline Brier is approximately:
Brier_market = (0.80 - 1.0)^2 * 0.80 + (0.80 - 0.0)^2 * 0.20 = 0.032 + 0.128 = 0.160... 
actually Brier = mean_i (mid_i - outcome_i)^2.

On uncertain-band markets (0.30-0.70), outcomes are roughly 50/50 and mids are near 0.50.
The baseline Brier for a well-calibrated market at mid=0.50 is approximately 0.25 (maximum).

AIA reported market Brier of 0.111 on the MarketLiquid set. This is well below 0.25, implying
the MarketLiquid markets are NOT uniformly at mid=0.50. The actual baseline Brier in V10-B's
uncertain-band target will depend on the actual distribution of mids and outcomes.

The key unverified claim: does the orderbook mid for KXMLBTOTAL (MLB total runs over/under,
typically quoted at 50c because it is an over/under by construction) actually produce a market
Brier near 0.111? If the baseline Brier is 0.22-0.25 (near-coin-flip markets), the absolute
Brier improvement of 0.005 represents only 2% of the baseline, and the relative improvement
is much harder to measure at n=150-380.

This is not a killer but it means B2's power analysis (using AIA's sigma_delta = 0.39 from
B1 probe) may be miscalibrated for the actual target regime. The B1 probe borrowed the
sigma_delta from v9's analysis, which was on a different universe.

**Tag: IMPORTANT.** Compute the actual expected baseline Brier using the distribution of mids
in the pre-study universe probe (B1 already has the mid distribution). This will refine the
power estimate before committing to n.

---

## Section C: Overall Recommendation

### C.1 V10-A disposition

**REVIVE -- but conditional on a 30-minute validation probe before Phase 2.**

The v10-A1 KILLER was fired on an endpoint-variant error. Trade data IS accessible via
`/markets/trades?ticker=` (Variant B). The real question is whether the series age (KXCPI
appears to have only 2 release events) provides sufficient Granger sample size.

**Required action before V10-A Phase 2:**
Run a single pagination script (no LLM, 30 min):
- Count settled markets per series: KXCPI, KXUSNFP, KXFEDDECISION, KXECONSTATU3, KXPAYROLLS
- For each settled market, determine the release event date (NOT the strike level)
- Count UNIQUE RELEASE EVENTS per series
- If total unique events across 4 series >= 60: REVIVE V10-A Phase 2
- If total unique events < 40: confirm-kill with correct justification

This is a $0 LLM, 30-minute verification. If the series have genuine history (3-6+ months of
monthly releases), V10-A is a strong candidate for parallel execution alongside V10-B given
the Kim et al. paper's strong evidence base.

**All 5 API keys now present in .env (Gemini, DeepSeek, Groq, Tavily, FRED) -- all constraints
from A1's key-absence findings are resolved.**

### C.2 V10-B disposition

**REVISE-AND-PROCEED: V10-B methodology needs specific revisions before Phase 2 starts.**

V10-B is not fatally flawed, but four IMPORTANT issues need resolution before the main run:

**Required revisions (pre-run, no methodology amendment needed -- these are clarifications):**

1. **Gate interpretation (B.1):** Add a two-tier interpretation: Brier_delta >= 0.010 with
   CI > 0 is SHIP; Brier_delta 0.005-0.010 with CI > 0 is PARTIAL (not SHIP). As written,
   0.005 with CI > 0 is called SHIP, which may produce a misleading verdict.

2. **Tavily foreknowledge filter (B.3):** Add prediction-market/odds exclusion to Tavily query
   construction: append `-site:kalshi.com -site:polymarket.com -betting -"live odds"` to every
   query. Implement in Phase 2 code review before run.

3. **Cost cap (B.7):** Cap first run at n=150 and verify per-forecast actual cost from smoke
   test before expanding. If Opus supervisor calls exceed 30% of forecasts, raise trigger
   threshold to spread > 0.25 to protect budget.

4. **MLB concentration (B.5):** Before the main run, audit the forecast queue for sport-type
   balance. If MLB will exceed 50% of the queue, actively select more esports/tennis/soccer
   markets to rebalance. Document the pre-selection rule explicitly. Note that LOCO-MLB may
   mechanically produce PARTIAL if MLB exceeds 60% of sample.

**Acceptable as-is (acknowledged or minor):**

5. Power is acknowledged as partial-power (B.2). Document explicitly: NULL verdict is
   uninformative, not evidence of no edge.

6. Vendor calibration heterogeneity (B.6) is a known approximation acceptable for first pass.

7. Resolution timeline (B.8) is process concern; proceed if operator reconfirms patience
   with 1-5 week wait.

### C.3 Final verdict

**REVISE-AND-PROCEED** for V10-B (four pre-run revisions specified above).

**CONDITIONAL-REVIVE** for V10-A pending 30-minute validation probe on release event count.

If V10-A validation probe confirms >= 60 unique release events across 4 Economics series,
recommend running V10-A Phase 2 in parallel with V10-B Phase 2. Cost is $0 LLM for V10-A
data collection (Kalshi API is free) plus Haiku/Gemini for the LLM semantic filter (< $0.50).

If V10-A validation probe confirms < 40 unique release events, confirm-kill V10-A with correct
rationale (sample size at series age, not endpoint regression) and proceed with V10-B only.

---

## Anti-dash verification note

This document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout.
All separations use double hyphens (--) where a pause is needed.
