# Phase 1 Research Document: Kalshi Quant Trading Bot

**Date:** 2026-05-22
**Operator:** WA-domiciled, physically in California most of the time
(USC), $25 initial live capital (down from $50 per critic), $100 hard cap
**Stack:** Windows 11 + WSL2 Ubuntu, Python with uv
**Status:** Phase 1 complete (post-critic + CA addendum). Operator on Path C.

This document synthesizes four parallel research briefs and a Research Critic
pass. Source files:
- [Agent A: Kalshi API and infrastructure](briefs/agent-a-api-infra.md)
- [Agent B: Edge identification](briefs/agent-b-edges.md)
- [Agent C: Risk and failure modes](briefs/agent-c-risk.md)
- [Agent D: Legal, tax, regulatory (WA-focused)](briefs/agent-d-legal.md)
- [Agent D CA addendum (post-operator-disclosure)](briefs/agent-d-legal-ca-addendum.md)
- [Research Critic report](critic-report.md)

## 0. What changed after the critic pass

The critic landed three substantive hits on the pre-critic draft. Each is now
reflected throughout the document.

1. **EC-1 was framed as a candidate edge; it is a hypothesis.** The entire
   4-7pp gross-edge number derives from one study (Zerve CalibShi, 14.8x ECE
   improvement on 8,494 KXHIGHNY markets) that does NOT document in-sample vs
   out-of-sample partition. Isotonic regression fit and scored on the same
   data is trivially well-calibrated; the published figure tells us nothing
   about live edge. The synthesis treated calibration as profitability. Wrong.
2. **Pre-critic said the WA AG preliminary injunction motion was "not
   filed/scheduled." That is wrong.** AG Brown's complaint explicitly seeks a
   preliminary injunction. Motion is on file; no hearing date set. Separately,
   the 9th Circuit panel at oral argument (2026-04-16) "appeared to lean
   Nevada's way" per Nevada Current reporting. WA sits in the 9th Circuit, so
   an adverse ruling shortens the access-loss window from "3-12 months" to
   plausibly "1-6 months."
3. **Northlake Labs 0-for-32 was misapplied.** That bot was a taker at extreme
   strikes with 15-60 minute polling. It is NOT a direct refutation of EC-1's
   maker-quoting design. The transferable lesson is the latency arms race
   ("pros react within seconds of every NWS cycle"), not the trade structure.

Several smaller corrections (OBBBA gambling-loss cap may NOT apply to event
contracts; sports is 89% of Kalshi revenue not 72% of volume; maker fee
arithmetic is conditional on fill rate * (1 - adverse selection); the
-$30 to +$15 range is vibes not math) are also incorporated.

## 1. Executive summary

**Headline.** Project is not blocked by any single hard constraint, but the
honest expected value on $100 of capital is **near zero, with a plausible
floor closer to the cap than to -$30** if execution fails. The only edge
"candidate" identified (EC-1 KXHIGH weather maker-quoting) is unvalidated and
likely zero-to-negative after fees, latency disadvantage, and adverse
selection. **Recommended path: kill live trading**, with two non-default
escape hatches detailed in Section 8.

**Scorecard.**

| Dimension                          | Status              | Comment                                                                                          |
|------------------------------------|---------------------|--------------------------------------------------------------------------------------------------|
| Legal access (WA, 2026-05-22)      | Yellow leaning red  | Trading open today. Preliminary injunction motion ON FILE. 9th Circuit oral argument unfavorable.|
| API and infrastructure             | Green               | Mature v2 API, working demo, official SDK, RSA-PSS auth well-understood.                          |
| Historical data for backtesting    | Yellow              | Tick trades and candles available. L2 orderbook depth history is not.                            |
| Fee tractability                   | Yellow              | Maker ~0.88% round-trip workable IF fills are not adversely selected. Taker ~3.5% kills most.    |
| Existence of a real edge           | Red                 | Sole candidate is calibration-only with no out-of-sample validation. Edge is a hypothesis.        |
| Capital sufficiency ($100)         | Yellow              | Sufficient for an instrumented research probe. Insufficient for meaningful $ returns.            |
| Tax treatment                      | Unsettled           | Federal classification ambiguous. Logging must support any of four treatments.                   |
| Engineering complexity             | Manageable          | Standard controls, idempotency, kill switch, reconciliation.                                      |
| Counterparty composition (EC-1)    | Red                 | Weather markets are bot vs bot. No retail dumb money to subsidize the maker.                     |

