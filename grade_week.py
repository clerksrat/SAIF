"""Grade a week's SAIF board against final scores.

Usage (from the saif_local folder, same place you run build_board.py):
    python grade_week.py 6
    python grade_week.py 6 --season 2026

Reads  state/week{N}_scored.pkl   (the frozen board: model margins + lines at pull time)
Fetches final scores from CFBD /games (needs CFBD_API_KEY in .env or the environment)
Writes state/graded/week{N}_graded.csv  (one row per completed game)
       state/graded/summary.csv         (one row per graded week, replaced on rerun)

Grading uses the line stored on the board at pull time, NOT the closing line,
so this is ATS-vs-pull-line, not CLV. Standard flat -110 payout (win +0.909, loss -1).
Convention: market_spread is the HOME spread (negative = home favored); a positive edge
means the model likes the home side. Home covers when actual_margin + market_spread > 0.
"""
import argparse, json, math, os, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import pandas as pd

HERE = Path(__file__).resolve().parent
WIN_PAYOUT = 100 / 110


def load_env_file(path=HERE / '.env'):
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def fetch_finals(season, week):
    key = os.environ.get('CFBD_API_KEY', '').strip()
    if not key:
        raise SystemExit('CFBD_API_KEY not set (put it in .env next to this script).')
    url = 'https://api.collegefootballdata.com/games?' + urlencode(
        {'year': season, 'week': week, 'seasonType': 'regular'})
    req = Request(url, headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    with urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def grade_side(edge, cover_margin):
    """edge>0 -> pick home. Returns (pick, result, units)."""
    if edge is None or (isinstance(edge, float) and math.isnan(edge)) or edge == 0:
        return None, None, None
    pick = 'home' if edge > 0 else 'away'
    c = cover_margin if pick == 'home' else -cover_margin
    if c > 0:
        return pick, 'W', WIN_PAYOUT
    if c < 0:
        return pick, 'L', -1.0
    return pick, 'P', 0.0


P4 = {'ACC', 'Big Ten', 'Big 12', 'SEC'}
G5 = {'American Athletic', 'Conference USA', 'Mid-American', 'Mountain West', 'Sun Belt'}


def conf_map():
    f = HERE / 'models' / 'cfbd_conferences_2022-2025.csv'
    if not f.exists():
        return {}
    c = pd.read_csv(f)
    return c[c.season == 2025].set_index('team')['conference'].to_dict()


def tier_of(conf):
    return 'P4' if conf in P4 else 'G5' if conf in G5 else 'other'


def matchup_tier(hc, ac):
    h, a = tier_of(hc), tier_of(ac)
    if h == 'other' or a == 'other':
        return 'OTHER'
    return 'P4vP4' if h == a == 'P4' else 'G5vG5' if h == a == 'G5' else 'CROSS'


def bucket(e):
    a = abs(e)
    return '<2' if a < 2 else '2-4' if a < 4 else '4-7' if a < 7 else '7+'


def summarize(df, tag, edge_col):
    g = df[df[f'{tag}_result'].isin(['W', 'L', 'P'])]
    w, l, p = (g[f'{tag}_result'] == x for x in 'WLP')
    n_dec = int(w.sum() + l.sum())
    units = float(g[f'{tag}_units'].sum())
    return {
        'model': tag, 'games': len(g), 'W': int(w.sum()), 'L': int(l.sum()), 'P': int(p.sum()),
        'ats_pct': round(w.sum() / n_dec * 100, 1) if n_dec else None,
        'units_flat_110': round(units, 2),
        'roi_pct': round(units / len(g) * 100, 1) if len(g) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('week', type=int)
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--state-dir', default=str(HERE / 'state'))
    ap.add_argument('--finals-json', help='offline: use a saved CFBD /games JSON instead of the API')
    a = ap.parse_args()

    load_env_file()
    state = Path(a.state_dir)
    pkl = state / f'week{a.week}_scored.pkl'
    if not pkl.exists():
        raise SystemExit(f'{pkl} not found -- run build_board.py for week {a.week} first.')
    board = pd.read_pickle(pkl)

    games = json.load(open(a.finals_json)) if a.finals_json else fetch_finals(a.season, a.week)
    fin = {}
    for g in games:
        if g.get('completed') is True and g.get('homePoints') is not None and g.get('awayPoints') is not None:
            fin[g['id']] = (g['homePoints'], g['awayPoints'])

    cmap = conf_map()
    rows = []
    for _, r in board.iterrows():
        gid = int(r['game_id'])
        if gid not in fin:
            continue
        hp, ap_ = fin[gid]
        actual = hp - ap_
        spread = r['market_spread']
        if spread is None or (isinstance(spread, float) and math.isnan(spread)):
            continue
        cover = actual + spread  # >0 means home covers
        row = {
            'game_id': gid, 'away': r['away_team'], 'home': r['home_team'],
            'home_pts': hp, 'away_pts': ap_, 'actual_margin': actual,
            'home_conf': cmap.get(r['home_team']), 'away_conf': cmap.get(r['away_team']),
            'tier': matchup_tier(cmap.get(r['home_team']), cmap.get(r['away_team'])),
            'market_spread_home': spread, 'home_cover_margin': round(cover, 1),
            'alpha_margin': r['independent_margin'], 'beta_margin': r['beta_margin'],
            'alpha_edge': round(r['independent_edge'], 2), 'beta_edge': round(r['beta_edge'], 2),
        }
        for tag, col in (('alpha', 'independent_edge'), ('beta', 'beta_edge')):
            pick, res, units = grade_side(r[col], cover)
            row[f'{tag}_pick'], row[f'{tag}_result'], row[f'{tag}_units'] = pick, res, units
            row[f'{tag}_bucket'] = bucket(r[col])
        row['alpha_err'] = abs(actual - r['independent_margin'])
        row['beta_err'] = abs(actual - r['beta_margin'])
        row['market_err'] = abs(actual - (-spread))
        rows.append(row)

    if not rows:
        raise SystemExit('No completed games matched yet -- try again after games finish.')
    df = pd.DataFrame(rows)
    out = state / 'graded'
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f'week{a.week}_graded.csv', index=False)

    print(f"\nWeek {a.week}: graded {len(df)} of {len(board)} board games (final scores in)")
    summ = []
    for tag, col in (('alpha', 'alpha_edge'), ('beta', 'beta_edge')):
        s = summarize(df, tag, col)
        s['mae'] = round(df[f'{tag}_err'].mean(), 2)
        s['week'] = a.week
        summ.append(s)
        print(f"  {tag.upper():5s} ATS {s['W']}-{s['L']}-{s['P']} ({s['ats_pct']}%)  "
              f"flat -110: {s['units_flat_110']:+.2f}u  ROI {s['roi_pct']}%  MAE {s['mae']}")
    print(f"  MARKET MAE {round(df['market_err'].mean(), 2)} (pull-time line)")

    print('\n  ATS by edge size (Alpha / Beta):')
    for tag in ('alpha', 'beta'):
        t = df.groupby(f'{tag}_bucket')[f'{tag}_result'].agg(
            W=lambda x: (x == 'W').sum(), L=lambda x: (x == 'L').sum(), P=lambda x: (x == 'P').sum())
        for b in ['<2', '2-4', '4-7', '7+']:
            if b in t.index:
                print(f"    {tag:5s} {b:>4s}: {t.loc[b,'W']}-{t.loc[b,'L']}-{t.loc[b,'P']}")

    sf = out / 'summary.csv'
    new = pd.DataFrame(summ)
    new['market_mae'] = round(df['market_err'].mean(), 2)
    if sf.exists():
        old = pd.read_csv(sf)
        old = old[old['week'] != a.week]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(sf, index=False)
    print(f"\nSaved {out / f'week{a.week}_graded.csv'} and {sf}")
    print('Note: graded against the line stored at pull time, not the closing line (no CLV yet).')


if __name__ == '__main__':
    main()
