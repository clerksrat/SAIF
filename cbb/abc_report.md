# CBB A/B/C harness — development run

Development data only. 2026 was examined earlier and is not a holdout; promotion requires the prospective 2027 shadow test and the pre-registered rule in SAIF-CBB-ABC-Design.md.

# Sides

## A-dev 2017–2024 (39,271 games; calibration fit only on earlier seasons)

Outcome accuracy vs the CLOSE (no openers in these seasons):

| model | MAE | RMSE | MAE early season | MAE later |
|---|---|---|---|---|
| A0 (live) | 8.987 | 11.402 | 9.653 | 8.842 |
| A1, expanding window | 8.986 | 11.397 | 9.655 | 8.840 |
| A1, rolling 3 seasons | 8.985 | 11.397 | 9.658 | 8.839 |
| A2 (rosters), expanding | 8.980 | 11.393 | 9.650 | 8.835 |
| A2 (rosters), rolling 3 | 8.980 | 11.393 | 9.651 | 8.834 |
| close (market benchmark) | 8.806 | 11.199 | 9.289 | 8.701 |

- A2 interval coverage (target 50 / 80 / 90%): 51% / 80% / 89%
- A1 interval coverage (target 50 / 80 / 90%): 51% / 80% / 89%
- σ_outcome early season (a team < 5 games) 12.1 vs later 11.0; σ_rating 6.0 vs 3.6
- |close| 0-10: mean signed error A0 +0.03, A1 +0.22, close -0.31 (positive = favorite did better than projected)
- |close| 10-20: mean signed error A0 +0.30, A1 +0.47, close +0.19 (positive = favorite did better than projected)
- |close| 20-+: mean signed error A0 +2.39, A1 +1.65, close +0.53 (positive = favorite did better than projected)
- Win probability, 38,341 games with closing moneylines: log loss A1 0.5458 vs market (de-vigged) 0.5448

## BC-dev: games with an opener (7,536; C scored on 6,491 from 2025-03 on, rolling monthly origin)

A1 calibration (fit on 2016–2024): [0.914, 0.0044] | σ_e² 151.4, s² 112.7; A2: [0.9099, 0.0042]

**1. Final outcomes** (identical games)

| model | MAE | RMSE | ΔMSE vs B (95% CI) |
|---|---|---|---|
| B (opener) | 9.064 | 11.488 |  |
| A0 (live) | 9.192 | 11.674 | +4.32 (+1.05 to +7.88) |
| A1 | 9.181 | 11.662 | +4.02 (+0.66 to +7.44) |
| A2 (rosters) | 9.200 | 11.692 | +4.73 (+1.58 to +7.81) |
| C (full) | 9.462 | 12.297 | +19.25 (+11.14 to +29.36) |
| C1 (opener + one weight) | 9.073 | 11.511 | +0.54 (+0.16 to +0.92) |
| close (market benchmark) | 8.981 | 11.376 | |

**2. Closing-line movement**

| model | slope of (close−open) on (model−open) | t | MAE predicting the close |
|---|---|---|---|
| B (opener) | — | — | 1.000 |
| A0 (live) | 0.098 | 16.4 | 2.066 |
| A1 | 0.101 | 16.6 | 2.035 |
| A2 (rosters) | 0.086 | 14.7 | 2.167 |
| C (full) | -0.014 | -2.9 | 2.099 |
| C1 (opener + one weight) | 0.411 | 15.6 | 1.091 |
| C (close-targeted) | 1.055 | 19.5 | 1.019 |

**3. Probability calibration** (cover at the opener; intervals for the final result)

| model | log loss (cover at opener) | Brier | calibration slope | 50% / 80% / 90% interval coverage |
|---|---|---|---|---|
| B (opener, p = 0.5) | 0.6931 | 0.2500 | — | — |
| A1 | 0.7043 | 0.2551 | 0.19 | 49% / 80% / 89% |
| A2 (rosters) | 0.7060 | 0.2558 | 0.18 | 49% / 80% / 89% |
| C (full) | 0.7284 | 0.2602 | -0.08 | 49% / 79% / 89% |
| C1 (opener + one weight) | 0.6940 | 0.2504 | 0.14 | 50% / 80% / 90% |

