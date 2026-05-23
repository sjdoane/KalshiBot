# Phase 1 Research Document: Kalshi Quant Trading Bot

**Date:** 2026-05-22
**Operator:** Washington state resident, $50 to $100 risk capital
**Stack:** Windows 11 + WSL2 Ubuntu, Python with uv
**Status:** Research complete (pre-critic). Awaiting operator decision before Phase 2.

Synthesis of four parallel research briefs:
- [Agent A: Kalshi API and infrastructure](briefs/agent-a-api-infra.md)
- [Agent B: Edge identification](briefs/agent-b-edges.md)
- [Agent C: Risk and failure modes](briefs/agent-c-risk.md)
- [Agent D: Legal, tax, regulatory](briefs/agent-d-legal.md)

---

## 1. Executive summary

**Headline.** The project is not blocked by any single hard constraint, but the
honest expected value on $100 of capital is **near zero with a realistic outcome
range of about -$30 to +$15** over a 3 to 6 month pilot. There is exactly one
credible edge candidate (KXHIGH weather maker-quoting), and it sits at the edge
of professional coverage. If the goal is to make money, the math says don't. If
the goal is an instrumented research and engineering exercise with at most a
$25-$30 tuition budget, the math says proceed with a tight, narrow Phase 2.

**Scorecard.**

| Dimension                          | Status        | Comment                                                                                  |
|------------------------------------|---------------|------------------------------------------------------------------------------------------|
| Legal access (WA, 2026-05-22)      | Open w/ risk  | Trading possible today. WA AG suit filed 2026-03-27. Access loss risk in 3-12 months.    |
| API and infrastructure             | Green         | Mature v2 API, working demo env, official Python SDK, RSA-PSS auth understood.           |
| Historical data for backtesting    | Yellow        | Tick trades available; full L2 orderbook history is not. Constrains backtest fidelity.   |
| Fee tractability                   | Yellow        | Maker fee ~0.88% round-trip is workable. Taker fee ~3.5% kills most candidates.          |
| Existence of a real edge           | Yellow        | One plausibly surviving candidate. Edge 3-6pp gross, 1.5-3pp net, contested by pros.     |
| Capital sufficiency ($100)         | Yellow        | Enough for an instrumented pilot. Insufficient for Kelly sizing or meaningful $ returns. |
| Tax treatment                      | Unsettled     | Federal classification ambiguous. Bot must log enough fields to support any treatment.   |
| Engineering complexity             | Manageable    | Risk controls, kill switch, reconciliation, idempotency are well-understood, not exotic. |

Recommendation in Section 8.

---

## 2. The edge question (most important section)

The single most important finding of Phase 1: on Kalshi, **takers lose ~32% on
a transactional basis and makers lose ~10%** (Burgi, Deng, Whelan 2025, n=300k+
contracts). That is the population baseline. To make money, the bot must
identify a sub-population where the cost structure inverts.

### What does NOT work for $100 retail in 2026

- **Cross-platform arb (Kalshi vs Polymarket).** 78% execution failure on
  low-volume opportunities; windows last seconds; pros are co-located. Net
  edge -1 to +1pp.
- **BTC short-dated lat-arb.** Pure HFT game. Residential latency loses.
  Round-trip fees ~3.5% on 50c contracts eat the theoretical 2-5% edge.
- **Sports.** 72% of Kalshi volume but Jump and Susquehanna run dedicated
  desks. Pinnacle remains the sharp benchmark and is faster than Kalshi.
  "Beat Kalshi sports CLV" is the same problem as "beat Pinnacle," which is
  very hard.
- **Economics (CPI, NFP, FOMC, GDP).** Kalshi macro markets outperform
  Bloomberg consensus (Fed FEDS 2026-010). Both sides smart money; edge
  negligible for retail.

### What plausibly works (one candidate, marginal)

**EC-1: KXHIGH weather residual calibration via maker quoting.**
- **Series:** KXHIGHNY, KXHIGHCHI, KXHIGHMIA, KXHIGHLAX, KXHIGHDEN (verified
  May 2026).
- **Mechanic:** isotonic-regression-recalibrated NWS HRRR / GFS ensemble
  probabilities vs Kalshi mid; post passive maker quotes on shoulder strikes
  when divergence > 8pp; cancel on NWS cycle update.
