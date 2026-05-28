# V10-A Literature Delta (2026 scout, beyond v10/02b baseline)

Date: 2026-05-26
Agent: v10A-2 (literature scout, no conversation history)
Scope: 2026 papers relevant to Kim arXiv 2602.07048v2 (LLM semantic
filter for Kalshi Economics lead-lag), beyond what is already in
`research/v10/02b-literature-delta.md`.

Status of Kim itself (re-verified): only v1 (4 Feb 2026) and v2
(27 Feb 2026) on arXiv. NO v3. No successor paper from the author
team surfaced in search. Critical methodology facts confirmed from
HTML v2 fetch:

- n = 554 event markets, 18 non-overlapping test windows (60d train,
  30d test), holding horizons h in {1, 3, 5, 7, 10, 14, 21} days,
  default 7d.
- NO transaction fees, NO bid/ask, NO slippage in P&L. Idealized
  execution.
- No discussion of generalization beyond the Economics category.

---

## Paper A: Mohanty, Krishnamachari, "Do Prediction Markets Forecast Cryptocurrency Volatility? Evidence from Kalshi Macro Contracts"

- arXiv: 2604.01431 (1 Apr 2026)
- One-line: Daily probability changes on 10 Kalshi macro contracts
  (KXFED, KXCPI, KXCPICORE, KXGDP, KXU3, KXPCECORE, KXRECSSNBER,
  KXACPI, etc.) predict crypto realized volatility via a monetary-
  policy channel and an inflation channel.
- Sample: Jan 2023 to Mar 2026, N=1,183 calendar days, effective
  per-series n 193 to 569.
- Lead-lag finding: explicit lead/lag regression test on monetary-
  policy channel, lagged t=3.71, lead t=-0.17 (rules out reverse
  causality). For CPI, both directions significant, suggests
  multi-day repricing around BLS release.
- Horizon profile: Fed signal peaks at h=3 to h=5 days for Bitcoin.
- Tag: **NEW-ANGLE / SUPPORTS-PIVOT.** This paper is the closest
  2026 work to Kim that is NOT Kim. It uses Kalshi macro probability
  changes as a leading indicator for an EXTERNAL asset (crypto IV),
  not for another Kalshi market. No fees in P&L. The KXFED daily
  delta with h=5 horizon and t=3.71 is a published, peer-style
  result on the exact macro ticker family Kim used.
- V10-A relevance: directly supports a pivot away from Kalshi-
  internal lead-lag (Kim) toward Kalshi-macro-as-leader for
  external instruments. If V10-A revives, the Mohanty channels are
  a candidate alternative to Kim's internal pairs.

## Paper B: Le, "Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets"

- arXiv: 2602.19520 (23 Feb 2026)
- One-line: 292M trades across 327K binary contracts on Kalshi and
  Polymarket, documents domain-specific calibration biases with
  underconfidence in political markets dominating.
- Macro coverage: abstract focuses on politics; macro/economics
  category breakdown not headlined.
- Tag: **CONFIRMS-EXISTING.** Adjacent calibration evidence;
  not directly load-bearing for V10-A.

## Paper C: Dubach, "The Anatomy of a Decentralized Prediction Market: Microstructure Evidence from the Polymarket Order Book"

- arXiv: 2604.24366 (27 Apr 2026, v2 14 May 2026)
- One-line: 30B tick-level events over 52 days on Polymarket, 600-
  market panel, 8 stylized facts including longshot spread premium,
  near-uniform depth, category-conditional spreads, and a 22%
  upper-tail self-counterparty wash share.
- Tag: **CONFIRMS-EXISTING / REFUTES-CROSS-VENUE-OPTIMISM.** The
  22% wash share upper-tail and the longshot premium reinforce
  Becker's "Finance category is efficient" finding on the Polymarket
  side. Cross-venue lead-lag using Polymarket fills as leader
  becomes harder to defend at this self-counterparty intensity.

## Paper D: Hua et al., "Unlocking the Forecasting Economy: A Suite of Datasets for the Full Lifecycle of Prediction Market"

