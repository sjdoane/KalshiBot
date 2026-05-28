# v11 Replay-Prevention Notes for Cumulative Failure-Mode Taxonomy

**Round:** 16 (v11). **Date:** 2026-05-27.
**Inherits:** research/v10/03-methodology-meta.md (F1 to F10),
CLAUDE.md Round 15 V10-A kill addition (F11).

v11 did NOT discover a new top-level failure mode. It DID surface a
new instance of an existing mode plus two operational lessons worth
adding to the cumulative taxonomy for future rounds.

---

## New instance of F1 (Data ceiling / coverage / dropout)

### F1-tz-mismatch: cross-venue date-timezone mismatch silently drops events

Surfaced by Phase 3 critic KILLER-1. The Kalshi ticker date is
local-ET; the the-odds-api commence-time is UTC; for evening games,
the two dates differ by 1 calendar day. A naive match on
`ticker_date == commence_date_utc` excludes 92% of NBA events
(evening commences), 27% of NFL events, and 24% of MLB late-night
events.

**Replay check for future rounds:** any cross-venue join must
explicitly verify timezone alignment. For each candidate (sport,
event), check whether the join key timezone is consistent across
sources. Acceptable resolutions: (a) accept both `event_date` and
`event_date + 1 day` as match candidates; (b) convert all dates to a
single explicit timezone (e.g., America/New_York for US sports
markets); (c) match on commence_time within a +/- few hours tolerance
rather than date equality.

**Diagnostic before lock:** during methodology lock, generate a
sample join and verify the match rate by sport. A match rate below
80% is a structural warning; below 50% (which NBA hit pre-fix at 10.5%)
is a kill condition.

**Cost of this lesson:** approximately $5 of LLM time was spent
attributing the 10.5% NBA match rate to underpowered NBA sportsbook
movement rather than to a date-parsing bug. Recovery via Phase 4
salvage took an additional small LLM expense plus 0 external
credits (the API data was already pulled).

---

## Operational lesson 1: Lock authors should pre-register an offset sensitivity range

v11 lock v2 Section 3 pre-registered `COMMENCE_OFFSET = 3.5h`
(close_time minus 3.5 hours = game commence estimate). Phase 3 critic
KILLER-3 (downgraded to IMPORTANT) found that F-stat varies by 38x
across the +/- 1 hour range of plausible offsets, including F=0.63
(no signal) at 2.5h.

The pre-registration was theory-grounded (MLB game length 3 hours +
ceremony/warm-up = roughly 3.5h close-to-commence). But the lock did
not specify what F-stat behavior would constitute "robust" vs
"fragile" to offset.

**Lesson:** future locks that depend on a derived target time (T-N
hours, T+N hours, etc.) should pre-register an offset-robustness
specification:

- The chosen offset value (single point estimate from theory)
- The offset sensitivity range (e.g., +/- 0.5h or +/- 1h)
- The gate logic across the range (e.g., "signal must clear at all
  offsets in the range" or "signal must clear at the center plus 2 of
  4 adjacent offsets")

Without pre-registration of the robustness gate, post-hoc evaluation
of the sensitivity range can either look like vindication (if signal
holds) or like a fragile finding (if signal collapses), depending on
the analyst's prior.

---

## Operational lesson 2: Always sanity-check the data layer BEFORE locking gates

v11 lock v2 spent 600+ lines specifying gate criteria predicated on
F4 Option B (DETERMINISTIC_HAIRCUT from Becker MARKETS snapshots).
Phase 2 Step 1a discovered in approximately 5 minutes of data probing
that Becker MARKETS is one-row-per-ticker post-settlement; no
intraday orderbook snapshots exist. The F4 Option B gate was
structurally infeasible.

The lock had to be amended (v3, Granger-first scope) before Phase 2
could fire. The amendment cost approximately $0.10 of LLM time, but
the original v2 lock contained a substantial Section 3.4 + Section 4
G_F4 + Section 4 G_F11 specification that was rendered moot.

**Lesson:** before locking a gate that depends on a specific data
field, run a 5-minute data probe to verify the field exists at the
required granularity and timestamp. This is a strict generalization of
F11 (Dataset Schema Phantom): not only verify the field exists, but
verify it has the time-series structure the gate needs.

Concretely:
- F11 V10-A check: does the schema have field X? (binary yes/no)
- F11 v11 extension: if yes, what is the snapshot cadence of X? (time
  distribution analysis)

For Becker MARKETS, the answer to "is yes_ask in the schema" is yes,
but the snapshot cadence is "one per ticker, fetched post-settlement,
all values 100 or 0 or 1." The gate was specified against a
non-existent intraday structure.

---

## Updated cumulative failure-mode taxonomy

F1 to F11 are unchanged in TYPE. v11 added one INSTANCE under F1
(tz-mismatch) and two OPERATIONAL LESSONS.

| Mode | Type | New instance from v11 |
|---|---|---|
| F1 | Data ceiling / coverage / dropout | F1-tz-mismatch (date-timezone) |
| F2 | Sample size insufficient | (no v11 instance) |
| F3 | Domain mismatch | (no v11 instance) |
| F4 | Trade-print vs orderbook ASK | (v11 sidestepped via Granger-first deferral) |
| F5 | Single-strategy bias / no comparator | (not tested in Granger phase) |
| F6 | Compounded multiple-test inflation | (v11 used pre-registered single cell) |
| F7 | Stale post-settlement price | (not relevant to Granger) |
| F8 | Gate-regime mismatch | (v11 derived gate from cost structure in v2, not used in v3) |
| F9 | Side-selection bias | (not tested in Granger phase) |
| F10 | LOO / LOCO fragility | (v11 LOCO-by-bookmaker passed) |
| F11 | Dataset schema phantom | (v11 confirmed; F4 Option B infeasible on Becker) |

Operational lessons added to the inherited taxonomy:

- **L1:** lock authors should pre-register an offset-sensitivity range
  for any derived target time
- **L2:** data probe before locking gates against specific fields
  (F11 strict generalization)

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or
U+2013 throughout.*
