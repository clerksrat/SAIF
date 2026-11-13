# CBB frozen v1 shadow test — week-1 review

Freeze: commit cdacf27, cbb/models/frozen_v1.json. Pre-specified rules only (side edge >= 3, total edge >= 4; A0/A1/C1 as logged). One week of data: this checks logging and market movement; it is not a profitability test.

## 1. Quote availability, timing and matching

Shadow games logged: 213 (2026-11-07 to 2026-11-11); finals available for 167 (CBBD data in the repo runs through 2026-11-10).

| book | morning spread | morning total | morning before tip | pre-tip spread | pre-tip total | pre-tip before tip |
|---|---|---|---|---|---|---|
| FanDuel | 205 | 205 | 100% | 161 | 161 | 98% |
| DraftKings | 204 | 204 | 100% | 161 | 161 | 98% |
| BetRivers | 205 | 205 | 100% | 161 | 161 | 98% |

- Morning quote taken 8.8 h before tip on median (range 1.2 to 13.7 h).
- Pre-tip snapshot exists for 161 of 213 games; taken 30 min before tip on median (range -0 to 90). Games without one: no snapshot in the window (rule: max one call per 45 min).
- Reversed listings (feed home/away opposite to ours) among pre-tip matches: 5; signs flipped to our home team.
- Matching check vs CBBD stored close: DraftKings morning spread has the opposite sign on 0 of 173 games with |spread| >= 3; differs by more than 6 points on 0 of 204.
- Odds sanity: 2456 prices logged, range -175 to 140; 0 invalid values between -100 and +100.

## 2. Market movement, morning quote -> our pre-tip quote

Positive = the line moved toward the model after we logged it (our morning number was better than pre-tip).