## 2. The edge question (most important section)

Population baseline on Kalshi: **takers lose ~32% per trade, makers lose ~10%**
(Burgi, Deng, Whelan 2025, n=300k+ contracts, confirmed). That is the
distribution any retail strategy starts inside. The bot must identify a
sub-population where the cost structure inverts. The critic also surfaced
Bartlett & O'Hara (2026, n=41.6M trades): makers ARE profitable in
single-name markets, but via a YES-overbet behavioral surplus on NO-settling
markets, NOT via calibration. Weather markets do not obviously exhibit a YES
bias (no ideological pull toward warm or cold), so the documented
maker-profit mechanism does not transfer to EC-1.

### What does NOT work for $100 retail in 2026

- **Cross-platform arb (Kalshi vs Polymarket).** 78% execution failure on
  low-volume opportunities. Windows last seconds. Pros are co-located. Net
  edge -1 to +1pp.
- **BTC short-dated lat-arb.** HFT game. Residential latency loses.
  Round-trip fees ~3.5% eat the theoretical 2-5% edge.
- **Sports.** Now 89% of Kalshi revenue (not 72% of volume as the brief had
  it). Jump and Susquehanna run dedicated desks. Pinnacle remains the sharp
  benchmark and is faster than Kalshi.
- **Economics (CPI/NFP/FOMC/GDP).** Kalshi macro outperforms Bloomberg
  consensus. Both sides smart money; edge negligible for retail.

### What was claimed to work (and why the critic disagrees)

**EC-1: KXHIGH weather residual calibration via maker quoting.**
- **Series:** KXHIGHNY, KXHIGHCHI, KXHIGHMIA, KXHIGHLAX, KXHIGHDEN
  (verified May 2026).
- **Mechanic (proposed):** isotonic-recalibrated NWS HRRR/GFS ensemble
  probabilities vs Kalshi mid; post maker quotes on shoulder strikes when
  divergence > 8pp; cancel on NWS cycle update.
- **Claimed edge:** 4-7pp gross, 1.5-3pp net after maker fees (Zerve CalibShi
  study, 8,494 settled markets, ECE 0.01624 -> 0.00109).
- **Critic's counterpoints:**
  - The Zerve study does not document an out-of-sample partition. Isotonic
    fit and scored on the same data is trivially well-calibrated. The 14.8x
    figure tells us nothing about live tradable edge.
  - Counterparty composition: weather markets are bot vs bot. There is no
    retail dumb money to subsidize the maker. This is the worst possible
    counterparty mix.
  - Latency: pros react within seconds of every NWS cycle. A residential
    Windows + WSL2 host in Washington state will not. EC-1's "cancel on NWS
    cycle update" requires sub-second reaction; if the bot lags, its resting
    orders get filled at stale prices after NWS has already updated. That is
    the textbook adverse-selection failure mode.
  - Open-source bot `suislanchez/polymarket-kalshi-weather-bot` is already
    publicly doing approximately this strategy.
  - Bartlett-O'Hara maker-profit mechanism is YES-bias, not calibration.
    Weather markets do not exhibit a clear YES-bias.
- **Critic's net edge estimate:** **[-1pp, +1pp], mode small negative.**

**EC-2 (politics underconfidence)** stays opportunistic only. Episodic, low
non-election-year volume, weakening in 2025 data. Useful as a secondary
signal around discrete political events; not a primary thesis.

### The bottom line on edges