- **Gross edge:** 4-7pp on shoulder strikes (Zerve CalibShi study, 8,494
  settled markets, ECE improves 14.8x vs raw market price).
- **Net edge after maker fees (~0.88% round-trip):** 1.5-3pp.
- **Why it might not work:** multiple known weather bots already operate;
  "maker" implies passive limits that adverse-select against you (you fill on
  the wrong side); Northlake Labs documented a 0-for-32 record on retail
  weather trades.
- **Backtest constraint:** need contemporaneous NWS forecast archives plus
  Kalshi tick data. Doable but engineering-intensive. Critical caveat:
  Kalshi historical L2 orderbook depth is not API-accessible, so any
  backtest of maker fill probability will be optimistic.

**EC-2 (politics underconfidence)** is opportunistic only. Edge of 3-10pp net
but episodic, weakening in 2025 data, and low non-election-year volume. Useful
as a secondary signal during major political events, not a primary thesis.

### The killer fact

Even the surviving candidate is "at the edge of professional coverage" and the
field is filling up fast. **Expected outcome on $100 over 3 to 6 months: range
-$30 to +$15, mode near zero.** This is not a profit position. It is an
instrumented learning expense with a small chance of being net positive.

---

## 3. Infrastructure (API, fees, data)

### API verdict: Green

- **Version:** v2. Canonical hosts: `external-api.kalshi.com` (prod),
  `external-api.demo.kalshi.co` (demo). Demo alive in May 2026.
- **Auth:** RSA-PSS-SHA256 over `timestamp_ms + METHOD + path`, three headers
  (`KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP`). Timestamp is milliseconds, not
  seconds (common gotcha). Private key shown once. Key rotation is informal
  (generate new, then revoke old).
- **Rate limits (Basic tier):** ~20 reads/s, ~10 writes/s, token bucket. 429
  on overage with no `Retry-After` header. Exponential backoff mandatory.
- **Order types:** **only `limit` accepted via API since Sep 25, 2025.**
  Market orders deprecated. IOC at $0.99 simulates market buy. Stop orders not
  natively supported (client-side only).
- **Tick:** $0.01 standard, some sub-penny markets ($0.001). Price field type
  migrated to fixed-point strings ("0.5500") in March 2026. Any pre-March 2026
  example code breaks.
- **Position limits:** moved to "position accountability levels" in Nov 2024.
  Exchange caps ($7M per strike per individual) irrelevant at retail scale.

### Fee math (cross-verified across multiple sources)

- **Taker:** ceil(0.07 * C * P * (1 - P) / 0.01) * 0.01 per contract. Max
  $0.0175 at P = $0.50.
- **Maker:** 25% of taker. Max $0.0044 at P = $0.50.
- **Settlement, ACH deposit, ACH withdrawal:** all $0.
- **Wire withdrawal:** $0 from Kalshi but $500k minimum (institutional only).

Worked example, taker: 10 contracts at $0.55, resolves YES.
- Entry fee: $0.18 -> gross P&L $4.50 -> net $4.32 -> **fee drag 4.0%**.

Worked example, maker (same trade):
- Entry fee: $0.05 -> net $4.45 -> **fee drag 1.1%**.

**Strategic implication:** mid-price taker trades need >7% mispricing to clear
a round-trip taker fee. Maker pathway is roughly 4x more forgiving. **Any
strategy requiring aggressive taker execution is dead on arrival.**

### Historical data: Yellow flag

- Trade-level history via `/historical/trades` (paginated 100/page,
  rate-limited).
- Candlestick history via `/historical/candlesticks`.
- **L2 orderbook depth history is NOT openly available via API.** Options:
  capture live WS `orderbook_delta` from now forward, pay a third party (e.g.,
  Lychee, ~36GB archive, pricing opaque), or do without.
- **Operational implication:** start a WS orderbook capture process from day
  one of Phase 2, in parallel with all other work, to begin building
  proprietary L2 history.

### Client library

Recommended: **`kalshi-python` 2.1.4 from PyPI** (official, OpenAPI-tracking,
captures Sep 2025 order-type and March 2026 string-price migrations).

**Caveat:** proprietary license (`LicenseRef-Proprietary`). Read terms before
depending in production. Fallback: write a thin RSA-PSS `httpx` client using
`Kalshi/kalshi-starter-code-python` as the reference. Async alternative:
`aiokalshi`.

