"""Review condition 4: are games WITH a usable opener different from games without one?

    python3 cbb/selection_check.py      # -> cbb/selection_check.txt (local data only, no API calls)

For 2025 and 2026 D1-vs-D1 finals: share with an opener (any book) and with any line at all,
by month, conference tier, closing-spread size, conference vs non-conference, and book.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import read

HERE = Path(__file__).resolve().parent
HIGH = {'ACC', 'Big 12', 'Big East', 'Big Ten', 'SEC', 'Pac-12'}
LOG = []


def say(s=''):
    print(s, flush=True)
    LOG.append(s)


def main():
    seasons = {2025, 2026}
    g = read('games', seasons)
    g = g[(g.status == 'final') & g.homeConference.notna() & g.awayConference.notna()].copy()
    l = read('lines', seasons)
    by = l.groupby('game_id').agg(close=('spread', 'median'), opener=('spreadOpen', 'median'),
                                  books=('provider', lambda s: ','.join(sorted(set(s)))))
    g = g.merge(by, left_on='id', right_index=True, how='left')
    g['has_line'] = g.close.notna()
    g['has_open'] = g.opener.notna()
    g['month'] = g.startDate.str[:7]
    hi = g.homeConference.isin(HIGH).astype(int) + g.awayConference.isin(HIGH).astype(int)
    g['tier'] = np.select([hi == 2, hi == 1], ['high v high', 'high v other'], 'other v other')
    g['spread_size'] = pd.cut(g.close.abs(), [-0.1, 5, 10, 20, 99], labels=['0-5', '5-10', '10-20', '20+'])
    g['conf'] = np.where(g.conferenceGame.fillna(False).astype(bool), 'conference', 'non-conference')
    say('Opener selection check -- D1-vs-D1 finals')
    for s, x in g.groupby('season'):
        say(f'\n=== {s}: {len(x)} games | any line {x.has_line.mean():.0%} | opener {x.has_open.mean():.0%} ===')
        for col in ('month', 'tier', 'spread_size', 'conf'):
            t = x.groupby(col, observed=True).agg(games=('id', 'size'), line=('has_line', 'mean'), opener=('has_open', 'mean'))
            say(f'  by {col}:')
            for k, r in t.iterrows():
                say(f'    {str(k):16s} {int(r.games):5d} games | line {r.line:5.0%} | opener {r.opener:5.0%}')
        w = x[x.has_line]
        say(f'  books on games with a line: {w.books.value_counts().head(6).to_dict()}')
        o, n = x[x.has_open], x[x.has_line & ~x.has_open]
        if len(o) and len(n):
            say(f'  with opener vs line-but-no-opener: |close spread| {o.close.abs().mean():.1f} vs {n.close.abs().mean():.1f}; '
                f'conference games {(o.conf == "conference").mean():.0%} vs {(n.conf == "conference").mean():.0%}; '
                f'high-major involved {(o.tier != "other v other").mean():.0%} vs {(n.tier != "other v other").mean():.0%}')
    (HERE / 'selection_check.txt').write_text('\n'.join(LOG) + '\n')


if __name__ == '__main__':
    main()
