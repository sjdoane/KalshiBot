# V10-A Round 15 FINAL RECOMMENDATION

**Date:** 2026-05-27
**Author:** V10-A orchestrator
**Status:** Round 15 V10-A pivoted to empirical Becker exploration after methodology kill; FIVE PERSISTENT EDGE candidates found, plus ONE Media midprice shadow-mode candidate from independent agent. Total V10-A spend ~$4 of expanded operator budget.

---

## Bottom line

**The Becker post-October-2024 dataset shows a real, statistically significant maker advantage in multiple Kalshi market categories.** Two independent analyses (orchestrator prefix-level + agent category-level) converged on the same conclusion: makers earn positive net excess return after fees in the uncertain price band (0.30 to 0.70) across many market types.

**Six candidate strategies** identified, each with bootstrap CI excluding zero on at least one window and most with persistent edge across train + OOS:

| Candidate | Type | Edge (OOS) | n_events OOS | Top concern |
|---|---|---|---|---|
| Media maker midprice | political mentions, polls, TSA | +6.55pp net | 138 prefixes | F11 fill rate |
| KXWTAMATCH maker | WTA tennis matches | +3.27% net (cluster) | 421 | F11 |
| KXATPMATCH maker | ATP tennis matches | +2.63% net | 471 | F11 |
| KXETHD maker | Ethereum daily | +2.46% net | 1,296 | Edge decay (6.45 to 2.46) |
| Other maker [0.60-0.80] | wide tail of 1087 prefixes | +2.40pp net | many | low per-trade edge |
| KXBTCD maker | Bitcoin daily | +1.25% net | 1,327 | smallest edge |

**None are SHIP-CANDIDATE for direct live deployment** because of failure mode F11 (Dataset Schema Phantom): the Becker dataset has no orderbook bid/ask at trade time, so the realized maker fills in the data may not represent what a NEW retail bot's bid would have been filled at. This is the same data-layer infeasibility that killed V10-A Kim replication and is in the same family as v7-B confirmed phantom.

**Recommended action: SHIP TO SHADOW MODE.** Build a paper-trade logger on v1 infrastructure that prospectively records hypothetical maker fills on a CURATED universe spanning the six candidate categories. Run 60 to 120 days. The pre-registered shadow-mode gate is documented below.

---

## What was done in Round 15b/c (post V10-A NULL)

1. **Becker dataset downloaded** (36 GB) and extracted (46 GB). 7900 Kalshi parquet files. Coverage: 2021-06-30 to 2025-11-25.

2. **Macro inventory** confirmed V10-A KILL: only 16 post-flip Kim release events. Pre-flip data has 125 events but violates CLAUDE.md fact 3.

3. **Quick category scan** showed empirical maker advantage in ScienceTech +3.28%, Crypto +2.93%, Weather +2.40% (net, after fees). Sports +1.12% per Becker headline reproduction.

4. **Cluster bootstrap sweep** across 13 candidate prefixes: 13 prefixes pass the rigorous gate (cluster-CI > 0, n_events >= 30). Top edges in tennis, basketball, totals, crypto.

5. **Train/OOS sweep** with proper chronological split (train Nov 2024 to Aug 2025, OOS Sep 2025 to Nov 2025): 5 prefixes show PERSISTENT EDGE across both windows.

6. **Independent agent (Becker empirical edge discovery)** ran parallel analysis at category-level granularity. Surfaced side-selection bias warning, then found Media maker midprice (+6.55pp net) and Other maker (+2.40pp) as MARGINAL candidates after combined-side LOCO.

7. **Mohanty pivot agent (Kalshi macro -> crypto vol)**: signal reproduces empirically (t=3.67 vs paper 3.71) but Kalshi BTC product universe has wrong horizons (KXBTCD too short, KXBTCMAXM has 5/30 dilution); round-trip cost dominates. KILL the pivot.

---

## Why the cluster bootstrap matters (methodology critic IMPORTANT-1 applied)

The V10-A methodology critic flagged that trade-level inference inflates apparent edges because trades within an event are not independent (e.g., multiple strikes of CPI April 2025 share the realized outcome).

My initial quick scan showed KXEPLGAME maker net +2.42pp at trade-level. With cluster bootstrap by event_ticker, the OOS cluster-mean was actually NEGATIVE (-5.27%) and the CI included zero. This is exactly the kind of statistical illusion the critic warned about.

The five PERSISTENT EDGE candidates documented above ALL survive cluster bootstrap on event_ticker. Their edges are real statistical signals at the per-event level, not artifacts of within-event clustering.

---

## Shadow-mode protocol (recommended deployment)

### Universe definition

Curate a portfolio of open Kalshi markets across the six candidate cells:

1. **Media midprice (top priority):**
   - Open markets in the Media group: KXTSAW (TSA counts), KXVANCEMENTION (Vance mentions), KXAPRPOTUS (POTUS approval), KX538APPROVE (538 approval), KXEARNINGSMENTION* (earnings mentions), KXSNFMENTION (Sunday Night Football mentions), KXSNLMENTION (SNL mentions), KXHEADLINE (general headlines)
   - Filter: orderbook mid in [0.40, 0.60]
   - Maker quote: 1 cent inside orderbook mid on the side with thinnest depth

2. **Tennis WTA + ATP:**
   - Open KXWTAMATCH and KXATPMATCH markets
   - Filter: orderbook mid in [0.30, 0.70]
   - Maker quote: passive bid 1 cent below orderbook mid

3. **Crypto BTCD:**
   - Open KXBTCD markets (daily Bitcoin price levels)
   - Filter: orderbook mid in [0.30, 0.70]
   - Maker quote: passive bid 1 cent below mid

