# v22 H-3 pre-count gate result (2026-06-11)

Structural query per lock v2 (population definition only; no outcome
aggregates): finalized yes/no markets, open_time >= 2024-11-01, close_time
< 2025-11-01, lifetime >= 10d, KXMVE excluded, prints 3-97c with age since
open < 6h.

**Result: cold_events = 1,188 (gate >= 300: PASS), cold_prints = 39,152,
distinct prefixes = 941.**

The round proceeds to the remaining pre-screen artifacts in lock-mandated
order: (1) dated per-series maker-fee table from archived Kalshi fee
schedules (or dual-fee conservative gate where the archive is silent),
(2) frozen rebrand-unified category map (structural freeze script,
committed before the screen script exists), then (3) the screen script
(cell construction + joint two-sample cluster bootstrap), code-reviewed
before its output is read. Note for the K-P1 evaluation: 1,188 is the RAW
cold-event count; the >= 300 kill floor applies to the POST-MATCHING
included population.
