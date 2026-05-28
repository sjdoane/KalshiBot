# v7 Phase 2 Synthesis: B + C Results + Decision Point

**Date:** 2026-05-26
**Status:** Both v7 Angle B (Kronos / naive_p_yes) and Angle C (TabPFN) complete. Phase 3 critic on Angle B complete. Per pre-locked plan: "if either passes, escalate to Angle A." Mechanically v7-B passed orthogonality; substantively the Phase 3 critic verdict is PARTIAL with strong phantom suspicion. Operator decision needed on escalation path.

## TL;DR

- **v7-C TabPFN**: CLEAN NULL. v6 and v5-B NULLs are model-class-robust. TabPFN ties LightGBM within +0.00040 Brier on v5-B (FAIL +0.003 model-class delta); underperforms identity by -0.00091 Brier on v6. Apparent +0.07 Brier lift over the v6 logit baseline turned out to be the same D3 regime-shift artifact the v6 critic identified.
- **v7-B Kronos / naive_p_yes**: PARTIAL with PHANTOM SUSPICION. Kronos itself adds nothing (-0.00148 marginal over naive). But the diagnostic exposed a one-line feature `naive_p_yes = Normal-CDF(Coinbase spot at t, strike, sigma)` that beats Kalshi mid by +0.20842 Brier on midband holdout. Phase 3 critic adjudication: the comparison is well-formed (baseline is legitimate AS-OF horizon-time last-trade, NOT v5-B post-settlement phantom) BUT the live orderbook reality check shows 0 of 188 currently-open KXBTCD contracts have `|naive_p - mid| >= 0.10`. MMs actively maintain orderbook quotes against spot independent of whether trades fire. The +0.208 Brier is improvement over stale TRADE PRINT, not stale ORDERBOOK.
- **Net interpretation**: v7-B uncovered a methodology gap (v6 framed Coinbase features as returns not levels, missing a trivially-predictive level signal) but the operational claim of +32c per fired contract may not survive a prospective audit against actual orderbook ASKs.

## v7-B verdict per critic

The Phase 3 critic returned 4 KILLER + 7 IMPORTANT + 3 MINOR findings. The single most important:

**Killer Finding 9.1 (the central one):**
"Market microstructure picture: (a) when spot has not moved (naive_p ~ mid), orderbook stays at stale mid, no edge; (b) when spot has moved meaningfully, orderbook updates toward naive_p quickly, MMs reprice, and a +2c-take rule against stale mid either (i) does not fill because the visible ask has moved or (ii) fills at the new updated ask which is no longer profitable. The +0.208 Brier is what you'd EXPECT from any feature that tracks the true orderbook mid better than the last-trade-print does, even though that feature has no tradeable edge."

This is **v7-B's analog of v5-B Killer 2c**. v5-B used `last_price_dollars` (post-settlement). v7-B uses `kalshi_mid_at_t` (legitimate AS-OF horizon-time last-trade). Both proxies systematically diverge from the true transactable ASK in regimes where no trade has happened recently. The v7 diagnostic is more refined; the operational claim is unsupported.

## Critic's recommended next steps

The critic recommended a v8 prospective build:

1. Wire `scripts/v6/probe_kxbtcd_microstructure.py` to run hourly for 60-90 days. Capture yes_ask_dollars, yes_bid_dollars, size_fp at every cron iteration.
2. Cost ~50k snapshots, < $1 API spend.
3. After 30 days, recompute `kalshi_mid_at_t_orderbook` from snapshots. Re-run +0.208 Brier comparison against orderbook mid (not trade-print mid).
4. If improvement survives at orderbook mid AND +2c-take rule clears C3a + C4b against measured ASK, v8-B SHIP.
5. If improvement collapses or rule fails, v7-B closes as a stale-trade-print phantom.

NO LIVE CAPITAL until prospective audit confirms.

