"""Closing-line snapshots for CLV.

Cron runs this every 30 minutes. It only calls The Odds API when a game kicks off in the
next WINDOW_MIN minutes, so most runs cost nothing. Each call asks for spreads only
(1 credit) and logs the consensus home spread for the games about to start to
state/closing_lines.csv. grade_week.py uses the last snapshot before kickoff as the close.
The same call also writes every book's quote -- both sides' spread and price, with the book's
own timestamp -- to state/closing_quotes.csv (no extra credits). Alternate closing lines at a
ticket's exact number would need the per-event endpoint; not captured, so pricing an entry at a
different number than the close remains an approximation.

Kickoff times come from the morning pull's saved odds feed
(cfb_fullseason_data_<season>/odds_api/raw_odds.json), so no API call is spent finding them.

    python snapshot_close.py            # normal cron use
    python snapshot_close.py --force    # snapshot now even if nothing is about to kick off
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from saif_pull_all import HERE, ODDS_URL, http_json   # also loads .env
from odds_lines import consensus

WINDOW_MIN = 35   # cron every 30 min -> each game is captured once, 5-35 min before kickoff
FIELDS = ['snapshot_utc', 'odds_api_id', 'commence_time', 'home_team', 'away_team',
          'close_spread_home', 'min_spread_home', 'max_spread_home', 'n_books', 'minutes_to_kick']
QFIELDS = ['snapshot_utc', 'odds_api_id', 'commence_time', 'home_team', 'away_team', 'book', 'book_last_update',
           'home_point', 'home_price', 'away_point', 'away_price', 'minutes_to_kick']


def kickoff(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def known_kickoffs(data_dir):
    import json
    f = data_dir / 'odds_api' / 'raw_odds.json'
    if not f.exists():
        return []
    return [kickoff(g['commence_time']) for g in json.loads(f.read_text(encoding='utf-8')).get('data', [])
            if g.get('commence_time')]


def home_points(game):
    home = game.get('home_team')
    return [float(o['point']) for bk in game.get('bookmakers', []) for m in bk.get('markets', [])
            if m.get('key') == 'spreads' for o in m.get('outcomes', [])
            if o.get('name') == home and o.get('point') is not None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    import os
    key = os.environ.get('ODDS_API_KEY', '').strip()
    if not key:
        raise SystemExit('[close] ODDS_API_KEY not set -- skipped')
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=WINDOW_MIN)
    upcoming = [k for k in known_kickoffs(HERE / f'cfb_fullseason_data_{a.season}') if now < k <= soon]
    if not upcoming and not a.force:
        print(f'[close] {now:%a %H:%MZ}: no kickoffs in the next {WINDOW_MIN} min -- no API call')
        return

    url = ODDS_URL + '?' + urlencode({'apiKey': key, 'regions': 'us', 'markets': 'spreads',
                                      'oddsFormat': 'american'})
    games, headers = http_json(url)
    rows, qrows = [], []
    for g in games:
        k = kickoff(g['commence_time'])
        if not (now < k <= soon) and not (a.force and k > now):
            continue            # already started (in-play lines) or not close yet
        pts = home_points(g)
        if not pts:
            continue
        mins = round((k - now).total_seconds() / 60)
        for bk in g.get('bookmakers', []):
            for m in bk.get('markets', []):
                if m.get('key') != 'spreads':
                    continue
                q = {'snapshot_utc': now.isoformat(timespec='seconds'), 'odds_api_id': g.get('id'),
                     'commence_time': g['commence_time'], 'home_team': g.get('home_team'), 'away_team': g.get('away_team'),
                     'book': bk.get('title') or bk.get('key'), 'book_last_update': m.get('last_update') or bk.get('last_update'),
                     'minutes_to_kick': mins}
                for o in m.get('outcomes', []):
                    sd = 'home' if o.get('name') == g.get('home_team') else 'away'
                    q[f'{sd}_point'], q[f'{sd}_price'] = o.get('point'), o.get('price')
                qrows.append(q)
        rows.append({'snapshot_utc': now.isoformat(timespec='seconds'), 'odds_api_id': g.get('id'),
                     'commence_time': g['commence_time'], 'home_team': g.get('home_team'),
                     'away_team': g.get('away_team'), 'close_spread_home': consensus(pts),
                     'min_spread_home': min(pts), 'max_spread_home': max(pts), 'n_books': len(pts),
                     'minutes_to_kick': round((k - now).total_seconds() / 60)})
    out = HERE / 'state' / 'closing_lines.csv'
    out.parent.mkdir(exist_ok=True)
    new = not out.exists()
    with out.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    qout = HERE / 'state' / 'closing_quotes.csv'
    qnew = not qout.exists()
    with qout.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=QFIELDS)
        if qnew:
            w.writeheader()
        w.writerows(qrows)
    h = {k.lower(): v for k, v in headers.items()}
    print(f"[close] {now:%a %H:%MZ}: logged {len(rows)} games kicking off soon | "
          f"credits remaining {h.get('x-requests-remaining')} (this call {h.get('x-requests-last')})")


if __name__ == '__main__':
    main()
