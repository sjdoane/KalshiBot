# V10-B Phase 1.5 Methodology Lock

**Date:** 2026-05-26
**Agent:** v10-B1
**Status:** LOCKED. No amendments permitted after first forecast is run.
**Predecessor:** `research/v9/02-recipe-methodology.md` (AIA recipe, reused verbatim with modifications below)
**Evidence base:** AIA Forecaster arXiv 2511.07678, TimeSeek arXiv 2604.04220, Halawi 2024,
Prediction Arena arXiv 2604.07355, v9 Phase 3 critic, v10 F1-F10 taxonomy.
**Do not modify after first data pull.**

---

## 1. Design Changes from v9 (Explicit Comparison)

### v9 design (NULL, killed at Phase 1)

| Parameter | v9 value | Problem |
|---|---|---|
| Sub-agents | 3x Claude Opus 4.7 (same vendor, same model) | No vendor diversity; same RLHF bias profile |
| Target universe | v1 denylisted-residual sports (confident favorites 0.70-0.95 YES) | Wrong regime: AIA +0.014 measured on uncertain (0.20-0.80) markets |
| Horizon | T-35d to T-7d | Long horizon, outside TimeSeek "early lifecycle" optimum |
| Brier gate | +0.014 | AIA hard-market lift; measured on uncertain regime; unfirable on confident markets |
| Result | Design-layer kill (F7 + F8) | Expected lift on confident favorites: approximately 0.00015 |

### v10-B design (this document)

| Parameter | v10-B value | Failure mode addressed |
|---|---|---|
| Sub-agents | Up to 4 vendors: Opus + Gemini + DeepSeek + Groq | Multi-vendor diversity; different RLHF profiles (F7) |
| Target universe | Uncertain band mid 0.30-0.70, mixed sports props + esports + tennis + soccer | Regime-matched to AIA + TimeSeek evidence (F8) |
| Horizon | 1-30 days (short lifecycle = TimeSeek "early" optimum) | TimeSeek: LLMs competitive early and on high-uncertainty |
| Brier gate | +0.005 with 95% bootstrap CI > 0 | AIA full-set ensemble lift (not hard-market subset) |
| Fallback | Haiku 4.5 orchestrator if keys absent; degraded ensemble |  |

**Three changes simultaneously, each addressing a documented failure mode:**
- F7 (topic-regime mismatch for LLM): mix of sport types (props, esports, tennis, soccer)
  distributes topic risk; no single weakest-LLM topic dominates
- F8 (gate-regime mismatch): uncertain band is the regime where AIA measured +0.014;
  gate lowered to 0.005 (full-set ensemble lift, which is the conservative AIA estimate)
- Horizon alignment: TimeSeek empirically confirms LLMs competitive early and uncertain on Kalshi

### Why the gate changes from 0.014 to 0.005

The v9 gate was +0.014, sourced from the AIA hard-subset Brier lift. The AIA paper reports
two numbers:
- MarketLiquid ensemble Brier 0.092 vs market alone 0.111 (delta = 0.019, hard subset)
- MarketLiquid ensemble Brier 0.106 vs market alone 0.111 (delta = 0.005, full set)

The 0.014 figure used in v9 corresponds to the market-vs-AIA gap on the HARD SUBSET, not the
ensemble lift on the full set. The ensemble improvement on the full MarketLiquid set is
approximately 0.005 (0.111 minus 0.106). V10-B uses 0.005 because:
- Our target universe IS the uncertain (hard) regime; the hard-subset numbers apply to this
  regime specifically
- BUT the hard-subset delta (0.014-0.019) includes regime-selection; we are running
  prospectively on markets already in the uncertain band, not post-hoc selecting the hardest
- The conservative full-set delta 0.005 is the appropriate pre-registered threshold for a
  prospective ensemble that includes both market weighting AND the uncertain filter
- v9 Phase 3 critic Test 5 (design kill) noted the gate should be 0.000-0.003 on confident
  markets; on uncertain markets the appropriate gate is 0.005-0.010, so 0.005 is the
  lower bound of the plausible range

**Gate = 0.005 is the pre-registered threshold. No post-hoc adjustment permitted.**

---

## 2. Universe and Selection

### Price regime (pre-registered)

Uncertain band: mid in [0.30, 0.70] at time of forecast.