- arXiv: 2604.20421 (22 Apr 2026)
- One-line: 943M fill records on Polymarket Oct 2020 to Mar 2026,
  770K markets, 2M oracle events; downstream case study is "CPI
  expectation reconstruction" on Polymarket.
- Tag: **NEW-ANGLE / DATA-LAYER.** Polymarket-side macro is thin
  (CPI mentioned as a case study, not headline); the dataset is
  rich on the trade side. Cross-venue Kalshi-Polymarket macro
  lead-lag is plausible at the data layer if Polymarket macro
  volume is non-trivial. Open question: is the Polymarket macro
  book deep enough for daily-resolution lead-lag against Kalshi?

## Paper E: PolyBench - "Benchmarking LLM Forecasting and Trading Capabilities on Live Prediction Market Data"

- arXiv: 2604.14199 (3 Apr 2026)
- One-line: 38,666 Polymarket binary markets, 7 LLMs tested,
  36,165 predictions over Feb 6 to 12, 2026; only 2 of 7 LLMs
  achieve positive Confidence-Weighted Return (MiMo-V2-Flash 17.6%,
  Gemini-3-Flash 6.2%). Fee treatment not stated.
- Tag: **REFUTES-LLM-EDGE / CONFIRMS-EXISTING.** Five of seven
  LLMs lose money on Polymarket even gross of fees. This is a
  bearish prior on LLM-direct-forecasting; supports Kim's "LLM
  as filter, not forecaster" framing but raises the question of
  whether the filter signal survives net of fees.

## Paper F: Prediction Arena - "Benchmarking AI Models on Real-World Prediction Markets"

- arXiv: 2604.07355 (28 Mar 2026)
- One-line: Live-execution benchmark of LLMs on Kalshi and Polymarket;
  Cohort 1 Kalshi returns range -16.0% to -30.8%. No fee
  disclosure, no macro-specific breakdown in abstract.
- Tag: **REFUTES-LLM-EDGE.** Direct on-Kalshi LLM trading lost
  16% to 31%. Consistent with Halawi 2024 and v9 Phase 3 critic's
  gate-regime mismatch concern.

## Paper G: PolySwarm - "Multi-Agent LLM Framework for Prediction Market Trading and Latency Arbitrage"

- arXiv: 2604.03888 (4 Apr 2026)
- One-line: 50-persona LLM swarm + confidence-weighted Bayesian
  combination + information-theoretic inefficiency detection on
  Polymarket binary markets. Brier and log-loss reported, fees not.
- Tag: **NEW-ANGLE / WEAK-EVIDENCE.** Multi-agent LLM is conceptually
  related to Kim's "LLM filter" but with much higher cost and no
  fee-net P&L. Not load-bearing for V10-A given Kim's single-LLM
  approach is cheaper and has cleaner results.

## Paper H: "Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets"

- arXiv: 2601.01706 (5 Jan 2026)
- One-line: 100K+ events across 10 venues 2018 to 2025; 2 to 4%
  persistent cross-platform price deviations due to semantic non-
  fungibility (different resolution criteria).
- Tag: **NEW-ANGLE / REFUTES-CROSS-VENUE-ARB.** The 2 to 4% spread
  is structural, not exploitable. Important counterweight to any
  V10-A pivot that assumes cross-venue arb is the edge.

## Paper I: Wang et al., "Stock Market Volatility Predictability: A Transfer Entropy-Determined Model-Switching Strategy"

- DOI 10.1002/ijfe.70210 (Wiley, 2026)
- One-line: Transfer entropy gates a model-switching strategy on
  stock-market volatility indices, detecting dependence vs
  independence regimes.
- Tag: **NEW-ANGLE / ALTERNATIVE-METHOD.** This is the closest
  2026 application of transfer entropy as a regime gate. NOT on
  prediction markets directly, but the gating idea (use TE to
  decide WHEN a lead-lag signal is reliable) is applicable to
  Kalshi macro pairs at small n.

## Paper J: Wang et al., "Information Propagation Across Investor Types: Transfer Entropy Networks in the Korean Equity Market"

- arXiv: 2603.20271 (March 2026)
- One-line: Transfer entropy network on cross-investor information
  propagation in Korean equities.