### Demo environment

- Working. Separate API keys. Mirrored market data.
- **Fills are simulated, not real counterparty.** Demo slippage is not
  predictive of production slippage. Use demo for correctness, not execution
  quality. Execution quality must be validated via paper-trade-on-prod (live
  data, zero-size or sandboxed orders).

---

## 4. Risk controls

### Position sizing for $50 to $100 bankroll

**Recommended: flat $1 to $2 per position for the first 50 settled trades;
switch to Quarter-Kelly capped at 5% of bankroll only after p has been
validated on out-of-sample data.**

Why not Kelly at start:
- Full Kelly requires known p. Quant strategies have noisy p estimates. Half-
  Kelly captures ~75% of growth at one-quarter the variance, but $50 cannot
  survive even one Kelly miscalibration.
- Integer-contract constraint on Kalshi already forces near-flat sizing for
  sub-$5 positions. The granularity floor dominates the math.
- At $50 bankroll, $1-$2 sizing supports up to 25 concurrent positions, max
  gross exposure $50.

### Drawdown circuit breakers (specific numbers)

| Threshold     | Trigger              | Action                                                |
|---------------|----------------------|-------------------------------------------------------|
| -5% / day     | $2.50 down today     | Soft pause: no new entries, hold existing             |
| -10% / day    | $5 down today        | Hard halt: cancel open orders, close speculative, 24h |
| -15% / week   | $7.50 down WTD       | Hard halt: pause 7 days, manual review                |
| -25% from peak| $12.50 from $50 peak | Full stop: manual code review + operator approval     |
| $25 floor     | bankroll < $25       | Auto-flatten and shut down                            |

No auto-resume below the floor. After daily/weekly halts, require manual
one-command resume and a logged reason. Auto-resume invites the bug that
caused the halt to repeat overnight.

### Five mandatory controls before live capital

1. **`CAPITAL_CAP_USD = 50`** as a single constant, checked pre-every-order.
   Absolute floor $25 auto-shutdown.
2. **Idempotent `client_order_id`** = sha256(strategy|market|side|epoch_minute|seq)
   to make restart-after-crash safe.
3. **Drawdown circuit breakers** as above with manual-resume-only.
4. **Reconciliation every 60 seconds** between local SQLite state and Kalshi
   `GET /portfolio/positions`. Any mismatch -> log, alert, refuse new orders
   until cleared.
5. **WSL2 clock-skew startup check** (abort if local time differs from NTP
   > 2s) plus private key PEM in OS secret store with restricted ACL.

### Most underrated failure mode

**WSL2 clock skew after laptop sleep/resume.** Silently breaks Kalshi's
RSA-PSS signed requests (timestamps stale). Documented in `microsoft/WSL`
issues #4677, #10006, #11790 but missing from every Kalshi tutorial reviewed.
Five lines of NTP-check code prevents it.

### Other failure modes worth memorizing

- **Knight Capital (2012):** $440M in 45 minutes. Root cause: partial
  deployment (7 of 8 servers) + reused flag re-activating dead code. Lesson:
  deploy completely or not at all; never reuse flags for new features.
- **3Commas (2022):** $22M+ via leaked API keys. Lesson: never grant
  withdrawal scope to bot keys; rotate immediately on any laptop/VPS loss.
- **LTCM (1998):** correlated risk you did not model is the risk that kills
  you. For Kalshi: two markets you think are independent (two Fed decisions,
  two NFL games tied to the same weather front) may co-move in tail
  scenarios.
- **Polymarket 2024 manipulation:** one wallet, $30M, moved a thin market for
  weeks. Plan for whales.

---

## 5. Legal and tax (WA-specific)

### Access status: open with elevated risk

A WA resident can open, fund, and trade today, including sports contracts. WA
is on Kalshi's "fully supported" list, not among the restricted nine (AZ, IL,
MA, MD, MI, MT, NJ, NV, OH).

**But:**
- **2026-03-27.** WA AG Nick Brown filed civil suit in King County Superior
  Court alleging WA Gambling Act and Consumer Protection Act violations.
- **Mid-May 2026.** Ninth Circuit denied Kalshi's bid to halt the WA case;
  case proceeds in state court. No preliminary injunction yet. No hearing
  scheduled as of early April 2026.
