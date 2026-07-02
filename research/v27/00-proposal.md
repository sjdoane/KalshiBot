# v27 PROPOSAL: TSA weekly nowcast taker (flight data as the disparate driver)

**Date:** 2026-07-02. Hypothesis family ~#27. Pre-lock, pre-critic. No
settlement-conditioned Kalshi analysis run.

## Idea

KXTSAW settles on the Mon-Sun average of daily TSA screenings; TSA publishes Mon-Fri
by ~9am ET only, so during the final trading days (Fri open through Sun 11:59pm ET)
the three highest-variance days are unpublished to every participant. Aviation
activity is measured continuously by DIFFERENT public systems (flight schedules,
cancellation trackers, FAA ground-stop feeds). A nowcast of the unpublished days from
those disparate sources, anchored on the published partial week, prices the ladder
better than participants extrapolating seasonally, IF the thin ladder is not already
at that frontier. Universe verified: 87 settled weekly events Dec 2024 - May 2026
(1,750 markets, 59,345 banked prints) plus one new cluster forever after, weekly,
which is what makes this DEPLOYABLE: a live shadow accrues ~4 honest clusters/month.

## The two registered parts (the constructed method)

- **H1 (BINDING): reconstructible-as-of nowcast.** Inputs strictly limited to what
  the Wayback vintage audit proves knowable at fire time: TSA vintage partials
  (first-published values; 527-day reconstruction, intra-window self-consistent, 6
  tiny revisions, none over 0.5 percent), BTS scheduled-flight counts for the
  unpublished days (schedules fixed in advance), day-of-week and holiday structure
  estimated walk-forward on vintages. Standard v25-template execution (taker prints,
  binding +3c, worst-case quadratic fee, one position per market per ET day),
  cluster = ISO week, gates = power floor + CI + control + LOCO + regime guards.
  CONTROL = same machinery WITHOUT the schedule/flight terms (pure seasonal +
  partials): the informational delta under test is the aviation data.
- **D1 (REGISTERED DIAGNOSTIC, non-binding BY CONSTRUCTION): the perfect-information
  upper bound.** Same pipeline with the unpublished days' ACTUAL BTS flown/cancelled
  counts substituted in (deliberate look-ahead). D1 cannot route to capital ever; its
  pre-committed decision rule: if D1's clustered CI lower bound > 0 with mean >= 8pp,
  the disruption channel is worth a >= 8-week live shadow (where the true as-of feed
  exists: FlightAware live + nasstatus polling, self-archived) EVEN IF H1 nulls; if
  D1 shows nothing, the family dies entirely (no shadow). D1 uses flight outcomes,
  not Kalshi outcomes, as its extra information; it bounds the channel, it never
  validates it.

## Honest prior

H1 ~8-10 percent (the ladder may already price seasonality + schedules; that is the
capture-phantom shape and the control will say so). D1-justified-shadow ~25-30
percent (that PERFECT weekend knowledge beats the ladder somewhere is plausible; the
live question is how much survives a real feed and frictions). Family kill risks:
power (fires concentrate in disrupted/holiday weeks), the ladder simply matching the
nowcast (market-matches-frontier null, cheap to find), vintage gaps (112
Sunday-relevant snapshot days constrain which weeks are evaluable as-of).

## Data status (all verified today, research/v27/scout-flight-data.md)

- Kalshi: banked (87 events, prints deduped).
- TSA vintages: built (527 days; extension crawl to Nov 2024 running).
- BTS ground truth: verified through May 2026 (~4-5 week lag), pull running.
- Live as-of feed for shadow: FlightAware /live/cancelled + /yesterday + FAA
  nasstatus API, all verified live today; self-archiving starts with the shadow.
- OPERATOR FLAG (per instruction to name dataset needs immediately): a one-time
  HISTORICAL as-of pull from a paid flight API (FlightAware AeroAPI or Cirium, order
  ~$100) would upgrade D1 from an upper bound to an honest as-of backtest of the
  disruption term. Not blocking: free data carries H1, D1, and the live shadow.

## Kill risks invited at the plan critic

1. Week-mask reconstruction: which (week, day) partials were truly published at each
   print time, from vintages alone; any gap = that print unevaluable (no fill).
2. BTS schedule field as-of purity (schedules in the monthly file are as-flown
   records; the scheduled COUNT includes flights added/removed intra-week).
3. Fires clustering on 5-8 holiday/disruption weeks (power floor).
4. D1's look-ahead leaking into H1 through any shared fitted component.
5. The 2023-restatement-era factor leak (v26 E1): factors must come from vintages or
   pre-2025 archives with the restatement documented.

*Em-dash audit: clean (verified after write).*
