# Project Kalshi: Key Findings Distilled

This document is the single highest-leverage page in the project
knowledge base. It's the answer to "what did Project Kalshi learn?"
Read this before doing any new strategy work.

It compresses the 7 literature extractions
([research/literature/](literature/)), the Phase 1 sub-agent briefs
([research/briefs/](briefs/)), the critic pass
([research/critic-report.md](critic-report.md)), and the two empirical
gate runs (Phase 1.5 and 1.6) into the facts that any new strategy
proposal must be consistent with.

## Section 1: The four facts every Kalshi strategy must respect

These are load-bearing - any strategy proposal that contradicts one
of these without explicit reasoning is wrong.

### Fact 1: Makers > Takers structurally

Takers pay fees and accept premium prices to guarantee execution;
Makers extract that premium on matches. This is an equilibrium
property of any exchange-style market (Whelan model). Cross-checks
that confirm:
- **Bürgi (Kalshi, 313k prices)**: maker -9.64% / taker -31.46%
  avg return (pre-2025 fee regime)
- **Becker (Kalshi, 72M trades)**: maker +1.12% / taker -1.12% avg
  per-trade return (post-2024)
- **Bartlett & O'Hara (Kalshi, 41M trades)**: makers earn 2x more
  per contract in single-name markets despite higher adverse selection

Implication for new strategies: **default to maker-side strategies**
unless there's an explicit reason a taker strategy survives the fee
plus information disadvantage.

### Fact 2: Bias varies enormously by category; weather is on the low end

Becker's per-trade maker-taker gap by category (gross of fees):

| Category | Gap (pp) | Verdict for retail |
|---|---|---|
| Finance | 0.17 | Dead - too efficient |
| Politics | 1.02 | Small; episodic edge |
| **Weather** | **2.57** | **EC-1 already killed; too small after fees** |
| Sports | 2.23 | Large absolute volume but Jump/SIG dominate |
| Crypto | 2.69 | HFT-dominated short-term; weekly maybe viable |
| Entertainment | 4.79 | Large bias but only 0.6M trades total |
| Media | 7.28 | Large bias but only 0.6M trades total |
| World Events | 7.32 | Largest bias; only 0.2M trades; very thin |

Implication: **the higher-bias categories (Entertainment, Media,
World Events) are also the thinnest** - making a Kalshi-living from
them is nearly impossible. Larger, lower-bias categories may still
work if the right strategy filters the order flow.

### Fact 3: The 2024 sign flip

Per Becker: **takers won pre-October-2024** (+2.0% avg per trade);
**makers win post-flip** (+2.5% avg). The driver was the
~27x volume surge after Kalshi's October 2024 CFTC ruling plus the
November 2024 election attracting professional MMs.

Implication: **any model trained on pre-October-2024 Kalshi data
is misleading**. Use only post-flip data. This is part of why the
literature's headline numbers (e.g. Bürgi's -9.64% maker, sample
2021-2025) understate current maker-side economics.

### Fact 4: Bias is shrinking yearly

Bürgi's regression coefficient on price (the favorite-longshot
intensity) over time:

| Year | ψ | Significance |
|---|---|---|
| 2021 | 0.041 | *** |
| 2022 | 0.023 | ** |
| 2023 | 0.036 | *** |
| 2024 | 0.048 | *** (peak) |
| 2025 | 0.021 | * (half the 2024 level) |

Implication: institutional MMs continue to compress the bias. **Any
2026+ strategy must factor in further compression beyond the 2025
data.** Edges that were +5pp in 2024 may be +2-3pp now and trending
to zero.

## Section 2: Meta-lessons from Phase 1.5 vs 1.6 (the methodology lesson)

The single most important meta-finding from Phase 1.5 / 1.6:
**the choice of trading window swamps the choice of model.**

- **Phase 1.5** (60-min VWAP ending 30 min before close): 9pp
  shoulder edge OOS - but this was an artifact. KXHIGH markets close
  AFTER the NWS has reported the daily high. The "trading window" we
  measured was actually post-resolution arbitrage on near-settled
  markets. Apparent edge had nothing to do with forecast skill.
- **Phase 1.6** (12-hour VWAP starting 1h after open, ~14h before
  measurement begins): 1.5pp gross / -0.5pp net edge. This is the
  actual tradable signal. Below the maker fee model.

**For any new strategy:** before locking methodology, explicitly
think about what window represents "trades the bot could realistically
have placed." Don't measure prices in windows the bot can't trade in.

Sub-lesson: **Le's calibration regime structure**:
- Weather: overconfident at short horizons, underconfident at long
- Politics: chronically underconfident (compressed toward 50%)
- Sports: well-calibrated short, sharply underconfident beyond 1mo
- All domains: universal underconfidence at long horizons (slope
  rises from 0.99 at <1h to 1.32 at >1mo)

The "right" calibration adjustment differs by category AND horizon.
A maker-quoting strategy that works at one (category, horizon)
combination may be entirely wrong at another.

## Section 3: What's empirically validated vs what's hypothesis

**Empirically validated by Project Kalshi's own data:**
- Kalshi v2 API with RSA-PSS signing works as documented
- Maker fee formula: ceil(0.07 * C * P * (1-P)) * 0.25 per contract
- Historical data endpoints: `/historical/markets`, `/historical/trades`
  cover pre-2026-03-23 data
