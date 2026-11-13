"""Phase 0 data backfill (approved 2026-11-06). Read-only for the live model / board / grading.

Run on the Pi from the repo folder:
    . .venv/bin/activate && python3 cbb/backfill_extra.py --push

  1. Team box + games + lines for 2014-2020 via backfill_cbbd.py (games/lines already cached
     by probe v2, so mostly team-box calls)                                     ~90 calls
  2. Player box scores, 2014-2027, 10-day windows (split if near the 3,000 cap) ~250 calls
     -> cbb/data/players_<season>.csv.gz (one row per player per game, slim columns)
  3. Recruiting classes 2013-2026 (class year Y enrolls for season Y+1)          14 calls
     -> cbb/data/recruits.csv.gz
  4. Weekly polls 2014-2027                                                      14 calls
     -> cbb/data/rankings.csv.gz
Total ~370 of the shared CFBD/CBBD quota. Everything is cached in cbb_data/raw/, so a rerun
after an interruption only pulls what's missing. Rosters are deliberately NOT pulled
(not point-in-time safe historically -- review condition 2).
"""
import argparse
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import backfill_cbbd as B  # noqa: E402  (shared cache, retries, cap splitting)

DATA = HERE / 'data'
PLAYER_WINDOW_DAYS = 10


def say(s):
    print(s, flush=True)


def player_rows(team_game):
    keep = {k: team_game.get(k) for k in ('season', 'gameId', 'startDate', 'seasonType', 'teamId', 'team',
                                          'conference', 'isHome', 'opponentId', 'opponent', 'neutralSite', 'gameMinutes')}
    out = []
    for p in team_game.get('players') or []:
        fg, f3, ft, rb = (p.get(k) or {} for k in ('fieldGoals', 'threePointFieldGoals', 'freeThrows', 'rebounds'))
        out.append({**keep, 'athleteId': p.get('athleteId'), 'name': p.get('name'), 'position': p.get('position'),
                    'starter': p.get('starter'), 'minutes': p.get('minutes'), 'points': p.get('points'),
                    'usage': p.get('usage'), 'ortg': p.get('offensiveRating'), 'drtg': p.get('defensiveRating'),
                    'fgm': fg.get('made'), 'fga': fg.get('attempted'), 'tpm': f3.get('made'), 'tpa': f3.get('attempted'),
                    'ftm': ft.get('made'), 'fta': ft.get('attempted'), 'oreb': rb.get('offensive'),
                    'dreb': rb.get('defensive'), 'ast': p.get('assists'), 'tov': p.get('turnovers'),
                    'stl': p.get('steals'), 'blk': p.get('blocks'), 'pf': p.get('fouls')})
    return out


def player_season(season, today):
    start, last = date(season - 1, 11, 1), min(date(season, 4, 15), today + timedelta(days=1))
    rows = []
    while start < last:
        end = min(start + timedelta(days=PLAYER_WINDOW_DAYS), last)
        for tg in B.pull_window('/games/players', season, start, end):
            rows += player_rows(tg)
        start = end
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(['gameId', 'teamId', 'athleteId'])
        df.to_csv(DATA / f'players_{season}.csv.gz', index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--skip-teambox', action='store_true')
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    log = [f'CBB phase-0 backfill {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}']

    if not a.skip_teambox:
        say('[1/4] team box 2014-2020 ...')
        r = subprocess.run([sys.executable, str(HERE / 'backfill_cbbd.py'), '--seasons',
                            '2014,2015,2016,2017,2018,2019,2020', '--quiet'], cwd=ROOT, capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if l[:4].isdigit() or l.startswith(('TOTAL', 'API'))]
        say('\n'.join(lines))
        log += lines
        if r.returncode:
            say(r.stderr[-800:])
            raise SystemExit('team box backfill failed -- rerun to resume (cached calls are free)')

    say('[2/4] player box scores 2014-2027 ...')
    for s in range(2014, 2028):
        df = player_season(s, today)
        msg = (f'  players {s}: {len(df):6d} player-games, {df.gameId.nunique() if len(df) else 0} games, '
               f'{df.athleteId.nunique() if len(df) else 0} players | calls so far {B.STATE["calls"]}')
        say(msg)
        log.append(msg)

    say('[3/4] recruiting classes 2013-2026 ...')
    rec = []
    for y in range(2013, 2027):
        for r_ in B.get('/recruiting/players', {'year': y}, datetime(y + 1, 1, 1, tzinfo=timezone.utc)) or []:
            ct = r_.get('committedTo') or {}
            rec.append({'year': r_.get('year', y), 'athleteId': r_.get('athleteId'), 'name': r_.get('name'),
                        'position': r_.get('position'), 'ranking': r_.get('ranking'), 'rating': r_.get('rating'),
                        'stars': r_.get('stars'), 'heightInches': r_.get('heightInches'),
                        'committedTo': ct.get('name'), 'committedToId': ct.get('id'), 'conference': ct.get('conference')})
    rec = pd.DataFrame(rec)
    rec.to_csv(DATA / 'recruits.csv.gz', index=False)
    msg = f'  recruits: {len(rec)} across {rec.year.nunique() if len(rec) else 0} classes, ' \
          f'{rec.athleteId.notna().mean() if len(rec) else 0:.0%} linked to an athleteId'
    say(msg)
    log.append(msg)

    say('[4/4] weekly polls 2014-2027 ...')
    rk = []
    for s in range(2014, 2028):
        end = datetime(s, 4, 30, tzinfo=timezone.utc) if s < 2027 else datetime.now(timezone.utc)
        rk += B.get('/rankings', {'season': s}, end) or []
    rk = pd.DataFrame(rk)
    rk.to_csv(DATA / 'rankings.csv.gz', index=False)
    msg = f'  rankings: {len(rk)} rows, poll types {sorted(rk.pollType.dropna().unique()) if len(rk) else []}'
    say(msg)
    log.append(msg)

    msg = f'API calls this run: {B.STATE["calls"]} (cache hits {B.STATE["cached"]}) | quota remaining {B.STATE["quota"]}'
    say(msg)
    log.append(msg)
    (HERE / 'backfill_extra_report.txt').write_text('\n'.join(log) + '\n')
    if a.push:
        subprocess.run(['git', 'add', str(DATA), str(HERE / 'backfill_extra_report.txt')], cwd=ROOT, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'CBB phase-0 backfill data'], cwd=ROOT, check=False)
        subprocess.run([str(ROOT / 'publish.sh')], cwd=ROOT, check=True)
        print('Pushed cbb/data and cbb/backfill_extra_report.txt')


if __name__ == '__main__':
    main()