This is the regime where:
- AIA Forecaster measured +0.014 Brier lift (MarketLiquid "hard" = mid 0.20-0.80)
- Halawi 2024 documents LLM beats crowd (crowd-predicted 0.3-0.7: LLM 0.199 vs crowd 0.246)
- TimeSeek (arXiv 2604.04220) documents LLMs competitive on "high-uncertainty markets"
- Prediction Arena all-6-lost on Kalshi is evidence that LLMs need structural edge beyond
  pure forecasting; the 67/33 ensemble weight is that structural edge

The 0.30-0.70 band is NARROWER than AIA's 0.20-0.80. This is deliberate: we exclude the
extreme-uncertain range (0.20-0.30 and 0.70-0.80) where market liquidity is typically thin
and spread is wide, making the orderbook mid less reliable as a baseline.

### Target series (pre-registered, in priority order)

| Series | Type | Rationale |
|---|---|---|
| KXMLBTOTAL | MLB total runs (over/under) | High volume; by construction targets 0.50 mid; same-day resolution |
| KXMLBF5 | MLB first 5 innings result | Same as KXMLBTOTAL; resolves mid-game |
| KXMVESPORTSMULTIGAMEEXTENDED | Esports multi-game props | Highest non-crypto/sports trade frequency (21 in last-200); zero prior coverage |
| KXITFWMATCH | ITF Women's tennis | 18 trades in last-200; daily tournaments; ATPranking data free |
| KXNBASPREAD | NBA point spread | In uncertain band by construction; Finals ongoing |
| KXNBATOTAL | NBA total points | Same as KXNBASPREAD |
| KXVALORANTGAME | Valorant esports | 3 trades in last-200; novel category |
| KXMVECROSSCATEGORY | Esports cross-category | 5 trades in last-200 |
| KXATPCHALLENGERMATCH | ATP Challenger tennis | 5 trades in last-200; Roland Garros context |
| KXCONMEBOLLIBGAME | Copa Libertadores match | 6 trades in last-200; South American soccer |
| KXNHLGAME | NHL game | 2 trades; NHL Finals in progress |
| KXMLBRFI, KXMLBKS, KXMLBHIT | MLB prop variants | Lower priority; add if inventory thin on main series |

### Excluded (pre-registered)

- Confident regime (mid > 0.70): v1's live universe; not tested here by design
- v1 denylist: KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS
- Crypto denylist: KXBTCD, KXETHD, KXBTC15M, KXETH15M (v5-C/v6/v7-B NULLs)
- Season-long sports: KXMLBWINS, KXNBAWINS (long horizon; v1 live; F9 seasonal)
- Weather: EC-1 killed at Phase 1.6 OOS gate
- Macro (KXCPI, KXFOMC): Diercks 2026 confirms institutional pricing; Susquehanna MMs
- Politics domestic: Becker/Burgi smallest gap categories

### Close-time filter

At forecast time, only markets with close_time >= now AND close_time <= now + 30 days.
This enforces the TimeSeek "early lifecycle" alignment. Markets closing in 1-30 days are
"early" relative to their resolution date, ensuring LLM search context is fresh and
relevant (not stale pre-match narratives).

### Sport-stratified breakdown (required for verdict)

After gate evaluation, report Brier_delta by series group:
- MLB props (KXMLBTOTAL, KXMLBF5, KXMLBRFI, KXMLBKS, KXMLBHIT)
- Esports (KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME, KXMVECROSSCATEGORY)
- Tennis (KXITFWMATCH, KXATPCHALLENGERMATCH)
- NBA (KXNBASPREAD, KXNBATOTAL)
- Soccer (KXCONMEBOLLIBGAME)
- Other

This breakdown is DESCRIPTIVE ONLY. The verdict is on the pooled Brier_delta. Sport-specific
deltas are informative for future targeted research (per v10-S1 "sports is weakest LLM topic"
concern); they do NOT change the verdict.

---

## 3. LLM Ensemble Formula (Pre-Registered)

### Sub-agent configuration

K = number of active vendor sub-agents, ranging from 2 (degraded) to 4 (best case).

**Best case (operator adds free-tier keys):**
- Sub-agent 1: Gemini 2.5 Flash (Google AI Studio free tier, 1,500 req/day)
- Sub-agent 2: DeepSeek V4 Flash (5M free signup tokens, then $0.14/M)
- Sub-agent 3: Groq Llama-3.1-70B (1,000 req/day free)
- Sub-agent 4 (supervisor): Claude Opus 4.7 (triggered only when spread > 0.15)

