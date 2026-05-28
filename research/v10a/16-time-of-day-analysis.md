# Round 15c Track 2D: Time-of-day analysis on PERSIST prefixes

Method: for each of the 5 Becker-validated PERSIST prefixes,
stratify post-Oct-2024 maker trades (at yes_price >= 0.70) by
hour-of-day (US Eastern) and day-of-week. Per-cell event-level
cluster bootstrap CI (n=1000 resamples). Goal: identify time
windows with materially higher edge than the prefix overall.

## Per-prefix hour-band results

### KXMLBGAME

Overall: n_events=2203, event_mean=+0.0345, CI=[+0.0284, +0.0399]

| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| 00-02_ET | 23744 | 357 | +0.0248 | +0.0123 | +0.0356 |
| 03-05_ET | 10 | 2 | +0.1463 | +0.0075 | +0.2850 |
| 06-08_ET | 199 | 48 | -0.0231 | -0.1587 | +0.0900 |
| 09-11_ET | 349 | 77 | +0.0679 | -0.0282 | +0.1508 |
| 12-14_ET | 11867 | 405 | +0.0241 | -0.0119 | +0.0541 |
| 15-17_ET | 49574 | 799 | +0.0060 | -0.0122 | +0.0225 |
| 18-20_ET | 69590 | 1229 | -0.0031 | -0.0204 | +0.0155 |
| 21-23_ET | 131475 | 1374 | +0.0228 | +0.0137 | +0.0323 |
| evening_19-23_ET | 184890 | 1535 | +0.0265 | +0.0166 | +0.0352 |
| daytime_09-18_ET | 77965 | 937 | +0.0289 | +0.0136 | +0.0427 |
| late_night_00-05_ET | 23754 | 357 | +0.0248 | +0.0123 | +0.0356 |

Day-of-week (ET):

| DOW | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| Sun | 35113 | 412 | +0.0385 | +0.0252 | +0.0532 |
| Mon | 28259 | 230 | +0.0244 | -0.0036 | +0.0484 |
| Tue | 51398 | 395 | +0.0260 | +0.0078 | +0.0441 |
| Wed | 62413 | 437 | +0.0345 | +0.0206 | +0.0475 |
| Thu | 30358 | 260 | +0.0270 | +0.0070 | +0.0472 |
| Fri | 38332 | 387 | +0.0230 | +0.0031 | +0.0416 |
| Sat | 40935 | 448 | +0.0184 | +0.0024 | +0.0341 |

### KXATPMATCH

Overall: n_events=1190, event_mean=+0.0327, CI=[+0.0232, +0.0415]

| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| 00-02_ET | 8552 | 328 | -0.0371 | -0.0776 | -0.0011 |
| 03-05_ET | 6077 | 203 | -0.0005 | -0.0439 | +0.0433 |
| 06-08_ET | 12469 | 374 | -0.0013 | -0.0330 | +0.0294 |
| 09-11_ET | 32821 | 539 | -0.0021 | -0.0274 | +0.0220 |
| 12-14_ET | 37752 | 515 | +0.0005 | -0.0259 | +0.0239 |
| 15-17_ET | 32545 | 416 | -0.0018 | -0.0281 | +0.0263 |
| 18-20_ET | 11559 | 319 | -0.0063 | -0.0397 | +0.0271 |
| 21-23_ET | 10506 | 281 | -0.0113 | -0.0501 | +0.0262 |
| evening_19-23_ET | 17561 | 385 | -0.0029 | -0.0326 | +0.0253 |
| daytime_09-18_ET | 107622 | 930 | +0.0225 | +0.0079 | +0.0356 |
| late_night_00-05_ET | 14629 | 406 | -0.0086 | -0.0394 | +0.0229 |

Day-of-week (ET):

| DOW | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| Sun | 12722 | 164 | +0.0410 | +0.0072 | +0.0727 |
| Mon | 23017 | 264 | +0.0133 | -0.0161 | +0.0396 |
| Tue | 27996 | 271 | -0.0078 | -0.0388 | +0.0214 |
| Wed | 27509 | 246 | -0.0028 | -0.0363 | +0.0254 |
| Thu | 23319 | 244 | +0.0145 | -0.0139 | +0.0427 |
| Fri | 24696 | 191 | +0.0382 | +0.0056 | +0.0672 |
| Sat | 13022 | 156 | +0.0124 | -0.0235 | +0.0492 |

