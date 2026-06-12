# v22 archived fee-table research (2026-06-11, lock H-4 artifact)

Built from Wayback captures of the Kalshi fee-schedule PDF (7 distinct
versions verified by text diff), the help-center fees page, the
designated-series search API (captures from 2025-09-26), and the
fee_changes API log. Downloaded artifacts preserved at
`AI Projects/_kalshi_fee_archive/` (outside this repo).

## Headline finding (changes the screen's fee handling)

**Maker fees did not exist AT ALL from 2024-11-01 to 2025-05-12** (every
schedule version states fees are charged only on immediately matched
orders). They were introduced 2025-05-13 on a 29-series designated list at
a FLAT $0.0025/contract, expanded 2025-06-05 (+10 series incl. KXNFLGAME),
switched to the quadratic ceil(1.75*P*(1-P))-cent formula on 2025-07-08
(+9 series; KXATPMATCH/KXWTAMATCH de-designated 2025-07-13), and expanded
again between 2025-08-17 and 2025-09-26 (~31 series incl. KXNCAAFGAME,
KXEPLGAME, NFL futures; exact start unarchived = the main ambiguity zone),
plus KXWNBA*/KXMLBGAME/KXMLBSERIES from 2025-10-04T07:00Z (fee_changes
log). Everything not designated = ZERO maker fee for the entire window.

Two prior assumptions corrected: the 0.0175 coefficient is valid only from
2025-07-08; index series were reduced-TAKER (0.035), not maker-fee, series
for nearly the whole window (KXINXY/KXNASDAQ100Y joined the maker list by
late Sep with an ambiguous 0.5 multiplier).

## Encoding

`research/v22/fee_table.json` encodes each row with a fee_low/fee_high
envelope; ambiguous spans (the Jun gap for the 9 July series, the Aug-Sep
expansion start, the index-series coefficient) have fee_low != fee_high
and are resolved conservatively by the lock's dual-run rule (K-P1 must
pass under both). flat_0025 is encoded unrounded ($0.0025/contract; the
era's monthly rounding rebate refunds the ceil residue). NFL division
futures are matched by the KXNFLAFC*/KXNFLNFC* globs because the archive
lists them as a family; a glob miss falls to ALL_OTHER zero, which is the
fee_low direction (noted as a residual naming risk).

## Capture record

PDF versions: 20241105134520, 20241228202003, 20250108014437,
20250201011604 (all taker-only), 20250514231857 (maker intro, stamped
2025-05-13), 20250606094329 (stamped 2025-06-05), 20250708150126 (stamped
2025-07-08, quadratic formula), 20250817122512 (identical), revisit
20250903044644 (unchanged), 20251008232930 (stamped 2025-10-01, list moved
to the web/API). Designated-list API snapshots: 20250926131715,
20250930171924, 20251010153527, 20251020183118. fee_changes API:
20251007033820 + live fetch 2026-06-11. Help-center: 6 captures 2025-03-16
to 2025-10-10. Taker-side context for completeness: general 0.07
quadratic all window; INX*/NASDAQ100* taker at 0.035; election markets
zero-fee through early 2025; weather taker experiment 2025-03-04 to
2025-04-01; five politics series zero-fee from 2025-10-21.
