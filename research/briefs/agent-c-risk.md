# Agent C Brief: Risk Management & Bot Failure Modes (Kalshi, $50-100 Bankroll)

Date: 2026-05-22. Scope: prevent the operator's #1 failure mode (losing more than the cap due to a bug, not a strategy loss). Recommendations are tuned for a $50 starting bankroll, $100 hard cap.

## 1. Position Sizing for a $100 Account

**Kelly math (full).** f* = (bp - q) / b, where p = true win probability, q = 1 - p, b = net odds. On a Kalshi YES at price c that pays $1, b = (1 - c) / c. Example: edge model says p = 0.55 on a contract trading at 0.50, so b = 1, q = 0.45. Full Kelly = (1 * 0.55 - 0.45) / 1 = 0.10, i.e., bet 10% of bankroll ($5 on $50).

**Why almost no pro uses full Kelly.** Full Kelly assumes p is known exactly. In practice p is an estimate with noise. If you overestimate edge by even 50% (very easy with a small sample), full Kelly puts you above the optimal point, where geometric growth turns negative. Empirical drawdowns of 50-80% are routine even when the underlying edge is real. The Kelly criterion was designed for repeated independent bets with known probabilities; quant strategies have neither.

**Fractional Kelly (1/4 to 1/2).** Standard practice. Half-Kelly captures ~75% of the growth rate of full Kelly with roughly one-quarter of the variance. Quarter-Kelly is the right starting point when your edge estimate is young or noisy. Estimating p: use Brier-calibrated probabilities from a model with at least 100+ resolved markets of out-of-sample evidence; without that, do not trust p enough to feed it into Kelly at all.

**Fixed fractional (always risk N%).** Simpler, ignores edge size. Common N = 1-2% per trade.

**Flat sizing.** Constant dollars per trade. Simplest, no model dependency.

**Kalshi minimums verified.** Contracts trade in 1-cent increments from $0.01 to $0.99 and settle at $0 or $1. The platform's smallest meaningful trade is 1 contract at the listed price; practical floor is ~$1-5 of notional. A $50 bankroll therefore supports at most ~10-50 concurrent positions before granularity dominates sizing.

**RECOMMENDATION: Flat sizing at $1-2 per position for the first 50 settled trades. Then switch to Quarter-Kelly capped at 5% of bankroll per trade.** Math: $50 bankroll, 50 positions max, $1 each = max gross exposure $50. With a $100 cap, this leaves headroom for live mistakes. Kelly-style sizing on $50 is mathematically defensible only when each position has at least ~$1 of granularity AND p has been validated; both fail until live data accumulates. The integer-contract constraint already imposes near-flat sizing for sub-$5 positions, so embrace it. Reassess at $200 bankroll.

## 2. Drawdown Management & Circuit Breakers

A 10% loss on $50 is $5 - small in dollars but a meaningful signal that the model is wrong, the code is wrong, or the regime shifted. Treat drawdowns as evidence, not just damage.

**Recommended thresholds for $50-100 bankroll:**
- Daily soft pause: -5% of bankroll ($2.50 on $50). Stop new entries, hold existing.
- Daily hard halt: -10% of bankroll ($5). Cancel open orders, close speculative positions, sleep 24h.
- Weekly hard halt: -15% of bankroll cumulative ($7.50). Pause 7 days, manual review required.
- Total drawdown halt: -25% from peak ($12.50 from $50 peak). FULL STOP. Manual code review and operator approval required to resume.
- Absolute floor: $25 remaining. Auto-flatten and shut down. Below this, slippage and fee drag will eat any edge.

**Resume rules.** No auto-resume below the absolute floor. After daily/weekly halts, require a manual one-command resume (e.g. `bot resume --confirm`) AND a written reason logged. Auto-resume invites the bug that caused the halt to repeat overnight.

## 3. Quant Bot Failure Modes