### KXNFLGAME

Overall: n_events=210, event_mean=+0.0376, CI=[+0.0159, +0.0575]

| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| 00-02_ET | 6295 | 74 | -0.0048 | -0.0973 | +0.0801 |
| 03-05_ET | 250 | 54 | +0.0190 | -0.1003 | +0.1230 |
| 06-08_ET | 1104 | 67 | -0.0094 | -0.1094 | +0.0947 |
| 09-11_ET | 7454 | 84 | -0.0149 | -0.1103 | +0.0747 |
| 12-14_ET | 49038 | 132 | -0.0345 | -0.1024 | +0.0284 |
| 15-17_ET | 101394 | 158 | +0.0101 | -0.0322 | +0.0478 |
| 18-20_ET | 82692 | 136 | +0.0033 | -0.0637 | +0.0589 |
| 21-23_ET | 137398 | 126 | +0.0226 | -0.0323 | +0.0753 |
| evening_19-23_ET | 192617 | 156 | +0.0211 | -0.0243 | +0.0595 |
| daytime_09-18_ET | 185359 | 166 | -0.0041 | -0.0468 | +0.0347 |
| late_night_00-05_ET | 6545 | 76 | -0.0114 | -0.1040 | +0.0785 |

Day-of-week (ET):

| DOW | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| Sun | 248511 | 154 | +0.0221 | -0.0092 | +0.0536 |
| Mon | 62837 | 81 | -0.0173 | -0.1057 | +0.0658 |
| Tue | 4898 | 70 | -0.0021 | -0.1059 | +0.0903 |
| Wed | 2107 | 67 | -0.0101 | -0.1093 | +0.0872 |
| Thu | 54665 | 74 | +0.0402 | -0.0412 | +0.1180 |
| Fri | 6998 | 72 | +0.0668 | -0.0140 | +0.1395 |
| Sat | 5609 | 88 | +0.0342 | -0.0395 | +0.1004 |

### KXNCAAFGAME

Overall: n_events=812, event_mean=+0.0460, CI=[+0.0371, +0.0545]

| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| 00-02_ET | 39013 | 453 | +0.0187 | -0.0091 | +0.0454 |
| 03-05_ET | 892 | 153 | +0.0094 | -0.0462 | +0.0592 |
| 06-08_ET | 1482 | 324 | +0.0221 | -0.0150 | +0.0525 |
| 09-11_ET | 4908 | 422 | -0.0069 | -0.0383 | +0.0254 |
| 12-14_ET | 54600 | 536 | -0.0033 | -0.0310 | +0.0238 |
| 15-17_ET | 105847 | 631 | +0.0022 | -0.0212 | +0.0238 |
| 18-20_ET | 129099 | 655 | +0.0050 | -0.0167 | +0.0257 |
| 21-23_ET | 154900 | 587 | +0.0288 | +0.0097 | +0.0482 |
| evening_19-23_ET | 229703 | 681 | +0.0345 | +0.0182 | +0.0492 |
| daytime_09-18_ET | 219651 | 680 | +0.0193 | +0.0020 | +0.0379 |
| late_night_00-05_ET | 39905 | 475 | +0.0155 | -0.0132 | +0.0414 |

Day-of-week (ET):

| DOW | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| Sun | 30268 | 322 | +0.0283 | -0.0041 | +0.0566 |
| Mon | 4044 | 345 | +0.0391 | +0.0063 | +0.0678 |
| Tue | 16022 | 361 | +0.0100 | -0.0226 | +0.0436 |
| Wed | 12390 | 346 | +0.0018 | -0.0338 | +0.0371 |
| Thu | 17534 | 360 | +0.0183 | -0.0146 | +0.0486 |
| Fri | 45800 | 431 | +0.0295 | +0.0022 | +0.0580 |
| Sat | 364683 | 737 | +0.0364 | +0.0235 | +0.0479 |

### KXWTAMATCH

