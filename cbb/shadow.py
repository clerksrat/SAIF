"""Frozen v1 shadow logging (prospective test). Additive: never changes the live board (A0).

Called from run_cbb.py each morning. For every game on today's board that hasn't tipped, appends one
row to cbb/state/shadow_entries.csv (first logging per game sticks):
  * A0, A1 and C1 projections (sides + totals) and A1's sigma_outcome, from models/frozen_v1.json
  * the actual morning prices at Jeff's books -- FanDuel, DraftKings, BetRivers -- point AND odds,
    with the feed's timestamp (executable prices, review item 5)
  * CBBD's opener (median of books, and DraftKings') as an UNTIMED opener-window proxy
Grading, CLV vs our timestamped pre-tip close, and probability recalibration are applied later from
these logged inputs and the frozen parameters, so nothing here depends on future data.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from odds_match import Matcher
from ratings import SIDES, TOTALS, load, load_prior, read, walk_forward

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FROZEN = HERE / 'models' / 'frozen_v1.json'
OUT = HERE / 'state' / 'shadow_entries.csv'
BOOKS = {'fanduel': 'fd', 'draftkings': 'dk', 'betrivers': 'br'}
FIELDS = (['date', 'logged_utc', 'feed_utc', 'model_version', 'game_id', 'tip_utc', 'home', 'away', 'neutral',
           'A0_margin', 'A1_margin', 'C1_margin', 'sig_o_side', 'A0_total', 'A1_total', 'C1_total', 'sig_o_total',
           'cbbd_open_spread', 'cbbd_open_total', 'cbbd_dk_open_spread', 'cbbd_dk_open_total']
          + [f'{b}_{f}' for b in BOOKS.values() for f in ('spread_home', 'spread_home_price', 'spread_away_price',
                                                            'total', 'over_price', 'under_price')])


def _a1(pred, q, poss, cal, sig, kind):
    m = pred
    a1 = cal[0] * m + cal[1] * m * abs(m) if kind == 'side' else cal[0] + cal[1] * m
    so = np.sqrt(sig['sigma_e2'] * (poss / 100) ** 2 * q + sig['s2'] * poss / 70)
    return a1, so


def latest_feed():
    files = sorted(f for f in (ROOT / 'cbb_data' / 'odds').glob('*.json') if f.name != 'credits.json')
    if not files:
        return None, []
    f = files[-1]
    stamp = datetime.strptime(f.stem, '%Y-%m-%dT%H%MZ').replace(tzinfo=timezone.utc)
    return stamp, json.loads(f.read_text())


def book_prices(game, home_name):
    """Per-book home spread / prices and total / prices from one Odds API game."""
    out = {}
    for bk in game.get('bookmakers', []):
        tag = BOOKS.get(bk.get('key'))
        if not tag:
            continue
        for mk in bk.get('markets', []):
            for o in mk.get('outcomes', []):
                if mk['key'] == 'spreads':
                    if o.get('name') == home_name:
                        out[f'{tag}_spread_home'], out[f'{tag}_spread_home_price'] = o.get('point'), o.get('price')
                    else:
                        out[f'{tag}_spread_away_price'] = o.get('price')
                elif mk['key'] == 'totals':
                    if o.get('name') == 'Over':
                        out[f'{tag}_total'], out[f'{tag}_over_price'] = o.get('point'), o.get('price')
                    elif o.get('name') == 'Under':
                        out[f'{tag}_under_price'] = o.get('price')
    return out


def log_shadow(today, now, season=2027):
    fz = json.loads(FROZEN.read_text())
    g = load({season})
    y = today - timedelta(days=1)
    ps, _ = walk_forward(g, SIDES, prior=load_prior(season), final_through=y, with_var=True)
    pt, _ = walk_forward(g, TOTALS, prior=load_prior(season, '_totals'), final_through=y, with_var=True)
    ps, pt = ps[ps.date == today], pt[pt.date == today].set_index('game_id')
    info = g.set_index('id')
    feed_utc, feed = latest_feed()
    teams = sorted(set(g.homeTeam) | set(g.awayTeam))
    m = Matcher(teams)
    l = read('lines', {season})
    op = l.groupby('game_id').agg(o_sp=('spreadOpen', 'median'), o_tot=('overUnderOpen', 'median'))
    dk = l[l.provider == 'Draft Kings'].set_index('game_id')
    done = set(pd.read_csv(OUT).game_id) if OUT.exists() else set()
    rows = []
    for r in ps.itertuples():
        tip = pd.Timestamp(info.at[r.game_id, 'startDate']).tz_convert('UTC')
        if r.game_id in done or tip <= now or info.at[r.game_id, 'status'] == 'final' or r.game_id not in pt.index:
            continue
        ks, kt = fz['kinds']['side'], fz['kinds']['total']
        a1s, sos = _a1(r.model_margin, r.q_margin, r.model_poss, ks['A1_calibration'], ks['A1_sigma'], 'side')
        t = pt.loc[r.game_id]
        a1t, sot = _a1(t.model_total, t.q_total, t.model_poss, kt['A1_calibration'], kt['A1_sigma'], 'total')
        o_sp = op.o_sp.get(r.game_id, np.nan)
        o_tot = op.o_tot.get(r.game_id, np.nan)
        # C1 is defined relative to the opener (v = -spread for sides)
        c1s = (-o_sp + ks['C1']['intercept'] + ks['C1']['weight'] * (a1s + o_sp)) if pd.notna(o_sp) else np.nan
        c1t = (o_tot + kt['C1']['intercept'] + kt['C1']['weight'] * (a1t - o_tot)) if pd.notna(o_tot) else np.nan
        row = {'date': today.isoformat(), 'logged_utc': now.isoformat(timespec='seconds'),
               'feed_utc': feed_utc.isoformat(timespec='seconds') if feed_utc else '', 'model_version': fz['version'],
               'game_id': r.game_id, 'tip_utc': tip.strftime('%Y-%m-%dT%H:%MZ'), 'home': r.home, 'away': r.away,
               'neutral': r.loc == 0, 'A0_margin': round(r.model_margin, 2), 'A1_margin': round(a1s, 2),
               'C1_margin': round(c1s, 2) if pd.notna(c1s) else '', 'sig_o_side': round(sos, 2),
               'A0_total': round(t.model_total, 1), 'A1_total': round(a1t, 1),
               'C1_total': round(c1t, 1) if pd.notna(c1t) else '', 'sig_o_total': round(sot, 2),
               'cbbd_open_spread': o_sp, 'cbbd_open_total': o_tot,
               'cbbd_dk_open_spread': dk.spreadOpen.get(r.game_id, np.nan) if 'spreadOpen' in dk else np.nan,
               'cbbd_dk_open_total': dk.overUnderOpen.get(r.game_id, np.nan) if 'overUnderOpen' in dk else np.nan}
        for gm in feed:                                     # this morning's per-book prices
            h, a = m.team(gm['home_team']), m.team(gm['away_team'])
            gt = pd.Timestamp(gm['commence_time'])
            if abs((gt - tip).total_seconds()) > 6 * 3600:
                continue
            if (h, a) == (r.home, r.away):
                row.update(book_prices(gm, gm['home_team']))
                break
            if (h, a) == (r.away, r.home):                  # feed lists it reversed: read prices for OUR home team
                row.update(book_prices(gm, gm['away_team']))
                break
        rows.append(row)
    OUT.parent.mkdir(exist_ok=True)
    new = not OUT.exists()
    with OUT.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        if new:
            w.writeheader()
        w.writerows(rows)
    priced = sum(1 for x in rows if x.get('dk_spread_home') is not None or x.get('fd_spread_home') is not None)
    print(f'[shadow v1] logged {len(rows)} games ({priced} with FanDuel/DraftKings/BetRivers prices)')
