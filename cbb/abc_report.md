# CBB A/B/C harness — development run

Development data only. 2026 was examined earlier and is not a holdout; promotion requires the prospective 2027 shadow test and the pre-registered rule in SAIF-CBB-ABC-Design.md.

# Sides

## A-dev 2022–2025 (21,910 games, leave-one-season-out A1)

Outcome accuracy vs the CLOSE (no openers in these seasons):

| model | MAE | RMSE |
|---|---|---|
| A0 (live) | 9.050 | 11.484 |
| A1 | 9.046 | 11.477 |
| close (market benchmark) | 8.793 | 11.160 |

- A1 interval coverage (target 50 / 80 / 90%): 51% / 81% / 90%
- σ_outcome early season (a team < 5 games) 12.5 vs later 11.2; σ_rating 6.7 vs 4.0
- |close| 0-10: mean signed error A0 +0.05, A1 +0.27, close -0.29 (positive = favorite did better than projected)
- |close| 10-20: mean signed error A0 +0.59, A1 +0.75, close +0.11 (positive = favorite did better than projected)
- |close| 20-+: mean signed error A0 +3.80, A1 +2.91, close +0.28 (positive = favorite did better than projected)
- Win probability, 21,737 games with closing moneylines: log loss A1 0.5404 vs market (de-vigged) 0.5324

## BC-dev: games with an opener (7,536; C scored on 6,491 from 2025-03 on, rolling monthly origin)

A1 calibration (fit on 2022–24): [0.9032, 0.0055] | σ_e² 174.7, s² 113.5

**1. Final outcomes** (identical games)

| model | MAE | RMSE | ΔMSE vs B (95% CI) |
|---|---|---|---|
| B (opener) | 9.064 | 11.488 |  |
| A0 (live) | 9.193 | 11.677 | +4.38 (+1.10 to +7.95) |
| A1 | 9.182 | 11.662 | +4.04 (+0.70 to +7.36) |
| C (full) | 9.461 | 12.295 | +19.19 (+10.85 to +28.38) |
| C1 (opener + one weight) | 9.073 | 11.510 | +0.51 (+0.09 to +0.89) |
| close (market benchmark) | 8.981 | 11.376 | |

**2. Closing-line movement**

| model | slope of (close−open) on (model−open) | t | MAE predicting the close |
|---|---|---|---|
| B (opener) | — | — | 1.000 |
| A0 (live) | 0.097 | 16.3 | 2.071 |
| A1 | 0.102 | 16.8 | 2.038 |
| C (full) | -0.016 | -3.2 | 2.095 |
| C1 (opener + one weight) | 0.422 | 16.0 | 1.088 |
| C (close-targeted) | 0.985 | 18.7 | 1.020 |

**3. Probability calibration** (cover at the opener; intervals for the final result)

| model | log loss (cover at opener) | Brier | calibration slope | 50% / 80% / 90% interval coverage |
|---|---|---|---|---|
| B (opener, p = 0.5) | 0.6931 | 0.2500 | — | — |
| A1 | 0.7039 | 0.2550 | 0.19 | 50% / 81% / 90% |
| C (full) | 0.7272 | 0.2599 | -0.08 | 49% / 80% / 89% |
| C1 (opener + one weight) | 0.6940 | 0.2504 | 0.15 | 51% / 81% / 90% |

**4. Betting economics at the opener**, edge ≥ 3 (threshold carried over from earlier work, not re-tuned here), −110

| model | bets | toward / against | avg CLV | record | units | ROI (95% CI) | max drawdown | ROI at mid fill | ROI −0.5 |
|---|---|---|---|---|---|---|---|---|---|
| A0 (live) | 1150 | 48% / 38% | +0.38 | 582-564 (50.8%) | -34.9u | -3.0% (-10.0% to +4.2%) | 66.3u | -3.3% | -6.3% |
| A1 | 1096 | 50% / 37% | +0.45 | 549-544 (50.2%) | -44.9u | -4.1% (-10.5% to +3.0%) | 55.8u | -4.6% | -7.4% |
| C (full) | 940 | 47% / 40% | +0.04 | 445-491 (47.5%) | -86.5u | -9.2% (-18.9% to -0.3%) | 118.2u | -8.3% | -12.1% |
| C1 (opener + one weight) | 16 | too few bets | | | | | | | |

*C weights by test month (C1: share of the model−opener gap kept):* 2025-03 -0.20, 2025-04 0.10, 2025-11 0.04, 2025-12 0.47, 2026-01 0.44, 2026-02 0.28, 2026-03 0.25, 2026-04 0.25

**5. Uncertainty test** (reported separately; not a profitability claim)

Train months < 2025-12, test months ≥ 2025-12. τ chosen on train: 0.25
- Spearman with movement toward the model, test months: |edge| 0.078 vs stabilized ratio 0.085 (n = 4491)
- Regression on test months, movement toward model ~ |edge| + σ_rating + |edge|×σ_rating: const +0.300 (t 1.8), |edge| +0.289 (t 3.5), σ_r -0.128 (t -3.1), |edge|×σ_r -0.010 (t -0.5)