There is no edge candidate validated to the standard required to risk real
money on a $100 account. EC-1 is a hypothesis backed by one calibration study
without an out-of-sample test. The minimum required research to upgrade EC-1
from hypothesis to candidate is detailed in Section 8 as a **Phase 1.5 gate**.

## 3. Infrastructure (API, fees, data)

### API verdict: Green (critic confirmed all major numbers)

- **Version:** v2. Canonical hosts: `external-api.kalshi.com` (prod),
  `external-api.demo.kalshi.co` (demo). Demo alive in May 2026.
- **Auth:** RSA-PSS-SHA256 over `timestamp_ms + METHOD + path`, three headers
  (`KALSHI-ACCESS-KEY/SIGNATURE/TIMESTAMP`). Timestamp is milliseconds.
  Private key shown once. Key rotation is informal (generate new, revoke old).
  Scopes (`read`/`write`) added Dec 2025 - useful for least-privilege keys.
- **Rate limits (Basic tier):** ~20 reads/s, ~10 writes/s, token bucket.
  429 on overage with no `Retry-After` header. Exponential backoff mandatory.
- **Order types:** **only `limit` accepted via API since Sep 25, 2025.**
  Market orders deprecated. IOC at $0.99 simulates market buy. Stop orders
  not natively supported.
- **Tick:** $0.01 standard, some sub-penny markets ($0.001). Price field
  migrated to fixed-point strings ("0.5500") in March 2026. Pre-March example
  code breaks.
- **Position limits:** moved to "position accountability levels" in Nov 2024.
  Exchange caps ($7M per strike per individual) irrelevant at retail scale.

### Fee math (confirmed by critic across multiple sources)

- **Taker:** ceil(0.07 * C * P * (1 - P) / 0.01) * 0.01 per contract. Max
  $0.0175 at P = $0.50.
- **Maker:** 25% of taker. Max $0.0044 at P = $0.50.
- **Settlement, ACH deposit, ACH withdrawal:** all $0.
- **Wire withdrawal:** $0 from Kalshi but $500k minimum (institutional only).

Worked examples (unchanged from pre-critic).
- Taker, 10 contracts at $0.55, resolves YES: entry fee $0.18, net $4.32,
  **fee drag 4.0%**.
- Maker, same trade: entry fee $0.05, net $4.45, **fee drag 1.1%**.

**Critical reframing per critic:** "maker fee 4x more forgiving" is too
optimistic in isolation. True net edge =
`(gross_edge - 0.88%) * fill_rate * (1 - adverse_selection_rate)`. At
plausible fill rate 30-50% and adverse-selection 50-70%, the maker advantage
compresses substantially. Live measurement is the only honest way to
calibrate this.

**Special-event markets** can have bespoke fee schedules. Per-market rule
text must be read in code, not at design time. If KXHIGH carries non-standard
fees, EC-1 economics change.

### Historical data: Yellow flag (unchanged)

- Trade-level history via `/historical/trades` (paginated, 100/page).
- Candlestick history via `/historical/candlesticks`.
- **L2 orderbook depth history is NOT openly available via API.** Options:
  capture live WS `orderbook_delta` from now forward, pay Lychee (~36GB
  archive, "contact sales" pricing), or do without.
- **Operational implication:** if Phase 2 proceeds, start a WS orderbook
  capture process from day one, parallel to all other work.

### Client library

Recommended: **`kalshi-python` 2.1.4 from PyPI** (official, tracks OpenAPI
spec, captures Sep 2025 order-type and March 2026 string-price migrations).
Critic confirmed PyPI version and the proprietary license (`LicenseRef-
Proprietary`). Read EULA before depending in any redistributed code.

Fallback: thin RSA-PSS `httpx` client using `Kalshi/kalshi-starter-code-python`
as the reference. Async alternative: `aiokalshi`.

### Demo environment

Mirrored market data, **simulated fills**. Demo slippage is not predictive of
production slippage. Use demo for code correctness, paper-trade-on-prod for
execution-quality validation.

## 4. Risk controls (critic confirmed all controls)

### Position sizing for $50 to $100

