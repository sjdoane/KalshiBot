# v1 fill-rate kill + dynamic sizing decision (2026-05-30)

After the settlement fix re-armed v1's kill triggers, v1 tripped `fill_rate_low`
("fill rate 0.173 < 0.3 after 168 attempts") and halted. The trigger had been
DORMANT for weeks (it only evaluates inside record_settlement, which never ran
until settlement was fixed), so it fired on a pre-existing low fill rate.
Operator: do NOT make the decision to kill v1; reassess; look at what fills;
and make per-bid size dynamically bankroll-scaled (auto-detect deposits), and
confirm v14 already does this.

## Real-data: what fills vs what doesn't (the operator's ask)
Fill rate is driven by the SERIES, not price (filled + cancelled both cluster
70-79c). v1 bids across ~40 series; most fills come from a few:
- FILL: KXNBAPLAYOFFWINS 62%, KXPGATOP20 75%, KXNFLGAME 50%, KXNCAABBPLAYOFFS 40%.
- WASTE (never fill): KXWCGAME 3/26 (10%), KXUFCFIGHT 2/19, KXPGAMAKECUT 0/13,
  KXWCSTAGEOFELIM 1/11, KXWNBAWINS 1/9, KXNBADRAFTTOP 0/8, KXSTARTINGQBWEEK1 0/8,
  ~20 more 0%-fill one-offs.
Tension: the BEST-fill series (KXNBAPLAYOFFWINS, KXPGATOP20) are NOT Becker-
validated; the validated 5 (KXMLBGAME/KXATPMATCH/KXNFLGAME/KXNCAAFGAME/KXWTAMATCH)
are seasonal and barely filling now.

## Council (4 members) + verifier-synthesis decision
- **A: demote fill_rate from a halting KILL to a logged health metric**
  (`KillTriggerConfig.fill_rate_kill=False` default), and reset the contaminated
  cumulative counters (they accrued during the dormant era + count still-resting
  bids as non-fills). Fill rate is a liquidity diagnostic, not an EV signal; a
  patient deep-favorite maker is inherently low-fill. The EV-relevant kills
  (drawdown, consecutive-loss, rolling-mean, single-loss) stay armed. Directly
  honors "do not kill v1." KillTriggerMonitor is v1-only (v14 has its own
  check_kill_triggers), so this cannot affect v14.
- **B: denylist the proven never-fill series** (new `LOW_FILL_DENYLIST` of 7,
  unioned into `DEFAULT_SERIES_DENYLIST` so a restart applies it). Do NOT enable
  the restrictive 5-prefix PERSIST allowlist: it would starve v1 to near-dormant
  (seasonal), against "keep it productive." The validated allowlist is the gate
  for SCALING CAPITAL later, not for staying alive now. The EV kills (not fill
  rate) catch genuine EV failure on the unvalidated-but-filling series.
- **C: make per-bid sizing dynamic** (bankroll-scaled like v14) but DON'T
  increase stakes now. `v1_per_bid_contracts(...)` = floor(V1_PER_BID_FRACTION
  (0.03) * v1_cap_total / price), floor 1. Calibrated so the current ~$48
  bankroll yields 1 contract (= today's fixed $0.95), auto-scaling as the
  operator deposits ($100 total -> 2 contracts, $200 -> 4, $500 -> 12). The edge
  is live-unconfirmed (n=5, -$0.74), so growth comes from the operator's money,
  not from raising the bet. Based on v1_cap_total (gross 60% slice), NOT the
  headroom-shrunk cash, so no double-cap with the aggregate budget gate.
- **v14 dynamic sizing CONFIRMED functional**: reads /portfolio/balance every
  loop, sizes each fire as 0.5*0.3*0.40*live_bankroll/price, auto-detects
  deposits/withdrawals. No hardcoded dollars.

The Quant member argued for the validated allowlist on pure EV grounds (filling
on unvalidated series is +variance, plausibly -EV given -4.93pp adverse drift);
the synthesis keeps v1 active (denylist, not allowlist) but layers the EV kills
as the real safety net and keeps per-bid tiny, so the unvalidated exposure is
low-stakes and self-policing. Allowlist deferred to the capital-scale-up gate.

## Implementation
- `kill_triggers.py`: `fill_rate_kill` flag (default off, metric-only) +
  `clear(reset_fill_counters=True)`.
- `market_scanner.py`: `LOW_FILL_DENYLIST` (7 series) unioned into the default.
- `paper_trade_favorite.py`: `v1_per_bid_contracts` helper + dynamic sizing at
  the placement site (v1_cap_total hoisted to function scope) + heartbeat now
  shows fill_rate (metric, no kill) and per-bid sizing ($/% of live cap).
- `scripts/reset_v1_kill.py`: one-shot to clear tripped + reset counters.

## Review + verification
Post-impl review: 0 Critical / 0 High. Confirmed EV kills intact + v14
untouched; no double-cap; sizing = 1 contract at the current bankroll (no stake
increase); denylist has no typos and no overlap with the validated allowlist.
1 Medium (reset-script docstring PowerShell syntax) fixed. 124 targeted tests
pass (fill-rate demote, clear-reset, sizing-scaling, denylist). Real-data:
per-bid = 1 contract at the live $48.53 bankroll, scaling with deposits;
denylist excludes all 7 never-fillers.

## Operator restart for v1 (these take effect on restart)
1. Clear the kill + reset the fill window:
   `.venv-kronos/Scripts/python.exe -m scripts.reset_v1_kill --i-mean-it`
2. Restart v1: `.\scripts\restart_bot.ps1` (or Stop/Start-ScheduledTask
   KalshiLiveBot). The trimmed universe + dynamic sizing apply on launch.
v1 resumes placing; fill-rate is now a heartbeat metric (no longer halts);
per-bid auto-tracks the bankroll. Watch the heartbeat fill_rate line trend up
under the trimmed universe. Re-review the denylist as live data accumulates;
enable `--allowlist` only when scaling capital onto the validated 5.
