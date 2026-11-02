# CBB backtest — efficiency ratings vs the market

## Tuning (2022-25, by model MAE only)

| k_prior | carry | model MAE |
|---|---|---|
| 3 | 0.5 | 9.146 |
| 3 | 0.7 | 9.079 |
| 3 | 0.85 | 9.053 |
| 6 | 0.5 | 9.194 |
| 6 | 0.7 | 9.094 |
| 6 | 0.85 | 9.050 |
| 10 | 0.5 | 9.321 |
| 10 | 0.7 | 9.193 |
| 10 | 0.85 | 9.128 |
| 16 | 0.5 | 9.507 |
| 16 | 0.7 | 9.357 |
| 16 | 0.85 | 9.273 |

Chosen: k_prior=6, carry=0.85


## Tune seasons 2022–25: 21,910 games with a line

- MAE: model **9.05** vs market **8.79** (market better by 0.26)
- Information test (margin ~ market + model): market coef 0.89, **model coef 0.129 (t = 4.9)** -- model adds information beyond the line
- All games, side the model prefers: 10910-10863-137 | 50.1% ±0.3 | -944.8u  (break-even 52.4%)

| edge | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 0–1 | 3534-3482-48 | 50.4% ±0.6 | -269.3u |
| 1–2 | 2842-2847-40 | 50.0% ±0.7 | -263.4u |
| 2–3 | 1853-1991-16 | 48.2% ±0.8 | -306.5u |
| 3–4 | 1117-1055-11 | 51.4% ±1.1 | -39.5u |
| 4–6 | 935-970-9 | 49.1% ±1.1 | -120.0u |
| 6–+ | 629-518-13 | 54.8% ±1.5 | +53.8u |

**Splits** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Home pick | 2781-2805-32 | 49.8% ±0.7 | -276.8u |
| Away pick | 1753-1729-17 | 50.3% ±0.8 | -135.4u |
| Favorite pick | 1703-1764-18 | 49.1% ±0.8 | -215.8u |
| Underdog pick | 2785-2748-31 | 50.3% ±0.7 | -216.2u |
| Conference game | 2092-2261-20 | 48.1% ±0.8 | -359.2u |
| Non-conference | 2442-2273-29 | 51.8% ±0.7 | -53.0u |
| Early (a team has < 5 games) | 1373-1189-19 | 53.6% ±1.0 | +59.2u |
| Later | 3161-3345-30 | 48.6% ±0.6 | -471.4u |
| Neutral site | 645-578-8 | 52.7% ±1.4 | +8.4u |
| Postseason | 71-87-0 | 44.9% ±4.0 | -22.5u |

**By month** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Nov | 1538-1371-22 | 52.9% ±0.9 | +27.2u |
| Dec | 1005-1006-9 | 50.0% ±1.1 | -92.4u |
| Jan | 985-1051-11 | 48.4% ±1.1 | -155.5u |
| Feb | 656-712-4 | 48.0% ±1.4 | -115.6u |
| Mar | 346-383-3 | 47.5% ±1.9 | -68.5u |
| Apr | 4-11-0 | 26.7% ±12.9 | -7.4u |

**By season** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 2022 | 1236-1129-28 | 52.3% ±1.0 | -5.4u |
| 2023 | 1144-1143-21 | 50.0% ±1.0 | -103.0u |
| 2024 | 1096-1110-0 | 49.7% ±1.1 | -113.6u |
| 2025 | 1058-1152-0 | 47.9% ±1.1 | -190.2u |

## Holdout 2026 (never used for tuning): 5,748 games with a line

- MAE: model **9.24** vs market **9.01** (market better by 0.22)
- Information test (margin ~ market + model): market coef 0.85, **model coef 0.153 (t = 3.0)** -- model adds information beyond the line
- All games, side the model prefers: 2884-2843-21 | 50.4% ±0.7 | -221.2u  (break-even 52.4%)

| edge | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 0–1 | 997-969-6 | 50.7% ±1.1 | -62.6u |
| 1–2 | 745-775-4 | 49.0% ±1.3 | -97.7u |
| 2–3 | 508-450-6 | 53.0% ±1.6 | +11.8u |
| 3–4 | 249-288-2 | 46.4% ±2.2 | -61.6u |
| 4–6 | 231-225-3 | 50.7% ±2.3 | -15.0u |
| 6–+ | 154-136-0 | 53.1% ±2.9 | +4.0u |

**Splits** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Home pick | 640-643-5 | 49.9% ±1.4 | -61.2u |
| Away pick | 502-456-6 | 52.4% ±1.6 | +0.4u |
| Favorite pick | 417-433-4 | 49.1% ±1.7 | -53.9u |
| Underdog pick | 714-665-7 | 51.8% ±1.3 | -15.9u |
| Conference game | 540-516-6 | 51.1% ±1.5 | -25.1u |
| Non-conference | 602-583-5 | 50.8% ±1.5 | -35.7u |
| Early (a team has < 5 games) | 327-325-3 | 50.2% ±2.0 | -27.7u |
| Later | 815-774-8 | 51.3% ±1.3 | -33.1u |
| Neutral site | 165-105-1 | 61.1% ±3.0 | +45.0u |
| Postseason | 15-12-0 | 55.6% ±9.6 | +1.6u |

**By month** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| Nov | 407-380-4 | 51.7% ±1.8 | -10.0u |
| Dec | 227-254-1 | 47.2% ±2.3 | -47.6u |
| Jan | 272-231-2 | 54.1% ±2.2 | +16.3u |
| Feb | 159-150-4 | 51.5% ±2.8 | -5.5u |
| Mar | 75-84-0 | 47.2% ±4.0 | -15.8u |
| Apr | 2-0-0 | 100.0% ±35.4 | +1.8u |

**By season** (plays: |edge| ≥ 2.0)

| | record | ATS ± 1 s.e. | units |
|---|---|---|---|
| 2026 | 1142-1099-11 | 51.0% ±1.1 | -60.8u |

## Against opening lines (7,536 games, seasons [2025, 2026])

CLV = points the line moved toward the model’s side between open and close.

| edge vs open | games | avg CLV | beat close / moved against | ATS at open |
|---|---|---|---|---|
| ≥ 0 | 7,536 | +0.16 | 43% / 36% | 3806-3703 50.7% ±0.6 |
| ≥ 1 | 4,561 | +0.23 | 46% / 35% | 2302-2244 50.6% ±0.7 |
| ≥ 2 | 2,423 | +0.32 | 48% / 35% | 1225-1187 50.8% ±1.0 |
| ≥ 3 | 1,216 | +0.38 | 47% / 37% | 615-597 50.7% ±1.4 |
| ≥ 4 | 675 | +0.55 | 47% / 38% | 351-321 52.2% ±1.9 |
| ≥ 6 | 274 | +0.96 | 49% / 42% | 149-124 54.6% ±3.0 |
