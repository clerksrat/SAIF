"""Make a slim CSV of historical games (lines, results, pass-rate columns) for the weather backtest.
Run from saif_local:  python export_backtest.py    -> backtest_export.csv (attach it back to Claude).
Reads cfb_fullseason_data_2026/expanded_features.csv. Makes no API calls."""
import re
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
src = HERE / 'cfb_fullseason_data_2026' / 'expanded_features.csv'
if not src.exists():
    raise SystemExit(f'{src} not found - run saif_pull_all.py first.')
df = pd.read_csv(src, low_memory=False)
want = ['game_id', 'season', 'week', 'home_team', 'away_team', 'kickoff_utc', 'neutral_site',
        'home_classification', 'away_classification', 'conference_game',
        'market_spread', 'opening_spread', 'market_total', 'opening_total',
        'actual_margin', 'actual_total']
extra = [c for c in df.columns
         if re.search(r'(passingPlays\.rate|rushingPlays\.rate)$', c) and ('blended' in c or 'current' in c)
         and ('offense' in c)]
extra += [c for c in df.columns if c in ('diff_passingPlays_rate', 'diff_rushingPlays_rate', 'diff_ppa')]
cols = [c for c in dict.fromkeys(want + extra) if c in df.columns]
out = df[cols]
out.to_csv(HERE / 'backtest_export.csv', index=False)
print(f'Wrote backtest_export.csv: {len(out)} rows, {len(cols)} columns')
print('seasons:', sorted(out.season.dropna().unique().tolist()))
print('with market_total:', int(out.market_total.notna().sum()), ' with actual_total:', int(out.actual_total.notna().sum()))
print('columns:', cols)