- **2025-12-12.** WA State Gambling Commission advisory called prediction
  markets "unauthorized activity."

**Material risk of access loss in 3 to 12 months** via: (a) preliminary
injunction in King County, (b) Kalshi voluntary WA geofence, (c) frozen
deposits or delayed withdrawals, (d) sports-only block.

**Implication:** the bot must include a wind-down mode from day one. On any
loss-of-access signal, flatten positions cleanly and stop, without operator
intervention.

### Top federal events to monitor

1. **Ninth Circuit ruling on Kalshi/Robinhood/Crypto.com v. NV Gaming Control
   Board.** Oral argument 2026-04-16, opinion pending. The most consequential
   single event for WA access.
2. **CFTC final rule on event contracts.** ANPRM comments closed 2026-04-30;
   final rule possibly Q3 or Q4 2026.
3. **WA AG preliminary injunction motion** (unscheduled).
4. **Third Circuit (NJ) ruled 2026-04-06** that CEA preempts state gambling
   law for sports contracts on a CFTC DCM. Mixed signal.

### Tax: bot must log to support any of 4 treatments

Federal classification is unsettled. Logging schema must support all of:
- **Section 1256** (60/40 long/short, mark-to-market). Aggressive. Defensible
  because Kalshi is a CFTC DCM.
- **Short-term capital gains.** Moderate. Form 8949 / Schedule D.
- **Ordinary income.** Conservative. Schedule 1 line 8 or Schedule C.
- **Gambling income.** Worst case. OBBBA 2026 caps gambling-loss deduction at
  90%, creating phantom income for break-even traders.

**Per-trade logging requirements:** UTC and WA-local timestamps, market
ticker, side, quantity, fill price, fees, settlement value, holding period in
hours, market category, exchange order ID, client order ID. Capture year-end
mark-to-market FMV of every open position at 23:59 ET on Dec 31.

**Wash-sale (IRC 1091):** likely does not apply to event contracts.
Statutorily inapplicable if 1256 is elected. Confirm with CPA.

**WA capital gains tax:** $278k floor and long-term only. Kalshi contracts are
short-term. Not in scope at $100 bankroll.

**Required action before live capital:** consult a WA-licensed attorney and a
CPA familiar with CFTC-regulated derivatives. Non-negotiable.

### 1099 forms (incomplete picture)

- **1099-INT** for $10+ interest on cash balances.
- **1099-MISC** for referral bonuses or credits ($2,000+ threshold in 2026).
- **1099-B coverage is disputed.** Some sources say Kalshi sends 1099-B at
  $600+ proceeds; others say it does not cover event-contract P/L.
  Conservative posture: **assume Kalshi does NOT send a comprehensive 1099-B;
  the bot is the authoritative P/L source for tax filing.**

---

## 6. Open questions and critical unknowns

Compiled from all four briefs. The critic pass will pressure-test these.

**Edge-related:**
1. **Maker fill rate vs adverse selection on KXHIGH.** Published 4-7pp gross
   edge is calibration on settled prices. Whether a passive limit would
   actually fill at those prices without adverse selection by faster bots is
   the single biggest unknown. Could be tested with ~$20 over 50 markets.
2. **EC-1 capital constraint.** Maker quoting on 5 cities x 5-10 strikes each
   = 25 to 50 resting orders. On $50, average position is $1-$2; minimum-tick
   and adverse-selection effects may dominate.
3. **Political underconfidence persistence** outside high-volume election
   windows is unverified.

**Infrastructure:**
4. **Kalshi fee schedule PDF** returned 429 on direct fetch. Numbers
   cross-checked via three secondary sources; operator should download the
   PDF manually before live trading.
5. **Special-event market fees** can deviate from the standard formula.
   Per-market rule text must be checked.
6. **WebSocket rate limits** (subscriptions per connection, message rate,
   reconnect backoff) not publicly documented. Measure in demo.
7. **`kalshi-python` license terms** are proprietary. Operator must read
   before relying in production.
8. **Lychee historical L2 dataset pricing** is "contact sales." Budget
   relevance unknown.
9. **API key scope separation.** Unclear whether Kalshi supports trade-only
   vs withdraw-enabled scopes on one key. If not, key compromise = bank
   drain risk; design must keep withdrawals manual-only.