**Current-state fallback (Anthropic keys only):**
- Sub-agent 1: Claude Haiku 4.5, phrasings A (direct probability estimate)
- Sub-agent 2: Claude Haiku 4.5, phrasings B (scenario-based probability)
- Sub-agent 3 (supervisor): Claude Opus 4.7 (triggered when spread > 0.15)
- Effective K = 2 vendors, with prompt diversity as intra-vendor diversity proxy

**Minimum required:** at least 1 Anthropic sub-agent + 1 non-Anthropic sub-agent. If only
Anthropic models are available, run with 2 Haiku phrasings as described above.

### Per-sub-agent calibration (Platt scaling)

Each sub-agent receives independent Platt scaling:

```
p_calibrated_k = sigmoid(t_k * logit(p_raw_k))
logit(x) = log(x / (1 - x))
```

Temperature parameter t_k:
- Default for all vendors: t_k = sqrt(3) = 1.7320508 (AIA ablation best-single-step)
- This is the same parameter used in v9's recipe (locked in Section 1.4 of v9-A2)
- Per-vendor training-period t_k grid search: permitted only if n >= 100 training markets
  are accumulated BEFORE running the eval set. If training set is unavailable, use default.

For V10-B prospective design (no historical orderbook for training):
- t_k = sqrt(3) for all vendors, locked pre-run

### Aggregation

```
p_llm_ensemble = mean(p_calibrated_1, p_calibrated_2, ..., p_calibrated_K)
```

Simple mean across K Platt-scaled sub-agent outputs. Weights are equal (1/K each). No
post-hoc reweighting of sub-agents.

### Ensemble with market

```
p_v10 = 0.67 * orderbook_book_mid + 0.33 * p_llm_ensemble
```