### Logging

For each maker quote placed, log:
- Quote time, ticker, side, our bid price, our ask price
- Orderbook snapshot at quote time (bid_levels, ask_levels, mid)
- Fill events: timestamp, side filled, fill price, our fill size
- Market resolution (when settled): result, our P&L on the fill

### Pre-registered gates (60 to 120 day evaluation)

**Per candidate cell, evaluate independently:**

- **G1 (fill rate floor)**: realized fill rate >= 15% of placed quotes (otherwise the strategy doesn't fire enough to evaluate)
- **G2 (n_fills floor)**: at least 30 fills accumulated (otherwise underpowered)
- **G3 (mean net P&L > 0 after fees)**: realized mean P&L per fill > 0
- **G4 (bootstrap CI lower > 0)**: 95% percentile bootstrap CI on per-fill net P&L excludes zero
- **G5 (within +/- 3pp of Becker baseline)**: realized edge within 3 percentage points of Becker's empirical baseline (e.g., Media expected +6.55pp, accept [+3.55, +9.55])
- **G6 (LOCO event-level still positive)**: per-event mean P&L bootstrap CI lower > 0 with LOCO on largest event_ticker subgroup

**Verdict tree per candidate:**
- If all 6 gates pass: ESCALATE to $5 live deployment for that candidate
- If 4 or 5 of 6 pass: CONTINUE SHADOW for another 60 days
- If 3 or fewer pass: NULL the candidate

### Cost

- LLM: $0 (no LLM in the shadow logging flow)
- External API: $0 (Kalshi READ key already in .env)
- Engineering: 4 to 8 hours operator time to wire shadow-mode on v1 infrastructure (similar to existing v1 paper trade)
- Wall clock: 60 to 120 days for first verdict

---

## Why this is HONEST, not SOLD

The empirical analyses produced positive results. The natural temptation is to immediately deploy capital. The honest constraints:

1. **F11 phantom risk:** Becker's "maker P&L" is the COUNTERPARTY P&L of taker-aggressor trades. It does not directly measure what a new retail maker bot's bids would experience. The realistic fill-conditional distribution may differ significantly.

2. **Selection by orderflow:** the maker side in Becker is determined by which way the taker hit, not by our own choice. Our retail bot would quote both sides and get filled by whichever side the taker hits; in aggregate, this is what Becker measures, but per-trade-conditional realized P&L could differ.

3. **Cumulative project track record:** 8 NULLs, 1 PHANTOM, 2 PARTIALs in 14 rounds. The base rate for any new candidate is 10 to 15% of clearing all live-validation gates. Six candidates means a roughly 50 to 70% chance that AT LEAST ONE clears shadow-mode gates, but a specific candidate is still subject to the base rate.

4. **Diercks 2026 (Federal Reserve) on macro markets** documents Susquehanna pricing efficiently. Some of the Becker edges may decay as MMs compete more aggressively post our sample window (Nov 2025).

5. **No live capital risk required.** Shadow mode is $0 capital. The validation cost is operator time only.

---

## Updates to memory and CLAUDE.md (this section is operator-action)

Per operator request "Please update memory and context documents. I want this continually updated thoroughly," the following memory and CLAUDE.md updates have ALREADY been applied:

- `MEMORY.md` index updated with Round 15 V10-A status
- `project_kalshi.md` memory updated with V10-A NULL + pivot
- `CLAUDE.md` "Where this project stands" updated with full Round 15 V10-A NULL details and F11 failure mode

PENDING operator action (Round 15 closure):
- Update `CLAUDE.md` and `project_kalshi.md` once V10-B (other window) reports its verdict
- Add a section to project memory documenting the SIX shadow-mode candidates from this round
- Decide whether to commit to shadow-mode protocol or defer to Round 16

---

## What did NOT pan out (NULL records for replay prevention)

- **V10-A Kim replication** (Granger + LLM filter on Kalshi macro): NULL at methodology lock, 3 KILLERs, F11 logged.
- **Mohanty pivot** (Kalshi macro to crypto vol): KILL, signal real but venue infeasible.
- **KXEPLGAME** at trade-level looked promising but cluster bootstrap showed CI includes zero. NULL.
- **KXNCAAMBGAME, KXMLBTOTAL** at OOS looked great (+11.92, +3.53) but train data was missing. CANNOT CONFIRM until prior season indexing fix.
- **Weather (KXHIGH*)** as a category passes naive scan but fails LOCO (top-3 prefix dominates). Consistent with EC-1 Round 1 kill on KXHIGHNY specifically.

---

## Round 15 final accounting

| Item | Spend |
|---|---|
| V10-A core (NULL at lock) | $1.50 |
| Becker download + extraction | $0 |
| Mohanty pivot agent | $0.20 |
| Becker edge discovery agent | $1.00 |
| Orchestrator analyses + writing | $1.30 |
| **Total V10-A round 15** | **approximately $4.00** |

Well under the operator's expanded budget. v1 continues running on $32 unchanged. No live capital deployed.

---

## Operator decision points

1. **Authorize shadow-mode wiring:** 4 to 8 hours engineering work to extend v1's paper-trade infrastructure. This is the recommended next step.
2. **Pick scope:** which of the six candidates to log in shadow mode. Recommended: ALL six, with independent gates. Cost is the same (just logging more universes).
3. **Coordinate Round 15 closure** with V10-B (other window) for consolidated CLAUDE.md update.

---

## Anti em-dash verification

This document was written without em-dashes (U+2014) or en-dashes (U+2013).