Per critic, this path has prior of monetizable signal ~40% (higher than Angle A's 25-35%).

## What the pre-locked plan says

Per operator decision at v7 scoping: "All three sequentially (B + C now, then A if either passes)."

Mechanically, v7-B passed orthogonality (+0.20217 Kronos, +0.20842 naive both clear +0.005 threshold). Per pre-lock, this triggers Angle A escalation.

Substantively, the Phase 3 critic verdict is PARTIAL with phantom suspicion. The escalation rule was written before the critic could expose the phantom mechanism.

This is the operator's call.

## Updated prior distribution for next-step options

| Next step | Cost | Wall-clock | Prior of monetizable signal | What it closes |
|---|---|---|---|---|
| Angle A (agentic LLM sports ensemble) | $20-40 LLM | 6-10h | 25-35% | The "did we try LLM hard enough?" question; v4-Track-B follow-up |
| v8 Angle B (prospective orderbook collection) | ~$1 API + 4-6h build | 60-90d wait | 40% | The "is the +0.208 Brier real or phantom?" question; cleanest replay of v6 with real ASK data |
| Both (Angle A this session + v8 build to record forward) | $21-41 + 10-16h | 6-10h active + 60-90d passive | 40-50% (independent shots) | Both above |
| Close v7 clean | $0 | 0h | 0% (close, not test) | v7 final verdict (PARTIAL + diagnostic + NULL on C); CLAUDE.md update |

## What the cumulative project state looks like after v7

| Round | Approach | Outcome | Notes |
|---|---|---|---|
| v1 (Round 6, live) | Favorite-maker on Kalshi sports | LIVE | Running on $32 with W1 denylist; W2 audit YELLOW (lean GREEN) at +7.68pp residual |
| v2 | Game-market ML | NULL | Single-team artifact, C5 leak |
| v3 | Polymarket-as-feature + team stats | NULL | Polymarket 30-day data ceiling killed it at data layer |
| v4-A | Polymarket fade filter | PARTIAL | SHIP shadow-mode pending wire |
| v4-B | LLM-as-forecaster (no tools) | NULL | BSS -2.17 vs market |
| v5-A | Sportsbook fade filter | PARTIAL | SHIP shadow-mode pending wire |
| v5-B | Statcast prop ML | NULL | n=146k, positive Brier but unmonetizable; v7-C confirmed model-class-robust |
| v5-C | Crypto on-chain features | NULL | 0 of 7 features cleared orthogonality |
| v6 | Crypto microstructure at T-30/T-15 | NULL | Best lift +0.00214 below threshold; D1/D2/D3 diagnostics surfaced |
| v7-B | Kronos + naive_p_yes diagnostic | PARTIAL-PHANTOM | +0.208 Brier real vs stale trade-print; live orderbook contradicts |
| v7-C | TabPFN model-class diagnostic | NULL | Model-class-robust null on v6 and v5-B |

The pattern is clear: free-tier public-feature ML at retail scale on Kalshi has not produced a monetizable edge in 9 distinct attempts. v7-B is the first PARTIAL on crypto, but the Phase 3 critic mechanism flags it as likely-phantom.

## Operator decision options

### Option 1: Escalate to Angle A per pre-locked rule (LLM ensemble on sports)

- Honor the pre-locked escalation. Run Angle A: Claude Opus 4.7 + web search + sportsbook tool + Kalshi mid ensemble on v1's denylisted-residual sports universe.
- Cost: $20-40 LLM, 6-10h.
- Prior: 25-35% per scoping doc.
- Closes the v4-B follow-up question definitively. Closes the agentic-retrieval frontier.

### Option 2: Build v8 forward-record infrastructure, defer Angle A

- Higher-prior, lower-cost angle per critic (40% prior vs Angle A's 25-35%).
- Wire `probe_kxbtcd_microstructure.py` to record `/markets` snapshots hourly. Cost: 4-6h engineering, < $1 API.
- Then 60-90 day passive wait before re-evaluating the +0.208 Brier vs real orderbook mid.
- Does NOT close v7 in this session; closes 60-90d hence.

### Option 3: Both (Angle A this session + v8 record-forward in parallel)

- Most thorough but highest total cost.
- Angle A produces session-final verdict; v8 records forward for future session.

### Option 4: Close v7 clean, no more research this session

- Write v7 FINAL-VERDICT.md as PARTIAL (B with phantom suspicion) + NULL (C).
- Update CLAUDE.md and project memory to reflect Round 13.
- Operator decides on Angle A and v8 in a future session.

### Option 5: Skip Angle A and Option 4 entirely; pivot

- Operator may have a different priority (e.g., wire the v4/v5 Track A SHIP shadow-mode, scale-up v1, work on a different project).

## Honest recommendation

Per kill-early principle and the operator's "really cool and original" instruction: **the v7-B finding IS cool and original** (stale-trade-print baseline phantom is a genuinely new failure mode), but it's NOT cleanly monetizable without forward-recording.

The honest moves:

- **Most rigorous: Option 2 (v8 forward-record).** Highest prior, lowest cost, directly addresses the phantom suspicion. Closes the question definitively in 60-90 days. Does not produce a session-final SHIP but lays the groundwork for one.
- **Most operator-spec-conforming: Option 3 (Both).** Pre-locked rule says escalate to Angle A; critic says v8 has higher prior. Doing both honors the rule and captures the higher-prior bet.
- **Most kill-early: Option 4 (Close clean).** v7 produced one clean NULL (C) and one phantom-suspect PARTIAL (B). The diagnostic is preserved as a v7 cache artifact for any future v8 prospective study. v1 unchanged.

The least defensible move is **Option 1 alone** (Angle A only): the pre-locked rule says escalate, but doing only Angle A skips the higher-prior v8 question. Mechanical compliance not substantive optimization.

## Files

- `research/v7/00-scoping-synthesis.md`
- `research/v7/01-data-sources-scoping.md`
- `research/v7/02-recent-ml-research.md`
- `research/v7/03-kronos-methodology.md`
- `research/v7/04-tabpfn-methodology.md`
- `research/v7/05-kronos-results.md`
- `research/v7/06-tabpfn-results.md`
- `research/v7/07-naive-p-yes-critic.md`
- `research/v7/08-phase2-synthesis.md` (this doc)
- `data/v7/kronos_predictions.parquet`, `tabpfn_v6_predictions.parquet`, `tabpfn_v5b_predictions.parquet`
- `data/v7/critic_test4_*.parquet`, `critic_test5_realistic2_orth.parquet`, `critic_live_probe.parquet`
- `src/kalshi_bot_v7/kronos_features.py`, `tabpfn_swap.py`
- `vendor/Kronos/` (read-only)
- `scripts/v7/run_kronos.py`, `run_tabpfn.py`, `run_kronos_orthogonality.py`, `fetch_coinbase_extend.py`, `write_kronos_results.py`, `critic_test4*.py`, `critic_test5*.py`, `critic_live_probe.py`

## Next action

Wait for operator green light on Option 1 / 2 / 3 / 4 / 5.