**4. Betting economics at the opener**, edge ≥ 3 (threshold carried over from earlier work, not re-tuned here), −110

| model | bets | toward / against | avg CLV | record | units | ROI (95% CI) | max drawdown | ROI at mid fill | ROI −0.5 |
|---|---|---|---|---|---|---|---|---|---|
| A0 (live) | 1142 | 48% / 38% | +0.39 | 579-559 (50.9%) | -32.6u | -2.9% (-9.3% to +4.1%) | 62.3u | -3.1% | -6.2% |
| A1 | 1086 | 49% / 37% | +0.43 | 544-539 (50.2%) | -44.5u | -4.1% (-10.6% to +2.8%) | 57.9u | -4.6% | -7.4% |
| A2 (rosters) | 1257 | 48% / 39% | +0.33 | 645-608 (51.5%) | -21.6u | -1.7% (-6.8% to +3.9%) | 53.4u | -2.0% | -4.5% |
| C (full) | 942 | 47% / 40% | +0.04 | 447-491 (47.7%) | -84.6u | -9.0% (-17.0% to -1.4%) | 121.8u | -8.3% | -11.9% |
| C1 (opener + one weight) | 17 | too few bets | | | | | | | |

*C weights by test month (C1: share of the model−opener gap kept):* 2025-03 -0.21, 2025-04 0.10, 2025-11 0.03, 2025-12 0.47, 2026-01 0.45, 2026-02 0.28, 2026-03 0.24, 2026-04 0.25

**5. Uncertainty test** (reported separately; not a profitability claim)

Train months < 2025-12, test months ≥ 2025-12. τ chosen on train: 0.25
- Spearman with movement toward the model, test months: |edge| 0.081 vs stabilized ratio 0.089 (n = 4491)
- Regression on test months, movement toward model ~ |edge| + σ_rating + |edge|×σ_rating: const +0.356 (t 2.2), |edge| +0.289 (t 3.5), σ_r -0.155 (t -3.5), |edge|×σ_r -0.010 (t -0.5)

**Sensitivity: benchmark book choice** (outcome MAE of B and A1 on the same games)

| opener source | games | B MAE | A1 MAE | close MAE |
|---|---|---|---|---|
| median of all books | 7,536 | 8.969 | 9.087 | 8.892 |
| Bovada only | 4,922 | 9.087 | 9.159 | 9.035 |
| excluding DraftKings / ESPN BET | 4,922 | 9.087 | 9.159 | 9.035 |

# Totals

## A-dev 2017–2024 (39,292 games; calibration fit only on earlier seasons)

Outcome accuracy vs the CLOSE (no openers in these seasons):

| model | MAE | RMSE | MAE early season | MAE later |
|---|---|---|---|---|
| A0 (live) | 13.284 | 16.904 | 13.752 | 13.182 |
| A1, expanding window | 13.319 | 16.894 | 13.792 | 13.216 |
| A1, rolling 3 seasons | 13.311 | 16.894 | 13.771 | 13.211 |
| A2 (rosters), expanding | 13.308 | 16.881 | 13.765 | 13.209 |
| A2 (rosters), rolling 3 | 13.301 | 16.881 | 13.747 | 13.205 |
| close (market benchmark) | 13.117 | 16.681 | 13.423 | 13.050 |

- A2 interval coverage (target 50 / 80 / 90%): 52% / 81% / 91%
- A1 interval coverage (target 50 / 80 / 90%): 52% / 81% / 91%
- σ_outcome early season (a team < 5 games) 17.5 vs later 17.0; σ_rating 5.4 vs 3.8

## BC-dev: games with an opener (7,453; C scored on 5,726 from 2025-04 on, rolling monthly origin)

A1 calibration (fit on 2016–2024): [2.5424, 0.9891] | σ_e² 242.7, s² 271.9; A2: [0.7337, 1.0019]

**1. Final outcomes** (identical games)