**Flat $1 to $2 per position for first 50 settled trades; switch to
Quarter-Kelly capped at 5% of bankroll only after p has been validated
out-of-sample.** Integer-contract constraint on Kalshi already forces
near-flat sizing for sub-$5 positions, so embrace it. At $50 bankroll,
$1-$2 sizing supports up to 25 concurrent positions, max gross exposure $50.

### Drawdown circuit breakers

| Threshold     | Trigger              | Action                                                |
|---------------|----------------------|-------------------------------------------------------|
| -5% / day     | $2.50 down today     | Soft pause: no new entries, hold existing             |
| -10% / day    | $5 down today        | Hard halt: cancel open orders, close speculative, 24h |
| -15% / week   | $7.50 down WTD       | Hard halt: pause 7 days, manual review                |
| -25% from peak| $12.50 from $50 peak | Full stop: manual code review + operator approval     |
| $25 floor     | bankroll < $25       | Auto-flatten and shut down                            |

No auto-resume below the floor.

### Five mandatory controls before any live capital

1. **`CAPITAL_CAP_USD = 50`** as a single constant, checked pre-every-order.
   Absolute floor $25 auto-shutdown.
2. **Idempotent `client_order_id`** = sha256(strategy|market|side|epoch_minute|seq).
3. **Drawdown circuit breakers** as above, manual-resume-only.
4. **Reconciliation every 60 seconds** vs Kalshi `GET /portfolio/positions`.
5. **WSL2 clock-skew startup check** + private key PEM in OS secret store
   with restricted ACL.

### Most underrated failure mode (critic confirmed)

**WSL2 clock skew after sleep/resume.** Silently breaks signed requests.
Issues `microsoft/WSL` #4677, #10006, #11790. Five lines of NTP-check code
prevents it.

### Critic refinement on Knight Capital

The standard "partial deployment + reused flag" story is directionally right
but the precise root cause is **silent deploy-script SSH failure to one of
eight SMARS servers, leaving a zombie code path active behind the reused
Power Peg flag**. The lesson is deploy verification, not just "deploy
completely."

## 5. Legal and tax (WA + CA dual exposure, with critic corrections)

### Two states matter: WA (domicile) and CA (physical presence)

The operator is WA-domiciled but physically in California most of the year
(USC student). Kalshi's per-state restriction applies based on the
residential address on file at KYC. So the practical access question
depends on which address the operator registers with. See full analysis in
the [CA addendum](briefs/agent-d-legal-ca-addendum.md).

**CA access (cleaner today):**
- Open. No CA cease-and-desist or suit against Kalshi as of 2026-05-22.
- N.D. Cal. DENIED the three CA tribes' preliminary injunction in Nov
  2025; tribes' appeal is now in the 9th Circuit on a separate track
  from the NV case (consolidation denied 2026-05-06).
- **Loaded but not fired:** CA AG Rob Bonta is "preparing a
  cease-and-desist" and "considering" a state suit per CNIGA chair
  James Siva (Dec 2025). Treat as imminent-but-uncertain.
- CA tax exposure: nonresident filing (Form 540NR) sources intangible
  income to domicile state (WA), so Kalshi P/L is NOT CA-taxable for a
  nonresident. Trivial dollars at $100 cap either way.

**WA access (status quo, see below):**

### Access status (WA): Yellow leaning red

WA resident can open, fund, and trade today. WA is on Kalshi's "fully
supported" list. But:

- **2026-03-27.** WA AG Nick Brown filed civil suit in King County Superior
  Court (atg.wa.gov, Spokesman-Review, GeekWire confirm). **Complaint
  explicitly seeks a preliminary injunction "to stop the company from
  operating in the state immediately."** Motion is on file. No hearing date
  scheduled as of late May 2026. (The pre-critic draft was factually wrong on
  this point.)
- **2026-04-16.** Ninth Circuit oral argument in Kalshi/Robinhood/Crypto.com
  v. NV Gaming Control Board. **Per Nevada Current, the panel "appeared to
  lean Nevada's way."** Opinion pending. WA sits in the 9th Circuit, so an
  adverse 9th Circuit ruling binds directly.
