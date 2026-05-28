# V10-B Methodology Revisions (Phase 1.5 Critic Response)

**Date:** 2026-05-27
**Author:** v10 orchestrator
**Predecessor:** `B2-methodology-lock.md` (the original methodology lock, REVISED below)
**Critic source:** `05-phase1.5-critic.md` Section B
**Status:** Pre-run revisions; no methodology amendment after Phase 2 starts.

---

## Purpose

The Phase 1.5 adversarial methodology critic identified 4 IMPORTANT findings on V10-B before Phase 2 begins. None are KILLER. All require pre-run revision or clarification. This document supplements `B2-methodology-lock.md` with the specific revisions.

The base methodology in B2 stands; only the items below are revised.

---

## Revision 1: Two-tier gate interpretation (B.1)

### Original (B2 Section 8)

Gate criterion: Brier_delta >= 0.005 with 95% bootstrap CI > 0 is SHIP.

### Revised

Two-tier gate, applied to the same point estimate and CI:

- **SHIP**: Brier_delta >= 0.010 AND 95% bootstrap CI strictly positive
- **PARTIAL**: 0.005 <= Brier_delta < 0.010 AND 95% bootstrap CI strictly positive
- **NULL**: Brier_delta < 0.005 OR CI includes zero

### Rationale (per critic B.1)

The AIA hard-subset lift on uncertain markets is 0.014 to 0.019. The full-set lift is 0.005. Our universe is pre-filtered to uncertain (0.30 to 0.70), which is the hard-subset regime. The appropriate benchmark for the uncertain regime is 0.014 to 0.019, not 0.005.

Setting the gate at 0.005 risks calling a marginal noise-floor result a SHIP. The two-tier interpretation honors the regime-matched benchmark while still allowing PARTIAL results to indicate directional signal.

This is a strict tightening of the SHIP threshold, not a relaxation; it cannot retroactively turn a NULL into a PARTIAL.

---

## Revision 2: Tavily price-content exclusion filter (B.3)

### Original (B2 Section 5)

Tool 1: Tavily Search API; query is built from market title and rules text.

### Revised

Every Tavily query has the following suffix appended:

```
-site:kalshi.com -site:polymarket.com -site:predictit.org -site:manifold.markets -site:metaculus.com -betting -"live odds" -sportsbook -DraftKings -FanDuel -BetMGM -Caesars -Pinnacle -Bovada -"prediction market" -odds
```

Plus a post-retrieval LLM-as-judge filter call (Haiku 4.5, ~$0.001 per snippet check) to scan each retrieved snippet for content mentioning:
- Kalshi or Polymarket or Manifold or Metaculus prices or contracts
- Sportsbook odds or moneylines or spreads
- Any "this contract is trading at X cents" phrasing

Snippets flagged by the post-retrieval judge are removed BEFORE assembly into the LLM forecaster prompt. The forecaster never sees flagged content.

### Rationale (per critic B.3)

B2 prohibits Kalshi prices in the LLM prompt directly, but Tavily retrieval may return tweets, news articles, or aggregator pages citing Kalshi or sportsbook prices. This is a backdoor anchoring pathway. The combined Tavily query filter plus post-retrieval judge cuts this off at both the request and ingestion layers.

The Haiku judge cost per forecast: approximately 5-10 snippets per forecast x $0.001 per check = $0.005 to $0.010 per forecast. Budget cost: $0.75 to $1.50 at n=150. Already within the cost projection.

---

## Revision 3: Cost cap at n=150 with supervisor threshold tightening (B.7)

### Original (B2 Section 11)

Target n = 80 to 150. Opus supervisor triggers at spread > 0.15. Estimated 30% supervisor rate at $0.03 per call.

### Revised

- **First run cap: n = 150.** Hard cap; no expansion without explicit operator authorization or completion of a budget audit from the smoke test.
- **Supervisor trigger: spread > 0.25** (raised from > 0.15). Reduces expected supervisor rate from ~30% to ~10-15%, cutting Opus calls by half.
- **Per-forecast cost budget: $0.020.** If actual cost from smoke test exceeds $0.020/forecast averaged over 5 markets, halt and reassess before main run.
- **Total budget hard cap: $3.00 for V10-B.** Includes smoke test, foreknowledge judges, Tavily filter judges, and main forecast batch.

### Rationale (per critic B.7)

Critic's recalculation: at n=300 with 30% supervisor rate, total cost approaches $7.50, exceeding the approximately $3 to $4 remaining LLM budget. At n=150 with the original 30% supervisor rate, cost is approximately $4.80, still above the comfortable budget. The two revisions together (n cap + supervisor threshold) bring expected cost to approximately $2.40 to $3.00.

If the smoke test reveals actual cost is lower than projected, the operator may authorize an expansion. The hard cap protects against budget overrun even if assumptions are wrong.

