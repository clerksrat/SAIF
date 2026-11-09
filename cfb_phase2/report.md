# CFB Phase 2 — CFBD pack backtest

Data: 4777 regular-season games with a closing spread (2016-19, 2021-25); 2026 weekly files 411 games, 228 with results (weeks 6-9).
Ridge lambda (tuned on 2024): STATS 3000, RESID 100000. Validation MAE by lambda (STATS, RESID): 10: 12.35/12.01, 100: 12.34/12.01, 300: 12.31/12.01, 1000: 12.26/12.00, 3000: 12.21/11.97, 10000: 12.31/11.95, 30000: 12.85/11.94, 100000: 13.85/11.93
BLEND weight w = out-of-season slope of (h - line) on (STATS - line) = 0.077 (se 0.055).

Benchmark in 2016-25 = CLOSING line (hardest, not bettable). Benchmark in 2026 = CFBD opening line.
dMSE_vs_mkt < 0 means better than the market; se is over game-week blocks. ATS columns: games where |model - line| >= threshold.

## 2016-2024, leave one season out
| sample       | model   |    n |    MAE |   RMSE |   dMSE_vs_mkt |   dMSE_se |   slope |   slope_se | ATS_t1                          | ATS_t2                         | ATS_t3                        |
|:-------------|:--------|-----:|-------:|-------:|--------------:|----------:|--------:|-----------:|:--------------------------------|:-------------------------------|:------------------------------|
| 2016-24 LOSO | line    | 4210 | 12.317 | 15.690 |         0.000 |     0.000 | nan     |    nan     | nan                             | nan                            | nan                           |
| 2016-24 LOSO | ELO     | 4210 | 12.957 | 16.333 |        20.570 |     4.309 |   0.015 |      0.048 | 0.496 (n=1984, -105.5u, gap>=3) | 0.483 (n=1057, -81.5u, gap>=5) | 0.464 (n=511, -58.5u, gap>=7) |
| 2016-24 LOSO | STATS   | 4210 | 12.787 | 16.250 |        17.890 |     4.735 |   0.077 |      0.055 | 0.501 (n=1953, -84.0u, gap>=3)  | 0.512 (n=1061, -24.4u, gap>=5) | 0.533 (n=516, +9.0u, gap>=7)  |
| 2016-24 LOSO | BLEND   | 4210 | 12.317 | 15.686 |        -0.124 |     0.195 |   1.000 |      0.724 | 0.525 (n=613, +1.7u, gap>=0.5)  | 0.525 (n=40, +0.1u, gap>=1)    | 1.000 (n=1, +0.9u, gap>=1.5)  |
| 2016-24 LOSO | RESID   | 4210 | 12.319 | 15.693 |         0.102 |     0.066 |  -3.228 |      1.625 | nan (n=0, +0.0u, gap>=0.5)      | nan (n=0, +0.0u, gap>=1)       | nan (n=0, +0.0u, gap>=1.5)    |

## STATS by season (out of season), slope vs the closing line
|   season |       n |   STATS_MAE |   line_MAE |   slope_vs_close |    se |
|---------:|--------:|------------:|-----------:|-----------------:|------:|
| 2016.000 | 500.000 |      13.472 |     13.365 |            0.363 | 0.178 |
| 2017.000 | 529.000 |      12.822 |     12.109 |           -0.234 | 0.186 |
| 2018.000 | 493.000 |      12.573 |     11.944 |           -0.098 | 0.079 |
| 2019.000 | 545.000 |      13.096 |     12.294 |           -0.061 | 0.106 |
| 2021.000 | 527.000 |      13.135 |     12.525 |           -0.020 | 0.118 |
| 2022.000 | 524.000 |      12.307 |     12.069 |            0.329 | 0.157 |
| 2023.000 | 534.000 |      12.720 |     12.363 |            0.060 | 0.114 |
| 2024.000 | 558.000 |      12.214 |     11.920 |            0.272 | 0.102 |

## 2025 held-out test (fit on 2016-2024)
| sample    | model   |   n |    MAE |   RMSE |   dMSE_vs_mkt |   dMSE_se |   slope |   slope_se | ATS_t1                        | ATS_t2                        | ATS_t3                      |
|:----------|:--------|----:|-------:|-------:|--------------:|----------:|--------:|-----------:|:------------------------------|:------------------------------|:----------------------------|
| 2025 test | line    | 567 | 11.748 | 14.852 |         0.000 |     0.000 | nan     |    nan     | nan                           | nan                           | nan                         |
| 2025 test | ELO     | 567 | 12.334 | 15.422 |        17.251 |     6.131 |   0.084 |      0.125 | 0.502 (n=275, -11.5u, gap>=3) | 0.510 (n=143, -3.6u, gap>=5)  | 0.567 (n=67, +5.5u, gap>=7) |
| 2025 test | STATS   | 567 | 12.293 | 15.455 |        18.269 |     6.415 |  -0.034 |      0.135 | 0.480 (n=229, -19.0u, gap>=3) | 0.480 (n=125, -10.5u, gap>=5) | 0.510 (n=49, -1.3u, gap>=7) |
| 2025 test | BLEND   | 567 | 11.757 | 14.859 |         0.185 |     0.403 |  -0.438 |      1.769 | 0.492 (n=63, -3.8u, gap>=0.5) | 0.750 (n=4, +1.7u, gap>=1)    | nan (n=0, +0.0u, gap>=1.5)  |
| 2025 test | RESID   | 567 | 11.746 | 14.850 |        -0.072 |     0.090 |  18.312 |     12.084 | nan (n=0, +0.0u, gap>=0.5)    | nan (n=0, +0.0u, gap>=1)      | nan (n=0, +0.0u, gap>=1.5)  |