**Legal/tax:**
10. **WA AG preliminary injunction motion** timing unscheduled. Could land
    Q3 2026 or later.
11. **Kalshi voluntary WA geofence** decision (a Ninth Circuit loss could
    trigger it).
12. **Federal tax classification of event contracts** is genuinely
    unresolved. Consult CPA.
13. **OBBBA 90% gambling-loss cap exposure** if gambling treatment is forced.

---

## 7. Contradictions and gaps between briefs

- **1099-B coverage.** Agent A briefly mentioned Kalshi sends 1099-B for
  proceeds > $600; Agent D's deeper review found CPAs split on whether this
  covers event-contract P/L. Reconciled: **assume not comprehensive**; the
  bot computes its own P/L authoritatively.
- **Fee schedule verification.** Agent A confirmed the formula via three
  secondary sources because Kalshi's PDF returned 429; Agent B independently
  cited the same formula. Acceptable but warrants direct PDF download by the
  operator before live.
- **EC-1 backtest feasibility.** Agent B says "doable" given Kalshi historical
  trades + NWS + Open-Meteo. Agent A flagged that historical L2 depth is NOT
  API-accessible. Tension: maker-quoting backtest needs depth data to model
  fill probability honestly. Trade-print backtests will overstate fill rates.
- **Demo usefulness.** Reconciled: demo for code correctness; paper-trade-on-
  prod (live data, zero-size or sandboxed) for execution-quality validation.

---

## 8. Recommendation

This is the operator's call. The honest framing:

**If the goal is profit:** kill or defer. Expected EV is near zero with range
-$30 to +$15. The opportunity cost of the engineering hours is large relative
to the realistic upside.

**If the goal is a real-money instrumented research and engineering exercise
with a $25 to $30 tuition budget:** proceed with a tightly scoped Phase 2 per
the conditions below.

### Conditional-proceed plan

1. **Restrict Phase 2 to EC-1 (KXHIGH weather maker-quoting) only.** Treat
   EC-2 (politics underconfidence) as an opportunistic add-on after EC-1 is
   live and instrumented.
2. **Build a wind-down mode from day one.** On a loss-of-access signal,
   flatten positions cleanly and stop, no operator action required.
3. **Hard go/no-go gate after 200 live paper-traded fills.** If maker fill
   rate < 55% on resting orders (adverse selection dominates), pull the plug.
4. **Start WS orderbook capture now**, in parallel with all other work, to
   build proprietary L2 history.
5. **Cap initial live capital at $25**, not $50. Half of half. If it works at
   $25 it'll work at $50; if it blows up at $25, you saved $25.
6. **Two-week paper trade requirement** remains non-negotiable. If paper P&L
   distribution diverges meaningfully from backtest, debug before going live.
7. **CPA and WA-licensed attorney consults** before live trading. Budget
   separate from the $100 cap.

If any of these conditions are unacceptable, kill the project.

---

## 9. What I need from the operator

To move to Phase 2, please confirm:

1. **Goal framing.** Profit-motivated (recommendation: kill) or
   research/learning with tuition budget (recommendation: conditional
   proceed)?
2. **Outcome acceptance.** Realistic range -$30 to +$15 over 3 to 6 months,
   mode near zero. Acceptable as the honest base case?
3. **WA legal risk.** Trading open today but may close in 3 to 12 months. Bot
   will wind down cleanly but cannot prevent access loss. Acceptable?
4. **Pre-live consults.** CPA + WA attorney short consultations before live
   trading. In scope?
5. **Initial live cap of $25** (not $50). Acceptable?

If yes to all five, Phase 2 will produce a narrowed strategy proposal
(EC-1 KXHIGH maker-quoting) plus the architecture sketch for evaluation
before any production code lands.

---

## Appendix: individual briefs

- [Agent A: Kalshi API and infrastructure](briefs/agent-a-api-infra.md) (11 sections, ~30 sources)
- [Agent B: Edge identification](briefs/agent-b-edges.md) (6 sections, ~25 sources)
- [Agent C: Risk and failure modes](briefs/agent-c-risk.md) (5 sections, ~20 sources)
- [Agent D: Legal, tax, regulatory](briefs/agent-d-legal.md) (5 sections, ~25 sources)
