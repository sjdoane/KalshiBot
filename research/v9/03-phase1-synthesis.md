# v9 Phase 1 Synthesis and Decision Point

**Date:** 2026-05-26
**Author:** v9 orchestrator (post 3-agent Phase 1)
**Predecessor docs:** `00-v10-candidate-angles.md`, `01-data-universe.md`, `02-recipe-methodology.md`
**Status:** Phase 1 complete. Phase 1.5 methodology lock blocked pending operator decision on scope.

---

## Headline

Phase 1 surfaced a structural feasibility gap in v9 Angle A as originally scoped: **the universe and timeline do not produce a session-final verdict at the pre-registered +0.014 Brier threshold.** Two of the three angle-A components (recipe, cost) are healthy. The third (data universe) collapses on contact with the post-Opus-cutoff Kalshi sports market structure.

This document presents the gap honestly and asks for a scope decision before methodology lock.

---

## What worked

**Recipe (v9-A2):** clean. Locked pipeline: 1 sub-agent per forecast at approximately $0.10 (Opus 4.7 with web_search_20250305 + the-odds-api + ESPN tools, Platt scaling t = sqrt(3), 67/33 ensemble, foreknowledge audit via Haiku 4.5 judge). At a $15 LLM cap this yields approximately 120 forecasts. All seven failure-mode guards documented (v4-B no-tools, v7-B stale-mid, market-anchoring, foreknowledge, post-hoc tuning, round-number clustering, honest negative).

**Data sources (partial):** the-odds-api key already in `.env` with 477 of 500 free credits remaining. ESPN site.api returns 200 OK for all six sports endpoints from this host. GDELT now reachable (HTTP 429 rate-limit, not the v7 timeout). Kalshi orderbook endpoint returns 200 OK on open markets with `yes_bid_dollars`, `yes_ask_dollars`, derivable yes_ask via `1.0 - no_bid` parity.

**v10 scouting:** done. 9 candidates scored. Top-3: (1) v8-A prospective recovery, (2) sportsbook line movement on game-resolution markets, (3) sports microstructure on game-resolution series. No candidate priced above 22% prior. Pre-decision zero-cost checklist identified: v8-A analysis pass, Polymarket depth probe, GDELT re-probe.

---

## What broke

### Break 1: historical Kalshi orderbook is structurally unavailable

`/markets/{ticker}/orderbook` returns an empty book for any settled market. The `?ts=` parameter is silently ignored (the endpoint returns the current live book). The trade history endpoint returns prints, not orderbook quotes.

Implication: **the v7-B phantom prevention rule (use real orderbook mid, not stale trade-print) eliminates the entire retrospective backtest option.** Without historical orderbook, the only honest baseline for a backtest is the trade-print mid, which IS the v7-B phantom we are trying to avoid.

### Break 2: v1's denylisted-residual sports universe is seasonal

The four series that drive v1's W2 residual edge (KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF, KXNFLGAME) have zero settled markets in the post-Opus-cutoff window (2026-01-15 to 2026-05-26):

| Series | Last close_time | Notes |
|---|---|---|
| KXNBAWINS | 2026-04-13 (NBA season end) | 200 settled but ALL pre-cutoff or no-mid-band |
| KXMLBWINS | November 2025 | Before Opus cutoff |
| KXNCAAFPLAYOFF | January 2026 | Cutoff boundary, 8 markets in W2 |
| KXNFLGAME | September 2025 to January 2026 | Before cutoff |

The post-cutoff settled sports universe is dominated by KXBOXING (132 settled) and KXUFCFIGHT (200 settled), with only 5 of 594 total settled markets in v1's [0.70, 0.95] band.

### Break 3: prospective F2 universe is 56x underpowered

Currently-open v1-eligible sports markets closing 2026-05-27 to 2026-06-30: **n = 87**, distributed:

| Series | n | Sports |
|---|---|---|
| KXUFCFIGHT | 11 | MMA |
| KXWCGAME | 4 | World Cup qualifying soccer |
| KXPGAUSO | 4 | PGA U.S. Open |
| KXNHL* awards | 3 | NHL season-end awards |
| Other tail | 65 | Mixed |