## 2026 weeks 6-9 (fit on 2016-2025), graded vs the CFBD opener
| sample               | model      |   n |    MAE |   RMSE |   dMSE_vs_mkt |   dMSE_se |   slope |   slope_se | ATS_t1                        | ATS_t2                      | ATS_t3                      |
|:---------------------|:-----------|----:|-------:|-------:|--------------:|----------:|--------:|-----------:|:------------------------------|:----------------------------|:----------------------------|
| 2026 wk6-9 vs opener | open_line  | 228 | 11.577 | 14.283 |         0.000 |     0.000 | nan     |    nan     | nan                           | nan                         | nan                         |
| 2026 wk6-9 vs opener | board_line | 228 | 11.414 | 14.103 |        -5.107 |     2.547 |   1.492 |      0.397 | 0.609 (n=23, +3.7u, gap>=3)   | 1.000 (n=3, +2.7u, gap>=5)  | nan (n=0, +0.0u, gap>=7)    |
| 2026 wk6-9 vs opener | ALPHA      | 228 | 11.940 | 14.587 |         8.777 |     3.886 |   0.262 |      0.084 | 0.581 (n=93, +10.1u, gap>=3)  | 0.519 (n=52, -0.5u, gap>=5) | 0.667 (n=24, +6.5u, gap>=7) |
| 2026 wk6-9 vs opener | STATS      | 228 | 11.742 | 14.456 |         4.976 |     5.788 |   0.344 |      0.154 | 0.568 (n=95, +8.1u, gap>=3)   | 0.568 (n=44, +3.7u, gap>=5) | 0.500 (n=18, -0.8u, gap>=7) |
| 2026 wk6-9 vs opener | MIX        | 228 | 11.799 | 14.466 |         5.242 |     4.380 |   0.330 |      0.112 | 0.558 (n=86, +5.6u, gap>=3)   | 0.488 (n=41, -2.8u, gap>=5) | 0.619 (n=21, +3.8u, gap>=7) |
| 2026 wk6-9 vs opener | BLEND      | 228 | 11.548 | 14.257 |        -0.756 |     0.472 |   4.495 |      2.016 | 0.545 (n=22, +0.9u, gap>=0.5) | 1.000 (n=1, +0.9u, gap>=1)  | nan (n=0, +0.0u, gap>=1.5)  |
| 2026 wk6-9 vs opener | RESID      | 228 | 11.567 | 14.276 |        -0.197 |     0.099 |  13.627 |     16.037 | nan (n=0, +0.0u, gap>=0.5)    | nan (n=0, +0.0u, gap>=1)    | nan (n=0, +0.0u, gap>=1.5)  |

## 2026: did the line move from the opener toward the model by our Saturday board line?
| model   |   games |   moves |   toward_model |   avg_clv_pts |   slope_move_on_gap |   corr |   avg_clv_pts_gap4+ |   n_gap4+ |
|:--------|--------:|--------:|---------------:|--------------:|--------------------:|-------:|--------------------:|----------:|
| ALPHA   |     228 |     171 |          0.556 |         0.197 |               0.048 |  0.132 |               0.420 |    75.000 |
| STATS   |     228 |     171 |          0.596 |         0.294 |               0.086 |  0.216 |               0.651 |    63.000 |
| MIX     |     228 |     171 |          0.573 |         0.272 |               0.072 |  0.181 |               0.578 |    64.000 |
| RESID   |     228 |     171 |          0.520 |         0.105 |               2.771 |  0.094 |             nan     |   nan     |

Correlation of ALPHA and STATS gaps to the opener (2026): 0.819

## STATS top coefficients (standardized, pts per 1 sd)
|                                |   coef |
|:-------------------------------|-------:|
| elo                            |   2.5  |
| talent                         |   1.56 |
| adjusted_success               |   1.53 |
| adjusted_standard_down_success |   1.36 |
| adjusted_epa                   |   1.27 |
| adjusted_passing_epa           |   1.26 |
| adjusted_line_yards            |   1.02 |
| adjusted_rushing_epa           |   0.84 |
| adjusted_passing_down_success  |   0.77 |
| avg_start_offense              |  -0.63 |

## RESID top coefficients (pts of h - line per 1 sd)
|                                |   coef |
|:-------------------------------|-------:|
| adjusted_line_yards            |   0.03 |
| epa_away_off_vs_home_def       |   0.02 |
| adjusted_explosiveness         |  -0.02 |
| adjusted_passing_epa           |  -0.01 |
| adjusted_standard_down_success |   0.01 |
| adjusted_rushing_epa           |   0.01 |
| epa_home_off_vs_away_def       |   0.01 |
| adjusted_passing_down_success  |  -0.01 |
| adjusted_epa                   |  -0.01 |
| adjusted_success               |   0.01 |
