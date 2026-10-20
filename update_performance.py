"""Add graded live weeks to docs/performance.html.

Usage (after grade_week.py has written state/graded/week{N}_graded.csv):
    python update_performance.py          # folds in every graded week found
    python update_performance.py --dry    # print what would change, write nothing

Weeks already on the page when this script first runs (4 and 5) are kept as a frozen
baseline; each graded week found locally is added on top, and rerunning the same week
replaces it instead of double counting. Alpha = "Verified", Beta = "Flat-corrected".
Tier = P4vP4 / G5vG5 / CROSS / OTHER from the 2025 conference map; conference = home team's.
Units are flat -110 (win +0.909, loss -1), matching the existing page.

Also records, per model, a "plays" record (games where |edge| >= MIN_EDGE -- the PICK games on
the board) and a by-edge-size breakdown. These need per-game edges, so they cover graded weeks
only (the frozen baseline weeks have totals but no per-game rows).
"""
import argparse, json, re, glob
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'docs' / 'performance.html'
WIN = 100 / 110
MODELS = {'Verified': 'alpha', 'Flat-corrected': 'beta'}
MIN_EDGE = 1.5  # keep in step with MIN_EDGE in build_board.py
EDGE_BUCKETS = [('No play (<1.5)', 0, 1.5), ('1.5–3', 1.5, 3), ('3–6', 3, 6), ('6+', 6, 1e9)]


def edge_bucket(x):
    a = abs(x)
    for name, lo, hi in EDGE_BUCKETS:
        if lo <= a < hi:
            return name


SIDE_ROWS = ['Favorite', 'Underdog', 'Underdog +10 or more', "Pick'em", 'Home team', 'Away team']


def side_masks(d, tag):
    """Which side each pick is on. The line the pick is taken at is the home spread for a home pick
    and its negative for an away pick: negative = laying points (favorite), positive = getting them."""
    home = d[f'{tag}_pick'] == 'home'
    line = d['market_spread_home'].where(home, -d['market_spread_home'])
    return {'Favorite': line < 0, 'Underdog': line > 0, 'Underdog +10 or more': line >= 10,
            "Pick'em": line == 0, 'Home team': home, 'Away team': ~home}


def by_side(d, tag):
    m = side_masks(d, tag)
    return {row: tally(d.loc[m[row], f'{tag}_result']) for row in SIDE_ROWS if m[row].any()}


def tally(results):
    w, l, p = (int((results == x).sum()) for x in 'WLP')
    n = w + l
    return {'games': w + l + p, 'wins': w, 'losses': l, 'pushes': p,
            'ats_pct': round(w / n, 4) if n else None, 'units': round(w * WIN - l, 2)}


def add(a, b):
    out = {k: a.get(k, 0) + b.get(k, 0) for k in ('games', 'wins', 'losses', 'pushes')}
    n = out['wins'] + out['losses']
    out['ats_pct'] = round(out['wins'] / n, 4) if n else None
    out['units'] = round(a.get('units', 0) + b.get('units', 0), 2)
    return out