- Live endpoints: `/markets`, `/markets/trades` cover post-cutoff
- KXHIGH series ticker schema (legacy `HIGH<X>-` prefix prior to
  late 2024; current `KXHIGH<X>-`)
- KXHIGH weather pre-resolution mispricing: 1.5pp gross / -0.5pp
  net edge on 12-hour pre-measurement window across 24,744 markets
  (Phase 1.6)

**Validated by external research (the 7 papers):**
- Maker-taker structural advantage (Bürgi, Becker, Bartlett)
- Per-category bias magnitudes (Becker)
- Calibration regime structure by domain + horizon (Le)
- 2024 sign flip (Becker)
- YES-overbet behavioral surplus on NO-settle single-name markets
  (Bartlett)

**Still hypothesis:**
- Whether OTHER Kalshi categories yield retail-tradable edge after
  fees (only weather was empirically tested by Project Kalshi)
- Whether cross-platform Kalshi-Polymarket arb has retail-scale
  capacity (Le shows microstructure differences, Clinton & Huang
  shows 78% execution failure on low-volume - probably not)
- Whether manipulation-reversal trades (60+ day persistence per
  Rasooly & Rozzi) are exploitable at retail scale
- Whether maker-quoting >= 50c contracts (Bürgi's +2.6% finding)
  works as a generic strategy outside the +50c-window context
- Whether event-driven directional plays around scheduled releases
  can outperform institutional pricing

## Section 4: Specific pin numbers worth retaining

Fee math (verified):
- Taker fee = ceil(0.07 * C * P * (1-P)) cents per contract
- Maker fee = 25% of taker = ceil(0.0175 * C * P * (1-P)) cents
- At P=0.50: taker $0.02/contract, maker $0.005/contract,
  round-trip maker ~1% on $1 notional

Microstructure (verified):
- Limit orders only (market orders deprecated Sep 2025)
- Tick = $0.01 standard; sub-penny on some markets
- Rate limit Basic tier: ~20 reads/s, ~10 writes/s, 429 on overage,
  no Retry-After header
- Historical cutoff is moving target (was 2026-03-23 in May 2026)

Kalshi 2025 per-domain volume distribution (Becker):
- Sports: 43.2M trades = 66.7% of total
- Crypto: 6.5M (10.0%)
- Politics: 4.9M (7.5%)
- Weather: 4.4M (6.8%)
- Finance: 4.3M (6.6%)
- Entertainment: 1.5M (2.3%)
- Other small categories add the rest

Kalshi sample sizes (Le, through Dec 2025):
- Sports: 55,637 markets, median per-market volume 76 trades
- Politics: 6,609 markets but 127 trades median (intense per market)
- Weather: 26,911 markets, 74 trades median
- Note: politics has the highest per-market liquidity DESPITE having
  fewer markets

Behavioral parameter (Bürgi's structural model):
- β = 0.09: probability over-weighting magnitude (Kahneman-Tversky).
  Tightly identified, robust to other parameter variations.
- σ = 0.107: belief dispersion (subjective probability SD)
- θ = 0.60: matching rate (fraction of resting orders that fill)

## Section 5: Risk factors any new strategy must address

1. **Adverse selection** (Bartlett): single-name markets attract
   informed flow. Resting maker orders get picked off.
2. **Variance** (Bürgi): 33% SD per trade on the maker-profitable
   50c+ subpopulation. Even with positive expected return, drawdowns
   are large.
3. **Regime change** (Becker, Bürgi): a 2024-style sign flip can
   happen again with new institutional entry or new regulation. The
   strategy must monitor for it.
4. **Fee compression risk**: Kalshi could change fees again. They
   added maker fees in April 2025; could raise further.
5. **WSL2 clock-skew on operator's stack** (Phase 1 research):
   sleep/resume breaks RSA signed requests. Mitigation in
   `src/kalshi_bot/data/auth.py` documentation.
6. **California regulatory risk**: CA AG Bonta is "preparing" action
   per CNIGA Dec 2025. Risk of state-level injunction within 6-12mo.

## Section 6: Methodology discipline lessons

What worked in Phase 1.5/1.6:
- **Locking pass criteria pre-data** prevented post-hoc
  rationalization of a near-miss.
- **Walk-forward + LOCO + purge buffer** caught a regime mismatch
  that simple holdout would have missed.
- **Adversarial critic pass** caught the central Zerve methodology
  flaw before it cost money.
- **No third bite commitment** when Phase 1.5 nearly passed: by
  forcing a clean Phase 1.6 redesign, we discovered the close-window
  artifact rather than trying to tune around it.

What new strategies must replicate:
1. Lock pass criteria BEFORE pulling new data.
2. Use walk-forward and LOCO (or analogous OOS partitions) not
   simple holdout.
3. Apply purge buffers in time-based splits.
4. Subject the proposed strategy to an adversarial critic agent
   before live capital.
5. Pre-commit to "no third bite": if the gate fails, the strategy
   ends.
6. Distinguish between "trading window" and "measurement window" -
   the window the bot trades in must be empirically tradable.

What new strategies should NOT do:
- Cite Zerve as evidence of edge (unvalidated community notebook).
- Trust in-sample backtest results without OOS validation.
- Train on pre-October-2024 Kalshi data and assume it applies now.
- Promise edges that contradict the per-category bias magnitudes
  in Becker without strong category-specific justification.
- Skip the maker fee model. Round-trip maker fees can flip 2pp
  gross edge to negative net edge.