**Sensitivity: benchmark book choice** (outcome MAE of B and A1 on the same games)

| opener source | games | B MAE | A1 MAE | close MAE |
|---|---|---|---|---|
| median of all books | 7,536 | 8.969 | 9.089 | 8.892 |
| Bovada only | 4,922 | 9.087 | 9.161 | 9.035 |
| excluding DraftKings / ESPN BET | 4,922 | 9.087 | 9.161 | 9.035 |

# Totals

## A-dev 2022–2025 (21,923 games, leave-one-season-out A1)

Outcome accuracy vs the CLOSE (no openers in these seasons):

| model | MAE | RMSE |
|---|---|---|
| A0 (live) | 13.075 | 16.674 |
| A1 | 13.085 | 16.658 |
| close (market benchmark) | 12.872 | 16.415 |

- A1 interval coverage (target 50 / 80 / 90%): 52% / 81% / 90%
- σ_outcome early season (a team < 5 games) 17.1 vs later 16.6; σ_rating 4.8 vs 3.4

## BC-dev: games with an opener (7,453; C scored on 5,726 from 2025-04 on, rolling monthly origin)

A1 calibration (fit on 2022–24): [-0.1392, 1.0084] | σ_e² 223.9, s² 267.7

**1. Final outcomes** (identical games)

| model | MAE | RMSE | ΔMSE vs B (95% CI) |
|---|---|---|---|
| B (opener) | 13.563 | 17.131 |  |
| A0 (live) | 13.734 | 17.346 | +7.43 (+3.09 to +11.89) |
| A1 | 13.797 | 17.363 | +8.01 (+3.69 to +12.16) |
| C (full) | 13.575 | 17.101 | -1.04 (-2.11 to +0.31) |
| C1 (opener + one weight) | 13.588 | 17.118 | -0.46 (-1.42 to +0.56) |
| close (market benchmark) | 13.380 | 16.911 | |

**2. Closing-line movement**

| model | slope of (close−open) on (model−open) | t | MAE predicting the close |
|---|---|---|---|
| B (opener) | — | — | 1.731 |
| A0 (live) | 0.146 | 18.0 | 2.848 |
| A1 | 0.128 | 16.8 | 3.127 |
| C (full) | 0.150 | 5.9 | 1.928 |
| C1 (opener + one weight) | 0.106 | 3.4 | 1.886 |
| C (close-targeted) | 0.600 | 15.0 | 1.716 |

**3. Probability calibration** (cover at the opener; intervals for the final result)

| model | log loss (cover at opener) | Brier | calibration slope | 50% / 80% / 90% interval coverage |
|---|---|---|---|---|
| B (opener, p = 0.5) | 0.6931 | 0.2500 | — | — |
| A1 | 0.7047 | 0.2552 | 0.19 | 48% / 79% / 89% |
| C (full) | 0.6937 | 0.2503 | 1.22 | 49% / 80% / 89% |
| C1 (opener + one weight) | 0.6943 | 0.2506 | 0.37 | 49% / 80% / 90% |

**4. Betting economics at the opener**, edge ≥ 4 (threshold carried over from earlier work, not re-tuned here), −110

| model | bets | toward / against | avg CLV | record | units | ROI (95% CI) | max drawdown | ROI at mid fill | ROI −0.5 |
|---|---|---|---|---|---|---|---|---|---|
| A0 (live) | 1298 | 61% / 30% | +0.93 | 697-594 (54.0%) | +39.6u | +3.1% (-1.9% to +8.4%) | 33.3u | +0.4% | +0.4% |
| A1 | 1599 | 62% / 30% | +0.88 | 850-739 (53.5%) | +33.7u | +2.1% (-2.9% to +7.5%) | 41.4u | -0.5% | -0.3% |
| C (full) | 2 | too few bets | | | | | | | |
| C1 (opener + one weight) | 0 | too few bets | | | | | | | |

*C weights by test month (C1: share of the model−opener gap kept):* 2025-04 -0.12, 2025-11 -0.05, 2025-12 0.18, 2026-01 0.21, 2026-02 0.30, 2026-03 0.32, 2026-04 0.27

**5. Uncertainty test** (reported separately; not a profitability claim)

Train months < 2025-12, test months ≥ 2025-12. τ chosen on train: 0.25
- Spearman with movement toward the model, test months: |edge| 0.178 vs stabilized ratio 0.171 (n = 4496)
- Regression on test months, movement toward model ~ |edge| + σ_rating + |edge|×σ_rating: const -0.113 (t -0.3), |edge| +0.068 (t 0.7), σ_r +0.001 (t 0.0), |edge|×σ_r +0.028 (t 1.1)

**Sensitivity: benchmark book choice** (outcome MAE of B and A1 on the same games)

| opener source | games | B MAE | A1 MAE | close MAE |
|---|---|---|---|---|
| median of all books | 7,453 | 13.374 | 13.579 | 13.198 |
| Bovada only | 4,925 | 13.576 | 13.776 | 13.402 |
| excluding DraftKings / ESPN BET | 4,925 | 13.576 | 13.776 | 13.402 |
