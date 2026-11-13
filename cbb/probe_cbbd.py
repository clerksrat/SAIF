"""CBB step 1: what does CollegeBasketballData actually have, and what would a backfill cost?

Run on the Pi from the repo folder (uses CFBD_API_KEY from .env -- same key works for CBBD):
    . .venv/bin/activate && python3 cbb/probe_cbbd.py --push

About 5 calls per season, ~30 total, out of the quota shared with CFBD.
Prints a short report, saves it to cbb/probe_report.txt, and with --push commits just that
report so it can be read from GitHub. Raw responses are cached in cbb_data/raw/ (gitignored)
and reused by the backfill, so nothing pulled here is pulled twice.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saif_pull_all import load_env_file  # noqa: E402  (already ran on import: reads .env)

BASE = 'https://api.collegebasketballdata.com'
RAW = ROOT / 'cbb_data' / 'raw'
REPORT = Path(__file__).resolve().parent / 'probe_report.txt'
CALLS = {'n': 0}
QUOTA = {}
LINES = []


def say(s=''):
    print(s, flush=True)
    LINES.append(s)


def get(endpoint, params):
    ident = {'endpoint': endpoint, 'params': params}
    f = RAW / (hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest() + '.json')
    if f.exists():
        return json.loads(f.read_text())['data']
    key = (os.environ.get('CBBD_API_KEY') or os.environ.get('CFBD_API_KEY') or '').strip()
    if not key:
        raise SystemExit('No CFBD_API_KEY in .env')
    url = BASE + endpoint + ('?' + urlencode(params) if params else '')
    for attempt in range(5):
        try:
            CALLS['n'] += 1
            with urlopen(Request(url, headers={'Authorization': 'Bearer ' + key,
                                               'Accept': 'application/json'}), timeout=90) as r:
                data = json.load(r)
                for k, v in r.headers.items():
                    if 'limit' in k.lower() or 'remaining' in k.lower():
                        QUOTA[k] = v
            break
        except HTTPError as e:
            code = e.code
            e.close()
            if code in (401, 403):
                raise SystemExit(f'HTTP {code} on {endpoint}: key not accepted for basketball') from None
            if code == 429 or code >= 500:
                time.sleep(2 ** attempt)
                continue
            say(f'  ! {endpoint} {params}: HTTP {code}')
            return None
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(2 ** attempt)
    else:
        say(f'  ! {endpoint} {params}: no response after retries')
        return None
    RAW.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({'request': ident, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                             'data': data}))
    time.sleep(.3)
    return data


def pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return None


def capped(n):
    return n >= 1000 and n % 500 == 0   # a round count usually means the API truncated the result


def month(s):
    return (s or '')[:7]


def probe_season(season):
    say(f'--- season={season} ---')
    games = get('/games', {'season': season}) or []
    if not games:
        say('  games: none')
        return
    dates = sorted(pick(g, 'startDate', 'start_date') or '' for g in games)
    done = [g for g in games if pick(g, 'homePoints', 'home_points') is not None]
    stype = Counter(pick(g, 'seasonType', 'season_type') for g in games)
    say(f'  games: {len(games)}{"  (ROUND NUMBER - likely capped)" if capped(len(games)) else ""} | '
        f'with scores {len(done)} | {dates[0][:10]} -> {dates[-1][:10]} | types {dict(stype)}')
    say(f'  neutral {sum(bool(pick(g, "neutralSite", "neutral_site")) for g in games)} | '
        f'conf games {sum(bool(pick(g, "conferenceGame", "conference_game")) for g in games)}')

    lines = get('/lines', {'season': season}) or []
    have = [g for g in lines if g.get('lines')]
    prov, spread, opened, total, ml = Counter(), 0, 0, 0, 0
    keys = Counter()
    for g in have:
        for l in g['lines']:
            prov[pick(l, 'provider') or '?'] += 1
            keys.update(l.keys())
        ls = g['lines']
        spread += any(pick(l, 'spread') is not None for l in ls)
        opened += any(pick(l, 'spreadOpen', 'spread_open') is not None for l in ls)
        total += any(pick(l, 'overUnder', 'over_under') is not None for l in ls)
        ml += any(pick(l, 'homeMoneyline', 'home_moneyline') is not None for l in ls)
    say(f'  lines: {len(lines)} rows{"  (ROUND NUMBER - likely capped)" if capped(len(lines)) else ""}, '
        f'{len(have)} games with a line | spread {spread} | opener {opened} | total {total} | ML {ml}')
    say(f'  providers: {dict(prov.most_common(6))}')
    if keys and season == 2025:
        say(f'  line fields: {sorted(keys)}')
    by_m = Counter(month(pick(g, 'startDate', 'start_date')) for g in have)
    all_m = Counter(month(d) for d in dates)
    say('  line coverage by month: ' + ', '.join(f'{m[5:]} {by_m.get(m, 0)}/{n}' for m, n in sorted(all_m.items())))

    # cap check + box score fields: one January window
    yr = int(dates[-1][:4])
    win = {'startDateRange': f'{yr}-01-10T00:00:00Z', 'endDateRange': f'{yr}-01-17T00:00:00Z'}
    wg = get('/games', {'season': season, **win}) or []
    in_full = sum(win['startDateRange'] <= (pick(g, 'startDate', 'start_date') or '') < win['endDateRange'] for g in games)
    say(f'  Jan 10-17 window: {len(wg)} games via date range vs {in_full} in the full-season pull'
        + ('' if len(wg) == in_full else '  <- MISMATCH: full pull is truncated, backfill must go by date range'))
    box = get('/games/teams', {'season': season, **win}) or []
    if box and season == 2025:
        b = box[0]
        ts = b.get('teamStats') or b.get('team_stats') or {}
        say(f'  team box rows (1 wk): {len(box)} | top fields: {sorted(k for k in b if not isinstance(b[k], dict))}')
        say(f'  teamStats fields: {sorted(ts)[:40]}')
    elif box:
        say(f'  team box rows (1 wk): {len(box)}')


def main():
    global SEASONS
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true', help='commit + push cbb/probe_report.txt')
    ap.add_argument('--seasons', default='2022,2023,2024,2025,2026,2027')
    a = ap.parse_args()
    SEASONS = [int(s) for s in a.seasons.split(',')]
    say(f'CBBD probe {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}')
    provs = get('/lines/providers', {}) or []
    say(f'line providers: {[pick(p, "name") for p in provs]}')
    for s in SEASONS:
        probe_season(s)
    say(f'API calls this run: {CALLS["n"]} | quota headers: {QUOTA or "none returned"}')
    REPORT.write_text('\n'.join(LINES) + '\n')
    print(f'\nSaved {REPORT}')
    if a.push:
        subprocess.run(['git', 'add', str(REPORT)], cwd=ROOT, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'CBB probe report'], cwd=ROOT, check=True)
        subprocess.run([str(ROOT / 'publish.sh')], cwd=ROOT, check=True)
        print('Pushed cbb/probe_report.txt')


SEASONS = []
if __name__ == '__main__':
    main()