- **2026-05-20.** Case remanded to WA state court. Kalshi appealed remand to
  9th Circuit.
- **2025-12-12.** WA State Gambling Commission advisory called prediction
  markets "unauthorized activity."

**Honest probability estimate (per critic):** 30-50% chance WA access closes
within 6 months. The pre-critic "3-12 months" framing was too sanguine. A
preliminary injunction with 30-day comply-or-cease language would force
Kalshi to either geofence WA or contest mid-case, either of which can affect
deposited funds for weeks to months. WA's use of the Recovery of Money Lost
at Gambling Act treats WA traders as victims rather than complicit (favorable
for the operator if Kalshi loses or settles), but practical effects on a live
account during an injunction window are not specified anywhere public.

### Top federal events to monitor

1. **Ninth Circuit ruling on Kalshi/Robinhood/Crypto.com v. NV GCB.** Most
   consequential single event for WA access. Panel directional signal is
   unfavorable for Kalshi.
2. **CFTC final rule on event contracts.** ANPRM comments closed 2026-04-30;
   final rule possibly Q3-Q4 2026.
3. **WA preliminary injunction hearing.** Unscheduled but motion is filed.
4. **Third Circuit (NJ), 2026-04-06.** Affirmed a preliminary injunction
   holding CEA preempts state gambling law for sports event contracts. 2-1
   ruling (Porter, Chagares; Roth dissent). Merits not decided. Sets up a
   circuit split likely heading to SCOTUS.

### Address recommendation

If the operator genuinely lives at a CA dorm/apartment Aug-May, the
**CA address is the cleaner Kalshi KYC entry today**: it matches
physical reality, avoids the WA AG suit's class definition, and the CA
AG threat is not yet operational. Do NOT use a CA address while not
actually living there - that is misrepresentation. Update Kalshi if/when
domicile changes. A 30-minute CPA call before scaling past ~$5k PnL is
recommended given 9-month-presumption edge cases.

The address question gates the rest of Phase 1.5 because the Kalshi API
keys for historical data must be tied to whichever address is on file.

### Sports = 89% of Kalshi revenue (critic correction)

The Agent B figure (72% of volume) understates regulatory exposure. Per
ingame.com / Sportico / Sacra, sports is **89% of Kalshi 2025 revenue**. The
WA AG suit is squarely targeting Kalshi's main business. If Kalshi loses
sports nationally (plausible after a 9th Circuit loss + SCOTUS denial),
platform economics shift and the appetite to keep marginal-revenue WA-
resident retail accounts open shifts with it.

### Tax: log to support any of 4 treatments (with OBBBA nuance)

Federal classification is unsettled. Bot logs must support:
- **Section 1256** (60/40 long/short, mark-to-market). Aggressive.
- **Short-term capital gains.** Moderate.
- **Ordinary income.** Conservative.
- **Gambling income.** Worst case.

**OBBBA 90% gambling-loss cap (critic correction).** OBBBA Public Law 119-21
Section 70114 does amend IRC 165(d), confirmed. **But multiple CPA sources
(Camuso, Monaco, defirate) argue the 90% cap may NOT apply to prediction-
market event contracts**, precisely because their classification is
unsettled. Industry framing is that prediction markets ESCAPE the cap. The
phantom-income risk only materializes if IRS specifically forces gambling
treatment. Worth logging defensively, but not the four-alarm fire the
pre-critic draft implied.

**Per-trade logging requirements:** UTC and WA-local timestamps, market
ticker, side, quantity, fill price, fees, settlement value, holding period in
hours, market category, exchange order ID, client order ID. Year-end
mark-to-market FMV at 23:59 ET Dec 31.

**Wash-sale (IRC 1091)** likely does not apply to event contracts. Confirm
with CPA. **WA capital gains tax** ($278k floor, long-term only) not in
scope at $100 bankroll.

