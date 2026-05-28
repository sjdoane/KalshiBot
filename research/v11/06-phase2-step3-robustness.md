# v11 Phase 2 Step 3: Robustness Checks

**Round:** 16 (v11) Track 1 Granger-first.
**Date:** 2026-05-27. **Script:** scripts/v11/phase2_step3_robustness.py

Two robustness checks on the Granger MLB signal that fired at
F=20.12, p=0.000022, gamma=0.7746 (n=89) in Step 2.

## LOCO-by-bookmaker (MLB only)

Drop one bookmaker at a time from the per-game implied median.
If the MLB signal survives all single-bookmaker drops, the
lead-lag is not driven by any one venue.

| Bookmaker dropped | n | F | p_value | gamma | gamma_se | passes (p<=0.05/3, gamma>0) |
|---|---|---|---|---|---|---|
| fanduel | 89 | 21.2226 | 0.000014 | 0.7910 | 0.1717 | True |
| williamhill_us | 89 | 18.9977 | 0.000036 | 0.7739 | 0.1776 | True |
| draftkings | 89 | 19.9353 | 0.000024 | 0.7710 | 0.1727 | True |
| lowvig | 89 | 18.6604 | 0.000042 | 0.7546 | 0.1747 | True |
| betonlineag | 89 | 18.6277 | 0.000042 | 0.7546 | 0.1748 | True |
| bovada | 89 | 18.9898 | 0.000036 | 0.7588 | 0.1741 | True |
| fanatics | 89 | 20.7772 | 0.000017 | 0.7824 | 0.1717 | True |
| mybookieag | 89 | 19.2243 | 0.000033 | 0.7783 | 0.1775 | True |
| betmgm | 89 | 20.6764 | 0.000018 | 0.7833 | 0.1723 | True |
| betrivers | 89 | 17.4065 | 0.000072 | 0.7313 | 0.1753 | True |

**LOCO verdict: ROBUST** (all single-bookmaker drops maintain the gate).

## Commence-time offset sensitivity (MLB only)

Vary the commence_estimate offset (lock v3 default 3.5h);
if the signal collapses at one offset, the 3.5h choice was a
post-hoc fit.

| Offset | n | F | p_value | gamma | gamma_se |
|---|---|---|---|---|---|
| 2.5h | 115 | 0.6312 | 0.428606 | 0.2145 | 0.2700 |
| 3.0h | 107 | 8.8071 | 0.003724 | 0.5853 | 0.1972 |
| 3.5h | 89 | 20.1193 | 0.000022 | 0.7746 | 0.1727 |
| 4.0h | 88 | 23.8181 | 0.000005 | 0.7665 | 0.1571 |
| 4.5h | 86 | 6.5064 | 0.012585 | 0.3330 | 0.1306 |

F-statistic range across offsets: [0.63, 23.82]; signal unstable across +/- 1 hour of commence-time approximation.

## Combined robustness verdict for MLB signal

- LOCO-by-bookmaker: ROBUST
- Commence-offset sensitivity: F-range [0.63, 8.81, 20.12, 23.82, 6.51]

These robustness diagnostics inform the Phase 3 adversarial
critic of the per-sport MLB signal. NFL non-result and NBA
underpowered status are unchanged.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014
or U+2013 throughout.*