# CBB backtest — efficiency ratings vs the market


Parameters (picked by the 2022-25 MAE grid: k_prior 6, carry 0.85 was best of 12): k_prior=6, carry=0.85


## Tune seasons 2022–25: 21,910 games with a line

- MAE: model **9.21** vs market **8.79** (market better by 0.42)
- Information test (margin ~ market + model): market coef 0.95, **model coef 0.058 (t = 3.2)** -- model adds information beyond the line
- All games, side the model prefers: 10870-10903-137 | 49.9% ±0.3 | -1021.2u  (break-even 52.4%)

| edge | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 0–1 | 3471-3494-48 | 49.8% ±0.6 | -338.5u |
| 1–2 | 2839-2856-38 | 49.9% ±0.7 | -275.1u |
| 2–3 | 1790-1891-13 | 48.6% ±0.8 | -263.7u |
| 3–4 | 1098-1075-11 | 50.5% ±1.1 | -76.8u |
| 4–6 | 944-959-12 | 49.6% ±1.1 | -100.8u |
| 6–+ | 728-628-15 | 53.7% ±1.4 | +33.8u |

**Splits** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Home pick | 2655-2670-28 | 49.9% ±0.7 | -256.4u |
| Away pick | 1905-1883-23 | 50.3% ±0.8 | -151.2u |
| Favorite pick | 1676-1723-20 | 49.3% ±0.9 | -199.4u |
| Underdog pick | 2838-2809-31 | 50.3% ±0.7 | -229.0u |
| Conference game | 2133-2258-22 | 48.6% ±0.8 | -318.9u |
| Non-conference | 2427-2295-29 | 51.4% ±0.7 | -88.6u |
| Early (a team has < 5 games) | 1372-1191-18 | 53.5% ±1.0 | +56.3u |
| Later | 3188-3362-33 | 48.7% ±0.6 | -463.8u |
| Neutral site | 653-596-7 | 52.3% ±1.4 | -2.4u |
| Postseason | 69-92-1 | 42.9% ±3.9 | -29.3u |

**By month** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Nov | 1527-1382-22 | 52.5% ±0.9 | +6.2u |
| Dec | 997-1000-9 | 49.9% ±1.1 | -93.6u |
| Jan | 1006-1054-14 | 48.8% ±1.1 | -139.5u |
| Feb | 674-712-3 | 48.6% ±1.3 | -99.3u |
| Mar | 351-394-3 | 47.1% ±1.8 | -74.9u |
| Apr | 5-11-0 | 31.2% ±12.5 | -6.5u |

**By season** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 2022 | 1237-1133-28 | 52.2% ±1.0 | -8.5u |
| 2023 | 1151-1145-23 | 50.1% ±1.0 | -98.6u |
| 2024 | 1109-1119-0 | 49.8% ±1.1 | -110.8u |
| 2025 | 1063-1156-0 | 47.9% ±1.1 | -189.6u |

## Holdout 2026 (never used for tuning): 5,748 games with a line

- MAE: model **9.24** vs market **9.01** (market better by 0.22)
- Information test (margin ~ market + model): market coef 0.85, **model coef 0.152 (t = 3.0)** -- model adds information beyond the line
- All games, side the model prefers: 2889-2838-21 | 50.4% ±0.7 | -211.6u  (break-even 52.4%)

| edge | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 0–1 | 1009-971-6 | 51.0% ±1.1 | -53.7u |
| 1–2 | 742-761-4 | 49.4% ±1.3 | -86.5u |
| 2–3 | 507-463-6 | 52.3% ±1.6 | -2.1u |
| 3–4 | 245-283-2 | 46.4% ±2.2 | -60.3u |
| 4–6 | 232-223-3 | 51.0% ±2.3 | -12.1u |
| 6–+ | 154-137-0 | 52.9% ±2.9 | +3.0u |

**Splits** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Home pick | 635-648-5 | 49.5% ±1.4 | -70.7u |
| Away pick | 503-458-6 | 52.3% ±1.6 | -0.7u |
| Favorite pick | 414-439-4 | 48.5% ±1.7 | -62.6u |
| Underdog pick | 713-666-7 | 51.7% ±1.3 | -17.8u |
| Conference game | 536-520-6 | 50.8% ±1.5 | -32.7u |
| Non-conference | 602-586-5 | 50.7% ±1.5 | -38.7u |
| Early (a team has < 5 games) | 325-324-3 | 50.1% ±2.0 | -28.5u |
| Later | 813-782-8 | 51.0% ±1.3 | -42.9u |
| Neutral site | 165-106-1 | 60.9% ±3.0 | +44.0u |
| Postseason | 15-12-0 | 55.6% ±9.6 | +1.6u |

**By month** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Nov | 408-380-4 | 51.8% ±1.8 | -9.1u |
| Dec | 226-257-1 | 46.8% ±2.3 | -51.5u |
| Jan | 270-234-2 | 53.6% ±2.2 | +11.5u |
| Feb | 157-151-4 | 51.0% ±2.8 | -8.3u |
| Mar | 75-84-0 | 47.2% ±4.0 | -15.8u |
| Apr | 2-0-0 | 100.0% ±35.4 | +1.8u |

**By season** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 2026 | 1138-1106-11 | 50.7% ±1.1 | -71.5u |

## Against opening lines (7,536 games, seasons [np.int64(2025), np.int64(2026)])

CLV = points the line moved toward the model’s side between open and close.

| edge vs open | games | avg CLV | beat close / moved against | ATS at open |
|---|---|---|---|---|
| ≥ 0 | 7,536 | +0.17 | 43% / 36% | 3812-3697 50.8% ±0.6 |
| ≥ 1 | 4,557 | +0.24 | 46% / 35% | 2298-2243 50.6% ±0.7 |
| ≥ 2 | 2,418 | +0.32 | 48% / 35% | 1213-1195 50.4% ±1.0 |
| ≥ 3 | 1,213 | +0.39 | 47% / 37% | 616-593 51.0% ±1.4 |
| ≥ 4 | 665 | +0.56 | 48% / 38% | 345-317 52.1% ±1.9 |
| ≥ 6 | 284 | +0.91 | 48% / 42% | 156-127 55.1% ±3.0 |
