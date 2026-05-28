# v11 Phase 2 Step 1a: Becker-side Dataset Prep

**Round:** 16. **Phase:** 2 Step 1a (no external spend).
**Date:** 2026-05-27. **Script:** scripts/v11/phase2_step1a_becker.py

Per methodology lock v2 Section 8 Step 1: Becker-side prep that does not require the-odds-api purchase.

## Universe

- Total settled game-resolution markets in 3 sports (close_time >= 2024-10-01): n=5574
- Per-sport breakdown:
  - KXMLBGAME: n=4408
  - KXNBAGAME: n=738
  - KXNFLGAME: n=428

## Per-sport median close_time (split boundary)

- KXMLBGAME: 2025-07-09T02:59:13.322792+00:00
- KXNBAGAME: 2025-10-29T05:39:48.076391+00:00
- KXNFLGAME: 2025-09-28T21:44:37.882283+00:00

## Dev / val / purged split sizes

| sport | dev | val | purged |
|---|---|---|---|
| KXMLBGAME | 2108 | 2110 | 190 |
| KXNBAGAME | 310 | 324 | 104 |
| KXNFLGAME | 194 | 202 | 32 |

## Pilot-A (50 events: haircut, X, Y)

- Total: n=50
- Per-sport: {'KXMLBGAME': np.int64(17), 'KXNBAGAME': np.int64(17), 'KXNFLGAME': np.int64(16)}
- Date range: 2025-04-16 02:39:09.736516+00:00 to 2025-08-10 04:04:51.376793+00:00

## Pilot-B (50 events: sigma)

- Total: n=50
- Per-sport: {'KXMLBGAME': np.int64(17), 'KXNBAGAME': np.int64(17), 'KXNFLGAME': np.int64(16)}
- Date range: 2025-04-16 20:32:15.384691+00:00 to 2025-08-10 23:36:08.175249+00:00

## G_F7 assertion (no trades within 60s of close in qualified universe)

{
  "n_trades_within_60s_of_close_diagnostic": 282,
  "tickers_affected_diagnostic": 24,
  "n_qualified_trades_within_60s_of_close_ASSERTION": 0,
  "g_f7_assertion_passes": true
}

Diagnostic note: the diagnostic counter shows late-60s trades exist on some tickers (pre-close prints, taker_side=no). The G_F7 ASSERTION runs against the qualified universe (T-6h to T-1h window) which excludes the last 60s by construction. The assertion passes trivially because the qualified universe is disjoint from the last-60s buffer.

## F4 Option B feasibility probe (the load-bearing finding)

{
  "kxmlbgame_total_tickers": 4428,
  "kxmlbgame_multi_snapshot_tickers": 0,
  "yes_ask_distribution_top6": [
    {
      "yes_ask": 100,
      "n": 4269
    },
    {
      "yes_ask": 1,
      "n": 129
    },
    {
      "yes_ask": 0,
      "n": 2
    },
    {
      "yes_ask": 2,
      "n": 1
    },
    {
      "yes_ask": 5,
      "n": 1
    },
    {
      "yes_ask": 63,
      "n": 1
    }
  ],
  "f4_option_b_feasibility": "INFEASIBLE: MARKETS is one-row-per-ticker post-settlement; yes_ask is dominated by 100 (YES wins) and 1 (NO wins). No T-6h to T-1h intraday orderbook snapshot exists in Becker."
}

## Verdict on Phase 2 Step 1a

Becker-side prep COMPLETE. The pilots are identified and persisted to data/v11/pilot_events.parquet. G_F7 status is reported above.

**F4 Option B infeasibility is the load-bearing finding.** Per methodology lock v2 Section 3.2 escalation rule, the lock is INVALID at Phase 2 stage unless operator authorizes either:

(a) v3 lock with F4 Option A (forward live spot-check, no in-session haircut applied; verdict PROVISIONAL pending 30-day post-backtest live ask vs trade-print median check)

(b) v3 lock with in-session live probe to derive haircut from currently-open game-resolution markets via Kalshi orderbook polling (smaller sample but in-session-computable)

(c) NULL Track 1 due to F11 (dataset schema phantom; Becker has no orderbook history at trade time and no synthetic source recovers it)

Operator decision required before Phase 2 Step 2 (the-odds-api purchase). Even Path (c) avoids the $59 external spend.

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*