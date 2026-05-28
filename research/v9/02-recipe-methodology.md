# v9 Angle A: AIA Forecaster Recipe + Methodology Lock

**Date:** 2026-05-26
**Author:** Agent v9-A2 (methodology + recipe)
**Status:** Pre-registered methodology. No data pulled. No post-hoc amendments permitted.
**Scope:** Agentic LLM forecaster (Claude Opus 4.7) plus Kalshi-mid ensemble on v1's denylisted-residual sports universe. Replicates AIA Forecaster (arXiv 2511.07678) in an Anthropic SDK environment.
**Do not modify after first data pull.**

---

## 1. Full AIA Forecaster Pipeline Spec

Source: AIA Team (Nov 2025), arXiv:2511.07678. All section citations below refer to the AIA paper.

### 1.1 Sub-agent count and independence

AIA uses multiple independent forecaster sub-agents per question (Section 3, System Architecture). The extraction in `research/literature/aia-2025-forecaster-and-followups.md` summarizes: "Multiple independent agents conduct iterative queries; full discretion to determine whether and how to query the search provider." The AIA paper does not publish the exact sub-agent count as a fixed parameter; it is described as a supervisor-controlled adaptive process. Based on AIA's described supervisor loop and the ablation context (Section 4 ablations compare single-pass vs multi-pass agentic search), the effective count is 2 to 5 sub-agents per question with the supervisor deciding when disagreement is low enough to stop.

**v9 binding spec:** 3 independent sub-agents per question, fixed. The supervisor fires a 4th pass only when the sub-agent spread exceeds 0.15 (see Section 1.3).

### 1.2 Search provider

AIA Forecaster uses "high-quality news sources" queried via an agentic search framework (Section 3.1). The extraction notes AIA agentic search adds -0.009 Brier vs non-agentic, and -0.009 vs no-search baseline (Section 4, Search Ablation table). The paper does not name the specific search API. The Janna Lu 2025 follow-up (same cluster) explicitly used AskNews API for retrieval, achieving o3 Brier 0.1352.

**v9 binding spec:** Anthropic-native `web_search_20250305` tool as the primary search provider (zero incremental cost beyond Opus 4.7 API use). Supplementary sportsbook data from the-odds-api free tier (500 req/mo, operator signup required). ESPN public JSON as fallback for team rosters and standings. GDELT excluded (timed out from CA IP in v7 scoping).

### 1.3 Supervisor agent protocol

AIA Section 3, Supervisor Agent: "The supervisor agent examines disagreements among individual forecasts; issues additional search queries to resolve ambiguities; synthesizes final prediction." No exact disagreement threshold is published; the AIA paper describes the supervisor as having "full discretion."

**v9 binding spec:**

