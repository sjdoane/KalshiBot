# v24 strategic pivot: from backtestable edges (all walled) to live-only mechanical edges

**Date:** 2026-06-30. This is the synthesis of the whole project plus this session's
four newly-closed angles (index realized-vol NULL, event-vol REJECTED, sports-props
BLOCKED, cross-market structural-arb WALLED static). It reframes what to try next.

## The unifying lesson

Every edge the project has tested is a BACKTESTABLE edge: something you can measure on
Kalshi's public trade history. All of them are walled, by one of two mechanisms:

- Taker capture phantom (7 live/data confirmations): the market prices public info into
  the ask at least as well as a retail model, so crossing the spread captures nothing.
- Maker adverse selection: resting quotes fill more on the adverse book.
- (And this session) Static structural arbs: within-event ladders are kept consistent.

The deeper pattern: ANYTHING measurable on public history has already been priced or
arbed by the time you can trade it. That is almost tautological in a semi-efficient
venue. So the backtestable-edge search is genuinely exhausted.

## What is NOT walled: edges that cannot be backtested

Kalshi serves NO historical orderbook (confirmed in v9: `/orderbook?ts=` is ignored,
settled books are empty). So a whole class of edges is invisible to backtesting and,
precisely for that reason, may remain un-arbed by other retail quants who (like this
project until now) only backtest. These are LIVE-ONLY mechanical / speed edges, where
the edge is a timing/mechanics gap, not an information advantage, so the capture phantom
does not apply. Two concrete candidates:

1. **Transient dutch books.** During a fast move (equity open, FOMC 2pm, CPI/NFP 8:30am,
   a sharp crypto candle) MMs pull or lag their quotes and a ladder momentarily crosses,
   yielding a locked basket < $1. Risk-free when it fires; capturable by a retail taker
   because Kalshi is not HFT-speed. Tool built: `scripts/v24/kalshi_arb_scanner.py
   --monitor`. Static scans are clean; the value is strictly during volatility.

2. **Post-determination convergence.** After an outcome is KNOWN (final out/buzzer, a
   "by date Y" event occurs, a threshold is irreversibly crossed) but BEFORE the market
   settles, the price sometimes still trades away from 0/1 (e.g. a determined winner at
   0.96-0.98). Buying the determined side is near-risk-free with ZERO forecast risk, so
   the capture phantom cannot apply. The edge is recognizing determination faster than
   the slowest MM adjusts. It needs a live outcome feed (ESPN/box-score for sports; the
   settlement source for macro) aligned to the live Kalshi price.

## Why this is the right pivot (and its honest risks)

- It is genuinely new: every prior idea was a forecast; these are mechanics/speed.
- It escapes BOTH walls (no forecast = no phantom; take/lift immediately = no resting
  adverse selection).
- It is validated the ONLY way it can be (live monitoring), which is also why it may be
  un-competed.
- Risks: (a) both are RARE (transient arbs need a vol spike; determination gaps need a
  slow MM), unknown frequency/size since not backtestable; (b) execution has LEG/latency
  risk (place both arb legs IOC and unwind if one fails; for determination, the price
  may snap before the taker fills); (c) capturing them profitably eventually needs a
  fast auto-execution layer with its own risk controls, which is a live-capital build.

## Plan (data-first, no capital until frequency/size justify a bot)

1. Run `kalshi_arb_scanner.py --monitor` during real volatility windows (US equity open
   9:30 ET, FOMC/CPI/NFP releases, active crypto) to MEASURE whether transient arbs
   occur and their edge/size. Log every sighting.
2. Build a post-determination monitor: for a live slate (e.g. tonight's MLB games via a
   scores feed), track the Kalshi winner-market price in the seconds/minutes after the
   game ends, and measure the convergence lag (does it trade < 0.99 after the result is
   final?). Log the gap and its duration.
3. Only if either shows a real, recurring, sized gap: build a fast auto-exec layer
   (reusing `LiveOrderManager`) with atomic/IOC placement, a hard per-fire cap, and a
   kill switch. Until then, no capital.

This keeps the loop alive on the one frontier that is not yet proven walled, and it does
so honestly (measure first, deploy only on evidence).

## LIVE RESULT (2026-06-30 night): post-determination convergence = NULL

Ran `postdet_monitor.py` for 90 x 60s through 8 MLB game settlements (PITPHI, CWSBAL,
DETNYY, NYMTOR, STLATL, CINMIL, WSHBOS, TBKC), logging KXMLBGAME bid/ask/status +
the-odds-api scores to `scratchpad/postdet_log.jsonl`. Findings:

- At EVERY settlement, the winning side's last pre-settlement quote was bid 0.99 / ask
  **1.00** (loser 0.00 / 0.01). There was NO poll where a decided winner could be BOUGHT
  (ask) below 1.00. Tracing the ask into settlement (e.g. STLATL): it oscillated
  0.90-0.96 while the game was genuinely in-progress-and-uncertain, then jumped straight
  to 1.00 at determination and settled ~1-2 min later. Sub-1.00 winner asks (235 of them)
  occurred ONLY while the result was still uncertain = the live win probability = the
  sharp-line capture phantom (the leading team can still lose), NOT a determined outcome.
- There is no gap between "outcome determined" and "ask still < 1.00": the ask converges
  to 1.00 AT determination. The only near-arb (buy the 0.99 BID as a maker) nets ~0 after
  the KXMLBGAME maker fee (ceil(1.75*p*(1-p)) ~ 1c at p=0.99).
- Bonus finding: the-odds-api `/scores` reported 0 completed even at the final poll while
  Kalshi had already settled the games. the-odds-api is SLOWER than Kalshi's own
  settlement, so it cannot serve as a fast determination detector; beating Kalshi would
  need a sub-second feed AND a window, and there is no window.

Verdict: post-determination convergence is a clean live NULL. Kalshi is efficient in the
settlement/mechanics dimension too, not just the informational one. The live-mechanical
frontier now has one candidate left: transient dutch books during volatility (the
`kalshi_arb_scanner.py --monitor` tool; 0 in calm conditions, needs a vol window to
measure). That is the only Kalshi edge-class not yet conclusively walled, and its EV is
unknown and likely small.

## Bottom line for the project

Across 15+ rounds plus this session's five newly-closed angles (index realized-vol,
event-vol, sports-props, static structural-arb, post-determination), Kalshi is
comprehensively efficient for a retail account across BOTH the informational and the
mechanical/settlement dimensions. A real edge now requires a new external advantage the
project does not have: a sub-second private/data-speed feed, an auto-execution latency
layer aimed at transient arbs during volatility, or materially more capital for
fee-rebate economics. Absent that, capital stays flat; the thorough negative result is
the honest deliverable. The one standing, $0, non-phantom tool worth keeping live is the
transient-arb monitor, run during volatility windows.

*Em-dash and en-dash audit: verified clean after write.*
