"""Review condition 1(a): are CBBD's stored DraftKings / Bovada numbers the books' real prices?

Free -- uses only files already on the Pi:
  * cbb_data/odds/*.json      timestamped per-book Odds API feeds saved by the morning run (since 2026-11-02)
  * cbb/state/closing_lines.csv  our own pre-tip snapshots (DK / Bovada columns), once they exist
  * cbb/data/lines_2027.csv.gz   CBBD's stored lines for the same games

    python3 cbb/audit_lines.py --push     # -> cbb/line_audit.txt

Checks, per book:
  1. Whole-number share of spreads in each source. Books post whole numbers often; if the Odds API
     DraftKings feed has them and CBBD's DraftKings copy never does, CBBD is altering the number.
  2. Same game, same book: CBBD spreadOpen and CBBD spread vs the Odds API morning number.
     Pattern of differences (exactly 0, +/-0.5, other). The morning quote is not the same moment as
     CBBD's open or close, so a few-point spread of differences is normal; a systematic half point is not.
  3. When our own pre-tip snapshot exists: CBBD close vs our timestamped close, same book.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from odds_match import Matcher  # noqa: E402
from ratings import read  # noqa: E402

BOOKS = {'draftkings': 'Draft Kings', 'bovada': 'Bovada', 'espnbet': 'ESPN BET'}
OUT = HERE / 'line_audit.txt'
LOG = []


def say(s=''):
    print(s, flush=True)
    LOG.append(s)


def odds_api_rows():
    rows = []
    for f in sorted((ROOT / 'cbb_data' / 'odds').glob('*.json')):
        if f.name == 'credits.json':
            continue
        for g in json.loads(f.read_text()):
            for bk in g.get('bookmakers', []):
                for mk in bk.get('markets', []):
                    if mk.get('key') != 'spreads':
                        continue
                    for o in mk.get('outcomes', []):
                        if o.get('name') == g['home_team'] and o.get('point') is not None:
                            rows.append({'file': f.stem, 'commence_time': g['commence_time'], 'home_team': g['home_team'],
                                         'away_team': g['away_team'], 'book': bk['key'], 'spread': float(o['point'])})
    return pd.DataFrame(rows)


def whole(s):
    s = s.dropna()
    return f'{(s % 1 == 0).mean() * 100:5.1f}% of {len(s):5d}' if len(s) else '   n/a'


def diff_pattern(d):
    d = d.dropna()
    if not len(d):
        return 'n/a'
    return (f'n={len(d)} | exact {(d == 0).mean()*100:.0f}% | +0.5 {(d == 0.5).mean()*100:.0f}% | '
            f'-0.5 {(d == -0.5).mean()*100:.0f}% | other {(~d.isin([0, 0.5, -0.5])).mean()*100:.0f}% | '
            f'mean {d.mean():+.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true')
    a = ap.parse_args()
    oa = odds_api_rows()
    cb = read('lines', {2027})
    games = read('games', {2027})
    say('Line audit -- CBBD stored lines vs timestamped Odds API quotes (2027 season)')
    if oa.empty:
        say('No saved Odds API feeds found in cbb_data/odds/ -- nothing to compare.')
    else:
        say(f'Odds API: {oa.file.nunique()} morning feeds, {len(oa)} book-game spreads')
        say('\n1. Whole-number share of home spreads')
        for key, prov in BOOKS.items():
            c = cb[cb.provider == prov]
            say(f'   {prov:12s} Odds API {whole(oa[oa.book == key].spread)} | CBBD close {whole(c.spread)} '
                f'| CBBD open {whole(c.spreadOpen)}')
        say(f'   all Odds API books: {whole(oa.spread)}')

        teams = sorted(set(games.homeTeam) | set(games.awayTeam))
        m = Matcher(teams)
        oa['home'] = oa.home_team.map(m.team)
        oa['away'] = oa.away_team.map(m.team)
        oa['tip'] = pd.to_datetime(oa.commence_time, utc=True, format='ISO8601')
        oa = oa.dropna(subset=['home', 'away']).sort_values('file').drop_duplicates(['home', 'away', 'book'], keep='first')
        gk = games[['id', 'homeTeam', 'awayTeam', 'startDate']].copy()
        gk['tip'] = pd.to_datetime(gk.startDate, utc=True, format='ISO8601')
        fwd = oa.merge(gk, left_on=['home', 'away'], right_on=['homeTeam', 'awayTeam'])
        rev = oa.merge(gk, left_on=['home', 'away'], right_on=['awayTeam', 'homeTeam'])
        rev['spread'] = -rev.spread
        j = pd.concat([fwd, rev])
        j = j[(j.tip_x - j.tip_y).abs() <= pd.Timedelta(hours=6)]
        say('\n2. Same game, same book: CBBD minus Odds API morning quote (home spread)')
        for key, prov in BOOKS.items():
            x = j[j.book == key].merge(cb[cb.provider == prov][['game_id', 'spread', 'spreadOpen']],
                                       left_on='id', right_on='game_id', suffixes=('_oa', '_cb'))
            if x.empty:
                continue
            say(f'   {prov:12s} CBBD open  - morning: {diff_pattern(x.spreadOpen - x.spread_oa)}')
            say(f'   {prov:12s} CBBD close - morning: {diff_pattern(x.spread_cb - x.spread_oa)}')
            w = x[x.spread_oa % 1 == 0]
            if len(w):
                say(f'   {prov:12s}   when the Odds API number is whole: CBBD open {whole(w.spreadOpen)} whole; '
                    f'CBBD open - morning: {diff_pattern(w.spreadOpen - w.spread_oa)}')

    snap = HERE / 'state' / 'closing_lines.csv'
    say('\n3. CBBD close vs our timestamped pre-tip close (same book)')
    if not snap.exists():
        say('   no snapshots yet (snapshot_cbb_close.py starts with the new cron)')
    else:
        c = pd.read_csv(snap)
        c['tip'] = pd.to_datetime(c.commence_time, utc=True, format='ISO8601')
        c['snap'] = pd.to_datetime(c.snapshot_utc, utc=True, format='ISO8601')
        c = c[c.snap < c.tip].sort_values('snap').drop_duplicates('odds_api_id', keep='last')
        teams = sorted(set(games.homeTeam) | set(games.awayTeam))
        m = Matcher(teams)
        c['home'], c['away'] = c.home_team.map(m.team), c.away_team.map(m.team)
        c = c.merge(games[['id', 'homeTeam', 'awayTeam']], left_on=['home', 'away'], right_on=['homeTeam', 'awayTeam'])
        for col, prov in (('dk_spread_home', 'Draft Kings'), ('bov_spread_home', 'Bovada')):
            x = c.merge(cb[cb.provider == prov][['game_id', 'spread']], left_on='id', right_on='game_id')
            say(f'   {prov:12s} our close whole {whole(x[col])} | CBBD close - our close: {diff_pattern(x.spread - x[col])}')
    OUT.write_text('\n'.join(LOG) + '\n')
    print(f'Saved {OUT}')
    if a.push:
        subprocess.run(['git', 'add', str(OUT)], cwd=ROOT, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'CBB line audit'], cwd=ROOT, check=False)
        subprocess.run([str(ROOT / 'publish.sh')], cwd=ROOT, check=True)
        print('Pushed cbb/line_audit.txt')


if __name__ == '__main__':
    main()