---

## Revision 4: MLB concentration pre-audit (B.5)

### Original (B2)

LOCO by sport type required for SHIP verdict. Mixed sports: MLB props, NBA props, esports, tennis, soccer, NHL.

### Revised

**Pre-run concentration audit**: Before the main forecast batch, count the candidate uncertain-band markets by sport type after applying all other filters (close_time, mid range, denylist).

Concentration rules:
- If any single sport type produces > 50% of the candidate queue, actively under-sample MLB to bring the share to <= 50%.
- Reserve at least 15% of n for each of the following sport groups: (esports, tennis + soccer combined, NBA, MLB). NHL is optional (small n expected).
- If any sport group cannot supply 15% of n (e.g., esports has fewer than 22 markets at n=150), document the gap and reduce target n proportionally to maintain the balance ratio.

**LOCO consequence statement (mandatory in final report regardless of result)**:
If LOCO-MLB drops the remaining sample below n=80 and the bootstrap CI includes zero, the verdict is PARTIAL-WITH-LOCO-FRAGILITY. Cannot SHIP regardless of overall delta. This must be stated in the V10-B FINAL-VERDICT.md.

### Rationale (per critic B.5)

The original LOCO criterion is meaningful only if the sample is balanced across sport types. With MLB dominance the most likely scenario (high open-market count, daily resolution, well-populated uncertain band by construction), LOCO-MLB will mechanically force PARTIAL. The pre-run balance audit gives the methodology a chance to actually pass the SHIP gate; the LOCO consequence statement ensures honesty if the balance audit fails.

---

## Acknowledged but accepted as-is

### Power is partial (B.2)

Critic computed approximately 10 to 17% statistical power at n=150 to 380 against a true delta of 0.014. B2 acknowledged this. Operator was explicitly informed at Phase 0 that V10-B is a "session pilot, results pending over 1-5 weeks." The partial-power design is accepted.

**Explicit interpretation rule**: A NULL verdict at n=80-150 is NOT evidence of no edge. It is uninformative. Only PARTIAL or SHIP verdicts are evidentially meaningful in this round.

### Vendor calibration heterogeneity is a known approximation (B.6)

Default Platt parameter t = sqrt(3) applied to all 4 vendors. Per-vendor calibration would require >= 100 markets of training data which we do not have. This is the AIA Forecaster recipe's default. Document as a known approximation.

### Resolution timeline is acceptable (B.8)

Operator approved the prospective design at Phase 0. Same-day MLB markets give a directional read in 24 to 48 hours; the 7-30 day markets resolve over the 1-5 week window. No revision needed.

### Baseline Brier may differ from AIA's 0.111 (B.9)

The critic flagged that uncertain-band sports markets may have baseline Brier closer to 0.22 to 0.25 than AIA's 0.111. The power estimate may be miscalibrated. The fix: compute the actual baseline Brier from the first 30 resolved smoke-test and pilot markets and re-evaluate power before committing the full batch.

This is a Phase 2 monitoring task, not a Phase 1.5 amendment.

---

## Summary of binding changes

| Item | Before | After |
|---|---|---|
| SHIP gate | Brier_delta >= 0.005 with CI > 0 | Brier_delta >= 0.010 with CI > 0 |
| PARTIAL gate | (not specified) | 0.005 <= Brier_delta < 0.010 with CI > 0 |
| Tavily query | Built from market title alone | Append exclusion filter; post-retrieval judge |
| n target | 80 to 150 (flexible) | 150 hard cap on first run |
| Supervisor threshold | spread > 0.15 | spread > 0.25 |
| LLM budget | Implicit ~$2-5 | $3.00 hard cap |
| Sport balance | LOCO sport-stratified | Pre-run concentration audit; max 50% any single sport; reserve 15% per sport group |
| LOCO consequence | (not specified) | LOCO-MLB CI > 0 violation = PARTIAL-WITH-LOCO-FRAGILITY, cannot SHIP |

---

## Phase 2 smoke test gate (unchanged from B2 but reinforced)

Before the main run, execute 5-market smoke test. Hard gates:

1. Kalshi orderbook returns valid bid+ask for all 5 markets
2. >= 4 of 5 LLM vendor responses parseable as valid JSON
3. >= 4 of 5 forecasts complete with at least one Tavily search result retrieved
4. Tavily filter (B.3 above) removes 0 to 2 snippets per forecast on average (sanity check that filter is active but not over-aggressive)
5. Per-forecast actual cost <= $0.025 (1.25x revised projection)
6. Foreknowledge judge runs cleanly with non-trivial flag rate (1-15% flagged; if 0% or > 30%, judge is broken)

If any hard gate fails, halt and report to operator. Do NOT proceed to main run.

---

## Anti-em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013) throughout.
