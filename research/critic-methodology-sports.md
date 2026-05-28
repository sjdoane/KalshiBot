# Sports x Long-Horizon Methodology Critic

**Date:** 2026-05-23
**Author:** Methodology-Critic sub-agent (sports pivot review)
**Scope:** Adversarial pre-data review of
[sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
and the underlying
[sports-longhorizon-proposal.md](sports-longhorizon-proposal.md).
The Phase 2 mechanical fail
([phase-2-results.md](phase-2-results.md)) justifies the methodology
delta; this review tests whether the new design is honestly powered
and leakage-controlled.

## Executive summary

The sports methodology should be locked WITH ADJUSTMENTS, not as-is.
The headline pivot decisions (long-horizon filter, larger test
windows, league-out replacing event-out) are defensible reactions to
the Phase 2 mechanical fail, but three issues rise to BLOCKING and
must be fixed before any data pull: C3 at alpha = 0.109 over only 6
splits is statistically incoherent as a "gate" and should be
demoted; the lifetime-straddle removal has NO compensating leakage
control because leave-one-league-out is structurally orthogonal to
the news-period contamination path; and the expected sample size,
when honestly modeled against Le's per-domain data, falls below the
minimum required for the locked split design.

## 1. Lifetime-straddle removal stress-test

### 1.1 The leakage path is unchanged

The prior critic
([critic-methodology-phase-2.md](critic-methodology-phase-2.md)
Section "Walk-forward purge") established the leakage path: joint
news-period structure absorbed by the isotonic / logistic fit on
train when train and test markets have OVERLAPPING LIFETIMES, even
with temporally-disjoint VWAP windows. The mechanism is the same in
sports. An NFL futures market opened in August 2025 and an NBA
championship market opened in October 2025 both trade through the
same November 2025 news environment; the isotonic absorbs the joint
structure during train fit. The sports methodology
([sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 5.1) acknowledges this but overstates the mitigation.

### 1.2 League-out does not compensate

Leave-one-league-out
([sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 5.2) tests cross-LEAGUE generalization, not
cross-TIME-PERIOD generalization. The news-period leakage path runs
through SHARED TIME, not shared sport. A November 2025 macro shock
hits both NFL and NBA futures concurrently; holding out NBA does
not remove NFL's contemporaneous absorption of that shock during
train. League-out only catches leakage that is league-specific
(intra-NFL injury cluster). It cannot catch cross-league news,
regulatory shifts, or broad institutional MM repricing. The prior
critic rated the analogous LOCO event-window check NICE-TO-HAVE
for the same reason
([critic-methodology-phase-2.md](critic-methodology-phase-2.md)
Section "Isotonic / logistic absorbing cross-market correlation").

### 1.3 Compatible leakage controls that should be added

Two controls are both leakage-protective AND compatible with
long-horizon lifetimes:

1. **Resolution-time purge variant**: require train markets to
   RESOLVE before test_start (not merely OPEN before train_end). A
   train market resolved on day 175 has its outcome REVEALED at day
   175, well before any test VWAP window starting day 195. The
   long-horizon test sample is preserved (constraint is on close,
   not open). Residual news-period price correlation remains but is
   unavoidable in any time-overlapping regime.

2. **Within-cluster outcome shuffle bootstrap**: run the gate with
   true outcomes, rerun with outcomes shuffled within league. If
   the C3 / C5 statistics under shuffled outcomes show similar pass
   rates, the apparent edge is leakage artifact. Cheap diagnostic;
   would falsify a leakage-driven pass.

### 1.4 Verdict

Removal is ACCEPTABLE in principle (the strategy cannot be tested
otherwise per [phase-2-results.md](phase-2-results.md) Funnel
table) but the "leave-one-league-out compensates" framing in
[sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 5.1 Rationale paragraph is INCORRECT. Severity: IMPORTANT.

## 2. C3 / power calibration findings

### 2.1 C3 at alpha = 0.109 is incoherent as a gate

The methodology
([sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 7 C3) sets C3 = 5/6 splits with median net edge > 0,
binomial null 7/64 = 0.109. Phase 2's prior was alpha = 0.05 (13/17)
([phase-2-methodology.md](phase-2-methodology.md) Section 7 C3).
Doubling the false-acceptance rate is not a small concession.

Walk-forward correlation is sharper here. With 180d train / 60d
step, consecutive train windows share 120/180 = 67% of days. With
only 6 splits, effective independent N is ~4 to 5. Under H0 the
actual false-acceptance rate exceeds nominal 0.109 because
positively-correlated splits inflate the probability of a run.

### 2.2 The 5/6 vs 6/6 vs pooled-bootstrap choice

Section 7 C3 sub-bullets correctly identify the trade space: 6/6
has alpha 0.016 but one failing split kills; 4/6 has alpha 0.34,
too permissive. The rejection of 6/6 ("correlation effectively
reduces independence below 6") CUTS AGAINST 5/6 as well: at
effective N = 4-5, true alpha at 5/6 is plausibly 0.15-0.20. C3 is
not gate-quality.

### 2.3 Recommended treatment

DEMOTE C3 to diagnostic. PROMOTE pooled bootstrap (currently
informational per Section 7.1) to gate status. Pooled bootstrap
sidesteps per-split correlation by computing SE on concatenated
test data. The prior Phase 2 critic
([critic-methodology-phase-2.md](critic-methodology-phase-2.md)
Section "C3" recommended fix) made the same recommendation; it
applies a fortiori at N=6.

Concrete C3 replacement: "pooled mean per-trade net edge across all
6 test partitions has bootstrap 95% CI lower bound > 0pp." Section
7.1 already estimates pooled SE ~3pp for n=300; power-appropriate.

Severity: BLOCKING.

## 3. Long-horizon filter critique

Section 2.2 sets `lifetime >= 60 days`. Le's documented slope of
1.74 applies to the >1mo bin (conventionally >30 days)
([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Domain-by-horizon trajectories"); the methodology doubles this
without literature support. Two failure modes:

1. **Too strict**: many "season totals" or "make playoffs" markets
   open 30-60 days pre-resolution and ARE long-horizon for Le.
   Excluded without thesis support.
2. **Too lenient**: Jump/SIG adverse-selection is distance-from-
   resolution dependent; institutional MMs are still active in
   major sports futures at 60-90d. A 90d or 120d minimum would
   more cleanly remove institutional-dominated markets.

Recommended: either 30d (matches Le's bin, maximizes sample) OR
90d (matches Bartlett's single-name reasoning,
[bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR item 2). The 60d midpoint optimizes neither.

Severity: IMPORTANT (not BLOCKING; defensible if documented as
heuristic midpoint).

## 4. Adverse selection unaddressed concerns

### 4.1 Becker's 2.23pp sports gap is FULL-SAMPLE

C2 = 4.46pp = 2x Becker sports gap
([sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
Section 7 C2) repeats the Phase 2 framing. It is weaker for sports
because Becker's 2.23pp INCLUDES single-game markets where
Bartlett's adverse-selection AND behavioral-surplus mechanisms are
both large. The sports gap = behavioral surplus - adverse selection
cost averaged over all types. The long-horizon-only subset removes
some adverse selection (single-game adverse selection is sharpest,
[bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR items 2 and 4) but also removes behavioral surplus
([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
TL;DR item 4: takers overpay for YES longshots, the single-game
pattern). Net effect is unknown. A more honest C2: 2.23pp
unmodified (requiring the long-horizon slice to match the full
average, not exceed by 2x).

### 4.2 Long-horizon SPORTS markets are STILL often single-name

The methodology Section 2.2 filters by LIFETIME, not by single-name
vs broad-based. "Lakers win championship" passes the 60d filter but
is exactly the single-name structure where Bartlett finds higher
adverse selection
([bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
TL;DR item 2). The binary-only filter (Section 2.2) does not help:
each binary contract in a multi-team championship event is still
single-name in Bartlett's sense.

Recommended: tag each market as single-name vs broad-based
(broad-based = parent event has >= 5 binary sibling contracts).
Report per-split net edge separately per segment. Do NOT exclude
single-name (would gut sample), but segment-report prevents silent
overweighting of the high-adverse-selection regime.

Severity: IMPORTANT.

### 4.3 Jump / Susquehanna competition acknowledged but ungated

Section 7.1 Jump/Susquehanna paragraph correctly flags this as
untested in historical trade data, defers to Phase 3 paper trading.
There is no defensible pre-data gate for fill-rate against
institutional inside quotes. Keep as-is.

Severity: ACCEPTABLE-AS-FLAGGED.

## 5. Sample size estimation

### 5.1 Funnel against Le's documented sports numbers

Starting from Le's per-domain breakdown
([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Per-domain breakdown on Kalshi"): sports has 55,637 markets total
through 2025-12-31. Apply the methodology filters:

| Filter step | Estimate | Multiplier | Running count |
|---|---|---|---|
| Total sports markets | 55,637 | 1.00 | 55,637 |
| Post-2024-10 (estimate Q4 24 onward dominated total; Becker's 27x Q4 surge implies ~70%) | 0.70 | 0.70 | 38,946 |
| Binary contracts only (single contract per event; sports events often have multi-team championships, but individual game markets ARE binary) | 0.40 estimate | 0.40 | 15,578 |
| Lifetime >= 60d (excludes single-game which is the bulk of sports) | 0.05 to 0.15 (single-game is the dominant sports market type) | 0.10 | 1,558 |
| Min 50 lifetime trades | 0.60 (Le's median sports lifetime trades is 76 per [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md) "Per-domain breakdown") | 0.60 | 935 |
| Min 20 trades in [-35, -28] window | 0.50 (rough; will trigger Option A 14-day widening if median < 20) | 0.50 | 467 |
| Section 4 mid-band + one-sided-flow filters | 0.40 (politics had 28% Section-4 eligible; sports may be similar) | 0.40 | 187 |

Honest range: 150 to 400 strategy-eligible markets across the full
[2024-10-01, 2026-04-30] corpus.

### 5.2 Per-split implications

With 6 splits and 467 long-horizon eligible markets (pre-Section-4):

- Per test partition (60d window): roughly 467 / 6 = 78 markets
  ASSUMING uniform temporal distribution (which is wrong; sports
  futures cluster by season).

After Section 4 filters: 78 * 0.4 = 31 per test partition. This is
BELOW the Phase 2 MIN_TEST_SIZE = 50 threshold that Politics x H
nominally aimed for. The methodology
([sports-longhorizon-methodology.md](sports-longhorizon-methodology.md))
does not specify MIN_TEST_SIZE; the Phase 2 implementation
defaulted to 50 ([phase-2-results.md](phase-2-results.md) Funnel
discussion).

The Section 7.1 power paragraph estimates 30-50 per test, which
matches. But the conclusion "appropriately powered" assumes a 4pp
true edge; if the true edge is 2-3pp (Becker's 2.23pp sports gap
INCLUDES large trades and full-sample mix), the per-split power
drops to ~0.4 and the pooled power to ~0.5. The methodology is
optimistically powered.

### 5.3 Seasonality compounds the problem

NFL season is Sept-Feb; NBA is Oct-June; MLB is Apr-Oct. A 60d
test window straddling Aug-Oct will be NFL-preseason heavy plus
end-of-MLB; a 60d window in May-July will be heavily NBA-playoffs
plus early-MLB. The "uniform per-split sample" assumption breaks.
Per-split eligible counts could range from 15 to 80 with the lower
end well below any reasonable MIN_TEST_SIZE.

### 5.4 Recommended adjustment

Add explicit MIN_TEST_SIZE_PER_SPLIT = 30 (lower than Phase 2's 50,
honest about the smaller corpus) and PRE-COMMIT that splits below
this threshold are reported but excluded from C3. Reduces the
denominator of C3 but prevents single-sport-season splits from
dominating the pass / fail call.

Severity: BLOCKING. Without a pre-committed MIN_TEST_SIZE, the
methodology cannot honestly report whether splits failed for
sample-size or signal-absence reasons.

## 6. League-out check viability

### 6.1 League distribution is unbalanced

The methodology Section 5.2 requires >= 100 markets per league for
LOCO. Expected leagues: NFL, NBA, MLB, NHL, NCAA-FB, NCAA-BB plus
maybe MLS, PGA, F1, Boxing.

Reality check: 467 long-horizon markets total (Section 5 funnel).
NFL is the largest US sport on Kalshi by volume; if NFL is 30-50%
of long-horizon sports, that's 140-230 NFL markets and each other
league at 25-70. Only NFL and possibly NBA clear 100.

LOCO with N=2 triggers the C4 fallback ("if only 2 leagues have
sufficient sample, fall back to requiring 2 of 2"). The
"cross-sport generalization" claim collapses to two-sport.
Worse, if NBA only squeaks by on 15-20 strategy-eligible markets,
C4 has effectively been passed by NFL alone. Sports analog of the
prior critic's election-cycle-dominance finding
([critic-methodology-phase-2.md](critic-methodology-phase-2.md)
Section "Survivorship and corpus composition").

### 6.2 Recommended adjustment

Reduce LOCO threshold to >= 50 markets to capture more leagues.
Report C4 per-league INCLUDING those below 50; flag if NFL is the
only league above 50. Replace the "2 of 2" fallback with "gate
fails for insufficient cross-sport sample if N < 3."

Severity: IMPORTANT.

## 7. Recommended changes before unlock

### BLOCKING

1. **Demote C3 to diagnostic; promote pooled bootstrap to gate.**
   Replace C3 in
   [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)
   Section 7 with: "C3 (revised): pooled mean per-trade net edge
   across all test partitions has bootstrap 95% CI lower bound >
   0pp." This was the prior critic's
   ([critic-methodology-phase-2.md](critic-methodology-phase-2.md)
   Section "C3" recommended fix) recommendation and applies with
   greater force at N=6.

2. **Pre-commit MIN_TEST_SIZE_PER_SPLIT = 30.** Add to Section 5.1.
   Splits below threshold are reported but excluded from gate
   evaluation. Without this, the methodology cannot distinguish
   sample-size SKIPs from signal-absence FAILs.

3. **Correct the "leave-one-league-out compensates" claim** in
   Section 5.1 Rationale paragraph. State explicitly: "league-out
   does NOT compensate for news-period leakage; the residual
   leakage is accepted as the cost of testability."

### IMPORTANT

4. **Add resolution-time-purge variant** as a sensitivity check.
   Re-run the gate with the additional constraint that train
   markets must RESOLVE before test_start (not merely OPEN before
   train_end + 14d). Reports as supplementary; if pooled mean edge
   collapses under this constraint, leakage is suspected.

5. **Tag and segment-report single-name vs broad-based markets.**
   Per Section 4 of this review. Single-name = parent event with 1
   contract; broad-based = parent event with >= 5 sibling binaries.
   Report C3 / C5 separately per segment. Do NOT exclude single-name.

6. **Reduce LOCO league threshold to 50 markets** and replace the
   "2 of 2" fallback with "gate fails if N < 3." Per Section 6 of
   this review.

7. **Re-derive C2 from long-horizon literature, not 2x Becker
   full-sample.** Becker's 2.23pp is a mix of single-game (high
   adverse selection) and futures. Setting C2 at 2.23pp UNMODIFIED
   (requiring the long-horizon slice to match the full-sample
   average) is more defensible than the 4.46pp 2x multiplier.

8. **Reconsider the 60d long-horizon threshold.** Either 30d
   (matches Le's >1mo bin and maximizes sample) or 90d (matches
   Bartlett's adverse-selection logic). 60d optimizes neither.

### NICE-TO-HAVE

9. **Add per-market-cluster shuffle bootstrap as leakage diagnostic.**
   Run the gate with true outcomes; rerun with outcomes shuffled
   within league. A positive pass under shuffled outcomes indicates
   leakage artifact.

10. **Flag in any pass verdict that fill rate vs institutional MMs
    remains untested.** Per Section 4.3 of this review.

## Citations table

| Claim | Source | Section / Item |
|---|---|---|
| Sports long-horizon slope 1.74 at >1mo | le-2026-crowd-wisdom.md | Domain-by-horizon trajectories |
| Sports 55,637 markets, 43.2M trades, median 76 trades | le-2026-crowd-wisdom.md | Per-domain breakdown on Kalshi |
| Bin boundary >1mo conventionally ~30 days | le-2026-crowd-wisdom.md | Time bins |
| Becker sports gap 2.23pp on 43.6M trades (full-sample mix) | becker-2026-microstructure.md | Per-category maker-taker gap |
| Becker Q4 2024 27x volume surge | becker-2026-microstructure.md | The 2024 sign flip |
| Becker TL;DR item 4: takers overpay for YES longshots (single-game pattern) | becker-2026-microstructure.md | TL;DR |
| Bartlett single-name higher informed price impact | bartlett-ohara-2026-adverse-selection.md | TL;DR item 2 |
| Bartlett behavioral surplus 2x adverse selection in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR item 4 |
| Bartlett VPIN one-sided flow predicts maker losses in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR item 6 |
| Burgi Jump / Susquehanna competition | burgi-deng-whelan-2025.md | Section 6 / Why hasn't the bias been arbitraged away |
| Phase 2 funnel: 12/12 splits skipped n_test=0 | phase-2-results.md | Funnel table |
| Phase 2 critic: news-period joint structure leakage path | critic-methodology-phase-2.md | Walk-forward purge |
| Phase 2 critic: C3 at alpha 0.05 needed pooled bootstrap | critic-methodology-phase-2.md | C3 recommended fix |
| Sports methodology C3 at alpha 0.109 | sports-longhorizon-methodology.md | Section 7 C3 |
| Sports methodology long-horizon filter 60d | sports-longhorizon-methodology.md | Section 2.2 |
| Sports methodology LOCO threshold 100 markets | sports-longhorizon-methodology.md | Section 5.2 |
| Sports methodology C2 = 4.46pp = 2x Becker | sports-longhorizon-methodology.md | Section 7 C2 |
| Sports methodology lifetime-straddle removed; LOCO claimed mitigation | sports-longhorizon-methodology.md | Section 5.1 Rationale |
