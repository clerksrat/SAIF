"""SAIF combined weekly pull: one run, one results ZIP.

Runs, in order:
  1. CFBD collector (cfb_collect_fullseason.pull) -- game features, scores, lines
  2. SportsDataIO InjuredPlayers + TeamsBasic     -- injury cards on the board
  3. The Odds API NCAAF odds (spreads/totals/h2h) -- second market-line source

Put this file in the same folder as cfb_collect_fullseason.py. Standard
library only (same as the collector), so it also runs on a bare GitHub
Actions runner.

Keys (environment variables, never saved):
  CFBD_API_KEY            required
  SPORTSDATAIO_API_KEY    optional -- injuries step is skipped with a warning if absent
  ODDS_API_KEY            optional -- odds step is skipped with a warning if absent

Stale-cache fix: the collector caches every response forever, keyed by
endpoint+params. For the live season that silently freezes /games, so scores
never arrive on reruns. This script deletes cached 2026 responses before the
CFBD step (historical years stay cached, so reruns are still fast).

Usage:
    python saif_pull_all.py                 # everything
    python saif_pull_all.py --skip-injuries # CFBD + odds only
    python saif_pull_all.py --skip-odds
    python saif_pull_all.py --season 2026
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cfb_collect_fullseason as collector  # noqa: E402

SDIO_BASE = 'https://api.sportsdata.io/v3/cfb/scores/json'
ODDS_URL = 'https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds/'


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value), encoding='utf-8')
    tmp.replace(path)


def http_json(url, headers=None, retries=4):
    """GET JSON; returns (data, response_headers). Never prints the URL (keys live in it)."""
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={'Accept': 'application/json', **(headers or {})}), timeout=60) as r:
                return json.load(r), dict(r.headers)
        except HTTPError as e:
            code = e.code
            e.close()
            if code in (401, 403):
                raise RuntimeError(f'HTTP {code}: key rejected or feed not enabled.') from None
            if code == 429 or code >= 500:
                time.sleep(min(2 ** attempt, 16))
                continue
            raise RuntimeError(f'HTTP {code}.') from None
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(min(2 ** attempt, 16))
    raise RuntimeError('Retry limit reached.')


# ---------------------------------------------------------------- step 0/1: CFBD
def purge_live_season_cache(out, season):
    raw = Path(out) / 'raw'
    removed = 0
    if raw.exists():
        for p in raw.glob('*.json'):
            try:
                req = json.loads(p.read_text(encoding='utf-8')).get('request', {})
            except (ValueError, OSError):
                continue
            if str(req.get('params', {}).get('year')) == str(season):
                p.unlink()
                removed += 1
    print(f'[cache] removed {removed} cached {season} responses so scores/lines refetch fresh', flush=True)


def run_cfbd(out, season):
    purge_live_season_cache(out, season)
    args = argparse.Namespace(
        out=str(out), years=[2022, 2023, 2024, 2025, season], start_week=0, end_week=14,
        prior_weight=4, providers=['Bovada', 'ESPN Bet'], offline=False,
        cache_source=str(HERE / 'cfb_expanded_data'))
    collector.pull(args)


# ---------------------------------------------------------------- step 2: injuries
def run_injuries(out):
    key = os.environ.get('SPORTSDATAIO_API_KEY', '').strip()
    if not key:
        print('[injuries] SPORTSDATAIO_API_KEY not set -- skipped', flush=True)
        return
    hdr = {'Ocp-Apim-Subscription-Key': key}
    base = Path(out) / 'sportsdataio' / 'raw'
    for name, endpoint in (('injured_players', 'InjuredPlayers'), ('teams', 'TeamsBasic')):
        data, _ = http_json(f'{SDIO_BASE}/{endpoint}', hdr)
        # same wrapper shape the board's injury injector already reads
        write_json(base / f'{name}.json', {'retrieved_at_utc': now_utc(),
                                           'endpoint': f'scores/json/{endpoint}', 'data': data})
        print(f'[injuries] {endpoint}: {len(data)} records', flush=True)


# ---------------------------------------------------------------- step 3: odds
def flatten_odds(games):
    rows = []
    for g in games:
        home, away = g.get('home_team'), g.get('away_team')
        spreads, totals, hml, aml = [], [], [], []
        books = g.get('bookmakers', [])
        for bk in books:
            for m in bk.get('markets', []):
                for o in m.get('outcomes', []):
                    if m['key'] == 'spreads' and o.get('name') == home and o.get('point') is not None:
                        spreads.append(o['point'])
                    elif m['key'] == 'totals' and o.get('name') == 'Over' and o.get('point') is not None:
                        totals.append(o['point'])
                    elif m['key'] == 'h2h':
                        (hml if o.get('name') == home else aml).append(o.get('price'))
        med = lambda xs: round(statistics.median(xs), 2) if xs else ''
        rows.append({
            'odds_api_id': g.get('id'), 'commence_time': g.get('commence_time'),
            'home_team': home, 'away_team': away,
            'median_spread_home': med(spreads), 'min_spread_home': min(spreads) if spreads else '',
            'max_spread_home': max(spreads) if spreads else '',
            'median_total': med(totals), 'median_ml_home': med(hml), 'median_ml_away': med(aml),
            'n_books': len(books)})
    return rows


def run_odds(out, regions='us', markets='h2h,spreads,totals'):
    key = os.environ.get('ODDS_API_KEY', '').strip()
    if not key:
        print('[odds] ODDS_API_KEY not set -- skipped', flush=True)
        return
    url = ODDS_URL + '?' + urlencode({'apiKey': key, 'regions': regions, 'markets': markets,
                                      'oddsFormat': 'american'})
    games, headers = http_json(url)
    folder = Path(out) / 'odds_api'
    write_json(folder / 'raw_odds.json', {'retrieved_at_utc': now_utc(), 'regions': regions,
                                          'markets': markets, 'data': games})
    rows = flatten_odds(games)
    folder.mkdir(parents=True, exist_ok=True)
    if rows:
        with (folder / 'odds_api_lines.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    h = {k.lower(): v for k, v in headers.items()}
    print(f"[odds] {len(rows)} games | credits used {h.get('x-requests-used')} "
          f"remaining {h.get('x-requests-remaining')} this call {h.get('x-requests-last')}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--skip-cfbd', action='store_true')
    ap.add_argument('--skip-injuries', action='store_true')
    ap.add_argument('--skip-odds', action='store_true')
    a = ap.parse_args()

    out = HERE / f'cfb_fullseason_data_{a.season}'
    if not a.skip_cfbd:
        run_cfbd(out, a.season)
    out.mkdir(parents=True, exist_ok=True)
    for label, skip, fn in (('injuries', a.skip_injuries, lambda: run_injuries(out)),
                            ('odds', a.skip_odds, lambda: run_odds(out))):
        if skip:
            continue
        try:  # a side-feed failing must not throw away the CFBD pull
            fn()
        except (RuntimeError, ValueError, OSError) as e:
            print(f'[{label}] FAILED: {e} -- continuing without it', flush=True)
    collector.package(out)
    print('DONE. One ZIP covers CFBD + injuries + odds.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        raise SystemExit('Stopped. Rerun to resume cached progress.') from None
