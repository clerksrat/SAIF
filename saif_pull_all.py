"""SAIF combined weekly pull: one run, one results ZIP.

Runs, in order:
  1. CFBD collector (cfb_collect_fullseason.pull) -- game features, scores, lines
  2. SportsDataIO InjuredPlayers + TeamsBasic     -- injury cards on the board
  3. The Odds API NCAAF odds (spreads/totals/h2h) -- second market-line source

Put this file in the same folder as cfb_collect_fullseason.py. Standard
library only (same as the collector), so it also runs on a bare GitHub
Actions runner.

Keys: put them in a .env file beside this script (see .env.example) or export them.\n  Never saved by this script; .env is gitignored.
  CFBD_API_KEY            required
  SPORTSDATAIO_API_KEY    optional -- injuries step is skipped with a warning if absent
  ODDS_API_KEY            optional -- odds step is skipped with a warning if absent

Cache: the collector caches every response forever, keyed by endpoint+params.
Prior seasons are pulled once and never again. For the live season this script
deletes only what can still change (the schedule/scores, plus stats and lines for
weeks not yet final) -- finished weeks stay cached. See purge_live_season_cache.

Usage:
    python saif_pull_all.py                 # everything
    python saif_pull_all.py --skip-injuries # CFBD + odds only
    python saif_pull_all.py --skip-odds
    python saif_pull_all.py --season 2026
    python saif_pull_all.py --week 9        # what run_week.sh uses: live season only through week 9
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


def load_env_file(path=HERE / '.env'):
    """Read KEY=value lines from .env beside this script (real environment variables win).
    Tolerates UTF-8 BOM / UTF-16 (PowerShell and Notepad write these), 'export ' prefixes and quotes."""
    if not Path(path).exists():
        print(f'[env] no .env found at {path} -- using environment variables only', flush=True)
        return
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-16'):
        try:
            text = raw.decode(enc)
            if '=' in text:
                break
        except UnicodeError:
            continue
    else:
        text = raw.decode('utf-8', 'ignore')
    found = []
    for line in text.splitlines():
        line = line.strip().lstrip('\ufeff')
        if line.lower().startswith('export '):
            line = line[7:].strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key, value)
            found.append(key)
    print(f'[env] loaded {path.name if hasattr(path, "name") else path}: keys found = {found or "NONE"}', flush=True)

load_env_file()
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
# A finished week's CFBD data is kept once it was pulled this long after the week's last kickoff
# (stats and lines are final by then). Anything newer is refetched.
STATS_FINAL_AFTER_H = 24
LINES_FINAL_AFTER_H = 6


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def purge_live_season_cache(out, season):
    """Delete only the cached live-season responses that can still change.

    Prior seasons are never touched (cached forever). For the live season:
      /games schedule                  -> always refetched (scores, kickoff changes)
      stats with endWeek=k             -> kept once pulled 24h+ after the last kickoff of weeks <= k
      /lines for week k                -> kept once pulled 6h+ after week k's last kickoff
      anything else for the season     -> refetched
    With no cached schedule yet (first run), every live-season response is refetched."""
    raw = Path(out) / 'raw'
    if not raw.exists():
        print(f'[cache] no cache yet -- first run pulls everything', flush=True)
        return
    files = []
    for p in raw.glob('*.json'):
        try:
            saved = json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        req = saved.get('request', {})
        if str(req.get('params', {}).get('year')) == str(season):
            files.append((p, saved))
    last_kick = {}   # week -> latest kickoff that week, from the previously cached schedule
    for _, saved in files:
        if saved['request'].get('endpoint') == '/games':
            for g in saved.get('data', []):
                k = _ts(g.get('startDate'))
                if k and g.get('week') is not None:
                    last_kick[g['week']] = max(k, last_kick.get(g['week'], k))
    removed = kept = 0
    for p, saved in files:
        req, params = saved['request'], saved['request'].get('params', {})
        got = _ts(saved.get('retrieved_at_utc'))
        endpoint = req.get('endpoint')
        keep = False
        if got and last_kick:
            if endpoint in ('/stats/season/advanced', '/stats/season') and params.get('endWeek') is not None:
                k = int(params['endWeek'])
                kicks = [t for w, t in last_kick.items() if w <= k]
                keep = bool(kicks) and got.timestamp() >= max(kicks).timestamp() + STATS_FINAL_AFTER_H * 3600
            elif endpoint == '/lines' and params.get('week') is not None:
                t = last_kick.get(int(params['week']))
                keep = t is not None and got.timestamp() >= t.timestamp() + LINES_FINAL_AFTER_H * 3600
        if keep:
            kept += 1
        else:
            p.unlink()
            removed += 1
    print(f'[cache] {season}: kept {kept} finished-week responses, refetching {removed} live ones', flush=True)


def run_cfbd(out, season, max_week=None):
    """max_week: only build feature rows through this week (the board's week). Later weeks
    can't be scored yet anyway, and skipping them avoids ~3 API calls per future week."""
    purge_live_season_cache(out, season)
    args = argparse.Namespace(
        out=str(out), years=[2022, 2023, 2024, 2025, season], start_week=0, end_week=14,
        prior_weight=4, providers=['Bovada', 'ESPN Bet'], offline=False,
        cache_source=str(HERE / 'cfb_expanded_data'), max_week=max_week)
    collector.pull(args)
    try:
        calls = json.loads((Path(out) / 'run_summary.json').read_text())['network_requests_this_run']
        print(f'[cfbd] {calls} API calls this run', flush=True)
    except (OSError, ValueError, KeyError):
        pass


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


# ---------------------------------------------------------------- step 2b: QB box scores
def run_qb_box(out, season, max_week=15):
    """Per-game passing box scores (CFBD /games/players) -> QB1 availability flags. ~1-2 calls/run.
    Weeks already saved are skipped, except the newest one (it may have been pulled mid-week)."""
    key = os.environ.get('CFBD_API_KEY', '').strip()
    if not key:
        print('[qb] CFBD_API_KEY not set -- skipped', flush=True)
        return
    box = Path(out) / 'qb_box'
    box.mkdir(parents=True, exist_ok=True)
    have = sorted(int(p.stem.rsplit('_w', 1)[1]) for p in box.glob(f'passing_{season}_w*.json'))
    newest = have[-1] if have else 0
    for wk in range(1, max_week + 1):
        f = box / f'passing_{season}_w{wk:02d}.json'
        if f.exists() and wk != newest:
            continue
        q = urlencode({'year': season, 'week': wk, 'seasonType': 'regular', 'category': 'passing'})
        data, _ = http_json('https://api.collegefootballdata.com/games/players?' + q, {'Authorization': f'Bearer {key}'})
        if not data:
            break
        write_json(f, data)
        print(f'[qb] week {wk}: {len(data)} games', flush=True)


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
    ap.add_argument('--week', type=int, help='board week: build live-season features only through this week')
    a = ap.parse_args()

    out = HERE / f'cfb_fullseason_data_{a.season}'
    if not a.skip_cfbd:
        run_cfbd(out, a.season, a.week)
    out.mkdir(parents=True, exist_ok=True)
    for label, skip, fn in (('injuries', a.skip_injuries, lambda: run_injuries(out)),
                            ('qb box scores', a.skip_cfbd, lambda: run_qb_box(out, a.season)),
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