- Tag: **CONFIRMS-METHOD.** Transfer entropy can detect directed
  information flow at small n more robustly than Granger when
  relationships are nonlinear. Methodological reference if V10-A
  swaps Granger for transfer entropy.

## Paper K: Diebold-Yilmaz / Connectedness on Prediction Markets

- Not found. Diebold-Yilmaz variance-decomposition connectedness
  is widely applied to equities, crypto, commodities in 2026 but
  NO paper applies it to prediction-market probability spillovers.
- Tag: **CONFIRMED GAP.**

## Paper L: Hawkes Processes on Prediction Markets

- Not found. Hawkes models are deeply studied for high-frequency
  trade arrival on equities and crypto (multiple 2025 to 2026
  papers, e.g. arXiv 2503.14814) but NO paper applies them to
  cross-market intensity in Kalshi or Polymarket.
- Tag: **CONFIRMED GAP.**

## Paper M: Cointegration / VECM on Kalshi Macro Pairs

- Not found in 2026 literature. The Diercks/Katz/Wright Fed paper
  documents Kalshi macro is efficient against Bloomberg consensus
  and NY Fed SoMA but does NOT use cointegration or VECM to test
  long-run equilibrium between Kalshi macro tickers.
- Tag: **CONFIRMED GAP.**

## Paper N: Becker, "The Microstructure of Wealth Transfer" (re-checked)

- Already in INDEX; re-checked for macro net-of-fee returns. Becker
  reports Finance category gross excess returns: taker -0.08%,
  maker +0.08% per trade. **GROSS, not net of fees.** Kalshi fees
  are roughly 1 to 4c per contract for under-$1 contracts. The
  Finance category is essentially break-even gross; almost
  certainly negative net for takers, marginally positive at best
  for makers.
- Tag: **REFUTES-KIM-NET-EDGE.** Kim's +3.1pp gross win rate
  improvement on Kalshi Economics must clear Kalshi's 1 to 4c
  per-contract take fee plus the maker-taker spread. The Becker
  gross-zero baseline on Finance category implies any retail
  edge from Kim's filter is structurally fragile after fees.

## Paper O: Kim et al. citations / replication

- Researchgate, gist.science, openreview all index Kim v2 but no
  independent replication, no extension paper, no errata. The
  paper is too new (Feb 2026, ~3 months) for citation accumulation.
- Tag: **NO REPLICATION YET.** V10-A would be first to attempt.

---

# Top 3 actionable papers for V10-A revival

## 1. Mohanty/Krishnamachari arXiv 2604.01431

DIRECT PIVOT CANDIDATE. Uses KXFED daily probability changes to
predict Bitcoin/altcoin realized volatility at h=3 to h=5 days
with t=3.71 lead-only significance. This is:

- A published 2026 positive result on Kalshi macro tickers
  (the exact universe Kim uses).
- A lead-lag relationship, but Kalshi-macro-to-EXTERNAL-asset,
  not Kalshi-internal.
- Tradable via crypto options or Deribit IV; orthogonal to the
  Diercks "Kalshi macro is efficient" critique because the edge
  is in the EXTERNAL instrument (crypto vol), not in Kalshi
  itself.

For V10-A: consider replacing Kim's "KXCPI leads KXNFP" framing
with "KXCPI leads BTC realized vol at h=5d, fade short-dated
straddles." This makes the venue of execution Deribit, not Kalshi,
which sidesteps Kalshi fees entirely.

## 2. Becker Microstructure (RE-CHECKED, refutation lens)

The +0.08% Finance maker excess return / -0.08% taker excess return
on 4.4M trades is the empirical net-of-fee constraint Kim's paper
ignores. Any V10-A revival MUST:

- Compute Kim's published +3.1pp win rate gain in DOLLAR EXPECTED
  VALUE per round trip on actual Kalshi spreads (1c, 2c, 4c at
  different price levels).
- Verify the edge survives Becker's documented Finance category
  efficiency. If win rate goes 51.4% to 54.5% at 2c average spread
  and 1c taker fee, the dollar EV is approximately +0.031 * $1.00
  - 1.5c effective cost = approximately +1.6c per trade. Marginal.