| model | MAE | RMSE | ΔMSE vs B (95% CI) |
|---|---|---|---|
| B (opener) | 13.563 | 17.131 |  |
| A0 (live) | 13.734 | 17.346 | +7.43 (+3.64 to +12.09) |
| A1 | 13.780 | 17.351 | +7.60 (+3.29 to +11.71) |
| A2 (rosters) | 13.775 | 17.333 | +6.96 (+3.01 to +10.80) |
| C (full) | 13.571 | 17.098 | -1.13 (-2.26 to +0.11) |
| C1 (opener + one weight) | 13.588 | 17.117 | -0.50 (-1.50 to +0.52) |
| close (market benchmark) | 13.380 | 16.911 | |

**2. Closing-line movement**

| model | slope of (close−open) on (model−open) | t | MAE predicting the close |
|---|---|---|---|
| B (opener) | — | — | 1.731 |
| A0 (live) | 0.146 | 18.0 | 2.848 |
| A1 | 0.133 | 17.3 | 3.063 |
| A2 (rosters) | 0.145 | 18.6 | 3.004 |
| C (full) | 0.185 | 7.2 | 1.912 |
| C1 (opener + one weight) | 0.120 | 3.9 | 1.883 |
| C (close-targeted) | 0.677 | 15.8 | 1.706 |

**3. Probability calibration** (cover at the opener; intervals for the final result)

| model | log loss (cover at opener) | Brier | calibration slope | 50% / 80% / 90% interval coverage |
|---|---|---|---|---|
| B (opener, p = 0.5) | 0.6931 | 0.2500 | — | — |
| A1 | 0.7037 | 0.2548 | 0.20 | 49% / 80% / 90% |
| A2 (rosters) | 0.7033 | 0.2546 | 0.20 | 49% / 79% / 90% |
| C (full) | 0.6935 | 0.2502 | 1.39 | 50% / 80% / 90% |
| C1 (opener + one weight) | 0.6943 | 0.2506 | 0.49 | 50% / 80% / 90% |

**4. Betting economics at the opener**, edge ≥ 4 (threshold carried over from earlier work, not re-tuned here), −110

| model | bets | toward / against | avg CLV | record | units | ROI (95% CI) | max drawdown | ROI at mid fill | ROI −0.5 |
|---|---|---|---|---|---|---|---|---|---|
| A0 (live) | 1299 | 61% / 30% | +0.93 | 698-594 (54.0%) | +40.5u | +3.1% (-3.2% to +8.4%) | 33.3u | +0.5% | +0.5% |
| A1 | 1545 | 62% / 30% | +0.90 | 831-704 (54.1%) | +51.5u | +3.4% (-2.3% to +8.4%) | 38.3u | +0.6% | +1.0% |
| A2 (rosters) | 1496 | 63% / 29% | +0.98 | 805-683 (54.1%) | +48.8u | +3.3% (-3.4% to +9.6%) | 41.6u | +0.5% | +1.1% |
| C (full) | 3 | too few bets | | | | | | | |
| C1 (opener + one weight) | 0 | too few bets | | | | | | | |

*C weights by test month (C1: share of the model−opener gap kept):* 2025-04 -0.11, 2025-11 -0.06, 2025-12 0.19, 2026-01 0.22, 2026-02 0.32, 2026-03 0.33, 2026-04 0.28

**5. Uncertainty test** (reported separately; not a profitability claim)

Train months < 2025-12, test months ≥ 2025-12. τ chosen on train: 1
- Spearman with movement toward the model, test months: |edge| 0.180 vs stabilized ratio 0.174 (n = 4496)
- Regression on test months, movement toward model ~ |edge| + σ_rating + |edge|×σ_rating: const -0.085 (t -0.2), |edge| +0.087 (t 0.9), σ_r -0.000 (t -0.0), |edge|×σ_r +0.024 (t 1.0)

**Sensitivity: benchmark book choice** (outcome MAE of B and A1 on the same games)

| opener source | games | B MAE | A1 MAE | close MAE |
|---|---|---|---|---|
| median of all books | 7,453 | 13.374 | 13.565 | 13.198 |
| Bovada only | 4,925 | 13.576 | 13.759 | 13.402 |
| excluding DraftKings / ESPN BET | 4,925 | 13.576 | 13.759 | 13.402 |
