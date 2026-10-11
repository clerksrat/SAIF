"""Add graded live weeks to docs/performance.html.

Usage (after grade_week.py has written state/graded/week{N}_graded.csv):
    python update_performance.py          # folds in every graded week found
    python update_performance.py --dry    # print what would change, write nothing

Weeks already on the page when this script first runs (4 and 5) are kept as a frozen
baseline; each graded week found locally is added on top, and rerunning the same week
replaces it instead of double counting. Alpha = "Verified", Beta = "Flat-corrected".
Tier = P4vP4 / G5vG5 / CROSS / OTHER from the 2025 conference map; conference = home team's.
Units are flat -110 (win +0.909, loss -1), matching the existing page.
"""
import argparse, json, re, glob
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'docs' / 'performance.html'
WIN = 100 / 110
MODELS = {'Verified': 'alpha', 'Flat-corrected': 'beta'}


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
            live['models'][mk]['detail'][str(wk)] = {
                'overall': tally(d[f'{tag}_result']), 'by_tier': tier, 'by_conference': conf}

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

    live['weeks_graded'] = sorted(set(base_weeks) | {int(w) for w in live['models']['Verified']['detail']})
    wk = live['weeks_graded']
    span = f"{wk[0]}&ndash;{wk[-1]}" if len(wk) > 1 else str(wk[0])

    for mk in MODELS:
        o = live['models'][mk]['overall']
        print(f"{mk:15s} {o['wins']}-{o['losses']}-{o['pushes']}  ATS {o['ats_pct']:.1%}  {o['units']:+.2f}u  ({o['games']} games)")
    print('weeks on page:', wk)
    if a.dry:
        return

    html = html[:i] + json.dumps(live) + html[end:]
    html = re.sub(r'Weeks? [\d&;a-z\-–]+ tracked so far\.', f'Weeks {span} tracked so far.', html, count=1)
    PAGE.write_text(html, encoding='utf-8')
    print(f'Updated {PAGE}')


if __name__ == '__main__':
    main()