This is the AIA MarketLiquid formula verbatim (Section 5, simplex regression: "67% market
consensus, 33% AI Forecaster"). Weights are locked. No post-hoc adjustment.

The 0.67/0.33 split was measured on the full MarketLiquid hard set (mid 0.20-0.80), which
overlaps substantially with our uncertain band (0.30-0.70). This is the regime where the
split was calibrated; it is appropriate to apply here.

### Supervisor pass

If spread(p_calibrated_1, ..., p_calibrated_K) > 0.15:
- Supervisor call (Claude Opus 4.7) reads all sub-agent reasonings and search results
- Supervisor issues up to 2 additional targeted search queries
- Supervisor outputs a synthesis probability p_supervisor
- Final ensemble: mean of all K sub-agent outputs plus p_supervisor

If spread <= 0.15: no supervisor pass. Final ensemble is mean of K sub-agent outputs.

---

## 4. Prompt Template (Locked)

These prompts are fixed for all sub-agents. No per-market variation permitted. The system
prompt is cached across all forecasts in a session (Anthropic prompt caching).

### System prompt (all vendors)

```
You are an expert forecaster. Estimate the probability of YES resolution for the prediction
market described. Do not search for or incorporate any prediction market price, sportsbook
line, or betting market consensus into your estimate. Your estimate must be independent of
market prices.

Use any available search or retrieval tools to find current factual context relevant to the
market outcome. Only use information dated before the market's close_time.

Output JSON only, with this exact schema:
{"reasoning": "<your step-by-step analysis>", "p_yes": <float between 0.01 and 0.99>}

Do not output exactly 0.50 unless you genuinely believe the event is a coin flip after
careful analysis. Use two-decimal precision (e.g., 0.43, not 0.4 or 43%).
```

### User prompt per market (NOT cached; unique per forecast)

```
Market: {market.title}
Resolution rules: {market.rules_primary}
Market closes (resolves): {market.close_time} UTC
Today's date and time: {now_utc} UTC

Please research this question and provide your probability estimate. Output JSON only.
```

### What is explicitly excluded from the prompt

- No Kalshi orderbook mid, bid, or ask
- No sportsbook line or spread
- No prediction market price from any venue
- No "the market thinks" or "the current consensus is" phrasing

This is F3 (no Kalshi prices in LLM prompt, anchoring prevention). The Kalshi mid is
captured separately at forecast time and combined OUTSIDE the LLM calls.

---

## 5. Tool Wiring

### Tavily Search (if TAVILY_API_KEY present)

- One search call per forecast, query derived from market title
- Example query: `"{team_a} vs {team_b} {sport} latest news injury lineup"`
- Tavily returns structured JSON snippets; pass top-3 snippets to sub-agent context
- Cost: free tier 1,000 req/month; at 300 forecasts = 300 credits (within budget)

### ESPN site.api (fallback, no key)

- Endpoint: `http://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard`
- Use for: current game status, team records, recent results
- Rate limit: 1 req/sec courtesy delay
- Maps to sport codes: baseball/mlb, basketball/nba, hockey/nhl, soccer
- Limitation: no free-text news summaries; structured data only

### The-odds-api (COMPARATOR ONLY, not shown to LLM)

- Fetched at forecast time alongside orderbook mid
- Records: the-odds-api line, implied probability, line movement (if prior fetch available)
- NOT passed to any LLM sub-agent
- Used for: post-hoc correlation with ensemble output; sanity checking
- Credit cost: 1 credit per sport per session batch (477 credits remaining)

### Foreknowledge guard (mandatory)

For each forecast, after sub-agent calls complete:
- Haiku 4.5 judge call: receives (a) list of search result snippets, (b) market close_time
- Judge prompt: "Does any of these search results contain information about the specific
  event outcome AFTER {close_time}? Reply YES or NO. If YES, identify which snippet."
- If judge returns YES: flag the market; exclude from primary analysis; include in flagged
  tally. If flagged rate exceeds 5%, pause and debug search prompts.
- Per-forecast cost: approximately $0.002 (Haiku 4.5)

---

## 6. Pre-Registered Gate Criteria

### Primary gate (verdict-binding)

```
Brier_delta = mean(Brier_kalshi) - mean(Brier_v10)
SHIP if: Brier_delta >= 0.005 AND 95% bootstrap CI lower bound > 0
NULL if: Brier_delta < 0.005 OR 95% bootstrap CI lower bound <= 0
```

Bootstrap protocol: 10,000 bootstrap resamples with replacement from N resolved markets.
Report 2.5th and 97.5th percentile as the 95% CI.

### Gate threshold derivation

0.005 is the conservative AIA full-set ensemble lift (market alone 0.111 minus ensemble 0.106).
This is the lower bound of the AIA improvement range. The upper bound (0.014-0.019, hard
subset only) is not used because:
- We are running prospectively on uncertain markets, not post-hoc selecting the hardest subset
- The hard-subset lift includes the regime-selection bonus; our uncertain filter is
  pre-applied, removing that bonus
- F8 lesson: gate must match the experimental regime. The full-set 0.005 is regime-matched
  to a prospective uncertain-band study.

### Sample-size minimum

N >= 80 resolved markets to evaluate the gate. Below N=80, report Brier_delta as a point
estimate only (no CI) and declare PARTIAL regardless of directional sign.

### LOCO requirement

Leave-one-sport-type-out (LOCO) validation: re-compute Brier_delta after removing each sport
group (MLB, esports, tennis, NBA, soccer, other) from the sample.

SHIP requires the 95% bootstrap CI to remain strictly positive in all LOCO runs.
If any LOCO run produces a CI including zero, report as PARTIAL with LOCO fragility noted.

This addresses F10 (LOO fragility): the edge cannot depend on a single sport type dominating.

### Secondary metrics (informational, not for verdict)

- Brier_delta at weights [50/50, 67/33, 80/20] -- informational only
- Brier_delta on YES-only and NO-only resolved markets
- Sport-stratified Brier_delta (per series group)
- Pearson r between p_llm_ensemble and orderbook_book_mid (anchoring check; if r > 0.80,
  report as potential anchoring failure regardless of Brier outcome)
- Fraction of forecasts where supervisor pass was triggered

---

## 7. Failure Modes Addressed (F1-F10 per v10-S3 taxonomy)

| Code | Failure | v10-B response |
|---|---|---|
| F1 | Data availability ceiling | Prospective design; no historical orderbook needed; live orderbook is always available for open markets |
| F2 | Sample size insufficient | n=150-300 is achievable in 5-week window; gate 0.005 still requires ~48,000 for 80% power; explicitly labeled partial-power study |
| F3 | Domain mismatch | Series-stratified reporting; LOCO validation; no single series exceeds 30% of expected sample |
| F4 | Phantom from stale-price proxy | Orderbook mid at forecast time (`/markets/{ticker}/orderbook`), NOT last_price_dollars; capture timestamp within 60 seconds of LLM call |
| F5 | Methodological leak | All features computed from data prior to forecast timestamp; no look-ahead; Platt t fixed pre-run |
| F6 | Single-entity artifact | LOCO validation by sport type; concentration report at Phase 2 start |
| F7 | Topic mismatch for LLM | Mixed topic set (MLB + esports + tennis + soccer + NBA); no single topic dominates; esports and tennis less LLM-weak than pure game-winner sports |
| F8 | Gate-regime mismatch | Gate 0.005 = AIA full-set ensemble lift on uncertain markets; target regime 0.30-0.70 is within AIA's measured 0.20-0.80 regime |
| F9 | Seasonal scope collapse | MLB props and esports are year-round (or at minimum available through June 2026); no seasonal gap in the 5-week study window |
| F10 | LOO fragility | LOCO by sport type required for SHIP; if any LOCO removes CI > 0, verdict is PARTIAL not SHIP |

---

## 8. What We Will NOT Do

These are non-negotiable rules. Operator cannot waive them.

1. **No Kalshi prices in any LLM prompt.** Any prompt containing Kalshi bid, ask, mid,
   last_price, or any prediction market price is invalid. The code must be audited before
   the main run to confirm.

2. **No post-hoc weight tuning.** The 67/33 ensemble weight is locked. Reporting the delta
   at other weights is permitted but cannot change the verdict.

3. **No post-hoc Platt parameter tuning.** t_k = sqrt(3) for all vendors. If training data
   accumulates after Phase 2 runs, a tuned t_k may be reported as informational for a future
   round but cannot retroactively change this round's verdict.

4. **No live capital.** V10-B is a paper study. No /portfolio/orders calls during any part
   of V10-B Phase 1 through Phase 3. Live capital decision requires a passing gate verdict
   AND a separate Phase 5 paper-trading period (minimum 30 days).

5. **No back-tested verdict.** Historical orderbook is unavailable for settled markets (F1).
   The study is prospective only. Any claim based on reconstructed historical data would be
   a F4 phantom.

6. **No third bite.** If the gate fails, V10-B closes as NULL. No re-running with a
   different sport subset, different date window, or different ensemble weight after seeing
   the results.

7. **No foreknowledge bypass.** The Haiku judge is mandatory for every forecast. If a market
   has a flagged result, it is excluded from the primary analysis. The flagged-market rate
   is reported in the final verdict.

---

## 9. Smoke Test Plan

Before the main Phase 2 run, execute a 5-market smoke test.

### Smoke test market selection

- 5 markets from the target series (not from the eval set)
- OR 5 markets that will resolve within 48 hours (quick feedback)
- All must have mid in [0.30, 0.70] at smoke-test time

### Smoke test hard gates (abort if any fail)

| Check | Gate |
|---|---|
| Kalshi orderbook endpoint | HTTP 200 with non-empty yes/no fields; mid in [0.01, 0.99] |
| Each LLM vendor returns parseable JSON | >= 90% of sub-agent calls parse successfully |
| Tool fires at least once per sub-agent | >= 80% of calls invoke at least one search call |
| Per-forecast cost | <= $0.05 (for Haiku/Gemini/Groq) or <= $0.15 (for Opus-orchestrated) |
| Foreknowledge judge runs | Judge call executes and returns YES or NO for all 5 markets |

If any vendor fails the smoke test: run with reduced ensemble (remove that vendor, proceed
with remaining). Degrade gracefully; do not abort the full study for one vendor failure.

### Smoke test cost estimate

5 markets x 3 sub-agents (Haiku 4.5 only) = 15 LLM calls at $0.002-0.005 each = $0.03-0.08.
With Opus supervisor pass on 1-2 markets: add $0.10-0.20.
Total smoke test: approximately $0.05-0.15. Well within budget.

---

## 10. Cost Projection

### Per-forecast cost breakdown

| Component | Best case (4 vendors, free tiers) | Current state (Opus+Haiku only) |
|---|---|---|
| Gemini 2.5 Flash sub-agent | $0.00 (free tier) | $0.00 (not available) |
| DeepSeek V4 Flash sub-agent | $0.00 (5M free tokens) | $0.00 (not available) |
| Groq Llama-3.1-70B sub-agent | $0.00 (free tier) | $0.00 (not available) |
| Haiku 4.5 (orchestrator) | $0.002 (1k input + 200 output) | $0.005 (2x calls for phrasing diversity) |
| Opus 4.7 supervisor (30% of forecasts) | $0.03 x 0.30 = $0.009 | $0.03 x 0.30 = $0.009 |
| Foreknowledge judge (Haiku 4.5) | $0.002 | $0.002 |
| Tavily search | $0.00 (free tier) | $0.00 (ESPN fallback) |
| Total per forecast | approximately $0.013 | approximately $0.016 |

**RECOMMENDED ORCHESTRATION: Haiku 4.5 orchestrates; Opus reserved for supervisor pass only.**
This is the key cost-saving change from v9 (which used Opus for every sub-agent at $0.088/call).

### Budget scenarios

| Config | Per-forecast | N=80 | N=150 | N=300 |
|---|---|---|---|---|
| Best case (4 free vendors) | $0.013 | $1.04 | $1.95 | $3.90 |
| Current state (Opus+Haiku) | $0.016 | $1.28 | $2.40 | $4.80 |

With $6-8 remaining LLM budget: N=300 is achievable in both configurations. Even N=400 is
within budget in the best case.

### Remaining LLM budget

Per FINAL-VERDICT.md cumulative spend: approximately $17-19 of $25 cap used. Remaining:
approximately $6-8. V10-B targets $0.50-2.00 total for the forecasting run (50-150 markets
at $0.013-0.016). This leaves $4-6 for Phase 3 critic and any subsequent iterations.

---

## 11. Data Recording Schema

Each forecast record must contain (for scoring):

```json
{
  "ticker": "KXMLBTOTAL-26MAY26...",
  "series": "KXMLBTOTAL",
  "forecast_ts": "2026-05-27T18:00:00Z",
  "close_ts": "2026-05-27T23:00:00Z",
  "days_to_close_at_forecast": 0.2,
  "orderbook_yes_bid": 0.44,
  "orderbook_yes_ask": 0.46,
  "orderbook_mid": 0.45,
  "orderbook_spread": 0.02,
  "p_llm_vendor_1_raw": 0.41,
  "p_llm_vendor_1_platt": 0.38,
  "p_llm_vendor_2_raw": 0.52,
  "p_llm_vendor_2_platt": 0.50,
  "p_llm_ensemble": 0.44,
  "p_v10": 0.44,
  "supervisor_triggered": false,
  "foreknowledge_judge": "NO",
  "odds_api_implied": 0.47,
  "outcome": null
}
```

The `outcome` field is null until resolution. Scoring is run after resolution.

---

## Summary: Pre-Registered Parameters

| Parameter | Value | Source |
|---|---|---|
| Uncertain band | mid in [0.30, 0.70] | AIA MarketLiquid "hard" regime; regime-matched gate |
| Target series | KXMLBTOTAL, KXMLBF5, KXMVESPORTSMULTIGAMEEXTENDED, KXITFWMATCH, KXNBASPREAD, KXNBATOTAL, KXVALORANTGAME, KXMVECROSSCATEGORY, KXATPCHALLENGERMATCH, KXCONMEBOLLIBGAME, KXNHLGAME | v10-S1 confirmed active markets |
| Sub-agents | K=2-4 depending on key availability | Best case: Gemini + DeepSeek + Groq + Opus-supervisor |
| Orchestrator | Haiku 4.5 (or cheapest available) | Cost control; Opus reserved for supervisor only |
| Platt scaling t | sqrt(3) = 1.7320508 per vendor | AIA ablation best single-step |
| Ensemble weight | 0.67 market, 0.33 LLM | AIA Section 5 simplex regression (full set) |
| Kalshi baseline | orderbook mid at forecast time | v7-B phantom lesson (F4) |
| Gate threshold | Brier_delta >= 0.005 | AIA full-set ensemble lift (conservative) |
| Bootstrap samples | 10,000 | Standard |
| Minimum N for gate | 80 resolved markets | Power constraint |
| Target N | 150-300 | 5-week MLB/esports season window |
| LOCO | Required by sport type | F10 LOO fragility prevention |
| Foreknowledge cutoff | Market close_time (operational) + LLM parametric cutoff | Per vendor: Opus Jan 2026, Gemini Apr 2025, DeepSeek late 2024, Llama Apr 2024 |
| Smoke test size | 5 markets | Before main run |
| LLM budget | $0.50-2.00 for forecasts; $6-8 total remaining | Remaining cap |
| Data path | data/v10/B2/ | Separate from v1 and all prior rounds |
| No live capital | All phases | Operator policy |
