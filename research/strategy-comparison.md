# Kalshi Strategy Comparison: Candidates for the Next Project Phase

This document is the explicit comparison the new project context
needs to consume and act on. It's the substrate for "compare,
decide, implement" - laying out the candidate (category, strategy)
combinations along with the literature-grounded reasons each is or
isn't viable for a $25-$100 retail account.

**Use this document as the starting point for strategy selection.**
Do not propose strategies that aren't in the matrix below without
first explaining why this matrix is incomplete.

## Decision criteria

Any strategy proposal should be evaluated on:

1. **Net EV after fees**: expected per-trade return after maker
   round-trip fees (~0.5-1.0% on $1 notional depending on price).
2. **Variance**: per-trade standard deviation. Bürgi finds 33% on
   the maker-profitable subpopulation. A $25 cap can absorb only
   so much variance.
3. **Liquidity ceiling**: how much capital can a $25-50 account
   actually deploy without moving the market or failing to fill?
4. **Information / latency disadvantage**: does the strategy
   require speed or information the operator doesn't have?
5. **Backtest feasibility**: do we have data to validate this OOS
   before live capital? (Kalshi historical data is API-pullable;
   external data feeds may not be.)
6. **Regulatory / regime stability**: how exposed is the strategy
   to a state AG action, CFTC rulemaking, or Kalshi fee change?
7. **2024-sign-flip robustness**: does the strategy still work
   post-flip, or did it only exist in the pre-October-2024 regime?

## Categories: which Kalshi market families are worth considering

| Category | Gap (Becker, pp) | Trades (2025) | Verdict | Reasoning |
|---|---|---|---|---|
| Weather (KXHIGH/KXSNOW/KXRAIN) | 2.57 | 4.4M | **EXCLUDED** | EC-1 KXHIGH killed at Phase 1.6 gate. Could revisit KXSNOW/KXRAIN but expect similar issue per Le's regime analysis. |
| Finance | 0.17 | 4.3M | EXCLUDED | Too efficient. Fed paper confirms it matches Bloomberg consensus. Pros price these tightly. |
| Macro (CPI/NFP/FOMC) | n/a (subset of Finance) | included above | EXCLUDED | Same - Fed paper FEDS 2026-010 validates these are pro-priced. |
| Politics (elections, polling) | 1.02 | 4.9M | **CANDIDATE** | Le's load-bearing finding: chronically underconfident (compressed toward 50%). Bias is real and persistent. Episodic - volume concentrates around elections / FOMC / Senate votes. |
| Sports | 2.23 | 43.2M (largest!) | **CONDITIONAL CANDIDATE** | Jump/Susquehanna dominate. But largest absolute volume, so even thin per-trade edges accumulate. Specific sub-categories (e.g., NCAA tournament longshots) may have retail-overpriced YES. |
| Crypto | 2.69 | 6.5M | LONG-SHOT | Sub-daily lat-arb is HFT-dominated. Weekly/range markets may have less HFT pressure. |
| Entertainment | 4.79 | 1.5M | LONG-SHOT | Large bias but thin. Only 60 trades/market median. $25 can move the market. |
| Media | 7.28 | 0.6M | EXCLUDED | Largest gap but volumes too thin for systematic strategy. |
| World Events | 7.32 | 0.2M | EXCLUDED | Largest gap, thinnest market. One trade can be the entire signal. |

## Strategy types: orthogonal to category

