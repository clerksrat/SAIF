"""SAIF college basketball DRY RUN: one morning job.

    . .venv/bin/activate && python3 cbb/run_cbb.py --push       (what cron runs, ~10:15 ET daily)
    python3 cbb/run_cbb.py --skip-pull                           (rebuild from data already on disk)

Each run:
  1. Tops up this season's CBBD data (games, lines, box scores): ~3-6 calls.
  2. Refits the ratings through yesterday's finals and projects today's games.
  3. Pulls The Odds API NCAAB spreads + totals once (2 credits) = the ENTRY line, i.e. what
     SAIF could have bet this morning. Games the feed doesn't have fall back to CBBD's line.
  4. Logs today's entries to cbb/state/entries.csv. The first run of the day sticks: a rerun
     adds games that weren't logged yet but never moves an entry line.
  5. Grades every logged game that's now final, against CBBD's post-game (closing) line:
     W/L at the entry line, and CLV = points the line moved toward our side, entry -> close.
  6. Writes docs/cbb.html (today's board + the dry-run scorecard) and, with --push, publishes.
Nothing here places or sizes a bet.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from saif_pull_all import http_json  # noqa: E402  (also loads .env)
from snapshot_cbb_close import save_credits  # noqa: E402
from odds_match import Matcher  # noqa: E402
from ratings import SIDES, TOTALS, load, load_prior, read, walk_forward  # noqa: E402
import cbb_page  # noqa: E402

SEASON = 2027
SIDE_PLAY = 3.0          # |side edge| that counts as a play (backtest: line moves our way more as edge grows)
TOTAL_PLAY = 4.0         # |total edge| that counts as a play (backtest vs openers: CLV +0.9 at 4+)
ET = ZoneInfo('America/New_York')
STATE = HERE / 'state'
ENTRIES = STATE / 'entries.csv'
GRADED = STATE / 'graded.csv'
ODDS_URL = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/'
MAX_TIP_GAP_H = 6


def pull_cbbd():
    r = subprocess.run([sys.executable, str(HERE / 'backfill_cbbd.py'), '--seasons', str(SEASON), '--quiet'],
                       cwd=ROOT, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith((str(SEASON), 'API calls'))]
    print('\n'.join(f'[cbbd] {l}' for l in lines) or r.stdout[-500:])
    if r.returncode:
        print(f'[cbbd] FAILED -- building from data on disk\n{r.stderr[-800:]}')


def project(today):
    """Ratings through yesterday's finals; projections for every game dated `today` (ET).
    Sides and totals come from two separately tuned versions of the same model."""
    g = load({SEASON})
    y = today - timedelta(days=1)
    pred, _ = walk_forward(g, SIDES, prior=load_prior(SEASON), final_through=y)
    tot, _ = walk_forward(g, TOTALS, prior=load_prior(SEASON, '_totals'), final_through=y)
    pred['model_total'] = pred.game_id.map(tot.set_index('game_id').model_total)
    pred = pred.merge(g[['id', 'startDate', 'status', 'neutralSite', 'homeConference', 'awayConference']].rename(columns={'id': 'game_id'}),
                      on='game_id')
    pred['tip'] = pd.to_datetime(pred.startDate, utc=True)
    return pred[pred.date == today].copy(), g


def odds_lines(teams, today):
    key = os.environ.get('ODDS_API_KEY', '').strip()
    if not key:
        print('[odds] ODDS_API_KEY not set -- CBBD lines only')
        return {}
    url = ODDS_URL + '?' + urlencode({'apiKey': key, 'regions': 'us', 'markets': 'spreads,totals',
                                      'oddsFormat': 'american'})
    try:
        games, headers = http_json(url)
    except RuntimeError as e:
        print(f'[odds] FAILED: {e} -- CBBD lines only')
        return {}
    raw = ROOT / 'cbb_data' / 'odds'
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f'{datetime.now(timezone.utc):%Y-%m-%dT%H%MZ}.json').write_text(json.dumps(games))
    save_credits(headers, 'cbb morning board')
    h = {k.lower(): v for k, v in headers.items()}
    print(f"[odds] {len(games)} NCAAB games | credits remaining {h.get('x-requests-remaining')} "
          f"(this call {h.get('x-requests-last')})")
    m = Matcher(teams)
    out, unmapped = [], set()
    for g in games:
        home, away = m.team(g['home_team']), m.team(g['away_team'])
        for raw_name, t in ((g['home_team'], home), (g['away_team'], away)):
            if t is None:
                unmapped.add(raw_name)
        if not home or not away:
            continue
        sp, tot = [], []
        for bk in g.get('bookmakers', []):
            for mk in bk.get('markets', []):
                for o in mk.get('outcomes', []):
                    if mk['key'] == 'spreads' and o.get('name') == g['home_team'] and o.get('point') is not None:
                        sp.append(float(o['point']))
                    elif mk['key'] == 'totals' and o.get('name') == 'Over' and o.get('point') is not None:
                        tot.append(float(o['point']))
        out.append({'home': home, 'away': away, 'tip': pd.Timestamp(g['commence_time']),
                    'spread': float(np.median(sp)) if sp else np.nan,
                    'total': float(np.median(tot)) if tot else np.nan, 'books': len(g.get('bookmakers', []))})
    if unmapped:
        print(f'[odds] {len(unmapped)} team names not mapped (add to cbb/odds_match.py ALIASES; '
              f'many are non-D1): {sorted(unmapped)[:25]}')
    return out


def cbbd_lines():
    """Current CBBD line per game (median across books) -- fallback entry line, and the CLOSE after tip."""
    l = read('lines', {SEASON})
    if l.empty:
        return pd.DataFrame(columns=['spread', 'total', 'spread_open', 'total_open'])
    return l.groupby('game_id').agg(spread=('spread', 'median'), total=('overUnder', 'median'),
                                    spread_open=('spreadOpen', 'median'), total_open=('overUnderOpen', 'median'))


def attach_entry_lines(today_games, odds, cb):
    rows = []
    for r in today_games.itertuples():
        hit = None
        for o in odds:
            if abs((o['tip'] - r.tip).total_seconds()) / 3600 > MAX_TIP_GAP_H:
                continue
            if (o['home'], o['away']) == (r.home, r.away):
                hit = (o, 1)
            elif (o['home'], o['away']) == (r.away, r.home):      # listed reversed (neutral site)
                hit = (o, -1)
            if hit:
                break
        spread = total = np.nan
        src = ''
        if hit and not np.isnan(hit[0]['spread']):
            spread, total, src = hit[1] * hit[0]['spread'], hit[0]['total'], f"Odds API ({hit[0]['books']} books)"
        elif r.game_id in cb.index and not np.isnan(cb.at[r.game_id, 'spread']):
            spread, total, src = cb.at[r.game_id, 'spread'], cb.at[r.game_id, 'total'], 'CBBD'
        if hit and np.isnan(total) and not np.isnan(hit[0]['total']):
            total = hit[0]['total']
        rows.append({'entry_spread': spread, 'entry_total': total, 'entry_src': src})
    return pd.concat([today_games.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def log_entries(board, now):
    cols = ['date', 'logged_utc', 'game_id', 'tip_utc', 'home', 'away', 'neutral', 'model_margin',
            'model_total', 'entry_spread', 'entry_total', 'entry_src', 'side_edge', 'total_edge']
    b = board[board.entry_spread.notna() & (board.tip > now) & (board.status != 'final')].copy()
    b['logged_utc'] = now.isoformat(timespec='seconds')
    b['tip_utc'] = b.tip.dt.strftime('%Y-%m-%dT%H:%MZ')
    b['neutral'] = b['loc'] == 0
    b['side_edge'] = (b.model_margin + b.entry_spread).round(2)
    b['total_edge'] = (b.model_total - b.entry_total).round(2)
    b = b[cols].round({'model_margin': 2, 'model_total': 1})
    old = pd.read_csv(ENTRIES) if ENTRIES.exists() else pd.DataFrame(columns=cols)
    new = b[~b.game_id.isin(old.game_id)]
    STATE.mkdir(exist_ok=True)
    pd.concat([old, new], ignore_index=True).to_csv(ENTRIES, index=False)
    print(f'[entries] logged {len(new)} new games for {board.date.iloc[0] if len(board) else "-"} '
          f'({len(b) - len(new)} already logged earlier today)')


def own_closes(teams):
    """Timestamped closes from snapshot_cbb_close.py, keyed to CBBD names: list of
    (home, away, tip, snapshot, spread_home, total, minutes_to_tip)."""
    f = STATE / 'closing_lines.csv'
    if not f.exists():
        return []
    c = pd.read_csv(f)
    if c.empty:
        return []
    m = Matcher(teams)
    c['tip'] = pd.to_datetime(c.commence_time, utc=True, format='ISO8601')
    c['snap'] = pd.to_datetime(c.snapshot_utc, utc=True, format='ISO8601')
    c = c[c.snap < c.tip]
    c['home'] = c.home_team.map(m.team)
    c['away'] = c.away_team.map(m.team)
    c = c.dropna(subset=['home', 'away'])
    return list(c[['home', 'away', 'tip', 'snap', 'close_spread_home', 'close_total', 'minutes_to_tip']]
                .itertuples(index=False, name=None))


def own_close_for(closes, home, away, tip):
    best = None
    for h, a, t, snap, sp, tot, mins in closes:
        if abs((t - tip).total_seconds()) / 3600 > MAX_TIP_GAP_H:
            continue
        sign = 1 if (h, a) == (home, away) else -1 if (h, a) == (away, home) else 0
        if sign and (best is None or snap > best[0]):
            best = (snap, sign * sp if pd.notna(sp) else np.nan, tot, mins)
    return best


def grade(games, cb, teams=None):
    if not ENTRIES.exists():
        return pd.DataFrame()
    e = pd.read_csv(ENTRIES)
    fin = games[games.status == 'final'].set_index('id')
    e = e[e.game_id.isin(fin.index)].copy()
    if e.empty:
        return e
    e['home_pts'] = e.game_id.map(fin.homePoints)
    e['away_pts'] = e.game_id.map(fin.awayPoints)
    e['margin'] = e.home_pts - e.away_pts
    e['actual_total'] = e.home_pts + e.away_pts
    for c in ('spread', 'total', 'spread_open', 'total_open'):
        e[f'close_{c}' if not c.endswith('open') else c] = e.game_id.map(cb[c]) if c in cb else np.nan
    side = np.sign(e.side_edge)
    e['side_pick'] = np.where(side > 0, 'home', np.where(side < 0, 'away', ''))
    e['side_result'] = np.sign((e.margin + e.entry_spread) * side)            # 1 W, -1 L, 0 P
    e['side_clv'] = np.where(side > 0, e.entry_spread - e.close_spread, e.close_spread - e.entry_spread)
    ts = np.sign(e.total_edge)
    e['total_pick'] = np.where(ts > 0, 'over', np.where(ts < 0, 'under', ''))
    e['total_result'] = np.sign((e.actual_total - e.entry_total) * ts)
    e['total_clv'] = np.where(ts > 0, e.close_total - e.entry_total, e.entry_total - e.close_total)
    # Additive: timestamped close from our own pre-tip snapshots (CBBD close above stays the scorecard basis)
    closes = own_closes(teams) if teams is not None else []
    own = [own_close_for(closes, r.home, r.away, pd.Timestamp(r.tip_utc)) if closes else None for r in e.itertuples()]
    e['own_close_spread'] = [o[1] if o else np.nan for o in own]
    e['own_close_total'] = [o[2] if o else np.nan for o in own]
    e['own_close_min_before'] = [o[3] if o else np.nan for o in own]
    e['side_clv_own'] = np.where(side > 0, e.entry_spread - e.own_close_spread, e.own_close_spread - e.entry_spread)
    e['total_clv_own'] = np.where(ts > 0, e.own_close_total - e.entry_total, e.entry_total - e.own_close_total)
    e.to_csv(GRADED, index=False)
    print(f'[grade] {len(e)} games graded')
    return e


def publish():
    subprocess.run(['git', 'add', 'docs/cbb.html', 'cbb/state', f'cbb/data'], cwd=ROOT, check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode == 0:
        print('No changes to publish.')
        return
    subprocess.run(['git', 'commit', '-q', '-m', f'CBB dry board {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}'],
                   cwd=ROOT, check=True)
    r = subprocess.run([str(ROOT / 'publish.sh')], cwd=ROOT)
    if r.returncode:
        raise SystemExit('publish failed -- see message above')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--skip-pull', action='store_true')
    ap.add_argument('--skip-odds', action='store_true')
    ap.add_argument('--date', help='board date YYYY-MM-DD (ET); default today')
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    today = datetime.strptime(a.date, '%Y-%m-%d').date() if a.date else now.astimezone(ET).date()
    print(f'=== CBB dry run {now.astimezone(ET):%a %Y-%m-%d %H:%M %Z} | board date {today} ===')
    if a.push:
        subprocess.run([str(ROOT / 'publish.sh'), 'sync'], cwd=ROOT, check=False)
    if not a.skip_pull:
        pull_cbbd()
    todays, games = project(today)
    cb = cbbd_lines()
    teams = sorted(set(games.homeTeam) | set(games.awayTeam))
    odds = [] if a.skip_odds else odds_lines(teams, today)
    board = attach_entry_lines(todays, odds, cb)
    n_odds = int(board.entry_src.str.startswith('Odds').sum()) if len(board) else 0
    print(f'[board] {len(board)} D1 games today | entry line from Odds API {n_odds}, CBBD '
          f'{int((board.entry_src == "CBBD").sum()) if len(board) else 0}, none {int((board.entry_src == "").sum()) if len(board) else 0}')
    log_entries(board, now)
    try:                                   # frozen v1 shadow test -- additive; never blocks the live board
        import shadow
        shadow.log_shadow(today, now)
    except Exception as e:  # noqa: BLE001
        print(f'[shadow v1] skipped: {type(e).__name__}: {e}')
    graded = grade(games, cb, teams)
    entries = pd.read_csv(ENTRIES) if ENTRIES.exists() else pd.DataFrame()
    if len(entries) and len(board):   # show the LOGGED entry line, not a later rerun's line
        logged = entries.set_index('game_id')
        for c, src in (('entry_spread', 'entry_spread'), ('entry_total', 'entry_total'), ('entry_src', 'entry_src')):
            m = board.game_id.isin(logged.index)
            board.loc[m, c] = board.loc[m, 'game_id'].map(logged[src])
    html = cbb_page.render(board, graded, entries, today, now, SIDE_PLAY, TOTAL_PLAY)
    (ROOT / 'docs' / 'cbb.html').write_text(html, encoding='utf-8')
    print(f'Wrote docs/cbb.html')
    if a.push:
        publish()


if __name__ == '__main__':
    main()