- Document the math BEFORE pulling any data.

## 3. Hua arXiv 2604.20421 (Polymarket Lifecycle) + cross-venue

If V10-A's mechanical edge in Kim survives Becker fee math (above),
extending to cross-venue Kalshi macro vs Polymarket macro is the
next move, using the Polymarket lifecycle dataset (943M fills,
includes "CPI expectation reconstruction"). The Diercks paper
showed Kalshi macro is efficient vs Bloomberg; Polymarket macro
is likely THINNER and less efficient (Hua does not break out macro
volume but Polymarket politics dominates Polymarket volume by ~10x).
A Polymarket-LEADS-Kalshi macro hypothesis is the cross-venue
analog of the Ng et al. 2026 politics finding.

---

# Confirmed gaps (V10-A first-mover angles)

These are areas where NO 2026 literature exists, so V10-A would
not be replicating anyone:

1. **Transfer entropy on Kalshi macro pairs.** Wang et al. (Paper I)
   applies TE to volatility regime switching; nobody has applied
   TE directly to Kalshi macro market probability time series.
   At Kim's effective n (193 to 569 per series), TE would handle
   non-linear dependence better than Granger.

2. **Hawkes processes on prediction-market cross-market intensity.**
   No 2026 paper. Could model whether a probability shock on KXCPI
   excites probability shocks on KXFED within minutes.

3. **Cointegration / VECM on Kalshi macro pair long-run equilibrium.**
   No 2026 paper. Would be the natural counterpart to Kim's pair-
   wise Granger test for testing long-run equilibrium rather than
   short-run lead-lag.

4. **Diebold-Yilmaz connectedness on Kalshi macro probability
   spillovers.** No 2026 paper. Could quantify which Kalshi macro
   ticker is the net transmitter vs receiver of probability shocks.

5. **Fee-aware net P&L on Kim's method.** No 2026 paper, including
   Kim itself, publishes net-of-fee P&L on Kalshi macro lead-lag.

6. **LLM-filter generalization to non-Economics Kalshi categories.**
   No 2026 paper. Kim explicitly does not test this. PolyBench and
   Prediction Arena show LLMs lose money on Polymarket and Kalshi
   in general, but neither tests Kim's two-stage filter framing.

7. **Cross-venue macro lead-lag Polymarket vs Kalshi.** Ng/Peng/
   Tao/Zhou 2026 (already in v10/02b baseline) covered politics
   only. No 2026 paper has run the same analysis on macro.

8. **Kim replication on the April 2026 rebranded Kalshi tickers**
   (KXFEDDECISION, KXEFFR, KXUSNFP, KXPAYROLLS, KXECONSTATU3, KXU3).
   The Becker prediction-market-analysis dataset (Feb 2026) only
   has the legacy KXFEDFUNDS/KXNFP/KXUNRATE series. No 2026 paper
   has tested whether Kim's lead-lag pairs persist across the
   ticker rebrand.

---

# Summary verdict for V10-A revival

**Kim v2 stands alone with no successor and no independent
replication.** The 2026 literature has produced one strongly
adjacent paper (Mohanty/Krishnamachari, Kalshi-macro-leads-crypto-
vol) that pivots the lead-lag thesis to an external execution
venue, sidestepping Kalshi fees. The methodological gaps (TE,
Hawkes, VECM, DY) are real first-mover opportunities but require
small-n robustness arguments. The fee-net P&L gap is the load-
bearing risk: Becker's Finance gross-zero result is the hard
prior to beat.

**If V10-A revives, the strongest defensible angle is the Mohanty
pivot: KXFED daily delta as a leader of BTC realized vol at h=5d,
with execution on Deribit (not Kalshi).** This is the only 2026
positive published result on the Kalshi macro tickers that does
not require Kalshi as the execution venue.

Additional candidates available beyond the 15 papers / 15 web
fetches scouted; see ArXiv listings for q-fin.TR, q-fin.MF,
q-fin.ST throughout 2026 for further candidates.