def merge_group(base, details, key):
    res = {k: dict(v) for k, v in base.items()}
    for d in details.values():
        for name, t in d[key].items():
            res[name] = add(res[name], t) if name in res else dict(t)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    html = PAGE.read_text(encoding='utf-8')
    i = html.index('const LIVE = ') + len('const LIVE = ')
    live, end = json.JSONDecoder().raw_decode(html[i:])
    end += i

    files = sorted(glob.glob(str(HERE / 'state' / 'graded' / 'week*_graded.csv')))
    if not files:
        raise SystemExit('No state/graded/week*_graded.csv found -- run grade_week.py first.')

    base_weeks = live.get('base_weeks', live['weeks_graded'])
    live['base_weeks'] = base_weeks
    for mk, tag in MODELS.items():
        m = live['models'][mk]
        if 'base' not in m:  # freeze whatever the page already had
            m['base'] = {k: m[k] for k in ('overall', 'by_tier', 'by_conference')}
            m['base_by_week'] = dict(m['by_week'])
        m['detail'] = m.get('detail', {})

    graded_weeks = []
    for f in files:
        wk = int(re.search(r'week(\d+)_graded', f).group(1))
        if wk in base_weeks:
            print(f'skip week {wk}: already in the frozen baseline')
            continue
        df = pd.read_csv(f)
        graded_weeks.append(wk)
        for mk, tag in MODELS.items():
            d = df[df[f'{tag}_result'].isin(['W', 'L', 'P'])]
            conf = {}
            for c, g in d.groupby('home_conf'):
                conf[c] = tally(g[f'{tag}_result'])
            tier = {t: tally(g[f'{tag}_result']) for t, g in d.groupby('tier')}
            eb = d[f'{tag}_edge'].map(edge_bucket)
            by_edge = {b: tally(d.loc[eb == b, f'{tag}_result']) for b, _, _ in EDGE_BUCKETS if (eb == b).any()}
            is_play = d[f'{tag}_edge'].abs() >= MIN_EDGE
            plays = tally(d.loc[is_play, f'{tag}_result'])
            live['models'][mk]['detail'][str(wk)] = {
                'overall': tally(d[f'{tag}_result']), 'by_tier': tier, 'by_conference': conf,
                'by_edge': by_edge, 'plays': plays,
                'by_side': {'plays': by_side(d[is_play], tag), 'all': by_side(d, tag)}}

    for mk in MODELS:
        m = live['models'][mk]
        det = m['detail']
        overall = m['base']['overall']
        for d in det.values():
            overall = add(overall, d['overall'])
        m['overall'] = overall
        m['by_tier'] = merge_group(m['base']['by_tier'], det, 'by_tier')
        m['by_conference'] = merge_group(m['base']['by_conference'], det, 'by_conference')
        m['by_week'] = {**m['base_by_week'], **{w: d['overall'] for w, d in det.items()}}
        # plays / edge-size: only weeks with per-game rows
        ew = {w: d for w, d in det.items() if 'plays' in d}
        plays, all_g, by_edge = {}, {}, {}
        for d in ew.values():
            plays = add(plays, d['plays'])
            all_g = add(all_g, d['overall'])
            for b, t in d['by_edge'].items():
                by_edge[b] = add(by_edge.get(b, {}), t)
        m['plays'] = plays or None
        m['plays_all_games'] = all_g or None
        m['by_edge'] = {b: by_edge[b] for b, _, _ in EDGE_BUCKETS if b in by_edge}
        m['plays_by_week'] = {w: d['plays'] for w, d in ew.items()}
        side = {'plays': {}, 'all': {}}
        for d in ew.values():
            for grp in side:
                for row, t in d.get('by_side', {}).get(grp, {}).items():
                    side[grp][row] = add(side[grp].get(row, {}), t)
        m['by_side'] = {grp: {r: side[grp][r] for r in SIDE_ROWS if r in side[grp]} for grp in side}
    live['edge_weeks'] = sorted(int(w) for w, d in live['models']['Verified']['detail'].items() if 'plays' in d)
    live['min_edge'] = MIN_EDGE

    live['weeks_graded'] = sorted(set(base_weeks) | {int(w) for w in live['models']['Verified']['detail']})
    wk = live['weeks_graded']
    span = f"{wk[0]}&ndash;{wk[-1]}" if len(wk) > 1 else str(wk[0])

    for mk in MODELS:
        o = live['models'][mk]['overall']
        print(f"{mk:15s} {o['wins']}-{o['losses']}-{o['pushes']}  ATS {o['ats_pct']:.1%}  {o['units']:+.2f}u  ({o['games']} games)")
        p = live['models'][mk]['plays']
        if p and p['ats_pct'] is not None:
            print(f"{'  plays only':15s} {p['wins']}-{p['losses']}-{p['pushes']}  ATS {p['ats_pct']:.1%}  {p['units']:+.2f}u  "
                  f"({p['games']} games, edge >= {MIN_EDGE}, weeks {live['edge_weeks']})")
            for b, t in live['models'][mk]['by_edge'].items():
                print(f"{'':17s}{b:>15s}: {t['wins']}-{t['losses']}-{t['pushes']}  {t['units']:+.2f}u")
            sp, sa = live['models'][mk]['by_side']['plays'], live['models'][mk]['by_side']['all']
            print(f"{'':17s}{'side (plays | all games)':>24s}")
            for r in SIDE_ROWS:
                if r in sa:
                    t = sp.get(r, {'wins': 0, 'losses': 0, 'pushes': 0, 'units': 0})
                    u = sa[r]
                    print(f"{'':17s}{r:>24s}: {t['wins']}-{t['losses']}-{t['pushes']} {t['units']:+.2f}u"
                          f"  |  {u['wins']}-{u['losses']}-{u['pushes']} {u['units']:+.2f}u")
    print('weeks on page:', wk)
    if a.dry:
        return

    html = html[:i] + json.dumps(live) + html[end:]
    html = re.sub(r'Weeks? [\d&;a-z\-–]+ tracked so far\.', f'Weeks {span} tracked so far.', html, count=1)
    PAGE.write_text(html, encoding='utf-8')
    print(f'Updated {PAGE}')


if __name__ == '__main__':
    main()