**Required action before any live capital:** consult a WA-licensed attorney
and a CPA familiar with CFTC-regulated derivatives. Non-negotiable.

### 1099 forms (incomplete picture)

- 1099-INT for $10+ interest.
- 1099-MISC for referral bonuses ($2,000+ threshold in 2026).
- **1099-B coverage disputed.** Conservative posture: assume Kalshi does NOT
  send a comprehensive 1099-B; the bot is the authoritative P/L source.

## 6. Open questions and critical unknowns (re-ordered post-critic)

**Phase 1.5 gate (highest priority - must be done before any Phase 2 work
involving live capital):**

1. **Out-of-sample validation of Zerve isotonic recalibration.** Pull
   500-1000 settled KXHIGHNY contracts from a held-out window, fit isotonic
   on the first half, score the second half, compute realized edge vs raw
   market. If the 14.8x ECE figure does not survive a clean train/test split,
   EC-1 is dead. Estimated effort: 1-2 days on free data (Kalshi
   `/historical/trades`, Iowa State NWS archive). **This is the single
   highest-value research item and gates the proceed/kill decision.**

**Secondary, before live capital:**

2. **Live fill-rate test on KXHIGH maker quotes.** $5-10, one week of resting
   orders on KXHIGHNY shoulder strikes. Log quote-to-fill latency, fill price
   vs subsequent NWS update, adverse-selection events. Target 50 fills.
   Kill EC-1 if fill rate < 40% or adverse-selection rate > 60%.
3. **Counterparty composition on KXHIGH.** Are fills bot-clustered around NWS
   updates (worst case) or uniform across the day (some retail flow)? Sample
   50 fills across a week.
4. **WSocket subscription cap and reconnect behavior on demo.** If cap < 50,
   the 25-50-resting-orders proposal needs multiple connections.

**Tertiary (verify before live):**

5. **Kalshi fee schedule PDF** - download directly from a clean session.
   Verify formula constants and any KXHIGH-specific schedule.
6. **Lychee L2 dataset pricing.** "Contact sales" is not a budget.
7. **WA-licensed attorney 30-minute consult** on restitution / disgorgement /
   escheatment exposure during a preliminary-injunction window.
8. **API key scope verification.** Critic indicates Dec 2025 scopes field
   makes trade-only keys feasible. Operator should verify in dashboard.

**Monitor continuously:**

9. WA AG preliminary injunction hearing date.
10. Ninth Circuit ruling on NV GCB case.
11. CFTC final rule on event contracts.
12. Kalshi voluntary WA geofence signals.

## 7. Contradictions and gaps between briefs (mostly unchanged)

- **1099-B coverage.** A briefly mentioned 1099-B for $600+; D found CPAs
  split. Reconciled: bot computes own P/L authoritatively.
- **Fee schedule verification.** A confirmed via three secondary sources;
  critic re-confirmed; PDF still 429s on direct fetch. Operator should pull
  the live PDF before live trading.
- **EC-1 backtest feasibility.** B said "doable" given Kalshi historical
  trades + NWS + Open-Meteo. A flagged no historical L2. Critic resolved:
  trade-print backtest is doable but will overstate fill rates; the Phase
  1.5 gate (item 1 above) can use it because it tests calibration, not fill.
- **Demo usefulness.** Demo for correctness; paper-trade-on-prod for
  execution quality.
- **Maker fee 4x advantage (NEW post-critic).** Pre-critic framing was too
  optimistic. Real advantage is conditional on fill rate * (1 - adverse
  selection). Must be measured live.

## 8. Recommendation

Three honest paths. The default is the first.

### Path A (default): kill live trading

Do not move to Phase 2 involving live capital. The single edge candidate is
unvalidated, the access window is potentially short, and the engineering
learnings can be obtained for free elsewhere. Expected outcome on $100 is
near zero, with a realistic floor closer to the cap than to -$30 if
execution fails.

### Path B (recommended if the goal is engineering practice): demo-only

