# v28 FINAL-VERDICT: RT score ladders = H-A killed pre-lock; D' FEASIBILITY-CENSUS PASS (downgraded); stage-1 live read DEPLOYED

**Date:** 2026-07-03. Family ~#28. Verdict per the locked lattice as amended by the
adversarial verdict critic (04-verdict-critic.md, PASS-DOWNGRADED; the critic
reproduced the run byte-identically from lock commit e0fc76f). Capital $0, FLAT.

## H-A (live-certifiable bound): KILLED PRE-LOCK

Zero fires at the outcome-blind projection: the registered conservative arrival cap
never decides inside the executable band during archive-visible trading (38 decided
prints, all beyond 0.955). The v26 kill shape, now confirmed on a 15M-contract
family.

## D' (realized-arrival bound): FEASIBILITY-CENSUS PASS, explicitly NOT an edge

The gates passed (18 fires / 9 movie clusters, mean +6.8pp, CI [+2.5, +10.0], net of
worst-case frictions), and the verdict critic DOWNGRADED the class with these
binding facts, all of which this document adopts:
- The win record was deterministically implied at the lock commit (0-S coverage
  34/34 guarantees every valid-archive D' fire wins); the CI measures fire SIZE, not
  win probability. Zero out-of-sample content. The +6.8pp figure MAY NOT be quoted
  as an edge.
- What the census establishes: over ~5 months, 18 prints (16 markets, 9 movies)
  traded at or below 0.955 on outcomes already decided by review arithmetic, against
  2,385 decided prints (99.25 percent) already priced past breakeven. Two off-market
  flukes carry 59 percent of the P&L; the quotable ex-fluke statistic is +3.1pp
  [+2.1, +4.1] per contract. 16 of 18 prints show the taker on the opposite side;
  the side-matched sensitivity is 2 fires / 2 clusters.
- The 0-S refinement history (naive form -> validity rule -> bound-coverage) was
  each individually necessary for the pass and adopted after seeing violations;
  ruled honest audit repair (the final form is the correct test for a realized-
  arrival bound), hence downgrade rather than refutation, and it is on the record.
  The alternate reading of the D' spec (last-pre-close-row fallback) produces a
  FAILING result (100 fires, 33 busts, mean -7.0pp) and was ruled anti-conservative;
  the conflict is documented, not hidden.
- Live replicability: 0 of 18 fires were decidable in real time under the registered
  cap. "NOT the project's first validated edge, but the first family whose
  executable-print census came back nonempty."

## The deployed stage-1 $0 live read, and its PRE-COMMITTED gate

scripts/v28/live_rt_read.py runs every 30 minutes (scheduled task KalshiV28RTRead,
task and script self-expire ~2026-09-01), polling live RT pages (verified unblocked)
and Kalshi quotes for all open KXRT events, self-archiving the state series, and
computing the LIVE bound under the frozen envelope rule (cross-movie max arrival
ratios by remaining-day, monotone envelope from the banked vintages, times 2.0, with
the 24h-own-rate term and floor 5). Its first pass produced three in-band rows under
a retracted floor-only rule (the floor was provably too tight at long horizons);
those rows are STRUCK from gate evidence, the envelope rule replaced it before
deployment, and the second pass correctly logged zero decided rows.

READ GATE (pre-committed here, immutable): if the log records >= 1 `decided_in_band`
row under the ENVELOPE rule by 2026-08-31, the single v27-A3 shadow opens (weeks
13/26/39, one shadow ever, H-B strictly a reported overlay). If ZERO such rows
accumulate across >= 6 movie closes, the family DIES and no shadow ever opens.
Slug gaps (EVI/ODY/SPI/AVE/DUNE candidates pending page creation) are logged
honestly by the engine; a gap that persists past a movie's close excludes that
close from the six.

## Ledger

Families ~28. This round: H-A (killed pre-lock), D' (census pass, downgraded);
zero post-data strata; the E5-margin code deviation and the D'-spec reading conflict
are documented in 04 with their recomputed alternates. Banked: the 43-event vintage
layer (691 rows, settlement-basis-validated), the arrival-ratio envelope table, the
live read engine and its accumulating self-archive.

*Em-dash audit: clean (verified after write).*
