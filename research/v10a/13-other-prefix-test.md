# V10-A Round 15b: OTHER Prefix Validation Test

## Purpose

v1's PERSIST allowlist (KXMLBGAME, KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH) covers only 1 of 19 live fills since 2026-05-23. The other 18 fills landed in prefixes that have NEVER been validated. This test runs v1's exact strategy regime (buy YES as maker at yes_price >= 0.70 on Becker post-Oct-2024 data) against the OTHER prefixes to classify each as PERSIST, NULL, TRAIN_ONLY, OOS_ONLY, or INSUFFICIENT.

## Method

Identical to `validate_v1_strategy.py`:
1. Becker trades joined to finalized markets, prefix LIKE filter, post-2024-11-01.
2. Maker side at yes_price >= 0.70 (taker_side='no' AND yes_price >= 70).
3. Chronological split: train Nov 2024 to Sep 2025, OOS Sep 2025 to Nov 2025.
4. Per-event maker net P&L after Kalshi maker fee, cluster bootstrap n=2000 by event_ticker, 95% CI.
5. Verdict gate: PERSIST if both windows have n_events >= 10 AND CI excludes 0 (positive) AND event_mean > 0.

Script: `scripts/v10a/validate_other_prefixes.py`. Raw output: `research/v10a/13-other-prefix-test.json`.

## Results

| prefix | train n_evt | train mean (CI) | OOS n_evt | OOS mean (CI) | verdict |
|---|---|---|---|---|---|
| KXUFCFIGHT | 94 | +3.44% [+0.28%, +6.26%] | 82 | +1.97% [-0.78%, +4.35%] | TRAIN_ONLY |
| KXFOMEN (French Open men) | 113 | +0.89% [-2.23%, +3.71%] | 0 | none | INSUFFICIENT |
| KXBOXING | 2 | -8.56% [-32.74%, +15.62%] | 2 | +11.88% [+9.90%, +13.86%] | INSUFFICIENT |
| KXCS2 (Counter-Strike 2) | 1 | +3.75% (single event) | 19 | -1.66% [-10.84%, +6.15%] | INSUFFICIENT |
| KXUCLTOTAL | 0 | none | 5 | -18.87% [-59.25%, +1.90%] | INSUFFICIENT |
| KXNFLWINS (W1 denylist, sanity) | 7 | +19.17% [+13.61%, +24.43%] | 25 | +9.83% [+8.30%, +11.64%] | INSUFFICIENT (train n<10) |
| KXNBAPLAYOFFWINS | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXWCGAME | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXIPLFINALS | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXWCSTAGEOFELIM | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNHLDRAFTPICK | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXWNBAWINS | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXUFCOCCUR | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXOWGRRANK | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXPLAYWC | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNCAAFTOPAPRANK | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNEXTTEAMNBA | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNEXTTEAMNFL | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNEXTTEAMNHL | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXSTARTINGQBWEEK1 | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNFLPLAYOFF (W1 denylist, sanity) | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNHLSERIESSPREAD | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXWCSQUAD | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |
| KXNBAPOLOSE | 0 | n/a | 0 | n/a | INSUFFICIENT (NO BECKER DATA) |

Sanity check on Becker existence (post-Oct-2024 trades count, all regimes): `scripts/v10a/check_other_prefix_existence.py` confirms 17 of 24 prefixes have ZERO Becker market records at all. These are post-April-2026-rebrand tickers that Becker (which extends to November 2025) does not cover.

## Classifications

### PERSIST (allow these in v1's universe)

**None.** Zero of 24 OTHER prefixes meet the PERSIST gate.

### TRAIN_ONLY / NULL (deny these, add to denylist)

- **KXUFCFIGHT.** Train +3.44% with CI excluding zero, OOS +1.97% with CI [-0.78%, +4.35%] (includes zero). Classic regime-decay pattern: signal collapses out-of-sample. v1 has 2 KXUFCFIGHT fills and 2 resting. RECOMMEND DENY.

### INSUFFICIENT (untested, no Becker data or n_events < 10 in either window)

22 prefixes are INSUFFICIENT. Two sub-classes:

**Class A: zero Becker data (17 prefixes).** These are post-rebrand tickers Becker simply does not have. Cannot validate retrospectively. Includes KXNBAPLAYOFFWINS (4 v1 fills), KXWCGAME (3 fills + 3 resting), KXIPLFINALS (2 fills), KXWCSTAGEOFELIM (1 fill + 2 resting), KXNHLDRAFTPICK (1), KXWNBAWINS (1 fill + 1 resting), KXUFCOCCUR (1), KXOWGRRANK (1 resting), KXPLAYWC (1 resting), KXNCAAFTOPAPRANK (1 resting), KXNEXTTEAMNBA (0 in state but listed), KXNEXTTEAMNFL, KXNEXTTEAMNHL, KXSTARTINGQBWEEK1, KXNFLPLAYOFF (W1 denylist, sanity), KXNHLSERIESSPREAD, KXWCSQUAD, KXNBAPOLOSE.

**Class B: thin Becker data (5 prefixes).**
- KXFOMEN (French Open men): 113 train events with mean +0.89% and CI straddling zero, plus zero OOS events because the French Open is a once-per-year tournament outside the OOS window. NULL signal in train.
- KXBOXING: only 2 events per window. Train CI [-32.74%, +15.62%] is uninformative due to n=2. OOS shows +11.88% [+9.90%, +13.86%] but on only 2 events, which is structurally INSUFFICIENT.
- KXCS2 (Counter-Strike 2): 1 train event, 19 OOS events; OOS CI [-10.84%, +6.15%] includes zero. Functionally NULL.
- KXUCLTOTAL: 0 train, 5 OOS events with mean -18.87%. Insufficient n but the point estimate is negative.
- KXNFLWINS (W1 denylist sanity): 7 train events, 25 OOS events. The train n_evt < 10 threshold triggers INSUFFICIENT, but the OOS data here is interesting: OOS event mean +9.83%, CI [+8.30%, +11.64%] excludes zero. This is the opposite direction of the original v4-H finding (-1.03pp on n=95). The discrepancy is because v4-H measured ALL post-Oct-2024 KXNFLWINS YES sales (any price) whereas this test only counts YES-maker at >= 0.70. Selection effect: at >=0.70 the implied prob is high enough that even season-winner futures resolve mostly YES. Note that v4-H's adversarial reasoning still applies (high-variance long-horizon outcomes). RECOMMEND v1 KEEP this denylisted, but flag the regime discrepancy for future investigation.

## Recommendations for v1's updated allowlist/denylist

### Immediate v1 actions

1. **DENY KXUFCFIGHT in v1.** Empirical TRAIN_ONLY signal decay. v1 has 2 filled + 2 resting; cancel resting and add to denylist alongside W1 (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS).

2. **DENY ALL Class A (no-Becker-data) prefixes by default until shadow validation.** Specifically: KXNBAPLAYOFFWINS, KXWCGAME, KXIPLFINALS, KXWCSTAGEOFELIM, KXNHLDRAFTPICK, KXWNBAWINS, KXUFCOCCUR, KXOWGRRANK, KXPLAYWC, KXNCAAFTOPAPRANK, KXNEXTTEAMNBA, KXNEXTTEAMNFL, KXNEXTTEAMNHL, KXSTARTINGQBWEEK1, KXNHLSERIESSPREAD, KXWCSQUAD, KXNBAPOLOSE. Rationale: v1's PERSIST set is the only set we have positive evidence for; firing on untested universes is the same selection-effect failure mode as Round 10 v4-H (v1's measured edge did not generalize across prefixes).

3. **DENY thin-data prefixes** KXFOMEN (null signal), KXBOXING (n=2 per window), KXCS2 (esports, OOS negative), KXUCLTOTAL (OOS negative).

4. **Net allowlist for v1 (proposed):** ONLY the 5 PERSIST prefixes from Round 15. KXMLBGAME, KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH. Everything else off until shadow mode logs forward fills for 60-120 days, then re-evaluate.

### Shadow-mode candidates

If operator wants forward-validation rather than hard deny, the no-Becker-data Class A prefixes are candidates for shadow logging. They are NOT validated; deploying live capital to them is firing into a phantom (same F11 failure mode as v7-B).

### Caveats and known limits

- Becker post-Oct-2024 ends ~November 2025; live v1 has been firing in May 2026, so the post-rebrand universe is structurally outside Becker coverage. This is not Becker's fault; it is the dataset boundary.
- The W1 denylist sanity (KXNFLWINS) shows direction-dependent results vs v4-H. Worth a future deep-dive: does the maker-at->=70 filter accidentally select a winning subset of an otherwise-losing universe? If so the v1 PERSIST set may also have hidden selection effects.
- 17 of 24 prefixes simply cannot be tested retrospectively. The honest verdict for those is "do not deploy capital without forward validation."
