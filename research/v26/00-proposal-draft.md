# v26 PROPOSAL (PRE-DRAFT, queued behind v25): true window-aggregate markets

**Status: DRAFT, written 2026-07-02 while v25 (gas pass-through) awaits its data. This
is the pre-staged pivot target if v25 nulls. NOTHING here is locked; no v26 data has
been pulled beyond the v25 universe scan (research/v25/scout-universe-scan.md). If v25
passes, this stays queued.**

## One-line idea

Trade Kalshi markets whose settlement is a SUM or AVERAGE of daily public observations
over a window (monthly rain totals in 11 cities, TSA weekly average screenings,
monthly launch counts) as a TAKER, when the arithmetic of the already-observed partial
window plus a climatological/empirical remainder distribution diverges from the market
price. The mechanism: as the window progresses, observed days deterministically pin an
increasing share of the settlement value; late-window prices must converge to the
partial-sum arithmetic, and any lag is a mechanical mispricing, not a forecast dispute.

## Why this differs from v25 and from every dead idea

- v25 (gas) is a POINT-READ of a slow series: the whole edge claim lives in a
  pass-through MODEL. Here the partial-window component is ARITHMETIC, not a model:
  by mid-window, half the settlement value is a published fact. The model only covers
  the REMAINDER, and late-window fires need almost no model at all.
- TARGET: physical count/aggregate series (rain, screenings, launches), not sports,
  not financial, no sharp reference book, no options surface.
- The known counter-prior: the MLB post-determination NULL showed Kalshi converges
  instantly AT determination on its most liquid series. But these are thin Economics/
  Climate series where determination arrives GRADUALLY over days (each morning's CLI
  report pins another increment), which is a different microstructure question than a
  single determination instant with a settlement race.

## Honest prior: ~10-12 percent (to be re-marked by a plan critic)

Tempering: capture phantom generalizes to any public arithmetic; volumes are thin
(NYC rain top strike ~2k contracts); rain remainder distributions are fat-tailed
(a single storm can blow through a strike); seasonal dormancy (snow relists in
October). Supporting: the arithmetic-pinning share is a mechanical, checkable
quantity; eleven cities x 12 months + 52 TSA weeks give real cluster counts; ACIS
daily data is free, keyless, and was verified live by the v25 scout; TSA publishes
next-day throughput.

## Sketch (for the eventual lock; constants illustrative only until locked)

- Universe: KXRAIN*M city-months, KXTSAW weeks, KXLAUNCHCOUNTM months, post-2024-10,
  settled, from /historical/markets + live settled.
- Signal: P_model(total > K) = P(remaining sum > K - observed partial sum) with the
  remainder distribution from the day-of-window-conditional EMPIRICAL climatology
  (30+ years of GHCN daily rain for the exact station; TSA daily counts since 2019,
  day-of-week + seasonality adjusted), computed strictly as-of (CLI/TSA publication
  lags respected).
- CONTROL: unconditional climatology for the WHOLE window (ignores the observed
  partial sum). The edge claim is that the market underweights the pinned component;
  the control catches general climatology miscalibration.
- Execution/fee/verdict machinery: reuse v25's (taker prints, +3c binding haircut,
  worst-case 0.07 quadratic fee, ISO-week or window-end clusters, cluster bootstrap,
  power floors, verdict lattice). The v25 lock's E-edits carry over as a template.
- Settlement-source audits first: CLI vs GHCN station identity per city (the v24
  weather work already mapped these), TSA revision policy, SPC "preliminary" count
  wrinkle (excluded unless resolved).

## Pre-registered data needs (all free, mostly verified)

- NOAA ACIS daily precip for the 11 Kalshi rain cities (VERIFIED live by v25 scout).
- TSA checkpoint throughput daily CSV (public; verify revision behavior).
- FAA licensed-launch log (public; verify update cadence).
- Kalshi trades for the chosen series (same puller as v25).

## What kills it at plan stage (invite the critic)

1. Print liquidity too thin for even 30 fired clusters after dedup.
2. Evidence the ladders already track the partial sum tightly (the market-matches-
   arithmetic NULL, cheap to detect and honest to report).
3. Remainder fat tails making late-window "near-certainty" fires rarer than the
   pinning intuition suggests.
4. Settlement-source wrinkles (SPC preliminary vs final; TSA revisions).

*Em-dash audit: clean (verified after write).*