**Sides** (candidates: edge >= 3 vs the book's morning line)

| model | book | candidates | with pre-tip | toward / against / unchanged | mean move, pts (95% CIs) |
|---|---|---|---|---|---|
| A0 | FanDuel | 117 | 88 | 23% / 15% / 62% | +0.12 (date-clustered +0.05 to +0.22; team-clustered -0.06 to +0.31) |
| A0 | DraftKings | 120 | 92 | 33% / 17% / 50% | +0.24 (date-clustered +0.07 to +0.42; team-clustered +0.02 to +0.45) |
| A0 | BetRivers | 112 | 83 | 28% / 16% / 57% | +0.14 (date-clustered -0.05 to +0.34; team-clustered -0.05 to +0.34) |
| A0 | best of three | 124 | 94 | 34% / 7% / 59% | +0.38 (date-clustered +0.29 to +0.52; team-clustered +0.20 to +0.58) |
| A1 | FanDuel | 112 | 84 | 24% / 17% / 60% | +0.12 (date-clustered +0.01 to +0.22; team-clustered -0.06 to +0.31) |
| A1 | DraftKings | 114 | 86 | 33% / 19% / 49% | +0.21 (date-clustered +0.05 to +0.38; team-clustered +0.01 to +0.44) |
| A1 | BetRivers | 107 | 79 | 28% / 16% / 56% | +0.14 (date-clustered -0.03 to +0.31; team-clustered -0.06 to +0.35) |
| A1 | best of three | 122 | 92 | 35% / 9% / 57% | +0.38 (date-clustered +0.28 to +0.48; team-clustered +0.20 to +0.57) |
| C1 | FanDuel | 22 | 17 | 29% / 6% / 65% | +0.41 (date-clustered -0.20 to +0.73; team-clustered +0.00 to +0.88) |
| C1 | DraftKings | 24 | 19 | 47% / 0% / 53% | +0.68 (date-clustered +0.29 to +1.14; team-clustered +0.37 to +1.11) |
| C1 | BetRivers | 20 | 14 | 29% / 7% / 64% | +0.29 (date-clustered +0.00 to +0.60; team-clustered -0.07 to +0.64) |
| C1 | best of three | 26 | 20 | 45% / 0% / 55% | +0.65 (date-clustered +0.28 to +1.00; team-clustered +0.30 to +1.05) |

**Totals** (candidates: edge >= 4 vs the book's morning line)

| model | book | candidates | with pre-tip | toward / against / unchanged | mean move, pts (95% CIs) |
|---|---|---|---|---|---|
| A0 | FanDuel | 63 | 47 | 36% / 32% / 32% | +0.17 (date-clustered +0.03 to +0.57; team-clustered -0.16 to +0.48) |
| A0 | DraftKings | 66 | 51 | 33% / 24% / 43% | +0.22 (date-clustered -0.04 to +0.43; team-clustered -0.08 to +0.54) |
| A0 | BetRivers | 67 | 51 | 39% / 29% / 31% | +0.27 (date-clustered +0.06 to +0.58; team-clustered -0.12 to +0.67) |
| A0 | best of three | 72 | 55 | 45% / 20% / 35% | +0.62 (date-clustered +0.37 to +0.82; team-clustered +0.28 to +0.96) |
| A1 | FanDuel | 61 | 46 | 39% / 28% / 33% | +0.20 (date-clustered -0.05 to +0.52; team-clustered -0.11 to +0.49) |
| A1 | DraftKings | 59 | 45 | 33% / 20% / 47% | +0.24 (date-clustered -0.09 to +0.40; team-clustered -0.02 to +0.52) |
| A1 | BetRivers | 64 | 48 | 40% / 27% / 33% | +0.27 (date-clustered +0.00 to +0.40; team-clustered -0.15 to +0.66) |
| A1 | best of three | 69 | 52 | 42% / 19% / 38% | +0.48 (date-clustered +0.12 to +0.64; team-clustered +0.19 to +0.80) |
| C1 | FanDuel | 18 | 11 | 64% / 9% / 27% | +0.55 (date-clustered +0.33 to +1.00; team-clustered +0.09 to +0.91) |
| C1 | DraftKings | 15 | 10 | 40% / 10% / 50% | +0.30 (date-clustered +0.00 to +1.00; team-clustered -0.10 to +0.70) |
| C1 | BetRivers | 20 | 13 | 54% / 0% / 46% | +0.92 (date-clustered +0.50 to +2.00; team-clustered +0.38 to +1.54) |
| C1 | best of three | 21 | 14 | 64% / 7% / 29% | +0.86 (date-clustered +0.50 to +1.50; team-clustered +0.36 to +1.43) |

**All games (not just candidates):** slope of (pre-tip − morning) on (model − morning), DraftKings lines

| market | model | games | slope | date-clustered 95% CI |
|---|---|---|---|---|
| sides | A0 | 161 | +0.039 | +0.002 to +0.078 |
| sides | A1 | 161 | +0.039 | +0.003 to +0.073 |
| sides | C1 | 161 | +0.116 | +0.059 to +0.201 |
| totals | A0 | 161 | +0.029 | -0.003 to +0.065 |
| totals | A1 | 161 | +0.025 | -0.009 to +0.061 |
| totals | C1 | 161 | -0.005 | -0.149 to +0.095 |

## 3. Results at the logged book prices — ONE WEEK, NOT A PROFITABILITY TEST

Graded at the actual morning number and American odds. Pushes return the stake.

| market | model | prices | bets graded | record | units (1u stakes) | ROI (date-clustered 95% CI) |
|---|---|---|---|---|---|---|
| sides | A0 | best of three | 94 | 41-53-0 | -15.7u | -16.7% (-35.3% to +8.0%) |
| sides | A0 | DraftKings only | 92 | 41-51-0 | -13.9u | -15.1% (-33.3% to +9.1%) |
| sides | A1 | best of three | 92 | 39-53-0 | -17.6u | -19.2% (-37.7% to +8.8%) |
| sides | A1 | DraftKings only | 86 | 39-47-0 | -11.8u | -13.8% (-35.0% to +11.3%) |
| sides | C1 | best of three | 20 | 7-13-0 | -6.7u | -33.7% (-84.4% to +19.0%) |
| sides | C1 | DraftKings only | 19 | 7-12-0 | -5.8u | -30.3% (-84.5% to +36.0%) |
| totals | A0 | best of three | 55 | 28-27-0 | -2.0u | -3.6% (-29.4% to +13.1%) |
| totals | A0 | DraftKings only | 51 | 25-26-0 | -3.3u | -6.5% (-27.4% to +7.7%) |
| totals | A1 | best of three | 52 | 27-25-0 | -0.9u | -1.7% (-27.2% to +17.9%) |
| totals | A1 | DraftKings only | 45 | 22-23-0 | -3.1u | -6.8% (-23.2% to +10.2%) |
| totals | C1 | best of three | 14 | 7-7-0 | -0.8u | -5.8% (-100.0% to +41.6%) |
| totals | C1 | DraftKings only | 10 | 5-5-0 | -0.5u | -4.5% (-100.0% to +59.2%) |

## 4. CBBD opener — untimed reference only (never priced)

Movement from CBBD's stored opener to our timestamped pre-tip consensus, on the model's side vs the opener.

| market | model | games | toward / against | mean move, pts |
|---|---|---|---|---|
| sides | A0 | 83 | 40% / 47% | -0.14 |
| sides | A1 | 81 | 40% / 47% | -0.14 |
| totals | A0 | 36 | 42% / 53% | -0.58 |
| totals | A1 | 32 | 47% / 44% | -0.28 |

## 5. Reading the numbers (uncertainty clustered by date and by home team throughout)

- **Logging works.** Morning quotes at all three books for 96-100% of logged games, every one taken before tip (median 8.8 h before). Pre-tip snapshots for 161 of 213 games (median 30 min before tip); the rest fell between snapshot calls (max one per 45 min). Matching is clean: 0 sign mismatches vs CBBD's stored close on 173 games with |spread| >= 3, 0 lines more than 6 points off, 0 invalid odds; 5 reversed listings flipped correctly.
- **Per-book movement is the honest read.** After our morning quote, lines moved toward the A0/A1 side on candidates by +0.12 to +0.24 pts (sides) and +0.17 to +0.27 pts (totals), mostly "unchanged" (50-62% of sides). Sides at FanDuel and DraftKings have date-clustered CIs above zero; team-clustered CIs are borderline. Totals CIs mostly include zero. On all games the slope of later movement on the model gap is about +0.03 to +0.04 (development opener-to-close: 0.10-0.15), consistent with less movement left after the morning.
- **Best-of-three movement is inflated by selection** and should not be read as model signal: picking the best of three morning numbers favors the book that is off-market, and that book tends to move back toward the others by tip whatever the model says. Its +0.38 to +0.62 is mostly that artifact.
- **C1** shows the largest per-book moves, but on 10-24 candidates; not interpretable after one week.
- **CBBD opener (untimed):** this week the line moved from the CBBD opener to our pre-tip consensus *against* the model's side on average (sides -0.14, totals -0.58 pts). The opposite of the development pattern, on 32-83 games.
- **Results:** sides -14% to -19% ROI at actual prices, totals -2% to -7%, every CI spanning zero widely. One week; not evidence either way on profitability.

## 6. Data, credits, operations

- Finals in the repo run through Nov 10, so results cover Nov 7-10 games (graded subsets above). The Pi has not pushed since Nov 11 10:15 ET (no football or basketball commits on Nov 12-13); its Nov 11 snapshots and later data are not in the repo. Needs a check on the Pi.
- Odds API, basketball: 46 pre-tip snapshot calls Nov 6-11 (about 92 credits) + 6 morning pulls (12 credits), about 104 credits in six days, plus football. The credit balance and any floor pause are only visible on the Pi (cbb_data/odds/credits.json, logs/cbb_close.log).

## 7. Recommendation on the $30 Odds API plan (timestamped opener / overnight windows)

Pre-specified question: does morning -> pre-tip movement follow the model? **Weakly, for sides only.** Per-book movement toward the model is positive but small (+0.1 to +0.25 pts, with most lines unchanged), the all-games slope is about +0.04, and totals are not clearly positive. The untimed CBBD opener moved *against* the model this week. That is not enough evidence that earlier quotes would add value to justify the spend now. **Recommendation: do not buy yet; keep logging on the free plan through the next review, fix the Pi gap first, and re-decide with more data.**