| Strategy type | Mechanism | Best fit categories | Backtest feasibility |
|---|---|---|---|
| **A. Maker-quote shoulder strikes (15-40c & 60-85c)** | Capture spread + favorite-longshot bias on resting orders | Politics, conditional Sports | High - replicate Phase 1.5/1.6 pipeline |
| **B. Maker-quote >= 50c contracts (Bürgi)** | Bürgi finds +2.6% maker return on >50c subpopulation | Any with adequate liquidity | High - same pipeline |
| **C. Calibration recalibration (isotonic etc.)** | Train OOS recalibrator, fade overconfident prices | Politics (chronically underconfident per Le) | High - same pipeline; just different category |
| **D. Cross-platform arb (Kalshi vs Polymarket)** | Trade divergences between platforms | Politics (Polymarket's strongest) | Medium - need Polymarket data feed, USDC handling |
| **E. Behavioral surplus harvest (Bartlett)** | YES-overbet on NO-settle markets | Single-name markets across categories | Medium - need a market-classification model |
| **F. Manipulation reversal (Rasooly & Rozzi)** | Buy against post-manipulation prices, hold 60+ days | Politics (manipulation incidents documented) | Low - manipulation events are sparse |
| **G. Event-driven directional (around scheduled releases)** | Bet directionally on under/over of consensus before release | Macro, Sports games | High - schedule is known in advance |
| **H. Maker on long-horizon Politics (Le)** | Le's strongest finding: politics chronically underconfident at all horizons | Politics specifically | High - same pipeline |

## The matrix: (Category, Strategy) crosses ranked by expected viability

Best candidates highlighted in **bold**.

| Pair | Pros | Cons | Backtest Plan |
|---|---|---|---|
| **Politics x H (maker on chronically-underconfident)** | Le directly documents this; persistent (not just election-year). Mechanically: post bids inside the compressed band, expect prices to extend back toward truth. | Episodic volume; risk that "chronic" pattern dies as politics MMs arrive. | Replicate Phase 1.5/1.6 pipeline on politics series; lock methodology, OOS gate. |
| **Politics x C (calibration recalibration)** | Le's regime finding maps directly: politics is underconfident at all horizons. Recalibration should push predictions OUT toward extremes. | Same risk as H. Calibration model needs sufficient sample of resolved political markets. | Pull settled politics markets + multi-horizon snapshots; fit isotonic; OOS. |
| Sports x B (maker on >= 50c contracts) | Largest volume category. Bürgi finding suggests +2.6% on 50c+ subpopulation. Sports HAS the volume to support meaningful position size. | Jump/SIG dominate. Adverse selection (Bartlett) likely high in single-name games. | Replicate pipeline on settled sports markets; explicit fee model; LOCO across sports types. |
| Sports x E (behavioral surplus on YES-overbet) | Bartlett's mechanism: traders systematically overbet "YES my team wins" on objectively-NO-settling games. | Need to classify which sports markets are "behavioral surplus markets" reliably. | Need a markets classification model trained on resolved YES/NO base rates. |
| Crypto x B (maker on weekly range markets) | Less HFT pressure than hourly markets. Weekly cadence is tradable from home. | Crypto markets are still relatively pro-priced; retail edge thinner than weather even. | Same pipeline; explicit weekly-horizon analysis. |
| Entertainment x B (maker on Oscars / awards) | Bürgi's biggest maker-taker gap and thinnest pro presence. | Volume too thin to scale; individual contract base rates vary wildly. | Pipeline on entertainment series; will likely have insufficient sample. |
| Cross-platform Kalshi-Polymarket arb | Le shows real microstructure differences. Polymarket politics is more efficient than Kalshi politics in some windows. | 78% execution failure on low-volume opportunities (Clinton & Huang). Latency disadvantage from residential connection. Needs USDC infrastructure on Polygon. | Pull Polymarket politics + Kalshi politics for same events; look for sustained divergences. Likely fails the latency-disadvantage test. |
| Event-driven Macro directional | Fed paper validates Kalshi macro accuracy. Some releases have predictable surprise patterns. | Macro markets are pro-priced; retail directional won't beat consensus. | Probably skip - Fed paper says these are efficient. |

## Top three candidates to flesh out

The new context window should propose ONE of these (or a defensible
alternative grounded in the research) as the focus of Phase 2:

### Candidate 1: Politics x Calibration Recalibration (Politics x C)

**The pitch:** Le 2026 documents that political markets on Kalshi
are chronically underconfident across all horizons (price slopes
0.93-1.83). Isotonic recalibration should extract a "push toward
extremes" signal that's robust to the calibration regime. Bürgi
confirms politics is the second-most-biased category overall.

**Why it survives where weather didn't:** Weather's bias varies by
horizon (overconfident short / underconfident long), so we measured
the wrong regime. Politics is consistently underconfident, so any
horizon gives the same sign of edge. The 1.02pp per-trade gap
(Becker) is smaller than weather's 2.57pp but the **persistence**
across horizons makes it cleaner to capture.

**What's needed:** Resolved Kalshi politics markets with multi-day
price snapshots. The pipeline from Phase 1.5/1.6 needs minor adaptation
(politics series_ticker discovery, possibly multi-strike-per-event
handling because politics has both winner-take-all and multi-strike
markets).

**Pre-lock criteria proposal:**
- OOS ECE improvement >= 3x (more lenient than weather's 5x given
  smaller absolute bias)
- Median net edge after fees > 0 across walk-forward splits
- Hit rate > 60% on trades clearing 3pp edge filter
- Volume sufficiency: median per-market trades >= 50

### Candidate 2: Sports x Behavioral Surplus (Sports x E)

**The pitch:** Bartlett's mechanism: retail systematically overbets
YES (their team) on games that statistically settle NO. Sports has
43M trades and the biggest absolute volume of any category. Even a
small per-trade edge accumulates fast.

**Why it could work:** This isn't a forecasting bet; it's an
order-flow accommodation bet. We don't need to predict the games
better than Pinnacle - we just need to identify markets where the
YES base rate is meaningfully below 50% (NO-settling tendency) and
take the NO side as the resting maker.

**Risks:** Adverse selection in single-name games is highest among
all market types (Bartlett). The maker side gets picked off when
real information arrives (injury news, lineup changes). Jump/SIG
will be doing similar trades faster.

**Pre-lock criteria proposal:**
- Maker fill rate on resting NO orders > 50%
- Net edge after fees and adverse selection > 0
- Specifically test on game types where retail YES-overbet is most
  documented (e.g., underdog YES on long-shot teams)

### Candidate 3: Politics x Maker on Chronically Underconfident (Politics x H)

**The pitch:** Variation of Candidate 1 that doesn't require an
explicit calibration model. Le finds politics slopes are 0.93-1.83
across all horizons - i.e., prices are compressed. Post resting
maker bids at prices that BET ON the compression resolving toward
truth (i.e., bet that 70c contracts will resolve more often than 70%
of the time).

**Why simpler than recalibration:** No isotonic fit needed; the
strategy is just "post a maker bid X pp inside the current best
ask" on contracts with mid in some range. Calibration validation
becomes "did the bid fill, and did the contract resolve in our
favor?"

**Pre-lock criteria proposal:**
- Maker fill rate > 40%
- Realized P&L per filled order > $0.02
- Edge survives within walk-forward splits (no time-period
  cherry-picking)

## What NOT to do

1. **Do not re-open EC-1 KXHIGH.** Killed at Phase 1.6 gate. No
   third bite per locked methodology.
2. **Do not propose a Crypto sub-daily strategy.** HFT-dominated;
   residential latency loses. Le confirms platform-specific
   microstructure on Kalshi vs Polymarket is hard to exploit.
3. **Do not pursue macro (CPI/NFP/FOMC).** Fed paper validates these
   markets are pro-priced; retail can't beat the consensus.
4. **Do not assume Zerve numbers as evidence.** That community
   notebook produced an in-sample number that didn't survive Phase
   1.6's OOS gate. Any new strategy must do its own OOS validation.
5. **Do not train on pre-October-2024 Kalshi data without explicit
   regime adjustment.** The 2024 sign flip means pre-flip economics
   don't apply.

## Required next actions for the new context

1. Pick ONE candidate from the matrix above (or propose an
   alternative with research-grounded justification).
2. Write a methodology lock-in doc analogous to
   [phase-1.5-methodology.md](phase-1.5-methodology.md) before
   pulling new data. Lock the pass criteria, the dataset, the
   splits, and the "no third bite" commitment.
3. Run an adversarial critic pass on the proposal (spawn a Critic
   sub-agent like the one in Phase 1).
4. After critic OK, pull data, build dataset, run gate.
5. If gate passes, design the live strategy with full risk controls
   (drawdown breakers, kill switch, etc. from the Phase 1 risk
   brief).
6. Two weeks of paper trading before any live capital.
7. Live trading at $25 initial cap with $50 absolute ceiling.
