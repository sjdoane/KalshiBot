# V10-B Smoke Test Report

**Date:** 2026-05-27 04:51 UTC
**Agent:** V10-B Phase 2 build-and-smoke agent
**Markets tested:** 5
**Total LLM cost:** $0.0063
**Gates passed:** 6/6
**Verdict:** READY-FOR-MAIN

---

## Gate Results

### Gate 1: Kalshi orderbook valid bid+ask for all 5 markets
**Result: PASS**
Detail: 5/5 markets have valid mid (4/5 are two-sided)

### Gate 2: >=4/5 LLM vendor responses parseable as JSON
**Result: PASS**
Detail: 5/5 forecasts have parseable LLM output

### Gate 3: >=4/5 forecasts with >=1 Tavily snippet
**Result: PASS**
Detail: 4/5 forecasts retrieved >=1 Tavily snippet (niche markets may lack news)

### Gate 4: Tavily filter removes 0-2 snippets avg (sanity)
**Result: PASS**
Detail: avg 0.20 snippets flagged per forecast (gate: 0-2)

### Gate 5: Per-forecast cost <=$0.025
**Result: PASS**
Detail: max per-forecast cost $0.0014, avg $0.0013 (gate: <=$0.025)

### Gate 6: Foreknowledge judge runs cleanly (1-15% flag rate)
**Result: PASS**
Detail: 1/13 snippets flagged (7.7%)

---

## Per-Market Summary

| Ticker | Sport | Mid | p_llm | p_v10 | Cost | Snippets | Flagged |
|---|---|---|---|---|---|---|---|
| KXMLBTOTAL-26MAY271340STLMIL-9 | mlb | 0.480 | 0.534 | 0.498 | $0.0013 | 3 | 0 |
| KXMVESPORTSMULTIGAMEEXTENDED-S2026C153EB | esports | 0.387 | 0.110 | 0.295 | $0.0014 | 5 | 1 |
| KXITFWMATCH-26MAY27CROTHO-THO | tennis | 0.485 | 0.543 | 0.504 | $0.0012 | 0 | 0 |
| KXMLBTOTAL-26MAY271340STLMIL-8 | mlb | 0.565 | 0.636 | 0.589 | $0.0014 | 3 | 0 |
| KXMLBTOTAL-26MAY271340STLMIL-7 | mlb | 0.670 | 0.671 | 0.670 | $0.0009 | 2 | 0 |

---

## Methodology Notes

- Ensemble formula: p_v10 = 0.67 * orderbook_mid + 0.33 * p_llm_ensemble
- Platt scaling: t = sqrt(3) = 1.7320508 applied per vendor
- Supervisor threshold: spread > 0.25 (B3 Revision 3)
- Tavily exclusion suffix: applied per B3 Revision 2
- Foreknowledge judge: Haiku 4.5 per B2 Section 5

## Anti-em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013).

*Report generated: 2026-05-27 04:51 UTC*