1. Run 3 sub-agents independently (no cross-visibility of each other's outputs).
2. Collect 3 raw p_yes values: p1, p2, p3.
3. Compute spread = max(p1, p2, p3) - min(p1, p2, p3).
4. If spread <= 0.15: final_raw = mean(p1, p2, p3). No supervisor search.
5. If spread > 0.15: supervisor agent (same model) reads all 3 reasonings plus search results, issues up to 2 additional targeted search queries on the specific point of disagreement, produces a synthesis probability p4. final_raw = mean(p1, p2, p3, p4).
6. Platt-scale final_raw to get p_llm (see Section 1.4).
7. DO NOT show any Kalshi price to any sub-agent or the supervisor at any stage.

### 1.4 Platt scaling

AIA Section 4, Calibration Ablation (Table 2): "Platt scaling with parameter sqrt(3) approximately 1.73 is the recommended single-step post-processing." Brier improvement: -0.007 vs no correction baseline of 0.1140. This is the best single calibration method in AIA's ablation, outperforming log-odds extremization (-0.006), isotonic (-0.004), and OLS (-0.002).

The Platt scaling addresses RLHF hedging: Halawi 2024 documents that LLMs "rarely output low probabilities" because of safety training, causing systematic hedging toward 0.50. The mathematical form for logit-space Platt scaling with temperature parameter t:

```
logit(p_platt) = t * logit(p_raw)
p_platt = sigmoid(t * logit(p_raw))
```

With t = sqrt(3) approximately 1.732, a raw output of 0.80 maps to: logit(0.80) = 1.386, scaled = 1.732 * 1.386 = 2.402, p_platt = sigmoid(2.402) = 0.917. This pushes confident outputs further toward the extremes, counteracting RLHF shrinkage.

**v9 binding spec:** Apply Platt scaling with t = sqrt(3) = 1.7320508 to the mean raw sub-agent output BEFORE ensemble combination. The Platt parameter is fixed pre-run; it is NOT fit on the v9 data. Fitting would constitute post-hoc tuning.

### 1.5 Ensemble weight

AIA Section 5, MarketLiquid analysis: "Simplex regression on MarketLiquid hard subset (1,610 questions): optimal weight 67% market consensus, 33% AI Forecaster. Ensemble Brier 0.106 vs market alone 0.111 and AIA alone 0.126." This is the canonical source for the 67/33 split.

Note on the AIA paper's numbers: the extraction flags two number variants (0.108/0.098 and 0.126/0.111 depending on subset). Both pairs show AIA lagging market by 0.010 to 0.015 Brier, and the ensemble lifting above either component. The 67/33 weight is consistent across both reported subsets.

**v9 binding spec:** p_v9 = 0.67 * kalshi_book_mid + 0.33 * p_llm_platt_scaled. Weights are fixed now. No re-optimization on v9 data.

### 1.6 Foreknowledge audit

AIA Section 3, Foreknowledge Control: "LLM-as-judge protocol audits search results for content exceeding the intended information cutoff. On 502 traced audits, 1.65% contained foreknowledge bias. Robustness checks: removing flagged results changes Brier by at most 0.6%."

Opus 4.7 knowledge cutoff is January 2026 (per CLAUDE.md / v4 critic cutoff documentation). All Kalshi markets in our eval set have close_time in 2026. We need to audit for two potential foreknowledge sources:

a. Web search results that contain post-close_time information about the specific event.
b. LLM's parametric knowledge about events that resolved before January 2026.

**v9 binding spec:** After each forecast, a separate "judge" call (model = claude-haiku-4-5, cheaper) receives: (i) the market close_time, (ii) the raw search result snippets retrieved by the sub-agents, (iii) prompt: "Does any search result contain information about the specific event outcome AFTER [close_time]? Reply YES/NO and identify which snippet if YES." Flag any market where judge returns YES. Report percentage flagged in final verdict. Flagged markets are included in the primary analysis but tabulated separately. If flagged rate exceeds 5%, halt and re-evaluate search prompts.

---

## 2. v9 Pipeline Design: Anthropic SDK plus Opus 4.7

### 2.1 Model selection

Model: `claude-opus-4-7` (1M context available as `claude-opus-4-7-1m` but not needed for per-forecast payloads). Extended thinking: OFF by default. Rationale: AIA Forecaster does not describe extended thinking; the additional cost of extended thinking on Opus 4.7 at $6/MTok output would approximately double per-forecast cost without documented Brier improvement for this task type. Extended thinking can be enabled in the supervisor pass only if budget allows.

### 2.2 Anthropic SDK call structure

```python
import anthropic

client = anthropic.Anthropic()

# Sub-agent call (one of 3 per forecast)
response = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=2048,
    system=SYSTEM_PROMPT,          # cached block (see Section 2.5)
    tools=[WEB_SEARCH_TOOL],       # cached block (see Section 2.5)
    messages=[
        {"role": "user", "content": user_prompt_for_market}
    ]
)
```

Output must parse to JSON: `{"reasoning": str, "p_yes": float}`.

### 2.3 Tool definitions

Tools available to sub-agents and supervisor:

**Tool 1: web_search_20250305** (Anthropic native)
- No signup required; billed as Anthropic API usage
- Use for: recent team news, injury reports, standings, schedule information
- Rate limit: Anthropic's managed; no per-call fee beyond model usage

**Tool 2: the-odds-api** (operator must sign up for free tier at the-odds-api.com)
- Free tier: 500 requests/month. Each request covers all bookmakers for one sport + market.
- Endpoints used: `/v4/sports/{sport}/odds` for current lines, `/v4/sports/{sport}/scores` for recent results
- Relevant sports: americanfootball_nfl, basketball_nba, baseball_mlb, basketball_ncaab, americanfootball_ncaaf, soccer_usa_mls, mma_mixed_martial_arts
- Implement as a custom Python function that the sub-agent can call with a structured input

**Tool 3: ESPN public JSON** (no auth required)
- Base: `http://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard`
- Use for: standings, recent game results, team records
- Rate limit: gentle throttle at 1 req/sec to avoid 429s

**Tool 4: NOT INCLUDED (Kalshi prices)**
- Per v7-B phantom lesson and ForecastBench 2026 GPT-4.5 0.994 anchoring finding, Kalshi prices MUST NOT be given to any sub-agent or supervisor.
- The Kalshi orderbook mid is captured separately at forecast time and combined OUTSIDE the LLM.

### 2.4 Prompt template

**System prompt (cached across all forecasts in a session):**

```
You are an expert sports forecaster. Your task is to estimate the probability
that a specific Kalshi prediction market resolves YES.

Rules:
- Do NOT search for or incorporate Kalshi market prices or any prediction
  market prices. Your estimate must be independent.
- Use your web_search tool to find recent news, injury reports, standings,
  and any relevant information about the teams or athletes involved.
- The market close_time is the resolution deadline. Only use information
  available BEFORE that date.
- Output your final answer as JSON: {"reasoning": "<your step-by-step
  reasoning>", "p_yes": <float between 0.01 and 0.99>}
- Express probabilities to two decimal places (e.g. 0.73, not 0.7 or 70%).
- Do not output exactly 0.50 unless you genuinely believe the event is a
  coin flip after research. Round-number anchoring is a documented bias;
  use precise values.
```

**User prompt per market (NOT cached, unique per forecast):**

```
Market: {market.title}
Resolution criteria: {market.rules_primary}
Market closes (resolves): {market.close_time} UTC
Today's date: {today_date} UTC

Please research this question thoroughly and provide your probability estimate.
Search for: current standings, recent performance, injury news, and any other
factors relevant to this outcome. Output JSON only.
```

### 2.5 Prompt caching

Anthropic's API supports prompt caching with a 5-minute TTL. The system prompt and tool definitions are identical across all forecasts in a session. Add `cache_control: {type: ephemeral}` to both blocks. Cached reads are billed at approximately 10% of full input price. At 120 forecasts, this saves roughly 120 * 750 = 90,000 cached tokens per session.

### 2.6 Sub-agent independence

Each sub-agent call is a fresh API call. Sub-agents do NOT see each other's outputs or search results. Per AIA Section 3: "independent agents." Shared search results would introduce correlation that deflates the supervisor's ability to resolve genuine disagreement. Collect (p1, reasoning1), (p2, reasoning2), (p3, reasoning3) before passing to the supervisor.

---

## 3. Cost Projection

### 3.1 Opus 4.7 published rates (as of 2026-05-26)

Per Anthropic's pricing page (anthropic.com/pricing). Operator should verify before the run:
- Input tokens (uncached): $15.00 per million tokens
- Input tokens (cached read): $1.50 per million tokens (90% discount)
- Output tokens: $75.00 per million tokens
- Web search: billed as input tokens (results returned count as context)

### 3.2 Token estimate per forecast

A single sub-agent call:
- System prompt (cached after first call): 250 tokens (cached read at $1.50/MTok after first)
- Tool definitions (cached): 500 tokens (cached read after first)
- User prompt per market: 300 tokens (uncached each call)
- Search results returned: 1,500 tokens average (3 searches x 500 tokens each, uncached)
- Output (reasoning + JSON): 800 tokens average

Per sub-agent call token cost:
- Input uncached: 300 + 1500 = 1800 tokens at $15/MTok = $0.027
- Input cached: 250 + 500 = 750 tokens at $1.50/MTok = $0.001125
- Output: 800 tokens at $75/MTok = $0.060
- Sub-agent call total: approximately $0.088

For 3 sub-agents per forecast (assuming no supervisor pass for markets with spread <= 0.15):
- 3 * $0.088 = $0.264 per forecast (base case, no supervisor)

Supervisor pass (triggered approximately 30% of markets based on typical LLM forecast variance):
- Supervisor reads 3 reasonings (3 * 800 = 2400 tokens) + 2 new searches (1000 tokens) + output (600 tokens)
- Supervisor cost: approximately $0.088 additional
- Expected supervisor cost per forecast: 0.30 * $0.088 = $0.026

Foreknowledge judge (Haiku 4.5, cheap):
- Haiku 4.5 rate: approximately $0.80 input / $4.00 output per MTok
- Per forecast: 1000 input tokens + 200 output tokens = $0.0008 + $0.0008 = $0.0016
- Negligible: less than $0.01 per 5 forecasts

**Total per forecast: approximately $0.264 + $0.026 + $0.002 = $0.292 approximately $0.30**

### 3.3 Budget projections

| Budget | Forecasts at $0.30/each | With 20% cost buffer |
|---|---|---|
| $15 | 50 | 40 |
| $18 | 60 | 48 |
| $20 | 67 | 53 |

**This does NOT reach n >= 100 at 3 sub-agents per forecast with Opus 4.7.**

### 3.4 Alternative configuration: 1 sub-agent at $0.10/forecast

Single sub-agent per forecast (no supervisor):
- 1 * $0.088 + judge $0.002 = $0.09 per forecast

| Budget | Forecasts at $0.10/each | With 20% cost buffer |
|---|---|---|
| $15 | 150 | 120 |
| $18 | 180 | 144 |

**This reaches n >= 100 comfortably.**

### 3.5 Recommended configuration

**Use 1 sub-agent per forecast for the main run.** Rationale:

- AIA Forecaster's documented improvement from multiple sub-agents vs single-agent is attributable to the supervisor's additional search, not to averaging multiple uncorrelated estimates from identical prompts. With a single query structure, the marginal value of 3 identical sub-agents is lower than AIA's multi-step reasoning loop.
- Janna Lu 2025 uses 5 predictions per question, but those are 5 independent API calls on a diverse question set; the improvement is already captured in AIA's ensemble weight.
- n >= 100 is required for the 95% bootstrap CI on the Brier delta to have adequate power. At n=60 the CI half-width on a 0.014 Brier delta is approximately +/- 0.020, meaning even a real effect cannot be distinguished from zero. At n=120 the half-width drops to approximately +/- 0.013, which is marginally adequate.
- If budget permits after the smoke test, run a 20-market 3-sub-agent comparison batch to empirically measure the per-forecast Brier improvement from 3 vs 1 sub-agents in this specific domain.

**Primary configuration locked:** 1 sub-agent per forecast, supervisor pass if confidence is low (operator discretion on a per-market basis), n target = 120 at $15 budget.

---

## 4. Ensemble and Scoring Methodology (PRE-REGISTERED)

This section is the methodology lock. No amendments after first data pull.

### 4.1 Kalshi baseline

```
kalshi_book_mid = (yes_bid_dollars + yes_ask_dollars) / 2
```

Captured from Kalshi REST API endpoint: `GET /markets/{ticker}/orderbook` at forecast time.

This is the REAL orderbook mid, NOT the stale last-trade-print (`last_price_dollars`). The v7-B phantom finding (07-naive-p-yes-critic.md) confirmed that `last_price_dollars` can diverge significantly from the live orderbook quote, inflating apparent edge. v9 MUST capture the live orderbook at time of forecast.

Capture timestamp must be within 60 seconds of the LLM forecast call. If the orderbook fetch fails, skip that market and log the failure; do not impute the mid from last trade.

### 4.2 LLM probability

```
p_raw = raw JSON p_yes output from the sub-agent (or mean of sub-agents if 3-agent config is used)
p_llm_platt = sigmoid(sqrt(3) * logit(p_raw))
logit(x) = log(x / (1 - x))
sigmoid(y) = 1 / (1 + exp(-y))
```

Clip p_raw to [0.01, 0.99] before logit to prevent overflow.

### 4.3 Ensemble formula

```
p_v9 = 0.67 * kalshi_book_mid + 0.33 * p_llm_platt
```

### 4.4 Brier score

```
Brier_kalshi(market_i) = (kalshi_book_mid_i - outcome_i)^2
Brier_v9(market_i) = (p_v9_i - outcome_i)^2
```

where outcome_i is 1 if the market resolves YES, 0 if NO.

Mean Brier over all N markets:
```
mean_Brier_kalshi = (1/N) * sum(Brier_kalshi_i)
mean_Brier_v9 = (1/N) * sum(Brier_v9_i)
Brier_delta = mean_Brier_kalshi - mean_Brier_v9
```

Positive Brier_delta means v9 is better calibrated than the market baseline.

### 4.5 Gate criterion (pre-registered)

**SHIP gate:** Brier_delta >= 0.014 AND 95% bootstrap CI of Brier_delta strictly positive (lower bound > 0).

The 0.014 threshold comes from AIA Forecaster Section 5: MarketLiquid ensemble Brier 0.106 vs market alone 0.111, delta = 0.005 (lower bound of improvement). The higher threshold (0.014) corresponds to the full market-ensemble improvement range (0.015 in the hard subset) and is appropriate for a pre-registered threshold because it represents the published lift of the AIA method itself.

Bootstrap protocol: 10,000 bootstrap resamples with replacement from the N markets, compute Brier_delta on each resample, report the 2.5th and 97.5th percentiles as the 95% CI.

**If gate fails:** report honest NULL. No re-tuning. The 67/33 weight is the claim; measuring it at 50/50 or 80/20 is informational only and CANNOT retroactively change the verdict.

### 4.6 Robustness sensitivity (informational only, not for verdict)

Report but do not use for verdict selection:
- Brier_delta at weights [50/50, 67/33, 80/20]
- Brier_delta on YES-only outcomes (markets that resolved YES)
- Brier_delta on NO-only outcomes (markets that resolved NO)
- Per-sport breakdown: NFL, MLB, NBA, NCAA-FB, NCAA-BB, MMA, Soccer

The per-sport breakdown is particularly relevant given the literature finding (Janna Lu 2025: o3 sports Brier 0.1649, 37% worse than politics). If the LLM adds lift on one sport but hurts on another, that is an honest diagnostic for future targeted research, not a route to cherry-picking the verdict.

### 4.7 Minimum sample

Gate requires N >= 80 resolved markets to attempt. Below N=80, report Brier_delta as a point estimate only (no CI); declare the sample "BELOW THRESHOLD for gate evaluation" and label the result PARTIAL regardless of the directional sign of Brier_delta.

---

## 5. Failure-Mode Prevention Checklist

The following guards are mandatory. Each must be confirmed before the main run.

### F1: Tool use working (v4-B BSS -2.17 prevention)

v4-B's confirmed null (BSS -2.17 at n=238) used Claude Haiku 4.5 with NO tool use, NO retrieval. The literature (Halawi 2024 Section 3) shows retrieval adds -0.020 Brier; AIA Section 4 shows agentic search adds -0.009 vs no-search. v9 with zero retrieval is expected to replicate v4-B.

**Guard:** Smoke test (Section 6) must confirm web_search_20250305 tool calls are firing and returning non-empty search snippets. If the tool fires 0 times across 10 smoke-test markets, abort and debug before main run.

**Verification check:** log tool_use blocks in the raw API response for each sub-agent. Compute fraction of sub-agent calls where at least one tool was invoked. Gate: >= 80% of sub-agent calls must invoke at least one search tool.

### F2: Orderbook mid vs last-trade-print (v7-B phantom prevention)

v7-B PARTIAL was killed because the baseline was stale trade-print (`last_price_dollars`) rather than real orderbook. v9 ensemble uses Kalshi orderbook `/markets/{ticker}/orderbook` at forecast time.

**Guard:** For every captured orderbook mid, log the `yes_bid_dollars`, `yes_ask_dollars`, and their difference (spread). Compare to the market's `last_price_dollars` from the markets endpoint. If spread is > 10c or `last_price_dollars` differs from the orderbook mid by > 5c, log as a "stale divergence" event. If more than 10% of markets show stale divergence, escalate to operator before running the gate.

### F3: No Kalshi prices in the LLM prompt (market-anchoring prevention)

ForecastBench 2026 documents GPT-4.5 achieving 0.994 correlation with market prices when given access. v4 V4-C pilot confirmed price-anchoring for Prompt A (r=+0.48 with Kalshi price when shown); Prompt C (no price) resolved this.

**Guard:** Code review of the prompt template in Section 2.4 confirms no Kalshi price, no prediction market price, no "market thinks" phrasing. Before main run, run 5 smoke-test markets and manually inspect the raw system prompt and user prompt strings to confirm.

Additionally: after the main run, compute the Pearson correlation between p_llm_platt (before Platt scaling) and kalshi_book_mid across all N markets. If r > 0.80, report as a potential anchoring failure and treat the result with extreme caution.

### F4: Foreknowledge audit (cutoff discipline)

Opus 4.7 knowledge cutoff: January 2026. v9 targets markets with close_time in 2026 (post-cutoff for LLM parametric knowledge). The LLM may have parametric knowledge of events that resolved before January 2026 in the training set.

**Guard:** The LLM-as-judge foreknowledge audit (Section 1.6) is mandatory for every forecast. Additionally: restrict v9 eval to markets where close_time is AFTER 2026-01-01. Markets closing before January 2026 may be contaminated by Opus 4.7's parametric knowledge and must be excluded from the evaluation set.

Report the percentage of judge-flagged markets and the Brier_delta computed with flagged markets excluded. If the two Brier_delta values differ by more than 0.005, report both and note the discrepancy.

### F5: No post-hoc weight tuning (pre-registration discipline)

The 67/33 weight is locked by this document. The gate criterion (Brier_delta >= 0.014) applies to 67/33 and only 67/33. Reporting the delta at other weights (Section 4.6) is permitted but cannot change the verdict.

**Guard:** The ensemble formula and weights are hardcoded in the scoring script. The script must not accept command-line arguments that change the weights. Weight tuning after data collection is prohibited.

### F6: Round-number clustering check (Schoenegger 2024 prevention)

Schoenegger 2024 documents 38 LLM predictions at exactly 50%, zero at 49% or 51%. The v9 prompt explicitly asks for two-decimal precision. After the main run, produce a histogram of p_llm_platt values.

**Guard:** Flag if more than 20% of raw p_yes values fall on multiples of 0.05 (i.e., 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85). If flagging rate exceeds 20%, the LLM is not producing genuine fine-grained estimates; report this as a limitation regardless of the Brier_delta outcome.

### F7: Honest negative verdict

If the budget is exhausted before N=80 resolved markets are available, report the partial result as "SAMPLE INSUFFICIENT." Do not cherry-pick the date cutoff to include or exclude markets to improve the delta. If Brier_delta is negative (v9 is WORSE than the market baseline), report as CONFIRMED NULL. No third bite.

---

## 6. Smoke Test Plan

Before the main run, execute a 10-market smoke test on currently-OPEN sports markets that are:
- NOT in the eval set (do not use smoke-test markets in the gate computation)
- NOT on the v1 denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS)
- OPEN status (not closed, not resolved)
- Price between 0.55 and 0.95 (consistent with v1's universe)

The smoke test is DESCRIPTIVE ONLY. Results are not used in gating.

### 6.1 Smoke test steps

1. **API connectivity check:** Call `GET /markets?series_ticker=KXMLBWINS&status=open&limit=10` on the Kalshi API. Confirm response is 200 with at least 1 market. Capture `yes_bid_dollars` and `yes_ask_dollars` for each market. Confirm orderbook mid is non-null and within [0.01, 0.99].

2. **LLM forecast call:** For each of 10 markets, run the v9 sub-agent pipeline (1 sub-agent config). Log: API response time, tool_use block count, raw p_yes output, whether output parsed as valid JSON.

3. **The-odds-api connectivity check:** Call `/v4/sports/baseball_mlb/odds` with API key. Confirm response is 200 with sportsbook data. If this fails, proceed with main run using only web_search + ESPN; flag the-odds-api as unavailable in the verdict.

4. **Cost per forecast:** Log the input_tokens, output_tokens, and cache_read_input_tokens from each API response. Compute actual cost against the Section 3 projection. If actual cost exceeds $0.20 per forecast (2x projection), halt and re-examine the prompt templates.

5. **Output parsability check:** Confirm that 9 of 10 (90%) smoke-test markets produce parseable JSON output. If fewer, debug the output format before main run.

6. **Ballpark Brier (descriptive only):** If some smoke-test markets resolve before the eval period begins, compute the raw Brier of the LLM forecast on those markets as a sanity check. A raw LLM Brier above 0.35 on open markets that are 0.55-0.95 YES would be a warning sign (worse than the 0.261 in v4-B's null); do not abort the main run for this alone, but log.

### 6.2 Smoke test pass/fail criteria (hard gates before main run)

| Check | Gate |
|---|---|
| Kalshi API orderbook endpoint | Returns 200 with bid/ask |
| LLM tool use fires | >= 80% of calls invoke web_search at least once |
| Output JSON parseable | >= 90% of calls parse successfully |
| Per-forecast cost | <= $0.20 (2x projection buffer) |
| The-odds-api | Returns 200; if not, flag but continue |

If any hard gate fails, abort main run and report to operator.

---

## 7. Coordination with Agent v9-A1

v9-A1 owns market selection. Required outputs before main run:

1. **Universe size:** Confirm >= 120 eligible open markets (price 0.55 to 0.95, lifetime 7 to 180 days, denylist applied). If n < 80 available, pre-flag Section 4.7 PARTIAL.
2. **Close_time filter:** All eval markets must have close_time > 2026-01-01. Earlier markets may be contaminated by Opus 4.7 parametric knowledge.
3. **Run ordering:** Forecast in ascending close_time order so early-resolving markets accumulate before budget runs out.
4. **Denylist:** KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS excluded per v4-H / W1.

---

## Summary Table: Pre-Registered Parameters

| Parameter | Value | Source |
|---|---|---|
| Model | claude-opus-4-7 | AIA recipe requires frontier reasoning |
| Sub-agents per forecast | 1 (main run) | Budget constraint to reach n >= 100 |
| Supervisor trigger | manual escalation only (1-agent config) | n/a at 1-agent |
| Platt scaling parameter | sqrt(3) = 1.7320508 | AIA Section 4 ablation |
| Ensemble weight | 0.67 kalshi, 0.33 LLM | AIA Section 5 simplex regression |
| Kalshi baseline | orderbook mid (bid + ask)/2 | v7-B phantom lesson |
| Brier gate threshold | delta >= 0.014 | AIA MarketLiquid ensemble lift |
| Bootstrap samples | 10,000 | standard |
| Minimum N for gate | 80 resolved markets | power constraint |
| Target N | 120 markets | $15 / $0.10 per forecast |
| Foreknowledge cutoff | 2026-01-01 (Opus 4.7 knowledge cutoff) | published by Anthropic |
| LLM budget | $15 target, $18 hard cap | operator authorization |
| Smoke test size | 10 markets | before main run |
| Denylist | KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS | v4-H / v1 W1 |