- **Overfitting.** Detect with walk-forward analysis, purged k-fold (Lopez de Prado 2017), combinatorial purged CV (CPCV outperforms walk-forward on PBO and Deflated Sharpe per Arian et al. 2024), and parameter-stability heatmaps. Mitigate with deflated Sharpe ratio (DSR) corrects for the number of trials. Require DSR > 0 before live capital, not raw Sharpe.
- **Slippage on illiquid books.** Kalshi orderbooks for non-political/non-sports markets are routinely 5-10 contracts deep at top of book. Effective fill is far from quoted mid. Detect with order book snapshots at trade time; mitigate by capping order size at ~20% of top-of-book depth and using limit orders inside the spread, not market orders.
- **Fee drag.** Kalshi taker fee at $0.50 strike is $0.0175/contract = $0.035 round-trip (3.5% of $1 notional). If your model edge is 3% you are net negative. Worked example: 100 contracts at $0.50 with 3% edge wins $3, costs $3.50 in fees, net -$0.50. Mitigate by avoiding 40-60 cent strikes when possible (fees scale by p*(1-p)), preferring maker orders (25% of taker), and requiring modeled edge of at least 2x estimated round-trip cost.
- **Lookahead bias.** Sources: (1) timestamp misalignment between data sources/timezones, (2) using non-lagged features, (3) economic data without first-print vs revised handling, (4) as-of joins that grab the next-bar value, (5) test/train leakage when label windows overlap features. Mitigate with strict point-in-time data (PIT) and freqtrade-style lookahead-analysis tools that perturb test data and compare results.
- **Survivorship bias on Kalshi.** Settled and delisted markets must be in the backtest universe at the timestamps they existed. Build the universe at-time-T (the markets available on Kalshi as of T) not the markets that exist today. Without this, success rate is inflated.
- **Regime change.** Strategy that worked in election season fails post-election. Mitigate by regime tagging (election cycle / Fed cycle / sports season), live performance monitoring vs backtest, and automatic strategy disablement on N-trade rolling Sharpe drop > 50%.
- **Fat-finger orders.** Decimal placement, contract-count vs cents confusion, signed vs unsigned size. Mitigate with pre-trade sanity bounds in code (see Section 5).
- **Infrastructure outages.** Mid-fill network drop, Kalshi API outage, VPS reboot, laptop sleep. Mitigate with idempotent orders (client_order_id), persistent state in SQLite (not memory), and reconciliation loop on every restart.
- **API key compromise.** Kalshi uses RSA-PSS signed requests; the private key is downloaded once and never retrievable. Blast radius if leaked: an attacker can place orders, cancel orders, withdraw to the linked bank account if withdrawal API is enabled. Mitigate by storing the PEM in OS-level secret store (Windows Credential Manager / WSL gnome-keyring), never in repo, rotate immediately if any laptop/VPS is lost. The 3Commas 2022 breach ($22M stolen) is the canonical lesson: an attacker with API keys drains accounts within minutes.
- **Clock skew.** WSL2 has a well-documented drift problem after sleep/resume (microsoft/WSL issues #4677, #10006, #11790). Signed requests with timestamps off by more than a few seconds are rejected. Mitigate: enable systemd-timesyncd or chrony in WSL, force `hwclock -s` on resume, add a startup check that aborts the bot if local time differs from `time.kalshi.com` (or NTP) by > 2s.
- **Concurrency bugs.** Double-submit on retry, race on position state, stale cache. Mitigate by single-writer model (one process owns orders), per-market mutex, all state writes go through a single transactional store.
- **Restart-from-crash.** Bot crashes after sending order but before recording it; restarts and re-sends. Mitigate with idempotency key = deterministic client_order_id (e.g., hash of strategy_id + market_id + epoch_minute + side); Kalshi rejects duplicates so retries are safe.

## 4. Real Case Studies

1. **Knight Capital, 2012 ($440M in 45 minutes).** Deployment to 7 of 8 SMARS servers; the 8th still had a reused flag (Power Peg) that re-activated dead code. The dead code's cumulative-fill counter had been moved years earlier without retest, so it sent child orders forever for each parent. Root cause: incomplete deployment + code reuse via flag toggles + no integration test that the 8 servers behaved identically. Lessons: never deploy partial; never reuse flags for new features; assume any "dead" code is one config flip from live.
2. **3Commas API key leak, December 2022 ($22M+).** Attackers obtained the platform's user API key database and used the keys directly on Binance, KuCoin to drain accounts. Lesson: API keys are bearer credentials. Never enable withdrawal scope; if your strategy can be expressed with trade-only scope, do it.
3. **Long-Term Capital Management, 1998.** Leverage 25:1 ($125B assets on $4.8B equity). Strategy assumed historical spread correlations would hold; Russian default broke them. Lesson: correlated risk you did not model is the risk that kills you. For Kalshi, this means two markets you think are independent (e.g., two Fed decisions, two NFL games tied to weather) may co-move in tail scenarios.
4. **PredictIt 2020 election anomalies.** Persistent mispricings driven by misinformation; bots that arbitraged across exchanges were exposed to platform-resolution risk and tax-treatment differences. Lesson: prediction market "edges" sometimes reflect news the rest of the market has not seen yet; do not assume your edge is real if you cannot identify the marginal trader on the other side.
5. **Polymarket 2024 single-trader manipulation.** One wallet (4 accounts) put $30M on Trump, ~25% of all electoral contracts. PredictIt at $850/trader cap stayed accurate (93%); Polymarket fell to 67%. Lesson: a small market is moved by whoever brings the most capital, not by truth. In thin Kalshi markets your model can be right and you can still lose because a whale is leaning the other way until settlement.

**Distilled lessons applicable to $100 Kalshi bot:** (a) deploy completely or not at all; (b) idempotent orders are non-negotiable; (c) never grant withdrawal scope to bot keys; (d) correlated positions are one position; (e) thin markets are dangerous regardless of edge; (f) reconcile state with the exchange constantly; (g) the budget cap is a code constant, not a guideline.

## 5. Concrete Risk Controls (copy-paste rules)

```
# constants.py
CAPITAL_CAP_USD = 50          # hard ceiling, checked before every order
PER_MARKET_CAP_PCT = 0.10     # max 10% of bankroll on one market ($5 on $50)
PER_TRADE_USD = 2.0           # flat sizing default
MAX_ORDERS_PER_DAY = 50       # sanity gate
MAX_OPEN_POSITIONS = 25       # concurrency cap
PRICE_MIN, PRICE_MAX = 0.01, 0.99
DAILY_DD_HALT_PCT = 0.10      # halt at -10% day
WEEKLY_DD_HALT_PCT = 0.15
TOTAL_DD_HALT_PCT = 0.25
ABS_FLOOR_USD = 25.0          # below this, shut down

# pre-trade gate (every order)
assert PRICE_MIN <= price <= PRICE_MAX
assert 1 <= contracts <= max_contracts_for_market
assert notional <= PER_MARKET_CAP_PCT * current_bankroll
assert sum_open_notional + notional <= CAPITAL_CAP_USD
assert today_order_count < MAX_ORDERS_PER_DAY
assert client_order_id not in submitted_order_ids
```

- **Kill switches (defense in depth).** (1) `./KILL` file flag, polled every loop iteration; presence = cancel-all-and-exit. (2) SIGTERM handler that flattens before exit. (3) Heartbeat dead-man timer: bot writes timestamp to file every 30s; a separate watchdog (cron / systemd) flattens if file is stale > 5 min. (4) One-command operator script `python -m bot.panic` that cancels all and disables on disk.
- **Reconciliation.** Every 60 seconds, GET /portfolio/positions, diff against local SQLite. Any mismatch -> log, alert, refuse new orders until cleared.
- **Idempotency.** `client_order_id = sha256(f"{strategy_id}|{market_ticker}|{side}|{epoch_minute}|{seq}")[:16]`. Stored before send; Kalshi-side duplicate-rejection makes retries safe.
- **Logging.** Per-trade row: timestamp_utc, market_ticker, side, price, contracts, fee, client_order_id, exchange_order_id, settlement_value, settlement_ts. SQLite + daily JSONL backup. Required for tax reporting (US Section 1256 / ordinary income treatment of event contracts is still unsettled; preserve the audit trail).
- **Key management.** Private key PEM lives in `%LOCALAPPDATA%\KalshiBot\key.pem` with ACL restricted to current user (Windows) or `~/.config/kalshibot/key.pem` mode 0600 (WSL). Never in repo. Loaded once at startup; never logged.
- **Clock check at startup.** Compare local time to NTP; abort if delta > 2s. Re-check on resume from sleep.

## Sources

- Kalshi fee schedule: https://kalshi.com/docs/kalshi-fee-schedule.pdf
- Kalshi orderbook docs: https://docs.kalshi.com/getting_started/orderbook_responses
- Kalshi API key/RSA docs: https://docs.kalshi.com/getting_started/api_keys
- Knight Capital SEC case study: https://www.henricodolfing.ch/en/case-study-4-the-440-million-software-error-at-knight-capital/
- Knight Capital DevOps writeup: https://dougseven.com/2014/04/17/knightmare-a-devops-cautionary-tale/
- 3Commas breach (Dec 2022): https://www.bleepingcomputer.com/news/security/crypto-platform-3commas-admits-hackers-stole-api-keys/
- 3Commas breach explainer: https://www.halborn.com/blog/post/explained-the-3commas-breach-december-2022
- LTCM lessons (US Treasury report): https://home.treasury.gov/system/files/236/hedgfund.pdf
- LTCM PRMIA case: https://prmia.org/common/Uploaded%20files/ORM%20Designation/PRMIA_LTCM_062321.pdf
- Polymarket / PredictIt 2024 accuracy: https://bettermarkets.org/newsroom/prediction-markets-did-not-nail-the-2024-election/
- PredictIt 2020 inefficiencies: https://www.socialscience.international/aiden-singh-predictit-inefficiencies
- Kelly criterion fractional sizing: https://www.predictionhunt.com/blog/prediction-market-position-sizing-kelly-criterion
- Backtest overfitting (Arian et al. 2024 CPCV vs walk-forward): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4686376
- Deflated Sharpe ratio (Lopez de Prado): https://www.researchgate.net/publication/286121118_The_Deflated_Sharpe_Ratio_Correcting_for_Selection_Bias_Backtest_Overfitting_and_Non-Normality
- Purged cross-validation: https://en.wikipedia.org/wiki/Purged_cross-validation
- WSL2 clock skew megathread: https://github.com/microsoft/WSL/issues/10006
- WSL2 clock fix: https://cr0x.net/en/wsl2-time-drift-fix/
- Survivorship bias in backtesting: https://www.quantifiedstrategies.com/survivorship-bias-in-backtesting/
- Lookahead bias detection (freqtrade): https://www.freqtrade.io/en/stable/lookahead-analysis/
- Idempotency for trading APIs: https://www.tokenmetrics.com/blog/idempotency-keys-order-placement

## Unknowns / Blockers

- Kalshi API exact rate limit (cited ~10 req/s but not officially published). Need to confirm in sandbox before production.
- Kalshi withdrawal API scope: unclear if read/trade/withdraw scopes can be separated on a single API key. If not, the blast radius of key compromise includes bank-linked withdrawal. Verify in account settings before live trading.
- US tax treatment of Kalshi event contracts: as of 2026 still partly unsettled (CFTC-regulated but not necessarily Section 1256). Operator should confirm with a CPA; logging schema must support either treatment.
- Whether Kalshi auto-cancels working orders on session disconnect (some exchanges do, some don't). If not, a dead bot leaves live orders; the watchdog must handle cancel-all on heartbeat loss.
- Realistic fill rates for limit orders inside the spread on thin Kalshi markets - hard to estimate without paper-trading data.
- Exact Brier-score floor at which Quarter-Kelly is justified - depends on calibration validation that has not yet been run.