Build the bot end-to-end against Kalshi's demo environment plus a paper-trade
layer driven by live production market data. Zero capital at risk. Practice
the full M1-M8 milestone progression: RSA-PSS auth, rate-limit-aware client,
idempotent orders, reconciliation, kill switch, drawdown breakers, WSL2
clock-skew check, logging, Discord alerts. The engineering value of this
project is real. The live-trading value is not.

**Required to defend this path against scope creep:** explicit operator
agreement that demo and paper-on-prod are the terminal states. No live API
keys generated. No bank account linked. The $50 capital cap is enforced by
not depositing $50.

### Path C (only if the operator wants the trading research): Phase 1.5 gate first

Before any Phase 2 work involving real capital:

1. **Out-of-sample Zerve replication.** 1-2 days on free data. Fit isotonic
   on a held-out partition, score on the other half, compute realized edge
   vs raw market. Concrete pass criteria:
   - Out-of-sample ECE improvement >= 5x (down from in-sample 14.8x is fine;
     trivially-low out-of-sample improvement is the failure mode).
   - Median per-trade gross edge >= 2pp on shoulder strikes (15-40c bucket).
   - Edge persistence across at least 4 disjoint monthly windows.
2. If Phase 1.5 passes, then a Phase 2 strategy proposal becomes defensible,
   gated on the additional requirements below.
3. **If Phase 1.5 fails**, the project ends. The Zerve study was the only
   evidence backing the only candidate; without out-of-sample support, there
   is no edge to chase.

If Phase 1.5 passes, Phase 2 still requires:
- Initial live cap of **$25** (not $50). Half of half.
- **200-fill live paper-traded go/no-go gate** on maker fill rate
  (>= 55% required) and adverse selection (<= 60% required).
- **Wind-down mode** triggered automatically on any WA access signal.
- **CPA + WA-licensed attorney consults** completed before live capital.
- Two-week paper-trade requirement (no real money) before any live capital.

Capital cap remains $50 hard, $25 initial. If at any time during Phase 2 the
weekly drawdown crosses -15% ($7.50), the project pauses for review.

### Why the critic recommends a clean kill

The critic argues Path C is too generous because: (a) the WA access window may
close within Phase 1.5 + Phase 2's combined timeline, making the live runtime
zero; (b) the engineering learnings in Path C are obtainable in Path B for
zero capital risk; (c) the EC-1 edge claim is single-sourced. I find these
arguments strong but not dispositive. The honest framing is: Path B if you
want engineering practice; Path C if and only if the Zerve gate clears and
you accept that the realistic dollar outcome may be small loss to small win.
Path A by default.

## 9. What I need from the operator

Pick a path:

1. **Path A: kill live trading.** No further work. Project archives at this
   commit. Recommended if the goal is profit.
2. **Path B: demo and paper-on-prod only.** Phase 2-6 proceed but with
   permanent no-live-capital posture. Recommended if the goal is engineering
   practice.
3. **Path C: Phase 1.5 Zerve gate, then conditional Phase 2.** I run the
   out-of-sample replication; we look at the results together; we proceed
   only if it clears the bar in Section 8.

If Path C, also confirm:
- Realistic outcome acceptance (range -$50 to +$15 if execution fails badly,
  -$30 to +$15 if it functions, mode near zero). Acceptable?
- WA legal risk acceptance (30-50% chance access closes within 6 months).
  Acceptable?
- $25 initial live cap (not $50). Acceptable?
- CPA + WA attorney consults before live (separate budget). Acceptable?
- Hard kill of the project if Phase 1.5 out-of-sample replication fails.
  Acceptable?

## Appendix: source documents

- [Agent A: Kalshi API and infrastructure](briefs/agent-a-api-infra.md)
- [Agent B: Edge identification](briefs/agent-b-edges.md)
- [Agent C: Risk and failure modes](briefs/agent-c-risk.md)
- [Agent D: Legal, tax, regulatory](briefs/agent-d-legal.md)
- [Research Critic report](critic-report.md)
