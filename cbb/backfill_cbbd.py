"""CBB step 2: backfill CollegeBasketballData history into three compact tables.

Run on the Pi from the repo folder:
    . .venv/bin/activate && python3 cbb/backfill_cbbd.py --push

What the probe showed and how this handles it:
  * Every CBBD call returns at most 3000 rows, so a full-season pull silently drops games.
    This pulls in 28-day date windows and splits any window that comes back near the cap.
  * Season N = the (N-1)-N season (2027 = this season, started Nov 2026).
  * Scheduled games can carry points, so "played" is decided by status, never by points.
Seasons 2021-2027 (2021 only so 2022 has a prior season). About 25 calls per finished
season, ~180 total the first time, out of the CFBD/CBBD shared quota (~4,950 left).
Finished windows are cached in cbb_data/raw/ and never pulled again; windows that reach
into the last 3 days are refetched, so rerunning later just tops up the current season.

Writes cbb/data/games_<season>.csv.gz, lines_<season>.csv.gz, team_box_<season>.csv.gz (committed with --push so the
backtest can run anywhere) and cbb/backfill_report.txt.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from saif_pull_all import load_env_file  # noqa: E402,F401  (reads .env on import)

BASE = 'https://api.collegebasketballdata.com'
RAW = ROOT / 'cbb_data' / 'raw'
OUT = HERE / 'data'
REPORT = HERE / 'backfill_report.txt'
CAP = 3000
SPLIT_AT = 2700          # treat a response this big as possibly truncated -> halve the window
WINDOW_DAYS = 28
REFRESH_DAYS = 3         # windows ending within this many days of a cached pull get refetched
STATE = {'calls': 0, 'cached': 0, 'quota': None}
LOG = []


def say(s=''):
    print(s, flush=True)
    LOG.append(s)


def get(endpoint, params, window_end):
    ident = {'endpoint': endpoint, 'params': params}
    f = RAW / (hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest() + '.json')
    if f.exists():
        saved = json.loads(f.read_text())
        got = datetime.fromisoformat(saved['retrieved_at_utc'])
        if got >= window_end + timedelta(days=REFRESH_DAYS):   # pulled well after the window closed
            STATE['cached'] += 1
            return saved['data']
    key = (os.environ.get('CBBD_API_KEY') or os.environ.get('CFBD_API_KEY') or '').strip()
    if not key:
        raise SystemExit('No CFBD_API_KEY in .env')
    url = BASE + endpoint + '?' + urlencode(params)
    for attempt in range(6):
        try:
            STATE['calls'] += 1
            with urlopen(Request(url, headers={'Authorization': 'Bearer ' + key,
                                               'Accept': 'application/json'}), timeout=120) as r:
                data = json.load(r)
                STATE['quota'] = r.headers.get('X-CallLimit-Remaining', STATE['quota'])
            break
        except HTTPError as e:
            code = e.code
            e.close()
            if code in (401, 403):
                raise SystemExit(f'HTTP {code} on {endpoint}: key rejected') from None
            if code == 429 or code >= 500:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise SystemExit(f'HTTP {code} on {endpoint} {params}') from None
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(min(2 ** attempt, 30))
    else:
        raise SystemExit(f'{endpoint} {params}: no response after retries -- rerun to resume')
    RAW.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({'request': ident, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                             'data': data}))
    time.sleep(.3)
    return data


def iso(d):
    return f'{d.isoformat()}T00:00:00Z'


def pull_window(endpoint, season, start, end):
    """All rows for [start, end), splitting the window while a response looks truncated."""
    params = {'season': season, 'startDateRange': iso(start), 'endDateRange': iso(end)}
    rows = get(endpoint, params, datetime.combine(end, datetime.min.time(), timezone.utc))
    if len(rows) >= SPLIT_AT:
        if (end - start).days <= 1:
            say(f'  ! {endpoint} {start}: {len(rows)} rows in a single day -- may be truncated')
            return rows
        mid = start + (end - start) / 2
        return pull_window(endpoint, season, start, mid) + pull_window(endpoint, season, mid, end)
    return rows


def pull_season(endpoint, season, today):
    start, last = date(season - 1, 11, 1), min(date(season, 4, 15), today + timedelta(days=2))
    rows = []
    while start < last:
        end = min(start + timedelta(days=WINDOW_DAYS), last)
        rows += pull_window(endpoint, season, start, end)
        start = end
    return rows


def flat(obj, prefix=''):
    out = {}
    for k, v in (obj or {}).items():
        name = f'{prefix}{k}'
        if isinstance(v, dict):
            out.update(flat(v, name + '_'))
        elif not isinstance(v, list):
            out[name] = v
    return out


def game_row(g):
    keep = ['id', 'season', 'seasonType', 'tournament', 'startDate', 'status', 'neutralSite',
            'conferenceGame', 'homeTeamId', 'homeTeam', 'homeConference', 'homePoints',
            'awayTeamId', 'awayTeam', 'awayConference', 'awayPoints', 'venueId']
    return {k: g.get(k) for k in keep}


def line_rows(g):
    base = {'game_id': g.get('gameId', g.get('id')), 'season': g.get('season'), 'startDate': g.get('startDate'),
            'homeTeam': g.get('homeTeam'), 'awayTeam': g.get('awayTeam')}
    return [{**base, **{k: v for k, v in l.items() if not isinstance(v, (dict, list))}}
            for l in g.get('lines') or []]


def box_row(b):
    top = {k: v for k, v in b.items() if not isinstance(v, (dict, list))}
    top.update(flat(b.get('teamStats'), 'team_'))
    top.update(flat(b.get('opponentStats'), 'opp_'))
    return top


def dedupe(df, keys):
    return df.drop_duplicates(subset=keys, keep='last') if len(df) else df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seasons', default='2021,2022,2023,2024,2025,2026,2027')
    ap.add_argument('--push', action='store_true', help='commit + push cbb/data and the report')
    ap.add_argument('--quiet', action='store_true', help='skip the column/provider dump (daily use)')
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    say(f'CBBD backfill {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}')
    G, L, B = [], [], []
    OUT.mkdir(exist_ok=True)
    for s in [int(x) for x in a.seasons.split(',')]:
        g = [game_row(x) for x in pull_season('/games', s, today)]
        l = [r for x in pull_season('/lines', s, today) for r in line_rows(x)]
        b = [box_row(x) for x in pull_season('/games/teams', s, today)]
        gd, ld, bd = (dedupe(pd.DataFrame(g), ['id']), dedupe(pd.DataFrame(l), ['game_id', 'provider']),
                      dedupe(pd.DataFrame(b), ['gameId', 'teamId']))
        # one file per season: daily updates rewrite only the current season's (small) files
        for name, df in (('games', gd), ('lines', ld), ('team_box', bd)):
            if len(df):
                df.to_csv(OUT / f'{name}_{s}.csv.gz', index=False)
        G.append(gd); L.append(ld); B.append(bd)
        st = Counter(gd['status']) if len(gd) else {}
        say(f'{s}: {len(gd)} games {dict(st)} | lines for {ld.game_id.nunique() if len(ld) else 0} games | '
            f'box rows {len(bd)} | calls so far {STATE["calls"]}')
    games, lines, box = pd.concat(G), pd.concat(L), pd.concat(B)
    say(f'TOTAL games {len(games)} | line rows {len(lines)} ({lines.game_id.nunique()} games) | '
        f'box rows {len(box)} ({box.shape[1]} cols)')
    say(f'status values: {dict(Counter(games.status))}')
    say(f'season types: {dict(Counter(games.seasonType))}')
    if len(lines) and not a.quiet:
        say('line providers by season: ' + '; '.join(
            f'{s}: {dict(Counter(grp.provider))}' for s, grp in lines.groupby('season')))
        say(f'line fields: {[c for c in lines.columns]}')
        say(f'spreadOpen filled: {int(lines.spreadOpen.notna().sum()) if "spreadOpen" in lines else 0} of {len(lines)}')
    if not a.quiet:
        say(f'box columns (first 60): {list(box.columns)[:60]}')
    say(f'API calls this run: {STATE["calls"]} (cache hits {STATE["cached"]}) | quota remaining {STATE["quota"]}')
    if not a.quiet:
        REPORT.write_text('\n'.join(LOG) + '\n')
    if a.push:
        subprocess.run(['git', 'add', str(OUT), str(REPORT)], cwd=ROOT, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'CBB backfill data'], cwd=ROOT, check=False)
        subprocess.run(['git', 'pull', '--rebase', '--autostash', '-q'], cwd=ROOT, check=False)
        subprocess.run(['git', 'push', '-q'], cwd=ROOT, check=True)
        print('Pushed cbb/data and cbb/backfill_report.txt')


if __name__ == '__main__':
    main()