At n = 87, SE_Brier = 0.054 and the minimum detectable Brier delta at 80 percent power, alpha 0.05, is 0.088. The pre-registered AIA target is 0.014, which is **6x below the detection floor**. To detect 0.014 at 80 percent power, n must be approximately 1,300 (AIA's own MarketLiquid sample was approximately 3,000 per subcategory).

Resolutions arrive on a rolling basis 2026-05-27 to 2026-06-30. **No in-session verdict is achievable on the pre-registered gate.**

---

## What this means for the pre-registered gate

The pre-registered gate as drafted in A2 Section 4.5 requires Brier_delta >= 0.014 with 95 percent bootstrap CI strictly positive. Three things this cannot do at n = 87:

1. **Pass cleanly.** Even if true delta is exactly 0.014, the bootstrap CI half-width at n = 87 is approximately +/- 0.10; the lower bound will almost certainly include zero unless delta is closer to 0.10. That's a 7x-bigger signal than the AIA Forecaster ever measured on hard MarketLiquid markets.
2. **Fail cleanly.** A small negative or zero delta at n = 87 produces a CI that includes both +0.10 and -0.10. We could not honestly call NULL.
3. **Distinguish phantom from real.** The literature evidence (Janna Lu 2025: o3 sports Brier 0.165; Future-is-Unevenly-Distributed: Claude 3.7 sports Brier 0.28) suggests the LLM forecaster will produce a HIGH baseline Brier and the 67/33 ensemble will be dragged toward market price. The expected delta is probably in the +0.005 to -0.020 range, which is invisible at n = 87.

A pre-registered methodology with a gate that cannot fire is not a methodology; it is data collection.

---

## What COULD still produce a session verdict

Three modifications, each with trade-offs:

### Modification M1: prospective pilot WITHOUT a binding gate

**Change:** drop the pre-registered +0.014 SHIP gate. Instead, report Brier_delta with 95 percent CI at n = 87 (when full resolution arrives by 2026-06-30) and an in-session interim at whatever n is resolved by the operator's chosen checkpoint. The "verdict" becomes either (a) "directional pilot supportive, continue infrastructure for 2026-27 season at n approximately 1,000" or (b) "directional pilot null or negative, kill at $8-15 spend."

Cost: approximately $8-15 LLM. Wall-clock: 5 weeks to full data; 1 to 2 weeks for partial interim.

Honesty: high. Caveats explicit. Builds infrastructure usable past this session.

Operator-spec fit: medium. The prompt asked for a session-final verdict; M1 gives a pilot result instead.

### Modification M2: scope expansion to AIA's hard-market band

**Change:** drop the v1 [0.70, 0.95] band. Use AIA's hard-market definition (markets where Kalshi mid is in approximately [0.20, 0.80], the regime where Halawi 2024 shows LLM beats crowd). Keep the sports universe constraint. Apply the foreknowledge cutoff at 2026-01-01 and forecast on every open sports market closing 2026-05-27 to 2026-07-31.

Projected n: from A1's note Section 6.2, the open sports universe in this window is approximately 4,223 markets; expanding the band to [0.20, 0.80] yields an estimated 300 to 500 markets per the agent's rough estimate.

Cost: at $0.10 per forecast and n = 300, approximately $30 LLM. **Exceeds the $18 remaining cap.** Would need to drop to n = 150 to 180 at the $15 to $18 budget. SE at n = 180 is 0.037 and detectable delta is 0.057, still 4x the AIA target but closer.

Honesty: medium. The scope departs from the operator's stated target (v1 residual). The AIA +0.014 number is on hard MarketLiquid, which is the band where v9 has a chance; this aligns method to target rather than target to method.

Operator-spec fit: low. The operator explicitly named "v1's denylisted-residual sports universe at T-35d to T-7d horizons." Expanding the band breaks that specification.

### Modification M3: KILL v9 now, write NULL verdict, redirect to v10

**Change:** declare v9 Angle A structurally infeasible at the pre-registered gate within the session budget and timeline. Write `research/v9/FINAL-VERDICT.md` as NULL with the breakdown above. Update CLAUDE.md to Round 14 v9 NULL. Move directly to A3's top-3 v10 candidates, starting with the zero-cost actions:
- v8-A analysis pass when v8-A finishes at 2026-05-26 23:48 UTC (highest EV)
- Polymarket depth re-probe (30 min, free)
- GDELT re-probe (already confirmed reachable; 30 min)

Cost: $0 LLM remaining for v9. Frees $18 budget for v10.

Honesty: highest. Operator's kill-early preference is the controlling rule.

Operator-spec fit: high in spirit (kill-early), low in letter (the prompt said to run Angle A).

---

## Honest assessment

The prompt I was given asked for v9 Angle A as a fresh research round, with the implicit assumption that the n was workable. Phase 1 demonstrated the n is not workable for the pre-registered gate at the session budget and timeline.

The cleanest answer is M3. v9 closes NULL on data-layer feasibility, the spend was approximately $2 LLM for Phase 1 (well under the $20 ceiling), and the highest-EV next action is the v8-A analysis pass that runs essentially for free when the live probe finishes tonight at 23:48 UTC.

The strongest defense of M1 is that the LLM tool wiring itself is novel and worth building even at underpowered n. If Phase 2 builds the agentic pipeline and runs 30 to 50 smoke-and-pilot forecasts at $5 spend, we have a working v9 codebase that can extend to a 2026-27 season rolling study. That's a real asset even without a session verdict.

M2 (scope expansion) is the option most likely to produce a positive headline number, which is precisely why I am suspicious of it. Changing the target band after seeing the data is a form of post-hoc tuning. If we adopt M2, the foreknowledge audit and Platt locking become load-bearing because the methodology now diverges from AIA's exact recipe.

---

## What I am NOT recommending

- Running the full pipeline at n = 87 and HOPING the delta is large enough to clear the +0.014 gate. The literature evidence on sports LLM forecasting (Brier 0.16 to 0.28 against market 0.10) suggests this will not happen. Running anyway burns budget for noise.
- Tightening the gate to a smaller delta (e.g., +0.005) to make it fireable at n = 87. That's post-hoc target adjustment.
- Spending $30 on the-odds-api Starter to unlock historical odds. Worth it for v10 Candidate 9, not for v9 Angle A.
- Forecasting on past markets with trade-print mid as the "real" baseline. v7-B phantom replays.

---

## Operator decision needed

Pick one, and Phase 1.5 methodology lock proceeds accordingly:

1. **M1: run pilot, accept no session verdict.** Forecast 87 prospective markets, report at n = 87 in 5 weeks. Cost approximately $8-15 LLM.
2. **M2: expand band to AIA hard market range.** n approximately 150 to 180 at $15 budget. Departs from operator-stated target.
3. **M3: kill v9 NULL on feasibility, redirect to v10.** Zero further v9 spend. v8-A analysis tonight, then v10 selection.
4. **M4: something else** (e.g., halt and rethink scope further).

The default per kill-early principle and the prompt's "honest negative is better than burning budget on diminishing returns" instruction is M3.
