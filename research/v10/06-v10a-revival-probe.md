# V10-A Revival Probe: Economics Series Release Event Count

**Date:** 2026-05-27
**Purpose:** Verify whether Kim et al. (arXiv 2602.07048) replication on Kalshi Economics
markets has sufficient sample size to revive after the v10-A1 agent falsely killed the
angle via a wrong endpoint path.

**Context for this probe:** The v10-A1 agent tested `/markets/{ticker}/trades` (path
parameter), which returns 404 universally. The correct endpoint is
`/markets/trades?ticker=...` (query parameter), which returns 200 with real trade data.
The data IS accessible. The question is whether the SERIES AGE provides enough unique
release events for Granger analysis.

---

## Methodology

For each of 7 candidate Economics series, paginated ALL settled markets via
`/markets?series_ticker={series}&status=settled&limit=1000&cursor={cursor}`.
Extracted `close_time` per market and grouped by YYYY-MM-DD date. Each unique date
represents one macro release event (multiple strike contracts per event share the same
close date). Picked best-equivalent series per Kim's four tickers by event count.

Kim mapping applied:
- Kim KXCPI -> our KXCPI (direct match)
- Kim KXFEDFUNDS -> KXFEDDECISION (preferred) or KXEFFR
- Kim KXNFP -> KXUSNFP (preferred) or KXPAYROLLS
- Kim KXUNRATE -> KXECONSTATU3 (preferred) or KXU3

---

## Results Table

| Series | n_settled_markets | n_unique_release_events | oldest_release_date | newest_release_date |
|---|---|---|---|---|
| KXCPI | 27 | 2 | 2026-04-10 | 2026-05-12 |
| KXFEDDECISION | 5 | 1 | 2026-04-29 | 2026-04-29 |
| KXEFFR | 5 | 1 | 2026-04-01 | 2026-04-01 |
| KXUSNFP | 30 | 2 | 2026-04-03 | 2026-05-08 |
| KXPAYROLLS | 35 | 2 | 2026-04-03 | 2026-05-08 |
| KXECONSTATU3 | 46 | 2 | 2026-04-03 | 2026-05-08 |
| KXU3 | 20 | 2 | 2026-04-03 | 2026-05-08 |

## Kim-Mapped Series (4 best-equivalent)

| Kim Target | Our Series | n_unique_events | oldest_release_date |
|---|---|---|---|
| KXCPI (Kim KXCPI) | KXCPI | 2 | 2026-04-10 |
| KXFEDFUNDS (Kim) | KXFEDDECISION | 1 | 2026-04-29 |
| KXNFP (Kim) | KXUSNFP | 2 | 2026-04-03 |
| KXUNRATE (Kim) | KXECONSTATU3 | 2 | 2026-04-03 |

**Total unique release events across 4 Kim-mapped series: 7**

---

## Verdict

**FAIL -- V10-A CONFIRM-KILL on sample size.**

7 total unique release events across 4 series is catastrophically below the 60-event
PASS threshold and the 40-event MARGINAL threshold. Even below the 40-event floor,
Granger analysis requires at minimum 20-30 observations per series for meaningful
inference. No series has more than 2 unique release events.

---

## Root Cause: Series Age

All 7 candidate series appear to be newly launched. The oldest settled market in any
series dates to 2026-04-01 (KXEFFR). All series have at most 2 monthly release cycles
represented in settled data. Kim's paper presumably ran on KXCPI, KXFEDFUNDS, KXNFP,
and KXUNRATE when those series had years of history (each macro release is monthly,
so 60 events = roughly 5 years of monthly data).

The current Kalshi Economics series (KXCPI, KXFEDDECISION, KXUSNFP, KXECONSTATU3)
launched in early 2026 based on the settled-market evidence. At the monthly cadence
of macro releases, reaching 60 events would require approximately 5 years of operation
from today (mid-2031 at earliest). This is not a viable research horizon.

---

## Trade Data Verification (Step 5)

Verified that the correct trades endpoint works:

- Endpoint tested: `/markets/trades?ticker=KXCPI-26APR-T0.8&limit=100`
- Result: HTTP 200, n_trades = 100 (at limit, real data present)
- Confirms: Variant B trade-series construction IS accessible
- API regression from v10-A1 was endpoint PATH error, now confirmed fixed

The trade data layer is functional. The kill is on sample size, not data access.

---

## Kill Rationale

The correct kill rationale for V10-A is:

**Series age: all 4 Kim-equivalent Economics series on Kalshi launched in early 2026
and have at most 2 monthly release events in settled data (n=7 total across 4 series).
Granger analysis per Kim's design requires n>=60 unique events. At monthly cadence,
that requires ~5 more years of Kalshi Economics series operation. V10-A is killed on
sample size, not API access (the correct trades endpoint returns 200 with real data).**

The v10-A1 agent's kill was correct in VERDICT but wrong in RATIONALE. The endpoint
bug it identified (`/markets/{ticker}/trades` 404) is real but orthogonal: even with
perfect data access, 7 release events cannot support Granger analysis. The kill stands.

---

## Probe script

`scripts/v10/probe_v10a_revival.py` -- run with `.venv-kronos/Scripts/python.exe`