Overall: n_events=1136, event_mean=+0.0264, CI=[+0.0166, +0.0371]

| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| 00-02_ET | 21410 | 311 | -0.0107 | -0.0467 | +0.0237 |
| 03-05_ET | 10228 | 214 | -0.0221 | -0.0633 | +0.0186 |
| 06-08_ET | 10004 | 309 | -0.0210 | -0.0583 | +0.0143 |
| 09-11_ET | 15566 | 433 | -0.0041 | -0.0346 | +0.0237 |
| 12-14_ET | 20365 | 434 | -0.0103 | -0.0370 | +0.0161 |
| 15-17_ET | 13891 | 344 | +0.0059 | -0.0230 | +0.0341 |
| 18-20_ET | 12662 | 281 | +0.0156 | -0.0172 | +0.0486 |
| 21-23_ET | 10096 | 298 | -0.0070 | -0.0462 | +0.0288 |
| evening_19-23_ET | 19249 | 405 | +0.0019 | -0.0291 | +0.0314 |
| daytime_09-18_ET | 53331 | 773 | +0.0147 | -0.0021 | +0.0316 |
| late_night_00-05_ET | 31638 | 402 | -0.0087 | -0.0390 | +0.0211 |

Day-of-week (ET):

| DOW | n_trades | n_events | event_mean | CI lower | CI upper |
|---|---|---|---|---|---|
| Sun | 9469 | 150 | -0.0115 | -0.0612 | +0.0307 |
| Mon | 19942 | 291 | +0.0046 | -0.0272 | +0.0343 |
| Tue | 20386 | 304 | -0.0001 | -0.0300 | +0.0257 |
| Wed | 19953 | 237 | +0.0139 | -0.0175 | +0.0424 |
| Thu | 17354 | 201 | +0.0124 | -0.0241 | +0.0456 |
| Fri | 17357 | 162 | +0.0395 | +0.0089 | +0.0680 |
| Sat | 9761 | 124 | +0.0373 | -0.0021 | +0.0707 |

## Verdict

**Result: SHADOW-CANDIDATE.** Two of the five PERSIST prefixes show
modest time-of-day concentration; the others have edge that is
already uniformly distributed across the day or that does not pass
any single per-band CI gate.

### Per-prefix findings

| Prefix | Best window (ET) | Window edge (CI lower) | Overall edge | Lift over overall |
|---|---|---|---|---|
| KXMLBGAME | 21-23 ET or 19-23 ET | +2.66% (+1.66%) | +3.45% | -0.79pp (worse) |
| KXATPMATCH | daytime 09-18 ET | +2.25% (+0.79%) | +3.27% | -1.02pp (worse) |
| KXNFLGAME | (no band passes) | n/a | +3.76% | n/a |
| KXNCAAFGAME | evening 19-23 ET | +3.45% (+1.82%) | +4.60% | -1.15pp (worse) |
| KXWTAMATCH | (no band passes) | n/a | +2.64% | n/a |

### Honest read

The time-of-day stratification did NOT produce a window with higher
event-level edge than the prefix overall on any of the five PERSIST
prefixes. The cells that passed (CI lower > 0) are subsets of the
overall distribution that happen to have positive bootstraps; none
of them have point estimates above the overall.

This is the OPPOSITE of the hypothesized pattern (evening retail
volume produces a fatter retail mispricing tail). The actual data
suggests that the edge is operator-distributed across the trading
day, NOT concentrated. Restricting v1 to a specific window would
reduce fill volume without improving per-fill EV.

### Day-of-week tail

A weaker secondary finding: KXWTAMATCH on Fridays has a per-event
mean of +3.95% with CI [+0.89%, +6.80%] vs the overall +2.64%. This
is a 1.31pp lift but n_events=162 in the Friday cell (low power) and
not consistent across other prefixes. Possible WTA tour scheduling
artifact (Friday is typically Round of 16). NOT actionable on its
own.

### Action

NO change recommended to v1's scanning logic. The PERSIST prefix
allowlist already captures the edge. A more sophisticated future
investigation could try (a) hour-of-day specific to each individual
match's start time (rather than trade-clock hour) and (b) interact
with time-to-close. Neither is justified by current evidence.
