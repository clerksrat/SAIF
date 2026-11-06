"""Timestamped closing-line snapshots for college basketball, with a credit guard.

Cron runs this every 15 minutes, 11:00-23:45 ET. It calls The Odds API only when
  * a game on today's board tips within TIP_WINDOW_MIN minutes, and
  * the last snapshot was at least MIN_GAP_MIN minutes ago, and
  * the last known credit balance is above CREDIT_FLOOR (football's board and Saturday
    closes always keep enough).
Each call = spreads + totals, US books = 2 credits, whatever the number of games.
Kickoff times come from this morning's saved odds feed, so deciding costs nothing.

Writes cbb/state/closing_lines.csv (one row per game per snapshot, games tipping within the
next MIN_GAP_MIN + TIP_WINDOW_MIN minutes, i.e. before the next possible snapshot). Grading
uses each game's last snapshot before tip as the timestamped close, alongside CBBD's close.
Per-book DraftKings / Bovada numbers are kept for the line audit.

    python3 cbb/snapshot_cbb_close.py            # cron
    python3 cbb/snapshot_cbb_close.py --force    # snapshot now (ignores window/gap; still respects the floor)
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from saif_pull_all import http_json  # noqa: E402  (also loads .env)

ODDS_URL = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/'
ODDS_DIR = ROOT / 'cbb_data' / 'odds'
CREDITS = ODDS_DIR / 'credits.json'
OUT = HERE / 'state' / 'closing_lines.csv'
TIP_WINDOW_MIN = 30
MIN_GAP_MIN = 45
CREDIT_FLOOR = 150
FIELDS = ['snapshot_utc', 'odds_api_id', 'commence_time', 'home_team', 'away_team', 'minutes_to_tip',
          'close_spread_home', 'close_total', 'n_books', 'dk_spread_home', 'bov_spread_home',
          'dk_total', 'bov_total', 'fd_spread_home', 'br_spread_home', 'fd_total', 'br_total']


def credits():
    try:
        return json.loads(CREDITS.read_text())
    except (OSError, ValueError):
        return {}


def save_credits(headers, source):
    h = {k.lower(): v for k, v in headers.items()}
    if h.get('x-requests-remaining') is None:
        return None
    rec = {'remaining': float(h['x-requests-remaining']), 'used': float(h.get('x-requests-used') or 0),
           'checked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': source}
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    CREDITS.write_text(json.dumps(rec))
    return rec['remaining']


def todays_tips(now):
    """Kickoffs from the latest saved morning feed (written by run_cbb.py)."""
    files = sorted(f for f in ODDS_DIR.glob('*.json') if f.name != 'credits.json')
    if not files:
        return []
    games = json.loads(files[-1].read_text())
    return [datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00')) for g in games if g.get('commence_time')]


def last_snapshot():
    if not OUT.exists():
        return None
    last = None
    with OUT.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            last = row['snapshot_utc']
    return datetime.fromisoformat(last) if last else None


def book_point(game, book, market, name):
    for bk in game.get('bookmakers', []):
        if bk.get('key') == book:
            for mk in bk.get('markets', []):
                if mk.get('key') == market:
                    for o in mk.get('outcomes', []):
                        if o.get('name') == name and o.get('point') is not None:
                            return float(o['point'])
    return None


def all_points(game, market, name):
    return [float(o['point']) for bk in game.get('bookmakers', []) for mk in bk.get('markets', [])
            if mk.get('key') == market for o in mk.get('outcomes', [])
            if o.get('name') == name and o.get('point') is not None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    stamp = f'[cbb close] {now:%a %H:%MZ}'
    c = credits()
    if c and c.get('remaining', 1e9) < CREDIT_FLOOR:
        print(f'{stamp}: PAUSED -- {c["remaining"]:.0f} credits left (floor {CREDIT_FLOOR}); '
              f'upgrade the Odds API plan or wait for the monthly reset')
        return
    soon = now + timedelta(minutes=TIP_WINDOW_MIN)
    due = [t for t in todays_tips(now) if now < t <= soon]
    last = last_snapshot()
    gap_ok = last is None or (now - last) >= timedelta(minutes=MIN_GAP_MIN)
    if not a.force and (not due or not gap_ok):
        why = 'no tips in the next %d min' % TIP_WINDOW_MIN if not due else f'last snapshot {last:%H:%MZ}, < {MIN_GAP_MIN} min ago'
        print(f'{stamp}: {why} -- no API call')
        return
    key = os.environ.get('ODDS_API_KEY', '').strip()
    if not key:
        raise SystemExit(f'{stamp}: ODDS_API_KEY not set')
    url = ODDS_URL + '?' + urlencode({'apiKey': key, 'regions': 'us', 'markets': 'spreads,totals',
                                      'oddsFormat': 'american'})
    games, headers = http_json(url)
    left = save_credits(headers, 'cbb close snapshot')
    horizon = now + timedelta(minutes=MIN_GAP_MIN + TIP_WINDOW_MIN)   # until the next snapshot can cover it
    rows = []
    for g in games:
        tip = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
        if not (now < tip <= horizon):
            continue
        sp = all_points(g, 'spreads', g['home_team'])
        tot = all_points(g, 'totals', 'Over')
        if not sp and not tot:
            continue
        rows.append({'snapshot_utc': now.isoformat(timespec='seconds'), 'odds_api_id': g.get('id'),
                     'commence_time': g['commence_time'], 'home_team': g['home_team'], 'away_team': g['away_team'],
                     'minutes_to_tip': round((tip - now).total_seconds() / 60),
                     'close_spread_home': float(np.median(sp)) if sp else '',
                     'close_total': float(np.median(tot)) if tot else '', 'n_books': len(g.get('bookmakers', [])),
                     'dk_spread_home': book_point(g, 'draftkings', 'spreads', g['home_team']),
                     'bov_spread_home': book_point(g, 'bovada', 'spreads', g['home_team']),
                     'dk_total': book_point(g, 'draftkings', 'totals', 'Over'),
                     'bov_total': book_point(g, 'bovada', 'totals', 'Over'),
                     'fd_spread_home': book_point(g, 'fanduel', 'spreads', g['home_team']),
                     'br_spread_home': book_point(g, 'betrivers', 'spreads', g['home_team']),
                     'fd_total': book_point(g, 'fanduel', 'totals', 'Over'),
                     'br_total': book_point(g, 'betrivers', 'totals', 'Over')})
    OUT.parent.mkdir(exist_ok=True)
    if OUT.exists():                       # older file without the FanDuel/BetRivers columns: widen it once
        with OUT.open(encoding='utf-8') as f:
            header = f.readline().strip().split(',')
        if header != FIELDS:
            import pandas as pd
            pd.read_csv(OUT).reindex(columns=FIELDS).to_csv(OUT, index=False)
    new = not OUT.exists()
    with OUT.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f'{stamp}: logged {len(rows)} games tipping within {MIN_GAP_MIN + TIP_WINDOW_MIN} min | '
          f'credits remaining {left:.0f}' if left is not None else f'{stamp}: logged {len(rows)} games')


if __name__ == '__main__':
    main()
