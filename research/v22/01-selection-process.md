# v22 Candidate Selection Process (scouts, council, verifier)

**Date:** 2026-06-11. Operator authorization: "research another methodology
and test another potential bot... be creative and cross disciplinary."
Run while v21 Candidate C0 collects (G-C0 verdict due by 2026-06-23).

## Stage 1: two parallel scouts

**Theory scout** (cross-disciplinary, 2025-2026 literature) ranked six
candidates: (1) hazard-clock decay on by-date markets (survival analysis,
prior 10-12pct); (2) new-listing cold-start maker premium (Glosten-Milgrom,
8-10pct); (3) flow-toxicity gate overlay (VPIN with exact taker_side labels,
15-20pct the pattern exists, overlay only); (4) strike-ladder shape relative
value (shape-constrained density estimation, 6-8pct); (5) cross-horizon
coherence lattice (de Finetti, 5-7pct); (6) affirmation-tax longshot
NO-maker (prospect theory, 3-5pct). Key literature: Becker microstructure
decomposition; Whelan 2026 (favorite-longshot coefficient decaying in 2025);
arXiv 2510.15205, 2601.01706, 2512.02436, 2604.10005.

**Data scout** (structural only, no outcome reads) verified: open_time
trustworthy (0 of 67.9M post-flip prints precede it); trade-age and
time-to-expiry distributions per category; 300-380 traded strike-ladder
events/week; the KXMVE prop series explosion (launched 2025-09-17, ~58-65k
listings/day, ~145k traded events in 2 months, ~1.7 prints/market); traps:
created_time unusable as listing anchor (51pct inverted vs open_time), 191k
prints after close_time (sports overruns), 2030 placeholder close_times,
KX-rebrand prefix break, age/TTE collinearity on short-lived markets.

## Stage 2: council (Realist, Quant, Builder), unanimous core

- Slate: new-listing cold-start (P1, only fundable candidate), flow-toxicity
  (P2, overlay screen; Quant upgrade: test it on v1's OWN live fills, which
  escape incumbent-maker selection), affirmation-tax (P3, cheap screen with
  pre-registered funding veto and 2025-decay clause).
- Excluded: hazard-clock (Quant: unidentified on prints, the stale-print
  confound IS the observable; Builder: heaviest build on thinnest series);
  coherence map (maintenance rot, researcher degrees of freedom, adjacent to
  the 0-in-2,791 dutch-book null); ladder-shape RV deferred to a zero-cost
  read on the accumulating C0 JSONL (Builder: the collection is already
  deployed).
- Structure: one slate lock; screens are rankers (non-inferential); one
  funded forward test; winner's-curse discounting (power at half the screen
  effect); economic floor gates; round-level kills.

## Stage 3: verifier (data-grounded adversarial check): NO-GO as written

The verifier reproduced the data claims against the full Becker parquets and
v1's perf log, and broke three load-bearing planks of the council text:

1. **The lifetime >= 7d filter CREATES a TTE confound instead of breaking
   one.** Cold bucket (age < 6h) median time-to-close 27.2 days; aged bucket
   (age > 3d) median TTE 0.26 days (61pct of its prints within 2 days of
   close). As council-spec'd, P1 measures near-settlement adverse selection,
   not cold-start premium. FIX: aged comparator = age > 3d AND TTE > 3d;
   lifetime floor raised to 10d; contrast within (category x TTE band).
2. **Qualifying volume is ~130 settled events/month (71-243), not 600-800**,
   dominated by KXNCAAFGAME/KXNFLGAME/KXBTCD/KXEPLGAME plus v21-graveyard
   Media/Entertainment series (must be labeled/excluded as in v21).
3. **The KXMVE stratum is self-contradicted**: only 7.9pct of KXMVE markets
   pass even a 7d filter; 44pct of volume-positive KXMVE markets have zero
   trade rows (print-selection bias); parlay legs share games ACROSS events
   so event_ticker clustering is insufficient there. Dropped to a
   no-inference descriptive table.
4. **Fee schedule changed 2026-02-05, after the whole Becker window.** The
   screen must charge era-correct (old ceil) fees for the historical window;
   FORWARD economics (floors, live probes) must use the Feb-2026 schedule in
   integer cents.
5. **The council capital plan breached the $100 ceiling** ($40 Stage-C on
   top of v1's ~$80) and silently assumed changing v1's bankroll fraction.
   FIX: capital split table per Jun-23 branch; Stage-C = min($40, $100 minus
   v1 balance); operator-approved v1 fraction restore is an explicit
   prerequisite.
6. **A maker "record-only shadow" contradicts the project's own v16 lesson**
   (fill-or-no-fill is unobservable without a resting order). The forward
   test must be LIVE 1-LOT PROBES, triple-gated, own intent prefix.
7. **Seasonality:** NCAAF/NFL/EPL are out of season until late August; a
   late-June probe start self-starves. Season-aware start required.
8. **P2 on v1's own fills is currently noise** (83 settled fills); reframe
   as an accumulating diagnostic read at n >= 200 fills / >= 60 event-day
   clusters, median split not deciles.
9. **P3's exact binomial is broken by within-event leg correlation**; fix =
   one leg per event (max fill volume), Poisson-binomial conservative bound,
   plus the standard event-cluster bootstrap as robustness; v18
   heavy-underdog-weak prior registered.
10. **External overhang:** state sports-contract litigation; pre-register a
    VOID (not null) kill if sports contracts become restricted for CA
    accounts mid-round.
11. **C0 interaction unspecified:** if G-C0 PASSES, Candidate C takes the
    build slot and v22 is screens-only this round; the C0 task's fate (and
    the deferred ladder-shape read date) must be branch-explicit.
12. Hazard-clock exclusion CONFIRMED but reclassified: "excluded for cost on
    forward data, unidentified on historical data," not graveyard.

**Verifier verdict: GO to re-lock with all amendments** (specification
changes only; no new data collection). The lock at
`research/v22/00-methodology-lock.md` is the re-locked text.
